#!/usr/bin/env python3
"""Small 65816 disassembler for FE4 (ExHiROM).

  python dis65816.py <rom> <snes_addr_hex> [count] [--m8|--m16] [--x8|--x16]

Tracks REP/SEP to follow accumulator/index width, so straight-line code
decodes correctly. Width after a branch target or JSR return may need a hint.
"""
import sys

# mnemonic, addressing mode
OPS = {}
_tbl = """
00 BRK imm8|01 ORA dpxi|02 COP imm8|03 ORA sr|04 TSB dp|05 ORA dp|06 ASL dp|07 ORA dpil|08 PHP imp|09 ORA immm|0A ASL acc|0B PHD imp|0C TSB abs|0D ORA abs|0E ASL abs|0F ORA long
10 BPL rel|11 ORA dpiy|12 ORA dpi|13 ORA sriy|14 TRB dp|15 ORA dpx|16 ASL dpx|17 ORA dpily|18 CLC imp|19 ORA absy|1A INC acc|1B TCS imp|1C TRB abs|1D ORA absx|1E ASL absx|1F ORA longx
20 JSR abs|21 AND dpxi|22 JSL long|23 AND sr|24 BIT dp|25 AND dp|26 ROL dp|27 AND dpil|28 PLP imp|29 AND immm|2A ROL acc|2B PLD imp|2C BIT abs|2D AND abs|2E ROL abs|2F AND long
30 BMI rel|31 AND dpiy|32 AND dpi|33 AND sriy|34 BIT dpx|35 AND dpx|36 ROL dpx|37 AND dpily|38 SEC imp|39 AND absy|3A DEC acc|3B TSC imp|3C BIT absx|3D AND absx|3E ROL absx|3F AND longx
40 RTI imp|41 EOR dpxi|42 WDM imm8|43 EOR sr|44 MVP mv|45 EOR dp|46 LSR dp|47 EOR dpil|48 PHA imp|49 EOR immm|4A LSR acc|4B PHK imp|4C JMP abs|4D EOR abs|4E LSR abs|4F EOR long
50 BVC rel|51 EOR dpiy|52 EOR dpi|53 EOR sriy|54 MVN mv|55 EOR dpx|56 LSR dpx|57 EOR dpily|58 CLI imp|59 EOR absy|5A PHY imp|5B TCD imp|5C JML long|5D EOR absx|5E LSR absx|5F EOR longx
60 RTS imp|61 ADC dpxi|62 PER rell|63 ADC sr|64 STZ dp|65 ADC dp|66 ROR dp|67 ADC dpil|68 PLA imp|69 ADC immm|6A ROR acc|6B RTL imp|6C JMP absi|6D ADC abs|6E ROR abs|6F ADC long
70 BVS rel|71 ADC dpiy|72 ADC dpi|73 ADC sriy|74 STZ dpx|75 ADC dpx|76 ROR dpx|77 ADC dpily|78 SEI imp|79 ADC absy|7A PLY imp|7B TDC imp|7C JMP absxi|7D ADC absx|7E ROR absx|7F ADC longx
80 BRA rel|81 STA dpxi|82 BRL rell|83 STA sr|84 STY dp|85 STA dp|86 STX dp|87 STA dpil|88 DEY imp|89 BIT immm|8A TXA imp|8B PHB imp|8C STY abs|8D STA abs|8E STX abs|8F STA long
90 BCC rel|91 STA dpiy|92 STA dpi|93 STA sriy|94 STY dpx|95 STA dpx|96 STX dpy|97 STA dpily|98 TYA imp|99 STA absy|9A TXS imp|9B TXY imp|9C STZ abs|9D STA absx|9E STZ absx|9F STA longx
A0 LDY immx|A1 LDA dpxi|A2 LDX immx|A3 LDA sr|A4 LDY dp|A5 LDA dp|A6 LDX dp|A7 LDA dpil|A8 TAY imp|A9 LDA immm|AA TAX imp|AB PLB imp|AC LDY abs|AD LDA abs|AE LDX abs|AF LDA long
B0 BCS rel|B1 LDA dpiy|B2 LDA dpi|B3 LDA sriy|B4 LDY dpx|B5 LDA dpx|B6 LDX dpy|B7 LDA dpily|B8 CLV imp|B9 LDA absy|BA TSX imp|BB TYX imp|BC LDY absx|BD LDA absx|BE LDX absy|BF LDA longx
C0 CPY immx|C1 CMP dpxi|C2 REP imm8|C3 CMP sr|C4 CPY dp|C5 CMP dp|C6 DEC dp|C7 CMP dpil|C8 INY imp|C9 CMP immm|CA DEX imp|CB WAI imp|CC CPY abs|CD CMP abs|CE DEC abs|CF CMP long
D0 BNE rel|D1 CMP dpiy|D2 CMP dpi|D3 CMP sriy|D4 PEI dp|D5 CMP dpx|D6 DEC dpx|D7 CMP dpily|D8 CLD imp|D9 CMP absy|DA PHX imp|DB STP imp|DC JML absil|DD CMP absx|DE DEC absx|DF CMP longx
E0 CPX immx|E1 SBC dpxi|E2 SEP imm8|E3 SBC sr|E4 CPX dp|E5 SBC dp|E6 INC dp|E7 SBC dpil|E8 INX imp|E9 SBC immm|EA NOP imp|EB XBA imp|EC CPX abs|ED SBC abs|EE INC abs|EF SBC long
F0 BEQ rel|F1 SBC dpiy|F2 SBC dpi|F3 SBC sriy|F4 PEA abs|F5 SBC dpx|F6 INC dpx|F7 SBC dpily|F8 SED imp|F9 SBC absy|FA PLX imp|FB XCE imp|FC JSR absxi|FD SBC absx|FE INC absx|FF SBC longx
"""
for line in _tbl.strip().splitlines():
    for ent in line.split('|'):
        op, mn, mode = ent.split()
        OPS[int(op, 16)] = (mn, mode)

