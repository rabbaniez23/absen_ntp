# 🏢 Sistem Absensi Karyawan (absen_ntp)

Sistem Absensi Otomatis berbasis **WebRTC**, **USB Smart Card RFID**, dan arsitektur **Micro-Server Python** (tanpa framework eksternal). Sistem ini dirancang untuk sistem absensi (absen_ntp) yang responsif, berkecepatan tinggi, dan dapat berjalan secara mandiri (*standalone*) di Linux (Debian/Ubuntu/Mint) maupun Windows.

---

## ✨ Fitur Utama

- **WebRTC Camera Capture**:
  - Live video stream dari webcam (resolusi ideal HD 720p/1080p).
  - Biometric Face Oval Guide (panduan posisi wajah dinamis).
  - Shutter flash effect dan hitung mundur otomatis 3-2-1.
  - Fitur toggle **Mirror Mode** interaktif (Normal vs Mirror) dengan sinkronisasi canvas snapshot.
- **Dukungan Smart Card RFID (USB HID)**:
  - Bekerja secara *plug-and-play* dengan USB RFID Reader standar (125 kHz / 13.56 MHz).
  - Mode *Keyboard Emulation* dengan *auto-focus trapping* cerdas (tahan gangguan sentuhan layar).
  - Mendeteksi nomor UID kartu secara instan dan memverifikasi identitas karyawan.
- **Backend Ringan & Zero Framework**:
  - Dibangun murni menggunakan pustaka standar Python (`http.server`, `urllib`, `json`, `pathlib`).
  - Tidak memerlukan framework berat seperti Django atau Flask.
- **Penyimpanan Ganda (MariaDB + JSON Fallback)**:
  - Terkoneksi langsung ke MariaDB menggunakan parameterized query SQL murni (tanpa ORM) untuk performa maksimal.
  - Dilengkapi mekanisme **Auto-Fallback ke JSON** jika server database offline, sehingga proses absensi tidak akan pernah terganggu.
- **Struktur Filesystem Terorganisir**:
  - Foto disimpan berpartisi berdasarkan tanggal: `captures/TAHUN/BULAN/TANGGAL/`.
  - Database hanya menyimpan *relatif path* untuk menjaga bobot database tetap ringan dan cepat.
- **Autostart & Standalone Linux (absen_ntp)**:
  - Skrip deployment otomatis ke `/opt/employee-attendance`.
  - Systemd service unit (`attendance-server.service`) dengan auto-restart.
  - XDG Desktop Entry (`attendance-kiosk.desktop`) untuk meluncurkan Chromium fullscreen saat boot.

---

## 📂 Struktur Direktori Proyek

```text
absen_ntp/
├── .gitignore                 # Konfigurasi pengabaian file sampah/cache
├── README.md                  # Dokumentasi lengkap sistem
├── config.py                  # Pengaturan jalur direktori & konfigurasi database
├── db.py                      # Lapisan SQL MariaDB & fallback JSON
├── server.py                  # HTTP server utama (port 8000)
├── view_db.py                 # CLI Viewer tabel database di terminal
├── migrate_json_to_db.py      # Skrip migrasi data riwayat JSON ke MariaDB
├── requirements.txt           # Dependensi Python murni (pymysql)
│
├── static/                    # Frontend Web (absen_ntp)
│   ├── index.html             # Antarmuka Absensi (absen_ntp)
│   ├── style.css              # Styling Modern Glassmorphism
│   └── app.js                 # State machine, WebRTC kamera, & RFID event listener
│
├── scripts/                   # Skrip Otomatisasi & Deployment Linux
│   ├── debian_setup.sh        # Setup user & paket sistem Linux
│   ├── deploy_debian.sh       # Skrip deploy file ke /opt/
│   ├── launch_kiosk.sh        # Dedicated Chromium launcher (fullscreen)
│   ├── setup_autostart.sh     # Konfigurasi systemd & autostart desktop
│   ├── attendance-server.service # Unit file systemd
│   └── attendance-kiosk.desktop  # Shortcut autostart browser
│
├── sql/                       # Skema Basis Data & Migrasi
│   ├── schema.sql             # DDL pembuatan tabel employees & attendance
│   └── import_data.sql        # Skrip impor data awal otomatis
│
├── tests/                     # Suite Pengujian Otomatis
│   └── test_windows_final.py  # 9 pengujian integrasi & end-to-end
│
├── data/                      # Master Data & Storage JSON
│   ├── employees.json         # Data karyawan terdaftar
│   └── attendance.json        # Log riwayat absensi lokal
│
├── captures/                  # Direktori penyimpanan foto webcam
└── logs/                      # Log aktivitas & akses server
```

---

## 🚀 Panduan Memulai Cepat (Quick Start)

### 1. Persyaratan Sistem
- Python 3.9+
- Web browser modern (Google Chrome, Chromium, atau Microsoft Edge)
- Webcam (USB atau bawaan laptop)
- *(Opsional)* USB RFID Reader & Server MariaDB / MySQL

### 2. Menjalankan di Windows

1. Buka PowerShell / Terminal di folder proyek.
2. Pasang dependensi database:
   ```bash
   pip install -r requirements.txt
   ```
3. Jalankan server:
   ```bash
   python server.py
   ```
4. Buka browser di alamat:
   ```text
   http://localhost:8000
   ```
5. Untuk melihat data yang tersimpan di database kapan saja:
   ```bash
   python view_db.py
   ```

### 3. Menjalankan di Linux (Debian / Ubuntu / Mint)

1. Jalankan skrip persiapan awal:
   ```bash
   sudo bash scripts/debian_setup.sh
   ```
2. Deploy aplikasi ke `/opt/employee-attendance`:
   ```bash
   sudo bash scripts/deploy_debian.sh
   ```
3. Pasang autostart absen_ntp:
   ```bash
   sudo bash scripts/setup_autostart.sh
   ```

---

## 🧪 Menjalankan Pengujian Otomatis (Testing)

Proyek ini telah dilengkapi dengan unit & integration test suite lengkap yang mencakup 9 skenario pengujian:
```bash
python tests/test_windows_final.py
```
*(Atau `python3 tests/test_windows_final.py` di Linux)*.

---

## 📡 Dokumentasi Endpoint API

| Method | Endpoint | Keterangan | Parameter / Body |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Menampilkan antarmuka web absen_ntp | - |
| `GET` | `/api/employee?id={ID_OR_RFID}` | Mencari data karyawan berdasarkan ID / UID RFID | Query param `id` |
| `POST` | `/api/upload` | Mengunggah foto absensi (.PNG) dan mencatat ke database | `multipart/form-data`: `employee_id`, `image` |

---

## 👤 Data Pengujian Default (RFID UID)

| UID RFID | Employee ID | Nama Karyawan | Status |
| :--- | :--- | :--- | :--- |
| `983746128` | `EMP001` | Budi Santoso | Aktif |
| `827364928` | `EMP002` | Andi Wijaya | Aktif |

*Cukup tempelkan kartu RFID atau ketikkan salah satu angka UID di atas lalu tekan Enter untuk menguji alur absensi.*

---

## 📄 Lisensi
Proyek ini dikembangkan untuk kebutuhan operasional sistem absensi cerdas (absen_ntp).
