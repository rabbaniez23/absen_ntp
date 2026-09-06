/**
 * Employee Attendance System - Task 11: Comprehensive Error Handling
 */

// Application States Definition
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
let isMirrored = false; // Default: Normal (NOT MIRRORED)

// DOM Elements - Camera & Capture
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

// DOM Elements - Date and Time
const liveDate = document.getElementById("liveDate");
const liveTime = document.getElementById("liveTime");
const attendanceDate = document.getElementById("attendanceDate");
const attendanceTime = document.getElementById("attendanceTime");

// DOM Elements - Employee Info & Status
const employeeName = document.getElementById("employeeName");
const employeeId = document.getElementById("employeeId");
const statusBanner = document.getElementById("statusBanner");
const statusText = document.getElementById("statusText");

// DOM Elements - Input Field (RFID / Keyboard / Numpad)
const rfidInput = document.getElementById("rfidInput");

// Month names in Indonesian
const MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
];

/**
 * Formats a Date object into DD MMMM YYYY (e.g. 05 September 2026).
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) {
    const day = String(date.getDate()).padStart(2, "0");
    const month = MONTH_NAMES[date.getMonth()];
    const year = date.getFullYear();
    return `${day} ${month} ${year}`;
}

/**
 * Formats a Date object into HH:mm:ss (e.g. 22:10:45).
 * @param {Date} date
 * @returns {string}
 */
function formatTime(date) {
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    return `${hours}:${minutes}:${seconds}`;
}

/**
 * Updates the date and time elements every second.
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
 * Starts the realtime clock timer.
 */
function initializeClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

/**
 * Sets the application state and updates UI components accordingly.
 * @param {string} newState
 * @param {string} [customMessage=""]
 */
function setApplicationState(newState, customMessage = "") {
    currentState = newState;
    console.log(`[Attendance System] State Transition -> ${newState} ${customMessage ? `("${customMessage}")` : ""}`);

    if (statusBanner) {
        statusBanner.className = `status-banner state-${newState.toLowerCase()}`;
    }

    // Toggle biometric face oval guide during camera positioning & countdown
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
            statusText.textContent = "TEMPELKAN KARTU RFID DI READER";
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
            statusText.textContent = customMessage || "EMPLOYEE FOUND";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.CAMERA_READY:
            statusText.textContent = customMessage || "POSITION YOUR FACE";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.COUNTDOWN:
            statusText.textContent = customMessage ? `COUNTDOWN: ${customMessage}` : "COUNTDOWN";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.CAPTURING:
            statusText.textContent = customMessage || "CAPTURING...";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.SAVING:
            statusText.textContent = customMessage || "SAVING...";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.SUCCESS:
            statusText.textContent = customMessage || "ABSENSI BERHASIL";
            if (rfidInput) rfidInput.disabled = true;
            break;

        case AppState.ERROR:
            statusText.textContent = customMessage || "ERROR";
            if (rfidInput) rfidInput.disabled = true;
            break;

        default:
            statusText.textContent = customMessage || newState;
            break;
    }
}

/**
 * Handles errors gracefully and guarantees safe recovery back to IDLE state.
 * @param {string} errorMessage
 * @param {number} [displayDuration=2500]
 */
function handleErrorAndRecover(errorMessage, displayDuration = 2500) {
    console.warn(`[Attendance System] Error occurred: ${errorMessage}`);

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
 * Resets application state, overlays, and employee display back to IDLE.
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
        capturedPreview.src = "";
    }
    if (currentPreviewUrl) {
        URL.revokeObjectURL(currentPreviewUrl);
        currentPreviewUrl = null;
    }
    currentEmployeeId = null;
    if (employeeName) employeeName.textContent = "-";
    if (employeeId) employeeId.textContent = "-";
    if (rfidInput) rfidInput.value = "";

    // Guarantee webcam video playback is active and unpaused
    if (webcamVideo && isCameraOnline && webcamVideo.paused) {
        webcamVideo.play().catch(err => console.warn("[Attendance System] Video resume error:", err));
    }

    setApplicationState(AppState.IDLE);
}

/**
 * Keeps the input field focused when system is in IDLE state.
 */
function focusInputField() {
    if (currentState === AppState.IDLE && rfidInput && document.activeElement !== rfidInput) {
        rfidInput.focus();
    }
}

/**
 * Helper to perform fetch with request timeout using AbortController.
 * @param {string} url
 * @param {RequestInit} [options={}]
 * @param {number} [timeoutMs=8000]
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(url, {
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
 * Parses JSON response safely; handles invalid JSON formatting.
 * @param {Response} response 
 * @returns {Promise<any>}
 */
