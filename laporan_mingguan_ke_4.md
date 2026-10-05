# Laporan Progres Mingguan (Minggu Ke-4)

**Nama Proyek:** Sistem Presensi Karyawan Berbasis Dual RFID, Kamera V4L2, dan Multi-Service Decoupled  
**Periode Pengerjaan:** 22 September – 05 Oktober 2026  
**Penyusun:** Mahasiswa Magang  
**Repository:** `employee-attendance/`  

---

## Ringkasan Eksekutif (Executive Summary)

Pada minggu ke-4 (22 September – 05 Oktober 2026), fokus pengerjaan diarahkan pada **rekayasa skema relasional database (pemisahan tabel kartu RFID mandiri)**, **penanganan kartu tidak terdaftar (tabel `attendance_error` & audit snapshot)**, **optimasi performa latensi antrian presensi cepat (1.2 detik hold time & 0.7 detik debounce)**, **sinkronisasi data real-time dua arah (Dual-Channel SSE + 500ms Fast Polling)**, serta **integrasi sistem input keyboard & Numpad lengkap (Enter untuk MASUK, + untuk KELUAR, dan penanganan NumLock ON/OFF)**.

Seluruh fitur telah berhasil diuji coba secara langsung di lingkungan Linux Debian (mesin Kiosk dan service backend), memberikan alur presensi yang sangat cepat, handal, dan akurat untuk penggunaan banyak karyawan sekaligus.

---

## 1. Rekayasa Basis Data: Skema Relasional Tabel RFID Mandiri (Opsi B) & Dual Attendance

Sebelumnya, nomor kartu RFID disimpan langsung pada satu kolom di tabel utama `employees` (`employees.rfid_no`). Berdasarkan hasil diskusi arsitektur dan kebutuhan skalabilitas jangka panjang, sistem ditingkatkan menggunakan **Skema Relasional Opsi B (Tabel Mandiri `rfid_cards`)** serta **Pemisahan Tabel Presensi Valid & Error**.

```
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│           employees             │                 │           rfid_cards            │
├─────────────────────────────────┤                 ├─────────────────────────────────┤
│ id (PK)                         │◄─── 1 : N ────-─│ id (PK)                         │
│ nik (VARCHAR UNIQUE)            │                 │ employee_id (FK -> employees.id)│
│ name (VARCHAR)                  │                 │ rfid_number (VARCHAR UNIQUE)    │
│ position (VARCHAR)              │                 │ is_active (TINYINT / BOOLEAN)   │
│ created_at / updated_at         │                 │ assigned_at / updated_at        │
└─────────────────────────────────┘                 └─────────────────────────────────┘
                 │                                                   │
                 ▼                                                   ▼
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│           attendance            │                 │        attendance_error         │
│   (Presensi Karyawan Valid)     │                 │ (Kartu Tidak Terdaftar / Invalid│
├─────────────────────────────────┤                 ├─────────────────────────────────┤
│ id (PK)                         │                 │ id (PK)                         │
│ employee_id (FK -> employees.id)│                 │ rfid_number (VARCHAR)           │
│ nik (VARCHAR)                   │                 │ scan_time (DATETIME)            │
│ timestamp (DATETIME)            │                 │ scan_type (TINYINT - IN/OUT)    │
│ scan_type (TINYINT: 1=IN, 0=OUT)│                 │ reason (VARCHAR - Error Reason) │
│ raw_data (VARCHAR - 15 digit)   │                 │ photo_path (VARCHAR)            │
│ photo_path (VARCHAR)            │                 │ raw_data (VARCHAR)              │
└─────────────────────────────────┘                 └─────────────────────────────────┘
```

### A. Keunggulan Implementasi Tabel `rfid_cards`:
1. **Dukungan Multi-Card per Karyawan:** Memungkinkan 1 karyawan memiliki kartu cadangan atau mengganti kartu yang rusak/hilang tanpa menghapus riwayat presensi kartu lama.
2. **Audit & Status Tracking:** Setiap kartu memiliki status aktif/nonaktif (`is_active`) serta tanggal penetapan (`assigned_at`).
3. **Auto-Migration Otomatis:** Script backend MariaDB (`connector/db.py` dan `admin/db.py`) secara otomatis melakukan migrasi data kolom lama `employees.rfid_no` ke tabel baru `rfid_cards` jika tabel belum terbentuk.

