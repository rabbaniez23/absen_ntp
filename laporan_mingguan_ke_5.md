# Laporan Progres Mingguan (Minggu Ke-5)

**Nama Proyek:** Sistem Presensi Karyawan Berbasis Dual RFID, Kamera V4L2, dan Multi-Service Decoupled  
**Periode Pengerjaan:** 06 Oktober – 12 Oktober 2026  
**Penyusun:** Mahasiswa Magang  
**Repository:** `employee-attendance/`  

---

## Ringkasan Eksekutif (Executive Summary)

Pada minggu ke-5 (06 Oktober – 12 Oktober 2026), fokus pengerjaan diarahkan pada **penyempurnaan dan isolasi eksklusif sistem input fisik keypad numerik (Numpad sebelah kanan)** sesuai dengan instruksi dan arahan pembimbing lapangan.

Sistem diatur agar mesin Kiosk presensi **hanya menerima input dari tombol Numpad samping** secara terdedikasi. Seluruh tombol keyboard utama di luar Numpad (termasuk angka baris atas, tombol Backspace utama, serta deretan tombol huruf/simbol) diblokir secara ketat untuk mencegah salah ketik atau interaksi yang tidak diinginkan. Selain itu, panjang input NIK manual dibatasi secara mutlak **maksimal 6 digit**, serta ditambahkan fungsi tombol **CLEAR** (`-` dan `*`) dan **BACKSPACE** (`/`) langsung dari keypad numerik.

Seluruh fitur telah berhasil diuji coba pada mesin fisik Debian Linux dan bekerja stabil berdampingan dengan pembacaan kartu Dual RFID reader.

---

## 1. Desain & Pemetaan Tombol Eksklusif Numpad (Dedicated Keypad Layout)

Untuk memudahkan operasional karyawan dan mencegah kesalahan penekanan tombol pada keyboard biasa, perangkat keypad numerik (Numpad) dipetakan secara khusus sebagai antarmuka input mandiri:

```
┌────────────────────────────────────────────────────────┐
│              TATA LETAK FISIK NUMPAD KIOSK             │
├─────────────┬─────────────┬─────────────┬──────────────┤
│  [ NumLk ]  │  [  /  ]    │  [  *  ]    │  [  -  ]     │
│  (NumLock)  │ (BACKSPACE) │   (CLEAR)   │   (CLEAR)    │
├─────────────┼─────────────┼─────────────┼──────────────┤
│  [   7   ]  │  [  8  ]    │  [  9  ]    │              │
├─────────────┼─────────────┼─────────────┤  [  +  ]     │
│  [   4   ]  │  [  5  ]    │  [  6  ]    │  (PRESENSI   │
├─────────────┼─────────────┼─────────────┤   KELUAR)    │
│  [   1   ]  │  [  2  ]    │  [  3  ]    │   [Kode: 0]  │
├─────────────┴─────────────┼─────────────┤              │
│         [   0   ]         │  [  .  ]    ├──────────────┤
│       (Input Digit NIK)   │  (Diabaikan)│  [ Enter ]   │
│     (Maksimal 6 Digit)    │             │  (PRESENSI   │
│                           │             │    MASUK)    │
│                           │             │   [Kode: 1]  │
└───────────────────────────┴─────────────┴──────────────┘
```

### Rincian Fungsi Masing-Masing Tombol:

| Tombol Fisik | Kode Sistem | Fungsi Presensi | Perilaku Sistem |
| :---: | :---: | :---: | :--- |
| **`0` – `9`** | `Numpad0` – `Numpad9` | **Input Angka NIK** | Menambah digit NIK. **Dibatasi maksimal 6 digit**; pengetikan digit ke-7 dst otomatis ditolak. |
| **`Enter`** | `NumpadEnter` | **🟢 PRESENSI MASUK (IN)** | Memvalidasi NIK ke backend dan mencatat status kehadiran **MASUK (Kode: 1)**. |
| **`+` (Plus)** | `NumpadAdd` | **🔴 PRESENSI KELUAR (OUT)** | Memvalidasi NIK ke backend dan mencatat status kehadiran **KELUAR (Kode: 0)**. |
| **`-` (Minus)** & **`*` (Bintang)** | `NumpadSubtract` / `NumpadMultiply` | **🧹 CLEAR / RESET SEMUA** | Mengosongkan seluruh kolom input NIK secara instan untuk mengetik ulang dari awal. |
| **`/` (Slash)** | `NumpadDivide` | **⌫ BACKSPACE (HAPUS 1 DIGIT)** | Menghapus satu digit angka terakhir jika terjadi kesalahan pengetikan digit. |
| **Keyboard Utama** | *Alphabet / Top row numbers / Main Backspace* | **⛔ DIBLOKIR TOTAL** | Seluruh tombol di luar Numpad diblokir (`preventDefault()`) sehingga tidak memengaruhi form. |

