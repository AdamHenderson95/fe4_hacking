"""Map battles (battle animations off): the little figures that fight on the map.

Found for the editor (kit v43) by turning the Prologue fight into a map battle:
  $9E:83DE JSL $9E:85A4 picks each fighter's FIGURE from its class ($7E:4EBF), a flag ($7E:4EC1, 1 for
  women) and its weapon ($7E:4EBD): the figure is the class number, except
    - class 6 (Knight Lord) with item $19 -> figure $5D,
    - $9E:85DF word per class: $FFFF = no exception, else the high byte is the figure when the flag is 1
      (Master Knight $48, Mage Knight $49, Dracorider $4A ... Hero $51).
  Results: $7F:454E (attacker) / $7F:4550 (defender).
  $9E:B50D  94 figure records ($00-$5D) of $31 bytes: 8 x [ptr24 script, ptr24 graphics] + a byte.
            The entry used is the direction $7F:455E / $7F:4560, from where the fighter stands against
            its foe ($9E:80CB: (x, y) of self - foe -> 0-7).  By where the foe is: 0 left, 1 up-left,
            2 up, 3 up-right, 4 right, 5 down-right, 6 down, 7 down-left.  Up-right uses the right sheet,
            down-left the left one.
  Both blocks are compressed ($80:AA02 format) and unpacked when the battle starts ($9E:8941...):
  graphics (8 KB, 256 tiles) to $7E:8B88 (attacker) / $7E:AB88 (defender), scripts (2 KB) to $7E:EB88 /
  $7E:F408; the shared weapon sheet $AC:CC17 goes to $7E:CB88.  The scripts run on the sprite engine in
  bank $81 ($81:8216: command byte -> $81:823B; 00/18 frame, 03 tile page from graphics + $1000, 0E
  frame of the script's own table, ...).
The kit can give any class any figure (for men and for women) - a table hook replaces $9E:85A4 - and
redraw a figure's sheets (each redrawn sheet is compressed into the free banks; only that figure's
pointers change).
"""
import csv
import os
import re

import fe4lz
from asm65816 import Asm
from dis65816 import snes_to_file
from fe4gfx import _fo, read_png
import fe4sprites as SP

PICK = 0x9E85A4
PICK_BYTES = bytes.fromhex('da5aa500c90600d00c')
EXCEPTIONS = 0x9E85DF
RECORDS = 0x9EB50D
REC_SIZE = 0x31
FIGURES = 0x5E
DIRS = ('left', 'up-left', 'up', 'up-right', 'right', 'down-right', 'down', 'down-left')
SHEET_TILES = 256
SHEET_W, SHEET_H = 128, 128             # 16 tiles across, the way they sit in video memory
FILE = 'map_battle.csv'
FIELDS = ['class', '_class_name', 'figure', 'women']


def _p24(rom, f):
    return rom[f] | rom[f + 1] << 8 | rom[f + 2] << 16


def record_at(fig):
    return _fo(RECORDS) + fig * REC_SIZE


def pointers(rom, fig):
    """[(script, graphics)] for the 8 directions."""
    f = record_at(fig)
    return [(_p24(rom, f + 6 * k), _p24(rom, f + 6 * k + 3)) for k in range(8)]


def sheets(rom, fig):
    """[(graphics address, [directions])]: the figure's distinct sheets in direction order."""
    out = []
    for k, (_, g) in enumerate(pointers(rom, fig)):
        for a, ks in out:
            if a == g:
                ks.append(k)
                break
        else:
            out.append((g, [k]))
    return out


def sheet_bytes(rom, addr):
    return bytes(fe4lz.decompress(rom, addr))[:SHEET_TILES * 32]


