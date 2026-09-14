import base64
import http.server
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socketserver
import sys
import time
from urllib.parse import parse_qs, urlparse
import urllib.request
import urllib.error

import config

# ----------------------------------------------------------------------
# Pengaturan Log Terminal Kiosk (Port 8000)
# ----------------------------------------------------------------------
logger = logging.getLogger("CaptureKiosk")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt="[%(asctime)s] [KIOSK] %(message)s",
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


class KioskRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handler HTTP Kiosk Absensi Ringan (Thin Client / Edge Capture).
    - Menampilkan UI Kiosk Absensi NTP
    - Streaming kamera MJPEG via V4L2
    - Meneruskan data RFID/NIK dan foto jepretan ke Server Admin Pusat
    - Bebas dari dependensi Database MariaDB
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        logger.info(f"HTTP {self.address_string()} - {format % args}")

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
        root_aliases = {
            "", "/", "/index.html",
            "/debian", "/debian/",
            "/attendance", "/attendance/",
            "/debian/attendance", "/debian/attendance/",
            "/public", "/public/"
        }
        if raw_path in root_aliases:
            return "/index.html"

        prefixes = ["/debian/attendance", "/attendance", "/debian", "/public"]
        for prefix in prefixes:
            if raw_path.startswith(prefix + "/"):
                sub_path = raw_path[len(prefix):]
                if sub_path in ["", "/"]:
                    return "/index.html"
                return sub_path

        return raw_path

    def do_GET(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)

        # 1. Live stream kamera USB Logitech C930e via V4L2
        if clean_path in ["/api/camera/stream", "/api/stream"]:
            self.handle_get_camera_stream()
            return

        # 2. Cek identitas karyawan atau daftar karyawan ke Server Pusat (Forwarding)
        if clean_path in ["/api/employee", "/api/employees", "/api/attendance"]:
            self.forward_get_to_admin(self.path)
            return

        # 3. Akses foto absensi (Forward ke Server Pusat)
        if clean_path.startswith("/captures/"):
            self.forward_get_to_admin(clean_path)
            return

        # 4. File statis web kiosk (index.html, app.js, style.css)
        original_path = self.path
        self.path = clean_path
        try:
            super().do_GET()
        finally:
            self.path = original_path

    def do_POST(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)

        # Tangani scan RFID / absensi: Jepret foto lokal kamera lalu kirim ke Server Pusat
        if clean_path in ["/api/attendance/scan", "/api/tap"]:
            self.handle_post_attendance_scan()
            return

        # Rute lainnya diteruskan ke Admin jika diperlukan
        self.send_json(404, {"success": False, "message": f"Endpoint tidak ditemukan di Kiosk: {parsed_url.path}"})

    # ------------------------------------------------------------------
    # Streaming Kamera MJPEG (Local Hardware V4L2)
    # ------------------------------------------------------------------
    def handle_get_camera_stream(self):
        try:
            import camera_v4l2
            streamer = camera_v4l2.CameraStreamer.get_instance()
            streamer.start()
        except Exception as err:
            logger.error(f"Gagal menginisialisasi kamera V4L2: {err}")
            self.send_json(500, {"success": False, "message": "Kamera tidak dapat diakses"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while True:
                frame = streamer.get_latest_frame()
                if frame and len(frame) > 100:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.065)  # ~15 FPS hemat CPU
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            logger.debug(f"[Stream] Klien disconnect: {e}")

    # ------------------------------------------------------------------
    # Proses Scan Absensi (Jepret Kamera + Kirim ke Admin Pusat)
    # ------------------------------------------------------------------
    def handle_post_attendance_scan(self):
        logger.info("KIOSK: Memproses Absensi (Tap RFID / Input NIK)")
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

        # 1. Ambil foto wajah langsung dari kamera hardware Logitech C930e
        photo_bytes = None
        try:
            import camera_v4l2
            photo_bytes = camera_v4l2.capture_image_from_device()
        except Exception as cam_err:
            logger.error(f"[Kiosk] Kendala saat mengambil foto kamera: {cam_err}")

        # Konversi foto ke base64 jika berhasil diambil
        image_base64 = ""
        if photo_bytes and len(photo_bytes) > 100:
            image_base64 = base64.b64encode(photo_bytes).decode("ascii")

        # 2. Kirim data ke Server Admin & DB Pusat via HTTP POST
        admin_url = f"{config.ADMIN_SERVER_URL.rstrip('/')}/api/attendance/scan"
        forward_data = {
            "rfid_uid": identifier,
            "image_base64": image_base64
        }

        try:
            req_data = json.dumps(forward_data).encode("utf-8")
            req = urllib.request.Request(
                admin_url,
                data=req_data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_status = resp.getcode()
                resp_body = resp.read().decode("utf-8")
                resp_json = json.loads(resp_body)
                self.send_json(resp_status, resp_json)
                logger.info(f"[Kiosk] Sukses kirim ke Admin: {resp_json.get('name', '')} (Status: {resp_status})")
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                self.send_json(http_err.code, err_json)
            except Exception:
                self.send_json(http_err.code, {"success": False, "message": f"Respon Server Pusat: {http_err.reason}"})
        except urllib.error.URLError as url_err:
            logger.error(f"[Kiosk] Gagal menghubungi Server Admin ({admin_url}): {url_err.reason}")
            self.send_json(503, {
                "success": False,
                "message": "Server Database Pusat sedang tidak dapat dihubungi. Pastikan admin.py aktif!"
            })
        except Exception as ex:
            logger.error(f"[Kiosk] Kesalahan forwarding absensi: {ex}")
            self.send_json(500, {"success": False, "message": f"Kesalahan sistem Kiosk: {str(ex)}"})

    # ------------------------------------------------------------------
    # Forwarder Request GET ke Server Pusat
    # ------------------------------------------------------------------
    def forward_get_to_admin(self, sub_path: str):
        admin_url = f"{config.ADMIN_SERVER_URL.rstrip('/')}/{sub_path.lstrip('/')}"
        try:
            req = urllib.request.Request(admin_url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_status = resp.getcode()
                resp_content_type = resp.headers.get("Content-Type", "application/json")
                resp_body = resp.read()

                self.send_response(resp_status)
                self.send_header("Content-Type", resp_content_type)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read()
            self.send_response(http_err.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
        except urllib.error.URLError as url_err:
            logger.warning(f"[Kiosk] Server Admin offline saat lookup: {url_err.reason}")
            self.send_json(503, {
                "success": False,
                "message": "Server Database Pusat offline. Pastikan admin.py berjalan."
            })


def run_kiosk():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((config.HOST, config.PORT), KioskRequestHandler) as httpd:
        print("=" * 60)
        print("   TERMINAL KIOSK ABSENSI NTP (EDGE CAPTURE)")
        print(f"   Status          : AKTIF (Tanpa Database Lokal)")
        print(f"   Port Kiosk      : {config.PORT}")
        print(f"   URL Layar Absen : http://localhost:{config.PORT}")
        print(f"   Server Pusat    : {config.ADMIN_SERVER_URL}")
        print("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nMenghentikan Kiosk Absensi dengan aman...")


if __name__ == "__main__":
    run_kiosk()
