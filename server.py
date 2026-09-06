import datetime
import email
from email.parser import BytesParser
from email.policy import default
import http.server
import json
import logging
from logging.handlers import RotatingFileHandler
import re
import socketserver
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
import db

# Batas maksimal ukuran berkas unggahan (10 MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Magic signature format berkas PNG standar
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# ----------------------------------------------------------------------
# Pengaturan Log Terpusat (Konsol Terminal + File Berotasi logs/app.log)
# ----------------------------------------------------------------------
logger = logging.getLogger("AttendanceServer")
logger.setLevel(logging.INFO)

# Cegah duplikasi handler saat modul dimuat ulang
if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Handler terminal (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    # 2. Handler berkas rotasi (logs/app.log, maks 5MB, 5 cadangan)
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)


class AttendanceRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handler HTTP untuk melayani aset antarmuka statis dan endpoint API absensi."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        """Mengarahkan pesan akses HTTP melalui logger terpusat."""
        logger.info(f"HTTP {self.address_string()} - {format % args}")

    def end_headers(self):
        """Menambahkan header no-cache pada semua respons agar data di browser selalu mutakhir."""
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, status_code: int, data: dict):
        """Mengirim respons JSON dengan header HTTP yang sesuai."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        """Mengarahkan request GET ke file statis web atau endpoint API."""
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/employee":
            self.handle_get_employee(parsed_url)
        elif parsed_url.path == "/api/employees":
            self.handle_get_employees()
        else:
            super().do_GET()

    def do_POST(self):
        """Mengarahkan request POST ke endpoint API."""
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/upload":
            self.handle_post_upload()
        elif parsed_url.path == "/api/employees":
            self.handle_post_employee()
        elif parsed_url.path == "/api/employees/delete":
            self.handle_delete_employee()
        else:
            logger.warning(f"ENDPOINT NOT FOUND: {parsed_url.path}")
            self.send_json(404, {
                "success": False,
                "message": f"Endpoint tidak ditemukan: {parsed_url.path}"
            })

    def do_DELETE(self):
        """Mengarahkan request DELETE ke endpoint API."""
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/employees":
            self.handle_delete_employee(parsed_url)
        else:
            self.send_json(404, {
                "success": False,
                "message": f"Endpoint tidak ditemukan: {parsed_url.path}"
            })

    def handle_get_employees(self):
        """Mengambil dan mengembalikan seluruh daftar karyawan dari database."""
        logger.info("API: GET /api/employees")
        employees = db.get_all_employees()
        self.send_json(200, {
            "success": True,
            "count": len(employees),
            "employees": employees
        })

    def handle_post_employee(self):
        """Menambahkan karyawan baru ke database dan file cadangan JSON."""
        logger.info("API: POST /api/employees")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as e:
            logger.warning(f"INVALID JSON: {e}")
            self.send_json(400, {"success": False, "message": f"Payload JSON tidak valid: {str(e)}"})
            return

        emp_id = payload.get("employee_id", "").strip()
        name = payload.get("name", "").strip()
        rfid = payload.get("rfid_uid", "").strip()

        if not emp_id or not name or not rfid:
            self.send_json(400, {
                "success": False,
                "message": "Semua bidang (Employee ID, Nama, RFID UID) wajib diisi."
            })
            return

        success, msg = db.add_employee(emp_id, name, rfid)
        status_code = 200 if success else 400
        self.send_json(status_code, {
            "success": success,
            "message": msg,
            "employee": {"employee_id": emp_id, "name": name, "rfid_uid": rfid} if success else None
        })

    def handle_delete_employee(self, parsed_url=None):
        """Menghapus data karyawan berdasarkan ID."""
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

    def handle_get_employee(self, parsed_url):
        """Mencari data karyawan berdasarkan ID atau nomor kartu RFID."""
        query_params = parse_qs(parsed_url.query)
        lookup_id = query_params.get("id", [""])[0].strip()

        if not lookup_id:
            logger.warning("PENCARIAN GAGAL: Parameter 'id' tidak disertakan")
            self.send_json(400, {
                "success": False,
                "message": "Parameter 'id' wajib diisi"
            })
            return

        logger.info(f"PENCARIAN KARYAWAN: {lookup_id}")

        emp = db.lookup_employee(lookup_id)
        if emp:
            logger.info(f"KARYAWAN DITEMUKAN: {emp['employee_id']} ({emp['name']}) [sumber: {emp.get('source', 'unknown')}]")
            self.send_json(200, {
                "success": True,
                "employee_id": emp["employee_id"],
                "name": emp["name"],
                "rfid_uid": emp.get("rfid_uid") or emp["employee_id"]
            })
        else:
            logger.warning(f"KARYAWAN TIDAK DITEMUKAN: {lookup_id}")
            self.send_json(404, {
                "success": False,
                "message": "Karyawan tidak ditemukan"
            })

    def handle_post_upload(self):
        """Menangani unggahan foto absensi PNG dengan validasi integritas data."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length <= 0:
            logger.warning("UNGGAHAN DITOLAK: Body request kosong")
            self.send_json(400, {
                "success": False,
                "message": "Body request kosong"
            })
            return

        if content_length > MAX_UPLOAD_SIZE:
            logger.warning(f"UNGGAHAN DITOLAK: Ukuran {content_length} bytes melampaui batas {MAX_UPLOAD_SIZE}")
            self.send_json(413, {
                "success": False,
                "message": f"Ukuran berkas terlalu besar: melebihi batas maksimal {MAX_UPLOAD_SIZE // (1024*1024)}MB"
            })
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            logger.warning(f"UNGGAHAN DITOLAK: Content-Type tidak valid '{content_type}'")
            self.send_json(400, {
                "success": False,
                "message": "Content-Type harus berupa multipart/form-data"
            })
            return

        try:
            raw_body = self.rfile.read(content_length)
        except Exception as e:
            logger.error(f"GAGAL MEMBACA UNGGAHAN: {e}")
            self.send_json(500, {
                "success": False,
                "message": f"Gagal membaca payload unggahan: {str(e)}"
            })
            return

        # Parsing data formulir multipart
        try:
            header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
            msg = BytesParser(policy=default).parsebytes(header_bytes + raw_body)

            employee_id = None
            image_bytes = None

            for part in msg.iter_parts():
                disp_header = part.get("Content-Disposition", "")
                part_name = part.get_param("name", header="content-disposition")

                if part_name == "employee_id":
                    employee_id = part.get_payload().strip()
                elif part_name == "image":
                    image_bytes = part.get_payload(decode=True)

        except Exception as e:
            logger.error(f"PARSING MULTIPART GAGAL: {e}")
            self.send_json(400, {
                "success": False,
                "message": f"Format data multipart tidak valid: {str(e)}"
            })
            return

        # Validasi format ID Karyawan
        if not employee_id:
            logger.warning("UNGGAHAN DITOLAK: Kolom employee_id tidak ada")
            self.send_json(400, {
                "success": False,
                "message": "Field 'employee_id' wajib disertakan"
            })
            return

        if not re.match(r"^[A-Za-z0-9_-]+$", employee_id):
            logger.warning(f"UNGGAHAN DITOLAK: Karakter tidak valid pada employee_id '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Format ID karyawan hanya boleh alfanumerik, tanda strip, atau garis bawah."
            })
            return

        # Validasi berkas biner foto PNG
        if not image_bytes:
            logger.warning(f"UNGGAHAN DITOLAK: Data gambar tidak ditemukan untuk '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Berkas 'image' wajib disertakan"
            })
            return

        if not image_bytes.startswith(PNG_SIGNATURE):
            logger.warning(f"UNGGAHAN DITOLAK: Magic signature berkas tidak valid untuk '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Format berkas tidak valid. Foto harus berformat PNG asli."
            })
            return

        # Buat timestamp dan jalur direktori penyimpanan foto
        now = datetime.datetime.now()
        year_str = now.strftime("%Y")
        month_str = now.strftime("%m")
        day_str = now.strftime("%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")

        target_dir = config.CAPTURES_DIR / year_str / month_str / day_str
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{employee_id}_{timestamp_str}.png"
        file_path = target_dir / filename

        # Simpan berkas gambar ke harddisk
        try:
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            logger.info(f"FOTO TERSIMPAN: {employee_id} -> {filename} ({len(image_bytes)} bytes)")
        except Exception as e:
            logger.error(f"GAGAL MENULIS KE DISK: {file_path}: {e}")
            self.send_json(500, {
                "success": False,
                "message": f"Gagal menyimpan foto ke harddisk: {str(e)}"
            })
            return

        rel_path = str(file_path.relative_to(config.BASE_DIR)).replace("\\", "/")

        # Catat data absensi ke basis data
        db.record_attendance(employee_id, now, rel_path, "SUCCESS")

        logger.info(f"ABSENSI BERHASIL: {employee_id}")

        # Kirim respons sukses ke klien
        self.send_json(200, {
            "success": True,
            "message": "Absensi berhasil dicatat",
            "employee_id": employee_id,
            "filename": filename,
            "filepath": rel_path,
            "timestamp": now.isoformat(timespec="seconds")
        })


def run_server():
    """Menjalankan HTTP server pada host dan port yang telah ditentukan."""
    # Inisialisasi basis data dan tabel jika belum ada
    db.init_database_tables()

    address = (config.HOST, config.PORT)
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(address, AttendanceRequestHandler) as httpd:
        logger.info("=" * 60)
        logger.info(f"SERVER ABSEN_NTP AKTIF di http://localhost:{config.PORT}")
        logger.info(f"Melayani aset statis dari: {config.STATIC_DIR}")
        logger.info(f"Penyimpanan foto di: {config.CAPTURES_DIR}")
        logger.info(f"Data karyawan dimuat dari: {config.EMPLOYEES_FILE}")
        logger.info(f"Berkas log aktif di: {config.LOG_FILE}")
        logger.info("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("MENGHENTIKAN SERVER DENGAN AMAN...")
        finally:
            httpd.server_close()



if __name__ == "__main__":
    run_server()
