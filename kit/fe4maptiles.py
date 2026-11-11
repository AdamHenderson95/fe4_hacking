"""Map tile graphics: redrawing a chapter's own 16x16 tiles (metatiles 0-255) from pictures, and the
terrain type of every metatile.

How a chapter's tiles are built (see fe4maps):
  * 1024 metatiles of 4 tilemap words (TL, BL, TR, BR): 0-255 from the chapter (+3, compressed),
    256-1023 shared by every chapter.  Word = tile (10 bits) | palette row << 10 | h-flip $4000 |
    v-flip $8000.
  * 8x8 tiles 0-639 shared (raw at file 0x190000), 640-767 the chapter's own (+6, compressed, 4 KB).
  * Palette rows 1-7 from the chapter (+9); the metatiles use rows 1-5.
  * Terrain: one byte per metatile (+24, compressed).

A redrawn metatile gets, for each 8x8 quarter, the palette row (of those the chapter uses) that fits
its colours best, and reuses any 8x8 tile already in VRAM that matches (also flipped).  Only new
quarters take one of the chapter's free 8x8 tiles (640-767 that no metatile uses; 3-22 per chapter),
then one from the shared pool: shared tiles 0-639 that no chapter's metatiles use and the map doesn't
animate (25 in the game).
Pool tiles are raw in the shared tile data, so each one goes to one chapter: chapters are filled in
order (Prologue first) and later chapters get what is left.
"""
import csv
import os
import re

import fe4lz
import fe4maps as M
from dis65816 import snes_to_file
from fe4gfx import png, read_png

CH_TILE0, CH_TILES = 640, 128
# shared tiles the map animates (water): $88:CFC2 sends 32 tiles from $DC:xxxx to tiles 160-191 every
# few frames, and tiles up to 254 changed during play too; the pool leaves 128-255 alone
ANIMATED = (128, 256)
FIELDS = ['chapter', 'tile', 'terrain']


