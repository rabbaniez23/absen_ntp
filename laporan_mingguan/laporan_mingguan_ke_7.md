# Laporan Progres Mingguan (Minggu Ke-7)

**Nama Proyek:** Sistem Presensi Karyawan Berbasis Dual RFID, Kamera V4L2, dan Multi-Service Decoupled  
**Periode Pengerjaan:** 20 Oktober – 26 Oktober 2026  
**Penyusun:** Mahasiswa Magang  
**Repository:** `employee-attendance/`  

---

## Ringkasan Eksekutif (Executive Summary)

Pada minggu ke-7 (20 Oktober – 26 Oktober 2026), fokus pengerjaan adalah **migrasi basis data dari MariaDB lokal di mesin Kiosk ke server MariaDB terpusat `db2.ntp.id`**, beserta penanganan kendala yang muncul setelah migrasi.

Setelah koneksi dipindahkan, ditemukan dua gejala: **kartu RFID karyawan yang sudah terdaftar dianggap TIDAK VALID**, dan **seluruh data tap tidak masuk ke database baru**. Dari penelusuran log dan pengecekan lingkungan server, akar masalahnya ternyata **bukan pada kode atau database**. Penyebabnya adalah library penghubung MariaDB (`pymysql`) yang belum terpasang di *Python Virtual Environment* (venv) mesin Kiosk. Akibatnya, ketiga service tidak pernah tersambung ke database dan diam-diam memakai cadangan file JSON.

Masalah diselesaikan dengan memasang `pip` dan `pymysql` ke venv **tanpa `sudo`**. Setelah itu tap kartu kembali tervalidasi dan tersimpan ke `db2.ntp.id`. Sebagai pencegahan, sistem kini memberi **peringatan yang jelas di log** saat database tidak tersambung, dan cadangan JSON tetap dapat **mengenali kartu RFID** saat database sedang mati.

---

## 1. Migrasi Basis Data ke Server Terpusat

Basis data dipindahkan dari server MariaDB lokal yang berjalan di mesin Kiosk ke server MariaDB terpusat milik jaringan NTP:

```
┌──────────────────────────────────────────────────────────────────┐
│                  PERUBAHAN LOKASI BASIS DATA                     │
├────────────────────────┬─────────────────────────────────────────┤
│ Sebelum                │ Sesudah                                 │
├────────────────────────┼─────────────────────────────────────────┤
│ MariaDB Lokal          │ MariaDB Server Terpusat                 │
│ Host: 127.0.0.1        │ Host: db2.ntp.id                        │
│ Port: 3306             │ Port: 3306                              │
│ (di mesin Kiosk)       │ (server database terpisah)              │
└────────────────────────┴─────────────────────────────────────────┘
```

```
SEBELUM:                                SESUDAH:
┌────────────── Mesin Kiosk ─────────┐  ┌────────────── Mesin Kiosk ─────────┐
│ capture.py → connector.py ─┐       │  │ capture.py → connector.py ─┐       │
│              admin.py ─────┤       │  │              admin.py ─────┤       │
│                            ▼       │  └────────────────────────────┼───────┘
│                 MariaDB 127.0.0.1  │                               ▼
└────────────────────────────────────┘                  ┌────────────────────────┐
                                                        │ MariaDB db2.ntp.id     │
                                                        └────────────────────────┘
```

### A. Perubahan Konfigurasi
- Nilai default `DB_HOST` pada `connector/config.py` dan `admin/config.py` diubah dari `127.0.0.1` menjadi `db2.ntp.id`.
- Nilai tersebut tetap dapat ditimpa melalui *environment variable* `DB_HOST` tanpa mengubah kode.
- Nama database, akun, struktur tabel (`employees`, `rfid_cards`, `attendance`, `attendance_error`), dan format `raw_data` 15 digit **tidak berubah**.

---

## 2. Kendala Setelah Migrasi

Setelah service dijalankan ulang dengan konfigurasi baru, ditemukan dua gejala berikut:

