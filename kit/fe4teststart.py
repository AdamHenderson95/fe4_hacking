"""A test copy of a built ROM whose New Game goes straight to one chapter (1.1; was dev/ch6start.py).

    python fe4teststart.py myhack.smc test.smc --chapter 4
    python fe4teststart.py myhack.smc test6.smc --chapter 6 --marry Lewyn-Ayra,Lex-Erin --single Bridget

How each chapter is reached:
  * Prologue: nothing changes.
  * Chapters 1-5: New Game opens the Prologue and each chapter before the one asked for ends right after
    its opening scene (event $78, chapter clear, is added to its opening script; the Save Game screen
    that follows goes on to the next chapter), so the army those openings set up is carried on.
    Units that join later in a chapter (talks, visits) are not there.
  * Chapters 6-8: before chapter 6 loads, the generation-1 cast is created and married (FE4's usual
    pairs unless --marry is given; --single leaves a woman unmarried so her children's substitutes
    appear) and Sigurd is marked dead, as at the end of chapter 5; then the game's own transition runs
    (children born with your parent links and inheritance rules) and that chapter opens.  Gen-1 stats
    are their starting ones, so the children's numbers are lower than in a real playthrough.
  * Chapters 9-11: as chapter 6, then chapters 6 .. N-1 end right after their opening scenes.
  * --ending: on to the Final Chapter, whose opening scene then goes on to scene 412 (the ending).
For testing only: the copy can't play the first part of the game.
"""
import argparse
import sys

import fe4lib as L
from asm65816 import Asm
from dis65816 import snes_to_file

ENDING_SCENE_AT = 0xB1E58C   # scene 412, the Final Chapter's end: event $78, then the ending
ENDING_JUMP = 0xB1DF0C       # the end of scene 398 (the Final Chapter's opening), same bank
MAP_FLAG = 0x81A97C          # LDA #1 / STA $0508 at a map's start
SAVE_END = 0x91D921          # LDA $0D79 / BIT #$0400: chapter cleared -> $81:B301 (next chapter)
CHAPTER_HEADERS = 0x86C739   # 13 ptr24 to [chapter word][opening ptr24][trigger ptr24]
MAP_SONGS = 0x81AB0E         # map-start song per chapter (word)

CAST = [1, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24]
PAIRS = {16: 1, 17: 6, 18: 13, 19: 14, 20: 8, 21: 12, 22: 10, 23: 9, 24: 5}   # a common playthrough
CHAPTER_LOAD = 0x00AF06      # LDA $0D6A; JSL $86C528  (new game / chapter start)
CHAPTER_UNITS = 0x00AF19     # JSL $8480EC (runs the gen-2 transition when the chapter is 6)


def gen1_ids(rom):
    look = {}
    for k in (0, 2):
        for idx, _, _, lab in L.unit_rows(rom, k):
            if idx <= 24:
                look.setdefault(lab.lower(), idx)
    return look


