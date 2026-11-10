#!/usr/bin/env python3
"""Generation 2: who the children's parents are, what they inherit, and who loves whom.

How FE4 does it (Project Naga ROM):
  * At the end of chapter 5, $84:8200 walks the table at $84:8237 (unit, action,
    param): mothers get action 2 (make their children, then leave), the other gen-1
    units action 0 (leave), Finn action 1 (becomes his gen-2 record 34).
  * Action 2 ($84:BAA1) looks up the mother's two children in $83:8993 (by her army
    slot), needs her to be alive (except Deirdre and Ethlyn) and married (lover =
    unit data +3), then creates each child with $84:931A ($00 = father, $02 = mother)
    and sets the child's "born" flag from $84:BB1E (scenes test it to choose the
    child or the substitute).
  * Creating a child ($84:8F83) copies both parents and then:
      growths  = same-gender parent + other parent / 2          ($87:A9EA)
      stats    = (2 x same-gender parent + other) / 10 + level-ups ($87:A83A, capped 15)
      blood    = heir's blood + the other parent's halved          ($87:A9FB)
      skills   = (mother | father) & the child's mask ($87:A975, 3 bytes per child)
      gold     = (mother + father) / 10 + 2000
      items    = everything the heir parent carries ($87:AA39)
    The heir is the child record's byte 11 (1 = father, 0 = mother).
  * Love: each woman has 15 (gen 1) or 23 (gen 2) love counters, one per man.  The
    starting value and the growth per turn come from byte tables at $83:850F and
    $83:8738 (offset per woman, then one byte per man); 500 = lovers.

The kit replaces the mother-only step with its own: any unit can be a child's parent
(the "anchor"); the other parent is whoever the anchor married.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
import fe4skillfx as FX
from asm65816 import Asm

TRANSITION = 0x048237
MOTHERS = 0x038993            # 9 offsets (Deirdre..Bridget, by army slot - 16), then child pairs
FLAGS = 0x04BB1E              # born flag per pair entry (same offsets)
MASKS = 0x07A975              # 3 bytes per child id 25..63
SUBS = 0x11AEF2               # (substitute, child) word pairs, 14
ALWAYS = (16, 17)             # Deirdre and Ethlyn: children even though they are gone by then
SITE_TRANS = 0x048204         # LDY #$8237 at the start of the transition
SITE_MASK = 0x07A8E1          # LDA $0000,Y; SEC; SBC #$19; ... TAX  (14 bytes)
OP_MASK = (0x07A8F8, 0x07A907)  # AND $87A975,X / AND $87A976,X operands
SITE_GROW = (0x07A9EA, bytes.fromhex('a504f004'), 0x87A9FA)   # growth combine; RTS
SITE_STAT = (0x07A83E, bytes.fromhex('a506f004'), 0x87A866)   # stat combine; PLP PLB RTS
GOLD_DIV, GOLD_BASE = 0x07A74F, 0x07A75D
STAT_CAP = (0x51630D, 0x516311)
CREATE_UNIT, FIND_UNIT, LOVER, GENDER, FLAGS_OF, SET_FLAG = (0x84931A, 0x8484B4, 0x849635, 0x84A3E5,
                                                            0x8495E5, 0x8680BE)
ENT = 16
CHILD_HEAP, UNIT_HEAP, CHILD_OBJ = 0x2D4F, 0x3131, 0x34   # WRAM heaps; child unit object size
LOVE_HEAP = 0x3BD7                        # women's love counters: 9 x (30 + 6) bytes
SITE_HEAP = 0x048FDF                      # LDA #$2D4F; STA $24 in the child creation ($84:8F83)
SITE_MOTHER = 0x04A40D                    # a child's mother, from FE4's own table (status screen)
SITE_HEAP_LOAD = 0x07F611                 # the same when a save is loaded ($87:F60B)
SUB_OPS = (0x11AEC1, 0x11AEE2)            # LDA $91AEF2,X operands (substitute pairs)
SLOT_OP = 0x11AECF                        # LDA $91AF2C,X operand (army slot per pair)
JOIN_CHAPTERS = range(6, 12)              # chapter numbers whose opening scene can add a child
NEW_FLAG_BASE = 0x80                      # born flags for new children (the game's scripts use < 0x60)

# love tables
MALES, FEMALES = 0x03848D, 0x0384DB       # unit ids per love index, ended by $FFFF
LOVE_START, LOVE_GROW = 0x03850F, 0x038738
OPS_START = (0x07AC06, 0x07AC0E)          # LDA $83850F,X operands
OPS_GROW = (0x07AD53, 0x07AD5B)           # LDA $838738,X operands
GEN1_MEN, GEN1_WOMEN = 15, 9


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


# ---------------------------------------------------------------- reading the game's own data
def vanilla(rom):
    """{child id: {...}} straight from the game's tables."""
    out = {}
    offs = [_w(rom, MOTHERS + 2 * i) for i in range(9)]
    for i, o in enumerate(offs):
        for k in range(2):
            c = _w(rom, MOTHERS + o + 2 * k)
            if not c:
                continue
            f = _w(rom, FLAGS + o + 2 * k)
            out[c] = {'parent': 16 + i, 'born_flag': None if f == 0xFFFF else f, 'always': 16 + i in ALWAYS}
    for k in range(14):
        s, c = _w(rom, SUBS + 4 * k), _w(rom, SUBS + 4 * k + 2)
        out.setdefault(c, {})['substitute'] = s
    return out


def vanilla_flags(rom):
    """{child: born flag} of the game's own children (the table the kit leaves alone)."""
    return {c: d['born_flag'] for c, d in vanilla(rom).items() if d.get('born_flag') is not None}


def _long(rom, fo):
    from dis65816 import snes_to_file
    return snes_to_file(rom[fo] | rom[fo + 1] << 8 | rom[fo + 2] << 16)


def sub_pairs(rom):
    """[(substitute, child, army slot)] from the game's table (or the kit's copy)."""
    t, sl = _long(rom, SUB_OPS[0]), _long(rom, SLOT_OP)
    out = []
    k = 0
    while _w(rom, t + 4 * k):
        out.append((_w(rom, t + 4 * k), _w(rom, t + 4 * k + 2), rom[sl + k]))
        k += 1
    return out


