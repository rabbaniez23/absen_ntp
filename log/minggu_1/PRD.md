# Product Requirement Document (PRD)
## Sistem Web Presensi Karyawan Berbasis RFID & Verifikasi Foto (`absen_ntp`)

| Atribut | Keterangan |
| :--- | :--- |
| **Nama Aplikasi** | Sistem Presensi Karyawan (*absen_ntp*) |
| **Versi Dokumen** | 1.1.0 |
| **Status** | Disetujui / Selesai Implementasi |
| **Target Lingkungan** | Linux (Debian 11/12, Ubuntu) & Windows |
| **Teknologi Backend** | Python 3 (HTTP Server native) & PyMySQL |
| **Teknologi Frontend** | HTML5, Vanilla JavaScript, Modern CSS |
| **Penyimpanan Data** | MariaDB (Database Utama) & File JSON (Cadangan Lokal) |

---

## 1. Arsitektur Sistem & Alur Kerja (Workflow)

### 1.1. Alur Kerja Presensi (State Machine)
Sistem menggunakan *finite state machine* berbasis siklus otomatis tanpa perlu interaksi klik tombol untuk presensi:

```
[IDLE] (Kursor fokus otomatis di input RFID)
  │
  ▼  (Pengguna tap kartu RFID)
[IDENTIFYING] (Mencari data karyawan ke Backend)
  │
  ├─► (Jika ID tidak terdaftar) ──► [ERROR] ──► (Jeda 2.5 detik) ──► [IDLE]
  │
  ▼  (Jika Karyawan Ditemukan)
[EMPLOYEE_FOUND] (Tampilkan nama karyawan & UID kartu)
  │  (Jeda 1.2 detik)
  ▼
[CAMERA_READY] (Tampilkan panduan oval posisi wajah)
  │  (Jeda 1.5 detik)
  ▼
[COUNTDOWN] (Hitung mundur visual 3 -> 2 -> 1)
  │
  ▼
[CAPTURING] (Efek lampu kilat & pengambilan frame canvas)
  │
  ▼
[SAVING] (Kirim Multipart foto PNG ke /api/upload)
  │
  ├─► (Jika Gagal Unggah) ──► [ERROR] ──► (Jeda 2.5 detik) ──► [IDLE]
  │
  ▼  (Jika Berhasil)
[SUCCESS] (Status "ABSENSI BERHASIL", Tampilkan pratinjau foto)
  │  (Jeda 2.5 detik)
  ▼
[IDLE] (Reset seluruh variabel, siap untuk presensi berikutnya)
```

### 1.2. Arsitektur Komponen
```
┌─────────────────────────────────────────────────────────┐
│               FRONTEND (Web Browser Application)        │
│  - WebRTC Webcam Feed        - Umpan Balik Visual UI    │
│  - Input RFID Trapper        - Pengaturan Mirror Kamera │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP REST API (Port 8000)
┌────────────────────────────▼────────────────────────────┐
│               BACKEND (Python HTTP Server)              │
│  - Endpoint HTTP Routing     - Validasi Magic Bytes PNG │
│  - Multipart Parser Upload   - Manajemen File Foto Disk │
└──────────────┬────────────────────────────┬─────────────┘
               │ Penyimpanan Utama          │ Cadangan Otomatis
┌──────────────▼─────────────┐ ┌────────────▼─────────────┐
│    MariaDB (attendance_db) │ │    File JSON Lokal       │
│  - Tabel employees         │ │  - data/employees.json   │
│  - Tabel attendance        │ │  - data/attendance.json  │
└────────────────────────────┘ └──────────────────────────┘
```

---

## 2. Spesifikasi Kebutuhan Fungsional (Functional Requirements)

### 2.1. Pembacaan Kartu RFID (USB HID Emulation)
* Sistem mendeteksi nomor UID kartu RFID yang dikirim oleh USB Reader (tipe EM4100 125KHz atau Mifare 13.56MHz).
* Input RFID otomatis mempertahankan fokus kursor secara konsisten, bahkan jika pengguna mengeklik area lain pada layar.
* Sistem mendukung nomor UID berformat desimal (8–10 digit) maupun format heksadesimal.

