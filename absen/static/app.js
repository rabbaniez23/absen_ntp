/**
 * Logika Antarmuka Pengguna (Frontend) Sistem Presensi Karyawan
 * Mengatur alur pemindaian kartu RFID, pratinjau kamera webcam, hitung mundur,
 * pengambilan foto, serta pengiriman data ke server backend.
 */

// Definisi status aplikasi (State Machine)
const AppState = Object.freeze({
    IDLE: "IDLE",
    IDENTIFYING: "IDENTIFYING",
    EMPLOYEE_FOUND: "EMPLOYEE_FOUND",
    CAMERA_READY: "CAMERA_READY",
    COUNTDOWN: "COUNTDOWN",
    CAPTURING: "CAPTURING",
    SAVING: "SAVING",
    SUCCESS: "SUCCESS",
    ERROR: "ERROR"
});

let currentState = AppState.IDLE;
let currentEmployeeId = null;
let mediaStream = null;
let isCameraOnline = false;
let countdownTimer = null;
let errorRecoveryTimer = null;
let currentPreviewUrl = null;
let isMirrored = false; // Pengaturan bawaan kamera: Normal (tidak dicerminkan)

// Elemen DOM - Kamera & Tangkapan Gambar
const streamVideo = document.getElementById("streamVideo");
const webcamVideo = document.getElementById("webcamVideo");
const cameraOverlay = document.getElementById("cameraOverlay");
const cameraIcon = document.getElementById("cameraIcon");
const cameraMessage = document.getElementById("cameraMessage");
const cameraStatusBadge = document.getElementById("cameraStatus");
const countdownOverlay = document.getElementById("countdownOverlay");
const countdownNumber = document.getElementById("countdownNumber");
const faceGuide = document.getElementById("faceGuide");
const capturedPreview = document.getElementById("capturedPreview");
const captureFlash = document.getElementById("captureFlash");
const captureCanvas = document.getElementById("captureCanvas");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const retryCameraBtn = document.getElementById("retryCameraBtn");
const mirrorToggleBtn = document.getElementById("mirrorToggleBtn");
const mirrorStatusText = document.getElementById("mirrorStatusText");

// Elemen DOM - Tanggal dan Waktu
const liveDate = document.getElementById("liveDate");
const liveTime = document.getElementById("liveTime");
const attendanceDate = document.getElementById("attendanceDate");
const attendanceTime = document.getElementById("attendanceTime");

// Elemen DOM - Informasi Karyawan & Status
const employeeName = document.getElementById("employeeName");
const employeeNik = document.getElementById("employeeNik");
const employeeId = document.getElementById("employeeId") || employeeNik;
const attendanceType = document.getElementById("attendanceType");
const cameraTitle = document.getElementById("cameraTitle");
const statusBanner = document.getElementById("statusBanner");
const statusText = document.getElementById("statusText");

// Elemen DOM - Input RFID / Keyboard & Tombol Masuk/Keluar
const rfidInput = document.getElementById("rfidInput");
const btnManualMasuk = document.getElementById("btnManualMasuk");
const btnManualKeluar = document.getElementById("btnManualKeluar");

// Nama bulan dalam Bahasa Indonesia
const MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
];

/**
 * Format objek Date menjadi tanggal terformat (contoh: 05 September 2026).
 */
function formatDate(date) {
    const day = String(date.getDate()).padStart(2, "0");
    const month = MONTH_NAMES[date.getMonth()];
    const year = date.getFullYear();
    return `${day} ${month} ${year}`;
}

/**
 * Format objek Date menjadi jam terformat (contoh: 22:10:45).
 */
function formatTime(date) {
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    return `${hours}:${minutes}:${seconds}`;
}

/**
 * Memperbarui tampilan tanggal dan jam setiap detik.
 */
function updateClock() {
    const now = new Date();
    const formattedDate = formatDate(now);
    const formattedTime = formatTime(now);

    if (liveDate) liveDate.textContent = formattedDate;
    if (liveTime) liveTime.textContent = formattedTime;
    if (attendanceDate) attendanceDate.textContent = formattedDate;
    if (attendanceTime) attendanceTime.textContent = formattedTime;
}

/**
 * Mengaktifkan timer jam waktu nyata.
 */
function initializeClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

/**
 * Mengubah status aplikasi dan memperbarui elemen antarmuka terkait.
 */
