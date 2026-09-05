import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
CAPTURES_DIR = BASE_DIR / "captures"
LOGS_DIR = BASE_DIR / "logs"

# Server configuration
HOST = "0.0.0.0"
PORT = 8000

# Ensure required directories exist
for directory in [STATIC_DIR, DATA_DIR, CAPTURES_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Data & log files
EMPLOYEES_FILE = DATA_DIR / "employees.json"
LOG_FILE = LOGS_DIR / "app.log"

# MariaDB Configuration (Task 14-15) - Default matches Laragon/XAMPP (root, no password)
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "attendance_db")
