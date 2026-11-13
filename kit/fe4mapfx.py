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
    export_colours(rom, proj, item_names)
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
    return n + apply_bg(rom, proj, far) + apply_colours(rom, proj, far)


# ---------------------------------------------------------------- background pieces
# $9F:80D9, 9 bytes per spell: ptr24 tiles (4 KB = 128 4bpp tiles, numbers $380-$3FF, sent to BG2 at +$3800 /
# +$3C00), ptr24 tilemap (32 x 32 words: tile | palette << 10 | flips; scrolled to make it move), ptr24
# colours (256).  On screen the effect's colours (BG palette 6, colours 9-15) come from each spell's own code,
# which cycles them from tables in bank $9F (Fire: $DF:96D5; Meteor: $9F:B37D), so the block's colours are only
# close.  Every spell from Fire to Broken staff (A) has a set; many share one.
BG_TABLE = 0x9F80D9
BG_COUNT = 42                    # Fire ($3E) to Broken staff (A) ($67)
BG_TILE0 = 0x380
BG_W = BG_H = 256


def bg_pointers(rom, s):
    f = _fo(BG_TABLE) + 9 * s
    return [rom[f + j] | rom[f + j + 1] << 8 | rom[f + j + 2] << 16 for j in (0, 3, 6)]


def bg_blocks(rom, s):
    """(tiles 4096 bytes, map 2048 bytes, colours [256])."""
    a, m, c = [bytes(fe4lz.decompress(rom, p)) for p in bg_pointers(rom, s)]
    return a[:4096], m[:2048], [c[2 * i] | c[2 * i + 1] << 8 for i in range(256)]


def _bg_entries(mp):
    return [mp[2 * i] | mp[2 * i + 1] << 8 for i in range(1024)]


