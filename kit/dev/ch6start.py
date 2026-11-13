#!/usr/bin/env python3
"""Make a TEST copy of a built ROM whose New Game opens straight on chapter 6 (or 7-11 with --chapter).

    python dev/ch6start.py myhack.smc test6.smc
    python dev/ch6start.py myhack.smc test6.smc --marry Lewyn-Ayra,Lex-Erin --single Bridget
    python dev/ch6start.py myhack.smc test9.smc --chapter 9

Before chapter 6 loads, the gen-1 cast is created and married (FE4's usual pairs unless you
give --marry; --single leaves a woman unmarried so her children's substitutes appear), and
Sigurd is marked dead, as at the end of chapter 5.  Then the game's own transition runs: the
children are born (with your parent links and inheritance rules), and chapter 6 opens.
Gen-1 stats are their starting ones, so the children's numbers are lower than in a real
playthrough.  For testing only: the copy can't play the first half of the game.
With --chapter 7-11 the transition runs the same way, then that chapter loads: the army is the
children and their substitutes as chapter 6 starts them (no later recruits, no levels).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import fe4lib as L
from asm65816 import Asm

CAST = [1, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24]
PAIRS = {16: 1, 17: 6, 18: 13, 19: 14, 20: 8, 21: 12, 22: 10, 23: 9, 24: 5}   # a common playthrough
CHAPTER_LOAD = 0x00AF06      # LDA $0D6A; JSL $86C528  (new game / chapter start)
CHAPTER_UNITS = 0x00AF19     # JSL $8480EC (runs the gen-2 transition when the chapter is 6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--marry', default='', help='man-woman pairs by name or id, comma-separated')
    ap.add_argument('--single', default='', help='women left unmarried, comma-separated')
    ap.add_argument('--chapter', type=int, default=6, help='the chapter New Game opens (6-11)')
    a = ap.parse_args()
    copier, rom = L.load_rom(a.rom)
    look = {}
    for k in (0, 2):
        for idx, _, _, lab in L.unit_rows(rom, k):
            if idx <= 24:
                look.setdefault(lab.lower(), idx)

    def uid(t):
        t = t.strip()
        if t.isdigit():
            return int(t)
        if t.lower() not in look:
            sys.exit(f'unknown gen-1 unit {t!r}')
        return look[t.lower()]
    pairs = dict(PAIRS)
    for p in filter(None, a.marry.split(',')):
        m, w = (uid(x) for x in p.split('-'))
        if m >= 16:
            m, w = w, m
        for k in [k for k, v in pairs.items() if v == m]:
            del pairs[k]
        pairs[w] = m
    if not 6 <= a.chapter <= 11:
        sys.exit('--chapter is 6 to 11')
    for t in filter(None, a.single.split(',')):
        pairs.pop(uid(t), None)
    if rom[CHAPTER_LOAD:CHAPTER_LOAD + 7] != bytes.fromhex('ad6a0d2228c586') or \
       rom[CHAPTER_UNITS:CHAPTER_UNITS + 4] != bytes.fromhex('22ec8084'):
        sys.exit('this ROM already has a test start (or is not FE4)')
    # free space for the stub: zero bytes just below the kit's code area
    org = next((x for x in range(0x7DCC00, 0x7D0000, -0x100) if not any(rom[x:x + 0x400])), None)
    if org is None:
        sys.exit('no room for the test stub')
    s = Asm(org)
    s.label('load')
    s.op('lda', 'abs', 0x0D6A)
    s.op('bne', 'rel', 'a1')
    s.op('lda', 'long', 'chapter')
    s.op('sta', 'abs', 0x0D6A)
    s.label('a1')
    s.op('lda', 'abs', 0x0D6A)
    s.op('jsl', 'long', 0x86C528)
    s.op('rtl')
    s.label('units')
    s.op('php')
    s.op('rep', '#8', 0x30)
    s.op('phb')
    s.op('lda', 'abs', 0x0D6A)
    s.op('cmp', 'long', 'chapter')
    s.op('bne', 'far', 'go')
    s.op('lda', 'abs', 0x0D79)                  # not when a save is being loaded
    s.op('bit', '#', 0x0100)
    s.op('bne', 'far', 'go')
    for u in CAST:
        s.op('lda', '#', u)
        s.op('jsl', 'long', 0x84931A)
    for w, m in pairs.items():
        for p, q in ((w, m), (m, w)):
            s.op('lda', '#', p)
            s.op('jsl', 'long', 0x8484B4)
            s.op('phb')
            s.op('jsl', 'long', 0x849488)
            s.op('sep', '#8', 0x20)
            s.op('lda', '#', q)
            s.op('sta', 'abs,x', 3)
            s.op('rep', '#8', 0x20)
            s.op('plb')
    s.op('lda', '#', 1)                         # Sigurd fell at Belhalla
    s.op('jsl', 'long', 0x8484B4)
    s.op('bcs', 'rel', 'nos')
    s.op('lda', '#', 0x0200)
    s.op('jsl', 'long', 0x8495F5)
    s.label('nos')
    s.op('lda', '#', 0)                         # event flag 0: Seliph leads the army
    s.op('jsl', 'long', 0x8680BE)
    s.op('lda', 'abs', 0x0D6A)                  # chapters 7-11: the gen-2 transition as chapter 6 runs it
    s.op('cmp', '#', 7)                         # ($84:81A1), then that chapter's own units
    s.op('bcc', 'far', 'go')
    s.op('lda', '#', 6)
    s.op('sta', 'abs', 0x0D6A)
    s.op('jsl', 'long', 0x82F866)
    s.op('jsl', 'long', 0x8481FF)
    s.op('jsl', 'long', 0x8BCE71)
    s.op('lda', 'long', 'chapter')
    s.op('sta', 'abs', 0x0D6A)
    s.label('go')
    s.op('jsl', 'long', 0x8480EC)
    s.op('plb')
    s.op('plp')
    s.op('rtl')
    s.label('chapter')                          # data: the chapter New Game opens
    s.data([a.chapter, 0])
    code = s.assemble()
    rom[org:org + len(code)] = code
    rom[CHAPTER_LOAD:CHAPTER_LOAD + 7] = bytes([0x22]) + s.labels['load'].to_bytes(3, 'little') + b'\xea' * 3
    rom[CHAPTER_UNITS:CHAPTER_UNITS + 4] = bytes([0x22]) + s.labels['units'].to_bytes(3, 'little')
    L.save_rom(a.out, copier, rom)
    names = {idx: lab for k in (0, 2) for idx, _, _, lab in L.unit_rows(rom, k)}
    print('couples:', ', '.join(f'{names.get(m, m)}-{names.get(w, w)}' for w, m in sorted(pairs.items())))
    print('wrote', a.out, f'(New Game starts at chapter {a.chapter})')


if __name__ == '__main__':
    main()
