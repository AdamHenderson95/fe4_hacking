"""Pictures from the ROM for the editors: character portraits (48x64, PNG).

Portraits (found for the editor; the status screen loads them at $8A:B369):
  $8B:9A88   word per character ID - 1: portrait number (243 = none / chosen at run time)
  $8A:B4F9   ptr24 per portrait number (248 of them): compressed tiles ($80:AA02 format, fe4lz)
  $8A:B7E1   ptr24 per portrait number: 16-colour palette (raw, colour 0 = transparent)
The 64 tiles decompress as a 16-tile-wide block: the face is tiles 0-5 of rows 0-3 (top half)
and tiles 6-11 of rows 0-3 (bottom half); tiles 12-15 are mouth and eye frames.
"""
import struct
import zlib

from cpu65816 import CPU

PORTRAIT_COUNT = 248
NO_PORTRAIT = 243


def _fo(snes):
    """File offset of a HiROM address (banks $80-$FF and $40-$7D)."""
    b = snes >> 16
    if b >= 0xC0:
        return ((b - 0xC0) << 16) | (snes & 0xFFFF)
    if b >= 0x80:
        return ((b - 0x80) << 16) | (snes & 0xFFFF)
    return 0x400000 + ((b - 0x40) << 16) + (snes & 0xFFFF)


def _p24(rom, fo):
    return rom[fo] | rom[fo + 1] << 8 | rom[fo + 2] << 16


def portrait_of_char(rom, char_id):
    """Portrait number for a character ID (1-768), or None."""
    if not 1 <= char_id <= 768:
        return None
    o = 0x0B9A88 + 2 * (char_id - 1)
    n = rom[o] | rom[o + 1] << 8
    return n if n < PORTRAIT_COUNT and n != NO_PORTRAIT else None


