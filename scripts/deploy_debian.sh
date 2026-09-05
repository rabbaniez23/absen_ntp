#!/usr/bin/env bash
# ==============================================================================
# Employee Attendance System - Task 18: Debian Deployment Script
# Deploys application files, runs DB migration, and prepares production environment
# Target directory: /opt/employee-attendance
# Run with sudo: sudo bash deploy_debian.sh
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
echo "    DEPLOYING EMPLOYEE ATTENDANCE SYSTEM TO DEBIAN (/opt)"
echo "======================================================================"

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
if [ ! -d "${TARGET_DIR}/venv" ]; then
    python3 -m venv "${TARGET_DIR}/venv"
fi
"${TARGET_DIR}/venv/bin/pip" install --upgrade pip
"${TARGET_DIR}/venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt"

# 4. Impor Skema & Data Migrasi ke MariaDB Debian
echo "[4/6] Mengimpor skema tabel dan data ke MariaDB lokal..."
# Gunakan socket root lokal MariaDB Debian (tanpa password default di Linux)
mysql -e "CREATE DATABASE IF NOT EXISTS \`attendance_db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS 'attendance_user'@'localhost' IDENTIFIED BY 'attendance_secure_pass123';"
mysql -e "GRANT ALL PRIVILEGES ON \`attendance_db\`.* TO 'attendance_user'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Eksekusi DDL & Data awal
mysql attendance_db < "${TARGET_DIR}/schema.sql"
if [ -f "${TARGET_DIR}/import_data.sql" ]; then
    mysql attendance_db < "${TARGET_DIR}/import_data.sql"
    echo "  -> Data awal berhasil diimpor ke MariaDB."
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

echo "======================================================================"
echo "  DEPLOYMENT SELESAI DENGAN SUKSES!"
echo "  Untuk menjalankan server di Debian:"
echo "    sudo -u attendance ${TARGET_DIR}/venv/bin/python3 ${TARGET_DIR}/server.py"
echo "======================================================================"
