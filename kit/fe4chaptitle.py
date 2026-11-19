"""Chapter titles: the title card shown when a chapter starts, and the chapter's name in the game's text.

Found by tracing the Prologue's card (editor 1.2).  The card is drawn by $80:F390-$80:F412:

  letters   4bpp tiles $43:14F0 (compressed, $6000 bytes = 768 tiles, to VRAM $0000), named by the
            graphics script at $80:F42B (24-bit pointer at $80:F430).  Project Naga drew every
            chapter's title into this one sheet (16 tiles wide, 24 px strips, the titles run on from
            one strip to the next), plus "Prologue", "Chapter", "Endgame" and the digits.
  layout    a BG1 map $42:5A10 (compressed; the immediates LDA #$425A / LDA #$5A10 at $80:F3DD and
            $80:F3E2): 12 blocks of $180 bytes, one per chapter ($0D6A: 0 = Prologue .. 11 = Endgame),
            each 6 rows of 32 entries.  Rows 0-2 are the label ("Prologue", "Chapter 3"), rows 3-5 the
            title.  The chapter's block is copied to VRAM $5140 (screen rows 10-15).
  colours   palette 4, colours 1-8: 1 = the black outline, 2-8 grey from dark to light (the card
            tints them).  Tile $033 is empty.

A new title is drawn by the editor (the browser renders the text) and stored as a 256x24 picture of
colour numbers.  The build cuts it into tiles, reuses the tiles of the chapter's old title (and any
tile no chapter uses), and writes the sheet and the map to free space.

The same names are in the game's text: a slot per chapter in the Naga text table at $50:6010..
($09 text $01, 32 bytes each), and the end-of-game turn record at $68:3100.. ("Ch. 1: <title>").
Those are rewritten too (the record only while the new titles fit in the old record's length).

Project file: chapter_titles.json  {"<chapter 0-11>": {"text": "...", "px": "<6144 digits 0-8>"}}
"""
import json
import os

import fe4events as E
import fe4lz
from dis65816 import snes_to_file as _fo

FILE = 'chapter_titles.json'
CHAPTERS = 12
NAMES = ['Prologue'] + ['Chapter %d' % i for i in range(1, 11)] + ['Endgame']
W, H = 256, 24
BLANK = 0x033
PAL = 0x1000                                   # palette 4
SHEET_REF = 0x80F430                           # 24-bit pointer in the graphics script
MAP_REFS = (0x80F3DE, 0x80F3DF, 0x80F3E3, 0x80F3E4)   # LDA #$425A (mid, bank), LDA #$5A10 (lo, mid)
SHEET_TILES = 768
BLOCK = 0x180
TEXT_SLOTS = [0x506010, 0x506040, 0x506060, 0x506080, 0x5060A0, 0x5060C0, 0x506100, 0x506120,
              0x506140, 0x506160, 0x506190, 0x5061C0]
SLOT_LEN = 32
TEXT_MAX = SLOT_LEN - 2
RECORD = (0x683100, 0x683400)                  # the end-of-game turn record's text
CHARS = set(E._CH_INV) | {':'}
# the card's colours 0-8 as greys (the game tints them); for previews
GREYS = [None, 0, 32, 56, 104, 120, 128, 144, 160]


def _rd(rom, a):
    return rom[_fo(a)]


def sheet_ptr(rom):
    o = _fo(SHEET_REF)
    return int.from_bytes(rom[o:o + 3], 'little')


def map_ptr(rom):
    mid, bank, lo, mid2 = (_rd(rom, a) for a in MAP_REFS)
    return bank << 16 | mid << 8 | lo


def known(rom):
    """True when this ROM's card code is the one traced here."""
    o = _fo(0x80F3DD)
    h = _fo(0x80F392)
    return (rom[h:h + 14] == bytes.fromhex('a9008085 28a92bf4 8527 22798987'.replace(' ', ''))
            and rom[o] == 0xA9 and rom[o + 3:o + 5] == b'\x85\x25' and rom[o + 5] == 0xA9
            and rom[o + 8:o + 10] == b'\x85\x24' and _rd(rom, MAP_REFS[0]) == _rd(rom, MAP_REFS[3])
            and rom[_fo(0x80F42B):_fo(0x80F42B) + 5] == b'\x00\x60\x00\x00\x01')