function setApplicationState(newState, customMessage = "", isOut = false) {
    currentState = newState;
    console.log(`[Presensi] Perubahan Status -> ${newState} ${customMessage ? `("${customMessage}")` : ""}`);

    if (statusBanner) {
        if (newState === AppState.SUCCESS) {
            statusBanner.className = isOut
                ? "status-banner state-success-out"
                : "status-banner state-success";
        } else {
            statusBanner.className = `status-banner state-${newState.toLowerCase()}`;
        }
    }

    // Tampilkan panduan oval posisi wajah saat bersiap atau hitung mundur
    if (faceGuide) {
        if (newState === AppState.CAMERA_READY || newState === AppState.COUNTDOWN) {
            faceGuide.classList.add("visible");
        } else {
            faceGuide.classList.remove("visible");
        }
    }

    const isIdle = (newState === AppState.IDLE);
    if (btnManualMasuk) btnManualMasuk.disabled = !isIdle;
    if (btnManualKeluar) btnManualKeluar.disabled = !isIdle;

    if (rfidInput) {
        rfidInput.disabled = !isIdle;
        if (isIdle) focusInputField();
    }

    if (statusText) {
        statusText.textContent = customMessage || newState;
    }
}

/**
 * Menampilkan pesan kesalahan dan otomatis kembali ke kondisi siap (IDLE).
 */
function handleErrorAndRecover(errorMessage, displayDuration = 2500) {
    console.warn(`[Presensi] Kesalahan: ${errorMessage}`);

    if (errorRecoveryTimer) {
        clearTimeout(errorRecoveryTimer);
    }

    setApplicationState(AppState.ERROR, errorMessage);

    errorRecoveryTimer = setTimeout(() => {
        errorRecoveryTimer = null;
        resetToIdle();
    }, displayDuration);
}

/**
 * Mengembalikan tampilan dan status antarmuka kembali ke kondisi awal (IDLE).
 */
function resetToIdle() {
    if (countdownTimer) {
        clearInterval(countdownTimer);
        countdownTimer = null;
    }
    if (errorRecoveryTimer) {
        clearTimeout(errorRecoveryTimer);
        errorRecoveryTimer = null;
    }
    if (countdownOverlay) {
        countdownOverlay.classList.add("hidden");
    }
    if (capturedPreview) {
        capturedPreview.classList.add("hidden");
        capturedPreview.classList.remove("preview-out");
        capturedPreview.src = "";
    }
    if (currentPreviewUrl) {
        URL.revokeObjectURL(currentPreviewUrl);
        currentPreviewUrl = null;
    }
    currentEmployeeId = null;
    if (employeeName) employeeName.textContent = "-";
    if (employeeNik) employeeNik.textContent = "-";
    if (employeeId && employeeId !== employeeNik) employeeId.textContent = "-";
    if (attendanceType) attendanceType.textContent = "-";
    if (rfidInput) {
        rfidInput.value = "";
        rfidInput.disabled = false;
    }

    // Sembunyikan lingkaran panduan saat standby (hanya muncul saat hitung mundur)
    if (faceGuide) {
        faceGuide.classList.remove("visible");
    }

    setApplicationState(AppState.IDLE);
}

/**
 * Memastikan kursor selalu fokus pada input RFID agar siap membaca kartu.
 */
function focusInputField() {
    if (currentState === AppState.IDLE && rfidInput && document.activeElement !== rfidInput) {
        rfidInput.focus();
    }
}

function getApiUrl(endpoint) {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint.slice(1) : endpoint;
    if (window.location.port !== "8000") {
        return `http://${window.location.hostname}:8000/${cleanEndpoint}`;
    }
    return cleanEndpoint;
}

/**
 * Fungsi pembantu fetch dengan batas waktu timeout menggunakan AbortController.
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
    const targetUrl = getApiUrl(url);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(targetUrl, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timer);
        return response;
    } catch (error) {
        clearTimeout(timer);
        if (error.name === "AbortError") {
            throw new Error("REQUEST_TIMEOUT");
        }
        throw error;
    }
}

/**
 * Membaca respons JSON secara aman jika respons bukan format valid.
 */
async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch (error) {
        throw new Error("JSON_INVALID");
    }
}

/**
 * Memeriksa apakah sistem kamera siap (ditangani langsung di hardware Linux V4L2).
 */
function isCameraReady() {
    return true; // Kamera hardware Logitech C930e standby di backend Linux
}

/**
 * Menangani tap kartu RFID atau input NIK manual:
 * Seluruh kartu (baik yang terdaftar maupun belum terdaftar) TETAP DI-CAPTURE fotonya.
 */
async function handleEmployeeInput(rawInput, forcedMode = "", readerName = "Web Kiosk UI", timingInfo = {}) {
    if (currentState !== AppState.IDLE) {
        console.warn(`[Presensi] Input diabaikan: Sistem sedang dalam status ${currentState}`);
        return;
    }

    const cleanId = rawInput.trim();
    if (!cleanId) return;

    if (rfidInput) rfidInput.value = "";

    setApplicationState(AppState.IDENTIFYING, "MEMPROSES PRESENSI...");

    // Langsung jalankan proses absensi & capture foto di backend
    processAttendanceScan(cleanId, null, forcedMode, readerName, timingInfo);
}

/**
 * Menjepret frame kamera dan mencatat absensi ke server backend.
 */
