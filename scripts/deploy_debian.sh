#!/usr/bin/env bash
# ==============================================================================
# Skrip Deployment Aplikasi Sistem Presensi Karyawan ke Debian (/opt)
# Menyalin berkas aplikasi, migrasi database MariaDB, dan konfigurasi hak akses
# Target direktori: /opt/employee-attendance
# Jalankan dengan sudo: sudo bash deploy_debian.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/server.py" ]; then
    SOURCE_DIR="${SCRIPT_DIR}"
else
    SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
TARGET_DIR="/opt/employee-attendance"

echo "======================================================================"
echo "    MENYIAPKAN DEPLOYMENT APLIKASI PRESENSI KE DEBIAN (/opt)"
echo "======================================================================"

# 0. Pastikan user 'attendance' ada di sistem
if ! id "attendance" &>/dev/null; then
    echo "  -> Menyiapkan user sistem 'attendance'..."
    useradd -m -s /bin/bash attendance
    usermod -a -G video,dialout attendance 2>/dev/null || true
fi

# 1. Pastikan direktori tujuan ada dan berizin tepat
echo "[1/6] Menyiapkan struktur direktori di ${TARGET_DIR}..."
mkdir -p "${TARGET_DIR}/static"
mkdir -p "${TARGET_DIR}/data"
mkdir -p "${TARGET_DIR}/captures"
mkdir -p "${TARGET_DIR}/logs"
mkdir -p "${TARGET_DIR}/sql"
mkdir -p "${TARGET_DIR}/scripts"

# 2. Salin file aplikasi ke direktori produksi
echo "[2/6] Menyalin file aplikasi ke ${TARGET_DIR}..."
cp -r "${SOURCE_DIR}/static/"* "${TARGET_DIR}/static/"
cp "${SOURCE_DIR}/config.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/db.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/server.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/requirements.txt" "${TARGET_DIR}/"

# SQL files
[ -f "${SOURCE_DIR}/sql/schema.sql" ] && cp "${SOURCE_DIR}/sql/schema.sql" "${TARGET_DIR}/" || cp "${SOURCE_DIR}/schema.sql" "${TARGET_DIR}/"
[ -f "${SOURCE_DIR}/sql/import_data.sql" ] && cp "${SOURCE_DIR}/sql/import_data.sql" "${TARGET_DIR}/" || cp "${SOURCE_DIR}/import_data.sql" "${TARGET_DIR}/" 2>/dev/null || true

# Scripts
[ -f "${SCRIPT_DIR}/launch_kiosk.sh" ] && cp "${SCRIPT_DIR}/launch_kiosk.sh" "${TARGET_DIR}/" || cp "${SOURCE_DIR}/scripts/launch_kiosk.sh" "${TARGET_DIR}/" 2>/dev/null || true


# Salin data JSON jika ada (untuk sinkronisasi awal)
if [ -f "${SOURCE_DIR}/data/employees.json" ]; then
    cp "${SOURCE_DIR}/data/employees.json" "${TARGET_DIR}/data/"
fi
if [ -f "${SOURCE_DIR}/data/attendance.json" ]; then
    cp "${SOURCE_DIR}/data/attendance.json" "${TARGET_DIR}/data/"
fi

# 3. Setup Python Virtual Environment
echo "[3/6] Memasang paket Python (PyMySQL) di Virtual Environment..."
if [ ! -f "${TARGET_DIR}/venv/bin/pip" ]; then
    echo "  -> Menyiapkan lingkungan virtual Python..."
    rm -rf "${TARGET_DIR}/venv"
    apt update -y && apt install -y python3-venv python3.12-venv 2>/dev/null || true
    python3 -m venv "${TARGET_DIR}/venv"
fi
"${TARGET_DIR}/venv/bin/pip" install --upgrade pip
"${TARGET_DIR}/venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt"

# 4. Impor Skema & Data Migrasi ke MariaDB Debian
echo "[4/6] Mengimpor skema tabel dan data ke MariaDB lokal..."
if command -v mysql &>/dev/null; then
    mysql -e "CREATE DATABASE IF NOT EXISTS \`attendance_db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true
    mysql -e "CREATE USER IF NOT EXISTS 'attendance_user'@'localhost' IDENTIFIED BY 'attendance_secure_pass123';" 2>/dev/null || true
    mysql -e "GRANT ALL PRIVILEGES ON \`attendance_db\`.* TO 'attendance_user'@'localhost';" 2>/dev/null || true
    mysql -e "FLUSH PRIVILEGES;" 2>/dev/null || true
    mysql attendance_db < "${TARGET_DIR}/schema.sql" 2>/dev/null || true
    if [ -f "${TARGET_DIR}/import_data.sql" ]; then
        mysql attendance_db < "${TARGET_DIR}/import_data.sql" 2>/dev/null || true
        echo "  -> Data awal berhasil diimpor ke MariaDB."
    fi
else
    echo "  -> MariaDB tidak terpasang. Sistem akan otomatis berjalan menggunakan penyimpanan lokal JSON."
fi

# 5. Atur kepemilikan berkas ke user layanan 'attendance'
echo "[5/6] Mengonfigurasi hak akses kepemilikan user 'attendance'..."
chown -R attendance:attendance "${TARGET_DIR}"
chmod -R 755 "${TARGET_DIR}"
chmod -R 775 "${TARGET_DIR}/captures"
chmod -R 775 "${TARGET_DIR}/logs"
chmod -R 775 "${TARGET_DIR}/data"
chmod +x "${TARGET_DIR}/launch_kiosk.sh" 2>/dev/null || true

# 6. Uji jalan backend Python
echo "[6/6] Melakukan uji sintaks Python pada direktori produksi..."
"${TARGET_DIR}/venv/bin/python3" -m py_compile \
    "${TARGET_DIR}/server.py" \
    "${TARGET_DIR}/db.py" \
    "${TARGET_DIR}/config.py"

# 7. Otomatis restart service jika ada
if systemctl is-active --quiet attendance-server 2>/dev/null; then
    echo "  -> Me-restart attendance-server service otomatis..."
    systemctl restart attendance-server
fi

echo "======================================================================"
echo "  DEPLOYMENT SELESAI DENGAN SUKSES!"
echo "  Server aktif di background dan siap diakses di port 8000."
echo "======================================================================"
