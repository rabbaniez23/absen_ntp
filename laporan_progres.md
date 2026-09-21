# Laporan Progres Proyek Sistem Absensi Karyawan

**Nama Proyek:** Sistem Absensi Karyawan Berbasis RFID, Kamera V4L2, dan Centralized Admin  
**Lokasi Proyek:** `employee-attendance/`  
**Periode Pengerjaan:** 1 September – 15 September 2026  
**Penyusun:** Mahasiswa Magang  

---

# BAB I: CAPAIAN PENGERJAAN

Bab ini menjabarkan secara rinci seluruh fitur, modul, dan infrastruktur teknis yang telah berhasil dibangun dan dioperasikan sejak awal pengerjaan proyek hingga tanggal 15 September 2026.

---

## 1.1 Arsitektur Sistem: Pemisahan Menjadi Dua Service Independen

Sistem awalnya berjalan dalam satu file monolitik (`server.py`) yang menggabungkan tampilan kiosk absensi, streaming kamera, manajemen admin, dan akses database pada port yang sama. Pendekatan monolitik ini menyebabkan bottleneck parah: ketika streaming MJPEG kamera aktif, seluruh request API tertahan (blocking) karena server hanya mampu melayani satu koneksi pada satu waktu.

Solusi yang diimplementasikan adalah **decoupling arsitektur** menjadi dua service yang sepenuhnya independen:

### A. Terminal Kiosk Absensi — `absen/capture.py` (Port 8000)

Modul ini merupakan **thin client** yang berjalan langsung di mesin terminal Debian. Tanggung jawabnya sangat spesifik dan ringan:

- **Menampilkan antarmuka Kiosk** melalui browser Firefox dalam mode fullscreen (Kiosk Mode) pada monitor BenQ yang terhubung ke mesin Debian.
- **Streaming kamera** secara real-time dari webcam USB Logitech C930e menggunakan protokol MJPEG melalui kernel Linux V4L2 (`/dev/video0`).
- **Menerima input identitas karyawan** berupa tap kartu RFID atau input manual NIK melalui antarmuka web.
- **Menjepret foto wajah** secara instan menggunakan kamera hardware.
- **Meneruskan (forwarding)** data identitas dan foto yang sudah di-encode base64 ke Server Admin Pusat melalui HTTP POST.

Catatan penting: modul Kiosk **tidak memiliki dependensi database lokal** sama sekali. Tidak ada MariaDB, tidak ada pymysql, tidak ada penyimpanan data lokal. Seluruh logika bisnis dan penyimpanan data ditangani oleh Server Admin Pusat.

**File terkait:**
| File | Ukuran | Fungsi |
|---|---|---|
| `capture.py` | 12 KB | Server HTTP Kiosk, handler scan RFID, forwarder ke Admin |
| `camera_v4l2.py` | 15 KB | Driver kamera native Linux V4L2 (tanpa OpenCV) |
| `config.py` | 672 B | Konfigurasi port, path, dan alamat server admin |
| `static/index.html` | 7 KB | Halaman antarmuka layar Kiosk |
| `static/app.js` | 30 KB | Logika UI Kiosk (input RFID, trigger kamera, kirim data) |
| `static/style.css` | 25 KB | Styling antarmuka Kiosk |

### B. Server Admin & Database Pusat — `admin/admin.py` (Port 8001)

Modul ini merupakan **pusat kendali sistem** yang menangani seluruh operasi berat:

- **Manajemen basis data MariaDB** untuk penyimpanan data karyawan dan riwayat absensi.
- **REST API terpusat** yang melayani seluruh kebutuhan data dari Kiosk maupun browser Admin.
- **Antarmuka Admin Dashboard** yang dapat diakses secara remote dari laptop administrator melalui jaringan LAN (`http://10.1.0.11:8001/employees.html`).
- **Penyimpanan dan serving file foto** hasil jepretan kamera di direktori `captures/`.
- **Cadangan data otomatis** ke file JSON (`data/employees.json` & `data/attendance.json`) sebagai fallback jika MariaDB sedang offline.

**File terkait:**
| File | Ukuran | Fungsi |
|---|---|---|
| `admin.py` | 20 KB | Server HTTP Admin, handler semua endpoint API |
| `db.py` | 41 KB | Lapisan akses database, CRUD, query, migrasi otomatis |
| `config.py` | 882 B | Konfigurasi port, path, kredensial MariaDB |
| `static/employees.html` | 49 KB | Antarmuka dashboard admin (HTML + embedded JS) |
| `static/style.css` | 23 KB | Styling dashboard admin Dark Glassmorphism |

