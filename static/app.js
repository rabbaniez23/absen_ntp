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
function setApplicationState(newState, customMessage = "") {
    currentState = newState;
    console.log(`[Presensi] Perubahan Status -> ${newState} ${customMessage ? `("${customMessage}")` : ""}`);

    if (statusBanner) {
        statusBanner.className = `status-banner state-${newState.toLowerCase()}`;
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
    if (rfidInput) rfidInput.value = "";

    // Pastikan video kamera tetap berputar
    if (webcamVideo && isCameraOnline && webcamVideo.paused) {
        webcamVideo.play().catch(err => console.warn("[Presensi] Gagal memutar ulang video:", err));
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
 * Memeriksa apakah feed video kamera sedang aktif dan siap.
 */
function isCameraReady() {
    return isCameraOnline && webcamVideo && webcamVideo.readyState >= 2 && webcamVideo.videoWidth > 0;
}

/**
 * Mencari data karyawan ke backend berdasarkan ID atau UID kartu RFID.
 */
async function lookupEmployee(id) {
    setApplicationState(AppState.IDENTIFYING);

    try {
        const response = await fetchWithTimeout(`api/employee?id=${encodeURIComponent(id)}`, {}, 6000);
        const data = await parseJsonResponse(response);

        if (response.ok && data.success) {
            const nikDisplay = data.nik || data.employee_id;
            console.log(`[Presensi] Karyawan ditemukan: ${data.name} (NIK: ${nikDisplay})`);
            currentEmployeeId = data.employee_id;

            // Tampilkan HANYA Nama Karyawan dan NIK (Jangan tampilkan Nomor RFID)
            if (employeeName) employeeName.textContent = data.name;
            if (employeeNik) employeeNik.textContent = nikDisplay;
            if (employeeId && employeeId !== employeeNik) employeeId.textContent = nikDisplay;
            if (rfidInput) rfidInput.value = "";

            setApplicationState(AppState.EMPLOYEE_FOUND, `KARYAWAN TERDETEKSI: ${data.name.toUpperCase()}`);

            // Transisi: KARTU TERDETEKSI -> ARAHKAN WAJAH
            setTimeout(() => {
                // Pastikan kamera aktif sebelum meminta karyawan menghadap kamera
                if (!isCameraReady()) {
                    handleErrorAndRecover("KAMERA TIDAK TERSEDIA");
                    return;
                }

                setApplicationState(AppState.CAMERA_READY, "ARAHKAN WAJAH KE KAMERA");

                setTimeout(() => {
                    startCountdown(() => {
                        captureWebcamFrame();
                    });
                }, 1500);

            }, 1200);

        } else {
            // Kasus data karyawan tidak ditemukan
            const message = data && data.message ? data.message.toUpperCase() : "KARYAWAN TIDAK DITEMUKAN";
            handleErrorAndRecover(message);
        }
    } catch (error) {
        console.error("[Presensi] Kesalahan pencarian karyawan:", error);

        if (error.message === "REQUEST_TIMEOUT") {
            handleErrorAndRecover("SERVER TIDAK MERESPON (TIMEOUT)");
        } else if (error.message === "JSON_INVALID") {
            handleErrorAndRecover("FORMAT RESPON SERVER TIDAK VALID");
        } else {
            handleErrorAndRecover("SERVER BACKEND TIDAK TERHUBUNG");
        }
    }
}

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
 * Menangani penerimaan input ID Karyawan / UID RFID.
 */
function handleEmployeeInput(rawInput) {
    if (currentState !== AppState.IDLE) {
        console.warn(`[Presensi] Input diabaikan: Sistem sedang dalam status ${currentState}`);
        return;
    }

    if (!isCameraReady()) {
        handleErrorAndRecover("KAMERA TIDAK AKTIF / BELUM DIIZINKAN");
        return;
    }

    const cleanId = rawInput.trim();
    if (!cleanId) return;

    console.log(`[Presensi] Input diterima: "${cleanId}"`);
    if (rfidInput) rfidInput.value = "";

    lookupEmployee(cleanId);
}

// Variabel penampung karakter scanner RFID global
let rfidBuffer = "";
let rfidBufferTimer = null;

/**
 * Menginisialisasi pendengar event keyboard dan kartu RFID.
 * Mendukung QinHeng Electronics RFID Reader (Bus 005 Device 002: ID 1a86:dd01).
 */
function initializeInputHandler() {
    // 1. Tangani input langsung pada elemen rfidInput
    if (rfidInput) {
        rfidInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                const cleanVal = rfidInput.value.trim();
                rfidInput.value = "";
                if (cleanVal) handleEmployeeInput(cleanVal);
            }
        });
    }

    // 2. Global Keydown listener untuk menangkap input QinHeng Electronics RFID Reader
    // di mana pun posisi kursor / fokus mouse berada
    document.addEventListener("keydown", (event) => {
        // Jika fokus sedang di input teks lain (misal modal atau form admin), abaikan
        if (event.target !== rfidInput && (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA")) {
            return;
        }

        if (event.key === "Enter") {
            const rawVal = rfidBuffer.trim() || (rfidInput ? rfidInput.value.trim() : "");
            rfidBuffer = "";
            if (rfidInput) rfidInput.value = "";
            if (rawVal) {
                event.preventDefault();
                handleEmployeeInput(rawVal);
            }
            return;
        }

        // Tampung karakter dari reader RFID (kecepatan tinggi)
        if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
            rfidBuffer += event.key;
            clearTimeout(rfidBufferTimer);
            rfidBufferTimer = setTimeout(() => {
                rfidBuffer = "";
            }, 600);
        }
    });

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
 * Mengakses webcam peramban dengan prioritas Logitech Webcam C930e (046d:0843).
 */
async function initializeCamera(retryCount = 0) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        isCameraOnline = false;
        setCameraError("Peramban tidak mendukung akses kamera webcam.");
        return;
    }

    // Bersihkan stream lama jika ada sebelum membuka stream baru
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => {
            try { track.stop(); } catch (e) { }
        });
        mediaStream = null;
    }

    setCameraConnecting(retryCount > 0 ? `Menunggu kamera dilepas oleh sistem (${retryCount}/3)...` : "Menghubungkan kamera...");

    try {
        // Cari kamera Logitech C930e terlebih dahulu
        const preferredDeviceId = await findLogitechOrExternalCameraId();

        const videoConstraints = {
            width: { ideal: 1280 },
            height: { ideal: 720 }
        };
        if (preferredDeviceId) {
            videoConstraints.deviceId = { exact: preferredDeviceId };
        } else {
            videoConstraints.facingMode = "user";
        }

        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
        } catch (exactErr) {
            console.warn("[Presensi] Gagal menggunakan deviceId spesifik, fallback ke kamera standar:", exactErr);
            stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
        }

        mediaStream = stream;
        webcamVideo.srcObject = stream;

        webcamVideo.onloadedmetadata = () => {
            webcamVideo.play().catch(err => {
                console.warn("[Presensi] Peringatan pemutaran video kamera:", err);
            });
            isCameraOnline = true;
            setCameraActive();

            // Tampilkan info kamera aktif pada judul
            try {
                const track = stream.getVideoTracks()[0];
                const trackLabel = track ? track.label : "";
                if (cameraTitle) {
                    if (/c930|logitech/i.test(trackLabel)) {
                        cameraTitle.textContent = "CAMERA PREVIEW (Logitech C930e)";
                    } else if (trackLabel) {
                        cameraTitle.textContent = `CAMERA PREVIEW (${trackLabel.slice(0, 24)})`;
                    }
                }
                console.log(`[Presensi] Feed video kamera aktif: "${trackLabel || 'Standard Camera'}"`);
            } catch (lblErr) { }
        };

        // Deteksi jika kabel kamera terputus
        stream.getVideoTracks().forEach(track => {
            track.onended = () => {
                isCameraOnline = false;
                handleCameraError({ name: "NotFoundError", message: "Kamera terputus" });
            };
        });

    } catch (error) {
        isCameraOnline = false;
        console.error("[Presensi] Kesalahan kamera:", error);

        // Jika kamera terkunci sementara oleh driver sistem, coba ulang hingga 3 kali
        if ((error.name === "NotReadableError" || error.name === "TrackStartError") && retryCount < 3) {
            const delay = 1200 + (retryCount * 500);
            console.log(`[Presensi] Kamera terkunci sistem. Mencoba ulang dalam ${delay}ms (Percobaan ${retryCount + 1}/3)...`);
            setTimeout(() => {
                initializeCamera(retryCount + 1);
            }, delay);
            return;
        }

        handleCameraError(error);
    }
}

/**
 * Memperbarui tampilan antarmuka ke status menghubungkan kamera.
 */
function setCameraConnecting(msg = "Menghubungkan kamera...") {
    if (cameraStatusBadge) {
        cameraStatusBadge.textContent = "MENGHUBUNGKAN...";
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
 * Menangani pesan kesalahan akses kamera.
 */
function handleCameraError(error) {
    let message = "Kendala kamera: " + error.message;

    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
        message = "Izin akses kamera ditolak oleh browser.";
    } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
        message = "Perangkat kamera tidak ditemukan.";
    } else if (error.name === "NotReadableError" || error.name === "TrackStartError") {
        message = "Kamera sedang dipakai aplikasi lain atau belum dilepas sistem.";
    } else if (error.name === "OverconstrainedError") {
        message = "Resolusi kamera tidak didukung perangkat.";
    }

    setCameraError(message);
}

/**
 * Menampilkan pesan kesalahan pada area layar kamera.
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
        statusText.textContent = "KAMERA TIDAK TERSEDIA";
    }
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
});
