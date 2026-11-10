#!/usr/bin/env python3
"""New skills in the map menu's Skills list (name, icon, type and help text).

How the translated Skills menu works (Project Naga build):
  * The list is up to 18 rows of skill IDs at $8B:DFBF.  Each row's text is a short
    tilemap string at $50:7A00 + 32*row, drawn by the text routine $87:9354 from an
    unrolled block at $80:D523.  The strings use glyph codes 0x01NN = BG3 tile NN (top)
    and NN+16 (bottom); the glyph tiles are raw 2bpp at $45:0000 (tiles $E0-$13F are
    blank and free, which is where new names go).
  * The help pane is a pre-drawn 128x64 2bpp picture per row at $59:4000 + row*$800
    (name line + three text lines), copied to VRAM by $51:1500.
  * Icons are 16x16 sprites: the list draws groups of 7 rows ($8B:DAB4); the help pane
    icon comes from the per-row table $8B:DB7E (sprite tile - $20).
  * Bearers are gathered per row into $7F:81F9 (64 bytes a row) and $7F:8741 (counts),
    which only have room for 21 rows; longer lists move both to $7F:A000.
New rows are appended after the game's 18.  Up to 32 rows fit the list buffer.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asm65816 import Asm
import fe4names as N

LIST = 0x0BDFBF
VANILLA_ROWS = 18
MAX_ROWS = 32
ROW_TEXT = 0x507A00
DESC = 0x594000
DESC_SIZE = 0x800
GLYPH_SHEET = 0x450000
FREE_CELLS = (list(range(0xE0, 0xEF))     # not $EF: its lower half, tile $FF, is the blank the menu draws for spaces
              + list(range(0x100, 0x110)) + list(range(0x120, 0x130))
              + list(range(0x1E6, 0x1F0)))      # 57 glyph cells (8 px each) for new names
NAME_SHEET = 0x45D000                           # tiles $140-$1FF (bearer names) come from here


def cell_addr(t):
    return GLYPH_SHEET + 16 * t if t < 0x140 else NAME_SHEET + 16 * (t - 0x140)
NAME_CELLS = 7
ICON_TABLE = 0x0BDB7E
ICON_TILES = [0x26, 0x20, 0x22, 0x24, 0x64, 0x66, 0x28, 0x2C, 0x2E, 0x40, 0x42, 0x44, 0x46, 0x48, 0x4A,
              0x60, 0x62, 0x68]                 # list sprite tile per vanilla row
SPARE_ICONS = [0x2A, 0x4C, 0x4E, 0x6A, 0x6C, 0x6E]
TYPES = {'combat': bytes.fromhex('01aa01ab01ac01ad01ae'), 'field': bytes.fromhex('01c001c101c2'),
         'sword': bytes.fromhex('01c501c601c701c8')}
SPACE = bytes.fromhex('8140')
# code sites
SITE_ROWS = 0x00D523, 0x80D655                  # unrolled row drawing; continue at
SITE_DESC = 0x511500, 0x511537                  # help picture copy; continue after its DMA
SITE_ICONS = 0x0BDAB4                           # list icon groups (JSR'd, ends RTS)
OPS_LIST = [0x00D88A, 0x0BD9C7, 0x0BDC59]       # long operands of LDA $8BDFBF,X
OP_COUNT = 0x00D8E3                             # CMP #$0012 (rows)
OP_LAST = 0x0BDCEF                              # CMP #$0011 (last row)
OP_SCROLL = 0x0BDC0A                            # CMP #$000C (bottom scroll, 8px steps)
OP_ICON = 0x0BDB5B                              # LDA $8BDB7E,X operand
BEARERS, COUNTS = (0x7F81F9, [0x00D867, 0x00D8CB, 0x0BDA4F, 0x0BDE6E]), \
                  (0x7F8741, [0x00D875, 0x00D8DB, 0x0BD85D, 0x0BD8BB, 0x0BDBC0, 0x0BDC8E])
OP_CLEAR_B, OP_CLEAR_C = 0x00D86D, 0x00D87B     # CPX #$0540 / CPX #$002A
NEW_BEARERS, NEW_COUNTS = 0x7FA000, 0x7FA800


def vanilla_rows(rom):
    return [rom[LIST + 2 * k] | rom[LIST + 2 * k + 1] << 8 for k in range(VANILLA_ROWS)]


def icon_names(rom, names):
    """{name: sprite tile} for the icons that can be borrowed"""
    out = {}
    for k, sid in enumerate(vanilla_rows(rom)):
        out[names[sid].lower()] = ICON_TILES[k]
    for k, t in enumerate(SPARE_ICONS, 1):
        out['spare%d' % k] = t
    return out


HELP_WIDTH = 96          # the help pane shows about 100 pixels of each 128-pixel line


def _line(text, width_px=HELP_WIDTH):
    rows, w = N.render(text) if text else ([[0] * 8 for _ in range(16)], 1)
    used = max((x for row in rows for x, v in enumerate(row) if v), default=-1) + 1
    if used > width_px:
        raise ValueError('"%s" is %d pixels wide; the limit is %d' % (text, used, width_px))
    rows = [row[:128] + [0] * (128 - len(row[:128])) for row in rows]
    return N.to_tiles(rows, 16)


def wrap(text, width_px=HELP_WIDTH):
    """Split help text into lines that fit (a '/' forces a break)."""
    out = []
    for part in text.split('/'):
        words, cur = part.split(), ''
        for wd in words:
            t = (cur + ' ' + wd).strip()
            if _width(t) <= width_px:
                cur = t
            else:
                if cur:
                    out.append(cur)
                cur = wd
        out.append(cur)
    return out


def _width(text):
    rows, _ = N.render(text)
    return max((x for row in rows for x, v in enumerate(row) if v), default=-1) + 1


def desc_picture(name, lines):
    if len(lines) > 3:
        raise ValueError('help text needs %d lines; 3 fit (shorten it)' % len(lines))
    pic = b''.join(_line(t) for t in [name] + lines + [''] * (3 - len(lines)))
    assert len(pic) == DESC_SIZE
    return pic


class MenuError(Exception):
    pass


def build(rom, rows, region, space, far, meta_table):
    """rows: [(skill id, name, icon tile, type, help lines)] for the new rows.
    region: the kit's code region (fe4skillfx.Region); space: BankSpace; far: FreeSpace."""
    if not rows:
        return
    total = VANILLA_ROWS + len(rows)
    if total > MAX_ROWS:
        raise MenuError('the Skills menu holds %d rows; %d new skills fit (set menu=no on some)'
                        % (MAX_ROWS, MAX_ROWS - VANILLA_ROWS))
    # glyphs for the names
    cells = list(FREE_CELLS)
    texts = []
    for sid, name, icon, typ, lines in rows:
        r, w = N.render(name)
        used = max((x for row in r for x, v in enumerate(row) if v), default=-1) + 1
        if used > NAME_CELLS * 8:
            raise MenuError('%s is %d pixels wide; menu names fit in %d' % (name, used, NAME_CELLS * 8))
        w = (used + 7) // 8
        if w > len(cells):
            raise MenuError('out of room for new names in the Skills menu (57 glyph cells of 8 pixels); '
                            'use shorter names or set menu=no on some skills')
        tiles = N.to_tiles(r, len(r[0]) // 8)
        full = len(r[0]) // 8
        s = bytearray()
        for c in range(w):
            t = cells.pop(0)
            top = tiles[c * 16:c * 16 + 16]
            bot = tiles[(full + c) * 16:(full + c) * 16 + 16]
            rom[cell_addr(t):cell_addr(t) + 16] = top
            rom[cell_addr(t + 16):cell_addr(t + 16) + 16] = bot
            s += (0x100 + t).to_bytes(2, 'big')
        s += SPACE * (NAME_CELLS - w) + TYPES[typ] + b'\0\0'
        texts.append(bytes(s))
    # row strings and help pictures
    row_ptrs = [0x500000 | (ROW_TEXT + 32 * k) & 0xFFFF for k in range(VANILLA_ROWS)]
    desc_ptrs = [0x590000 | (DESC + DESC_SIZE * k) & 0xFFFF for k in range(VANILLA_ROWS)]
    for (sid, name, icon, typ, lines), s in zip(rows, texts):
        a = far.alloc(len(s))
        rom[a:a + len(s)] = s
        row_ptrs.append(a)
        pic = desc_picture(name, lines)
        a = far.alloc(len(pic))
        rom[a:a + len(pic)] = pic
        desc_ptrs.append(a)
    # list of skill IDs and help-pane icons
    ids = vanilla_rows(rom) + [r[0] for r in rows]
    fo, _ = space.alloc(0x870000, 2 * total)
    rom[fo:fo + 2 * total] = b''.join(i.to_bytes(2, 'little') for i in ids)
    for op in OPS_LIST:
        rom[op:op + 3] = (0x800000 | fo).to_bytes(3, 'little')
    icons = ICON_TILES + [r[2] for r in rows]
    fo, _ = space.alloc(0x870000, 2 * total)
    rom[fo:fo + 2 * total] = b''.join((t - 0x20).to_bytes(2, 'little') for t in icons)
    rom[OP_ICON:OP_ICON + 3] = (0x800000 | fo).to_bytes(3, 'little')
    # counts
    rom[OP_COUNT:OP_COUNT + 2] = total.to_bytes(2, 'little')
    rom[OP_LAST:OP_LAST + 2] = (total - 1).to_bytes(2, 'little')
    rom[OP_SCROLL:OP_SCROLL + 2] = (2 * (total - 12)).to_bytes(2, 'little')
    if total > 21:
        for (old, ops), new in ((BEARERS, NEW_BEARERS), (COUNTS, NEW_COUNTS)):
            for op in ops:
                assert rom[op:op + 3] == old.to_bytes(3, 'little'), hex(op)
                rom[op:op + 3] = new.to_bytes(3, 'little')
        rom[OP_CLEAR_B:OP_CLEAR_B + 2] = (0x40 * total).to_bytes(2, 'little')
        rom[OP_CLEAR_C:OP_CLEAR_C + 2] = (2 * total).to_bytes(2, 'little')
    # list icon sprite groups (7 rows each), in a bank that sees low RAM
    groups = []
    for g in range(0, total, 7):
        part = icons[g:g + 7]
        data = len(part).to_bytes(2, 'little') + b''.join(
            bytes([0x0F, 0xC2, 0x10 * i, t, 0x26]) for i, t in enumerate(part))
        fo, snes = space.alloc(0x810000, len(data))
        rom[fo:fo + len(data)] = data
        groups.append(snes)
    # tables in the code region
    tab = bytearray()
    for p in row_ptrs:
        tab += p.to_bytes(3, 'little')
    T_ROW = region.put(bytes(tab))
    tab = bytearray()
    for p in desc_ptrs:
        tab += p.to_bytes(3, 'little')
    T_DESC = region.put(bytes(tab))
    region.table('menu', meta_table)
    a = Asm(region.cur)
    # rows: draw every row's string (replaces 18 unrolled calls)
    a.label('rows')
    a.op('ldx', '#', 0)
    a.label('r_loop')
    a.op('phx')
    a.op('txa')
    a.op('asl')
    a.op('clc')
    a.op('adc', 'sr', 1)
    a.op('tax')
    a.op('lda', 'long,x', T_ROW + 1)
    a.op('sta', 'dp', 0x25)
    a.op('lda', 'long,x', T_ROW)
    a.op('sta', 'dp', 0x24)
    a.op('lda', 'sr', 1)
    a.op('xba')
    a.op('asl')
    a.op('tax')                                 # X = row * $200
    a.op('jsl', 'long', 0x879354)
    a.op('plx')
    a.op('inx')
    a.op('cpx', '#', total)
    a.op('bne', 'rel', 'r_loop')
    a.op('jml', 'long', SITE_ROWS[1])
    # desc: A = row*2 on entry (from $8B:D986); pushes as the original, then DMAs the picture
    a.label('desc')
    a.op('sta', 'abs', 0x140C)
    a.op('lda', 'dp', 0x00)
    a.op('pha')
    a.op('lda', 'dp', 0x02)
    a.op('pha')
    a.op('lda', 'dp', 0x24)
    a.op('pha')
    a.op('lda', 'dp', 0x25)
    a.op('pha')
    a.op('phx')
    a.op('phy')
    a.op('lda', 'abs', 0x140C)
    a.op('lsr')
    a.op('pha')
    a.op('asl')
    a.op('clc')
    a.op('adc', 'sr', 1)
    a.op('tax')
    a.op('pla')
    a.op('lda', 'long,x', T_DESC + 1)
    a.op('sta', 'dp', 0x25)
    a.op('lda', 'long,x', T_DESC)
    a.op('sta', 'dp', 0x24)
    a.op('sta', 'abs', 0x140C)
    a.op('lda', '#', 0x0800)
    a.op('sta', 'dp', 0x00)
    a.op('lda', '#', 0x1400)
    a.op('sta', 'dp', 0x02)
    a.op('jsl', 'long', 0x80A58C)
    a.op('jml', 'long', SITE_DESC[1])
    # icons: the list's sprite groups, 7 rows ($70 px) apart, scrolled by $85
    a.label('icons')
    a.op('phb')
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 0x81)
    a.op('pha')
    a.op('plb')
    a.op('rep', '#8', 0x20)
    for g, snes in enumerate(groups):
        a.op('lda', '#', 0x19 + 0x70 * g)
        a.op('sec')
        a.op('sbc', 'dp', 0x85)
        a.op('sta', 'dp', 0x02)
        a.op('stz', 'dp', 0x00)
        a.op('stz', 'dp', 0x08)
        a.op('stz', 'dp', 0x0A)
        a.op('ldy', '#', snes & 0xFFFF)
        a.op('jsl', 'long', 0x8087C7)
    a.op('plb')
    a.op('rtl')
    code = a.assemble()
    region.put(code)
    L = a.labels
    _jump(rom, SITE_ROWS[0], L['rows'], bytes.fromhex('a90050'))
    _jump(rom, SITE_DESC[0], L['desc'], bytes.fromhex('0a0a0a0a'))
    assert rom[SITE_ICONS:SITE_ICONS + 3] == bytes.fromhex('a91900')
    rom[SITE_ICONS:SITE_ICONS + 5] = bytes([0x22]) + L['icons'].to_bytes(3, 'little') + b'\x60'


def _jump(rom, fo, target, expect):
    assert rom[fo:fo + len(expect)] == expect, 'menu hook site %06X already changed' % fo
    rom[fo:fo + 4] = bytes([0x5C]) + target.to_bytes(3, 'little')


def read_meta(rom, addr):
    """menu table -> {id: {'icon': tile, 'type': name, 'description': text}}"""
    out = {}
    inv_t = {k: n for n, k in enumerate(TYPES)}
    while addr and rom[addr]:
        sid, icon, typ, n = rom[addr:addr + 4]
        out[sid] = {'icon': icon, 'type': list(TYPES)[typ], 'description':
                    bytes(rom[addr + 4:addr + 4 + n]).decode('ascii', 'replace')}
        addr += 4 + n
    return out


def meta_bytes(entries):
    """entries: [(id, icon tile, type, description text)]"""
    out = bytearray()
    for sid, icon, typ, text in entries:
        t = text.encode('ascii', 'replace')[:255]
        out += bytes([sid, icon, list(TYPES).index(typ), len(t)]) + t
    return bytes(out + b'\0')
