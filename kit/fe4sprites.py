"""Map sprites: the little units standing on the chapter map, which one each class uses, and their
drawings.

Found for the editor (kit v23):
  $88:D526  ptr24 x 63: small sprites (id 0-62): 3 frames of 16x16, 0x80 bytes each (tiles TL TR BL BR,
            4bpp), raw.  The map shows frames 0 1 2 1 ($88:DC20).
  $88:D5E3  ptr24 x 31: tall sprites (id $8000-$801E, mounted and flying units): 3 frames of 16x24,
            0xC0 bytes each.  Tiles 0-1 are the middle row, 2-3 the bottom row, 4-5 the top row.
            ($88:DC8B uploads 0x40 to VRAM $6E00 and 0x80 to $6F00.)
  $83:805E  word per class: offset (+$805E, bank $83) of the class's list of 5-byte entries
            [character word][gender][sprite word]; gender $FF ends the list and its sprite is the
            default.  An entry matches when gender equals the unit's (ROM record +18: 0 male,
            1 female) and its character is 0 (anyone) or the unit's character ID ($84:A84A).
  $8C:9520  sprite palettes, 16 colours each: +$00 player (blue), +$20 enemy (red), +$40 ally
            (green), +$60 other (yellow), +$C0 grey (units that have moved).  The colour numbers mean
            the same in every palette, so a drawing is stored once in the player's colours.
A class list that grows moves to the free end of bank $83 (the offsets are 16-bit in that bank).
"""
import csv
import os
import re

from fe4gfx import _fo, _p24, png, read_png

SMALL_TABLE, SMALL_COUNT = 0x88D526, 63
TALL_TABLE, TALL_COUNT = 0x88D5E3, 31
CLASS_TABLE = 0x83805E
PALETTES = 0x8C9520
ARMIES = [('player', 0x00), ('enemy', 0x20), ('ally', 0x40), ('other', 0x60), ('moved', 0xC0)]
TALL = 0x8000
FIELDS = ['class', '_class_name', 'entry', 'gender', 'character', '_character_name', 'sprite']


def is_tall(sid):
    return bool(sid & TALL)


def all_ids():
    return list(range(SMALL_COUNT)) + [TALL | n for n in range(TALL_COUNT)]


def sprite_name(sid):
    return ('T%d' if is_tall(sid) else 'S%d') % (sid & 0x7FFF)


def parse_sprite(text):
    """'S12' / 'T3' (or a number, $8000 = tall) -> sprite id."""
    t = text.strip().upper()
    m = re.fullmatch(r'([ST])(\d+)', t)
    if m:
        n = int(m.group(2))
        if m.group(1) == 'S':
            if not 0 <= n <= SMALL_COUNT:     # S63 (one civilian in the game) reads T0's data as small
                raise ValueError(f'small sprites are S0-S{SMALL_COUNT - 1}')
            return n
        if not 0 <= n < TALL_COUNT:
            raise ValueError(f'tall sprites are T0-T{TALL_COUNT - 1}')
        return TALL | n
    n = int(t, 0)
    if n not in all_ids() and n != SMALL_COUNT:
        raise ValueError(f'{text}: not a sprite (S0-S{SMALL_COUNT - 1}, T0-T{TALL_COUNT - 1})')
    return n


def size(sid):
    """(width, height, bytes per frame)."""
    return (16, 24, 0xC0) if is_tall(sid) else (16, 16, 0x80)


def data_addr(rom, sid):
    if is_tall(sid):
        return _p24(rom, _fo(TALL_TABLE) + 3 * (sid & 0x7FFF))
    return _p24(rom, _fo(SMALL_TABLE) + 3 * sid)


# tile k of a frame -> (x, y) in the frame
SMALL_LAYOUT = [(0, 0), (8, 0), (0, 8), (8, 8)]
TALL_LAYOUT = [(0, 8), (8, 8), (0, 16), (8, 16), (0, 0), (8, 0)]


def _decode_tile(b):
    out = []
    for y in range(8):
        p = [b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[17 + 2 * y]]
        out.append([((p[0] >> (7 - x)) & 1) | ((p[1] >> (7 - x)) & 1) << 1 | ((p[2] >> (7 - x)) & 1) << 2
                    | ((p[3] >> (7 - x)) & 1) << 3 for x in range(8)])
    return out