### C. Multi-Threading Server

Kedua server ditingkatkan dari `http.server.TCPServer` (single-threaded) menjadi `socketserver.ThreadingTCPServer`. Perubahan ini menyelesaikan masalah kritis di mana loop infinite MJPEG stream dari kamera sebelumnya memblokir seluruh request API lain. Dengan threading, streaming kamera dan request API dapat berjalan bersamaan secara paralel tanpa saling menghalangi.

---

## 1.2 Driver Kamera Native V4L2 (Tanpa OpenCV)

Pengambilan foto dan streaming video dari webcam Logitech C930e dilakukan **tanpa menggunakan OpenCV** atau library image processing pihak ketiga. Modul `camera_v4l2.py` mengakses perangkat kamera secara langsung melalui **Video4Linux2 (V4L2)** API menggunakan operasi ioctl dan memory-mapped I/O pada level kernel Linux.

### Teknis Implementasi:

1. **Deteksi Perangkat Otomatis**: Modul mencari kamera Logitech di `/dev/v4l/by-id/` secara otomatis, atau fallback ke `/dev/video0`.
2. **Format Pixel**: Menggunakan format `V4L2_PIX_FMT_MJPEG` (Motion JPEG hardware) yang dihasilkan langsung oleh chip kamera Logitech C930e, sehingga tidak perlu proses encoding software.
3. **Resolusi**: Dikonfigurasi pada **640×480 (VGA)** untuk keseimbangan optimal antara kualitas foto dan beban CPU/bandwidth.
4. **Memory-Mapped Buffers**: Menggunakan `mmap` untuk mengakses frame buffer kamera secara zero-copy langsung dari kernel space.
5. **Singleton Pattern**: Menggunakan `CameraStreamer.get_instance()` untuk memastikan hanya ada satu instance yang mengakses device kamera pada satu waktu.

### Alasan Tidak Menggunakan OpenCV:

- Mesin Debian terminal memiliki resource terbatas (RAM dan storage).
- OpenCV memerlukan instalasi library besar (`libopencv-dev`, `numpy`, dll.) yang membebani sistem.
- V4L2 native memberikan akses langsung ke hardware MJPEG kamera tanpa overhead encoding/decoding software.
- Dependensi proyek menjadi minimal: hanya `pymysql` yang tercatat di `requirements.txt`.

---

## 1.3 Optimasi Performa dan Responsivitas Kiosk

Beberapa optimasi kritis yang telah diterapkan untuk memastikan pengalaman pengguna yang responsif di terminal Debian:

### A. Penurunan Resolusi Kamera ke 640×480

Resolusi frame kamera diturunkan dari 1280×720 (HD) ke 640×480 (VGA). Dampaknya:
- Ukuran frame MJPEG berkurang ~60%, mengurangi beban bandwidth streaming.
- CPU usage menurun signifikan saat streaming aktif.
- Kualitas foto wajah tetap memadai untuk kebutuhan absensi.

### B. Jepretan Foto Instan (Zero Delay)

Menghapus seluruh mekanisme countdown 3 detik pada UI Kiosk (`app.js`). Alur yang baru:
1. Karyawan mendekatkan kartu RFID atau menekan tombol NIK.
2. Kamera **langsung menjepret foto** pada detik itu juga (instant capture).
3. Data dikirim ke Server Admin Pusat **tanpa jeda apapun**.

Perubahan ini sangat meningkatkan throughput absensi saat jam sibuk (jam masuk/pulang kerja).

---

## 1.4 Antarmuka Admin Dashboard (UI/UX)

Halaman Admin Dashboard (`employees.html`) dirancang ulang secara menyeluruh dengan tema visual **Modern Dark Navy Glassmorphism**. Desain menggunakan palet warna gelap profesional dengan efek kaca transparan (glassmorphism), gradient halus, dan animasi mikro pada elemen interaktif.

Dashboard terbagi menjadi **3 tab navigasi** utama:

### Tab 1: Ringkasan Sistem (Overview KPI)

Menampilkan 4 kartu indikator performa utama secara real-time:
- **Total Karyawan** terdaftar di database.
- **Karyawan Aktif** (badge hijau).
- **Karyawan Nonaktif** (badge merah).
- **Jumlah Absensi Hari Ini** yang sudah tercatat.

