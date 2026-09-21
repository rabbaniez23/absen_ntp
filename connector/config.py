import os
from pathlib import Path

# Jalur direktori modul Connector (Jembatan Database & API Absensi)
CONNECTOR_DIR = Path(__file__).resolve().parent
ROOT_DIR = CONNECTOR_DIR.parent
DATA_DIR = ROOT_DIR / "admin" / "data"
CAPTURES_DIR = ROOT_DIR / "admin" / "captures"
LOGS_DIR = CONNECTOR_DIR / "logs"

# Konfigurasi alamat server Connector
HOST = "0.0.0.0"
PORT = 8002

# Buat direktori yang diperlukan jika belum ada
for directory in [DATA_DIR, CAPTURES_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

EMPLOYEES_FILE = DATA_DIR / "employees.json"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"
LOG_FILE = LOGS_DIR / "connector.log"

# Konfigurasi koneksi MariaDB / MySQL
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "debian")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "dreizehn")
DB_NAME = os.environ.get("DB_NAME", "debian")
