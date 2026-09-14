# Laporan Progres Pengerjaan Sistem Absensi Karyawan

**Nama Proyek:** Sistem Absensi Karyawan Berbasis RFID, Kamera V4L2, dan Centralized Admin  
**Lokasi Proyek:** `employee-attendance/`  
**Tanggal Pengerjaan:** 14 September 2026 (Minggu ke-2)  
**Penyusun:** Mahasiswa Magang  

---

## Bab 1: Ringkasan Eksekutif

Pada tanggal 14 September 2026, telah diselesaikan serangkaian pengembangan besar (*major refactoring*) pada sistem presensi karyawan. Fokus pengerjaan mencakup **pemisahan arsitektur monolitik menjadi dua *service* independen (Edge Kiosk & Central Admin)**, **optimasi performa jepretan kamera instan tanpa *lag***, **perancangan ulang antarmuka Admin Dashboard secara menyeluruh**, **penambahan status keaktifan karyawan**, serta **implementasi format data presensi khusus (*Raw Data* & penamaan *Image*) sesuai instruksi pembimbing magang**.

---

## Bab 2: Rincian Pekerjaan yang Telah Diselesaikan

### 2.1 Pemisahan Arsitektur Server (Decoupling Architecture)

Sebelumnya, sistem berjalan dalam satu berkas monolitik (`server.py`) yang menggabungkan layar kiosk absensi dan halaman admin pada port yang sama. Hal ini menyebabkan beban tinggi pada sistem dan kendala antrean (*blocking*) saat streaming kamera aktif.

Sistem kini dipisahkan menjadi dua modul independen:

1. **Terminal Kiosk Presensi (`absen/capture.py` - Port 8000)**
   - Berjalan secara lokal di monitor BenQ terminal Debian (mode fullscreen Firefox Kiosk).
   - Bertanggung jawab khusus untuk menangkap input kartu RFID / NIK manual dan mengambil video *live-feed* dari hardware webcam Logitech C930e melalui kernel Linux V4L2 (`/dev/video0`).
   - Tidak terbebani operasi database lokal. Ketika kartu di-tap, Kiosk menjepret foto lokal dan meneruskannya (*forwarding*) ke Server Admin Pusat via HTTP POST.

2. **Server Admin & Basis Data Pusat (`admin/admin.py` - Port 8001)**
   - Berfungsi sebagai server pusat pengelola basis data MariaDB dan berkas cadangan JSON (`data/attendance.json` & `data/employees.json`).
   - Menyediakan REST API terpusat untuk autentikasi data karyawan, pencatatan log presensi, manajemen CRUD master karyawan, metrik statistik, dan pengunduhan laporan CSV.
   - Dapat diakses secara remote dari laptop administrator melalui jaringan LAN (`http://10.1.0.11:8001/employees.html`).

3. **Implementasi Multi-Threading (`ThreadingTCPServer`)**
   - Server ditingkatkan dari `TCPServer` tunggal (*single-threaded*) menjadi `socketserver.ThreadingTCPServer`.
   - Hal ini menyelesaikan masalah *blocking* di mana loop *infinite stream* MJPEG kamera sebelumnya menahan *request* API lainnya.

---

### 2.2 Optimasi Kamera dan Responsivitas Kiosk

Untuk mengatasi kendala *lag*, beban CPU, dan keterlambatan respon pada terminal Debian:

1. **Penurunan Resolusi Kamera ke 640x480 (VGA)**
   - Resolusi frame kamera pada `absen/camera_v4l2.py` disesuaikan dari 1280x720 ke 640x480.
   - Ukuran *bandwidth* frame MJPEG berkurang signifikan sehingga *streaming* berjalan sangat mulus tanpa membebani memori mesin Debian.
2. **Jepretan Foto Instan Tanpa Countdown 3 Detik**
   - Menghapus jeda hitung mundur 3 detik pada antarmuka Kiosk (`absen/static/app.js`).
   - Begitu kartu RFID didekatkan atau tombol NIK ditekan, kamera langsung menjepret foto wajah secara instan detik itu juga dan mengirimkannya ke server backend.

