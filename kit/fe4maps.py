#!/usr/bin/env python3
"""FE4 chapter maps: export to CSV + PNG, rebuild with recompression.

Each chapter map header (12 x 27 bytes, pointer table at $88:9FC3):
  +0  ptr24  map layout, compressed (64 x N words; word & $3FF = metatile)
  +3  ptr24  chapter metatiles 0-255, compressed (2 KB; 256-1023 shared at $D9:5000)
  +6  ptr24  chapter BG tile graphics, compressed (4 KB -> VRAM $5000, tiles $280-$2FF)
  +9  ptr24  chapter palettes 1-7, raw (224 bytes -> CGRAM byte 32)
  +24 ptr24  terrain type per metatile, compressed (1 KB)

Metatile = 4 tilemap words (TL, BL, TR, BR) at $7F:0000 + 8*n.  Shared BG
tiles are raw at file 0x190000.  Rendering is optional and needs Pillow.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lz
from dis65816 import snes_to_file

HEADER_TABLE = 0x089FC3
MAP_COUNT = 12
MAP_NAMES = ['prologue', 'ch01', 'ch02', 'ch03', 'ch04', 'ch05', 'ch06', 'ch07', 'ch08',
             'ch09', 'ch10', 'endgame']
SHARED_META = 0xD95000
SHARED_TILES = 0x190000
WIDTH = 64
FREE_START, FREE_END = 0x780000, 0x7DD000      # banks $78-$7D; $7D:D000+ is for code hooks
# palette 0 as loaded by the game on the map screen (not stored raw in the ROM)
PAL0 = bytes.fromhex('00008b31ff7f8414d5629546850cf85a0000fc02f75ad652b5529546753ee90c')


def _p24(rom, fo):
    return rom[fo] | rom[fo + 1] << 8 | rom[fo + 2] << 16


def header(rom, ch):
    h = snes_to_file(_p24(rom, HEADER_TABLE + 3 * ch))
    return {'file': h, 'map': _p24(rom, h), 'meta': _p24(rom, h + 3), 'tiles': _p24(rom, h + 6),
            'pal': _p24(rom, h + 9), 'terrain': _p24(rom, h + 24)}


def load_map(rom, ch):
    raw = fe4lz.decompress(bytes(rom), header(rom, ch)['map'])
    return [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw) - 1, 2)]


def load_map_v15(rom, ch):
    """The map as kits up to v15 exported it (wrong for chapter 5 and the endgame)."""
    raw = fe4lz.decompress_v15(bytes(rom), header(rom, ch)['map'])
    return [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw) - 1, 2)]


def read_csv(path):
    words = []
    for ln, row in enumerate(csv.reader(open(path, newline='')), start=1):
        if not row:
            continue
        if len(row) > WIDTH:
            raise SystemExit(f'{path}:{ln}: expected at most {WIDTH} columns, got {len(row)}')
        for v in row:
            if not v.strip():
                continue
            n = int(v, 0)
            if not 0 <= n <= 0xFFFF:
                raise SystemExit(f'{path}:{ln}: value {v} out of range')
            words.append(n)
    return words


def write_csv(path, words):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        for r in range(0, len(words), WIDTH):
            w.writerow(words[r:r + WIDTH])           # last row may be partial


def upgrade_v15_maps(rom, mapdir):
    """Rewrite map CSVs that an older kit exported wrongly (see fe4lz.decompress). Only files
    still exactly as exported are rewritten; returns [(chapter, 'fixed' | 'edited')]."""
    out = []
    if not os.path.isdir(mapdir):
        return out
    for ch in range(MAP_COUNT):
        path = os.path.join(mapdir, 'ch%02d_%s.csv' % (ch, MAP_NAMES[ch]))
        if not os.path.exists(path):
            continue
        try:
            words = read_csv(path)
        except (SystemExit, ValueError):
            continue
        good = load_map(rom, ch)
        if len(words) == len(good):
            continue
        if words == load_map_v15(rom, ch):
            write_csv(path, good)
            out.append((ch, 'fixed'))
        else:
            out.append((ch, 'edited'))
    return out


def map_bytes(words):
    out = bytearray()
    for w in words:
        out += bytes([w & 0xFF, w >> 8])
    return bytes(out)


# ---------------------------------------------------------------- rendering
class Renderer:
    def __init__(self, rom, ch):
        hd = header(rom, ch)
        rom = bytes(rom)
        meta = fe4lz.decompress(rom, hd['meta'])[:0x800].ljust(0x800, b'\0')
        fo = snes_to_file(SHARED_META)
        meta += rom[fo:fo + 0x1800]
        self.meta = [meta[i] | meta[i + 1] << 8 for i in range(0, 0x2000, 2)]
        vram = bytearray(rom[SHARED_TILES:SHARED_TILES + 0x5000])
        vram += fe4lz.decompress(rom, hd['tiles'])[:0x1000].ljust(0x1000, b'\0')
        self.vram = bytes(vram)
        cg = bytearray(PAL0) + bytearray(rom[snes_to_file(hd['pal']):snes_to_file(hd['pal']) + 224])
        self.pal = [((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3)
                    for v in (cg[2 * k] | cg[2 * k + 1] << 8 for k in range(128))]
        self._tiles = {}
        self._metas = {}

    def tile(self, n):
        if n not in self._tiles:
            a = n * 32
            px = []
            for y in range(8):
                b0, b1, b2, b3 = (self.vram[a + 2 * y] if a + 2 * y < len(self.vram) else 0,
                                  self.vram[a + 2 * y + 1] if a + 2 * y + 1 < len(self.vram) else 0,
                                  self.vram[a + 16 + 2 * y] if a + 16 + 2 * y < len(self.vram) else 0,
                                  self.vram[a + 17 + 2 * y] if a + 17 + 2 * y < len(self.vram) else 0)
                px.append([((b0 >> (7 - x)) & 1) | (((b1 >> (7 - x)) & 1) << 1) |
                           (((b2 >> (7 - x)) & 1) << 2) | (((b3 >> (7 - x)) & 1) << 3) for x in range(8)])
            self._tiles[n] = px
        return self._tiles[n]

    def metatile(self, k):
        from PIL import Image
        if k in self._metas:
            return self._metas[k]
        img = Image.new('RGB', (16, 16))
        for q in range(4):
            e = self.meta[(k & 0x3FF) * 4 + q]
            t = self.tile(e & 0x3FF)
            p = (e >> 10) & 7
            hf, vf = e & 0x4000, e & 0x8000
            ox, oy = (q // 2) * 8, (q % 2) * 8
            for y in range(8):
                for x in range(8):
                    c = t[7 - y if vf else y][7 - x if hf else x]
                    img.putpixel((ox + x, oy + y), self.pal[(p * 16 + c) % 128])
        self._metas[k] = img
        return img

    def render(self, words, width=WIDTH):
        from PIL import Image
        h = len(words) // width
        img = Image.new('RGB', (width * 16, h * 16))
        for i, w in enumerate(words[:width * h]):
            img.paste(self.metatile(w & 0x3FF), ((i % width) * 16, (i // width) * 16))
        return img

    def tileset(self):
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (32 * 16, 32 * 16))
        for k in range(1024):
            img.paste(self.metatile(k), ((k % 32) * 16, (k // 32) * 16))
        return img


# ---------------------------------------------------------------- export / apply
def export(rom, outdir, images=True):
    os.makedirs(outdir, exist_ok=True)
    try:
        import PIL  # noqa: F401
    except ImportError:
        images = False
    for ch in range(MAP_COUNT):
        words = load_map(rom, ch)
        name = 'ch%02d_%s' % (ch, MAP_NAMES[ch])
        write_csv(os.path.join(outdir, name + '.csv'), words)
        if images:
            rd = Renderer(rom, ch)
            img = rd.render(words)
            _draw_locations(rom, ch, img)
            img.save(os.path.join(outdir, name + '.png'))
            rd.tileset().save(os.path.join(outdir, name + '_tiles.png'))
    print('wrote %d maps to %s%s' % (MAP_COUNT, outdir, '' if images else ' (no PNGs: pip install pillow)'))


# location boxes per kind (dx1, dy1, dx2, dy2) from the game's table at $87:F455
_KIND_BOX = {0: (-1, -1, 1, 2), 1: (0, 0, 1, 0), 2: (-1, -1, 1, 0)}


def _draw_locations(rom, ch, img):
    """Outline castles and villages on a map preview, labelled with their index."""
    try:
        from PIL import ImageDraw
        import fe4locations as LOC
    except ImportError:
        return
    d = ImageDraw.Draw(img)
    for c, q, n in LOC.records(rom):
        if c != ch:
            continue
        idx, cid, kind, x, y = rom[q:q + 5]
        dx1, dy1, dx2, dy2 = _KIND_BOX.get(kind, (0, 0, 0, 0))
        box = ((x + dx1) * 16, (y + dy1) * 16, (x + dx2 + 1) * 16 - 1, (y + dy2 + 1) * 16 - 1)
        color = (255, 214, 64) if kind == 0 else (120, 220, 255)
        d.rectangle(box, outline=(0, 0, 0), width=4)
        d.rectangle(box, outline=color, width=2)
        label = '%d %s' % (idx, LOC.castle_name(rom, cid) if kind == 0 else LOC.KINDS.get(kind, ''))
        tx, ty = box[0] + 3, box[1] + 2
        d.rectangle((tx - 2, ty - 1, tx + 6 * len(label) + 2, ty + 11), fill=(0, 0, 0))
        d.text((tx, ty), label, fill=color)


def _free_alloc(rom, size, cursor):
    a = cursor[0]
    while True:
        if a + size > FREE_END:
            raise SystemExit('out of free space for maps')
        bank_end = (a | 0xFFFF) + 1
        if (a & 0xFFFF) < 0x8000:
            a = (a & 0xFF0000) | 0x8000
            continue
        if a + size > bank_end:
            a = bank_end
            continue
        if not any(rom[a:a + size]):
            cursor[0] = a + size
            return a
        a = a + 1


def apply_maps(rom, mapdir, far=None):
    if not os.path.isdir(mapdir):
        return 0
    changes = 0
    far = far or __import__('fe4lib').FreeSpace()
    clean = bytes(rom)
    for ch in range(MAP_COUNT):
        path = os.path.join(mapdir, 'ch%02d_%s.csv' % (ch, MAP_NAMES[ch]))
        if not os.path.exists(path):
            continue
        words = read_csv(path)
        orig = load_map(clean, ch)
        if len(words) != len(orig) and words == load_map_v15(clean, ch):
            continue                                  # an old export of the unchanged map
        if len(words) != len(orig):
            raise SystemExit(f'{path}: map must keep the same size ({len(orig)} cells); edit values, '
                             'do not add or remove cells')
        if words == orig:
            continue
        data = fe4lz.compress(map_bytes(words))
        dest = far.alloc(len(data), upper_half=True)
        rom[dest:dest + len(data)] = data
        snes = dest                                   # banks $40-$7D map 1:1 to file 0x400000+
        h = header(clean, ch)['file']
        rom[h:h + 3] = bytes([snes & 0xFF, (snes >> 8) & 0xFF, snes >> 16])
        if fe4lz.decompress(bytes(rom), snes) != map_bytes(words):
            raise SystemExit(f'{path}: internal error, recompressed map does not round-trip')
        changes += 1
    return changes


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'export':
        import fe4lib as L
        _, r = L.load_rom(sys.argv[2])
        export(r, sys.argv[3])
    else:
        print(__doc__)
