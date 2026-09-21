import base64
import datetime
import http.server
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import socketserver
import struct
import sys
import threading
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


# ----------------------------------------------------------------------
# Manajemen Hardware Dual RFID (QinHeng IN & Sycreader OUT)
# ----------------------------------------------------------------------
class RFIDHardwareManager:
    """
    Manajer deteksi dan pemantau Hardware Dual-RFID Reader di sistem Linux Debian:
    - Reader 1: QinHeng Electronics (1a86:dd01) -> PRESENSI MASUK (IN / Kode: 1)
    - Reader 2: Sycreader SYC ID&IC (ffff:0035) -> PRESENSI KELUAR (OUT / Kode: 0)
    
    Membaca event USB Keyboard secara langsung dari kernel /dev/input/eventX,
    sehingga pembacaan kartu 100% independen dari fokus jendela browser (Firefox Kiosk).
    """

    LINUX_KEY_MAP = {
        2: '1', 3: '2', 4: '3', 5: '4', 6: '5', 7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
        16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',
        30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g', 35: 'h', 36: 'j', 37: 'k', 38: 'l',
        44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm',
        # Keypad Numpad
        71: '7', 72: '8', 73: '9', 75: '4', 76: '5', 77: '6', 79: '1', 80: '2', 81: '3', 82: '0',
    }
    ENTER_CODES = {28, 96}  # Enter & Numpad Enter

    def __init__(self, on_scan_callback):
        self.on_scan_callback = on_scan_callback
        self.active_devices = []
        self.threads = []
        self.running = False
        self.last_scan_time = {}  # Anti-double tap (debounce)

    def scan_devices(self):
        """Mendeteksi perangkat input RFID reader dari /proc/bus/input/devices dan /dev/input/by-id/"""
        detected = []

        # 1. Parsing /proc/bus/input/devices (Standar Linux)
        proc_path = Path("/proc/bus/input/devices")
        if proc_path.exists():
            try:
                content = proc_path.read_text(encoding="utf-8", errors="ignore")
                blocks = content.split("\n\n")
                for block in blocks:
                    vendor = ""
                    product = ""
                    event_node = ""
                    name = ""
                    for line in block.splitlines():
                        if line.startswith("I:"):
                            parts = line.split()
                            for p in parts:
                                if p.startswith("Vendor="):
                                    vendor = p.split("=")[1].lower()
                                elif p.startswith("Product="):
                                    product = p.split("=")[1].lower()
                        elif line.startswith("N:"):
                            name = line.split("Name=", 1)[-1].strip('"\n ')
                        elif line.startswith("H:"):
                            for h in line.split():
                                if h.startswith("event"):
                                    event_node = f"/dev/input/{h}"

                    if event_node and Path(event_node).exists():
                        # Cek kecocokan QinHeng (IN)
                        if (vendor == "1a86" and product == "dd01") or "qinheng" in name.lower():
                            detected.append({
                                "node": event_node,
                                "vendor": vendor or "1a86",
                                "product": product or "dd01",
                                "name": name or config.RFID_IN_CONFIG["name"],
                                "type": "1",
                                "label": "MASUK (IN)",
                                "reader_key": "qinheng"
                            })
                        # Cek kecocokan Sycreader (OUT)
                        elif (vendor == "ffff" and product == "0035") or "sycreader" in name.lower() or "syc" in name.lower():
                            detected.append({
                                "node": event_node,
                                "vendor": vendor or "ffff",
                                "product": product or "0035",
                                "name": name or config.RFID_OUT_CONFIG["name"],
                                "type": "0",
                                "label": "KELUAR (OUT)",
                                "reader_key": "sycreader"
                            })
            except Exception as e:
                logger.warning(f"[RFID Hardware] Gagal membaca /proc/bus/input/devices: {e}")

        # 2. Fallback via /dev/input/by-id/
        by_id_dir = Path("/dev/input/by-id")
        if by_id_dir.exists():
            existing_nodes = {d["node"] for d in detected}
            try:
                for link in by_id_dir.glob("*event-kbd"):
                    try:
                        real_node = str(link.resolve())
                        if real_node in existing_nodes:
                            continue
                        link_name = link.name.lower()
                        if "qinheng" in link_name or "1a86" in link_name:
                            detected.append({
                                "node": real_node,
                                "vendor": "1a86",
                                "product": "dd01",
                                "name": config.RFID_IN_CONFIG["name"],
                                "type": "1",
                                "label": "MASUK (IN)",
                                "reader_key": "qinheng"
                            })
                            existing_nodes.add(real_node)
                        elif "sycreader" in link_name or "syc" in link_name or "ffff" in link_name:
                            detected.append({
                                "node": real_node,
                                "vendor": "ffff",
                                "product": "0035",
                                "name": config.RFID_OUT_CONFIG["name"],
                                "type": "0",
                                "label": "KELUAR (OUT)",
                                "reader_key": "sycreader"
                            })
                            existing_nodes.add(real_node)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[RFID Hardware] Gagal membaca /dev/input/by-id: {e}")

        self.active_devices = detected
        return detected

    def start(self):
        """Memulai pemantauan background untuk seluruh perangkat RFID yang terhubung."""
        self.running = True
        devices = self.scan_devices()

        if not devices:
            logger.info("[RFID Hardware] Tidak ada device RFID /dev/input yang terdeteksi (Windows/dev mode).")
            return

        logger.info(f"[RFID Hardware] Ditemukan {len(devices)} perangkat RFID reader:")
        for dev in devices:
            logger.info(f"   -> [{dev['label']}] {dev['name']} ({dev['vendor']}:{dev['product']}) pada {dev['node']}")
            t = threading.Thread(target=self._device_listener_worker, args=(dev,), daemon=True)
            t.start()
            self.threads.append(t)

    def _device_listener_worker(self, dev):
        """Worker thread untuk membaca satu node /dev/input/eventX secara persisten."""
        node_path = dev["node"]
        reader_label = dev["label"]
        reader_type = dev["type"]
        reader_name = dev["name"]

        # Struct format: 64-bit Linux = @qqHHi (24 bytes), 32-bit Linux = @llHHi (16 bytes)
        is_64bit = sys.maxsize > 2**32
        event_fmt = "@qqHHi" if is_64bit else "@llHHi"
        event_size = struct.calcsize(event_fmt)

        buffer = []
        logger.info(f"[RFID Hardware] Listener AKTIF: {reader_name} -> {reader_label}")

        while self.running:
            try:
                with open(node_path, "rb") as fd:
                    # Coba exclusive grab agar keystroke RFID tidak diketik/bocor ke browser Firefox
                    try:
                        import fcntl
                        EVIOCGRAB = 0x40044590
                        fcntl.ioctl(fd.fileno(), EVIOCGRAB, 1)
                        logger.info(f"[RFID Hardware] Perangkat {reader_name} BERHASIL DIKUNCI (GRAB EKSKLUSIF). Input tidak akan bocor ke browser!")
                    except Exception as grab_err:
                        logger.warning(f"[RFID Hardware] Grab ioctl tidak aktif ({grab_err}), tetap membaca via input stream biasa.")

                    while self.running:
                        data = fd.read(event_size)
                        if not data or len(data) < event_size:
                            time.sleep(0.01)
                            continue

                        sec, usec, ev_type, code, value = struct.unpack(event_fmt, data)

                        # EV_KEY = 1, value == 1 (Key Down)
                        if ev_type == 1 and value == 1:
                            if code in self.ENTER_CODES:
                                raw_chars = "".join(buffer).strip()
                                card_uid = re.sub(r'[^a-zA-Z0-9]', '', raw_chars)
                                buffer.clear()
                                if card_uid:
                                    now = time.time()
                                    last_time = self.last_scan_time.get(card_uid, 0)
                                    if now - last_time < 2.5:
                                        logger.info(f"[RFID Hardware] Abaikan double-tap ({card_uid}) dalam 2.5 detik.")
                                        continue
                                    self.last_scan_time[card_uid] = now

                                    logger.info(f"[RFID TAP HARDWARE] [{reader_label}] Kartu: {card_uid} ({reader_name})")
                                    if self.on_scan_callback:
                                        self.on_scan_callback(card_uid, reader_type, reader_label, reader_name)

                            elif code in self.LINUX_KEY_MAP:
                                buffer.append(self.LINUX_KEY_MAP[code])
                            elif len(buffer) > 40:
                                buffer.clear()

            except PermissionError:
                logger.error(
                    f"===============================================================\n"
                    f"[RFID Hardware ERROR] Akses DITOLAK pada {node_path} ({reader_name})!\n"
                    f"Python tidak memiliki izin membaca input hardware kernel.\n"
                    f"SOLUSI INSTAN (Jalankan di Debian):\n"
                    f"   sudo chmod 666 /dev/input/event*\n"
                    f"Atau jalankan capture.py dengan sudo:\n"
                    f"   sudo nohup python3 absen/capture.py > /dev/null 2>&1 &\n"
                    f"==============================================================="
                )
                time.sleep(5)
            except FileNotFoundError:
                logger.warning(f"[RFID Hardware] Perangkat {node_path} terputus. Mencoba reconnect dalam 3 detik...")
                time.sleep(3)
            except Exception as err:
                logger.error(f"[RFID Hardware] Error pada {node_path}: {err}")
                time.sleep(3)