def rows_from_bytes(data):
    rows = [[0] * SHEET_W for _ in range(SHEET_H)]
    for t in range(min(SHEET_TILES, len(data) // 32)):
        px = SP._decode_tile(data[t * 32:t * 32 + 32])
        tx, ty = (t % 16) * 8, (t // 16) * 8
        for y in range(8):
            rows[ty + y][tx:tx + 8] = px[y]
    return rows


def bytes_from_rows(rows):
    out = bytearray()
    for t in range(SHEET_TILES):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        out += SP._encode_tile([rows[ty + y][tx:tx + 8] for y in range(8)])
    return bytes(out)


def rows_from_png(data, pal):
    pw, ph, px = read_png(data)
    if (pw, ph) != (SHEET_W, SHEET_H):
        raise ValueError(f'a map battle sheet is {SHEET_W} x {SHEET_H} pixels, 16 tiles across '
                         f'(this picture is {pw} x {ph})')
    cache = {}

    def near(rgb):
        if rgb not in cache:
            r, g, b = rgb
            cache[rgb] = min(range(1, 16), key=lambda i: 3 * (pal[i][0] - r) ** 2 + 4 * (pal[i][1] - g) ** 2
                             + 2 * (pal[i][2] - b) ** 2)
        return cache[rgb]
    return [[0 if px[y * pw + x][3] < 128 else near(px[y * pw + x][:3]) for x in range(pw)] for y in range(ph)]


def sheet_file(fig, k):
    return 'mapbattle/fig%02X_%d.png' % (fig, k)


# ---------------------------------------------------------------- which figure each class shows
def class_figures(rom, n_classes):
    """[(men's figure, women's figure)] per class, as the game picks them."""
    f = _fo(EXCEPTIONS)
    out = []
    for c in range(n_classes):
        w = rom[f + 2 * c] | rom[f + 2 * c + 1] << 8
        out.append((c, c if w == 0xFFFF else w >> 8))
    return out


def figure_label(fig, class_names):
    if fig < len(class_names) and class_names[fig]:
        return class_names[fig]
    return 'Figure %02X' % fig


def export(rom, path, class_names):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for c, (m, wo) in enumerate(class_figures(rom, len(class_names))):
            w.writerow({'class': c, '_class_name': class_names[c], 'figure': '%02X' % m, 'women': '%02X' % wo})
    print('wrote', path)


def read(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return None
    out = {}
    with open(p, newline='', encoding='utf-8') as fh:
        for ln, r in enumerate(csv.DictReader(fh), start=2):
            try:
                c = int(r['class'])
                m, wo = int(r['figure'], 16), int(r['women'], 16)
            except (KeyError, ValueError):
                raise SystemExit(f'{p}:{ln}: class is a number; figure and women are figure numbers in hex (00-5D)')
            if not (0 <= m < FIGURES and 0 <= wo < FIGURES):
                raise SystemExit(f'{p}:{ln}: figures are 00-{FIGURES - 1:02X}')
            out[c] = (m, wo)
    return out


def build_pick(rom, table, region):
    """Replace $9E:85A4 with a lookup in table ([(men, women)] per class); class 6 with item $19 keeps
    figure $5D, as in the game."""
    f = snes_to_file(PICK)
    if bytes(rom[f:f + len(PICK_BYTES)]) != PICK_BYTES:
        raise SystemExit('map battle figures: this ROM\'s code is different at $9E:85A4')
    T = region.put(b''.join(bytes([m, w]) for m, w in table))
    a = Asm(region.cur)
    a.op('phx')
    a.op('phy')
    a.op('lda', 'dp', 0x00)
    a.op('cmp', '#', 0x0006)
    a.op('bne', 'rel', 'look')
    a.op('lda', 'dp', 0x04)
    a.op('cmp', '#', 0x0019)
    a.op('bne', 'rel', 'look')
    a.op('lda', '#', 0x005D)
    a.op('bra', 'rel', 'done')
    a.label('look')
    a.op('lda', 'dp', 0x00)
    a.op('cmp', '#', len(table))
    a.op('bcs', 'rel', 'done')            # a class past the table: its own number, as in the game
    a.op('asl')
    a.op('tax')
    a.op('lda', 'dp', 0x02)
    a.op('cmp', '#', 0x0001)
    a.op('bne', 'rel', 'men')
    a.op('lda', 'long,x', T + 1)
    a.op('bra', 'rel', 'mask')
    a.label('men')
    a.op('lda', 'long,x', T)
    a.label('mask')
    a.op('and', '#', 0x00FF)
    a.label('done')
    a.op('ply')
    a.op('plx')
    a.op('rtl')
    at = region.put(a.assemble())
    rom[f:f + 4] = bytes([0x5C]) + at.to_bytes(3, 'little')
    return at


def apply(rom, proj, far, n_classes):
    """map_battle.csv (installs the hook only when it differs from the game) and mapbattle/*.png."""
    n = 0
    rows = read(proj)
    if rows:
        game = class_figures(rom, n_classes)
        table = [rows.get(c, game[c]) for c in range(n_classes)]
        if table != game:
            import fe4skillfx as FX
            build_pick(rom, table, FX.region_for(rom))
            n += 1
    folder = os.path.join(proj, 'mapbattle')
    if os.path.isdir(folder):
        pal = SP.palette(rom, 0)
        for fn in sorted(os.listdir(folder)):
            m = re.fullmatch(r'fig([0-9A-F]{2})_([0-7])\.png', fn, re.I)
            if not m:
                continue
            fig, k = int(m.group(1), 16), int(m.group(2))
            path = os.path.join(folder, fn)
            if fig >= FIGURES:
                raise SystemExit(f'{path}: figures are 00-{FIGURES - 1:02X}')
            try:
                rws = rows_from_png(open(path, 'rb').read(), pal)
            except ValueError as e:
                raise SystemExit(f'{path}: {e}')
            old = pointers(rom, fig)[k][1]
            data = fe4lz.compress(bytes_from_rows(rws))
            a = far.alloc(len(data))
            rom[a:a + len(data)] = data
            base = record_at(fig)
            for kk, (_, g) in enumerate(pointers(rom, fig)):
                if g == old:
                    rom[base + 6 * kk + 3:base + 6 * kk + 6] = a.to_bytes(3, 'little')
            n += 1
    return n


# ---------------------------------------------------------------- playing a figure's motions
# A script block starts with 5 word offsets, one section per weapon kind (sword, lance, axe, bow, magic or
# staff; a kind the figure can't use points outside the block).  A section starts with the offset of its
# frame table, then pairs of motion offsets (body, overlay): pair 1 is standing, the others are attacks.
# A frame is a word count, then 5-byte pieces (x, x high / size flags, y, tile, attribute).  Body tiles
# $20-$37 come from the page the script loads (command 03 n: graphics + $1000 + n x $140 small, $200 tall);
# $1E/$1F are the shadow ($DF:FFC0); $40-$5F come from graphics + $400 (a tall figure's overlay object adds $20
# to its tiles, so its riders and arms are there too); the weapon's art from the shared sheet goes over
# $40-$43 / $50-$53 ($9E:8E01: $9E:8EC4 word per item, art offset / $100 in $AC:CC17, colour variant).
SECTIONS = ('sword', 'lance', 'axe', 'bow', 'magic or staff')
SHADOW = 0xDFFFC0
ARGS = {0x00: 3, 0x01: 0, 0x02: 2, 0x03: 1, 0x04: 0, 0x05: 0, 0x06: 0, 0x07: 0, 0x08: 0, 0x09: 0, 0x0A: 0,
        0x0B: 0, 0x0C: 0, 0x0D: 0, 0x0E: 2, 0x0F: 0, 0x10: 0, 0x11: 0, 0x12: 1, 0x13: 1, 0x14: 2, 0x15: 2,
        0x16: 1, 0x17: 2, 0x18: 3, 0x19: 2, 0x1A: 0, 0x1B: 0, 0x1C: 0, 0x1D: 1, 0x1E: 1}
STOP = (0x01, 0x02, 0x09, 0x0A, 0x0B, 0x0C, 0x15)
CELL = 64                 # each rendered step is a 64 x 64 picture with the unit's tile at (24, 32)
ORIGIN = (32, 40)


WEAPON_SHEET = 0xACCC17          # shared weapon art, unpacked to $7E:CB88 for every map battle
WEAPON_ART = 0x9E8EC4            # word per weapon item ($00-$39): art offset / $100, colour variant
PREVIEW_ITEMS = (0x00, 0x1C, 0x28, 0x31, None)   # Iron sword, Iron lance, Iron axe, Iron bow, (magic)
_weapons = {}


def weapon_tiles(rom, item):
    """{tile: 32 bytes} for $40-$43 / $50-$53 with an item's art ($9E:8E01), or {}."""
    if item is None or not 0 <= item < 0x3A:
        return {}
    key = (id(rom), len(rom))
    if key not in _weapons:
        _weapons.clear()
        _weapons[key] = bytes(fe4lz.decompress(rom, WEAPON_SHEET))
    sheet = _weapons[key]
    art = rom[_fo(WEAPON_ART) + 2 * item] << 8
    out = {}
    for i in range(4):
        out[0x40 + i] = sheet[art + 32 * i:art + 32 * i + 32]
        out[0x50 + i] = sheet[art + 0x80 + 32 * i:art + 0x80 + 32 * i + 32]
    return out


def is_tall(rom, fig):
    return bool(rom[record_at(fig) + 0x30])


def script_bytes(rom, fig, k):
    return bytes(fe4lz.decompress(rom, pointers(rom, fig)[k][0]))


def _w(d, o):
    return d[o] | d[o + 1] << 8 if o + 1 < len(d) else 0xFFFF


def parse_section(script, s):
    """{frames: [[(x, y, tile, big, hflip, vflip)]], pairs: [(body offset or None, overlay offset or None)]}"""
    base = _w(script, 2 * s)
    if base + 2 >= len(script):
        return None
    ft = base + _w(script, base)
    if ft + 2 >= len(script):
        return None
    nh = (_w(script, ft) - 2) // 2
    if not 0 < nh < 40:
        return None
    mots = [base + _w(script, base + 2 + 2 * j) for j in range(nh)]
    mots = [m if ft < m < len(script) else None for m in mots]
    after = [m for m in mots if m]
    nfr = ((min(after) if after else ft + 2) - ft) // 2
    frames = []
    for i in range(nfr):
        f = base + _w(script, ft + 2 * i)
        n = _w(script, f)
        if f + 2 + 5 * n > len(script) or n > 32:
            frames.append([])
            continue
        pieces = []
        for j in range(n):
            x, fl, y, t, a = script[f + 2 + 5 * j:f + 7 + 5 * j]
            pieces.append((x - 256 if fl & 1 else x, y - 256 if y > 127 else y, t | (a & 1) << 8,
                           bool(fl & 2), bool(a & 0x40), bool(a & 0x80)))
        frames.append(pieces)
    pairs = [(mots[j], mots[j + 1] if j + 1 < len(mots) else None) for j in range(0, len(mots), 2)]
    return {'frames': frames, 'pairs': pairs}


def motion_steps(script, o, limit=80):
    """[(page, frame, ticks, dx, dy)] of a motion, until it ends or jumps."""
    out, page, dx, dy = [], 0, 0, 0
    for _ in range(limit):
        if o is None or o >= len(script):
            break
        c = script[o]
        n = ARGS.get(c)
        if n is None:
            break
        a = script[o + 1:o + 1 + n]
        if c == 0x03:
            page = a[0]
        elif c == 0x0E:
            out.append((page, a[1], a[0] or 1, dx, dy))
        elif c == 0x19:
            dx += a[0] - 256 if a[0] > 127 else a[0]
            dy += a[1] - 256 if a[1] > 127 else a[1]
        o += 1 + n
        if c in STOP:
            break
    return out


def _page_tiles(gfx, page, tall):
    """{tile number: 32 bytes}: the body slot ($20-$27 / $30-$37) from the page, and $40-$5F from
    graphics + $400 (riders, arms, weapons held; the game puts the weapon's own art over $40-$43 / $50-$53)."""
    size, half = (0x200, 0x100) if tall else (0x140, 0xA0)
    base = 0x1000 + page * size
    out = {0x40 + i: gfx[0x400 + 32 * i:0x420 + 32 * i] for i in range(32)}
    for row, first in ((0, 0x20), (1, 0x30)):
        for i in range(half // 32):
            off = base + row * half + 32 * i
            out[first + i] = gfx[off:off + 32]
    return out


def render(rom, gfx, frame_pieces, page, tall, shadow=None, dx=0, dy=0, weapon=None):
    """Index rows (CELL x CELL) of one frame drawn with a page's tiles (and a weapon's art)."""
    tiles = _page_tiles(gfx, page, tall)
    tiles.update(weapon or {})
    if shadow is None:
        f = _fo(SHADOW)
        shadow = {0x1E: rom[f:f + 32], 0x1F: rom[f + 32:f + 64]}
    tiles.update(shadow)
    rows = [[0] * CELL for _ in range(CELL)]
    for x, y, t, big, hf, vf in reversed(frame_pieces):
        n = 2 if big else 1
        for ty in range(n):
            for tx in range(n):
                sub = t + (n - 1 - tx if hf else tx) + 16 * (n - 1 - ty if vf else ty)
                data = tiles.get(sub)
                if data is None or len(data) < 32:
                    continue
                px = SP._decode_tile(data)
                for yy in range(8):
                    for xx in range(8):
                        c = px[7 - yy if vf else yy][7 - xx if hf else xx]
                        if not c:
                            continue
                        X = ORIGIN[0] + x + dx + 8 * tx + xx
                        Y = ORIGIN[1] + y + dy + 8 * ty + yy
                        if 0 <= X < CELL and 0 <= Y < CELL:
                            rows[Y][X] = c
    return rows


def player(rom, fig, k, s, gfx=None):
    """The figure's motions for direction k and weapon section s, rendered:
    (rows of a strip CELL high, one CELL per distinct picture, [{name, steps: [(cell, ticks)]}])
    or None when the figure has no such section."""
    script = script_bytes(rom, fig, k)
    sec = parse_section(script, s)
    if not sec:
        return None
    tall = is_tall(rom, fig)
    if gfx is None:
        gfx = sheet_bytes(rom, pointers(rom, fig)[k][1])
    gfx = gfx + bytes(max(0, 0x2000 - len(gfx)))
    weapon = weapon_tiles(rom, PREVIEW_ITEMS[s])
    cells, index, motions = [], {}, []
    for j, (body, over) in enumerate(sec['pairs']):
        b = motion_steps(script, body) if body else []
        ov = motion_steps(script, over) if over else []
        if not b:
            continue
        steps = []
        t_over, oi = 0, 0
        clock = 0
        for page, fr, ticks, dx, dy in b:
            # the overlay step that is showing at this time (drawn with the body's page)
            while oi + 1 < len(ov) and t_over + ov[oi][2] <= clock:
                t_over += ov[oi][2]
                oi += 1
            key = (page, fr, dx, dy, ov[oi][1] if ov else None)
            if key not in index:
                pieces = list(sec['frames'][fr]) if fr < len(sec['frames']) else []
                if ov and ov[oi][1] < len(sec['frames']):     # the overlay object's tiles are $20 on
                    pieces = [(x, y, t + 0x20, b, h, v) for x, y, t, b, h, v in sec['frames'][ov[oi][1]]] + pieces
                index[key] = len(cells)
                cells.append(render(rom, gfx, pieces, page, tall, dx=dx, dy=dy, weapon=weapon))
            steps.append((index[key], min(ticks, 60)))
            clock += ticks
        motions.append({'name': 'Standing' if j == 1 else f'Motion {j}', 'steps': steps})
    if not cells:
        return None
    strip = [sum((c[y] for c in cells), []) for y in range(CELL)]
    return strip, motions
