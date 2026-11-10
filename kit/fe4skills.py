#!/usr/bin/env python3
"""FE4 skills: who gets them, how often they trigger, and new stat skills.

Skill IDs 1-29 are the engine's own numbers.  HasSkill ($87:A19D, ID in A) checks
three masks per ID (all in bank $87):
  personal  3 bytes per ID at $87:A1EA  vs the unit's 24-bit skill field
  class     2 bytes per ID at $87:A244  vs the class's skill word (class +28)
  item      2 bytes per ID at $87:A280  vs each carried item's word (item +8),
            checked by $87:A2EF
The Skills menu lists 18 IDs from the word table at $8B:DFBF.

Editable effects (patched in place or through small hooks at $7D:F400+):
  Astra, Luna, Sol, 22, 23  activation rate = stat x percent / 100 + flat (game: Skill x 100%)
                            ($84:E14C loop; hook replaces JSL $849BCB at $84:E156)
  Wrath     crit when HP <= half          ($84:E67F: LDA #100)
  Charm     hit/avoid bonus to allies     ($84:DBDC: LDA #10)
  Miracle   avoid +(threshold-HP) x step  ($84:FADC / FAE6 / FAEB: 11, 11, 10)
  Renewal   heal base + random(range)     ($84:B00C / B014: 6, 5)
New skills (ID 30 and up) are stat bonuses added where the game adds holy
blood bonuses ($84:A6B6, called by the Str/Mag/Skl/Spd/Def/Res getters).
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
import fe4skillfx as FX
import fe4skillmenu as MN

NAMES = [None, 'Canto', 'Pavise', 'Wrath', 'Pursuit', 'Adept', 'Steal', 'Unused7', 'Dance', 'Unused9',
         'Troubadour?', 'Lord?', 'Charm', 'Hidden13', 'Nihil', 'Miracle', 'Critical', 'Vantage', 'Accost',
         'Astra', 'Luna', 'Sol', 'Hidden22', 'Hidden23', 'Renewal', 'Paragon', 'Hidden26', 'Recover',
         'Bargain', 'Return']
VANILLA_COUNT = 30
MENU_TABLE = 0x0BDFBF            # 18 words: skill IDs in the Skills menu
NOTES = {
    1: 'move again after acting (mounted classes, Knight ring)', 2: 'may block all damage (Baron, General, Emperor)',
    3: 'sure crit when HP is at or below half; amount = crit %', 4: 'attacks twice when faster',
    5: 'may attack again (rate: Speed)', 6: 'steal items (Thief)', 8: 'refresh an ally (Dancer)',
    12: 'allies within 3 get +amount hit and avoid', 13: 'story flag (Deirdre, Julia)',
    14: 'nullifies the enemy attack skills and weapon effectiveness', 15: 'avoid +(amount - HP) x amount2 when HP < amount',
    16: 'crit rate +Skill', 17: 'strikes first when HP is at or below half', 18: 'attacker cannot retreat',
    19: 'activation % = stat x amount / 100 + amount2', 20: 'activation % = stat x amount / 100 + amount2',
    21: 'activation % = stat x amount / 100 + amount2', 22: 'activation % = stat x amount / 100 + amount2 (unused)',
    23: 'activation % = stat x amount / 100 + amount2 (unused)',
    24: 'heal amount + random(amount2) HP each turn', 25: 'double experience', 26: 'story flag (Finn, Quan, Ethlyn)',
    27: 'full heal each turn (Recover band)', 28: 'half prices (Bargain band)', 29: 'warp home (Return band)',
}
STATS = {'str': 1, 'mag': 2, 'skl': 3, 'spd': 4, 'def': 5, 'res': 6, 'lck': 7}
STATS_INV = {v: k.capitalize() for k, v in STATS.items()}
GETTERS = {1: 0x849B15, 2: 0x849B70, 3: 0x849BCB, 4: 0x849C26, 5: 0x849C81, 6: 0x849CED, 7: 0x849D59}

# operand file offsets of the instructions that address each mask table
OPS = {'personal': [0x07A1BA, 0x07A2D8, 0x07A3B1], 'personal_hi': [0x07A1C2, 0x07A2E0, 0x07A3BA],
       'class': [0x07A1D4, 0x07A38B], 'item': [0x07A319, 0x07A400]}
STAT_CALLS = [0x049B25, 0x049B80, 0x049BDB, 0x049C36, 0x049C91, 0x049CFD]   # JSL $84A6B6
PROC_CALL = 0x04E156                                                        # JSL $849BCB
HOOK_STAT, STAT_TABLE = 0x7DF400, 0x7DF480
HOOK_PROC, PROC_TABLE = 0x7DF500, 0x7DF5C0
META = 0x7DF600                  # 'SKL' + count + 16-byte names of the new skills
PARAMS = {  # id: [(file offset, column, default)]
    3: [(0x04E680, 'amount', 100)],
    12: [(0x04DBDD, 'amount', 10)],
    15: [(0x04FADD, 'amount', 11), (0x04FAE7, 'amount', 11), (0x04FAEC, 'amount2', 10)],
    24: [(0x04B015, 'amount', 5), (0x04B00D, 'amount2', 6)],
}
PROC_IDS = range(19, 24)


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def tables(rom):
    """(personal base, class base, item base, count) as file offsets."""
    p = 0x070000 | _w(rom, OPS['personal'][0])
    c = 0x070000 | _w(rom, OPS['class'][0])
    i = 0x070000 | _w(rom, OPS['item'][0])
    n = rom[META + 3] if rom[META:META + 3] == b'SKL' else VANILLA_COUNT
    return p, c, i, n


def masks(rom):
    p, c, i, n = tables(rom)
    return [(int.from_bytes(rom[p + 3 * k:p + 3 * k + 3], 'little'), _w(rom, c + 2 * k), _w(rom, i + 2 * k))
            for k in range(n)]


def names(rom):
    out = list(NAMES)
    if rom[META:META + 3] == b'SKL':
        for k in range(VANILLA_COUNT, rom[META + 3]):
            a = META + 4 + 16 * (k - VANILLA_COUNT)
            out.append(bytes(rom[a:a + 16]).split(b'\0')[0].decode('ascii', 'replace'))
    return out


def set_maps(rom_or_rows):
    """Point fe4lib's skill name maps at the ROM's tables (or rows from skills.csv)."""
    rows = rom_or_rows if isinstance(rom_or_rows, list) else None
    if rows is None:
        nm = names(rom_or_rows)
        rows = [{'name': nm[k], 'personal': pm, 'class': cm, 'item': im}
                for k, (pm, cm, im) in enumerate(masks(rom_or_rows)) if k]
    for src, width in (('personal', 24), ('class', 16), ('item', 16)):
        m = {}
        for r in rows:
            for b in range(width):
                if r[src] >> b & 1:
                    m.setdefault(b, r['name'])
        L.SKILL_MAPS[src] = m


def _bit(v):
    bits = [b for b in range(24) if v >> b & 1]
    return ';'.join(map(str, bits))


# ---------------------------------------------------------------- export
FIELDS = ['id', 'name', 'personal_bit', 'class_bit', 'item_bit', 'units', 'classes', 'effect', 'stat', 'amount', 'amount2',
          'power', 'weapons', 'when', 'bonus', 'menu', 'icon', 'type', 'description', '_in_menu', '_notes']


def current_params(rom):
    out = {}
    for sid, ps in PARAMS.items():
        for fo, col, _ in ps:
            out.setdefault(sid, {})[col] = rom[fo]
    hooked = rom[PROC_CALL + 1:PROC_CALL + 4] == HOOK_PROC.to_bytes(3, 'little')
    for sid in PROC_IDS:
        if hooked:
            t = PROC_TABLE + 4 * (sid - 19) - 0x000000
            out[sid] = {'stat': STATS_INV.get(rom[t], 'Skl'), 'amount': rom[t + 1], 'amount2': rom[t + 2],
                        'weapons': 'any' if rom[t + 3] & 1 else 'sword'}
        else:
            out[sid] = {'stat': 'Skl', 'amount': 100, 'amount2': 0, 'weapons': 'sword'}
    t = STAT_TABLE
    if rom[STAT_CALLS[0] + 1:STAT_CALLS[0] + 4] == HOOK_STAT.to_bytes(3, 'little'):
        while rom[t]:
            out[rom[t]] = {'effect': 'stat', 'stat': STATS_INV[rom[t + 1]], 'amount': rom[t + 2]}
            t += 4
    for sid, (when, bonus) in FX.read_combat(rom).items():
        d = out.setdefault(sid, {})
        d.setdefault('effect', 'combat')
        d.update({'when': '' if when == 'always' else when, 'bonus': bonus})
    for sid, d in FX.read_effects(rom).items():
        out.setdefault(sid, {}).update(d)
    t = FX.table_addr(rom, 'menu')
    if t:
        inv = {v: k for k, v in MN.icon_names(rom, names(rom)).items()}
        for sid, d in MN.read_meta(rom, t).items():
            out.setdefault(sid, {}).update({'menu': 'yes', 'icon': _icon_label(inv.get(d['icon'], d['icon'])),
                                            'type': d['type'].capitalize(), 'description': d['description']})
    unames, cnames = _unit_names(rom), L.class_names(rom)
    for sid, (us, cs) in FX.read_extra(rom).items():
        d = out.setdefault(sid, {})
        d['units'] = ';'.join(unames.get(u, str(u)) for u in us)
        d['classes'] = ';'.join(cnames[c] if c < len(cnames) else str(c) for c in cs)
    return out


def _icon_label(k):
    if isinstance(k, int):
        return '0x%02X' % k
    return k if k.startswith('spare') else k.capitalize()


def _unit_lookup(rom):
    """name (lower case) -> unit index.  Playable units win when a name repeats
    (Finn, for example, is also an NPC record); other repeated names need the index."""
    by = {}
    for k in range(4):
        for idx, _, _, label in L.unit_rows(rom, k):
            if label:
                by.setdefault(label.lower(), []).append((k, idx))
    out = {}
    for n, hits in by.items():
        play = [i for k, i in hits if k == 0]
        if len(play) == 1:
            out[n] = play[0]
        elif len(hits) == 1:
            out[n] = hits[0][1]
    return out


def _unit_names(rom):
    """unit index -> name, where the name leads back to that unit"""
    labels = {}
    for k in range(4):
        for idx, _, _, label in L.unit_rows(rom, k):
            labels[idx] = label
    look = _unit_lookup(rom)
    return {i: n for i, n in labels.items() if n and look.get(n.lower()) == i}


def _parse_extra(rom, r, path):
    units, classes = [], []
    unames = _unit_lookup(rom)
    count = L.unit_count(rom)
    for t in filter(None, (x.strip() for x in r['units'].replace(',', ';').split(';'))):
        if t.isdigit() and 1 <= int(t) <= 0xFFFE:
            units.append(int(t))
        elif t.lower() in unames:
            units.append(unames[t.lower()])
        else:
            same = [str(idx) for k in range(4) for idx, _, _, lab in L.unit_rows(rom, k)
                    if lab.lower() == t.lower()]
            if same:
                raise SystemExit(f"{path}:{r['line']}: units: several units are called {t} "
                                 f"(indices {', '.join(same)}); write the index instead")
            raise SystemExit(f"{path}:{r['line']}: units: unknown unit {t!r}")
    cn = {n.lower(): i for i, n in enumerate(L.class_names(rom))}
    for t in filter(None, (x.strip() for x in r['classes'].replace(',', ';').split(';'))):
        if t.isdigit() and int(t) < 255:
            classes.append(int(t))
        elif t.lower() in cn:
            classes.append(cn[t.lower()])
        else:
            raise SystemExit(f"{path}:{r['line']}: classes: unknown class {t!r}")
    return units, classes


def export(rom, path):
    menu = {_w(rom, MENU_TABLE + 2 * k) for k in range(18)}
    params = current_params(rom)
    nm = names(rom)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k, (pm, cm, im) in enumerate(masks(rom)):
            if k == 0:
                continue
            row = {'id': k, 'name': nm[k], 'personal_bit': _bit(pm), 'class_bit': _bit(cm), 'item_bit': _bit(im),
                   '_in_menu': 'yes' if k in menu else '', '_notes': NOTES.get(k, '')}
            row.update(params.get(k, {}))
            if k >= VANILLA_COUNT and 'menu' not in row:
                row['menu'] = 'no'
            w.writerow(row)
    print('wrote', path)


# ---------------------------------------------------------------- apply
def read_rows(path):
    rows = []
    for ln, r in enumerate(csv.DictReader(open(path, newline='')), start=2):
        def bits(col, width):
            v = 0
            for t in (r.get(col) or '').replace(',', ';').split(';'):
                t = t.strip()
                if t:
                    if not t.isdigit() or int(t) >= width:
                        raise SystemExit(f'{path}:{ln}: {col} must be bit numbers 0-{width - 1}')
                    v |= 1 << int(t)
            return v
        try:
            sid = int(r['id'])
        except ValueError:
            raise SystemExit(f'{path}:{ln}: id must be a number')
        rows.append({'id': sid, 'line': ln, 'name': r['name'].strip(), 'personal': bits('personal_bit', 24),
                     'class': bits('class_bit', 16), 'item': bits('item_bit', 16),
                     'stat': (r.get('stat') or '').strip(), 'amount': (r.get('amount') or '').strip(),
                     'amount2': (r.get('amount2') or '').strip(), 'effect': (r.get('effect') or '').strip().lower(),
                     'when': (r.get('when') or '').strip().lower().replace(' ', ''),
                     'bonus': (r.get('bonus') or '').strip(), 'power': (r.get('power') or '').strip(),
                     'units': (r.get('units') or '').strip(), 'classes': (r.get('classes') or '').strip(),
                     'menu': (r.get('menu') or '').strip().lower(),
                     'weapons': (r.get('weapons') or '').strip().lower(), 'icon': (r.get('icon') or '').strip(),
                     'type': (r.get('type') or '').strip().lower(),
                     'description': (r.get('description') or '').strip()})
    ids = sorted(x['id'] for x in rows)
    if ids != list(range(1, len(ids) + 1)) or len(ids) < VANILLA_COUNT - 1:
        raise SystemExit(f'{path}: skills must be listed by id 1, 2, 3 ... with no gaps (new ones from 30)')
    for r in rows:
        if not r['name']:
            raise SystemExit(f"{path}:{r['line']}: every skill needs a name")
    if len({r['name'].lower() for r in rows}) != len(rows):
        raise SystemExit(f'{path}: skill names must be different from each other')
    return sorted(rows, key=lambda x: x['id'])


def _weapons(r, path, default):
    """1 = any weapon but staves, 0 = swords only"""
    w = r['weapons'] or default
    if w in ('sword', 'swords'):
        return 0
    if w in ('any', 'all'):
        return 1
    raise SystemExit(f"{path}:{r['line']}: weapons must be sword (swords only) or any (any weapon but staves)")


def _num(r, col, lo, hi, path):
    try:
        v = int(r[col], 0)
    except ValueError:
        raise SystemExit(f"{path}:{r['line']}: {col} must be a number")
    if not lo <= v <= hi:
        raise SystemExit(f"{path}:{r['line']}: {col} must be {lo}-{hi}")
    return v


def _stat(r, path, allow_lck):
    s = r['stat'].lower()[:3]
    if s not in STATS or (s == 'lck' and not allow_lck):
        raise SystemExit(f"{path}:{r['line']}: stat must be one of Str, Mag, Skl, Spd, Def, Res"
                         + (', Lck' if allow_lck else ''))
    return STATS[s]


def apply(rom, proj, space, far=None):
    """Apply skills.csv (if present); always sets the skill name maps for the other tables."""
    path = os.path.join(proj, 'skills.csv')
    if not os.path.exists(path):
        set_maps(rom)
        return 0
    rows = read_rows(path)
    set_maps(rows)
    changes = 0
    count = len(rows) + 1
    # mask tables
    pm, cm, im = [0], [0], [0]
    for r in rows:
        pm.append(r['personal'])
        cm.append(r['class'])
        im.append(r['item'])
    old = masks(rom)
    moved = False
    if count > VANILLA_COUNT:
        moved = True
        fo, sn = space.alloc(0x870000, 7 * count)
        pb, cb, ib = fo, fo + 3 * count, fo + 5 * count
        for name, base in (('personal', pb), ('personal_hi', pb + 1), ('class', cb), ('item', ib)):
            for op in OPS[name]:
                rom[op:op + 2] = (base & 0xFFFF).to_bytes(2, 'little')
        names_new = [r['name'] for r in rows[VANILLA_COUNT - 1:]]
        meta = bytearray(b'SKL' + bytes([count]))
        for n in names_new:
            meta += n.encode('ascii', 'replace')[:15].ljust(16, b'\0')
        if META + len(meta) > 0x7DF800:
            raise SystemExit(f'{path}: too many new skills')
        rom[META:META + len(meta)] = meta
        changes += 1
    pb, cb, ib, _ = tables(rom)
    for k in range(count):
        new = (pm[k], cm[k], im[k])
        if moved or k >= len(old) or new != old[k]:
            rom[pb + 3 * k:pb + 3 * k + 3] = pm[k].to_bytes(3, 'little')
            rom[cb + 2 * k:cb + 2 * k + 2] = cm[k].to_bytes(2, 'little')
            rom[ib + 2 * k:ib + 2 * k + 2] = im[k].to_bytes(2, 'little')
            changes += 1
    # simple parameters
    for r in rows:
        for fo, col, default in PARAMS.get(r['id'], []):
            if r[col] == '':
                continue
            v = _num(r, col, 0, 255, path)
            if rom[fo] != v:
                rom[fo] = v
                changes += 1
    # activation rates of Astra, Luna, Sol, 22, 23
    proc = []
    for sid in PROC_IDS:
        r = rows[sid - 1]
        st = _stat(r, path, True) if r['stat'] else 3
        pct = _num(r, 'amount', 0, 255, path) if r['amount'] else 100
        add = _num(r, 'amount2', 0, 100, path) if r['amount2'] else 0
        anyw = _weapons(r, path, 'sword')
        proc.append((st, pct, add, anyw))
    if any(p != (3, 100, 0, 0) for p in proc):
        _install_proc(rom, proc)
        changes += 1
        # the Skills menu calls Astra/Luna/Sol "Sword" skills; any-weapon ones become "Combat"
        menu_ids = MN.vanilla_rows(rom)
        for sid, p in zip(PROC_IDS, proc):
            if p[3] and sid in menu_ids:
                a = MN.ROW_TEXT + 32 * menu_ids.index(sid)
                row = bytes(rom[a:a + 32])
                i = row.find(MN.TYPES['sword'])
                if i >= 0:
                    new = row[:i] + MN.TYPES['combat'] + b'\0\0'
                    rom[a:a + len(new)] = new
    # new skills (stat bonuses, combat bonuses, effects from later games)
    stat_sk, combat, effects, ext_p, ext_c = [], [], [], [], []
    for r in rows:
        if r['id'] < VANILLA_COUNT and (r['units'] or r['classes']):
            raise SystemExit(f"{path}:{r['line']}: units/classes lists are for new skills (id 30 and up); "
                             "give built-in skills through the units' and classes' skills columns")
        new = r['id'] >= VANILLA_COUNT
        eff = r['effect']
        if new and not eff:
            eff = 'combat' if r['bonus'] and not r['stat'] else 'stat'
        if r['bonus']:
            if r['when'] not in FX.WHEN:
                raise SystemExit(f"{path}:{r['line']}: when must be one of: "
                                 + ', '.join(k for k in FX.WHEN if k))
            try:
                parts = FX.parse_bonus(r['bonus'])
            except ValueError as e:
                raise SystemExit(f"{path}:{r['line']}: bonus: {e}")
            combat += [(r['id'], FX.WHEN[r['when']], f, a) for f, a in parts]
        elif r['when'] and eff == 'combat':
            raise SystemExit(f"{path}:{r['line']}: when needs a bonus such as atk+5")
        if not new:
            if eff:
                raise SystemExit(f"{path}:{r['line']}: effect is only for new skills (id 30 and up); "
                                 'built-in skills keep their own behaviour')
            continue
        us, cs = _parse_extra(rom, r, path)
        ext_p += [(u, r['id']) for u in us]
        ext_c += [(c, r['id']) for c in cs]
        if not (r['personal'] or r['class'] or r['item'] or us or cs):
            raise SystemExit(f"{path}:{r['line']}: {r['name']} needs units, classes, or a personal_bit, "
                             'class_bit or item_bit so something can have it')
        if eff == 'stat':
            stat_sk.append((r['id'], _stat(r, path, False), _num(r, 'amount', 1, 30, path)))
        elif eff == 'combat':
            if not r['bonus']:
                raise SystemExit(f"{path}:{r['line']}: a combat skill needs a bonus such as atk+5;hit+10")
        elif eff in FX.EFFECTS:
            effects.append(FX.effect_entry(r, path))
        else:
            raise SystemExit(f"{path}:{r['line']}: unknown effect {eff!r}; use stat, combat or one of: "
                             + ', '.join(FX.EFFECTS))
    if stat_sk:
        _install_stat(rom, stat_sk)
        changes += 1
    menu = _menu_rows(rom, rows, path, effects, stat_sk)
    if combat or effects or ext_p or ext_c or menu:
        region = FX.build(rom, combat, effects, space, (ext_p, ext_c))
        changes += 1
        if menu:
            far = far or L.FreeSpace()
            try:
                MN.build(rom, [m[:5] for m in menu], region, space, far,
                         MN.meta_bytes([(m[0], m[2], m[3], m[5]) for m in menu]))
            except (MN.MenuError, ValueError) as e:
                raise SystemExit(f'{path}: Skills menu: {e}')
    return changes


# ---------------------------------------------------------------- hooks (65816)
def _menu_rows(rom, rows, path, effects, stat_sk):
    """New skills shown in the Skills menu: [(id, name, icon tile, type, help lines, help text)]"""
    icons = MN.icon_names(rom, [r['name'] for r in [{'name': ''}] + rows])
    icons.update(MN.icon_names(rom, NAMES))
    out = []
    for r in rows[VANILLA_COUNT - 1:]:
        where = f"{path}:{r['line']}"
        if r['menu'] in ('no', 'n', '0', 'false'):
            continue
        if r['menu'] not in ('', 'yes', 'y', '1', 'true'):
            raise SystemExit(f'{where}: menu must be yes or no')
        eff = r['effect'] or ('combat' if r['bonus'] and not r['stat'] else 'stat')
        kind = FX.EFFECTS[eff][0] if eff in FX.EFFECTS else 0
        icon = r['icon'] or FX.DEFAULT_ICON.get(kind, 'wrath' if eff == 'combat' else 'spare3')
        if icon.lower().startswith('0x'):
            tile = int(icon, 16)
        elif icon.lower() in icons:
            tile = icons[icon.lower()]
        else:
            raise SystemExit(f"{where}: icon must be a Skills-menu skill's name (Pavise, Luna, ...) or "
                             'spare1-spare6')
        typ = r['type'] or ('field' if kind == FX.K_KILL or r['when'] == 'ally_near' else 'combat')
        if typ not in MN.TYPES:
            raise SystemExit(f'{where}: type must be Combat, Field or Sword')
        text = r['description'] or _default_help(r, eff)
        try:
            lines = MN.wrap(text)
            MN.desc_picture(r['name'], lines)
        except ValueError as e:
            raise SystemExit(f'{where}: description: {e}')
        out.append((r['id'], r['name'], tile, typ, lines, text))
    return out


def _default_help(r, eff):
    if eff in FX.HELP:
        return FX.HELP[eff]
    if eff == 'stat':
        return '%s +%s.' % (r['stat'].capitalize()[:3], r['amount'])
    parts = []
    for p in r['bonus'].replace(',', ';').split(';'):
        p = p.strip()
        if not p:
            continue
        foe = p.lower().startswith('foe_')
        p = p[4:] if foe else p
        i = max(p.find('+'), p.find('-'))
        name = {'atk': 'Atk', 'def': 'Def', 'hit': 'Hit', 'avoid': 'Avoid', 'crit': 'Crit',
                'speed': 'Spd'}.get(p[:i].lower(), p[:i])
        parts.append(('Foe ' if foe else '') + name + ' ' + p[i:])
    when = {'attacking': ' when attacking', 'defending': ' when attacked', 'hp<=50': ' at half HP or less',
            'hp<=25': ' at 1/4 HP or less', 'hp_full': ' at full HP',
            'ally_near': ' for allies within 3 spaces'}.get(r['when'], '')
    return ', '.join(parts) + when + '.'


def _jsl(addr):
    return bytes([0x22, addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16])


def _lda_long_x(addr):
    return bytes([0xBF, addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16])


def _install_stat(rom, entries):
    T = STAT_TABLE
    c = bytearray()
    c += b'\x48'                                         # PHA (stat)
    for a in (0x0571, 0x0573, 0x0583, 0x0585):          # LDA abs; PHA  (save what HasSkill touches)
        c += bytes([0xAD, a & 0xFF, a >> 8, 0x48])
    c += b'\xA3\x09'                                     # LDA 9,S (stat)
    c += _jsl(0x84A6B6) + b'\x85\x4C'                    # JSL holy-blood bonus; STA $4C
    c += b'\xDA\x5A\xA2\x00\x00'                         # PHX PHY LDX #0
    loop = len(c)
    c += _lda_long_x(T) + b'\x29\xFF\x00' + b'\xF0\x00'  # LDA id; AND; BEQ done
    beq_done = len(c) - 1
    c += _lda_long_x(T + 1) + b'\x29\xFF\x00' + b'\xC3\x0D' + b'\xD0\x00'   # stat == requested?
    bne1 = len(c) - 1
    c += _lda_long_x(T) + b'\x29\xFF\x00' + _jsl(0x87A19D) + b'\xB0\x00'    # HasSkill
    bcs_yes = len(c) - 1
    c += _lda_long_x(T) + b'\x29\xFF\x00' + _jsl(0x87A2EF) + b'\x90\x00'    # item skill
    bcc_next = len(c) - 1
    yes = len(c)
    c += _lda_long_x(T + 2) + b'\x29\xFF\x00\x18\x65\x4C\x85\x4C'             # $4C += amount
    nxt = len(c)
    c += b'\xE8\xE8\xE8\xE8\x80\x00'
    c[-1] = (loop - len(c)) & 0xFF
    done = len(c)
    c += b'\x7A\xFA'                                     # PLY PLX
    for a in (0x0585, 0x0583, 0x0573, 0x0571):          # PLA; STA abs
        c += bytes([0x68, 0x8D, a & 0xFF, a >> 8])
    c += b'\x68\xA5\x4C\x6B'                             # PLA (stat); LDA $4C; RTL
    c[beq_done] = done - (beq_done + 1)
    c[bne1] = nxt - (bne1 + 1)
    c[bcs_yes] = yes - (bcs_yes + 1)
    c[bcc_next] = nxt - (bcc_next + 1)
    assert len(c) <= T - HOOK_STAT
    tab = b''.join(bytes([sid, st, amt, 0]) for sid, st, amt in entries) + b'\0\0\0\0'
    if T + len(tab) > HOOK_PROC:
        raise SystemExit('too many new stat skills (up to 31)')
    rom[HOOK_STAT:HOOK_STAT + len(c)] = c
    rom[T:T + len(tab)] = tab
    for op in STAT_CALLS:
        rom[op + 1:op + 4] = HOOK_STAT.to_bytes(3, 'little')


WEAPON_GATE = 0x04E13D        # JSL $87E48D; CMP #0; BNE $E166 (FE4: swords only)
WEAPON_TYPE = 0x7E4F5B        # weapon type of the striker, kept for the rate hook (combat scratch)
STAFF = 4


def _install_proc(rom, proc):
    T = PROC_TABLE
    c = bytearray(b'\xDA\x98\x38\xE9\x13\x00\x0A\x0A\xAA')   # PHX TYA SEC SBC #$13 ASL ASL TAX
    c += _lda_long_x(T + 3) + b'\x29\x01\x00\xD0\x00'           # any-weapon flag?  BNE ok
    bne_ok = len(c) - 1
    c += b'\xAF' + WEAPON_TYPE.to_bytes(3, 'little') + b'\xF0\x00'  # LDA weapon type; BEQ ok (sword)
    beq_ok = len(c) - 1
    c += b'\xA9\x00\x00\xFA\x6B'                                  # LDA #0; PLX; RTL (never)
    ok = len(c)
    c[bne_ok] = ok - (bne_ok + 1)
    c[beq_ok] = ok - (beq_ok + 1)
    c += _lda_long_x(T) + b'\x29\xFF\x00'                     # stat
    bras = []
    for st in range(1, 8):
        c += bytes([0xC9, st, 0x00, 0xD0, 0x06]) + _jsl(GETTERS[st]) + b'\x80\x00'
        bras.append(len(c) - 1)
    c += _jsl(GETTERS[3])                                     # default: Skill
    got = len(c)
    for b in bras:
        c[b] = got - (b + 1)
    c += b'\xE2\x20\x8F\x02\x42\x00'                          # SEP #$20; STA $004202
    c += _lda_long_x(T + 1) + b'\x8F\x03\x42\x00'             # LDA pct; STA $004203
    c += b'\xEA' * 4 + b'\xC2\x20\xAF\x16\x42\x00'           # wait; REP #$20; LDA $004216
    c += b'\x8F\x04\x42\x00\xE2\x20\xA9\x64\x8F\x06\x42\x00'  # STA $004204; SEP; LDA #100; STA $004206
    c += b'\xEA' * 8 + b'\xC2\x20\xAF\x14\x42\x00'           # wait; REP #$20; LDA $004214
    c += b'\x18' + bytes([0x7F, (T + 2) & 0xFF, ((T + 2) >> 8) & 0xFF, (T + 2) >> 16])  # CLC; ADC flat bonus
    c += b'\xFA\x6B'                                          # PLX RTL
    assert len(c) <= T - HOOK_PROC, len(c)
    # weapon gate: remember the weapon type; only staves stop the skills here
    g = T + 0x20                                              # after the 5-entry table, before META
    gc = _jsl(0x87E48D) + b'\x8F' + WEAPON_TYPE.to_bytes(3, 'little')   # STA long
    gc += bytes([0xC9, STAFF, 0x00, 0xF0, 0x04, 0xA9, 0x00, 0x00, 0x6B, 0xA9, 0x01, 0x00, 0x6B])
    # CMP #staff; BEQ +4; LDA #0; RTL; LDA #1; RTL   (Z set = may proceed)
    assert g + len(gc) <= META
    rom[HOOK_PROC:HOOK_PROC + len(c)] = c
    rom[g:g + len(gc)] = gc
    rom[T:T + 4 * len(proc)] = b''.join(bytes([st, pct, add, anyw]) for st, pct, add, anyw in proc)
    rom[PROC_CALL + 1:PROC_CALL + 4] = HOOK_PROC.to_bytes(3, 'little')
    assert rom[WEAPON_GATE:WEAPON_GATE + 9] == bytes.fromhex('228de487c90000d020')
    rom[WEAPON_GATE:WEAPON_GATE + 7] = _jsl(g) + b'\xEA\xEA\xEA'


if __name__ == '__main__':
    _, r = L.load_rom(sys.argv[1])
    export(r, sys.argv[2])