Dilengkapi komponen **"Absensi Terkini" (Live Feed)** yang menampilkan 6 kartu presensi terbaru, masing-masing berisi:
- Thumbnail foto wajah karyawan.
- Nomor NIK dan Nama.
- Waktu presensi.
- Status keaktifan karyawan (badge Aktif/Nonaktif).

### Tab 2: Manajemen Master Karyawan (CRUD)

Fitur lengkap pengelolaan data karyawan:
- **Tabel master** dengan kolom: NIK, Nama Lengkap, RFID UID, Status.
- **Pencarian instan** berdasarkan NIK, Nama, atau RFID UID.
- **Filter status**: Semua / Hanya Aktif / Hanya Nonaktif.
- **Tombol Tambah Karyawan Baru** dengan modal dialog.
- **Tombol Edit Data Karyawan** untuk mengubah informasi.
- **Quick Toggle Button** untuk mengaktifkan/menonaktifkan karyawan dengan 1 klik.
- **Tombol Hapus** dengan konfirmasi dialog.

### Tab 3: Riwayat Log Presensi & Ekspor Data

Fitur pengelolaan riwayat absensi:
- **Tabel riwayat** menampilkan data kronologis dengan kolom: ID, Raw Data, Image, Nama, NIK, Waktu, Status.
- **Filter tanggal fleksibel**: Tombol cepat "Hari Ini", "Semua", atau pemilih kalender kustom (date range picker).
- **Filter status karyawan**: Semua / Aktif / Nonaktif.
- **Modal pratinjau foto HD**: Klik pada thumbnail untuk melihat foto bukti absensi resolusi penuh beserta metadata lengkap.
- **Ekspor rekap ke CSV**: Tombol untuk mengunduh seluruh data absensi dalam format CSV yang siap untuk keperluan pelaporan HRD/Payroll.

---

## 1.5 Sistem Status Keaktifan Karyawan (Aktif / Nonaktif)

Ditambahkan kolom `is_active` (TINYINT 1/0) pada tabel `employees` di MariaDB untuk menandai status administratif karyawan.

### Karakteristik Penting:
- Status keaktifan bersifat **murni administratif**. Karyawan yang dinonaktifkan **tetap dapat** melakukan tap RFID, foto tetap terjepret, dan absensi tetap tercatat normal.
- Status ditampilkan secara konsisten dengan badge visual:
  - 🟢 **AKTIF** — Badge hijau
  - 🔴 **NONAKTIF** — Badge merah
- Terlihat pada: Master Karyawan, Tabel Riwayat, Feed Absensi Terkini, Modal Foto HD, dan File CSV.

---

## 1.6 Standarisasi Format Data Presensi (Raw Data & Image)

Berdasarkan arahan spesifik dari pembimbing magang, seluruh format penyimpanan data absensi distandarisasi:

### A. Struktur Tabel `attendance` di MariaDB

Tabel `attendance` distandarisasi dengan **hanya 3 kolom utama**:

| Kolom | Tipe Data | Keterangan |
|---|---|---|
| `id` | BIGINT AUTO_INCREMENT | ID transaksi presensi (Primary Key) |
| `raw_data` | VARCHAR(100) | String gabungan data transaksi presensi |
| `image` | VARCHAR(255) | Nama file foto presensi (sama dengan raw_data) |

### B. Rumus Penyusunan `raw_data`

String `raw_data` dibentuk otomatis oleh fungsi `generate_raw_data()` dengan format:

```
raw_data = {NIK}{Jam:HH}{Menit:MM}{Tanggal:DD}{Bulan:MM}{Tipe:1}
```

**Contoh kasus nyata:**
- NIK Karyawan: `210019`
- Waktu Tap: Jam `07`, Menit `45`, Tanggal `14`, Bulan `09`
- Status In/Out: `1` (Masuk/In)
- **Hasil `raw_data`**: **`210019074514091`**

### C. Penamaan File Foto

File foto hasil jepretan disimpan di direktori `captures/` dengan format:
```
Nama File = {raw_data}.jpg
Contoh   : 210019074514091.jpg
```

Nilai yang tersimpan pada kolom `image` di MariaDB juga persis sama: `210019074514091.jpg`.

### D. Fungsi Parser `parse_raw_data()`