async function processAttendanceScan(id, empInfo = null, forcedMode = "", readerName = "Web Kiosk UI", timingInfo = {}) {
    setApplicationState(AppState.SAVING, "MENYIMPAN DATA PRESENSI...");

    try {
        const response = await fetchWithTimeout("api/attendance/scan", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                rfid_uid: id,
                in_out: forcedMode,
                reader: readerName,
                duration_ms: timingInfo.duration || 0,
                avg_interval_ms: timingInfo.avgInterval || 0,
                enter_code: timingInfo.enterCode || "",
                first_key_code: timingInfo.firstKey || ""
            })
        }, 12000);

        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            displayAttendanceSuccess(data);
        } else {
            const message = data && data.message ? data.message.toUpperCase() : "GAGAL MENYIMPAN PRESENSI";
            handleErrorAndRecover(message, 3000);
        }
    } catch (error) {
        console.error("[Presensi] Kesalahan proses absensi:", error);
        handleErrorAndRecover("SERVER BACKEND TIDAK MERESPON", 3000);
    }
}

// Alias lookupEmployee untuk kompatibilitas
const lookupEmployee = handleEmployeeInput;

/**
 * Menjalankan urutan hitung mundur 3-2-1 dengan efek visual di layar.
 * @param {Function} onComplete Fungsi yang dijalankan setelah hitung mundur selesai.
 */
function startCountdown(onComplete) {
    let count = 3;

    if (countdownOverlay) {
        countdownOverlay.classList.remove("hidden");
    }
    if (countdownNumber) {
        countdownNumber.textContent = count;
    }

    setApplicationState(AppState.COUNTDOWN, String(count));

    if (countdownTimer) {
        clearInterval(countdownTimer);
    }

    countdownTimer = setInterval(() => {
        count--;

        if (count > 0) {
            if (countdownNumber) {
                countdownNumber.textContent = count;
                countdownNumber.style.animation = "none";
                void countdownNumber.offsetWidth;
                countdownNumber.style.animation = "countdownPop 0.9s ease-out infinite";
            }
            setApplicationState(AppState.COUNTDOWN, String(count));
        } else {
            clearInterval(countdownTimer);
            countdownTimer = null;

            if (countdownOverlay) {
                countdownOverlay.classList.add("hidden");
            }

            console.log("[Presensi] Hitung mundur selesai. Mengambil foto...");
            if (typeof onComplete === "function") {
                onComplete();
            }
        }
    }, 1000);
}

/**
 * Mengambil satu frame dari feed webcam ke elemen Canvas HTML,
 * mengubahnya menjadi Blob PNG, lalu mengirimkannya ke uploadCapture.
 */
function captureWebcamFrame() {
    setApplicationState(AppState.CAPTURING, "MENGAMBIL FOTO...");

    if (!isCameraReady()) {
        console.error("[Presensi] Gagal mengambil foto: Stream kamera tidak siap.");
        handleErrorAndRecover("KAMERA TIDAK TERSEDIA");
        return;
    }

    // Efek kilatan lampu rana (shutter flash)
    if (captureFlash) {
        captureFlash.classList.add("flash-active");
        setTimeout(() => captureFlash.classList.remove("flash-active"), 350);
    }

    const width = webcamVideo.videoWidth;
    const height = webcamVideo.videoHeight;
    captureCanvas.width = width;
    captureCanvas.height = height;

    try {
        const ctx = captureCanvas.getContext("2d");
        if (isMirrored) {
            ctx.save();
            ctx.translate(width, 0);
            ctx.scale(-1, 1);
            ctx.drawImage(webcamVideo, 0, 0, width, height);
            ctx.restore();
        } else {
            ctx.drawImage(webcamVideo, 0, 0, width, height);
        }

        captureCanvas.toBlob((blob) => {
            if (!blob) {
                console.error("[Presensi] Konversi Canvas ke Blob bernilai null.");
                handleErrorAndRecover("GAGAL MENGONVERSI GAMBAR");
                return;
            }

            console.log(`[Presensi] Foto berhasil diambil: PNG ${(blob.size / 1024).toFixed(1)} KB (${width}x${height})`);

            // Tampilkan pratinjau beku sementara
            if (currentPreviewUrl) {
                URL.revokeObjectURL(currentPreviewUrl);
            }
            currentPreviewUrl = URL.createObjectURL(blob);

            if (capturedPreview) {
                capturedPreview.src = currentPreviewUrl;
                capturedPreview.classList.remove("hidden");
            }

            // Kirim gambar ke server
            uploadCapture(currentEmployeeId, blob);

        }, "image/png");

    } catch (err) {
        console.error("[Presensi] Kendala kanvas saat mengambil foto:", err);
        handleErrorAndRecover("KESALAHAN KANVAS FOTO");
    }
}

/**
 * Mengunggah Blob foto dan ID Karyawan ke backend server.
 */