| No | Gejala | Seharusnya |
| :--- | :--- | :--- |
| 1 | Tap kartu RFID karyawan yang sudah terdaftar di database baru menghasilkan **TIDAK VALID** | Nama karyawan tampil dan absensi tercatat di tabel `attendance` |
| 2 | Data tap (baik valid maupun tidak valid) **tidak masuk ke database baru** | Tap valid masuk `attendance`, tap tidak valid masuk `attendance_error` |

### A. Proses Penelusuran (Diagnosa)
Penelusuran dilakukan langsung di terminal Debian tanpa mengubah kode:

1. **Log Kiosk (`absen/logs/kiosk.log`):** kedua reader membaca UID kartu dengan benar dan lengkap 10 digit (contoh: `0002482012`), sehingga perangkat keras dipastikan tidak bermasalah.
2. **Log Connector (`connector/logs/connector.log`):** NIK yang diketik lewat Numpad tervalidasi, tetapi kartu RFID untuk karyawan yang sama selalu ditolak.
3. **File cadangan JSON:** terdapat 13 record di `attendance.json` dan 17 record di `attendance_error.json` dengan tanda `"db_synced": false`. Artinya, **tidak satu pun tap berhasil masuk ke database**.
4. **Uji koneksi database dengan Python venv:** muncul pesan error berikut.
   ```
   ModuleNotFoundError: No module named 'pymysql'
   ```

---

## 3. Analisis Akar Masalah

### A. Library `pymysql` Belum Terpasang di venv
- Venv di mesin Kiosk dibuat **tanpa `pip`**. Python bawaan Debian tidak menyertakan modul `ensurepip`, dan paket `python3-venv` membutuhkan `sudo` untuk dipasang.
- Python sistem (`/usr/bin/python3`) ternyata sudah memiliki `pymysql`, sedangkan venv tidak. Inilah sebabnya koneksi database berjalan normal sebelum service dijalankan menggunakan venv.
- Ketika `pymysql` tidak ditemukan, fungsi koneksi database langsung mengembalikan nilai kosong **tanpa menulis peringatan apa pun ke log**, lalu sistem berpindah ke cadangan JSON secara diam-diam.

### B. Mengapa NIK Valid tetapi Kartu RFID Tidak Valid
Pada file cadangan `admin/data/employees.json`, nomor kartu RFID disimpan sebagai **kunci (key)**, sedangkan NIK disimpan sebagai **isi (value)**:

```json
"0002482012": {
  "employee_id": "EMP003",
  "nik": "210019",
  "name": "Pak Meka"
}
```

Pencarian cadangan pada connector hanya membaca bagian isi. Akibatnya NIK `210019` dapat ditemukan, tetapi nomor kartu `0002482012` tidak pernah cocok.

### C. Mengapa Data Tidak Masuk ke Database
Karena koneksi tidak pernah terbentuk, seluruh transaksi hanya tersimpan di file cadangan JSON pada mesin Kiosk dan tidak pernah terkirim ke `db2.ntp.id`.

---

## 4. Penyelesaian: Pemasangan `pymysql` ke venv Tanpa `sudo`

Karena venv tidak memiliki `pip`, pemasangan dilakukan menggunakan skrip resmi `get-pip.py` dari PyPA:

```bash
cd /home/debian/www/attendance
curl -sSL https://bootstrap.pypa.io/get-pip.py -o ~/get-pip.py
venv/bin/python ~/get-pip.py
venv/bin/python -m pip install -r requirements.txt
```

Hasil pemasangan:
- `pip 26.2.1` berhasil terpasang di venv.
- `pymysql 1.2.0` berhasil terpasang sesuai `requirements.txt`.

### A. Hasil Verifikasi Setelah Restart Service

