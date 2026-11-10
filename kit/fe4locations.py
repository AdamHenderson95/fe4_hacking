#!/usr/bin/env python3
"""FE4 chapter sites: castles, villages, castle-town facilities, armory stock,
village gold and arena opponents.

Chapter info pointers: $86:C760 (13 x ptr24; the 13th is unused).  Each info
block starts with five word pointers into its own bank:
  +0 location list   [count] [word ptr] x count
  +2 (map changes?)  not decoded
  +4 arena           [melee list ptr][ranged list ptr], each 7 unit IDs + $FFFF
                     (0 = no arena table; the Arena button needs facility bit $04)
  +6, +8             not decoded

Location record:
  +0 index in this chapter (event condition $0A COND_VISIT uses it)
  +1 castle name ID (castles only; names at 0x505000 + 16*id, +8 text)
  +2 kind: 0 castle, 2 village  (per-kind table at $87:F453: +0 village gold,
     +2..+5 footprint)
  +3 x, +4 y
castles add 3 bytes:
  +5 facilities (castle-town buttons): $80 Armory, $40 Pawnbroker,
     $20 Blacksmith, $10 Supply, $08 Augury, $04 Arena
  +6 armory stock: word pointer (same bank) to item instance bytes ending
     $FF $FF.  At chapter start ($87:EBC8) each listed instance that is still
     unused (status 7) is put on sale (status 4) at this castle.

Village gold: every village starts with the kind-2 amount (5000) in
$7E:4E55 + 2*index.  Per-village amounts are added by a small hook at
$7D:F000 that replaces JSL $87F391 at $87:EBEA and looks the record up in a
table of [record ptr16][bank][gold16] entries ending $FFFF.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
from dis65816 import snes_to_file

INFO_TABLE = 0x06C760
CHAPTERS = 12
CASTLE_NAMES = 0x505000
KIND_TABLE = 0x07F453
KINDS = {0: 'castle', 1: 'site1', 2: 'village', 3: 'site3', 4: 'site4', 5: 'site5', 6: 'site6'}
KINDS_INV = {v: k for k, v in KINDS.items()}
FACILITIES = [(0x80, 'Armory'), (0x40, 'Pawnbroker'), (0x20, 'Blacksmith'), (0x10, 'Supply'),
              (0x08, 'Augury'), (0x04, 'Arena'), (0x02, 'bit1'), (0x01, 'bit0')]
FAC_INV = {n.lower(): b for b, n in FACILITIES}

HOOK_CALL = 0x07EBEA            # JSL $87F391 (kind -> village gold) at chapter start
HOOK_ADDR = 0x7DF000            # reserved: maps stop allocating at $7D:F000
HOOK_END = 0x7E0000
GUARD = 32                      # bytes left untouched after a bank's last data


def _p24(rom, fo):
    return rom[fo] | rom[fo + 1] << 8 | rom[fo + 2] << 16


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def castle_name(rom, cid):
    a = CASTLE_NAMES + 16 * cid
    return L.decode(rom[a + 8:a + 16]) if cid < 0x40 else ''


def info_block(rom, ch):
    """(snes address, file offset) of a chapter's info block."""
    a = _p24(rom, INFO_TABLE + 3 * ch)
    return a, snes_to_file(a)


def records(rom):
    """[(chapter, file_offset, size)] for every location record."""
    return [(ch, q, n) for ch, q, n, _ in _records(rom)]


def _records(rom):
    out = []
    for ch in range(CHAPTERS):
        a, fo = info_block(rom, ch)
        bank = a & 0xFF0000
        lf = snes_to_file(bank | _w(rom, fo))
        for i in range(rom[lf]):
            sn = bank | _w(rom, lf + 1 + 2 * i)
            q = snes_to_file(sn)
            out.append((ch, q, 8 if rom[q + 2] == 0 else 5, sn))
    return out


def kind_gold(rom, kind):
    return _w(rom, KIND_TABLE + _w(rom, KIND_TABLE + 2 * kind))


def _byte_list(rom, fo):
    out = []
    while _w(rom, fo + len(out)) != 0xFFFF:
        out.append(rom[fo + len(out)])
        if len(out) > 255:
            raise ValueError('unterminated list at %06X' % fo)
    return out


def _word_list(rom, fo):
    out = []
    while _w(rom, fo + 2 * len(out)) != 0xFFFF:
        out.append(_w(rom, fo + 2 * len(out)))
        if len(out) > 64:
            raise ValueError('unterminated list at %06X' % fo)
    return out