def apply(rom, chapter, marry='', single='', ending=False):
    """Change rom (a bytearray, no copier header) so New Game reaches `chapter` (0-11).
    Returns a sentence for the person about what New Game does now."""
    if ending:
        chapter = 11
    if not 0 <= chapter <= 11:
        raise ValueError('Chapter is 0 (Prologue) to 11 (Final Chapter).')
    if chapter == 0:
        return 'New Game starts the Prologue as usual.'
    if rom[CHAPTER_LOAD:CHAPTER_LOAD + 7] != bytes.fromhex('ad6a0d2228c586') or \
       rom[CHAPTER_UNITS:CHAPTER_UNITS + 4] != bytes.fromhex('22ec8084'):
        raise ValueError('This ROM already has a test start (or is not FE4).')
    look = gen1_ids(rom)

    def uid(t):
        t = t.strip()
        if t.isdigit():
            return int(t)
        if t.lower() not in look:
            raise ValueError(f'unknown generation-1 unit {t!r}')
        return look[t.lower()]
    pairs = dict(PAIRS)
    for p in filter(None, marry.split(',')):
        m, w = (uid(x) for x in p.split('-'))
        if m >= 16:
            m, w = w, m
        for k in [k for k, v in pairs.items() if v == m]:
            del pairs[k]
        pairs[w] = m
    for t in filter(None, single.split(',')):
        pairs.pop(uid(t), None)
    gen2 = chapter >= 6
    first = 6 if gen2 else 0                    # the chapter New Game opens
    skip_from = 6 if chapter >= 9 else 0 if not gen2 else None
    # free space for the stub: zero bytes just below the kit's code area
    org = next((x for x in range(0x7DCC00, 0x7D0000, -0x100) if not any(rom[x:x + 0x600])), None)
    if org is None:
        raise ValueError('There is no room for the test start.')
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
    if gen2:
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
    s.label('clear')                            # the Save Game screen's end ($91:D921): chapters skip_from ..
    s.op('lda', 'abs', 0x0D6A)                  # N-1 count as cleared (the map's start clears the flag
    s.op('cmp', 'long', 'from')                 # $78 set), so $81:B301 opens the next chapter
    s.op('bcc', 'rel', 'cl1')
    s.op('cmp', 'long', 'target')
    s.op('bcs', 'rel', 'cl1')
    s.op('stz', 'abs', 0x0508)                  # the map's phase start set it ($81:A97F): songs wait on it
    s.op('lda', '#', 0x0400)
    s.op('bra', 'rel', 'cl2')
    s.label('cl1')
    s.op('lda', 'abs', 0x0D79)
    s.label('cl2')
    s.op('bit', '#', 0x0400)
    s.op('rtl')
    s.label('mapflag')                          # $81:A97C (map start): $0508 = 1 makes songs wait for the
    s.op('lda', 'abs', 0x0D6A)                  # map's first phase. A skipped chapter never gets there,
    s.op('cmp', 'long', 'from')                 # and its Save Game screen ignores input while a song
    s.op('bcc', 'rel', 'mf1')                   # waits ($91:D864), so it is left at 0 there
    s.op('cmp', 'long', 'target')
    s.op('bcs', 'rel', 'mf1')
    s.op('rtl')
    s.label('mf1')
    s.op('lda', '#', 1)
    s.op('sta', 'abs', 0x0508)
    s.op('rtl')
    s.label('from')                             # data: the first chapter that ends at once
    s.data([skip_from if skip_from is not None else 0xFF, 0])
    s.label('target')                           # data: the chapter asked for
    s.data([chapter, 0])
    s.label('chapter')                          # data: the chapter New Game opens
    s.data([chapter, 0])
    code = s.assemble()
    if skip_from is not None:   # open `first`; chapters skip_from .. N-1 end right after their opening
        hdrs = snes_to_file(CHAPTER_HEADERS)
        spot = org + len(code) + 0x10
        for ch in range(skip_from, chapter):
            hf = snes_to_file(int.from_bytes(rom[hdrs + 3 * ch:hdrs + 3 * ch + 3], 'little'))
            of = snes_to_file(int.from_bytes(rom[hf + 2:hf + 5], 'little'))
            # the opening script ends by running the opening scene ($30 FF lo hi) and FF FF: a copy of
            # it ends with $78 (chapter clear) after the scene: the game goes to its Save Game screen
            k = next((i for i in range(of, of + 0x400) if rom[i] == 0x30 and rom[i + 1] == 0xFF
                      and rom[i + 4:i + 6] == b'\xff\xff'), None)
            if k is None:
                raise ValueError(f'Chapter {ch}: its opening script is not as expected.')
            new = rom[of:k + 4] + b'\x78\xff\xff'
            rom[spot:spot + len(new)] = new
            rom[hf + 2:hf + 5] = spot.to_bytes(3, 'little')    # banks $70-$7D: SNES address = file offset
            spot += len(new)
            if spot > org + 0x600:
                raise ValueError('There is no room for the test start.')
            # no map-start song: its upload would wait for the map, and the Save Game screen for it
            fs = snes_to_file(MAP_SONGS) + 2 * ch
            rom[fs:fs + 2] = b'\0\0'
        code = code[:-2] + bytes([first, 0])        # New Game opens `first`
    if ending:              # the Final Chapter's opening scene (398) goes on to scene 412 (the ending)
        e = snes_to_file(ENDING_JUMP)
        if rom[e:e + 6] != bytes.fromhex('342300fdffff'):
            raise ValueError('The Final Chapter\'s opening scene is not as expected.')
        rom[e:e + 3] = bytes([0x02]) + (ENDING_SCENE_AT & 0xFFFF).to_bytes(2, 'little')   # scene GOTO
    rom[org:org + len(code)] = code
    rom[CHAPTER_LOAD:CHAPTER_LOAD + 7] = bytes([0x22]) + s.labels['load'].to_bytes(3, 'little') + b'\xea' * 3
    if gen2:
        rom[CHAPTER_UNITS:CHAPTER_UNITS + 4] = bytes([0x22]) + s.labels['units'].to_bytes(3, 'little')
    if skip_from is not None:
        se = snes_to_file(SAVE_END)
        if rom[se:se + 6] != bytes.fromhex('ad790d890004'):
            raise ValueError('The Save Game screen is not as expected.')
        rom[se:se + 6] = bytes([0x22]) + s.labels['clear'].to_bytes(3, 'little') + b'\xea\xea'
        mf = snes_to_file(MAP_FLAG)
        if rom[mf:mf + 6] != bytes.fromhex('a901008d0805'):
            raise ValueError('The map start is not as expected.')
        rom[mf:mf + 6] = bytes([0x22]) + s.labels['mapflag'].to_bytes(3, 'little') + b'\xea\xea'
    names = {idx: lab for k in (0, 2) for idx, _, _, lab in L.unit_rows(rom, k)}
    if ending:
        return 'New Game goes to the ending.'
    if skip_from is None:
        return f'New Game starts at chapter {chapter} (couples: ' + \
            ', '.join(f'{names.get(m, m)}-{names.get(w, w)}' for w, m in sorted(pairs.items())) + ').'
    return (f'New Game opens {"the Prologue" if first == 0 else "chapter 6"}; each chapter before chapter {chapter} '
            f'ends after its opening scene: press A through it and save at each Save Game screen.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--marry', default='', help='man-woman pairs by name or id, comma-separated')
    ap.add_argument('--single', default='', help='women left unmarried, comma-separated')
    ap.add_argument('--chapter', type=int, default=6, help='the chapter New Game opens (0-11)')
    ap.add_argument('--ending', action='store_true',
                    help='chapters 6-11 end at once and the Final Chapter opening goes on to the ending')
    a = ap.parse_args()
    copier, rom = L.load_rom(a.rom)
    try:
        msg = apply(rom, a.chapter, a.marry, a.single, a.ending)
    except ValueError as e:
        sys.exit(str(e))
    L.save_rom(a.out, copier, rom)
    print('wrote', a.out, '-', msg)


if __name__ == '__main__':
    main()