| Pengujian | Hasil Log Connector | Status |
| :--- | :--- | :--- |
| Tap kartu terdaftar (Reader IN) | `Karyawan ditemukan di MariaDB: pak meka (NIK: 210019, RFID: 0002482012)` → `Absensi tersimpan ke MariaDB: raw_data=210019130519101` | ✅ Berhasil |
| Tap kartu terdaftar (Reader OUT) | `Absensi tersimpan ke MariaDB: raw_data=210019130519100` | ✅ Berhasil |
| Tap kartu belum terdaftar | `Absensi ERROR tersimpan ke MariaDB: raw_data=0002669170130619101` | ✅ Berhasil (tercatat di `attendance_error`) |

Kode `In/Out` di digit terakhir `raw_data` juga sudah sesuai dengan reader yang digunakan (`1` = Masuk, `0` = Keluar).

---

## 5. Penguatan Sistem Agar Kendala Serupa Tidak Terulang

### A. Peringatan Database Tidak Tersambung
- Jika `pymysql` tidak terpasang atau server database tidak dapat dihubungi, log kini menulis peringatan yang jelas beserta alasannya:
  ```
  DATABASE TIDAK TERSAMBUNG: modul pymysql belum terpasang di venv (...). Sementara memakai cadangan JSON.
  ```
- Peringatan dibatasi **maksimal sekali per menit** agar file log tidak membengkak.
- Saat dijalankan, `connector.py` dan `admin.py` memeriksa koneksi database satu kali. Jika berhasil, log menulis `[Startup] Database MariaDB tersambung: ...`.
- Pesan database dari modul admin sebelumnya tidak pernah tercatat di `admin/logs/admin.log` karena nama logger yang berbeda. Kini pesan tersebut ikut tercatat.

### B. Cadangan JSON Mengenali Kartu RFID
Pencarian cadangan pada connector diperbaiki agar juga membaca nomor kartu yang tersimpan sebagai kunci. Karyawan berstatus nonaktif di cadangan JSON juga ditolak, sama seperti aturan di database. Hasil pengujian dengan kondisi database tidak tersambung:

| Input | Sebelum Perbaikan | Sesudah Perbaikan |
| :--- | :--- | :--- |
| Kartu `0002482012` | ❌ TIDAK VALID | ✅ Dikenali (Pak Meka) |
| NIK `210019` | ✅ Dikenali | ✅ Dikenali |
| Kartu `0002669170` (belum terdaftar) | ❌ TIDAK VALID | ❌ TIDAK VALID (sesuai harapan) |

Dengan perbaikan ini, absensi menggunakan kartu tetap dapat berjalan walaupun server database sedang mati.

---

## 6. Perbaikan Pembacaan Kartu RFID & Input Numpad

Bersamaan dengan migrasi, dilakukan beberapa penyesuaian pada jalur input:

1. **Pemulihan scancode angka standar pada `absen/capture.py`:**
   - Reader RFID USB mengirim UID kartu menggunakan scancode angka baris atas (scancode 2–11).
   - Penghapusan scancode tersebut pada minggu sebelumnya membuat UID kartu tidak terbaca. Scancode ini dipulihkan **khusus untuk listener reader RFID**.
   - Batas 6 digit pada buffer reader dilepas karena UID kartu berjumlah 10 digit.
2. **Kolom input NIK di layar Kiosk (`absen/static/app.js`, `index.html`):**
   - Tetap terkunci hanya untuk Numpad sebelah kanan dengan **maksimal 6 digit**.
   - Pemetaan tombol yang telah disepakati tidak berubah: **Enter = Masuk**, **+ = Keluar**, **-/* = Clear**, **/ = Backspace**.
   - Tap kartu tidak bergantung pada kolom input karena dibaca langsung dari kernel Linux oleh `capture.py`.
3. **Penyimpanan ke database:** ditambahkan `commit` eksplisit setelah penyimpanan absensi agar data dipastikan tersimpan permanen.

---

## 7. Keputusan Terkait Data Uji Coba

