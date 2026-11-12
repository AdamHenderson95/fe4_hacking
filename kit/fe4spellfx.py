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

SCRIPTS = 0x978F7D       # the game's tables; a project with new effects moves them (see table())
RECORDS = 0x97B081
RECORD_N = 136           # picture records in the game's table
MAX_RECORDS = 512        # script arguments are 9 bits
# where the code keeps each table's bank (LDA #$xx00) and address (LDA/ADC #$xxxx), all in bank $96
OPS = {'scripts': (0x96A4D4, (0x96A4DD, 0x96A4EC)), 'pictures': (0x96B950, (0x96B961,)),
       'fx': (0x96DB6D, (0x96DB78, 0x96DB83)), 'sets': (0x96BB72, (0x96BB7D, 0x96BB88)),
       'motions': (0x96DECA, (0x96DED4,))}
MOTION_LONG = 0x96DECF     # LDA $97BEAC,X: the motion table's address as a long operand too
# background motion records ($0D): layer, type, data; lengths of the types the kit edits
MOTION_LEN = {0x17: 6, 0x1A: 6, 0x1B: 3, 0x18: 3, 0x16: 5, 0x01: 2, 0x05: 2}
MOTION_NAMES = {0x01: 'Place at the attacker', 0x05: 'Place at the target', 0x17: 'Move', 0x1A: 'Move',
                0x1B: 'Fly to the target', 0x18: 'Fly to the target', 0x16: 'Follow a motion path'}
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


def table(rom, name):
    """Where a spell table is now (read from the code that uses it)."""
    bank_op, base_ops = OPS[name]
    f, g = snes_to_file(bank_op), snes_to_file(base_ops[0])
    return rom[f + 2] << 16 | rom[g + 1] | rom[g + 2] << 8


def _offset_count(rom, base):
    """Entries of a word-offset table that is followed by its data."""
    m, i = _w(rom, base), 0
    while 2 * i < m:
        m = min(m, _w(rom, base + 2 * i))
        i += 1
    return i


def spell_count(rom):
    return _offset_count(rom, table(rom, 'scripts'))


def record(rom, i):
    """(src, dst, vram, size) of record i."""
    f = snes_to_file(table(rom, 'pictures') + 10 * i)
    r = rom[f:f + 10]
    return (r[0] | r[1] << 8 | r[2] << 16, r[3] | r[4] << 8 | r[5] << 16, r[6] | r[7] << 8, r[8] | r[9] << 8)


def is_rom(a):
    b = a >> 16
    return 0x40 <= b <= 0x7D or b >= 0x80


def _valid(rom, i):
    src, dst, _, size = record(rom, i)
    return dst == BUFFER and is_rom(src) and size > 0


def script_records(rom, spell):
    """Records spell loads, in order (each once)."""
    out = []
    for x in script_words(rom, spell):
        if x >= 0xFF00:
            continue
        c, arg = (x >> 9) & 0x1F, x & 0x1FF
        if c == 0x01:
            out.append(arg)
        elif c == 0x14:
            out += [arg, arg + 1]
    return [r for r in dict.fromkeys(out) if r < MAX_RECORDS and _valid(rom, r)]


_cache = {}
_unpacked = {}


def _decompressed(rom, src):
    f = snes_to_file(src)
    k = (src, bytes(rom[f:f + 64]))
    if k not in _unpacked:
        _unpacked[k] = fe4lz.decompress(rom, src)
    return _unpacked[k]


_lock = __import__('threading').Lock()


def _key(rom):
    t = table(rom, 'pictures')
    return (id(rom), t, table(rom, 'scripts'), table(rom, 'fx'), table(rom, 'sets'),
            bytes(rom[snes_to_file(t):snes_to_file(t) + 10 * RECORD_N]))


def survey(rom):
    """{record: {'vram', 'size', 'src', 'kind' ('tiles4', 'tiles2', 'sprite', 'map'), 'spells': [...]}}
    and {spell: [records]}.  Decompresses everything once (a few seconds), then cached."""
    with _lock:
        return _survey(rom)


def _survey(rom):
    k = _key(rom)
    if k in _cache:
        return _cache[k]
    by_spell = {s: script_records(rom, s) for s in range(spell_count(rom))}
    recs = {}
    for s, rs in by_spell.items():
        for r in rs:
            if r not in recs:
                src, _, vram, size = record(rom, r)
                recs[r] = {'src': src, 'vram': vram, 'size': size, 'spells': [], 'data': _decompressed(rom, src)}
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



