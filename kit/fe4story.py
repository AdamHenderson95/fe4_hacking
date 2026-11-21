"""The opening's story pictures: its background layers, replaceable (editor 1.8: the four paintings; 1.9: the
layers around them).

Found by tracing the opening from power-on (lsrun: decompression calls, DMA to VRAM, writes to the palette
buffer at $0100, VRAM and CGRAM dumps compared with every decompressed stream).  Each layer is a background:
tiles and a map (both compressed, $80:AA02 format) and the colours of its palette rows.

  layer          BG   bpp  size     tiles (compressed)          map (compressed)            tiles  colours
  fire           1    4    512x256  $F3:426A  code $9B:E1E3     $F4:0F1E  code $9B:E20C     768    row 3       $E0:2299 ($9B:E286)
  fire_clouds    2    4    256x256  $F4:68D3  code $9B:E235     $F4:7CBD  code $9B:E25E     256    row 2       $E0:23B1 ($9B:E28D)
  tower          1    4    512x256  $F6:4799  record $97:F1F4   $F5:222D  record $97:F1FF   512    rows 3-4    $E0:23ED ($95:EADD)
  tower_cliff    2    4    512x256  $F6:76FE  record $97:F1B2   $F5:24B7  record $97:F1BD   512    rows 6-7    $E0:242B ($95:EAE4)
  tower_clouds   3    2    512x256  $F4:7E55  record $97:F20A   $F5:27E5  record $97:F215   256    BG3 4-7     $E0:23CF ($95:EB0C)
  dragon         1    4    512x256  $F4:1F38  record $97:F2C5   $F4:3803  record $97:F2D0   448    rows 3-5    $E0:2315 ($95:EC93)
  light          1    4    512x256  $F3:0E6F  record $97:F307   $F3:39EB  record $97:F312   512    rows 3-4    $E0:221D ($95:ED11)
  seal           1    8    256x256  $F5:2B03  record $97:F38B   $F5:580C  record $97:F396   128    194         $E0:24E3 ($9B:F405..)
  sky            2    4    256x256  $94:E9EE  record $97:F35F   $F5:597A  record $97:F36A   256    row 7       $E0:2667 ($95:ED9D)
                                    and code $95:EE93           and code $95:EECB                              and $95:F0A4

The records are the opening's graphics script ($97:F1xx: [source 24][destination 24][VRAM][size][flag]); some
streams are loaded by code instead (LDX #source, LDA #bank).  A palette load copies colours from $E0:xxxx into
the palette buffer ($0100 + 2 x colour) in a loop; the editor writes a new block of the same length and points
the load at it.  The seal (mode 3, 256 colours) fades in from a table of 194 colours: entry i is colour 16 + i
for i < 97, else colour 31 + i (colours 113-127 are the sky's row 7, 225-255 the weapons' sprites).  Row 0
(black and greys) is shared with the captions and stays as it is.

The seal's 128 tiles cannot grow: VRAM after them ($4000) is filled by something else during that scene
(tried: a 256-tile seal showed garbage in its lower half).

Left as the game's (their colours are made by code each frame, or they are sprites): the burst scene's sun
ring, its rays and streaks, the devil's rays, the holy dragon's golden burst, the twelve gods' flames, the
weapons and sparks.

A new picture (transparent where the layers behind should show) is reduced to the layer's colours and tile
room, compressed into free space, and the layer's references are pointed at it.

Project files: story/<layer>.png.
"""
import hashlib
import json
import os

import fe4gfx as G
import fe4lz
import fe4title as T
from dis65816 import snes_to_file as _fo

FOLDER = 'story'
W, H = 512, 256                 # the paintings' size (each layer has its own 'w', 'h')
CONVERTER = 4


def _rows4(*rows):
    """4bpp palette rows: (palette number, pixel values, colour numbers)."""
    return [(r, list(range(1, 16)), [16 * r + c for c in range(1, 16)]) for r in rows]


def _rows2(*pals):
    """2bpp palettes (BG3 in mode 1: colours 4p .. 4p+3)."""
    return [(p, [1, 2, 3], [4 * p + c for c in (1, 2, 3)]) for p in pals]


_SEAL = [16 + i if i < 97 else 31 + i for i in range(194)]

