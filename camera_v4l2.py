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

# Konstanta V4L2
V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_MEMORY_MMAP = 1
V4L2_PIX_FMT_MJPEG = 0x4745504A  # b'MJPG'
V4L2_PIX_FMT_YUYV = 0x56595559   # b'YUYV'
V4L2_FIELD_NONE = 1

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


def capture_v4l2_frame(device_path: Optional[str] = None, width: int = 1280, height: int = 720) -> Optional[bytes]:
    """
    Mengambil satu frame citra (JPEG bytes) langsung dari kamera V4L2.
    """
    path = device_path or find_logitech_device_path()
    if not os.path.exists(path):
        return None

    try:
        # Buka perangkat V4L2 dalam mode baca/tulis non-blocking
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK, 0)
    except Exception as e:
        print(f"[V4L2 Debug] Gagal membuka {path}: {e}")
        return None

    try:
        # 1. Atur Format Citra ke MJPEG (Motion JPEG)
        fmt = bytearray(SIZEOF_V4L2_FORMAT)
        struct.pack_into("=I", fmt, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
        # pix_format: width(I), height(I), pixelformat(I), field(I)
        struct.pack_into("=IIII", fmt, 8, width, height, V4L2_PIX_FMT_MJPEG, V4L2_FIELD_NONE)
        try:
            fcntl.ioctl(fd, VIDIOC_S_FMT, fmt)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_S_FMT: {e}")

        # 2. Minta buffer memori (request buffers)
        req = bytearray(SIZEOF_V4L2_REQUESTBUFFERS)
        struct.pack_into("=III", req, 0, 4, V4L2_BUF_TYPE_VIDEO_CAPTURE, V4L2_MEMORY_MMAP)
        try:
            fcntl.ioctl(fd, VIDIOC_REQBUFS, req)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_REQBUFS error: {e}")
            return None

        num_bufs = struct.unpack_from("=I", req, 0)[0]
        if num_bufs == 0:
            print("[V4L2 Debug] num_bufs is 0")
            return None

        # 3. Query buffer dan petakan memori (mmap)
        buffers = []
        for i in range(num_bufs):
            buf = bytearray(SIZEOF_V4L2_BUFFER)
            struct.pack_into("=II", buf, 0, i, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
            fcntl.ioctl(fd, VIDIOC_QUERYBUF, buf)

            # Pada kernel Linux 64-bit (x86_64):
            # union m.offset berada di byte 64
            # length berada di byte 72
            buf_offset = struct.unpack_from("=I", buf, 64)[0]
            buf_length = struct.unpack_from("=I", buf, 72)[0]
            print(f"[V4L2 Debug] Buffer {i}: length={buf_length}, offset={buf_offset}")

            mm = mmap.mmap(fd, buf_length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=buf_offset)
            buffers.append((mm, buf_length))
            # Antrikan buffer (QBUF)
            fcntl.ioctl(fd, VIDIOC_QBUF, buf)

        # 4. Aktifkan aliran video (STREAMON)
        buf_type = struct.pack("=I", V4L2_BUF_TYPE_VIDEO_CAPTURE)
        try:
            fcntl.ioctl(fd, VIDIOC_STREAMON, buf_type)
        except Exception as e:
            print(f"[V4L2 Debug] VIDIOC_STREAMON error: {e}")
            return None

        jpeg_data = None
        # Buang beberapa frame awal agar auto-exposure & white balance kamera stabil
        for frame_idx in range(5):
            r, _, _ = select.select([fd], [], [], 2.0)
            if not r:
                print(f"[V4L2 Debug] Frame {frame_idx} select timeout")
                break
            buf = bytearray(SIZEOF_V4L2_BUFFER)
            struct.pack_into("=II", buf, 0, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            struct.pack_into("=I", buf, 60, V4L2_MEMORY_MMAP)
            fcntl.ioctl(fd, VIDIOC_DQBUF, buf)
            idx = struct.unpack_from("=I", buf, 0)[0]
            bytes_used = struct.unpack_from("=I", buf, 8)[0]
            print(f"[V4L2 Debug] Frame {frame_idx}: idx={idx}, bytes_used={bytes_used}")

            mm, _ = buffers[idx]
            frame_bytes = mm[:bytes_used]
            if len(frame_bytes) > 100 and frame_bytes[:2] == b"\xff\xd8":
                jpeg_data = bytes(frame_bytes)

            fcntl.ioctl(fd, VIDIOC_QBUF, buf)

        # 5. Hentikan aliran video (STREAMOFF)
        try:
            fcntl.ioctl(fd, VIDIOC_STREAMOFF, buf_type)
        except Exception:
            pass

        # Bersihkan mmap
        for mm, _ in buffers:
            mm.close()

        if not jpeg_data:
            print("[V4L2 Debug] Tidak ada JPEG SOI header b'\\xff\\xd8' yang ditemukan pada buffer")

        return jpeg_data

    except Exception as e:
        print(f"[V4L2 Debug] Error tak terduga: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        os.close(fd)


def capture_image_from_device(output_file: Optional[Path] = None, width: int = 1280, height: int = 720) -> Optional[bytes]:
    """
    Mengambil foto dari kamera Logitech C930e.
    Mendukung fswebcam jika tersedia, atau otomatis fallback ke driver internal V4L2.
    """
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