# ---- colours ----
# Spells set colours two ways, both from their scripts:
#   command $0E (arg = record at $97:AFE5): start colour, count, ptr24 -> plain colours (bank $E0),
#     copied into the palette buffer ($7E:0100) once.
#   command $0B (arg = record at $97:A9A8): an effect slot (10 bytes at $7F:FD9A): slot, type, start,
#     count, then by type: 0/1/2/12 ptr24 to a colour stream (bank $9B), 7 delay + ptr24 to colours to
#     fade towards, 10 ptr24 to colours to copy; 3-6 rotate, 8/9 clear/fill, 11 stop.
# Streams ($96:D6F7, D774, D808, DA34): a byte $FF ends, $FE starts over, $80+n sets the delay to n frames
# for this step; otherwise a colour, high byte first.  Type 0 takes `count` colours a step (a whole
# frame), types 1, 2 and 12 one colour a step that pushes the others along (1 and 12 down, 2 up).
CYCLES = (1, 2, 12)


def script_words(rom, spell):
    t = table(rom, 'scripts')
    a = t + _w(rom, t + 2 * spell)
    out = []
    for k in range(4000):
        x = _w(rom, a + 2 * k)
        if x == 0xFFFF:
            break
        out.append(x)
    return out


def _p24(rom, a):
    f = snes_to_file(a)
    return rom[f] | rom[f + 1] << 8 | rom[f + 2] << 16


def colour_uses(rom, spell):
    """Colour sources a spell's script uses, in order: dicts with kind ('set', 'frames', 'cycle',
    'fade', 'copy'), start (0-255), n, addr (ROM only), ptr_at (where the record keeps the pointer)."""
    out = []
    for x in script_words(rom, spell):
        if x >= 0xFF00:
            continue
        c, arg = (x >> 9) & 0x1F, x & 0x1FF
        if c == 0x0E:
            ra = table(rom, 'sets') + _w(rom, table(rom, 'sets') + 2 * arg)
            f = snes_to_file(ra)
            if f is None:
                continue
            out.append({'kind': 'set', 'start': rom[f], 'n': rom[f + 1], 'addr': _p24(rom, ra + 2), 'ptr_at': ra + 2,
                        'cmd': (0x0E, arg)})
        elif c == 0x0B:
            ra = table(rom, 'fx') + _w(rom, table(rom, 'fx') + 2 * arg)
            f = snes_to_file(ra)
            if f is None:
                continue
            t, start, n = rom[f + 1] & 0x3F, rom[f + 2], rom[f + 3]
            at = {0: 4, 1: 4, 2: 4, 12: 4, 10: 4, 7: 5}.get(t)
            if at is None:
                continue
            kind = 'frames' if t == 0 else 'cycle' if t in CYCLES else 'fade' if t == 7 else 'copy'
            out.append({'kind': kind, 'type': t, 'start': start, 'n': n, 'addr': _p24(rom, ra + at), 'ptr_at': ra + at,
                        'cmd': (0x0B, arg)})
    return [u for u in out if is_rom(u['addr']) and u['n']]


def _parse_stream(rom, addr, per):
    """(colours, tokens) of a colour stream; tokens: ('d', byte) | ('c',) | ('e', byte)."""
    f = snes_to_file(addr)
    cols, toks = [], []
    for _ in range(4096):
        b = rom[f]
        if b in (0xFE, 0xFF):
            toks.append(('e', b))
            break
        if b & 0x80:
            toks.append(('d', b))
            f += 1
        for _ in range(per):
            cols.append(rom[f] << 8 | rom[f + 1])
            toks.append(('c',))
            f += 2
    return cols, toks


def read_source(rom, use):
    """(colours, tokens or None) of a use's data in the ROM."""
    if use['kind'] in ('frames', 'cycle'):
        return _parse_stream(rom, use['addr'], use['n'] if use['kind'] == 'frames' else 1)
    f = snes_to_file(use['addr'])
    return [rom[f + 2 * i] | rom[f + 2 * i + 1] << 8 for i in range(use['n'])], None


def write_source(cols, toks):
    """Bytes for colours laid out like the original (toks None: plain little-endian colours)."""
    if toks is None:
        return b''.join((c & 0xFFFF).to_bytes(2, 'little') for c in cols)
    out, i = bytearray(), 0
    for t in toks:
        if t[0] == 'c':
            out += (cols[i] & 0x7FFF).to_bytes(2, 'big')
            i += 1
        else:
            out.append(t[1])
    return bytes(out)


_colour_cache = {}


def colour_sets(rom, overrides=None):
    """{spell: [use + 'colours', 'game' (the ROM's colours), 'spells' (all spells using addr)]}."""
    import copy
    k = _key(rom)
    if k not in _colour_cache:
        _colour_cache.clear()
        _colour_cache[k] = _colour_sets(rom)
    out = copy.deepcopy(_colour_cache[k])
    for lst in out.values():
        for u in lst:
            if u['addr'] in (overrides or {}):
                u['colours'] = list(overrides[u['addr']])
    return out


