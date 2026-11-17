"""Custom map tile sets (kit v55): a chapter's whole set of 1024 map tiles as one picture you can
replace, and a whole chapter map drawn as one picture.

How the game loads a chapter's map graphics (ROM_MAP "Map graphics"):
  * 8x8 tiles 0-639: one raw block every chapter shares ($D9:0000), sent to VRAM $0000 by a DMA queued
    at $88:80C9 (chapter start) and at $88:8252 (the same code again, for a loaded game).  Tiles
    128-255 change during play (the water: $88:CFC2 sends frames from bank $DC to tiles 160-191).
  * 8x8 tiles 640-767: the chapter's own (header +6, compressed, to VRAM $5000).
  * 16x16 tiles ("metatiles", 4 tilemap words each) 0-255: the chapter's own (+3, compressed) at
    $7F:0000; 256-1023: shared, raw at $D9:5000, copied to $7F:0800 by the two places above.
  * palette rows 1-7: the chapter's own (+9, raw); the map's tiles use rows 1-5.

A chapter with a custom set gets its own copy of all of it.  Both loader places jump (JML) to a small
routine that looks the chapter ($0D6A) up in a table: for a custom chapter it queues the DMA from the
chapter's own tile block and copies the chapter's own 16x16 tiles 256-1023; for the others it runs the
game's own 32 bytes.  Tiles 0-255, tiles 640-767, the palettes and the terrain go through the chapter
header as for any chapter.

Project file: maps/tilesets/<chapter>.png (prologue.png, ch01.png ... endgame.png), 512 x 512: the
chapter's 1024 tiles as a 32 x 32 grid of 16 x 16 pictures, tile k at column k % 32, row k // 32.
Any colours: the build reduces them to 5 palettes of 15 (pure black and transparency are free) and
the 8x8 pieces to 639 (the most alike are merged when there are more).  8x8 tiles 128-255 keep the
game's animated water.

Tiles the game itself puts on the map during play (a village as raiders damage and destroy it, castle
and village footprints, the chapter's scripted map changes such as a bridge or a wall) are read from the
ROM: importing a whole-map picture keeps them where they are and never uses their numbers for other
pictures, so those changes still show the pictures the game expects.
"""
import hashlib
import json
import os
from collections import Counter

import fe4gfx as G
import fe4lz
import fe4maps as M
import fe4title as T
from dis65816 import snes_to_file as _fo

FOLDER = 'maps/tilesets'
CONVERTER = 1
ATLAS_W = 512
FREE_TILES = [t for t in range(1, 640) if not 128 <= t < 256] + list(range(640, 768))   # 639; 0 stays blank
ROWS = (1, 2, 3, 4, 5)
SITES = (0x0880C9, 0x088252)
BACK = (0x8880E9, 0x888272)
ORIGINAL = bytes.fromhex('22bda48002 0000d9 005080 0000 22059388 a2fe17 bf0050d9 9f00087f caca 10f4'.replace(' ', ''))
CHAPTER = 0x000D6A
CODE_BANKS = (0xB3, 0x90, 0x8E, 0x89, 0x88, 0xAE, 0x83, 0x81)


def atlas_file(ch):
    return f'{FOLDER}/{M.MAP_NAMES[ch]}.png'


def project_chapters(proj):
    """{chapter: png bytes} for the chapters that have a tile set picture on disk."""
    out = {}
    for ch in range(M.MAP_COUNT):
        p = os.path.join(proj, *atlas_file(ch).split('/'))
        if os.path.exists(p):
            out[ch] = open(p, 'rb').read()
    return out


def project_words(proj, rom, ch):
    """The chapter's map as the project has it (maps/chNN_name.csv), else the game's."""
    p = os.path.join(proj, 'maps', 'ch%02d_%s.csv' % (ch, M.MAP_NAMES[ch]))
    if os.path.exists(p):
        try:
            return M.read_csv(p)
        except (ValueError, SystemExit):
            pass
    return M.load_map(rom, ch)


