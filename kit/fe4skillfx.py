#!/usr/bin/env python3
"""Skill effects engine: new 65816 code for skills from later Fire Emblem games.

All code lives in $7D:E000-$7D:EFFF and is built from the rows of skills.csv.

Battle structs (bank $7E): attacker $4EB5, defender $4F15, $60 bytes each:
  +06 unit  +10 HP  +12 max HP  +14 level  +30 attack speed  +32 final hit
  +34 hit  +36 avoid  +38 crit  +3A attack  +3C defence  +3E bonus damage
The combat setup ($84:D5DC, and $84:B79A for the second driver) ends with
JSL $84D9B6 for the defender; the combat hook replaces that call, runs it, then
adds each side's skill bonuses and recomputes final hit (+32 = hit - foe avoid).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asm65816 import Asm

REGION, REGION_END = 0x7DE000, 0x7DF000
SPILL, SPILL_END = 0x7DD000, 0x7DE000     # second area once the first is full (free space stops here)
HAS_SKILL, ITEM_SKILL = 0x87A19D, 0x87A2EF
ATK, DEF = 0x4EB5, 0x4F15
COMBAT_CALLS = [0x04D68B, 0x04B7DF]          # JSL $84D9B6 (second side)
FIELDS = {'speed': 0x30, 'hit': 0x34, 'avoid': 0x36, 'crit': 0x38, 'atk': 0x3A, 'def': 0x3C}
WHEN = {'always': 0, '': 0, 'attacking': 1, 'defending': 2, 'hp<=50': 3, 'hp<=25': 4, 'hp_full': 5,
        'ally_near': 6}
SCRATCH = 0x4EF5           # 32 bytes at attacker struct +40 (cleared at combat setup, unused by the game)
SCRATCH2 = 0x4F55          # 32 bytes at defender struct +40
SAVED = (0x0571, 0x0573, 0x0583, 0x0585, 0x056F)


HEADER = REGION                # 'SFX' + version, then 3-byte pointers to each table (0 = none)
SLOTS = ['combat', 'proc', 'defend', 'field', 'extra', 'menu', 'gen2', 'love']


_regions = {}


def region_for(rom):
    """The one code Region of a ROM being built (skills, menu and gen-2 code share it)."""
    r = _regions.get(id(rom))
    if r is None or r.rom is not rom:
        r = _regions[id(rom)] = Region(rom)
    return r


class Region:
    def __init__(self, rom):
        self.rom = rom
        self.cur = REGION + 4 + 3 * len(SLOTS)
        self.end = REGION_END
        rom[REGION:REGION + 4] = b'SFX\x01'

    def table(self, slot, data):
        a = self.put(data)
        o = HEADER + 4 + 3 * SLOTS.index(slot)
        self.rom[o:o + 3] = a.to_bytes(3, 'little')
        return a

    def fits(self, n):
        return self.cur + n <= self.end

    def switch(self):
        if self.end != REGION_END:
            raise SystemExit('the kit\'s code and tables do not fit in $7D:D000-$7D:EFFF')
        self.cur, self.end = SPILL, SPILL_END

    def put(self, data):
        if not self.fits(len(data)):
            self.switch()
        a = self.cur
        if a + len(data) > self.end:
            raise SystemExit('the kit\'s code and tables do not fit in $7D:D000-$7D:EFFF')
        self.rom[a:a + len(data)] = data
        self.cur += len(data)
        return a


def parse_bonus(text):
    """'atk+6;foe_crit-100' -> [(field offset | 0x80 for foe, amount)]"""
    out = []
    for part in text.replace(',', ';').split(';'):
        part = part.strip().lower().replace(' ', '')
        if not part:
            continue
        foe = part.startswith('foe_')
        if foe:
            part = part[4:]
        for i, ch in enumerate(part):
            if ch in '+-':
                name, num = part[:i], part[i:]
                break
        else:
            raise ValueError('write bonuses like atk+6 or foe_crit-100')
        if name not in FIELDS:
            raise ValueError('unknown bonus %r (use %s)' % (name, ', '.join(FIELDS)))
        n = int(num)
        if not -128 <= n <= 127:
            raise ValueError('bonus must be -128..127')
        out.append((FIELDS[name] | (0x80 if foe else 0), n & 0xFF))
    if not out:
        raise ValueError('no bonus given')
    return out


def _save(a):
    for v in SAVED:
        a.op('lda', 'abs', v)
        a.op('pha')


def _restore(a):
    for v in reversed(SAVED):
        a.op('pla')
        a.op('sta', 'abs', v)


def _has_skill(a, table, off, yes, no):
    """A = id at table+off,X; branches to yes/no.  X preserved."""
    a.op('lda', 'long,x', table + off)
    a.op('and', '#', 0xFF)
    a.op('jsl', 'long', HAS_SKILL)
    a.op('bcs', 'rel', yes)
    a.op('lda', 'long,x', table + off)
    a.op('and', '#', 0xFF)
    a.op('jsl', 'long', ITEM_SKILL)
    a.op('bcc', 'rel', no)


def build_combat(region, entries):
    """entries: [(skill id, when, field, amount byte)].  Returns hook address."""
    tab = bytearray()
    for sid, when, field, amt in entries:
        tab += bytes([sid, when, field, amt])
    tab += b'\0\0\0\0'
    T = region.table('combat', bytes(tab))
    a = Asm(region.cur)
    a.op('jsl', 'long', 0x84D9B6)
    a.op('php')
    a.op('rep', '#8', 0x30)
    a.op('phx')
    a.op('phy')
    a.op('phb')
    _save(a)
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 0x7E)
    a.op('pha')
    a.op('plb')
    a.op('rep', '#8', 0x20)
    for me, foe in ((ATK, DEF), (DEF, ATK)):
        a.op('ldx', '#', me)
        a.op('ldy', '#', foe)
        a.op('jsr', 'abs', 'side')
    for me, foe in ((ATK, DEF), (DEF, ATK)):
        a.op('ldx', '#', me)
        a.op('ldy', '#', foe)
        a.op('jsr', 'abs', 'final')
    _restore(a)
    a.op('plb')
    a.op('ply')
    a.op('plx')
    a.op('plp')
    a.op('rtl')

    # side: X = me, Y = foe.  Stack locals: me at 1,S / foe at 3,S (index pushed on top inside loop)
    a.label('side')
    a.op('phy')
    a.op('phx')
    a.op('lda', 'abs,x', 0x0000)
    a.op('bmi', 'far', 'side_out')
    a.op('lda', 'abs,x', 0x0006)
    a.op('beq', 'far', 'side_out')
    a.op('sta', 'abs', 0x056F)
    a.op('ldx', '#', 0)
    a.label('loop')
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('beq', 'far', 'side_out')
    a.op('phx')                                  # me at 3,S  foe at 5,S
    a.op('lda', 'sr', 3)
    a.op('tay')
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', WHEN['ally_near'])
    a.op('bne', 'rel', 'own')
    a.op('lda', 'long,x', T)                     # aura: an ally within 3 spaces has the skill
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'aura')
    a.op('bcc', 'far', 'next')
    a.op('brl', 'brl', 'apply')
    a.label('own')
    _has_skill(a, T, 0, 'have', 'next_j')
    a.label('have')
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0xFF)
    a.op('beq', 'rel', 'apply')                  # 0 always
    a.op('cmp', '#', 1)
    a.op('bne', 'rel', 'c2')
    a.op('lda', 'sr', 3)
    a.op('cmp', '#', ATK)
    a.op('beq', 'rel', 'apply')
    a.op('bra', 'rel', 'next_j')
    a.label('c2')
    a.op('cmp', '#', 2)
    a.op('bne', 'rel', 'c3')
    a.op('lda', 'sr', 3)
    a.op('cmp', '#', DEF)
    a.op('beq', 'rel', 'apply')
    a.label('next_j')
    a.op('brl', 'brl', 'next')
    a.label('c3')
    a.op('pha')                                  # cond on stack; me at 5,S
    a.op('lda', 'sr', 5)
    a.op('tay')
    a.op('pla')
    a.op('cmp', '#', 5)
    a.op('bne', 'rel', 'c34')
    a.op('lda', 'abs,y', 0x0010)                 # hp full
    a.op('cmp', 'abs,y', 0x0012)
    a.op('beq', 'rel', 'apply')
    a.op('bra', 'rel', 'next_j')
    a.label('c34')                               # 3: hp*2 <= max   4: hp*4 <= max
    a.op('cmp', '#', 4)
    a.op('beq', 'rel', 'quarter')
    a.op('lda', 'abs,y', 0x0010)
    a.op('asl')
    a.op('bra', 'rel', 'cmp_max')
    a.label('quarter')
    a.op('lda', 'abs,y', 0x0010)
    a.op('asl')
    a.op('asl')
    a.label('cmp_max')
    a.op('cmp', 'abs,y', 0x0012)
    a.op('beq', 'rel', 'apply')
    a.op('bcs', 'rel', 'next_j')
    a.label('apply')
    a.op('lda', 'long,x', T + 2)                 # field (+0x80 = foe)
    a.op('and', '#', 0x7F)
    a.op('sta', 'abs', 0x0573)                   # scratch (restored on exit)
    a.op('lda', 'long,x', T + 2)
    a.op('and', '#', 0x80)
    a.op('beq', 'rel', 'mine')
    a.op('lda', 'sr', 5)                         # foe struct
    a.op('bra', 'rel', 'addr')
    a.label('mine')
    a.op('lda', 'sr', 3)
    a.label('addr')
    a.op('clc')
    a.op('adc', 'abs', 0x0573)
    a.op('tay')
    a.op('lda', 'abs,y', 0x0000)
    a.op('cmp', '#', 0xFF)                       # 255 = "cannot fight" marker: leave it
    a.op('beq', 'rel', 'next')
    a.op('lda', 'long,x', T + 3)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', 0x80)
    a.op('bcc', 'rel', 'pos')
    a.op('ora', '#', 0xFF00)
    a.label('pos')
    a.op('clc')
    a.op('adc', 'abs,y', 0x0000)
    a.op('bpl', 'rel', 'store')                  # hit/avoid/speed may go negative (the game's own
    a.op('pha')                                  # numbers do); crit/atk/def stop at 0
    a.op('lda', 'abs', 0x0573)
    a.op('cmp', '#', 0x38)
    a.op('pla')
    a.op('bcc', 'rel', 'store')
    a.op('lda', '#', 0)
    a.label('store')
    a.op('sta', 'abs,y', 0x0000)
    a.label('next')
    a.op('plx')
    a.op('inx')
    a.op('inx')
    a.op('inx')
    a.op('inx')
    a.op('brl', 'brl', 'loop')
    a.label('side_out')
    a.op('plx')
    a.op('ply')
    a.op('rts')

    # aura: A = skill id, Y = my struct -> carry set if an ally on the map within 3 spaces has it
    A_ID, A_MY, A_ARMY, A_I, A_D = range(SCRATCH + 20, SCRATCH + 30, 2)
    a.label('aura')
    a.op('phx')
    a.op('phy')
    a.op('sta', 'abs', A_ID)
    a.op('lda', 'abs,y', 0x0000)
    a.op('bmi', 'far', 'au_no')
    a.op('sta', 'abs', A_MY)
    a.op('tax')
    a.op('lda', 'long,x', 0x7E477B)
    a.op('sta', 'abs', A_ARMY)
    a.op('ldx', '#', 0x8E)
    a.label('au_loop')
    a.op('stx', 'abs', A_I)
    a.op('cpx', 'abs', A_MY)
    a.op('beq', 'far', 'au_next')
    a.op('lda', 'long,x', 0x7E438B)
    a.op('bit', '#', 0x80)
    a.op('beq', 'far', 'au_next')
    a.op('lda', 'long,x', 0x7E46EB)
    a.op('beq', 'far', 'au_next')
    a.op('lda', 'long,x', 0x7E441B)
    a.op('ldx', 'abs', A_MY)
    a.op('sec')
    a.op('sbc', 'long,x', 0x7E441B)
    a.op('bpl', 'rel', 'au_dx')
    a.op('eor', '#', 0xFFFF)
    a.op('inc')
    a.label('au_dx')
    a.op('sta', 'abs', A_D)
    a.op('ldx', 'abs', A_I)
    a.op('lda', 'long,x', 0x7E44AB)
    a.op('ldx', 'abs', A_MY)
    a.op('sec')
    a.op('sbc', 'long,x', 0x7E44AB)
    a.op('bpl', 'rel', 'au_dy')
    a.op('eor', '#', 0xFFFF)
    a.op('inc')
    a.label('au_dy')
    a.op('clc')
    a.op('adc', 'abs', A_D)
    a.op('cmp', '#', 4)
    a.op('bcs', 'rel', 'au_next')
    a.op('ldx', 'abs', A_I)
    a.op('lda', 'long,x', 0x7E477B)
    a.op('tax')
    a.op('lda', 'abs', A_ARMY)
    a.op('jsl', 'long', 0x84C15F)                # 1 = enemies
    a.op('cmp', '#', 1)
    a.op('beq', 'rel', 'au_next')
    a.op('ldx', 'abs', A_I)
    a.op('lda', 'long,x', 0x7E46EB)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', 'abs', A_ID)
    a.op('jsl', 'long', HAS_SKILL)
    a.op('bcs', 'rel', 'au_yes')
    a.op('lda', 'abs', A_ID)
    a.op('jsl', 'long', ITEM_SKILL)
    a.op('bcs', 'rel', 'au_yes')
    a.label('au_next')
    a.op('ldx', 'abs', A_I)
    a.op('dex')
    a.op('dex')
    a.op('bpl', 'far', 'au_loop')
    a.label('au_no')
    a.op('ply')
    a.op('plx')
    a.op('clc')
    a.op('rts')
    a.label('au_yes')
    a.op('ply')
    a.op('plx')
    a.op('sec')
    a.op('rts')

    # final: X = me, Y = foe: +32 = clamp(hit - foe avoid); clamp crit
    a.label('final')
    a.op('lda', 'abs,x', 0x0000)
    a.op('bmi', 'rel', 'f_out')
    a.op('lda', 'abs,x', 0x0032)
    a.op('cmp', '#', 0xFF)
    a.op('beq', 'rel', 'f_out')
    a.op('lda', 'abs,x', 0x0034)
    a.op('sec')
    a.op('sbc', 'abs,y', 0x0036)
    a.op('bpl', 'rel', 'f1')
    a.op('lda', '#', 0)
    a.label('f1')
    a.op('cmp', '#', 101)
    a.op('bcc', 'rel', 'f2')
    a.op('lda', '#', 100)
    a.label('f2')
    a.op('sta', 'abs,x', 0x0032)
    a.op('lda', 'abs,x', 0x0038)
    a.op('cmp', '#', 101)
    a.op('bcc', 'rel', 'f3')
    a.op('lda', '#', 100)
    a.label('f3')
    a.op('sta', 'abs,x', 0x0038)
    a.label('f_out')
    a.op('rts')
    code = a.assemble()
    addr = region.put(code)
    for op in COMBAT_CALLS:
        region.rom[op + 1:op + 4] = addr.to_bytes(3, 'little')
    return addr


def table_addr(rom, slot):
    if rom[HEADER:HEADER + 3] != b'SFX':
        return 0
    o = HEADER + 4 + 3 * SLOTS.index(slot)
    return int.from_bytes(rom[o:o + 3], 'little')


WHEN_INV = {v: k for k, v in WHEN.items() if k}
FIELDS_INV = {v: k for k, v in FIELDS.items()}


def read_combat(rom):
    """{skill id: (when name, 'atk+6;foe_crit-100')} from a built ROM."""
    t = table_addr(rom, 'combat')
    out = {}
    while t and rom[t]:
        sid, when, field, amt = rom[t:t + 4]
        n = amt - 256 if amt >= 128 else amt
        txt = ('foe_' if field & 0x80 else '') + FIELDS_INV[field & 0x7F] + ('%+d' % n)
        w, parts = out.get(sid, (WHEN_INV.get(when, 'always'), []))
        parts.append(txt)
        out[sid] = (w, parts)
        t += 4
    return {k: (w, ';'.join(p)) for k, (w, p) in out.items()}


# ---------------------------------------------------------------- effects from later games
# Effect table: ENT bytes per skill
#   +0 id  +1 kind (1 attack proc, 2 defend proc, 3 on kill)  +2 flags (word)
#   +4 rate stat  +5 rate %  +6 rate flat  +7 animation (skill id whose battle effect plays; 0 none)
#   +8 power stat  +9 power %  +10 which preset (index into EFFECTS, for reading back)
ENT = 11
K_ATTACK, K_DEFEND, K_KILL = 1, 2, 3
F_PIERCE, F_HEAL, F_LETHAL, F_VENG, F_ADD, F_MULT, F_BLOCK, F_REDUCE = 1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80
F_PRAY, F_RANGED, F_SURE, F_COUNTER, F_GALE, F_LIFE = 0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000
F_SWORD = 0x4000           # attack skill: swords only (as FE4's Astra, Luna, Sol)
V_WT = SCRATCH + 30        # striker's weapon type
STAT_CODES = {'str': 1, 'mag': 2, 'skl': 3, 'spd': 4, 'def': 5, 'res': 6, 'lck': 7, 'lv': 8, 'lvl': 8,
              'level': 8, 'none': 0, '-': 0}
STAT_NAMES = {1: 'Str', 2: 'Mag', 3: 'Skl', 4: 'Spd', 5: 'Def', 6: 'Res', 7: 'Lck', 8: 'Lv', 0: 'none'}
STAT_GETTERS = {1: 0x849B15, 2: 0x849B70, 3: 0x849BCB, 4: 0x849C26, 5: 0x849C81, 6: 0x849CED, 7: 0x849D59,
                8: 0x849E23}
ANIM_LUNA, ANIM_SOL, ANIM_PAVISE = 20, 21, 2

# name: (kind, flags, rate stat, rate %, rate flat, animation, power stat, power %, description)
EFFECTS = {
    'aether':       (K_ATTACK, F_PIERCE | F_HEAL | F_SURE, 3, 50, 0, ANIM_SOL, 0, 0,
                     'Skl/2 %: ignores defence and heals the damage dealt'),
    'ignis':        (K_ATTACK, F_ADD | F_SURE, 3, 100, 0, ANIM_LUNA, 5, 50,
                     'Skl %: damage + half your Def'),
    'lethality':    (K_ATTACK, F_LETHAL | F_SURE, 3, 25, 0, ANIM_LUNA, 0, 0,
                     'Skl/4 %: defeats the enemy outright'),
    'sure_strike':  (K_ATTACK, F_SURE, 3, 100, 0, ANIM_LUNA, 0, 0,
                     'Skl %: the attacks always hit'),
    'colossus':     (K_ATTACK, F_ADD | F_SURE, 1, 100, 0, ANIM_LUNA, 1, 100,
                     'Str %: damage + your Str'),
    'deadeye':      (K_ATTACK, F_MULT | F_SURE, 3, 50, 0, ANIM_LUNA, 0, 200,
                     'Skl/2 %: double damage'),
    'vengeance':    (K_ATTACK, F_VENG | F_SURE, 3, 200, 0, ANIM_LUNA, 0, 50,
                     'Skl x2 %: damage + half the HP you have lost'),
    'great_shield': (K_DEFEND, F_BLOCK, 8, 100, 0, ANIM_PAVISE, 0, 0,
                     'Lv %: blocks all damage from a hit'),
    'aegis':        (K_DEFEND, F_REDUCE | F_RANGED, 3, 100, 0, ANIM_PAVISE, 0, 50,
                     'Skl %: halves damage from magic and ranged hits'),
    'pray':         (K_DEFEND, F_PRAY, 7, 100, 0, 0, 0, 0,
                     'Lck %: survive a deadly hit with 1 HP (needs 2+ HP)'),
    'counter':      (K_DEFEND, F_COUNTER, 0, 0, 100, 0, 0, 100,
                     'when hit up close, the attacker takes the same damage (never below 1 HP); '
                     'shows on the map after the battle'),
    'galeforce':    (K_KILL, F_GALE, 0, 0, 100, 0, 0, 0,
                     'player units: after defeating an enemy, may act again'),
    'lifetaker':    (K_KILL, F_LIFE, 0, 0, 100, 0, 0, 50,
                     'after defeating an enemy, heal power % of max HP'),
}
V_TMP, V_TMP2, V_ATK, V_DEF, V_ENT, V_MASK, V_DMG, V_AFL, V_AENT, V_HP = range(SCRATCH, SCRATCH + 20, 2)
# hook sites: (file offset, the 4 original bytes, return address)
HELP = {
    'aether': 'Ignores the foe\'s defence and heals the damage dealt.',
    'ignis': 'Adds half of Def to the damage.',
    'lethality': 'May defeat the foe in a single blow.',
    'sure_strike': 'The user\'s attacks always hit.',
    'colossus': 'Adds the user\'s Str to the damage.',
    'deadeye': 'May deal double damage.',
    'vengeance': 'Adds half the HP the user has lost to the damage.',
    'great_shield': 'May block all damage from a hit.',
    'aegis': 'May halve damage from magic or ranged hits.',
    'pray': 'May survive a deadly blow with 1 HP.',
    'counter': 'Foes who strike up close take the same damage.',
    'galeforce': 'Defeating a foe lets the user act again.',
    'lifetaker': 'Defeating a foe restores HP.',
}
DEFAULT_ICON = {K_ATTACK: 'spare1', K_DEFEND: 'pavise', K_KILL: 'spare2'}
SITE_HIT = (0x04E554, bytes.fromhex('afe6cc7e'), 0x84E558)     # LDA $7ECCE6
SITE_BLOCK = (0x04E5ED, bytes.fromhex('afe6cc7e'), 0x84E5F1)   # LDA $7ECCE6
SITE_DMG = (0x04E6C4, bytes.fromhex('bd3a0018'), 0x84E6F5)     # LDA $003A,X; CLC
SITE_HEAL = (0x04EEFF, bytes.fromhex('afdccc7e'), 0x84EF03)    # LDA $7ECCDC
SITE_SELECT = 0x04DEFD                                          # JSR $E0DE
SITE_KILL = (0x04DD6B, bytes.fromhex('ae7207bdeb46'), 0x84DD71)  # LDX $0772; LDA $46EB,X (after battle)
SITE_DONE = (0x04CB24, bytes.fromhex('bf9b487e'), 0x84CB28)     # LDA $7E489B,X (unit finished acting)
K_SLOT, K_PEND, K_TMP = SCRATCH2, SCRATCH2 + 2, SCRATCH2 + 4
GET_HP, GET_MHP, RNG, PUSH_EVENT = 0x8498C6, 0x849AE5, 0x84EF9C, 0x82E465


def parse_stat(text):
    t = text.strip().lower().rstrip('.')
    if t not in STAT_CODES:
        raise ValueError('stat must be Str, Mag, Skl, Spd, Def, Res, Lck or Lv')
    return STAT_CODES[t]


def parse_power(text, default_stat):
    """'Def 50' -> (5, 50);  '200' -> (default stat, 200)"""
    parts = text.replace('%', ' ').replace('*', ' ').replace('x', ' ').split()
    st = default_stat
    if parts and not parts[0].isdigit():
        st = parse_stat(parts.pop(0))
    if len(parts) != 1 or not parts[0].isdigit() or not 0 <= int(parts[0]) <= 255:
        raise ValueError('power is a percent 0-255, optionally after a stat (e.g. Def 50)')
    return st, int(parts[0])


def effect_entry(r, path, stat_fn=None, num_fn=None):
    """A skills.csv row -> effect table entry (id, kind, flags, rstat, rpct, rflat, anim, pstat, pp)."""
    kind, flags, rs, rp, rf, anim, ps, pp, _ = EFFECTS[r['effect']]
    where = f"{path}:{r['line']}"
    try:
        if r['stat']:
            rs = parse_stat(r['stat'])
        if r['amount']:
            rp = int(r['amount'], 0)
        if r['amount2']:
            rf = int(r['amount2'], 0)
        if r.get('power'):
            ps, pp = parse_power(r['power'], ps)
    except ValueError as e:
        raise SystemExit(f'{where}: {e}')
    w = r.get('weapons') or 'any'
    if w in ('sword', 'swords'):
        if kind != K_ATTACK:
            raise SystemExit(f'{where}: weapons=sword is for attack skills')
        flags |= F_SWORD
    elif w not in ('any', 'all'):
        raise SystemExit(f'{where}: weapons must be any (any weapon but staves) or sword')
    if not (0 <= rp <= 255 and 0 <= rf <= 100):
        raise SystemExit(f'{where}: amount must be 0-255 and amount2 0-100')
    return (r['id'], kind, flags, rs, rp, rf, anim, ps, pp, list(EFFECTS).index(r['effect']))


def read_effects(rom):
    """{id: csv fields} for the effect skills in a built ROM."""
    t = table_addr(rom, 'proc')
    out = {}
    names = list(EFFECTS)
    while t and rom[t]:
        sid = rom[t]
        flags = rom[t + 2] | rom[t + 3] << 8
        rs, rp, rf, anim, ps, pp, which = rom[t + 4:t + 11]
        name = names[which] if which < len(names) else '?'
        d = {'effect': name, 'stat': STAT_NAMES.get(rs, rs), 'amount': rp, 'amount2': rf}
        if rom[t + 1] == K_ATTACK:
            d['weapons'] = 'sword' if flags & F_SWORD else 'any'
        dflt = EFFECTS.get(name)
        if dflt and (dflt[7] or dflt[6]):
            d['power'] = ('%s %d' % (STAT_NAMES[ps], pp)) if dflt[6] else str(pp)
        out[sid] = d
        t += ENT
    return out


def _jml(rom, site, target):
    fo, orig, _ = site
    assert rom[fo:fo + len(orig)] == orig, 'hook site %06X already changed' % fo
    rom[fo:fo + len(orig)] = bytes([0x5C]) + target.to_bytes(3, 'little') + b'\xEA' * (len(orig) - 4)


def _helpers(a, T):
    # h_has: A = skill id, $056F = unit -> carry set if the unit has it (personal, class or item)
    a.label('h_has')
    a.op('sta', 'abs', V_TMP)
    a.op('jsl', 'long', HAS_SKILL)
    a.op('bcs', 'rel', 'h_has_r')
    a.op('lda', 'abs', V_TMP)
    a.op('jsl', 'long', ITEM_SKILL)
    a.label('h_has_r')
    a.op('rts')
    # h_stat: A = stat code, $056F = unit -> A = stat value (X, Y kept)
    a.label('h_stat')
    a.op('phx')
    a.op('phy')
    for code, getter in STAT_GETTERS.items():
        a.op('cmp', '#', code)
        a.op('bne', 'rel', 'h_stat_%d' % code)
        a.op('jsl', 'long', getter)
        a.op('bra', 'rel', 'h_stat_out')
        a.label('h_stat_%d' % code)
    a.op('lda', '#', 0)
    a.label('h_stat_out')
    a.op('ply')
    a.op('plx')
    a.op('rts')
    # h_pct: A = value (0-255), X = percent -> A = value * percent / 100
    a.label('h_pct')
    a.op('cmp', '#', 256)
    a.op('bcc', 'rel', 'h_pct_ok')
    a.op('lda', '#', 255)
    a.label('h_pct_ok')
    a.op('sep', '#8', 0x20)
    a.op('sta', 'long', 0x004202)
    a.op('txa')
    a.op('sta', 'long', 0x004203)
    a.op('rep', '#8', 0x20)
    for _ in range(4):
        a.op('nop')
    a.op('lda', 'long', 0x004216)
    a.op('sta', 'long', 0x004204)
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 100)
    a.op('sta', 'long', 0x004206)
    a.op('rep', '#8', 0x20)
    for _ in range(8):
        a.op('nop')
    a.op('lda', 'long', 0x004214)
    a.op('rts')
    # h_rate: X = entry, $056F = unit -> A = activation rate
    a.label('h_rate')
    a.op('lda', 'long,x', T + 4)
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'h_stat')
    a.op('phx')
    a.op('pha')
    a.op('lda', 'long,x', T + 5)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('pla')
    a.op('jsr', 'abs', 'h_pct')
    a.op('plx')
    a.op('sta', 'abs', V_TMP2)
    a.op('lda', 'long,x', T + 6)
    a.op('and', '#', 0xFF)
    a.op('clc')
    a.op('adc', 'abs', V_TMP2)
    a.op('rts')
    # h_push: A = animation id (0 = none): adds a skill event to the battle's event list
    a.label('h_push')
    a.op('and', '#', 0xFF)
    a.op('beq', 'rel', 'h_push_r')
    a.op('xba')
    a.op('ora', '#', 0x00FE)
    a.op('sta', 'abs', 0x054A)
    a.op('lda', '#', 0x7E00)
    a.op('sta', 'abs', 0x055D)
    a.op('lda', '#', 0x4F81)
    a.op('sta', 'abs', 0x055C)
    a.op('phx')
    a.op('phy')
    a.op('jsl', 'long', PUSH_EVENT)
    a.op('ply')
    a.op('plx')
    a.label('h_push_r')
    a.op('rts')
    # h_find: A = skill id -> X = its entry, carry set when found
    a.label('h_find')
    a.op('sta', 'abs', V_TMP)
    a.op('ldx', '#', 0)
    a.label('h_find_l')
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('beq', 'rel', 'h_find_no')
    a.op('cmp', 'abs', V_TMP)
    a.op('beq', 'rel', 'h_find_yes')
    a.op('txa')
    a.op('clc')
    a.op('adc', '#', ENT)
    a.op('tax')
    a.op('bra', 'rel', 'h_find_l')
    a.label('h_find_yes')
    a.op('sec')
    a.op('rts')
    a.label('h_find_no')
    a.op('clc')
    a.op('rts')


def _select(a, T):
    """fx_select (JSL from the bank $84 trampoline): X = striker, Y = target.  May start an attack proc."""
    a.label('fx_select')
    a.op('php')
    a.op('rep', '#8', 0x30)
    a.op('phb')
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 0x7E)
    a.op('pha')
    a.op('plb')
    a.op('rep', '#8', 0x20)
    a.op('stx', 'abs', V_ATK)
    a.op('sty', 'abs', V_DEF)
    _save(a)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', '#', 14)                       # target has Nihil: no attack skills
    a.op('jsr', 'abs', 'h_has')
    a.op('bcs', 'far', 'sel_out')
    a.op('ldx', 'abs', V_ATK)                  # the striker's weapon type: no skills with a staff
    a.op('lda', 'abs,x', 0x0028)
    a.op('jsl', 'long', 0x87E31D)
    a.op('jsl', 'long', 0x87E48D)
    a.op('sta', 'abs', V_WT)
    a.op('cmp', '#', 4)
    a.op('beq', 'far', 'sel_out')
    a.op('ldx', '#', 0)
    a.label('sel_loop')
    a.op('stx', 'abs', V_ENT)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('beq', 'far', 'sel_out')
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', K_ATTACK)
    a.op('bne', 'rel', 'sel_next')
    a.op('lda', 'long,x', T + 2)
    a.op('bit', '#', F_SWORD)
    a.op('beq', 'rel', 'sel_anyw')
    a.op('lda', 'abs', V_WT)
    a.op('bne', 'rel', 'sel_next')
    a.label('sel_anyw')
    a.op('ldy', 'abs', V_ATK)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'h_has')
    a.op('bcc', 'rel', 'sel_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('jsr', 'abs', 'h_rate')
    a.op('jsl', 'long', RNG)
    a.op('bcs', 'rel', 'sel_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('sta', 'abs', 0xCCDC)
    a.op('lda', 'long,x', T + 7)
    a.op('jsr', 'abs', 'h_push')
    a.op('bra', 'rel', 'sel_out')
    a.label('sel_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('txa')
    a.op('clc')
    a.op('adc', '#', ENT)
    a.op('tax')
    a.op('bra', 'far', 'sel_loop')
    a.label('sel_out')
    _restore(a)
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('plb')
    a.op('plp')
    a.op('rtl')


def _defend(a, T):
    """d_roll: A = flag mask, X = attacker, Y = defender -> carry set when one of the defender's
    defend skills with those flags activates (V_ENT = its entry).  X, Y kept."""
    a.label('d_roll')
    a.op('sta', 'abs', V_MASK)
    a.op('stx', 'abs', V_ATK)
    a.op('sty', 'abs', V_DEF)
    _save(a)
    a.op('lda', 'abs,x', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', '#', 14)                       # attacker has Nihil
    a.op('jsr', 'abs', 'h_has')
    a.op('bcs', 'far', 'd_fail')
    a.op('ldx', '#', 0)
    a.label('d_loop')
    a.op('stx', 'abs', V_ENT)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('beq', 'far', 'd_fail')
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', K_DEFEND)
    a.op('bne', 'far', 'd_next')
    a.op('lda', 'long,x', T + 2)
    a.op('and', 'abs', V_MASK)
    a.op('beq', 'far', 'd_next')
    a.op('lda', 'long,x', T + 2)
    a.op('bit', '#', F_RANGED)
    a.op('beq', 'rel', 'd_any')
    a.op('lda', 'abs', 0xCCDE)                 # strike flags: $20 = from range 2+, $40 = magic
    a.op('and', '#', 0x60)
    a.op('beq', 'far', 'd_next')
    a.label('d_any')
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'h_has')
    a.op('bcc', 'rel', 'd_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('jsr', 'abs', 'h_rate')
    a.op('jsl', 'long', RNG)
    a.op('bcs', 'rel', 'd_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T + 7)
    a.op('jsr', 'abs', 'h_push')
    _restore(a)
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('sec')
    a.op('rts')
    a.label('d_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('txa')
    a.op('clc')
    a.op('adc', '#', ENT)
    a.op('tax')
    a.op('bra', 'far', 'd_loop')
    a.label('d_fail')
    _restore(a)
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('clc')
    a.op('rts')


def _hit_block_heal(a, T):
    # fx_hit replaces LDA $7ECCE6 at $84:E554 (hit roll).  Attack procs with F_SURE always hit.
    a.label('fx_hit')
    a.op('lda', 'long', 0x7ECCE6)
    a.op('bit', '#', 0x10)
    a.op('bne', 'rel', 'hit_orig')
    a.op('lda', 'long', 0x7ECCDC)
    a.op('cmp', '#', 30)
    a.op('bcc', 'rel', 'hit_orig')
    a.op('phx')
    a.op('jsr', 'abs', 'h_find')
    a.op('bcc', 'rel', 'hit_nf')
    a.op('lda', 'long,x', T + 2)
    a.op('plx')
    a.op('bit', '#', F_SURE)
    a.op('beq', 'rel', 'hit_orig')
    a.op('jml', 'long', 0x84E5E0)              # SEC; RTS = hit
    a.label('hit_nf')
    a.op('plx')
    a.label('hit_orig')
    a.op('lda', 'long', 0x7ECCE6)
    a.op('jml', 'long', SITE_HIT[2])
    # fx_block replaces LDA $7ECCE6 at $84:E5ED (Pavise).  Defend procs with F_BLOCK stop the hit.
    a.label('fx_block')
    a.op('lda', 'long', 0x7ECCE6)
    a.op('bit', '#', 0x10)
    a.op('bne', 'rel', 'blk_orig')
    a.op('lda', '#', F_BLOCK)
    a.op('jsr', 'abs', 'd_roll')
    a.op('bcc', 'rel', 'blk_orig')
    a.op('jml', 'long', 0x84E61D)              # damage 0; CLC; RTS (as after Pavise)
    a.label('blk_orig')
    a.op('lda', 'long', 0x7ECCE6)
    a.op('jml', 'long', SITE_BLOCK[2])
    # fx_heal replaces LDA $7ECCDC at $84:EEFF (Sol).  Attack procs with F_HEAL heal like Sol.
    a.label('fx_heal')
    a.op('lda', 'long', 0x7ECCDC)
    a.op('cmp', '#', 30)
    a.op('bcc', 'rel', 'heal_orig')
    a.op('phx')
    a.op('jsr', 'abs', 'h_find')
    a.op('bcc', 'rel', 'heal_nf')
    a.op('lda', 'long,x', T + 2)
    a.op('plx')
    a.op('bit', '#', F_HEAL)
    a.op('beq', 'rel', 'heal_orig')
    a.op('jml', 'long', 0x84EF08)              # heal the striker by the damage dealt
    a.label('heal_nf')
    a.op('plx')
    a.label('heal_orig')
    a.op('lda', 'long', 0x7ECCDC)
    a.op('jml', 'long', SITE_HEAL[2])


def _damage(a, T):
    """fx_dmg replaces the damage routine at $84:E6C4.  X = striker, Y = target,
    $0574 = extra damage so far (weapon bonus, crits).  Returns $0574 = damage (0-255)."""
    a.label('fx_dmg')
    a.op('lda', 'abs,x', 0x003A)
    a.op('clc')
    a.op('adc', 'abs', 0x0574)
    a.op('sta', 'abs', V_DMG)
    a.op('stx', 'abs', V_ATK)
    a.op('sty', 'abs', V_DEF)
    a.op('stz', 'abs', V_AFL)
    a.op('lda', 'long', 0x7ECCDC)
    a.op('cmp', '#', 30)
    a.op('bcc', 'rel', 'dm_nofx')
    a.op('jsr', 'abs', 'h_find')
    a.op('bcc', 'rel', 'dm_nofx')
    a.op('stx', 'abs', V_AENT)
    a.op('lda', 'long,x', T + 2)
    a.op('sta', 'abs', V_AFL)
    a.label('dm_nofx')
    _save(a)
    # + power stat x power %
    a.op('lda', 'abs', V_AFL)
    a.op('bit', '#', F_ADD)
    a.op('beq', 'rel', 'dm_s1')
    a.op('ldy', 'abs', V_ATK)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('ldx', 'abs', V_AENT)
    a.op('lda', 'long,x', T + 8)
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'h_stat')
    a.op('pha')
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('pla')
    a.op('jsr', 'abs', 'h_pct')
    a.op('clc')
    a.op('adc', 'abs', V_DMG)
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s1')
    # + (max HP - HP) x power %
    a.op('lda', 'abs', V_AFL)
    a.op('bit', '#', F_VENG)
    a.op('beq', 'rel', 'dm_s2')
    a.op('ldy', 'abs', V_ATK)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('jsl', 'long', GET_MHP)
    a.op('sta', 'abs', V_TMP2)
    a.op('jsl', 'long', GET_HP)
    a.op('eor', '#', 0xFFFF)
    a.op('sec')
    a.op('adc', 'abs', V_TMP2)
    a.op('bpl', 'rel', 'dm_lost')
    a.op('lda', '#', 0)
    a.label('dm_lost')
    a.op('ldx', 'abs', V_AENT)
    a.op('pha')
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('pla')
    a.op('jsr', 'abs', 'h_pct')
    a.op('clc')
    a.op('adc', 'abs', V_DMG)
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s2')
    # minus defence, unless Luna or a piercing skill
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', 'long', 0x7ECCDC)
    a.op('cmp', '#', 0x14)
    a.op('beq', 'rel', 'dm_s3')
    a.op('lda', 'abs', V_AFL)
    a.op('bit', '#', F_PIERCE)
    a.op('bne', 'rel', 'dm_s3')
    a.op('lda', 'abs', V_DMG)
    a.op('sec')
    a.op('sbc', 'abs,y', 0x003C)
    a.op('sec')
    a.op('sbc', 'abs,y', 0x003E)
    a.op('cmp', '#', 1)
    a.op('bpl', 'rel', 'dm_min')
    a.op('lda', '#', 1)
    a.label('dm_min')
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s3')
    # x power %
    a.op('lda', 'abs', V_AFL)
    a.op('bit', '#', F_MULT)
    a.op('beq', 'rel', 'dm_s4')
    a.op('ldx', 'abs', V_AENT)
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('lda', 'abs', V_DMG)
    a.op('jsr', 'abs', 'h_pct')
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s4')
    a.op('lda', 'abs', V_AFL)
    a.op('bit', '#', F_LETHAL)
    a.op('beq', 'rel', 'dm_s5')
    a.op('lda', '#', 255)
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s5')
    # the target's defend skills
    a.op('lda', 'long', 0x7ECCE6)
    a.op('bit', '#', 0x10)
    a.op('bne', 'far', 'dm_done')
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', '#', F_REDUCE)
    a.op('jsr', 'abs', 'd_roll')
    a.op('bcc', 'rel', 'dm_s6')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('lda', 'abs', V_DMG)
    a.op('jsr', 'abs', 'h_pct')
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s6')
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('jsl', 'long', GET_HP)
    a.op('sta', 'abs', V_HP)
    a.op('cmp', '#', 2)
    a.op('bcc', 'rel', 'dm_s7')
    a.op('lda', 'abs', V_DMG)
    a.op('cmp', 'abs', V_HP)
    a.op('bcc', 'rel', 'dm_s7')
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', '#', F_PRAY)
    a.op('jsr', 'abs', 'd_roll')
    a.op('bcc', 'rel', 'dm_s7')
    a.op('lda', 'abs', V_HP)
    a.op('dec')
    a.op('sta', 'abs', V_DMG)
    a.label('dm_s7')
    # Counter: a melee hit is returned to the attacker (who keeps at least 1 HP)
    a.op('lda', 'abs', 0xCCDE)
    a.op('and', '#', 0x20)
    a.op('bne', 'far', 'dm_done')
    a.op('lda', 'abs', V_DMG)
    a.op('beq', 'far', 'dm_done')
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('lda', '#', F_COUNTER)
    a.op('jsr', 'abs', 'd_roll')
    a.op('bcc', 'far', 'dm_done')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('lda', 'abs', V_DMG)
    a.op('jsr', 'abs', 'h_pct')
    a.op('sta', 'abs', V_TMP2)
    a.op('ldy', 'abs', V_ATK)
    a.op('lda', 'abs,y', 0x0006)
    a.op('sta', 'abs', 0x056F)
    a.op('jsl', 'long', GET_HP)
    a.op('dec')
    a.op('bmi', 'far', 'dm_done')
    a.op('cmp', 'abs', V_TMP2)
    a.op('bcs', 'rel', 'dm_cnt')
    a.op('sta', 'abs', V_TMP2)
    a.label('dm_cnt')
    a.op('lda', 'abs', V_TMP2)
    a.op('beq', 'far', 'dm_done')
    a.op('lda', 'abs', 0x0574)
    a.op('pha')
    a.op('lda', 'abs', V_TMP2)
    a.op('sta', 'abs', 0x0574)
    a.op('ldx', 'abs', V_DEF)
    a.op('lda', 'abs,x', 0x0008)
    a.op('jsl', 'long', 0x84A8C7)              # take HP from the attacker
    a.op('pla')
    a.op('sta', 'abs', 0x0574)
    a.label('dm_done')
    _restore(a)
    a.op('lda', 'abs', V_DMG)
    a.op('cmp', '#', 256)
    a.op('bcc', 'rel', 'dm_cap')
    a.op('lda', '#', 255)
    a.label('dm_cap')
    a.op('and', '#', 0xFF)
    a.op('sta', 'abs', 0x0574)
    a.op('ldx', 'abs', V_ATK)
    a.op('ldy', 'abs', V_DEF)
    a.op('jml', 'long', SITE_DMG[2])           # RTS


def _kill(a, T):
    """fx_kill replaces LDX $0772; LDA $46EB,X at $84:DD6B (after a battle, X = acting unit's slot).
    If the attacker survived and the target fell: Galeforce / Lifetaker."""
    a.label('fx_kill')
    a.op('ldx', 'abs', 0x0772)
    a.op('phx')
    a.op('php')
    a.op('rep', '#8', 0x30)
    a.op('phb')
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 0x7E)
    a.op('pha')
    a.op('plb')
    a.op('rep', '#8', 0x20)
    a.op('stx', 'abs', K_SLOT)
    a.op('lda', 'abs', 0x0574)
    a.op('pha')
    _save(a)
    a.op('lda', 'abs', 0x4EAA)                 # $10 = a unit fell, $20 = to the attacker's blow
    a.op('and', '#', 0x30)
    a.op('cmp', '#', 0x30)
    a.op('bne', 'far', 'k_out')
    a.op('lda', 'abs', ATK + 6)
    a.op('beq', 'far', 'k_out')
    a.op('ldx', '#', 0)
    a.label('k_loop')
    a.op('stx', 'abs', V_ENT)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('beq', 'far', 'k_out')
    a.op('lda', 'long,x', T + 1)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', K_KILL)
    a.op('bne', 'far', 'k_next')
    a.op('lda', 'abs', ATK + 6)
    a.op('sta', 'abs', 0x056F)
    a.op('lda', 'long,x', T)
    a.op('and', '#', 0xFF)
    a.op('jsr', 'abs', 'h_has')
    a.op('bcc', 'far', 'k_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('jsr', 'abs', 'h_rate')
    a.op('jsl', 'long', RNG)
    a.op('bcs', 'far', 'k_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T + 2)
    a.op('bit', '#', F_GALE)
    a.op('beq', 'rel', 'k_life')
    a.op('ldx', 'abs', K_SLOT)                 # player units only
    a.op('lda', 'long,x', 0x7E477B)
    a.op('bne', 'rel', 'k_life0')
    a.op('txa')
    a.op('ora', '#', 0x8000)
    a.op('sta', 'abs', K_PEND)
    a.label('k_life0')
    a.op('ldx', 'abs', V_ENT)
    a.op('lda', 'long,x', T + 2)
    a.label('k_life')
    a.op('bit', '#', F_LIFE)
    a.op('beq', 'far', 'k_next')
    a.op('lda', 'abs', ATK + 6)
    a.op('sta', 'abs', 0x056F)
    a.op('jsl', 'long', GET_MHP)
    a.op('pha')
    a.op('lda', 'long,x', T + 9)
    a.op('and', '#', 0xFF)
    a.op('tax')
    a.op('pla')
    a.op('jsr', 'abs', 'h_pct')
    a.op('beq', 'far', 'k_next')
    a.op('sta', 'abs', 0x0574)
    a.op('jsl', 'long', 0x84A927)              # heal (as Sol does)
    a.label('k_next')
    a.op('ldx', 'abs', V_ENT)
    a.op('txa')
    a.op('clc')
    a.op('adc', '#', ENT)
    a.op('tax')
    a.op('brl', 'brl', 'k_loop')
    a.label('k_out')
    _restore(a)
    a.op('pla')
    a.op('sta', 'abs', 0x0574)
    a.op('plb')
    a.op('plp')
    a.op('plx')
    a.op('lda', 'abs,x', 0x46EB)               # (DB = $7E here) original LDA $46EB,X
    a.op('jml', 'long', SITE_KILL[2])

    # fx_done replaces LDA $7E489B,X at $84:CB24 (a unit finishes acting): Galeforce refreshes it
    a.label('fx_done')
    a.op('lda', 'long', 0x7E0000 | K_PEND)
    a.op('bpl', 'rel', 'dn_orig')
    a.op('and', '#', 0x7FFF)
    a.op('sta', 'long', 0x7E0000 | K_TMP)
    a.op('txa')
    a.op('cmp', 'long', 0x7E0000 | K_TMP)
    a.op('bne', 'rel', 'dn_orig')
    a.op('lda', '#', 0)
    a.op('sta', 'long', 0x7E0000 | K_PEND)
    a.op('lda', 'long,x', 0x7E489B)
    a.op('and', '#', 0xFFA7)                   # clear acted / moved / done
    a.op('ora', '#', 0x0080)
    a.op('jml', 'long', 0x84CB33)              # STA $7E489B,X ...
    a.label('dn_orig')
    a.op('lda', 'long,x', 0x7E489B)
    a.op('jml', 'long', SITE_DONE[2])


def build_effects(region, effects, space):
    tab = bytearray()
    for sid, kind, flags, rs, rp, rf, anim, ps, pp, which in effects:
        tab += bytes([sid, kind, flags & 0xFF, flags >> 8, rs, rp, rf, anim, ps, pp, which])
    tab += bytes(ENT)
    T = region.table('proc', bytes(tab))
    a = Asm(region.cur)
    _helpers(a, T)
    _select(a, T)
    _defend(a, T)
    _hit_block_heal(a, T)
    _damage(a, T)
    kill = any(e[1] == K_KILL for e in effects)
    if kill:
        _kill(a, T)
    code = a.assemble()
    region.put(code)
    L = a.labels
    rom = region.rom
    # bank $84 trampoline for proc selection: JSR $E0DE, then (if no FE4 skill fired) new attack procs
    fo, snes = space.alloc(0x840000, 64)
    t = Asm(snes)
    t.op('jsr', 'abs', 0xE0DE)
    t.op('lda', 'long', 0x7ECCDC)
    t.op('bne', 'rel', 'out')
    t.op('ldx', 'abs', 0xCCD8)
    t.op('ldy', 'abs', 0xCCDA)
    t.op('lda', 'abs,x', 0x0000)
    t.op('bmi', 'rel', 'out')
    t.op('lda', 'abs,x', 0x0022)
    t.op('cmp', '#', 8)
    t.op('beq', 'rel', 'out')
    t.op('jsr', 'abs', 0xDF3B)                 # can strike
    t.op('bcc', 'rel', 'out')
    t.op('jsr', 'abs', 0xE4D7)                 # in range
    t.op('bcc', 'rel', 'out')
    t.op('jsl', 'long', L['fx_select'])
    t.label('out')
    t.op('rts')
    tc = t.assemble()
    rom[fo:fo + len(tc)] = tc
    assert rom[SITE_SELECT:SITE_SELECT + 3] == bytes.fromhex('20dee0')
    rom[SITE_SELECT + 1:SITE_SELECT + 3] = (snes & 0xFFFF).to_bytes(2, 'little')
    _jml(rom, SITE_HIT, L['fx_hit'])
    _jml(rom, SITE_BLOCK, L['fx_block'])
    _jml(rom, SITE_DMG, L['fx_dmg'])
    _jml(rom, SITE_HEAL, L['fx_heal'])
    if kill:
        _jml(rom, SITE_KILL, L['fx_kill'])
        _jml(rom, SITE_DONE, L['fx_done'])


# ---------------------------------------------------------------- extra skill lists
SITE_HAS = (0x07A19D, bytes.fromhex('8b084bab'), 0x87A1A1)       # PHB PHP PHK PLB (HasSkill)
GET_UNIT, GET_CLASS = 0x84A333, 0x84A02D


def build_extra(region, personal, classes):
    """personal: [(unit index, skill id)], classes: [(class id, skill id)].  HasSkill also answers
    yes for these (skills 30 and up), so new skills need no personal/class bit."""
    tab = bytearray()
    for u, sid in personal:
        tab += bytes([u & 0xFF, u >> 8, sid])
    tab += b'\xff\xff\xff'
    C = len(tab)
    for c, sid in classes:
        tab += bytes([c, sid])
    tab += b'\xff\xff'
    P = region.table('extra', bytes(tab))
    C += P
    a = Asm(region.cur)
    a.label('fx_has')
    a.op('cmp', '#', 30)
    a.op('bcs', 'rel', 'ext')
    a.label('van')
    a.op('phb')
    a.op('php')
    a.op('pha')
    a.op('sep', '#8', 0x20)
    a.op('lda', '#', 0x87)
    a.op('pha')
    a.op('plb')
    a.op('rep', '#8', 0x20)
    a.op('pla')
    a.op('jml', 'long', SITE_HAS[2])
    a.label('ext')
    a.op('pha')                                # id
    a.op('phk')
    a.op('pea', 'abs', ('ret', -1))
    a.op('lda', 'sr', 4)
    a.op('bra', 'rel', 'van')
    a.label('ret')
    a.op('pla')
    a.op('bcs', 'rel', 'yes')
    a.op('phx')
    a.op('phy')
    a.op('pha')                                # id at 1,S
    a.op('jsl', 'long', GET_UNIT)
    a.op('tay')
    a.op('ldx', '#', 0)
    a.label('pl')
    a.op('lda', 'long,x', P)
    a.op('cmp', '#', 0xFFFF)
    a.op('beq', 'rel', 'cls')
    a.op('tya')
    a.op('cmp', 'long,x', P)
    a.op('bne', 'rel', 'pn')
    a.op('lda', 'long,x', P + 2)
    a.op('and', '#', 0xFF)
    a.op('cmp', 'sr', 1)
    a.op('beq', 'rel', 'found')
    a.label('pn')
    a.op('inx')
    a.op('inx')
    a.op('inx')
    a.op('bra', 'rel', 'pl')
    a.label('cls')
    a.op('jsl', 'long', GET_CLASS)
    a.op('and', '#', 0xFF)
    a.op('pha')                                # class at 1,S, id at 3,S
    a.op('ldx', '#', 0)
    a.label('cl')
    a.op('lda', 'long,x', C)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', 0xFF)
    a.op('beq', 'rel', 'notf2')
    a.op('cmp', 'sr', 1)
    a.op('bne', 'rel', 'cn')
    a.op('lda', 'long,x', C + 1)
    a.op('and', '#', 0xFF)
    a.op('cmp', 'sr', 3)
    a.op('beq', 'rel', 'found2')
    a.label('cn')
    a.op('inx')
    a.op('inx')
    a.op('bra', 'rel', 'cl')
    a.label('notf2')
    a.op('pla')
    a.op('pla')
    a.op('ply')
    a.op('plx')
    a.op('clc')
    a.op('rtl')
    a.label('found2')
    a.op('pla')
    a.label('found')
    a.op('pla')
    a.op('ply')
    a.op('plx')
    a.label('yes')
    a.op('sec')
    a.op('rtl')
    code = a.assemble()
    region.put(code)
    _jml(region.rom, SITE_HAS, a.labels['fx_has'])


def read_extra(rom):
    """{skill id: ([unit indices], [class ids])}"""
    t = table_addr(rom, 'extra')
    out = {}
    if not t:
        return out
    while rom[t:t + 3] != b'\xff\xff\xff':
        out.setdefault(rom[t + 2], ([], []))[0].append(rom[t] | rom[t + 1] << 8)
        t += 3
    t += 3
    while rom[t] != 0xFF:
        out.setdefault(rom[t + 1], ([], []))[1].append(rom[t])
        t += 2
    return out


def build(rom, combat, effects, space=None, extra=None):
    """Writes the engine code; returns the Region (for the Skills menu code after it)."""
    region = region_for(rom)
    if extra and (extra[0] or extra[1]):
        build_extra(region, *extra)
    if combat:
        build_combat(region, combat)
    if effects:
        build_effects(region, effects, space)
    return region
