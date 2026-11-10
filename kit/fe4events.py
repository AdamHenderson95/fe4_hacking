#!/usr/bin/env python3
"""FE4 events, scenes and dialogue: dump to editable text, patch back.

  python fe4events.py dump <rom.smc> <outdir>

Writes into <outdir>:
  chNN_<name>.evt   each chapter's opening script and trigger list
  scenes.evt        all 562 scenes (cutscenes / conversations), by scene ID
  dialogue.txt      every message referenced by those scripts, editable text

.evt lines look like   86C8A7: 02 00 00 00 01 00   ; COND_TURN  turn 1
Change the hex bytes, keeping each command the same length.

dialogue.txt blocks look like
    @60597B  ; ch00 908114 TALK_SCENE
    {07}{00 3D}{00 3F}w{00 09}Oi, wait a sec!{02}
    No bows, you coward!{08}{01}
Edit the words; keep the {..} control tokens.  Line breaks in the file are
ignored ({02} is the in-game line break).  Changed messages are written to
free space and every known pointer to them is updated, so length is free.

`fe4hack.py build` applies <project>/events/ automatically.

Command lengths come from running the game's own handlers on a 65816
emulator (event VM: skip mode; scene VM: normal mode with external calls
stubbed), with three handler bugs patched by rule.  All 26 chapter scripts
and all 562 scenes decode end to end.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe4lib as L
import fe4asm as A
from cpu65816 import CPU, Halt
from dis65816 import snes_to_file

# ---------------------------------------------------------------- tables
EV_OPTABLE = 0x0683FA        # $86:83FA  event VM handlers (121)
EV_OPCOUNT = 121
CHAPTER_TABLE = 0x06C739     # $86:C739  13 chapter event headers
SC_OPTABLE = 0x11A50A        # $91:A50A  scene VM handlers (95)
SC_OPCOUNT = 95
SCENE_TABLE = 0x0FE8BF       # $8F:E8BF  562 x 3-byte scene pointers
SCENE_COUNT = 562
FREE_START, FREE_END = 0x700000, 0x7DD000   # empty banks $70-$7D (verified all zero); $7D:D000+ is for code hooks

CHAPTERS = ['prologue', 'ch01', 'ch02', 'ch03', 'ch04', 'ch05', 'ch06', 'ch07', 'ch08',
            'ch09', 'ch10', 'endgame', 'ch12_unused']

# Names ending in '?' are inferred from argument patterns, not yet confirmed in-game.
EV_NAMES = {
    0x00: 'BLOCK_END?', 0x02: 'COND_TURN', 0x04: 'COND_TALK', 0x05: 'COND_05?', 0x07: 'COND_07?',
    0x0A: 'COND_VISIT', 0x0B: 'COND_IN_AREA', 0x0C: 'COND_NEXT_TO?', 0x0D: 'COND_BATTLE',
    0x0E: 'COND_DEFEAT?', 0x0F: 'COND_UNIT?', 0x16: 'COND_TALK2', 0x1A: 'COND_DEATH',
    0x20: 'NOP2', 0x25: 'NOP2', 0x2E: 'NOP2', 0x21: 'ARMY_ORDER?', 0x2B: 'GOTO',
    0x30: 'RUN_SCENE', 0x31: 'TALK', 0x32: 'TALK_SCENE', 0x4B: 'SET_ARMY', 0x4D: 'ARMY_RELATION?',
    0x4E: 'DEPLOY', 0x4F: 'DEPLOY_INLINE', 0x50: 'INIT_ARMY?', 0x5F: 'MOVE_UNIT?',
    0x6B: 'MAP_TILE?', 0x6C: 'MAP_TILES?', 0x77: 'UNIT_LIST_OP',
    0x57: 'GIVE_ITEM', 0x70: 'STAT_UP',
}
SC_NAMES = {
    0x01: 'STOP', 0x02: 'GOTO', 0x03: 'IF_TRUE_GOTO', 0x04: 'IF_FALSE_GOTO',
    0x05: 'IF_TRUE_JR', 0x06: 'IF_FALSE_JR', 0x07: 'TEST_FLAG?', 0x0C: 'TEXT',
    0x14: 'TEXT_WINDOW', 0x45: 'CALL_ASM', 0x4A: 'EVENT', 0x4D: 'EVENT_ASYNC?',
}

STATS = ['HP', 'Str', 'Mag', 'Skl', 'Spd', 'Def', 'Res', 'Lck']
_EV_FIXED = {0x34: 2, 0x67: 3}   # skip-path bugs in the original handlers


# ---------------------------------------------------------------- event VM
class Ctx:
    def __init__(self, rom):
        self.rom = rom
        self.ev_h = [rom[EV_OPTABLE + 2 * i] | rom[EV_OPTABLE + 2 * i + 1] << 8 for i in range(EV_OPCOUNT)]
        self.sc_h = [rom[SC_OPTABLE + 2 * i] | rom[SC_OPTABLE + 2 * i + 1] << 8 for i in range(SC_OPCOUNT)]
        w = bytearray(0x20000)
        w[0x17C4:0x17CC] = b'\xff' * 8   # free async-task slots (scene op $24 waits otherwise)
        self.wram = bytes(w)

    def rd(self, a):
        return self.rom[snes_to_file(a)]

    def ev_len(self, addr):
        op = self.rd(addr)
        if op >= EV_OPCOUNT:
            raise Halt('event opcode %02X out of range' % op)
        if op in _EV_FIXED:
            return _EV_FIXED[op]
        if op == 0x5F:
            return 10 if self.rd(addr + 5) == 0x0B else 8
        c = CPU(self.rom)
        c.P = 0x05                      # 16-bit regs, carry set = skip mode
        c.Y = (addr + 1) & 0xFFFF
        c.DB = addr >> 16
        c.S = 0x1FF
        c.call(0x860000 | self.ev_h[op], max_steps=20000)
        return (c.Y - (addr & 0xFFFF)) & 0xFFFF

    def ev_walk(self, addr, limit=10000):
        out = []
        for _ in range(limit):
            fo = snes_to_file(addr)
            if self.rom[fo] | self.rom[fo + 1] << 8 == 0xFFFF:
                out.append((addr, bytes(self.rom[fo:fo + 2])))
                return out
            n = self.ev_len(addr)
            if not 1 <= n <= 64:
                raise Halt('bad event length %d at %06X' % (n, addr))
            out.append((addr, bytes(self.rom[fo:fo + n])))
            addr = (addr & 0xFF0000) | ((addr + n) & 0xFFFF)
        raise Halt('no terminator from %06X' % addr)

    # ------------------------------------------------------------ scene VM
    def sc_len(self, base, addr):
        """(kind, length) of the scene command at addr; base = scene start (for $30)."""
        b = self.rd(addr)
        w = b | self.rd(addr + 1) << 8
        if w == 0xFFFF:
            return 'END', 2
        if w == 0xFEFE:
            return 'PAD', 2
        if b == 0xFD:
            return 'YIELD', 1
        if b == 0x01:
            return 'STOP', 1
        if 2 <= b <= 6:
            return 'JUMP', 3
        if b == 0x45:
            return 'OP', 4
        if b in (0x4A, 0x4D):
            return 'OP', 1 + self.ev_len(addr + 1)
        if b >= SC_OPCOUNT or self.sc_h[b] == 0:
            raise Halt('scene opcode %02X invalid' % b)
        c = CPU(self.rom, wram=self.wram)
        c.stub_banks = {0x91, 0xD1}
        c.wram[0x30], c.wram[0x31], c.wram[0x32] = base & 0xFF, (base >> 8) & 0xFF, base >> 16
        pos = (addr - base) & 0xFFFF
        c.P = 0x04
        c.Y = pos + 1
        c.DB = 0x91
        c.S = 0x1FF
        c.call(0x910000 | self.sc_h[b], max_steps=50000)
        return 'OP', (c.Y - pos) & 0xFFFF

    def sc_decode(self, base):
        """Follow every branch. Returns {addr: bytes} of all reachable commands."""
        seen = {}
        work = [base]
        while work:
            a = work.pop()
            while a not in seen:
                kind, n = self.sc_len(base, a)
                if not 1 <= n <= 0x200:
                    raise Halt('bad scene length %d at %06X' % (n, a))
                fo = snes_to_file(a)
                seen[a] = bytes(self.rom[fo:fo + n])
                if kind in ('END', 'STOP'):
                    break
                if kind == 'JUMP':
                    op = self.rd(a)
                    arg = self.rd(a + 1) | self.rd(a + 2) << 8
                    tgt = (a & 0xFF0000) | (arg if op <= 4 else (a + 1 + arg) & 0xFFFF)
                    work.append(tgt)
                    if op == 2:
                        break
                a = (a & 0xFF0000) | ((a + n) & 0xFFFF)
        return seen

    # ------------------------------------------------------------ locations
    def chapter_scripts(self):
        out = []
        for ch in range(13):
            a = CHAPTER_TABLE + 3 * ch
            fo = snes_to_file(self.rom[a] | self.rom[a + 1] << 8 | self.rom[a + 2] << 16)
            init = self.rom[fo + 2] | self.rom[fo + 3] << 8 | self.rom[fo + 4] << 16
            trig = self.rom[fo + 5] | self.rom[fo + 6] << 8 | self.rom[fo + 7] << 16
            out.append((ch, CHAPTERS[ch], [('init', init), ('triggers', trig)]))
        return out

    def scene_ptrs(self):
        r = self.rom
        return [r[SCENE_TABLE + 3 * i] | r[SCENE_TABLE + 3 * i + 1] << 8 | r[SCENE_TABLE + 3 * i + 2] << 16
                for i in range(SCENE_COUNT)]

    def all_commands(self):
        """{addr: (vm, bytes, where)} for every decoded command."""
        cmds = {}
        for ch, name, scripts in self.chapter_scripts():
            for label, start in scripts:
                for a, b in self.ev_walk(start):
                    cmds[a] = ('ev', b, 'ch%02d' % ch)
        for sid, p in enumerate(self.scene_ptrs()):
            for a, b in self.sc_decode(p).items():
                cmds.setdefault(a, ('sc', b, 'scene %d' % sid))
        return cmds

    def text_refs(self, cmds=None):
        """{message_snes_addr: [(cmd_addr, ptr_field_offset, where, name)]}"""
        cmds = cmds or self.all_commands()
        refs = {}
        for a, (vm, b, where) in cmds.items():
            off = None
            if vm == 'ev' and b[0] in (0x31, 0x32) and len(b) >= 5:
                off = 2
            elif vm == 'sc' and b[0] in (0x0C, 0x14) and len(b) >= 4 and b != b'\xff\xff':
                off = 1
            if off is None:
                continue
            p = b[off] | b[off + 1] << 8 | b[off + 2] << 16
            if snes_to_file(p) is None:
                continue
            nm = (EV_NAMES if vm == 'ev' else SC_NAMES).get(b[0], '')
            refs.setdefault(p, []).append((a, off, where, nm))
        return refs


# ---------------------------------------------------------------- text codec
_CH = {}
for _i in range(26):
    _CH[0x10 + _i] = chr(65 + _i)
    _CH[0x2A + _i] = chr(97 + _i)
for _i in range(10):
    _CH[0x50 + _i] = chr(48 + _i)
_CH.update({0xBF: ' ', 0x44: '.', 0x45: ',', 0x46: '?', 0x47: '!', 0x48: "'", 0x49: '-'})
_CH_INV = {v: k for k, v in _CH.items()}

# Control-code lengths in bytes, measured by running the text renderer's own
# handlers ($91:8A01) on every code in the game's dialogue.
CTL_LEN = {0x05: 2}                      # single-byte codes 0x01-0x0F default to 1
EXT_LEN = {0x05: 3, 0x10: 4, 0x11: 4, 0x12: 3, 0x13: 3, 0x14: 3, 0x15: 4, 0x16: 4, 0x19: 4,
           0x1A: 4, 0x1B: 5, 0x1C: 3, 0x1D: 3, 0x1E: 4, 0x1F: 4, 0x20: 4, 0x2B: 3, 0x31: 3,
           0x32: 3, 0x33: 3, 0x3C: 3, 0x3F: 4, 0x80: 6, 0x81: 3, 0x82: 5, 0x83: 5, 0x84: 3,
           0x85: 5, 0x86: 3}             # "00 xx ..." codes; others are 2 bytes


def text_tokens(b, start=0, stop_at_end=True):
    """Split message bytes into (bytes, is_control) tokens."""
    out, i = [], start
    while i < len(b):
        x = b[i]
        if x == 0x00:
            n = EXT_LEN.get(b[i + 1], 2)
        elif x < 0x10:
            n = CTL_LEN.get(x, 1)
        else:
            out.append((b[i:i + 1], False))
            i += 1
            continue
        out.append((b[i:i + n], True))
        i += n
        if x == 0x01 and stop_at_end:
            break
    return out


def text_decode(b):
    out = []
    for tok, ctl in text_tokens(b, stop_at_end=False):
        if not ctl and tok[0] in _CH:
            out.append(_CH[tok[0]])
        else:
            out.append('{%s}' % ' '.join('%02X' % x for x in tok))
            if tok[0] in (0x01, 0x02):
                out.append('\n')
    return ''.join(out)


def text_encode(s):
    s = s.replace('\r', '').replace('\n', '')
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] == '{':
            j = s.index('}', i)
            out += bytes(int(x, 16) for x in s[i + 1:j].split())
            i = j + 1
            continue
        if s[i] not in _CH_INV:
            raise ValueError('character %r has no FE4 text code (use {XX})' % s[i])
        out.append(_CH_INV[s[i]])
        i += 1
    return bytes(out)


def message_end(rom, fo):
    """File offset just past the {01} that ends the message starting at fo."""
    n = sum(len(t) for t, _ in text_tokens(rom[fo:fo + 0x3000]))
    return fo + n


def text_preview(rom, addr, n=70):
    fo = snes_to_file(addr)
    out = ''
    for tok, ctl in text_tokens(rom[fo:fo + 0x1000]):
        if len(out) >= n:
            break
        if ctl:
            if tok[0] in (0x02, 0x04):
                out += ' '
            continue
        out += _CH.get(tok[0], '')
    return re.sub(r'\s+', ' ', out).strip()


def message_spans(rom, starts):
    """Message = bytes from its start through its terminating {01}."""
    return {a: (snes_to_file(a), message_end(rom, snes_to_file(a))) for a in starts}


# ---------------------------------------------------------------- dump
class Commenter:
    def __init__(self, rom):
        self.rom = rom
        self.names = L.unit_name_table(rom)
        self.addrs = L.unit_addrs(rom)
        self.inames = L.item_names(rom)

    def inst(self, x):
        t = self.rom[L.INSTANCES + x] if x < L.INSTANCE_COUNT else None
        return '%s(#%d)' % (self.inames[t] if t is not None and t < len(self.inames) else '?', x)

    def unit(self, uid):
        if uid in (0, 0xFFFF):
            return 'any'
        if not 1 <= uid <= len(self.addrs):
            return '#%d' % uid
        r = self.addrs[uid - 1]
        off = {0: 15, 2: 15, 1: 5, 3: 3}.get(self.rom[r])
        nid = self.rom[r + off] | self.rom[r + off + 1] << 8 if off else 0
        n = self.names[nid] if off and nid < len(self.names) else ''
        return '%s(%d)' % (n or 'unit', uid)

    def ev(self, b):
        op = b[0]
        w = lambda i: b[i] | b[i + 1] << 8  # noqa: E731
        try:
            if op == 0x02:
                return 'turn %d' % w(4)
            if op in (0x04, 0x16):
                return '%s talks to %s' % (self.unit(w(2)), self.unit(w(4)))
            if op == 0x0C:
                return '%s next to %s' % (self.unit(w(2)), self.unit(w(4)))
            if op == 0x0B:
                return '%s in (%d,%d)-(%d,%d)' % (self.unit(w(2)), b[4], b[5], b[6], b[7])
            if op in (0x0D, 0x0E):
                return '%s vs %s' % (self.unit(w(4)), self.unit(w(8)))
            if op in (0x0F, 0x1A):
                return self.unit(w(2))
            if op == 0x30:
                return 'scene %d' % w(2)
            if op in (0x31, 0x32):
                return '"%s"' % text_preview(self.rom, b[2] | b[3] << 8 | b[4] << 16)
            if op == 0x4E:
                return 'deploy list %d' % b[1]
            if op == 0x0A:
                return 'location %d (see locations.csv)' % w(4)
            if op == 0x2B:
                return '-> %04X' % w(1)
            if op == 0x4B and len(b) == 3:
                return 'slot %d = army %d (see armies.csv)' % (b[1], b[2])
            if op == 0x57:
                who = 'visitor' if w(1) == 0xFFFF else self.unit(w(1))
                return '%s gets %s' % (who, self.inst(b[3]))
            if op == 0x70:
                who = 'visitor' if b[1] == 0xFF else self.unit(b[1])
                stat = STATS[b[2]] if b[2] < len(STATS) else 'stat%d' % b[2]
                return '%s %s +%d' % (who, stat, b[3])
        except (IndexError, TypeError):
            pass
        return ''

    def sc(self, a, b):
        op = b[0]
        if b == b'\xff\xff':
            return 'END', ''
        if op == 0xFD:
            return 'YIELD', ''
        if b == b'\xfe\xfe':
            return 'PAD', ''
        name = SC_NAMES.get(op, 'SC_%02X' % op)
        if op in (0x0C, 0x14):
            return name, '"%s"' % text_preview(self.rom, b[1] | b[2] << 8 | b[3] << 16)
        if 2 <= op <= 6 and len(b) == 3:
            arg = b[1] | b[2] << 8
            t = arg if op <= 4 else (a + 1 + arg) & 0xFFFF
            return name, '-> %06X' % ((a & 0xFF0000) | t)
        if op in (0x4A, 0x4D):
            sub = EV_NAMES.get(b[1], 'OP_%02X' % b[1])
            c = self.ev(b[1:])
            return name, (sub + ' ' + c).strip()
        return name, ''


def dump(rom_path, outdir):
    _, rom = L.load_rom(rom_path)
    ctx = Ctx(rom)
    com = Commenter(rom)
    os.makedirs(outdir, exist_ok=True)
    n_ev = 0
    for ch, name, scripts in ctx.chapter_scripts():
        lines = ['; FE4 events - %s (chapter %d)' % (name, ch),
                 '; Edit the hex bytes. To add a command, write a line starting with + (e.g.',
                 '; "+ 57 01 00 7B"); to remove one, delete its line. Blocks that change size are',
                 '; moved to free space automatically.', '']
        for label, start in scripts:
            lines.append('== %s @%06X' % (label, start))
            for addr, b in ctx.ev_walk(start):
                hexs = ' '.join('%02X' % x for x in b)
                if b == b'\xff\xff':
                    lines.append('%06X: %-24s ; END' % (addr, hexs))
                    continue
                nm = EV_NAMES.get(b[0], 'OP_%02X' % b[0])
                lines.append(('%06X: %-24s ; %-14s %s' % (addr, hexs, nm, com.ev(b))).rstrip())
                n_ev += 1
            lines.append('')
        open(os.path.join(outdir, 'ch%02d_%s.evt' % (ch, name)), 'w').write('\n'.join(lines) + '\n')

    lines = ['; FE4 scenes (cutscenes and conversations), started by RUN_SCENE in chapter scripts.',
             '; Edit the hex bytes. Add a command with a line starting with + (e.g. "+ 4A 57 FF FF 7B");',
             '; remove one by deleting its line. Jump targets are always written as original addresses.', '']
    n_sc = 0
    for sid, p in enumerate(ctx.scene_ptrs()):
        cmds = ctx.sc_decode(p)
        lines.append('== scene %d @%06X' % (sid, p))
        prev_end = None
        for a in sorted(cmds):
            b = cmds[a]
            if prev_end is not None and a != prev_end:
                lines.append(';   ...')
            nm, c = com.sc(a, b)
            lines.append(('%06X: %-24s ; %-13s %s' % (a, ' '.join('%02X' % x for x in b), nm, c)).rstrip())
            prev_end = (a & 0xFF0000) | ((a + len(b)) & 0xFFFF)
            n_sc += 1
        lines.append('')
    open(os.path.join(outdir, 'scenes.evt'), 'w').write('\n'.join(lines) + '\n')

    cmds = ctx.all_commands()
    refs = ctx.text_refs(cmds)
    spans = message_spans(rom, refs)
    lines = ['; FE4 dialogue. Edit words, keep {..} tokens. File line breaks are ignored;',
             '; {02} = new line in game, {08} = wait for button, {01} = end of message.', '']
    for a in sorted(refs):
        fo, end = spans[a]
        where = ', '.join('%s %06X %s' % (w, ca, nm) for ca, _, w, nm in refs[a][:4])
        if len(refs[a]) > 4:
            where += ', +%d more' % (len(refs[a]) - 4)
        lines.append('@%06X  ; %s' % (a, where))
        lines.append(text_decode(rom[fo:end]).rstrip('\n'))
        lines.append('')
    open(os.path.join(outdir, 'dialogue.txt'), 'w').write('\n'.join(lines) + '\n')
    print(f'wrote {n_ev} event commands (13 chapters), {n_sc} scene commands (562 scenes), '
          f'{len(refs)} messages to {outdir}')


# ---------------------------------------------------------------- apply
_LINE = re.compile(r'^\s*([0-9A-Fa-f]{6}):\s*([0-9A-Fa-f ]+?)\s*(;.*)?$')


def _free_alloc(rom, size, cursor):
    """Next free run of `size` zero bytes in $70-$7D, not crossing a bank."""
    a = cursor[0]
    while a + size + 1 < FREE_END:
        if (a >> 16) != ((a + size) >> 16):
            a = ((a >> 16) + 1) << 16
            continue
        if not any(rom[a:a + size + 1]):
            cursor[0] = a + size + 1   # leave one zero byte gap
            return a
        a += 1 + max(i for i in range(size + 1) if rom[a + i]) if any(rom[a:a + size + 1]) else 1
    raise SystemExit('out of free space for dialogue')


def _verify_block(rom, vm, start, blk, newaddrs, path):
    """Decode the moved block with the game's rules; it must match the lines written."""
    ctx = Ctx(bytes(rom))
    for na, (_, b, ln) in zip(newaddrs, blk['cmds']):
        if b == b'\xff\xff':
            continue
        try:
            n = ctx.ev_len(na) if vm == 'ev' else ctx.sc_len(start, na)[1]
        except Halt as e:
            raise SystemExit(f'{path}:{ln}: {e}')
        if n != len(b):
            raise SystemExit(f'{path}:{ln}: opcode {b[0]:02X} takes {n} bytes here, not {len(b)}')
    try:
        if vm == 'ev':
            got = ctx.ev_walk(start)
        else:
            got = sorted(ctx.sc_decode(start).items())
    except Halt as e:
        raise SystemExit(f"{path}:{blk['line']}: the edited block does not decode: {e}")
    want = [(na, len(b)) for na, (_, b, _) in zip(newaddrs, blk['cmds'])]
    gotl = [(a, len(b)) for a, b in got]
    if vm == 'ev' and gotl != want:
        bad = next((i for i, (x, y) in enumerate(zip(gotl, want)) if x != y), min(len(gotl), len(want)))
        ln = blk['cmds'][min(bad, len(blk['cmds']) - 1)][2]
        raise SystemExit(f'{path}:{ln}: this command has the wrong length for its opcode, or the block '
                         f'is missing its FF FF end')
    if vm == 'sc':
        gd = dict(gotl)
        for (na, n), (_, _, ln) in zip(want, blk['cmds']):
            if gd.get(na) not in (n, None):
                raise SystemExit(f'{path}:{ln}: this command should be {gd[na]} bytes for its opcode')
        if not any(n == 2 and b == b'\xff\xff' for _, b, _ in [(0, c[1], 0) for c in blk['cmds']]):
            raise SystemExit(f"{path}:{blk['line']}: a scene must end with FF FF")


