"""
Modul Pengambilan Foto Langsung dari Perangkat Kamera Linux V4L2
Mendukung kamera USB seperti Logitech C930e (/dev/v4l/by-id/... atau /dev/video0).
Mengambil frame citra JPEG secara murni menggunakan standar Linux V4L2 & fcntl/mmap
tanpa memerlukan dependensi luar (tanpa OpenCV, tanpa ffmpeg, tanpa sudo).
"""

import fcntl
import mmap
import os
import select
import struct
import threading
import time
from pathlib import Path
from typing import Optional

# Definisi konstanta ioctl V4L2 untuk arsitektur Linux x86_64
def _IOC(dir_val, type_char, nr, size):
    return (dir_val << 30) | (ord(type_char) << 8) | nr | (size << 16)

def _IOR(type_char, nr, size):
    return _IOC(2, type_char, nr, size)

def _IOW(type_char, nr, size):
    return _IOC(1, type_char, nr, size)

def _IOWR(type_char, nr, size):
    return _IOC(3, type_char, nr, size)

def v4l2_fourcc(a, b, c, d):
    return ord(a) | (ord(b) << 8) | (ord(c) << 16) | (ord(d) << 24)

# Konstanta V4L2
V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_MEMORY_MMAP = 1
V4L2_PIX_FMT_MJPEG = v4l2_fourcc('M', 'J', 'P', 'G')  # Logitech C930e Hardware JPEG
V4L2_PIX_FMT_JPEG  = v4l2_fourcc('J', 'P', 'E', 'G')
V4L2_PIX_FMT_YUYV  = v4l2_fourcc('Y', 'U', 'Y', 'V')
V4L2_FIELD_NONE = 1
V4L2_FIELD_ANY = 0

# Ukuran struct pada Linux x86_64
SIZEOF_V4L2_FORMAT = 208
SIZEOF_V4L2_REQUESTBUFFERS = 20
SIZEOF_V4L2_BUFFER = 88

VIDIOC_G_FMT = _IOWR('V', 4, SIZEOF_V4L2_FORMAT)
VIDIOC_S_FMT = _IOWR('V', 5, SIZEOF_V4L2_FORMAT)
VIDIOC_REQBUFS = _IOWR('V', 8, SIZEOF_V4L2_REQUESTBUFFERS)
VIDIOC_QUERYBUF = _IOWR('V', 9, SIZEOF_V4L2_BUFFER)
VIDIOC_QBUF = _IOWR('V', 15, SIZEOF_V4L2_BUFFER)
VIDIOC_DQBUF = _IOWR('V', 17, SIZEOF_V4L2_BUFFER)
VIDIOC_STREAMON = _IOW('V', 18, 4)
VIDIOC_STREAMOFF = _IOW('V', 19, 4)


def find_logitech_device_path() -> str:
    """Mencari jalur ID perangkat kamera Logitech C930e di sistem Linux."""
    by_id_dir = Path("/dev/v4l/by-id")
    if by_id_dir.exists():
        for p in by_id_dir.iterdir():
            name = p.name.lower()
            if "logitech" in name and "video-index0" in name:
                return str(p)
        for p in by_id_dir.iterdir():
            if "video-index0" in p.name.lower():
                return str(p)

    # Fallback ke video0 atau video1
    if Path("/dev/video0").exists():
        return "/dev/video0"
    if Path("/dev/video1").exists():
        return "/dev/video1"

    return "/dev/video0"


def yuyv_to_bmp(yuyv_bytes: bytes, width: int = 1280, height: int = 720) -> bytes:
    """Mengonversi citra mentah YUYV 4:2:2 ke format BMP 24-bit murni tanpa dependensi eksternal."""
    row_stride = ((width * 3 + 3) // 4) * 4
    image_size = row_stride * height
    file_size = 54 + image_size

    header = bytearray(54)
    header[0:2] = b'BM'
    struct.pack_into("<I", header, 2, file_size)
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, -height)  # top-down
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 24)
    struct.pack_into("<I", header, 34, image_size)

    total_pixels = width * height
    out_bgr = bytearray(total_pixels * 3)
    mv = memoryview(yuyv_bytes)

    out_idx = 0
    in_idx = 0
    max_in = min(len(mv), width * height * 2) - 3

    while in_idx < max_in:
        y0 = mv[in_idx]
        u = mv[in_idx + 1] - 128
        y1 = mv[in_idx + 2]
        v = mv[in_idx + 3] - 128
        in_idx += 4

        r_diff = int(1.402 * v)
        g_diff = int(-0.344136 * u - 0.714136 * v)
        b_diff = int(1.772 * u)

        out_bgr[out_idx]     = max(0, min(255, y0 + b_diff))
        out_bgr[out_idx + 1] = max(0, min(255, y0 + g_diff))
        out_bgr[out_idx + 2] = max(0, min(255, y0 + r_diff))

        out_bgr[out_idx + 3] = max(0, min(255, y1 + b_diff))
        out_bgr[out_idx + 4] = max(0, min(255, y1 + g_diff))
        out_bgr[out_idx + 5] = max(0, min(255, y1 + r_diff))

        out_idx += 6

    return bytes(header) + bytes(out_bgr)