Fungsi `parse_raw_data()` melakukan operasi kebalikan — memecah string raw_data kembali menjadi komponen-komponen individual:
- NIK karyawan
- Jam dan Menit
- Tanggal dan Bulan
- Tipe presensi (1=MASUK, 0=KELUAR)
- String datetime terformat (`YYYY-MM-DD HH:MM:SS`)

### E. Migrasi Otomatis Database

Fungsi `init_database_tables()` menjalankan prosedur migrasi otomatis saat server dinyalakan. Jika tabel `attendance` masih menggunakan skema lama (kolom `employee_id`, `captured_at`, `image_path`, `attendance_status`), maka:
1. Kolom `raw_data` dan `image` ditambahkan.
2. Data lama dikonversi ke format `raw_data` baru menggunakan query SQL JOIN.
3. Kolom-kolom lama dihapus secara otomatis.
4. Proses ini berjalan tanpa kehilangan data historis.

---

## 1.7 REST API Endpoints

Berikut seluruh endpoint API yang tersedia pada Server Admin:

### Endpoint GET (Pengambilan Data)

| Endpoint | Fungsi |
|---|---|
| `GET /api/employees` | Mengambil seluruh daftar karyawan |
| `GET /api/employee?id={nik}` | Mencari karyawan berdasarkan NIK/RFID |
| `GET /api/stats` | Mengambil statistik dashboard (total, aktif, nonaktif, absen hari ini) |
| `GET /api/attendance` | Mengambil riwayat absensi (mendukung filter `?date=YYYY-MM-DD`, `?search=`, `?limit=`) |
| `GET /captures/{filename}` | Mengakses file foto absensi |

### Endpoint POST/PUT/DELETE (Modifikasi Data)

| Endpoint | Fungsi |
|---|---|
| `POST /api/attendance/scan` | Menerima data scan dari Kiosk (RFID + foto base64) |
| `POST /api/upload` | Upload foto manual via form multipart |
| `POST /api/employees` | Menambahkan karyawan baru |
| `POST /api/employees/update` | Memperbarui data karyawan |
| `POST /api/employees/toggle-status` | Toggle status aktif/nonaktif |
| `POST /api/employees/delete` | Menghapus karyawan |

---

## 1.8 Mekanisme Fallback JSON

Sistem dirancang dengan **dual-storage** untuk ketahanan operasional:

1. **Penyimpanan Utama**: MariaDB (basis data relasional).
2. **Cadangan/Fallback**: File JSON lokal (`data/employees.json` & `data/attendance.json`).

Jika MariaDB sedang offline atau tidak tersedia, sistem secara otomatis beralih membaca dan menulis ke file JSON. Setiap operasi tulis ke MariaDB juga secara otomatis disinkronkan ke file JSON sebagai backup.

---

## 1.9 Operasional Server Background (nohup)

Kedua server dijalankan sebagai proses background di mesin Debian menggunakan `nohup`:

```bash
nohup python3 capture.py &
nohup python3 admin.py &
```

Server tetap berjalan meskipun sesi SSH ditutup atau laptop pengembang dimatikan. Verifikasi proses aktif dilakukan dengan:

```bash
ps aux | grep python3
```

---

## 1.10 Teknologi dan Stack yang Digunakan

### Backend

| Teknologi | Versi/Detail | Kegunaan |
|---|---|---|
| **Python 3** | Standar Debian | Bahasa utama server backend |
| **http.server** | Bawaan Python | HTTP server (tanpa framework pihak ketiga) |
| **socketserver.ThreadingTCPServer** | Bawaan Python | Multi-threading untuk request paralel |
| **pymysql** | 1.2.0 | Connector Python ke MariaDB/MySQL |
| **V4L2 (Video4Linux2)** | Kernel Linux | Akses langsung ke hardware kamera |
| **fcntl + mmap** | Bawaan Python | Operasi I/O kernel-level untuk kamera |

### Database

| Teknologi | Detail |
|---|---|
| **MariaDB** | Server database relasional di mesin Debian |
| **Database Name** | `debian` |
| **Tabel `employees`** | Master data karyawan (7 kolom) |
| **Tabel `attendance`** | Riwayat absensi (3 kolom: id, raw_data, image) |
| **JSON Fallback** | `data/employees.json`, `data/attendance.json` |

### Frontend

| Teknologi | Kegunaan |
|---|---|
| **HTML5** | Struktur halaman Kiosk dan Admin Dashboard |
| **CSS3** | Styling (Dark Glassmorphism theme, responsive design) |
| **JavaScript (Vanilla)** | Logika UI tanpa framework (tanpa React, Vue, dll.) |
| **Fetch API** | Komunikasi AJAX ke REST API backend |

