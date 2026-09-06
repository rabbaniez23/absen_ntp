# Product Requirement Document (PRD)
## Sistem Presensi Karyawan Berbasis RFID & Verifikasi Foto Biometrik (`absen_ntp`)

| Atribut | Keterangan |
| :--- | :--- |
| **Nama Produk** | Sistem Presensi Karyawan (*absen_ntp*) |
| **Versi Dokumen** | 1.0.0 |
| **Status** | Disetujui / Selesai Implementasi |
| **Target Lingkungan** | Linux Kiosk (Debian 11/12, Ubuntu) & Windows Standalone |
| **Bahasa & Arsitektur** | Python (Backend HTTP), Vanilla JS & CSS (Frontend), MariaDB + JSON Storage (Database) |

---

## 1. Latar Belakang & Masalah (Problem Statement)

Dalam operasional harian perusahaan atau instansi, sistem pencatatan kehadiran karyawan konvensional sering menghadapi beberapa kendala kritis:
1. **Kecurangan Presensi ("Titip Absen"):** Karyawan dapat menitipkan kartu presensi atau RFID kepada rekan kerja tanpa hadir secara fisik di lokasi kerja.
2. **Ketergantungan Ekstrem pada Jaringan/Database:** Banyak sistem terhenti (*down*) saat database pusat mengalami gangguan jaringan, mengakibatkan antrean panjang di pintu masuk.
3. **Kerumitan Instalasi:** Sistem presensi biometrik komersial sering membutuhkan perangkat keras tertutup (*proprietary*), lisensi berkala, dan konfigurasi driver yang rumit.

### Solusi Produk
Sistem Presensi Karyawan `absen_ntp` dibangun sebagai sistem mandiri (*kiosk-ready*) yang menggabungkan kecepatan **pemindaian kartu RFID** (USB HID) dengan **verifikasi visual foto biometrik otomatis** via kamera web. Sistem dilengkapi mekanisme penyimpanan ganda (*dual-layer storage*) dengan fallback otomatis ke file lokal JSON jika koneksi MariaDB terputus, menjamin proses presensi tetap berjalan tanpa henti.

---

## 2. Tujuan Produk & Metrik Keberhasilan (Goals & Metrics)

### 2.1. Tujuan Utama
- Memastikan kehadiran fisik karyawan yang sah melalui foto bukti kehadiran (*audit trail*).
- Menghadirkan antarmuka kiosk layar penuh yang interaktif, elegan, dan mudah digunakan tanpa interaksi sentuhan (*touchless*).
- Memberikan fleksibilitas administrasi data karyawan langsung melalui antarmuka web.

### 2.2. Indikator Keberhasilan (Success Metrics)
| Metrik | Target |
| :--- | :--- |
| **Waktu Siklus Absensi** | $\le 3$ detik per karyawan (sejak tap kartu hingga foto tersimpan). |
| **Ketersediaan Layanan (Availability)** | 99.9% (tidak pernah gagal mencatat walau server database lokal mati). |
| **Toleransi Kesalahan Perangkat** | Pemulihan mandiri (*auto-recovery*) ke status awal dalam $\le 2.5$ detik jika terjadi error. |
| **Dukungan Hardware** | 100% Plug-and-Play untuk kamera webcam UVC USB dan USB RFID reader standar. |

---

## 3. Profil Pengguna (User Persona)

1. **Karyawan / Pegawai (End User):**
   - Menempelkan kartu RFID pada scanner saat jam masuk/pulang.
   - Mengarahkan wajah ke kamera mengikuti panduan oval di layar.
   - Melihat konfirmasi visual bahwa absensi berhasil dicatat.

2. **Administrator HR / Personalia:**
   - Membuka halaman administrasi karyawan (`/employees.html`).
   - Mendaftarkan karyawan baru dengan menempelkan kartu RFID ke alat pembaca.
   - Melihat daftar karyawan terdaftar dan menonaktifkan/menghapus karyawan.

3. **Operator IT / Teknisi Sistem:**
   - Melakukan deployment sistem ke mesin mini-PC / laptop Debian.
   - Memantau service background (`attendance-server.service`) dan log aktivitas.
   - Melakukan inspeksi langsung data absensi melalui database MariaDB atau terminal (`view_db.py`).

