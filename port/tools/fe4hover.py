"""Map hover box: add Mt / Hit / Avo / AS (FE4, Project Naga).

The game's unit box (name + HP, 9x5 tiles) is enlarged to 13x7 and two lines are added:
    MT24 HIT102
    AS 9 AVO 25
The numbers come from the game's own status-screen routines ($84:FE8F attack, $84:FE98 hit,
$84:FEA1 avoid, $84:FEB5 attack speed) for the hovered unit, drawn with the game's own string
routine and font. All new code/data lives in free space at the end of bank $85.

fe4hover.py patches            -> print the patch list
fe4hover.py apply in.sfc out.sfc
fe4hover.py header out.h       -> C header used by the PC port
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from asm import assemble, snes_to_file

ORG = 0x85FA00
W, H = 13, 7

# ---------------- frame template (13 x 7), built from the original 9 x 5 pieces ----------------
def template():
    rows = []
    rows.append([0x2364, 0x2365] + [0x2363] * (W - 4) + [0x6365, 0x6364])
    rows.append([0x2360] + [0x2361] * (W - 3) + [0x6361, 0x6360])
    for _ in range(H - 4):
        rows.append([0x2366] + [0x2361] * (W - 2) + [0x6366])
    rows.append([0xA360, 0xA361] + [0x2361] * (W - 4) + [0xE361, 0xE360])
    rows.append([0xA364, 0xA365] + [0xA363] * (W - 4) + [0xE365, 0xE364])
    return [w for r in rows for w in r]

# ---------------- pointer tail tables: index = |cursor col - box col|, 13 entries ----------------
def tails(bottom):
    out = []
    for d in range(W):
        if d <= 7: col, flip = d + 2, False   # cursor toward the left of the box: tail points left
        else: col, flip = d - 1, True          # toward the right: mirrored tail
        col = max(1, min(W - 2, col))
        off = (H - 1) * 64 + col * 2 if bottom else col * 2
        if bottom: tile = 0x6362 if flip else 0x2362
        else: tile = 0xE362 if flip else 0xA362
        out += [off, tile]
    return out

# characters for the game's string routine with glyph base $24F0
def ch(c):
    if c == ' ': return 0x0F
    if c == '-': return 0xEC
    if c.isdigit(): return 0x20 + int(c)
    return 0xD0 + ord(c) - ord('A')

def label(s):  # emit code that writes the label characters at [$24],Y
    return ''.join('    LDA #$%02X\n    STA [$24],Y\n    INY\n' % ch(c) for c in s)

CODE = f"""
.m 0
.x 0
template:
    .dw {','.join('$%04X' % w for w in template())}
tail_below:
    .dw {','.join('$%04X' % w for w in tails(False))}
tail_above:
    .dw {','.join('$%04X' % w for w in tails(True))}

; JSR here from $85:C97E (replaces JSR $C99F), where both the HP and the status-condition
; versions of the box finish: draw the stats, then continue with the original $C99F.
hover_entry:
    JSL hover_stats
    JMP $C99F

; JSR here from $85:C7AE (replaces JSR $C819) every time the box is drawn: set the box size
; so a save state made with the other setting can't leave a wrong-sized box
box_size:
    LDA #$0{H}0{W:X}
    STA $0FF7,X
    JMP $C819

hover_stats:
    PHP
    REP #$30
    PHB
    PHX
    PHY
    LDA $053A
    PHA
    LDA $24
    PHA
    LDA $26
    PHA
    LDA $056F
    PHA
    LDA $0ECF
    PHA
    LDA $0ED1
    PHA
    LDA $0ED3
    PHA
    LDA $0574
    PHA
    ; ---- the game's own stat routines for unit $056F ----
    LDA #$0000
    STA $0574
    JSL $84FE8F          ; attack (strength/magic + weapon might)
    PHA
    JSL $84FE98          ; hit ($FF = no usable weapon)
    PHA
    LDA #$FFFF           ; avoid without terrain, as on the status screen
    JSL $84FEA1
    PHA
    JSL $84FEB5          ; attack speed
    PHA
    ; stack: 1,S as  3,S avo  5,S hit  7,S atk  then saved values
    LDA 5,S
    CMP #$00FF
    BNE have_weapon
    LDA #$FFFF           ; no weapon: show "--" for MT and HIT
    STA 5,S
    STA 7,S