def _colour_sets(rom, overrides=None):
    overrides = overrides or {}
    by_addr = {}
    out = {}
    for s in range(spell_count(rom)):
        lst = []
        for u in colour_uses(rom, s):
            if any(v['addr'] == u['addr'] for v in lst):
                continue
            cols, toks = read_source(rom, u)
            u.update(game=cols, colours=list(overrides.get(u['addr'], cols)), tokens=toks)
            by_addr.setdefault(u['addr'], set()).add(s)
            lst.append(u)
        out[s] = lst
    for lst in out.values():
        for u in lst:
            u['spells'] = sorted(by_addr[u['addr']])
    return out


def cgram(rom, spell, overrides=None):
    """256 colours (or None) the spell's own colour sources give, in script order (fades only fill
    colours nothing set before); a guide to how its pictures look, not a frame of the battle."""
    overrides = overrides or {}
    cg = [None] * 256
    for u in colour_uses(rom, spell):
        cols = overrides.get(u['addr']) or read_source(rom, u)[0]
        if u['kind'] in ('set', 'copy', 'frames', 'cycle'):
            for i in range(min(u['n'], len(cols))):
                if u['start'] + i < 256:
                    cg[u['start'] + i] = cols[i]
        elif u['kind'] == 'fade':
            for i in range(min(u['n'], len(cols))):
                if u['start'] + i < 256 and cg[u['start'] + i] is None:
                    cg[u['start'] + i] = cols[i]
    return cg


def rgb(c):
    return ((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31)


def snes(r, g, b):
    return (r * 31 + 127) // 255 | ((g * 31 + 127) // 255) << 5 | ((b * 31 + 127) // 255) << 10


def colours_path(proj):
    return os.path.join(proj, FOLDER, 'colors.json')


def read_colours(blob):
    """{key: [colour words]} from colors.json bytes; keys are 'ADDRESS' (the game's colours) or
    'sID:ADDRESS' (new effect ID's copy of them)."""
    import json
    if not blob:
        return {}
    try:
        d = json.loads(blob)
        return {str(k).upper().replace('S', 's'): [int(c, 16) & 0xFFFF for c in v] for k, v in d.items()}
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f'{FOLDER}/colors.json is not readable')


def dump_colours(d):
    import json
    return json.dumps({k: [f'{c:04x}' for c in v] for k, v in sorted(d.items())}, indent=1).encode()


def apply_colours(rom, proj, far, fxmap=None):
    """spell_gfx/colors.json -> each changed colour source copied to free space with the new colours;
    every spell record that pointed at the old one points at the copy."""
    p = colours_path(proj)
    tp = os.path.join(proj, FOLDER, TIMING)
    if not os.path.exists(p) and not os.path.exists(tp):
        return 0
    try:
        want = colours_by_address(read_colours(open(p, 'rb').read()), fxmap) if os.path.exists(p) else {}
        timing = colours_by_address(read_json(open(tp, 'rb').read(), TIMING), fxmap) if os.path.exists(tp) else {}
    except ValueError as e:
        raise SystemExit(str(e))
    uses = {}
    for s in range(spell_count(rom)):
        for u in colour_uses(rom, s):
            uses.setdefault(u['addr'], []).append(u)
    n = 0
    for addr in sorted(set(want) | set(timing)):
        if addr not in uses:
            raise SystemExit(f'{FOLDER}: no spell uses colours at {addr:06X}')
        u = uses[addr][0]
        game, toks = read_source(rom, u)
        cols = want.get(addr, game)
        if len(cols) != len(game):
            raise SystemExit(f'{FOLDER}/colors.json: {addr:06X} has {len(game)} colours, not {len(cols)}')
        new_toks = toks
        if addr in timing and toks is not None:
            try:
                frames = int(timing[addr])
            except (TypeError, ValueError):
                raise SystemExit(f'{FOLDER}/{TIMING}: {addr:06X} needs a number of frames')
            if not 1 <= frames <= 128:
                raise SystemExit(f'{FOLDER}/{TIMING}: frames per step are 1-128')
            new_toks = with_delay(toks, frames)
        data = write_source(cols, new_toks)
        if data == write_source(game, toks):
            continue
        at = far.alloc(len(data), upper_half=True)
        fo = snes_to_file(at)
        rom[fo:fo + len(data)] = data
        for v in uses[addr]:
            f = snes_to_file(v['ptr_at'])
            rom[f:f + 3] = at.to_bytes(3, 'little')
        n += 1
    if n:
        print(f'spell colours: {n} colour set(s) changed')
    return n


