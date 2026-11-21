"""The opening's story pictures: the main painting of four of its scenes, replaceable (editor 1.8).

Found by tracing the opening from power-on (lsrun: decompression calls, DMA to VRAM, writes to the palette
buffer at $0100).  Each scene's painting is BG1, a 64 x 32 map (a 512 x 256 picture the camera pans across),
4bpp tiles, and its own palette rows; the other layers (fire, clouds, light, the flames and sparks as sprites)
stay the game's.

  scene      tiles (compressed)           map (compressed)            limit  palette rows   palette load
  fire       $F3:426A  LDX/LDA $9B:E1E3   $F4:0F1E  LDX/LDA $9B:E20C  768    3              $9B:E286 $E0:2299
  tower      $F6:4799  record $97:F1F4    $F5:222D  record $97:F1FF   512    3-4            $95:EADD $E0:23ED
  dragon     $F4:1F38  record $97:F2C5    $F4:3803  record $97:F2D0   448    3-5            $95:EC93 $E0:2315
  light      $F3:0E6F  record $97:F307    $F3:39EB  record $97:F312   512    3-4            $95:ED11 $E0:221D

The records are the opening's graphics script ($97:F1xx: [source 24][destination 24][VRAM][size][flag]); the
fire scene is loaded by code (LDX #source, LDA #bank).  A palette load copies colours 1-15 of its first row and
on through the rows after it (`LDA $E0xxxx,X : STA $0162,X`, row 3 = $0162).  Row 0 (black and greys) is
shared with the other layers and stays as it is.

A new picture (512 x 256, transparent where the layers behind should show) is reduced to the scene's rows and
tile room, compressed into free space, and the scene's references are pointed at it.  Other places that load
the same pictures (other graphics scripts) keep the game's.

Project files: story/<scene>.png (512 x 256).
"""
import hashlib
import json
import os

import fe4gfx as G
import fe4lz
import fe4title as T
from dis65816 import snes_to_file as _fo

FOLDER = 'story'
W, H = 512, 256
CONVERTER = 1

SCENES = [
    {'key': 'fire', 'title': 'The devil\'s fire',
     'when': 'The first scene: "In an age beyond living memory…" to "Plunging it into the deepest darkness"',
     'tiles': (0xF3426A, [('imm', 0x9BE1E4, 0x9BE1E9)]), 'map': (0xF40F1E, [('imm', 0x9BE20D, 0x9BE212)]),
     'limit': 768, 'rows': (3,), 'pal': (0x9BE287, 3, 1)},
    {'key': 'tower', 'title': 'The tower',
     'when': '"And condemning us to grief without end." to "The twelve gods descended from above"',
     'tiles': (0xF64799, [('ptr', 0x97F1F4)]), 'map': (0xF5222D, [('ptr', 0x97F1FF)]),
     'limit': 512, 'rows': (3, 4), 'pal': (0x95EADE, 3, 2)},
    {'key': 'dragon', 'title': 'The devil',
     'when': '"Invoking holy light, the gods smote the devil"',
     'tiles': (0xF41F38, [('ptr', 0x97F2C5)]), 'map': (0xF43803, [('ptr', 0x97F2D0)]),
     'limit': 448, 'rows': (3, 4, 5), 'pal': (0x95EC94, 3, 3)},
    {'key': 'light', 'title': 'The holy dragon',
     'when': '"And granted us our lost hope once more."',
     'tiles': (0xF30E6F, [('ptr', 0x97F307)]), 'map': (0xF339EB, [('ptr', 0x97F312)]),
     'limit': 512, 'rows': (3, 4), 'pal': (0x95ED12, 3, 2)},
]
BY_KEY = {s['key']: s for s in SCENES}
SHARED_ROW0 = 0xE02787          # row 0 of every scene (colours 1-15): black and greys, shown in previews


def _w(rom, a):
    o = _fo(a)
    return rom[o] | rom[o + 1] << 8


def _ptr(rom, ref):
    kind, a, *b = ref
    if kind == 'imm':
        return rom[_fo(b[0])] << 16 | _w(rom, a)
    o = _fo(a)
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def _set_ptr(rom, ref, v):
    kind, a, *b = ref
    if kind == 'imm':
        o = _fo(a)
        rom[o], rom[o + 1] = v & 0xFF, v >> 8 & 0xFF
        rom[_fo(b[0])] = v >> 16
    else:
        o = _fo(a)
        rom[o:o + 3] = bytes([v & 0xFF, v >> 8 & 0xFF, v >> 16])


