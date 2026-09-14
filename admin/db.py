"""
Modul Akses Basis Data (Database Layer)
Menyediakan eksekusi query SQL dengan parameterized query untuk keamanan data.
Mendukung pencarian karyawan, pencatatan absensi, dan manajemen master data karyawan.
Dilengkapi mekanisme fallback otomatis ke file JSON jika MariaDB sedang offline.
"""

import datetime
import json
import logging
import re
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

            # Tabel riwayat absensi (Format baru: id, raw_data, image sesuai instruksi pembimbing)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `attendance` (
                    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
                    `raw_data` VARCHAR(100) NOT NULL,
                    `image` VARCHAR(255) NOT NULL,
                    `employee_id` VARCHAR(50) DEFAULT NULL,
                    `captured_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                    `image_path` VARCHAR(255) DEFAULT NULL,
                    `attendance_status` VARCHAR(20) DEFAULT 'SUCCESS',
                    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX `idx_attendance_raw` (`raw_data`),
                    INDEX `idx_attendance_captured_at` (`captured_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            # Migrasi skema jika tabel lama belum memiliki kolom raw_data atau image
            try:
                cursor.execute("ALTER TABLE `attendance` ADD COLUMN IF NOT EXISTS `raw_data` VARCHAR(100) DEFAULT NULL AFTER `id`;")
                cursor.execute("ALTER TABLE `attendance` ADD COLUMN IF NOT EXISTS `image` VARCHAR(255) DEFAULT NULL AFTER `raw_data`;")
                cursor.execute("ALTER TABLE `attendance` MODIFY `employee_id` VARCHAR(50) DEFAULT NULL;")
                cursor.execute("ALTER TABLE `attendance` MODIFY `captured_at` DATETIME DEFAULT CURRENT_TIMESTAMP;")
                cursor.execute("ALTER TABLE `attendance` MODIFY `image_path` VARCHAR(255) DEFAULT NULL;")
                cursor.execute("ALTER TABLE `attendance` MODIFY `attendance_status` VARCHAR(20) DEFAULT 'SUCCESS';")
                # Konversi data lama yang raw_data-nya masih kosong
                cursor.execute("""
                    UPDATE `attendance` a
                    LEFT JOIN `employees` e ON a.employee_id = e.employee_id
                    SET a.raw_data = CONCAT(
                        COALESCE(e.nik, a.employee_id, '000000'),
                        DATE_FORMAT(COALESCE(a.captured_at, NOW()), '%H%i%d%m'),
                        '1'
                    ),
                    a.image = COALESCE(NULLIF(SUBSTRING_INDEX(a.image_path, '/', -1), ''), CONCAT(COALESCE(e.nik, a.employee_id, '000000'), DATE_FORMAT(COALESCE(a.captured_at, NOW()), '%H%i%d%m'), '1.jpg'))
                    WHERE a.raw_data IS NULL OR a.raw_data = '';
                """)
            except Exception as migr_err:
                logger.debug(f"[Database] Catatan migrasi tabel attendance: {migr_err}")

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


def generate_raw_data(nik: str, dt: Optional[datetime.datetime] = None, in_out: str = "1") -> str:
    """
    Menghasilkan string raw_data sesuai spesifikasi pembimbing:
    {NIK}{Jam:2}{Menit:2}{Tanggal:2}{Bulan:2}{In/Out:1}
    Contoh: NIK 210019 pada 14 September pukul 07:45 (Masuk/In=1) -> 210019074514091
    """
    if dt is None:
        dt = datetime.datetime.now()
    clean_nik = re.sub(r'[^A-Za-z0-9]', '', str(nik or '')).strip()
    if not clean_nik:
        clean_nik = "000000"
    hh = dt.strftime("%H")
    mm = dt.strftime("%M")
    dd = dt.strftime("%d")
    month = dt.strftime("%m")
    in_out_code = "1" if str(in_out).strip() in ["1", "in", "IN"] else "0"
    return f"{clean_nik}{hh}{mm}{dd}{month}{in_out_code}"