def _encode_tile(px):
    out = bytearray(32)
    for y in range(8):
        for plane in range(4):
            v = 0
            for x in range(8):
                if px[y][x] >> plane & 1:
                    v |= 0x80 >> x
            out[(plane >> 1) * 16 + 2 * y + (plane & 1)] = v
    return bytes(out)


def frames_from_bytes(sid, data):
    """Index sheet (list of rows) 48 wide: the three frames side by side."""
    w, h, fb = size(sid)
    lay = TALL_LAYOUT if is_tall(sid) else SMALL_LAYOUT
    rows = [[0] * (3 * w) for _ in range(h)]
    for f in range(3):
        for k, (x0, y0) in enumerate(lay):
            t = _decode_tile(data[f * fb + 32 * k:f * fb + 32 * k + 32])
            for y in range(8):
                rows[y0 + y][f * w + x0:f * w + x0 + 8] = t[y]
    return rows


def bytes_from_frames(sid, rows):
    w, h, fb = size(sid)
    lay = TALL_LAYOUT if is_tall(sid) else SMALL_LAYOUT
    out = bytearray()
    for f in range(3):
        for x0, y0 in lay:
            out += _encode_tile([rows[y0 + y][f * w + x0:f * w + x0 + 8] for y in range(8)])
    return bytes(out)


def sprite_rows(rom, sid):
    w, h, fb = size(sid)
    a = _fo(data_addr(rom, sid))
    return frames_from_bytes(sid, rom[a:a + 3 * fb])


