# Laporan Progres Mingguan (Minggu Ke-6)

**Nama Proyek:** Sistem Presensi Karyawan Berbasis Dual RFID, Kamera V4L2, dan Multi-Service Decoupled  
**Periode Pengerjaan:** 13 Oktober – 19 Oktober 2026  
**Penyusun:** Mahasiswa Magang  
**Repository:** `employee-attendance/`  

---

## Ringkasan Eksekutif (Executive Summary)

Pada minggu ke-6 (13 Oktober – 19 Oktober 2026), fokus pengerjaan difokuskan pada **penyempurnaan akhir dan isolasi proteksi ketat pada pemetaan tombol keypad numerik (Numpad samping)**, penanganan kasus khusus tombol di luar Numpad yang sempat bocor, serta pengujian stabilitas input presensi manual di mesin Kiosk.

Berdasarkan evaluasi langsung di lapangan, ditemukan bahwa tombol angka baris atas dan tombol Backspace pada keyboard utama sebelumnya masih dapat memicu input data. Pada minggu ini, sistem telah disempurnakan secara menyeluruh dengan memblokir total akses keyboard utama dan mengunci interaksi mesin Kiosk **100% eksklusif hanya untuk Numpad sebelah kanan**. Selain itu, pembatasan panjang NIK tepat 6 digit dan pemetaan tombol pintas (**Enter = Masuk**, **+ = Keluar**, **-/* = Clear**, **/ = Backspace**) telah berjalan sempurna tanpa celah *keystroke leak*.

---

## 1. Penyempurnaan & Isolasi Ketat Tombol Numpad

Untuk memastikan karyawan hanya menggunakan keypad numerik dan tidak terjadi penekanan tombol keyboard utama yang tidak disengaja, diterapkan aturan isolasi yang ketat:

```
┌────────────────────────────────────────────────────────┐
│             STATUS AKSES TOMBOL PADA KIOSK             │
├──────────────────────────┬─────────────────────────────┤
│ Perangkat Input          │ Status Akses                │
├──────────────────────────┼─────────────────────────────┤
│ Numpad Samping (0-9)     │ ✅ AKTIF (Maksimal 6 Digit) │
│ Numpad Enter             │ ✅ AKTIF (Presensi MASUK)   │
│ Numpad + (Add)           │ ✅ AKTIF (Presensi KELUAR)  │
│ Numpad - (Subtract)      │ ✅ AKTIF (Clear/Reset)      │
│ Numpad * (Multiply)      │ ✅ AKTIF (Clear/Reset)      │
│ Numpad / (Divide)        │ ✅ AKTIF (Backspace 1 Digit)│
├──────────────────────────┼─────────────────────────────┤
│ Angka Baris Atas (0-9)   │ ❌ DIBLOKIR TOTAL           │
│ Backspace Keyboard Biasa │ ❌ DIBLOKIR TOTAL           │
│ Tombol Huruf & Simbol    │ ❌ DIBLOKIR TOTAL           │
└──────────────────────────┴─────────────────────────────┘
```

### A. Rincian Pemetaan Tombol Eksklusif:
1. **Input Angka NIK (`Numpad0` s/d `Numpad9`):**
   - Hanya menerima angka dari keypad numerik sebelah kanan.
   - Tetap berfungsi normal baik saat lampu **NumLock ON** maupun **NumLock OFF** (fallback tombol navigasi `Home`, `End`, `Arrow`, `PgUp`, `PgDn`, `Ins`).
   - Dibatasi secara mutlak **maksimal 6 digit**.
2. **Presensi Masuk (`NumpadEnter`):**
   - Memproses pencatatan kehadiran **MASUK (IN / Kode: 1)** dan memicu jepretan kamera secara instan.
3. **Presensi Keluar (`NumpadAdd` / `+`):**
   - Memproses pencatatan kehadiran **KELUAR (OUT / Kode: 0)** dan memicu jepretan kamera secara instan.