FMT = {
    'imp': (0, '{mn}'), 'acc': (0, '{mn} A'), 'imm8': (1, '{mn} #${v:02X}'),
    'dp': (1, '{mn} ${v:02X}'), 'dpx': (1, '{mn} ${v:02X},X'), 'dpy': (1, '{mn} ${v:02X},Y'),
    'dpi': (1, '{mn} (${v:02X})'), 'dpxi': (1, '{mn} (${v:02X},X)'), 'dpiy': (1, '{mn} (${v:02X}),Y'),
    'dpil': (1, '{mn} [${v:02X}]'), 'dpily': (1, '{mn} [${v:02X}],Y'),
    'sr': (1, '{mn} ${v:02X},S'), 'sriy': (1, '{mn} (${v:02X},S),Y'),
    'abs': (2, '{mn} ${v:04X}'), 'absx': (2, '{mn} ${v:04X},X'), 'absy': (2, '{mn} ${v:04X},Y'),
    'absi': (2, '{mn} (${v:04X})'), 'absxi': (2, '{mn} (${v:04X},X)'), 'absil': (2, '{mn} [${v:04X}]'),
    'long': (3, '{mn} ${v:06X}'), 'longx': (3, '{mn} ${v:06X},X'),
    'mv': (2, '{mn} ${s:02X},${d:02X}'),
}


def snes_to_file(addr):
    """ExHiROM: $C0-$FF -> file 0x000000-0x3FFFFF; $40-$7D -> 0x400000+ ;
    $80-$BF (upper half) mirrors $C0-$FF; $00-$3F upper half mirrors $40-$7D."""
    bank, off = addr >> 16, addr & 0xFFFF
    if bank >= 0xC0:
        return ((bank - 0xC0) << 16) | off
    if 0x80 <= bank < 0xC0 and off >= 0x8000:
        return ((bank - 0x80) << 16) | off
    if 0x40 <= bank < 0x7E:
        return 0x400000 | ((bank - 0x40) << 16) | off
    if bank < 0x40 and off >= 0x8000:
        return 0x400000 | (bank << 16) | off
    return None


def file_to_snes(off):
    if off < 0x400000:
        return 0xC00000 | off
    return 0x400000 + (off - 0x400000)


def disasm(rom, addr, count=40, m8=True, x8=True, stop_at_return=False):
    out = []
    for _ in range(count):
        fo = snes_to_file(addr)
        if fo is None:
            break
        op = rom[fo]
        mn, mode = OPS[op]
        if mode == 'immm':
            n = 1 if m8 else 2
            v = int.from_bytes(rom[fo + 1:fo + 1 + n], 'little')
            txt = f'{mn} #${v:0{2*n}X}'
        elif mode == 'immx':
            n = 1 if x8 else 2
            v = int.from_bytes(rom[fo + 1:fo + 1 + n], 'little')
            txt = f'{mn} #${v:0{2*n}X}'
        elif mode == 'rel':
            n = 1
            d = rom[fo + 1]
            d = d - 256 if d >= 128 else d
            tgt = (addr & 0xFF0000) | ((addr + 2 + d) & 0xFFFF)
            txt = f'{mn} ${tgt & 0xFFFF:04X}'
        elif mode == 'rell':
            n = 2
            d = int.from_bytes(rom[fo + 1:fo + 3], 'little')
            d = d - 65536 if d >= 32768 else d
            tgt = (addr & 0xFF0000) | ((addr + 3 + d) & 0xFFFF)
            txt = f'{mn} ${tgt & 0xFFFF:04X}'
        elif mode == 'mv':
            n = 2
            txt = FMT['mv'][1].format(mn=mn, d=rom[fo + 1], s=rom[fo + 2])
        else:
            n, f = FMT[mode]
            v = int.from_bytes(rom[fo + 1:fo + 1 + n], 'little')
            txt = f.format(mn=mn, v=v)
        raw = ' '.join('%02X' % b for b in rom[fo:fo + 1 + n])
        out.append((addr, raw, txt))
        if mn == 'REP':
            if rom[fo + 1] & 0x20: m8 = False
            if rom[fo + 1] & 0x10: x8 = False
        elif mn == 'SEP':
            if rom[fo + 1] & 0x20: m8 = True
            if rom[fo + 1] & 0x10: x8 = True
        addr = (addr & 0xFF0000) | ((addr + 1 + n) & 0xFFFF)
        if stop_at_return and mn in ('RTS', 'RTL', 'RTI', 'JMP', 'JML', 'BRA', 'BRL'):
            break
    return out


def main():
    a = sys.argv[1:]
    rom = open(a[0], 'rb').read()
    if len(rom) % 0x8000 == 512:
        rom = rom[512:]
    addr = int(a[1], 16)
    count = int(a[2]) if len(a) > 2 and not a[2].startswith('--') else 40
    m8 = '--m16' not in a
    x8 = '--x16' not in a
    for ad, raw, txt in disasm(rom, addr, count, m8, x8):
        print(f'{ad:06X}  {raw:<12} {txt}')


if __name__ == '__main__':
    main()