# ---------------------------------------------------------------- tiles the game changes during play
def _w(rom, a):
    o = _fo(a)
    if o is None:
        raise IndexError(a)
    return rom[o] | rom[o + 1] << 8


def _block_ids(rom, a):
    o = _fo(a)
    bw, bh = rom[o], rom[o + 1]
    if not (0 < bw <= 16 and 0 < bh <= 16):
        return set()
    return {v & 0x3FF for v in (_w(rom, a + 2 + 2 * i) for i in range(bw * bh)) if v < 0x8000}


# found in the clean ROM; used when this ROM's tables don't read as the kit expects
_GENERIC = {0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 0x20, 0x21, 0x22, 42, 43, 44, 45, 46, 47,
            0x50, 0x53, 0x56, 0x72, 0x75, 0x78, 159, 177, 179, 191}


def generic_reserved(rom):
    """Tiles every chapter's map changes to or from during play:
      $87:EFD8   a tile $50, $53 or $56 next to a raided village becomes one of 4 by damage ($87:F007)
      $87:F0A4   village damage stages: 4 kinds x 9 blocks of tiles pasted over the village
      $87:F453   per site kind, +8: the footprint pasted when a castle or village changes
      $87:EF38, $87:F096   two more single-tile pastes
      $88:B3C2   puts tile 0 on a cell"""
    try:
        ids = {0}
        for x in range(7):               # X = tile - $50, a byte index into word offsets (overlapping)
            off = _w(rom, 0x87F007 + x)
            if not 8 <= off <= 0x40 or off % 2:
                continue
            ids.add(0x50 + x)
            ids |= {_w(rom, 0x87F007 + off + 2 * j) & 0xFF for j in range(4)}
        kinds = _w(rom, 0x87F0A4) // 2
        for k in range(min(kinds, 8)):
            base = 0x87F0A4 + _w(rom, 0x87F0A4 + 2 * k)
            for j in range(9):
                p = _w(rom, base + 2 * j)
                if p:
                    ids |= _block_ids(rom, 0x870000 | p)
        for k in range(7):
            e = 0x87F453 + _w(rom, 0x87F453 + 2 * k)
            p = _w(rom, e + 8)
            if p >= 0x8000:
                ids |= _block_ids(rom, 0x870000 | p)
        ids |= _block_ids(rom, 0x87EF38) | _block_ids(rom, 0x87F096)
        return ids if ids >= {0, 159, 191} else set(_GENERIC)
    except IndexError:
        return set(_GENERIC)


def chapter_changes(rom, ch):
    """The chapter's scripted map changes (info block +2: 7-byte records [chapter, ?, flag, x, y,
    block ptr16], $FFFF at the end): [(x, y, width, height, [tile words])]."""
    import fe4locations as LOC
    out = []
    try:
        a, fo = LOC.info_block(rom, ch)
        bank = a & 0xFF0000
        q = bank | _w(rom, a + 2)
        for _ in range(64):
            if _w(rom, q) == 0xFFFF:
                break
            o = _fo(q)
            b = bank | _w(rom, q + 5)
            bo = _fo(b)
            bw, bh = rom[bo], rom[bo + 1]
            out.append((rom[o + 3], rom[o + 4], bw, bh, [_w(rom, b + 2 + 2 * i) for i in range(bw * bh)]))
            q += 7
    except IndexError:
        pass
    return out


def reserved(rom, ch):
    ids = generic_reserved(rom)
    for _, _, _, _, words in chapter_changes(rom, ch):
        ids |= {v & 0x3FF for v in words if v < 0x8000}
    return ids


# ---------------------------------------------------------------- pictures
def _snes_cells(px, width, x0, y0, n):
    """SNES colours (None = colour 0) of an n x n square."""
    out = []
    for y in range(n):
        row = px[(y0 + y) * width + x0:(y0 + y) * width + x0 + n]
        for r, g, b, a in row:
            c = G.snes_color((r, g, b)) if a >= 128 else None
            out.append(None if c == 0 else c)
    return out