def child_rows(rom):
    return L.unit_rows(rom, 1)


def default_weights(gender):
    """(growth from father, from mother, stats from father, from mother) in %"""
    return (100, 50, 20, 10) if gender == 0 else (50, 100, 10, 20)


def current(rom):
    """The ROM's current gen-2 setup: {child id: row dict} (reads the kit's table when present)."""
    t = FX.table_addr(rom, 'gen2')
    rows = {}
    recs = {idx: a for idx, a, _, _ in child_rows(rom)}
    if t:
        while _w(rom, t):
            cid = _w(rom, t)
            a = _w(rom, t + 2)
            f = _w(rom, t + 4)
            rows[cid] = {'parent': a or None, 'born_flag': None if f == 0xFFFF else f,
                         'always': bool(rom[t + 6]), 'weights': tuple(rom[t + 7:t + 11]),
                         'mask': int.from_bytes(rom[t + 11:t + 14], 'little'), 'order': len(rows),
                         'joins': rom[t + 14] or None}
            t += ENT
    else:
        v = vanilla(rom)
        for cid in sorted(recs):
            d = v.get(cid, {})
            g = rom[recs[cid] + 8]
            m = int.from_bytes(rom[MASKS + 3 * (cid - 25):MASKS + 3 * (cid - 25) + 3], 'little') \
                if 25 <= cid <= 63 else 0
            rows[cid] = {'parent': d.get('parent'), 'born_flag': d.get('born_flag'), 'always': d.get('always', False),
                         'weights': default_weights(g), 'mask': m, 'joins': None}
        order = []
        for i in range(9):
            o = _w(rom, MOTHERS + 2 * i)
            order += [_w(rom, MOTHERS + o), _w(rom, MOTHERS + o + 2)]
        for n, c in enumerate([c for c in order if c in rows] + [c for c in rows if c not in order]):
            rows[c]['order'] = n
    subs = {c: sb for sb, c, _ in sub_pairs(rom)}
    for cid, r in rows.items():
        r['substitute'] = subs.get(cid)
    return rows


# ---------------------------------------------------------------- CSV
COLUMNS = ['parent', 'always', 'born_flag', 'substitute', 'joins', 'inherit_skills',
           'growth_father', 'growth_mother', 'stats_father', 'stats_mother']


def unit_label(rom):
    names = {}
    for k in range(4):
        for idx, _, _, lab in L.unit_rows(rom, k):
            names[idx] = lab
    return names


def _label(names, look, idx):
    if idx is None:
        return ''
    n = names.get(idx, '')
    return n if n and look.get(n.lower()) == idx else str(idx)


def extra_cols(rom, cache={}):
    """{child id: extra columns for units_children.csv}"""
    key = id(rom)
    if cache.get('key') != key:
        import fe4skills as SK
        look = SK._unit_lookup(rom)
        names = unit_label(rom)
        rows = current(rom)
        out = {}
        for cid, r in rows.items():
            gf, gm, sf, sm = r['weights']
            out[cid] = {'parent': _label(names, look, r['parent']),
                        'always': 'yes' if r['always'] else '',
                        'born_flag': '' if r['born_flag'] is None else r['born_flag'],
                        'substitute': _label(names, look, r['substitute']),
                        'joins': r['joins'] or '',
                        'inherit_skills': L.skillset_decode('personal', r['mask'].to_bytes(3, 'little')),
                        'growth_father': gf, 'growth_mother': gm, 'stats_father': sf, 'stats_mother': sm}
        cache.update(key=key, out=out, order={c: r['order'] for c, r in rows.items()})
    return cache['out']


def rules(rom):
    return {'gold_divisor': _w(rom, GOLD_DIV), 'gold_base': _w(rom, GOLD_BASE), 'stat_cap': rom[STAT_CAP[0]]}


def export_rules(rom, path):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rule', 'value', '_meaning'])
        r = rules(rom)
        w.writerow(['gold_divisor', r['gold_divisor'], "child's gold = (mother's + father's) / this + gold_base"])
        w.writerow(['gold_base', r['gold_base'], ''])
        w.writerow(['stat_cap', r['stat_cap'], 'highest inherited Str/Mag/Skl/Spd/Def/Res (not HP or Lck)'])


# ---------------------------------------------------------------- love tables
def love_lists(rom):
    def lst(fo):
        out = []
        while _w(rom, fo) < 0x8000:
            out.append(_w(rom, fo))
            fo += 2
        return out
    return lst(MALES), lst(FEMALES)


def love_tables(rom):
    """{(woman love index, man love index): (start byte, growth byte)} for the pairs the game stores."""
    men, women = love_lists(rom)
    sb = (FX.table_addr(rom, 'love') or 0)
    if sb:
        start, grow = _w(rom, sb) | rom[sb + 2] << 16, _w(rom, sb + 3) | rom[sb + 5] << 16
    else:
        start, grow = 0x830000 | (LOVE_START & 0xFFFF), 0x830000 | (LOVE_GROW & 0xFFFF)
    from dis65816 import snes_to_file
    sf, gf = snes_to_file(start), snes_to_file(grow)
    out = {}
    for wi in range(len(women)):
        mrange = range(GEN1_MEN) if wi < GEN1_WOMEN else range(GEN1_MEN, len(men))
        so, go = _w(rom, sf + 2 * wi), _w(rom, gf + 2 * wi)
        for mi in mrange:
            out[(wi, mi)] = (rom[sf + so + mi], rom[gf + go + mi])
    return out


def _start_text(b):
    return 'no' if b == 0xFF else ('499' if b == 0xFE else str(b * 10))


def export_lovers(rom, path):
    men, women = love_lists(rom)
    names = unit_label(rom)
    t = love_tables(rom)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['woman', 'man', 'start', 'growth', '_woman', '_man'])
        for (wi, mi), (s, g) in sorted(t.items()):
            gv = -(g & 0x7F) if g & 0x80 else g
            w.writerow([women[wi], men[mi], _start_text(s), gv, names.get(women[wi], ''), names.get(men[mi], '')])


def export(rom, proj):
    export_lovers(rom, os.path.join(proj, 'lovers.csv'))
    export_rules(rom, os.path.join(proj, 'gen2_rules.csv'))