---

## 4. Arsitektur Sistem & Alur Kerja (Workflow)

### 4.1. Alur Kerja Presensi (State Transition Diagram)
```
[IDLE] (Kursor fokus di RFID Reader)
  │
  ▼  (User menempelkan kartu RFID)
[IDENTIFYING] (Pencarian karyawan ke API Backend)
  │
  ├─► (Jika ID tidak terdaftar) ──► [ERROR] ──► (Jeda 2.5s) ──► [IDLE]
  │
  ▼  (Jika Karyawan Ditemukan)
[EMPLOYEE_FOUND] (Tampilkan nama & UID kartu)
  │  (Jeda 1.2s)
  ▼
[CAMERA_READY] (Aktifkan panduan oval wajah biometrik)
  │  (Jeda 1.5s)
  ▼
[COUNTDOWN] (Hitung mundur visual 3 -> 2 -> 1)
  │
  ▼
[CAPTURING] (Kilatan lampu rana & capture frame canvas)
  │
  ▼
[SAVING] (Kirim Multipart PNG ke /api/upload)
  │
  ├─► (Jika Unggah Gagal) ──► [ERROR] ──► (Jeda 2.5s) ──► [IDLE]
  │
  ▼  (Jika Sukses)
[SUCCESS] ("ABSENSI BERHASIL", Tampilkan pratinjau foto)
  │  (Jeda 2.5s)
  ▼
[IDLE] (Reset seluruh variabel, siap untuk presensi berikutnya)
```

### 4.2. Arsitektur Komponen
```
┌─────────────────────────────────────────────────────────┐
│              FRONTEND (Browser Kiosk Chromium)          │
│  - WebRTC Webcam Feed        - Audio/Visual Feedback    │
│  - Input RFID Trapper        - Mirror / Fullscreen Mode │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP REST API (Port 8000)
┌────────────────────────────▼────────────────────────────┐
│               BACKEND (Python HTTP Server)              │
│  - Endpoint Routing          - Magic Bytes PNG Check    │
│  - Multipart Parser          - Structured File Storage  │
└──────────────┬────────────────────────────┬─────────────┘
               │ Primary                    │ Fallback
┌──────────────▼─────────────┐ ┌────────────▼─────────────┐
│    MariaDB (attendance_db) │ │   Local Storage (JSON)   │
│  - employees table         │ │  - employees.json        │
│  - attendance table        │ │  - attendance.json       │
└────────────────────────────┘ └──────────────────────────┘
```

---

## 5. Spesifikasi Kebutuhan Fungsional (Functional Requirements)

### FR-01: Pembacaan Kartu RFID (USB HID Emulation)
* Sistem harus mampu mendeteksi nomor UID kartu RFID yang dikirimkan oleh USB Reader.
* Input field RFID harus otomatis difokuskan kembali secara konsisten setiap kali terjadi klik di area manapun pada layar.
* Sistem harus mendukung nomor UID berformat desimal (8–10 digit) maupun format heksadesimal.

### FR-02: Pratinjau dan Pengaturan Kamera
* Sistem harus mengakses video stream webcam pengguna dengan resolusi ideal HD (1280x720) menggunakan API peramban modern `navigator.mediaDevices.getUserMedia`.
* Menyediakan fitur **Mirror Mode** (pencerminan gambar) yang dapat diaktifkan/dinonaktifkan oleh pengguna melalui tombol antarmuka dan statusnya tersimpan di `localStorage`.
* Menyediakan tombol **Layar Penuh (Fullscreen)** untuk pengoperasian mode kiosk.
* Menyediakan tombol coba ulang otomatis (*auto-retry*) dan tombol manual jika webcam sempat terkunci oleh sistem operasi saat booting.

### FR-03: Panduan Biometrik & Pengambilan Gambar
* Menampilkan garis oval panduan posisi wajah (*face guide*) pada layar saat transisi status `CAMERA_READY` dan `COUNTDOWN`.
* Menjalankan animasi hitung mundur 3 detik dengan angka animasi pop-out.
* Menampilkan efek kilatan cahaya rana (*shutter flash*) saat pengambilan gambar berlangsung.
* Menampilkan pratinjau beku (*freeze frame preview*) dari foto yang baru saja diambil.

