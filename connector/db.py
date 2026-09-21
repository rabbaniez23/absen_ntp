"""
Modul Basis Data Connector Service
Menyediakan koneksi langsung ke MariaDB dan penyimpanan lokal untuk pencatatan absensi.
"""

import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import pymysql
    import pymysql.cursors
    HAVE_PYMYSQL = True
except ImportError:
    pymysql = None
    HAVE_PYMYSQL = False

import config

logger = logging.getLogger("AttendanceConnector")


def get_db_connection() -> Optional[Any]:
    """Membuka dan mengembalikan koneksi aktif ke MariaDB."""
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
        logger.debug(f"[Connector DB] Gagal terhubung ke basis data: {err}")
        return None


def lookup_employee(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Mencari data karyawan berdasarkan nomor UID RFID, NIK, atau Employee ID.
    Mendukung variasi awalan reader (seperti dreizehn/13) dan fallback ke employees.json.
    """
    clean_id = (identifier or "").strip()
    if not clean_id:
        return None

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
                    logger.info(f"[Connector DB] Karyawan ditemukan di MariaDB: {row['name']} (NIK: {nik_val})")
                    return {
                        "employee_id": row["employee_id"],
                        "nik": nik_val,
                        "name": row["name"],
                        "rfid_uid": row.get("rfid_uid") or row["employee_id"],
                        "source": "mariadb"
                    }
        except Exception as err:
            logger.warning(f"[Connector DB] Terjadi kendala query di MariaDB: {err}. Beralih ke JSON...")
        finally:
            conn.close()

    # 2. Fallback: cari di berkas lokal employees.json
    try:
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                employees = json.load(f)

            for emp in employees:
                emp_id = str(emp.get("employee_id", "")).strip().lower()
                emp_nik = str(emp.get("nik", "")).strip().lower()
                emp_rfid = str(emp.get("rfid_uid", "")).strip().lower()

                for cand in candidate_ids:
                    cand_lower = cand.lower()
                    if cand_lower in [emp_id, emp_nik, emp_rfid]:
                        return {
                            "employee_id": emp["employee_id"],
                            "nik": emp.get("nik") or emp["employee_id"],
                            "name": emp["name"],
                            "rfid_uid": emp.get("rfid_uid") or emp["employee_id"],
                            "source": "json"
                        }
    except Exception as ex:
        logger.error(f"[Connector DB] Gagal membaca data cadangan JSON: {ex}")

    return None


def generate_raw_data(nik: str, dt: Optional[datetime.datetime] = None, in_out: str = "1") -> str:
    """
    Menghasilkan string raw_data sesuai spesifikasi:
    {NIK}{Jam:2}{Menit:2}{Tanggal:2}{Bulan:2}{In/Out:1}
    Contoh: NIK 210019 pada 21 September pukul 12:24 (Masuk/In=1) -> 210019122421091
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


def record_attendance(raw_data: str, image: str, employee_id: str = None, captured_at: Optional[datetime.datetime] = None, status: str = "SUCCESS") -> bool:
    """
    Menyimpan data riwayat absensi ke MariaDB (kolom raw_data, image)
    serta mencadangkan ke file data/attendance.json.
    """
    db_success = False
    now = captured_at or datetime.datetime.now()

    clean_image = image if image.lower().endswith(".jpg") else f"{raw_data}.jpg"
    clean_rel_path = f"captures/{clean_image}"

    # 1. Simpan ke MariaDB
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW COLUMNS FROM `attendance` LIKE 'raw_data';")
                has_raw = cursor.fetchone() is not None

                if has_raw:
                    cursor.execute("SHOW COLUMNS FROM `attendance` LIKE 'employee_id';")
                    has_emp_col = cursor.fetchone() is not None

                    if has_emp_col:
                        sql = """
                            INSERT INTO attendance (raw_data, image, employee_id, captured_at, image_path, attendance_status)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(sql, (
                            raw_data,
                            clean_image,
                            employee_id or (raw_data[:-9] if len(raw_data) >= 10 else raw_data),
                            now.strftime("%Y-%m-%d %H:%M:%S"),
                            clean_rel_path,
                            status
                        ))
                    else:
                        sql = "INSERT INTO attendance (raw_data, image) VALUES (%s, %s)"
                        cursor.execute(sql, (raw_data, clean_image))
                else:
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
                logger.info(f"[Connector DB] Absensi tersimpan ke MariaDB: raw_data={raw_data}, image={clean_image}")
        except Exception as err:
            logger.warning(f"[Connector DB] Gagal menyimpan absensi ke MariaDB: {err}")
        finally:
            conn.close()

    # 2. Cadangkan riwayat ke file lokal data/attendance.json
    try:
        attendance_file = config.ATTENDANCE_FILE
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
            "captured_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "image_path": clean_rel_path,
            "attendance_status": status,
            "db_synced": db_success
        })

        with open(attendance_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    except Exception as e:
        logger.error(f"[Connector DB] Gagal menulis cadangan attendance.json: {e}")

    return True


def get_all_employees() -> List[Dict[str, Any]]:
    """Mengambil daftar seluruh karyawan aktif."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT employee_id, nik, name, rfid_uid, is_active FROM employees ORDER BY name ASC")
                rows = cursor.fetchall()
                if rows:
                    return rows
        except Exception:
            pass
        finally:
            conn.close()

    try:
        if config.EMPLOYEES_FILE.exists():
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass

    return []