### Hardware

| Perangkat | Fungsi |
|---|---|
| **Mesin Debian** (IP: 10.1.0.11) | Terminal server utama |
| **Monitor BenQ** | Layar tampilan Kiosk Absensi (fullscreen) |
| **Logitech C930e** | Webcam USB untuk foto wajah karyawan |
| **RFID Reader** | Input identitas kartu karyawan |

### Infrastruktur

| Teknologi | Kegunaan |
|---|---|
| **Debian Linux** | Sistem operasi terminal |
| **Firefox Kiosk Mode** | Browser fullscreen untuk antarmuka Kiosk |
| **Git + GitHub** | Version control, repository `absen_ntp.git` |
| **nohup** | Menjalankan server sebagai background process |
| **SSH** | Akses remote ke mesin Debian dari laptop pengembang |
| **LAN** | Jaringan lokal untuk akses Admin Dashboard |

---

## 1.11 Struktur Direktori Proyek

```
employee-attendance/
├── absen/                          # Modul Terminal Kiosk (Port 8000)
│   ├── capture.py                  # Server HTTP Kiosk Edge
│   ├── camera_v4l2.py              # Driver kamera native V4L2
│   ├── config.py                   # Konfigurasi Kiosk
│   ├── logs/                       # Log operasional Kiosk
│   │   └── kiosk.log
│   └── static/                     # Aset web Kiosk
│       ├── index.html              # Halaman utama Kiosk
│       ├── app.js                  # Logika UI Kiosk
│       └── style.css               # Styling Kiosk
│
├── admin/                          # Modul Server Admin Pusat (Port 8001)
│   ├── admin.py                    # Server HTTP Admin + API
│   ├── db.py                       # Lapisan akses database
│   ├── config.py                   # Konfigurasi Admin + MariaDB
│   ├── captures/                   # Penyimpanan foto absensi
│   │   └── {raw_data}.jpg          # Foto dinamai sesuai raw_data
│   ├── data/                       # Cadangan data JSON
│   │   ├── employees.json
│   │   └── attendance.json
│   ├── logs/                       # Log operasional Admin
│   │   └── admin.log
│   └── static/                     # Aset web Dashboard Admin
│       ├── employees.html          # Dashboard Admin (3 Tab)
│       └── style.css               # Styling Dark Glassmorphism
│
├── requirements.txt                # Dependensi Python (pymysql)
├── README.md                       # Dokumentasi proyek
├── .gitignore                      # Aturan pengabaian Git
└── index.php                       # Legacy redirect file
```

---

# BAB II: RENCANA PENGEMBANGAN KE DEPAN

Bab ini menjabarkan rencana pengembangan proyek untuk **12 tahap ke depan (± 3 bulan)**, dimulai dari kondisi sistem yang sudah berjalan saat ini. Seluruh rencana menggunakan **stack teknologi yang sudah ada** — tidak menambahkan framework atau library baru kecuali benar-benar diperlukan.

---

## Tahap 3: Stabilisasi Operasional & Auto-Start Server

**Tujuan:** Memastikan sistem berjalan otomatis tanpa intervensi manual saat mesin Debian dinyalakan.

### Rencana Detail:

1. **Membuat systemd Unit Service** untuk kedua server:
   - File `/etc/systemd/system/kiosk-absensi.service` untuk `capture.py` (Port 8000).
   - File `/etc/systemd/system/admin-absensi.service` untuk `admin.py` (Port 8001).
   - Konfigurasi `Restart=always` agar server otomatis restart jika crash.
   - Konfigurasi `After=network.target mariadb.service` agar server dimulai setelah jaringan dan database siap.

2. **Menggantikan nohup** dengan systemd yang lebih reliable:
   - Menambahkan `systemctl enable` agar service otomatis aktif saat boot.
   - Menambahkan logging ke journalctl untuk monitoring terpusat.

3. **Pengujian Power Cycle**:
   - Mematikan mesin Debian secara fisik dan memastikan seluruh server kembali aktif otomatis saat dinyalakan ulang.
   - Memverifikasi bahwa Firefox Kiosk Mode juga auto-start setelah reboot.

---

## Tahap 4: Implementasi Fitur In/Out (Masuk & Keluar)

**Tujuan:** Mengimplementasikan logika pembeda antara absensi **Masuk (In)** dan **Keluar (Out)**.