### FR-04: Penyimpanan Foto & Validasi Keamanan
* File foto disimpan dalam struktur folder berbasis tanggal: `captures/YYYY/MM/DD/`.
* Penamaan file mengikuti standar: `<EMPLOYEE_ID>_<YYYYMMDD>_<HHMMSS>.png`.
* Backend server wajib memverifikasi **Magic Bytes** file (`\x89PNG\r\n\x1a\n`) untuk memastikan bahwa berkas yang diunggah adalah file gambar PNG asli dan bukan file biner berbahaya.
* Batas ukuran unggahan foto dibatasi maksimum **10 Megabytes**.

### FR-05: Database & Mekanisme Failover Mandiri (*Dual-Layer Storage*)
* **Mode Utama (MariaDB):** Menyimpan data pada database `attendance_db` pada tabel `employees` dan `attendance`.
* **Mode Cadangan (JSON Storage):** Apabila koneksi MariaDB terputus atau layanan MariaDB belum menyala, sistem otomatis mengalihkan penyimpanan ke file `data/employees.json` dan `data/attendance.json`.
* Transisi antara database dan cadangan lokal terjadi secara transparan tanpa menampilkan pesan crash kepada karyawan yang sedang presensi.

### FR-06: Manajemen Data Karyawan (Admin Web)
* Tersedia antarmuka khusus di URL `/employees.html` yang terhubung ke REST API `/api/employees`.
* **Tambah Karyawan:** Form pendaftaran yang menerima ID Karyawan, Nama, dan UID RFID.
* **Cari Karyawan:** Filter pencarian instan (*live search*) berdasarkan Nama, ID, atau UID.
* **Hapus Karyawan:** Fitur penghapusan data karyawan disertai dialog konfirmasi keamanan.
* Setiap penambahan/penghapusan karyawan di-sinkronkan secara serentak ke MariaDB dan file `employees.json`.

---

## 6. Spesifikasi Kebutuhan Non-Fungsional (Non-Functional Requirements)

### 6.1. Performa
* Waktu respons pencarian karyawan via API backend $\le 100\text{ ms}$.
* Waktu pemrosesan penulisan file gambar dan pencatatan presensi $\le 300\text{ ms}$.
* Antarmuka frontend beroperasi mulus pada frame rate $60\text{ FPS}$.

### 6.2. Keamanan
* **Sanitasi Input:** Melindungi terhadap serangan *SQL Injection* dengan parameter query dan pengamanan karakter kutip.
* **Keamanan File Sistem:** Mencegah eksploitasi *Path Traversal* dengan membersihkan nama berkas ID karyawan sebelum disimpan ke disk.
* **Isolasi Layanan:** Pada sistem operasi Linux, backend dijalankan di bawah hak akses user terisolasi `attendance` tanpa hak akses root.

### 6.3. Keandalan & Robustness
* Terdapat penanganan batas waktu (*request timeout*) sebesar 6-10 detik pada setiap panggilan AJAX/fetch.
* Siklus error recovery otomatis mengembalikan sistem ke kondisi `IDLE` dalam 2.5 detik jika terjadi gangguan koneksi atau kartu tidak valid.

---

## 7. Desain Antarmuka Pengguna (UI/UX)

Sistem menggunakan gaya desain **Industrial Dark-Mode Kiosk** dengan prinsip kontras tinggi agar nyaman dipandang dari jarak 1–2 meter:
* **Warna Latar Belakang:** Hitam pekat `#0a0d13` & `#10141d` untuk menghemat konsumsi daya layar dan mereduksi pantulan cahaya.
* **Warna Aksen:** Biru `#58a6ff` untuk status normal/fokus, Hijau `#238636` untuk status presensi berhasil, dan Merah `#da3633` untuk penanda kesalahan.
* **Status Banner Ultra-Prominent:** Menampilkan teks status ukuran besar dengan font tebal (*bold*) yang memandu tindakan karyawan langkah demi langkah.
* **Jam Waktu Nyata:** Dilengkapi penunjuk tanggal dan jam digital yang diperbarui setiap detik.

---

## 8. Spesifikasi Antarmuka Aplikasi (API Endpoints)

