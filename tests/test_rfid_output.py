import sys
import time

print("=" * 60)
print("   PENGUJIAN OUTPUT 2 PERANGKAT RFID (TANPA SUDO)")
print("=" * 60)
print("\n[LANGKAH 1] Silakan TAP kartu di Reader QINHENG (untuk IN):")
sys.stdout.flush()

start_1 = time.time()
q_input = sys.stdin.readline().strip()
dur_1 = time.time() - start_1

print(f" -> Output QinHeng : '{q_input}'")
print(f" -> Panjang        : {len(q_input)} karakter")
print(f" -> Karakteristik  : IsDigit={q_input.isdigit()}, HexOnly={all(c in '0123456789abcdefABCDEF' for c in q_input)}")

print("\n" + "-" * 60)
print("[LANGKAH 2] Silakan TAP kartu di Reader SYCREADER (untuk OUT):")
sys.stdout.flush()

start_2 = time.time()
s_input = sys.stdin.readline().strip()
dur_2 = time.time() - start_2

print(f" -> Output Sycreader: '{s_input}'")
print(f" -> Panjang         : {len(s_input)} karakter")
print(f" -> Karakteristik   : IsDigit={s_input.isdigit()}, HexOnly={all(c in '0123456789abcdefABCDEF' for c in s_input)}")

print("\n" + "=" * 60)
if q_input == s_input:
    print("HASIL: Kedua reader menghasilkan teks yang persis sama.")
    print("Kita perlu cek apakah user debian punya izin di group input:")
else:
    print(f"HASIL: Kedua reader menghasilkan teks BERBEDA! ({len(q_input)} chars vs {len(s_input)} chars)")
    print("Sistem bisa membedakan IN vs OUT 100% otomatis lewat karakteristik teks tanpa perlu sudo!")
print("=" * 60)