def known(rom):
    """The ROM's opening is the one this module knows (the references point where the game has them, or a
    build of the editor moved them)."""
    try:
        for s in SCENES:
            for part in ('tiles', 'map'):
                for ref in s[part][1]:
                    if _ptr(rom, ref) >> 16 not in range(0x40, 0x100):
                        return False
            if rom[_fo(s['pal'][0]) - 1] != 0xBF:
                return False
        return True
    except (IndexError, TypeError):
        return False


def palette_src(rom, s):
    o = _fo(s['pal'][0])
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def read_scene(rom, s):
    """The game's painting (as the ROM has it now): {'tiles', 'map' (2,048 entries), 'pals'}."""
    tiles = fe4lz.decompress(rom, _ptr(rom, s['tiles'][1][0]))
    mb = fe4lz.decompress(rom, _ptr(rom, s['map'][1][0]))[:0x1000]
    m = [mb[2 * i] | mb[2 * i + 1] << 8 for i in range(len(mb) // 2)]
    src, first, n = palette_src(rom, s), s['pal'][1], s['pal'][2]
    o = _fo(src)
    flat = [0] + [rom[o + 2 * i] | rom[o + 2 * i + 1] << 8 for i in range(16 * n - 1)]
    pals = {first + r: flat[16 * r:16 * r + 16] for r in range(n)}
    z = _fo(SHARED_ROW0)
    pals[0] = [0] + [rom[z + 2 * i] | rom[z + 2 * i + 1] << 8 for i in range(15)]
    return {'tiles': tiles, 'map': m, 'pals': pals}


def _entry(m, x, y):
    """Map entry for tile column x (0-63), row y (0-31) of a 64 x 32 map (two 32 x 32 screens)."""
    return m[(x >> 5) * 1024 + y * 32 + (x & 31)]


def render(layer):
    """[W*H] SNES colours or None (transparent)."""
    out = [None] * (W * H)
    cache = {}
    tiles, m, pals = layer['tiles'], layer['map'], layer['pals']
    for ty in range(32):
        for tx in range(64):
            e = _entry(m, tx, ty)
            t, p = e & 0x3FF, e >> 10 & 7
            if t not in cache:
                cache[t] = T._tile_px(tiles, t)
            pal = pals.get(p)
            for y in range(8):
                row = cache[t][7 - y if e & 0x8000 else y]
                for x in range(8):
                    c = row[7 - x if e & 0x4000 else x]
                    if c and pal and c < len(pal):
                        out[(ty * 8 + y) * W + tx * 8 + x] = pal[c]
    return out


def png(layer, scale=1):
    px = render(layer)
    rgba = [(0, 0, 0, 0) if c is None else T._rgb(c) + (255,) for c in px]
    if scale > 1:
        rgba = [rgba[(y // scale) * W + x // scale] for y in range(H * scale) for x in range(W * scale)]
    rows = [bytes(b for p in rgba[y * W * scale:(y + 1) * W * scale] for b in p) for y in range(H * scale)]
    return G.png(W * scale, H * scale, rows)


# ---------------------------------------------------------------- conversion
def convert(s, data):
    """A 512 x 256 PNG -> ({'tiles', 'map', 'pals'}, note)."""
    try:
        w, h, px = G.read_png(data)
    except Exception as e:      # noqa: BLE001
        raise ValueError(f'not a PNG picture ({e})')
    if (w, h) != (W, H):
        raise ValueError(f'the picture is {W} x {H}; this one is {w} x {h}')
    canvas = [None if a < 128 else G.snes_color((r, g, b)) for r, g, b, a in px]
    cells = []
    order = []                                   # (tx, ty) of each cell
    for ty in range(32):
        for tx in range(64):
            cells.append([canvas[(ty * 8 + y) * W + tx * 8 + x] for y in range(8) for x in range(8)])
            order.append((tx, ty))
    sizes = tuple(15 for _ in s['rows'])
    palettes, assign, exact = T.reduce_cells(cells, sizes)
    memo = {}
    uniq, where, uses, entries = [], {}, [], []
    for i, cell in enumerate(cells):
        if all(c is None for c in cell):
            entries.append(None)
            continue
        idx = T._index_cell(cell, palettes[assign[i]], memo)
        if not any(idx):
            entries.append(None)
            continue
        hit = None
        for key, hf, vf in T._flips(idx, 8):
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
    merged = T._merge_tiles(uniq, list(uses), s['limit'] - 1, palettes, 8)      # tile 0 stays empty
    kept = sorted(set(merged))
    number = {t: k + 1 for k, t in enumerate(kept)}
    tiles = bytearray(32 * (len(kept) + 1))
    for t in kept:
        key = uniq[t][1]
        n = number[t]
        tiles[n * 32:n * 32 + 32] = T._tile_bytes([key[y * 8:(y + 1) * 8] for y in range(8)])
    m = [0] * 2048
    for (tx, ty), e in zip(order, entries):
        if e is None:
            continue
        t, hf, vf = e
        if merged[t] != t:
            t, hf, vf = merged[t], 0, 0
        p = s['rows'][uniq[t][0]]
        m[(tx >> 5) * 1024 + ty * 32 + (tx & 31)] = number[t] | p << 10 | (0x4000 if hf else 0) | (0x8000 if vf else 0)
    pals = {s['rows'][j]: [0] + palettes[j] + [0] * (15 - len(palettes[j])) for j in range(len(sizes))}
    note = {'tiles': len(kept) + 1, 'tile_limit': s['limit'], 'merged': len(uniq) - len(kept), 'exact': exact,
            'colours': sum(len(p) for p in palettes), 'colour_limit': 15 * len(s['rows'])}
    return {'tiles': bytes(tiles), 'map': m, 'pals': pals}, note


def converted(proj, key, data=None):
    """(layer, note) for story/<key>.png (or the given PNG bytes), cached in story/.cache."""
    s = BY_KEY[key]
    if data is None:
        p = os.path.join(proj, FOLDER, key + '.png')
        if not os.path.exists(p):
            return None
        data = open(p, 'rb').read()
    h = hashlib.sha1(data + bytes([CONVERTER])).hexdigest()[:16]
    cdir = os.path.join(proj, FOLDER, '.cache')
    cp = os.path.join(cdir, f'{key}-{h}.json')
    if os.path.exists(cp):
        try:
            d = json.load(open(cp))
            return T._unpack(d['layer']), d['note']
        except (ValueError, KeyError):
            pass
    layer, note = convert(s, data)
    os.makedirs(cdir, exist_ok=True)
    for f in os.listdir(cdir):
        if f.startswith(key + '-'):
            os.remove(os.path.join(cdir, f))
    json.dump({'layer': T._pack(layer), 'note': note}, open(cp, 'w'))
    return layer, note


def project_scene(rom, proj, s):
    """The scene's painting as the project will build it: (layer, custom, note)."""
    got = converted(proj, s['key']) if proj else None
    if got:
        layer, note = got
        base = read_scene(rom, s)
        pals = dict(base['pals'])
        pals.update(layer['pals'])
        return {'tiles': layer['tiles'], 'map': layer['map'], 'pals': pals}, True, note
    return read_scene(rom, s), False, None


def _put(rom, far, blob):
    a = far.alloc(len(blob) + 1, upper_half=True)
    rom[_fo(a):_fo(a) + len(blob)] = blob
    return a


def apply(rom, proj, far):
    n = 0
    for s in SCENES:
        got = converted(proj, s['key'])
        if not got:
            continue
        if not known(rom):
            raise SystemExit('story pictures: the opening is not the one the editor knows; pictures left as they are')
        layer, _note = got
        mb = bytearray()
        for e in layer['map']:
            mb += bytes([e & 0xFF, e >> 8])
        ta = _put(rom, far, fe4lz.compress(layer['tiles']))
        ma = _put(rom, far, fe4lz.compress(bytes(mb)))
        for ref in s['tiles'][1]:
            _set_ptr(rom, ref, ta)
        for ref in s['map'][1]:
            _set_ptr(rom, ref, ma)
        # the palette block the scene loads: colours 1-15 of its first row and on through the next rows
        old = read_scene(rom, s)['pals']
        first, rows = s['pal'][1], s['pal'][2]
        flat = []
        for r in range(first, first + rows):
            flat += (layer['pals'].get(r) or old[r])
        blob = b''.join(bytes([c & 0xFF, c >> 8]) for c in flat[1:])
        pa = _put(rom, far, blob)
        o = _fo(s['pal'][0])
        rom[o:o + 3] = bytes([pa & 0xFF, pa >> 8 & 0xFF, pa >> 16])
        n += 1
    return n