have_weapon:
    ; restore what the stat routines may have changed before drawing
    LDA 9,S
    STA $0574
    LDA 11,S
    STA $0ED3
    LDA 13,S
    STA $0ED1
    LDA 15,S
    STA $0ECF
    LDA 17,S
    STA $056F
    ; 12-byte string buffer on the stack (bank 0)
    TSC
    SEC
    SBC #$000C
    TCS
    INC A
    STA $24
    STZ $26
    LDA #$24F0
    STA $053A
    ; ---- line 1: MTnn HITnnn ----
    LDY #$0000
    SEP #$20
{label('MT')}    REP #$20
    LDA 19,S             ; atk (12 bytes of buffer + 7)
    JSR put2
    SEP #$20
{label(' HIT')}    REP #$20
    LDA 17,S             ; hit
    JSR put3
    SEP #$20
    LDA #$00
    STA [$24],Y
    REP #$20
    LDA $0ECF
    CLC
    ADC #$0401
    TAX
    JSL $878F6E
    ; ---- line 2: ASnn AVOnnn ----
    LDY #$0000
    SEP #$20
{label('AS')}    REP #$20
    LDA 13,S             ; as
    JSR put2
    SEP #$20
{label(' AVO')}    REP #$20
    LDA 15,S             ; avo
    JSR put3
    SEP #$20
    LDA #$00
    STA [$24],Y
    REP #$20
    LDA $0ECF
    CLC
    ADC #$0501
    TAX
    JSL $878F6E
    ; ---- clean up: buffer + 4 stats, then restore saved values ----
    TSC
    CLC
    ADC #$0014
    TCS
    PLA
    STA $0574
    PLA
    STA $0ED3
    PLA
    STA $0ED1
    PLA
    STA $0ECF
    PLA
    STA $056F
    PLA
    STA $26
    PLA
    STA $24
    PLA
    STA $053A
    PLY
    PLX
    PLB
    PLP
    RTL

; A = value -> 2 characters at [$24],Y (blank tens; $FFFF = "--"; negative = 0; max 99)
put2:
    CMP #$FFFF
    BEQ dash2
    CMP #$8000
    BCC p2pos
    LDA #$0000
p2pos:
    CMP #$0064
    BCC p2ok
    LDA #$0063
p2ok:
    LDX #$0000
p2loop:
    CMP #$000A
    BCC p2done
    SBC #$000A
    INX
    BRA p2loop
p2done:
    PHA
    TXA
    BEQ p2blank
    CLC
    ADC #$0020
    BRA p2tens
p2blank:
    LDA #$000F
p2tens:
    SEP #$20
    STA [$24],Y
    INY
    REP #$20
    PLA
    CLC
    ADC #$0020
    SEP #$20
    STA [$24],Y
    INY
    REP #$20
    RTS
dash2:
    SEP #$20
    LDA #$EC
    STA [$24],Y
    INY
    STA [$24],Y
    INY
    REP #$20
    RTS

; A = value -> 3 characters (leading blanks; $FFFF = " --"; negative = 0; max 999)
put3:
    CMP #$FFFF
    BEQ dash3
    CMP #$8000
    BCC p3pos
    LDA #$0000
p3pos:
    CMP #$03E8
    BCC p3ok
    LDA #$03E7
p3ok:
    LDX #$0000
p3loop:
    CMP #$0064
    BCC p3done
    SBC #$0064
    INX
    BRA p3loop
p3done:
    CPX #$0000
    BEQ p3small
    PHA
    TXA
    CLC
    ADC #$0020
    SEP #$20
    STA [$24],Y
    INY
    REP #$20
    PLA
    LDX #$0000           ; tens digit is always shown after a hundreds digit
p3tl:
    CMP #$000A
    BCC p3td
    SBC #$000A
    INX
    BRA p3tl
p3td:
    PHA
    TXA
    CLC
    ADC #$0020
    SEP #$20
    STA [$24],Y
    INY
    REP #$20
    PLA
    CLC
    ADC #$0020
    SEP #$20
    STA [$24],Y
    INY
    REP #$20
    RTS
p3small:
    PHA
    SEP #$20
    LDA #$0F
    STA [$24],Y
    INY
    REP #$20
    PLA
    JMP put2