def shop_list(rom, q, bank):
    p = _w(rom, q + 6)
    return None if p == 0 else _byte_list(rom, snes_to_file(bank | p))


# ---------------------------------------------------------------- village gold hook
def _hook_installed(rom):
    return rom[HOOK_CALL] == 0x22 and _p24(rom, HOOK_CALL + 1) == HOOK_ADDR


def _hook_table(rom):
    """{record snes addr: gold} from an installed hook."""
    if not _hook_installed(rom):
        return {}
    t = HOOK_ADDR + _HOOK_TABLE_OFF
    out = {}
    while _w(rom, t) != 0xFFFF:
        out[rom[t + 2] << 16 | _w(rom, t)] = _w(rom, t + 3)
        t += 5
    return out


def _hook_code(table):
    """65816 code: A = kind, Y = record ptr, DB = record bank.  Returns gold in A."""
    T = table

    def lng(op, off):
        a = T + off
        return [op, a & 0xFF, (a >> 8) & 0xFF, a >> 16]
    c = [0x08, 0xC2, 0x30, 0xDA, 0x48, 0xA2, 0x00, 0x00]          # PHP REP#$30 PHX PHA LDX#0
    loop = len(c)
    c += lng(0xBF, 0) + [0xC9, 0xFF, 0xFF, 0xF0, None]               # LDA T,X CMP#$FFFF BEQ nf
    beq_nf = len(c) - 1
    c += [0x98] + lng(0xDF, 0) + [0xD0, None]                        # TYA CMP T,X BNE next
    bne1 = len(c) - 1
    c += [0xE2, 0x20, 0x8B, 0x68] + lng(0xDF, 2) + [0xC2, 0x20, 0xD0, None]  # SEP PHB PLA CMP T+2,X REP BNE
    bne2 = len(c) - 1
    c += lng(0xBF, 3) + [0xFA, 0xFA, 0x28, 0x6B]                     # LDA T+3,X PLX PLX PLP RTL
    nxt = len(c)
    c += [0xE8] * 5 + [0x80, None]                                   # INX x5 BRA loop
    c[-1] = (loop - len(c)) & 0xFF
    nf = len(c)
    c += [0x68, 0xFA, 0x28, 0x5C, 0x91, 0xF3, 0x87]                  # PLA PLX PLP JML $87F391
    c[beq_nf] = nf - (beq_nf + 1)
    c[bne1] = nxt - (bne1 + 1)
    c[bne2] = nxt - (bne2 + 1)
    return bytes(c)


_HOOK_TABLE_OFF = 0x60


def _install_hook(rom, gold_by_rec):
    table = HOOK_ADDR + _HOOK_TABLE_OFF
    code = _hook_code(table)
    assert len(code) <= _HOOK_TABLE_OFF
    data = bytearray()
    for sn, g in sorted(gold_by_rec.items()):
        data += bytes([sn & 0xFF, (sn >> 8) & 0xFF, sn >> 16, g & 0xFF, g >> 8])
    data += b'\xff\xff'
    if table + len(data) > HOOK_END:
        raise SystemExit('village gold table is too large')
    rom[HOOK_ADDR:HOOK_ADDR + len(code)] = code
    rom[table:table + len(data)] = data
    rom[HOOK_CALL:HOOK_CALL + 4] = bytes([0x22, HOOK_ADDR & 0xFF, (HOOK_ADDR >> 8) & 0xFF, HOOK_ADDR >> 16])


def village_gold(rom):
    """{record snes addr: gold} for every village (default or per-village)."""
    over = _hook_table(rom)
    return {sn: over.get(sn, kind_gold(rom, rom[q + 2]))
            for ch, q, n, sn in _records(rom) if rom[q + 2] != 0}


# ---------------------------------------------------------------- free space in info banks
BankSpace = L.BankSpace


# ---------------------------------------------------------------- locations.csv
FIELDS = ['chapter', 'index', 'kind', 'castle_id', '_castle_name', 'x', 'y', 'facilities',
          'gold', 'shop', '_shop_items']


def _fac_str(v):
    return ';'.join(n for b, n in FACILITIES if v & b) or '-'


def _fac_parse(s):
    s = s.strip()
    if s in ('', '-', 'none'):
        return 0
    v = 0
    for t in s.replace(',', ';').split(';'):
        t = t.strip()
        if not t:
            continue
        if t.lower() not in FAC_INV:
            raise ValueError('unknown facility %r (use %s)' % (t, ', '.join(n for _, n in FACILITIES[:6])))
        v |= FAC_INV[t.lower()]
    return v


