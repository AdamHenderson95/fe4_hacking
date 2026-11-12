"""Spell effect graphics: the pictures the battle scene draws for magic, staves and weapon effects.

Each spell script ($97:8F7D, see fe4battle) loads its pictures with commands 01 (one record) and 14
(a record, or the next one for the other side).  Records are 10 bytes at $97:B081:
    src ptr24 (compressed, fe4lz)   dst ptr24 (always $7E:8B88, a buffer)   VRAM word address   byte count
The game decompresses src into the buffer and copies it to VRAM in pieces over the next frames.

What a record holds depends on where it goes; the layer set-up differs per spell, so the kit works it
out from the records themselves:
  * VRAM $4000-$5FFF: sprite tiles (4 bits a pixel).
  * a record whose words look like tilemap entries (few tile blocks, few palettes) is a tilemap,
    unless another tilemap of the same spell points at tiles inside it.
  * other records are background tiles: 4 bits a pixel when a 4-bit tilemap of the spell points into
    them (tiles counted from VRAM $0000), 2 bits a pixel when only a BG3 tilemap does (tiles counted
    from $3000 or $7000).

The battle colours change while a spell plays (palette cycling, fades, the terrain's colours), so the
editor shows and reads pictures by colour number with a fixed preview ramp.

Project files: spell_gfx/rNNN.png, one per changed record (tile sheet, 16 tiles a row).  The build
compresses each into free space and points the record at it; the original stays where it was.
"""
import os

import fe4gfx as G
import fe4lz
from dis65816 import snes_to_file

SCRIPTS = 0x978F7D
REAL_SPELLS = 77          # the script table has 105 entries; 77-104 point into other data
RECORDS = 0x97B081
RECORD_N = 136
BUFFER = 0x7E8B88
FOLDER = 'spell_gfx'

# preview ramps: colour 0 is see-through; the rest go dark -> bright through warm colours
RAMP4 = [(0, 0, 0)] + [
    (24, 16, 48), (48, 24, 88), (80, 32, 120), (120, 40, 136), (160, 48, 128), (200, 56, 104),
    (232, 80, 72), (248, 112, 48), (252, 148, 40), (252, 184, 48), (252, 212, 80), (252, 232, 128),
    (252, 244, 180), (252, 252, 220), (255, 255, 255)]
RAMP2 = [RAMP4[0], RAMP4[5], RAMP4[10], RAMP4[15]]   # what the preview shows for colours 1-3


def _w(rom, a):
    f = snes_to_file(a)
    return rom[f] | rom[f + 1] << 8


def record(rom, i):
    """(src, dst, vram, size) of record i."""
    f = snes_to_file(RECORDS + 10 * i)
    r = rom[f:f + 10]
    return (r[0] | r[1] << 8 | r[2] << 16, r[3] | r[4] << 8 | r[5] << 16, r[6] | r[7] << 8, r[8] | r[9] << 8)


def _valid(rom, i):
    src, dst, _, size = record(rom, i)
    return dst == BUFFER and src >= 0x800000 and size > 0


def script_records(rom, spell):
    """Records spell loads, in order (each once)."""
    a = SCRIPTS + _w(rom, SCRIPTS + 2 * spell)
    out = []
    for k in range(4000):
        x = _w(rom, a + 2 * k)
        if x == 0xFFFF:
            break
        if x >= 0xFF00:
            continue
        c, arg = (x >> 9) & 0x1F, x & 0x1FF
        if c == 0x01:
            out.append(arg)
        elif c == 0x14:
            out += [arg, arg + 1]
    return [r for r in dict.fromkeys(out) if r < RECORD_N and _valid(rom, r)]


_cache = {}
_lock = __import__('threading').Lock()


def _key(rom):
    return id(rom), bytes(rom[snes_to_file(RECORDS):snes_to_file(RECORDS) + 10 * RECORD_N])


def survey(rom):
    """{record: {'vram', 'size', 'src', 'kind' ('tiles4', 'tiles2', 'sprite', 'map'), 'spells': [...]}}
    and {spell: [records]}.  Decompresses everything once (a few seconds), then cached."""
    with _lock:
        return _survey(rom)