# ---- new effects ----
# spell_gfx/effects.json: [{"id": 77, "from": 2, "name": "Blue fire"}, ...].  A new effect is a copy of
# another effect's script with its own copies of every picture record and colour set it uses, so its
# pictures and colours can change without touching the original.  Its files: spell_gfx/sID_rNNN.png
# (picture NNN of the original) and colors.json keys "sID:ADDRESS" (the original's colour address).
# The build moves the four tables (scripts, pictures, colour sets $0B, palette loads $0E) to free
# space with room for the copies and points the code at them (OPS).
EFFECTS = 'effects.json'
FX_LEN = {0: 3, 1: 3, 2: 3, 12: 3, 10: 3, 7: 4, 3: 1, 4: 1, 5: 1, 6: 1, 8: 0, 9: 0, 11: 0}


def read_effects(blob):
    import json
    if not blob:
        return []
    try:
        d = json.loads(blob)
        out = [{'id': int(e['id']), 'from': int(e['from']), 'name': str(e.get('name', ''))[:40],
                'deleted': bool(e.get('deleted'))} for e in d]
    except (ValueError, KeyError, TypeError):
        raise ValueError(f'{FOLDER}/{EFFECTS} is not readable')
    return sorted(out, key=lambda e: e['id'])


def dump_effects(effects):
    import json
    return json.dumps([{k: v for k, v in e.items() if v or k in ('id', 'from', 'name')} for e in effects],
                      indent=1).encode()


def _fx_len(rom, a):
    f = snes_to_file(a)
    return 4 + FX_LEN.get(rom[f + 1] & 0x3F, 0)


def _colour_data_len(rom, kind, addr, n):
    if kind in ('frames', 'cycle'):
        _, toks = _parse_stream(rom, addr, n if kind == 'frames' else 1)
        return sum(2 if t[0] == 'c' else 1 for t in toks)
    return 2 * n