def palette(rom, army=0):
    """16 (r, g, b) for an army's palette offset (see ARMIES)."""
    fo = _fo(PALETTES) + army
    out = []
    for i in range(16):
        c = rom[fo + 2 * i] | rom[fo + 2 * i + 1] << 8
        out.append(((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31))
    return out


def rows_png(rows, pal, scale=1):
    """RGBA PNG; colour 0 transparent."""
    out = []
    for r in rows:
        line = b''.join((bytes(pal[c]) + b'\xff' if c else b'\0\0\0\0') * scale for c in r)
        out += [line] * scale
    return png(len(rows[0]) * scale, len(rows) * scale, out)


def indexed_sheet_png(rows, pal):
    """8-bit palette PNG of a sheet (for editing elsewhere; colour 0 transparent)."""
    import fe4gfx
    w, h = len(rows[0]), len(rows)
    return fe4gfx.indexed_png(w, h, [c for r in rows for c in r], pal)


def rows_from_png(sid, data, pal):
    """Index rows from a PNG of the 3 frames side by side (48x16 or 48x24).  Each colour goes to the
    nearest colour of the player's palette; transparent pixels to colour 0."""
    w, h, _ = size(sid)
    pw, ph, px = read_png(data)
    if (pw, ph) != (3 * w, h):
        raise ValueError(f'this sprite is three {w}x{h} frames side by side: {3 * w}x{h} pixels '
                         f'(this picture is {pw}x{ph})')
    cache = {}

    def near(rgb):
        if rgb not in cache:
            r, g, b = rgb
            cache[rgb] = min(range(1, 16), key=lambda i: 3 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2
                             + 2 * (pal[i][2] - b) ** 2)
        return cache[rgb]
    return [[0 if px[y * pw + x][3] < 128 else near(px[y * pw + x][:3]) for x in range(pw)] for y in range(ph)]


# ---------------------------------------------------------------- class lists
def class_count(rom):
    """Classes with a sprite list: until the word offsets stop pointing just past the table."""
    fo = _fo(CLASS_TABLE)
    first = rom[fo] | rom[fo + 1] << 8
    return first // 2


def class_list(rom, c):
    """[(character, gender, sprite)], the last with gender 0xFF (the default)."""
    fo = _fo(CLASS_TABLE)
    off = rom[fo + 2 * c] | rom[fo + 2 * c + 1] << 8
    x = _fo(0x830000 | ((CLASS_TABLE & 0xFFFF) + off) & 0xFFFF)
    out = []
    for _ in range(32):
        ch, g, sp = rom[x] | rom[x + 1] << 8, rom[x + 2], rom[x + 3] | rom[x + 4] << 8
        out.append((ch, g, sp))
        x += 5
        if g == 0xFF:
            return out, x - 5 * len(out)
    raise ValueError(f'class {c}: sprite list has no end')


def export(rom, path, class_names=None, char_name=None):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for c in range(class_count(rom)):
            for k, (ch, g, sp) in enumerate(class_list(rom, c)[0]):
                w.writerow({'class': c, '_class_name': (class_names or {}).get(c, ''), 'entry': k,
                            'gender': 'default' if g == 0xFF else ('female' if g == 1 else 'male' if g == 0 else g),
                            'character': ch if g != 0xFF else '',
                            '_character_name': (char_name(ch) if char_name and ch and g != 0xFF else ''),
                            'sprite': sprite_name(sp)})
    print('wrote', path)


GENDERS = {'male': 0, 'female': 1, 'default': 0xFF, '': 0xFF}


def apply(rom, proj, space=None):
    """map_sprites.csv and sprites/*.png.  A class's list is rewritten in place when it is no longer;
    a longer list moves to free space at the end of bank $83 (space: fe4lib.BankSpace)."""
    n = 0
    path = os.path.join(proj, 'map_sprites.csv')
    if os.path.exists(path):
        want = {}
        for ln, r in enumerate(csv.DictReader(open(path, newline='')), start=2):
            try:
                c = int(r['class'])
                g = r['gender'].strip().lower()
                g = GENDERS[g] if g in GENDERS else int(g, 0)
                ch = int(r['character'], 0) if r.get('character', '').strip() else 0
                sp = parse_sprite(r['sprite'])
            except (ValueError, KeyError) as e:
                raise SystemExit(f'{path}:{ln}: {e}')
            if not (0 <= g <= 0xFF and 0 <= ch <= 0xFFFF):
                raise SystemExit(f'{path}:{ln}: gender is male, female or default; character 0-65535')
            want.setdefault(c, []).append((0 if g == 0xFF else ch, g, sp))
        for c, new in want.items():
            if not 0 <= c < class_count(rom):
                raise SystemExit(f'{path}: class {c} has no sprite list')
            if [g == 0xFF for _, g, _ in new] != [False] * (len(new) - 1) + [True]:
                raise SystemExit(f'{path}: class {c}: the last row of a class (and only it) is "default"')
            if len(new) > 30:
                raise SystemExit(f'{path}: class {c}: at most 30 rows')
            cur, x = class_list(rom, c)
            if new == cur:
                continue
            data = b''.join(bytes([ch & 0xFF, ch >> 8, g, sp & 0xFF, sp >> 8]) for ch, g, sp in new)
            if len(new) > len(cur):
                if space is None:
                    import fe4lib
                    space = fe4lib.BankSpace(rom)
                x, a = space.alloc(0x838000, len(data))
                if not 0x838000 <= a <= 0x83FFFF:
                    raise SystemExit('no room for sprite lists in bank $83')
                off = ((a & 0xFFFF) - (CLASS_TABLE & 0xFFFF)) & 0xFFFF
                fo = _fo(CLASS_TABLE) + 2 * c
                rom[fo:fo + 2] = off.to_bytes(2, 'little')
            rom[x:x + len(data)] = data
            n += 1
    folder = os.path.join(proj, 'sprites')
    if os.path.isdir(folder):
        pal = palette(rom, 0)
        for f in sorted(os.listdir(folder)):
            m = re.fullmatch(r'([st])(\d{2})\.png', f, re.I)
            if not m:
                continue
            sid = parse_sprite(m.group(1).upper() + str(int(m.group(2))))
            try:
                rows = rows_from_png(sid, open(os.path.join(folder, f), 'rb').read(), pal)
            except ValueError as e:
                raise SystemExit(f'{os.path.join(folder, f)}: {e}')
            data = bytes_from_frames(sid, rows)
            a = _fo(data_addr(rom, sid))
            rom[a:a + len(data)] = data
            n += 1
    return n


def sprite_file(sid):
    return 'sprites/%s%02d.png' % ('t' if is_tall(sid) else 's', sid & 0x7FFF)
