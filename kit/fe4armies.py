#!/usr/bin/env python3
"""FE4 armies and enemy AI orders.

Army table: $86:C784, 72 x ptr24 (army IDs 0-71).  At chapter start the
opening script assigns armies to slots with event command $4B [slot][army]
(slot 0 is the player).  A deploy-list entry's `army_slot` picks the slot and
its `orders` picks one of that army's AI programs (1-based; 0 = none).

Army record (9 bytes, pointers are 16-bit in the record's bank):
  +0 name: castle name ID ($FF none; $35 is used for Sigurd's army)
  +1, +2 unknown bytes
  +3 word -> member unit IDs (words, $FFFF): spawned/joined when the army is set up
  +5 word -> castles the army holds (location index words, $FFFF)
  +7 word -> AI programs (ptr24 each, $FFFF); `orders` n uses entry n-1

AI program VM: $87:CD1E, 36 opcodes through $87:CD38.  A unit's program runs
from the top on each of its turns; each command either acts (and ends the
unit's decision) or falls through to the next.  $FF ends the program.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
from dis65816 import snes_to_file
import fe4locations as LOC

ARMY_TABLE = 0x06C784
ARMY_COUNT = 72

# opcode: (name, argument bytes, jump-target offset within the arguments or None)
AI_OPS = {
    0x00: ('STOP', 0, None),            0x01: ('GOTO', 2, 0),
    0x02: ('SET_MODE', 1, None),        0x03: ('PACE', 1, None),
    0x04: ('SPARE_SLOT', 1, None),      0x05: ('OP_05', 0, None),
    0x06: ('SEIZE_CASTLE', 2, None),    0x07: ('GUARD_CASTLE', 2, None),
    0x08: ('RAID_VILLAGE', 1, None),    0x09: ('MOVE_TO', 5, None),
    0x0A: ('ATTACK_IN_REACH', 0, None), 0x0B: ('ATTACK_IN_REACH_OR_GO_ON', 0, None),
    0x0C: ('FORMATION', 2, None),       0x0D: ('ATTACK_UNIT', 2, None),
    0x0E: ('FOLLOW_UNIT', 3, None),     0x0F: ('RETREAT', 0, None),
    0x10: ('RETREAT_IF_CLEAR', 0, None), 0x11: ('RETREAT_IF_GROUP_LOW', 1, None),
    0x12: ('FALL_BACK', 0, None),       0x13: ('HOLD', 0, None),
    0x14: ('REINFORCE_EVERY', 1, None), 0x15: ('SET_FLAG', 3, None),
    0x16: ('CLEAR_FLAG', 3, None),      0x17: ('RAID_ANY_VILLAGE', 0, None),
    0x18: ('ATTACK_ANY', 0, None),      0x19: ('ATTACK_ANY_7', 0, None),
    0x1A: ('SURROUND', 0, None),        0x1B: ('SURROUND', 0, None),
    0x1C: ('SURROUND', 0, None),        0x1D: ('SURROUND', 0, None),
    0x1E: ('RETREAT_IF_HURT', 3, None), 0x1F: ('IF_TURN_GOTO', 3, 1),
    0x20: ('IF_FLAG_GOTO', 5, 3),       0x21: ('IF_NOT_FLAG_GOTO', 5, 3),
    0x22: ('IF_NO_TARGET_GOTO', 2, 0),  0x23: ('IF_ASM_GOTO', 5, 3),
}
# FORMATION shapes ($87:DCD8: 15 lists of 18 x/y offsets from the group's centre)
# and facings ($87:DAB0 rotates them); names are by look.
FORMATIONS = ['none (all aim for the same spot)', 'wedge, narrow', 'wide wings', 'arrowhead', 'triangle',
              'line abreast (one row)', 'block, two rows', 'single file', 'column, two wide',
              'column, three wide', 'V, wide', 'zigzag column', 'ring', 'cluster', 'cluster, loose']
FACINGS = ['south', 'west', 'north', 'east']
STOPS = {0x00, 0x01, 0xFF}


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def _p24(rom, fo):
    return rom[fo] | rom[fo + 1] << 8 | rom[fo + 2] << 16


def army_addr(rom, i):
    return _p24(rom, ARMY_TABLE + 3 * i)


def _wlist(rom, bank, p, step=2, limit=64):
    if p == 0:
        return None
    fo = snes_to_file(bank | p)
    out = []
    while _w(rom, fo) != 0xFFFF:
        out.append(_w(rom, fo) if step == 2 else _p24(rom, fo))
        fo += step
        if len(out) > limit:
            raise ValueError('unterminated list at %06X' % (bank | p))
    return out


def army(rom, i):
    a = army_addr(rom, i)
    fo = snes_to_file(a)
    bank = a & 0xFF0000
    r = rom[fo:fo + 9]
    return {'addr': a, 'file': fo, 'bank': bank, 'name': r[0], 'unk1': r[1], 'unk2': r[2],
            'members_ptr': _w(r, 3), 'castles_ptr': _w(r, 5), 'orders_ptr': _w(r, 7),
            'members': _wlist(rom, bank, _w(r, 3)), 'castles': _wlist(rom, bank, _w(r, 5)),
            'orders': _wlist(rom, bank, _w(r, 7), step=3)}


def slot_assignments(rom):
    """{army id: [(chapter, slot)]} from event command $4B in each opening script."""
    import fe4events as EV
    ctx = EV.Ctx(bytes(rom))
    out = {}
    for ch, name, scripts in ctx.chapter_scripts():
        for label, start in scripts:
            for addr, b in ctx.ev_walk(start):
                if b[0] == 0x4B and len(b) == 3:
                    out.setdefault(b[2], []).append((ch, b[1]))
    return out


# ---------------------------------------------------------------- AI programs
def ai_walk(rom, start):
    """Decode every command reachable from start: {addr: bytes}."""
    seen, todo = {}, [start]
    while todo:
        a = todo.pop()
        while a not in seen:
            fo = snes_to_file(a)
            op = rom[fo]
            if op == 0xFF:
                seen[a] = bytes([0xFF])
                break
            if op not in AI_OPS:
                raise ValueError('unknown AI opcode %02X at %06X' % (op, a))
            name, n, jt = AI_OPS[op]
            b = bytes(rom[fo:fo + 1 + n])
            seen[a] = b
            if jt is not None:
                todo.append((a & 0xFF0000) | _w(b, 1 + jt))
            if op in STOPS:
                break
            a += 1 + n
    return seen


def ai_comment(rom, b, com, locnames):
    op = b[0]
    if op == 0xFF:
        return 'END', ''
    name, n, jt = AI_OPS[op]
    w = lambda i: b[i] | b[i + 1] << 8  # noqa: E731
    c = ''
    if op in (0x06, 0x07, 0x08):
        c = 'location %d%s' % (b[1], locnames.get(b[1], ''))
    elif op == 0x09:
        c = 'to (%d,%d) unless flag %d.%d, then set it' % (b[4], b[5], w(1), b[3])
    elif op in (0x0D, 0x0E):
        c = com.unit(w(1))
        if op == 0x0E:
            c += ', within %d' % b[3]
    elif op == 0x0C:
        c = '%s, facing %s' % (FORMATIONS[b[1]] if b[1] < len(FORMATIONS) else 'shape %d' % b[1], FACINGS[b[2] & 3])
    elif op == 0x03:
        c = 'full move' if b[1] == 0 else 'about %d%% of its move' % round(b[1] * 100 / 256)
    elif op == 0x04:
        c = 'slot %d' % b[1]
    elif op == 0x11:
        c = 'under %d%% of its group left' % round(b[1] * 100 / 256)
    elif op == 0x14:
        c = 'every %d turn%s' % (b[1], '' if b[1] == 1 else 's')
    elif op == 0x1E:
        c = 'HP at or below %d%%' % round(b[1] * 100 / 256)
    elif op in (0x15, 0x16):
        c = 'flag %d.%d' % (w(1), b[3])
    elif op == 0x1F:
        c = 'turn >= %d -> %04X' % (b[1], w(2))
    elif op in (0x20, 0x21):
        c = 'flag %d.%d -> %04X' % (w(1), b[3], w(4))
    elif op in (0x01, 0x22):
        c = '-> %04X' % w(1)
    elif op == 0x23:
        c = 'asm %06X -> %04X' % (b[1] | b[2] << 8 | b[3] << 16, w(4))
    return name, c


def _locnames(rom):
    """{chapter: {index: ' (Name)'}}"""
    out = {}
    for ch, q, n in LOC.records(rom):
        nm = LOC.castle_name(rom, rom[q + 1]) if rom[q + 2] == 0 else 'village'
        out.setdefault(ch, {})[rom[q]] = ' (%s)' % nm
    return out


def all_ai_commands(rom):
    cmds = {}
    for i in range(ARMY_COUNT):
        for p in army(rom, i)['orders'] or []:
            cmds.update(ai_walk(rom, p))
    return cmds


def _listing(rom):
    """[(label, start, [addrs])] in the order ai_orders.evt lists them (shared code once)."""
    out, done = [], set()
    for i in range(ARMY_COUNT):
        for k, p in enumerate(army(rom, i)['orders'] or [], start=1):
            lab = 'army %d orders %d' % (i, k)
            if p in done:
                out.append((lab, p, []))
                continue
            addrs = [a for a in sorted(ai_walk(rom, p)) if a not in done]
            done.update(addrs)
            out.append((lab, p, addrs))
    return out


# ---------------------------------------------------------------- export
ARMY_FIELDS = ['army', '_used_in', 'name', '_name', 'unk1', 'unk2', 'members', '_member_names',
               'castles', '_orders']


def export(rom, proj):
    import fe4events as EV
    com = EV.Commenter(rom)
    used = slot_assignments(rom)
    locn = _locnames(rom)
    path = os.path.join(proj, 'armies.csv')
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ARMY_FIELDS)
        w.writeheader()
        for i in range(ARMY_COUNT):
            a = army(rom, i)
            w.writerow({
                'army': i,
                '_used_in': ' '.join('ch%d/slot%d' % cs for cs in used.get(i, [])),
                'name': a['name'], '_name': LOC.castle_name(rom, a['name']) if a['name'] < 0x40 else '',
                'unk1': a['unk1'], 'unk2': a['unk2'],
                'members': ';'.join(str(u) for u in a['members'] or []),
                '_member_names': ' / '.join(com.unit(u).rsplit('(', 1)[0] for u in a['members'] or []),
                'castles': ';'.join(str(c) for c in a['castles'] or []),
                '_orders': len(a['orders'] or []),
            })
    print('wrote', path)

    lines = ['; FE4 enemy AI orders.  Each army has numbered programs; a deployed unit runs',
             '; program <orders> of the army in its <army_slot> (see deploy.csv, armies.csv).',
             '; A unit runs its program from the top each turn: the first command that can',
             '; act does so; the rest fall through.  Edit the hex bytes; add a command with a',
             '; line starting with + (e.g. "+ 17"), remove one by deleting its line.',
             '; Names ending in ? or OP_xx are not confirmed (see ROM_MAP.md for what each does).', '']
    done = set()
    for i in range(ARMY_COUNT):
        a = army(rom, i)
        if not a['orders']:
            continue
        chs = [c for c, s in used.get(i, [])]
        ln = locn.get(chs[0], {}) if chs else {}
        for k, p in enumerate(a['orders'], start=1):
            lines.append('== army %d orders %d @%06X%s' % (i, k, p, '  (shared, listed above)' if p in done else ''))
            if p in done:
                lines.append('')
                continue
            cmds = ai_walk(rom, p)
            for addr in sorted(cmds):
                if addr in done:
                    continue
                done.add(addr)
                b = cmds[addr]
                name, c = ai_comment(rom, b, com, ln)
                lines.append(('%06X: %-18s ; %-17s %s' % (addr, ' '.join('%02X' % x for x in b), name, c)).rstrip())
            lines.append('')
    path = os.path.join(proj, 'ai_orders.evt')
    open(path, 'w').write('\n'.join(lines) + '\n')
    print('wrote', path)


# ---------------------------------------------------------------- apply
_LINE = re.compile(r'^\s*([0-9A-Fa-f]{6}):\s*([0-9A-Fa-f ]+?)\s*(;.*)?$')


def _ids(text, where, lo, hi, what):
    out = []
    for t in text.replace(',', ';').split(';'):
        t = t.strip()
        if t:
            v = int(t, 0)
            if not lo <= v <= hi:
                raise SystemExit(f'{where}: {what} {v} out of range {lo}-{hi}')
            out.append(v)
    return out


def jumps_ai(b):
    op = AI_OPS.get(b[0])
    return [(1 + op[2], 'abs')] if op and op[2] is not None and len(b) == 1 + op[1] else []


def _apply_orders(rom, path, space):
    """ai_orders.evt: in-place edits, or rebuild programs with inserted/removed commands."""
    import fe4asm as AS
    clean = bytes(rom)
    cmds = all_ai_commands(clean)
    starts = {}                      # program start -> [(army, file offset of its ptr24)]
    for i in range(ARMY_COUNT):
        a = army(clean, i)
        if a['orders_ptr']:
            fo = snes_to_file(a['bank'] | a['orders_ptr'])
            for k, p in enumerate(a['orders'] or []):
                starts.setdefault(p, []).append(fo + 3 * k)
    placer = AS.make_placer(space)
    groups = {(lab, st): addrs for lab, st, addrs in _listing(clean)}
    changes = 0
    for blk in AS.parse_blocks(path):
        if not blk['cmds']:
            continue
        for addr, data, ln in blk['cmds']:
            if addr is not None and addr not in cmds:
                raise SystemExit(f'{path}:{ln}: {addr:06X} is not the start of a known AI command')
            if data[0] != 0xFF and (data[0] not in AI_OPS or AI_OPS[data[0]][1] + 1 != len(data)):
                raise SystemExit(f'{path}:{ln}: opcode {data[0]:02X} takes '
                                 f'{AI_OPS[data[0]][1] if data[0] in AI_OPS else "?"} argument bytes')
        orig = groups.get((blk['label'], blk['start']), [])
        same = ([a for a, _, _ in blk['cmds']] == orig and not blk.get('steps')
                and all(len(d) == len(cmds[a]) for a, d, _ in blk['cmds']))
        if same:
            for addr, data, ln in blk['cmds']:
                fo = snes_to_file(addr)
                if rom[fo:fo + len(data)] != data:
                    rom[fo:fo + len(data)] = data
                    changes += 1
            continue
        st = blk['start']
        whole = orig and orig[0] == st and all(
            cmds[a][0] in STOPS or ((a & 0xFF0000) | ((a + len(cmds[a])) & 0xFFFF)) in orig for a in orig)
        if st not in starts or not whole:
            raise SystemExit(f"{path}:{blk['line']}: this program shares code with one listed earlier, so "
                             'commands cannot be inserted here; insert them in the earlier program')
        new_start, remap, newaddrs = AS.assemble(rom, blk, path, jumps_ai, placer(st & 0xFF0000))
        for fo in starts[st]:
            rom[fo:fo + 3] = new_start.to_bytes(3, 'little')
        try:
            got = ai_walk(rom, new_start)
        except ValueError as e:
            raise SystemExit(f"{path}:{blk['line']}: the edited program does not decode: {e}")
        end = newaddrs[-1] + len(blk['cmds'][-1][1])
        for na, (_, d, ln) in zip(newaddrs, blk['cmds']):
            if len(got.get(na, d)) != len(d):
                raise SystemExit(f'{path}:{ln}: wrong length for this opcode')
        stray = [a for a in got if new_start <= a < end and a not in newaddrs]
        last = blk['cmds'][-1][1]
        if stray or last[0] not in STOPS:
            raise SystemExit(f"{path}:{blk['line']}: the program must end with FF, 00 or a GOTO")
        changes += 1
    return changes


def apply(rom, proj, space=None):
    changes = 0
    space = space or LOC.BankSpace(rom)
    path = os.path.join(proj, 'ai_orders.evt')
    if os.path.exists(path):
        changes += _apply_orders(rom, path, space)

    path = os.path.join(proj, 'armies.csv')
    if os.path.exists(path):
        for ln, row in enumerate(csv.DictReader(open(path, newline='')), start=2):
            where = f'{path}:{ln}'
            try:
                i = int(row['army'])
                if not 0 <= i < ARMY_COUNT:
                    raise SystemExit(f'{where}: army must be 0-{ARMY_COUNT - 1}')
                a = army(rom, i)
                rec = bytearray(rom[a['file']:a['file'] + 9])
                rec[0] = int(row['name'], 0)
                rec[1] = int(row['unk1'], 0)
                rec[2] = int(row['unk2'], 0)
                mem = _ids(row['members'], where, 1, L.unit_count(rom), 'unit')
                cas = _ids(row['castles'], where, 0, 63, 'location')
            except ValueError as e:
                raise SystemExit(f'{where}: {e}')
            for off, key, new in ((3, 'members', mem), (5, 'castles', cas)):
                old = a[key]
                if (old or []) == new:
                    continue
                if not new:
                    rec[off] = rec[off + 1] = 0
                    continue
                data = b''.join(v.to_bytes(2, 'little') for v in new) + b'\xff\xff'
                p = rec[off] | rec[off + 1] << 8
                if old is not None and len(new) <= len(old):
                    fo = snes_to_file(a['bank'] | p)
                else:
                    fo, sn = space.alloc(a['bank'], len(data))
                    rec[off], rec[off + 1] = sn & 0xFF, (sn >> 8) & 0xFF
                rom[fo:fo + len(data)] = data
            if rec != rom[a['file']:a['file'] + 9]:
                rom[a['file']:a['file'] + 9] = rec
                changes += 1
            elif any((a[k] or []) != v for k, v in (('members', mem), ('castles', cas))):
                changes += 1
    return changes


if __name__ == '__main__':
    _, r = L.load_rom(sys.argv[1])
    export(r, sys.argv[2])