SCENES = [
    {'key': 'fire', 'scene': 'The devil\'s fire', 'title': 'The painting', 'w': 512, 'h': 256, 'bpp': 4,
     'when': 'The first scene: "In an age beyond living memory…" to "Plunging it into the deepest darkness"',
     'tiles': (0xF3426A, [('imm', 0x9BE1E4, 0x9BE1E9)]), 'map': (0xF40F1E, [('imm', 0x9BE20D, 0x9BE212)]),
     'limit': 768, 'groups': _rows4(3), 'block': ([0x9BE287], list(range(49, 64)))},
    {'key': 'fire_clouds', 'scene': 'The devil\'s fire', 'title': 'The red clouds', 'w': 256, 'h': 256, 'bpp': 4,
     'when': 'Drifts over the painting, its colours added to it (black adds nothing). It scrolls and repeats '
             'on all sides: make the edges meet.',
     'tiles': (0xF468D3, [('imm', 0x9BE236, 0x9BE23B)]), 'map': (0xF47CBD, [('imm', 0x9BE25F, 0x9BE264)]),
     'limit': 256, 'groups': _rows4(2), 'block': ([0x9BE28E], list(range(33, 48)))},
    {'key': 'tower', 'scene': 'The tower', 'title': 'The painting', 'w': 512, 'h': 256, 'bpp': 4,
     'when': '"And condemning us to grief without end." to "The twelve gods descended from above"',
     'tiles': (0xF64799, [('ptr', 0x97F1F4)]), 'map': (0xF5222D, [('ptr', 0x97F1FF)]),
     'limit': 512, 'groups': _rows4(3, 4), 'block': ([0x95EADE], list(range(49, 80)))},
    {'key': 'tower_cliff', 'scene': 'The tower', 'title': 'The cliff', 'w': 512, 'h': 256, 'bpp': 4,
     'when': 'Behind the painting; the camera pans across both together.',
     'tiles': (0xF676FE, [('ptr', 0x97F1B2)]), 'map': (0xF524B7, [('ptr', 0x97F1BD)]),
     'limit': 512, 'groups': _rows4(6, 7), 'block': ([0x95EAE5], list(range(97, 128)))},
    {'key': 'tower_clouds', 'scene': 'The tower', 'title': 'The dark clouds', 'w': 512, 'h': 256, 'bpp': 2,
     'when': 'The back layer, drifting on its own: a simple layer of 12 colours (four sets of three).',
     'tiles': (0xF47E55, [('ptr', 0x97F20A)]), 'map': (0xF527E5, [('ptr', 0x97F215)]),
     'limit': 256, 'groups': _rows2(4, 5, 6, 7), 'block': ([0x95EB0D], list(range(17, 32)))},
    {'key': 'dragon', 'scene': 'The devil', 'title': 'The painting', 'w': 512, 'h': 256, 'bpp': 4,
     'when': '"Invoking holy light, the gods smote the devil"',
     'tiles': (0xF41F38, [('ptr', 0x97F2C5)]), 'map': (0xF43803, [('ptr', 0x97F2D0)]),
     'limit': 448, 'groups': _rows4(3, 4, 5), 'block': ([0x95EC94], list(range(49, 96)))},
    {'key': 'light', 'scene': 'The holy dragon', 'title': 'The painting', 'w': 512, 'h': 256, 'bpp': 4,
     'when': '"And granted us our lost hope once more."',
     'tiles': (0xF30E6F, [('ptr', 0x97F307)]), 'map': (0xF339EB, [('ptr', 0x97F312)]),
     'limit': 512, 'groups': _rows4(3, 4), 'block': ([0x95ED12], list(range(49, 80)))},
    {'key': 'seal', 'scene': 'Time flows on', 'title': 'The seal', 'w': 256, 'h': 256, 'bpp': 8,
     'when': '"As time flows endlessly on…": fades in over the sky, ringed by the weapons, and ripples. '
             'Up to 194 colours, but only 128 different tiles: keep it about the size of the game\'s seal.',
     'tiles': (0xF52B03, [('ptr', 0x97F38B)]), 'map': (0xF5580C, [('ptr', 0x97F396)]),
     'limit': 128, 'groups': [(0, _SEAL, _SEAL)], 'block': ([0x9BF406, 0x9BF411, 0x9BF41C], _SEAL)},
    {'key': 'sky', 'scene': 'Time flows on', 'title': 'The sky', 'w': 256, 'h': 256, 'bpp': 4,
     'when': 'From "And so…" on, behind the weapons and the seal. It scrolls and repeats on all sides (make the '
             'edges meet). A later scene shows it again, darker.',
     'tiles': (0x94E9EE, [('ptr', 0x97F35F), ('imm', 0x95EE94, 0x95EE99)]),
     'map': (0xF5597A, [('ptr', 0x97F36A), ('imm', 0x95EECC, 0x95EED1)]),
     'limit': 256, 'groups': _rows4(7), 'block': ([0x95ED9E, 0x95F0A5], list(range(113, 128)))},
]
BY_KEY = {s['key']: s for s in SCENES}
SHARED_ROW0 = 0xE02787          # row 0 of every scene (colours 1-15): black and greys, shown in previews