def apply_effects(rom, effects, far, steps=None, motions=None):
    """Write the new effects (and changed steps, {spell: words}) into rom; the tables move to free space.
    Returns the map of what was copied: {'pictures': {new record: (effect id, original record)},
    'colours': {new address: (effect id, original address)}, 'fx'/'sets': {new record: (effect id,
    original record)}}, or None when there is nothing to do.  A new effect's steps are given in terms of
    the original's records."""
    effects = [e for e in effects]
    steps = steps or {}
    if not effects and not steps and not motions:
        return None
    n0 = spell_count(rom)
    ids = [e['id'] for e in effects]
    if ids != list(range(n0, n0 + len(ids))):
        raise SystemExit(f'{FOLDER}/{EFFECTS}: new effects are numbered {n0} and up, one after another')
    if n0 + len(ids) > 255:
        raise SystemExit('at most 255 effects')
    t_s, t_p, t_fx, t_set = (table(rom, k) for k in ('scripts', 'pictures', 'fx', 'sets'))
    n_fx, n_set = _offset_count(rom, t_fx), _offset_count(rom, t_set)
    pics = [bytes(rom[snes_to_file(t_p) + 10 * i:snes_to_file(t_p) + 10 * i + 10]) for i in range(RECORD_N)]
    def rec_bytes(a, n):
        f = snes_to_file(a)
        return bytes(rom[f:f + n])
    fx = [rec_bytes(t_fx + _w(rom, t_fx + 2 * i), _fx_len(rom, t_fx + _w(rom, t_fx + 2 * i))) for i in range(n_fx)]
    t_mo = table(rom, 'motions')
    n_mo = _offset_count(rom, t_mo)
    mot = [motion_bytes(rom, i) for i in range(n_mo)]
    for k, v in (motions or {}).items():
        if isinstance(k, int) and k < n_mo:
            mot[k] = bytes(v)
    sets = [rec_bytes(t_set + _w(rom, t_set + 2 * i), 5) for i in range(n_set)]
    scripts = [script_words(rom, k) for k in range(n0)]
    game_scripts = list(scripts)
    for k, ws in steps.items():
        if k < n0:
            scripts[k] = list(ws)
    out = {'pictures': {}, 'colours': {}, 'fx': {}, 'sets': {}, 'motions': {}}

    def copy_colours(data, kind, n, eid, at):
        """Copy the colours a record points at (at = pointer offset in data) to free space."""
        ptr = data[at] | data[at + 1] << 8 | data[at + 2] << 16
        if not is_rom(ptr):
            return data
        ln = _colour_data_len(rom, kind, ptr, n)
        new = far.alloc(ln, upper_half=True)
        fo, fs = snes_to_file(new), snes_to_file(ptr)
        rom[fo:fo + ln] = rom[fs:fs + ln]
        out['colours'][new] = (eid, ptr)
        return data[:at] + new.to_bytes(3, 'little') + data[at + 3:]

    for e in effects:
        if e['deleted']:
            scripts.append([])
            continue
        if not 0 <= e['from'] < n0:
            raise SystemExit(f'{FOLDER}/{EFFECTS}: effect {e["id"]} copies effect {e["from"]}, which isn\'t one of the game\'s')
        pmap, fmap, smap, mmap = {}, {}, {}, {}
        words = []
        for x in steps.get(e['id'], game_scripts[e['from']]):
            c, arg = (x >> 9) & 0x1F, x & 0x1FF
            if x < 0xFF00 and c == 0x01 and arg < RECORD_N:
                if arg not in pmap:
                    pmap[arg] = len(pics)
                    pics.append(pics[arg])
                    out['pictures'][pmap[arg]] = (e['id'], arg)
                x = (x & ~0x1FF) | pmap[arg]
            elif x < 0xFF00 and c == 0x14 and arg + 1 < RECORD_N:
                key = ('pair', arg)
                if key not in pmap:
                    pmap[key] = len(pics)
                    for k in (arg, arg + 1):
                        out['pictures'][len(pics)] = (e['id'], k)
                        pics.append(pics[k])
                x = (x & ~0x1FF) | pmap[key]
            elif x < 0xFF00 and c == 0x0B and arg < n_fx:
                if arg not in fmap:
                    d = fx[arg]
                    t = d[1] & 0x3F
                    kind = 'frames' if t == 0 else 'cycle' if t in CYCLES else 'fade' if t == 7 else 'copy' if t == 10 else None
                    if kind:
                        d = copy_colours(d, kind, d[3], e['id'], 5 if t == 7 else 4)
                    fmap[arg] = len(fx)
                    out['fx'][len(fx)] = (e['id'], arg)
                    fx.append(d)
                x = (x & ~0x1FF) | fmap[arg]
            elif x < 0xFF00 and c == 0x0D and arg < n_mo:
                if arg not in mmap:
                    mmap[arg] = len(mot)
                    out['motions'][len(mot)] = (e['id'], arg)
                    mot.append(bytes((motions or {}).get((e['id'], arg), mot[arg])))
                x = (x & ~0x1FF) | mmap[arg]
            elif x < 0xFF00 and c == 0x0E and arg < n_set:
                if arg not in smap:
                    smap[arg] = len(sets)
                    out['sets'][len(sets)] = (e['id'], arg)
                    sets.append(copy_colours(sets[arg], 'set', sets[arg][1], e['id'], 2))
                x = (x & ~0x1FF) | smap[arg]
            words.append(x)
        scripts.append(words)
    if max(len(pics), len(fx), len(sets), len(mot)) > MAX_RECORDS:
        raise SystemExit('too many new effects: the pictures or colour sets they copy don\'t fit (512 at most)')

    def offset_block(items):
        head = 2 * len(items)
        body, offs = bytearray(), []
        for it in items:
            offs.append(head + len(body))
            body += it
        return b''.join(o.to_bytes(2, 'little') for o in offs) + bytes(body)

    def put(name, data):
        if len(data) > 0x8000:
            raise SystemExit(f'the spell {name} table is too big')
        a = far.alloc(len(data), upper_half=True)
        fo = snes_to_file(a)
        rom[fo:fo + len(data)] = data
        bank_op, base_ops = OPS[name]
        rom[snes_to_file(bank_op) + 2] = a >> 16
        for op in base_ops:
            g = snes_to_file(op)
            rom[g + 1:g + 3] = (a & 0xFFFF).to_bytes(2, 'little')
        if name == 'motions':
            g = snes_to_file(MOTION_LONG)
            rom[g + 1:g + 4] = a.to_bytes(3, 'little')

    put('scripts', offset_block([b''.join(w.to_bytes(2, 'little') for w in ws) + b'\xff\xff' for ws in scripts]))
    put('pictures', b''.join(pics))
    put('fx', offset_block(fx))
    put('sets', offset_block(sets))
    put('motions', offset_block(mot))
    _cache.clear()
    _colour_cache.clear()
    return out


def effect_file(eid, orig):
    return f'{FOLDER}/s{eid}_r{orig:03d}.png'


def picture_file(r, fxmap):
    """Project file for picture record r (fxmap: apply_effects' map, or None)."""
    if fxmap and r in fxmap['pictures']:
        return effect_file(*fxmap['pictures'][r])
    return f'{FOLDER}/r{r:03d}.png'


def colour_key(addr, fxmap):
    """colors.json key for a colour address of the (built) ROM."""
    if fxmap and addr in fxmap['colours']:
        eid, orig = fxmap['colours'][addr]
        return f's{eid}:{orig:06X}'
    return f'{addr:06X}'