### 2.2. Feed Kamera & Pengaturan Visual
* Sistem mengakses webcam peramban dengan resolusi ideal HD (1280x720) menggunakan WebRTC API (`navigator.mediaDevices.getUserMedia`).
* Menyediakan fitur **Mirror Mode** (pencerminan gambar) yang dapat dinyalakan/dimatikan melalui tombol antarmuka, dengan status tersimpan di `localStorage`.
* Menyediakan fitur pemulihan otomatis (*auto-retry*) hingga 3 kali jika kamera sempat terkunci oleh sistem saat awal dibuka.

### 2.3. Panduan Wajah & Pengambilan Foto Otomatis
* Menampilkan garis oval panduan posisi wajah pada layar saat status `CAMERA_READY` dan `COUNTDOWN`.
* Menjalankan animasi hitung mundur 3 detik dengan indikator angka.
* Memberikan efek kilatan rana (*shutter flash*) saat pengambilan gambar berlangsung.
* Menampilkan pratinjau beku sementara (*freeze frame preview*) dari foto yang berhasil diambil.

### 2.4. Validasi Keamanan & Penyimpanan Foto di Disk
* Berkas foto disimpan dalam struktur folder berbasis tanggal: `captures/YYYY/MM/DD/`.
* Format nama berkas: `<EMPLOYEE_ID>_<YYYYMMDD>_<HHMMSS>.png`.
* Backend memvalidasi **Magic Bytes** berkas (`\x89PNG\r\n\x1a\n`) untuk menjamin berkas yang diunggah adalah gambar PNG murni.
* Ukuran maksimal file foto dibatasi hingga **10 MB**.

### 2.5. Basis Data Ganda (*Dual-Layer Storage Failover*)
* **Penyimpanan Utama (MariaDB):** Menyimpan data pada basis data `attendance_db` pada tabel `employees` dan `attendance`.
* **Penyimpanan Cadangan (File JSON):** Jika server database MariaDB belum aktif atau koneksi terputus, sistem secara otomatis mengalihkan penyimpanan ke file `data/employees.json` dan `data/attendance.json`.
* Proses presensi tidak boleh terhenti meskipun database MariaDB sedang offline.

### 2.6. Manajemen Data Karyawan (Admin Web)
* Tersedia halaman administrasi di `/employees.html` yang terhubung dengan API `/api/employees`.
* **Tambah Karyawan:** Form input yang menerima ID Karyawan, Nama, dan UID RFID.
* **Pencarian Cepat:** Kotak pencarian langsung (*live search*) untuk memfilter data karyawan berdasarkan Nama, ID, atau UID kartu.
* **Hapus Karyawan:** Fitur penghapusan data karyawan dengan konfirmasi dialog.
* Penambahan dan penghapusan karyawan disinkronkan langsung ke MariaDB dan file `employees.json`.

---

## 3. Spesifikasi Kebutuhan Non-Fungsional (Non-Functional Requirements)

### 3.1. Performa
* Waktu respon pencarian data karyawan melalui API backend $\le 100\text{ ms}$.
* Waktu pemrosesan penulisan file foto dan pencatatan presensi $\le 300\text{ ms}$.
* Tampilan antarmuka berjalan responsif dan stabil pada $60\text{ FPS}$.

### 3.2. Keamanan
* **Pencegahan SQL Injection:** Parameter query dienkapsulasi dan karakter kutip disanitasi.
* **Pencegahan Path Traversal:** Pembersihan karakter spesial pada parameter nama file sebelum disimpan ke disk.
* **Isolasi Layanan Linux:** Backend dapat dijalankan di bawah pengguna sistem `attendance` tanpa hak akses root.

### 3.3. Keandalan (*Robustness*)
* Batas waktu (*timeout*) permintaan HTTP antara 6–10 detik dengan pemutusan otomatis jika server tidak merespon.
* Pemulihan status mandiri (*auto-recovery*) kembali ke status `IDLE` dalam waktu 2.5 detik saat terjadi kegagalan.

---

## 4. Desain Antarmuka Pengguna (UI/UX)

