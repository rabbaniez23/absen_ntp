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

// Elemen DOM - Input RFID / Keyboard
const rfidInput = document.getElementById("rfidInput");

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

    if (!statusText) return;

    switch (newState) {
        case AppState.IDLE:
            statusText.textContent = "TEMPEL KARTU RFID ATAU MASUKKAN NIK";
            if (rfidInput) {
                rfidInput.disabled = false;
                focusInputField();
            }
            break;

        case AppState.IDENTIFYING:
            statusText.textContent = "MENCARI DATA KARYAWAN...";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.EMPLOYEE_FOUND:
            statusText.textContent = customMessage || "KARTU TERDETEKSI";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.CAMERA_READY:
            statusText.textContent = customMessage || "ARAHKAN WAJAH KE KAMERA";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.COUNTDOWN:
            statusText.textContent = customMessage ? `HITUNG MUNDUR: ${customMessage}` : "HITUNG MUNDUR";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.CAPTURING:
            statusText.textContent = customMessage || "MENGAMBIL FOTO...";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.SAVING:
            statusText.textContent = customMessage || "MENYIMPAN DATA...";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.SUCCESS:
            statusText.textContent = customMessage || "ABSENSI BERHASIL";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.ERROR:
            statusText.textContent = customMessage || "TERJADI KESALAHAN";
            if (rfidInput) rfidInput.disabled = true;
            break;

        default:
            statusText.textContent = customMessage || newState;
            break;
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
    lastHandledScanId = null;
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
 * Menangani tap kartu RFID QinHeng:
 * 1. Menampilkan Nama Karyawan & NIK (Nomor RFID disembunyikan).
 * 2. Mengaktifkan panduan lingkaran wajah & hitung mundur 3-2-1.
 * 3. Menjepret frame live stream kamera Logitech C930e dan menyimpan ke MariaDB.
 */
async function handleEmployeeInput(rawInput, forcedMode = "", readerName = "Web Kiosk UI", timingInfo = {}) {
    if (currentState !== AppState.IDLE) {
        console.warn(`[Presensi] Input diabaikan: Sistem sedang dalam status ${currentState}`);
        return;
    }

    const cleanId = rawInput.trim();
    if (!cleanId) return;

    if (rfidInput) rfidInput.value = "";

    // 1. Cari data karyawan ke backend
    setApplicationState(AppState.IDENTIFYING, "MENCARI DATA KARYAWAN...");

    try {
        const response = await fetchWithTimeout(`api/employee?id=${encodeURIComponent(cleanId)}`, {}, 6000);
        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            const nikDisplay = data.nik || data.employee_id;
            console.log(`[Presensi] Karyawan ditemukan: ${data.name} (NIK: ${nikDisplay}) | Mode: ${forcedMode || 'Auto'}`);
            currentEmployeeId = data.employee_id;

            // Tampilkan HANYA Nama Karyawan dan NIK (Nomor RFID disembunyikan demi privasi)
            if (employeeName) employeeName.textContent = data.name;
            if (employeeNik) employeeNik.textContent = nikDisplay;
            if (employeeId && employeeId !== employeeNik) employeeId.textContent = nikDisplay;

            setApplicationState(AppState.EMPLOYEE_FOUND, `KARYAWAN TERDETEKSI: ${data.name.toUpperCase()}`);

            // Langsung jepret foto absensi seketika tanpa jeda hitung mundur
            processAttendanceScan(cleanId, data, forcedMode, readerName, timingInfo);

        } else {
            const message = data && data.message ? data.message.toUpperCase() : "KARTU RFID TIDAK TERDAFTAR";
            handleErrorAndRecover(message, 2500);
        }
    } catch (error) {
        console.error("[Presensi] Kesalahan pencarian karyawan:", error);
        handleErrorAndRecover("SERVER BACKEND TIDAK TERHUBUNG", 2500);
    }
}

/**
 * Menjepret frame kamera dan mencatat absensi ke server backend.
 */