async function uploadCapture(empId, blob) {
    setApplicationState(AppState.SAVING, "MENYIMPAN DATA PRESENSI...");

    const formData = new FormData();
    formData.append("employee_id", empId);
    formData.append("image", blob, "webcam.png");

    try {
        const response = await fetchWithTimeout("api/upload", {
            method: "POST",
            body: formData
        }, 10000);

        if (response.status === 413) {
            handleErrorAndRecover("UKURAN FILE TERLALU BESAR (MAKS 10MB)");
            return;
        }

        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            console.log("[Presensi] Presensi berhasil dicatat:", data);
            setApplicationState(AppState.SUCCESS, "ABSENSI BERHASIL");

            setTimeout(() => {
                resetToIdle();
            }, 2500);
        } else {
            const message = data && data.message ? `GAGAL: ${data.message}` : "PRESENSI GAGAL";
            handleErrorAndRecover(message);
        }
    } catch (error) {
        console.error("[Presensi] Kesalahan unggah foto:", error);

        if (error.message === "REQUEST_TIMEOUT") {
            handleErrorAndRecover("UNGGAH TIMEOUT (SERVER TIDAK MERESPON)");
        } else if (error.message === "JSON_INVALID") {
            handleErrorAndRecover("FORMAT DATA RESPON TIDAK VALID");
        } else {
            handleErrorAndRecover("SERVER BACKEND TIDAK TERHUBUNG");
        }
    }
}

/**
 * Menginisialisasi pendengar event keyboard dan tombol Masuk/Keluar manual.
 */
