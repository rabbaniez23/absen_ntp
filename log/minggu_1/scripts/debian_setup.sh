#!/usr/bin/env bash
# ==============================================================================
# Skrip Persiapan & Instalasi Lingkungan Sistem Presensi di Debian/Ubuntu
# Target OS: Debian 11 / Debian 12 / Ubuntu Server (Bare-metal / VM - Non-Docker)
# Menyiapkan Apache 2, MariaDB, Python 3 venv, dan izin hardware
# Jalankan sebagai root atau dengan sudo: sudo bash debian_setup.sh
# ==============================================================================

set -e

echo "======================================================================"
echo "      PERSIAPAN SISTEM DEBIAN UNTUK SISTEM PRESENSI KARYAWAN"
echo "======================================================================"

# 1. Update Repository dan Paket Sistem
echo "[1/8] Memperbarui repositori paket Debian (apt update)..."
apt update -y
apt upgrade -y

# 2. Install Dependensi (Python 3, MariaDB, Apache 2, OpenSSH, v4l-utils)
echo "[2/8] Menginstal Python 3, MariaDB Server, Apache 2, dan OpenSSH..."
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    mariadb-server \
    mariadb-client \
    apache2 \
    openssh-server \
    v4l-utils \
    curl \
    git \
    ufw

# 3. Pengaturan User Sistem 'debian'
echo "[3/8] Mengonfigurasi hak akses user 'debian'..."
if id "debian" &>/dev/null; then
    echo "  -> User 'debian' terdeteksi di sistem."
else
    useradd -m -s /bin/bash debian
    echo "  -> User 'debian' berhasil dibuat."
fi

# Tambahkan user debian ke group hardware (video untuk webcam, dialout untuk RFID)
echo "  -> Menambahkan hak akses hardware (video, dialout) ke user 'debian'..."
usermod -a -G video,dialout debian 2>/dev/null || true

# 4. Direktori Aplikasi
PROJECT_DIR="/home/debian/www/attendance"
echo "[4/8] Menyiapkan direktori aplikasi di ${PROJECT_DIR}..."
mkdir -p "${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}/captures"
mkdir -p "${PROJECT_DIR}/logs"
mkdir -p "${PROJECT_DIR}/data"

# Hak akses direktori
chown -R debian:debian "${PROJECT_DIR}" 2>/dev/null || true
chmod -R 755 "${PROJECT_DIR}"
chmod -R 775 "${PROJECT_DIR}/captures"
chmod -R 775 "${PROJECT_DIR}/logs"
chmod -R 775 "${PROJECT_DIR}/data"

# 5. Konfigurasi Layanan MariaDB
echo "[5/8] Mengonfigurasi dan menyalakan layanan MariaDB..."
systemctl enable mariadb
systemctl start mariadb

DB_NAME="attendance_db"
DB_USER="debian"
DB_PASS="dreizehn"

echo "  -> Menyiapkan database dan kredensial user MariaDB (${DB_USER})..."
mysql -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';"
mysql -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# 6. Python Virtual Environment
echo "[6/8] Menyiapkan Python Virtual Environment (venv)..."
VENV_DIR="${PROJECT_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

# Pasang PyMySQL di dalam venv
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install pymysql==1.2.0
chown -R debian:debian "${VENV_DIR}" 2>/dev/null || true

# 7. Konfigurasi Firewall UFW & Apache 2
echo "[7/8] Mengonfigurasi firewall UFW dan modul Apache 2..."
systemctl enable ssh
systemctl start ssh

# Aktifkan modul proxy Apache 2
a2enmod proxy proxy_http headers 2>/dev/null || true

ufw allow 22/tcp comment "SSH Remote Management"
ufw allow 80/tcp comment "Apache 2 Web Server"
ufw allow 8000/tcp comment "Attendance absen_ntp Web Server"
echo "y" | ufw enable || true

# 8. Pemeriksaan Kamera & Hardware
echo "[8/8] Memeriksa ketersediaan perangkat kamera USB..."
if ls /dev/video* 1> /dev/null 2>&1; then
    echo "  -> Kamera terdeteksi di sistem:"
    ls -l /dev/video*
else
    echo "  [PERINGATAN] Belum ada webcam USB tercolok ke /dev/video*. Hubungkan webcam USB nanti."
fi

echo "======================================================================"
echo "  PERSIAPAN DEBIAN SELESAI DENGAN SUKSES!"
echo "  - Direktori Aplikasi: ${PROJECT_DIR}"
echo "  - Pengguna Sistem: debian (Groups: video, dialout)"
echo "  - Database: ${DB_NAME} (User: ${DB_USER})"
echo "  - Port Terbuka: 22 (SSH), 80 (Apache), 8000 (Python)"
echo "======================================================================"
