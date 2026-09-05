-- ====================================================================
-- Employee Attendance System - Task 14: MariaDB Database Schema
-- Database: attendance_db
-- Collation: utf8mb4_unicode_ci (Supports full Unicode & high performance)
-- ====================================================================

-- 1. Create Database if not exists
CREATE DATABASE IF NOT EXISTS `attendance_db`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `attendance_db`;

-- --------------------------------------------------------------------
-- 2. Table: employees
-- Stores master data for all registered employees and RFID card mappings.
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `employees` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `employee_id` VARCHAR(50) NOT NULL UNIQUE COMMENT 'Unique business identifier, e.g. EMP001',
    `name` VARCHAR(100) NOT NULL COMMENT 'Full name of employee',
    `rfid_uid` VARCHAR(50) DEFAULT NULL UNIQUE COMMENT 'RFID card UID from USB Reader',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1: Active, 0: Inactive/Terminated',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_employees_rfid` (`rfid_uid`),
    INDEX `idx_employees_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------------------
-- 3. Table: attendance
-- Stores historical log of biometric attendance events and image paths.
-- Foreign Key: employee_id references employees(employee_id)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `attendance` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `employee_id` VARCHAR(50) NOT NULL COMMENT 'Foreign key to employees.employee_id',
    `captured_at` DATETIME NOT NULL COMMENT 'Exact timestamp of camera snapshot',
    `image_path` VARCHAR(255) NOT NULL COMMENT 'Relative filesystem path to captured PNG',
    `attendance_status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'Attendance status, e.g. SUCCESS',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_attendance_employee`
        FOREIGN KEY (`employee_id`)
        REFERENCES `employees` (`employee_id`)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    INDEX `idx_attendance_emp_date` (`employee_id`, `captured_at`),
    INDEX `idx_attendance_captured_at` (`captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
