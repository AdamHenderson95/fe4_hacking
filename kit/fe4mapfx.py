"""Spell effects on the map: what a tome or staff shows in a map battle (battle animations off).

Found for the editor (kit v44) by giving Midir a Fire tome in the Prologue map battle:
  $7F:5089 = map spell number = item - $3E (Fire 0, Elfire 1 ... Thief staff 40); $FFFF for weapons.
  $9F:8724  5 bytes per spell ($9F:86BF): word palette (bank $9F; $FFFF = no effect), ptr24 sprite sheet.
            The palette's 16 colours go to OBJ palette 6 (CGRAM buffer $0100 + $1C0); the sheet
            (compressed, $400 bytes = 32 tiles) is unpacked to $7F:45D9 and sent to OBJ tiles $00-$1F.
            Fire's fireball is the 16x16 object at tile $04.
  The six palettes are $9F:8800, 8820, 8840, 8860, 8880, 88A0 (bank $9F is full, so the kit changes them in
  place and lets a spell pick another one).
  $9F:80D9  9 bytes per spell: ptr24 x 3 for bigger pieces drawn on the background ($9F:84E5...: to
            $7E:CB88, $7E:DB88, $7E:E388; Valflame and Meteor have special cases) - not edited yet.
"""
import csv
import os
import re

import fe4lz
from fe4gfx import _fo, read_png
import fe4sprites as SP

TABLE = 0x9F8724
COUNT = 44                       # items $3E (Fire) to $69
FIRST_ITEM = 0x3E
PALETTES = [0x8800 + 0x20 * i for i in range(6)]
BANK = 0x9F0000
SHEET_W, SHEET_H = 128, 16       # 32 tiles, 16 across, as they sit in video memory
FILE = 'map_spells.csv'
FIELDS = ['spell', '_name', 'palette']
PAL_FILE = 'map_palettes.csv'
PAL_FIELDS = ['palette', 'colours']


def entry(rom, s):
    """(palette word or None, sprite sheet address)."""
    f = _fo(TABLE) + 5 * s
    pal = rom[f] | rom[f + 1] << 8
    spr = rom[f + 2] | rom[f + 3] << 8 | rom[f + 4] << 16
    return (None if pal == 0xFFFF else pal), spr


def spells(rom):
    """[(spell, item)] that have an effect."""
    return [(s, FIRST_ITEM + s) for s in range(COUNT) if entry(rom, s)[0] is not None]


def palette_index(word):
    return PALETTES.index(word) if word in PALETTES else 0


def colours(rom, p):
    """16 BGR555 colours of palette p (0-5)."""
    f = _fo(BANK | PALETTES[p])
    return [rom[f + 2 * i] | rom[f + 2 * i + 1] << 8 for i in range(16)]


def rgb(c):
    return ((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31)


def sheet_bytes(rom, s):
    return bytes(fe4lz.decompress(rom, entry(rom, s)[1]))[:0x400]


def rows_from_bytes(data):
    rows = [[0] * SHEET_W for _ in range(SHEET_H)]
    for t in range(min(32, len(data) // 32)):
        px = SP._decode_tile(data[32 * t:32 * t + 32])
        tx, ty = (t % 16) * 8, (t // 16) * 8
        for y in range(8):
            rows[ty + y][tx:tx + 8] = px[y]
    return rows


def bytes_from_rows(rows):
    out = bytearray()
    for t in range(32):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        out += SP._encode_tile([rows[ty + y][tx:tx + 8] for y in range(8)])
    return bytes(out)


def rows_from_png(data, pal):
    """pal: 16 (r, g, b).  Colours go to the nearest of the palette; transparent pixels to colour 0."""
    pw, ph, px = read_png(data)
    if (pw, ph) != (SHEET_W, SHEET_H):
        raise ValueError(f'a map spell sheet is {SHEET_W} x {SHEET_H} pixels, 16 tiles across '
                         f'(this picture is {pw} x {ph})')
    cache = {}

    def near(c):
        if c not in cache:
            r, g, b = c
            cache[c] = min(range(1, 16), key=lambda i: 3 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2
                           + 2 * (pal[i][2] - b) ** 2)
        return cache[c]
    return [[0 if px[y * pw + x][3] < 128 else near(px[y * pw + x][:3]) for x in range(pw)] for y in range(ph)]


# The project keeps redrawn sheets in stand-in colours (one per colour number, as the spell pictures do), so
# changing a palette later never changes which colour numbers a sheet uses.
from fe4spellfx import RAMP4 as STAND_IN    # noqa: E402


def stand_in_png(rows):
    return SP.indexed_sheet_png(rows, STAND_IN)


def sheet_file(s):
    return 'mapfx/spell%02d.png' % s


def export(rom, proj, item_names):
    with open(os.path.join(proj, FILE), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for s, it in spells(rom):
            w.writerow({'spell': s, '_name': item_names[it] if it < len(item_names) else '',
                        'palette': palette_index(entry(rom, s)[0])})
    with open(os.path.join(proj, PAL_FILE), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=PAL_FIELDS)
        w.writeheader()
        for p in range(len(PALETTES)):
            w.writerow({'palette': p, 'colours': ' '.join('%04x' % c for c in colours(rom, p))})


def _read(path, fields):
    if not os.path.exists(path):
        return None
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def apply(rom, proj, far):
    n = 0
    for ln, r in enumerate(_read(os.path.join(proj, PAL_FILE), PAL_FIELDS) or [], start=2):
        try:
            p = int(r['palette'])
            cols = [int(x, 16) & 0x7FFF for x in r['colours'].split()]
        except (KeyError, ValueError):
            raise SystemExit(f'{PAL_FILE}:{ln}: palette is 0-5, colours are 16 4-digit hex colours')
        if not 0 <= p < len(PALETTES) or len(cols) != 16:
            raise SystemExit(f'{PAL_FILE}:{ln}: palette is 0-5, colours are 16 4-digit hex colours')
        if cols != colours(rom, p):
            f = _fo(BANK | PALETTES[p])
            rom[f:f + 32] = b''.join(c.to_bytes(2, 'little') for c in cols)
            n += 1
    for ln, r in enumerate(_read(os.path.join(proj, FILE), FIELDS) or [], start=2):
        try:
            s, p = int(r['spell']), int(r['palette'])
        except (KeyError, ValueError):
            raise SystemExit(f'{FILE}:{ln}: spell and palette are numbers')
        if not 0 <= s < COUNT or entry(rom, s)[0] is None or not 0 <= p < len(PALETTES):
            raise SystemExit(f'{FILE}:{ln}: spell {s} has no map effect, or palette {p} is not 0-5')
        if entry(rom, s)[0] != PALETTES[p]:
            f = _fo(TABLE) + 5 * s
            rom[f:f + 2] = PALETTES[p].to_bytes(2, 'little')
            n += 1
    folder = os.path.join(proj, 'mapfx')
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            m = re.fullmatch(r'spell(\d{2})\.png', fn, re.I)
            if not m:
                continue
            s = int(m.group(1))
            path = os.path.join(folder, fn)
            if not 0 <= s < COUNT or entry(rom, s)[0] is None:
                raise SystemExit(f'{path}: spell {s} has no map effect')
            try:
                rows = rows_from_png(open(path, 'rb').read(), STAND_IN)
            except ValueError as e:
                raise SystemExit(f'{path}: {e}')
            data = fe4lz.compress(bytes_from_rows(rows))
            a = far.alloc(len(data))
            rom[a:a + len(data)] = data
            f = _fo(TABLE) + 5 * s
            rom[f + 2:f + 5] = a.to_bytes(3, 'little')
            n += 1
    return n
