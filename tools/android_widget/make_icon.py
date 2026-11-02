"""the launcher icon (96 px PNG, no image library): a dark rounded square with three green rising bars"""
import zlib, struct, sys
N = 96; px = []
for y in range(N):
    row = []
    for x in range(N):
        r = 20; cx = min(max(x, r), N - 1 - r); cy = min(max(y, r), N - 1 - r)
        inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        c = (0, 0, 0, 0)
        if inside:
            c = (22, 27, 34, 255)
            for k, h in enumerate((30, 48, 66)):
                x0 = 18 + k * 22
                if x0 <= x < x0 + 16 and N - 16 - h <= y < N - 16: c = (74, 222, 128, 255)
        row.append(c)
    px.append(row)
raw = b"".join(b"\x00" + bytes(v for c in row for v in c) for row in px)
chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