def _survey(rom):
    k = _key(rom)
    if k in _cache:
        return _cache[k]
    by_spell = {s: script_records(rom, s) for s in range(REAL_SPELLS)}
    recs = {}
    for s, rs in by_spell.items():
        for r in rs:
            if r not in recs:
                src, _, vram, size = record(rom, r)
                recs[r] = {'src': src, 'vram': vram, 'size': size, 'spells': [], 'data': fe4lz.decompress(rom, src)}
            recs[r]['spells'].append(s)
    for r, d in recs.items():
        d['words'] = [d['data'][k] | d['data'][k + 1] << 8 for k in range(0, len(d['data']) - 1, 2)]
        d['maplike'] = len({(x >> 10) & 7 for x in d['words']}) <= 4
    for r, d in recs.items():
        if 0x4000 <= d['vram'] < 0x6000:
            d['kind'] = 'sprite'
            continue
        maps = [m for s in d['spells'] for m in by_spell[s] if m != r and recs[m]['maplike']
                and not 0x4000 <= recs[m]['vram'] < 0x6000]

        def refs(lo, hi):
            return any(lo <= (x & 0x3FF) < hi for m in maps for x in recs[m]['words'] if x & 0x3FF)
        v, n = d['vram'], len(d['data'])
        ref4 = refs(v // 16, (v + n // 2 + 15) // 16)
        base2 = 0x7000 if v >= 0x7000 else 0x3000
        ref2 = 0x3000 <= v < 0x3800 or v >= 0x7000
        ref2 = ref2 and refs((v - base2) // 8, (v - base2 + n // 2 + 7) // 8)
        if d['maplike'] and (not ref4 or 0x3800 <= v < 0x4000 or v >= 0x6000):
            d['kind'] = 'map'
        elif ref4 and not (ref2 and v >= 0x7000):
            d['kind'] = 'tiles4'
        elif ref2 or v >= 0x7000:
            d['kind'] = 'tiles2'
        else:
            d['kind'] = 'tiles4'
    _cache.clear()
    _cache[k] = (recs, by_spell)
    return recs, by_spell


# ---- tiles <-> pictures ----

def _decode(data, bpp):
    """Pixel indices of every 8x8 tile: list of 64-lists."""
    tb = 8 * bpp
    out = []
    for t in range(len(data) // tb):
        b = data[t * tb:(t + 1) * tb]
        px = []
        for y in range(8):
            planes = [b[2 * y], b[2 * y + 1]] + ([b[16 + 2 * y], b[17 + 2 * y]] if bpp == 4 else [])
            for s in range(7, -1, -1):
                px.append(sum(((p >> s) & 1) << i for i, p in enumerate(planes)))
        out.append(px)
    return out


def _encode(tiles, bpp):
    out = bytearray()
    for px in tiles:
        b = bytearray(8 * bpp)
        for y in range(8):
            for x in range(8):
                v, s = px[y * 8 + x], 7 - x
                b[2 * y] |= (v & 1) << s
                b[2 * y + 1] |= (v >> 1 & 1) << s
                if bpp == 4:
                    b[16 + 2 * y] |= (v >> 2 & 1) << s
                    b[17 + 2 * y] |= (v >> 3 & 1) << s
        out += b
    return bytes(out)


def bpp_of(kind):
    return 2 if kind == 'tiles2' else 4


def sheet_size(n_bytes, bpp):
    tiles = n_bytes // (8 * bpp)
    return 128, max(1, (tiles + 15) // 16) * 8


def sheet_png(data, bpp, scale=1):
    """Indexed PNG of a tile record, 16 tiles a row, in the preview ramp."""
    tiles = _decode(data, bpp)
    w, h = sheet_size(len(data), bpp)
    idx = bytearray(w * h)
    for t, px in enumerate(tiles):
        ox, oy = (t % 16) * 8, (t // 16) * 8
        for i, v in enumerate(px):
            idx[(oy + i // 8) * w + ox + i % 8] = v
    return G.indexed_png(w, h, idx, RAMP2 + [(0, 0, 0)] * 12 if bpp == 2 else RAMP4, scale)


def sheet_from_png(png, n_bytes, bpp):
    """Tile bytes from an edited sheet: each pixel takes the nearest preview colour (see-through
    pixels are colour 0)."""
    w, h, px = G.read_png(png)
    ew, eh = sheet_size(n_bytes, bpp)
    if (w, h) != (ew, eh):
        raise ValueError(f'This picture is {w}x{h}; this spell graphic is {ew}x{eh} (16 tiles a row). '
                         'Download it, draw over the download and keep its size.')
    ramp = RAMP2 if bpp == 2 else RAMP4
    memo = {}

    def near(p):
        if p[3] < 128:
            return 0
        k = p[:3]
        if k not in memo:
            memo[k] = min(range(1, len(ramp)), key=lambda i: sum((a - b) ** 2 for a, b in zip(ramp[i], k)))
        return memo[k]
    tiles = []
    for t in range(n_bytes // (8 * bpp)):
        ox, oy = (t % 16) * 8, (t // 16) * 8
        tiles.append([near(px[(oy + y) * w + ox + x]) for y in range(8) for x in range(8)])
    out = _encode(tiles, bpp)
    return out + bytes(n_bytes - len(out))


# ---- the composed look of a spell ----

def preview_png(rom, spell, overrides=None, scale=1):
    """The spell's backgrounds as the game lays them out (all its tilemaps side by side, one 256x256
    screen per 2 KB of map), in the preview ramp.  overrides = {record: tile bytes}."""
    recs, by_spell = survey(rom)
    overrides = overrides or {}
    vram = bytearray(0x10000)
    for r in by_spell.get(spell, []):
        d = recs[r]
        data = overrides.get(r, d['data'])
        at = 2 * d['vram']
        vram[at:at + len(data)] = data[:0x10000 - at]
    maps = [r for r in by_spell.get(spell, []) if recs[r]['kind'] == 'map']
    if not maps:
        return None
    t2 = [r for r in by_spell[spell] if recs[r]['kind'] == 'tiles2']
    base2 = 0x7000 if any(recs[r]['vram'] >= 0x7000 for r in t2) else 0x3000
    screens = []
    for m in maps:
        words = recs[m]['words']
        bg3 = recs[m]['vram'] >= 0x7000 or (t2 and not any(
            recs[r]['kind'] == 'tiles4' and recs[r]['vram'] // 16 <= (x & 0x3FF) < (recs[r]['vram'] + len(recs[r]['data']) // 2) // 16
            for x in words[:64] for r in by_spell[spell]))
        for s in range(max(1, len(words) // 1024)):
            screens.append((words[s * 1024:(s + 1) * 1024], bg3))
    W, H = 256 * len(screens), 256
    idx = bytearray(W * H)
    cache = {}
    for n, (words, bg3) in enumerate(screens):
        bpp = 2 if bg3 else 4
        for i, x in enumerate(words):
            t = x & 0x3FF
            key = (t, bpp)
            if key not in cache:
                at = 2 * (base2 + 8 * t) if bpp == 2 else 32 * t
                cache[key] = _decode(bytes(vram[at:at + 8 * bpp]).ljust(8 * bpp, b'\0'), bpp)[0]
            px = cache[key]
            hf, vf = x >> 14 & 1, x >> 15 & 1
            ox, oy = n * 256 + (i % 32) * 8, (i // 32) * 8
            for k, v in enumerate(px):
                if not v:
                    continue
                xx, yy = k % 8, k // 8
                if hf:
                    xx = 7 - xx
                if vf:
                    yy = 7 - yy
                idx[(oy + yy) * W + ox + xx] = v * 5 if bpp == 2 and v < 4 else v
    return G.indexed_png(W, H, idx, RAMP4, scale)


# ---- project ----

def path_of(proj, r):
    return os.path.join(proj, FOLDER, f'r{r:03d}.png')


def edited(proj):
    d = os.path.join(proj, FOLDER)
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.startswith('r') and f.endswith('.png') and f[1:-4].isdigit():
                out[int(f[1:-4])] = os.path.join(d, f)
    return out


def apply(rom, proj, far):
    """spell_gfx/rNNN.png -> compressed tiles in free space, record NNN pointed at them."""
    files = edited(proj)
    if not files:
        return 0
    recs, _ = survey(rom)
    n = 0
    for r, path in files.items():
        if r not in recs or recs[r]['kind'] == 'map':
            raise SystemExit(f'{FOLDER}/r{r:03d}.png: record {r} is not a spell picture the kit can edit')
        d = recs[r]
        try:
            data = sheet_from_png(open(path, 'rb').read(), len(d['data']), bpp_of(d['kind']))
        except ValueError as e:
            raise SystemExit(f'{FOLDER}/r{r:03d}.png: {e}')
        if data == d['data']:
            continue
        comp = fe4lz.compress(data)
        at = far.alloc(len(comp) + 1, upper_half=True)
        fo = snes_to_file(at)
        rom[fo:fo + len(comp)] = comp
        f = snes_to_file(RECORDS + 10 * r)
        rom[f:f + 3] = at.to_bytes(3, 'little')
        n += 1
    if n:
        _cache.clear()
        print(f'spell graphics: {n} picture(s) redrawn')
    return n