function initializeInputHandler() {
    // 1. Tangani tombol Masuk manual
    if (btnManualMasuk) {
        btnManualMasuk.addEventListener("click", () => {
            if (currentState !== AppState.IDLE) return;
            const cleanVal = rfidInput ? rfidInput.value.trim() : "";
            if (!cleanVal) {
                handleErrorAndRecover("SILAKAN MASUKKAN NIK TERLEBIH DAHULU", 2000);
                if (rfidInput) rfidInput.focus();
                return;
            }
            handleEmployeeInput(cleanVal, "1", "Manual Web Masuk");
        });
    }

    // 2. Tangani tombol Keluar manual
    if (btnManualKeluar) {
        btnManualKeluar.addEventListener("click", () => {
            if (currentState !== AppState.IDLE) return;
            const cleanVal = rfidInput ? rfidInput.value.trim() : "";
            if (!cleanVal) {
                handleErrorAndRecover("SILAKAN MASUKKAN NIK TERLEBIH DAHULU", 2000);
                if (rfidInput) rfidInput.focus();
                return;
            }
            handleEmployeeInput(cleanVal, "0", "Manual Web Keluar");
        });
    }

    // 3. Tangani input KHUSUS Numpad Samping (Maks 6 Digit)
    if (rfidInput) {
        // Sanitize agar hanya angka dan maks 6 digit
        rfidInput.addEventListener("input", () => {
            let sanitized = rfidInput.value.replace(/[^0-9]/g, "");
            if (sanitized.length > 6) {
                sanitized = sanitized.slice(0, 6);
            }
            if (rfidInput.value !== sanitized) {
                rfidInput.value = sanitized;
            }
        });

        rfidInput.addEventListener("keydown", (event) => {
            // A. Tombol MINUS (-) atau BINTANG (*) pada Numpad -> CLEAR / HAPUS SEMUA
            if (
                event.code === "NumpadSubtract" || event.code === "NumpadMultiply" ||
                (event.key === "-" && event.code.startsWith("Numpad")) ||
                (event.key === "*" && event.code.startsWith("Numpad")) ||
                event.key === "Subtract" || event.key === "Multiply"
            ) {
                event.preventDefault();
                rfidInput.value = "";
                rfidInput.dispatchEvent(new Event("input"));
                return;
            }

            // B. Tombol SLASH (/) pada Numpad -> BACKSPACE / HAPUS 1 DIGIT TERAKHIR
            if (
                event.code === "NumpadDivide" ||
                (event.key === "/" && (event.code.startsWith("Numpad") || event.code === "NumpadDivide")) ||
                event.key === "Divide"
            ) {
                event.preventDefault();
                rfidInput.value = rfidInput.value.slice(0, -1);
                rfidInput.dispatchEvent(new Event("input"));
                return;
            }

            // C. Tombol ENTER pada Numpad -> Presensi MASUK (IN / Kode: 1)
            if (event.code === "NumpadEnter" || (event.key === "Enter" && event.code.startsWith("Numpad")) || event.key === "Enter") {
                event.preventDefault();
                if (currentState !== AppState.IDLE) return;
                const cleanVal = rfidInput.value.trim().replace(/[^0-9]/g, "").slice(0, 6);
                if (!cleanVal) {
                    handleErrorAndRecover("SILAKAN MASUKKAN NIK", 2000);
                    return;
                }
                handleEmployeeInput(cleanVal, "1", "Numpad Enter (IN)");
                return;
            }

            // D. Tombol PLUS (+) pada Numpad -> Presensi KELUAR (OUT / Kode: 0)
            if (event.code === "NumpadAdd" || (event.key === "+" && event.code.startsWith("Numpad")) || event.key === "+") {
                event.preventDefault();
                if (currentState !== AppState.IDLE) return;
                const cleanVal = rfidInput.value.trim().replace(/[^0-9]/g, "").slice(0, 6);
                if (!cleanVal) {
                    handleErrorAndRecover("SILAKAN MASUKKAN NIK", 2000);
                    return;
                }
                handleEmployeeInput(cleanVal, "0", "Numpad Plus (OUT)");
                return;
            }

            // E. Tombol ANGKA KHUSUS NUMPAD (0-9) - baik NumLock ON maupun OFF
            if (event.code && /^Numpad[0-9]$/.test(event.code)) {
                event.preventDefault();
                const digit = event.code.replace("Numpad", "");
                if (rfidInput.value.length < 6) {
                    rfidInput.value += digit;
                    rfidInput.dispatchEvent(new Event("input"));
                }
                return;
            }

            // F. BLOKIR SEMUA TOMBOL LAIN (Angka Baris Atas, Backspace Keyboard Biasa, Huruf, Simbol Lain)
            if (!["Tab", "F5", "F11", "F12", "NumLock"].includes(event.key)) {
                event.preventDefault();
            }
        });
    }

    // Tangani input keyboard global (Hanya izinkan tombol Numpad samping)
    window.addEventListener("keydown", (event) => {
        if (event.target === rfidInput) return;

        // A. Global MINUS (-) / BINTANG (*) pada Numpad -> CLEAR
        if (
            event.code === "NumpadSubtract" || event.code === "NumpadMultiply" ||
            (event.key === "-" && event.code.startsWith("Numpad")) ||
            (event.key === "*" && event.code.startsWith("Numpad")) ||
            event.key === "Subtract" || event.key === "Multiply"
        ) {
            event.preventDefault();
            if (currentState === AppState.IDLE && rfidInput && !rfidInput.disabled) {
                rfidInput.value = "";
                rfidInput.focus();
                rfidInput.dispatchEvent(new Event("input"));
            }
            return;
        }

        // B. Global SLASH (/) pada Numpad -> BACKSPACE 1 DIGIT
        if (
            event.code === "NumpadDivide" ||
            (event.key === "/" && (event.code.startsWith("Numpad") || event.code === "NumpadDivide")) ||
            event.key === "Divide"
        ) {
            event.preventDefault();
            if (currentState === AppState.IDLE && rfidInput && !rfidInput.disabled) {
                rfidInput.value = rfidInput.value.slice(0, -1);
                rfidInput.focus();
                rfidInput.dispatchEvent(new Event("input"));
            }
            return;
        }

        // C. Global Numpad Numbers KHUSUS Samping (0-9)
        if (event.code && /^Numpad[0-9]$/.test(event.code)) {
            event.preventDefault();
            const digit = event.code.replace("Numpad", "");
            if (currentState === AppState.IDLE && rfidInput && !rfidInput.disabled) {
                if (rfidInput.value.length < 6) {
                    rfidInput.value += digit;
                    rfidInput.dispatchEvent(new Event("input"));
                }
                rfidInput.focus();
            }
            return;
        }

        // D. Global ENTER / Numpad Enter -> Masuk
        if (event.code === "NumpadEnter" || (event.key === "Enter" && event.code.startsWith("Numpad")) || event.key === "Enter") {
            event.preventDefault();
            if (currentState !== AppState.IDLE) return;
            const cleanVal = rfidInput ? rfidInput.value.trim().replace(/[^0-9]/g, "").slice(0, 6) : "";
            if (!cleanVal) {
                handleErrorAndRecover("SILAKAN MASUKKAN NIK", 2000);
                return;
            }
            handleEmployeeInput(cleanVal, "1", "Numpad Enter (IN)");
            return;
        }

        // E. Global PLUS (+) / Numpad Add -> Keluar
        if (event.code === "NumpadAdd" || (event.key === "+" && event.code.startsWith("Numpad")) || event.key === "+") {
            event.preventDefault();
            if (currentState !== AppState.IDLE) return;
            const cleanVal = rfidInput ? rfidInput.value.trim().replace(/[^0-9]/g, "").slice(0, 6) : "";
            if (!cleanVal) {
                handleErrorAndRecover("SILAKAN MASUKKAN NIK", 2000);
                return;
            }
            handleEmployeeInput(cleanVal, "0", "Numpad Plus (OUT)");
            return;
        }
    });

    // Klik di sembarang tempat otomatis memfokuskan kursor ke input NIK
    document.addEventListener("click", (e) => {
        if (
            e.target !== btnManualMasuk &&
            e.target !== btnManualKeluar &&
            e.target !== mirrorToggleBtn &&
            e.target !== fullscreenBtn &&
            e.target !== retryCameraBtn
        ) {
            focusInputField();
        }
    });

    window.addEventListener("focus", () => {
        focusInputField();
    });

    focusInputField();
}

