#!/usr/bin/env python3
"""A small two-pass 65816 assembler for the kit's engine hooks.

    a = Asm(0x7DF800)              # origin (24-bit)
    a.op('lda', '#', 0x10)         # immediate (width from a.m16 / a.x16)
    a.op('sta', 'abs', 0x0574)
    a.op('lda', 'long,x', 0x7DF900)
    a.op('beq', 'rel', 'done')     # branch to a label
    a.label('done'); a.op('rtl')
    code = a.assemble()

Addressing modes: imp  # (immediate)  dp  dp,x  abs  abs,x  abs,y  long  long,x
                  sr (n,S)  rel (8-bit branch)  brl  ind (JMP ($nnnn))  absx_ind (JSR ($nnnn,X))
Mode 'far' (beq/bne/... far, label) branches any distance (inverted branch + BRL).
Operands may be numbers or label names (labels resolve to the full 24-bit address;
abs/rel modes use the low 16 bits / the offset).  rep/sep update the M/X widths.
"""

OPS = {
    # (mnemonic, mode): opcode
    ('adc', '#'): 0x69, ('adc', 'dp'): 0x65, ('adc', 'abs'): 0x6D, ('adc', 'abs,x'): 0x7D, ('adc', 'abs,y'): 0x79,
    ('adc', 'long'): 0x6F, ('adc', 'long,x'): 0x7F, ('adc', 'sr'): 0x63, ('adc', 'dp,x'): 0x75,
    ('sbc', '#'): 0xE9, ('sbc', 'dp'): 0xE5, ('sbc', 'abs'): 0xED, ('sbc', 'abs,x'): 0xFD, ('sbc', 'abs,y'): 0xF9,
    ('sbc', 'long'): 0xEF, ('sbc', 'long,x'): 0xFF, ('sbc', 'sr'): 0xE3,
    ('and', '#'): 0x29, ('and', 'dp'): 0x25, ('and', 'abs'): 0x2D, ('and', 'abs,x'): 0x3D, ('and', 'long'): 0x2F,
    ('and', 'long,x'): 0x3F, ('and', 'sr'): 0x23, ('and', 'abs,y'): 0x39,
    ('ora', '#'): 0x09, ('ora', 'dp'): 0x05, ('ora', 'abs'): 0x0D, ('ora', 'abs,x'): 0x1D, ('ora', 'long'): 0x0F,
    ('ora', 'long,x'): 0x1F, ('ora', 'abs,y'): 0x19,
    ('eor', '#'): 0x49, ('eor', 'abs'): 0x4D, ('eor', 'long,x'): 0x5F,
    ('cmp', '#'): 0xC9, ('cmp', 'dp'): 0xC5, ('cmp', 'abs'): 0xCD, ('cmp', 'abs,x'): 0xDD, ('cmp', 'abs,y'): 0xD9,
    ('cmp', 'long'): 0xCF, ('cmp', 'long,x'): 0xDF, ('cmp', 'sr'): 0xC3,
    ('cpx', '#'): 0xE0, ('cpx', 'abs'): 0xEC, ('cpy', '#'): 0xC0, ('cpy', 'abs'): 0xCC,
    ('bit', '#'): 0x89, ('bit', 'abs'): 0x2C, ('bit', 'abs,x'): 0x3C, ('bit', 'dp'): 0x24,
    ('lda', '#'): 0xA9, ('lda', 'dp'): 0xA5, ('lda', 'dp,x'): 0xB5, ('lda', 'abs'): 0xAD, ('lda', 'abs,x'): 0xBD,
    ('lda', 'abs,y'): 0xB9, ('lda', 'long'): 0xAF, ('lda', 'long,x'): 0xBF, ('lda', 'sr'): 0xA3,
    ('lda', 'dp_ind_long,y'): 0xB7, ('lda', 'dp_ind_long'): 0xA7,
    ('ldx', '#'): 0xA2, ('ldx', 'dp'): 0xA6, ('ldx', 'abs'): 0xAE, ('ldx', 'abs,y'): 0xBE,
    ('ldy', '#'): 0xA0, ('ldy', 'dp'): 0xA4, ('ldy', 'abs'): 0xAC, ('ldy', 'abs,x'): 0xBC,
    ('sta', 'dp'): 0x85, ('sta', 'dp,x'): 0x95, ('sta', 'abs'): 0x8D, ('sta', 'abs,x'): 0x9D, ('sta', 'abs,y'): 0x99,
    ('sta', 'long'): 0x8F, ('sta', 'long,x'): 0x9F, ('sta', 'sr'): 0x83, ('sta', 'dp_ind_long,y'): 0x97,
    ('stx', 'dp'): 0x86, ('stx', 'abs'): 0x8E, ('sty', 'dp'): 0x84, ('sty', 'abs'): 0x8C,
    ('stz', 'dp'): 0x64, ('stz', 'abs'): 0x9C, ('stz', 'abs,x'): 0x9E,
    ('inc', 'imp'): 0x1A, ('dec', 'imp'): 0x3A, ('inc', 'abs'): 0xEE, ('dec', 'abs'): 0xCE, ('inc', 'abs,x'): 0xFE,
    ('dec', 'abs,x'): 0xDE, ('inc', 'dp'): 0xE6, ('dec', 'dp'): 0xC6,
    ('asl', 'imp'): 0x0A, ('lsr', 'imp'): 0x4A, ('rol', 'imp'): 0x2A, ('ror', 'imp'): 0x6A,
    ('asl', 'abs'): 0x0E, ('asl', 'dp'): 0x06, ('lsr', 'dp'): 0x46, ('lsr', 'abs'): 0x4E, ('asl', 'abs,x'): 0x1E, ('lsr', 'abs,x'): 0x5E,
    ('tsb', 'abs'): 0x0C, ('trb', 'abs'): 0x1C, ('tsb', 'dp'): 0x04, ('trb', 'dp'): 0x14,
    ('inx', 'imp'): 0xE8, ('iny', 'imp'): 0xC8, ('dex', 'imp'): 0xCA, ('dey', 'imp'): 0x88,
    ('tax', 'imp'): 0xAA, ('tay', 'imp'): 0xA8, ('txa', 'imp'): 0x8A, ('tya', 'imp'): 0x98, ('txy', 'imp'): 0x9B,
    ('tyx', 'imp'): 0xBB, ('xba', 'imp'): 0xEB, ('tsc', 'imp'): 0x3B, ('tcs', 'imp'): 0x1B,
    ('pha', 'imp'): 0x48, ('pla', 'imp'): 0x68, ('phx', 'imp'): 0xDA, ('plx', 'imp'): 0xFA, ('phy', 'imp'): 0x5A,
    ('ply', 'imp'): 0x7A, ('php', 'imp'): 0x08, ('plp', 'imp'): 0x28, ('phb', 'imp'): 0x8B, ('plb', 'imp'): 0xAB,
    ('phk', 'imp'): 0x4B, ('phd', 'imp'): 0x0B, ('pld', 'imp'): 0x2B, ('pea', 'abs'): 0xF4,
    ('clc', 'imp'): 0x18, ('sec', 'imp'): 0x38, ('nop', 'imp'): 0xEA, ('rts', 'imp'): 0x60, ('rtl', 'imp'): 0x6B,
    ('rep', '#8'): 0xC2, ('sep', '#8'): 0xE2,
    ('jsl', 'long'): 0x22, ('jml', 'long'): 0x5C, ('jsr', 'abs'): 0x20, ('jmp', 'abs'): 0x4C,
    ('jsr', 'absx_ind'): 0xFC, ('jmp', 'absx_ind'): 0x7C,
    ('bra', 'rel'): 0x80, ('beq', 'rel'): 0xF0, ('bne', 'rel'): 0xD0, ('bcc', 'rel'): 0x90, ('bcs', 'rel'): 0xB0,
    ('bmi', 'rel'): 0x30, ('bpl', 'rel'): 0x10, ('bvc', 'rel'): 0x50, ('bvs', 'rel'): 0x70, ('brl', 'brl'): 0x82,
}
SIZE = {'imp': 0, 'dp': 1, 'dp,x': 1, 'sr': 1, 'abs': 2, 'abs,x': 2, 'abs,y': 2, 'long': 3, 'long,x': 3,
        'rel': 1, 'brl': 2, '#8': 1, 'absx_ind': 2, 'dp_ind_long,y': 1, 'dp_ind_long': 1}