dash3:
    SEP #$20
    LDA #$0F
    STA [$24],Y
    INY
    REP #$20
    LDA #$FFFF
    JMP put2
"""

def build():
    code, L = assemble(CODE, ORG)
    pt = lambda lab: L[lab] & 0xffff
    patches = []
    def p(snes, orig, new):
        patches.append((snes_to_file(snes), bytes(orig), bytes(new)))
    # size 9x5 -> 13x7
    p(0x85C673, [0xA9, 0x09, 0x00], [0xA9, W, 0x00])
    p(0x85C679, [0xA9, 0x05, 0x00], [0xA9, H, 0x00])
    # frame template
    p(0x85C7B4, [0xA9, 0xBF, 0xC7], [0xA9, pt('template') & 0xff, pt('template') >> 8])
    # placement relative to the cursor (box is 4 wider, 2 taller)
    p(0x85C81D, [0xC9, 0xD0, 0x00], [0xC9, 0xC0, 0x00])   # right clamp threshold
    p(0x85C822, [0xC9, 0x30, 0x00], [0xC9, 0x38, 0x00])   # left clamp threshold
    p(0x85C827, [0xA9, 0x28, 0x00], [0xA9, 0x38, 0x00])   # left clamp value
    p(0x85C82C, [0xA9, 0xC0, 0x00], [0xA9, 0xB8, 0x00])   # right clamp value
    p(0x85C833, [0xE9, 0x03, 0x00], [0xE9, 0x05, 0x00])   # box starts 5 columns left of the cursor
    p(0x85C83C, [0xC9, 0x30, 0x00], [0xC9, 0x48, 0x00])   # near the top: put the box below the cursor
    p(0x85C842, [0x69, 0x48, 0x00], [0x69, 0x58, 0x00])
    p(0x85C849, [0xE9, 0x06, 0x00], [0xE9, 0x08, 0x00])   # box ends 1 row above the cursor
    # pointer tail tables
    for at, lab, off in ((0x85C9E8, 'tail_below', 0), (0x85C9F0, 'tail_below', 2), (0x85C9F9, 'tail_above', 0), (0x85CA01, 'tail_above', 2)):
        orig_lo = {0x85C9E8: 0x0B, 0x85C9F0: 0x0D, 0x85C9F9: 0x2B, 0x85CA01: 0x2D}[at]
        a = pt(lab) + off
        p(at, [0xB9, orig_lo, 0xCA], [0xB9, a & 0xff, a >> 8])
    # box size refreshed on every draw
    b = L['box_size']
    p(0x85C7AE, [0x20, 0x19, 0xC8], [0x20, b & 0xff, (b >> 8) & 0xff])
    # hook where both box variants finish
    h = L['hover_entry']
    p(0x85C97E, [0x20, 0x9F, 0xC9], [0x20, h & 0xff, (h >> 8) & 0xff])
    # the new code + data (free space: zeros)
    patches.append((snes_to_file(ORG), bytes(len(code)), code))
    return patches, L, code

OFF_CODE = '''
.m 0
.x 0
box_size:
    LDA #$0509
    STA $0FF7,X
    JMP $C819
'''

def build_off():
    # option off: original 9x5 box, but still refresh its size on every draw (see box_size)
    code, L = assemble(OFF_CODE, ORG)
    b = L['box_size']
    return [(snes_to_file(0x85C7AE), bytes([0x20, 0x19, 0xC8]), bytes([0x20, b & 0xff, (b >> 8) & 0xff])),
            (snes_to_file(ORG), bytes(len(code)), code)]


# ---------------- switchable version (PC port): on/off at any time through a flag word in ROM ----------------
# Every changed instruction in the box code becomes a JSR to a small helper that checks hover_flag
# ($85:FA00, 0 = off, 1 = on) and then does the original or the enlarged-box version. The port writes
# the flag into its copy of the ROM when the option is changed, so it takes effect immediately.
# (Data reads go through the bus, so the flag is not baked into the translated code.)
SITES = [  # (address, original bytes, kind, value when on, value when off)
    (0x85C673, [0xA9, 0x09, 0x00], 'LDA', W, 0x09),          # box width
    (0x85C679, [0xA9, 0x05, 0x00], 'LDA', H, 0x05),          # box height
    (0x85C7B4, [0xA9, 0xBF, 0xC7], 'LDA', 'template', 0xC7BF),
    (0x85C81D, [0xC9, 0xD0, 0x00], 'CMP', 0xC0, 0xD0),       # right clamp threshold
    (0x85C822, [0xC9, 0x30, 0x00], 'CMP', 0x38, 0x30),       # left clamp threshold
    (0x85C827, [0xA9, 0x28, 0x00], 'LDA', 0x38, 0x28),       # left clamp value
    (0x85C82C, [0xA9, 0xC0, 0x00], 'LDA', 0xB8, 0xC0),       # right clamp value
    (0x85C833, [0xE9, 0x03, 0x00], 'SBC', 0x05, 0x03),       # columns left of the cursor
    (0x85C83C, [0xC9, 0x30, 0x00], 'CMP', 0x48, 0x30),       # near the top: box below the cursor
    (0x85C842, [0x69, 0x48, 0x00], 'ADC', 0x58, 0x48),
    (0x85C849, [0xE9, 0x06, 0x00], 'SBC', 0x08, 0x06),       # rows above the cursor
    (0x85C9E8, [0xB9, 0x0B, 0xCA], 'TAB', ('tail_below', 0), 0xCA0B),
    (0x85C9F0, [0xB9, 0x0D, 0xCA], 'TAB', ('tail_below', 2), 0xCA0D),
    (0x85C9F9, [0xB9, 0x2B, 0xCA], 'TAB', ('tail_above', 0), 0xCA2B),
    (0x85CA01, [0xB9, 0x2D, 0xCA], 'TAB', ('tail_above', 2), 0xCA2D),
]

def dual_source(L):
    lab = lambda v: (L.get(v[0], 0) + v[1]) & 0xffff if isinstance(v, tuple) else (L.get(v, 0) & 0xffff if isinstance(v, str) else v)
    src = ".m 0\n.x 0\nhover_flag:\n    .dw $0001\n"
    src += CODE.split('hover_entry:')[0].replace('.m 0\n.x 0\n', '', 1)  # template + tail tables
    src += """
