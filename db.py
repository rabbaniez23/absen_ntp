"""
Employee Attendance System - Task 15: MariaDB Database Layer
Provides direct SQL parameterized queries without ORM.
Supports employee lookup and attendance recording.
Includes automatic fallback to local JSON if database is unreachable.
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pymysql
import pymysql.cursors

import config

logger = logging.getLogger("AttendanceServer")


def get_db_connection() -> Optional[pymysql.Connection]:
    """
    Establishes and returns a connection to MariaDB.
    Returns None if database server is offline or connection fails.
    """
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
        logger.debug(f"[Database] Connection error: {err}")
        return None


def init_database_tables() -> bool:
    """
    Initializes MariaDB database and tables directly via SQL without external CLI.
    Creates attendance_db, employees table, and attendance table if they do not exist.
    """
    try:
        # Step 1: Connect to server without database to ensure database exists
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

        # Step 2: Connect to the database and create tables
        db_conn = get_db_connection()
        if not db_conn:
            return False

        with db_conn.cursor() as cursor:
            # Table: employees
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `employees` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `employee_id` VARCHAR(50) NOT NULL UNIQUE,
                    `name` VARCHAR(100) NOT NULL,
                    `rfid_uid` VARCHAR(50) DEFAULT NULL UNIQUE,
                    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
                    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX `idx_employees_rfid` (`rfid_uid`),
                    INDEX `idx_employees_active` (`is_active`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)

            # Table: attendance
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

            # Seed initial employees from employees.json if table is empty
            cursor.execute("SELECT COUNT(*) AS total FROM `employees`;")
            count = cursor.fetchone().get("total", 0)
            if count == 0 and config.EMPLOYEES_FILE.exists():
                logger.info("[Database] Seeding initial employee data from employees.json...")
                with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                    emp_data = json.load(f)
                    for key, val in emp_data.items():
                        emp_id = val.get("employee_id", key)
                        name = val.get("name", "")
                        rfid = key if key != emp_id else None
                        cursor.execute("""
                            INSERT INTO `employees` (`employee_id`, `name`, `rfid_uid`, `is_active`)
                            VALUES (%s, %s, %s, 1)
                            ON DUPLICATE KEY UPDATE `name` = VALUES(`name`), `rfid_uid` = VALUES(`rfid_uid`);
                        """, (emp_id, name, rfid))

        db_conn.close()
        logger.info("[Database] MariaDB schema initialized successfully.")
        return True
    except Exception as err:
        logger.warning(f"[Database] Schema auto-init notice: {err}")
        return False


def lookup_employee(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Finds an employee by RFID UID or Employee ID using direct parameterized SQL.
    Falls back to local JSON if database connection is unavailable.
    """
    clean_id = identifier.strip()
    if not clean_id:
        return None

    # 1. Attempt lookup in MariaDB using parameterized SQL (NO ORM)
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                sql = """
                    SELECT employee_id, name, rfid_uid, is_active
                    FROM employees
                    WHERE (rfid_uid = %s OR employee_id = %s) AND is_active = 1
                    LIMIT 1
                """
                cursor.execute(sql, (clean_id, clean_id))
                row = cursor.fetchone()
                if row:
                    logger.info(f"[Database] Employee found in MariaDB: {row['name']} ({row['employee_id']})")
                    return {
                        "employee_id": row["employee_id"],
                        "name": row["name"],
                        "rfid_uid": row.get("rfid_uid") or row["employee_id"],
                        "source": "mariadb"
                    }
                else:
                    logger.info(f"[Database] Employee not found in MariaDB: {clean_id}")
                    return None
        except Exception as err:
            logger.warning(f"[Database] Query error in lookup_employee: {err}. Falling back to JSON...")
        finally:
            conn.close()

    # 2. Resilient fallback: data/employees.json
    logger.info(f"[Fallback] Querying local employees.json for {clean_id}")
    if config.EMPLOYEES_FILE.exists():
        try:
            with open(config.EMPLOYEES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if clean_id in data:
                    emp = data[clean_id]
                    rfid = clean_id if clean_id != emp.get("employee_id") else None
                    return {
                        "employee_id": emp.get("employee_id", clean_id),
                        "name": emp.get("name", "Unknown"),
                        "rfid_uid": rfid or emp.get("rfid_uid", clean_id),
                        "source": "json_fallback"
                    }
                for key, emp in data.items():
                    if emp.get("employee_id") == clean_id:
                        rfid = key if key != emp.get("employee_id") else None
                        return {
                            "employee_id": emp.get("employee_id"),
                            "name": emp.get("name", "Unknown"),
                            "rfid_uid": rfid or emp.get("rfid_uid", key),
                            "source": "json_fallback"
                        }
        except Exception as e:
            logger.error(f"[Fallback] Error reading employees.json: {e}")

    return None


def record_attendance(employee_id: str, captured_at: datetime.datetime, image_path: str, status: str = "SUCCESS") -> bool:
    """
    Inserts a new attendance record into MariaDB using direct parameterized SQL.
    Always maintains a backup record in data/attendance.json.
    """
    db_success = False

    # 1. Insert into MariaDB via direct parameterized SQL (NO ORM)
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
                logger.info(f"[Database] Attendance inserted into MariaDB: {employee_id} at {captured_at}")
        except Exception as err:
            logger.warning(f"[Database] Insert error in record_attendance: {err}")
        finally:
            conn.close()

    # 2. Always persist into local data/attendance.json as persistent cache / backup
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
        logger.error(f"[Storage] Error writing backup attendance.json: {e}")

    return True
