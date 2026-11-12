"""Walking pictures: what a map unit looks like while it moves (and while it is selected).

Found for the editor (kit v42) by moving Sigurd and Arden in the Prologue:
  $88:D365  ptr24 x 63: walk set of small sprite 0-62    } compressed ($80:AA02 format); the
  $88:D428  ptr24 x 31: walk set of tall sprite 0-30     } map sprite id picks the set
            ($88:C9C0 / $88:C9F4 unpack it to $7E:AB88 when a unit is picked up).
  A set is 4 directions x 4 steps: left, right, up, down ($07E2 = 0, 8, $10, $18 from the
  d-pad bits $0200, $0100, $0800, $0400; $88:AA30).  The step $07DC counts 0 1 2 3 ($88:C90C).
  Small: 24x24 frames, $140 bytes (10 tiles); $A0 bytes go to VRAM $6200 and $A0 to $6300
  ($88:CA80).  Drawn by the sprite record $88:CC5F: 16x16 tile $20 at (0,0), 16x16 $22 at
  (8,8) (in front), 8x8 $24 at (16,0), 8x8 $34 at (0,16) - the 3x3 grid of 8x8 cells
  20 21 24 / 30 22 23 / 34 32 33; tile $31 (behind $22) is a copy of $22 in every set.  The frame sits on the unit's tile, centred,
  bottom on the tile's bottom.
  Tall: 32x32 frames, $200 bytes (16 tiles), $100 to $6200 and $100 to $6300 ($88:CB43).
  Record $88:CC49: four 16x16 objects $20 $22 / $24 $26.  Each tall sprite also moves its
  frames by a per-step offset: $88:D488 word per tall sprite -> offset into $88:D4C6, pairs of
  signed bytes (x, y) at offset + 2 x step + direction (0, 8, $10, $18) ($88:C939).
A redrawn set is compressed again and goes to the free banks; only its pointer changes.
"""
import os
import re

import fe4lz
from fe4gfx import _fo, _p24, read_png
from fe4sprites import (_decode_tile, _encode_tile, is_tall, parse_sprite, sprite_name, all_ids,
                        indexed_sheet_png, rows_png, palette)

SMALL_TABLE = 0x88D365
TALL_TABLE = 0x88D428
OFFSET_TABLE = 0x88D488
OFFSET_DATA = 0x88D4C6
DIRS = ('left', 'right', 'up', 'down')
STEPS = 4

# (x, y, tile k of the frame) for each 8x8 cell
SMALL_CELLS = [(0, 0, 0), (8, 0, 1), (16, 0, 4),
               (0, 8, 5), (8, 8, 2), (16, 8, 3),
               (0, 16, 9), (8, 16, 7), (16, 16, 8)]