def _rgba_png(width, height, cells, side=16, per_row=None):
    """A PNG from {index: n*n SNES colours or None}, laid out per_row to a row."""
    per_row = per_row or width // side
    rows = [bytearray(width * 4) for _ in range(height)]
    for k, cell in cells.items():
        bx, by = (k % per_row) * side, (k // per_row) * side
        for y in range(side):
            line = rows[by + y]
            for x in range(side):
                c = cell[y * side + x]
                if c is None:
                    continue
                o = (bx + x) * 4
                line[o:o + 4] = bytes(((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31, 255))
    return G.png(width, height, [bytes(r) for r in rows])


def gfx_cells(g, k):
    """Metatile k of a fe4maptiles.ChapterGfx as 256 SNES colours (None = colour 0)."""
    out = []
    for row in g.metatile_rgba(k):
        for r, gg, b, a in row:
            c = G.snes_color((r, gg, b))
            out.append(None if c == 0 else c)
    return out


def atlas_png_of(g):
    return _rgba_png(ATLAS_W, ATLAS_W, {k: gfx_cells(g, k) for k in range(1024)})


def map_png(g, words, width=M.WIDTH):
    """The whole map as one picture (16 pixels a cell)."""
    h = len(words) // width
    memo = {}
    rows = [bytearray(width * 16 * 4) for _ in range(h * 16)]
    for i, w in enumerate(words[:width * h]):
        k = w & 0x3FF
        if k not in memo:
            memo[k] = [b''.join(bytes(px) for px in r) for r in g.metatile_rgba(k)]
        bx, by = (i % width) * 16 * 4, (i // width) * 16
        for y in range(16):
            rows[by + y][bx:bx + 64] = memo[k][y]
    return G.png(width * 16, h * 16, [bytes(r) for r in rows])


# ---------------------------------------------------------------- merging alike pictures
def _sig(cell, n, block):
    """Average colour of each block x block square of an n x n list of SNES colours."""
    out = []
    for by in range(0, n, block):
        for bx in range(0, n, block):
            acc = [0, 0, 0]
            for y in range(by, by + block):
                for x in range(bx, bx + block):
                    c = cell[y * n + x] or 0
                    acc[0] += c & 31
                    acc[1] += c >> 5 & 31
                    acc[2] += c >> 10 & 31
            out += acc
    return out


def _coarse(sig):
    """A 4x4-block signature (48 values) -> 2x2 blocks (12 values)."""
    out = []
    for by in (0, 2):
        for bx in (0, 2):
            for c in range(3):
                out.append(sum(sig[((by + y) * 4 + bx + x) * 3 + c] for y in (0, 1) for x in (0, 1)))
    return out


def merge_alike(groups, sigs, uses, limit, prio=None):
    """Too many different pictures: keep the `limit` that matter most (needed first, then the most used;
    each group keeps at least one) and show each of the others as the kept picture of its group that
    looks most like it.  sigs: 48-value signatures (4 x 4 blocks of r, g, b).
    Returns, for each picture, the index of the one kept for it."""
    n = len(sigs)
    if n <= limit:
        return list(range(n))
    prio = prio or [1] * n
    order = sorted(range(n), key=lambda i: (-prio[i], -uses[i], i))
    kept, seen = [], set()
    for i in order:                    # one per group first
        if groups[i] not in seen:
            seen.add(groups[i])
            kept.append(i)
    chosen = set(kept)
    for i in order:
        if len(kept) >= limit:
            break
        if i not in chosen:
            kept.append(i)
            chosen.add(i)
    by_group = {}
    for i in kept:
        by_group.setdefault(groups[i], []).append((i, _coarse(sigs[i]), sigs[i]))
    keep = list(range(n))
    for j in range(n):
        if j in chosen:
            continue
        cj, fj = _coarse(sigs[j]), sigs[j]
        cands = by_group[groups[j]]
        if len(cands) > 6:
            scored = sorted(cands, key=lambda e: sum((a - b) * (a - b) for a, b in zip(cj, e[1])))[:6]
        else:
            scored = cands
        keep[j] = min(scored, key=lambda e: sum((a - b) * (a - b) for a, b in zip(fj, e[2])))[0]
    return keep


# ---------------------------------------------------------------- the tile set picture -> SNES data
def _decode(b):
    out = []
    for y in range(8):
        p = (b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[17 + 2 * y])
        out += [sum(((p[k] >> (7 - x)) & 1) << k for k in range(4)) for x in range(8)]
    return tuple(out)


def chapter_palettes(rom, ch):
    """The chapter's palette rows 1-5 in the ROM: 5 lists of 15 SNES colours."""
    o = _fo(M.header(rom, ch)['pal'])
    return [[rom[o + (r - 1) * 32 + 2 + 2 * i] | rom[o + (r - 1) * 32 + 3 + 2 * i] << 8 for i in range(15)] for r in ROWS]


def _seeded(cells, seed):
    """Fit every cell into one of the seed palettes (adding colours to free places if need be; a few
    cells that still don't fit take the nearest colours of the palette that suits them best).
    -> (palettes, candidate palettes per cell, exact) or None when too many cells don't fit."""
    pals = [list(p) for p in seed]
    sets = [set(p) for p in pals]
    cand, misfits = [], []
    for n, cell in enumerate(cells):
        s = {c for c in cell if c is not None}
        js = [j for j in range(len(pals)) if s <= sets[j]]
        if not js and s:
            for j in range(len(pals)):
                miss = s - sets[j]
                seen, free = set(), []
                for i, c in enumerate(pals[j]):
                    if c in seen or (c == 0 and i):
                        free.append(i)
                    seen.add(c)
                if len(miss) <= len(free):
                    for c, i in zip(sorted(miss), free):
                        pals[j][i] = c
                    sets[j] = set(pals[j])
                    js = [j]
                    break
            if not js:
                misfits.append(n)
        cand.append(js)
    used = sum(1 for cell in cells if any(c is not None for c in cell))
    if len(misfits) > used // 20:
        return None
    memo = {}
    for n in misfits:
        from collections import Counter as _C
        cnt = _C(c for c in cells[n] if c is not None)
        cand[n] = [min(range(len(pals)), key=lambda j: T._cell_error(cnt, pals[j], memo))]
    return pals, cand, not misfits


def convert(data, rom, ch=None, wanted=None):
    """A 512 x 512 tile set picture -> ({'words': 4096 tilemap words, 'shared': 0x5000 bytes (tiles
    0-639), 'ctiles': 0x1000 bytes (640-767), 'pals': 5 lists of 15 SNES colours}, note).

    ch: start from that chapter's palettes (a picture in the game's colours keeps them exactly, and
    its water tiles keep animating).  wanted: the tiles that matter (on the map, or put there during
    play); when 8x8 pieces must be merged, the others' go first."""
    try:
        w, h, px = G.read_png(data)
    except Exception as e:      # noqa: BLE001
        raise ValueError(f'the tile set is not a PNG picture ({e})')
    if (w, h) != (ATLAS_W, ATLAS_W):
        raise ValueError(f'a tile set picture is {ATLAS_W} x {ATLAS_W} (32 x 32 tiles of 16 x 16); this one is {w} x {h}')
    cells = []
    for k in range(1024):
        bx, by = (k % 32) * 16, (k // 32) * 16
        for q in range(4):
            cells.append(_snes_cells(px, w, bx + (q // 2) * 8, by + (q % 2) * 8, 8))
    seeded = _seeded(cells, chapter_palettes(rom, ch)) if ch is not None else None
    anim = {}
    if seeded:
        palettes, cand, exact = seeded
        # the game's animated tiles (128-255) stay where they are: a piece drawn exactly like one uses it
        for t in range(128, 256):
            key = _decode(rom[M.SHARED_TILES + 32 * t:M.SHARED_TILES + 32 * t + 32])
            if any(key):
                for fk, hf, vf in T._flips(list(key), 8):
                    anim.setdefault(fk, (t, hf, vf))
    else:
        palettes, assign, exact = T.reduce_cells(cells, [15] * len(ROWS))
        cand = [[a] for a in assign]
    memo = {}
    uniq, where, uses, prio, entries = [], {}, [], [], []
    for i, cell in enumerate(cells):
        if all(c is None for c in cell):
            entries.append(None)
            continue
        need = 1 if wanted is None or i // 4 in wanted else 0
        hit = None
        if anim:
            for j in cand[i]:
                idx = tuple(T._index_cell(cell, palettes[j], memo))
                if idx in anim:
                    hit = ('a', j) + anim[idx]
                    break
        if hit is None:
            j = cand[i][0]
            idx = T._index_cell(cell, palettes[j], memo)
            for key, hf, vf in T._flips(idx, 8):
                if (j, key) in where:
                    hit = ('u', j, where[(j, key)], hf, vf)
                    break
            if hit is None:
                where[(j, tuple(idx))] = len(uniq)
                uniq.append((j, tuple(idx)))
                uses.append(0)
                prio.append(0)
                hit = ('u', j, len(uniq) - 1, 0, 0)
            uses[hit[2]] += 1
            prio[hit[2]] |= need
        entries.append(hit)

    def colours_of(t):
        p, key = uniq[t]
        return [palettes[p][v - 1] if v else None for v in key]
    merged = merge_alike([0] * len(uniq), [_sig(colours_of(t), 8, 2) for t in range(len(uniq))],
                         list(uses), len(FREE_TILES), prio)
    kept = sorted(set(merged), key=lambda t: (-prio[t], t))
    number = {t: FREE_TILES[k] for k, t in enumerate(kept)}
    shared = bytearray(rom[M.SHARED_TILES:M.SHARED_TILES + 0x5000])
    for t in list(range(0, 128)) + list(range(256, 640)):
        shared[t * 32:t * 32 + 32] = bytes(32)
    ctiles = bytearray(0x1000)
    for t in kept:
        key = uniq[t][1]
        tb = T._tile_bytes([key[y * 8:(y + 1) * 8] for y in range(8)])
        n = number[t]
        if n < 640:
            shared[n * 32:n * 32 + 32] = tb
        else:
            ctiles[(n - 640) * 32:(n - 640) * 32 + 32] = tb
    words = []
    lost = 0
    for i, e in enumerate(entries):
        if e is None:
            words.append(ROWS[0] << 10)
            continue
        kind, j, t, hf, vf = e
        if kind == 'u':
            if merged[t] != t:
                t, hf, vf = merged[t], 0, 0
                lost += wanted is None or i // 4 in wanted
            t = number[t]
        words.append(t | ROWS[j] << 10 | (0x4000 if hf else 0) | (0x8000 if vf else 0))
    pals = [list(p) + [0] * (15 - len(p)) for p in palettes]
    note = {'tiles': len(kept), 'tile_limit': len(FREE_TILES), 'merged': len(uniq) - len(kept), 'exact': exact,
            'colours': len({c for p in palettes for c in p}), 'changed_on_map': lost, 'animated': sum(1 for e in entries if e and e[0] == 'a')}
    return {'words': words, 'shared': bytes(shared), 'ctiles': bytes(ctiles), 'pals': pals}, note


_mem = {}


def wanted_tiles(rom, ch, words):
    """The tiles that matter for a chapter: on its map, or put there by the game during play."""
    return {w & 0x3FF for w in words} | reserved(rom, ch)


def converted(proj, ch, data, rom, words=None):
    """(set, note) for chapter ch's tile set picture (words: its map, for which tiles matter), cached
    in memory and in maps/tilesets/.cache."""
    wanted = wanted_tiles(rom, ch, words) if words is not None else None
    po = _fo(M.header(rom, ch)['pal'])
    key = (data + bytes([CONVERTER, ch]) + bytes(rom[M.SHARED_TILES + 0x1000:M.SHARED_TILES + 0x2000])
           + bytes(rom[po:po + 160]) + (b'w' + b''.join(k.to_bytes(2, 'little') for k in sorted(wanted)) if wanted else b''))
    h = hashlib.sha1(key).hexdigest()[:16]
    if h in _mem:
        return _mem[h]
    cp = None
    if proj:
        cdir = os.path.join(proj, *FOLDER.split('/'), '.cache')
        cp = os.path.join(cdir, f'{M.MAP_NAMES[ch]}-{h}.json')
        if os.path.exists(cp):
            try:
                d = json.load(open(cp))
                s = d['set']
                got = ({'words': s['words'], 'shared': bytes.fromhex(s['shared']), 'ctiles': bytes.fromhex(s['ctiles']),
                        'pals': s['pals']}, d['note'])
                _mem[h] = got
                return got
            except (ValueError, KeyError):
                pass
    got = convert(data, rom, ch, wanted)
    if cp:
        try:
            os.makedirs(os.path.dirname(cp), exist_ok=True)
            for f in os.listdir(os.path.dirname(cp)):
                if f.startswith(M.MAP_NAMES[ch] + '-'):
                    os.remove(os.path.join(os.path.dirname(cp), f))
            s = got[0]
            json.dump({'set': {'words': s['words'], 'shared': s['shared'].hex(), 'ctiles': s['ctiles'].hex(),
                               'pals': s['pals']}, 'note': got[1]}, open(cp, 'w'))
        except OSError:
            pass
    if len(_mem) > 16:
        _mem.clear()
    _mem[h] = got
    return got


def chapter_gfx(rom, ch, tset):
    """A fe4maptiles.ChapterGfx showing a converted set (for previews and for the build)."""
    import fe4maptiles as MT
    g = MT.ChapterGfx(rom, ch)
    g.words = list(tset['words'])
    g.shared = bytes(tset['shared'])
    g.ctiles = bytearray(tset['ctiles'])
    for j, row in enumerate(ROWS):
        for i, c in enumerate(tset['pals'][j]):
            g.pal[row * 16 + 1 + i] = ((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31)
    g.rows = list(ROWS)
    g.pool = []
    g.custom_set = tset
    return g


# ---------------------------------------------------------------- a whole map picture -> tile set + map
def import_map(rom, ch, data, g, words, terrain, terrain_from='place'):
    """A whole-map picture (16 pixels a cell) -> (tile set PNG, new map words, terrain per tile, note).

    g: the chapter's tiles now (ChapterGfx); words: its map now; terrain: its 1024 terrain types now.
    Tiles the game changes during play keep their pictures and numbers.  Each cell's terrain comes from
    the tile under it now (terrain_from='place') or from the game's tile that looks most alike ('look')."""
    try:
        w, h, px = G.read_png(data)
    except Exception as e:      # noqa: BLE001
        raise ValueError(f'not a PNG picture ({e})')
    width = M.WIDTH
    rows = len(words) // width
    if (w, h) != (width * 16, rows * 16):
        raise ValueError(f'this map is {width} x {rows} cells, so its picture is {width * 16} x {rows * 16} pixels; '
                         f'this one is {w} x {h}')
    keep = sorted(reserved(rom, ch))
    keep_set = set(keep)
    cells = [tuple(_snes_cells(px, w, (i % width) * 16, (i // width) * 16, 16)) for i in range(width * rows)]
    if terrain_from == 'look':
        on_map = sorted({x & 0x3FF for x in words})
        lib = [(_sig(gfx_cells(g, k), 16, 8), terrain[k]) for k in on_map]
        look = {}

        here = {}

        def terr_of(i):
            c = cells[i]
            k = words[i] & 0x3FF
            if k not in here:
                here[k] = tuple(gfx_cells(g, k))
            if here[k] == c:                 # unchanged cell: the terrain it has now
                return terrain[k]
            if c not in look:
                s = _sig(c, 16, 8)
                look[c] = min(lib, key=lambda e: sum((a - b) * (a - b) for a, b in zip(s, e[0])))[1]
            return look[c]
    else:
        def terr_of(i):
            return terrain[words[i] & 0x3FF]
    fixed = {}
    for k in keep:
        fixed.setdefault((tuple(gfx_cells(g, k)), terrain[k]), k)
    keys = [(cells[i], terr_of(i)) for i in range(len(cells))]
    uniq, index, uses = [], {}, []
    cell_u = []
    for key in keys:
        if key in fixed:
            cell_u.append(('k', fixed[key]))
            continue
        if key not in index:
            index[key] = len(uniq)
            uniq.append(key)
            uses.append(0)
        uses[index[key]] += 1
        cell_u.append(('u', index[key]))
    free = [k for k in range(1024) if k not in keep_set]
    merged = merge_alike([u[1] for u in uniq], [_sig(u[0], 16, 4) for u in uniq], list(uses), len(free))
    kept = sorted(set(merged), key=lambda t: t)
    number = {t: free[n] for n, t in enumerate(kept)}
    new_words = []
    for i, (kind, v) in enumerate(cell_u):
        k = v if kind == 'k' else number[merged[v]]
        new_words.append((words[i] & 0xFC00) | k)
    new_terrain = list(terrain)
    atlas = {}
    for k in keep:
        atlas[k] = gfx_cells(g, k)
    for t in kept:
        atlas[number[t]] = list(uniq[t][0])
        new_terrain[number[t]] = uniq[t][1]
    used = set(number.values())
    for k in free:
        if k not in used:
            new_terrain[k] = 3          # Plain, for unused tiles
    note = {'pictures': len(uniq), 'kept': len(kept), 'merged': len(uniq) - len(kept), 'limit': len(free),
            'reserved': len(keep)}
    return _rgba_png(ATLAS_W, ATLAS_W, atlas), new_words, new_terrain, note


def draw_tile(atlas_data, k, rgba16):
    """The tile set picture with tile k replaced by a 16x16 picture (rows of (r, g, b, a))."""
    w, h, px = G.read_png(atlas_data)
    cells = {}
    for n in range(1024):
        cells[n] = _snes_cells(px, w, (n % 32) * 16, (n // 32) * 16, 16)
    new = []
    for row in rgba16:
        for r, g, b, a in row:
            c = G.snes_color((r, g, b)) if a >= 128 else None
            new.append(None if c == 0 else c)
    cells[k] = new
    return _rgba_png(ATLAS_W, ATLAS_W, cells)


# ---------------------------------------------------------------- the build
def _code(org, table_entries):
    """The loader routine at org: two entries (from $88:80C9 and $88:8252), the chapter table, the
    game's own 32 bytes as the default, then the custom chapters' versions."""
    out = bytearray()
    entries = []
    table_at = org + 2 * 24            # after the two entries (24 bytes each)
    for back in BACK:
        entries.append(org + len(out))
        e = bytearray()
        e += bytes([0xAF]) + CHAPTER.to_bytes(3, 'little')          # LDA $000D6A
        e += bytes([0x29, 0xFF, 0x00])                               # AND #$00FF
        e += bytes([0xC9, M.MAP_COUNT, 0x00])                        # CMP #12
        e += bytes([0x90, 0x03])                                     # BCC +3
        e += bytes([0xA9, M.MAP_COUNT, 0x00])                        # LDA #12 (the game's own code)
        e += bytes([0x0A, 0xAA])                                     # ASL A, TAX
        e += bytes([0xFC]) + (table_at & 0xFFFF).to_bytes(2, 'little')   # JSR ($table,X)
        e += bytes([0x5C]) + back.to_bytes(3, 'little')              # JML back
        assert len(e) == 24
        out += e
    assert org + len(out) == table_at
    stubs_at = table_at + 2 * (M.MAP_COUNT + 1)
    stubs = bytearray(ORIGINAL + b'\x60')
    addr = {None: stubs_at}
    for ch, (tiles_a, meta_a) in sorted(table_entries.items()):
        addr[ch] = stubs_at + len(stubs)
        s = bytearray(ORIGINAL)
        s[5:8] = tiles_a.to_bytes(3, 'little')           # DMA source of tiles 0-639
        s[21:24] = meta_a.to_bytes(3, 'little')          # LDA $xxxxxx,X: metatiles 256-1023
        stubs += s + b'\x60'
    for ch in range(M.MAP_COUNT + 1):
        out += (addr.get(ch, addr[None]) & 0xFFFF).to_bytes(2, 'little')
    out += stubs
    return bytes(out), entries


def apply(rom, proj, far, space):
    """Palettes, the raw tile and metatile blocks and the loader hook for the project's tile sets.
    (The chapter's tiles 0-255, tiles 640-767 and terrain are written by fe4maptiles.apply.)"""
    sets = project_chapters(proj)
    if not sets:
        return 0
    if rom[SITES[0]:SITES[0] + 32] != ORIGINAL or rom[SITES[1]:SITES[1] + 32] != ORIGINAL:
        raise SystemExit('map tile sets: this ROM\'s map loading code ($88:80C9) is not the one the kit knows')
    clean = bytes(rom)
    table = {}
    n = 0
    for ch, data in sorted(sets.items()):
        try:
            tset, _ = converted(proj, ch, data, clean, project_words(proj, clean, ch))
        except ValueError as e:
            raise SystemExit(f'{atlas_file(ch)}: {e}')
        blob = tset['shared'] + b''.join(bytes([v & 0xFF, v >> 8]) for v in tset['words'][1024:])
        a = far.alloc(len(blob))
        rom[_fo(a):_fo(a) + len(blob)] = blob
        table[ch] = (a, a + 0x5000)                 # LDA src,X with X = $0000-$17FE: metatiles 256-1023
        hd = M.header(clean, ch)
        po = _fo(hd['pal'])
        pal = bytearray(clean[po:po + 224])
        for j in range(len(ROWS)):
            for i, c in enumerate(tset['pals'][j]):
                o = (ROWS[j] - 1) * 32 + 2 + 2 * i
                pal[o], pal[o + 1] = c & 0xFF, c >> 8
        pa = far.alloc(len(pal))
        rom[_fo(pa):_fo(pa) + len(pal)] = pal
        rom[hd['file'] + 9:hd['file'] + 12] = pa.to_bytes(3, 'little')
        n += 1
    # the routine runs with the data bank set to its own bank ($80:A4BD reads the DMA settings after the
    # JSL with DB = the caller's bank and writes the queue at $0346 through DB): it must be in a bank
    # $80-$BF, where $0000-$1FFF is RAM
    size = len(_code(0x808000, {ch: (0, 0) for ch in table})[0])
    org = None
    for b in CODE_BANKS:
        try:
            fo, a = space.alloc(b << 16, size)
        except SystemExit:
            continue
        if a & 0xFFFF >= 0x8000:
            org = a
            break
    if org is None:
        raise SystemExit('map tile sets: no room for the loader in banks ' + ', '.join('$%02X' % b for b in CODE_BANKS))
    code, entries = _code(org, table)
    rom[_fo(org):_fo(org) + len(code)] = code
    for site, e in zip(SITES, entries):
        rom[site:site + 4] = bytes([0x5C]) + e.to_bytes(3, 'little')
    return n