def _tile(data, t):
    b = data[t * 32:t * 32 + 32]
    rows = []
    for y in range(8):
        p0, p1, p2, p3 = b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[17 + 2 * y]
        rows.append([((p0 >> s) & 1) | ((p1 >> s) & 1) << 1 | ((p2 >> s) & 1) << 2 | ((p3 >> s) & 1) << 3
                     for s in range(7, -1, -1)])
    return rows


def _tile_bytes(px):
    out = bytearray(32)
    for y in range(8):
        for plane in range(4):
            v = 0
            for x in range(8):
                if px[y][x] >> plane & 1:
                    v |= 0x80 >> x
            out[(plane >> 1) * 16 + 2 * y + (plane & 1)] = v
    return bytes(out)


_cache = {}


def read(rom):
    """(sheet bytes, map bytes) as the ROM has them."""
    key = (id(rom), sheet_ptr(rom), map_ptr(rom))
    if key not in _cache:
        _cache.clear()
        _cache[key] = (fe4lz.decompress(rom, sheet_ptr(rom)), fe4lz.decompress(rom, map_ptr(rom)))
    return _cache[key]


def _entries(mp, ch, rows):
    b = ch * BLOCK
    return [[int.from_bytes(mp[b + (r * 32 + c) * 2:b + (r * 32 + c) * 2 + 2], 'little') for c in range(32)]
            for r in rows]


def picture(sheet, mp, ch, rows):
    """The rows' tiles as a 256 x 8*len(rows) grid of colour numbers (a string of digits)."""
    out = []
    ents = _entries(mp, ch, rows)
    for row in ents:
        tiles = [_tile(sheet, e & 0x3FF) if (e & 0x3FF) * 32 + 32 <= len(sheet) else [[0] * 8] * 8 for e in row]
        for y in range(8):
            line = []
            for e, t in zip(row, tiles):
                r = t[7 - y] if e & 0x8000 else t[y]
                line += r[::-1] if e & 0x4000 else r
            out.append(''.join(str(min(v, 9)) for v in line))
    return ''.join(out)


def _slot_text(rom, ch):
    o = _fo(TEXT_SLOTS[ch])
    b = rom[o:o + SLOT_LEN]
    if not b or b[0] != 0x09:
        return ''
    end = b.find(b'\x01')
    return decode(b[1:end if end > 0 else len(b)])


def decode(b):
    return ''.join(':' if x == 0x4C else E._CH.get(x, '') for x in b)


def encode(s):
    out = bytearray()
    for c in s:
        if c == ':':
            out.append(0x4C)
        elif c in E._CH_INV:
            out.append(E._CH_INV[c])
        else:
            raise ValueError(f'"{c}" is not in the game\'s letters')
    return bytes(out)


