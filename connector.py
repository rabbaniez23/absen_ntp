#!/usr/bin/env python3
"""
Root Launcher untuk Connector Service Presensi.
Menjalankan connector/connector.py pada Port 8002.
"""

import os
import sys
from pathlib import Path

# Pastikan direktori connector ada di dalam sys.path
BASE_DIR = Path(__file__).resolve().parent
CONNECTOR_DIR = BASE_DIR / "connector"
if str(CONNECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(CONNECTOR_DIR))

os.chdir(str(CONNECTOR_DIR))

if __name__ == "__main__":
    import connector
    connector.run_connector()
