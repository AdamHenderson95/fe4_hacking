"""Skill activation animations: the sparkles that play when Astra, Luna, Sol or Pavise activate.

When a skill activates, the battle code adds an event `FE xx` to the battle's event list (xx = the
skill's number; the kit's new skills add one too, see fe4skillfx h_push).  When a fighter's
animation reaches it, $95:A761 calls $96:F697, which the game hard-codes:
    $13 Astra  -> 5 colours $E0:27C3 to sprite palette 3, colours 10-14 ($7E:0274), effect $36
    $14 Luna   -> $E0:27CD, effect $37        $15 Sol -> $E0:27D7, effect $38
    $16 (22)   -> $E0:27E1 to sprite palette 7 ($7E:02F4), $7F:FC5F = $16, effect $39
    $17 (23)   -> $E0:27EB, palette 7, $FC5F = $17, effect $3A
    $02 Pavise -> $E0:27F5, palette 7, $FC5F = $02, effect $3F
$7F:FC5F is the defender's reaction when the hit lands ($96:F9BF; $96:FA39 picks the reaction's
pictures: $17, $02 (the shield), anything else).

The kit replaces $96:F697 with a table: one 16-byte row per skill number:
    +0 skill number  +1 reaction (0 none, else the $FC5F value)  +2 effect (word)  +4 five colours
ending with $FF.  skill_anims.csv holds the rows; skills without a row keep the game's look (new
skills from fe4skillfx use the look of the skill they borrow: Luna, Sol or Pavise).
"""
import csv
import os

import fe4skillfx as FX
from asm65816 import Asm
from dis65816 import snes_to_file

CALL = 0x96F697
CALL_BYTES = bytes.fromhex('5ac8b72429ff00')
START = 0x96A4B2
FILE = 'skill_anims.csv'
FIELDS = ['skill', '_name', 'effect', 'reaction', 'colours']
GAME = [  # skill, effect, colours at, reaction
    (0x13, 0x36, 0xE027C3, 0), (0x14, 0x37, 0xE027CD, 0), (0x15, 0x38, 0xE027D7, 0),
    (0x16, 0x39, 0xE027E1, 0x16), (0x17, 0x3A, 0xE027EB, 0x17), (0x02, 0x3F, 0xE027F5, 0x02)]
REACTIONS = {0: 'none', 0x02: 'shield', 0x16: 'reaction_a', 0x17: 'reaction_b'}
REACTION_CODES = {v: k for k, v in REACTIONS.items()}
REACTION_NAMES = {0: 'None (the sparkle plays on the skill user)', 0x02: 'Shield (Pavise)',
                  0x16: 'Reaction A (unused skill 22)', 0x17: 'Reaction B (unused skill 23)'}
SPARKLES = [0x36, 0x37, 0x38, 0x39, 0x3A, 0x3F]      # the game's sparkle effects
ENT = 16


def _colours(rom, a):
    f = snes_to_file(a)
    return [rom[f + 2 * i] | rom[f + 2 * i + 1] << 8 for i in range(5)]


def game_rows(rom):
    """{skill: (effect, reaction, [5 colours])} as the game has them."""
    return {sid: (eff, rea, _colours(rom, at)) for sid, eff, at, rea in GAME}


def installed(rom):
    f = snes_to_file(CALL)
    return rom[f] == 0x5C


def table_rows(rom):
    """The rows in a ROM (the game's, or the kit's table once installed)."""
    if not installed(rom):
        return game_rows(rom)
    f = snes_to_file(CALL)
    hook = rom[f + 1] | rom[f + 2] << 8 | rom[f + 3] << 16
    # the table address is the operand of the first LDA long,X in the hook (see build())
    g = snes_to_file(hook)
    k = bytes(rom[g:g + 64]).index(b'\xbf')
    t = rom[g + k + 1] | rom[g + k + 2] << 8 | rom[g + k + 3] << 16
    out = {}
    h = snes_to_file(t)
    while rom[h] != 0xFF:
        out[rom[h]] = (rom[h + 2] | rom[h + 3] << 8, rom[h + 1], [rom[h + 4 + 2 * i] | rom[h + 5 + 2 * i] << 8 for i in range(5)])
        h += ENT
    return out


def export(rom, path, names):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for sid, (eff, rea, cols) in sorted(table_rows(rom).items()):
            w.writerow([sid, names.get(sid, ''), eff, REACTIONS.get(rea, rea), ' '.join(f'{c:04x}' for c in cols)])
    print('wrote', path)


