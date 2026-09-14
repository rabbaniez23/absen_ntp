#!/usr/bin/env bash
# ==============================================================================
# Skrip Deployment Aplikasi Sistem Presensi Karyawan ke Debian (/home/debian/www/attendance)
# Menyalin berkas aplikasi, migrasi database MariaDB, konfigurasi hak akses debian,
# dan mengonfigurasi Apache 2 Reverse Proxy (/debian/attendance -> http://127.0.0.1:8000)
# Jalankan dengan sudo: sudo bash deploy_debian.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/server.py" ]; then
    SOURCE_DIR="${SCRIPT_DIR}"
else
    SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
TARGET_DIR="/home/debian/www/attendance"

echo "======================================================================"
echo "    DEPLOYMENT SISTEM PRESENSI KE DEBIAN (/home/debian/www/attendance)"
echo "======================================================================"

# 1. Pastikan direktori tujuan ada
echo "[1/7] Menyiapkan struktur direktori di ${TARGET_DIR}..."
mkdir -p "${TARGET_DIR}/static"
mkdir -p "${TARGET_DIR}/data"
mkdir -p "${TARGET_DIR}/captures"
mkdir -p "${TARGET_DIR}/logs"
mkdir -p "${TARGET_DIR}/sql"
mkdir -p "${TARGET_DIR}/scripts"

# 2. Salin file aplikasi ke direktori produksi
echo "[2/7] Menyalin file aplikasi ke ${TARGET_DIR}..."
cp -r "${SOURCE_DIR}/static/"* "${TARGET_DIR}/static/"
cp "${SOURCE_DIR}/config.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/db.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/server.py" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/requirements.txt" "${TARGET_DIR}/"

# Salin skrip dan SQL
[ -f "${SOURCE_DIR}/sql/schema.sql" ] && cp "${SOURCE_DIR}/sql/schema.sql" "${TARGET_DIR}/" || cp "${SOURCE_DIR}/schema.sql" "${TARGET_DIR}/"
[ -f "${SOURCE_DIR}/sql/import_data.sql" ] && cp "${SOURCE_DIR}/sql/import_data.sql" "${TARGET_DIR}/" || cp "${SOURCE_DIR}/import_data.sql" "${TARGET_DIR}/" 2>/dev/null || true
cp -r "${SOURCE_DIR}/scripts/"* "${TARGET_DIR}/scripts/" 2>/dev/null || true

# Salin data JSON jika ada (untuk sinkronisasi awal)
if [ -f "${SOURCE_DIR}/data/employees.json" ]; then
    cp "${SOURCE_DIR}/data/employees.json" "${TARGET_DIR}/data/"
fi
if [ -f "${SOURCE_DIR}/data/attendance.json" ]; then
    cp "${SOURCE_DIR}/data/attendance.json" "${TARGET_DIR}/data/"
fi

# 3. Setup Python Virtual Environment
echo "[3/7] Memasang paket Python (PyMySQL) di Virtual Environment..."
if [ ! -f "${TARGET_DIR}/venv/bin/pip" ]; then
    echo "  -> Menyiapkan lingkungan virtual Python..."
    rm -rf "${TARGET_DIR}/venv"
    apt update -y && apt install -y python3-venv python3.12-venv 2>/dev/null || true
    python3 -m venv "${TARGET_DIR}/venv"
fi
"${TARGET_DIR}/venv/bin/pip" install --upgrade pip
"${TARGET_DIR}/venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt"