def colours_by_address(keyed, fxmap):
    """colors.json ({key: colours}) -> {address in the built ROM: colours}."""
    inv = {colour_key(a, fxmap): a for a in (fxmap or {}).get('colours', {})}
    out = {}
    for k, v in keyed.items():
        if k in inv:
            out[inv[k]] = v
        elif ':' not in k:
            out[int(k, 16)] = v
    return out


# ---- steps ----
STEPS = 'steps.json'          # {spell: ["083b", ...]}: changed scripts (new effects: the original's records)
TIMING = 'timing.json'        # {colour key: frames per step}
MOTIONS = 'motions.json'      # {motion record or 'sID:record': hex bytes}
COMMANDS = {
    0x00: ('sprite', 'Sprite effect'), 0x01: ('picture', 'Load picture'), 0x02: ('layers', 'Layer set-up'),
    0x03: ('screen', 'Screen colours'), 0x04: ('scene', 'Scene set-up'), 0x06: ('data', 'Load sprite data'),
    0x07: ('data', 'Load sprite data'), 0x08: ('screen', 'Screen routine'), 0x0A: ('pause', 'Pause'),
    0x0B: ('colours', 'Colour effect'), 0x0D: ('motion', 'Background motion'), 0x0E: ('colours', 'Set colours'),
    0x14: ('picture', 'Load picture for this side'), 0x15: ('sound', 'Sound'),
    0x16: ('sound', 'Sound at the attacker'), 0x17: ('sound', 'Sound at the target'), 0x18: ('pause', 'Pause'),
}
CONTROLS = {0xFFFE: 'Wait for the steps above to finish', 0xFFFD: 'Signal the caster\'s animation',
            0xFFFC: 'Signal the target\'s animation', 0xFFFB: 'Fighter step A', 0xFFFA: 'Target reacts',
            0xFFF9: 'Hit: damage or dodge', 0xFFF8: 'Fighter step B'}
SOUNDS = 0x98AD04            # word per sound step value: the game's sound number


def describe(x):
    """(kind, label, value) of one script word."""
    if x >= 0xFF00:
        return 'control', CONTROLS.get(x, f'Control {x:04X}'), None
    c, arg = (x >> 9) & 0x1F, x & 0x1FF
    kind, label = COMMANDS.get(c, ('other', f'Game step {c}'))
    return kind, label, arg


def check_steps(words):
    """Raise ValueError unless every word is a step the game knows."""
    if len(words) > 2000:
        raise ValueError('That is too many steps.')
    for x in words:
        if x == 0xFFFF:
            raise ValueError('The end of the steps is added for you.')
        if x >= 0xFF00 and x not in CONTROLS:
            raise ValueError(f'{x:04X} is not a step the game knows.')
        if x < 0xFF00 and (x >> 9) & 0x1F >= 25:
            raise ValueError(f'{x:04X} is not a step the game knows.')


def read_json(blob, what):
    import json
    if not blob:
        return {}
    try:
        return json.loads(blob)
    except ValueError:
        raise ValueError(f'{FOLDER}/{what} is not readable')


def read_steps(blob):
    d = read_json(blob, STEPS)
    try:
        return {int(k): [int(w, 16) for w in v] for k, v in d.items()}
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f'{FOLDER}/{STEPS} is not readable')


def dump_steps(d):
    import json
    return json.dumps({str(k): [f'{w:04x}' for w in v] for k, v in sorted(d.items())}, indent=1).encode()


def to_source_terms(words, eid, fxmap):
    """A new effect's words (records as built) -> words naming the original's records."""
    inv = {'p': {k: o for k, (e, o) in (fxmap or {}).get('pictures', {}).items() if e == eid},
           'f': {k: o for k, (e, o) in (fxmap or {}).get('fx', {}).items() if e == eid},
           's': {k: o for k, (e, o) in (fxmap or {}).get('sets', {}).items() if e == eid},
           'm': {k: o for k, (e, o) in (fxmap or {}).get('motions', {}).items() if e == eid}}
    out = []
    for x in words:
        if x < 0xFF00:
            c, arg = (x >> 9) & 0x1F, x & 0x1FF
            m = (inv['p'] if c in (0x01, 0x14) else inv['f'] if c == 0x0B else inv['s'] if c == 0x0E
                 else inv['m'] if c == 0x0D else None)
            if m is not None and arg in m:
                x = (x & ~0x1FF) | m[arg]
        out.append(x)
    return out


def motion_bytes(rom, i):
    t = table(rom, 'motions')
    f = snes_to_file(t + _w(rom, t + 2 * i))
    return bytes(rom[f:f + MOTION_LEN.get(rom[f + 1] & 0x1F, 8)])