# ---------------------------------------------------------------- apply
def _unit_ref(rom, text, where, look, allow_blank=True):
    t = text.strip()
    if not t:
        if allow_blank:
            return None
        raise SystemExit(f'{where}: needs a unit')
    if t.isdigit():
        return int(t)
    if t.lower() in look:
        return look[t.lower()]
    same = [str(idx) for k in range(4) for idx, _, _, lab in L.unit_rows(rom, k) if lab.lower() == t.lower()]
    if same:
        raise SystemExit(f"{where}: several units are called {t} (indices {', '.join(same)}); write the index")
    raise SystemExit(f'{where}: unknown unit {t!r}')


def _pct(row, col, default, where):
    v = (row.get(col) or '').strip()
    if v == '':
        return default
    try:
        n = int(v)
    except ValueError:
        raise SystemExit(f'{where}: {col} must be a number (percent)')
    if not 0 <= n <= 255:
        raise SystemExit(f'{where}: {col} must be 0-255')
    return n


def read_children(rom, proj):
    """units_children.csv -> ordered list of row dicts (or None if the file has no gen-2 columns)."""
    path = os.path.join(proj, 'units_children.csv')
    if not os.path.exists(path):
        return None
    import fe4skills as SK
    look = SK._unit_lookup(rom)
    rows = []
    with open(path, newline='') as f:
        rd = csv.DictReader(f)
        if 'parent' not in (rd.fieldnames or []):
            return None
        for ln, r in enumerate(rd, start=2):
            where = f'{path}:{ln}'
            cid = int(r['index'])
            gender = int((r.get('gender') or '0').strip() or 0)
            gf, gm, sf, sm = default_weights(gender)
            flag = (r.get('born_flag') or '').strip()
            try:
                mask = int.from_bytes(L.skillset_encode('personal', r.get('inherit_skills') or ''), 'little')
            except ValueError as e:
                raise SystemExit(f'{where}: inherit_skills: {e}')
            if 'inherit_skills' not in r or (r.get('inherit_skills') or '').strip() == '':
                mask = None                   # new child: everything; the game's own: nothing
            j = (r.get('joins') or '').strip().lower().removeprefix('ch').removeprefix('chapter').strip()
            if j and (not j.isdigit() or int(j) not in JOIN_CHAPTERS):
                raise SystemExit(f'{where}: joins must be a chapter number 6-11 (or blank)')
            rows.append({
                'id': cid, 'line': ln, 'where': where,
                'joins': int(j) if j else None,
                'slot_blank': (r.get('slot') or '').strip() == '',
                'parent': _unit_ref(rom, r.get('parent') or '', where + ': parent', look),
                'always': (r.get('always') or '').strip().lower() in ('yes', 'y', '1', 'true'),
                'born_flag': int(flag, 0) if flag else None,
                'substitute': _unit_ref(rom, r.get('substitute') or '', where + ': substitute', look),
                'mask': mask,
                'weights': (_pct(r, 'growth_father', gf, where), _pct(r, 'growth_mother', gm, where),
                            _pct(r, 'stats_father', sf, where), _pct(r, 'stats_mother', sm, where)),
            })
            if rows[-1]['born_flag'] is not None and not 0 <= rows[-1]['born_flag'] <= 255:
                raise SystemExit(f'{where}: born_flag must be 0-255 (event flag)')
    return rows


def _same_as_vanilla(rom, rows):
    cur = current(rom)
    if {r['id'] for r in rows} != set(cur):
        return False
    for r in rows:
        d = cur[r['id']]
        for k in ('parent', 'always', 'born_flag', 'mask', 'weights', 'joins'):
            if r[k] != d[k]:
                return False
    return True


_pending = {}


def apply(rom, proj, space, added=()):
    """Parent links, inheritance and love (runs with the unit tables).  The script side
    (substitutes, joining) runs later in apply_scenes, after the project's own events."""
    changes = 0
    rows = read_children(rom, proj)
    if rows is not None:
        _check_rows(rom, rows, set(added))
        n = sum(1 for r in rows if r['parent'] is not None)
        if n > 18:
            print(f'note: {n} children can be born. FE4\'s save slot is nearly full at the start of '
                  f'chapter 6 (about 1900 of 1982 bytes with its own 17); each extra child born adds about '
                  f'50 bytes, so more than one extra can break saving. Substitutes cost nothing extra.')
        if not _same_as_vanilla(rom, rows):
            _install(rom, rows, space)
            changes += 1
        _pending[id(rom)] = rows
    changes += _apply_rules(rom, proj)
    changes += _apply_lovers(rom, proj)
    return changes


def _check_rows(rom, rows, added):
    vflags = vanilla_flags(rom)
    look = {idx: a for idx, a, _, _ in child_rows(rom)}
    seen = set()
    for r in rows:
        if r['id'] in seen:
            raise SystemExit(f"{r['where']}: child {r['id']} is listed twice")
        seen.add(r['id'])
        if r['id'] in vflags and r['born_flag'] != vflags[r['id']]:
            raise SystemExit(f"{r['where']}: born_flag of the game's own children is fixed "
                             f"(its scripts test flag {vflags[r['id']]}); leave it as is")
        r['new'] = r['id'] in added
        if r['mask'] is None:
            r['mask'] = 0xFFFFFF if r['new'] else 0
        if r['new'] and r['parent'] is None:
            raise SystemExit(f"{r['where']}: a new child needs a parent")
    used = {r['born_flag'] for r in rows if r['born_flag'] is not None} | set(vflags.values())
    nxt = NEW_FLAG_BASE
    for r in rows:
        if r['new'] and r['born_flag'] is None:
            while nxt in used:
                nxt += 1
            if nxt > 0xFF:
                raise SystemExit(f"{r['where']}: no free event flags left for born_flag")
            r['born_flag'] = nxt
            used.add(nxt)
        # a new child shares its substitute's army slot unless the row sets one
        if r['new'] and r['slot_blank'] and r['substitute'] is not None:
            sa = next((a for k in (0, 2) for i, a, _, _ in L.unit_rows(rom, k) if i == r['substitute']), None)
            if sa is not None and r['id'] in look:
                rom[look[r['id']] + 7] = rom[sa + 17]


