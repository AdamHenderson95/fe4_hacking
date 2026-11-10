#!/usr/bin/env python3
"""FE4 hack builder.

  python fe4hack.py extract <clean.smc> <project_dir>   ROM -> editable CSVs
  python fe4hack.py build   <clean.smc> <project_dir> <out.smc> [--ips out.ips] [--hover-stats]
  python fe4hack.py diff    <a.smc> <b.smc>             list changed table fields

Edit the CSVs in a spreadsheet or text editor, then build.  The build always
starts from the clean ROM, so the CSVs are the single source of truth.
Columns whose names start with '_' are informational and ignored on build.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
import fe4events as EV
import fe4maps as MP
import fe4locations as LOC
import fe4armies as AR
import fe4names as NM
import fe4skills as SK
import fe4gen2 as G2


def _info_cols(tname, rom, rec, cnames, inames, idx=None):
    """Extra read-only columns that make the CSVs easier to read."""
    def cls(c):
        return cnames[c] if c < len(cnames) else '?'

    def inst(x):
        return inames[rom[L.INSTANCES + x]] if x < L.INSTANCE_COUNT else '?'

    def itype(x):
        return inames[x] if x < len(inames) else '?'

    if tname == 'units_playable':
        return {'_class_name': cls(rec[9]), '_items': ' / '.join(inst(x) for x in rec[35:38] if x != 255)}
    if tname == 'units_npc':
        return {'_class_name': cls(rec[9]), '_items': ' / '.join(itype(x) for x in rec[35:38] if x != 255)}
    if tname == 'units_children':
        out = dict(G2.extra_cols(rom).get(idx, {c: '' for c in G2.COLUMNS}))
        out.update({'_class_name': cls(rec[1]), '_items': ' / '.join(inst(x) for x in rec[9:11] if x != 255)})
        return out
    if tname == 'units_generic':
        return {'_class_name': cls(rec[5]), '_items': ' / '.join(itype(x) for x in rec[10:13] if x != 255)}
    return {}


def extract(rom_path, proj):
    copier, rom = L.load_rom(rom_path)
    if L.sha1(rom) != L.EXPECTED_SHA1:
        print('warning: ROM hash differs from the one this map was built on; offsets may not match')
    os.makedirs(proj, exist_ok=True)
    SK.set_maps(rom)
    SK.export(rom, os.path.join(proj, 'skills.csv'))
    cnames, inames = L.class_names(rom), L.item_names(rom)
    ports = L.portraits(rom)
    for tname, (rows_fn, fields) in L.TABLES.items():
        rows = rows_fn(rom)
        path = os.path.join(proj, tname + '.csv')
        with open(path, 'w', newline='') as f:
            w = None
            for idx, addr, size, label in rows:
                rec = rom[addr:addr + size]
                row = {'index': idx, '_name': label}
                row.update({c: L.get_field(rec, o, k) for c, o, k in fields})
                if tname.startswith('units_'):
                    row['portrait'] = ports[idx]
                row.update(_info_cols(tname, rom, rec, cnames, inames, idx))
                if w is None:
                    w = csv.DictWriter(f, fieldnames=list(row))
                    w.writeheader()
                w.writerow(row)
        print(f'wrote {path} ({len(rows)} rows)')
    path = os.path.join(proj, 'item_instances.csv')
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['instance', 'item_type', '_item_name'])
        for i in range(L.INSTANCE_COUNT):
            t = rom[L.INSTANCES + i]
            w.writerow([i, t, inames[t] if t < len(inames) else '?'])
    print('wrote', path)
    EV.dump(rom_path, os.path.join(proj, 'events'))
    MP.export(rom, os.path.join(proj, 'maps'))
    LOC.export(rom, os.path.join(proj, 'locations.csv'))
    LOC.export_arena(rom, os.path.join(proj, 'arena.csv'))
    LOC.export_talks(rom, os.path.join(proj, 'talks.csv'))
    AR.export(rom, proj)
    G2.export(rom, proj)
    NM.export(rom, os.path.join(proj, 'names.csv'))


def _put_fields(rec, fields, row, path, line, tname=None):
    if tname in L.RAW_SKILL_COLUMNS and 'skills' not in row:
        lo, hi = L.RAW_SKILL_COLUMNS[tname]
        if lo in row:                      # project from before v10: raw skill numbers
            v = int(row[lo], 0) | (int(row[hi], 0) << 8 if hi and hi in row else 0)
            row = dict(row, skills=';'.join('bit%d' % b for b in range(16) if v >> b & 1))
    for col, off, kind in fields:
        if col not in row:
            col = L.COLUMN_ALIASES.get(col, col)
            if col not in row:
                continue
        try:
            L.put_field(rec, off, kind, row[col])
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f'{path}:{line}: column {col!r}: {e}')


NEW_UNIT_FILES = (('units_generic', 3), ('units_children', 1))


def _free_name_ids(rom):
    """Character name slots no unit uses (570-575 in FE4 are empty)."""
    used = set()
    for k in range(4):
        off = {0: 15, 2: 15, 1: 5, 3: 3}[k]
        for _, a, _, _ in L.unit_rows(rom, k):
            used.add(rom[a + off] | rom[a + off + 1] << 8)
    return [i for i in range(576) if i not in used]


def _add_units(rom, proj, space):
    """New rows in units_generic.csv / units_children.csv (IDs after the last unit) become new units.
    Returns the set of new IDs."""
    first = L.first_new_id(rom)
    cnt = L.unit_count(rom)
    new = {}
    for tname, rtype in NEW_UNIT_FILES:
        path = os.path.join(proj, tname + '.csv')
        if not os.path.exists(path):
            continue
        for line, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
            try:
                i = int(row['index'])
            except ValueError:
                raise SystemExit(f'{path}:{line}: index must be a number')
            if i > cnt:
                if i in new:
                    raise SystemExit(f'{path}:{line}: unit {i} is added twice')
                new[i] = rtype
    if not new:
        return set()
    ids = sorted(new)
    legacy = L.GAME_UNITS <= cnt <= L.RESERVED_IDS and ids[0] == cnt + 1
    if legacy:                       # projects from before v12 numbered new units from 570
        first = cnt + 1
        print(f'note: new units {ids[0]}-{ids[-1]} share their ids with dialogue speakers 570-768 '
              f'(their portraits); numbering new units from {L.RESERVED_IDS + 1} avoids that')
    if ids != list(range(first, first + len(ids))):
        raise SystemExit(f'new units (in units_generic.csv and units_children.csv together) must use IDs '
                         f'{first}, {first + 1}, ... with no gaps (got {ids}); 570-768 are the game\'s '
                         f'dialogue speakers')
    addrs = L.add_units(rom, [new[i] for i in ids], space, reserve=not legacy)
    free = sorted(_free_name_ids(rom), key=lambda i: (not NM.slot_empty(rom, i), i))
    for i, a in zip(ids, addrs):
        if new[i] == 1:                       # defaults for a new child; the CSV row overrides them
            nid = free.pop(0) if free else 0
            rom[a + 1:a + 12] = bytes([0, 1]) + i.to_bytes(2, 'little') + nid.to_bytes(2, 'little') + \
                bytes([0x80, 0, 255, 255, 1])
    return set(ids)


def _apply_portraits(rom, proj, far):
    import fe4skills as SK2
    look = None
    want = {}
    for tname in ('units_playable', 'units_children', 'units_npc', 'units_generic'):
        path = os.path.join(proj, tname + '.csv')
        if not os.path.exists(path):
            continue
        for line, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
            v = (row.get('portrait') or '').strip()
            if not v:
                continue
            if v.isdigit():
                p = int(v)
            else:
                if look is None:
                    look = SK2._unit_lookup(rom)
                    cur = L.portraits(rom)
                u = look.get(v.lower())
                if u is None:
                    raise SystemExit(f"{path}:{line}: portrait: write a number or a unit's name (unknown {v!r})")
                p = cur[u]
            if not 0 <= p <= 0xFFFF:
                raise SystemExit(f'{path}:{line}: portrait must be 0-65535')
            want[int(row['index'])] = p
    return L.set_portraits(rom, want, far)


def _apply_deploy(rom, path, space):
    """deploy.csv: edit entries in place, or rebuild lists whose rows were added/removed."""
    fields = L.TABLES['deploy'][1]
    existing = {}
    for idx, addr, size, _ in L.deploy_rows(rom):
        li, en = map(int, idx.split('.'))
        existing.setdefault(li, []).append(addr)
    want = {}
    for line, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
        try:
            li, en = map(int, row['index'].strip().split('.'))
        except ValueError:
            raise SystemExit(f'{path}:{line}: index must look like list.entry, e.g. 0.12')
        if not 0 <= li < L.DEPLOY_LISTS:
            raise SystemExit(f'{path}:{line}: there are only lists 0-{L.DEPLOY_LISTS - 1} (new lists cannot be added)')
        if en in want.setdefault(li, {}):
            raise SystemExit(f'{path}:{line}: entry {li}.{en} is listed twice')
        want[li][en] = (line, row)
    ucount = L.unit_count(rom)
    changes = 0
    for li, ents in sorted(want.items()):
        old = existing.get(li, [])
        for en, (line, row) in ents.items():
            cid = int(row['char_id'], 0)
            if not 1 <= cid <= ucount:
                raise SystemExit(f'{path}:{line}: unit {cid} does not exist (1-{ucount})')
        if sorted(ents) == list(range(len(old))):
            for en, (line, row) in ents.items():
                a = old[en]
                rec = bytearray(rom[a:a + 8])
                _put_fields(rec, fields, row, path, line)
                if rec != rom[a:a + 8]:
                    rom[a:a + 8] = rec
                    changes += 1
            continue
        data = bytearray()
        for en in sorted(ents):
            line, row = ents[en]
            miss = [c for c, _, _ in fields if c not in row and L.COLUMN_ALIASES.get(c) not in row]
            if miss:
                raise SystemExit(f'{path}:{line}: new entries need every column ({", ".join(miss)})')
            rec = bytearray(8)
            _put_fields(rec, fields, row, path, line)
            data += rec
        data += b'\xff\xff'
        if old and len(data) <= 8 * len(old) + 2:
            fo = old[0]
        else:
            fo, _ = space.alloc(0x810000, len(data))
            off = fo - L.DEPLOY_DIR
            rom[L.DEPLOY_DIR + 2 * li:L.DEPLOY_DIR + 2 * li + 2] = off.to_bytes(2, 'little')
        rom[fo:fo + len(data)] = data
        changes += 1
    return changes


def apply_project(rom, proj, space=None, far=None):
    space = space or L.BankSpace(rom)
    changes = SK.apply(rom, proj, space, far)          # first: it sets the skill names the tables use
    far = far or L.FreeSpace()
    added = _add_units(rom, proj, space)
    changes += len(added)
    for tname, (rows_fn, fields) in L.TABLES.items():
        path = os.path.join(proj, tname + '.csv')
        if not os.path.exists(path):
            continue
        if tname == 'deploy':
            changes += _apply_deploy(rom, path, space)
            continue
        rows = {str(idx): (addr, size) for idx, addr, size, _ in rows_fn(rom)}
        with open(path, newline='') as f:
            for line, row in enumerate(csv.DictReader(f), start=2):
                key = row['index'].strip()
                if key not in rows:
                    raise SystemExit(f'{path}:{line}: unknown index {key!r} (only units_generic.csv, units_children.csv and deploy.csv can gain rows)')
                a, size = rows[key]
                if int(key) in added:                  # new unit: blank cells keep the defaults
                    row = {k: v for k, v in row.items() if (v or '').strip() != ''}
                rec = bytearray(rom[a:a + size])
                _put_fields(rec, fields, row, path, line, tname)
                if rec != rom[a:a + size]:
                    changes += 1
                    rom[a:a + size] = rec
    path = os.path.join(proj, 'item_instances.csv')
    if os.path.exists(path):
        with open(path, newline='') as f:
            for row in csv.DictReader(f):
                i, t = int(row['instance']), int(row['item_type'])
                if rom[L.INSTANCES + i] != t:
                    rom[L.INSTANCES + i] = t
                    changes += 1
    changes += _apply_portraits(rom, proj, far)
    changes += G2.apply(rom, proj, space, added)  # after the unit records: reads units_children.csv
    return changes


def _check_names(rom):
    for k in range(4):
        off = {0: 15, 2: 15, 1: 5, 3: 3}[k]
        for idx, a, _, _ in L.unit_rows(rom, k):
            nid = rom[a + off] | rom[a + off + 1] << 8
            if nid < 576 and NM.slot_empty(rom, nid):
                raise SystemExit(f'unit {idx} uses name_id {nid}, which has no name yet: '
                                 f'give it one in names.csv (character,{nid},...)')


def write_ips(orig, new, path):
    out = bytearray(b'PATCH')
    i, n = 0, len(new)
    while i < n:
        if orig[i] == new[i]:
            i += 1
            continue
        j = i
        while j < n and j - i < 0xFFFF and (orig[j] != new[j] or (j + 1 < n and orig[j + 1] != new[j + 1])):
            j += 1
        if i == 0x454F46:  # 'EOF' offset collides with the terminator
            i -= 1
        out += i.to_bytes(3, 'big') + (j - i).to_bytes(2, 'big') + new[i:j]
        i = j
    out += b'EOF'
    open(path, 'wb').write(out)


def build(rom_path, proj, out_path, ips=None, hover=False):
    copier, rom = L.load_rom(rom_path)
    clean = bytes(rom)
    if hover:   # unit stats in the map box; first, so the project's own data goes around it
        import fe4hoverpatch
        if fe4hoverpatch.apply(rom):
            print('added unit stats to the map box (MT / HIT / AS / AVO)')
        else:
            print('unit stats in the map box: this ROM\'s code is different there; left out')
    space = L.BankSpace(rom)
    far = L.FreeSpace()
    n = apply_project(rom, proj, space, far)
    n += EV.apply_events(rom, os.path.join(proj, 'events'), space, far)
    n += G2.apply_scenes(rom, proj, space, far)     # after the project's own scripts
    n += MP.apply_maps(rom, os.path.join(proj, 'maps'), far)
    n += NM.apply(rom, os.path.join(proj, 'names.csv'), far, space)
    n += LOC.apply(rom, os.path.join(proj, 'locations.csv'), space)
    n += LOC.apply_arena(rom, os.path.join(proj, 'arena.csv'), space)
    n += LOC.apply_talks(rom, os.path.join(proj, 'talks.csv'), space)
    n += AR.apply(rom, proj, space)
    _check_names(rom)
    L.save_rom(out_path, copier, rom)
    print(f'{n} record(s) changed -> {out_path}')
    if ips:
        hdr = bytes(copier)
        write_ips(hdr + clean, hdr + bytes(rom), ips)
        print('wrote', ips)


def diff(a_path, b_path):
    _, a = L.load_rom(a_path)
    _, b = L.load_rom(b_path)
    SK.set_maps(b)
    for tname, (rows_fn, fields) in L.TABLES.items():
        rb_rows = {idx: (addr, size, label) for idx, addr, size, label in rows_fn(b)}
        seen = set()
        for idx, addr, size, label in rows_fn(a):
            seen.add(idx)
            if idx not in rb_rows:
                print(f'{tname}[{idx}] {label}: removed')
                continue
            ra, rb = a[addr:addr + size], b[rb_rows[idx][0]:rb_rows[idx][0] + size]
            if ra == rb:
                continue
            for col, off, kind in fields:
                va, vb = L.get_field(ra, off, kind), L.get_field(rb, off, kind)
                if va != vb:
                    print(f'{tname}[{idx}] {label}: {col} {va} -> {vb}')
        for idx, (addr, size, label) in rb_rows.items():
            if idx not in seen:
                rb = b[addr:addr + size]
                print(f'{tname}[{idx}] {label}: added (' + ', '.join(
                    f'{col} {L.get_field(rb, off, kind)}' for col, off, kind in fields) + ')')
    for i in range(L.INSTANCE_COUNT):
        if a[L.INSTANCES + i] != b[L.INSTANCES + i]:
            print(f'item_instances[{i}]: {a[L.INSTANCES + i]} -> {b[L.INSTANCES + i]}')


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) >= 3 and args[0] == 'extract':
        extract(args[1], args[2])
    elif len(args) >= 4 and args[0] == 'build':
        ips = args[args.index('--ips') + 1] if '--ips' in args else None
        build(args[1], args[2], args[3], ips, '--hover-stats' in args)
    elif len(args) == 3 and args[0] == 'diff':
        diff(args[1], args[2])
    else:
        print(__doc__)
        sys.exit(1)
