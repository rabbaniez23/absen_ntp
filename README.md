# Absen NTP – Sistem Presensi Karyawan

Sistem presensi karyawan berbasis **Dual RFID Reader**, **kamera V4L2**, dan **Numpad**, yang berjalan sebagai terminal Kiosk di Linux Debian. Ditulis dengan Python murni (pustaka standar + `pymysql`) dan frontend Vanilla HTML/CSS/JS, dengan basis data **MariaDB**.

> Dokumentasi lengkap (arsitektur, hardware, histori, troubleshooting) ada di
> [`laporan_mingguan/konteks_projek_handover.md`](laporan_mingguan/konteks_projek_handover.md).
> Laporan progres per minggu ada di folder [`laporan_mingguan/`](laporan_mingguan/).

---

## Arsitektur: 3 Service Terpisah

| Service | Port | File | Fungsi |
| :--- | :--- | :--- | :--- |
| Kiosk | 8000 | `absen/capture.py` | Layar presensi, listener Dual RFID (kernel `/dev/input`), stream & snapshot kamera |
| Connector | 8002 | `connector.py` → `connector/connector.py` | Validasi karyawan, simpan foto, catat ke MariaDB |
| Admin | 8001 | `admin/admin.py` | Dashboard riwayat presensi & manajemen karyawan |

Jika database tidak tersambung, connector tetap mencatat ke cadangan JSON di `admin/data/` dan menulis peringatan `DATABASE TIDAK TERSAMBUNG` di log.

## Struktur Direktori

```text
employee-attendance/
├── absen/                 # Kiosk (port 8000)
│   ├── capture.py         # Server Kiosk + listener RFID
│   ├── camera_v4l2.py     # Akses kamera V4L2 (mmap, MJPEG)
│   ├── config.py
│   └── static/            # index.html, app.js, style.css
├── connector/             # Connector (port 8002)
│   ├── connector.py
│   ├── db.py
│   └── config.py          # DB_HOST default: db2.ntp.id
├── connector.py           # Launcher connector
├── admin/                 # Admin (port 8001)
│   ├── admin.py
│   ├── db.py
│   ├── config.py
│   ├── data/              # employees.json + cadangan JSON presensi
│   └── static/            # employees.html, style.css
├── index.php              # Redirect Apache /attendance → Kiosk port 8000
├── laporan_mingguan/      # Laporan progres & konteks proyek
└── requirements.txt       # pymysql
```

## Format `raw_data`

`{NIK 6 digit}{Jam:2}{Menit:2}{Tanggal:2}{Bulan:2}{In/Out:1}`, dengan `1` untuk Masuk dan `0` untuk Keluar.
Contoh: `210019122421091` berarti NIK 210019 Masuk pada 21/09 pukul 12:24. Foto disimpan dengan nama `{raw_data}.jpg`.

## Menjalankan di Debian (Tanpa sudo)

```bash
cd /home/debian/www/attendance

# Sekali saja: pasang pip & pymysql ke venv (venv Debian dibuat tanpa pip)
curl -sSL https://bootstrap.pypa.io/get-pip.py -o ~/get-pip.py
venv/bin/python ~/get-pip.py
venv/bin/python -m pip install -r requirements.txt

# Menjalankan / restart seluruh service
pkill -9 -f "connector.py" ; pkill -9 -f "capture.py" ; pkill -9 -f "admin.py"
nohup venv/bin/python connector.py > /dev/null 2>&1 &
nohup venv/bin/python absen/capture.py > /dev/null 2>&1 &
nohup venv/bin/python admin/admin.py > /dev/null 2>&1 &

# Cek koneksi database ("database_connected": true)
curl -s http://127.0.0.1:8002/api/health
```

| Alamat | Halaman |
| :--- | :--- |
| `http://localhost:8000` | Layar Kiosk presensi |
| `http://localhost:8001/employees.html` | Dashboard admin |

Log tiap service ada di `absen/logs/kiosk.log`, `connector/logs/connector.log`, dan `admin/logs/admin.log`.