async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch (error) {
        throw new Error("JSON_INVALID");
    }
}

/**
 * Verifies if camera stream is active and functional.
 * @returns {boolean}
 */
function isCameraReady() {
    return isCameraOnline && webcamVideo && webcamVideo.readyState >= 2 && webcamVideo.videoWidth > 0;
}

/**
 * Look up employee data from backend API with robust error handling.
 * @param {string} id 
 */
async function lookupEmployee(id) {
    setApplicationState(AppState.IDENTIFYING);

    try {
        const response = await fetchWithTimeout(`/api/employee?id=${encodeURIComponent(id)}`, {}, 6000);
        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            console.log(`[Attendance System] Employee found: ${data.name} (${data.employee_id})`);
            currentEmployeeId = data.employee_id;

            if (employeeName) employeeName.textContent = data.name;
            if (employeeId) employeeId.textContent = data.rfid_uid || data.employee_id;

            setApplicationState(AppState.EMPLOYEE_FOUND, `KARTU TERDETEKSI: ${data.name.toUpperCase()}`);

            // Transition: EMPLOYEE_FOUND -> CAMERA_READY
            setTimeout(() => {
                // Ensure camera is still ready before prompting position face
                if (!isCameraReady()) {
                    handleErrorAndRecover("KAMERA TIDAK TERSEDIA");
                    return;
                }

                setApplicationState(AppState.CAMERA_READY, "POSITION YOUR FACE");

                setTimeout(() => {
                    startCountdown(() => {
                        captureWebcamFrame();
                    });
                }, 1500);

            }, 1200);

        } else {
            // Error 1: Employee tidak ditemukan
            const message = data && data.message ? data.message.toUpperCase() : "EMPLOYEE NOT FOUND";
            handleErrorAndRecover(message);
        }
    } catch (error) {
        console.error("[Attendance System] Lookup error:", error);

        // Error 7: Request timeout
        if (error.message === "REQUEST_TIMEOUT") {
            handleErrorAndRecover("REQUEST TIMEOUT (SERVER TIDAK MERESPON)");
        }
        // Error 9: JSON invalid
        else if (error.message === "JSON_INVALID") {
            handleErrorAndRecover("FORMAT DATA JSON TIDAK VALID");
        }
        // Error 6: Backend tidak aktif
        else {
            handleErrorAndRecover("SERVER BACKEND TIDAK AKTIF / OFFLINE");
        }
    }
}

/**
 * Executes a 3-2-1 countdown sequence with visual display.
 * @param {Function} onComplete Callback function executed after countdown ends.
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

            console.log("[Attendance System] Countdown finished. Triggering capture...");
            if (typeof onComplete === "function") {
                onComplete();
            }
        }
    }, 1000);
}

/**
 * Captures a single frame from the webcam stream onto an HTML Canvas,
 * converts it into a PNG Blob, and dispatches to uploadCapture.
 */
function captureWebcamFrame() {
    setApplicationState(AppState.CAPTURING, "CAPTURING IMAGE...");

    // Error 8: Capture gagal (kamera terputus atau frame kosong)
    if (!isCameraReady()) {
        console.error("[Attendance System] Capture failed: Camera stream not ready.");
        handleErrorAndRecover("CAPTURE GAGAL: KAMERA TIDAK TERSEDIA");
        return;
    }

    // Shutter flash effect
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
                console.error("[Attendance System] Canvas toBlob returned null.");
                handleErrorAndRecover("CAPTURE GAGAL: KONVERSI GAMBAR GAGAL");
                return;
            }

            console.log(`[Attendance System] Frame captured: PNG Blob ${(blob.size / 1024).toFixed(1)} KB (${width}x${height})`);

            // Freeze frame preview
            if (currentPreviewUrl) {
                URL.revokeObjectURL(currentPreviewUrl);
            }
            currentPreviewUrl = URL.createObjectURL(blob);

            if (capturedPreview) {
                capturedPreview.src = currentPreviewUrl;
                capturedPreview.classList.remove("hidden");
            }

            // Upload image to backend
            uploadCapture(currentEmployeeId, blob);

        }, "image/png");

    } catch (err) {
        console.error("[Attendance System] Exception during canvas drawImage:", err);
        handleErrorAndRecover("CAPTURE GAGAL: KESALAHAN KANVAS");
    }
}

/**
 * Uploads captured PNG Blob and Employee ID to the Python backend with complete error handling.
 * @param {string} empId
 * @param {Blob} blob
 */
