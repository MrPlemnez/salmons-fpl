"""Composite an 8-bit RGBA PNG onto white (stdlib only). Used once to make the home-screen icons opaque.
    python3 scripts/flatten_png.py in.png out.png"""
import struct, sys, zlib

def read(path):
    b = open(path, "rb").read()
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    i, idat, w = 8, b"", None
    while i < len(b):
        n, t = struct.unpack(">I4s", b[i:i + 8]); c = b[i + 8:i + 8 + n]; i += 12 + n
        if t == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", c)
            assert depth == 8 and ctype == 6 and inter == 0, (depth, ctype, inter)
        elif t == b"IDAT":
            idat += c
    raw, stride, rows, prev, p = zlib.decompress(idat), w * 4, [], bytearray(w * 4), 0
    for _ in range(h):
        f = raw[p]; line = bytearray(raw[p + 1:p + 1 + stride]); p += 1 + stride
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0; u = prev[x]; c = prev[x - 4] if x >= 4 else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + u) & 255
            elif f == 3: line[x] = (line[x] + (a + u) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(u - c), abs(a - c), abs(a + u - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (u if pb <= pc else c))) & 255
        rows.append(line); prev = line
    return w, h, rows

def write(path, w, h, rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

w, h, rows = read(sys.argv[1])
out = []
for r in rows:
    o = bytearray()
    for x in range(0, len(r), 4):
        a = r[x + 3] / 255
        o += bytes(int(r[x + k] * a + 255 * (1 - a) + 0.5) for k in range(3))
    out.append(o)
write(sys.argv[2], w, h, out)
