# Laporan Progres Pengerjaan Sistem Absensi Karyawan

**Nama Proyek:** Sistem Absensi Karyawan Berbasis RFID dan Kamera  
**Lokasi Proyek:** `employee-attendance/`  
**Periode Pengerjaan:** 7 September 2026  

---

## Bab 1: Hasil Pekerjaan yang Telah Diselesaikan

### 1.1 Gambaran Umum Sistem

Sistem absensi ini dirancang untuk berjalan di atas lingkungan Linux Debian dengan spesifikasi perangkat keras terbatas. Backend menggunakan Python (`http.server`) sebagai web server sederhana tanpa framework berat. Frontend dibangun dengan HTML, CSS, dan JavaScript murni. Sistem mendukung dua metode identifikasi karyawan:
1. **RFID Card** — karyawan mendekatkan kartu ke reader.
2. **Input Manual NIK** — karyawan mengetikkan NIK secara langsung sebagai cadangan.

Database utama menggunakan **MariaDB**, dengan fallback otomatis ke file `data/employees.json` apabila koneksi database tidak tersedia.

---

### 1.2 Arsitektur Sistem

```
[Browser Karyawan]
       |
       | HTTP
       v
[server.py] -- route /api/employee      --> [db.py] --> MariaDB / employees.json
            -- route /api/attendance    --> [db.py] --> Tabel attendance
            -- route /api/stream        --> [camera_v4l2.py] --> Kamera USB V4L2
            -- route /static/           --> index.html, app.js, employees.html
```

**File Utama:**

| File | Peran |
|---|---|
| `server.py` | HTTP server, routing API |
| `db.py` | Logika database (MariaDB + JSON fallback) |
| `camera_v4l2.py` | Streaming kamera via V4L2 |
| `static/index.html` | Halaman utama absensi (kiosk) |
| `static/app.js` | State machine frontend (RFID, kamera, API) |
| `static/employees.html` | Halaman manajemen data karyawan |
| `data/employees.json` | Data karyawan fallback |
| `config.py` | Konfigurasi global (DB, kamera, port) |

---

### 1.3 Fitur yang Telah Diimplementasikan

#### A. Tampilan Absensi (Layar Utama)

- Tampilan **fullscreen kiosk** yang bersih, hanya menampilkan:
  - Jam dan tanggal real-time
  - Stream video kamera langsung
  - Kolom input NIK (label diganti menjadi **"Masukkan NIK"**)
  - Tombol **"ABSEN"** untuk konfirmasi manual
  - Status bar keterangan (menunggu / berhasil / gagal)
- Navigasi menu yang tidak perlu (seperti "Riwayat Foto") **telah dihapus** agar UI lebih ringan dan fokus.
- Header "Logitech C930e" pada tampilan kamera **telah dihapus** dari UI.

#### B. Input RFID dan Input Manual NIK

- RFID reader (QinHeng Electronics) terintegrasi sebagai **keyboard input** — saat kartu di-tap, ID terbaca otomatis ke field NIK.
- Field NIK dibuat **dapat diedit secara manual** sehingga karyawan yang tidak membawa kartu tetap bisa melakukan absensi dengan mengetik NIK mereka.
- Tombol **"ABSEN"** memvalidasi NIK ke API backend.
- Sistem menampilkan **nama karyawan** dan **hasil absensi** (Masuk/Pulang) setelah verifikasi berhasil.

#### C. Streaming Kamera Real-Time

- Streaming kamera menggunakan modul `camera_v4l2.py` dengan protokol **MJPEG over HTTP**.
- Frame rate dioptimasi menjadi **~15 FPS** (`sleep = 0.06 detik`) untuk menyeimbangkan kelancaran tampilan dan beban CPU.
- Pengurangan sleep berhasil **menekan penggunaan CPU hingga ~50%** dibandingkan konfigurasi awal.

#### D. Pencatatan Absensi

- Setiap tap RFID atau input NIK yang berhasil diverifikasi akan **mencatat data absensi** ke database MariaDB.
- Data yang dicatat meliputi: NIK karyawan, nama, timestamp (tanggal & jam), dan status (Masuk/Pulang).
- Log absensi tersimpan di direktori `logs/`.

#### E. Manajemen Data Karyawan (`employees.html`)

- Halaman daftar karyawan menampilkan tabel berisi: NIK, Nama, dan ID RFID.
- Fitur **Edit Data Karyawan** melalui modal popup:
  - Mengubah **NIK**, **Nama**, dan **ID RFID** karyawan.
  - Perubahan disimpan ke database via endpoint `PUT /api/employees/update`.
- Backend mendukung pencarian karyawan berdasarkan NIK maupun ID RFID, termasuk penanganan variasi format.

#### F. Perbaikan dan Sinkronisasi Data

- Data karyawan `data/employees.json` diperbarui dengan entri yang belum tercatat (termasuk mapping RFID yang sebelumnya tidak terdaftar).
- NIK karyawan tertentu berhasil diperbarui melalui fitur edit yang baru dibuat.
- Lookup RFID diperkuat untuk menangani berbagai variasi format ID yang dikirim oleh reader.

---

### 1.4 Optimasi Performa

Mengingat sistem berjalan di Debian dengan spesifikasi terbatas, beberapa optimasi telah dilakukan:

| Aspek | Sebelum | Sesudah |
|---|---|---|
| Frame rate kamera | Default (tidak dikontrol) | ~15 FPS (sleep 0.06s) |
| Halaman/menu aktif | Banyak (termasuk Riwayat Foto) | Hanya halaman absensi |
| Beban CPU streaming | Tinggi | Berkurang ~50% |
| Navigasi UI | Ada menu navigasi | Dihapus, fokus kiosk |

---

## Bab 2: Rencana Selanjutnya

### 2.1 Implementasi Laporan Rekap Absensi

Saat ini sistem belum memiliki fitur untuk melihat dan mengekspor rekap data absensi. Rencana ke depan adalah:
- Membuat halaman **Laporan Absensi** yang dapat memfilter data berdasarkan rentang tanggal, nama karyawan, atau departemen.
- Menyediakan fitur **ekspor ke format Excel (.xlsx) atau CSV** sehingga data absensi dapat langsung digunakan untuk keperluan penggajian atau pelaporan HRD.
- Menambahkan **ringkasan statistik** seperti: jumlah hadir, jumlah tidak hadir, dan keterlambatan per karyawan dalam periode tertentu.

### 2.2 Pengujian Menyeluruh dan Deployment Final

Sebelum sistem diserahkan sebagai produk akhir, perlu dilakukan serangkaian pengujian dan persiapan deployment:
- **Pengujian fungsional end-to-end**: memastikan seluruh alur absensi (tap RFID -> verifikasi -> catat -> tampil hasil) berjalan tanpa error di lingkungan Debian yang sebenarnya.
- **Pengujian edge case**: karyawan tidak terdaftar, kartu rusak, kamera tidak terdeteksi, dan koneksi database terputus.
- **Dokumentasi teknis final**: menyempurnakan `README.md` dan membuat panduan operasional singkat untuk operator/admin sistem.
- **Autostart service**: mengonfigurasi sistem agar server Python berjalan otomatis saat perangkat dinyalakan (menggunakan `systemd` service unit).

---