def load(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return {}
    with open(p, 'rb') as f:
        return parse(f.read())


def _uses(mp):
    uses = {}
    for ch in range(len(mp) // BLOCK):
        for part, rows in (('label', (0, 1, 2)), ('title', (3, 4, 5))):
            for row in _entries(mp, ch, rows):
                for e in row:
                    uses.setdefault(e & 0x3FF, set()).add((ch, part))
    return uses


def budget(sheet, mp, ch):
    """Tiles a new title of chapter ch can use: its own sheet copy keeps only its label's tiles."""
    keep = {BLANK}
    for row in _entries(mp, ch, (0, 1, 2)):
        keep |= {e & 0x3FF for e in row}
    return [t for t in range(SHEET_TILES) if t not in keep]


def cut(px):
    """A 256x24 digit string -> 32x3 tiles (each 8 rows of 8 colour numbers)."""
    if len(px) != W * H or any(c not in '012345678' for c in px):
        raise ValueError('the title picture must be 256 x 24 colour numbers 0-8')
    tiles = []
    for ty in range(3):
        for tx in range(32):
            tiles.append([[int(px[(ty * 8 + y) * W + tx * 8 + x]) for x in range(8)] for y in range(8)])
    return tiles


def tiles_needed(px):
    return len({_tile_bytes(t) for t in cut(px) if any(any(r) for r in t)})


def build_card(sheet, mp, ch, px):
    """(sheet, block): chapter ch's own copy of the letter sheet with the new title in it, and its
    $180-byte map block.  Raises ValueError when the title doesn't fit."""
    sheet = bytearray(sheet.ljust(SHEET_TILES * 32, b'\0'))
    block = bytearray(mp[ch * BLOCK:(ch + 1) * BLOCK])
    free = sorted(budget(sheet, mp, ch), reverse=True)
    made = {}
    for i, t in enumerate(cut(px)):
        if not any(any(r) for r in t):
            e = BLANK
        else:
            b = _tile_bytes(t)
            if b not in made:
                if not free:
                    raise ValueError(f'{NAMES[ch]}: the title needs more tiles than the card has')
                n = free.pop()
                sheet[n * 32:n * 32 + 32] = b
                made[b] = n
            e = PAL | made[b]
        o = ((3 + i // 32) * 32 + i % 32) * 2
        block[o:o + 2] = e.to_bytes(2, 'little')
    return bytes(sheet), bytes(block)


def _write_slots(rom, data):
    n = 0
    for ch, v in data.items():
        text = (v.get('text') or '').strip()
        if not text:
            continue
        b = b'\x09' + encode(text)[:TEXT_MAX] + b'\x01'
        o = _fo(TEXT_SLOTS[ch])
        new = b.ljust(SLOT_LEN, b'\0')
        if rom[o:o + SLOT_LEN] != new:
            rom[o:o + SLOT_LEN] = new
            n += 1
    return n


def _record(rom, data):
    """Rewrite the titles in the end-of-game record while the whole block keeps its length."""
    lo, hi = _fo(RECORD[0]), _fo(RECORD[1])
    blk = bytes(rom[lo:hi])
    colon_sp = bytes([0x4C, E._CH_INV[' ']])
    start = blk.find(encode('Prologue') + colon_sp)
    end = blk.find(encode('Total') + bytes([0x4C]))
    if start < 0 or end < 0:
        return 'left as it is (this ROM\'s record text is different)'
    seg = blk[start:end]
    parts, i = [], 0
    for ch in range(CHAPTERS):
        j = seg.find(colon_sp, i)
        k = seg.find(b'\x02', j)
        if j < 0 or k < 0:
            return 'left as it is (this ROM\'s record text is different)'
        parts.append((j + 2, k))
        i = k
    out, last = bytearray(), 0
    for ch, (a, b) in enumerate(parts):
        out += seg[last:a]
        t = (data.get(ch) or {}).get('text', '').strip()
        out += encode(t) if t else seg[a:b]
        last = b
    out += seg[last:]
    if len(out) > len(seg):
        return 'left as it is (the new titles are longer than the old ones there)'
    if len(out) < len(seg):     # pad the last title line with spaces
        k = parts[-1][1] + (len(out) - len(seg))
        pad = len(seg) - len(out)
        out = out[:k] + bytes([E._CH_INV[' ']]) * pad + out[k:]
    if bytes(out) != seg:
        rom[lo + start:lo + end] = out
        return 'updated'
    return 'unchanged'


HOOK_AT = 0x80F392          # LDA #$8000 / STA $28 / LDA #$F42B / STA $27 (10 bytes), then JSL $87:8979
SCRIPT = 0x80F42B           # the letters' graphics script entry (8 bytes: size, VRAM, 01, pointer)


def _put(rom, far, blob):
    # upper half: $70-$7D:6000-7FFF reads as save RAM, and the decompression queue takes a $xx:0000
    # source for "no job"
    a = far.alloc(len(blob) + 1, upper_half=True)
    rom[_fo(a):_fo(a) + len(blob)] = blob
    return a


SCRIPT_BANKS = (0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88)


def _bank_alloc(space, n):
    for b in SCRIPT_BANKS:
        try:
            return space.alloc(b << 16 | 0x8000, n)
        except SystemExit:
            continue
    raise SystemExit('chapter titles: no room left in banks $80-$88')


def _write_cards(rom, far, space, cards):
    """Each changed chapter gets its own letter sheet; a hook picks the sheet by chapter ($0D6A)."""
    sheet, mp = read(rom)
    mp = bytearray(mp)
    scripts = [SCRIPT] * CHAPTERS
    so = _fo(SCRIPT)
    for ch, px in sorted(cards.items()):
        try:
            sh, block = build_card(sheet, mp, ch, px)
        except ValueError as e:
            raise SystemExit(f'{FILE}: {e}')
        mp[ch * BLOCK:(ch + 1) * BLOCK] = block
        a = _put(rom, far, fe4lz.compress(sh))
        # the script runner reads the entry with DB = its bank and the queue at $0446 with the same DB,
        # so the entry must sit in a bank with WRAM at $0000-$1FFF ($80-$BF)
        fo, scripts[ch] = _bank_alloc(space, 8)
        rom[fo:fo + 8] = bytes(rom[so:so + 5]) + a.to_bytes(3, 'little')
    a = _put(rom, far, fe4lz.compress(bytes(mp)))
    for ref, val in zip(MAP_REFS, (a >> 8 & 0xFF, a >> 16, a & 0xFF, a >> 8 & 0xFF)):
        rom[_fo(ref)] = val
    table = b''.join(s.to_bytes(3, 'little') + b'\0' for s in scripts)
    tbl = _put(rom, far, table)
    t0, t2 = tbl.to_bytes(3, 'little'), (tbl + 2).to_bytes(3, 'little')
    code = (b'\xDA\xAD\x6A\x0D\xC9\x0C\x00\x90\x03\xA9\x00\x00\x0A\x0A\xAA'
            + b'\xBF' + t2 + b'\xEB\x29\x00\xFF\x85\x28'
            + b'\xBF' + t0 + b'\x85\x27\xFA\x6B')
    h = _put(rom, far, code)
    o = _fo(HOOK_AT)
    rom[o:o + 10] = b'\x22' + h.to_bytes(3, 'little') + b'\xEA' * 6


def apply(rom, proj, far, space):
    data = load(proj)
    data = {c: v for c, v in data.items() if 0 <= c < CHAPTERS and (v.get('px') or v.get('text'))}
    if not data:
        return 0
    for c, v in data.items():
        try:
            encode((v.get('text') or '').strip())
        except ValueError as e:
            raise SystemExit(f'{FILE}: {NAMES[c]}: {e}')
    n = _write_slots(rom, data)
    res = _record(rom, data)
    if res.startswith('left'):
        print('chapter titles: end-of-game record', res)
    cards = {c: v['px'] for c, v in data.items() if v.get('px')}
    if cards:
        if not known(rom):
            raise SystemExit('chapter titles: this ROM\'s title card code is not the one the kit knows; left as it is')
        _write_cards(rom, far, space, cards)
        n += len(cards)
    return n


def parse(blob):
    """chapter_titles.json bytes -> {chapter: entry}."""
    if not blob:
        return {}
    return {int(k): v for k, v in json.loads(blob.decode('utf-8')).items()}


def dump(data):
    return json.dumps({str(k): v for k, v in sorted(data.items())}, indent=1).encode('utf-8') if data else None


def info(rom, data=None, ch=None):
    """What the editor shows: per chapter the label and title pictures and the names."""
    sheet, mp = read(rom)
    data = data or {}
    out = []
    for c in range(CHAPTERS):
        if ch is not None and c != ch:
            continue
        own = data.get(c, {})
        out.append({'ch': c, 'name': NAMES[c], 'gameText': _slot_text(rom, c),
                    'text': own.get('text', ''), 'custom': bool(own.get('px')),
                    'label': picture(sheet, mp, c, (0, 1, 2)), 'orig': picture(sheet, mp, c, (3, 4, 5)),
                    'px': own.get('px', ''), 'look': own.get('look')})
    return {'chapters': out, 'w': W, 'h': H, 'greys': GREYS[1:], 'textMax': TEXT_MAX,
            'chars': ''.join(sorted(CHARS))}