def parse_rows(rows, where='skill_anims.csv'):
    """csv dicts -> {skill: (effect or None, reaction, colours)}"""
    out = {}
    for line, r in enumerate(rows, 2):
        try:
            sid = int(r['skill'])
            eff = int(r['effect']) if (r.get('effect') or '').strip() not in ('', 'none', '-') else None
            rea = r.get('reaction', '').strip() or 'none'
            rea = REACTION_CODES[rea] if rea in REACTION_CODES else int(rea, 0)
            cols = [int(c, 16) & 0x7FFF for c in (r.get('colours') or '').split()]
        except (KeyError, ValueError):
            raise SystemExit(f'{where} line {line}: skill and effect are numbers, reaction is none, shield, '
                             'reaction_a or reaction_b, colours are five 4-digit hex colours')
        if not 1 <= sid <= 0xFE or sid in out:
            raise SystemExit(f'{where} line {line}: skill {sid} is out of range or listed twice')
        if rea not in REACTIONS:
            raise SystemExit(f'{where} line {line}: reaction must be none, shield, reaction_a or reaction_b')
        if len(cols) != 5:
            raise SystemExit(f'{where} line {line}: colours are five 4-digit hex colours')
        out[sid] = (eff, rea, cols)
    return out


def read(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return None
    with open(p, newline='', encoding='utf-8') as fh:
        return parse_rows(list(csv.DictReader(fh)), p)


def build(rom, rows, n_effects):
    """Install the table hook with rows ({skill: (effect or None, reaction, colours)})."""
    region = FX.region_for(rom)
    tab = bytearray()
    for sid, (eff, rea, cols) in sorted(rows.items()):
        if eff is None:
            continue
        if not 0 <= eff < n_effects:
            raise SystemExit(f'{FILE}: skill {sid} plays effect {eff}, but effects are 0-{n_effects - 1}')
        tab += bytes([sid, rea]) + eff.to_bytes(2, 'little') + b''.join(c.to_bytes(2, 'little') for c in cols) + b'\0\0'
    tab += b'\xff' + bytes(ENT - 1)
    T = region.put(bytes(tab))
    a = Asm(region.cur)
    a.op('phy')
    a.op('iny')
    a.op('lda', 'dp_ind_long,y', 0x24)
    a.op('and', '#', 0x00FF)
    a.op('phx')
    a.op('pha')
    a.op('ldx', '#', 0)
    a.label('loop')
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0x00FF)
    a.op('cmp', '#', 0x00FF)
    a.op('beq', 'rel', 'done')
    a.op('cmp', 'sr', 1)
    a.op('beq', 'rel', 'found')
    a.op('txa')
    a.op('clc')
    a.op('adc', '#', ENT)
    a.op('tax')
    a.op('bra', 'rel', 'loop')
    a.label('found')
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0x00FF)
    a.op('beq', 'rel', 'mine')
    a.op('sep', '#8', 0x20)
    a.op('sta', 'long', 0x7FFC5F)
    a.op('rep', '#8', 0x20)
    for i in range(5):
        a.op('lda', 'long,x', T + 4 + 2 * i)
        a.op('sta', 'abs', 0x02F4 + 2 * i)
    a.op('bra', 'rel', 'go')
    a.label('mine')
    for i in range(5):
        a.op('lda', 'long,x', T + 4 + 2 * i)
        a.op('sta', 'abs', 0x0274 + 2 * i)
    a.label('go')
    a.op('lda', 'long,x', T + 2)
    a.op('jsl', 'long', START)
    a.label('done')
    a.op('pla')
    a.op('plx')
    a.op('ply')
    a.op('rtl')
    code = a.assemble()
    at = region.put(code)
    f = snes_to_file(CALL)
    if bytes(rom[f:f + 7]) != CALL_BYTES:
        raise SystemExit('skill animations: this ROM\'s battle code is different at $96:F697')
    rom[f:f + 7] = bytes([0x5C]) + at.to_bytes(3, 'little') + b'\xea\xea\xea'
    return at


def apply(rom, proj, n_effects):
    """skill_anims.csv -> the table hook (only when it differs from the game) and the kit's new skills'
    animation bytes (a new skill with its own row plays that row)."""
    rows = read(proj)
    if rows is None:
        return 0
    game = {k: (e, r, c) for k, (e, r, c) in game_rows(rom).items()}
    full = dict(game)
    full.update(rows)
    # new skills (fe4skillfx effect table): +7 = the row to play
    t = FX.table_addr(rom, 'proc')
    news = 0
    while t and rom[t]:
        sid = rom[t]
        if sid in rows:
            rom[t + 7] = sid if rows[sid][0] is not None else 0
            news += 1
        t += FX.ENT
    if full == game:
        return news
    build(rom, full, n_effects)
    print(f'skill animations: {len(rows)} row(s)')
    return 1 + news
