#!/usr/bin/env bash
# ==============================================================================
# Employee Attendance System - absen_ntp Launcher Script
# Launches full-screen dedicated browser for absen_ntp with auto-allowed webcam
# ==============================================================================

# URL server absen_ntp lokal
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
