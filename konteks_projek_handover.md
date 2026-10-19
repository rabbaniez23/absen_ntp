# KONTEKS PROYEK LENGKAP & REKAP STATUS SISTEM (HANDOVER DOKUMEN)

> **Untuk AI Asisten Baru:**  
> Dokumen ini berisi ringkasan arsitektur, histori implementasi, konfigurasi perangkat keras, batasan teknis, dan seluruh pekerjaan yang telah diselesaikan hingga **Minggu Ke-6 (19 Oktober 2026)** untuk sistem presensi karyawan **Absen NTP**. Bacalah dokumen ini dengan seksama sebelum memberikan instruksi atau menulis kode baru.

---

## 1. Profil Proyek & Lingkungan Teknis

* **Nama Sistem:** Absen NTP – Automated Biometric & Dual RFID Attendance System
* **Mesin Target (Deployment):** Linux Debian (Mini PC / Terminal Kiosk Low-Spec)
* **Direktori Deployment:** `/home/debian/www/attendance`
* **User Linux:** `debian`
* **BATASAN KRITIS:** User `debian` **TIDAK BISA RUN `sudo`** secara bebas di terminal produksi. Semua perintah restart, eksekusi, dan manajemen service **HARUS BISA DIJALANKAN TANPA `sudo`** (menggunakan Python Virtual Environment `/home/debian/www/attendance/venv/bin/python`).
* **Repositori GitHub:** `https://github.com/rabbaniez23/absen_ntp.git` (Branch utama: `main`)
* **Arsitektur Pemrograman:**
  - Python murni untuk backend service (menggunakan library standar: `socketserver`, `http.server`, `fcntl`, `mmap`, `struct`, tanpa OpenCV / tanpa framework berat).
  - Vanilla HTML5, CSS3, dan Modern JavaScript di frontend Kiosk (tanpa React/Vue, ringan, responsif).
  - Basis Data: **MariaDB / MySQL**.

---

## 2. Arsitektur 3 Service Mandiri (Decoupled Services)

Sistem dirancang terpisah menjadi 3 service independen agar jika satu service bermasalah atau dimatikan, service lainnya tetap beroperasi:

```
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│     absen/capture.py            │                 │     connector/connector.py      │
│  (Port 8000 - Terminal Kiosk)   │───(HTTP POST)──►│  (Port 8002 - Database Bridge)  │
│ - Hardware Dual RFID Listener   │                 │ - Koneksi MariaDB               │
│ - Dedicated Numpad Keyboard     │                 │ - Format 15-digit RAW_DATA      │
│ - Camera V4L2 Stream & Snapshot │                 │ - Penyimpanan Foto di captures/ │
│ - Web Kiosk Frontend (UI)       │                 │ - Table: attendance & error     │
└─────────────────────────────────┘                 └─────────────────────────────────┘
                                                             ▲
                                                             │ (Query Database)
                                                    ┌────────┴────────────────────────┐
                                                    │     admin/admin.py              │
                                                    │  (Port 8001 - Admin Dashboard)  │
                                                    │ - Manajemen Karyawan (CRUD)     │
                                                    │ - Riwayat Presensi HD + Filter  │
                                                    │ - Dapat dimatikan sewaktu-waktu │
                                                    └─────────────────────────────────┘
```

1. **`connector.py` (Port 8002):** Backend utama yang menghubungkan Kiosk ke database MariaDB dan menyimpan foto ke folder `captures/`.
2. **`absen/capture.py` (Port 8000):** Menjalankan web Kiosk, membaca input hardware secara langsung di level Linux kernel, dan streaming kamera.
3. **`admin/admin.py` (Port 8001):** Panel dashboard admin untuk melihat log absensi dan data master karyawan.

---

## 3. Integrasi Perangkat Keras Fisik (Hardware Setup)

### A. Dual RFID Reader (Event-Driven via Linux Kernel `/dev/input/event*`)
Sistem tidak mengandalkan input fokus browser, melainkan membaca langsung file descriptor kernel Linux dengan penguncian eksklusif `EVIOCGRAB` (mencegah karakter bocor/terketik liar ke layar):
1. **Reader 1 (PRESENSI MASUK / IN - Kode: 1):**
   - Vendor/Product ID: `1a86:dd01` (QinHeng Electronics)
   - Tombol fisik / trigger: Tap kartu pada reader ini otomatis mencatat **MASUK**.