def colour_limit(s):
    return sum(len(g[1]) for g in s['groups'])


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
                    if ref[0] == 'imm' and (rom[_fo(ref[1]) - 1] != 0xA2 or rom[_fo(ref[2]) - 1] != 0xA9):
                        return False
            for a in s['block'][0]:
                if rom[_fo(a) - 1] != 0xBF:
                    return False
        return True
    except (IndexError, TypeError):
        return False


def palette_src(rom, s):
    o = _fo(s['block'][0][0])
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def _block(rom, s):
    """{colour number: SNES colour} of the layer's palette block as the ROM has it."""
    o = _fo(palette_src(rom, s))
    return {n: rom[o + 2 * i] | rom[o + 2 * i + 1] << 8 for i, n in enumerate(s['block'][1])}


def read_scene(rom, s):
    """The game's layer (as the ROM has it now): {'tiles', 'map', 'pals' {colour number: SNES colour}}."""
    tiles = fe4lz.decompress(rom, _ptr(rom, s['tiles'][1][0]))
    n = s['w'] // 8 * s['h'] // 8
    mb = fe4lz.decompress(rom, _ptr(rom, s['map'][1][0]))[:2 * n]
    m = [mb[2 * i] | mb[2 * i + 1] << 8 for i in range(len(mb) // 2)]
    z = _fo(SHARED_ROW0)
    pals = {c: rom[z + 2 * (c - 1)] | rom[z + 2 * (c - 1) + 1] << 8 for c in range(1, 16)}
    pals.update(_block(rom, s))
    return {'tiles': tiles, 'map': m, 'pals': pals}


def _index(tx, ty):
    """Map entry number of tile column tx, row ty (64-wide maps are two 32 x 32 screens side by side)."""
    return (tx >> 5) * 1024 + ty * 32 + (tx & 31)


def tile_px(data, t, bpp):
    """8 rows of 8 pixel values of tile t."""
    tb = 8 * bpp
    d = data[t * tb:t * tb + tb]
    if len(d) < tb:
        d = bytes(d) + bytes(tb - len(d))
    out = []
    for y in range(8):
        planes = [d[(p >> 1) * 16 + 2 * y + (p & 1)] for p in range(bpp)]
        out.append([sum((planes[p] >> (7 - x) & 1) << p for p in range(bpp)) for x in range(8)])
    return out


def tile_bytes(rows, bpp):
    out = bytearray(8 * bpp)
    for y in range(8):
        for x in range(8):
            v = rows[y][x]
            for p in range(bpp):
                if v >> p & 1:
                    out[(p >> 1) * 16 + 2 * y + (p & 1)] |= 0x80 >> x
    return bytes(out)


def _colour_number(s, pal, v):
    return v if s['bpp'] == 8 else (4 * pal + v if s['bpp'] == 2 else 16 * pal + v)


def render(layer, s=None):
    """[w*h] SNES colours or None (transparent)."""
    s = s or SCENES[0]
    w, h, bpp = s['w'], s['h'], s['bpp']
    out = [None] * (w * h)
    cache = {}
    tiles, m, pals = layer['tiles'], layer['map'], layer['pals']
    for ty in range(h // 8):
        for tx in range(w // 8):
            i = _index(tx, ty)
            if i >= len(m):
                continue
            e = m[i]
            t, p = e & 0x3FF, e >> 10 & 7
            if t not in cache:
                cache[t] = tile_px(tiles, t, bpp)
            for y in range(8):
                row = cache[t][7 - y if e & 0x8000 else y]
                for x in range(8):
                    v = row[7 - x if e & 0x4000 else x]
                    if v:
                        c = pals.get(_colour_number(s, p, v))
                        if c is not None:
                            out[(ty * 8 + y) * w + tx * 8 + x] = c
    return out


def png(layer, scale=1, s=None):
    s = s or SCENES[0]
    w, h = s['w'], s['h']
    px = render(layer, s)
    rgba = [(0, 0, 0, 0) if c is None else T._rgb(c) + (255,) for c in px]
    if scale > 1:
        rgba = [rgba[(y // scale) * w + x // scale] for y in range(h * scale) for x in range(w * scale)]
    rows = [bytes(b for p in rgba[y * w * scale:(y + 1) * w * scale] for b in p) for y in range(h * scale)]
    return G.png(w * scale, h * scale, rows)


# ---------------------------------------------------------------- conversion
def convert(s, data):
    """A PNG of the layer's size -> ({'tiles', 'map', 'pals'}, note)."""
    w, h, bpp = s['w'], s['h'], s['bpp']
    try:
        pw, ph, px = G.read_png(data)
    except Exception as e:      # noqa: BLE001
        raise ValueError(f'not a PNG picture ({e})')
    if (pw, ph) != (w, h):
        raise ValueError(f'the picture is {w} x {h}; this one is {pw} x {ph}')
    canvas = [None if a < 128 else G.snes_color((r, g, b)) for r, g, b, a in px]
    cells, order = [], []
    for ty in range(h // 8):
        for tx in range(w // 8):
            cells.append([canvas[(ty * 8 + y) * w + tx * 8 + x] for y in range(8) for x in range(8)])
            order.append((tx, ty))
    groups = s['groups']
    sizes = tuple(len(g[1]) for g in groups)
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
    tb = 8 * bpp
    tiles = bytearray(tb * (len(kept) + 1))
    for t in kept:
        g, key = uniq[t]
        vals = groups[g][1]
        n = number[t]
        tiles[n * tb:n * tb + tb] = tile_bytes([[vals[v - 1] if v else 0 for v in key[y * 8:(y + 1) * 8]]
                                                for y in range(8)], bpp)
    m = [0] * (w // 8 * h // 8)
    for (tx, ty), e in zip(order, entries):
        if e is None:
            continue
        t, hf, vf = e
        if merged[t] != t:
            t, hf, vf = merged[t], 0, 0
        p = groups[uniq[t][0]][0]
        m[_index(tx, ty)] = number[t] | p << 10 | (0x4000 if hf else 0) | (0x8000 if vf else 0)
    pals = {}
    for j, g in enumerate(groups):
        for k, c in enumerate(palettes[j]):
            pals[g[2][k]] = c
    note = {'tiles': len(kept) + 1, 'tile_limit': s['limit'], 'merged': len(uniq) - len(kept), 'exact': exact,
            'colours': sum(len(p) for p in palettes), 'colour_limit': colour_limit(s)}
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
    """The layer as the project will build it: (layer, custom, note)."""
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
        # the tiles fill the room the game's own took (the load copies that much to VRAM)
        room = len(fe4lz.decompress(rom, _ptr(rom, s['tiles'][1][0])))
        tiles = layer['tiles'][:room] + bytes(max(0, room - len(layer['tiles'])))
        mb = bytearray()
        for e in layer['map']:
            mb += bytes([e & 0xFF, e >> 8])
        ta = _put(rom, far, fe4lz.compress(tiles))
        ma = _put(rom, far, fe4lz.compress(bytes(mb)))
        for ref in s['tiles'][1]:
            _set_ptr(rom, ref, ta)
        for ref in s['map'][1]:
            _set_ptr(rom, ref, ma)
        # the palette block the layer loads, the same length, new colours where the picture has them
        old = _block(rom, s)
        blob = b''.join(bytes([c & 0xFF, c >> 8]) for c in (layer['pals'].get(k, old[k]) for k in s['block'][1]))
        pa = _put(rom, far, blob)
        for a in s['block'][0]:
            o = _fo(a)
            rom[o:o + 3] = bytes([pa & 0xFF, pa >> 8 & 0xFF, pa >> 16])
        n += 1
    return n
