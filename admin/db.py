"""
Modul Akses Basis Data (Database Layer)
Menyediakan eksekusi query SQL dengan parameterized query untuk keamanan data.
Mendukung pencarian karyawan, pencatatan absensi, dan manajemen master data karyawan.
Dilengkapi mekanisme fallback otomatis ke file JSON jika MariaDB sedang offline.
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import pymysql
    import pymysql.cursors
    HAVE_PYMYSQL = True
except ImportError:
    pymysql = None
    HAVE_PYMYSQL = False

import config

logger = logging.getLogger("AttendanceServer")


def get_db_connection() -> Optional[Any]:
    """
    Membuka dan mengembalikan koneksi aktif ke basis data MariaDB.
    Mengembalikan None jika pymysql belum terpasang atau database offline.
    """
    if not HAVE_PYMYSQL or pymysql is None:
        return None
    try:
        connection = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=3,
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Exception as err:
        logger.debug(f"[Database] Gagal terhubung ke basis data: {err}")
        return None


def init_database_tables() -> bool:
    """
    Menginisialisasi basis data dan tabel langsung melalui SQL tanpa CLI eksternal.
    Membuat database attendance_db, tabel employees, dan attendance jika belum ada.
    """
    if not HAVE_PYMYSQL or pymysql is None:
        logger.info("[Database] Driver pymysql belum terpasang di sistem. Menggunakan penyimpanan data JSON.")
        return False

    try:
        # Langkah 1: Hubungkan ke server MariaDB untuk memastikan database sudah dibuat
        server_conn = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=3
        )
        with server_conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        server_conn.close()

        # Langkah 2: Hubungkan ke database dan buat struktur tabel
        db_conn = get_db_connection()
        if not db_conn:
            return False

        with db_conn.cursor() as cursor:
            # Tabel master karyawan (dengan kolom NIK)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `employees` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `employee_id` VARCHAR(50) NOT NULL UNIQUE,
                    `nik` VARCHAR(50) DEFAULT NULL,
                    `name` VARCHAR(100) NOT NULL,
                    `rfid_uid` VARCHAR(50) DEFAULT NULL UNIQUE,
                    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
                    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX `idx_employees_nik` (`nik`),
                    INDEX `idx_employees_rfid` (`rfid_uid`),
                    INDEX `idx_employees_active` (`is_active`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            # Migrasi skema jika tabel lama belum memiliki kolom nik
            try:
                cursor.execute("ALTER TABLE `employees` ADD COLUMN IF NOT EXISTS `nik` VARCHAR(50) DEFAULT NULL AFTER `employee_id`;")
                cursor.execute("UPDATE `employees` SET `nik` = `employee_id` WHERE `nik` IS NULL OR `nik` = '';")
            except Exception as e:
                logger.debug(f"[Database] Migrasi kolom nik: {e}")

            # Tabel riwayat absensi
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `attendance` (
                    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
                    `employee_id` VARCHAR(50) NOT NULL,
                    `captured_at` DATETIME NOT NULL,
                    `image_path` VARCHAR(255) NOT NULL,
                    `attendance_status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
                    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT `fk_attendance_employee`
                        FOREIGN KEY (`employee_id`)
                        REFERENCES `employees` (`employee_id`)
                        ON DELETE RESTRICT
                        ON UPDATE CASCADE,
                    INDEX `idx_attendance_emp_date` (`employee_id`, `captured_at`),
                    INDEX `idx_attendance_captured_at` (`captured_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            # Isi data awal karyawan dari employees.json jika tabel masih kosong
            cursor.execute("SELECT COUNT(*) AS total FROM `employees`;")
            count = cursor.fetchone().get("total", 0)
            if count == 0 and config.EMPLOYEES_FILE.exists():
                logger.info("[Database] Mengimpor data karyawan awal dari employees.json...")
                with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                    emp_data = json.load(f)
                    for key, val in emp_data.items():
                        emp_id = val.get("employee_id", key)
                        nik = val.get("nik") or emp_id
                        name = val.get("name", "")
                        rfid = key if key != emp_id else None
                        cursor.execute("""
                            INSERT INTO `employees` (`employee_id`, `nik`, `name`, `rfid_uid`, `is_active`)
                            VALUES (%s, %s, %s, %s, 1)
                            ON DUPLICATE KEY UPDATE `nik` = VALUES(`nik`), `name` = VALUES(`name`), `rfid_uid` = VALUES(`rfid_uid`);
                        """, (emp_id, nik, name, rfid))

        db_conn.close()
        logger.info("[Database] Skema MariaDB berhasil diinisialisasi.")
        return True
    except Exception as err:
        logger.warning(f"[Database] Catatan inisialisasi basis data: {err}")
        return False


def lookup_employee(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Mencari data karyawan berdasarkan nomor UID RFID, NIK, atau Employee ID.
    Mendukung variasi awalan reader (seperti dreizehn/13) dan fallback ke employees.json.
    """
    clean_id = (identifier or "").strip()
    if not clean_id:
        return None

    # Bentuk daftar variasi kemungkinan ID yang dikirim oleh RFID reader
    candidate_ids = [clean_id]
    lower_id = clean_id.lower()
    if "dreizehn" in lower_id:
        c1 = lower_id.replace("dreizehn", "13")
        c2 = lower_id.replace("dreizehn", "")
        c3 = c2.lstrip("0")
        for c in [c1, c2, c3]:
            if c and c not in candidate_ids:
                candidate_ids.append(c)
    elif clean_id.startswith("13"):
        c_dz = "dreizehn" + clean_id[2:]
        if c_dz not in candidate_ids:
            candidate_ids.append(c_dz)

    # 1. Coba pencarian di MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                placeholders = ", ".join(["%s"] * len(candidate_ids))
                sql = f"""
                    SELECT employee_id, nik, name, rfid_uid, is_active
                    FROM employees
                    WHERE (rfid_uid IN ({placeholders}) OR employee_id IN ({placeholders}) OR nik IN ({placeholders}))
                      AND is_active = 1
                    LIMIT 1
                """
                params = tuple(candidate_ids * 3)
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row:
                    nik_val = row.get("nik") or row["employee_id"]
                    logger.info(f"[Database] Karyawan ditemukan di MariaDB: {row['name']} (NIK: {nik_val})")
                    return {
                        "employee_id": row["employee_id"],
                        "nik": nik_val,
                        "name": row["name"],
                        "rfid_uid": row.get("rfid_uid") or row["employee_id"],
                        "source": "mariadb"
                    }
                else:
                    logger.info(f"[Database] Karyawan tidak ditemukan di MariaDB untuk kandidat {candidate_ids}. Mencoba fallback...")
        except Exception as err:
            logger.warning(f"[Database] Terjadi kendala query di MariaDB: {err}. Beralih ke JSON...")
        finally:
            conn.close()

    # 2. Fallback: cari di berkas lokal data/employees.json
    logger.info(f"[Fallback] Mencari data di employees.json untuk kandidat: {candidate_ids}")
    if config.EMPLOYEES_FILE.exists():
        try:
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for cand in candidate_ids:
                if cand in data:
                    emp = data[cand]
                    emp_id = emp.get("employee_id", cand)
                    return {
                        "employee_id": emp_id,
                        "nik": emp.get("nik") or emp_id,
                        "name": emp.get("name", "Unknown"),
                        "rfid_uid": cand if cand != emp_id else emp.get("rfid_uid", cand),
                        "source": "json_fallback"
                    }
                for key, emp in data.items():
                    emp_id = emp.get("employee_id")
                    emp_nik = emp.get("nik")
                    if emp_id == cand or emp_nik == cand or key == cand:
                        return {
                            "employee_id": emp_id or cand,
                            "nik": emp_nik or emp_id or cand,
                            "name": emp.get("name", "Unknown"),
                            "rfid_uid": key if key != emp_id else emp.get("rfid_uid", key),
                            "source": "json_fallback"
                        }
        except Exception as e:
            logger.error(f"[Fallback] Error reading employees.json: {e}")

    return None