# ----------------------------------------------------------------------
# Event Bus (SSE & State Notifikasi Kiosk)
# ----------------------------------------------------------------------
class KioskEventHub:
    """Manajer pengiriman event real-time (Server-Sent Events) ke antarmuka web Kiosk."""
    def __init__(self):
        self.subscribers = []
        self.lock = threading.Lock()
        self.latest_event = None

    def add_subscriber(self, q: queue.Queue):
        with self.lock:
            self.subscribers.append(q)

    def remove_subscriber(self, q: queue.Queue):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def broadcast(self, event_data: dict):
        self.latest_event = event_data
        with self.lock:
            dead_queues = []
            for q in self.subscribers:
                try:
                    q.put_nowait(event_data)
                except Exception:
                    dead_queues.append(q)
            for q in dead_queues:
                if q in self.subscribers:
                    self.subscribers.remove(q)


event_hub = KioskEventHub()
recent_pipeline_scans = {}
recent_pipeline_lock = threading.Lock()


# ----------------------------------------------------------------------
# Handler Eksekusi Scan Absensi Bersama (Hardware & Web API)
# ----------------------------------------------------------------------
def execute_attendance_pipeline(identifier: str, in_out: str = "", reader_name: str = "Web Kiosk UI", extra_params: dict = None) -> dict:
    """
    Menjalankan alur lengkap absensi:
    1. Ambil foto wajah dari kamera lokal Logitech C930e
    2. Kirim data RFID + Foto JPEG ke Server Admin Pusat
    3. Broadcast hasil absensi via Server-Sent Events (SSE) ke browser Kiosk
    """
    clean_id = (identifier or "").strip()
    if not clean_id:
        return {"success": False, "message": "Nomor RFID kosong"}

    now_ts = time.time()

    # Deduplikasi: Jika kartu ini baru saja diproses dalam 2.5 detik terakhir,
    # jangan proses ulang (kembalikan hasil yang sudah ada).
    with recent_pipeline_lock:
        if clean_id in recent_pipeline_scans:
            last_ts, last_resp = recent_pipeline_scans[clean_id]
            if now_ts - last_ts < 2.5:
                logger.info(f"[PIPELINE] Mengabaikan request duplikat untuk {clean_id} ({reader_name}).")
                return last_resp

    raw_in_out = str(in_out).strip() if in_out is not None else ""
    in_out_val = "0" if raw_in_out in ["0", "out", "OUT", "keluar", "KELUAR"] else ("1" if raw_in_out in ["1", "in", "IN", "masuk", "MASUK"] else "")

    logger.info(f"[PIPELINE] Memproses scan kartu/NIK: {clean_id} | Reader: {reader_name} | Mode: {in_out_val or 'Auto'}")

    # 1. Ambil foto wajah dari webcam Logitech C930e lokal
    photo_bytes = None
    try:
        import camera_v4l2
        photo_bytes = camera_v4l2.capture_image_from_device()
    except Exception as cam_err:
        logger.error(f"[Kiosk] Gagal mengambil foto webcam: {cam_err}")

    image_base64 = ""
    if photo_bytes and len(photo_bytes) > 100:
        image_base64 = base64.b64encode(photo_bytes).decode("ascii")

    # 2. Kirim ke Server Admin Pusat
    admin_url = f"{config.ADMIN_SERVER_URL.rstrip('/')}/api/attendance/scan"
    forward_data = {
        "rfid_uid": clean_id,
        "in_out": in_out_val,
        "reader": reader_name,
        "image_base64": image_base64
    }
    if extra_params:
        forward_data.update(extra_params)

    resp_json = {}
    resp_status = 500

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
            lbl = resp_json.get("in_out_label", "Presensi")
            logger.info(f"[Kiosk] Sukses kirim ke Admin: {resp_json.get('name', '')} ({lbl})")
    except urllib.error.HTTPError as http_err:
        resp_status = http_err.code
        err_body = http_err.read().decode("utf-8")
        try:
            resp_json = json.loads(err_body)
        except Exception:
            resp_json = {"success": False, "message": f"Respon Server Pusat: {http_err.reason}"}
    except urllib.error.URLError as url_err:
        resp_status = 503
        resp_json = {
            "success": False,
            "message": "Server Database Pusat sedang offline. Pastikan admin.py aktif!"
        }
    except Exception as ex:
        resp_status = 500
        resp_json = {"success": False, "message": f"Kesalahan sistem Kiosk: {str(ex)}"}

    # Lengkapi metadata hasil
    res_in_out = resp_json.get("in_out") or in_out_val or "1"
    res_label = resp_json.get("in_out_label") or ("KELUAR (OUT)" if res_in_out == "0" else "MASUK (IN)")
    resp_json["in_out"] = res_in_out
    resp_json["in_out_label"] = res_label
    resp_json["reader_used"] = reader_name
    resp_json["status_code"] = resp_status

    with recent_pipeline_lock:
        recent_pipeline_scans[clean_id] = (now_ts, resp_json)

    # 3. Broadcast ke seluruh layar browser Kiosk via SSE
    event_hub.broadcast(resp_json)

    return resp_json


