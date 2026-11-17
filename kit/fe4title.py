"""The title screen: its background, logo and emblem as pictures you can replace (kit v53).

Found by tracing the title (ROM_MAP "Title screen").  Three layers, drawn back to front:

  background  BG2: 4bpp tiles $9C:8000 (compressed; the first 512 tiles go to VRAM $2000), map $9C:BBB7
              (32x32), palettes 5 and 6 = colours 1-15 of rows 5 and 6 of the 256-colour block $9C:BFA1
              (compressed).  The title scrolls it up 31 lines: the screen shows map lines 31-254.
  emblem      sprites (the sword and the book): tiles $F5:7E44 (compressed, to VRAM $6000), 12 sprite
              objects $99:FEAC (13 bytes each: script, frames table, x, y, tile add, attribute OR) whose
              scripts show one metasprite each, OBJ palettes 2 ($E0:271D) and 4 ($E0:2769).
  logo        BG1 ("FIRE EMBLEM", the subtitle box, the copyright line), in front of the emblem:
              4bpp tiles $43:0000 (Project Naga's, compressed; $2200 bytes = 272 tiles to VRAM $4000),
              map $42:24D0 (32x32), palettes 2 ($E0:26FF), 3 ($E0:26C3) and 4 ($E0:2759, colours 1-8:
              its colour 9 is the emblem palette's colour 1).  Scrolled down one line.  The opening's
              last scene flies the same layer in.

When the opening runs into the title (no Start), the logo flies in (the same layer, with the subtitle
rows filled with tile $0B), the sword slides in, and a BG3 map ($42:29A0, 2bpp tiles $42:2660)
subtracts a drop shadow under "FIRE EMBLEM"; a new logo clears that shadow.

The title code at $95:EE73-$95:F0C5 decompresses them (immediates LDX #lo / LDA #bank), and a graphics
script table at $97:F3C2-$97:F468 names some of them again (24-bit pointers): a picture that changes
is written to free space and every one of those places is repointed.

Project files: title/background.png, title/logo.png and title/emblem.png, each 256x224 (any colours:
they are reduced to what the SNES allows).  A missing file keeps the game's own layer; an emblem.png
with nothing on it hides the sword and book.
"""
import hashlib
import json
import os

import fe4gfx as G
import fe4lz
from dis65816 import snes_to_file as _fo

W, H = 256, 224
FOLDER = 'title'
LAYERS = ('background', 'logo', 'emblem')
CONVERTER = 1          # bump when the conversion changes (cached results are keyed by it)

BG_TILES, BG_MAP, BG_PALS = 0x9C8000, 0x9CBBB7, 0x9CBFA1
BG_TILE_LIMIT = 512             # VRAM $2000-$3FFF; the stream holds 64 more tiles, kept as they are
BG_SCROLL = 31                  # screen row y shows map line y + 31 + 1 (the first shown line is line 1)
BG_ROWS = (5, 6)
LOGO_TILES, LOGO_MAP = 0x430000, 0x4224D0
LOGO_BYTES = 0x2200             # 272 tiles; VRAM $5100 on is the menu font
LOGO_SCROLL = -1
LOGO_PALS = ((2, 0xE026FF, 15), (3, 0xE026C3, 15), (4, 0xE02759, 8))
OBJ_TILES = 0xF57E44
OBJ_BYTES = 0x2C80              # 356 tiles (decompressed to $7E:8B88: more would overrun what follows)
OBJ_PALS = ((2, 0xE0271D, 15), (4, 0xE02769, 15))
# 14 sprite objects: $99:FE92 / $99:FE9F (the sword sliding in when the opening runs into the title),
# $99:FEAC (the sword when Start skips the opening), $99:FEB9-$99:FF3B (the book, piece by piece; both
# ways).  A new emblem is drawn by the first book piece (it stays where it is); the others show nothing.
OBJECTS, OBJECT_COUNT, EMBLEM_OBJECT = 0x99FE92, 14, 3
OBJ_X, OBJ_Y = 128, 112        # the new emblem's origin
LOGO_BLANK = (0, 0x0B)          # tiles the game's own code uses as blanks (the opening's fly-in fills
                                # the subtitle rows with tile $0B); a new logo keeps them empty
SHADOW_MAP = 0x4229A0           # BG3 map: the logo's drop shadow when the opening runs into the title
SPRITE_LIMIT = 128

