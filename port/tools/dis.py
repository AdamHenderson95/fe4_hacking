"""65816 disassembler for the FE4 ROM (ExHiROM), tracking M/X through REP/SEP.
dis.py rom.sfc BANK:ADDR count [m x]      e.g. dis.py rom.sfc 85:C690 80 0 0
"""
import sys, os

OPTAB = os.path.join(os.path.dirname(__file__), '..', 'work', 'optab.txt')
ops = {}
for line in open(OPTAB):
    c, op, mode = line.split()
    ops[int(c, 16)] = (op, mode)

def rom_read(rom, adr):
    bank = adr >> 16; a = adr & 0xffff
    second = bank < 0x80; bank &= 0x7f
    return rom[(((bank & 0x3f) << 16) | (0x400000 if second else 0) | a) % len(rom)]

def length(mode, m, x):
    if mode == 'imp': return 1
    if mode == 'imm(m)': return 2 if m else 3
    if mode == 'imm(x)': return 2 if x else 3
    if mode in ('imm(l)', 'abs', 'abx', 'abx(r)', 'aby', 'aby(r)', 'ind', 'iax', 'ial', 'rll', 'bm'): return 3
    if mode in ('abl', 'alx'): return 4
    return 2

def fmt(op, mode, b, pc, ln):
    mn = op.upper()
    for suf in ('ASLA', 'LSRA', 'ROLA', 'RORA', 'INCA', 'DECA'):
        if mn == suf: return mn[:3] + ' A'
    if mn == 'BITI': mn = 'BIT'
    b = list(b) + [0, 0, 0]
    o16 = b[0] | (b[1] << 8)
    o24 = o16 | (b[2] << 16)
    m = {
        'imp': '', 'imm(s)': '#$%02X' % (b[0] if b else 0), 'imm(l)': '$%04X' % o16,
        'dp': '$%02X' % b[0], 'dpx': '$%02X,X' % b[0], 'dpy': '$%02X,Y' % b[0],
        'idp': '($%02X)' % b[0], 'idx': '($%02X,X)' % b[0], 'idy': '($%02X),Y' % b[0], 'idy(r)': '($%02X),Y' % b[0],
        'idl': '[$%02X]' % b[0], 'ily': '[$%02X],Y' % b[0], 'sr': '$%02X,S' % b[0], 'isy': '($%02X,S),Y' % b[0],
        'abs': '$%04X' % o16, 'abx': '$%04X,X' % o16, 'abx(r)': '$%04X,X' % o16, 'aby': '$%04X,Y' % o16, 'aby(r)': '$%04X,Y' % o16,
        'abl': '$%06X' % o24, 'alx': '$%06X,X' % o24, 'ind': '($%04X)' % o16, 'iax': '($%04X,X)' % o16, 'ial': '[$%04X]' % o16,
    }
    if mode in ('imm(m)', 'imm(x)'):
        return mn + (' #$%02X' % b[0] if ln == 2 else ' #$%04X' % o16)
    if mode == 'rel':
        t = (pc & 0xff0000) | ((pc + 2 + (b[0] - 256 if b[0] > 127 else b[0])) & 0xffff)
        return mn + ' $%04X' % (t & 0xffff)
    if mode == 'rll':
        v = o16 - 65536 if o16 > 32767 else o16
        return mn + ' $%04X' % ((pc + 3 + v) & 0xffff)
    if mode == 'bm': return mn + ' $%02X,$%02X' % (b[1], b[0])
    return (mn + ' ' + m.get(mode, '?')).rstrip()

def disasm(rom, pc, count, m=1, x=1, out=print):
    for _ in range(count):
        opc = rom_read(rom, pc)
        op, mode = ops[opc]
        ln = length(mode, m, x)
        b = [rom_read(rom, (pc & 0xff0000) | ((pc + i) & 0xffff)) for i in range(1, ln)]
        out('%02X:%04X  %-12s %s' % (pc >> 16, pc & 0xffff, ' '.join('%02X' % v for v in [opc] + b), fmt(op, mode, b, pc, ln)))
        if op == 'rep':
            if b[0] & 0x20: m = 0
            if b[0] & 0x10: x = 0
        if op == 'sep':
            if b[0] & 0x20: m = 1
            if b[0] & 0x10: x = 1
        pc = (pc & 0xff0000) | ((pc + ln) & 0xffff)
    return pc

if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    if len(rom) % 0x8000 == 0x200: rom = rom[0x200:]
    bank, addr = sys.argv[2].split(':')
    m = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    x = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    disasm(rom, (int(bank, 16) << 16) | int(addr, 16), int(sys.argv[3]), m, x)