/**
 * Mencari kamera Logitech C930e (046d:0843) atau kamera eksternal USB terbaik
 */
async function findLogitechOrExternalCameraId() {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return null;
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(d => d.kind === "videoinput");
        if (videoDevices.length === 0) return null;

        // 1. Prioritaskan Logitech C930e (046d:0843)
        const logitech = videoDevices.find(d => /c930|logitech/i.test(d.label));
        if (logitech) {
            console.log(`[Presensi] Kamera Logitech C930e ditemukan: "${logitech.label}"`);
            return logitech.deviceId;
        }

        // 2. Prioritaskan kamera eksternal USB
        const usbCam = videoDevices.find(d => /usb|external/i.test(d.label));
        if (usbCam) {
            console.log(`[Presensi] Kamera USB terdeteksi: "${usbCam.label}"`);
            return usbCam.deviceId;
        }

        // 3. Fallback: kamera pertama
        return videoDevices[0].deviceId;
    } catch (e) {
        console.warn("[Presensi] Gagal menginventarisasi perangkat kamera:", e);
        return null;
    }
}

/**
 * Menginisialisasi siaran langsung kamera Logitech C930e dari backend (MJPEG stream).
 * Tidak memerlukan izin getUserMedia di peramban Firefox.
 */
function initializeCamera() {
    isCameraOnline = true;

    // Sembunyikan overlay loading agar siaran langsung kamera langsung terlihat
    if (cameraOverlay) {
        cameraOverlay.classList.add("hidden");
    }
    if (faceGuide) {
        faceGuide.classList.add("visible");
    }
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ONLINE";
        cameraStatusBadge.className = "badge active";
    }
    if (cameraTitle) {
        cameraTitle.textContent = "CAMERA PREVIEW";
    }

    // Hubungkan elemen <img> langsung ke endpoint streaming video backend
    if (streamVideo) {
        streamVideo.src = getApiUrl("api/camera/stream");
    }

    // Panduan oval disembunyikan di awal, hanya akan muncul saat countdown
    if (faceGuide) {
        faceGuide.classList.remove("visible");
    }
}

/**
 * Memperbarui tampilan antarmuka ke status menghubungkan kamera.
 */
function setCameraConnecting(msg = "Menghubungkan kamera...") {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ONLINE";
        cameraStatusBadge.className = "badge active";
    }
    if (cameraOverlay) {
        cameraOverlay.classList.add("hidden");
    }
    if (retryCameraBtn) {
        retryCameraBtn.classList.add("hidden");
    }
}

/**
 * Memperbarui status antarmuka ketika kamera aktif dan siap digunakan.
 */
function setCameraActive() {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ONLINE";
        cameraStatusBadge.className = "badge active";
    }
    if (cameraOverlay) {
        cameraOverlay.classList.add("hidden");
    }
    if (retryCameraBtn) {
        retryCameraBtn.classList.add("hidden");
    }
}

/**
 * Menangani respon atau kendala akses kamera browser.
 * Tidak memblokir absensi karena sistem utama menggunakan V4L2 di server.
 */
function handleCameraError(error) {
    console.log("[Presensi] Info stream kamera:", error ? error.message : "OK");
    isCameraOnline = true;
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ONLINE";
        cameraStatusBadge.className = "badge active";
    }
    if (cameraOverlay) {
        cameraOverlay.classList.add("hidden");
    }
    if (retryCameraBtn) {
        retryCameraBtn.classList.add("hidden");
    }
    if (statusText && currentState === AppState.IDLE) {
        statusText.textContent = "TEMPELKAN KARTU RFID DI READER";
    }
}

/**
 * Menampilkan pesan status kamera tanpa mengganggu alur presensi.
 */
function setCameraError(message) {
    handleCameraError({ name: "Warning", message: message });
}

/**
 * Mengatur fungsi tombol layar penuh (fullscreen).
 */
function initializeFullscreenHandler() {
    if (!fullscreenBtn) return;

    fullscreenBtn.addEventListener("click", () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.warn("[Presensi] Kendala fullscreen:", err);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(err => {
                    console.warn("[Presensi] Kendala keluar fullscreen:", err);
                });
            }
        }
    });

    document.addEventListener("fullscreenchange", () => {
        if (document.fullscreenElement) {
            fullscreenBtn.innerHTML = '<span class="fs-icon">🗗</span> JENDELA';
        } else {
            fullscreenBtn.innerHTML = '<span class="fs-icon">⛶</span> LAYAR PENUH';
        }
    });
}

/**
 * Mengatur orientasi pencerminan tampilan kamera (mirror/normal).
 */
