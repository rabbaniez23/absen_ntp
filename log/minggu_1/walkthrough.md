# Walkthrough: Pemisahan Backend Menjadi 2 Folder (absen & admin)

## Ringkasan Perubahan
Sesuai instruksi pembimbing (desain arsitektur Edge-Kiosk dan Central Server), sistem absensi telah dirombak dari satu server monolitik (`server.py`) menjadi 2 modul mandiri:

1. **`absen/` (Port 8000 — Kiosk Terminal)**
   - Khusus menangani hardware kamera Logitech C930e (`camera_v4l2.py`), sensor RFID, dan UI layar kiosk absensi (`index.html`).
   - Bersih dari koneksi database MariaDB / SQL (`no db server`), menghasilkan memory footprint yang sangat rendah.
   - Mengirimkan data NIK dan foto jepretan webcam ke server admin pusat melalui HTTP POST.

2. **`admin/` (Port 8001 — Central Server & Database)**
   - Mengelola koneksi database MariaDB (`db.py`) dan data karyawan.
   - Menyajikan dashboard web manajemen karyawan (`employees.html`).
   - Menerima dan memproses pencatatan absensi serta menyimpan arsip foto ke `admin/captures/`.

## Struktur Direktori Baru
```text
employee-attendance/
├── absen/                      # Terminal Kiosk (Port 8000)
│   ├── capture.py              # Server kiosk & streaming kamera
│   ├── camera_v4l2.py          # Driver kamera V4L2
│   ├── config.py               # Port 8000 & target server admin
│   └── static/
│       ├── index.html          # Tampilan Absen NTP
│       ├── app.js              # State machine kiosk
│       └── style.css
│
└── admin/                      # Central Server (Port 8001)
    ├── admin.py                # Server admin & API master data
    ├── db.py                   # Layer database MariaDB
    ├── config.py               # Port 8001 & kredensial DB
    ├── data/                   # Fallback data JSON
    ├── captures/               # Arsip foto absensi
    └── static/
        ├── employees.html      # Tampilan manajemen karyawan
        └── style.css
```

## Verifikasi Sintaks
Modul `admin.py`, `capture.py`, dan kedua file `config.py` telah diverifikasi menggunakan `py_compile` dan berhasil tanpa error sintaks.
