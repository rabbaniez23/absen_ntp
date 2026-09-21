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

# Alamat Server Connector (Jembatan Database & API Presensi)
# Default: 127.0.0.1:8002 (Connector Service mandiri)
CONNECTOR_SERVER_URL = os.environ.get("CONNECTOR_SERVER_URL", "http://127.0.0.1:8002")
ADMIN_SERVER_URL = os.environ.get("ADMIN_SERVER_URL", CONNECTOR_SERVER_URL)

# ----------------------------------------------------------------------
# Konfigurasi Hardware RFID Dual-Reader (IN & OUT)
# ----------------------------------------------------------------------
# Reader 1: QinHeng Electronics (1a86:dd01) -> PRESENSI MASUK (IN / Kode: 1)
RFID_IN_CONFIG = {
    "vendor": "1a86",
    "product": "dd01",
    "name": "QinHeng Electronics RFID Reader",
    "type": "1",
    "label": "MASUK (IN)"
}

# Reader 2: Sycreader ID&IC USB (ffff:0035) -> PRESENSI KELUAR / PULANG (OUT / Kode: 0)
RFID_OUT_CONFIG = {
    "vendor": "ffff",
    "product": "0035",
    "name": "Sycreader RFID Technology SYC ID&IC USB Reader",
    "type": "0",
    "label": "KELUAR (OUT)"
}
