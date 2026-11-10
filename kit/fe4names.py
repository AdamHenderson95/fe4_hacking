#!/usr/bin/env python3
"""Character, class, item and castle names (Project Naga pre-drawn name graphics).

Naga stores most English names as ready-made 2bpp graphics.  The name slot
table at 0x500000 has 16-byte entries:
  +0 width in 8x8 tiles, +1 ptr24 to the graphic (top tile row, then bottom row)
  +4 (items, castles) a second variant: width + ptr24
  +8 up to 8 characters of the name as text (used for reference only)
Slots: characters = name_id (0-575), classes = 576 + class, items = 1024 + item,
castles = 1280 + castle (and 800 + castle, with three variants, for the map
terrain window).  Item variant 2 is the same picture right-aligned in its
width; castle variant 2 is 8 tiles wide, right-aligned (the map terrain window).

Renaming draws the new name with the game's own name font (fe4font.py) into free
space and repoints the slot.  The text tables for classes (0x506200) and items
(0x506700) are updated too.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
from fe4font import FONT

SLOTS = 0x500000
KINDS = {  # kind: (first slot, count, max tiles)
    'character': (0, 576, 7),
    'class': (576, 72, 8),
    'item': (1024, 122, 9),
    'castle': (1280, 46, 7),
}
CASTLE_TERRAIN = 800  # castle names again, as shown in the map terrain window
SPACE_ADV = 3      # extra columns for a space (measured from class names)
GLYPHS = {c: [[{'.': 0, '+': 2, 'o': 3}[ch] for ch in row] for row in rows] for c, rows in FONT.items()}
STROKES = {}
for _c, _g in GLYPHS.items():
    _xs = [x for row in _g for x, v in enumerate(row) if v == 2]
    STROKES[_c] = frozenset((x - min(_xs), y) for y, row in enumerate(_g) for x, v in enumerate(row) if v == 2)


# ---------------------------------------------------------------- drawing
def render(text):
    """-> (16 rows of pixel values 0/2/3, width in tiles)"""
    canvas = [[0] * 512 for _ in range(16)]
    cur = 1
    for c in text:
        if c == ' ':
            cur += SPACE_ADV
            continue
        if c not in GLYPHS:
            raise ValueError('no glyph for %r (letters, digits and . , \' - ! ? : / & ( ) are available)' % c)
        g = GLYPHS[c]
        x0 = cur - 1
        for y in range(16):
            for x, v in enumerate(g[y]):
                if v and (v == 2 or canvas[y][x0 + x] != 2):
                    canvas[y][x0 + x] = v
        cur += len(g[0]) - 1
    w = (cur + 7) // 8
    return [row[:w * 8] for row in canvas], w


def right_align(rows, width_px):
    last = max((x for row in rows for x, v in enumerate(row) if v), default=0)
    off = width_px - 1 - last
    return [[0] * off + row[:last + 1] for row in rows]


def to_tiles(rows, w):
    out = bytearray()
    for half in range(2):
        for t in range(w):
            for y in range(8):
                p0 = p1 = 0
                for x in range(8):
                    v = rows[half * 8 + y][t * 8 + x] if t * 8 + x < len(rows[0]) else 0
                    p0 |= (v & 1) << (7 - x)
                    p1 |= (v >> 1) << (7 - x)
                out += bytes([p0, p1])
    return bytes(out)


def from_tiles(rom, w, p):
    rows = [[0] * (w * 8) for _ in range(16)]
    for half in range(2):
        for t in range(w):
            b = rom[p + (half * w + t) * 16:p + (half * w + t) * 16 + 16]
            for y in range(8):
                for x in range(8):
                    rows[half * 8 + y][t * 8 + x] = ((b[2 * y] >> (7 - x)) & 1) | (((b[2 * y + 1] >> (7 - x)) & 1) << 1)
    return rows


# ---------------------------------------------------------------- reading names back
def read_graphic(rom, rows, hint=''):
    """Recognise a drawn name with the font; None if any letter is unknown.
    hint (the slot's 8-letter text) settles look-alikes such as I and l."""
    W = len(rows[0])
    cols = [any(rows[y][x] == 2 for y in range(16)) for x in range(W)]
    segs, x = [], 0
    while x < W:
        if cols[x]:
            s = x
            while x < W and cols[x]:
                x += 1
            segs.append((s, x - 1))
        else:
            x += 1
    text, prev = '', None
    for s, e in segs:
        shape = frozenset((xx - s, y) for y in range(16) for xx in range(s, e + 1) if rows[y][xx] == 2)
        hit = [c for c, st in STROKES.items() if st == shape]
        if not hit:
            return None
        if prev is not None and s - prev > 2:
            text += ' ' * max(1, (s - prev - 2) // SPACE_ADV)
        pos = len(text)
        if pos < len(hint) and hint[pos] in hit:
            ch = hint[pos]
        elif len(hit) > 1:
            word_start = pos == 0 or text[-1] == ' '
            ch = next((c for c in hit if c.isupper() == word_start), hit[0])
        else:
            ch = hit[0]
        text += ch
        prev = e
    return text


def slot_header(rom, slot):
    a = SLOTS + 16 * slot
    return rom[a], rom[a + 1] | rom[a + 2] << 8 | rom[a + 3] << 16


def slot_valid(rom, slot):
    w, p = slot_header(rom, slot)
    return 1 <= w <= 12 and 0x400000 <= p < 0x7F0000


def current_name(rom, slot):
    if slot_empty(rom, slot):
        return ''
    w, p = slot_header(rom, slot)
    hint = L.decode(rom[SLOTS + 16 * slot + 8:SLOTS + 16 * slot + 16]).replace('{44}', '.')
    txt = read_graphic(rom, from_tiles(rom, w, p), hint)
    return txt if txt else hint


_ENC = {' ': 0xBF, '.': 0x44, ',': 0x45, '?': 0x46, '!': 0x47, "'": 0x48, '-': 0x49}


def encode_name(s, n):
    out = bytearray()
    for c in s:
        if 'A' <= c <= 'Z':
            out.append(0x10 + ord(c) - 65)
        elif 'a' <= c <= 'z':
            out.append(0x2A + ord(c) - 97)
        elif '0' <= c <= '9':
            out.append(0x50 + ord(c) - 48)
        elif c in _ENC:
            out.append(_ENC[c])
    return bytes(out[:n])


# ---------------------------------------------------------------- csv
FIELDS = ['kind', 'id', 'name', '_tiles']


def slot_empty(rom, slot):
    return not any(rom[SLOTS + 16 * slot:SLOTS + 16 * slot + 16])


def rows_for(rom):
    for kind, (first, count, _) in KINDS.items():
        for i in range(count):
            slot = first + i
            # empty character slots (570-575 in FE4) can be named for new units
            if slot_valid(rom, slot) or (kind == 'character' and slot_empty(rom, slot)):
                yield kind, i, slot


def export(rom, path):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for kind, i, slot in rows_for(rom):
            w.writerow({'kind': kind, 'id': i, 'name': current_name(rom, slot), '_tiles': rom[SLOTS + 16 * slot]})
    print('wrote', path)


def _class_raw(i):
    return None if i == 10 else (i if i < 10 else i - 1)


def _item_raw(i):
    """item ID -> index in the 0x506700 text table (broken weapons share one entry)."""
    raw = 0
    out = {}
    for r in range(94):
        if r in L.BROKEN_NAME_IDX:
            for k in range(3):
                out[raw + k] = None
            raw += 3
        else:
            out[raw] = r
            raw += 1
    for r in range(94, 110):
        out[raw] = r
        raw += 1
    return out.get(i)


def apply(rom, path, far=None, space=None):
    if not os.path.exists(path):
        return 0
    far = far or L.FreeSpace()
    renamed = set()
    valid = {(k, i): s for k, i, s in rows_for(rom)}
    changes = 0
    for ln, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
        kind = row['kind'].strip()
        try:
            i = int(row['id'])
        except ValueError:
            raise SystemExit(f'{path}:{ln}: id must be a number')
        if (kind, i) not in valid:
            raise SystemExit(f'{path}:{ln}: no {kind} name {i}')
        slot = valid[(kind, i)]
        name = row['name'].strip()
        same = lambda a: a.replace('I', 'l')  # noqa: E731  (I and l are drawn alike)
        if same(name) == same(current_name(rom, slot)):
            continue
        try:
            pix, w = render(name)
        except ValueError as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        maxw = KINDS[kind][2]
        if w > maxw:
            raise SystemExit(f'{path}:{ln}: "{name}" is {w} tiles wide; {kind} names fit in {maxw}')
        a = SLOTS + 16 * slot
        data = to_tiles(pix, w)
        p = far.alloc(len(data))
        rom[p:p + len(data)] = data
        rom[a:a + 4] = bytes([w]) + p.to_bytes(3, 'little')
        if kind in ('item', 'castle'):
            w2 = w if kind == 'item' else 8
            pix2 = right_align(pix, w2 * 8)
            d2 = to_tiles(pix2, w2)
            p2 = far.alloc(len(d2))
            rom[p2:p2 + len(d2)] = d2
            rom[a + 4:a + 8] = bytes([w2]) + p2.to_bytes(3, 'little')
        rom[a + 8:a + 16] = encode_name(name, 8).ljust(8, b'\0')
        if kind == 'castle':
            # second slot set used by the map terrain window: normal, centred in 8 tiles, right-aligned
            b = SLOTS + 16 * (CASTLE_TERRAIN + i)
            last = max((x for row in pix for x, v in enumerate(row) if v), default=0)
            off = (64 - (last + 1)) // 2
            centred = [[0] * off + row[:last + 1] for row in pix]
            d2 = to_tiles(centred, 8)
            d3 = to_tiles(right_align(pix, w * 8), w)
            p2, p3 = far.alloc(len(d2)), far.alloc(len(d3))
            rom[p2:p2 + len(d2)] = d2
            rom[p3:p3 + len(d3)] = d3
            rom[b:b + 12] = (bytes([w]) + p.to_bytes(3, 'little') + bytes([8]) + p2.to_bytes(3, 'little') +
                             bytes([w]) + p3.to_bytes(3, 'little'))
            rom[b + 12:b + 16] = encode_name(name, 4).ljust(4, b'\0')
        if kind == 'class' and _class_raw(i) is not None:
            t = L.CLASS_NAMES + 16 * _class_raw(i)
            rom[t:t + 16] = (encode_name(name, 15) + b'\x01').ljust(16, b'\0')
        if kind == 'item' and _item_raw(i) is not None:
            t = L.ITEM_NAMES + 16 * _item_raw(i)
            rom[t:t + 16] = (encode_name(name, 15) + b'\x01').ljust(16, b'\0')
        if kind == 'character':
            renamed.add(i)
        changes += 1
    changes += apply_list_names(rom, renamed, space or L.BankSpace(rom))
    return changes


# ---------------------------------------------------------------- names in unit lists
# Lists (the Unit list, item bearers, ...) draw names from a pre-drawn sheet loaded into VRAM:
# generation 1 uses $45:D000 (6 rows), generation 2 $45:E000 (10 rows).  A row is 16 columns of
# 8x16 (a top tile, and the bottom tile 16 tiles later).  $50:A000 + 16 x name_id lists the
# columns of each name as big-endian tile ids (0x240 + row x 0x20 + column), up to 6, 0 = end.
SHEETS = {1: (0x45D000, 6), 2: (0x45E000, 10)}
LIST_NAMES = 0x50A000
LIST_LIMIT = 512                    # entries past this overlap other data
LIST_HOOK = 0x510736                # PLA; CLC; ADC #$A000; STA $142A; RTL  (name_id x 16 in A)
LIST_COLS = 6
GEN1_NAMES = range(0, 24)           # Sigurd..Bridget


def _list_entry_addr(rom, nid):
    if nid < LIST_LIMIT:
        return LIST_NAMES + 16 * nid
    if rom[LIST_HOOK] == 0x68:
        return None
    t = rom[LIST_HOOK + 1] | rom[LIST_HOOK + 2] << 8 | rom[LIST_HOOK + 3] << 16   # JML operand
    from dis65816 import snes_to_file
    code = snes_to_file(t)
    base = _w(rom, code + 8)                                      # ADC #table - 16 x first
    return 0x500000 + ((base + 16 * nid) & 0xFFFF)


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def _entry_cols(rom, nid):
    a = _list_entry_addr(rom, nid)
    if a is None:
        return []
    out = []
    for k in range(LIST_COLS):
        t = rom[a + 2 * k] << 8 | rom[a + 2 * k + 1]
        if not t:
            break
        out.append(t - 0x240)
    return out


def _list_users(rom):
    """{name_id: generation} for names shown in the player's unit lists."""
    out = {}
    for k in (0, 1):
        off = {0: 15, 1: 5}[k]
        for idx, a, _, _ in L.unit_rows(rom, k):
            nid = rom[a + off] | rom[a + off + 1] << 8
            if idx <= 63 or idx > L.RESERVED_IDS:
                gen = 1 if (k == 0 and idx <= 24) else 2
                out.setdefault(nid, gen)
    return out


def _install_list_hook(rom, space):
    if rom[LIST_HOOK] != 0x68:
        return
    from asm65816 import Asm
    first = 570
    tfo, tsn = space.alloc(0x500000, 16 * 6)
    rom[tfo:tfo + 96] = bytes(96)
    cfo, csn = space.alloc(0x510000, 24)
    a = Asm(csn)
    a.op('pla')
    a.op('cmp', '#', 16 * LIST_LIMIT)
    a.op('bcc', 'rel', 'v')
    a.op('clc')
    a.op('adc', '#', ((tsn & 0xFFFF) - 16 * first) & 0xFFFF)   # operand read back by _list_entry_addr
    a.op('bra', 'rel', 'st')
    a.label('v')
    a.op('clc')
    a.op('adc', '#', 0xA000)
    a.label('st')
    a.op('sta', 'abs', 0x142A)
    a.op('rtl')
    code = a.assemble()
    rom[cfo:cfo + len(code)] = code
    assert rom[cfo + 7] == 0x69
    rom[LIST_HOOK:LIST_HOOK + 4] = bytes([0x5C]) + csn.to_bytes(3, 'little')


def apply_list_names(rom, renamed, space):
    """Draw renamed (or new) player characters into the list name sheets."""
    users = _list_users(rom)
    todo = sorted(n for n, g in users.items() if n in renamed or (not _entry_cols(rom, n) and not slot_empty(rom, n)))
    n_changed = 0
    for nid in todo:
        gen = users[nid]
        if nid >= 576:
            continue
        if nid >= LIST_LIMIT:
            if not (570 <= nid < 576):
                continue
            _install_list_hook(rom, space)
        base, rows = SHEETS[gen]
        same_gen = [m for m, g in users.items() if g == gen and m != nid]
        if gen == 1:
            same_gen += [m for m in GEN1_NAMES if m != nid]
        else:
            same_gen += [m for m in range(24, 63) if m != nid]
        taken = set()
        for m in set(same_gen):
            taken.update(_entry_cols(rom, m))
        own = _entry_cols(rom, nid)
        w, p = slot_header(rom, nid)
        need = min(w, LIST_COLS)
        free = [c for c in range(rows * 32) if c % 32 < 16 and c not in taken and c not in own]
        cols = own[:need] if len(own) >= need else own + free[:need - len(own)]
        if len(cols) < need:
            print(f'note: no room left in the generation-{gen} name sheet for "{current_name(rom, nid)}"; '
                  f'unit lists will show it blank')
            cols = []
        for c in own:                                  # clear the old picture
            for t in (c, c + 16):
                rom[base + 16 * t:base + 16 * t + 16] = bytes(16)
        tiles = rom[p:p + 32 * w]
        for k, c in enumerate(cols):
            rom[base + 16 * c:base + 16 * c + 16] = tiles[16 * k:16 * k + 16]
            rom[base + 16 * (c + 16):base + 16 * (c + 16) + 16] = tiles[16 * (w + k):16 * (w + k) + 16]
        a = _list_entry_addr(rom, nid)
        ent = b''.join((0x240 + c).to_bytes(2, 'big') for c in cols)
        rom[a:a + 16] = ent.ljust(16, b'\0')
        n_changed += 1
    return n_changed


if __name__ == '__main__':
    _, r = L.load_rom(sys.argv[1])
    export(r, sys.argv[2])
