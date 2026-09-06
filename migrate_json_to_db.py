"""
Skrip Migrasi Data JSON ke MariaDB
Memindahkan data riwayat dari berkas JSON (employees.json & attendance.json) ke MariaDB.
Berkas JSON asli tetap dipertahankan sebagai cadangan lokal.
"""

import json
import logging
import sys
from pathlib import Path

import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DataMigration")


def load_employees_data(file_path: Path) -> list:
    """Membaca data karyawan baik format dictionary dengan key RFID maupun array list."""
    if not file_path.exists():
        logger.warning(f"File tidak ditemukan: {file_path}")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if isinstance(raw, dict):
                result = []
                for key, val in raw.items():
                    emp_entry = {
                        "employee_id": val.get("employee_id", key),
                        "name": val.get("name", ""),
                        "rfid_uid": key if key != val.get("employee_id") else val.get("rfid_uid", key),
                        "is_active": val.get("is_active", True)
                    }
                    result.append(emp_entry)
                return result
            elif isinstance(raw, list):
                return raw
            return []
    except Exception as e:
        logger.error(f"Gagal membaca {file_path}: {e}")
        return []


def load_attendance_data(file_path: Path) -> list:
    """Membaca data riwayat absensi dari berkas JSON."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Gagal membaca {file_path}: {e}")
        return []


def generate_migration_sql(employees: list, attendances: list, output_sql_path: Path):
    """Membuat skrip SQL migrasi data karyawan dan riwayat absensi."""
    lines = [
        "-- ====================================================================",
        "-- Skrip Migrasi Otomatis dari Berkas JSON ke MariaDB",
        "-- Aman & Idempoten (ON DUPLICATE KEY UPDATE)",
        "-- ====================================================================",
        "USE `attendance_db`;",
        ""
    ]

    # 1. Migrasi Data Master Karyawan
    lines.append("-- 1. Migrasi Karyawan")
    for emp in employees:
        emp_id = emp.get("employee_id", "").replace("'", "''")
        name = emp.get("name", "").replace("'", "''")
        rfid = emp.get("rfid_uid", "")
        if rfid:
            clean_rfid = rfid.replace("'", "''")
            rfid_val = f"'{clean_rfid}'"
        else:
            rfid_val = "NULL"
        is_active = 1 if emp.get("is_active", True) else 0

        sql = (
            f"INSERT INTO `employees` (`employee_id`, `name`, `rfid_uid`, `is_active`) "
            f"VALUES ('{emp_id}', '{name}', {rfid_val}, {is_active}) "
            f"ON DUPLICATE KEY UPDATE `name` = VALUES(`name`), `rfid_uid` = VALUES(`rfid_uid`);"
        )
        lines.append(sql)

    lines.append("")

    # 2. Migrasi Riwayat Presensi
    lines.append("-- 2. Migrasi Riwayat Presensi")
    for att in attendances:
        emp_id = att.get("employee_id", "").replace("'", "''")
        captured_at = att.get("captured_at", "").replace("T", " ")
        image_path = att.get("image_path", "").replace("'", "''")
        status = att.get("attendance_status", "SUCCESS").replace("'", "''")

        sql = (
            f"INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) "
            f"VALUES ('{emp_id}', '{captured_at}', '{image_path}', '{status}');"
        )
        lines.append(sql)

    lines.append("")

    with open(output_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"File SQL migrasi berhasil dibuat: {output_sql_path} ({len(employees)} karyawan, {len(attendances)} presensi)")


def main():
    logger.info("Memulai persiapan migrasi data JSON ke MariaDB...")

    employees = load_employees_data(config.EMPLOYEES_FILE)
    attendances_file = config.DATA_DIR / "attendance.json"
    attendances = load_attendance_data(attendances_file)

    logger.info(f"Ditemukan {len(employees)} data karyawan di {config.EMPLOYEES_FILE}")
    logger.info(f"Ditemukan {len(attendances)} riwayat absensi di {attendances_file}")

    # Buat file import_data.sql untuk query database
    output_sql = config.BASE_DIR / "import_data.sql"
    generate_migration_sql(employees, attendances, output_sql)

    logger.info("Persiapan migrasi berhasil.")
    logger.info("CATATAN: File data/employees.json dan data/attendance.json tetap disimpan sebagai cadangan offline.")

    # Eksekusi langsung ke database MariaDB jika sedang berjalan
    try:
        import pymysql
        conn = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=3
        )
        with conn.cursor() as cursor:
            with open(output_sql, "r", encoding="utf-8") as sf:
                sql_content = sf.read()
            for stmt in sql_content.split(";"):
                stmt = stmt.strip()
                if stmt and not stmt.startswith("--"):
                    cursor.execute(stmt)
        conn.close()
        logger.info("Semua data berhasil dieksekusi dan tersimpan langsung ke database MariaDB!")
    except Exception as err:
        logger.warning(f"Koneksi MariaDB belum aktif, SQL telah disimpan di import_data.sql: {err}")


if __name__ == "__main__":
    main()

