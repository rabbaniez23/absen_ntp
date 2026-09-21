# Laporan Progres Mingguan (Minggu Ke-3)

**Nama Proyek:** Sistem Presensi Karyawan Berbasis Dual RFID, Kamera V4L2, dan Multi-Service Decoupled  
**Periode Pengerjaan:** 15 September – 21 September 2026  
**Penyusun:** Mahasiswa Magang  
**Repository:** `employee-attendance/`  

---

## Ringkasan Eksekutif (Executive Summary)

Pada minggu ke-3 (15 – 21 September 2026), fokus pengerjaan diarahkan pada **integrasi perangkat keras Dual RFID Reader di level kernel Linux**, **rekayasa arsitektur 3-Service mandiri**, **penyempurnaan format database sesuai instruksi pembimbing**, serta **penataan antarmuka pengguna (UI) Kiosk dan Admin Dashboard**.

Seluruh fitur inti berhasil diselesaikan, diuji coba pada mesin fisik Debian Linux dengan perangkat keras asli (Webcam Logitech C930e, Reader QinHeng, Reader Sycreader), dan siap digunakan untuk operasional harian.

---

## 1. Integrasi Hardware Dual RFID Reader (Kernel Level & Event-Driven)

Sebelumnya pembacaan RFID mengandalkan simulasi keyboard biasa di antarmuka browser. Pada minggu ini, sistem ditingkatkan menjadi **pembacaan langsung dari Linux Kernel Input Subsystem (`/dev/input/event*`)**.

### A. Identifikasi & Pemetaan Perangkat Keras
Berdasarkan investigasi perangkat USB (`lsusb` dan `/proc/bus/input/devices`), kedua reader fisik dipetakan secara otomatis:
1. **Reader 1: QinHeng Electronics (`1a86:dd01`)** ➔ Ditetapkan sebagai **PRESENSI MASUK (IN / Kode: 1)** 🟢
2. **Reader 2: Sycreader SYC ID&IC USB (`ffff:0035`)** ➔ Ditetapkan sebagai **PRESENSI KELUAR (OUT / Kode: 0)** 🔴

### B. Konfigurasi Linux Udev Rules
Dibuat aturan udev di `/etc/udev/rules.d/99-rfid.rules` agar service Python dapat mengakses event reader tanpa hak akses root (`sudo`):
```udev
SUBSYSTEM=="input", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="dd01", MODE="0666"
SUBSYSTEM=="input", ATTRS{idVendor}=="ffff", ATTRS{idProduct}=="0035", MODE="0666"
```
Diaktifkan menggunakan perintah: `sudo udevadm control --reload-rules && sudo udevadm trigger`.

### C. Penguncian Eksklusif (*EVIOCGRAB*)
Menggunakan operasi kernel `ioctl(fd, EVIOCGRAB, 1)` sehingga input kartu RFID langsung diproses di latar belakang (background daemon) dan **tidak bocor / mengetik angka ke browser Firefox Kiosk**.

### D. Analisis Sidik Jari Kecepatan Hardware (*Hardware Timing Fingerprint*)
Diterapkan analisis jeda waktu antar-karakter USB untuk membedakan karakteristik hardware:
- Reader QinHeng (Burst Cepat ~36ms) ➔ Terdeteksi sebagai Masuk (IN).
- Reader Sycreader (Burst Standar ~143ms) ➔ Terdeteksi sebagai Keluar (OUT).

---

## 2. Refactoring Arsitektur: Pemisahan Menjadi 3 Service Mandiri

Sesuai arahan pembimbing, sistem yang sebelumnya terdiri dari 2 service dipisahkan menjadi **3 Service Independen**:

```
[ capture.py (Port 8000) ]  ───(HTTP POST / GET)───►  [ connector.py (Port 8002) ]  ◄───►  [ MariaDB & Folder captures/ ]
     (Terminal Kiosk)                                       (Database Bridge)
                                                                    ▲
                                                                    │ (Akses Mandiri)
                                                       [ admin.py (Port 8001) ]
                                                            (Admin Dashboard)
```

### Rincian Pembagian Service:
1. **`connector.py` (Port 8002 - Database & API Bridge Service)**:
   - Menjadi backend pemroses utama yang selalu aktif di background.
   - Endpoint: `POST /api/attendance/scan`, `GET /api/employee`, `GET /api/employees`, `GET /captures/<file>`.
   - Mengelola koneksi basis data MariaDB, validasi nomor kartu/NIK, penyimpanan file foto jepretan, dan pencatatan record absensi.
2. **`capture.py` (Port 8000 - Terminal Kiosk UI & Hardware)**:
   - Menampilkan antarmuka Kiosk absensi di monitor terminal Debian.
   - Menjalankan streaming kamera webcam Logitech C930e native V4L2.
   - Membaca event tap kartu fisik dari kernel Linux dan meneruskannya ke `connector.py`.
3. **`admin.py` (Port 8001 - Admin Management Dashboard)**:
   - Panel web untuk manajemen data karyawan (CRUD), melihat riwayat absensi dengan foto HD, dan ekspor data CSV.
   - **Dapat dinyalakan atau dimatikan kapan saja** tanpa memengaruhi operasional mesin Kiosk absensi.