def describe_motion(data):
    """(label, editable params {name: value}) of a motion record."""
    t = data[1] & 0x1F
    label = MOTION_NAMES.get(t, f'Motion type {t}')
    if t in (0x17, 0x1A):
        sx, sy = data[2] - 256 if data[2] > 127 else data[2], data[3] - 256 if data[3] > 127 else data[3]
        return label, {'x': sx, 'y': sy, 'frames': data[4] | data[5] << 8}
    if t in (0x1B, 0x18):
        return label, {'speed': data[2]}
    return label, {}


def set_motion(data, params):
    """Motion record bytes with new params (as describe_motion gives them)."""
    d = bytearray(data)
    t = d[1] & 0x1F
    if t in (0x17, 0x1A):
        x, y, n = int(params['x']), int(params['y']), int(params['frames'])
        if not (-128 <= x <= 127 and -128 <= y <= 127 and 1 <= n <= 9999):
            raise ValueError('A move is -128 to 127 pixels a frame, for 1 to 9999 frames.')
        d[2], d[3], d[4], d[5] = x & 0xFF, y & 0xFF, n & 0xFF, n >> 8
    elif t in (0x1B, 0x18):
        n = int(params['speed'])
        if not 1 <= n <= 255:
            raise ValueError('Flying speed is 1 to 255.')
        d[2] = n
    return bytes(d)


def read_motions(blob):
    """motions.json -> {record or 'sID:record': bytes}."""
    d = read_json(blob, MOTIONS)
    try:
        return {k: bytes.fromhex(v) for k, v in d.items()}
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f'{FOLDER}/{MOTIONS} is not readable')


def motions_for_build(keyed):
    """{'12': b, 's77:12': b} -> {12: b, (77, 12): b}"""
    out = {}
    for k, v in keyed.items():
        if ':' in k:
            e, r = k[1:].split(':')
            out[(int(e), int(r))] = v
        else:
            out[int(k)] = v
    return out


def motion_key(i, fxmap):
    if fxmap and i in fxmap.get('motions', {}):
        e, o = fxmap['motions'][i]
        return f's{e}:{o}'
    return str(i)


def stream_delays(toks):
    """Frames per step of a colour stream: [each delay token's frames]."""
    return [(t[1] & 0x7F) + 1 for t in (toks or []) if t[0] == 'd']


def with_delay(toks, frames):
    """Tokens with one delay (frames per step) at the start and no others."""
    rest = [t for t in toks if t[0] != 'd']
    return [('d', 0x80 | max(0, min(127, frames - 1)))] + rest


def apply_all(rom, proj, far):
    """Everything in spell_gfx/: new effects, then redrawn pictures, then colours."""
    blob = lambda rel: open(os.path.join(proj, *rel.split('/')), 'rb').read() if os.path.exists(os.path.join(proj, *rel.split('/'))) else None
    try:
        effects = read_effects(blob(f'{FOLDER}/{EFFECTS}'))
    except ValueError as e:
        raise SystemExit(str(e))
    try:
        steps = read_steps(blob(f'{FOLDER}/{STEPS}'))
        for ws in steps.values():
            check_steps(ws)
    except ValueError as e:
        raise SystemExit(f'{FOLDER}/{STEPS}: {e}')
    try:
        motions = motions_for_build(read_motions(blob(f'{FOLDER}/{MOTIONS}')))
    except ValueError as e:
        raise SystemExit(str(e))
    fxmap = apply_effects(rom, effects, far, steps, motions)
    n = len(effects) + len(steps) + len(motions) if fxmap else 0
    if n:
        print(f'spell effects: {len(effects)} new effect(s), {len(steps)} with changed steps, '
              f'{len(motions)} changed motion(s)')
    n += apply(rom, proj, far, fxmap)
    n += apply_colours(rom, proj, far, fxmap)
    return n

# ---- the composed look of a spell ----

def _colour_of(cg, pal, v, bpp):
    """RGB for colour v of background palette pal (from cg, else the stand-in ramp)."""
    i = (4 if bpp == 2 else 16) * pal + v
    if cg is not None and i < 256 and cg[i] is not None:
        return rgb(cg[i])
    return RAMP4[v * 5 if bpp == 2 and v < 4 else v]