def png(width, height, rgba_rows):
    """Minimal PNG writer: rgba_rows = list of bytes (width*4 each)."""
    raw = b''.join(b'\x00' + bytes(r) for r in rgba_rows)

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def _palette(rom, fo):
    out = []
    for i in range(16):
        c = rom[fo + 2 * i] | rom[fo + 2 * i + 1] << 8
        r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
        out.append((r * 255 // 31, g * 255 // 31, b * 255 // 31, 0 if i == 0 else 255))
    return out


def _tile(data, t):
    b = data[t * 32:t * 32 + 32]
    rows = []
    for y in range(8):
        p0, p1, p2, p3 = b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[17 + 2 * y]
        rows.append([((p0 >> s) & 1) | ((p1 >> s) & 1) << 1 | ((p2 >> s) & 1) << 2 | ((p3 >> s) & 1) << 3
                     for s in range(7, -1, -1)])
    return rows


def decompress(rom, src):
    """The game's decompressor through its $80:AA02 entry (the one the portrait code uses; unlike
    $80:A9F2 it handles streams in the lower half of a HiROM bank)."""
    c = CPU(rom)
    c.wram[0xC8], c.wram[0xC9], c.wram[0xCA] = src & 0xFF, (src >> 8) & 0xFF, src >> 16
    c.wram[0xCB] = c.wram[0xCC] = 0
    c.wram[0xCD] = 0x7F
    c.P, c.DB, c.D, c.S = 0x34, 0x80, 0, 0x1FF
    top = [0]
    orig = c.write

    def track(addr, v):
        if (addr >> 16) & 0xFF == 0x7F and (addr & 0xFFFF) >= top[0]:
            top[0] = (addr & 0xFFFF) + 1
        orig(addr, v)
    c.write = track
    c.call(0x80AA02, long=True, max_steps=20_000_000)
    return bytes(c.wram[0x10000:0x10000 + top[0]])


_cache = {}


def portrait_png(rom, n, scale=1):
    """PNG bytes of portrait n (48x64 times scale), or None."""
    key = (id(rom), n, scale)
    if key in _cache:
        return _cache[key]
    if not 0 <= n < PORTRAIT_COUNT or n == NO_PORTRAIT:
        return None
    try:
        src = _p24(rom, 0x0AB4F9 + 3 * n)
        pal = _palette(rom, _fo(_p24(rom, 0x0AB7E1 + 3 * n)))
        data = decompress(rom, src)
    except Exception:          # noqa: BLE001 - a hack may have changed the tables
        return None
    if len(data) < 64 * 32:
        data = bytes(data) + bytes(64 * 32 - len(data))
    pix = [[0] * 48 for _ in range(64)]
    for half in range(2):
        for ty in range(4):
            for tx in range(6):
                t = ty * 16 + tx + 6 * half
                tile = _tile(data, t)
                for y in range(8):
                    pix[half * 32 + ty * 8 + y][tx * 8:tx * 8 + 8] = tile[y]
    rows = []
    for y in range(64):
        row = bytearray()
        for x in range(48):
            row += bytes(pal[pix[y][x]]) * scale
        for _ in range(scale):
            rows.append(row)
    out = png(48 * scale, 64 * scale, rows)
    _cache[key] = out
    return out


# ---------------------------------------------------------------- map tiles
def map_atlas(rom, ch):
    """(PNG bytes of chapter ch's 1024 metatiles as a 32x32 grid of 16x16 tiles, terrain id per metatile).

    Same drawing as fe4maps.Renderer, without Pillow."""
    import fe4lz
    import fe4maps
    from dis65816 import snes_to_file
    key = (id(rom), 'atlas', ch)
    if key in _cache:
        return _cache[key]
    rom = bytes(rom)
    hd = fe4maps.header(rom, ch)
    meta = fe4lz.decompress(rom, hd['meta'])[:0x800].ljust(0x800, b'\0')
    fo = snes_to_file(fe4maps.SHARED_META)
    meta += rom[fo:fo + 0x1800]
    meta = [meta[i] | meta[i + 1] << 8 for i in range(0, 0x2000, 2)]
    vram = bytearray(rom[fe4maps.SHARED_TILES:fe4maps.SHARED_TILES + 0x5000])
    vram += fe4lz.decompress(rom, hd['tiles'])[:0x1000].ljust(0x1000, b'\0')
    vram += bytes(32)
    pfo = snes_to_file(hd['pal'])
    cg = bytes(fe4maps.PAL0) + rom[pfo:pfo + 224]
    pal = []
    for k in range(128):
        v = cg[2 * k] | cg[2 * k + 1] << 8
        pal.append(bytes(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31, 255)))
    try:
        terrain = list(fe4lz.decompress(rom, hd['terrain'])[:1024].ljust(1024, b'\0'))
    except Exception:          # noqa: BLE001
        terrain = [0] * 1024
    tiles = {}
    W = 32 * 16
    pix = [bytearray(W * 4) for _ in range(W)]
    for k in range(1024):
        bx, by = (k % 32) * 16, (k // 32) * 16
        for q in range(4):
            e = meta[k * 4 + q]
            n = e & 0x3FF
            if n not in tiles:
                tiles[n] = _tile(vram, n) if n * 32 + 32 <= len(vram) else [[0] * 8] * 8
            t = tiles[n]
            p = ((e >> 10) & 7) * 16
            hf, vf = e & 0x4000, e & 0x8000
            ox, oy = bx + (q // 2) * 8, by + (q % 2) * 8
            for y in range(8):
                src = t[7 - y if vf else y]
                if hf:
                    src = src[::-1]
                row = pix[oy + y]
                row[ox * 4:(ox + 8) * 4] = b''.join(pal[(p + c) % 128] for c in src)
    out = (png(W, W, pix), terrain)
    _cache[key] = out
    return out


# ---------------------------------------------------------------- portrait sheets (import / export)
# A portrait sheet is 80x64: the 48x64 face at the left, and the two talking-mouth frames (32x16
# each) at x 48, y 0 and y 16.  The game draws a frame over the face's 32x16 block at (0, 32)
# (face tiles 0-3 of the bottom half's first two rows) while the person speaks.
SHEET_W, SHEET_H = 80, 64
MOUTH = (0, 32, 32, 16)          # x, y, w, h on the face


def _sheet_tile_xy(t):
    """Top-left pixel on the sheet of decompressed tile t (16 wide x 4 high block)."""
    col, row = t % 16, t // 16
    if col < 6:
        return col * 8, row * 8
    if col < 12:
        return (col - 6) * 8, 32 + row * 8
    return 48 + (col - 12) * 8, row * 8


def portrait_sheet(rom, n):
    """(indices: list of 80*64 ints, palette: 16 (r, g, b)) of portrait n from the ROM, or None."""
    if not 0 <= n < PORTRAIT_COUNT or n == NO_PORTRAIT:
        return None
    try:
        src = _p24(rom, 0x0AB4F9 + 3 * n)
        pal = _palette(rom, _fo(_p24(rom, 0x0AB7E1 + 3 * n)))
        data = decompress(rom, src)
    except Exception:          # noqa: BLE001
        return None
    data = bytes(data).ljust(64 * 32, b'\0')
    idx = [0] * (SHEET_W * SHEET_H)
    for t in range(64):
        x0, y0 = _sheet_tile_xy(t)
        tile = _tile(data, t)
        for y in range(8):
            idx[(y0 + y) * SHEET_W + x0:(y0 + y) * SHEET_W + x0 + 8] = tile[y]
    return idx, [p[:3] for p in pal]


def sheet_tiles(idx):
    """The 64 tiles (2048 bytes, 4bpp SNES planar) for an 80x64 index sheet."""
    out = bytearray(64 * 32)
    for t in range(64):
        x0, y0 = _sheet_tile_xy(t)
        for y in range(8):
            row = idx[(y0 + y) * SHEET_W + x0:(y0 + y) * SHEET_W + x0 + 8]
            for plane in range(4):
                v = 0
                for x, c in enumerate(row):
                    if c >> plane & 1:
                        v |= 0x80 >> x
                out[t * 32 + (plane >> 1) * 16 + 2 * y + (plane & 1)] = v
    return bytes(out)


def snes_color(rgb):
    r, g, b = ((v * 31 + 127) // 255 for v in rgb[:3])
    return r | g << 5 | b << 10


def palette_bytes(pal):
    out = bytearray()
    for i in range(16):
        c = snes_color(pal[i]) if i < len(pal) else 0
        out += bytes([c & 0xFF, c >> 8])
    return bytes(out)


def indexed_png(w, h, idx, pal, scale=1):
    """An 8-bit palette PNG (colour 0 transparent)."""
    rows = []
    for y in range(h):
        row = bytes(idx[y * w:(y + 1) * w])
        if scale > 1:
            row = bytes(c for c in row for _ in range(scale))
        rows += [row] * scale
    raw = b''.join(b'\x00' + r for r in rows)

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
    plte = b''.join(bytes(p[:3]) for p in pal[:16]).ljust(48, b'\0')
    trns = b'\x00' + b'\xff' * 15
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w * scale, h * scale, 8, 3, 0, 0, 0))
            + chunk(b'PLTE', plte) + chunk(b'tRNS', trns) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def read_png(data):
    """(width, height, [(r, g, b, a)] per pixel) for 8-bit PNGs of any colour type, and 1/2/4-bit
    palette or grey ones (not interlaced)."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG file')
    pos, idat, plte, trns = 8, b'', None, None
    w = h = depth = ctype = None
    while pos < len(data):
        n = struct.unpack('>I', data[pos:pos + 4])[0]
        t, d = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', d)
            if inter:
                raise ValueError('interlaced PNGs are not supported; save it without interlacing')
        elif t == b'PLTE':
            plte = [tuple(d[i:i + 3]) for i in range(0, len(d), 3)]
        elif t == b'tRNS':
            trns = d
        elif t == b'IDAT':
            idat += d
        elif t == b'IEND':
            break
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    if depth == 16 or (depth < 8 and ctype not in (0, 3)):
        raise ValueError('save the PNG with 8 bits per channel')
    bpp = max(1, chans * depth // 8)
    stride = (w * chans * depth + 7) // 8
    raw = zlib.decompress(idat)
    prev = bytearray(stride)
    px = []
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        prev = line
        if depth < 8:
            per = 8 // depth
            vals = [(line[x // per] >> (8 - depth * (x % per + 1))) & ((1 << depth) - 1) for x in range(w)]
        else:
            vals = None
        for x in range(w):
            if ctype == 3:
                i = vals[x] if vals else line[x]
                r, g, b = plte[i]
                px.append((r, g, b, trns[i] if trns and i < len(trns) else 255))
            elif ctype == 0:
                v = vals[x] * 255 // ((1 << depth) - 1) if vals else line[x]
                px.append((v, v, v, 255))
            elif ctype == 4:
                px.append((line[2 * x], line[2 * x], line[2 * x], line[2 * x + 1]))
            elif ctype == 2:
                r, g, b = line[3 * x:3 * x + 3]
                a = 0 if trns and len(trns) >= 6 and (r, g, b) == (trns[1], trns[3], trns[5]) else 255
                px.append((r, g, b, a))
            else:
                px.append(tuple(line[4 * x:4 * x + 4]))
    return w, h, px


def sheet_from_png(data):
    """(indices 80x64, palette 16 rgb) from a portrait sheet PNG: 80x64, or 48x64 (no talking frames:
    the mouth stays still).  Transparent pixels become colour 0; at most 15 other colours (as the
    SNES sees them, 5 bits per channel)."""
    w, h, px = read_png(data)
    if (w, h) not in ((80, 64), (48, 64)):
        raise ValueError(f'a portrait is 48x64 (face) or 80x64 (face + two mouth frames); this one is {w}x{h}')
    cols, idx = [], []
    for r, g, b, a in px:
        if a < 128:
            idx.append(0)
            continue
        c = snes_color((r, g, b))
        if c not in cols:
            cols.append(c)
            if len(cols) > 15:
                raise ValueError('a portrait has at most 15 colours plus transparency; this one has more '
                                 '(the editor\'s Replace button reduces colours for you)')
        idx.append(cols.index(c) + 1)
    if w == 48:
        idx = [v for y in range(64) for v in idx[y * 48:(y + 1) * 48] + [0] * 32]
        mx, my, mw, mh = MOUTH
        for f in range(2):
            for y in range(mh):
                for x in range(mw):
                    idx[(f * 16 + y) * SHEET_W + 48 + x] = idx[(my + y) * SHEET_W + mx + x]
    pal = [(0, 0, 0)] + [((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31) for c in cols]
    pal += [(0, 0, 0)] * (16 - len(pal))
    return idx, pal


def face_png(idx, pal, scale=1):
    """RGBA PNG of the 48x64 face from a sheet."""
    rgba = [bytes((0, 0, 0, 0))] + [bytes(tuple(p[:3]) + (255,)) for p in pal[1:16]]
    rows = []
    for y in range(64):
        row = b''.join(rgba[idx[y * SHEET_W + x]] * scale for x in range(48))
        rows += [row] * scale
    return png(48 * scale, 64 * scale, rows)


def apply_portraits(rom, folder, far):
    """Write portraits/pNNN.png (portrait number NNN) into the ROM: tiles compressed in far space,
    palette next to them, both pointers repointed.  Returns the number of portraits written."""
    import os
    import re
    import fe4lz
    if not os.path.isdir(folder):
        return 0
    n = 0
    for f in sorted(os.listdir(folder)):
        m = re.fullmatch(r'p(\d{3})\.png', f, re.I)
        if not m:
            continue
        num = int(m.group(1))
        where = os.path.join(folder, f)
        if not 0 <= num < PORTRAIT_COUNT or num == NO_PORTRAIT:
            raise SystemExit(f'{where}: portrait numbers are 0-{PORTRAIT_COUNT - 1} (not {NO_PORTRAIT})')
        try:
            idx, pal = sheet_from_png(open(where, 'rb').read())
        except (ValueError, zlib.error, struct.error, KeyError) as e:
            raise SystemExit(f'{where}: {e}')
        data = fe4lz.compress(sheet_tiles(idx))
        a = far.alloc(len(data) + 1)
        rom[_fo(a):_fo(a) + len(data)] = data
        pa = far.alloc(32)
        rom[_fo(pa):_fo(pa) + 32] = palette_bytes(pal)
        rom[0x0AB4F9 + 3 * num:0x0AB4F9 + 3 * num + 3] = a.to_bytes(3, 'little')
        rom[0x0AB7E1 + 3 * num:0x0AB7E1 + 3 * num + 3] = pa.to_bytes(3, 'little')
        n += 1
    return n
