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


def _tables(rom, operand, add_at):
    """(id byte table, records) where the code reads them now (moved when a project adds looks)."""
    idx = _p24(rom, operand)
    return idx, idx + _w(rom, add_at)


def anim_rec(rom, aid):
    idx, recs = _tables(rom, 0x958ABF, 0x958ACD)
    k = _b(rom, idx + 1 + aid)
    return {'rec': k, 'script': _p24(rom, recs + 6 * k), 'pages': _p24(rom, recs + 6 * k + 3)}


def gfx_rec(rom, gid):
    idx, recs = _tables(rom, 0x9584E2, 0x9584F0)
    k = _b(rom, idx + 1 + gid)
    a = recs + 5 * k
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
    looks = read_looks(lambda rel: open(os.path.join(proj, *rel.split('/')), 'rb').read()
                       if os.path.exists(os.path.join(proj, *rel.split('/'))) else None)
    extra = {'anim': {int(x['anim']) for x in looks}, 'body': {int(x['body']) for x in looks}}
    n = 0
    for line, r in enumerate(read_rows(path), 2):
        i = int(r['row'])
        if not 0 <= i < ASSIGN_N:
            raise SystemExit(f'battle_anims.csv line {line}: row {i} is outside 0-{ASSIGN_N - 1}')
        vals = []
        for k in ('class', 'weapon', 'character', 'gender', 'anim', 'body', 'upper', 'palette'):
            v = int(r[k])
            hi = lim.get(k, 255)
            if not (0 <= v <= hi or v in extra.get(k, ())):
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


# ---------------------------------------------------------------- redrawing frames
BAND = 10            # colour swatches above the frames in a drawing PNG
ANIM_N, BODY_N = 0x5F, 0x67      # ids in the game's own tables (0..ANIM_N-1, 0..BODY_N-1)
MAX_SHEET = 0x6000   # a fighter's decompressed sheet must end before the next buffer


def is_drawn(t, at):
    """Pieces a drawing covers: the frame's own tiles and the upper-body tiles in body colours.
    Weapon ($40-$5F), shadow ($60-$7F) and weapon-coloured upper tiles stay as they are."""
    return t < 0x40 or (t >= 0x80 and (at >> 1) & 7 in (0, 1))


def _script_extent(rom, base):
    lt = _w(rom, base + 2)
    end = lt + 2 * len(layouts_offsets(rom, base))
    for o in _motion_offsets(rom, base):
        a = o
        for _ in range(400):
            c = _b(rom, base + a)
            a += 2
            if c in (0xFE, 0xFF):
                break
        end = max(end, a)
    for o in layouts_offsets(rom, base):
        end = max(end, o + 3 + 5 * _b(rom, base + o + 1))
    return end


def layouts_offsets(rom, base):
    lt = _w(rom, base + 2)
    n = (min(_motion_offsets(rom, base)) - lt) // 2
    return [_w(rom, base + lt + 2 * k) for k in range(n)]