def preview_png(rom, spell, overrides=None, scale=1, cg=None):
    """The spell's backgrounds as the game lays them out (all its tilemaps side by side, one 256x256
    screen per 2 KB of map).  overrides = {record: tile bytes}; cg = 256 colours (None: the stand-in
    ramp)."""
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
    px = bytearray(W * H * 4)
    cache = {}
    for n, (words, bg3) in enumerate(screens):
        bpp = 2 if bg3 else 4
        for i, x in enumerate(words):
            t, pal = x & 0x3FF, (x >> 10) & 7
            key = (t, bpp)
            if key not in cache:
                at = 2 * (base2 + 8 * t) if bpp == 2 else 32 * t
                cache[key] = _decode(bytes(vram[at:at + 8 * bpp]).ljust(8 * bpp, b'\0'), bpp)[0]
            tile = cache[key]
            hf, vf = x >> 14 & 1, x >> 15 & 1
            ox, oy = n * 256 + (i % 32) * 8, (i // 32) * 8
            for k, v in enumerate(tile):
                if not v:
                    continue
                xx, yy = k % 8, k // 8
                if hf:
                    xx = 7 - xx
                if vf:
                    yy = 7 - yy
                o = 4 * ((oy + yy) * W + ox + xx)
                px[o:o + 4] = bytes(_colour_of(cg, pal, v, bpp)) + b'\xff'
    rows = [bytes(px[y * W * 4:(y + 1) * W * 4]) for y in range(H)]
    if scale > 1:
        rows = [bytes(b for i in range(0, len(r), 4) for _ in range(scale) for b in r[i:i + 4]) for r in rows for _ in range(scale)]
    return G.png(W * scale, H * scale, rows)


def record_palette(rom, r, spell=None):
    """The background palette the spells' tilemaps mostly draw record r's tiles with (or None)."""
    recs, by_spell = survey(rom)
    d = recs.get(r)
    if not d or d['kind'] not in ('tiles4', 'tiles2'):
        return None
    import collections
    cnt = collections.Counter()
    for s in ([spell] if spell in d['spells'] else d['spells']):
        for m in by_spell[s]:
            if recs[m]['kind'] != 'map':
                continue
            for x in recs[m]['words']:
                t = x & 0x3FF
                if not t:
                    continue
                if d['kind'] == 'tiles4':
                    hit = d['vram'] // 16 <= t < (d['vram'] + len(d['data']) // 2) // 16
                else:
                    base = 0x7000 if d['vram'] >= 0x7000 else 0x3000
                    hit = (d['vram'] - base) // 8 <= t < (d['vram'] - base + len(d['data']) // 2) // 8
                if hit:
                    tb = 8 * bpp_of(d['kind'])
                    k = (t - (d['vram'] // 16 if d['kind'] == 'tiles4' else (d['vram'] - (0x7000 if d['vram'] >= 0x7000 else 0x3000)) // 8)) * tb
                    if any(d['data'][k:k + tb]):
                        cnt[(x >> 10) & 7] += 1
    return cnt.most_common(1)[0][0] if cnt else None


def sheet_colour_png(data, bpp, cg, pal, scale=1):
    """A tile sheet in battle colours (palette pal of cg; colours the spell doesn't set use the ramp)."""
    tiles = _decode(data, bpp)
    w, h = sheet_size(len(data), bpp)
    cols = [None] + [_colour_of(cg, pal, v, bpp) for v in range(1, 16 if bpp == 4 else 4)]
    px = bytearray(w * h * 4)
    for t, tile in enumerate(tiles):
        ox, oy = (t % 16) * 8, (t // 16) * 8
        for i, v in enumerate(tile):
            if v:
                o = 4 * ((oy + i // 8) * w + ox + i % 8)
                px[o:o + 4] = bytes(cols[v]) + b'\xff'
    rows = [bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h)]
    if scale > 1:
        rows = [bytes(b for i in range(0, len(r), 4) for _ in range(scale) for b in r[i:i + 4]) for r in rows for _ in range(scale)]
    return G.png(w * scale, h * scale, rows)


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


def apply(rom, proj, far, fxmap=None):
    """spell_gfx/rNNN.png (and sID_rNNN.png for new effects) -> compressed tiles in free space, the
    record pointed at them."""
    files = edited(proj)
    for new, (eid, orig) in ((fxmap or {}).get('pictures') or {}).items():
        path = os.path.join(proj, *effect_file(eid, orig).split('/'))
        if os.path.exists(path):
            files[new] = path
    if not files:
        return 0
    recs, _ = survey(rom)
    n = 0
    for r, path in files.items():
        if r not in recs or recs[r]['kind'] == 'map':
            raise SystemExit(f'{FOLDER}/{os.path.basename(path)}: record {r} is not a spell picture the kit can edit')
        d = recs[r]
        try:
            data = sheet_from_png(open(path, 'rb').read(), len(d['data']), bpp_of(d['kind']))
        except ValueError as e:
            raise SystemExit(f'{FOLDER}/{os.path.basename(path)}: {e}')
        if data == d['data']:
            continue
        comp = fe4lz.compress(data)
        at = far.alloc(len(comp) + 1, upper_half=True)
        fo = snes_to_file(at)
        rom[fo:fo + len(comp)] = comp
        f = snes_to_file(table(rom, 'pictures') + 10 * r)
        rom[f:f + 3] = at.to_bytes(3, 'little')
        n += 1
    if n:
        _cache.clear()
        print(f'spell graphics: {n} picture(s) redrawn')
    return n