def parse_raw_data(raw_data: str, fallback_dt: Optional[datetime.datetime] = None) -> dict:
    """
    Mem-parse string raw_data menjadi dictionary komponen:
    NIK, Jam, Menit, Tanggal, Bulan, In/Out, Datetime string terformat.
    Contoh: 210019074514091 ->
      nik: 210019
      hh: 07, mm: 45, dd: 14, month: 09
      in_out: 1 (label: MASUK (IN))
      datetime_str: 2026-09-14 07:45:00
    """
    raw = str(raw_data or "").strip()
    now = fallback_dt or datetime.datetime.now()
    current_year = now.strftime("%Y")

    if len(raw) >= 10:
        nik = raw[:-9]
        hh = raw[-9:-7]
        mm = raw[-7:-5]
        dd = raw[-5:-3]
        month = raw[-3:-1]
        in_out = raw[-1]
        datetime_str = f"{current_year}-{month}-{dd} {hh}:{mm}:00"
        in_out_label = "MASUK (IN)" if in_out == "1" else "KELUAR (OUT)"
        return {
            "nik": nik,
            "raw_data": raw,
            "hh": hh,
            "mm": mm,
            "dd": dd,
            "month": month,
            "datetime_str": datetime_str,
            "in_out": in_out,
            "in_out_label": in_out_label
        }

    # Fallback jika raw_data tidak sesuai panjang standar
    return {
        "nik": raw,
        "raw_data": raw,
        "hh": now.strftime("%H"),
        "mm": now.strftime("%M"),
        "dd": now.strftime("%d"),
        "month": now.strftime("%m"),
        "datetime_str": now.strftime("%Y-%m-%d %H:%M:%S"),
        "in_out": "1",
        "in_out_label": "MASUK (IN)"
    }