def export(rom, path):
    inames = L.item_names(rom)
    gold = village_gold(rom)

    def iname(x):
        return inames[rom[L.INSTANCES + x]] if x < L.INSTANCE_COUNT else '?'
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for ch, q, n, sn in _records(rom):
            r = rom[q:q + n]
            castle = r[2] == 0
            row = {'chapter': ch, 'index': r[0], 'kind': KINDS.get(r[2], str(r[2])),
                   'castle_id': r[1], '_castle_name': castle_name(rom, r[1]) if castle else '',
                   'x': r[3], 'y': r[4]}
            if castle:
                sl = shop_list(rom, q, sn & 0xFF0000)
                row.update(facilities=_fac_str(r[5]), shop=';'.join(str(x) for x in sl or []),
                           _shop_items=' / '.join(iname(x) for x in sl or []))
            else:
                row['gold'] = gold[sn]
            w.writerow(row)
    print('wrote', path)


def apply(rom, path, space=None):
    if not os.path.exists(path):
        return 0
    space = space or BankSpace(rom)
    recs = {(ch, rom[q]): (q, n, sn) for ch, q, n, sn in _records(rom)}
    old_gold = village_gold(rom)
    new_gold = dict(old_gold)
    changes = 0
    for ln, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
        try:
            key = (int(row['chapter']), int(row['index']))
        except (ValueError, KeyError) as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        if key not in recs:
            raise SystemExit(f'{path}:{ln}: no location {key[1]} in chapter {key[0]} (rows cannot be added yet)')
        q, n, sn = recs[key]
        new = bytearray(rom[q:q + n])
        kind = row['kind'].strip()
        k = KINDS_INV.get(kind)
        try:
            if k is None:
                k = int(kind, 0)
            if (k == 0) != (n == 8):
                raise SystemExit(f'{path}:{ln}: a castle cannot become another kind (or the reverse) yet')
            new[1] = int(row['castle_id'], 0)
            new[2] = k
            new[3] = int(row['x'], 0)
            new[4] = int(row['y'], 0)
            if n == 8:
                if 'facilities' in row:
                    new[5] = _fac_parse(row['facilities'])
                elif row.get('flags', '').strip():            # v5 projects
                    new[5] = int(row['flags'], 0)
                if 'shop' in row:
                    changes += _apply_shop(rom, new, row['shop'], sn, space, f'{path}:{ln}')
                elif row.get('home_ptr', '').strip():          # v5 projects
                    hp = int(row['home_ptr'], 16)
                    new[6], new[7] = hp & 0xFF, hp >> 8
            elif row.get('gold', '').strip():
                g = int(row['gold'], 0)
                if not 1 <= g <= 50000:
                    raise SystemExit(f'{path}:{ln}: village gold must be 1-50000')
                new_gold[sn] = g
        except ValueError as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        if not (0 <= new[3] < 64 and 0 <= new[4] < 64):
            raise SystemExit(f'{path}:{ln}: x and y must be 0-63')
        if new != rom[q:q + n]:
            rom[q:q + n] = new
            changes += 1
    if new_gold != old_gold:
        over = {sn: g for sn, g in new_gold.items() if g != kind_gold(rom, 2)}
        _install_hook(rom, over)
        changes += 1
    return changes


def _apply_shop(rom, rec, text, rec_snes, space, where):
    """Update rec[6:8] (armory stock pointer) for a shop list; writes list data."""
    items = []
    for t in text.replace(',', ';').split(';'):
        t = t.strip()
        if t:
            v = int(t, 0)
            if not 0 <= v < L.INSTANCE_COUNT:
                raise SystemExit(f'{where}: shop item {v} is not an item instance (0-{L.INSTANCE_COUNT - 1})')
            items.append(v)
    if len(set(items)) != len(items):
        raise SystemExit(f'{where}: a shop lists the same item instance twice')
    bank = rec_snes & 0xFF0000
    p = rec[6] | rec[7] << 8
    old = None if p == 0 else _byte_list(rom, snes_to_file(bank | p))
    if (old or []) == items:
        return 0
    if not items:
        rec[6] = rec[7] = 0
        return 1
    data = bytes(items) + b'\xff\xff'
    if old is not None and len(items) <= len(old):
        fo = snes_to_file(bank | p)
        rom[fo:fo + len(data)] = data
        return 1
    fo, sn = space.alloc(bank, len(data))
    rom[fo:fo + len(data)] = data
    rec[6], rec[7] = sn & 0xFF, (sn >> 8) & 0xFF
    return 1