---

## 2. Pembatasan Input NIK Maksimal 6 Digit

Panjang Nomor Induk Karyawan (NIK) perusahaan memiliki format standar 6 digit angka (misalnya `210019`). Untuk menjaga konsistensi data dan mencegah kesalahan ketik data yang terlalu panjang, diterapkan validasi multi-layer:

1. **Layer Antarmuka HTML ([`absen/static/index.html`](file:///d:/magang/projek/employee-attendance/absen/static/index.html)):**
   - Penambahan atribut `maxlength="6"` dan `pattern="[0-9]*"` pada elemen input NIK.
2. **Layer Logika JavaScript ([`absen/static/app.js`](file:///d:/magang/projek/employee-attendance/absen/static/app.js)):**
   - Sanitasi realtime saat pengetikan (`input` event): nilai string langsung dipotong dengan `slice(0, 6)`.
   - Pencegahan tombol angka (`keydown` event): jika panjang karakter sudah mencapai 6 digit, penekanan angka berikutnya dibatalkan (`event.preventDefault()`).
3. **Layer Buffer Kernel Daemon ([`absen/capture.py`](file:///d:/magang/projek/employee-attendance/absen/capture.py)):**
   - Pengecekan buffer internal: `if len(buffer) < 6:` sebelum menyimpan karakter ke memori transaksi.

---

## 3. Isolasi Proteksi Keyboard & Penanganan Multi-Layer

Penerapan proteksi ini dilakukan pada dua tingkatan sistem untuk menjamin keandalan penuh:

### A. Level Backend Linux Kernel Subsystem (`absen/capture.py`)
Pemetaan scancode kernel Linux disaring murni hanya untuk keypad numerik:
- **Scancode Numpad NumLock ON:** `71: '7'`, `72: '8'`, `73: '9'`, `75: '4'`, `76: '5'`, `77: '6'`, `79: '1'`, `80: '2'`, `81: '3'`, `82: '0'`.
- **Scancode Numpad NumLock OFF Fallback:** `102: '7'`, `103: '8'`, `104: '9'`, `105: '4'`, `106: '6'`, `107: '1'`, `108: '2'`, `109: '3'`, `110: '0'`.
- **Scancode Kontrol:**
  - `ENTER_CODES = {96, 28}` (Numpad Enter)
  - `PLUS_CODES = {78}` (Numpad Plus)
  - `CLEAR_CODES = {74, 55}` (Numpad Minus & Numpad Asterisk)
  - `BACKSPACE_CODES = {98, 181}` (Numpad Slash)
- **Scancode yang Dihapus / Dinonaktifkan:**
  - Menghapus scancode baris atas keyboard utama (scancode 2 hingga 11).
  - Menghapus scancode Backspace keyboard utama (scancode 14).

### B. Level Frontend Web Kiosk (`absen/static/app.js`)
- Menggunakan deteksi kode hardware browser (`event.code`):
  - Mengabaikan `Digit0` s/d `Digit9` (angka baris atas).
  - Mengabaikan `Backspace` dari keyboard utama.
  - Hanya menerima `event.code.startsWith("Numpad")`.
- **Global Key Event Listener:**
  - Memastikan input Numpad tetap tertangkap langsung meskipun kursor mouse sedang tidak aktif mengklik kotak input NIK.

---

## 4. Ringkasan File & Modul yang Dikerjakan pada Minggu Ke-5

| Modul / File | Status | Deskripsi Pekerjaan |
| :--- | :--- | :--- |
| `absen/capture.py` | **Diperbarui** | Pembersihan scancode keyboard baris atas, penambahan konstanta `CLEAR_CODES` & `BACKSPACE_CODES`, pembatasan buffer 6 digit |
| `absen/static/index.html` | **Diperbarui** | Penambahan atribut `maxlength="6"`, pembaruan teks instruksi footer Kiosk, peningkatan versi cache asset (`v=34`) |
| `absen/static/app.js` | **Diperbarui** | Filter ketat penekanan tombol Numpad samping, pemblokiran angka atas dan backspace biasa, logika tombol `-`, `*`, `/`, `Enter`, `+` |
| `laporan_mingguan_ke_5.md` | **Baru** | Dokumentasi laporan progres komprehensif Minggu Ke-5 |

---

## 5. Prosedur Pembaruan & Pengoperasian di Debian Linux

Seluruh kode program telah diuji coba dan di-push ke repositori GitHub `main`. Untuk menerapkan pembaruan pada mesin terminal Debian:

```bash
# 1. Menarik update terbaru dari GitHub
cd /home/debian/www/attendance
git pull origin main

# 2. Restart service capture / Kiosk (Tanpa sudo)
pkill -f "python.*capture.py"
nohup /home/debian/www/attendance/venv/bin/python absen/capture.py > /dev/null 2>&1 &
```