def record_attendance(
    raw_data: str,
    image: str,
    employee_id: Optional[str] = None,
    captured_at: Optional[datetime.datetime] = None,
    status: str = "SUCCESS"
) -> bool:
    """
    Menyimpan data riwayat absensi ke MariaDB dengan kolom utama: id, raw_data, image.
    Mendukung skema baru sesuai instruksi pembimbing:
    - id: auto increment
    - raw_data: gabungan NIK + Jam + Menit + Tanggal + Bulan + In/Out (misal: 210019074514091)
    - image: nama file foto persis sama dengan raw_data (misal: 210019074514091.jpg)
    Selalu mencadangkan catatan absensi ke file data/attendance.json.
    """
    db_success = False
    now = captured_at or datetime.datetime.now()

    # Pastikan nama file image berekstensi .jpg
    clean_image = image if image.lower().endswith(".jpg") else f"{raw_data}.jpg"
    clean_rel_path = f"captures/{clean_image}"

    # 1. Simpan ke MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Periksa struktur kolom pada tabel attendance
                cursor.execute("SHOW COLUMNS FROM `attendance` LIKE 'raw_data';")
                has_raw = cursor.fetchone() is not None

                if has_raw:
                    cursor.execute("SHOW COLUMNS FROM `attendance` LIKE 'employee_id';")
                    has_emp_col = cursor.fetchone() is not None

                    if has_emp_col:
                        # Menyimpan ke tabel yang memiliki kolom raw_data, image, dan kolom pendukung
                        sql = """
                            INSERT INTO attendance (raw_data, image, employee_id, captured_at, image_path, attendance_status)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (
                            raw_data,
                            clean_image,
                            employee_id or raw_data[:-9],
                            now.strftime("%Y-%m-%d %H:%M:%S"),
                            clean_rel_path,
                            status
                        ))
                    else:
                        # Tabel murni dengan 2 kolom data: raw_data dan image
                        sql = "INSERT INTO attendance (raw_data, image) VALUES (%s, %s)"
                        cursor.execute(sql, (raw_data, clean_image))
                else:
                    # Tabel skema lama
                    sql = """
                        INSERT INTO attendance (employee_id, captured_at, image_path, attendance_status)
                        VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(sql, (
                        employee_id or raw_data,
                        now.strftime("%Y-%m-%d %H:%M:%S"),
                        clean_rel_path,
                        status
                    ))

                db_success = True
                logger.info(f"[Database] Absensi tersimpan: raw_data={raw_data}, image={clean_image}")
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
            "id": len(records) + 1,
            "raw_data": raw_data,
            "image": clean_image,
            "employee_id": employee_id or (raw_data[:-9] if len(raw_data) >= 10 else raw_data),
            "nik": raw_data[:-9] if len(raw_data) >= 10 else raw_data,
            "captured_at": now.isoformat(timespec="seconds"),
            "image_path": clean_rel_path,
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
    Mengambil riwayat absensi dengan kolom id, raw_data, image, beserta nama & status karyawan.
    Mendukung filter tanggal dan pencarian.
    Mengutamakan MariaDB dan fallback ke data/attendance.json.
    """
    records = []

    # Siapkan mapping master karyawan (NIK & Employee ID -> Employee Data)
    emp_map = {}
    all_emps = get_all_employees()
    for e in all_emps:
        if e.get("nik"):
            emp_map[str(e["nik"]).strip().lower()] = e
        if e.get("employee_id"):
            emp_map[str(e["employee_id"]).strip().lower()] = e

    # 1. Ambil dari MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Periksa apakah kolom raw_data sudah ada
                cursor.execute("SHOW COLUMNS FROM `attendance` LIKE 'raw_data';")
                has_raw = cursor.fetchone() is not None

                if has_raw:
                    sql = "SELECT id, raw_data, image, employee_id, captured_at, image_path, attendance_status FROM attendance ORDER BY id DESC LIMIT %s;"
                    cursor.execute(sql, (limit * 2,))
                    rows = cursor.fetchall()
                    for r in rows:
                        raw = r.get("raw_data")
                        cap_dt = r.get("captured_at")
                        if not raw:
                            # Jika data lama belum ada raw_data, generate on the fly
                            emp_id_val = r.get("employee_id") or ""
                            emp_obj = emp_map.get(emp_id_val.lower(), {})
                            nik_val = emp_obj.get("nik") or emp_id_val
                            raw = generate_raw_data(nik_val, cap_dt if isinstance(cap_dt, datetime.datetime) else None, "1")

                        parsed = parse_raw_data(raw, cap_dt if isinstance(cap_dt, datetime.datetime) else None)
                        emp_id_lookup = parsed["nik"].lower()
                        emp = emp_map.get(emp_id_lookup, {})
                        emp_name = emp.get("name") or emp_id_lookup.upper()
                        is_active = bool(emp.get("is_active", True))

                        img_name = r.get("image") or f"{raw}.jpg"
                        img_path = f"captures/{img_name}"

                        # Filter Tanggal (YYYY-MM-DD)
                        if date_filter and not parsed["datetime_str"].startswith(date_filter):
                            continue

                        # Filter Pencarian (Nama, NIK, Raw Data)
                        if search:
                            s_lower = search.lower()
                            if (s_lower not in emp_name.lower() and
                                s_lower not in parsed["nik"].lower() and
                                s_lower not in raw.lower()):
                                continue

                        records.append({
                            "id": r["id"],
                            "raw_data": raw,
                            "image": img_name,
                            "image_path": img_path,
                            "employee_id": parsed["nik"],
                            "nik": parsed["nik"],
                            "name": emp_name,
                            "is_active": is_active,
                            "captured_at": parsed["datetime_str"],
                            "in_out": parsed["in_out"],
                            "in_out_label": parsed["in_out_label"],
                            "status": r.get("attendance_status") or "SUCCESS",
                            "source": "mariadb"
                        })

                        if len(records) >= limit:
                            break

                    return records
                else:
                    # Query backward-compatible jika kolom raw_data belum ada
                    sql = """
                        SELECT a.id, a.employee_id, e.nik, COALESCE(e.name, a.employee_id) AS name,
                               COALESCE(e.is_active, 1) AS is_active,
                               a.captured_at, a.image_path, a.attendance_status
                        FROM attendance a
                        LEFT JOIN employees e ON a.employee_id = e.employee_id
                        ORDER BY a.captured_at DESC LIMIT %s;
                    """
                    cursor.execute(sql, (limit,))
                    rows = cursor.fetchall()
                    for r in rows:
                        cap_at = r["captured_at"]
                        cap_str = cap_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(cap_at, (datetime.datetime, datetime.date)) else str(cap_at)
                        emp_nik = r.get("nik") or r["employee_id"]
                        raw = generate_raw_data(emp_nik, cap_at if isinstance(cap_at, datetime.datetime) else None, "1")
                        records.append({
                            "id": r["id"],
                            "raw_data": raw,
                            "image": f"{raw}.jpg",
                            "image_path": str(r.get("image_path") or f"captures/{raw}.jpg").replace("\\", "/"),
                            "employee_id": r["employee_id"],
                            "nik": emp_nik,
                            "name": r.get("name") or r["employee_id"],
                            "is_active": bool(r.get("is_active", 1)),
                            "captured_at": cap_str,
                            "in_out": "1",
                            "in_out_label": "MASUK (IN)",
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

            for idx, item in enumerate(reversed(json_records)):
                raw = item.get("raw_data")
                emp_id = item.get("employee_id", "")
                cap_at = item.get("captured_at", "")

                if not raw:
                    emp = emp_map.get(emp_id.lower(), {})
                    nik_val = emp.get("nik") or emp_id
                    try:
                        dt_obj = datetime.datetime.fromisoformat(cap_at.replace("Z", ""))
                    except Exception:
                        dt_obj = None
                    raw = generate_raw_data(nik_val, dt_obj, "1")

                parsed = parse_raw_data(raw)
                emp = emp_map.get(parsed["nik"].lower(), {})
                emp_name = emp.get("name", parsed["nik"])
                is_active = bool(emp.get("is_active", True))

                if date_filter and not parsed["datetime_str"].startswith(date_filter):
                    continue

                if search:
                    s_lower = search.lower()
                    if (s_lower not in emp_name.lower() and
                        s_lower not in parsed["nik"].lower() and
                        s_lower not in raw.lower()):
                        continue

                img_name = item.get("image") or f"{raw}.jpg"
                records.append({
                    "id": item.get("id") or (idx + 1),
                    "raw_data": raw,
                    "image": img_name,
                    "image_path": f"captures/{img_name}",
                    "employee_id": parsed["nik"],
                    "nik": parsed["nik"],
                    "name": emp_name,
                    "is_active": is_active,
                    "captured_at": parsed["datetime_str"],
                    "in_out": parsed["in_out"],
                    "in_out_label": parsed["in_out_label"],
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
                sql = "SELECT employee_id, nik, name, rfid_uid, is_active FROM employees ORDER BY id ASC;"
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


def update_employee(employee_id: str, name: str, nik: str, rfid_uid: str = None, is_active: Optional[bool] = None) -> tuple:
    """
    Memperbarui NIK, Nama, RFID UID, dan status keaktifan karyawan di MariaDB dan employees.json.
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

                active_val = 1 if is_active is None or is_active else 0
                if rfid:
                    cursor.execute(
                        "UPDATE employees SET name = %s, nik = %s, rfid_uid = %s, is_active = %s WHERE employee_id = %s;",
                        (emp_name, clean_nik, rfid, active_val, emp_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE employees SET name = %s, nik = %s, is_active = %s WHERE employee_id = %s;",
                        (emp_name, clean_nik, active_val, emp_id)
                    )
                logger.info(f"[Database] Karyawan {emp_id} berhasil diperbarui di MariaDB (NIK: {clean_nik}, Nama: {emp_name}, Aktif: {active_val})")
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
                "name": emp_name,
                "is_active": True if is_active is None or is_active else False
            }

            with open(config.EMPLOYEES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"[Storage] Karyawan {emp_id} berhasil diperbarui di employees.json")
    except Exception as e:
        logger.error(f"[Storage] Gagal memperbarui data di employees.json: {e}")

    return True, f"Data karyawan '{emp_name}' ({emp_id}) berhasil diperbarui!"


