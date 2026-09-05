#!/usr/bin/env bash
# ==============================================================================
# Employee Attendance System - Task 19: Autostart Configuration Script
# Configures Systemd Service for Python Server and XDG Desktop Autostart for Kiosk
# Target OS: Debian Linux
# Run as root / with sudo: sudo bash setup_autostart.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="attendance-server.service"
DESKTOP_NAME="attendance-kiosk.desktop"
TARGET_DIR="/opt/employee-attendance"

echo "======================================================================"
echo "    CONFIGURING AUTOSTART SYSTEMD & DESKTOP KIOSK FOR DEBIAN"
echo "======================================================================"

# 1. Pastikan file service dan launch_kiosk ada di /opt/employee-attendance
echo "[1/4] Menyalin file service dan skrip peluncur kiosk..."
cp "${SCRIPT_DIR}/launch_kiosk.sh" "${TARGET_DIR}/" 2>/dev/null || true
chmod +x "${TARGET_DIR}/launch_kiosk.sh"
chown attendance:attendance "${TARGET_DIR}/launch_kiosk.sh"

# 2. Pasang Systemd Service
echo "[2/4] Memasang systemd service (${SERVICE_NAME})..."
cp "${SCRIPT_DIR}/${SERVICE_NAME}" /etc/systemd/system/
chmod 644 "/etc/systemd/system/${SERVICE_NAME}"

# Reload systemd daemon
systemctl daemon-reload

# Enable dan start service
echo "  -> Mengaktifkan service otomatis saat boot (systemctl enable)..."
systemctl enable "${SERVICE_NAME}"

echo "  -> Menjalankan service sekarang (systemctl start)..."
systemctl restart "${SERVICE_NAME}"

# 3. Konfigurasi Autostart Browser Kiosk di Desktop
echo "[3/4] Mengonfigurasi autostart browser Chromium Kiosk saat user login..."
# Buat direktori autostart global dan user
mkdir -p /etc/xdg/autostart
mkdir -p /home/attendance/.config/autostart

cp "${SCRIPT_DIR}/${DESKTOP_NAME}" /etc/xdg/autostart/
cp "${SCRIPT_DIR}/${DESKTOP_NAME}" /home/attendance/.config/autostart/

chown -R attendance:attendance /home/attendance/.config
chmod 644 /etc/xdg/autostart/"${DESKTOP_NAME}"
chmod 644 /home/attendance/.config/autostart/"${DESKTOP_NAME}"

# 4. Status Verifikasi
echo "[4/4] Memeriksa status systemd service..."
systemctl is-active --quiet "${SERVICE_NAME}" && echo "  -> [OK] ${SERVICE_NAME} BERJALAN AKTIF!" || echo "  -> [WARNING] Service belum berjalan, periksa: journalctl -u ${SERVICE_NAME}"

echo "======================================================================"
echo "  AUTOSTART BERHASIL DIKONFIGURASI!"
echo "  Alur Booting Mesin Kiosk:"
echo "    1. Debian Boot -> MariaDB aktif -> attendance-server.service aktif"
echo "    2. Desktop Login -> Chromium Kiosk terbuka otomatis di http://localhost:8000"
echo "======================================================================"