---

## 3. Format Basis Data & Presisi Waktu Real-Time

### A. Implementasi Format RAW_DATA Spesifikasi Pembimbing
Format `raw_data` dan nama file gambar foto dibuat seragam dengan pola 15 digit:
$$\text{RAW\_DATA} = \text{\{NIK\}} + \text{\{Jam:2\}} + \text{\{Menit:2\}} + \text{\{Tanggal:2\}} + \text{\{Bulan:2\}} + \text{\{In/Out:1\}}$$
*Contoh:* Karyawan NIK `210019` melakukan presensi MASUK pada 21 September pukul 12:24 ➔ `210019122421091` dan foto disimpan dengan nama `210019122421091.jpg`.

### B. Presisi Detik Waktu Asli (Real-Time Seconds)
Mengatasi kendala waktu yang sebelumnya berakhiran `:00` karena format `raw_data` tidak memiliki digit detik:
- Logika query di `db.py` disempurnakan untuk mengambil timestamp asli dari metadata file foto jepretan di folder `captures/` serta `attendance.json`.
- Riwayat absensi di Admin Panel kini menampilkan jam, menit, dan detik secara presisi dan *real-time* (misalnya `2026-09-21 12:24:54`).

### C. Penanganan Anti-Looping & Anti-Bounce
- Ditambahkan identitas transaksi unik per-tap (`scan_id` UUID) dan debouncing 1.2 detik sehingga kartu dapat di-tap berulang kali secara instan tanpa terjadi *infinite loop* atau *freeze*.

---

## 4. Penataan & Kerapian Antarmuka Pengguna (UI Kiosk)

Antarmuka layar Kiosk [absen/static/index.html](file:///d:/magang/projek/employee-attendance/absen/static/index.html) dan [style.css](file:///d:/magang/projek/employee-attendance/absen/static/style.css) telah dirapikan:
1. **Field Tipe Presensi (In / Out)**:
   - Menampilkan indikator visual yang jelas dan menyala: **`🟢 MASUK (IN)`** untuk Reader 1 dan **`🔴 KELUAR (OUT)`** untuk Reader 2.
2. **Pembersihan Elemen Redundant**:
   - Menghapus kolom Tanggal & Jam Absensi yang duplikat dengan jam utama.
   - Menghapus status banner lama agar tampilan lebih bersih (*clean minimal design*).
3. **Proporsi & Spasi Antar Kolom**:
   - Mengatur jarak antar kolom yang seimbang dan proporsional (`gap: 20px`).
   - Menambahkan label **`MASUKKAN NIK`** yang posisinya presisi langsung di bawah Tipe Presensi.
   - Mengosongkan teks placeholder pada input NIK demi menjaga kerahasiaan dan estetika.

---

## 5. Ringkasan File & Modul yang Dikerjakan

| Modul / File | Status | Deskripsi Pekerjaan |
| :--- | :--- | :--- |
| `connector/connector.py` | **Baru** | Service HTTP API mandiri (Port 8002) untuk database & absensi |
| `connector/config.py` | **Baru** | Konfigurasi port 8002 dan koneksi database MariaDB |
| `connector/db.py` | **Baru** | Lapisan akses basis data & pencatatan absensi |
| `connector.py` | **Baru** | Root launcher untuk menjalankan connector service |
| `absen/capture.py` | **Diperbarui** | Integrasi listener Dual-RFID kernel udev, penguncian EVIOCGRAB, dan forwarding ke connector |
| `absen/config.py` | **Diperbarui** | Konfigurasi endpoint `CONNECTOR_SERVER_URL = "http://127.0.0.1:8002"` |
| `absen/static/index.html` | **Diperbarui** | Penataan layout panel karyawan, badge MASUK/KELUAR, label input NIK |
| `absen/static/app.js` | **Diperbarui** | Integrasi SSE real-time hardware tap, penanganan UUID per-tap, anti-looping |
| `absen/static/style.css` | **Diperbarui** | Styling layout modern, perataan spasi 20px, input height 54px |
| `admin/admin.py` | **Diperbarui** | Pembersihan service agar fokus melayani Admin Web Dashboard (Port 8001) |
| `admin/db.py` | **Diperbarui** | Optimasi pembacaan timestamp presisi detik asli dari disk foto captures |

---

## 6. Panduan Pengoperasian Sistem di Debian

### A. Menjalankan Semua Service (Kiosk + Connector + Admin):
```bash
cd /home/debian/www/attendance && pkill -9 -f "connector.py" ; pkill -9 -f "capture.py" ; pkill -9 -f "admin.py" ; nohup python3 connector.py > /dev/null 2>&1 & nohup python3 absen/capture.py > /dev/null 2>&1 & nohup python3 admin/admin.py > /dev/null 2>&1 &
```

### B. Menjalankan Mode Kiosk Mandiri (Tanpa Admin):
```bash
nohup python3 connector.py > /dev/null 2>&1 &
nohup python3 absen/capture.py > /dev/null 2>&1 &
```

### C. Memeriksa Status Seluruh Service:
```bash
ps aux | grep -E "connector\.py|capture\.py|admin\.py" | grep -v grep
```
