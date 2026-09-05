#!/usr/bin/env bash
# ==============================================================================
# Employee Attendance System - Task 18: Chromium Kiosk Launcher Script
# Launches full-screen dedicated kiosk browser on Debian with auto-allowed webcam
# ==============================================================================

# URL server kiosk lokal
KIOSK_URL="http://localhost:8000"

# Tunggu hingga server Python aktif merespons
echo "[Kiosk] Menunggu server Python di ${KIOSK_URL} aktif..."
until curl -s --head "${KIOSK_URL}" | grep "200 OK" > /dev/null; do
    sleep 1
done
echo "[Kiosk] Server terdeteksi aktif! Membuka Chromium Kiosk..."

# Matikan screen saver dan manajemen daya layar jika berjalan di X11
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Luncurkan Chromium dalam mode Kiosk penuh
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
    "${KIOSK_URL}"
