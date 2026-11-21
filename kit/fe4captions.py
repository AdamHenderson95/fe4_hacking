"""The opening's captions: the line of words under each story picture (editor 1.7).

Found by tracing the opening from power-on.  The opening's graphics script table at $97:F1xx-$97:F4xx
(11-byte records: [source 24][destination 24][VRAM word][size][flag]) has one record per caption with
destination $7E:8B88 and VRAM $7800; the source is a compressed picture ($80:AA02 format) that unpacks to
2,048 bytes: 64 4bpp tiles, a 256 x 16 strip.  Tile t sits at x = (t % 16) * 8 + (t // 32) * 128,
y = (t // 16 % 2) * 8 (the game's own BG1 map, rows 25-26 of $7C00, places them; it isn't touched).
Colours: palette 0, a ramp from black (0) to light grey (15); the opening fades it in and out.
Where it shows: the BG1 map turns the strip by 64 pixels, and each caption has its own horizontal scroll, a
byte in the table at $99:FFE7 (entry k for caption k; the game's own captions are not centred in their
strips, the scroll centres them).  Screen x shows strip x (scroll + 64) mod 256, so a strip drawn centred
needs scroll 192.

Project Naga drew all 13 captions:  0 "In an age beyond living memory..." .. 12 "Our nightmare has faded
into legend...".

A new caption is drawn by the editor (the browser renders the words) and stored as 256 x 16 colour numbers.
The build packs it into tiles, compresses it into free space and points the caption's record at it.

Project file: story_captions.json  {"<caption 0-12>": {"text": "...", "px": "<4096 hex digits>"}}
"""
import json
import os

import fe4lz
from dis65816 import snes_to_file as _fo

FILE = 'story_captions.json'
W, H = 256, 16
TABLE = (0x97F100, 0x97F500)
DEST = bytes([0x88, 0x8B, 0x7E, 0x00, 0x78])
SCROLLS = 0x99FFE7                     # a byte per caption
CENTRED = 192
# palette 0 while a caption shows (8-bit greys), for previews
GREYS = [0, 0, 8, 16, 40, 48, 56, 64, 72, 80, 88, 104, 120, 144, 168, 200]


def records(rom):
    """File offsets of the caption records, in the order the opening shows them."""
    a, z = _fo(TABLE[0]), _fo(TABLE[1])
    return [o for o in range(a, z - 10) if bytes(rom[o + 3:o + 8]) == DEST]


def known(rom):
    return len(records(rom)) == 13


def source(rom, o):
    return rom[o] | rom[o + 1] << 8 | rom[o + 2] << 16


def _xy(t):
    return (t % 16) * 8 + (t // 32) * 128, (t // 16 % 2) * 8


def picture(tiles):
    """2,048 bytes of tiles -> 4,096 colour numbers (row by row)."""
    px = bytearray(W * H)
    for t in range(64):
        x0, y0 = _xy(t)
        d = tiles[t * 32:t * 32 + 32]
        for y in range(8):
            p0, p1, p2, p3 = d[2 * y], d[2 * y + 1], d[16 + 2 * y], d[16 + 2 * y + 1]
            for x in range(8):
                b = 7 - x
                px[(y0 + y) * W + x0 + x] = (p0 >> b & 1) | (p1 >> b & 1) << 1 | (p2 >> b & 1) << 2 | (p3 >> b & 1) << 3
    return bytes(px)


def tiles_of(px):
    """4,096 colour numbers -> 2,048 bytes of tiles."""
    out = bytearray(2048)
    for t in range(64):
        x0, y0 = _xy(t)
        for y in range(8):
            p = [0, 0, 0, 0]
            for x in range(8):
                c = px[(y0 + y) * W + x0 + x]
                for k in range(4):
                    p[k] |= (c >> k & 1) << (7 - x)
            out[t * 32 + 2 * y], out[t * 32 + 2 * y + 1] = p[0], p[1]
            out[t * 32 + 16 + 2 * y], out[t * 32 + 16 + 2 * y + 1] = p[2], p[3]
    return bytes(out)


def parse_px(s):
    s = str(s or '')
    if len(s) != W * H or any(c not in '0123456789abcdefABCDEF' for c in s):
        raise ValueError('The caption picture is not 256 x 16 colour numbers.')
    return bytes(int(c, 16) for c in s)


def read(rom):
    """The game's captions as pictures (colour numbers)."""
    return [picture(fe4lz.decompress(rom, source(rom, o))[:2048]) for o in records(rom)]


def load(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return {}
    return parse(open(p, encoding='utf-8').read())


def parse(blob):
    d = json.loads(blob or '{}')
    return {int(k): v for k, v in d.items()}


def dump(data):
    return (json.dumps({str(k): data[k] for k in sorted(data)}, indent=1) + '\n').encode('utf-8') if data else None


def apply(rom, proj, far):
    data = load(proj)
    if not data:
        return 0
    recs = records(rom)
    if len(recs) != 13:
        raise SystemExit('story captions: the opening is not the one the editor knows; captions left as they are')
    n = 0
    for i, v in sorted(data.items()):
        if not 0 <= i < len(recs):
            continue
        blob = fe4lz.compress(tiles_of(parse_px(v['px'])))
        # upper half: $70-$7D:6000-7FFF reads as save RAM, and the decompression queue takes a $xx:0000
        # source for "no job" (as for chapter titles)
        snes = far.alloc(len(blob) + 1, upper_half=True)
        rom[_fo(snes):_fo(snes) + len(blob)] = blob
        o = recs[i]
        rom[o:o + 3] = bytes([snes & 0xFF, (snes >> 8) & 0xFF, snes >> 16])
        rom[_fo(SCROLLS) + i] = CENTRED
        n += 1
    return n
