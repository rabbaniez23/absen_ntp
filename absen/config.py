import os
from pathlib import Path

# Jalur direktori modul Kiosk Absensi (Edge Terminal)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
LOGS_DIR = BASE_DIR / "logs"

# Port Kiosk Absensi (Port 8000 untuk tampilan layar monitor)
HOST = "0.0.0.0"
PORT = 8000

# Buat direktori yang diperlukan jika belum ada
for directory in [STATIC_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "kiosk.log"

# Alamat Server Admin & Database Pusat
# Default: 127.0.0.1:8001 (jika 1 mesin), atau 10.1.0.2:8001 (jika server pusat sudah siap)
ADMIN_SERVER_URL = os.environ.get("ADMIN_SERVER_URL", "http://127.0.0.1:8001")
