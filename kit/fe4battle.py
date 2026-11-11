"""FE4 battle animations: tables, sheets, palettes, scripts and frame layouts (read-only for now).

Lookup ($95:A2C8): each combatant's (class, weapon kind, character, gender) is matched against
ASSIGN, 8-byte rows; the last four bytes give (animation, graphics, palette, extra).
  animation -> ANIM_IDX byte -> ANIM_REC (script ptr24, tile-page table ptr24)
  graphics  -> GFX_IDX byte  -> GFX_REC  (compressed sheet ptr24, overlay word)
  palette   -> PAL_IDX byte  -> PAL_REC  (ptr24 to 15 colours, byte count); characters can
               override it through PAL_CHAR (char word, class byte, palette byte).
"""
import fe4gfx as G
from dis65816 import snes_to_file

ASSIGN, ASSIGN_N = 0x9788C9, 0x670 // 8
ANIM_IDX, ANIM_REC = 0x97874F, 0x97874F + 0x60
GFX_IDX, GFX_REC = 0x978039, 0x978039 + 0x68
PAL_IDX, PAL_REC = 0x9784B6, 0x9784B6 + 0x6B
EXTRA_IDX, EXTRA_REC = 0x97828B, 0x97828B + 0x48
WEAPON_IDX, WEAPON_SRC, WEAPON_PAL = 0x998725, 0x99881F, 0xE00F30
OVL = 0x9784B6           # ptr24 per overlay index (3 bytes each)
PAL_CHAR = 0x9786AD
WEAPON_KINDS = {0: 'sword', 1: 'lance', 2: 'axe', 3: 'bow', 4: '4?', 5: 'thrown lance', 6: 'thrown axe',
                7: 'magic', 8: 'staff', 9: 'any'}


def _p24(rom, a):
    f = snes_to_file(a)
    return rom[f] | rom[f + 1] << 8 | rom[f + 2] << 16


def _b(rom, a):
    return rom[snes_to_file(a)]


def _w(rom, a):
    f = snes_to_file(a)
    return rom[f] | rom[f + 1] << 8


def assignments(rom):
    out = []
    for i in range(ASSIGN_N):
        f = snes_to_file(ASSIGN + 8 * i)
        e = rom[f:f + 8]
        out.append({'row': i, 'class': e[0], 'weapon': e[1], 'character': e[2], 'gender': e[3],
                    'anim': e[4], 'gfx': e[5], 'palette': e[6], 'extra': e[7]})
    return out


def anim_rec(rom, aid):
    k = _b(rom, ANIM_IDX + 1 + aid)
    return {'rec': k, 'script': _p24(rom, ANIM_REC + 6 * k), 'pages': _p24(rom, ANIM_REC + 6 * k + 3)}


def gfx_rec(rom, gid):
    k = _b(rom, GFX_IDX + 1 + gid)
    a = GFX_REC + 5 * k
    return {'rec': k, 'sheet': _p24(rom, a), 'overlay': _w(rom, a + 3)}