### B. Implementasi Tabel `attendance_error` untuk Audit Keamanan:
- Ketika kartu yang di-tap **belum terdaftar** di sistem, sistem tetap mengambil jepretan foto wajah melalui kamera Logitech C930e (V4L2).
- Catatan kartu invalid disimpan di tabel `attendance_error` lengkap dengan snapshot foto, waktu scan, tipe scan (In/Out), dan alasan error (`UNREGISTERED_CARD`).
- Admin dapat melihat dan memfilter log kartu yang tidak terdaftar di Dashboard Admin sebagai bagian dari audit keamanan fisik.

---

## 2. Optimasi Sinkronisasi Real-Time & Antrian Presensi Cepat

Untuk mengatasi kebutuhan antrian karyawan yang padat di gerbang masuk/keluar pabrik atau kantor, dilakukan pembenahan menyeluruh pada sisi waktu respon Kiosk:

```
[ Tap Kartu / Input NIK ] ──► [ Ambil Snapshot & Verifikasi ] ──► [ Layar Tampil: 1.2 Detik ] ──► [ Otomatis Siap (IDLE) ]
                                                                      ▲
                                                     (Sebelumnya 4s ──┴── Terlalu lama untuk antrian)
```

### A. Dual-Channel Real-Time Sync (SSE + 500ms Fast Polling)
- **Kendala Sebelumnya:** Terkadang browser Kiosk mengalami perlambatan event stream saat rendering nama dan foto karyawan dari hardware reader.
- **Solusi:** Mengimplementasikan sinkronisasi dua jalur (*Dual-Channel*):
  1. Jalur Utama: Server-Sent Events (SSE) untuk perpindahan data instan berbasis event (*push*).
  2. Jalur Pendukung: Polling cepat berfrekuensi 500ms sebagai fallback penjamin data selalu termuat tanpa *freeze*.
- Memastikan informasi Nama Karyawan, NIK, dan Tipe Presensi (MASUK/KELUAR) selalu tampil 100% konsisten begitu kartu ditempelkan.

### B. Penurunan Durasi Tampil Layar (*Screen Hold Time*)
- Durasi jeda tampilan hasil presensi diturunkan dari **4 detik menjadi 1.2 detik**.
- Layar Kiosk langsung kembali ke status siap (*IDLE*) dalam waktu singkat, sehingga karyawan berikutnya tidak perlu menunggu lama untuk melakukan tap presensi.

### C. Optimasi Debounce Hardware (0.7 Detik)
- Nilai penahan anti-double tap (hardware debounce) disesuaikan menjadi **0.7 detik**.
- Mencegah pembacaan ganda kartu yang sama dalam satu kali tap tanpa menghambat pergantian antar pengguna yang berbeda.

---

## 3. Integrasi Input Fleksibel: Keyboard & Numpad Keypad

Selain menggunakan tap kartu RFID fisik, sistem kini mendukung penuh input manual menggunakan keyboard maupun keypad numerik (Numpad) eksternal dengan pemetaan tombol cerdas:

### A. Pemetaan Logika Tombol Presensi:
1. **Ketik NIK + Tombol `Enter`** ➔ Memproses **PRESENSI MASUK (IN / Kode: 1)** 🟢
2. **Ketik NIK + Tombol `+` (Plus)** ➔ Memproses **PRESENSI KELUAR (OUT / Kode: 0)** 🔴

### B. Penanganan Status NumLock (ON vs OFF):
Pada keyboard fisik, jika tombol *NumLock* dalam keadaan non-aktif (OFF), keypad angka sebelah kanan biasanya mengirimkan kode navigasi (`Home`, `End`, `Arrow`, `Insert`). Masalah ini telah diselesaikan dengan:
1. **Di Level Kernel Linux (`absen/capture.py`):**
   - Menambahkan pemetaan scancode NumLock ON (71–82) dan fallback scancode NumLock OFF (102–110).