2. **Reader 2 (PRESENSI KELUAR / OUT - Kode: 0):**
   - Vendor/Product ID: `ffff:0035` (Sycreader SYC ID&IC USB Reader)
   - Tombol fisik / trigger: Tap kartu pada reader ini otomatis mencatat **KELUAR**.

### B. Kamera Linux V4L2 (Video4Linux2 Native)
* **Perangkat Saat Ini:** Logitech C270 Webcam (`046d:0825`) pada `/dev/video0`.
* **Mekanisme Kerja:** Modul [`absen/camera_v4l2.py`](file:///d:/magang/projek/employee-attendance/absen/camera_v4l2.py) membaca memory map `mmap` dari V4L2 secara langsung dengan format MJPEG 640x480.
* **Streaming Browser:** Endpoint `http://localhost:8000/api/camera/stream` disajikan dalam bentuk MJPEG stream ke tag `<img id="streamVideo">`, sehingga tidak membutuhkan WebRTC atau dialog izin browser.

### C. Dedicated Numpad Keypad (Input Samping Eksklusif)
Karyawan juga dapat melakukan presensi manual menggunakan keypad numerik (Numpad) sebelah kanan keyboard. Sistem **MEMBLOKIR TOTAL** keyboard biasa dan **HANYA** menerima interaksi Numpad samping:
* **`0` – `9` (Numpad):** Input NIK (dibatasi ketat **maksimal 6 digit**).
* **`Enter` (Numpad):** Memicu **🟢 PRESENSI MASUK (IN / Kode: 1)**.
* **`+` (Plus Numpad):** Memicu **🔴 PRESENSI KELUAR (OUT / Kode: 0)**.
* **`-` (Minus) & `*` (Bintang):** **🧹 CLEAR / RESET** seluruh inputan.
* **`/` (Slash Numpad):** **⌫ BACKSPACE** (menghapus 1 digit terakhir).
* **NumLock Handling:** Berfungsi sempurna baik status NumLock menyala (ON) maupun mati (OFF navigasi).

---

## 4. Skema Basis Data MariaDB & Spesifikasi Khusus

### A. Format `RAW_DATA` Spesifikasi Pembimbing (Pola 15 Digit)
Setiap transaksi dan nama file foto disimpan seragam dengan pola 15 digit:
$$\text{RAW\_DATA} = \text{\{NIK 6 digit\}} + \text{\{Jam:2\}} + \text{\{Menit:2\}} + \text{\{Tanggal:2\}} + \text{\{Bulan:2\}} + \text{\{In/Out:1\}}$$
*Contoh:* NIK `210019` tap Masuk pada 21 September pukul 12:24 ➔ `210019122421091` dan file foto bernama `210019122421091.jpg`.

### B. Skema Tabel Relasional Opsi B (Pemisahan Kartu RFID)
1. **`employees`:** Master data karyawan (`id`, `nik`, `name`, `position`, dll).
2. **`rfid_cards`:** Tabel relasi kartu mandiri (`id`, `rfid_uid`, `employee_id`, `card_status`, `assigned_at`). Mendukung 1 karyawan memiliki banyak kartu dan pelacakan kartu aktif/hilang.
3. **`attendance`:** Riwayat absensi sukses (Kolom: `id`, `raw_data`, `image`).
4. **`attendance_error`:** Riwayat kartu belum terdaftar / invalid. Sistem tetap memotret wajah orang yang tap kartu dan mencatat waktu untuk keperluan audit keamanan fisik.

---

## 5. Ringkasan Progres Mingguan yang Telah Selesai

* **Minggu 1 & 2:** Inisiasi sistem Kiosk, setup database MariaDB, formula 15-digit `raw_data`, dan modul kamera V4L2 native.
* **Minggu 3:** Pemisahan sistem menjadi 3 service decoupled (`capture.py`, `connector.py`, `admin.py`), integrasi driver Dual-RFID (`1a86:dd01` & `ffff:0035`), udev rules, dan `EVIOCGRAB`.
* **Minggu 4:** Implementasi skema database relasional Opsi B (`rfid_cards`), penanganan tabel `attendance_error`, optimasi antrian cepat (screen hold 1.2s & debounce 0.7s), dan sinkronisasi real-time dua arah (Dual-Channel SSE + 500ms fast polling).
* **Minggu 5 & 6:** Pemetaan dedicated Numpad keypad, pembatasan ketat NIK 6 digit, fungsi tombol `-`, `*`, `/`, `Enter`, `+`, serta pemblokiran total keyboard utama dan backspace biasa agar operasional Kiosk terisolasi rapi.
* **Pengujian Hardware:** Kamera Logitech C270 (`046d:0825`) pada `/dev/video0` dan Dual RFID telah terverifikasi menyala dan berfungsi normal di mesin fisik Debian.

---

## 6. Prosedur Operasional di Terminal Debian (Cheat Sheet)

### A. Persiapan Virtual Environment (Sekali Saja, Tanpa sudo)
Venv di Debian dibuat **tanpa `pip`** (modul `ensurepip` tidak tersedia tanpa paket `python3-venv`). Jika `venv/bin/pip` tidak ada, pasang pip secara manual lalu pasang dependensi:

```bash
cd /home/debian/www/attendance
curl -sSL https://bootstrap.pypa.io/get-pip.py -o ~/get-pip.py
venv/bin/python ~/get-pip.py
venv/bin/python -m pip install -r requirements.txt

# Verifikasi pymysql terpasang di venv
venv/bin/python -c "import pymysql; print('pymysql OK')"
```

> ⚠️ **Wajib dicek setiap kali venv dibuat ulang atau pindah mesin.** Tanpa `pymysql`, ketiga service **tidak tersambung ke database sama sekali** dan diam-diam memakai cadangan JSON (`admin/data/*.json`). Gejalanya: tap kartu yang sudah terdaftar dianggap TIDAK VALID dan riwayat tidak masuk ke database.

### B. Menjalankan & Mengelola Service

```bash
# Direktori Kerja
cd /home/debian/www/attendance

# Menarik Update Kode Terbaru
git pull origin main

# Menjalankan Seluruh Service (Tanpa sudo):
pkill -9 -f "connector.py" ; pkill -9 -f "capture.py" ; pkill -9 -f "admin.py"
nohup /home/debian/www/attendance/venv/bin/python connector.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python absen/capture.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python admin/admin.py > /dev/null 2>&1 &

# Memeriksa Service yang Berjalan:
ps aux | grep -E "connector\.py|capture\.py|admin\.py" | grep -v grep
```

### C. Troubleshooting Koneksi Database
Database produksi: **MariaDB di `db2.ntp.id`** (lihat `connector/config.py` dan `admin/config.py`).

```bash
# 1. Cek apakah connector tersambung ke database ("database_connected": true)
curl -s http://127.0.0.1:8002/api/health

# 2. Cari peringatan koneksi database di log
grep -E "DATABASE TIDAK TERSAMBUNG|Startup|kendala|Gagal" connector/logs/connector.log | tail -n 20
grep -E "DATABASE TIDAK TERSAMBUNG|Startup" admin/logs/admin.log | tail -n 10
```

* Saat start, connector & admin menulis `[Startup] Database MariaDB tersambung: ...` jika koneksi berhasil.
* Jika gagal, log menampilkan `DATABASE TIDAK TERSAMBUNG: <alasan>` (maksimal sekali per menit agar log tidak banjir).
* Saat database mati, cadangan JSON tetap mengenali **NIK maupun nomor kartu RFID** dari `admin/data/employees.json`, sehingga absensi tetap berjalan. Record yang tersimpan saat database mati ditandai `"db_synced": false` dan **tidak otomatis** dikirim ke database.

---

## 7. Catatan Penting untuk AI Berikutnya:
1. **Jangan gunakan `sudo`** saat memberikan perintah terminal ke user, gunakan path interpreter virtual environment `/home/debian/www/attendance/venv/bin/python`.
2. **Jangan merusak pemetaan tombol Numpad**, karena tata letak tombol sudah disepakati bersama pembimbing lapangan.
3. Selalu pertahankan arsitektur multi-service decoupled dan kemurnian kode (bebas dependensi berat).
4. **Jika muncul gejala "kartu terdaftar tapi TIDAK VALID" atau "riwayat tidak masuk database"**, cek dulu lingkungan sebelum mengubah kode: `venv/bin/python -c "import pymysql"` dan `curl -s http://127.0.0.1:8002/api/health` (lihat bagian 6C). Kasus 19 Oktober 2026 penyebabnya adalah `pymysql` belum terpasang di venv, bukan bug di kode.