### Rencana Detail:

1. **Logika Penentuan In/Out Otomatis**:
   - Saat karyawan melakukan tap pertama pada hari itu, sistem otomatis mencatatnya sebagai **IN (1)**.
   - Tap berikutnya pada hari yang sama dicatat sebagai **OUT (0)**.
   - Implementasi query SQL: cek apakah sudah ada record `raw_data` yang diakhiri `1` (In) untuk NIK tersebut pada tanggal hari ini.

2. **Perubahan pada `generate_raw_data()`**:
   - Parameter `in_out` tidak lagi di-hardcode `"1"`, melainkan ditentukan secara dinamis berdasarkan logika di atas.

3. **Update Tampilan Dashboard Admin**:
   - Menambahkan kolom/badge "MASUK" atau "KELUAR" pada tabel riwayat absensi.
   - Update label pada Feed Absensi Terkini.

4. **Update Tampilan Kiosk**:
   - Menampilkan feedback visual kepada karyawan setelah tap: "Selamat Datang, [Nama]! Absensi MASUK tercatat." atau "Sampai Jumpa, [Nama]! Absensi KELUAR tercatat."

---

## Tahap 5: Validasi Fisik RFID Reader & Pengujian Lapangan

**Tujuan:** Menguji integrasi menyeluruh dengan hardware RFID reader fisik di lingkungan produksi.

### Rencana Detail:

1. **Integrasi RFID Reader**:
   - Menguji pembacaan kartu RFID dari berbagai jarak dan kecepatan tap.
   - Memvalidasi bahwa UID yang dikirim reader sesuai dengan format yang tersimpan di database.
   - Menangani kasus edge: tap ganda cepat, kartu rusak, kartu tidak terdaftar.

2. **Stress Testing Jam Sibuk**:
   - Simulasi skenario jam masuk kerja: banyak karyawan tap berurutan dalam waktu singkat.
   - Memastikan threading server mampu menangani beban paralel.
   - Mengukur waktu respon rata-rata per transaksi absensi.

3. **Pengujian Kamera dalam Kondisi Nyata**:
   - Menguji kualitas foto pada berbagai kondisi pencahayaan (pagi, siang, malam).
   - Memastikan foto wajah terjepret dengan fokus yang tepat.

---

## Tahap 6: Rekap Absensi Harian & Laporan Otomatis

**Tujuan:** Menambahkan fitur rangkuman harian dan ekspor laporan yang lebih kaya.

### Rencana Detail:

1. **Endpoint API Rekap Harian**:
   - `GET /api/attendance/summary?date=YYYY-MM-DD` yang mengembalikan:
     - Total karyawan hadir.
     - Total karyawan tidak hadir (tidak ada record sama sekali pada hari itu).
     - Karyawan yang hanya tap IN tanpa OUT (atau sebaliknya).
     - Karyawan yang terlambat (jika batasan jam masuk didefinisikan).

2. **Tampilan Rekap di Dashboard Admin**:
   - Menambahkan view "Rekap Harian" pada Tab Overview yang merangkum seluruh statistik kehadiran.
   - Menampilkan daftar karyawan yang tidak hadir (absen) pada hari yang dipilih.

3. **Peningkatan Ekspor CSV**:
   - Menambahkan kolom "Jam Masuk", "Jam Keluar", dan "Durasi Kerja" pada file ekspor.
   - Opsi ekspor berdasarkan rentang tanggal (mingguan/bulanan).

---

## Tahap 7: Keamanan dan Autentikasi Admin Dashboard

**Tujuan:** Mengamankan akses ke halaman Admin Dashboard agar tidak dapat diakses oleh sembarang orang di jaringan LAN.

### Rencana Detail:

1. **Sistem Login Sederhana**:
   - Halaman login (`login.html`) dengan form username dan password.
   - Endpoint `POST /api/auth/login` untuk validasi kredensial.
   - Menyimpan kredensial admin di file konfigurasi atau di tabel `admin_users` di MariaDB.

2. **Session Management**:
   - Menggunakan token sederhana (random string) yang disimpan di cookie browser.
   - Middleware validasi token pada setiap request ke endpoint API yang sensitif.
   - Timeout session otomatis setelah periode inaktivitas tertentu.

3. **Proteksi Endpoint**:
   - Endpoint publik (untuk Kiosk): `/api/attendance/scan`, `/api/employee` — tetap terbuka.
   - Endpoint admin (untuk Dashboard): `/api/employees` (POST/PUT/DELETE), `/api/stats` — dilindungi autentikasi.

