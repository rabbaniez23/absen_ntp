import base64
import datetime
import email
from email.parser import BytesParser
from email.policy import default
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

# Batas maksimal ukuran berkas unggahan (10 MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# ----------------------------------------------------------------------
# Pengaturan Log Terpusat untuk Admin Server
# ----------------------------------------------------------------------
logger = logging.getLogger("AdminServer")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt="[%(asctime)s] [ADMIN] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Handler terminal (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    # 2. Handler berkas rotasi logs/admin.log
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)


class AdminRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handler HTTP untuk antarmuka Admin dan endpoint API Master Database."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        logger.info(f"HTTP {self.address_string()} - {format % args}")

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, status_code: int, data: dict):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def get_clean_path(self, raw_path: str) -> str:
        root_aliases = {"", "/", "/index.html", "/admin", "/admin/"}
        if raw_path in root_aliases:
            # Di modul admin, default halaman utama langsung membuka employees.html
            return "/employees.html"

        prefixes = ["/debian/attendance", "/attendance", "/debian", "/public", "/admin"]
        for prefix in prefixes:
            if raw_path.startswith(prefix + "/"):
                sub_path = raw_path[len(prefix):]
                if sub_path in ["", "/"]:
                    return "/employees.html"
                return sub_path

        return raw_path

    def do_GET(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)

        # 1. Melayani file foto absensi (/captures/...)
        if clean_path.startswith("/captures/"):
            capture_file = config.BASE_DIR / clean_path.lstrip("/")
            if not capture_file.exists() or not capture_file.is_file():
                sub_name = clean_path[len("/captures/"):].lstrip("/")
                capture_file = config.CAPTURES_DIR / sub_name

            if capture_file.exists() and capture_file.is_file():
                self.send_response(200)
                suffix = capture_file.suffix.lower()
                content_type = "image/bmp" if suffix == ".bmp" else "image/jpeg"
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(capture_file.stat().st_size))
                self.end_headers()
                with open(capture_file, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_json(404, {"success": False, "message": "File foto tidak ditemukan"})
                return

        # 2. Endpoint API
        if clean_path == "/api/employee":
            self.handle_get_employee(parsed_url)
        elif clean_path == "/api/employees":
            self.handle_get_employees()
        elif clean_path == "/api/stats":
            self.handle_get_stats()
        elif clean_path in ["/api/attendance", "/api/attendance/records"]:
            self.handle_get_attendance(parsed_url)
        else:
            original_path = self.path
            self.path = clean_path
            try:
                super().do_GET()
            finally:
                self.path = original_path

    def do_POST(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)

        if clean_path in ["/api/attendance/scan", "/api/attendance/record", "/api/tap"]:
            self.handle_post_attendance_scan()
        elif clean_path == "/api/upload":
            self.handle_post_upload()
        elif clean_path == "/api/employees":
            self.handle_post_employee()
        elif clean_path in ["/api/employees/update", "/api/employees/edit"]:
            self.handle_update_employee()
        elif clean_path == "/api/employees/toggle-status":
            self.handle_toggle_status()
        elif clean_path == "/api/employees/delete":
            self.handle_delete_employee()
        else:
            logger.warning(f"ENDPOINT TIDAK DITEMUKAN: {parsed_url.path}")
            self.send_json(404, {"success": False, "message": f"Endpoint tidak ditemukan: {parsed_url.path}"})

    def do_PUT(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)
        if clean_path in ["/api/employees", "/api/employees/update"]:
            self.handle_update_employee()
        else:
            self.send_json(404, {"success": False, "message": f"Endpoint tidak ditemukan: {parsed_url.path}"})

    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)
        if clean_path == "/api/employees":
            self.handle_delete_employee(parsed_url)
        else:
            self.send_json(404, {"success": False, "message": f"Endpoint tidak ditemukan: {parsed_url.path}"})

    # ------------------------------------------------------------------
    # Handler API Master Data & Absensi
    # ------------------------------------------------------------------
    def handle_get_employees(self):
        logger.info("API: GET /api/employees")
        employees = db.get_all_employees()
        self.send_json(200, {
            "success": True,
            "count": len(employees),
            "employees": employees
        })

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

    def handle_get_attendance(self, parsed_url):
        logger.info("API: GET /api/attendance")
        query_params = parse_qs(parsed_url.query)
        date_filter = query_params.get("date", [None])[0]
        search = query_params.get("search", [None])[0]
        try:
            limit = int(query_params.get("limit", [100])[0])
        except (ValueError, TypeError):
            limit = 100

        records = db.get_attendance_records(limit=limit, date_filter=date_filter, search=search)
        self.send_json(200, {
            "success": True,
            "count": len(records),
            "records": records
        })

    def handle_post_attendance_scan(self):
        """
        Menerima data absensi dari Terminal Kiosk (capture.py).
        Mencari data karyawan di MariaDB, menyimpan foto JPEG yang dikirim kiosk,
        dan mencatat record absensi ke basis data.
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

        # 2. Bentuk RAW_DATA dan Nama File IMAGE sesuai spesifikasi:
        # format: {nik}{jam}{menit}{tanggal}{bulan}{in_out:1} (contoh: 210019074514091)
        # in_out: "1" untuk MASUK (IN), "0" untuk KELUAR (OUT)
        now = datetime.datetime.now()
        raw_in_out = str(payload.get("in_out") or payload.get("type") or "1").strip()
        in_out = "0" if raw_in_out in ["0", "out", "OUT", "keluar", "KELUAR"] else "1"
        in_out_label = "MASUK (IN)" if in_out == "1" else "KELUAR (OUT)"

        raw_data = db.generate_raw_data(nik=emp_nik, dt=now, in_out=in_out)
        image_filename = f"{raw_data}.jpg"

        # Simpan Foto langsung di config.CAPTURES_DIR dengan nama {raw_data}.jpg
        config.CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        file_path = config.CAPTURES_DIR / image_filename

        image_base64 = payload.get("image_base64", "")
        if image_base64:
            try:
                # Hilangkan header data URL jika ada (misal data:image/jpeg;base64,...)
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

    def handle_post_employee(self):
        """Menambahkan karyawan baru ke database."""
        logger.info("API: POST /api/employees")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as e:
            self.send_json(400, {"success": False, "message": f"Payload JSON tidak valid: {str(e)}"})
            return

        emp_id = payload.get("employee_id", "").strip()
        nik = payload.get("nik", "").strip()
        name = payload.get("name", "").strip()
        rfid = payload.get("rfid_uid", "").strip()

        if not nik and emp_id:
            nik = emp_id
        if not emp_id and nik:
            emp_id = nik

        if not name or not rfid or not (nik or emp_id):
            self.send_json(400, {
                "success": False,
                "message": "Semua bidang (NIK / ID Karyawan, Nama, RFID UID) wajib diisi."
            })
            return

        success, msg = db.add_employee(emp_id, name, rfid, nik=nik)
        status_code = 200 if success else 400
        self.send_json(status_code, {
            "success": success,
            "message": msg,
            "employee": {"employee_id": emp_id, "nik": nik, "name": name, "rfid_uid": rfid} if success else None
        })

    def handle_update_employee(self):
        """Memperbarui data karyawan (Nama, NIK, RFID)."""
        logger.info("API: POST/PUT /api/employees/update")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as err:
            self.send_json(400, {"success": False, "message": f"Format data JSON tidak valid: {err}"})
            return

        emp_id = payload.get("employee_id", "").strip()
        nik = payload.get("nik", "").strip()
        name = payload.get("name", "").strip()
        rfid = payload.get("rfid_uid", "").strip()

        if not emp_id or not name or not nik:
            self.send_json(400, {"success": False, "message": "ID Karyawan, Nama, dan NIK wajib diisi."})
            return

        is_active = payload.get("is_active")
        if is_active is not None:
            is_active = bool(is_active)

        success, msg = db.update_employee(emp_id, name, nik, rfid_uid=rfid, is_active=is_active)
        self.send_json(200 if success else 400, {
            "success": success,
            "message": msg
        })

    def handle_toggle_status(self):
        """Mengubah status aktif/nonaktif karyawan secara cepat."""
        logger.info("API: POST /api/employees/toggle-status")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as err:
            self.send_json(400, {"success": False, "message": f"Format data JSON tidak valid: {err}"})
            return

        emp_id = payload.get("employee_id", "").strip()
        is_active = bool(payload.get("is_active", True))

        if not emp_id:
            self.send_json(400, {"success": False, "message": "ID Karyawan wajib diisi."})
            return

        success, msg = db.toggle_employee_status(emp_id, is_active)
        self.send_json(200 if success else 400, {
            "success": success,
            "message": msg,
            "employee_id": emp_id,
            "is_active": is_active
        })

    def handle_get_stats(self):
        """Mengambil data statistik untuk dashboard ringkasan."""
        logger.info("API: GET /api/stats")
        stats = db.get_dashboard_stats()
        self.send_json(200, {
            "success": True,
            "stats": stats
        })

    def handle_delete_employee(self, parsed_url=None):
        """Menghapus data karyawan."""
        logger.info("API: DELETE /api/employees")
        emp_id = None
        if parsed_url:
            query_params = parse_qs(parsed_url.query)
            emp_id = query_params.get("id", [""])[0].strip()

        if not emp_id:
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0:
                    raw_body = self.rfile.read(content_length).decode("utf-8")
                    payload = json.loads(raw_body)
                    emp_id = payload.get("employee_id", "").strip()
            except Exception:
                pass

        if not emp_id:
            self.send_json(400, {"success": False, "message": "Parameter ID karyawan tidak ditemukan."})
            return

        success, msg = db.delete_employee(emp_id)
        self.send_json(200 if success else 400, {
            "success": success,
            "message": msg
        })

    def handle_post_upload(self):
        """Menangani unggahan foto manual dari form."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
            msg = BytesParser(policy=default).parsebytes(header_bytes + raw_body)

            employee_id = None
            image_bytes = None
            for part in msg.iter_parts():
                part_name = part.get_param("name", header="content-disposition")
                if part_name == "employee_id":
                    employee_id = part.get_payload().strip()
                elif part_name == "image":
                    image_bytes = part.get_payload(decode=True)

            if not employee_id or not image_bytes:
                self.send_json(400, {"success": False, "message": "Data tidak lengkap"})
                return

            now = datetime.datetime.now()
            emp = db.lookup_employee(employee_id)
            nik_val = (emp.get("nik") if emp else None) or employee_id
            raw_data = db.generate_raw_data(nik_val, now, "1")
            image_filename = f"{raw_data}.jpg"
            file_path = config.CAPTURES_DIR / image_filename
            file_path.write_bytes(image_bytes)

            rel_path = f"captures/{image_filename}"
            db.record_attendance(
                raw_data=raw_data,
                image=image_filename,
                employee_id=employee_id,
                captured_at=now,
                status="SUCCESS"
            )
            self.send_json(200, {
                "success": True,
                "message": "Presensi berhasil dicatat",
                "raw_data": raw_data,
                "image": image_filename,
                "photo_url": rel_path
            })
        except Exception as e:
            self.send_json(500, {"success": False, "message": str(e)})


def run_server():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((config.HOST, config.PORT), AdminRequestHandler) as httpd:
        print("=" * 60)
        print("   SERVER ADMIN & DATABASE PUSAT (NTP ATTENDANCE)")
        print(f"   Status     : AKTIF")
        print(f"   Port       : {config.PORT}")
        print(f"   URL Admin  : http://localhost:{config.PORT}/employees.html")
        print(f"   Database   : {config.DB_NAME}@{config.DB_HOST}")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nMenghentikan Server Admin dengan aman...")


if __name__ == "__main__":
    run_server()