def apply_scenes(rom, proj, space, far):
    """After the project's events: substitutes in the scripts, and new children joining."""
    rows = _pending.pop(id(rom), None)
    if rows is None:
        return 0
    import fe4events as EV
    changes = 0
    old = {c: sb for sb, c, _ in sub_pairs(rom)}
    joins = [r for r in rows if r['joins']]
    if joins:                                   # first: it may move a scene the swap then edits
        changes += _add_joins(rom, joins, space, far)
    swap = {r['id']: (old[r['id']], r['substitute']) for r in rows
            if r['id'] in old and r['substitute'] is not None and r['substitute'] != old[r['id']]}
    if swap:
        changes += _swap_substitutes(rom, EV.Ctx(bytes(rom)), swap)
    changes += _write_sub_table(rom, rows)
    return changes


def _branches(cmds, i):
    """For `07 flag` at cmds[i] followed by a jump: (not-born commands, born commands)."""
    if i + 1 >= len(cmds) or cmds[i + 1][1][0] not in (3, 4) or len(cmds[i + 1][1]) != 3:
        return None
    a, j = cmds[i + 1]
    T = (a & 0xFF0000) | j[1] | j[2] << 8
    idx = {x: k for k, (x, _) in enumerate(cmds)}
    if T not in idx:
        return None
    first = []
    k = i + 2
    while k < len(cmds) and cmds[k][0] < T:
        first.append(cmds[k])
        k += 1
    E = None
    if first and first[-1][1][0] == 2 and len(first[-1][1]) == 3:
        E = (a & 0xFF0000) | first[-1][1][1] | first[-1][1][2] << 8
        first = first[:-1]
    second = [x for x in cmds[idx[T]:] if E is not None and x[0] < E]
    return (first, second) if j[0] == 3 else (second, first)


def _swap_substitutes(rom, ctx, swap):
    """Where a scene picks between a child and its substitute (born flag test), put the new
    substitute in the not-born branch."""
    from dis65816 import snes_to_file
    flags = vanilla_flags(rom)
    by_flag = {flags[c]: (c, o, n) for c, (o, n) in swap.items() if c in flags}
    n_edits = 0
    for p in ctx.scene_ptrs():
        cmds = sorted(ctx.sc_decode(p).items())
        for i, (a, b) in enumerate(cmds):
            if len(b) != 2 or b[0] != 7 or b[1] not in by_flag:
                continue
            br = _branches(cmds, i)
            if not br:
                continue
            c, o, n = by_flag[b[1]]
            for (sa, sb), (_, cb) in zip(*br):
                if len(sb) != len(cb):
                    continue
                for q in range(1, len(sb) - 1):
                    if sb[q] | sb[q + 1] << 8 == o and cb[q] | cb[q + 1] << 8 == c:
                        fo = snes_to_file(sa) + q
                        rom[fo:fo + 2] = n.to_bytes(2, 'little')
                        n_edits += 1
    return n_edits


def _write_sub_table(rom, rows):
    """The (substitute, child) table scenes use to name whichever of the two is around."""
    pairs = sub_pairs(rom)
    have = {c for _, c, _ in pairs}
    want = []
    recs = {idx: a for idx, a, _, _ in child_rows(rom)}
    byid = {r['id']: r for r in rows}
    for sb, c, sl in pairs:
        r = byid.get(c)
        want.append(((r['substitute'] if r and r['substitute'] is not None else sb), c, sl))
    for r in rows:
        if r['id'] not in have and r['substitute'] is not None:
            want.append((r['substitute'], r['id'], rom[recs[r['id']] + 7]))
    if want == pairs:
        return 0
    if len(want) <= 14 and _long(rom, SUB_OPS[0]) == SUBS:
        for k, (sb, c, sl) in enumerate(want):
            rom[SUBS + 4 * k:SUBS + 4 * k + 4] = sb.to_bytes(2, 'little') + c.to_bytes(2, 'little')
            rom[_long(rom, SLOT_OP) + k] = sl
        return 1
    region = FX.region_for(rom)
    tab = b''.join(sb.to_bytes(2, 'little') + c.to_bytes(2, 'little') for sb, c, _ in want) + bytes(4)
    ta = region.put(tab)
    sa = region.put(bytes(sl for _, _, sl in want))
    for op in SUB_OPS:
        rom[op:op + 3] = ta.to_bytes(3, 'little')
    rom[SLOT_OP:SLOT_OP + 3] = sa.to_bytes(3, 'little')
    return 1


def _add_joins(rom, joins, space, far):
    """Put each child (or its substitute when the child wasn't born) into the army at the start of
    its chapter: commands added at the top of the chapter's opening scene."""
    import fe4events as EV
    import fe4asm as A
    from dis65816 import snes_to_file
    n = 0
    by_ch = {}
    for r in joins:
        by_ch.setdefault(r['joins'], []).append(r)
    for ch, rs in sorted(by_ch.items()):
        ctx = EV.Ctx(bytes(rom))
        init = dict(ctx.chapter_scripts()[ch][2])['init']
        sid = None
        for a, b in ctx.ev_walk(init):
            if b[0] == 0x30 and len(b) == 4:
                sid = b[2] | b[3] << 8
                break
        if sid is None:
            raise SystemExit(f"{rs[0]['where']}: chapter {ch} has no opening scene to add the child to")
        start = ctx.scene_ptrs()[sid]
        cmds = sorted(ctx.sc_decode(start).items())
        present = b''.join(b for _, b in cmds)
        todo = [r for r in rs if (bytes([0x4A, 0x50]) + r['id'].to_bytes(2, 'little')) not in present]
        if not todo:
            continue
        # new lines: (bytes, jump target label or None); labels resolved after layout
        new = []
        for r in todo:
            new.append((bytes([0x4A, 0x49]) + r['id'].to_bytes(2, 'little'), None, None))
            if r['substitute'] is not None:
                new.append((bytes([0x4A, 0x49]) + r['substitute'].to_bytes(2, 'little'), None, None))
        for k, r in enumerate(todo):
            put = lambda u: bytes([0x4A, 0x50]) + u.to_bytes(2, 'little') + bytes(3)
            born, after = ('born', k), ('after', k)
            new.append((bytes([0x07, r['born_flag']]), None, None))
            new.append((bytes([0x03, 0, 0]), born, None))
            if r['substitute'] is not None:
                new.append((put(r['substitute']), None, None))
            new.append((bytes([0x02, 0, 0]), after, None))
            new.append((put(r['id']), None, born))
            new.append((None, None, after))           # marks the next line
        lines, targets, labels = [], [], {}
        for b, tgt, lab in new:
            if lab is not None:
                labels[lab] = len(lines)
            if b is None:
                continue
            lines.append(b)
            targets.append(tgt)
        first = cmds[0][0]
        blk = {'start': start, 'label': f'scene {sid}', 'line': 0,
               'cmds': [(None, (b[:1] + (first & 0xFFFF).to_bytes(2, 'little')) if t else b, 0)
                        for b, t in zip(lines, targets)] + [(a, b, 0) for a, b in cmds]}
        placer = A.make_placer(space, lambda size: far.alloc(size + 1))
        new_start, remap, newaddrs = A.assemble(rom, blk, f'scene {sid}', A.jumps_sc, placer(start & 0xFF0000))
        for k, t in enumerate(targets):
            if t is None:
                continue
            dest = newaddrs[labels[t]] if labels[t] < len(lines) else newaddrs[len(lines)]
            fo = snes_to_file(newaddrs[k]) + 1
            rom[fo:fo + 2] = (dest & 0xFFFF).to_bytes(2, 'little')
        rom[EV.SCENE_TABLE + 3 * sid:EV.SCENE_TABLE + 3 * sid + 3] = new_start.to_bytes(3, 'little')
        n += 1
    return n