---

### 2.3 Perombakan Antarmuka Admin Dashboard (UI/UX)

Antarmuka halaman admin (`admin/static/employees.html` dan `admin/static/style.css`) dirancang ulang secara menyeluruh dengan tema profesional **Modern Dark Navy Glassmorphism** yang terbagi menjadi 3 tab navigasi:

1. **Tab 1: Ringkasan Sistem Presensi (Overview KPI)**
   - Menampilkan 4 kartu indikator performa utama secara *real-time*:
     - **Total Karyawan** terdaftar.
     - **Karyawan Aktif**.
     - **Karyawan Nonaktif**.
     - **Jumlah Absensi Hari Ini**.
   - Menyediakan komponen *Live Feed* "Absensi Terkini" yang menampilkan 6 kartu presensi terbaru beserta thumbnail foto wajah, NIK, nama, waktu presensi, dan status keaktifan.
2. **Tab 2: Manajemen Master Karyawan (CRUD)**
   - Tabel master data yang menyajikan Nomor Induk Karyawan (NIK), Nama Lengkap, Nomor Kartu RFID UID, dan Status Keaktifan.
   - Fitur pencarian instan berdasarkan NIK, Nama, maupun nomor RFID.
   - Filter tabel berdasarkan status (Semua / Hanya Aktif / Hanya Nonaktif).
   - Modal dialog untuk **Tambah Karyawan Baru** dan **Edit Data Karyawan**.
   - Tombol cepat (*Quick Toggle Button*) untuk mengaktifkan atau menonaktifkan status karyawan dengan 1 klik.
   - Fitur konfirmasi hapus karyawan dari sistem.
3. **Tab 3: Riwayat Log Presensi & Ekspor Data**
   - Menampilkan daftar riwayat absensi secara kronologis.
   - Filter rentang tanggal fleksibel (tombol cepat "Hari Ini", "Semua", atau pemilih kalender kustom).
   - Filter status karyawan (Semua / Aktif / Nonaktif).
   - Fitur **Ekspor Rekap ke CSV** untuk integrasi pelaporan HRD/Payroll.
4. **Modal Pratinjau Foto HD**
   - Modal pembesar foto bukti presensi yang menampilkan jepretan kamera resolusi penuh beserta informasi metadata lengkap.

---

### 2.4 Penambahan Status Keaktifan Karyawan (Aktif / Nonaktif)

Sesuai kebutuhan manajemen karyawan:
- Ditambahkan kolom `is_active` (TINYINT 1/0 pada MariaDB dan Boolean pada JSON fallback).
- **Karakteristik Status Administratif:** Status keaktifan ini murni bersifat administratif. Karyawan yang dinonaktifkan tetap dapat melakukan *tap* kartu RFID maupun input NIK, foto wajah tetap terjepret, dan absensi tetap tercatat normal pada sistem.
- Status keaktifan ditampilkan dengan badge visual yang jelas:
  - 🟢 **AKTIF** (Badge hijau)
  - 🔴 **NONAKTIF** (Badge merah)
- Ditampilkan secara konsisten pada: Master Karyawan, Tabel Riwayat Absensi, Feed Absensi Terkini, Modal Foto HD, dan File Ekspor CSV.

---

### 2.5 Standarisasi Struktur Database & Penamaan File Sesuai Arahan Pembimbing

Menindaklanjuti arahan spesifik dari pembimbing magang mengenai format data presensi, telah dilakukan perombakan skema tabel dan logika penyimpanan:

#### A. Struktur Kolom Tabel `attendance`
Tabel `attendance` distandarisasi dengan kolom utama:
* **`id`** : ID transaksi presensi (BigInt, Auto Increment).
* **`raw_data`** : String gabungan data transaksi presensi.
* **`image`** : Nama file foto presensi (persis sama dengan `raw_data`).

#### B. Rumus Penyusunan `raw_data`
String `raw_data` dibentuk secara otomatis dari gabungan:
$$\mathbf{raw\_data} = \text{NIK} + \text{Jam (HH)} + \text{Menit (MM)} + \text{Tanggal (DD)} + \text{Bulan (MM)} + \text{Tipe Presensi (1)}$$