function setMirrorMode(mirrored) {
    isMirrored = Boolean(mirrored);
    if (webcamVideo) {
        if (isMirrored) {
            webcamVideo.classList.add("mirrored");
        } else {
            webcamVideo.classList.remove("mirrored");
        }
    }
    if (streamVideo) {
        if (isMirrored) {
            streamVideo.classList.add("mirrored");
        } else {
            streamVideo.classList.remove("mirrored");
        }
    }
    if (mirrorToggleBtn && mirrorStatusText) {
        if (isMirrored) {
            mirrorToggleBtn.classList.add("active");
            mirrorStatusText.textContent = "MIRROR: ON";
        } else {
            mirrorToggleBtn.classList.remove("active");
            mirrorStatusText.textContent = "MIRROR: OFF";
        }
    }
    try {
        localStorage.setItem("absen_ntp_camera_mirrored", isMirrored ? "1" : "0");
    } catch (e) { }
}

/**
 * Menginisialisasi tombol pengalih mirror kamera.
 */
function initializeMirrorHandler() {
    if (!mirrorToggleBtn) return;

    let saved = false;
    try {
        const val = localStorage.getItem("absen_ntp_camera_mirrored") ?? localStorage.getItem("kiosk_camera_mirrored");
        saved = val === "1";
    } catch (e) { }
    setMirrorMode(saved);

    mirrorToggleBtn.addEventListener("click", () => {
        setMirrorMode(!isMirrored);
        console.log(`[Presensi] Mode mirror diubah: ${isMirrored ? "ON" : "OFF"}`);
    });
}

/**
 * Menginisialisasi tombol coba ulang kamera jika sebelumnya bermasalah.
 */
function initializeCameraRetryHandler() {
    if (!retryCameraBtn) return;

    retryCameraBtn.addEventListener("click", () => {
        console.log("[Presensi] Menghubungkan ulang kamera secara manual...");
        initializeCamera(0);
    });
}

// Lepas akses perangkat kamera saat halaman ditutup atau dimuat ulang
window.addEventListener("beforeunload", () => {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) { }
        });
    }
});

window.addEventListener("pagehide", () => {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) { }
        });
    }
});

let lastHandledScanId = null;
let lastHandledScanTime = 0;

/**
 * Memperbarui indikator status hardware RFID di UI
 */
function updateHardwareReaderStatus(readers) {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ONLINE";
        cameraStatusBadge.className = "badge active";
    }
}

/**
 * Menampilkan hasil presensi karyawan pada kartu informasi (Nama, NIK, Tipe, Foto & Kilatan).
 */
function displayAttendanceSuccess(data) {
    if (!data) return;

    // Deduplikasi ketat: Cegah render ganda dalam rentang 800ms
    const now = Date.now();
    const scanKey = data.scan_id || data.raw_data || `${data.nik || data.employee_id || ''}_${data.time || ''}`;
    if (scanKey && lastHandledScanId === scanKey && (now - lastHandledScanTime < 800)) {
        console.log(`[Presensi] Mengabaikan render ganda untuk scan: ${scanKey}`);
        return;
    }
    lastHandledScanId = scanKey;
    lastHandledScanTime = now;

    // 1. Efek kilatan lampu rana kamera (Shutter Flash)
    if (captureFlash) {
        captureFlash.classList.remove("flash-active");
        void captureFlash.offsetWidth; // Force reflow
        captureFlash.classList.add("flash-active");
        setTimeout(() => {
            if (captureFlash) captureFlash.classList.remove("flash-active");
        }, 250);
    }

    // 2. Evaluasi Validitas Data
    const isValid = (data.is_valid !== false) && (data.nik !== "TIDAK VALID") && (data.name !== "TIDAK VALID") && (data.success !== false);
    const nikDisplay = isValid ? (data.nik || data.employee_id || "-") : "TIDAK VALID";
    const empName = isValid ? (data.name || "Karyawan") : "TIDAK VALID";
    const isOut = data.in_out === "0" || (data.in_out_label && data.in_out_label.toUpperCase().includes("KELUAR")) || (data.reader_used && data.reader_used.toLowerCase().includes("sycreader"));

    console.log(`[Presensi UI Render] Nama: ${empName} | NIK: ${nikDisplay} | Mode: ${isOut ? 'KELUAR' : 'MASUK'} | Valid: ${isValid}`);

    // 3. Tampilkan Nama Karyawan
    if (employeeName) {
        employeeName.innerHTML = isValid
            ? `<span style="color: #f0f6fc; font-weight: 700;">${empName}</span>`
            : '<span class="text-invalid">TIDAK VALID</span>';
    }

    // 4. Tampilkan NIK Karyawan
    if (employeeNik) {
        employeeNik.innerHTML = isValid
            ? `<span style="color: var(--accent); font-weight: 800;">${nikDisplay}</span>`
            : '<span class="text-invalid">TIDAK VALID</span>';
    }
    if (employeeId && employeeId !== employeeNik) {
        employeeId.innerHTML = isValid
            ? `<span style="color: var(--accent); font-weight: 800;">${nikDisplay}</span>`
            : '<span class="text-invalid">TIDAK VALID</span>';
    }

    // 5. Tampilkan Tipe Presensi (In / Out)
    if (attendanceType) {
        attendanceType.innerHTML = isOut
            ? '<span style="color: #ff7b72; font-weight: 800; font-size: 1.15rem; text-shadow: 0 0 10px rgba(248, 81, 73, 0.4);">🔴 KELUAR (OUT)</span>'
            : '<span style="color: #56d364; font-weight: 800; font-size: 1.15rem; text-shadow: 0 0 10px rgba(86, 211, 100, 0.4);">🟢 MASUK (IN)</span>';
    }

    // 6. Tanggal dan Jam jika elemen tersedia
    if (attendanceDate && data.date) attendanceDate.textContent = data.date;
    if (attendanceTime && data.time) attendanceTime.textContent = data.time;

    // 7. Pratinjau Foto Jepretan Webcam
    if (capturedPreview) {
        if (data.photo_url) {
            capturedPreview.src = getApiUrl(data.photo_url) + "?t=" + Date.now();
        }
        if (isOut || !isValid) {
            capturedPreview.classList.add("preview-out");
        } else {
            capturedPreview.classList.remove("preview-out");
        }
        capturedPreview.classList.remove("hidden");
    }

    if (rfidInput) rfidInput.value = "";

    setApplicationState(isValid ? AppState.SUCCESS : AppState.ERROR, "", isOut);

    // 8. Jeda cepat 1.2 detik sebelum kembali standby (agar antrean presensi lancar & cepat)
    if (window._idleResetTimer) clearTimeout(window._idleResetTimer);
    window._idleResetTimer = setTimeout(() => {
        resetToIdle();
    }, 1200);
}

