"""Event conditions the game doesn't have, added by the kit (editor 1.3).

Rout: `03 [flag] [slot mask word] 00 00`.  True when every army slot in the mask (bit n = slot n, 1-7) has no
units left on the map, checked as each army's phase starts (mode $21, raised at $81:A9AC / $81:ADB3 with
$0EBD = turn, $0EBF = the slot whose phase it is).

The game's own condition $03 (mode 2, 5 bytes) is used by no chapter, so its handler in the event VM table
($86:83FA + 2*3, a pointer in bank $86) is pointed at the kit's: it keeps the length (5) so scripts decode the
same with or without it.  Unit lists: word offsets from $7E:2180 per slot 0-7 at $7E:2180 + 2*slot; a list
holds +0 army, +1 ?, +2/+3 relations, +4 count, +5 handles.

Condition protocol (from $86:866F and $86:84ED): the handler is entered with Y at the flag byte and carry set
when the VM only skips; it sets $0EB6 = length after the op byte and $0EAB = a matcher, loads A = the mode the
condition answers to and jumps to $86:84ED, which compares the mode with $0EBC, checks the flag and calls the
matcher (Y at the flag byte); the matcher returns carry set for a match.
"""
import os

import fe4events as E
from asm65816 import Asm

ROUT_OP = 0x03
ROUT_LEN = 5
TABLE = E.EV_OPTABLE                  # file offset of the event handler table ($86:83FA)
ORIG_03 = 0x898A                      # the game's handler for $03: LDA #$0002, JML $86:866F


def rout_cond(flag, slots):
    """Hex for 'every army in slots is gone'."""
    mask = 0
    for s in slots:
        if not 1 <= int(s) <= 7:
            raise ValueError('Rout works for armies in slots 1 to 7.')
        mask |= 1 << int(s)
    if not mask:
        raise ValueError('Choose the armies to rout.')
    return '03 %02X %02X %02X 00 00' % (flag, mask & 0xFF, mask >> 8)


def rout_slots(b):
    """Slots of a rout condition's bytes."""
    mask = b[2] | b[3] << 8
    return [s for s in range(1, 8) if mask >> s & 1]


def uses_rout(proj):
    d = os.path.join(proj, 'events')
    if not os.path.isdir(d):
        return False
    for f in os.listdir(d):
        if f.endswith('.evt') and f != 'scenes.evt' and not f.startswith('ai'):
            with open(os.path.join(d, f), encoding='utf-8') as fh:
                for line in fh:
                    h = line.split(';', 1)[0].split(':', 1)
                    if len(h) == 2 and h[1].split()[:1] == ['03']:
                        return True
    return False


def _code(base):
    a = Asm(base)
    a.label('handler')
    a.op('php')
    a.op('ldx', '#', ROUT_LEN)
    a.op('stx', 'abs', 0x0EB6)
    a.op('ldx', '#', 'matcher')
    a.op('stx', 'abs', 0x0EAB)
    a.op('plp')
    a.op('lda', '#', 0x0021)
    a.op('jml', 'long', 0x8684ED)
    a.label('matcher')
    a.op('phy')
    a.op('lda', 'abs,y', 0x0001)
    a.op('lsr')                         # slot 0 is never checked
    a.op('pha')
    a.op('ldx', '#', 0x0002)
    a.label('loop')
    a.op('lda', 'sr', 1)
    a.op('lsr')
    a.op('sta', 'sr', 1)
    a.op('bcc', 'rel', 'next')
    a.op('lda', 'long,x', 0x7E2180)
    a.op('phx')
    a.op('tax')
    a.op('lda', 'long,x', 0x7E2184)
    a.op('plx')
    a.op('and', '#', 0x00FF)
    a.op('bne', 'rel', 'fail')
    a.label('next')
    a.op('inx')
    a.op('inx')
    a.op('cpx', '#', 0x0010)
    a.op('bcc', 'rel', 'loop')
    a.op('pla')
    a.op('ply')
    a.op('sec')
    a.op('rts')
    a.label('fail')
    a.op('pla')
    a.op('ply')
    a.op('clc')
    a.op('rts')
    return a.assemble()


def apply(rom, proj, space):
    if not uses_rout(proj):
        return 0
    o = TABLE + 2 * ROUT_OP
    if rom[o] | rom[o + 1] << 8 != ORIG_03:
        raise SystemExit('rout condition: the event table entry for $03 is not the game\'s; left as it is')
    size = len(_code(0x868000))
    fo, sn = space.alloc(0x868000, size)
    code = _code(sn)
    rom[fo:fo + len(code)] = code
    rom[o], rom[o + 1] = sn & 0xFF, (sn >> 8) & 0xFF
    return 1
