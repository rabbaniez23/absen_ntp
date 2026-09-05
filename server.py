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

# Maximum allowed upload size (10 MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Standard PNG magic signature
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# ----------------------------------------------------------------------
# Centralized Logging Setup (Console + Rotating File logs/app.log)
# ----------------------------------------------------------------------
logger = logging.getLogger("AttendanceServer")
logger.setLevel(logging.INFO)

# Avoid duplicate handlers if reloaded
if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler (logs/app.log, max 5MB, 5 backups)
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)


class AttendanceRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP request handler serving static assets and attendance APIs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        """Routes HTTP access messages through logger instead of stderr."""
        logger.info(f"HTTP {self.address_string()} - {format % args}")

    def end_headers(self):
        """Forces no-cache headers on all HTTP responses to avoid stale browser cache."""
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, status_code: int, data: dict):
        """Sends a JSON response with proper HTTP headers."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        """Routes GET requests to static file handler or API endpoints."""
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/employee":
            self.handle_get_employee(parsed_url)
        else:
            super().do_GET()

    def do_POST(self):
        """Routes POST requests to API endpoints."""
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/upload":
            self.handle_post_upload()
        else:
            logger.warning(f"ENDPOINT NOT FOUND: {parsed_url.path}")
            self.send_json(404, {
                "success": False,
                "message": f"Endpoint not found: {parsed_url.path}"
            })

    def handle_get_employee(self, parsed_url):
        """Lookup employee via MariaDB parameterized query with JSON fallback."""
        query_params = parse_qs(parsed_url.query)
        lookup_id = query_params.get("id", [""])[0].strip()

        if not lookup_id:
            logger.warning("EMPLOYEE LOOKUP FAILED: Missing 'id' parameter")
            self.send_json(400, {
                "success": False,
                "message": "Missing 'id' query parameter"
            })
            return

        logger.info(f"EMPLOYEE LOOKUP {lookup_id}")

        emp = db.lookup_employee(lookup_id)
        if emp:
            logger.info(f"EMPLOYEE FOUND {emp['employee_id']} ({emp['name']}) [source: {emp.get('source', 'unknown')}]")
            self.send_json(200, {
                "success": True,
                "employee_id": emp["employee_id"],
                "name": emp["name"],
                "rfid_uid": emp.get("rfid_uid") or emp["employee_id"]
            })
        else:
            logger.warning(f"EMPLOYEE NOT FOUND {lookup_id}")
            self.send_json(404, {
                "success": False,
                "message": "Employee not found"
            })

    def handle_post_upload(self):
        """Handles PNG image upload with Employee ID validation and disk storage."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length <= 0:
            logger.warning("UPLOAD REJECTED: Empty request body")
            self.send_json(400, {
                "success": False,
                "message": "Empty request body"
            })
            return

        if content_length > MAX_UPLOAD_SIZE:
            logger.warning(f"UPLOAD REJECTED: Size {content_length} bytes exceeds {MAX_UPLOAD_SIZE} limit")
            self.send_json(413, {
                "success": False,
                "message": f"Payload too large: exceeds maximum limit of {MAX_UPLOAD_SIZE // (1024*1024)}MB"
            })
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            logger.warning(f"UPLOAD REJECTED: Invalid Content-Type '{content_type}'")
            self.send_json(400, {
                "success": False,
                "message": "Content-Type must be multipart/form-data"
            })
            return

        try:
            raw_body = self.rfile.read(content_length)
        except Exception as e:
            logger.error(f"UPLOAD READ ERROR: {e}")
            self.send_json(500, {
                "success": False,
                "message": f"Failed to read upload payload: {str(e)}"
            })
            return

        # Parse multipart payload
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
            logger.error(f"MULTIPART PARSE ERROR: {e}")
            self.send_json(400, {
                "success": False,
                "message": f"Malformed multipart data: {str(e)}"
            })
            return

        # Validate Employee ID
        if not employee_id:
            logger.warning("UPLOAD REJECTED: Missing employee_id field")
            self.send_json(400, {
                "success": False,
                "message": "Missing 'employee_id' in form data"
            })
            return

        if not re.match(r"^[A-Za-z0-9_-]+$", employee_id):
            logger.warning(f"UPLOAD REJECTED: Illegal characters in employee_id '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Invalid characters in employee_id. Only alphanumeric, dashes, and underscores allowed."
            })
            return

        # Validate Image Bytes
        if not image_bytes:
            logger.warning(f"UPLOAD REJECTED: Missing image data for employee_id '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Missing 'image' file in form data"
            })
            return

        if not image_bytes.startswith(PNG_SIGNATURE):
            logger.warning(f"UPLOAD REJECTED: Invalid image signature for employee_id '{employee_id}'")
            self.send_json(400, {
                "success": False,
                "message": "Invalid file format. Uploaded image must be a valid PNG."
            })
            return

        # Generate timestamps and paths
        now = datetime.datetime.now()
        year_str = now.strftime("%Y")
        month_str = now.strftime("%m")
        day_str = now.strftime("%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")

        target_dir = config.CAPTURES_DIR / year_str / month_str / day_str
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{employee_id}_{timestamp_str}.png"
        file_path = target_dir / filename

        # Write image to disk
        try:
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            logger.info(f"IMAGE SAVED {employee_id} -> {filename} ({len(image_bytes)} bytes)")
        except Exception as e:
            logger.error(f"DISK WRITE ERROR: Failed to save {file_path}: {e}")
            self.send_json(500, {
                "success": False,
                "message": f"Failed to save image to disk: {str(e)}"
            })
            return

        rel_path = str(file_path.relative_to(config.BASE_DIR)).replace("\\", "/")

        # Record attendance in MariaDB using direct SQL parameterized query
        db.record_attendance(employee_id, now, rel_path, "SUCCESS")

        logger.info(f"ATTENDANCE SUCCESS {employee_id}")

        # Send JSON response
        self.send_json(200, {
            "success": True,
            "message": "Attendance saved",
            "employee_id": employee_id,
            "filename": filename,
            "filepath": rel_path,
            "timestamp": now.isoformat(timespec="seconds")
        })


def run_server():
    """Starts the HTTP server on configured host and port."""
    # Attempt automatic database and table initialization
    db.init_database_tables()

    address = (config.HOST, config.PORT)
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(address, AttendanceRequestHandler) as httpd:
        logger.info("=" * 60)
        logger.info(f"SERVER STARTED at http://localhost:{config.PORT}")
        logger.info(f"Serving static files from: {config.STATIC_DIR}")
        logger.info(f"Captures stored under: {config.CAPTURES_DIR}")
        logger.info(f"Employee data loaded from: {config.EMPLOYEES_FILE}")
        logger.info(f"Log file active at: {config.LOG_FILE}")
        logger.info("=" * 60)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("SERVER SHUTTING DOWN GRACEFULLY...")
        finally:
            httpd.server_close()


if __name__ == "__main__":
    run_server()
