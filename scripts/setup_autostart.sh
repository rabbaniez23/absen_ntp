#!/usr/bin/env bash
# ==============================================================================
# Skrip Konfigurasi Layanan Background (Systemd Service)
# Mengatur agar server backend Python otomatis berjalan di latar belakang saat booting
# Target OS: Debian / Ubuntu / Linux Mint
# Jalankan sebagai root / sudo: sudo bash setup_autostart.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="attendance-server.service"
TARGET_DIR="/opt/employee-attendance"

echo "======================================================================"
echo "       KONFIGURASI LAYANAN LATAR BELAKANG SYSTEMD PRESENSI"
echo "======================================================================"

# 1. Pastikan user 'attendance' ada di sistem
if ! id "attendance" &>/dev/null; then
    echo "  -> Menyiapkan user sistem 'attendance'..."
    useradd -m -s /bin/bash attendance
    usermod -a -G video,dialout attendance 2>/dev/null || true
fi

# 2. Pasang berkas Systemd Service ke direktori sistem
echo "[1/3] Memasang konfigurasi systemd service (${SERVICE_NAME})..."
cp "${SCRIPT_DIR}/${SERVICE_NAME}" /etc/systemd/system/
chmod 644 "/etc/systemd/system/${SERVICE_NAME}"

# 3. Muat ulang daemon systemd dan aktifkan service
echo "[2/3] Mengaktifkan dan menyalakan service..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# 4. Verifikasi status service
echo "[3/3] Memeriksa status service..."
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "  -> [SUKSES] ${SERVICE_NAME} BERJALAN AKTIF DI LATAR BELAKANG!"
else
    echo "  -> [PERINGATAN] Service belum berjalan. Periksa log dengan perintah: journalctl -u ${SERVICE_NAME} -n 20"
fi

echo "======================================================================"
echo "  KONFIGURASI SELESAI!"
echo "  Server presensi sekarang otomatis menyala setiap kali komputer hidup."
echo "  Akses aplikasi melalui peramban: http://localhost:8000"
echo "======================================================================"
