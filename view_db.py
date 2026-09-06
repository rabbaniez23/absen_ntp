"""
Employee Attendance System - Database Viewer Utility
Inspects and displays employees and attendance tables directly in terminal.
Works with both MariaDB and local persistent storage.
"""

import json
from pathlib import Path

import config
import db


def print_table(title: str, headers: list, rows: list):
    """Prints a formatted ASCII table in terminal."""
    print("\n" + "=" * 70)
    print(f"  TABEL: {title.upper()}")
    print("=" * 70)

    if not rows:
        print("  (Belum ada data / tabel kosong)")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    # Format header
    header_str = " | ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers)))
    sep_str = "-+-".join("-" * widths[i] for i in range(len(headers)))

    print(header_str)
    print(sep_str)

    # Format rows
    for row in rows:
        row_str = " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(row)))
        print(row_str)

    print(f"Total baris: {len(rows)}")


def show_employees():
    """Displays employee master data."""
    headers = ["EMPLOYEE ID", "NAMA KARYAWAN", "RFID UID", "STATUS"]
    rows = []

    # 1. Try MariaDB
    conn = db.get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT employee_id, name, rfid_uid, is_active FROM employees;")
                for r in cursor.fetchall():
                    rows.append([
                        r.get("employee_id", "-"),
                        r.get("name", "-"),
                        r.get("rfid_uid") or "-",
                        "AKTIF" if r.get("is_active") == 1 else "NONAKTIF"
                    ])
            conn.close()
            print_table("employees (Sumber: MariaDB Database)", headers, rows)
            return
        except Exception:
            if conn:
                conn.close()

    # 2. Fallback: employees.json
    if config.EMPLOYEES_FILE.exists():
        with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for rfid, val in data.items():
                rows.append([
                    val.get("employee_id", "-"),
                    val.get("name", "-"),
                    rfid,
                    "AKTIF"
                ])
        print_table("employees (Sumber: Local Storage / JSON)", headers, rows)


def show_attendance():
    """Displays attendance logs."""
    headers = ["ID EMP", "WAKTU ABSENSI", "PATH FOTO DI DISK", "STATUS"]
    rows = []

    # 1. Try MariaDB
    conn = db.get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT employee_id, captured_at, image_path, attendance_status FROM attendance ORDER BY captured_at DESC;")
                for r in cursor.fetchall():
                    rows.append([
                        r.get("employee_id", "-"),
                        str(r.get("captured_at", "-")),
                        r.get("image_path", "-"),
                        r.get("attendance_status", "-")
                    ])
            conn.close()
            print_table("attendance (Sumber: MariaDB Database)", headers, rows)
            return
        except Exception:
            if conn:
                conn.close()

    # 2. Fallback: attendance.json
    att_file = config.DATA_DIR / "attendance.json"
    if att_file.exists():
        with open(att_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in reversed(data):
                rows.append([
                    item.get("employee_id", "-"),
                    item.get("captured_at", "-"),
                    item.get("image_path", "-"),
                    item.get("attendance_status", "-")
                ])
        print_table("attendance (Sumber: Local Storage / JSON)", headers, rows)


def main():
    print("\n" + "#" * 70)
    print("      SISTEM ABSENSI NTP (absen_ntp) - VIEWER DATABASE & DATA")
    print("#" * 70)
    show_employees()
    show_attendance()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
