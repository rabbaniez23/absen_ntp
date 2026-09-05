#!/usr/bin/env bash
# ==============================================================================
# Employee Attendance System - Task 17: Debian Preparation & Setup Script
# Target OS: Debian 11 / Debian 12 / Ubuntu Server (Bare-metal / VM - No Docker)
# Run as root or with sudo: sudo bash debian_setup.sh
# ==============================================================================

set -e

echo "======================================================================"
echo "    PREPARING DEBIAN ENVIRONMENT FOR EMPLOYEE ATTENDANCE SYSTEM"
echo "======================================================================"

# 1. Update Repository and System Packages
echo "[1/8] Memperbarui repositori paket Debian (apt update)..."
apt update -y
apt upgrade -y

# 2. Install Required Dependencies (Python 3, MariaDB, OpenSSH, Chromium)
echo "[2/8] Menginstal Python 3, MariaDB Server, OpenSSH, dan Chromium Browser..."
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    mariadb-server \
    mariadb-client \
    openssh-server \
    chromium \
    v4l-utils \
    curl \
    git \
    ufw

# 3. Dedicated Service User Setup
echo "[3/8] Menyiapkan user layanan terisolasi 'attendance'..."
if id "attendance" &>/dev/null; then
    echo "  -> User 'attendance' sudah ada."
else
    useradd -m -s /bin/bash attendance
    echo "  -> User 'attendance' berhasil dibuat."
fi

# Add user to hardware device groups (video for webcam, dialout for USB RFID)
echo "  -> Menambahkan hak akses hardware (video, dialout) ke user 'attendance'..."
usermod -a -G video,dialout attendance

# 4. Project Directory & Permissions Setup
PROJECT_DIR="/opt/employee-attendance"
echo "[4/8] Menyiapkan direktori aplikasi di ${PROJECT_DIR}..."
mkdir -p "${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}/captures"
mkdir -p "${PROJECT_DIR}/logs"
mkdir -p "${PROJECT_DIR}/data"

# Set ownership and permissions
chown -R attendance:attendance "${PROJECT_DIR}"
chmod -R 755 "${PROJECT_DIR}"
# Ensure write permissions for captures and logs
chmod -R 775 "${PROJECT_DIR}/captures"
chmod -R 775 "${PROJECT_DIR}/logs"
chmod -R 775 "${PROJECT_DIR}/data"

# 5. MariaDB Service Configuration & Hardening
echo "[5/8] Mengonfigurasi dan menyalakan layanan MariaDB..."
systemctl enable mariadb
systemctl start mariadb

DB_NAME="attendance_db"
DB_USER="attendance_user"
DB_PASS="attendance_secure_pass123"

echo "  -> Membuat database dan user MariaDB..."
mysql -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';"
mysql -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# 6. Python Virtual Environment & Driver Installation
echo "[6/8] Menyiapkan Python Virtual Environment (venv)..."
VENV_DIR="${PROJECT_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

# Install PyMySQL inside venv
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install pymysql==1.2.0
chown -R attendance:attendance "${VENV_DIR}"

# 7. Firewall & SSH Management
echo "[7/8] Mengonfigurasi firewall UFW dan akses SSH..."
systemctl enable ssh
systemctl start ssh

ufw allow 22/tcp comment "SSH Remote Management"
ufw allow 8000/tcp comment "Attendance Kiosk Web Server"
# Enable UFW if not enabled (promptless)
echo "y" | ufw enable || true

# 8. Camera & Hardware Verification
echo "[8/8] Memeriksa ketersediaan perangkat kamera USB..."
if ls /dev/video* 1> /dev/null 2>&1; then
    echo "  -> Kamera terdeteksi di sistem:"
    ls -l /dev/video*
else
    echo "  [PERINGATAN] Belum ada perangkat webcam USB tercolok ke /dev/video*. Hubungkan webcam USB nanti."
fi

echo "======================================================================"
echo "  PERSIAPAN DEBIAN SELESAI DENGAN SUKSES!"
echo "  - Direktori Aplikasi: ${PROJECT_DIR}"
echo "  - Service User: attendance (Groups: video, dialout)"
echo "  - Database: ${DB_NAME} (User: ${DB_USER})"
echo "  - Python Venv: ${VENV_DIR}"
echo "======================================================================"