def _apply_rules(rom, proj):
    path = os.path.join(proj, 'gen2_rules.csv')
    if not os.path.exists(path):
        return 0
    n = 0
    for ln, r in enumerate(csv.DictReader(open(path, newline='')), start=2):
        k, v = r['rule'].strip(), r['value'].strip()
        try:
            v = int(v, 0)
        except ValueError:
            raise SystemExit(f'{path}:{ln}: value must be a number')
        if k == 'gold_divisor':
            if not 1 <= v <= 255:
                raise SystemExit(f'{path}:{ln}: gold_divisor must be 1-255')
            new = {GOLD_DIV: v.to_bytes(2, 'little')}
        elif k == 'gold_base':
            if not 0 <= v <= 60000:
                raise SystemExit(f'{path}:{ln}: gold_base must be 0-60000')
            new = {GOLD_BASE: v.to_bytes(2, 'little')}
        elif k == 'stat_cap':
            if not 1 <= v <= 255:
                raise SystemExit(f'{path}:{ln}: stat_cap must be 1-255')
            new = {STAT_CAP[0]: bytes([v]), STAT_CAP[1]: bytes([v])}
        else:
            raise SystemExit(f'{path}:{ln}: unknown rule {k!r} (gold_divisor, gold_base, stat_cap)')
        for fo, b in new.items():
            if rom[fo:fo + len(b)] != b:
                rom[fo:fo + len(b)] = b
                n += 1
    return n