class Drawing:
    """A look's frames as pixels of (palette 0/1, colour) for the drawn pieces only."""

    def __init__(self, look):
        self.look = look
        x0, y0, x1, y1 = look.bounds()
        x0, x1 = max(x0, -160), min(x1, 160)
        y0, y1 = max(y0, -184), min(y1, 24)
        self.cell = (x1 - x0 + 4, y1 - y0 + 4)
        self.origin = (-x0 + 2, -y0 + 2)

    def frame_px(self, k):
        cw, chh = self.cell
        ox, oy = self.origin
        grid = [None] * (cw * chh)
        L = self.look
        page, ents = L.layouts[k]
        tiles = dict(L.extra)
        if page is not None and page < len(L.pages):
            for r, (off, n) in enumerate(L.pages[page]):
                for i in range(n // 32):
                    if off + 32 * i + 32 <= len(L.sheet):
                        tiles[16 * r + i] = L.sheet[off + 32 * i: off + 32 * i + 32]
        for x, y, t, at, big, xh in reversed(ents):
            p = (at >> 1) & 7
            if not is_drawn(t, at):
                continue
            n = 2 if big else 1
            hf, vf = bool(at & 0x40), bool(at & 0x80)
            for ty in range(n):
                for tx in range(n):
                    sx = (n - 1 - tx) if hf else tx
                    sy = (n - 1 - ty) if vf else ty
                    d = tiles.get((t + sx + 16 * sy) & 0xFF)
                    if d is None:
                        continue
                    px = _tile_idx(d)
                    for py in range(8):
                        Y = oy + y + 8 * ty + py
                        if not 0 <= Y < chh:
                            continue
                        for qx in range(8):
                            v = px[8 * (7 - py if vf else py) + (7 - qx if hf else qx)]
                            X = ox + x + 8 * tx + qx
                            if v and 0 <= X < cw:
                                grid[Y * cw + X] = (p & 1, v)
        return grid

    def png(self):
        cw, chh = self.cell
        n = len(self.look.layouts)
        W, H = max(cw * n, 9 * 31 + 2), BAND + chh
        buf = bytearray(W * H * 4)

        def put(x, y, c):
            o = (y * W + x) * 4
            buf[o:o + 4] = bytes(c)
        for p in (0, 1):
            for i in range(1, 16):
                c = self.look.pals[p][i]
                for yy in range(1, 9):
                    for xx in range(8):
                        put(1 + (p * 15 + i - 1) * 9 + p * 4 + xx, yy, c)
        for k in range(n):
            g = self.frame_px(k)
            for i, v in enumerate(g):
                if v:
                    put(k * cw + i % cw, BAND + i // cw, self.look.pals[v[0]][v[1]])
            # a faint frame border so frames are easy to tell apart
            for yy in range(chh):
                if not g[yy * cw]:
                    put(k * cw, BAND + yy, (128, 128, 128, 40))
        return G.png(W, H, [buf[y * W * 4:(y + 1) * W * 4] for y in range(H)])


def _match(pals, rgb):
    """{palette: colour} for every exact-or-close match of rgb in palettes 0 and 1."""
    best, out = None, {}
    for p in (0, 1):
        for i in range(1, 16):
            c = pals[p][i]
            d = abs(c[0] - rgb[0]) + abs(c[1] - rgb[1]) + abs(c[2] - rgb[2])
            if d <= 24:
                if p not in out or d < out[p][1]:
                    out[p] = (i, d)
            if best is None or d < best:
                best = d
    return {p: v[0] for p, v in out.items()}, best


COMMANDS = {
    # command byte: (name, takes an argument, what it does)
    0xFE: ('End', False, 'stop here'),
    0xFD: ('Hold', False, 'keep showing the frame'),
    0xFC: ('Start over', False, 'play the motion again from its first step'),
    0xFB: ('Go back', True, 'jump back this many steps'),
    0xFA: ('Wait', True, 'keep the frame for this many 1/60 s'),
    0xF7: ('Signal', False, 'tell the other fighter (e.g. the hit lands); usually before End'),
    0xF4: ('Wait for signal', False, 'wait until the other fighter signals'),
    0xF3: ('Repeat back', True, 'jump back this many steps (game-controlled repeat)'),
    0xF1: ('Finish', False, 'end the attack'),
    0xF0: ('Effect F0', False, ''), 0xEF: ('Effect', True, 'start an effect (e.g. a thrown weapon)'),
    0xEE: ('Weapon effect', True, 'effect from the weapon in hand'), 0xED: ('Effect ED', False, ''),
    0xEC: ('Layer', True, 'which layer the fighter is drawn on'), 0xEB: ('Show/hide', True, ''),
    0xE9: ('Flag E9', False, ''), 0xE8: ('Effect E8', False, ''), 0xE7: ('Count hit', False, ''),
}


def check_motion(steps, n_frames):
    """Steps are [command or frame, value]; raises ValueError with a readable reason."""
    if not steps:
        raise ValueError('A motion needs at least one step.')
    if len(steps) > 200:
        raise ValueError('A motion can have at most 200 steps.')
    for i, (c, v) in enumerate(steps):
        if not (0 <= c <= 255 and 0 <= v <= 255):
            raise ValueError(f'Step {i + 1}: values are 0-255.')
        if c < 0xE7:
            if c >= n_frames:
                raise ValueError(f'Step {i + 1}: there is no frame {c} (frames 0-{n_frames - 1}).')
        elif c not in COMMANDS:
            raise ValueError(f'Step {i + 1}: command ${c:02X} isn\'t one the editor knows.')
        if c in (0xFB, 0xF3) and not 1 <= v <= i:
            raise ValueError(f'Step {i + 1}: can only go back 1 to {i} steps.')
    if steps[-1][0] not in (0xFE, 0xFD, 0xFC, 0xFB, 0xF3, 0xF1):
        raise ValueError('The last step must be End, Hold, Start over, Go back or Finish, '
                         'or the game would read past the motion.')


def extended_look(rom, base, extra):
    """Look for base (anim, body, upper, palette) with extra frames appended (copies by number)."""
    a, bd, up, pl = base
    look = Look(rom, a, bd, up, pl)
    n0 = len(look.layouts)
    for j, k in enumerate(extra or []):
        if not 0 <= int(k) < n0 + j:
            raise ValueError(f'Frame {k} doesn\'t exist.')
        look.layouts.append(look.layouts[int(k)])
    return look


def grow_drawing(png_data, cell, src):
    """Append a copy of frame src's cell to a drawing PNG (for a frame added after it was drawn)."""
    w, h, px = G.read_png(png_data)
    cw = cell[0]
    rows = []
    for y in range(h):
        row = list(px[y * w:(y + 1) * w])
        row += row[src * cw:(src + 1) * cw] if y >= BAND else [(0, 0, 0, 0)] * cw
        rows.append(bytes(v for p in row for v in p))
    return G.png(w + cw, h, rows)


def import_drawing(rom, base, png_data, motions_over=None, extra=None):
    """Build a new look from base (anim, body, upper, palette): an optional drawing PNG (changed frames are
    re-cut), motion overrides {index: steps} and extra frames (copies of existing ones, by number).
    Returns {'script', 'pages', 'sheet' (None = keep the base sheet), 'changed', 'tiles'}."""
    a, bd, up, pl = base
    extra = [int(k) for k in (extra or [])]
    look = extended_look(rom, base, extra)
    dr = Drawing(look)
    cw, chh = dr.cell
    ox, oy = dr.origin
    n = len(look.layouts)
    sbase = script_base(rom, a)
    old_offs = layouts_offsets(rom, sbase)
    sraw = rom[snes_to_file(sbase):snes_to_file(sbase) + _script_extent(rom, sbase)]
    layout_recs = [bytes(sraw[o:o + 3 + 5 * sraw[o + 1]]) for o in old_offs]
    layout_recs += [layout_recs[int(k)] for k in extra]
    mot = [list(m) for m in motions(rom, a)]
    for i, steps in (motions_over or {}).items():
        i = int(i)
        if not 0 <= i < len(mot):
            raise ValueError(f'There is no motion {i}.')
        steps = [[int(c), int(v)] for c, v in steps]
        check_motion(steps, n)
        mot[i] = steps
    sheet_out = bytearray(look.sheet)
    new_pages = []
    changed = []
    total_tiles = 0
    if png_data is None:
        png_data = dr.png()
    try:
        w, h, px = G.read_png(png_data)
    except Exception as e:      # noqa: BLE001 (zlib, struct and format errors alike)
        raise ValueError(f'That file isn\'t a PNG the editor can read ({e}). Save it as a PNG and try again.')
    if (w, h) != (max(cw * n, 9 * 31 + 2), BAND + chh):
        raise ValueError(f'The picture is {w}x{h}; this animation\'s drawing is {max(cw * n, 9 * 31 + 2)}x{BAND + chh}. '
                         'Start from "Download frames to draw on" and keep its size.')
    for k in range(n):
        old = dr.frame_px(k)
        cand = [None] * (cw * chh)
        for y in range(chh):
            for x in range(cw):
                r, g, b, al = px[(BAND + y) * w + k * cw + x]
                if al < 128:
                    continue
                m, dist = _match(look.pals, (r, g, b))
                if not m:
                    raise ValueError(f'Frame {k}, pixel ({x}, {y}): colour #{r:02X}{g:02X}{b:02X} isn\'t in this '
                                     'look\'s palettes. Use the colours in the swatches at the top.')
                cand[y * cw + x] = m
        same = all((o is None and c is None) or (o is not None and c is not None and c.get(o[0]) == o[1])
                   for o, c in zip(old, cand))
        if same:
            continue
        changed.append(k)
        # 8x8 tiles on a grid aligned to the frame's origin
        gx0 = -((ox + 7) // 8) * 8
        gy0 = -((oy + 7) // 8) * 8
        tiles = {}          # (tx, ty, palette) -> 64 colour indexes; a square may need one piece per palette
        for ty in range(gy0, chh - oy, 8):
            for tx in range(gx0, cw - ox, 8):
                cells = []
                for yy in range(8):
                    for xx in range(8):
                        X, Y = ox + tx + xx, oy + ty + yy
                        cells.append(cand[Y * cw + X] if 0 <= X < cw and 0 <= Y < chh else None)
                if not any(cells):
                    continue
                votes = [0, 0]
                for c in cells:
                    if c and len(c) == 1:
                        votes[next(iter(c))] += 1
                pref = 0 if votes[0] >= votes[1] else 1
                for p in (0, 1):
                    data = [(c[p] if (c and p in c and (len(c) == 1 or p == pref)) else 0) for c in cells]
                    if any(data):
                        tiles[(tx, ty, p)] = data
        # pair 8x8 tiles into 16x16 pieces where a 16x16 square has 3+ tiles of one palette
        used = set()
        pieces = []
        for (tx, ty, p) in sorted(tiles):
            if (tx, ty, p) in used or (tx - gx0) % 16 or (ty - gy0) % 16:
                continue
            quad = [(tx, ty, p), (tx + 8, ty, p), (tx, ty + 8, p), (tx + 8, ty + 8, p)]
            if sum(q in tiles for q in quad) >= 3:
                pieces.append(('big', tx, ty, p, [tiles.get(q, [0] * 64) for q in quad]))
                used.update(quad)
        for q, data in sorted(tiles.items()):
            if q not in used:
                pieces.append(('small', q[0], q[1], q[2], [data]))
        # place pieces on a 16x4 tile grid (tiles $00-$3F)
        slots = [[False] * 16 for _ in range(4)]
        vram = {}
        ents = []
        for kind, tx, ty, p, datas in sorted(pieces, key=lambda q: q[0] != 'big'):
            size = 2 if kind == 'big' else 1
            spot = next(((c, r) for r in range(5 - size) for c in range(17 - size)
                         if all(not slots[r + dr_][c + dc] for dr_ in range(size) for dc in range(size))), None)
            if spot is None:
                raise ValueError(f'Frame {k} needs more than 64 tiles of 8x8. Make it smaller or leave more empty space.')
            c, r = spot
            for dr_ in range(size):
                for dc in range(size):
                    slots[r + dr_][c + dc] = True
                    vram[16 * (r + dr_) + c + dc] = datas[dr_ * 2 + dc] if size == 2 else datas[0]
            xh = (0xC2 if size == 2 else 0) | (1 if tx < 0 else 0)
            ents.append(bytes([tx & 0xFF, xh, ty & 0xFF, 16 * r + c, 0x20 | (p << 1)]))
        top = max(vram) + 1
        total_tiles += len(vram)
        tile_bytes = bytearray(32 * top)
        for t, data in vram.items():
            for yy in range(8):
                b = [0, 0, 0, 0]
                for xx in range(8):
                    v = data[yy * 8 + xx]
                    for pl_ in range(4):
                        b[pl_] |= ((v >> pl_) & 1) << (7 - xx)
                tile_bytes[32 * t + 2 * yy], tile_bytes[32 * t + 2 * yy + 1] = b[0], b[1]
                tile_bytes[32 * t + 16 + 2 * yy], tile_bytes[32 * t + 17 + 2 * yy] = b[2], b[3]
        off = len(sheet_out)
        sheet_out += tile_bytes
        page_no = len(look.pages) + len(new_pages)
        new_pages.append([(off, len(tile_bytes))])
        # the frame's new layout: kept pieces in their places, the new ones where the first drawn piece was
        orig = layout_recs[k]
        hdr = orig[:3]
        kept_before, kept_after, seen = [], [], False
        for i in range(hdr[1]):
            e = orig[3 + 5 * i: 8 + 5 * i]
            if is_drawn(e[3], e[4]):
                seen = True
                continue
            (kept_after if seen else kept_before).append(e)
        allents = kept_before + ents + kept_after
        if len(allents) > 64:
            raise ValueError(f'Frame {k} would need {len(allents)} sprite pieces; the most is 64.')
        rec = bytes([page_no, len(allents), hdr[2]]) + b''.join(allents)
        if page_no > 0xFE:
            raise ValueError('Too many tile pages in one animation.')
        layout_recs[k] = rec
    if len(sheet_out) > MAX_SHEET:
        raise ValueError(f'The drawings need {len(sheet_out)} bytes of tiles; a fighter can use at most {MAX_SHEET}. '
                         'Redraw fewer frames or make them smaller.')
    # the script block, rebuilt: header, motion offsets, layout offsets, motions, layouts
    nm = len(mot)
    lt = 4 + 2 * nm
    body = bytearray()
    m_offs, l_offs = [], []
    start = lt + 2 * n
    for steps in mot:
        m_offs.append(start + len(body))
        body += b''.join(bytes([c, v]) for c, v in steps)
    for rec in layout_recs:
        l_offs.append(start + len(body))
        body += rec
    script = (b'\x04\x00' + lt.to_bytes(2, 'little') + b''.join(o.to_bytes(2, 'little') for o in m_offs)
              + b''.join(o.to_bytes(2, 'little') for o in l_offs) + bytes(body))
    if len(script) > 0x7FFF:
        raise ValueError('This animation got too big.')
    # page table: offsets for old + new pages, then the records
    allp = look.pages + new_pages
    head = 2 * len(allp)
    recs = bytearray()
    offs = []
    for pg in allp:
        offs.append(head + len(recs))
        recs += bytes([len(pg)]) + b''.join(o.to_bytes(2, 'little') + s.to_bytes(2, 'little') for o, s in pg)
    pages_blk = b''.join(o.to_bytes(2, 'little') for o in offs) + bytes(recs)
    return {'script': bytes(script), 'pages': pages_blk, 'sheet': bytes(sheet_out) if changed else None,
            'changed': changed, 'tiles': total_tiles}


# ---------------------------------------------------------------- custom looks in a project
# battle/looks.json: [{"anim": new id, "body": new id, "from": [anim, body, upper, palette], "png": "battle/xx.png"}]
LOOKS = 'battle/looks.json'
# code that reads the two tables: (address of the operand, what it points at now, offset in the new table)
ANIM_REFS = [(0x958ABF, ANIM_IDX, 0), (0x958AD2, ANIM_IDX, 0), (0x958AD9, ANIM_IDX + 1, 1),
             (0x958AE0, ANIM_IDX + 3, 3), (0x958AE7, ANIM_IDX + 4, 4)]
ANIM_ADD = 0x958ACD          # ADC #$0060 (records after the id bytes)
GFX_REFS = [(0x9584E2, GFX_IDX, 0), (0x9584FB, GFX_IDX, 0), (0x9584F5, GFX_IDX + 1, 1),
            (0x958527, GFX_IDX + 3, 3), (0x958538, GFX_IDX + 3, 3)]
GFX_ADD = 0x9584F0           # ADC #$0068
CUE_IDX = 0x97C884           # per-animation cue table ($95:E400: hit sparks, sounds), 9-byte records
CUE_REFS = [(0x95E41E, CUE_IDX, 0), (0x95E43E, CUE_IDX, 0), (0x95E444, CUE_IDX + 1, 1),
            (0x95E432, CUE_IDX + 3, 3), (0x95E438, CUE_IDX + 4, 4), (0x95E44A, CUE_IDX + 6, 6),
            (0x95E450, CUE_IDX + 7, 7)]
CUE_ADD = 0x95E42D           # ADC #$0060
NEW_ADD = 0x100              # expanded tables: 256 id bytes, then records


def read_looks(reader):
    import json
    d = reader(LOOKS)
    return json.loads(d.decode('utf-8')) if d else []


def _patch_operand(rom, at, expect, new):
    f = snes_to_file(at)
    cur = rom[f] | rom[f + 1] << 8 | rom[f + 2] << 16
    if cur != expect:
        raise SystemExit(f'battle animations: unexpected code at ${at:06X} (this ROM differs)')
    rom[f:f + 3] = new.to_bytes(3, 'little')


def expand_tables(rom, far, n_anim, n_body):
    """Move the animation and body tables to free space with room for new ids; returns their bases."""
    out = {}
    for name, idx_base, n_ids, rec_size, refs, add_at, old_add, n_new in (
            ('anim', ANIM_IDX, ANIM_N, 6, ANIM_REFS, ANIM_ADD, 0x60, n_anim),
            ('body', GFX_IDX, BODY_N, 5, GFX_REFS, GFX_ADD, 0x68, n_body),
            ('cue', CUE_IDX, ANIM_N, 9, CUE_REFS, CUE_ADD, 0x60, 0)):
        f = snes_to_file(idx_base)
        ids = bytearray(rom[f + 1:f + 1 + n_ids])          # byte per id (the table starts one byte early)
        n_recs = max(ids) + 1
        recs = bytearray(rom[f + old_add:f + old_add + rec_size * n_recs])
        size = NEW_ADD + rec_size * (n_recs + n_new)
        base = far.alloc(size)
        blk = bytearray(size)
        blk[0] = rom[f]
        blk[1:1 + n_ids] = ids
        blk[NEW_ADD:NEW_ADD + len(recs)] = recs
        fb = snes_to_file(base)
        rom[fb:fb + size] = blk
        for at, expect, delta in refs:
            _patch_operand(rom, at, expect, base + delta)
        fa = snes_to_file(add_at)
        if rom[fa:fa + 2] != old_add.to_bytes(2, 'little'):
            raise SystemExit(f'battle animations: unexpected code at ${add_at:06X}')
        rom[fa:fa + 2] = NEW_ADD.to_bytes(2, 'little')
        out[name] = (base, n_recs)
    return out


def apply_custom(rom, reader, far):
    """Write the project's redrawn looks: new animations and body graphics in free space.
    reader(rel path) -> bytes or None. Returns the number of looks written."""
    import fe4lz
    looks = read_looks(reader)
    if not looks:
        return 0
    tb = expand_tables(rom, far, len(looks), len(looks))
    (abase, a_recs), (bbase, b_recs) = tb['anim'], tb['body']
    clean = bytes(rom)
    for i, lk in enumerate(looks):
        aid, bid = int(lk['anim']), int(lk['body'])
        if not (ANIM_N <= aid <= 0xFE and BODY_N <= bid <= 0xFE):
            raise SystemExit(f'battle/looks.json: look {i} has ids outside the new range')
        png = reader(lk['png']) if lk.get('png') else None
        if lk.get('png') and png is None:
            raise SystemExit(f'battle animations: {lk["png"]} is missing')
        try:
            got = import_drawing(clean, tuple(int(x) for x in lk['from']), png, lk.get('motions'), lk.get('extra'))
        except ValueError as e:
            raise SystemExit(f'battle animations: look {lk.get("name") or i} ({lk.get("png") or "motions"}): {e}')
        if got['sheet'] is not None:
            packed = fe4lz.compress(got['sheet'])
            sheet_at = far.alloc(len(packed))
            f = snes_to_file(sheet_at)
            rom[f:f + len(packed)] = packed
            sheet_rec = sheet_at.to_bytes(3, 'little') + (0xFFFF).to_bytes(2, 'little')
        else:            # same drawings as the base: reuse its sheet (and overlay)
            g = gfx_rec(clean, int(lk['from'][1]))
            sheet_rec = g['sheet'].to_bytes(3, 'little') + g['overlay'].to_bytes(2, 'little')
        # the frame code sets the data bank to the script's bank and also reaches its RAM buffers through
        # it, so scripts and page tables must sit where $0000-$1FFF is RAM: the $30-$3D mirrors of the
        # upper halves of $70-$7D
        script_at = far.alloc(len(got['script']), upper_half=True) - 0x400000
        pages_at = far.alloc(len(got['pages']), upper_half=True) - 0x400000
        for at, data in ((script_at, got['script']), (pages_at, got['pages'])):
            f = snes_to_file(at)
            rom[f:f + len(data)] = data
        # new records and ids
        ar = a_recs + i
        f = snes_to_file(abase + NEW_ADD + 6 * ar)
        rom[f:f + 6] = script_at.to_bytes(3, 'little') + pages_at.to_bytes(3, 'little')
        rom[snes_to_file(abase + 1 + aid)] = ar
        cue = tb['cue'][0]       # the new animation keeps its base animation's hit and sound cues
        rom[snes_to_file(cue + 1 + aid)] = rom[snes_to_file(cue + 1 + int(lk['from'][0]))]
        br = b_recs + i
        f = snes_to_file(bbase + NEW_ADD + 5 * br)
        rom[f:f + 5] = sheet_rec
        rom[snes_to_file(bbase + 1 + bid)] = br
    print(f'battle animations: {len(looks)} redrawn look(s)')
    return len(looks)


# ---------------------------------------------------------------- spells: which effect an item plays
# $99:832D: 3-byte rows (item, spell, alternate spell) ending $FFFF, read by $96:DC7C when a motion's
# $EE/$EF step starts the item's effect. The alternate is used when $7E:4EAB >= 3 (Physic, Restore and
# the status staves at range). Spell scripts: $97:8F7D + word offset per spell (105 of them).
SPELL_TABLE = 0x99832D
SPELL_REFS = [(0x96DC92, SPELL_TABLE), (0x96DCB7, SPELL_TABLE + 1), (0x96DCBD, SPELL_TABLE + 2)]
SPELL_SCRIPTS = 0x978F7D
SPELL_FIELDS = ['item', '_item', 'spell', 'spell_far']


def spell_rows(rom):
    f = snes_to_file(SPELL_TABLE)
    out = []
    while rom[f] | rom[f + 1] << 8 != 0xFFFF:
        out.append((rom[f], rom[f + 1], rom[f + 2]))
        f += 3
    return out


def spell_count(rom):
    import fe4spellfx
    return fe4spellfx.spell_count(rom)


def spell_names(rom, item_names):
    """{spell: 'Fire'}: the items that use each spell in the game's table, tomes and staves before
    the swords that borrow their effect ('Fire / Flame sword')."""
    got = {}
    for it, a, b in sorted(spell_rows(rom), key=lambda r: (r[0] < 20, r[0])):
        for s in dict.fromkeys((a, b)):
            n = item_names.get(it, f'item {it}')
            if n not in got.setdefault(s, []):
                got[s].append(n)
    return {s: ' / '.join(v[:2]) for s, v in got.items()}


def export_spells(rom, path, item_names):
    import csv
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(SPELL_FIELDS)
        for it, a, b in spell_rows(rom):
            w.writerow([it, item_names.get(it, ''), a, b])
    print('wrote', path)


def apply_spells(rom, proj, far):
    """spells.csv -> the item/spell table; moved to free space when it gets longer."""
    import csv
    import os
    path = os.path.join(proj, 'spells.csv')
    if not os.path.exists(path):
        return 0
    n_sp = spell_count(rom)
    rows, seen = [], set()
    for line, r in enumerate(csv.DictReader(open(path, newline='', encoding='utf-8')), 2):
        try:
            it, a, b = int(r['item']), int(r['spell']), int(r.get('spell_far') or r['spell'])
        except (KeyError, ValueError):
            raise SystemExit(f'spells.csv line {line}: item, spell and spell_far are numbers')
        if not 0 <= it <= 0xFE or it in seen:
            raise SystemExit(f'spells.csv line {line}: item {it} is out of range or listed twice')
        if not (0 <= a < n_sp and 0 <= b < n_sp):
            raise SystemExit(f'spells.csv line {line}: spells are 0-{n_sp - 1}')
        seen.add(it)
        rows.append((it, a, b))
    old = spell_rows(rom)
    if rows == old:
        return 0
    data = b''.join(bytes(x) for x in rows) + b'\xff\xff\xff'
    f = snes_to_file(SPELL_TABLE)
    if len(rows) <= len(old):
        rom[f:f + len(data)] = data
    else:
        at = far.alloc(len(data))
        rom[snes_to_file(at):snes_to_file(at) + len(data)] = data
        for op, expect in SPELL_REFS:
            _patch_operand(rom, op, expect, at + (expect - SPELL_TABLE))
    print(f'spells: {len(rows)} item(s) with effects')
    return 1
