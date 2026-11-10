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
