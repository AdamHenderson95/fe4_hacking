"""Minimal 65816 interpreter for static analysis of FE4 code.

Runs routines against the ROM image with a flat 128 KiB WRAM and 8 KiB SRAM;
hardware registers read as 0 and writes are ignored. Good enough to execute
pure logic (table walks, script decoding) without the full console.
"""
from dis65816 import snes_to_file


class Halt(Exception):
    pass


class CPU:
    def __init__(self, rom, wram=None, sram=None):
        self.rom = rom
        self.wram = bytearray(wram) if wram else bytearray(0x20000)
        self.sram = bytearray(sram) if sram else bytearray(0x2000)
        self.A = self.X = self.Y = 0
        self.S = 0x1FF
        self.D = 0
        self.DB = 0
        self.PB = 0
        self.PC = 0
        self.P = 0x34  # M=1 X=1 I=1
        self.E = False
        self.steps = 0
        self.reads = []          # optional trace of ROM reads: (pc, file_offset)
        self.trace_reads = False
        self.last_pc = 0
        self.stub_banks = None   # if a set: JSL to other banks returns immediately

    # ---------------- memory
    def read(self, addr):
        addr &= 0xFFFFFF
        bank, off = addr >> 16, addr & 0xFFFF
        if bank in (0x7E, 0x7F):
            return self.wram[((bank - 0x7E) << 16) | off]
        if (bank < 0x40 or 0x80 <= bank < 0xC0):
            if off < 0x2000:
                return self.wram[off]
            if off < 0x6000:
                return 0
            if off < 0x8000:
                if (bank & 0x7F) >= 0x20:
                    return self.sram[off - 0x6000]
                return 0
        fo = snes_to_file(addr)
        if fo is None:
            return 0
        if self.trace_reads:
            self.reads.append((self.last_pc, fo))
        return self.rom[fo]

    def write(self, addr, v):
        addr &= 0xFFFFFF
        v &= 0xFF
        bank, off = addr >> 16, addr & 0xFFFF
        if bank in (0x7E, 0x7F):
            self.wram[((bank - 0x7E) << 16) | off] = v
        elif bank < 0x40 or 0x80 <= bank < 0xC0:
            if off < 0x2000:
                self.wram[off] = v
            elif 0x6000 <= off < 0x8000 and (bank & 0x7F) >= 0x20:
                self.sram[off - 0x6000] = v

    def r16(self, a):
        return self.read(a) | self.read(a + 1) << 8

    def w16(self, a, v):
        self.write(a, v)
        self.write(a + 1, v >> 8)

    # ---------------- flags
    @property
    def m8(self):
        return bool(self.P & 0x20)

    @property
    def x8(self):
        return bool(self.P & 0x10)

    def setf(self, mask, on):
        self.P = (self.P | mask) if on else (self.P & ~mask)

    def nz(self, v, eight):
        if eight:
            v &= 0xFF
            self.setf(0x80, v & 0x80)
        else:
            v &= 0xFFFF
            self.setf(0x80, v & 0x8000)
        self.setf(0x02, v == 0)
        return v

    def fix_x(self):
        if self.x8:
            self.X &= 0xFF
            self.Y &= 0xFF

    # ---------------- stack
    def push8(self, v):
        self.write(self.S, v)
        self.S = (self.S - 1) & 0xFFFF

    def pull8(self):
        self.S = (self.S + 1) & 0xFFFF
        return self.read(self.S)

    def push16(self, v):
        self.push8(v >> 8)
        self.push8(v)

    def pull16(self):
        lo = self.pull8()
        return lo | self.pull8() << 8

    # ---------------- fetch
    def fetch8(self):
        v = self.read((self.PB << 16) | self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch8()
        return lo | self.fetch8() << 8

    def fetch24(self):
        lo = self.fetch16()
        return lo | self.fetch8() << 16

    # ---------------- addressing: return 24-bit effective address
    def ea(self, mode):
        if mode == 'dp':
            return (self.D + self.fetch8()) & 0xFFFF
        if mode == 'dpx':
            return (self.D + self.fetch8() + self.X) & 0xFFFF
        if mode == 'dpy':
            return (self.D + self.fetch8() + self.Y) & 0xFFFF
        if mode == 'dpi':
            p = (self.D + self.fetch8()) & 0xFFFF
            return (self.DB << 16) | self.r16(p)
        if mode == 'dpxi':
            p = (self.D + self.fetch8() + self.X) & 0xFFFF
            return (self.DB << 16) | self.r16(p)
        if mode == 'dpiy':
            p = (self.D + self.fetch8()) & 0xFFFF
            return (((self.DB << 16) | self.r16(p)) + self.Y) & 0xFFFFFF
        if mode == 'dpil':
            p = (self.D + self.fetch8()) & 0xFFFF
            return self.r16(p) | self.read(p + 2) << 16
        if mode == 'dpily':
            p = (self.D + self.fetch8()) & 0xFFFF
            return ((self.r16(p) | self.read(p + 2) << 16) + self.Y) & 0xFFFFFF
        if mode == 'sr':
            return (self.S + self.fetch8()) & 0xFFFF
        if mode == 'sriy':
            p = (self.S + self.fetch8()) & 0xFFFF
            return (((self.DB << 16) | self.r16(p)) + self.Y) & 0xFFFFFF
        if mode == 'abs':
            return (self.DB << 16) | self.fetch16()
        if mode == 'absx':
            return (((self.DB << 16) | self.fetch16()) + self.X) & 0xFFFFFF
        if mode == 'absy':
            return (((self.DB << 16) | self.fetch16()) + self.Y) & 0xFFFFFF
        if mode == 'long':
            return self.fetch24()
        if mode == 'longx':
            return (self.fetch24() + self.X) & 0xFFFFFF
        raise ValueError(mode)

    def rd(self, a, eight):
        return self.read(a) if eight else self.r16(a)

    def wr(self, a, v, eight):
        if eight:
            self.write(a, v)
        else:
            self.w16(a, v)

    # ---------------- run
    def call(self, addr, ret_marker=0xFFFF, long=False, max_steps=200000):
        """Run a subroutine at addr until it returns past the marker frame."""
        self.PB, self.PC = addr >> 16, addr & 0xFFFF
        base_s = self.S
        if long:
            self.push8(0xFF)
        self.push16(ret_marker - 1)
        target_s = base_s
        n = 0
        while True:
            self.step()
            n += 1
            if self.S == target_s and self.PC == ret_marker and (not long or self.PB == 0xFF):
                return n
            if n > max_steps:
                raise Halt('step limit at %02X:%04X' % (self.PB, self.PC))

    def step(self):
        self.last_pc = (self.PB << 16) | self.PC
        op = self.fetch8()
        h = _HANDLERS.get(op)
        if h is None:
            raise Halt('unimplemented opcode %02X at %06X' % (op, self.last_pc))
        h(self)


# ---------------------------------------------------------------- handlers
_HANDLERS = {}


def _op(code):
    def deco(f):
        _HANDLERS[code] = f
        return f
    return deco


def _mk_alu(name, code, mode):
    def f(c):
        eight = c.m8
        if mode == 'immm':
            v = c.fetch8() if eight else c.fetch16()
        else:
            v = c.rd(c.ea(mode), eight)
        mask = 0xFF if eight else 0xFFFF
        a = c.A & mask
        if name == 'ORA':
            r = c.nz(a | v, eight)
        elif name == 'AND':
            r = c.nz(a & v, eight)
        elif name == 'EOR':
            r = c.nz(a ^ v, eight)
        elif name == 'LDA':
            r = c.nz(v, eight)
        elif name == 'ADC':
            if c.P & 0x08:
                raise Halt('decimal ADC')
            s = a + v + (c.P & 1)
            c.setf(0x40, (~(a ^ v) & (a ^ s)) & (0x80 if eight else 0x8000))
            c.setf(1, s > mask)
            r = c.nz(s, eight)
        elif name == 'SBC':
            if c.P & 0x08:
                raise Halt('decimal SBC')
            s = a - v - (1 - (c.P & 1))
            c.setf(0x40, ((a ^ v) & (a ^ s)) & (0x80 if eight else 0x8000))
            c.setf(1, s >= 0)
            r = c.nz(s, eight)
        elif name == 'CMP':
            c.setf(1, a >= v)
            c.nz(a - v, eight)
            return
        elif name == 'BIT':
            c.setf(0x02, (a & v) == 0)
            if mode != 'immm':
                c.setf(0x80, v & (0x80 if eight else 0x8000))
                c.setf(0x40, v & (0x40 if eight else 0x4000))
            return
        else:
            raise ValueError(name)
        c.A = (c.A & 0xFF00) | r if eight else r
    _HANDLERS[code] = f


def _mk_store(code, reg, mode):
    def f(c):
        a = c.ea(mode)
        if reg == 'A':
            c.wr(a, c.A, c.m8)
        elif reg == 'X':
            c.wr(a, c.X, c.x8)
        elif reg == 'Y':
            c.wr(a, c.Y, c.x8)
        else:
            c.wr(a, 0, c.m8)
    _HANDLERS[code] = f


def _mk_ldxy(code, reg, mode):
    def f(c):
        eight = c.x8
        if mode == 'immx':
            v = c.fetch8() if eight else c.fetch16()
        else:
            v = c.rd(c.ea(mode), eight)
        v = c.nz(v, eight)
        setattr(c, reg, v)
    _HANDLERS[code] = f


def _mk_cpxy(code, reg, mode):
    def f(c):
        eight = c.x8
        if mode == 'immx':
            v = c.fetch8() if eight else c.fetch16()
        else:
            v = c.rd(c.ea(mode), eight)
        r = getattr(c, reg)
        c.setf(1, r >= v)
        c.nz(r - v, eight)
    _HANDLERS[code] = f


def _mk_rmw(code, name, mode):
    def f(c):
        eight = c.m8
        mask = 0xFF if eight else 0xFFFF
        top = 0x80 if eight else 0x8000
        if mode == 'acc':
            v = c.A & mask
            a = None
        else:
            a = c.ea(mode)
            v = c.rd(a, eight)
        if name == 'ASL':
            c.setf(1, v & top); v = (v << 1) & mask
        elif name == 'LSR':
            c.setf(1, v & 1); v >>= 1
        elif name == 'ROL':
            cin = c.P & 1; c.setf(1, v & top); v = ((v << 1) | cin) & mask
        elif name == 'ROR':
            cin = c.P & 1; c.setf(1, v & 1); v = (v >> 1) | (top if cin else 0)
        elif name == 'INC':
            v = (v + 1) & mask
        elif name == 'DEC':
            v = (v - 1) & mask
        elif name in ('TSB', 'TRB'):
            c.setf(0x02, (c.A & v & mask) == 0)
            v = (v | c.A) & mask if name == 'TSB' else (v & ~c.A) & mask
            c.wr(a, v, eight)
            return
        c.nz(v, eight)
        if a is None:
            c.A = (c.A & 0xFF00) | v if eight else v
        else:
            c.wr(a, v, eight)
    _HANDLERS[code] = f


def _branch(cond):
    def f(c):
        d = c.fetch8()
        if d >= 128:
            d -= 256
        if cond(c):
            c.PC = (c.PC + d) & 0xFFFF
    return f


def _build():
    from dis65816 import OPS
    for code, (mn, mode) in OPS.items():
        if mn in ('ORA', 'AND', 'EOR', 'ADC', 'SBC', 'CMP', 'LDA', 'BIT'):
            _mk_alu(mn, code, mode)
        elif mn in ('STA', 'STX', 'STY', 'STZ'):
            _mk_store(code, {'STA': 'A', 'STX': 'X', 'STY': 'Y', 'STZ': 'Z'}[mn], mode)
        elif mn in ('LDX', 'LDY'):
            _mk_ldxy(code, mn[2], mode)
        elif mn in ('CPX', 'CPY'):
            _mk_cpxy(code, mn[2], mode)
        elif mn in ('ASL', 'LSR', 'ROL', 'ROR', 'TSB', 'TRB') or (mn in ('INC', 'DEC') and mode != 'imp'):
            _mk_rmw(code, mn, mode)
    br = {0x10: lambda c: not c.P & 0x80, 0x30: lambda c: c.P & 0x80, 0x50: lambda c: not c.P & 0x40,
          0x70: lambda c: c.P & 0x40, 0x90: lambda c: not c.P & 1, 0xB0: lambda c: c.P & 1,
          0xD0: lambda c: not c.P & 2, 0xF0: lambda c: c.P & 2, 0x80: lambda c: True}
    for k, v in br.items():
        _HANDLERS[k] = _branch(v)


_build()


@_op(0x82)
def _brl(c):
    d = c.fetch16()
    c.PC = (c.PC + (d - 65536 if d >= 32768 else d)) & 0xFFFF


@_op(0x4C)
def _jmp(c):
    c.PC = c.fetch16()


@_op(0x5C)
def _jml(c):
    a = c.fetch24()
    c.PB, c.PC = a >> 16, a & 0xFFFF


@_op(0x6C)
def _jmpi(c):
    c.PC = c.r16(c.fetch16())


@_op(0x7C)
def _jmpxi(c):
    p = (c.fetch16() + c.X) & 0xFFFF
    c.PC = c.r16((c.PB << 16) | p)


@_op(0xDC)
def _jmli(c):
    p = c.fetch16()
    c.PC = c.r16(p)
    c.PB = c.read(p + 2)


@_op(0x20)
def _jsr(c):
    t = c.fetch16()
    c.push16((c.PC - 1) & 0xFFFF)
    c.PC = t


@_op(0xFC)
def _jsrxi(c):
    p = (c.fetch16() + c.X) & 0xFFFF
    c.push16((c.PC - 1) & 0xFFFF)
    c.PC = c.r16((c.PB << 16) | p)


@_op(0x22)
def _jsl(c):
    t = c.fetch24()
    if c.stub_banks is not None and (t >> 16) not in c.stub_banks:
        c.A = 0
        c.P &= ~0x01  # pretend the call succeeded (carry clear)
        return
    c.push8(c.PB)
    c.push16((c.PC - 1) & 0xFFFF)
    c.PB, c.PC = t >> 16, t & 0xFFFF


@_op(0x60)
def _rts(c):
    c.PC = (c.pull16() + 1) & 0xFFFF


@_op(0x6B)
def _rtl(c):
    c.PC = (c.pull16() + 1) & 0xFFFF
    c.PB = c.pull8()


@_op(0x40)
def _rti(c):
    c.P = c.pull8()
    c.PC = c.pull16()
    c.PB = c.pull8()


def _simple():
    def tr(src, dst, flag_from=None):
        def f(c):
            v = getattr(c, src)
            eight = c.x8 if dst in ('X', 'Y') else c.m8
            if dst == 'A' and c.m8:
                c.A = (c.A & 0xFF00) | (v & 0xFF)
                c.nz(v, True)
            elif dst in ('X', 'Y'):
                setattr(c, dst, c.nz(v, eight))
            else:
                setattr(c, dst, v & 0xFFFF)
                c.nz(v, False)
        return f
    _HANDLERS[0xAA] = tr('A', 'X')
    _HANDLERS[0xA8] = tr('A', 'Y')
    _HANDLERS[0x8A] = tr('X', 'A')
    _HANDLERS[0x98] = tr('Y', 'A')
    _HANDLERS[0x9B] = tr('X', 'Y')
    _HANDLERS[0xBB] = tr('Y', 'X')

    def tcd(c):
        c.D = c.A & 0xFFFF; c.nz(c.D, False)

    def tdc(c):
        c.A = c.D; c.nz(c.A, False)

    def tcs(c):
        c.S = c.A & 0xFFFF

    def tsc(c):
        c.A = c.S; c.nz(c.A, False)

    def tsx(c):
        c.X = c.nz(c.S, c.x8)

    def txs(c):
        c.S = c.X
    _HANDLERS.update({0x5B: tcd, 0x7B: tdc, 0x1B: tcs, 0x3B: tsc, 0xBA: tsx, 0x9A: txs})

    def incdec(reg, d):
        def f(c):
            if reg == 'A':
                eight = c.m8
                v = ((c.A & (0xFF if eight else 0xFFFF)) + d)
                v = c.nz(v, eight)
                c.A = (c.A & 0xFF00) | v if eight else v
            else:
                setattr(c, reg, c.nz(getattr(c, reg) + d, c.x8))
        return f
    _HANDLERS.update({0x1A: incdec('A', 1), 0x3A: incdec('A', -1), 0xE8: incdec('X', 1),
                      0xCA: incdec('X', -1), 0xC8: incdec('Y', 1), 0x88: incdec('Y', -1)})

    def flag(mask, on):
        def f(c):
            c.setf(mask, on)
        return f
    _HANDLERS.update({0x18: flag(1, False), 0x38: flag(1, True), 0x58: flag(4, False),
                      0x78: flag(4, True), 0xB8: flag(0x40, False), 0xD8: flag(8, False), 0xF8: flag(8, True)})

    def rep(c):
        c.P &= ~c.fetch8(); c.fix_x()

    def sep(c):
        c.P |= c.fetch8(); c.fix_x()
    _HANDLERS[0xC2] = rep
    _HANDLERS[0xE2] = sep

    def xce(c):
        carry = c.P & 1
        c.setf(1, c.E)
        c.E = bool(carry)
    _HANDLERS[0xFB] = xce

    def xba(c):
        c.A = ((c.A >> 8) | (c.A << 8)) & 0xFFFF
        c.nz(c.A & 0xFF, True)
    _HANDLERS[0xEB] = xba

    def pha(c):
        if c.m8: c.push8(c.A)
        else: c.push16(c.A)

    def pla(c):
        if c.m8:
            v = c.pull8(); c.A = (c.A & 0xFF00) | v; c.nz(v, True)
        else:
            c.A = c.nz(c.pull16(), False)

    def phr(reg):
        def f(c):
            if c.x8: c.push8(getattr(c, reg))
            else: c.push16(getattr(c, reg))
        return f

    def plr(reg):
        def f(c):
            v = c.pull8() if c.x8 else c.pull16()
            setattr(c, reg, c.nz(v, c.x8))
        return f
    _HANDLERS.update({0x48: pha, 0x68: pla, 0xDA: phr('X'), 0xFA: plr('X'), 0x5A: phr('Y'), 0x7A: plr('Y')})

    def php(c): c.push8(c.P)

    def plp(c): c.P = c.pull8(); c.fix_x()

    def phb(c): c.push8(c.DB)

    def plb(c): c.DB = c.pull8(); c.nz(c.DB, True)

    def phk(c): c.push8(c.PB)

    def phd(c): c.push16(c.D)

    def pld(c): c.D = c.nz(c.pull16(), False)
    _HANDLERS.update({0x08: php, 0x28: plp, 0x8B: phb, 0xAB: plb, 0x4B: phk, 0x0B: phd, 0x2B: pld})

    def pea(c): c.push16(c.fetch16())

    def pei(c): c.push16(c.r16((c.D + c.fetch8()) & 0xFFFF))

    def per(c):
        d = c.fetch16(); c.push16((c.PC + d) & 0xFFFF)
    _HANDLERS.update({0xF4: pea, 0xD4: pei, 0x62: per})

    def mvn(c):
        dst = c.fetch8(); src = c.fetch8()
        while True:
            c.write((dst << 16) | c.Y, c.read((src << 16) | c.X))
            c.X = (c.X + 1) & 0xFFFF; c.Y = (c.Y + 1) & 0xFFFF
            c.A = (c.A - 1) & 0xFFFF
            if c.A == 0xFFFF: break
        c.DB = dst

    def mvp(c):
        dst = c.fetch8(); src = c.fetch8()
        while True:
            c.write((dst << 16) | c.Y, c.read((src << 16) | c.X))
            c.X = (c.X - 1) & 0xFFFF; c.Y = (c.Y - 1) & 0xFFFF
            c.A = (c.A - 1) & 0xFFFF
            if c.A == 0xFFFF: break
        c.DB = dst
    _HANDLERS.update({0x54: mvn, 0x44: mvp})
    _HANDLERS[0xEA] = lambda c: None
    _HANDLERS[0x42] = lambda c: c.fetch8()

    def brk(c):
        raise Halt('BRK at %06X' % c.last_pc)
    _HANDLERS[0x00] = brk
    _HANDLERS[0x02] = brk
    _HANDLERS[0xDB] = brk
    _HANDLERS[0xCB] = lambda c: None


_simple()