def palette(rom, pid):
    k = _b(rom, PAL_IDX + 1 + pid)
    a = PAL_REC + 4 * k
    src, n = _p24(rom, a), _b(rom, a + 3)
    f = snes_to_file(src)
    cols = [rom[f + 2 * i] | rom[f + 2 * i + 1] << 8 for i in range(n // 2)]
    return {'rec': k, 'src': src, 'colors': cols}


def extra_rec(rom, eid):
    k = _b(rom, EXTRA_IDX + 1 + eid)
    a = EXTRA_REC + 7 * k
    return {'rec': k, 'tile': _b(rom, a), 'count': _b(rom, a + 1), 'src': _p24(rom, a + 2), 'overlay': _w(rom, a + 5)}


def _with_overlay(rom, d, ov):
    d = bytearray(d)
    if ov != 0xFFFF and ov & 0xF800 != 0xF800:
        p = G.decompress(rom, _p24(rom, OVL + 3 * (ov & 0x7FF)))
        n, i = p[0] | p[1] << 8, 2
        for _ in range(n):
            off = p[i] | p[i + 1] << 8
            i += 2
            if off + 32 > len(d):
                d.extend(bytes(off + 32 - len(d)))
            d[off:off + 32] = p[i:i + 32]
            i += 32
    return bytes(d)


def extra_tiles(rom, eid):
    """{VRAM tile: 32 bytes} for the look's upper-body / weapon tiles (loaded once per battle)."""
    e = extra_rec(rom, eid)
    if e['rec'] == 0:
        return {}
    d = _with_overlay(rom, G.decompress(rom, e['src']), e['overlay'])
    return {e['tile'] + i: d[32 * i:32 * i + 32] for i in range(min(e['count'], len(d) // 32))}


def weapon(rom, item):
    """Battle weapon graphics for an item: tiles $40-$5F and OBJ palette 2."""
    w = _w(rom, WEAPON_IDX + 2 * item)
    k, p = w & 0xFF, w >> 8
    d = G.decompress(rom, _p24(rom, WEAPON_SRC + 3 * k))
    f = snes_to_file(WEAPON_PAL + 30 * p)
    cols = [rom[f + 2 * i] | rom[f + 2 * i + 1] << 8 for i in range(15)]
    return {'sheet': k, 'palette': p, 'tiles': {0x40 + i: d[32 * i:32 * i + 32] for i in range(min(32, len(d) // 32))},
            'colors': cols}


def sheet(rom, gid):
    g = gfx_rec(rom, gid)
    d = bytearray(G.decompress(rom, g['sheet']))
    ov = g['overlay']
    if ov != 0xFFFF and ov & 0xF800 != 0xF800:
        p = G.decompress(rom, _p24(rom, OVL + 3 * (ov & 0x7FF)))
        n, i = p[0] | p[1] << 8, 2
        for _ in range(n):
            off = p[i] | p[i + 1] << 8
            i += 2
            if off + 32 > len(d):
                d.extend(bytes(off + 32 - len(d)))
            d[off:off + 32] = p[i:i + 32]
            i += 32
    return bytes(d)


def pages(rom, aid):
    """Tile pages: page -> [(sheet offset, bytes)], row k of a page goes to VRAM tile 16*k."""
    base = anim_rec(rom, aid)['pages']
    out, k = [], 0
    first = _w(rom, base)
    while base + 2 * k < base + first:
        a = base + _w(rom, base + 2 * k)
        n = _b(rom, a)
        out.append([(_w(rom, a + 1 + 4 * r), _w(rom, a + 3 + 4 * r)) for r in range(n)])
        k += 1
    return out


def script_base(rom, aid):
    return anim_rec(rom, aid)['script']


def _motion_offsets(rom, base):
    lt = _w(rom, base + 2)
    return [_w(rom, base + 4 + 2 * k) for k in range((lt - 4) // 2)]


def layouts(rom, aid):
    """Frame layouts: [page or None, [(x, y, tile, attr, big, hi)]]."""
    base = script_base(rom, aid)
    lt = _w(rom, base + 2)
    n_frames = (min(_motion_offsets(rom, base)) - lt) // 2
    out = []
    for k in range(n_frames):
        a = base + _w(rom, base + lt + 2 * k)
        page, n = _b(rom, a), _b(rom, a + 1)
        ents = []
        for i in range(n):
            e = a + 3 + 5 * i
            xl, xh, y, t, at = (_b(rom, e + j) for j in range(5))
            x = xl - (256 if xh & 1 else 0)
            ents.append((x, y - 256 if y >= 128 else y, t, at, bool(xh & 2), xh))
        out.append([None if page == 0xFF else page, ents])
    return out


def motions(rom, aid):
    base = script_base(rom, aid)
    offs = _motion_offsets(rom, base)
    out = []
    for o in offs:
        a, cmds = base + o, []
        for _ in range(200):
            c, v = _b(rom, a), _b(rom, a + 1)
            cmds.append((c, v))
            a += 2
            if c in (0xFE, 0xFF):
                break
        out.append(cmds)
    return out


def _tile_px(d, o):
    rows = []
    for y in range(8):
        b0, b1, b2, b3 = d[o + 2 * y], d[o + 2 * y + 1], d[o + 16 + 2 * y], d[o + 17 + 2 * y]
        rows.append([((b0 >> (7 - x)) & 1) | ((b1 >> (7 - x)) & 1) << 1 | ((b2 >> (7 - x)) & 1) << 2 | ((b3 >> (7 - x)) & 1) << 3
                     for x in range(8)])
    return rows


def snes_rgb(c):
    return ((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31)


# ---------------------------------------------------------------- project file
FIELDS = ['row', 'class', '_class', 'weapon', '_weapon', 'character', 'gender', 'anim', 'body', 'upper', 'palette']
LIMITS = {'anim': None, 'body': None, 'upper': None, 'palette': None}


def id_limits(rom):
    """How many ids each lookup table has (index bytes before the first record)."""
    return {'anim': 0x60 - 1, 'body': 0x68 - 1, 'upper': 0x48 - 1, 'palette': 0x6B - 1}


def export(rom, path, class_names):
    import csv
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in assignments(rom):
            w.writerow([r['row'], r['class'], class_names.get(r['class'], ''), r['weapon'],
                        WEAPON_KINDS.get(r['weapon'], ''), r['character'], r['gender'],
                        r['anim'], r['gfx'], r['palette'], r['extra']])
    print('wrote', path)


def read_rows(path):
    import csv
    return list(csv.DictReader(open(path, newline='', encoding='utf-8')))


def apply(rom, proj):
    """Write battle_anims.csv back into the table at $97:88C9 (same 206 rows, in place)."""
    import os
    path = os.path.join(proj, 'battle_anims.csv')
    if not os.path.exists(path):
        return 0
    lim = id_limits(rom)
    n = 0
    for line, r in enumerate(read_rows(path), 2):
        i = int(r['row'])
        if not 0 <= i < ASSIGN_N:
            raise SystemExit(f'battle_anims.csv line {line}: row {i} is outside 0-{ASSIGN_N - 1}')
        vals = []
        for k in ('class', 'weapon', 'character', 'gender', 'anim', 'body', 'upper', 'palette'):
            v = int(r[k])
            hi = lim.get(k, 255)
            if not 0 <= v <= hi:
                raise SystemExit(f'battle_anims.csv line {line}: {k} {v} is outside 0-{hi}')
            vals.append(v)
        f = snes_to_file(ASSIGN + 8 * i)
        if bytes(rom[f:f + 8]) != bytes(vals):
            rom[f:f + 8] = bytes(vals)
            n += 1
    if n:
        print(f'battle animations: {n} class/weapon row(s) changed')
    return n


# ---------------------------------------------------------------- rendering (no extra packages)
_px_cache = {}


def _tile_idx(d):
    """64 colour indexes of a 4bpp tile, cached."""
    key = bytes(d)
    v = _px_cache.get(key)
    if v is None:
        v = [c for row in _tile_px(d, 0) for c in row]
        if len(_px_cache) > 50000:
            _px_cache.clear()
        _px_cache[key] = v
    return v


class Look:
    """Everything one combatant needs: animation, sheet, upper-body tiles, palettes and a weapon."""

    def __init__(self, rom, anim, body, upper, pal, item=None):
        self.rom, self.anim = rom, anim
        self.sheet = sheet(rom, body)
        self.pages = pages(rom, anim)
        self.layouts = layouts(rom, anim)
        self.motions = motions(rom, anim)
        self.extra = extra_tiles(rom, upper)
        cols = palette(rom, pal)['colors']
        pad = lambda p: (p + [(0, 0, 0, 255)] * 16)[:16]  # noqa: E731
        self.pals = {0: pad([(0, 0, 0, 0)] + [snes_rgb(c) + (255,) for c in cols[:15]]),
                     1: pad([(0, 0, 0, 0)] + [snes_rgb(c) + (255,) for c in cols[16:31]]),
                     3: [(0, 0, 0, 0)] + [(16, 16, 32, 120)] * 15}
        if item is not None:
            wp = weapon(rom, item)
            self.extra.update(wp['tiles'])
            self.pals[2] = pad([(0, 0, 0, 0)] + [snes_rgb(c) + (255,) for c in wp['colors'][:15]])

    def bounds(self):
        xs, ys = [0], [0]
        for _, ents in self.layouts:
            for x, y, t, at, big, xh in ents:
                n = 16 if big else 8
                xs += [x, x + n]
                ys += [y, y + n]
        return min(xs), min(ys), max(xs), max(ys)

    def frame(self, k, cell, origin, buf=None, x_off=0, stride=None):
        """Draw frame k into an RGBA bytearray (stride = row width in pixels)."""
        cw, chh = cell
        stride = stride or cw
        if buf is None:
            buf = bytearray(cw * chh * 4)
        page, ents = self.layouts[k]
        tiles = dict(self.extra)
        if page is not None and page < len(self.pages):
            for r, (off, n) in enumerate(self.pages[page]):
                for i in range(n // 32):
                    if off + 32 * i + 32 <= len(self.sheet):
                        tiles[16 * r + i] = self.sheet[off + 32 * i: off + 32 * i + 32]
        ox, oy = origin
        for x, y, t, at, big, xh in reversed(ents):
            n = 2 if big else 1
            hf, vf = bool(at & 0x40), bool(at & 0x80)
            pal = self.pals.get((at >> 1) & 7, self.pals[0])
            for ty in range(n):
                for tx in range(n):
                    sx = (n - 1 - tx) if hf else tx
                    sy = (n - 1 - ty) if vf else ty
                    d = tiles.get((t + sx + 16 * sy) & 0xFF)
                    if d is None:
                        continue
                    px = _tile_idx(d)
                    bx, by = ox + x + 8 * tx, oy + y + 8 * ty
                    for py in range(8):
                        Y = by + py
                        if not 0 <= Y < chh:
                            continue
                        row = px[8 * (7 - py if vf else py): 8 * (7 - py if vf else py) + 8]
                        for qx in range(8):
                            v = row[7 - qx if hf else qx]
                            if not v:
                                continue
                            X = bx + qx
                            if 0 <= X < cw:
                                o = ((Y * stride) + x_off + X) * 4
                                buf[o:o + 4] = bytes(pal[v])
        return buf

    def strip(self, max_w=320, max_h=200):
        """All frames side by side: (png bytes, cell size, origin)."""
        x0, y0, x1, y1 = self.bounds()
        x0, x1 = max(x0, -max_w // 2), min(x1, max_w // 2)
        y0, y1 = max(y0, -max_h + 16), min(y1, 24)
        cell = (x1 - x0 + 4, y1 - y0 + 4)
        origin = (-x0 + 2, -y0 + 2)
        n = max(1, len(self.layouts))
        W = cell[0] * n
        buf = bytearray(W * cell[1] * 4)
        for k in range(len(self.layouts)):
            self.frame(k, cell, origin, buf, k * cell[0], W)
        rows = [buf[y * W * 4:(y + 1) * W * 4] for y in range(cell[1])]
        return G.png(W, cell[1], rows), cell, origin