INDEX_IMM = {'ldx', 'ldy', 'cpx', 'cpy'}
INVERT = {'beq': 'bne', 'bne': 'beq', 'bcc': 'bcs', 'bcs': 'bcc', 'bmi': 'bpl', 'bpl': 'bmi',
          'bvc': 'bvs', 'bvs': 'bvc'}


class AsmError(Exception):
    pass


class Asm:
    def __init__(self, origin, m16=True, x16=True):
        self.origin = origin
        self.items = []          # (kind, ...)
        self.m16, self.x16 = m16, x16
        self.labels = {}

    # ------------------------------------------------------------ building
    def label(self, name):
        self.items.append(('label', name))

    def data(self, bs):
        self.items.append(('data', bytes(bs)))

    def word(self, v):
        self.items.append(('word', v))

    def long(self, v):
        self.items.append(('long', v))

    def op(self, mn, mode='imp', arg=None):
        mn = mn.lower()
        if mode == 'far':                    # any-distance branch: inverted branch over a BRL
            if mn == 'bra':
                return self.op('brl', 'brl', arg)
            self.items.append(('op', INVERT[mn], 'rel', ('+', 3), 1))
            return self.op('brl', 'brl', arg)
        if mode == '#':
            wide = self.x16 if mn in INDEX_IMM else self.m16
            size = 2 if wide else 1
        else:
            if (mn, mode) not in OPS:
                raise AsmError('no %s %s' % (mn, mode))
            size = SIZE[mode]
        if (mn, mode) not in OPS:
            raise AsmError('no %s %s' % (mn, mode))
        if mn == 'rep':
            self.m16 = self.m16 or bool(arg & 0x20)
            self.x16 = self.x16 or bool(arg & 0x10)
        if mn == 'sep':
            self.m16 = self.m16 and not (arg & 0x20)
            self.x16 = self.x16 and not (arg & 0x10)
        self.items.append(('op', mn, mode, arg, size))

    def __getattr__(self, mn):
        """a.lda('#', 5)  ==  a.op('lda', '#', 5);  a.rtl()  ==  a.op('rtl')"""
        if mn.startswith('_'):
            raise AttributeError(mn)
        return lambda mode='imp', arg=None: self.op(mn, mode, arg)

    # ------------------------------------------------------------ assembling
    def _layout(self):
        pc = self.origin
        for it in self.items:
            if it[0] == 'label':
                self.labels[it[1]] = pc
            elif it[0] == 'data':
                pc += len(it[1])
            elif it[0] == 'word':
                pc += 2
            elif it[0] == 'long':
                pc += 3
            else:
                pc += 1 + it[4]
        return pc

    def _val(self, a, pc=0):
        if isinstance(a, tuple):             # ('+', n): n bytes past the end of this instruction
            if a[0] == '+':
                return pc + 2 + a[1]
            return self._val(a[0]) + a[1]    # (label, offset)
        if isinstance(a, str):
            if a not in self.labels:
                raise AsmError('unknown label %s' % a)
            return self.labels[a]
        return a

    def assemble(self):
        end = self._layout()
        out = bytearray()
        pc = self.origin
        for it in self.items:
            if it[0] == 'label':
                continue
            if it[0] == 'data':
                out += it[1]
                pc += len(it[1])
                continue
            if it[0] in ('word', 'long'):
                n = 2 if it[0] == 'word' else 3
                out += (self._val(it[1]) & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')
                pc += n
                continue
            _, mn, mode, arg, size = it
            out.append(OPS[(mn, mode)] if mode != '#' else OPS[(mn, '#')])
            if size:
                v = self._val(arg, pc)
                if mode == 'rel':
                    d = v - (pc + 2)
                    if not -128 <= d <= 127:
                        raise AsmError('branch to %s out of range (%d)' % (arg, d))
                    v = d & 0xFF
                elif mode == 'brl':
                    v = (v - (pc + 3)) & 0xFFFF
                out += (v & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')
            pc += 1 + size
        assert pc == end
        return bytes(out)
