#!/bin/bash
# ==============================================================================
# Script Konfigurasi Hak Akses Dual RFID Reader di Linux Debian
# Reader 1: QinHeng Electronics (1a86:dd01) -> MASUK (IN)
# Reader 2: Sycreader SYC ID&IC (ffff:0035) -> KELUAR (OUT)
# ==============================================================================

echo "=== Menyiapkan Izin Akses Dual RFID Reader di Debian ==="

# 1. Tambahkan user saat ini ke group input (agar bisa membaca /dev/input/event*)
CURRENT_USER=$(whoami)
echo "[1/3] Menambahkan user '$CURRENT_USER' ke group 'input'..."
sudo usermod -a -G input "$CURRENT_USER"

# 2. Buat aturan udev otomatis untuk kedua reader
UDEV_RULE_PATH="/etc/udev/rules.d/99-rfid-readers.rules"
echo "[2/3] Membuat udev rule di $UDEV_RULE_PATH..."

sudo bash -c "cat << 'EOF' > $UDEV_RULE_PATH
# QinHeng Electronics RFID Reader (IN / 1)
SUBSYSTEM==\"input\", ATTRS{idVendor}==\"1a86\", ATTRS{idProduct}==\"dd01\", MODE=\"0666\", GROUP=\"input\"

# Sycreader SYC ID&IC USB Reader (OUT / 0)
SUBSYSTEM==\"input\", ATTRS{idVendor}==\"ffff\", ATTRS{idProduct}==\"0035\", MODE=\"0666\", GROUP=\"input\"
EOF"

# 3. Reload udev rule
echo "[3/3] Memperbarui dan menerapkan aturan udev..."
sudo udevadm control --reload-rules
sudo udevadm trigger

echo ""
echo "=== SELESAI ==="
echo "Hak akses perangkat RFID berhasil dikonfigurasi!"
echo "Catatan: Jika baru pertama kali menambahkan group 'input', silakan relogin terminal atau jalankan:"
echo "   newgrp input"
echo ""
echo "Cek deteksi reader dengan menjalankan:"
echo "   python3 absen/capture.py"
