-- ====================================================================
-- Skema Database Sistem Presensi Karyawan (MariaDB)
-- Database: attendance_db
-- Karakter & Collation: utf8mb4 / utf8mb4_unicode_ci
-- ====================================================================

-- 1. Buat database jika belum ada
CREATE DATABASE IF NOT EXISTS `attendance_db`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `attendance_db`;

-- --------------------------------------------------------------------
-- 2. Tabel: employees
-- Menyimpan data master karyawan dan pemetaan UID kartu RFID.
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `employees` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `employee_id` VARCHAR(50) NOT NULL UNIQUE COMMENT 'ID Karyawan, contoh: EMP001',
    `name` VARCHAR(100) NOT NULL COMMENT 'Nama lengkap karyawan',
    `rfid_uid` VARCHAR(50) DEFAULT NULL UNIQUE COMMENT 'UID kartu RFID dari scanner USB',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1: Aktif, 0: Nonaktif',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_employees_rfid` (`rfid_uid`),
    INDEX `idx_employees_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------------------
-- 3. Tabel: attendance
-- Menyimpan riwayat pencatatan presensi beserta path foto tangkapan webcam.
-- Relasi Foreign Key: employee_id merujuk ke employees.employee_id
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `attendance` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `employee_id` VARCHAR(50) NOT NULL COMMENT 'Relasi ke employees.employee_id',
    `captured_at` DATETIME NOT NULL COMMENT 'Waktu pengambilan foto presensi',
    `image_path` VARCHAR(255) NOT NULL COMMENT 'Path relatif file foto di disk',
    `attendance_status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'Status presensi, contoh: SUCCESS',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_attendance_employee`
        FOREIGN KEY (`employee_id`)
        REFERENCES `employees` (`employee_id`)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    INDEX `idx_attendance_emp_date` (`employee_id`, `captured_at`),
    INDEX `idx_attendance_captured_at` (`captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