| Method | Endpoint | Deskripsi | Parameter / Payload | Respon Sukses |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | Melayani halaman kiosk utama | - | `200 OK` (HTML) |
| `GET` | `/employees.html` | Melayani halaman manajemen karyawan | - | `200 OK` (HTML) |
| `GET` | `/api/employee` | Mencari data karyawan berdasarkan ID atau RFID | Query: `?id=<string>` | `{"success": true, "employee_id": "...", "name": "..."}` |
| `POST` | `/api/upload` | Mengunggah foto presensi dan mencatat kehadiran | `multipart/form-data`: `employee_id`, `image` | `{"success": true, "message": "Attendance recorded", "filepath": "..."}` |
| `GET` | `/api/employees` | Mengambil seluruh daftar karyawan aktif | - | `{"success": true, "employees": [...]}` |
| `POST` | `/api/employees` | Menambah atau memperbarui data karyawan | JSON: `{"employee_id", "name", "rfid_uid"}` | `{"success": true, "message": "Data karyawan berhasil disimpan"}` |
| `DELETE`| `/api/employees` | Menghapus data karyawan | Query: `?id=<employee_id>` | `{"success": true, "message": "Karyawan ... berhasil dihapus"}` |

---

## 9. Struktur Basis Data (MariaDB)

### 9.1. Tabel `employees`
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | `INT AUTO_INCREMENT` | Primary Key |
| `employee_id` | `VARCHAR(50) UNIQUE NOT NULL` | Nomor induk karyawan (contoh: `EMP001`) |
| `name` | `VARCHAR(100) NOT NULL` | Nama lengkap karyawan |
| `rfid_uid` | `VARCHAR(50) UNIQUE` | UID nomor kartu RFID |
| `is_active` | `TINYINT(1) DEFAULT 1` | Status karyawan (1: Aktif, 0: Nonaktif) |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | Waktu pendaftaran |
| `updated_at` | `TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | Waktu pembaruan data |

### 9.2. Tabel `attendance`
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | `BIGINT AUTO_INCREMENT` | Primary Key |
| `employee_id` | `VARCHAR(50) NOT NULL` | Foreign Key merujuk ke `employees.employee_id` |
| `captured_at` | `DATETIME NOT NULL` | Waktu pengambilan foto presensi |
| `image_path` | `VARCHAR(255) NOT NULL` | Path relatif file foto di sistem berkas |
| `attendance_status` | `VARCHAR(20) DEFAULT 'SUCCESS'` | Status presensi (contoh: `SUCCESS`) |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | Waktu pencatatan log |

---

## 10. Panduan Deployment & Otomasi Layanan (Debian Kiosk)

### 10.1. Persiapan Sistem
Eksekusi file skrip instalasi untuk mempersiapkan paket dependensi (Python 3 venv, MariaDB, Chromium Browser, dan UFW Firewall):
```bash
sudo bash scripts/debian_setup.sh
```

### 10.2. Deployment Aplikasi
Menyalin berkas produksi ke direktori `/opt/employee-attendance`, migrasi skema basis data, dan konfigurasi hak akses user `attendance`:
```bash
sudo bash scripts/deploy_debian.sh
```

### 10.3. Konfigurasi Autostart Layanan & Desktop Kiosk
Menghubungkan aplikasi ke sistem daemon `systemd` agar otomatis menyala saat mesin dihidupkan:
```bash
sudo bash scripts/setup_autostart.sh
```
* **Layanan Latar Belakang:** `/etc/systemd/system/attendance-server.service`
* **Peluncur Layar Kiosk:** `/etc/xdg/autostart/attendance-kiosk.desktop` yang mengeksekusi [launch_kiosk.sh](file:///d:/magang/projek/employee-attendance/scripts/launch_kiosk.sh) saat sesi GUI aktif.

---

## 11. Kesimpulan

Dokumen Kebutuhan Produk (PRD) ini merangkum fondasi fungsional, arsitektural, teknis, dan standar visual sistem presensi `absen_ntp`. Melalui perpaduan pemindaian kartu instan, verifikasi foto webcam biometrik, proteksi fallback penyimpanan ganda, serta desain ramah kiosk, produk ini siap beroperasi secara andal di lingkungan produksi industri maupun perkantoran.
