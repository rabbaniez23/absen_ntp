<?php
// Pengalihan otomatis dari Apache (/attendance) ke Terminal Kiosk Absen Port 8000
$host = $_SERVER['HTTP_HOST'] ?? '127.0.0.1';
// Hapus port bawaan jika ada di HTTP_HOST
if (strpos($host, ':') !== false) {
    $host = explode(':', $host)[0];
}
header("Location: http://" . $host . ":8000/");
exit;
