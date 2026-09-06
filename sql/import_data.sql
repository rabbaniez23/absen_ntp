-- ====================================================================
-- Skrip Migrasi Data dari File JSON ke Database MariaDB
-- Aman dieksekusi berulang (idempoten dengan update duplicate key)
-- ====================================================================
USE `attendance_db`;

-- 1. Migrasi Data Karyawan
INSERT INTO `employees` (`employee_id`, `name`, `rfid_uid`, `is_active`) VALUES ('EMP001', 'Budi Santoso', '983746128', 1) ON DUPLICATE KEY UPDATE `name` = VALUES(`name`), `rfid_uid` = VALUES(`rfid_uid`);
INSERT INTO `employees` (`employee_id`, `name`, `rfid_uid`, `is_active`) VALUES ('EMP002', 'Andi Wijaya', '827364928', 1) ON DUPLICATE KEY UPDATE `name` = VALUES(`name`), `rfid_uid` = VALUES(`rfid_uid`);

-- 2. Migrasi Riwayat Presensi
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP001', '2026-09-05 22:31:55', 'captures/2026/09/05/EMP001_20260905_223155.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP002', '2026-09-05 22:32:54', 'captures/2026/09/05/EMP002_20260905_223254.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP002', '2026-09-05 22:33:59', 'captures/2026/09/05/EMP002_20260905_223359.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP001', '2026-09-05 23:00:49', 'captures/2026/09/05/EMP001_20260905_230049.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP001', '2026-09-05 23:43:37', 'captures/2026/09/05/EMP001_20260905_234337.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP001', '2026-09-05 23:45:22', 'captures/2026/09/05/EMP001_20260905_234522.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP002', '2026-09-05 23:45:22', 'captures/test_audit.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP001', '2026-09-05 23:53:11', 'captures/2026/09/05/EMP001_20260905_235311.png', 'SUCCESS');
INSERT INTO `attendance` (`employee_id`, `captured_at`, `image_path`, `attendance_status`) VALUES ('EMP002', '2026-09-05 23:53:11', 'captures/test_audit.png', 'SUCCESS');