async function uploadCapture(empId, blob) {
    setApplicationState(AppState.SAVING, "MENYIMPAN FOTO ABSENSI...");

    const formData = new FormData();
    formData.append("employee_id", empId);
    formData.append("image", blob, "webcam.png");

    try {
        const response = await fetchWithTimeout("/api/upload", {
            method: "POST",
            body: formData
        }, 10000); // 10s upload timeout

        // Error 5: File terlalu besar (HTTP 413)
        if (response.status === 413) {
            handleErrorAndRecover("FILE TERLALU BESAR (MAKSIMUM 10MB)");
            return;
        }

        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            console.log("[Attendance System] Attendance recorded:", data);
            setApplicationState(AppState.SUCCESS, "ABSENSI BERHASIL");

            setTimeout(() => {
                resetToIdle();
            }, 2500);
        } else {
            // Error 4: Upload gagal
            const message = data && data.message ? `UPLOAD GAGAL: ${data.message}` : "UPLOAD GAGAL";
            handleErrorAndRecover(message);
        }
    } catch (error) {
        console.error("[Attendance System] Upload error:", error);

        // Error 7: Request timeout
        if (error.message === "REQUEST_TIMEOUT") {
            handleErrorAndRecover("UPLOAD TIMEOUT (SERVER TIDAK MERESPON)");
        }
        // Error 9: JSON invalid
        else if (error.message === "JSON_INVALID") {
            handleErrorAndRecover("FORMAT DATA RESPON TIDAK VALID");
        }
        // Error 6: Backend tidak aktif
        else {
            handleErrorAndRecover("SERVER BACKEND TIDAK TERHUBUNG");
        }
    }
}

/**
 * Handles submission of Employee ID / RFID UID.
 * Prevents overlapping processes if system is not in IDLE state.
 * @param {string} rawInput 
 */
function handleEmployeeInput(rawInput) {
    if (currentState !== AppState.IDLE) {
        console.warn(`[Attendance System] Input ignored: System busy in state ${currentState}`);
        return;
    }

    // Pre-validation: Ensure camera is operating before proceeding
    if (!isCameraReady()) {
        handleErrorAndRecover("KAMERA TIDAK AKTIF / BELUM DIIZINKAN");
        return;
    }

    const cleanId = rawInput.trim();
    if (!cleanId) return;

    console.log(`[Attendance System] Input received: "${cleanId}"`);
    if (rfidInput) rfidInput.value = "";

    lookupEmployee(cleanId);
}

/**
 * Initializes input event listeners for RFID and Keyboard.
 */
function initializeInputHandler() {
    if (!rfidInput) return;

    rfidInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            handleEmployeeInput(rfidInput.value);
        }
    });

    document.addEventListener("click", () => {
        focusInputField();
    });

    focusInputField();
}

/**
 * Initializes and requests browser webcam access with detailed error handling and auto-retry.
 * @param {number} [retryCount=0] Current retry attempt count
 */
async function initializeCamera(retryCount = 0) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        isCameraOnline = false;
        setCameraError("Webcam API tidak didukung pada browser ini.");
        return;
    }

    // Clean up any lingering old tracks before acquiring a new stream
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) {}
        });
        mediaStream = null;
    }

    setCameraConnecting(retryCount > 0 ? `Menunggu pelepasan kamera oleh sistem (${retryCount}/3)...` : "Menghubungkan kamera...");

    try {
        const constraints = {
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: "user"
            },
            audio: false
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        mediaStream = stream;
        webcamVideo.srcObject = stream;

        webcamVideo.onloadedmetadata = () => {
            webcamVideo.play().catch(err => {
                console.warn("[Attendance System] Video play warning:", err);
            });
            isCameraOnline = true;
            setCameraActive();
            console.log("[Attendance System] Webcam stream started successfully.");
        };

        // Handle stream interruption (e.g. USB webcam unplugged)
        stream.getVideoTracks().forEach(track => {
            track.onended = () => {
                isCameraOnline = false;
                handleCameraError({ name: "NotFoundError", message: "Webcam disconnected" });
            };
        });

    } catch (error) {
        isCameraOnline = false;
        console.error("[Attendance System] Webcam error:", error);

        // If camera hardware was temporarily locked by Windows/driver during reload, auto-retry up to 3 times
        if ((error.name === "NotReadableError" || error.name === "TrackStartError") && retryCount < 3) {
            const delay = 1200 + (retryCount * 500);
            console.log(`[Attendance System] Camera locked by device driver. Auto-retrying in ${delay}ms (Attempt ${retryCount + 1}/3)...`);
            setTimeout(() => {
                initializeCamera(retryCount + 1);
            }, delay);
            return;
        }

        handleCameraError(error);
    }
}