def record_attendance(employee_id: str, captured_at: datetime.datetime, image_path: str, status: str = "SUCCESS") -> bool:
    """
    Menyimpan data riwayat absensi ke tabel MariaDB.
    Selalu mencadangkan catatan absensi ke file data/attendance.json.
    """
    db_success = False

    # 1. Simpan ke MariaDB menggunakan parameterized query
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO attendance (employee_id, captured_at, image_path, attendance_status)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    employee_id,
                    captured_at.strftime("%Y-%m-%d %H:%M:%S"),
                    str(image_path).replace("\\", "/"),
                    status
                ))
                db_success = True
                logger.info(f"[Database] Data absensi tersimpan di MariaDB: {employee_id} ({captured_at})")
        except Exception as err:
            logger.warning(f"[Database] Gagal menyimpan absensi ke MariaDB: {err}")
        finally:
            conn.close()

    # 2. Cadangkan riwayat ke file lokal data/attendance.json
    try:
        attendance_file = config.DATA_DIR / "attendance.json"
        records = []
        if attendance_file.exists():
            with open(attendance_file, "r", encoding="utf-8") as f:
                try:
                    records = json.load(f)
                except Exception:
                    records = []

        records.append({
            "employee_id": employee_id,
            "captured_at": captured_at.isoformat(timespec="seconds"),
            "image_path": str(image_path).replace("\\", "/"),
            "attendance_status": status,
            "db_synced": db_success
        })

        with open(attendance_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    except Exception as e:
        logger.error(f"[Storage] Gagal menulis cadangan attendance.json: {e}")

    return True


def get_attendance_records(limit: int = 100, date_filter: Optional[str] = None, search: Optional[str] = None) -> list:
    """
    Mengambil riwayat absensi beserta foto, nama, dan NIK karyawan.
    Mendukung filter tanggal dan pencarian.
    Mengutamakan MariaDB dan fallback ke data/attendance.json.
    """
    records = []

    # 1. Ambil dari MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                sql = """
                    SELECT a.id, a.employee_id, e.nik, COALESCE(e.name, a.employee_id) AS name,
                           a.captured_at, a.image_path, a.attendance_status
                    FROM attendance a
                    LEFT JOIN employees e ON a.employee_id = e.employee_id
                """
                params = []
                where_clauses = []

                if date_filter:
                    where_clauses.append("DATE(a.captured_at) = %s")
                    params.append(date_filter)

                if search:
                    s = f"%{search.strip()}%"
                    where_clauses.append("(e.name LIKE %s OR e.nik LIKE %s OR a.employee_id LIKE %s)")
                    params.extend([s, s, s])

                if where_clauses:
                    sql += " WHERE " + " AND ".join(where_clauses)

                sql += " ORDER BY a.captured_at DESC LIMIT %s;"
                params.append(limit)

                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall()
                for r in rows:
                    cap_at = r["captured_at"]
                    cap_str = cap_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(cap_at, (datetime.datetime, datetime.date)) else str(cap_at)
                    records.append({
                        "id": r["id"],
                        "employee_id": r["employee_id"],
                        "nik": r.get("nik") or r["employee_id"],
                        "name": r.get("name") or r["employee_id"],
                        "captured_at": cap_str,
                        "image_path": str(r.get("image_path") or "").replace("\\", "/"),
                        "status": r.get("attendance_status") or "SUCCESS",
                        "source": "mariadb"
                    })
                return records
        except Exception as err:
            logger.warning(f"[Database] Gagal mengambil riwayat absensi dari MariaDB: {err}")
        finally:
            conn.close()

    # 2. Fallback: Baca dari data/attendance.json
    attendance_file = config.DATA_DIR / "attendance.json"
    if attendance_file.exists():
        try:
            with open(attendance_file, "r", encoding="utf-8") as f:
                json_records = json.load(f)

            # Muat mapping karyawan untuk mengisi NIK & Nama
            emp_map = {}
            if config.EMPLOYEES_FILE.exists():
                try:
                    with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                        emp_raw = json.load(f)
                        for k, v in emp_raw.items():
                            emp_map[v.get("employee_id", k)] = v
                            if "nik" in v:
                                emp_map[v["nik"]] = v
                except Exception:
                    pass

            for idx, item in enumerate(reversed(json_records)):
                emp_id = item.get("employee_id", "")
                cap_at = item.get("captured_at", "")
                emp = emp_map.get(emp_id, {})
                emp_name = emp.get("name", emp_id)
                emp_nik = emp.get("nik", emp_id)

                if date_filter and not cap_at.startswith(date_filter):
                    continue

                if search:
                    s_lower = search.lower()
                    if (s_lower not in emp_name.lower() and
                        s_lower not in emp_nik.lower() and
                        s_lower not in emp_id.lower()):
                        continue

                records.append({
                    "id": idx + 1,
                    "employee_id": emp_id,
                    "nik": emp_nik,
                    "name": emp_name,
                    "captured_at": cap_at.replace("T", " "),
                    "image_path": str(item.get("image_path") or "").replace("\\", "/"),
                    "status": item.get("attendance_status", "SUCCESS"),
                    "source": "json"
                })

                if len(records) >= limit:
                    break

        except Exception as err:
            logger.error(f"[Fallback] Gagal membaca attendance.json: {err}")

    return records


def get_all_employees() -> list:
    """
    Mengambil seluruh daftar karyawan aktif dari MariaDB atau fallback dari file JSON.
    Mengembalikan list berisi dict: [{'employee_id', 'nik', 'name', 'rfid_uid', 'is_active', 'source'}]
    """
    employees = []

    # 1. Ambil dari MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                sql = "SELECT employee_id, nik, name, rfid_uid, is_active FROM employees WHERE is_active = 1 ORDER BY id ASC;"
                cursor.execute(sql)
                rows = cursor.fetchall()
                for r in rows:
                    employees.append({
                        "employee_id": r["employee_id"],
                        "nik": r.get("nik") or r["employee_id"],
                        "name": r["name"],
                        "rfid_uid": r.get("rfid_uid") or "-",
                        "is_active": bool(r.get("is_active", 1)),
                        "source": "mariadb"
                    })
                return employees
        except Exception as err:
            logger.warning(f"[Database] Terjadi kendala saat mengambil data karyawan dari MariaDB: {err}")
        finally:
            conn.close()

    # 2. Fallback: baca dari data/employees.json
    if config.EMPLOYEES_FILE.exists():
        try:
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, val in data.items():
                    emp_id = val.get("employee_id", key)
                    nik = val.get("nik") or emp_id
                    name = val.get("name", "Unknown")
                    rfid = key if key != emp_id else val.get("rfid_uid", key)
                    employees.append({
                        "employee_id": emp_id,
                        "nik": nik,
                        "name": name,
                        "rfid_uid": rfid,
                        "is_active": True,
                        "source": "json"
                    })
        except Exception as err:
            logger.error(f"[Fallback] Gagal membaca berkas employees.json: {err}")

    return employees


def add_employee(employee_id: str, name: str, rfid_uid: str, nik: str = None) -> tuple:
    """
    Menambahkan karyawan baru ke MariaDB dan menyinkronkannya ke employees.json.
    Mendukung NIK resmi karyawan. Mengembalikan (success: bool, message: str).
    """
    clean_nik = (nik or employee_id).strip()
    emp_id = (employee_id or clean_nik).strip().upper()
    emp_name = name.strip()
    rfid = rfid_uid.strip()

    if not emp_name or not rfid or not (clean_nik or emp_id):
        return False, "Semua bidang (NIK / ID Karyawan, Nama, RFID UID) wajib diisi."

    # 1. Simpan ke MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Periksa apakah ID, NIK, atau RFID sudah terdaftar
                cursor.execute(
                    "SELECT employee_id, nik, rfid_uid FROM employees WHERE employee_id = %s OR rfid_uid = %s OR (nik IS NOT NULL AND nik = %s) LIMIT 1;",
                    (emp_id, rfid, clean_nik)
                )
                existing = cursor.fetchone()
                if existing:
                    if existing.get("employee_id") == emp_id:
                        return False, f"ID Karyawan '{emp_id}' sudah terdaftar!"
                    if existing.get("nik") == clean_nik:
                        return False, f"NIK '{clean_nik}' sudah digunakan oleh karyawan lain!"
                    if existing.get("rfid_uid") == rfid:
                        return False, f"Nomor RFID UID '{rfid}' sudah digunakan oleh karyawan lain!"

                cursor.execute(
                    "INSERT INTO employees (employee_id, nik, name, rfid_uid, is_active) VALUES (%s, %s, %s, %s, 1);",
                    (emp_id, clean_nik, emp_name, rfid)
                )
                logger.info(f"[Database] Karyawan berhasil ditambahkan ke MariaDB: {emp_name} (NIK: {clean_nik})")
        except Exception as err:
            logger.warning(f"[Database] Gagal menambahkan karyawan ke MariaDB: {err}")
        finally:
            conn.close()

    # 2. Sinkronkan ke berkas lokal data/employees.json
    try:
        data = {}
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}

        data[rfid] = {
            "employee_id": emp_id,
            "nik": clean_nik,
            "name": emp_name
        }

        with open(config.EMPLOYEES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"[Storage] Berkas employees.json berhasil disinkronkan: {emp_name} ({emp_id})")
    except Exception as e:
        logger.error(f"[Storage] Gagal menyinkronkan data ke employees.json: {e}")

    return True, f"Karyawan '{emp_name}' ({emp_id}) berhasil disimpan ke database!"


def delete_employee(employee_id: str) -> tuple:
    """
    Menghapus karyawan dari MariaDB dan employees.json.
    Mengembalikan (success: bool, message: str).
    """
    emp_id = employee_id.strip().upper()
    if not emp_id:
        return False, "Employee ID tidak valid."

    # 1. Hapus dari MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM employees WHERE employee_id = %s;", (emp_id,))
                logger.info(f"[Database] Karyawan dihapus dari MariaDB: {emp_id}")
        except Exception as err:
            logger.warning(f"[Database] Gagal menghapus karyawan dari MariaDB: {err}")
        finally:
            conn.close()

    # 2. Hapus dari data/employees.json
    try:
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            keys_to_remove = [k for k, v in data.items() if v.get("employee_id") == emp_id or k == emp_id]
            for k in keys_to_remove:
                del data[k]

            with open(config.EMPLOYEES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"[Storage] Karyawan {emp_id} berhasil dihapus dari employees.json")
    except Exception as e:
        logger.error(f"[Storage] Gagal menghapus karyawan dari employees.json: {e}")

    return True, f"Karyawan '{emp_id}' berhasil dihapus."


def update_employee(employee_id: str, name: str, nik: str, rfid_uid: str = None) -> tuple:
    """
    Memperbarui NIK, Nama, dan RFID UID karyawan di MariaDB dan employees.json.
    Mengembalikan (success: bool, message: str).
    """
    emp_id = (employee_id or "").strip().upper()
    emp_name = (name or "").strip()
    clean_nik = (nik or "").strip()
    rfid = (rfid_uid or "").strip()

    if not emp_id:
        return False, "ID Karyawan tidak valid."
    if not emp_name:
        return False, "Nama karyawan tidak boleh kosong."
    if not clean_nik:
        return False, "NIK karyawan tidak boleh kosong."

    # 1. Update di MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Periksa apakah NIK atau RFID baru bertabrakan dengan karyawan lain
                cursor.execute(
                    "SELECT employee_id FROM employees WHERE (nik = %s OR (rfid_uid = %s AND %s != '')) AND employee_id != %s LIMIT 1;",
                    (clean_nik, rfid, rfid, emp_id)
                )
                conflict = cursor.fetchone()
                if conflict:
                    return False, f"NIK '{clean_nik}' atau RFID '{rfid}' sudah digunakan oleh karyawan lain ({conflict.get('employee_id')})!"

                if rfid:
                    cursor.execute(
                        "UPDATE employees SET name = %s, nik = %s, rfid_uid = %s WHERE employee_id = %s;",
                        (emp_name, clean_nik, rfid, emp_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE employees SET name = %s, nik = %s WHERE employee_id = %s;",
                        (emp_name, clean_nik, emp_id)
                    )
                logger.info(f"[Database] Karyawan {emp_id} berhasil diperbarui di MariaDB (NIK: {clean_nik}, Nama: {emp_name})")
        except Exception as err:
            logger.warning(f"[Database] Gagal memperbarui karyawan di MariaDB: {err}")
        finally:
            conn.close()

    # 2. Update di data/employees.json
    try:
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            found_key = None
            for k, v in list(data.items()):
                if v.get("employee_id") == emp_id or v.get("nik") == clean_nik:
                    found_key = k
                    break

            target_key = rfid if rfid else (found_key or emp_id)
            if found_key and found_key != target_key:
                del data[found_key]

            data[target_key] = {
                "employee_id": emp_id,
                "nik": clean_nik,
                "name": emp_name
            }

            with open(config.EMPLOYEES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"[Storage] Karyawan {emp_id} berhasil diperbarui di employees.json")
    except Exception as e:
        logger.error(f"[Storage] Gagal memperbarui data di employees.json: {e}")

    return True, f"Data karyawan '{emp_name}' ({emp_id}) berhasil diperbarui ke NIK: {clean_nik}!"