2. **Di Level Antarmuka Browser (`absen/static/app.js`):**
   - Menambahkan event listener yang mendeteksi `event.code` (`Numpad0` s/d `Numpad9`, `NumpadEnter`, `NumpadAdd`).
   - Angka Numpad kanan dijamin masuk ke kolom NIK dalam kondisi NumLock menyala ataupun mati.

### C. Global Keystroke Capture (Tanpa Perlu Klik Mouse):
- Menambahkan penangkap event tombol global pada antarmuka Kiosk.
- Karyawan dapat langsung mengetikkan NIK pada keyboard/numpad tanpa harus mengklik kolom input terlebih dahulu menggunakan mouse.

---

## 4. Penyempurnaan Antarmuka Kiosk (UI/UX Refinement)

Tampilan antarmuka Kiosk pada [absen/static/index.html](file:///d:/magang/projek/employee-attendance/absen/static/index.html) dan [absen/static/style.css](file:///d:/magang/projek/employee-attendance/absen/static/style.css) telah dirapikan:

1. **Penyederhanaan Kolom Input:**
   - Label input diubah menjadi **`MASUKKAN NIK`** yang tegas dan rapi.
   - Placeholder disederhanakan menjadi **`Masukkan NIK`** tanpa teks instruksi panjang di dalam kotak input.
2. **Tombol Masuk & Keluar Berdampingan:**
   - Tersedia tombol visual **`🟢 MASUK (Enter)`** dan **`🔴 KELUAR (+)`** di bawah kotak input untuk opsi operasional berbasis layar sentuh (*touchscreen*) atau mouse.
3. **Pembersihan Komponen Sekunder:**
   - Menghilangkan tombol mirror kamera dan tombol fullscreen yang tidak dibutuhkan pada mode Kiosk terdedikasi.
   - Menghapus banner status lama untuk memberikan ruang visual yang lebih luas pada pratinjau kamera dan informasi karyawan.

---

## 5. Ringkasan File & Modul yang Dikerjakan pada Minggu Ke-4

| Modul / File | Tipe Perubahan | Deskripsi Pekerjaan |
| :--- | :--- | :--- |
| `connector/db.py` | **Diperbarui** | Implementasi skema tabel `rfid_cards`, migrasi relasional, pencatatan `attendance` dan `attendance_error` |
| `admin/db.py` | **Diperbarui** | Query relasi join `employees` dengan `rfid_cards`, filter log kartu tidak terdaftar |
| `absen/capture.py` | **Diperbarui** | Penambahan scancode Numpad NumLock ON/OFF, forwarding data NIK/RFID, penguncian exclusive grab |
| `absen/static/index.html` | **Diperbarui** | Label `MASUKKAN NIK`, placeholder bersih, tombol aksi side-by-side Masuk/Keluar |
| `absen/static/app.js` | **Diperbarui** | Dual-channel sync (SSE + Polling 500ms), screen hold time 1.2s, global Numpad capture, shortcut Enter & Plus |
| `absen/static/style.css` | **Diperbarui** | Styling tombol aksi Masuk/Keluar, perataan tipografi panel karyawan, responsivitas layar kiosk |
| `laporan_mingguan_ke_4.md` | **Baru** | Dokumentasi laporan progres komprehensif Minggu Ke-4 |

---

## 6. Prosedur Pembaruan & Pengoperasian di Debian Linux

Seluruh perubahan kode telah diintegrasikan pada repositori GitHub `main`. Untuk menerapkan pembaruan pada mesin Debian:

```bash
# 1. Menarik pembaruan terbaru dari GitHub
cd /home/debian/www/attendance
git pull origin main

# 2. Restart seluruh service (Tanpa sudo)
pkill -9 -f "connector.py"
pkill -9 -f "capture.py"
pkill -9 -f "admin.py"

nohup /home/debian/www/attendance/venv/bin/python connector.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python absen/capture.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python admin/admin.py > /dev/null 2>&1 &
```