*Contoh Kasus Nyata:*
- NIK Karyawan: `210019`
- Waktu Tap: Jam `07`, Menit `45`, Tanggal `14`, Bulan `09`
- Status In/Out: `1` (*In / Masuk*)
- **Hasil Nilai `raw_data`**: **`210019074514091`**

#### C. Standarisasi Penamaan dan Penyimpanan Gambar (`image`)
- Berkas foto hasil jepretan kamera disimpan di direktori `captures/` dengan format nama berkas:
  $$\text{Nama Berkas} = \mathbf{raw\_data} + \mathbf{.jpg}$$
  Contoh: **`210019074514091.jpg`**
- Nilai yang tersimpan pada kolom `image` di database MariaDB adalah: `210019074514091.jpg`.

#### D. Migrasi Otomatis Skema Basis Data
- Menambahkan prosedur migrasi otomatis pada `admin/db.py` (`init_database_tables()`). Saat server dijalankan, script secara otomatis menambahkan kolom `raw_data` dan `image` ke tabel MariaDB jika belum tersedia, serta mengonversi rekaman lama ke format baru tanpa kehilangan data historis.

---

## Bab 3: Matriks Perubahan File Codebase

| Modul / Berkas | Lokasi | Ringkasan Perubahan |
|---|---|---|
| `capture.py` | `absen/` | Pengalihan ke port 8000, multi-threading, pengambilan foto webcam instan, forward POST ke admin. |
| `camera_v4l2.py` | `absen/` | Penyesuaian resolusi kamera ke 640x480 VGA untuk performa tinggi. |
| `app.js` | `absen/static/` | Penghapusan countdown 3 detik; tap kartu langsung trigger jepretan kamera seketika. |
| `admin.py` | `admin/` | Server admin port 8001, generator `raw_data`, penamaan berkas foto `{raw_data}.jpg`, serving berkas `captures/`. |
| `db.py` | `admin/` | Fungsi `generate_raw_data()`, `parse_raw_data()`, skema tabel `attendance (id, raw_data, image)`, migrasi otomatis. |
| `employees.html` | `admin/static/` | UI/UX Dark Glassmorphism 3 Tab, kolom RAW DATA, kolom IMAGE, badge status AKTIF/NONAKTIF, ekspor CSV. |
| `style.css` | `admin/static/` | Design system CSS tokens, glassmorphism card, status pills, badge counter, responsive table. |

---

## Bab 4: Pengujian dan Verifikasi Sistem

Seluruh fitur telah melalui pengujian teknis lokal dan verifikasi sintaksis:
1. **Verifikasi Sintaks Python**: Modul `admin/db.py`, `admin/admin.py`, dan `absen/capture.py` terkompilasi sukses dengan `py_compile`.
2. **Unit Test Raw Data Generator**:
   - Input: NIK `210019`, Waktu `14 September 2026 07:45`, Status `1` (In).
   - Output `raw_data`: `210019074514091` (**Valid / Sesuai 100%**).
   - Output `image`: `210019074514091.jpg` (**Valid / Sesuai 100%**).
   - Hasil parsing: NIK `210019`, Waktu `2026-09-14 07:45:00`, Tipe `MASUK (IN)` (**Valid**).
3. **Sinkronisasi Git Repository**:
   - Seluruh perubahan telah di-commit dan di-push ke repositori GitHub `absen_ntp.git` pada branch `main`.

---

## Bab 5: Rencana Kerja Selanjutnya

1. Melakukan pengujian integrasi fisik menyeluruh di mesin Debian (`10.1.0.11`) menggunakan kartu RFID aktual dan kamera USB Logitech C930e.
2. Memantau stabilitas server background (`nohup`) dalam durasi operasional harian.
3. Menyiapkan konfigurasi *service auto-start* Linux (`systemd unit`) agar kedua server otomatis berjalan saat komputer Debian dinyalakan tanpa perlu terminal manual.