Sistem menggunakan gaya desain **Modern Dark Mode** yang bersih, berfokus pada kemudahan membaca data:
* **Palet Warna:** Latar gelap `#0a0d13` & `#10141d` dengan kontras teks terang `#f0f6fc`.
* **Aksen Status:** Biru `#58a6ff` untuk status pencarian/fokus, Hijau `#238636` untuk presensi sukses, dan Merah `#da3633` untuk kesalahan.
* **Banner Status:** Menampilkan instruksi yang jelas dengan font tebal (*bold*) agar mudah dibaca pengguna.
* **Jam Digital Realtime:** Dilengkapi penunjuk tanggal dan jam digital yang diperbarui setiap detik.

---

## 5. Spesifikasi REST API Endpoint

| Method | Endpoint | Fungsi | Parameter / Payload | Respon Sukses (JSON / HTML) |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | Menampilkan halaman utama presensi | - | `200 OK` (HTML) |
| `GET` | `/employees.html` | Menampilkan halaman manajemen karyawan | - | `200 OK` (HTML) |
| `GET` | `/api/employee` | Mencari data karyawan berdasarkan ID atau RFID | Query: `?id=<string>` | `{"success": true, "employee_id": "...", "name": "..."}` |
| `POST` | `/api/upload` | Mengunggah foto dan mencatat presensi | `multipart/form-data`: `employee_id`, `image` | `{"success": true, "message": "Attendance recorded", "filepath": "..."}` |
| `GET` | `/api/employees` | Mengambil semua daftar karyawan aktif | - | `{"success": true, "employees": [...]}` |
| `POST` | `/api/employees` | Menambah data master karyawan baru | JSON: `{"employee_id", "name", "rfid_uid"}` | `{"success": true, "message": "Data karyawan berhasil disimpan"}` |
| `DELETE`| `/api/employees` | Menghapus data karyawan | Query: `?id=<employee_id>` | `{"success": true, "message": "Karyawan ... berhasil dihapus"}` |

---

## 6. Struktur Basis Data (MariaDB)

### 6.1. Tabel `employees` (Master Karyawan)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | `INT AUTO_INCREMENT` | Primary Key |
| `employee_id` | `VARCHAR(50) UNIQUE NOT NULL` | Nomor identitas unik karyawan (contoh: `EMP001`) |
| `name` | `VARCHAR(100) NOT NULL` | Nama lengkap karyawan |
| `rfid_uid` | `VARCHAR(50) UNIQUE` | Nomor UID kartu RFID dari scanner |
| `is_active` | `TINYINT(1) DEFAULT 1` | Status akun (1: Aktif, 0: Nonaktif) |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | Waktu data dibuat |
| `updated_at` | `TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | Waktu data diperbarui |

### 6.2. Tabel `attendance` (Riwayat Presensi)
| Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `id` | `BIGINT AUTO_INCREMENT` | Primary Key |
| `employee_id` | `VARCHAR(50) NOT NULL` | Relasi ke `employees.employee_id` |
| `captured_at` | `DATETIME NOT NULL` | Waktu pengambilan foto presensi |
| `image_path` | `VARCHAR(255) NOT NULL` | Path relatif berkas foto di disk |
| `attendance_status` | `VARCHAR(20) DEFAULT 'SUCCESS'` | Status pencatatan (contoh: `SUCCESS`) |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | Waktu pencatatan log ke database |

---

## 7. Petunjuk Menjalankan & Deployment

### 7.1. Menjalankan di Lingkungan Windows
1. Buka terminal (Command Prompt / PowerShell) di folder proyek:
   ```powershell
   python server.py
   ```
2. Buka peramban web dan akses alamat:
   ```
   http://localhost:8000
   ```

### 7.2. Menjalankan di Lingkungan Linux (Debian / Ubuntu)
1. **Persiapan Dependensi:**
   ```bash
   sudo bash scripts/debian_setup.sh
   ```
2. **Deployment Berkas & Migrasi Database:**
   ```bash
   sudo bash scripts/deploy_debian.sh
   ```
3. **Pengaturan Service Otomatis (Opsional):**
   ```bash
   sudo bash scripts/setup_autostart.sh
   ```

---

## 8. Kesimpulan

Dokumen Kebutuhan Produk (PRD) ini menjelaskan secara lengkap alur teknis, spesifikasi fungsional, arsitektur basis data ganda, dan API dari aplikasi web presensi `absen_ntp`. Dengan integrasi sensor RFID USB dan pengambilan foto otomatis, aplikasi ini menjamin pencatatan presensi yang cepat, aman, dan dapat diandalkan.