def on_hardware_rfid_tap(card_uid: str, in_out: str, in_out_label: str, reader_name: str):
    """Callback saat kartu fisik ditempelkan ke reader QinHeng atau Sycreader."""
    threading.Thread(
        target=execute_attendance_pipeline,
        args=(card_uid, in_out, reader_name),
        daemon=True
    ).start()


rfid_hw_manager = RFIDHardwareManager(on_scan_callback=on_hardware_rfid_tap)


# ----------------------------------------------------------------------
# HTTP Request Handler Kiosk (Port 8000)
# ----------------------------------------------------------------------
class KioskRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handler HTTP Kiosk Absensi Ringan (Thin Client / Edge Capture).
    - Menampilkan UI Kiosk Absensi NTP
    - Streaming kamera MJPEG via V4L2
    - Meneruskan data RFID/NIK dan foto jepretan ke Server Admin Pusat
    - Menyediakan SSE (/api/kiosk/events) untuk notifikasi tap hardware
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

        # 2. Server-Sent Events (SSE) untuk update Kiosk saat tap RFID fisik
        if clean_path == "/api/kiosk/events":
            self.handle_sse_kiosk_events()
            return

        # 3. Status scan absensi terbaru (Polling fallback)
        if clean_path == "/api/kiosk/latest":
            latest = event_hub.latest_event or {"active": True, "readers": rfid_hw_manager.active_devices}
            self.send_json(200, latest)
            return

        # 4. Status perangkat RFID Hardware yang terdeteksi
        if clean_path == "/api/rfid/devices":
            devices = rfid_hw_manager.scan_devices()
            self.send_json(200, {
                "success": True,
                "count": len(devices),
                "devices": devices,
                "in_config": config.RFID_IN_CONFIG,
                "out_config": config.RFID_OUT_CONFIG
            })
            return

        # 5. Cek identitas karyawan atau daftar karyawan ke Server Pusat (Forwarding)
        if clean_path in ["/api/employee", "/api/employees", "/api/attendance"]:
            self.forward_get_to_admin(self.path)
            return

        # 6. Akses foto absensi (Forward ke Server Pusat)
        if clean_path.startswith("/captures/"):
            self.forward_get_to_admin(clean_path)
            return

        # 7. File statis web kiosk (index.html, app.js, style.css)
        original_path = self.path
        self.path = clean_path
        try:
            super().do_GET()
        finally:
            self.path = original_path

    def do_POST(self):
        parsed_url = urlparse(self.path)
        clean_path = self.get_clean_path(parsed_url.path)

        # Tangani scan RFID / absensi dari web UI
        if clean_path in ["/api/attendance/scan", "/api/tap"]:
            self.handle_post_attendance_scan()
            return

        self.send_json(404, {"success": False, "message": f"Endpoint tidak ditemukan di Kiosk: {parsed_url.path}"})

    # ------------------------------------------------------------------
    # Server-Sent Events (SSE) Stream
    # ------------------------------------------------------------------
    def handle_sse_kiosk_events(self):
        """Menyediakan aliran event real-time SSE ke browser Kiosk."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = queue.Queue()
        event_hub.add_subscriber(q)

        # Kirim event sapaan awal beserta status reader
        init_data = json.dumps({
            "type": "INIT",
            "message": "Terhubung ke Kiosk Event Bus",
            "readers": rfid_hw_manager.active_devices
        })
        self.wfile.write(f"data: {init_data}\n\n".encode("utf-8"))
        self.wfile.flush()

        try:
            while True:
                try:
                    event_data = q.get(timeout=15.0)
                    msg = f"data: {json.dumps(event_data)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Ping keep-alive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            event_hub.remove_subscriber(q)

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
    # Proses Scan Absensi Web UI
    # ------------------------------------------------------------------
    def handle_post_attendance_scan(self):
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

        in_out = str(payload.get("in_out") or payload.get("type") or "").strip()
        reader_source = payload.get("reader") or "Web Kiosk UI"

        result = execute_attendance_pipeline(identifier=identifier, in_out=in_out, reader_name=reader_source, extra_params=payload)
        status_code = result.get("status_code", 200)
        self.send_json(status_code, result)

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
    # 1. Mulai Daemon Hardware Dual RFID Reader di Linux
    rfid_hw_manager.start()

    # 2. Jalankan HTTP Kiosk Server
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((config.HOST, config.PORT), KioskRequestHandler) as httpd:
        print("=" * 65)
        print("   TERMINAL KIOSK ABSENSI NTP (EDGE CAPTURE)")
        print(f"   Status          : AKTIF (Dual RFID: IN & OUT)")
        print(f"   Port Kiosk      : {config.PORT}")
        print(f"   URL Layar Absen : http://localhost:{config.PORT}")
        print(f"   Server Pusat    : {config.ADMIN_SERVER_URL}")
        print(f"   Reader IN (1)   : {config.RFID_IN_CONFIG['name']} ({config.RFID_IN_CONFIG['vendor']}:{config.RFID_IN_CONFIG['product']})")
        print(f"   Reader OUT (0)  : {config.RFID_OUT_CONFIG['name']} ({config.RFID_OUT_CONFIG['vendor']}:{config.RFID_OUT_CONFIG['product']})")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nMenghentikan Kiosk Absensi dengan aman...")
            rfid_hw_manager.running = False


if __name__ == "__main__":
    run_kiosk()