def _install(rom, rows, space):
    region = FX.region_for(rom)
    # spawn order: by row order in the file
    genders = {}
    for k, off in ((0, 18), (1, 8), (2, 18)):
        for idx, a, _, _ in L.unit_rows(rom, k):
            genders[idx] = rom[a + off]
    tab = bytearray()
    for r in rows:
        gf, gm, sf, sm = r['weights']
        tab += r['id'].to_bytes(2, 'little') + (r['parent'] or 0).to_bytes(2, 'little')
        tab += (0xFFFF if r['born_flag'] is None else r['born_flag']).to_bytes(2, 'little')
        tab += bytes([1 if r['always'] else 0, gf, gm, sf, sm]) + r['mask'].to_bytes(3, 'little')
        tab += bytes([r.get('joins') or 0, 1 if genders.get(r['parent']) else 0])
    tab += bytes(ENT)
    tab += bytes(ENT)                          # entry used when a child has no row: no skills
    T = region.table('gen2', bytes(tab))
    NONE = len(rows) * ENT + ENT               # offset of the empty entry
    leave_ids = []                             # units the transition only sends away (action 0)
    e = TRANSITION
    while _w(rom, e) != 0xFFFF:
        if _w(rom, e + 2) in (0, 2) and _w(rom, e) not in leave_ids:
            leave_ids.append(_w(rom, e))
        e += 6

    def gen(org):
        a = Asm(org)
        # ---- make every child whose parent is married (runs before anyone leaves).
        #      Locals live on the stack and in $04/$06 (saved): the game's heaps cover most of WRAM.
        a.label('spawn')
        a.op('php')
        a.op('rep', '#8', 0x30)
        a.op('phb')
        a.op('phx')
        a.op('phy')
        for dp in (0x00, 0x02, 0x04, 0x06):
            a.op('lda', 'dp', dp)
            a.op('pha')
        a.op('lda', 'abs', 0x056F)
        a.op('pha')
        # love is over: free the generation-1 women's love counters.  Their heap ($7E:3BD7) holds
        # exactly nine, and each daughter born needs one, so a couple with two daughters ran out.
        for dp in (0x24, 0x39, 0x3A):
            a.op('lda', 'dp', dp)
            a.op('pha')
        for u in range(16, 25):
            a.op('lda', '#', u)
            a.op('jsl', 'long', FIND_UNIT)
            a.op('bcs', 'rel', 'lv%d' % u)
            a.op('ldx', 'abs', 0x056F)
            a.op('lda', 'long,x', 0x7E0010)
            a.op('ora', 'long,x', 0x7E0011)
            a.op('beq', 'rel', 'lv%d' % u)
            a.op('lda', '#', 0x7E00)
            a.op('sta', 'dp', 0x25)
            a.op('lda', '#', LOVE_HEAP)
            a.op('sta', 'dp', 0x24)
            a.op('jsl', 'long', 0x82EF72)
            a.op('lda', 'long,x', 0x7E0011)
            a.op('sta', 'dp', 0x3A)
            a.op('lda', 'long,x', 0x7E0010)
            a.op('sta', 'dp', 0x39)
            a.op('jsl', 'long', 0x82EE5C)
            a.op('ldx', 'abs', 0x056F)
            a.op('lda', '#', 0)
            a.op('sta', 'long,x', 0x7E0010)
            a.op('sta', 'long,x', 0x7E0011)
            a.label('lv%d' % u)
        for dp in (0x3A, 0x39, 0x24):
            a.op('pla')
            a.op('sta', 'dp', dp)
        a.op('ldx', '#', 0)
        # outer loop: the next anchor that is still around and married -> one couple
        a.label('o_loop')
        a.op('phx')                                 # [oi]
        a.op('lda', 'long,x', T)
        a.op('bne', 'rel', 'o_have')
        a.op('plx')
        a.op('brl', 'brl', 's_done')
        a.label('o_have')
        a.op('lda', 'long,x', T + 2)
        a.op('beq', 'far', 'o_next')
        a.op('sta', 'dp', 0x04)                     # anchor index
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'far', 'o_next')
        a.op('jsl', 'long', LOVER)
        a.op('and', '#', 0xFF)
        a.op('beq', 'far', 'o_next')
        a.op('sta', 'dp', 0x06)                     # lover index
        a.op('jsl', 'long', GENDER)
        a.op('and', '#', 0xFF)                      # (the game's getters restore the flags)
        a.op('bne', 'rel', 'o_fem')
        a.op('lda', 'dp', 0x06)                     # anchor is the father
        a.op('pha')                                 # [m][oi]
        a.op('lda', 'dp', 0x04)
        a.op('pha')                                 # [f][m][oi]
        a.op('bra', 'rel', 'o_couple')
        a.label('o_fem')
        a.op('lda', 'dp', 0x04)
        a.op('pha')
        a.op('lda', 'dp', 0x06)
        a.op('pha')
        a.label('o_couple')
        # inner loop: every child tied to either of them, in table order
        a.op('ldx', '#', 0)
        a.label('i_loop')
        a.op('phx')                                 # [j][f][m][oi]  j=1 f=3 m=5
        a.op('lda', 'long,x', T)
        a.op('beq', 'far', 'i_end')
        a.op('lda', 'long,x', T + 2)
        a.op('beq', 'far', 'i_next')
        a.op('cmp', 'sr', 5)
        a.op('beq', 'rel', 'i_take')
        a.op('cmp', 'sr', 3)
        a.op('bne', 'far', 'i_next')
        a.label('i_take')
        a.op('lda', 'long,x', T + 6)                # 'always': no need for the mother to be alive
        a.op('and', '#', 0xFF)
        a.op('bne', 'rel', 'i_make')
        a.op('lda', 'sr', 5)
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'far', 'i_next')
        a.op('jsl', 'long', FLAGS_OF)
        a.op('bit', '#', 0x0200)
        a.op('bne', 'far', 'i_next')
        a.label('i_make')
        a.op('lda', 'sr', 3)
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'far', 'i_next')
        a.op('lda', 'abs', 0x056F)
        a.op('sta', 'dp', 0x00)                     # father
        a.op('lda', 'sr', 5)
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'far', 'i_next')
        a.op('lda', 'abs', 0x056F)
        a.op('sta', 'dp', 0x02)                     # mother
        a.op('lda', 'sr', 1)
        a.op('tax')
        a.op('lda', 'long,x', T)
        a.op('jsl', 'long', FIND_UNIT)              # already made: skip
        a.op('bcc', 'far', 'i_next')
        a.op('lda', 'sr', 1)
        a.op('tax')
        a.op('lda', 'long,x', T)
        a.op('jsl', 'long', CREATE_UNIT)
        a.op('lda', 'sr', 1)
        a.op('tax')
        a.op('lda', 'long,x', T + 4)
        a.op('cmp', '#', 0xFFFF)
        a.op('beq', 'rel', 'i_next')
        a.op('jsl', 'long', SET_FLAG)
        a.label('i_next')
        a.op('plx')
        a.op('txa')
        a.op('clc')
        a.op('adc', '#', ENT)
        a.op('tax')
        a.op('brl', 'brl', 'i_loop')
        a.label('i_end')
        a.op('plx')                                 # [f][m][oi]
        # the mother leaves now, as in FE4, so her memory is free for the next couple
        a.op('lda', 'sr', 3)
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'rel', 'o_father')
        a.op('jsl', 'long', 0x84B1E4)
        a.op('jsl', 'long', 0x8483B8)
        # so does the father when FE4 would only send him away later (not Finn, who carries on):
        # with a child more than the game has, the unit memory would run out otherwise
        a.label('o_father')
        a.op('lda', 'sr', 1)
        for u in leave_ids:
            a.op('cmp', '#', u)
            a.op('beq', 'far', 'o_fret')
        a.op('bra', 'rel', 'o_drop')
        a.label('o_fret')
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'rel', 'o_drop')
        a.op('jsl', 'long', 0x84B1E4)
        a.op('jsl', 'long', 0x8483B8)
        a.label('o_drop')
        a.op('pla')
        a.op('pla')                                 # [oi]
        a.label('o_next')
        a.op('plx')
        a.op('txa')
        a.op('clc')
        a.op('adc', '#', ENT)
        a.op('tax')
        a.op('brl', 'brl', 'o_loop')
        a.label('s_done')
        a.op('pla')
        a.op('sta', 'abs', 0x056F)
        for dp in (0x06, 0x04, 0x02, 0x00):
            a.op('pla')
            a.op('sta', 'dp', dp)
        a.op('ply')
        a.op('plx')
        a.op('plb')
        a.op('plp')
        a.op('rtl')
        # ---- find: A = child id -> X = its entry, carry set when the kit has one
        a.label('find')
        a.op('pha')
        a.op('ldx', '#', 0)
        a.label('f_loop')
        a.op('lda', 'long,x', T)
        a.op('beq', 'rel', 'f_none')
        a.op('cmp', 'sr', 1)
        a.op('beq', 'rel', 'f_got')
        a.op('txa')
        a.op('clc')
        a.op('adc', '#', ENT)
        a.op('tax')
        a.op('bra', 'rel', 'f_loop')
        a.label('f_none')
        a.op('ldx', '#', NONE)
        a.op('pla')
        a.op('clc')
        a.op('rts')
        a.label('f_got')
        a.op('pla')
        a.op('sec')
        a.op('rts')
        # ---- skill mask: A = child id -> X = its entry (JSL from $87:A8E4)
        a.label('mask')
        a.op('jsr', 'abs', 'find')
        a.op('rtl')
        # ---- weights: (father x pct + mother x pct) / 100; FE4's own rule for children without a row
        def blend(label, off_f, off_m, done):
            a.label(label)
            a.op('phx')
            if label == 'grow':
                a.op('lda', 'abs,y', 0x0000)        # Y = the child's personal block: +0 = id
            else:
                a.op('jsl', 'long', 0x84A333)       # $056F = the child
            a.op('jsr', 'abs', 'find')
            a.op('bcs', 'rel', label + '_k')
            a.op('plx')
            a.op('lda', 'dp', 0x04 if label == 'grow' else 0x06)
            a.op('beq', 'rel', label + '_m')
            a.op('asl', 'dp', 0x00)
            a.op('bra', 'rel', label + '_v')
            a.label(label + '_m')
            a.op('asl', 'dp', 0x02)
            a.label(label + '_v')
            a.op('lda', 'dp', 0x00)
            a.op('clc')
            a.op('adc', 'dp', 0x02)
            if label == 'grow':
                a.op('lsr')
            else:
                a.op('sta', 'long', 0x004204)
                a.op('sep', '#8', 0x20)
                a.op('lda', '#', 10)
                a.op('sta', 'long', 0x004206)
                a.op('rep', '#8', 0x20)
                for _ in range(8):
                    a.op('nop')
                a.op('lda', 'long', 0x004214)
                a.op('clc')
                a.op('adc', 'dp', 0x04)
            a.op('jml', 'long', done)
            a.label(label + '_k')
            a.op('lda', 'long,x', T + off_m)
            a.op('and', '#', 0xFF)
            a.op('pha')                              # mother's %
            a.op('lda', 'long,x', T + off_f)
            a.op('and', '#', 0xFF)
            a.op('tax')
            a.op('lda', 'dp', 0x02)                  # father x pct
            a.op('jsr', 'abs', 'mul')
            a.op('plx')
            a.op('pha')                              # father part
            a.op('lda', 'dp', 0x00)                  # mother x pct
            a.op('jsr', 'abs', 'mul')
            a.op('clc')
            a.op('adc', 'sr', 1)
            a.op('bcc', 'rel', label + '_nc')
            a.op('lda', '#', 0xFFFF)
            a.label(label + '_nc')
            a.op('sta', 'long', 0x004204)            # / 100
            a.op('pla')
            a.op('sep', '#8', 0x20)
            a.op('lda', '#', 100)
            a.op('sta', 'long', 0x004206)
            a.op('rep', '#8', 0x20)
            for _ in range(8):
                a.op('nop')
            a.op('lda', 'long', 0x004214)
            if label == 'stat':
                a.op('clc')
                a.op('adc', 'dp', 0x04)
            a.op('cmp', '#', 256)
            a.op('bcc', 'rel', label + '_ok')
            a.op('lda', '#', 255)
            a.label(label + '_ok')
            a.op('plx')
            a.op('jml', 'long', done)
        blend('grow', 7, 8, SITE_GROW[2])
        blend('stat', 9, 10, SITE_STAT[2])
        # mul: A (0-255) x X (0-255) -> A
        a.label('mul')
        a.op('sep', '#8', 0x20)
        a.op('sta', 'long', 0x004202)
        a.op('txa')
        a.op('sta', 'long', 0x004203)
        a.op('rep', '#8', 0x20)
        for _ in range(4):
            a.op('nop')
        a.op('lda', 'long', 0x004216)
        a.op('rts')
        # ---- a child's mother for the status screen (replaces $84:A40D, which reads FE4's table):
        #      the parent the row names when that is a woman; else a sibling's mother with the same father
        a.label('mother')
        a.op('phx')
        a.op('phy')
        a.op('lda', 'abs', 0x056F)
        a.op('pha')                                 # [unit]
        a.op('jsl', 'long', 0x84A333)
        a.op('jsr', 'abs', 'find')
        a.op('bcc', 'rel', 'm_none')
        a.op('lda', 'long,x', T + 15)
        a.op('and', '#', 0xFF)
        a.op('beq', 'rel', 'm_sib')
        a.op('lda', 'long,x', T + 2)
        a.op('bra', 'rel', 'm_done')
        a.label('m_sib')
        a.op('jsl', 'long', 0x84A43D)               # father (personal +6)
        a.op('and', '#', 0xFF)
        a.op('beq', 'rel', 'm_none')
        a.op('pha')                                 # [father][unit]
        a.op('ldx', '#', 0)
        a.label('m_loop')
        a.op('phx')                                 # [e][father][unit]
        a.op('lda', 'long,x', T)
        a.op('beq', 'rel', 'm_end')
        a.op('lda', 'long,x', T + 15)
        a.op('and', '#', 0xFF)
        a.op('beq', 'rel', 'm_next')
        a.op('lda', 'long,x', T)
        a.op('jsl', 'long', FIND_UNIT)
        a.op('bcs', 'rel', 'm_next')
        a.op('jsl', 'long', 0x84A43D)
        a.op('and', '#', 0xFF)
        a.op('cmp', 'sr', 3)
        a.op('bne', 'rel', 'm_next')
        a.op('plx')
        a.op('pla')                                 # [unit]
        a.op('lda', 'long,x', T + 2)
        a.op('bra', 'rel', 'm_done')
        a.label('m_next')
        a.op('pla')
        a.op('clc')
        a.op('adc', '#', ENT)
        a.op('tax')
        a.op('bra', 'rel', 'm_loop')
        a.label('m_end')
        a.op('plx')
        a.op('pla')                                 # [unit]
        a.label('m_none')
        a.op('lda', '#', 0)
        a.label('m_done')
        a.op('tay')
        a.op('pla')
        a.op('sta', 'abs', 0x056F)
        a.op('tya')
        a.op('ply')
        a.op('plx')
        a.op('rtl')
        # ---- heap for a new child's unit object: FE4's child heap ($7E:2D4F) holds exactly 17;
        #      once it is full, use the playable-unit heap ($7E:3131), freed up by gen 1 leaving
        a.label('heap')
        a.op('phx')
        a.op('ldx', '#', CHILD_HEAP + 8)
        a.label('h_loop')
        a.op('txa')
        a.op('cmp', 'long', 0x7E0000 | (CHILD_HEAP + 1))
        a.op('bcs', 'rel', 'h_full')
        a.op('lda', 'long,x', 0x7E0000)
        a.op('bit', '#', 0x0080)
        a.op('beq', 'rel', 'h_next')
        a.op('lda', 'long,x', 0x7E0001)
        a.op('cmp', '#', CHILD_OBJ + 6)
        a.op('bcs', 'rel', 'h_ok')
        a.label('h_next')
        a.op('txa')
        a.op('clc')
        a.op('adc', 'long,x', 0x7E0001)
        a.op('tax')
        a.op('bra', 'rel', 'h_loop')
        a.label('h_full')
        a.op('lda', '#', UNIT_HEAP)
        a.op('bra', 'rel', 'h_set')
        a.label('h_ok')
        a.op('lda', '#', CHILD_HEAP)
        a.label('h_set')
        a.op('sta', 'dp', 0x24)
        a.op('plx')
        a.op('rtl')
        return a

    a = gen(region.cur)
    code = a.assemble()
    if not region.fits(len(code)):
        region.switch()
        a = gen(region.cur)
        code = a.assemble()
    region.put(code)
    lab = a.labels
    # bank $84 trampoline: make children, then the table walk as before
    fo, snes = space.alloc(0x840000, 8)
    t = Asm(snes)
    t.op('jsl', 'long', lab['spawn'])
    t.op('ldy', '#', 0x8237)
    t.op('rts')
    tc = t.assemble()
    rom[fo:fo + len(tc)] = tc
    assert rom[SITE_TRANS:SITE_TRANS + 3] == bytes.fromhex('a03782')
    rom[SITE_TRANS:SITE_TRANS + 3] = bytes([0x20]) + (snes & 0xFFFF).to_bytes(2, 'little')
    # mothers now only leave (their children were made above)
    e = TRANSITION
    while _w(rom, e) != 0xFFFF:
        if _w(rom, e + 2) == 2:
            rom[e + 2:e + 4] = b'\0\0'
        e += 6
    # skill masks per child from the kit's table
    assert rom[SITE_MASK:SITE_MASK + 3] == bytes.fromhex('b90000')
    rom[SITE_MASK + 3:SITE_MASK + 14] = bytes([0x22]) + lab['mask'].to_bytes(3, 'little') + b'\xEA' * 7
    rom[OP_MASK[0]:OP_MASK[0] + 3] = (T + 11).to_bytes(3, 'little')
    rom[OP_MASK[1]:OP_MASK[1] + 3] = (T + 12).to_bytes(3, 'little')
    assert rom[SITE_MOTHER:SITE_MOTHER + 4] == bytes.fromhex('da5a2233')
    rom[SITE_MOTHER:SITE_MOTHER + 4] = bytes([0x5C]) + lab['mother'].to_bytes(3, 'little')
    for site in (SITE_HEAP, SITE_HEAP_LOAD):
        assert rom[site:site + 5] == bytes.fromhex('a94f2d8524')
        rom[site:site + 5] = bytes([0x22]) + lab['heap'].to_bytes(3, 'little') + b'\xEA'
    for site, lbl in ((SITE_GROW, 'grow'), (SITE_STAT, 'stat')):
        fo, orig, _ = site
        assert rom[fo:fo + 4] == orig, hex(fo)
        rom[fo:fo + 4] = bytes([0x5C]) + lab[lbl].to_bytes(3, 'little')