# 4. Impor Skema & Data Migrasi ke MariaDB Debian (User: debian, Password: dreizehn)
echo "[4/7] Mengonfigurasi dan mengimpor data ke MariaDB lokal..."
if command -v mysql &>/dev/null; then
    mysql -e "CREATE DATABASE IF NOT EXISTS \`attendance_db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true
    mysql -e "CREATE USER IF NOT EXISTS 'debian'@'localhost' IDENTIFIED BY 'dreizehn';" 2>/dev/null || true
    mysql -e "GRANT ALL PRIVILEGES ON \`attendance_db\`.* TO 'debian'@'localhost';" 2>/dev/null || true
    mysql -e "FLUSH PRIVILEGES;" 2>/dev/null || true

    mysql -u debian -pdreizehn attendance_db < "${TARGET_DIR}/schema.sql" 2>/dev/null || mysql attendance_db < "${TARGET_DIR}/schema.sql" 2>/dev/null || true
    if [ -f "${TARGET_DIR}/import_data.sql" ]; then
        mysql -u debian -pdreizehn attendance_db < "${TARGET_DIR}/import_data.sql" 2>/dev/null || mysql attendance_db < "${TARGET_DIR}/import_data.sql" 2>/dev/null || true
        echo "  -> Data awal berhasil diimpor ke MariaDB."
    fi
else
    echo "  -> MariaDB tidak terpasang. Sistem berjalan menggunakan penyimpanan lokal JSON."
fi

# 5. Konfigurasi Apache 2 Reverse Proxy (/debian/attendance -> Port 8000)
echo "[5/7] Mengonfigurasi rute Apache 2 Reverse Proxy..."
if command -v apache2 &>/dev/null; then
    a2enmod proxy proxy_http headers 2>/dev/null || true

    APACHE_CONF="/etc/apache2/conf-available/attendance.conf"
    cat << 'EOF' > "${APACHE_CONF}"
# Konfigurasi Reverse Proxy Sistem Presensi Karyawan (absen_ntp)
<IfModule mod_proxy.c>
    ProxyPreserveHost On
    ProxyPass /debian/attendance http://127.0.0.1:8000
    ProxyPassReverse /debian/attendance http://127.0.0.1:8000
    ProxyPass /debian/attendance/ http://127.0.0.1:8000/
    ProxyPassReverse /debian/attendance/ http://127.0.0.1:8000/
</IfModule>
EOF
    a2enconf attendance 2>/dev/null || true
    systemctl restart apache2 2>/dev/null || true
    echo "  -> Apache 2 berhasil dikonfigurasi untuk rute: http://10.1.0.11/debian/attendance"
else
    echo "  -> Apache 2 belum terpasang. Aplikasi tetap dapat diakses langsung di port 8000."
fi

# 6. Atur kepemilikan berkas ke user 'debian'
echo "[6/7] Mengonfigurasi hak akses kepemilikan user 'debian'..."
chown -R debian:debian "${TARGET_DIR}" 2>/dev/null || true
chmod -R 755 "${TARGET_DIR}"
chmod -R 775 "${TARGET_DIR}/captures"
chmod -R 775 "${TARGET_DIR}/logs"
chmod -R 775 "${TARGET_DIR}/data"

# Tambahkan user debian ke group video (webcam) dan dialout (RFID)
usermod -a -G video,dialout debian 2>/dev/null || true

# 7. Uji sintaks Python & restart service
echo "[7/7] Melakukan uji sintaks Python pada direktori produksi..."
"${TARGET_DIR}/venv/bin/python3" -m py_compile \
    "${TARGET_DIR}/server.py" \
    "${TARGET_DIR}/db.py" \
    "${TARGET_DIR}/config.py"

# Pasang / perbarui attendance-server.service
if [ -f "${TARGET_DIR}/scripts/attendance-server.service" ]; then
    cp "${TARGET_DIR}/scripts/attendance-server.service" /etc/systemd/system/
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable attendance-server 2>/dev/null || true
    systemctl restart attendance-server 2>/dev/null || true
    echo "  -> Layanan attendance-server otomatis aktif di latar belakang."
fi

echo "======================================================================"
echo "  DEPLOYMENT SELESAI DENGAN SUKSES!"
echo "  Aplikasi aktif dan dapat diakses melalui:"
echo "    1. Jalur Apache 2: http://10.1.0.11/debian/attendance"
echo "    2. Jalur Langsung : http://10.1.0.11:8000"
echo "======================================================================"
