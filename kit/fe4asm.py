#!/usr/bin/env python3
"""Rebuild script blocks that had commands inserted or removed.

The .evt files list each block (a chapter script, a scene or an AI program) as
`ADDR: hex ; comment` lines.  Lines that start with `+` instead of an address
are new commands; deleting a line removes that command.  A block whose layout
changed is reassembled into free space:

  * jumps inside the block are retargeted to the moved commands,
  * jumps that leave the block must stay in the same bank (they keep pointing
    at the original code),
  * the block's start pointer is updated by the caller,
  * the result is decoded again with the game's own rules and must give back
    exactly the lines that were written.

A jump in a new line can also name a command of its own block: `@L3` is the
2-byte address of the block's 4th command line (counting from 0), wherever it
ends up.
"""
import re

from dis65816 import snes_to_file

_TOK = r'(?:[0-9A-Fa-f]{2}|@N\d{5}|@L\d{1,3})'
LINE = re.compile(r'^\s*([0-9A-Fa-f]{6}|\+)\s*:?\s*(' + _TOK + r'(?:\s+' + _TOK + r')*)\s*(;.*)?$')
SYMBOL = re.compile(r'^@(N\d{5})$')       # a new message from dialogue.txt: its 3-byte address
STEP = re.compile(r'^@L(\d{1,3})$')       # a command of the same block: its 2-byte address
HEAD = re.compile(r'^==\s*(.*?)\s*@([0-9A-Fa-f]{6})')


def parse_bytes(text, symbols=None, where='', steps=None):
    """Hex pairs, where @Nxxxxx stands for the 3-byte address of new message Nxxxxx and @Lk for the
    address of command k of the block (steps collects [(byte offset, k)]; placeholder 00 00)."""
    out = bytearray()
    for t in text.split():
        m = STEP.match(t)
        if m:
            if steps is None:
                raise SystemExit(f'{where}: {t} only works inside a script block')
            steps.append((len(out), int(m.group(1))))
            out += b'\0\0'
            continue
        m = SYMBOL.match(t)
        if m:
            if symbols is None or m.group(1) not in symbols:
                raise SystemExit(f'{where}: {t} is not a new message in dialogue.txt')
            a = symbols[m.group(1)]
            out += bytes([a & 0xFF, (a >> 8) & 0xFF, a >> 16])
        else:
            try:
                out.append(int(t, 16))
            except ValueError:
                raise SystemExit(f'{where}: bad hex')
    return bytes(out)


def parse_blocks(path, symbols=None):
    """[{'label', 'start', 'line', 'cmds': [(addr or None, bytes, line_no)]}] in file order."""
    blocks, cur = [], None
    for ln, line in enumerate(open(path), start=1):
        h = HEAD.match(line)
        if h:
            cur = {'label': h.group(1), 'start': int(h.group(2), 16), 'line': ln, 'cmds': []}
            blocks.append(cur)
            continue
        m = LINE.match(line)
        if not m or line.lstrip().startswith(';'):
            continue
        if cur is None:
            raise SystemExit(f'{path}:{ln}: command outside a "== ..." block')
        steps = []
        data = parse_bytes(m.group(2), symbols, f'{path}:{ln}', steps)
        if not data:
            raise SystemExit(f'{path}:{ln}: empty command')
        addr = None if m.group(1) == '+' else int(m.group(1), 16)
        if steps:
            cur.setdefault('steps', {})[len(cur['cmds'])] = steps
        cur['cmds'].append((addr, data, ln))
    for blk in blocks:
        for i, st in blk.get('steps', {}).items():
            for _, k in st:
                if k >= len(blk['cmds']):
                    raise SystemExit(f"{path}:{blk['cmds'][i][2]}: @L{k}: the block has {len(blk['cmds'])} commands")
    return blocks


def unchanged_layout(block, orig):
    """True if the block lists exactly the original commands (bytes may differ, lengths may not)."""
    if block.get('steps'):
        return False                             # @Lk jumps are filled in by assemble()
    got = [(a, len(b)) for a, b, _ in block['cmds']]
    return got == [(a, len(b)) for a, b in orig]


def jumps_ev(b):
    return [(1, 'abs')] if b[0] == 0x2B and len(b) >= 3 else []


def jumps_sc(b):
    if len(b) == 3 and 2 <= b[0] <= 4:
        return [(1, 'abs')]
    if len(b) == 3 and b[0] in (5, 6):
        return [(1, 'rel')]
    return []


def target(addr, b, pos, kind):
    w = b[pos] | b[pos + 1] << 8
    if kind == 'abs':
        return (addr & 0xFF0000) | w
    return (addr & 0xFF0000) | ((addr + pos + w) & 0xFFFF)


def _targets(block, path, jumps):
    """[(line index, arg pos, kind, original target)] for every jump in the block."""
    out = []
    bank = block['start'] & 0xFF0000
    steps = block.get('steps', {})
    for i, (a, b, ln) in enumerate(block['cmds']):
        for p, kind in jumps(b):
            if any(q == p for q, _ in steps.get(i, ())):
                continue                         # @Lk: filled in after layout
            w = b[p] | b[p + 1] << 8
            if kind == 'abs':
                t = bank | w
            else:
                if a is None:
                    raise SystemExit(f'{path}:{ln}: a new relative jump cannot be placed; use an absolute jump')
                t = (a & 0xFF0000) | ((a + p + w) & 0xFFFF)
            out.append((i, p, kind, t))
    return out


def assemble(rom, block, path, jumps, placer):
    """Lay out block['cmds'] in free space.  placer(size, same_bank) -> snes addr.

    Jump targets in the file (also in new lines) are original addresses.
    Returns (new_start, {old addr: new addr}, [new addr per line])."""
    cmds = block['cmds']
    olds = {a for a, _, _ in cmds if a is not None}
    tg = _targets(block, path, jumps)
    leaves = any(t not in olds for _, _, _, t in tg)
    size = sum(len(b) for _, b, _ in cmds)
    new_start = placer(size, leaves)
    pos, newaddr = new_start, []
    for a, b, _ in cmds:
        newaddr.append(pos)
        pos = (pos & 0xFF0000) | ((pos + len(b)) & 0xFFFF)
    remap = {a: n for (a, _, _), n in zip(cmds, newaddr) if a is not None}
    data = [bytearray(b) for _, b, _ in cmds]
    for i, p, kind, t in tg:
        na = newaddr[i]
        nt = remap.get(t, t)
        if (nt >> 16) != (na >> 16):
            raise SystemExit(f'{path}:{cmds[i][2]}: jump to {t:06X} leaves this block and the block '
                             f'could not stay in bank ${t >> 16:02X}')
        if kind == 'abs':
            data[i][p:p + 2] = (nt & 0xFFFF).to_bytes(2, 'little')
        else:
            data[i][p:p + 2] = ((nt - na - p) & 0xFFFF).to_bytes(2, 'little')
    for i, st in block.get('steps', {}).items():
        for p, k in st:
            data[i][p:p + 2] = (newaddr[k] & 0xFFFF).to_bytes(2, 'little')
    out = b''.join(bytes(d) for d in data)
    fo = snes_to_file(new_start)
    rom[fo:fo + len(out)] = out
    return new_start, remap, newaddr


def make_placer(space, far_alloc=None):
    """Prefer the zero tail of the block's own bank; fall back to far_alloc(size)
    (the shared free banks) when the block has no jumps leaving it."""
    def for_bank(bank):
        def place(size, same_bank):
            try:
                return space.alloc(bank, size)[1]
            except SystemExit:
                if same_bank or far_alloc is None:
                    raise
                return far_alloc(size)
        return place
    return for_bank