---

## Tahap 8: Notifikasi Real-Time & Halaman Monitoring

**Tujuan:** Membuat halaman monitoring real-time yang menampilkan setiap absensi secara langsung tanpa perlu refresh browser.

### Rencana Detail:

1. **Implementasi Polling atau Server-Sent Events (SSE)**:
   - Menggunakan teknik long-polling atau SSE native (tanpa WebSocket library tambahan) untuk push notifikasi ke browser Admin.
   - Setiap kali ada scan baru dari Kiosk, dashboard Admin langsung menampilkan notifikasi pop-up dan memperbarui Feed Absensi Terkini.

2. **Indikator Status Server**:
   - Menampilkan indikator hijau/merah pada Dashboard Admin yang menunjukkan apakah Kiosk dan MariaDB sedang online.
   - Endpoint `GET /api/health` yang mengembalikan status kesehatan seluruh komponen sistem.

3. **Log Aktivitas Admin**:
   - Mencatat setiap operasi yang dilakukan admin (tambah/edit/hapus karyawan, ekspor CSV) ke dalam log audit.

---

## Tahap 9: Manajemen Shift dan Jam Kerja

**Tujuan:** Menambahkan dukungan untuk konfigurasi shift kerja dan penentuan keterlambatan.

### Rencana Detail:

1. **Konfigurasi Jam Kerja**:
   - Tabel/konfigurasi baru di database yang mendefinisikan jadwal shift:
     - Shift Pagi: 07:00 – 15:00
     - Shift Siang: 15:00 – 23:00
     - (Dapat dikustomisasi sesuai kebijakan perusahaan)
   - Batasan jam masuk (grace period) untuk penentuan status terlambat.

2. **Kalkulasi Keterlambatan**:
   - Membandingkan waktu tap IN karyawan dengan jam masuk shift.
   - Menandai karyawan yang terlambat dengan badge visual pada Dashboard Admin.
   - Menyimpan data keterlambatan untuk keperluan pelaporan.

3. **Tampilan Dashboard**:
   - Menambahkan KPI "Karyawan Terlambat Hari Ini" pada tab Overview.
   - Filter riwayat absensi berdasarkan status kehadiran (Tepat Waktu / Terlambat / Tidak Hadir).

---

## Tahap 10: Profil Karyawan dan Riwayat Individual

**Tujuan:** Membuat halaman detail per karyawan yang menampilkan riwayat absensi lengkap individu tersebut.

### Rencana Detail:

1. **Halaman Profil Karyawan**:
   - Menampilkan informasi detail karyawan (NIK, Nama, RFID, Status Aktif, Tanggal Terdaftar).
   - Foto terakhir yang terjepret saat absensi.
   - Ringkasan statistik personal: total hari hadir bulan ini, rata-rata jam masuk, total keterlambatan.

2. **Tabel Riwayat Absensi Individual**:
   - Daftar seluruh riwayat absensi khusus karyawan tersebut.
   - Filter berdasarkan bulan/tahun.
   - Kalender visual yang menandai hari hadir (hijau), tidak hadir (merah), dan hari libur (abu-abu).

3. **Endpoint API Profil**:
   - `GET /api/employee/profile?nik={nik}` yang mengembalikan data profil dan statistik personal.
   - `GET /api/employee/attendance?nik={nik}&month=YYYY-MM` untuk riwayat individual.

---

## Tahap 11: Manajemen Hari Libur dan Kalender Kerja

**Tujuan:** Menambahkan sistem kalender kerja yang mengecualikan hari libur nasional dan cuti.

### Rencana Detail:

1. **Tabel Hari Libur**:
   - Tabel `holidays` di MariaDB: `id`, `date`, `description` (contoh: "Hari Kemerdekaan").
   - Form input di Dashboard Admin untuk menambahkan/menghapus hari libur.

2. **Integrasi dengan Rekap Harian**:
   - Pada hari libur, sistem tidak menandai karyawan sebagai "Tidak Hadir".
   - Kalender visual pada profil karyawan menampilkan hari libur dengan warna berbeda.

3. **Validasi Cerdas**:
   - Jika ada karyawan yang tetap tap pada hari libur (lembur), absensi tetap tercatat namun ditandai sebagai "Hari Libur / Lembur".

---