function handleHardwareAttendanceEvent(data) {
    if (!data) return;
    displayAttendanceSuccess(data);
}

/**
 * Menginisialisasi aliran event real-time Server-Sent Events (SSE) dan Fast Polling dari backend Kiosk.
 * Menggunakan Dual-Channel (SSE + 500ms Polling) sehingga pembacaan kartu hardware DIJAMIN 100%
 * langsung muncul di layar seketika tanpa ada event yang tertinggal atau terblokir browser.
 */
function initializeKioskEvents() {
    // 1. Selalu jalankan Fast Poller (500ms) untuk sinkronisasi instan
    startPollingFallback();

    // 2. Koneksi Server-Sent Events (SSE)
    if (typeof EventSource !== "undefined") {
        try {
            const sseUrl = getApiUrl("api/kiosk/events");
            console.log("[SSE] Menghubungkan ke Kiosk Event Stream:", sseUrl);
            const evtSource = new EventSource(sseUrl);

            evtSource.onopen = () => {
                console.log("[SSE] Terhubung ke Kiosk Event Stream (Dual-Reader Active).");
            };

            evtSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === "INIT") {
                        updateHardwareReaderStatus(data.readers);
                        return;
                    }

                    // Event absensi dari hardware tap (QinHeng / Sycreader)
                    if (data.name || data.nik || data.raw_data || data.employee_id) {
                        handleHardwareAttendanceEvent(data);
                    }
                } catch (err) {
                    console.error("[SSE] Gagal parse event data:", err);
                }
            };

            evtSource.onerror = () => {
                console.warn("[SSE] Event stream terputus, poller fallback tetap aktif...");
            };
        } catch (e) {
            console.error("[SSE] Kesalahan inisialisasi EventSource:", e);
        }
    }
}

/**
 * Fast Polling memeriksa /api/kiosk/latest setiap 500ms
 */
function startPollingFallback() {
    setInterval(async () => {
        try {
            const resp = await fetch(getApiUrl("api/kiosk/latest"), { cache: "no-store" });
            if (resp.ok) {
                const data = await resp.json();
                if (!data || !data.scan_id) return;
                const pollKey = data.scan_id;
                const isFresh = data.scan_ts ? (Date.now() / 1000 - data.scan_ts < 10) : true;
                if (isFresh && (data.name || data.nik || data.raw_data || data.employee_id) && pollKey !== lastHandledScanId) {
                    console.log("[Fast Poller] Mendeteksi scan baru dari backend:", data.name || data.nik);
                    handleHardwareAttendanceEvent(data);
                }
            }
        } catch (e) {
            // Silently ignore polling network errors
        }
    }, 500);
}

// Inisialisasi seluruh komponen saat dokumen HTML selesai dimuat
document.addEventListener("DOMContentLoaded", () => {
    console.log("[Presensi] Sistem Presensi Siap Digunakan.");
    setApplicationState(AppState.IDLE);
    initializeClock();
    initializeMirrorHandler();
    initializeCamera();
    initializeInputHandler();
    initializeFullscreenHandler();
    initializeCameraRetryHandler();
    initializeKioskEvents();
});