SMALL_HIDDEN = (8, 8, 6)          # tile $31: under $22 (in every game set a copy of it)
TALL_CELLS = [(8 * (i % 4), 8 * (i // 4), k) for i, k in
              enumerate([0, 1, 2, 3, 8, 9, 10, 11, 4, 5, 6, 7, 12, 13, 14, 15])]


def frame_size(sid):
    """(width, height, bytes) of one walking frame."""
    return (32, 32, 0x200) if is_tall(sid) else (24, 24, 0x140)


def sheet_size(sid):
    w, h, _ = frame_size(sid)
    return STEPS * w, len(DIRS) * h


def pointer_at(sid):
    """File offset of the sprite's ptr24."""
    if is_tall(sid):
        return _fo(TALL_TABLE) + 3 * (sid & 0x7FFF)
    return _fo(SMALL_TABLE) + 3 * sid


def set_addr(rom, sid):
    return _p24(rom, pointer_at(sid))


def set_bytes(rom, sid):
    _, _, fb = frame_size(sid)
    data = bytes(fe4lz.decompress(rom, set_addr(rom, sid)))
    return data[:STEPS * len(DIRS) * fb]


def _tile(data, off):
    t = _decode_tile(data[off:off + 32])
    return t if isinstance(t[0], list) else [t[y * 8:y * 8 + 8] for y in range(8)]


def rows_from_bytes(sid, data):
    """Index rows of the whole set: one direction per row (left, right, up, down), steps across."""
    w, h, fb = frame_size(sid)
    W, H = sheet_size(sid)
    rows = [[0] * W for _ in range(H)]
    cells = TALL_CELLS if is_tall(sid) else SMALL_CELLS
    for d in range(len(DIRS)):
        for s in range(STEPS):
            base = (d * STEPS + s) * fb
            X, Y = s * w, d * h
            if not is_tall(sid):
                x0, y0, k = SMALL_HIDDEN
                t = _tile(data, base + 32 * k)
                for y in range(8):
                    rows[Y + y0 + y][X + x0:X + x0 + 8] = t[y]
            for x0, y0, k in cells:
                t = _tile(data, base + 32 * k)
                over = not is_tall(sid) and (x0, y0) == SMALL_HIDDEN[:2]   # drawn over tile $31
                for y in range(8):
                    line = rows[Y + y0 + y]
                    for x in range(8):
                        if t[y][x] or not over:
                            line[X + x0 + x] = t[y][x]
    return rows


def bytes_from_rows(sid, rows):
    w, h, fb = frame_size(sid)
    out = bytearray(STEPS * len(DIRS) * fb)
    cells = TALL_CELLS if is_tall(sid) else SMALL_CELLS
    for d in range(len(DIRS)):
        for s in range(STEPS):
            base = (d * STEPS + s) * fb
            X, Y = s * w, d * h
            for x0, y0, k in cells:
                out[base + 32 * k:base + 32 * k + 32] = _encode_tile(
                    [rows[Y + y0 + y][X + x0:X + x0 + 8] for y in range(8)])
            if not is_tall(sid):           # the game keeps tile $31 a copy of $22
                x0, y0, k = SMALL_HIDDEN
                out[base + 32 * k:base + 32 * k + 32] = out[base + 64:base + 96]
    return bytes(out)


def set_rows(rom, sid):
    return rows_from_bytes(sid, set_bytes(rom, sid))


def offsets(rom, sid):
    """[[(dx, dy) x 4 steps] x 4 directions] the game adds to a tall sprite's frames; small: zeros."""
    if not is_tall(sid):
        return [[(0, 0)] * STEPS for _ in DIRS]
    fo = _fo(OFFSET_TABLE) + 2 * (sid & 0x7FFF)
    base = _fo(OFFSET_DATA) + (rom[fo] | rom[fo + 1] << 8)
    sb = lambda v: v - 256 if v > 127 else v   # noqa: E731
    return [[(sb(rom[base + 8 * d + 2 * s]), sb(rom[base + 8 * d + 2 * s + 1])) for s in range(STEPS)]
            for d in range(len(DIRS))]


def rows_from_png(sid, data, pal):
    """Index rows from a PNG of the whole set (96x96 on foot, 128x128 mounted / flying).  Colours go
    to the nearest of the player's map palette; transparent pixels to colour 0."""
    W, H = sheet_size(sid)
    w, h, _ = frame_size(sid)
    pw, ph, px = read_png(data)
    if (pw, ph) != (W, H):
        raise ValueError(f'walking pictures for this sprite are {STEPS} steps of {w}x{h} across and the '
                         f'{len(DIRS)} directions (left, right, up, down) down: {W}x{H} pixels '
                         f'(this picture is {pw}x{ph})')
    cache = {}

    def near(rgb):
        if rgb not in cache:
            r, g, b = rgb
            cache[rgb] = min(range(1, 16), key=lambda i: 3 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2
                             + 2 * (pal[i][2] - b) ** 2)
        return cache[rgb]
    return [[0 if px[y * pw + x][3] < 128 else near(px[y * pw + x][:3]) for x in range(pw)] for y in range(ph)]


def walk_file(sid):
    return 'sprites/walk_%s%02d.png' % ('t' if is_tall(sid) else 's', sid & 0x7FFF)


def apply(rom, proj, far):
    """sprites/walk_sNN.png and walk_tNN.png: each set is compressed into the free banks."""
    folder = os.path.join(proj, 'sprites')
    if not os.path.isdir(folder):
        return 0
    n = 0
    pal = palette(rom, 0)
    for f in sorted(os.listdir(folder)):
        m = re.fullmatch(r'walk_([st])(\d{2})\.png', f, re.I)
        if not m:
            continue
        path = os.path.join(folder, f)
        try:
            sid = parse_sprite(m.group(1).upper() + str(int(m.group(2))))
            rows = rows_from_png(sid, open(path, 'rb').read(), pal)
        except ValueError as e:
            raise SystemExit(f'{path}: {e}')
        data = fe4lz.compress(bytes_from_rows(sid, rows))
        a = far.alloc(len(data))
        rom[a:a + len(data)] = data                       # banks $70-$7D: snes == file
        rom[pointer_at(sid):pointer_at(sid) + 3] = a.to_bytes(3, 'little')
        n += 1
    return n


__all__ = ['DIRS', 'STEPS', 'frame_size', 'sheet_size', 'set_rows', 'rows_from_bytes', 'bytes_from_rows',
           'offsets', 'rows_from_png', 'walk_file', 'apply', 'indexed_sheet_png', 'rows_png', 'all_ids',
           'sprite_name']