def toggle_employee_status(employee_id: str, is_active: bool) -> tuple:
    """Mengubah status aktif/nonaktif karyawan secara cepat."""
    emp_id = (employee_id or "").strip().upper()
    if not emp_id:
        return False, "ID Karyawan tidak valid."

    status_int = 1 if is_active else 0
    status_str = "AKTIF" if is_active else "NONAKTIF"

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE employees SET is_active = %s WHERE employee_id = %s;", (status_int, emp_id))
                logger.info(f"[Database] Status karyawan {emp_id} diubah menjadi {status_str}")
        except Exception as err:
            logger.warning(f"[Database] Gagal mengubah status di MariaDB: {err}")
        finally:
            conn.close()

    try:
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if v.get("employee_id") == emp_id:
                    v["is_active"] = bool(is_active)
            with open(config.EMPLOYEES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"[Storage] Gagal mengubah status di employees.json: {e}")

    return True, f"Status karyawan '{emp_id}' berhasil diubah menjadi {status_str}."


def get_dashboard_stats() -> dict:
    """Mengambil metrik ringkasan untuk dashboard utama."""
    stats = {
        "total_employees": 0,
        "active_employees": 0,
        "inactive_employees": 0,
        "today_attendance": 0,
        "recent_attendance": []
    }

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # 1. Total & Keaktifan
                cursor.execute("""
                    SELECT 
                        COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), 0) AS active_cnt,
                        COALESCE(SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END), 0) AS inactive_cnt
                    FROM employees;
                """)
                row = cursor.fetchone()
                if row:
                    stats["total_employees"] = row.get("total") or 0
                    stats["active_employees"] = int(row.get("active_cnt") or 0)
                    stats["inactive_employees"] = int(row.get("inactive_cnt") or 0)

                # 2. Total Absensi Hari Ini & Absensi Terkini
                all_att = get_attendance_records(limit=200)
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                stats["today_attendance"] = sum(1 for a in all_att if str(a.get("captured_at", "")).startswith(today_str))
                stats["recent_attendance"] = all_att[:6]
                return stats
        except Exception as err:
            logger.warning(f"[Database] Gagal mengambil statistik dari MariaDB: {err}")
        finally:
            conn.close()

    # Fallback jika MariaDB offline
    all_emps = get_all_employees()
    stats["total_employees"] = len(all_emps)
    stats["active_employees"] = sum(1 for e in all_emps if e.get("is_active", True))
    stats["inactive_employees"] = stats["total_employees"] - stats["active_employees"]
    all_att = get_attendance_records(limit=200)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    stats["today_attendance"] = sum(1 for a in all_att if str(a.get("captured_at", "")).startswith(today_str))
    stats["recent_attendance"] = all_att[:6]
    return stats