class ChapterGfx:
    def __init__(self, rom, ch, pool=()):
        rom = bytes(rom)
        self.ch = ch
        self.pool = list(pool)            # shared tiles this chapter may take, in order
        self.pool_new = {}                # shared tile -> 32 bytes this chapter drew there
        hd = M.header(rom, ch)
        self.hd = hd
        meta = fe4lz.decompress(rom, hd['meta'])[:0x800].ljust(0x800, b'\0')
        fo = snes_to_file(M.SHARED_META)
        meta += rom[fo:fo + 0x1800]
        self.words = [meta[i] | meta[i + 1] << 8 for i in range(0, 0x2000, 2)]
        self.shared = bytes(rom[M.SHARED_TILES:M.SHARED_TILES + 0x5000])
        self.ctiles = bytearray(fe4lz.decompress(rom, hd['tiles'])[:0x1000].ljust(0x1000, b'\0'))
        pfo = snes_to_file(hd['pal'])
        cg = bytes(M.PAL0) + rom[pfo:pfo + 224]
        self.pal = []
        for k in range(128):
            v = cg[2 * k] | cg[2 * k + 1] << 8
            self.pal.append(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31))
        try:
            self.terrain = list(fe4lz.decompress(rom, hd['terrain'])[:1024].ljust(1024, b'\0'))
        except Exception:          # noqa: BLE001
            self.terrain = [0] * 1024
        self.rows = sorted({(w >> 10) & 7 for w in self.words[:1024]} - {0}) or [1, 2, 3, 4, 5]
        self._orig = (list(self.words), bytes(self.ctiles), list(self.terrain))

    # ---- tiles
    def tile_bytes(self, n):
        if n in self.pool_new:
            return self.pool_new[n]
        if n < CH_TILE0:
            return self.shared[n * 32:n * 32 + 32]
        if n < CH_TILE0 + CH_TILES:
            return bytes(self.ctiles[(n - CH_TILE0) * 32:(n - CH_TILE0) * 32 + 32])
        return bytes(32)

    @staticmethod
    def decode(b):
        out = []
        for y in range(8):
            p = (b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[17 + 2 * y])
            out.append(tuple(sum(((p[k] >> (7 - x)) & 1) << k for k in range(4)) for x in range(8)))
        return tuple(out)

    @staticmethod
    def encode(px):
        out = bytearray(32)
        for y in range(8):
            for k in range(4):
                v = 0
                for x in range(8):
                    if px[y][x] >> k & 1:
                        v |= 0x80 >> x
                out[(k >> 1) * 16 + 2 * y + (k & 1)] = v
        return bytes(out)

    def used_tiles(self, skip=()):
        return {w & 0x3FF for i, w in enumerate(self.words) if i // 4 not in skip}

    def free_tiles(self, skip=()):
        used = self.used_tiles(skip)
        return [n for n in range(CH_TILE0, CH_TILE0 + CH_TILES) if n not in used]

    def room(self):
        """(own free 8x8 tiles, pool tiles still available to this chapter)."""
        return len(self.free_tiles()), len(self.pool)

    def metatile_rgba(self, k):
        """16x16 rows of (r, g, b, a)."""
        rows = [[(0, 0, 0, 0)] * 16 for _ in range(16)]
        for q in range(4):
            w = self.words[4 * k + q]
            t = self.decode(self.tile_bytes(w & 0x3FF))
            p = ((w >> 10) & 7) * 16
            ox, oy = (q // 2) * 8, (q % 2) * 8
            for y in range(8):
                src = t[7 - y if w & 0x8000 else y]
                if w & 0x4000:
                    src = src[::-1]
                for x in range(8):
                    c = src[x]
                    rows[oy + y][ox + x] = (*self.pal[(p + c) % 128], 255) if c else (*self.pal[0], 255)
        return rows

    def metatile_png(self, k, scale=1):
        rows = self.metatile_rgba(k)
        out = []
        for r in rows:
            line = b''.join(bytes(px) * scale for px in r)
            out += [line] * scale
        return png(16 * scale, 16 * scale, out)

    def atlas_png(self):
        W = 512
        pix = [bytearray(W * 4) for _ in range(W)]
        for k in range(1024):
            rows = self.metatile_rgba(k)
            bx, by = (k % 32) * 16, (k // 32) * 16
            for y in range(16):
                pix[by + y][bx * 4:(bx + 16) * 4] = b''.join(bytes(px) for px in rows[y])
        return png(W, W, pix)

    # ---- redrawing
    def redraw(self, k, rgba):
        """Replace metatile k (0-255) with a 16x16 picture: rgba = 16 rows of 16 (r, g, b, a).
        Raises ValueError when the chapter runs out of free 8x8 tiles."""
        if not 0 <= k < 256:
            raise ValueError('only the chapter\'s own tiles (0-255) can be redrawn; 256-1023 are shared by every chapter')
        index = {}
        keep = self.used_tiles(skip=(k,))
        released = [n for n in self.pool_new if n not in keep]   # pool tiles only k used
        for n in released:
            del self.pool_new[n]
        self.pool = sorted(set(self.pool) | set(released))
        for n in range(CH_TILE0 + CH_TILES):
            if (n >= CH_TILE0 or n in self.pool) and n not in keep:
                continue                  # free (or about to be): not a reuse candidate
            t = self.decode(self.tile_bytes(n))
            for fl in range(4):
                v = t[::-1] if fl & 2 else t
                v = tuple(r[::-1] for r in v) if fl & 1 else v
                index.setdefault(v, (n, fl))
        free = self.free_tiles(skip=(k,)) + [n for n in self.pool if n not in keep]
        new_words = []
        new_tiles = {}
        for q in range(4):
            ox, oy = (q // 2) * 8, (q % 2) * 8
            px = [rgba[oy + y][ox:ox + 8] for y in range(8)]
            best = None
            for row in self.rows:
                cols = self.pal[row * 16 + 1:row * 16 + 16]
                err, idx = 0, []
                for line in px:
                    out = []
                    for r, g, b, a in line:
                        if a < 128:
                            out.append(0)
                            continue
                        d, i = min((3 * (c[0] - r) ** 2 + 4 * (c[1] - g) ** 2 + 2 * (c[2] - b) ** 2, i + 1)
                                   for i, c in enumerate(cols))
                        err += d
                        out.append(i)
                    idx.append(tuple(out))
                if best is None or err < best[0]:
                    best = (err, row, tuple(idx))
            _, row, idx = best
            if idx in index:
                n, fl = index[idx]
            elif idx in new_tiles:
                n, fl = new_tiles[idx], 0
            else:
                if not free:
                    raise ValueError(f'chapter {self.ch} has no free 8x8 tile left for this picture (its own and the '
                                     'shared pool are used up): reuse more of the map\'s existing tiles, or free some by '
                                     'redrawing unused tiles')
                n, fl = free.pop(0), 0
                new_tiles[idx] = n
            new_words.append(n | row << 10 | (0x4000 if fl & 1 else 0) | (0x8000 if fl & 2 else 0))
        for idx, n in new_tiles.items():
            if n < CH_TILE0:
                self.pool_new[n] = self.encode(idx)
                self.pool.remove(n)
            else:
                self.ctiles[(n - CH_TILE0) * 32:(n - CH_TILE0) * 32 + 32] = self.encode(idx)
        self.words[4 * k:4 * k + 4] = new_words
        return len(new_tiles)

    # ---- writing
    def write(self, rom, far):
        """Recompress what changed into far space and repoint the chapter header.  Returns parts written."""
        n = 0
        h = self.hd['file']
        w0, t0, r0 = self._orig
        if self.words[:1024] != w0[:1024]:
            data = b''.join(bytes([w & 0xFF, w >> 8]) for w in self.words[:1024])
            n += self._put(rom, far, h + 3, fe4lz.compress(data))
        if bytes(self.ctiles) != t0:
            n += self._put(rom, far, h + 6, fe4lz.compress(bytes(self.ctiles)))
        if self.terrain != r0:
            n += self._put(rom, far, h + 24, fe4lz.compress(bytes(self.terrain)))
        for t, data in sorted(self.pool_new.items()):
            rom[M.SHARED_TILES + t * 32:M.SHARED_TILES + t * 32 + 32] = data
            n += 1
        return n

    @staticmethod
    def _put(rom, far, ptr_fo, data):
        a = far.alloc(len(data) + 1)
        fo = snes_to_file(a)
        rom[fo:fo + len(data)] = data
        rom[ptr_fo:ptr_fo + 3] = a.to_bytes(3, 'little')
        return 1


# ---------------------------------------------------------------- project files
def drawing_file(ch, k):
    return f'maps/tiles/{M.MAP_NAMES[ch]}/t{k:03d}.png'


def rgba_from_png(data):
    w, h, px = read_png(data)
    if w != h or w % 16 or not 1 <= w // 16 <= 8:
        raise ValueError(f'a map tile is 16 x 16 pixels (or 2x to 8x that); this picture is {w} x {h}')
    s = w // 16
    return [[px[(y * s) * w + x * s] for x in range(16)] for y in range(16)]


def export_terrain(rom, path):
    with open(path, 'w', newline='') as f:
        wr = csv.writer(f)
        wr.writerow(FIELDS)
        for ch in range(M.MAP_COUNT):
            g = ChapterGfx(rom, ch)
            for k in range(1024):
                wr.writerow([ch, k, g.terrain[k]])
    print('wrote', path)


_pool_cache = {}


def pool_tiles(rom):
    """Shared tiles 0-639 that no chapter's metatiles use (in this ROM)."""
    key = (id(rom), len(rom))
    if key not in _pool_cache:
        used = set()
        for ch in range(M.MAP_COUNT):
            used |= {w & 0x3FF for w in ChapterGfx(rom, ch).words}
        _pool_cache.clear()
        _pool_cache[key] = [t for t in range(CH_TILE0) if t not in used and not ANIMATED[0] <= t < ANIMATED[1]]
    return _pool_cache[key]


def load_project(rom, proj, ch, terrain_rows=None, drawings=None, pool=()):
    """ChapterGfx with the project's terrain and drawings applied (drawings: {k: png bytes})."""
    g = ChapterGfx(rom, ch, pool)
    if terrain_rows is not None:
        for k, t in terrain_rows.items():
            g.terrain[k] = t
    for k, data in sorted((drawings or {}).items()):
        g.redraw(k, rgba_from_png(data))
    return g


def load_chapters(rom, terrain, drawings, upto=M.MAP_COUNT - 1):
    """{ch: ChapterGfx} for chapters 0..upto that have terrain rows or drawings, handing out the shared
    pool in chapter order.  terrain: {ch: {k: t}}, drawings: {ch: {k: png}}.  Raises ValueError
    (with the chapter in .ch) when a chapter runs out of tiles."""
    pool = list(pool_tiles(rom)) if any(drawings.values()) else []
    out = {}
    for ch in range(upto + 1):
        if not drawings.get(ch) and ch not in terrain:
            continue
        try:
            g = load_project(rom, None, ch, terrain.get(ch), drawings.get(ch), pool)
        except ValueError as e:
            e.ch = ch
            raise
        pool = list(g.pool)
        out[ch] = g
    return out


def project_drawings(proj, ch):
    d = os.path.join(proj, 'maps', 'tiles', M.MAP_NAMES[ch])
    out = {}
    if os.path.isdir(d):
        for f in os.listdir(d):
            m = re.fullmatch(r't(\d{3})\.png', f, re.I)
            if m:
                out[int(m.group(1))] = open(os.path.join(d, f), 'rb').read()
    return out


def project_terrain(proj):
    path = os.path.join(proj, 'map_terrain.csv')
    out = {}
    if not os.path.exists(path):
        return out
    for ln, r in enumerate(csv.DictReader(open(path, newline='')), start=2):
        try:
            ch, k, t = int(r['chapter']), int(r['tile']), int(r['terrain'])
        except (ValueError, KeyError) as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        if not (0 <= ch < M.MAP_COUNT and 0 <= k < 1024 and 0 <= t < 256):
            raise SystemExit(f'{path}:{ln}: chapter 0-{M.MAP_COUNT - 1}, tile 0-1023, terrain 0-255')
        out.setdefault(ch, {})[k] = t
    return out


def apply(rom, proj, far):
    terr = project_terrain(proj)
    drawings = {ch: project_drawings(proj, ch) for ch in range(M.MAP_COUNT)}
    try:
        gfx = load_chapters(bytes(rom), terr, drawings)
    except ValueError as e:
        raise SystemExit(f'maps/tiles/{M.MAP_NAMES[getattr(e, "ch", 0)]}: {e}')
    return sum(g.write(rom, far) for g in gfx.values())