def _apply_lovers(rom, proj):
    path = os.path.join(proj, 'lovers.csv')
    if not os.path.exists(path):
        return 0
    men, women = love_lists(rom)
    mi = {u: i for i, u in enumerate(men)}
    wi = {u: i for i, u in enumerate(women)}
    cur = love_tables(rom)
    new = dict(cur)
    for ln, r in enumerate(csv.DictReader(open(path, newline='')), start=2):
        where = f'{path}:{ln}'
        try:
            w, m = int(r['woman']), int(r['man'])
        except ValueError:
            raise SystemExit(f'{where}: woman and man are unit indices')
        if w not in wi or m not in mi:
            raise SystemExit(f'{where}: {w}/{m} is not in the game\'s love lists')
        key = (wi[w], mi[m])
        if key not in cur:
            raise SystemExit(f'{where}: gen-1 women pair with gen-1 men and gen-2 with gen-2')
        s = r['start'].strip().lower()
        if s in ('no', 'never', '-'):
            sb = 0xFF
        elif s == '499':
            sb = 0xFE
        else:
            try:
                v = int(s)
            except ValueError:
                raise SystemExit(f'{where}: start must be a number of love points, 499, or no')
            if not 0 <= v <= 2530 or v % 10:
                raise SystemExit(f'{where}: start must be 0-2530 in steps of 10 (or 499, or no)')
            sb = v // 10
        try:
            g = int(r['growth'])
        except ValueError:
            raise SystemExit(f'{where}: growth must be a number')
        if not -127 <= g <= 127:
            raise SystemExit(f'{where}: growth must be -127..127')
        new[key] = (sb, (0x80 | -g) if g < 0 else g)
    if new == cur:
        return 0
    # rebuild both tables (header of offsets per woman, then one byte per man)
    region = FX.region_for(rom)
    blobs = []
    for col in (0, 1):
        hdr, body = bytearray(), bytearray()
        base = 2 * len(women)
        for w_i in range(len(women)):
            gen1 = w_i < GEN1_WOMEN
            rng = range(GEN1_MEN) if gen1 else range(GEN1_MEN, len(men))
            off = base + len(body) - (0 if gen1 else GEN1_MEN)
            hdr += off.to_bytes(2, 'little')
            body += bytes(new[(w_i, m_i)][col] for m_i in rng)
        blobs.append(bytes(hdr + body))
    sa = region.put(blobs[0])
    ga = region.put(blobs[1])
    region.table('love', sa.to_bytes(3, 'little') + ga.to_bytes(3, 'little'))
    for ops, addr in ((OPS_START, sa), (OPS_GROW, ga)):
        for op in ops:
            rom[op:op + 3] = addr.to_bytes(3, 'little')
    return 1