/**
 * Updates UI to camera connecting state.
 * @param {string} [msg="Menghubungkan kamera..."]
 */
function setCameraConnecting(msg = "Menghubungkan kamera...") {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "CONNECTING...";
        cameraStatusBadge.className = "badge";
    }
    if (cameraOverlay) {
        cameraOverlay.classList.remove("hidden", "error");
    }
    if (cameraMessage) {
        cameraMessage.textContent = msg;
    }
    if (retryCameraBtn) {
        retryCameraBtn.classList.add("hidden");
    }
}

/**
 * Updates UI when camera is active and streaming.
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
 * Handles camera errors gracefully.
 * Covers Error 2 (Permission denied) and Error 3 (Camera not available).
 * @param {Error} error 
 */
function handleCameraError(error) {
    let message = "Camera error: " + error.message;

    // Error 2: Camera permission denied
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
        message = "Izin kamera ditolak oleh browser.";
    }
    // Error 3: Camera tidak tersedia
    else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
        message = "Kamera tidak ditemukan pada perangkat.";
    } else if (error.name === "NotReadableError" || error.name === "TrackStartError") {
        message = "Kamera sedang digunakan aplikasi lain atau belum dilepas oleh sistem.";
    } else if (error.name === "OverconstrainedError") {
        message = "Kamera tidak mendukung resolusi yang diminta.";
    }

    setCameraError(message);
}

/**
 * Displays error state on camera viewport.
 * @param {string} message 
 */
function setCameraError(message) {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "ERROR";
        cameraStatusBadge.className = "badge error";
    }
    if (cameraOverlay) {
        cameraOverlay.classList.remove("hidden");
        cameraOverlay.classList.add("error");
    }
    if (cameraIcon) {
        cameraIcon.textContent = "⚠️";
    }
    if (cameraMessage) {
        cameraMessage.textContent = message;
    }
    if (retryCameraBtn) {
        retryCameraBtn.classList.remove("hidden");
    }
    if (statusText && currentState === AppState.IDLE) {
        statusText.textContent = "CAMERA UNAVAILABLE";
    }
}

/**
 * Initializes fullscreen toggle button.
 */
function initializeFullscreenHandler() {
    if (!fullscreenBtn) return;

    fullscreenBtn.addEventListener("click", () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.warn("[Attendance System] Fullscreen error:", err);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(err => {
                    console.warn("[Attendance System] Exit fullscreen error:", err);
                });
            }
        }
    });

    document.addEventListener("fullscreenchange", () => {
        if (document.fullscreenElement) {
            fullscreenBtn.innerHTML = '<span class="fs-icon">🗗</span> WINDOWED';
        } else {
            fullscreenBtn.innerHTML = '<span class="fs-icon">⛶</span> FULLSCREEN';
        }
    });
}

/**
 * Applies mirror or normal orientation to camera viewport and button.
 * @param {boolean} mirrored
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
    } catch (e) {}
}

/**
 * Initializes camera mirror orientation toggle button.
 */
function initializeMirrorHandler() {
    if (!mirrorToggleBtn) return;

    // Load persisted user preference; default is FALSE (Normal / Non-Mirrored)
    let saved = false;
    try {
        const val = localStorage.getItem("absen_ntp_camera_mirrored") ?? localStorage.getItem("kiosk_camera_mirrored");
        saved = val === "1";
    } catch (e) {}
    setMirrorMode(saved);

    mirrorToggleBtn.addEventListener("click", () => {
        setMirrorMode(!isMirrored);
        console.log(`[Attendance System] User toggled mirror mode: ${isMirrored ? "ON" : "OFF"}`);
    });
}

/**
 * Initializes manual camera retry button listener.
 */
function initializeCameraRetryHandler() {
    if (!retryCameraBtn) return;

    retryCameraBtn.addEventListener("click", () => {
        console.log("[Attendance System] Reconnecting camera via manual retry button...");
        initializeCamera(0);
    });
}

// Clean up camera hardware tracks immediately when user leaves or refreshes the page
window.addEventListener("beforeunload", () => {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) {}
        });
    }
});

window.addEventListener("pagehide", () => {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) {}
        });
    }
});

// Lifecycle event: Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    console.log("[Attendance System] Initialized Task 13: UI Polish");
    setApplicationState(AppState.IDLE);
    initializeClock();
    initializeMirrorHandler();
    initializeCamera();
    initializeInputHandler();
    initializeFullscreenHandler();
    initializeCameraRetryHandler();
});