hover_entry:            ; from $85:C97E: stats (if on), then the original $C99F
    PHP
    PHA
    LDA hover_flag
    BEQ he_off
    PLA
    PLP
    JSL hover_stats
    JMP $C99F
he_off:
    PLA
    PLP
    JMP $C99F

box_size:               ; from $85:C7AE on every draw: the size that matches the setting
    LDA hover_flag
    BEQ bs_off
    LDA #$0%d0%X
    BRA bs_set
bs_off:
    LDA #$0509
bs_set:
    STA $0FF7,X
    JMP $C819
""" % (H, W)
    for i, (at, orig, kind, on, off) in enumerate(SITES):
        n = 'sw%d' % i
        if kind == 'LDA':
            src += f"{n}:\n    LDA hover_flag\n    BEQ {n}o\n    LDA #${lab(on):04X}\n    RTS\n{n}o:\n    LDA #${off:04X}\n    RTS\n"
        elif kind == 'TAB':
            src += f"{n}:\n    LDA hover_flag\n    BEQ {n}o\n    LDA ${lab(on):04X},Y\n    RTS\n{n}o:\n    LDA ${off:04X},Y\n    RTS\n"
        else:  # CMP / ADC / SBC: keep A and the carry, flags come from the operation itself
            src += f"{n}:\n    PHA\n    LDA hover_flag\n    BEQ {n}o\n    PLA\n    {kind} #${lab(on):04X}\n    RTS\n{n}o:\n    PLA\n    {kind} #${off:04X}\n    RTS\n"
    src += "hover_stats:" + CODE.split('hover_stats:', 1)[1]
    return src

def build_dual():
    code, L = assemble(dual_source({}), ORG)      # first pass: label addresses
    code, L2 = assemble(dual_source(L), ORG)
    assert L2 == L
    patches = []
    for i, (at, orig, kind, on, off) in enumerate(SITES):
        a = L['sw%d' % i] & 0xffff
        patches.append((snes_to_file(at), bytes(orig), bytes([0x20, a & 0xff, a >> 8])))
    b = L['box_size'] & 0xffff; h = L['hover_entry'] & 0xffff
    patches.append((snes_to_file(0x85C7AE), bytes([0x20, 0x19, 0xC8]), bytes([0x20, b & 0xff, b >> 8])))
    patches.append((snes_to_file(0x85C97E), bytes([0x20, 0x9F, 0xC9]), bytes([0x20, h & 0xff, h >> 8])))
    patches.append((snes_to_file(ORG), bytes(len(code)), code))
    return patches, snes_to_file(L['hover_flag']), code

def apply(rom, patches):
    rom = bytearray(rom)
    for off, orig, new in patches:
        if rom[off:off + len(orig)] != orig:
            raise ValueError('unexpected bytes at %06X: %s' % (off, rom[off:off + len(orig)].hex()))
        rom[off:off + len(new)] = new
    return rom

if __name__ == '__main__':
    patches, L, code = build()
    if sys.argv[1] == 'patches':
        for off, o, n in patches: print('%06X %s -> %s' % (off, o.hex()[:24], n.hex()[:24]))
        print('code+data %d bytes at %06X, hook at %06X' % (len(code), ORG, L['hover_entry']))
    elif sys.argv[1] == 'apply':
        rom = open(sys.argv[2], 'rb').read()
        if len(rom) % 0x8000 == 0x200: rom = rom[0x200:]
        open(sys.argv[3], 'wb').write(apply(rom, patches))
    elif sys.argv[1] == 'apply-dual':
        rom = open(sys.argv[2], 'rb').read()
        if len(rom) % 0x8000 == 0x200: rom = rom[0x200:]
        dp, flag, code = build_dual()
        rom = apply(rom, dp)
        if len(sys.argv) > 4: rom[flag] = int(sys.argv[4])
        open(sys.argv[3], 'wb').write(rom)
    elif sys.argv[1] == 'kitdata':      # the same patch as data for fe4kit (fe4hoverpatch.py)
        dp, flag, dcode = build_dual()
        with open(sys.argv[2], 'w') as f:
            f.write('"""Unit stats in the map hover box (MT / HIT / AS / AVO), the same patch the PC port uses.\n\n'
                    'Generated by the port\'s tools/fe4hover.py. The new code lives at $85:FA00; the word at FLAG\n'
                    'switches it on (1) or off (0). Headerless file offsets.\n"""\n')
            f.write('FLAG = 0x%06X\n' % flag)
            f.write('PATCHES = [\n')
            for off, o, n in dp:
                f.write('    (0x%06X, bytes.fromhex(%r), bytes.fromhex(%r)),\n' % (off, o.hex(), n.hex()))
            f.write(']\n\n\n')
            f.write('''def apply(rom, on=True):
    """Add the patch to a headerless ROM (bytearray). False if the game's code differs there."""
    def same(off, data, skip=0):
        return bytes(rom[off + skip:off + len(data)]) == data[skip:]
    if not all(same(off, new, 2 if len(new) > 16 else 0) for off, orig, new in PATCHES):
        if not all(same(off, orig) for off, orig, new in PATCHES):
            return False
        for off, orig, new in PATCHES:
            rom[off:off + len(new)] = new
    rom[FLAG] = 1 if on else 0
    rom[FLAG + 1] = 0
    return True
''')
        print('wrote', sys.argv[2])
    elif sys.argv[1] == 'header':
        dp, flag, dcode = build_dual()
        print('switchable: %d bytes at %06X, flag at file %06X' % (len(dcode), ORG, flag))
        with open(sys.argv[2], 'w') as f:
            f.write('// Generated by tools/fe4hover.py: map hover box with Mt/Hit/Avo/AS. Do not edit.\n')
            f.write('#include "fe4patch.h"\n')
            f.write('#define FE4_HOVER_FLAG 0x%06X  // file offset of the on/off word (1 = on)\n' % flag)
            for name, plist in (('FE4_HOVER', dp),):
                for i, (off, o, n) in enumerate(plist):
                    f.write('static const unsigned char %s_o%d[] = {%s};\n' % (name, i, ','.join(str(b) for b in o)))
                    f.write('static const unsigned char %s_n%d[] = {%s};\n' % (name, i, ','.join(str(b) for b in n)))
                f.write('static const Fe4Patch %s[] = {\n' % name)
                for i, (off, o, n) in enumerate(plist):
                    f.write('  { 0x%06X, %d, %d, %s_o%d, %s_n%d },\n' % (off, len(o), len(n), name, i, name, i))
                f.write('  { 0, 0, 0, 0, 0 }\n};\n')