# where the game names each stream: ('imm', LDX operand, LDA operand) or ('ptr', 24-bit pointer)
REFS = {
    # the menu and the chronology load the same picture again with their own, taller layout
    # ($97:F45B / $97:F466): they keep the game's picture
    BG_TILES: [('imm', 0x95EFD4, 0x95EFD9), ('ptr', 0x97F42D)],
    BG_MAP: [('imm', 0x95EFFD, 0x95F002), ('ptr', 0x97F438)],
    BG_PALS: [('imm', 0x95EF22, 0x95EF27)],
    LOGO_TILES: [('imm', 0x95EE78, 0x95EE7D), ('ptr', 0x97F3C2)],
    LOGO_MAP: [('imm', 0x95EEB0, 0x95EEB5)],
    OBJ_TILES: [('imm', 0x95F026, 0x95F02B), ('ptr', 0x97F3CD)],
    SHADOW_MAP: [('imm', 0x95EFAB, 0x95EFB0), ('ptr', 0x97F417)],
}


def _w(rom, a):
    o = _fo(a)
    return rom[o] | rom[o + 1] << 8


def _colors(rom, a, n):
    return [_w(rom, a + 2 * i) for i in range(n)]


def _rgb(c):
    return ((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31)


def _tile_px(data, t):
    """8x8 colour indices of 4bpp tile t (all 0 past the end of the data)."""
    if t * 32 + 32 > len(data):
        return [[0] * 8 for _ in range(8)]
    return G._tile(data, t)


def _tile_bytes(px):
    out = bytearray(32)
    for y in range(8):
        for plane in range(4):
            v = 0
            for x in range(8):
                if px[y][x] >> plane & 1:
                    v |= 0x80 >> x
            out[(plane >> 1) * 16 + 2 * y + (plane & 1)] = v
    return bytes(out)


# ---------------------------------------------------------------- the game's own layers

def _ref_target(rom, kind, a, b=None):
    if kind == 'imm':
        return rom[_fo(b)] << 16 | _w(rom, a)
    o = _fo(a)
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def current_source(rom, stream):
    """Where the title loads a stream from now (a built ROM may have moved it)."""
    kind, *args = REFS[stream][0]
    return _ref_target(rom, kind, *args)


def read_layers(rom):
    """{'background', 'logo', 'emblem'} as layer dicts (see render)."""
    bgt = G.decompress(rom, current_source(rom, BG_TILES))
    bgm = G.decompress(rom, current_source(rom, BG_MAP))
    block = G.decompress(rom, current_source(rom, BG_PALS))
    bg = {'tiles': bgt[:BG_TILE_LIMIT * 32], 'map': [bgm[2 * i] | bgm[2 * i + 1] << 8 for i in range(1024)],
          'pals': {r: [0] + [block[r * 32 + 2 * i] | block[r * 32 + 2 * i + 1] << 8 for i in range(1, 16)]
                   for r in BG_ROWS}}
    lt = G.decompress(rom, current_source(rom, LOGO_TILES))[:LOGO_BYTES]
    lm = G.decompress(rom, current_source(rom, LOGO_MAP))
    logo = {'tiles': lt, 'map': [lm[2 * i] | lm[2 * i + 1] << 8 for i in range(1024)],
            'pals': {p: [0] + _colors(rom, a + 0, 9 if p == 4 else n) + [0] * (6 if p == 4 else 0)
                     for p, a, n in LOGO_PALS}}
    ot = G.decompress(rom, current_source(rom, OBJ_TILES))
    sprites = []
    for i in range(2, OBJECT_COUNT):       # what Start shows (the sliding sword ends where $99:FEAC is)
        d = _fo(OBJECTS + 13 * i)
        sbank = rom[d + 2]
        script = sbank << 16 | rom[d] | rom[d + 1] << 8
        frames = sbank << 16 | rom[d + 3] | rom[d + 4] << 8
        ox, oy = rom[d + 5] | rom[d + 6] << 8, rom[d + 7] | rom[d + 8] << 8
        tadd, aor = rom[d + 9] | rom[d + 10] << 8, rom[d + 11] | rom[d + 12] << 8
        k = rom[_fo(script)]
        if k == 0x80 or k == 0:
            continue
        meta = sbank << 16 | (frames + _w(rom, frames + 2 * (k - 1))) & 0xFFFF
        n = _w(rom, meta)
        for j in range(n):
            e = meta + 2 + 5 * j
            xw, yb, ta = _w(rom, e), rom[_fo(e + 2)], _w(rom, e + 3)
            ta = (ta + tadd) & 0xFFFF | aor
            x = (xw + ox) & 0x1FF
            x = x - 512 if x >= 256 else x
            y = ((yb - 256 if yb & 0x80 else yb) + oy) & 0xFF
            sprites.append((x, y, ta & 0x1FF, ta >> 8, bool(xw & 0x8000)))
    emblem = {'tiles': ot, 'sprites': sprites,
              'pals': {p: [0] + _colors(rom, a + 0, n) for p, a, n in OBJ_PALS}}
    return {'background': bg, 'logo': logo, 'emblem': emblem}


# ---------------------------------------------------------------- drawing

def _draw_bg(layer, scroll, out, prio=None):
    """Draw a BG layer onto out (W*H list of colours or None).  prio: only entries with that priority."""
    tiles, m, pals = layer['tiles'], layer['map'], layer['pals']
    cache = {}
    for y in range(H):
        my = (y + scroll + 1) & 255
        for tx in range(32):
            e = m[(my >> 3) * 32 + tx]
            if prio is not None and bool(e & 0x2000) != prio:
                continue
            t, p = e & 0x3FF, e >> 10 & 7
            if t not in cache:
                cache[t] = _tile_px(tiles, t)
            ty = my & 7
            row = cache[t][7 - ty if e & 0x8000 else ty]
            pal = pals.get(p)
            for xx in range(8):
                c = row[7 - xx if e & 0x4000 else xx]
                if c and pal and c < len(pal):
                    out[y * W + tx * 8 + xx] = pal[c]


def _draw_sprites(layer, out):
    tiles, pals = layer['tiles'], layer['pals']
    for x, y, t, a, big in reversed(layer['sprites']):
        size = 16 if big else 8
        pal = pals.get(a >> 1 & 7)
        if not pal:
            continue
        for cy in range(size // 8):
            for cx in range(size // 8):
                tt = (t & 0x100) | ((t & 0xF0) + (cy << 4)) & 0xF0 | (t + cx) & 0x0F
                px = _tile_px(tiles, tt)
                for yy in range(8):
                    for xx in range(8):
                        c = px[yy][xx]
                        if not c:
                            continue
                        sx = x + ((size - 8 - cx * 8) + (7 - xx) if a & 0x40 else cx * 8 + xx)
                        sy = y + ((size - 8 - cy * 8) + (7 - yy) if a & 0x80 else cy * 8 + yy)
                        if 0 <= sx < W and 0 <= sy < H:
                            out[sy * W + sx] = pal[c]


def render(layers, which=None):
    """RGBA rows of the title (which=None) or of one layer."""
    out = [None] * (W * H)
    if which in (None, 'background'):
        _draw_bg(layers['background'], BG_SCROLL, out)
    if which is None:              # back to front: BG2, BG1 low priority, sprites (2), BG1 high priority
        _draw_bg(layers['logo'], LOGO_SCROLL, out, prio=False)
    if which in (None, 'emblem'):
        _draw_sprites(layers['emblem'], out)
    if which in (None, 'logo'):
        _draw_bg(layers['logo'], LOGO_SCROLL, out, prio=None if which else True)
    rows = []
    for y in range(H):
        r = bytearray()
        for c in out[y * W:(y + 1) * W]:
            if c is None:
                r += bytes((0, 0, 0, 255 if which is None else 0))
            else:
                r += bytes(_rgb(c) + (255,))
        rows.append(bytes(r))
    return rows


def png(layers, which=None, scale=1):
    rows = render(layers, which)
    if scale > 1:
        rows = [bytes(b for i in range(0, len(r), 4) for _ in range(scale) for b in r[i:i + 4])
                for r in rows for _ in range(scale)]
    return G.png(W * scale, H * scale, rows)


# ---------------------------------------------------------------- colour reduction

def _dist(a, b):
    dr, dg, db = (a & 31) - (b & 31), (a >> 5 & 31) - (b >> 5 & 31), (a >> 10 & 31) - (b >> 10 & 31)
    return 3 * dr * dr + 4 * dg * dg + 2 * db * db


def _median_cut(counts, n):
    """Up to n colours for a {colour: weight} dict."""
    if len(counts) <= n:
        return sorted(counts)
    boxes = [[(c & 31, c >> 5 & 31, c >> 10 & 31, w) for c, w in counts.items()]]
    while len(boxes) < n:
        best, bi = -1, -1
        for i, b in enumerate(boxes):
            if len(b) < 2:
                continue
            rng = max(max(p[k] for p in b) - min(p[k] for p in b) for k in range(3))
            score = rng * sum(p[3] for p in b) ** 0.5
            if score > best:
                best, bi = score, i
        if bi < 0:
            break
        b = boxes.pop(bi)
        k = max(range(3), key=lambda k: max(p[k] for p in b) - min(p[k] for p in b))
        b.sort(key=lambda p: p[k])
        half, acc, cut = sum(p[3] for p in b) / 2, 0, 1
        for i, p in enumerate(b):
            acc += p[3]
            if acc >= half:
                cut = min(max(i + 1, 1), len(b) - 1)
                break
        boxes += [b[:cut], b[cut:]]
    out = []
    for b in boxes:
        tw = sum(p[3] for p in b)
        r, g, bl = (round(sum(p[k] * p[3] for p in b) / tw) for k in range(3))
        c = r | g << 5 | bl << 10
        if c not in out:
            out.append(c)
    return out


def _nearest(c, pal, memo):
    key = (c, id(pal))
    v = memo.get(key)
    if v is None:
        v = min(range(len(pal)), key=lambda i: _dist(c, pal[i]))
        memo[key] = v
    return v


def _cell_error(counts, pal, memo):
    return sum(w * _dist(c, pal[_nearest(c, pal, memo)]) for c, w in counts.items())


def reduce_cells(cells, sizes):
    """cells: lists of SNES colours (None = colour 0).  sizes: colours per palette (without colour 0).
    Returns (palettes: [[colours]], pal_of_cell, exact)."""
    from collections import Counter
    counts = [Counter(c for c in cell if c is not None) for cell in cells]
    # exact: pack the colour sets into the palettes
    pals = [set() for _ in sizes]
    assign = [0] * len(cells)
    order = sorted(range(len(cells)), key=lambda i: -len(counts[i]))
    ok = True
    for i in order:
        s = set(counts[i])
        best = None
        for p, have in enumerate(pals):
            grow = len(s - have)
            if len(have) + grow <= sizes[p] and (best is None or grow < best[0]):
                best = (grow, p)
        if best is None:
            ok = False
            break
        pals[best[1]] |= s
        assign[i] = best[1]
    if ok:
        return [sorted(p) for p in pals], assign, True
    # lossy: group cells by their average colour, a median cut per group, then settle
    used = [i for i in range(len(cells)) if counts[i]]

    def mean(i):
        tw = sum(counts[i].values())
        return tuple(sum((c >> s & 31) * w for c, w in counts[i].items()) / tw for s in (0, 5, 10))
    means = {i: mean(i) for i in used}
    k = len(sizes)
    cents = [means[used[0]]] if used else [(0, 0, 0)]
    while len(cents) < k and used:
        far = max(used, key=lambda i: min(sum((a - b) ** 2 for a, b in zip(means[i], c)) for c in cents))
        cents.append(means[far])
    while len(cents) < k:
        cents.append(cents[0])
    for _ in range(6):
        for i in used:
            assign[i] = min(range(k), key=lambda j: sum((a - b) ** 2 for a, b in zip(means[i], cents[j])))
        for j in range(k):
            mem = [i for i in used if assign[i] == j]
            if mem:
                cents[j] = tuple(sum(means[i][d] for i in mem) / len(mem) for d in range(3))
    for _ in range(3):
        palettes = []
        for j in range(k):
            tot = Counter()
            for i in used:
                if assign[i] == j:
                    tot.update(counts[i])
            palettes.append(_median_cut(tot, sizes[j]) or [0])
        memo = {}
        changed = False
        for i in used:
            best = min(range(k), key=lambda j: _cell_error(counts[i], palettes[j], memo))
            if best != assign[i]:
                assign[i], changed = best, True
        if not changed:
            break
    palettes = []
    for j in range(k):
        tot = Counter()
        for i in used:
            if assign[i] == j:
                tot.update(counts[i])
        palettes.append(_median_cut(tot, sizes[j]) or [0])
    return palettes, assign, False


def _index_cell(cell, pal, memo):
    return [0 if c is None else 1 + _nearest(c, pal, memo) for c in cell]


# ---------------------------------------------------------------- tile sets

def _flips(px, n):
    """The 4 flips of an n x n index list: (key, hflip, vflip)."""
    rows = [tuple(px[y * n:(y + 1) * n]) for y in range(n)]
    out = []
    for hf in (0, 1):
        for vf in (0, 1):
            r = rows[::-1] if vf else rows
            r = [x[::-1] for x in r] if hf else r
            out.append((tuple(v for x in r for v in x), hf, vf))
    return out


def _merge_tiles(uniq, uses, limit, palettes, n):
    """Too many tiles: merge the most alike (same palette) until `limit` remain.
    uniq: [(pal, key)]; returns a list mapping each to the index of the tile kept for it."""
    keep = list(range(len(uniq)))
    excess = len(uniq) - limit
    if excess <= 0:
        return keep

    def sig(i):
        p, key = uniq[i]
        pal = palettes[p]
        h = n // 2
        out = []
        for by in (0, h):
            for bx in (0, h):
                acc = [0, 0, 0]
                for y in range(by, by + h):
                    for x in range(bx, bx + h):
                        v = key[y * n + x]
                        c = pal[v - 1] if v else 0
                        acc[0] += c & 31
                        acc[1] += c >> 5 & 31
                        acc[2] += c >> 10 & 31
                out += acc
        return out
    sigs = [sig(i) for i in range(len(uniq))]
    pairs = []
    for i in range(len(uniq)):
        si, pi = sigs[i], uniq[i][0]
        for j in range(i + 1, len(uniq)):
            if uniq[j][0] != pi:
                continue
            sj = sigs[j]
            pairs.append((sum((a - b) * (a - b) for a, b in zip(si, sj)), i, j))
    pairs.sort()
    parent = list(range(len(uniq)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for _, i, j in pairs:
        if excess <= 0:
            break
        a, b = root(i), root(j)
        if a == b:
            continue
        if uses[a] < uses[b]:
            a, b = b, a
        parent[b] = a
        uses[a] += uses[b]
        excess -= 1
    return [root(i) for i in range(len(uniq))]


def _bg_layer(px, scroll, sizes, pal_numbers, limit, prio, black_is_zero, what, blank=(0,)):
    """Tiles + map for a 256x224 picture on a scrolled BG.  px: W*H SNES colours or None."""
    canvas = [None] * (256 * 256)
    for y in range(H):
        my = (y + scroll + 1) & 255
        canvas[my * 256:(my + 1) * 256] = px[y * W:(y + 1) * W]
    if black_is_zero:
        canvas = [None if c == 0 else c for c in canvas]
    cells = []
    for ty in range(32):
        for tx in range(32):
            cells.append([canvas[(ty * 8 + y) * 256 + tx * 8 + x] for y in range(8) for x in range(8)])
    palettes, assign, exact = reduce_cells(cells, sizes)
    memo = {}
    uniq, where, uses = [], {}, []
    entries = []
    for i, cell in enumerate(cells):
        if all(c is None for c in cell):
            entries.append(None)
            continue
        idx = _index_cell(cell, palettes[assign[i]], memo)
        if not any(idx):
            entries.append(None)
            continue
        hit = None
        for key, hf, vf in _flips(idx, 8):
            if (assign[i], key) in where:
                hit = (where[(assign[i], key)], hf, vf)
                break
        if hit is None:
            where[(assign[i], tuple(idx))] = len(uniq)
            uniq.append((assign[i], tuple(idx)))
            uses.append(0)
            hit = (len(uniq) - 1, 0, 0)
        uses[hit[0]] += 1
        entries.append(hit)
    merged = _merge_tiles(uniq, list(uses), limit - len(blank), palettes, 8)     # blank tiles stay empty
    kept = sorted(set(merged))
    free = [n for n in range(limit) if n not in blank]
    number = {t: free[k] for k, t in enumerate(kept)}
    tiles = bytearray(32 * ((max(number.values()) + 1) if number else 1))
    for t in kept:
        key = uniq[t][1]
        n = number[t]
        tiles[n * 32:n * 32 + 32] = _tile_bytes([key[y * 8:(y + 1) * 8] for y in range(8)])
    m = []
    for e in entries:
        if e is None:
            m.append(0)
            continue
        t, hf, vf = e
        if merged[t] != t:            # merged into another tile: use it unflipped
            t, hf, vf = merged[t], 0, 0
        p = pal_numbers[uniq[t][0]]
        m.append(number[t] | p << 10 | (0x2000 if prio else 0) | (0x4000 if hf else 0) | (0x8000 if vf else 0))
    pals = {pal_numbers[j]: [0] + palettes[j] + [0] * (15 - len(palettes[j])) for j in range(len(sizes))}
    note = {'tiles': len(kept) + len(blank), 'tile_limit': limit, 'merged': len(uniq) - len(kept), 'exact': exact,
            'colours': sum(len(p) for p in palettes)}
    return {'tiles': bytes(tiles), 'map': m, 'pals': pals}, note


def _picture(data, what):
    try:
        w, h, px = G.read_png(data)
    except Exception as e:      # noqa: BLE001
        raise ValueError(f'{what}: not a PNG picture ({e})')
    if (w, h) != (W, H):
        raise ValueError(f'{what}: the title is {W}x{H}; this picture is {w}x{h}')
    return [None if a < 128 else G.snes_color((r, g, b)) for r, g, b, a in px]


def convert_background(data):
    px = _picture(data, 'background.png')
    return _bg_layer(px, BG_SCROLL, (15, 15), BG_ROWS, BG_TILE_LIMIT, False, True, 'background')


def convert_logo(data):
    px = _picture(data, 'logo.png')
    layer, note = _bg_layer(px, LOGO_SCROLL, tuple(n for _, _, n in LOGO_PALS), tuple(p for p, _, _ in LOGO_PALS),
                            LOGO_BYTES // 32, True, False, 'logo', LOGO_BLANK)
    return layer, note


def _emblem_plan(px, x0, y0, x1, y1):
    """[(x, y, big, palette, indices)] for a 16x16 grid from (x0, y0); a square whose quarters need
    two palettes is a 16x16 sprite in the palette most of them use, with 8x8 sprites in front for
    the others."""
    squares = []
    for cy in range(y0, y1 + 1, 16):
        for cx in range(x0, x1 + 1, 16):
            qs = []
            for qx, qy in ((0, 0), (8, 0), (0, 8), (8, 8)):
                q = [px[(cy + qy + y) * W + cx + qx + x] if 0 <= cy + qy + y < H and 0 <= cx + qx + x < W else None
                     for y in range(8) for x in range(8)]
                qs.append(q if any(c is not None for c in q) else None)
            if any(qs):
                squares.append((cx, cy, qs))
    units = [q for _, _, qs in squares for q in qs if q]
    palettes, assign, exact = reduce_cells(units, tuple(n for _, _, n in OBJ_PALS))
    memo, k, plan, front = {}, 0, [], []
    for cx, cy, qs in squares:
        mine = []
        for q in qs:
            mine.append(assign[k] if q else None)
            k += 1 if q else 0
        votes = [p for p in mine if p is not None]
        main = max(set(votes), key=votes.count)
        idx = [0] * 256
        for n, (qx, qy) in enumerate(((0, 0), (8, 0), (0, 8), (8, 8))):
            if not qs[n]:
                continue
            sub = _index_cell(qs[n], palettes[mine[n]], memo)
            if mine[n] == main:
                for y in range(8):
                    idx[(qy + y) * 16 + qx:(qy + y) * 16 + qx + 8] = sub[y * 8:(y + 1) * 8]
            else:
                front.append((cx + qx, cy + qy, False, mine[n], sub))
        if any(idx):
            plan.append((cx, cy, True, main, idx))
    return front + plan, palettes, exact


def _empty_quarters(idx16):
    return sum(1 for qx, qy in ((0, 0), (8, 0), (0, 8), (8, 8))
               if not any(idx16[(qy + y) * 16 + qx + x] for y in range(8) for x in range(8)))


def _emblem_layout(plan):
    """(tile data, sprites) for a plan, or None if its pieces need more than the sprite tiles."""
    tiles = bytearray(OBJ_BYTES)
    big_keys, small_keys, sprites = {}, {}, []
    nbig = nsmall = 0
    for x, y, big, pal, idx in plan:
        n = 16 if big else 8
        keys = big_keys if big else small_keys
        hit = None
        for key, hf, vf in _flips(idx, n):
            if (pal, key) in keys:
                hit = (keys[(pal, key)], hf, vf)
                break
        if hit is None:
            if big:
                t = (nbig // 8) * 32 + (nbig % 8) * 2
                nbig += 1
                if t + 17 >= OBJ_BYTES // 32 - nsmall:
                    return None
                for qx, qy in ((0, 0), (8, 0), (0, 8), (8, 8)):
                    tt = t + (1 if qx else 0) + (16 if qy else 0)
                    tiles[tt * 32:tt * 32 + 32] = _tile_bytes([idx[(qy + yy) * 16 + qx:(qy + yy) * 16 + qx + 8]
                                                               for yy in range(8)])
            else:
                t = OBJ_BYTES // 32 - 1 - nsmall      # single tiles fill the space from the end
                nsmall += 1
                if t < 0:
                    return None
                tiles[t * 32:t * 32 + 32] = _tile_bytes([idx[yy * 8:(yy + 1) * 8] for yy in range(8)])
            keys[(pal, tuple(idx))] = t
            hit = (t, 0, 0)
        t, hf, vf = hit
        p = OBJ_PALS[pal][0]
        a = (t >> 8) | p << 1 | 0x20 | (0x40 if hf else 0) | (0x80 if vf else 0)
        sprites.append((x, y, t & 0x1FF, a, big))
    used = {(k // 8) * 32 + (k % 8) * 2 + d for k in range(nbig) for d in (0, 1, 16, 17)}
    if used & set(range(OBJ_BYTES // 32 - nsmall, OBJ_BYTES // 32)) or max(used | {0}) >= OBJ_BYTES // 32:
        return None
    return bytes(tiles), sprites


def convert_emblem(data):
    """Sprites for the emblem (see _emblem_plan), at most 128, in the title's 356 sprite tiles."""
    px = _picture(data, 'emblem.png')
    sizes = tuple(n for _, _, n in OBJ_PALS)
    xs = [i % W for i, c in enumerate(px) if c is not None]
    ys = [i // W for i, c in enumerate(px) if c is not None]
    if not xs:
        return {'tiles': b'', 'sprites': [], 'pals': {p: [0] * 16 for p, _, _ in OBJ_PALS}}, \
            {'sprites': 0, 'hidden': True, 'exact': True, 'colours': 0}
    best = None
    for ox in range(0, 16, 4):            # the 16x16 grid's offset that needs the fewest sprites
        for oy in range(0, 16, 4):
            got = _emblem_plan(px, min(xs) - ox, min(ys) - oy, max(xs), max(ys))
            if best is None or len(got[0]) < len(best[0]):
                best = got
    plan, palettes, exact = best
    if len(plan) > SPRITE_LIMIT:
        raise ValueError(f'emblem.png: the emblem is made of sprites (16x16 squares), at most {SPRITE_LIMIT}; '
                         f'this picture needs {len(plan)}. Make it smaller, or put the big parts in the background.')
    while True:
        got = _emblem_layout(plan)
        if got:
            break
        # out of sprite tiles: a 16x16 square with empty quarters becomes 8x8 sprites (fewer tiles)
        bigs = [i for i, e in enumerate(plan) if e[2] and _empty_quarters(e[4])]
        if not bigs or len(plan) - 1 + 4 - _empty_quarters(plan[bigs[0]][4]) > SPRITE_LIMIT:
            raise ValueError(f'emblem.png: too many different pieces for the {OBJ_BYTES // 32} sprite tiles '
                             'the title has; make it smaller or simpler')
        i = max(bigs, key=lambda i: _empty_quarters(plan[i][4]))
        x, y, _, pal, idx = plan.pop(i)
        for qx, qy in ((0, 0), (8, 0), (0, 8), (8, 8)):
            sub = [idx[(qy + yy) * 16 + qx + xx] for yy in range(8) for xx in range(8)]
            if any(sub):
                plan.append((x + qx, y + qy, False, pal, sub))
    tiles, sprites = got
    if len(sprites) > SPRITE_LIMIT:
        raise ValueError(f'emblem.png: needs {len(sprites)} sprites, at most {SPRITE_LIMIT}; make it smaller')
    pals = {OBJ_PALS[j][0]: [0] + palettes[j] + [0] * (15 - len(palettes[j])) for j in range(len(sizes))}
    return {'tiles': bytes(tiles), 'sprites': sprites, 'pals': pals}, \
        {'sprites': len(sprites), 'sprite_limit': SPRITE_LIMIT, 'exact': exact,
         'colours': sum(len(p) for p in palettes)}


CONVERT = {'background': convert_background, 'logo': convert_logo, 'emblem': convert_emblem}


def _pack(layer):
    return {k: (v.hex() if isinstance(v, bytes) else
                {str(p): c for p, c in v.items()} if isinstance(v, dict) else v) for k, v in layer.items()}


def _unpack(d):
    out = {}
    for k, v in d.items():
        if k == 'tiles':
            out[k] = bytes.fromhex(v)
        elif k == 'pals':
            out[k] = {int(p): c for p, c in v.items()}
        elif k == 'sprites':
            out[k] = [tuple(s) for s in v]
        else:
            out[k] = v
    return out


def converted(proj, name, data=None):
    """(layer, note) for title/<name>.png (or the given PNG bytes), cached in title/.cache."""
    if data is None:
        p = os.path.join(proj, FOLDER, name + '.png')
        if not os.path.exists(p):
            return None
        data = open(p, 'rb').read()
    h = hashlib.sha1(data + bytes([CONVERTER])).hexdigest()[:16]
    cdir = os.path.join(proj, FOLDER, '.cache')
    cp = os.path.join(cdir, f'{name}-{h}.json')
    if os.path.exists(cp):
        try:
            d = json.load(open(cp))
            return _unpack(d['layer']), d['note']
        except (ValueError, KeyError):
            pass
    layer, note = CONVERT[name](data)
    os.makedirs(cdir, exist_ok=True)
    for f in os.listdir(cdir):
        if f.startswith(name + '-'):
            os.remove(os.path.join(cdir, f))
    json.dump({'layer': _pack(layer), 'note': note}, open(cp, 'w'))
    return layer, note


def project_layers(rom, proj, base=None):
    """The title as the project will have it: the game's layers with the project's pictures in."""
    lay = dict(base or read_layers(rom))
    for name in LAYERS:
        got = converted(proj, name)
        if got:
            lay[name] = got[0]
    return lay


# ---------------------------------------------------------------- writing

def _repoint(rom, stream, new):
    for kind, *args in REFS[stream]:
        if kind == 'imm':
            a, b = args
            o = _fo(a)
            rom[o], rom[o + 1] = new & 0xFF, new >> 8 & 0xFF
            rom[_fo(b)] = new >> 16
        else:
            o = _fo(args[0])
            rom[o:o + 3] = new.to_bytes(3, 'little')


def _check_refs(rom):
    for stream, refs in REFS.items():
        for kind, *args in refs:
            if _ref_target(rom, kind, *args) != stream:
                raise SystemExit('title screen: this ROM\'s title code is not the one the kit knows '
                                 f'(${args[0] >> 16:02X}:{args[0] & 0xFFFF:04X}); left as it is')


def _put(rom, far, stream, data):
    blob = fe4lz.compress(data)
    a = far.alloc(len(blob) + 1)
    rom[_fo(a):_fo(a) + len(blob)] = blob
    _repoint(rom, stream, a)


def _put_colors(rom, a, colors):
    o = _fo(a)
    for i, c in enumerate(colors):
        rom[o + 2 * i], rom[o + 2 * i + 1] = c & 0xFF, c >> 8


def apply(rom, proj, far, space):
    """Write the project's title pictures.  Returns how many layers changed."""
    have = [n for n in LAYERS if os.path.exists(os.path.join(proj, FOLDER, n + '.png'))]
    if not have:
        return 0
    _check_refs(rom)
    done = 0
    for name in have:
        try:
            layer, _ = converted(proj, name)
        except ValueError as e:
            raise SystemExit(f'{FOLDER}/{e}')
        if name == 'background':
            old = G.decompress(rom, BG_TILES)
            tiles = layer['tiles'].ljust(BG_TILE_LIMIT * 32, b'\0') + old[BG_TILE_LIMIT * 32:]
            _put(rom, far, BG_TILES, tiles)
            _put(rom, far, BG_MAP, b''.join(e.to_bytes(2, 'little') for e in layer['map']))
            block = bytearray(G.decompress(rom, BG_PALS))
            for r in BG_ROWS:
                for i in range(1, 16):
                    c = layer['pals'][r][i]
                    block[r * 32 + 2 * i], block[r * 32 + 2 * i + 1] = c & 0xFF, c >> 8
            _put(rom, far, BG_PALS, bytes(block))
        elif name == 'logo':
            _put(rom, far, LOGO_TILES, layer['tiles'].ljust(LOGO_BYTES, b'\0'))
            _put(rom, far, LOGO_MAP, b''.join(e.to_bytes(2, 'little') for e in layer['map']))
            for p, a, n in LOGO_PALS:
                _put_colors(rom, a, layer['pals'][p][1:1 + n])
            # the old logo's drop shadow (tile $20 is the shadow layer's empty tile)
            _put(rom, far, SHADOW_MAP, b'\x20\x00' * 1024)
        else:
            _write_emblem(rom, far, space, layer)
        done += 1
    return done


EMBLEM_BANKS = (0xB3, 0x90, 0x8E, 0x89, 0x88, 0xAE, 0x83, 0x81)


def _write_emblem(rom, far, space, layer):
    sprites = layer['sprites']
    if sprites:
        _put(rom, far, OBJ_TILES, layer['tiles'].ljust(OBJ_BYTES, b'\0'))
        for p, a, n in OBJ_PALS:
            _put_colors(rom, a, layer['pals'][p][1:1 + n])
    # one block in one bank: frames table, two scripts, the metasprite, an empty metasprite
    meta = bytearray(len(sprites).to_bytes(2, 'little'))
    for x, y, t, attr, big in sprites:
        dx, dy = x - OBJ_X, y - OBJ_Y
        meta += ((dx & 0x7FFF) | (0x8000 if big else 0)).to_bytes(2, 'little')
        meta += bytes([dy & 0xFF])
        meta += (t & 0xFF | (attr | (t >> 8 & 1)) << 8).to_bytes(2, 'little')
    size = 4 + 4 + 4 + len(meta) + 2
    # the sprite routine runs with DB = this data's bank and writes the OAM buffer with STA $1C00,X:
    # the bank has to be one that mirrors RAM ($80-$BF), in its ROM half
    base = None
    for b in EMBLEM_BANKS:
        try:
            _, base = space.alloc(b << 16, size)
            break
        except SystemExit:
            continue
    if base is None:
        raise SystemExit('title screen: no room left in banks $80-$BF for the emblem\'s sprite list')
    table, s_main, s_empty, m_at, e_at = base, base + 4, base + 8, base + 12, base + 12 + len(meta)
    blk = bytearray()
    blk += ((m_at - table) & 0xFFFF).to_bytes(2, 'little') + ((e_at - table) & 0xFFFF).to_bytes(2, 'little')
    blk += bytes([0x01, 0x10, 0x80, 0x01])          # show frame 0, then again
    blk += bytes([0x02, 0x10, 0x80, 0x01])          # show frame 1 (empty), then again
    blk += meta + b'\0\0'
    rom[_fo(base):_fo(base) + len(blk)] = blk
    bank = base >> 16
    for i in range(OBJECT_COUNT):
        d = _fo(OBJECTS + 13 * i)
        script = s_main if i == EMBLEM_OBJECT and sprites else s_empty
        rom[d:d + 13] = ((script & 0xFFFF).to_bytes(2, 'little') + bytes([bank])
                         + (table & 0xFFFF).to_bytes(2, 'little') + OBJ_X.to_bytes(2, 'little')
                         + OBJ_Y.to_bytes(2, 'little') + b'\0\0\0\0')