Record yang tersimpan di cadangan JSON selama database belum tersambung (13 record valid dan 17 record error) merupakan **data uji coba**. Karena itu diputuskan **tidak dipindahkan** ke database `db2.ntp.id`. Database baru hanya berisi data tap yang tercatat setelah koneksi berhasil.

---

## 8. Perapian Dokumentasi

- Dibuat folder **`laporan_mingguan/`** untuk menampung seluruh laporan progres dan dokumen konteks proyek agar struktur repositori lebih rapi.
- `README.md` ditulis ulang karena masih memuat informasi versi awal proyek (WebRTC, `server.py`, folder `scripts/`, `sql/`, `tests/`, dan perintah `sudo`) yang sudah tidak sesuai dengan sistem saat ini.
- Dokumen `konteks_projek_handover.md` ditambah dengan:
  - **Bagian 6A:** langkah persiapan venv dan pemasangan `pymysql` tanpa `sudo`.
  - **Bagian 6C:** langkah pemeriksaan koneksi database (`/api/health` dan log).
  - **Catatan No. 4:** jika kartu terdaftar dianggap TIDAK VALID, periksa lingkungan (`pymysql`) terlebih dahulu sebelum mengubah kode.

---

## 9. Ringkasan File & Modul yang Dikerjakan pada Minggu Ke-7

| Modul / File | Status | Deskripsi Pekerjaan |
| :--- | :--- | :--- |
| `connector/config.py` | **Diperbarui** | Default `DB_HOST` dipindah ke `db2.ntp.id` |
| `admin/config.py` | **Diperbarui** | Default `DB_HOST` dipindah ke `db2.ntp.id` |
| `connector/db.py` | **Diperbarui** | Peringatan database tidak tersambung, cadangan JSON mengenali kartu RFID, `commit` eksplisit |
| `connector/connector.py` | **Diperbarui** | Pemeriksaan koneksi database saat service dijalankan |
| `admin/db.py` | **Diperbarui** | Peringatan database tidak tersambung, logger disatukan ke `admin.log`, `commit` eksplisit |
| `admin/admin.py` | **Diperbarui** | Pemeriksaan koneksi database saat service dijalankan |
| `absen/capture.py` | **Diperbarui** | Pemulihan scancode angka standar untuk reader RFID, batas 6 digit buffer reader dilepas |
| `absen/static/app.js` | **Diperbarui** | Input NIK terkunci Numpad samping, maksimal 6 digit |
| `absen/static/index.html` | **Diperbarui** | `maxlength="6"`, teks footer, cache buster `v=36` |
| `README.md` | **Diperbarui** | Ditulis ulang sesuai arsitektur 3 service saat ini (menghapus referensi file lama yang sudah tidak ada) |
| `laporan_mingguan/` | **Baru** | Folder dokumentasi laporan mingguan dan konteks proyek |
| `laporan_mingguan/konteks_projek_handover.md` | **Diperbarui** | Panduan venv tanpa `sudo` dan troubleshooting database |
| `laporan_mingguan/laporan_mingguan_ke_7.md` | **Baru** | Dokumentasi laporan progres mingguan Minggu Ke-7 |

---

## 10. Prosedur Pembaruan & Pengoperasian di Debian Linux

```bash
# 1. Menarik update terbaru dari repositori GitHub
cd /home/debian/www/attendance
git pull origin main

# 2. (Sekali saja) Pastikan pymysql terpasang di venv
venv/bin/python -c "import pymysql; print('pymysql OK')"

# 3. Restart seluruh service (Tanpa sudo)
pkill -9 -f "connector.py" ; pkill -9 -f "capture.py" ; pkill -9 -f "admin.py"
nohup /home/debian/www/attendance/venv/bin/python connector.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python absen/capture.py > /dev/null 2>&1 &
nohup /home/debian/www/attendance/venv/bin/python admin/admin.py > /dev/null 2>&1 &

# 4. Verifikasi koneksi database
curl -s http://127.0.0.1:8002/api/health
grep "Startup" connector/logs/connector.log admin/logs/admin.log | tail -n 4
```
