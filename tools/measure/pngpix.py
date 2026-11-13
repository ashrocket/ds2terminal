"""pngpix.py - stdlib PNG reader for 8-bit RGB/RGBA (non-interlaced). Prints pixel samples.
usage: python3 -I pngpix.py FILE.png [x,y ...]   (no points: size + 5x5 grid of samples)"""
import struct, sys, zlib

def read_png(path):
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    pos, idat, w = 8, b'', None
    while pos < len(data):
        n, typ = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if typ == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', body)
            assert depth == 8 and ctype in (2, 6) and inter == 0, (depth, ctype, inter)
            bpp = 3 if ctype == 2 else 4
        elif typ == b'IDAT':
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        rows.append(bytes(line)); prev = line
    return w, h, bpp, rows

def pixel(img, x, y):
    w, h, bpp, rows = img
    o = x * bpp
    return '#%02x%02x%02x' % tuple(rows[y][o:o + 3])

if __name__ == '__main__':
    img = read_png(sys.argv[1])
    w, h = img[0], img[1]
    print('size', w, h)
    pts = [tuple(int(v) for v in a.split(',')) for a in sys.argv[2:]]
    if not pts:
        pts = [(int(w * fx / 6), int(h * fy / 6)) for fy in range(1, 6) for fx in range(1, 6)]
    for x, y in pts:
        print(x, y, pixel(img, x, y))