def capture_v4l2_frame(device_path: Optional[str] = None, width: int = 1280, height: int = 720) -> Optional[bytes]:
    """
    Mengambil satu frame citra (JPEG atau BMP bytes) langsung dari kamera V4L2.
    """
    path = device_path or find_logitech_device_path()
    if not os.path.exists(path):
        return None

    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK, 0)
    except Exception as e:
        print(f"[V4L2 Debug] Gagal membuka {path}: {e}")
        return None

    try:
        # 1. Coba atur format ke MJPEG
        fmt = bytearray(SIZEOF_V4L2_FORMAT)
        struct.pack_into("=I", fmt, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
        struct.pack_into("=IIII", fmt, 8, width, height, V4L2_PIX_FMT_MJPEG, V4L2_FIELD_NONE)
        try:
            fcntl.ioctl(fd, VIDIOC_S_FMT, fmt)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_S_FMT: {e}")

        # 2. Minta buffer memori
        req = bytearray(SIZEOF_V4L2_REQUESTBUFFERS)
        struct.pack_into("=III", req, 0, 4, V4L2_BUF_TYPE_VIDEO_CAPTURE, V4L2_MEMORY_MMAP)
        try:
            fcntl.ioctl(fd, VIDIOC_REQBUFS, req)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_REQBUFS error: {e}")
            return None

        num_bufs = struct.unpack_from("=I", req, 0)[0]
        if num_bufs == 0:
            return None

        # 3. Query buffer dan petakan memori
        buffers = []
        for i in range(num_bufs):
            buf = bytearray(SIZEOF_V4L2_BUFFER)
            struct.pack_into("=II", buf, 0, i, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
            fcntl.ioctl(fd, VIDIOC_QUERYBUF, buf)

            buf_offset = struct.unpack_from("=I", buf, 64)[0]
            buf_length = struct.unpack_from("=I", buf, 72)[0]

            mm = mmap.mmap(fd, buf_length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=buf_offset)
            buffers.append((mm, buf_length))
            fcntl.ioctl(fd, VIDIOC_QBUF, buf)

        # 4. STREAMON
        buf_type = struct.pack("=I", V4L2_BUF_TYPE_VIDEO_CAPTURE)
        try:
            fcntl.ioctl(fd, VIDIOC_STREAMON, buf_type)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_STREAMON error: {e}")
            return None

        jpeg_data = None
        last_raw_frame = None

        for frame_idx in range(5):
            r, _, _ = select.select([fd], [], [], 2.0)
            if not r:
                break
            buf = bytearray(SIZEOF_V4L2_BUFFER)
            struct.pack_into("=II", buf, 0, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
            fcntl.ioctl(fd, VIDIOC_DQBUF, buf)
            idx = struct.unpack_from("=I", buf, 0)[0]
            bytes_used = struct.unpack_from("=I", buf, 8)[0]

            mm, _ = buffers[idx]
            frame_bytes = bytes(mm[:bytes_used])
            last_raw_frame = frame_bytes

            if len(frame_bytes) > 100 and frame_bytes[:2] == b"\xff\xd8":
                jpeg_data = frame_bytes

            fcntl.ioctl(fd, VIDIOC_QBUF, buf)

        # 5. STREAMOFF
        try:
            fcntl.ioctl(fd, VIDIOC_STREAMOFF, buf_type)
        except Exception:
            pass

        for mm, _ in buffers:
            mm.close()

        if jpeg_data:
            print("[V4L2] Berhasil mendapatkan frame JPEG langsung dari Logitech C930e")
            return jpeg_data

        if last_raw_frame and len(last_raw_frame) >= width * height * 2:
            print("[V4L2] Mengonversi citra mentah YUYV Logitech C930e ke format BMP...")
            bmp_data = yuyv_to_bmp(last_raw_frame, width, height)
            return bmp_data

        return None

    except Exception as e:
        print(f"[V4L2 Debug] Error: {e}")
        return None
    finally:
        os.close(fd)


class CameraStreamer:
    """
    Menyediakan stream MJPEG berkelanjutan dari Logitech C930e (V4L2)
    sehingga browser dapat menampilkan preview live tanpa WebRTC / izin dialog.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.device_path = None
        self.running = False
        self.latest_frame: Optional[bytes] = None
        self.thread: Optional[threading.Thread] = None
        self.width = 1280
        self.height = 720

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = CameraStreamer()
            return cls._instance

    def start(self):
        with self._lock:
            if self.running and self.thread and self.thread.is_alive():
                return
            self.device_path = find_logitech_device_path()
            if not self.device_path or not os.path.exists(self.device_path):
                return
            self.running = True
            self.thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def get_latest_frame(self) -> Optional[bytes]:
        return self.latest_frame

    def _stream_loop(self):
        while self.running:
            fd = None
            buffers = []
            try:
                fd = os.open(self.device_path, os.O_RDWR | os.O_NONBLOCK, 0)
                fmt = bytearray(SIZEOF_V4L2_FORMAT)
                struct.pack_into("=I", fmt, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
                struct.pack_into("=IIII", fmt, 8, self.width, self.height, V4L2_PIX_FMT_MJPEG, V4L2_FIELD_NONE)
                try:
                    fcntl.ioctl(fd, VIDIOC_S_FMT, fmt)
                except Exception:
                    pass

                req = bytearray(SIZEOF_V4L2_REQUESTBUFFERS)
                struct.pack_into("=III", req, 0, 4, V4L2_BUF_TYPE_VIDEO_CAPTURE, V4L2_MEMORY_MMAP)
                fcntl.ioctl(fd, VIDIOC_REQBUFS, req)
                num_bufs = struct.unpack_from("=I", req, 0)[0]
                if num_bufs == 0:
                    time.sleep(1.0)
                    continue

                for i in range(num_bufs):
                    buf = bytearray(SIZEOF_V4L2_BUFFER)
                    struct.pack_into("=II", buf, 0, i, V4L2_BUF_TYPE_VIDEO_CAPTURE)
                    struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
                    fcntl.ioctl(fd, VIDIOC_QUERYBUF, buf)
                    buf_offset = struct.unpack_from("=I", buf, 64)[0]
                    buf_length = struct.unpack_from("=I", buf, 72)[0]
                    mm = mmap.mmap(fd, buf_length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=buf_offset)
                    buffers.append((mm, buf_length))
                    fcntl.ioctl(fd, VIDIOC_QBUF, buf)

                buf_type = struct.pack("=I", V4L2_BUF_TYPE_VIDEO_CAPTURE)
                fcntl.ioctl(fd, VIDIOC_STREAMON, buf_type)
                print("[V4L2 Streamer] Live stream Logitech C930e berhasil aktif")

                while self.running:
                    r, _, _ = select.select([fd], [], [], 0.5)
                    if not r:
                        continue
                    buf = bytearray(SIZEOF_V4L2_BUFFER)
                    struct.pack_into("=II", buf, 0, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
                    struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
                    fcntl.ioctl(fd, VIDIOC_DQBUF, buf)
                    idx = struct.unpack_from("=I", buf, 0)[0]
                    bytes_used = struct.unpack_from("=I", buf, 8)[0]

                    mm, _ = buffers[idx]
                    frame_data = bytes(mm[:bytes_used])
                    if len(frame_data) > 100 and frame_data[:2] == b"\xff\xd8":
                        self.latest_frame = frame_data

                    fcntl.ioctl(fd, VIDIOC_QBUF, buf)
                    time.sleep(0.035)  # ~25-30 fps

                try:
                    fcntl.ioctl(fd, VIDIOC_STREAMOFF, buf_type)
                except Exception:
                    pass

            except Exception as stream_err:
                print(f"[V4L2 Streamer Error] {stream_err}")
                time.sleep(1.0)
            finally:
                for mm, _ in buffers:
                    try:
                        mm.close()
                    except Exception:
                        pass
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass


def capture_image_from_device(output_file: Optional[Path] = None, width: int = 1280, height: int = 720) -> Optional[bytes]:
    """
    Mengambil foto dari kamera Logitech C930e.
    Jika CameraStreamer aktif, mengambil frame realtime yang sedang mengalir (instan 0ms).
    Jika belum, menjalankan capture V4L2 secara langsung.
    """
    streamer = CameraStreamer.get_instance()
    frame = streamer.get_latest_frame()
    if frame and len(frame) > 100:
        if output_file:
            try:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(frame)
            except Exception:
                pass
        return frame

    dev_path = find_logitech_device_path()
    
    # Cara 1: Coba gunakan fswebcam jika tersedia di sistem
    import shutil
    import subprocess
    fswebcam_bin = shutil.which("fswebcam")
    if fswebcam_bin:
        temp_file = output_file or Path("/tmp/attendance_snap.jpg")
        try:
            cmd = [
                fswebcam_bin,
                "-d", dev_path,
                "-r", f"{width}x{height}",
                "--no-banner",
                "-S", "3",
                str(temp_file)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            if res.returncode == 0 and temp_file.exists() and temp_file.stat().st_size > 0:
                data = temp_file.read_bytes()
                return data
        except Exception:
            pass

    # Cara 2: Driver murni Python V4L2 (tanpa dependensi eksternal)
    data = capture_v4l2_frame(dev_path, width, height)
    if data and output_file:
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(data)
        except Exception:
            pass
    return data


if __name__ == "__main__":
    dev = find_logitech_device_path()
    print(f"Perangkat kamera ditemukan: {dev}")
    data = capture_image_from_device(Path("test_capture.jpg"))
    if data:
        print(f"BERHASIL! Foto tersimpan di test_capture.jpg ({len(data)} bytes, format JPEG)")
    else:
        print("Gagal mengambil frame melalui V4L2 / fswebcam")
