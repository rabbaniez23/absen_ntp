#!/usr/bin/env python3
"""
Connector Service - Jembatan Database MariaDB & REST API Presensi Karyawan
Menangani pencarian data karyawan, pemrosesan transaksi absensi, dan penyimpanan foto jepretan.
Berjalan mandiri pada Port 8002 agar terminal Kiosk tetap bisa mencatat absensi walaupun Admin Dashboard mati.
"""

import base64
import datetime
import http.server
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socketserver
import sys
from urllib.parse import parse_qs, urlparse

import config
import db

# ----------------------------------------------------------------------
# Pengaturan Logging Connector Service
# ----------------------------------------------------------------------
logger = logging.getLogger("AttendanceConnector")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt="[%(asctime)s] [CONNECTOR] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)


# ----------------------------------------------------------------------
# HTTP Request Handler untuk Connector API (Port 8002)
# ----------------------------------------------------------------------
class ConnectorRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handler HTTP Connector Service.
    - POST /api/attendance/scan : Memproses data tap RFID & foto dari capture.py
    - GET  /api/employee        : Lookup karyawan berdasarkan nomor RFID / NIK
    - GET  /api/employees       : Mengambil seluruh daftar karyawan
    - GET  /captures/<filename> : Menyajikan file foto jepretan
    - GET  /api/health          : Status kesehatan service connector
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.CAPTURES_DIR), **kwargs)

    def log_message(self, format, *args):
        logger.info(f"HTTP {self.address_string()} - {format % args}")

    def send_json(self, status_code: int, data: dict):
        """Helper untuk mengirim respons JSON terstandar dengan header CORS."""
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        """Menangani CORS preflight options."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path.rstrip("/")
        if not clean_path:
            clean_path = "/"

        # 1. Healthcheck
        if clean_path in ["/api/health", "/health", "/"]:
            conn_ok = db.get_db_connection() is not None
            self.send_json(200, {
                "status": "ONLINE",
                "service": "Attendance Connector",
                "database_connected": conn_ok,
                "port": config.PORT,
                "timestamp": datetime.datetime.now().isoformat()
            })
            return

        # 2. Lookup Karyawan tunggal: GET /api/employee?id=...
        if clean_path == "/api/employee":
            self.handle_get_employee(parsed_url)
            return

        # 3. Daftar Seluruh Karyawan: GET /api/employees
        if clean_path == "/api/employees":
            employees = db.get_all_employees()
            self.send_json(200, {
                "success": True,
                "count": len(employees),
                "employees": employees
            })
            return

        # 4. Layani file foto dari folder captures/
        if clean_path.startswith("/captures/"):
            filename = clean_path.replace("/captures/", "")
            file_path = config.CAPTURES_DIR / filename
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_json(404, {"success": False, "message": "File foto tidak ditemukan"})
                return

        self.send_json(404, {"success": False, "message": f"Endpoint GET tidak ditemukan: {parsed_url.path}"})

    def do_POST(self):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path.rstrip("/")

        # 1. Pemrosesan Scan Absensi: POST /api/attendance/scan
        if clean_path in ["/api/attendance/scan", "/api/tap"]:
            self.handle_post_attendance_scan()
            return

        self.send_json(404, {"success": False, "message": f"Endpoint POST tidak ditemukan: {parsed_url.path}"})

    def handle_get_employee(self, parsed_url):
        query_params = parse_qs(parsed_url.query)
        lookup_id = query_params.get("id", [""])[0].strip()

        if not lookup_id:
            self.send_json(400, {"success": False, "message": "Parameter 'id' wajib diisi"})
            return

        logger.info(f"PENCARIAN KARYAWAN: {lookup_id}")
        emp = db.lookup_employee(lookup_id)
        if emp:
            nik_val = emp.get("nik") or emp["employee_id"]
            self.send_json(200, {
                "success": True,
                "employee_id": emp["employee_id"],
                "nik": nik_val,
                "name": emp["name"]
            })
        else:
            logger.warning(f"KARYAWAN TIDAK DITEMUKAN: {lookup_id}")
            self.send_json(404, {
                "success": False,
                "message": "Karyawan tidak ditemukan"
            })

    def handle_post_attendance_scan(self):
        """
        Menerima data absensi dari Terminal Kiosk (capture.py).
        Mencari data karyawan di MariaDB, menyimpan foto JPEG yang dikirim kiosk,
        dan mencatat record absensi ke basis data MariaDB (raw_data & image).
        """
        logger.info("API: POST /api/attendance/scan (Menerima dari Kiosk)")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as e:
            self.send_json(400, {"success": False, "message": f"Format data tidak valid: {e}"})
            return

        identifier = (payload.get("rfid_uid") or payload.get("id") or payload.get("nik") or "").strip()
        if not identifier:
            self.send_json(400, {"success": False, "message": "Nomor RFID / NIK tidak boleh kosong."})
            return

        # 1. Validasi Karyawan ke MariaDB
        emp = db.lookup_employee(identifier)
        if not emp:
            logger.warning(f"[Absensi Ditolak] Kartu/ID tidak terdaftar: {identifier}")
            self.send_json(404, {
                "success": False,
                "message": "Kartu RFID atau NIK tidak terdaftar di sistem!"
            })
            return

        emp_id = emp["employee_id"]
        emp_nik = emp.get("nik") or emp_id
        emp_name = emp["name"]

        # 2. Bentuk RAW_DATA dan Nama File IMAGE sesuai spesifikasi pembimbing:
        # format: {nik}{jam}{menit}{tanggal}{bulan}{in_out:1} (contoh: 210019074514091)
        # in_out: "1" untuk MASUK (IN), "0" untuk KELUAR (OUT)
        now = datetime.datetime.now()
        raw_in_out = str(payload.get("in_out") or payload.get("type") or "").strip()
        reader_source = str(payload.get("reader") or "Web Kiosk UI")
        dur = int(payload.get("duration_ms") or 0)
        avg_int = float(payload.get("avg_interval_ms") or 0)
        ident_lower = identifier.lower()

        # Deteksi tipe absensi KONSISTEN & SESUAI PERANGKAT:
        if raw_in_out in ["0", "out", "OUT", "keluar", "KELUAR"] or "out" in reader_source.lower() or "sycreader" in reader_source.lower():
            in_out = "0"
        elif raw_in_out in ["1", "in", "IN", "masuk", "MASUK"] or "qinheng" in reader_source.lower():
            in_out = "1"
        elif "dreizehn" in ident_lower or ident_lower.startswith("13") or (len(identifier) > 10 and not identifier.startswith("320")):
            in_out = "0"
        elif avg_int >= 10.0 or dur >= 80:
            in_out = "0"
        else:
            in_out = "1"

        in_out_label = "MASUK (IN)" if in_out == "1" else "KELUAR (OUT)"
        logger.info(f"[Scan Diproses] ID: '{identifier}' | Mode: {in_out_label} ({in_out}) | Reader: {reader_source}")

        raw_data = db.generate_raw_data(nik=emp_nik, dt=now, in_out=in_out)
        image_filename = f"{raw_data}.jpg"

        # Simpan Foto langsung di config.CAPTURES_DIR dengan nama {raw_data}.jpg
        config.CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        file_path = config.CAPTURES_DIR / image_filename

        image_base64 = payload.get("image_base64", "")
        if image_base64:
            try:
                if "," in image_base64:
                    image_base64 = image_base64.split(",", 1)[1]
                photo_bytes = base64.b64decode(image_base64)
                file_path.write_bytes(photo_bytes)
            except Exception as b64_err:
                logger.error(f"[Absensi] Gagal mendecode base64 foto: {b64_err}")
                file_path.write_bytes(b"")
        else:
            file_path.write_bytes(b"")

        # 3. Catat ke MariaDB (Kolom: id, raw_data, image)
        rel_path = f"captures/{image_filename}"
        db.record_attendance(
            raw_data=raw_data,
            image=image_filename,
            employee_id=emp_id,
            captured_at=now,
            status="SUCCESS"
        )

        logger.info(f"[Absensi BERHASIL] {emp_name} ({in_out_label}) | RAW_DATA: {raw_data} | IMAGE: {image_filename}")

        # 4. Kembalikan respons sukses ke Kiosk
        self.send_json(200, {
            "success": True,
            "message": f"Absensi {in_out_label} berhasil dicatat",
            "raw_data": raw_data,
            "image": image_filename,
            "employee_id": emp_id,
            "nik": emp_nik,
            "name": emp_name,
            "in_out": in_out,
            "in_out_label": in_out_label,
            "photo_url": rel_path,
            "date": now.strftime("%d %B %Y"),
            "time": now.strftime("%H:%M:%S")
        })


def run_connector():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((config.HOST, config.PORT), ConnectorRequestHandler) as httpd:
        print("=" * 65)
        print("   SERVICE CONNECTOR PRESENSI (DATABASE & API BRIDGE)")
        print(f"   Status       : AKTIF")
        print(f"   Port         : {config.PORT}")
        print(f"   Database     : MariaDB ({config.DB_HOST}:{config.DB_PORT})")
        print(f"   Captures Dir : {config.CAPTURES_DIR}")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nMenghentikan Connector Service dengan aman...")


if __name__ == "__main__":
    run_connector()
