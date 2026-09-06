#!/usr/bin/env bash
# ==============================================================================
# Skrip Peluncur Kiosk Sistem Presensi Karyawan
# Membuka peramban layar penuh otomatis dengan izin akses kamera aktif
# ==============================================================================

# URL server presensi lokal
SERVER_URL="http://localhost:8000"

# Tunggu hingga server Python aktif merespons
echo "[absen_ntp] Menunggu server Python di ${SERVER_URL} aktif..."
until curl -s --head "${SERVER_URL}" | grep "200 OK" > /dev/null; do
    sleep 1
done
echo "[absen_ntp] Server terdeteksi aktif! Membuka browser absen_ntp..."

# Matikan screen saver dan manajemen daya layar jika berjalan di X11
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Luncurkan Chromium dalam mode fullscreen tanpa gangguan UI
chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-translate \
    --no-first-run \
    --fast \
    --fast-start \
    --disable-features=Translate \
    --autoplay-policy=no-user-gesture-required \
    --use-fake-ui-for-media-stream \
    --check-for-update-interval=31536000 \
    "${SERVER_URL}"