4. **Clear / Reset Semuanya (`NumpadSubtract` / `-` dan `NumpadMultiply` / `*`):**
   - Mengosongkan seluruh kolom input NIK secara langsung agar pengguna dapat mengetik ulang dari awal jika terjadi kesalahan fatal.
5. **Backspace 1 Digit (`NumpadDivide` / `/`):**
   - Menjadi **satu-satunya tombol** untuk menghapus 1 karakter terakhir yang salah ketik.

---

## 2. Pemblokiran Total Akses Keyboard Utama (Anti-Bocor)

Menjawab kendala di mana tombol angka baris atas dan Backspace utama masih sempat berfungsi, dilakukan perbaikan multi-layer:

### A. Di Level Frontend Browser (`absen/static/app.js`):
- Pemeriksaan properti `event.code`:
  - Tombol dengan kode `Digit0` s/d `Digit9` (baris atas) dicegat dan dinonaktifkan via `event.preventDefault()`.
  - Tombol dengan kode `Backspace` pada keyboard biasa diblokir via `event.preventDefault()`.
  - Hanya tombol dengan kode berawalan `Numpad` yang diizinkan memproses data atau manipulasi teks.
  - Memastikan *event listener* global tidak meloloskan tombol non-Numpad meskipun kursor mouse sedang aktif atau tidak aktif pada kolom NIK.

### B. Di Level Kernel Linux Daemon (`absen/capture.py`):
- Pembersihan scancode keyboard utama dari kamus kernel:
  - Menghapus scancode baris atas (scancode 2 hingga 11).
  - Menghapus scancode Backspace standar Linux (scancode 14).
  - Mengunci pemetaan hanya pada scancode keypad: Numpad ON (71–82), Numpad OFF (102–110), Enter (96/28), Plus (78), Clear (74/55), dan Slash (98/181).

---

## 3. Validasi & Sanitasi Ketat Panjang NIK 6 Digit

Panjang NIK distandarkan tepat 6 digit untuk mencegah data kotor masuk ke database:
1. **Atribut HTML:** Penambahan atribut `maxlength="6"` dan input mode numerik pada input field.
2. **Realtime Slicing:** Event input memotong string secara otomatis (`sanitized.slice(0, 6)`) jika terjadi injeksi data lebih dari 6 karakter.
3. **Buffer Limiter:** Pemotongan buffer transaksi di kernel Linux dibatasi maksimal 6 karakter sebelum diteruskan ke pipeline presensi.

---

## 4. Ringkasan File & Modul yang Dikerjakan pada Minggu Ke-6

| Modul / File | Status | Deskripsi Pekerjaan |
| :--- | :--- | :--- |
| `absen/capture.py` | **Diperbarui** | Menghapus scancode angka baris atas & backspace utama, mengunci eksklusif scancode keypad samping |
| `absen/static/app.js` | **Diperbarui** | Filter `event.code` ketat untuk memblokir angka atas & backspace biasa, pemetaan tombol `-`, `*`, `/`, `Enter`, `+` Numpad |
| `absen/static/index.html` | **Diperbarui** | Update teks footer Kiosk, penambahan `maxlength="6"`, pembaruan cache buster script (`v=34`) |
| `laporan_mingguan_ke_6.md` | **Baru** | Dokumentasi laporan progres mingguan lengkap Minggu Ke-6 |

---

## 5. Prosedur Pembaruan & Pengoperasian di Debian Linux

Untuk memperbarui sistem pada mesin Debian Kiosk:

```bash
# 1. Menarik update terbaru dari repositori GitHub
cd /home/debian/www/attendance
git pull origin main

# 2. Restart background service capture / Kiosk (Tanpa sudo)
pkill -f "python.*capture.py"
nohup /home/debian/www/attendance/venv/bin/python absen/capture.py > /dev/null 2>&1 &
```