def apply_events(rom, evdir, space=None, far=None):
    """Apply edited .evt and dialogue.txt files. Returns number of changes."""
    if not os.path.isdir(evdir):
        return 0
    ctx = Ctx(bytes(rom))
    cmds = ctx.all_commands()
    changes = 0
    relmap = {}
    space = space or L.BankSpace(rom)
    far = far or L.FreeSpace()
    placer = A.make_placer(space, lambda size: far.alloc(size + 1))
    chapters = {(lab, st): (ch, i) for ch, _, scr in ctx.chapter_scripts() for i, (lab, st) in enumerate(scr)}
    scenes = {p: sid for sid, p in enumerate(ctx.scene_ptrs())}
    for fn in sorted(os.listdir(evdir)):
        if not fn.endswith('.evt'):
            continue
        path = os.path.join(evdir, fn)
        for blk in A.parse_blocks(path):
            st = blk['start']
            moved = None            # (table slot) for a block a hacked ROM had already moved
            if fn == 'scenes.evt':
                if st not in scenes:
                    m = re.match(r'scene\s+(\d+)$', blk['label'])
                    if not m or int(m.group(1)) >= len(scenes):
                        raise SystemExit(f"{path}:{blk['line']}: {st:06X} is not the start of a scene")
                    moved = SCENE_TABLE + 3 * int(m.group(1))
                    orig = []
                else:
                    orig = sorted(ctx.sc_decode(st).items())
                vm, jumps = 'sc', A.jumps_sc
            else:
                key = (blk['label'].split()[0], st)
                if key not in chapters:
                    m = re.match(r'ch(\d+)', fn)
                    hit = [v for (lab, _), v in chapters.items()
                           if m and v[0] == int(m.group(1)) and lab == key[0]]
                    if len(hit) != 1:
                        raise SystemExit(f"{path}:{blk['line']}: {st:06X} is not the start of a chapter script")
                    ch, i = hit[0]
                    a = CHAPTER_TABLE + 3 * ch
                    moved = snes_to_file(rom[a] | rom[a + 1] << 8 | rom[a + 2] << 16) + 2 + 3 * i
                    orig = []
                else:
                    orig = ctx.ev_walk(st)
                vm, jumps = 'ev', A.jumps_ev
            if A.unchanged_layout(blk, orig):
                for addr, data, ln in blk['cmds']:
                    fo = snes_to_file(addr)
                    if rom[fo:fo + len(data)] != data:
                        rom[fo:fo + len(data)] = data
                        changes += 1
                continue
            for addr, data, ln in blk['cmds']:
                if moved is None and addr is not None and addr not in dict(orig):
                    raise SystemExit(f'{path}:{ln}: {addr:06X} is not a command of this block')
            new_start, remap, newaddrs = A.assemble(rom, blk, path, jumps, placer(st & 0xFF0000))
            if moved is not None:
                t = moved
            elif vm == 'sc':
                t = SCENE_TABLE + 3 * scenes[st]
            else:
                ch, i = chapters[(blk['label'].split()[0], st)]
                a = CHAPTER_TABLE + 3 * ch
                t = snes_to_file(rom[a] | rom[a + 1] << 8 | rom[a + 2] << 16) + 2 + 3 * i
            rom[t:t + 3] = new_start.to_bytes(3, 'little')
            _verify_block(rom, vm, new_start, blk, newaddrs, path)
            relmap.update(remap)
            changes += 1

    path = os.path.join(evdir, 'dialogue.txt')
    if os.path.exists(path):
        refs = ctx.text_refs(cmds)
        spans = message_spans(ctx.rom, refs)
        blocks, cur, moved_refs = {}, None, None
        for ln, line in enumerate(open(path), start=1):
            line = line.rstrip('\n')
            if line.startswith(';'):
                continue
            if line.startswith('@'):
                cur = int(line[1:7], 16)
                if cur not in refs:
                    # a message an earlier build had moved: find who points at it now
                    if moved_refs is None:
                        c2 = Ctx(bytes(rom))
                        moved_refs = c2.text_refs(c2.all_commands())
                    if cur not in moved_refs:
                        raise SystemExit(f'{path}:{ln}: @{cur:06X} is not a known message')
                    refs[cur] = moved_refs[cur]
                    spans[cur] = None
                blocks[cur] = (ln, [])
            elif cur is not None and line.strip() != '':
                blocks[cur][1].append(line)
        for a, (ln, body) in blocks.items():
            try:
                new = text_encode(''.join(body))
            except ValueError as e:
                raise SystemExit(f'{path}:{ln}: {e}')
            if spans[a] is not None:
                fo, end = spans[a]
                if new == bytes(ctx.rom[fo:end]):
                    continue
            if not new.endswith(b'\x01'):
                raise SystemExit(f'{path}:{ln}: message must end with {{01}}')
            dest = far.alloc(len(new) + 1)
            rom[dest:dest + len(new)] = new
            snes = 0x400000 + (dest - 0x400000)          # banks $40-$7D map 1:1 to file 0x400000+
            for ca, off, _, _ in refs[a]:
                for c in {ca, relmap.get(ca, ca)}:
                    pfo = snes_to_file(c) + off
                    rom[pfo:pfo + 3] = bytes([snes & 0xFF, (snes >> 8) & 0xFF, snes >> 16])
            changes += 1
    return changes


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == 'dump':
        dump(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(1)
