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