## Tahap 12: Laporan Bulanan dan Ekspor Lanjutan

**Tujuan:** Menyediakan fitur laporan bulanan komprehensif yang siap digunakan oleh tim HRD.

### Rencana Detail:

1. **Laporan Bulanan Otomatis**:
   - Endpoint `GET /api/report/monthly?month=YYYY-MM` yang menghasilkan ringkasan:
     - Daftar seluruh karyawan beserta jumlah hari hadir, tidak hadir, terlambat.
     - Total jam kerja masing-masing karyawan.
     - Persentase kehadiran per karyawan.

2. **Ekspor ke Format Tambahan**:
   - Selain CSV, menambahkan opsi ekspor ke format yang lebih rapi (misalnya tabel HTML yang bisa di-print langsung).
   - Template laporan yang menyertakan kop surat/header perusahaan.

3. **Halaman Laporan di Dashboard**:
   - Tab baru "Laporan" pada Dashboard Admin.
   - Pemilih bulan/tahun untuk generate laporan.
   - Preview laporan sebelum diunduh/dicetak.

---

## Tahap 13: Multi-Kamera dan Multi-Terminal

**Tujuan:** Mendukung lebih dari satu terminal Kiosk yang terhubung ke Server Admin Pusat.

### Rencana Detail:

1. **Identifikasi Terminal**:
   - Menambahkan parameter `terminal_id` pada setiap request dari Kiosk ke Admin.
   - Menyimpan informasi terminal asal pada data absensi untuk audit trail.

2. **Konfigurasi Multi-Terminal**:
   - Halaman konfigurasi di Dashboard Admin untuk mengelola daftar terminal terdaftar.
   - Monitoring status online/offline setiap terminal.

3. **Skalabilitas**:
   - Dokumentasi langkah-langkah deployment terminal baru: copy folder `absen/`, sesuaikan `config.py`, jalankan service.

---

## Tahap 14: Polish, Dokumentasi, dan Persiapan Penyerahan

**Tujuan:** Finalisasi seluruh fitur, penyempurnaan UI/UX, dan penyusunan dokumentasi akhir.

### Rencana Detail:

1. **UI/UX Polish**:
   - Review dan perbaikan tampilan pada berbagai ukuran layar.
   - Konsistensi warna, typography, dan spacing di seluruh halaman.
   - Penambahan animasi loading state dan error handling yang user-friendly.

2. **Dokumentasi Teknis Lengkap**:
   - Update `README.md` dengan panduan instalasi, konfigurasi, dan troubleshooting.
   - Dokumentasi API endpoints (parameter, response format, error codes).
   - Panduan maintenance harian untuk operator (cara restart server, cek log, backup database).

3. **Dokumentasi Pengguna (User Manual)**:
   - Panduan penggunaan Dashboard Admin (dengan screenshot).
   - Panduan penggunaan Kiosk Absensi untuk karyawan.
   - FAQ dan troubleshooting umum.

4. **Penyerahan Proyek**:
   - Menyiapkan seluruh kode sumber final di repository Git.
   - Menyiapkan laporan akhir magang.
   - Presentasi demo sistem kepada pembimbing.

---

## Ringkasan Timeline Rencana Pengembangan

| Tahap | Fokus Utama | Deliverable |
|---|---|---|
| **3** | Stabilisasi & Auto-Start | systemd unit service, auto-boot server |
| **4** | Fitur In/Out | Logika masuk/keluar otomatis, feedback UI |
| **5** | Validasi RFID & Uji Lapangan | Hasil stress test, laporan kompatibilitas hardware |
| **6** | Rekap Harian & Laporan | API summary, ekspor CSV diperkaya |
| **7** | Keamanan Admin | Halaman login, session management, proteksi API |
| **8** | Monitoring Real-Time | SSE/polling, notifikasi pop-up, health check |
| **9** | Shift & Jam Kerja | Konfigurasi shift, kalkulasi keterlambatan |
| **10** | Profil Karyawan | Halaman detail individu, kalender kehadiran |
| **11** | Hari Libur & Kalender | Tabel holidays, integrasi rekap |
| **12** | Laporan Bulanan | Report generator, ekspor lanjutan, tab Laporan |
| **13** | Multi-Terminal | Dukungan banyak Kiosk, terminal ID |
| **14** | Polish & Dokumentasi | UI final, dokumentasi teknis & pengguna, penyerahan |

---

*Dokumen ini terakhir diperbarui pada: 15 September 2026*