def bg_picture(tiles, mp, cols):
    """RGBA rows (256 x 256) as stored (palette 6/7 colours from the block)."""
    rgbs = [rgb(c) for c in cols]
    img = [[(0, 0, 0, 0)] * BG_W for _ in range(BG_H)]
    for i, e in enumerate(_bg_entries(mp)):
        k = (e & 0x3FF) - BG_TILE0
        if not 0 <= k < 128:
            continue
        p, hf, vf = (e >> 10) & 7, e >> 14 & 1, e >> 15 & 1
        px = SP._decode_tile(tiles[32 * k:32 * k + 32])
        X, Y = (i % 32) * 8, (i // 32) * 8
        for y in range(8):
            for x in range(8):
                c = px[7 - y if vf else y][7 - x if hf else x]
                if c:
                    img[Y + y][X + x] = rgbs[16 * p + c] + (255,)
    return img


def bg_png(rom, s, tiles=None, mp=None, cols=None, scale=1):
    from fe4gfx import png
    t0, m0, c0 = bg_blocks(rom, s)
    img = bg_picture(tiles or t0, mp or m0, cols or c0)
    rows = [b''.join(bytes(px) * scale for px in r) for r in img for _ in range(scale)]
    return png(BG_W * scale, BG_H * scale, rows)


def bg_from_png(data, mp, cols, old_tiles=None):
    """(tiles, map) from a 256 x 256 picture: each 8x8 cell keeps the palette the game's map gives it and
    takes that palette's nearest colours; equal tiles (also flipped) are stored once, at most 128.  Empty
    cells use an empty tile (the one the game's set already has, when it has one)."""
    pw, ph, px = read_png(data)
    if (pw, ph) != (BG_W, BG_H):
        raise ValueError(f'a map spell background is {BG_W} x {BG_H} pixels (this picture is {pw} x {ph})')
    rgbs = [rgb(c) for c in cols]
    old = _bg_entries(mp)
    cache = {}

    def near(p, c):
        key = (p, c)
        if key not in cache:
            r, g, b = c
            cache[key] = min(range(1, 16), key=lambda i: 3 * (rgbs[16 * p + i][0] - r) ** 2 + 4 * (rgbs[16 * p + i][1] - g) ** 2
                             + 2 * (rgbs[16 * p + i][2] - b) ** 2)
        return cache[key]
    # an empty slot the game's set already has (kept where it is)
    blank = None
    if old_tiles is not None:
        blank = next((k for k in range(128) if not any(old_tiles[32 * k:32 * k + 32])), None)
    uniq, index, cells = [], {}, []
    for i in range(1024):
        p = (old[i] >> 10) & 7 if 0 <= (old[i] & 0x3FF) - BG_TILE0 < 128 else 6
        X, Y = (i % 32) * 8, (i // 32) * 8
        cell = [[0 if px[(Y + y) * pw + X + x][3] < 128 else near(p, px[(Y + y) * pw + X + x][:3])
                 for x in range(8)] for y in range(8)]
        if not any(any(r) for r in cell):
            if not 0 <= (old[i] & 0x3FF) - BG_TILE0 < 128:
                cells.append((p, 'keep', 0, 0))      # points past the effect's tiles in the game: keep it
            else:
                cells.append((p, None, 0, 0))
            continue
        found = None
        for hf in (0, 1):
            for vf in (0, 1):
                v = [list(reversed(r)) if hf else list(r) for r in (reversed(cell) if vf else cell)]
                key = tuple(tuple(r) for r in v)
                if key in index:
                    found = (index[key], hf, vf)
                    break
            if found:
                break
        if found is None:
            key = tuple(tuple(r) for r in cell)
            index[key] = len(uniq)
            uniq.append(SP._encode_tile([list(r) for r in cell]))
            found = (index[key], 0, 0)
        cells.append((p,) + found)
    need_blank = any(c[1] is None for c in cells)
    if need_blank and blank is None:
        blank = len(uniq)
    room = 128 - (1 if need_blank else 0)
    if len(uniq) > room:
        raise ValueError(f'this picture needs {len(uniq)} different 8 x 8 tiles{" and an empty one" if need_blank else ""};'
                         f' a map spell background has room for 128 (repeat or mirror more of it)')
    slots = [k for k in range(128) if not (need_blank and k == blank)]
    where = {u: slots[u] for u in range(len(uniq))}
    t = bytearray(32 * 128)
    for u, data_ in enumerate(uniq):
        t[32 * where[u]:32 * where[u] + 32] = data_
    entries = []
    for i, (p, u, hf, vf) in enumerate(cells):
        if u == 'keep':
            entries.append(old[i])
        elif u is None:
            entries.append((old[i] & 0x2000) | p << 10 | (BG_TILE0 + blank))
        else:
            entries.append((old[i] & 0x2000) | p << 10 | hf << 14 | vf << 15 | (BG_TILE0 + where[u]))
    return bytes(t), b''.join(e.to_bytes(2, 'little') for e in entries)


def bg_file(s):
    return 'mapfx/bg%02d.png' % s


def apply_bg(rom, proj, far):
    """mapfx/bgNN.png: a spell's background picture (tiles and tilemap) into the free banks."""
    n = 0
    folder = os.path.join(proj, 'mapfx')
    if not os.path.isdir(folder):
        return 0
    for fn in sorted(os.listdir(folder)):
        m = re.fullmatch(r'bg(\d{2})\.png', fn, re.I)
        if not m:
            continue
        s, path = int(m.group(1)), os.path.join(folder, fn)
        if not 0 <= s < BG_COUNT:
            raise SystemExit(f'{path}: spells are 0-{BG_COUNT - 1}')
        t, mp, cols = bg_blocks(rom, s)
        try:
            nt, nm = bg_from_png(open(path, 'rb').read(), mp, cols, t)
        except ValueError as e:
            raise SystemExit(f'{path}: {e}')
        f = _fo(BG_TABLE) + 9 * s
        for j, blob in ((0, nt), (3, nm)):
            data = fe4lz.compress(blob)
            a = far.alloc(len(data))
            rom[a:a + len(data)] = data
            rom[f + j:f + j + 3] = a.to_bytes(3, 'little')
        n += 1
    return n


# ---------------------------------------------------------------- background colours
# What a spell's background shows in BG palette 6 (and 7), colours 9-15.  $9F:8645 first copies them from
# the spell's colour block; most tomes' own code then cycles them through lists in bank $9F (found by tracing
# every tome in the Prologue map battle; each list is (start, number of colours), read 7 at a time or as a
# sliding window).  The kit changes those lists in place.  The spells marked BLOCK show the block's colours
# 9-15 of palettes 6 and 7 as they are (verified with Wind).  Staves were not traced.
COLOUR_LISTS = {
    0: [(0x9F96D5, 7)], 1: [(0x9F96D5, 7)],                                   # Fire, Elfire
    2: [(0x9FA3DB + 16 * i, 7) for i in range(18)],                         # Bolganone
    3: [(0x9FD513, 23)],                                                    # Valflame
    4: [(0x9FB37D, 29)],                                                    # Meteor
    5: [(0x9FAB2B + 16 * i, 7) for i in range(19)],                         # Thunder
    6: [(0x9FAB2B + 16 * i, 7) for i in range(12)],                         # Elthunder
    9: [(0x9FAB2B + 16 * i, 7) for i in range(19)],                         # Bolting
    7: [(0x9FAFA9, 18)],                                                    # Thoron
    8: [(0x9FBE52, 15), (0x9FBEE8, 10)],                                    # Mjolnir (colours 9-12, 13-15)
    13: [(0x9FC0FD + 14 * i, 7) for i in range(10)],                        # Forseti
    15: [(0x9FAD32, 22)],                                                   # Light
    16: [(0x9FC5AF, 18)],                                                   # Nosferatu
    17: [(0x9F98AA + 14 * i, 7) for i in range(12)],                        # Aura
    22: [(0x9F9B0A, 31)], 23: [(0x9F9B0A, 31)], 24: [(0x9F9B0A, 31)], 25: [(0x9F9B0A, 31)],   # Loptyr, drained
}
BLOCK = (10, 11, 12, 14, 18, 19, 20, 21)   # Wind, Elwind, Tornado, Blizzard, Naga, Jormungand, Fenrir, Hel
WORDS_FILE = 'map_colour_words.csv'        # address, colour: the lists above
BLOCK_FILE = 'map_spell_block.csv'         # spell, colours: palette 6 colours 9-15 then palette 7 colours 9-15


def colour_words():
    """{address: [spells]} for every word in the lists."""
    out = {}
    for s, lists in COLOUR_LISTS.items():
        for a, n in lists:
            for i in range(n):
                out.setdefault(a + 2 * i, []).append(s)
    return out


def word(rom, a):
    f = _fo(a)
    return rom[f] | rom[f + 1] << 8


def colour_rows(rom, s):
    """[[(address, colour)]] - the lists a spell cycles through."""
    return [[(a + 2 * i, word(rom, a + 2 * i)) for i in range(n)] for a, n in COLOUR_LISTS.get(s, [])]


def block_colours(rom, s):
    cols = bg_blocks(rom, s)[2]
    return cols[105:112] + cols[121:128]


def export_colours(rom, proj, item_names):
    with open(os.path.join(proj, WORDS_FILE), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['address', 'colour', '_spells'])
        w.writeheader()
        for a, ss in sorted(colour_words().items()):
            w.writerow({'address': '%06X' % a, 'colour': '%04x' % word(rom, a),
                        '_spells': ', '.join(item_names[FIRST_ITEM + s] for s in ss)})
    with open(os.path.join(proj, BLOCK_FILE), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['spell', '_name', 'colours'])
        w.writeheader()
        for s in BLOCK:
            w.writerow({'spell': s, '_name': item_names[FIRST_ITEM + s],
                        'colours': ' '.join('%04x' % c for c in block_colours(rom, s))})


def apply_colours(rom, proj, far):
    n = 0
    known = colour_words()
    p = os.path.join(proj, WORDS_FILE)
    if os.path.exists(p):
        for ln, r in enumerate(csv.DictReader(open(p, newline='', encoding='utf-8')), start=2):
            try:
                a, c = int(r['address'], 16), int(r['colour'], 16) & 0x7FFF
            except (KeyError, ValueError):
                raise SystemExit(f'{p}:{ln}: address and colour are hex')
            if a not in known:
                raise SystemExit(f'{p}:{ln}: {a:06X} is not one of the map spell colour lists')
            if word(rom, a) != c:
                f = _fo(a)
                rom[f:f + 2] = c.to_bytes(2, 'little')
                n += 1
    p = os.path.join(proj, BLOCK_FILE)
    if os.path.exists(p):
        for ln, r in enumerate(csv.DictReader(open(p, newline='', encoding='utf-8')), start=2):
            try:
                s = int(r['spell'])
                cols = [int(x, 16) & 0x7FFF for x in r['colours'].split()]
            except (KeyError, ValueError):
                raise SystemExit(f'{p}:{ln}: spell is a number, colours are 14 hex colours')
            if s not in BLOCK or len(cols) != 14:
                raise SystemExit(f'{p}:{ln}: spell {s} takes its colours from its own code, or not 14 colours')
            if cols == block_colours(rom, s):
                continue
            allc = bg_blocks(rom, s)[2]
            allc = allc[:105] + cols[:7] + allc[112:121] + cols[7:] + allc[128:]
            data = fe4lz.compress(b''.join(c.to_bytes(2, 'little') for c in allc))
            a = far.alloc(len(data))
            rom[a:a + len(data)] = data
            f = _fo(BG_TABLE) + 9 * s
            rom[f + 6:f + 9] = a.to_bytes(3, 'little')
            n += 1
    return n
