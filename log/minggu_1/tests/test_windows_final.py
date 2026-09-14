"""
Pengujian Otomatis Akhir Sistem Presensi Karyawan
Menguji fungsi server HTTP, berkas statis, API pencarian karyawan, simulasi RFID,
dan penanganan kesalahan.
"""

import datetime
import io
import json
import os
import sys
import unittest
import urllib.request
from pathlib import Path

# Tambahkan direktori root proyek ke sys.path
TEST_DIR = Path(__file__).resolve().parent
BASE_DIR = TEST_DIR.parent if TEST_DIR.name == "tests" else TEST_DIR
sys.path.insert(0, str(BASE_DIR))

import config
import db


class TestWindowsFinalAbsenNtp(unittest.TestCase):
    """Rangkaian Pengujian Menyeluruh (End-to-End) Sistem Presensi."""

    @classmethod
    def setUpClass(cls):
        cls.server_url = f"http://127.0.0.1:{config.PORT}"
        print("\n" + "=" * 65)
        print("  PENGUJIAN OTOMATIS SISTEM PRESENSI KARYAWAN")
        print("=" * 65)

    def test_01_server_running_and_html_accessible(self):
        """Uji 1: Server berjalan dan halaman HTML utama dapat diakses."""
        req = urllib.request.Request(f"{self.server_url}/")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            content = response.read().decode("utf-8")
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("EMPLOYEE ATTENDANCE", content)
            self.assertIn("webcamVideo", content)
            print("  [LULUS] 01. Server aktif & HTML utama dapat diakses (HTTP 200)")

    def test_02_css_loaded(self):
        """Uji 2: Berkas stylesheet CSS berhasil disajikan."""
        req = urllib.request.Request(f"{self.server_url}/style.css")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            content = response.read().decode("utf-8")
            self.assertIn(".absen-ntp-container", content)
            self.assertIn("#webcamVideo", content)
            print("  [LULUS] 02. Berkas CSS termuat dengan benar (HTTP 200)")

    def test_03_js_loaded(self):
        """Uji 3: Berkas logika JavaScript aplikasi berhasil disajikan."""
        req = urllib.request.Request(f"{self.server_url}/app.js")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            content = response.read().decode("utf-8")
            self.assertIn("AppState", content)
            self.assertIn("initializeCamera", content)
            self.assertIn("setMirrorMode", content)
            print("  [LULUS] 03. Berkas JavaScript aplikasi termuat (HTTP 200)")

    def test_04_employee_lookup_by_id(self):
        """Uji 4: Pencarian data karyawan berdasarkan ID Karyawan."""
        url = f"{self.server_url}/api/employee?id=EMP001"
        with urllib.request.urlopen(url, timeout=5) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("employee_id"), "EMP001")
            self.assertEqual(data.get("name"), "Budi Santoso")
            print(f"  [LULUS] 04. Pencarian karyawan via ID: EMP001 -> {data['name']}")

    def test_05_rfid_simulation_lookup(self):
        """Uji 5: Simulasi pemindaian UID kartu RFID."""
        # Tes RFID 1: 983746128 -> Budi Santoso
        url1 = f"{self.server_url}/api/employee?id=983746128"
        with urllib.request.urlopen(url1, timeout=5) as response:
            data1 = json.loads(response.read().decode("utf-8"))
            self.assertTrue(data1.get("success"))
            self.assertEqual(data1.get("employee_id"), "EMP001")

        # Tes RFID 2: 827364928 -> Andi Wijaya
        url2 = f"{self.server_url}/api/employee?id=827364928"
        with urllib.request.urlopen(url2, timeout=5) as response:
            data2 = json.loads(response.read().decode("utf-8"))
            self.assertTrue(data2.get("success"))
            self.assertEqual(data2.get("employee_id"), "EMP002")
            self.assertEqual(data2.get("name"), "Andi Wijaya")
            print("  [LULUS] 05. Simulasi tap kartu RFID berfungsi (Kartu: 983746128, 827364928)")

    def test_06_employee_not_found(self):
        """Uji 6: Penanganan ketika kartu / ID karyawan tidak terdaftar."""
        url = f"{self.server_url}/api/employee?id=INVALID_999"
        try:
            urllib.request.urlopen(url, timeout=5)
            self.fail("Seharusnya mengembalikan respons HTTP 404 untuk karyawan tidak terdaftar")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 404)
            data = json.loads(err.read().decode("utf-8"))
            self.assertFalse(data.get("success"))
            print("  [LULUS] 06. ID karyawan tidak dikenal mengembalikan HTTP 404")

    def test_07_png_captured_and_saved(self):
        """Uji 7: Validasi payload PNG, pengecekan magic bytes, dan penyimpanan ke disk."""
        # Buat payload biner PNG 1x1 yang valid
        valid_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        boundary = "----WebKitFormBoundaryFinalTestUpload"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="employee_id"\r\n\r\n'
            f"EMP001\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="webcam.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + valid_png + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{self.server_url}/api/upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body))
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=8) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            filepath = data.get("filepath")
            self.assertTrue(filepath)

            # Pastikan berkas benar-benar tersimpan di disk
            disk_file = config.BASE_DIR / filepath
            self.assertTrue(disk_file.exists())
            self.assertGreater(disk_file.stat().st_size, 0)
            print(f"  [LULUS] 07. PNG divalidasi & tersimpan di disk: {filepath}")

    def test_08_mariadb_or_storage_layer(self):
        """Uji 8: Penyimpanan data riwayat presensi melalui layer basis data."""
        now = datetime.datetime.now()
        res = db.record_attendance("EMP002", now, "captures/test_audit.png", "SUCCESS")
        self.assertTrue(res)

        # Periksa penyimpanan presensi lokal
        attendance_file = config.DATA_DIR / "attendance.json"
        self.assertTrue(attendance_file.exists())
        with open(attendance_file, "r", encoding="utf-8") as f:
            records = json.load(f)
            self.assertGreater(len(records), 0)
            last_record = records[-1]
            self.assertEqual(last_record["employee_id"], "EMP002")
            self.assertEqual(last_record["attendance_status"], "SUCCESS")
        print("  [LULUS] 08. Layer penyimpanan/database berhasil mencatat log presensi")

    def test_09_multiple_attendance_sequence(self):
        """Uji 9: Simulasi pencarian presensi berurutan."""
        for emp_id in ["EMP001", "EMP002", "EMP001"]:
            emp = db.lookup_employee(emp_id)
            self.assertIsNotNone(emp)
            self.assertEqual(emp["employee_id"], emp_id)
        print("  [LULUS] 09. Simulasi pencarian presensi beruntun berjalan sukses")

    def test_10_employee_management_crud(self):
        """Uji 10: API manajemen data karyawan (GET, POST, DELETE) dan halaman web admin."""
        # 1. Periksa aksesibilitas employees.html
        req = urllib.request.Request(f"{self.server_url}/employees.html")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            content = response.read().decode("utf-8")
            self.assertIn("MANAJEMEN DATA KARYAWAN", content)

        # 2. Uji GET /api/employees
        req = urllib.request.Request(f"{self.server_url}/api/employees")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIsInstance(data.get("employees"), list)

        # 3. Uji POST /api/employees (tambah data karyawan)
        payload = json.dumps({
            "employee_id": "TESTEMP99",
            "name": "Testing Employee",
            "rfid_uid": "998877665"
        }).encode("utf-8")
        post_req = urllib.request.Request(
            f"{self.server_url}/api/employees",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(post_req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            res = json.loads(response.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

        # Pastikan data karyawan baru dapat ditemukan
        emp = db.lookup_employee("998877665")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["name"], "Testing Employee")

        # 4. Uji DELETE /api/employees (hapus data karyawan)
        del_req = urllib.request.Request(
            f"{self.server_url}/api/employees?id=TESTEMP99",
            method="DELETE"
        )
        with urllib.request.urlopen(del_req, timeout=5) as response:
            self.assertEqual(response.status, 200)
            res = json.loads(response.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

        print("  [LULUS] 10. Halaman manajemen karyawan & API CRUD berfungsi sempurna")


if __name__ == "__main__":
    unittest.main(verbosity=1)