# ---------------------------------------------------------------- arena.csv
ARENA_FIELDS = ['chapter', 'rank', 'melee', '_melee_name', 'ranged', '_ranged_name']
ARENA_RANKS = 7


def arena_lists(rom, ch):
    """(melee unit IDs, ranged unit IDs) or None when the chapter has no arena table."""
    a, fo = info_block(rom, ch)
    p = _w(rom, fo + 4)
    if p == 0:
        return None
    bank = a & 0xFF0000
    t = snes_to_file(bank | p)
    return (_word_list(rom, snes_to_file(bank | _w(rom, t))),
            _word_list(rom, snes_to_file(bank | _w(rom, t + 2))))


def export_arena(rom, path):
    import fe4events as EV
    com = EV.Commenter(rom)
    nm = lambda u: com.unit(u).rsplit('(', 1)[0]  # noqa: E731
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ARENA_FIELDS)
        w.writeheader()
        for ch in range(CHAPTERS):
            al = arena_lists(rom, ch)
            if al is None:
                continue
            for r in range(max(len(al[0]), len(al[1]))):
                m = al[0][r] if r < len(al[0]) else ''
                g = al[1][r] if r < len(al[1]) else ''
                w.writerow({'chapter': ch, 'rank': r + 1, 'melee': m, '_melee_name': nm(m) if m != '' else '',
                            'ranged': g, '_ranged_name': nm(g) if g != '' else ''})
    print('wrote', path)


def apply_arena(rom, path, space=None):
    if not os.path.exists(path):
        return 0
    space = space or BankSpace(rom)
    want = {}
    for ln, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
        try:
            ch, rank = int(row['chapter']), int(row['rank'])
            pair = [int(row[k], 0) if row.get(k, '').strip() else None for k in ('melee', 'ranged')]
        except (ValueError, KeyError) as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        if not 0 <= ch < CHAPTERS:
            raise SystemExit(f'{path}:{ln}: chapter must be 0-{CHAPTERS - 1}')
        for u in pair:
            if u is not None and not 1 <= u <= L.unit_count(rom):
                raise SystemExit(f'{path}:{ln}: unit {u} is not a unit ID (1-{L.unit_count(rom)})')
        want.setdefault(ch, {})[rank] = pair
    changes = 0
    for ch, ranks in sorted(want.items()):
        lists = []
        for i, col in enumerate(('melee', 'ranged')):
            vals = [ranks[r][i] for r in sorted(ranks)]
            n = len(vals)
            while n and vals[n - 1] is None:
                n -= 1
            if sorted(ranks)[:n] != list(range(1, n + 1)) or None in vals[:n]:
                raise SystemExit(f'{path}: chapter {ch} {col} opponents must fill ranks 1-{n} with no gaps')
            if n < ARENA_RANKS:
                raise SystemExit(f'{path}: chapter {ch} needs {col} opponents for all {ARENA_RANKS} ranks')
            lists.append(vals[:n])
        mel, rng = lists
        cur = arena_lists(rom, ch)
        if cur is not None and (cur[0], cur[1]) == (mel, rng):
            continue
        a, fo = info_block(rom, ch)
        bank = a & 0xFF0000
        lists = []
        for i, new in enumerate((mel, rng)):
            data = b''.join(u.to_bytes(2, 'little') for u in new) + b'\xff\xff'
            if cur is not None and len(new) <= len(cur[i]):
                t = snes_to_file(bank | _w(rom, fo + 4))
                lf = snes_to_file(bank | _w(rom, t + 2 * i))
                rom[lf:lf + len(data)] = data
                lists.append(None)
            else:
                lists.append(data)
        if cur is None:
            tf, tsn = space.alloc(bank, 4)
            rom[fo + 4:fo + 6] = (tsn & 0xFFFF).to_bytes(2, 'little')
            rom[tf:tf + 4] = b'\0\0\0\0'
        t = snes_to_file(bank | _w(rom, fo + 4))
        for i, data in enumerate(lists):
            if data is None:
                continue
            lf, lsn = space.alloc(bank, len(data))
            rom[lf:lf + len(data)] = data
            rom[t + 2 * i:t + 2 * i + 2] = (lsn & 0xFFFF).to_bytes(2, 'little')
        changes += 1
    return changes