async function processAttendanceScan(id, empInfo = null, forcedMode = "", readerName = "Web Kiosk UI", timingInfo = {}) {
    setApplicationState(AppState.CAPTURING, "MENGAMBIL FOTO...");

    // Efek kilatan lampu rana kamera (shutter flash)
    if (captureFlash) {
        captureFlash.classList.add("flash-active");
        setTimeout(() => captureFlash.classList.remove("flash-active"), 350);
    }

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

// Variabel penampung karakter scanner RFID global
let rfidBuffer = "";
let rfidKeyEvents = [];
let rfidBufferTimer = null;

/**
 * Menginisialisasi pendengar event keyboard dan kartu RFID.
 */
function initializeInputHandler() {
    // 1. Tangani tombol ABSEN manual jika diklik
    const submitNikBtn = document.getElementById("submitNikBtn");
    if (submitNikBtn) {
        submitNikBtn.addEventListener("click", () => {
            const cleanVal = rfidBuffer.trim();
            rfidBuffer = "";
            rfidKeyEvents = [];
            if (rfidInput) rfidInput.value = "";
            if (cleanVal) handleEmployeeInput(cleanVal, "1", "Manual Web Button");
        });
    }

    // 2. Global Keydown listener untuk menangkap input scanner RFID & Keyboard
    // Menggunakan event.preventDefault() agar karakter mentah TIDAK PERNAH muncul di layar
    document.addEventListener("keydown", (event) => {
        // Jika fokus sedang di input teks lain (misal modal atau form admin), abaikan
        if (event.target !== rfidInput && (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA")) {
            return;
        }

        if (event.key === "Enter") {
            event.preventDefault();
            const rawVal = rfidBuffer.trim();
            const events = [...rfidKeyEvents];
            const enterCode = event.code;

            const duration = events.length > 1 ? Math.round(events[events.length - 1].time - events[0].time) : 0;
            const avgInterval = events.length > 1 ? +(duration / (events.length - 1)).toFixed(1) : 0;
            const firstKey = events.length > 0 ? events[0].code : "";
            const timingInfo = { duration, avgInterval, enterCode, firstKey };

            rfidBuffer = "";
            rfidKeyEvents = [];
            if (rfidInput) rfidInput.value = "";

            if (rawVal) {
                // Deteksi scancode keyboard hardware
                const isNumpad = enterCode === "NumpadEnter" || events.some(e => (e.code && e.code.startsWith("Numpad")) || e.location === 3);

                // Analisis Sidik Jari Kecepatan Hardware (Hardware Fingerprint):
                // Reader Awal (QinHeng): Ultra-fast burst (~36ms / 4ms per char) -> MASUK (IN / 1)
                // Reader Baru (Sycreader): Standard USB timing (~143ms / 16ms per char) -> KELUAR (OUT / 0)
                let detectedMode = "1";
                let readerLabel = `QinHeng IN (${duration}ms)`;

                if (avgInterval >= 10 || duration >= 80) {
                    detectedMode = "0";
                    readerLabel = `Sycreader OUT (${duration}ms)`;
                } else if (isNumpad || rawVal.startsWith("13") || rawVal.toLowerCase().includes("dreizehn") || (rawVal.length > 10 && !rawVal.startsWith("320"))) {
                    detectedMode = "0";
                    readerLabel = "Sycreader OUT (Scancode/Prefix)";
                }

                console.log(`[Input Timing] Raw: ${rawVal} | Dur: ${duration}ms | Avg: ${avgInterval}ms | Mode: ${detectedMode} (${readerLabel})`);
                handleEmployeeInput(rawVal, detectedMode, readerLabel, timingInfo);
            }
            return;
        }

        if (event.key === "Backspace") {
            event.preventDefault();
            rfidBuffer = rfidBuffer.slice(0, -1);
            if (rfidKeyEvents.length > 0) rfidKeyEvents.pop();
            if (rfidInput) rfidInput.value = "•".repeat(rfidBuffer.length);
            return;
        }

        // Tangkap karakter RFID / NIK secara instan tanpa merender angka aslinya
        if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
            event.preventDefault();
            rfidBuffer += event.key;
            rfidKeyEvents.push({
                key: event.key,
                code: event.code,
                location: event.location,
                time: event.timeStamp
            });

            if (rfidInput) {
                rfidInput.value = "•".repeat(rfidBuffer.length);
            }

            clearTimeout(rfidBufferTimer);
            rfidBufferTimer = setTimeout(() => {
                rfidBuffer = "";
                rfidKeyEvents = [];
                if (rfidInput && currentState === AppState.IDLE) {
                    rfidInput.value = "";
                }
            }, 800);
        }
    }, true);

    document.addEventListener("click", () => {
        focusInputField();
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

function updateHardwareReaderStatus(readers) {
    if (Array.isArray(readers)) {
        console.log(`[Hardware Readers] ${readers.length} perangkat aktif terhubung.`);
    }
}

/**
 * Menampilkan hasil presensi karyawan pada kartu informasi dan status banner.
 */
function displayAttendanceSuccess(data) {
    if (!data) return;

    if (captureFlash) {
        captureFlash.classList.add("flash-active");
        setTimeout(() => captureFlash.classList.remove("flash-active"), 350);
    }

    const nikDisplay = data.nik || data.employee_id || "-";
    const empName = data.name || "Karyawan";
    const isOut = data.in_out === "0" || (data.in_out_label && data.in_out_label.toUpperCase().includes("KELUAR")) || (data.reader_used && data.reader_used.toLowerCase().includes("sycreader"));
    const typeLabel = isOut ? "KELUAR (OUT)" : "MASUK (IN)";

    console.log(`[Presensi Sukses] ${empName} (NIK: ${nikDisplay}) -> ${typeLabel}`);

    if (employeeName) employeeName.textContent = empName;
    if (employeeNik) employeeNik.textContent = nikDisplay;
    if (employeeId && employeeId !== employeeNik) employeeId.textContent = nikDisplay;
    if (attendanceDate && data.date) attendanceDate.textContent = data.date;
    if (attendanceTime && data.time) attendanceTime.textContent = data.time;
    if (attendanceType) {
        attendanceType.innerHTML = isOut
            ? '<span style="color: #ff7b72; font-weight: 800; font-size: 1.15rem; text-shadow: 0 0 10px rgba(248, 81, 73, 0.4);">🔴 KELUAR (OUT)</span>'
            : '<span style="color: #56d364; font-weight: 800; font-size: 1.15rem; text-shadow: 0 0 10px rgba(86, 211, 100, 0.4);">🟢 MASUK (IN)</span>';
    }
    if (rfidInput) rfidInput.value = "";

    if (capturedPreview && data.photo_url) {
        capturedPreview.src = getApiUrl(data.photo_url) + "?t=" + Date.now();
        if (isOut) {
            capturedPreview.classList.add("preview-out");
        } else {
            capturedPreview.classList.remove("preview-out");
        }
        capturedPreview.classList.remove("hidden");
    }

    const successMsg = isOut
        ? `ABSENSI KELUAR (OUT) BERHASIL: ${empName.toUpperCase()}`
        : `ABSENSI MASUK (IN) BERHASIL: ${empName.toUpperCase()}`;

    setApplicationState(AppState.SUCCESS, successMsg, isOut);

    if (window._idleResetTimer) clearTimeout(window._idleResetTimer);
    window._idleResetTimer = setTimeout(() => {
        resetToIdle();
    }, 3000);
}

function handleHardwareAttendanceEvent(data) {
    if (!data) return;
    if (data.success === false) {
        handleErrorAndRecover(data.message ? data.message.toUpperCase() : "KARTU RFID TIDAK TERDAFTAR", 2500);
        return;
    }

    const eventKey = data.scan_id || `${data.raw_data || ''}_${data.scan_ts || data.time || ''}_${Date.now()}`;
    if (lastHandledScanId === eventKey) return;
    lastHandledScanId = eventKey;

    displayAttendanceSuccess(data);
}

/**
 * Menginisialisasi aliran event real-time Server-Sent Events (SSE) dari backend Kiosk.
 * Saat kartu RFID di-tap pada perangkat hardware fisik (QinHeng / Sycreader),
 * backend langsung mengirim sinyal ke sini sehingga UI otomatis terupdate tanpa perlu reload.
 */
function initializeKioskEvents() {
    if (typeof EventSource === "undefined") {
        console.warn("[SSE] Browser tidak mendukung EventSource. Mengaktifkan polling.");
        startPollingFallback();
        return;
    }

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
            console.warn("[SSE] Event stream terputus, reconnect otomatis...");
        };
    } catch (e) {
        console.error("[SSE] Kesalahan inisialisasi EventSource:", e);
    }

    // Polling cadangan (safety fallback) setiap 1.5 detik
    startPollingFallback();
}

/**
 * Polling fallback memeriksa /api/kiosk/latest secara periodik
 */
function startPollingFallback() {
    setInterval(async () => {
        if (currentState !== AppState.IDLE) return;
        try {
            const resp = await fetch(getApiUrl("api/kiosk/latest"));
            if (resp.ok) {
                const data = await resp.json();
                const pollKey = data.scan_id || `${data.raw_data || ''}_${data.scan_ts || data.time || ''}`;
                if (data && (data.name || data.nik || data.raw_data) && pollKey && pollKey !== lastHandledScanId) {
                    handleHardwareAttendanceEvent(data);
                }
            }
        } catch (e) {
            // Silently ignore polling network errors
        }
    }, 1500);
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
