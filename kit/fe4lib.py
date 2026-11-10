"""FE4 (Genealogy of the Holy War) data library — Project Naga 8 MB ExHiROM.

Every offset here is a *headerless* file offset (the 512-byte copier header,
if present, is stripped on load and restored on save).  Offsets were found
and verified against the running game; see ROM_MAP.md for the evidence.
"""
import hashlib

# --------------------------------------------------------------------------
# ROM I/O
# --------------------------------------------------------------------------
EXPECTED_SHA1 = '2b6eb74646a527ba293b0e004db3e0134a28dc6c'  # headerless Naga ROM this map was built from
HEADERS = (0x00FFC0, 0x40FFC0)  # ExHiROM keeps a header copy in both halves


def load_rom(path):
    data = open(path, 'rb').read()
    copier = b''
    if len(data) % 0x8000 == 512:
        copier, data = data[:512], data[512:]
    return copier, bytearray(data)


def fix_checksum(rom):
    for h in HEADERS:  # complement/checksum pair always sums to 0x1FE per header
        rom[h + 0x1C:h + 0x20] = b'\xff\xff\x00\x00'
    s = sum(rom) & 0xFFFF
    for h in HEADERS:
        rom[h + 0x1C:h + 0x20] = ((s ^ 0xFFFF).to_bytes(2, 'little') + s.to_bytes(2, 'little'))
    return s


def save_rom(path, copier, rom):
    fix_checksum(rom)
    open(path, 'wb').write(bytes(copier) + bytes(rom))


def sha1(rom):
    return hashlib.sha1(bytes(rom)).hexdigest()


# --------------------------------------------------------------------------
# Text (Naga name tables use this single-byte encoding; 0x01 terminates)
# --------------------------------------------------------------------------
def decode(b):
    out = ''
    for x in b:
        if x in (0x00, 0x01):
            break
        if 0x10 <= x < 0x2A:
            out += chr(x - 0x10 + 65)
        elif 0x2A <= x < 0x44:
            out += chr(x - 0x2A + 97)
        elif x == 0xBF:
            out += ' '
        elif x == 0x48:
            out += "'"
        else:
            out += '{%02X}' % x
    return out


def read_names(rom, base, count, stride=16, skip=0):
    return [decode(rom[base + i * stride + skip: base + (i + 1) * stride]) for i in range(count)]


# --------------------------------------------------------------------------
# Lookup tables
# --------------------------------------------------------------------------
STATS = ['str', 'mag', 'skl', 'spd', 'def', 'res', 'lck']
CLASS_STATS = ['str', 'mag', 'skl', 'spd', 'def', 'res']
WEAPON_TYPES = ['sword', 'lance', 'axe', 'bow', 'staff', 'fire', 'thunder', 'wind', 'light', 'dark']
RANKS = {0: 'A', 1: 'B', 2: 'C', 3: '-', 255: '*'}
RANKS_INV = {v: k for k, v in RANKS.items()}

# Holy blood: 13 two-bit slots packed LSB-first into 4 bytes (0 none, 1 minor, 2 major)
BLOODS = ['Baldur', 'Naga', 'Dain', 'Nova', 'Odo', 'Ullur', 'Neir', 'Fala',
          'Tordo', 'Forseti', 'Bragi', 'Hezul', 'Loptyr']

# Personal skill bits (24-bit field).  Verified in-game via the Skills menu.
SKILL_BITS = {0: 'Wrath', 1: 'Pursuit', 2: 'Adept', 4: 'Charm', 6: 'Nihil', 7: 'Miracle',
              8: 'Critical', 9: 'Vantage', 10: 'Accost', 11: 'Astra', 12: 'Luna', 13: 'Sol',
              16: 'Renewal', 17: 'Paragon', 20: 'Bargain'}
SKILL_BITS_INV = {v.lower(): k for k, v in SKILL_BITS.items()}


def blood_decode(b4):
    v = int.from_bytes(b4, 'little')
    parts = []
    for i, n in enumerate(BLOODS):
        lvl = (v >> (2 * i)) & 3
        if lvl:
            parts.append(n + (':major' if lvl == 2 else ':minor' if lvl == 1 else ':%d' % lvl))
    extra = v >> 26
    if extra:
        parts.append('raw_hi:%d' % extra)
    return ';'.join(parts)


def blood_encode(s):
    v = 0
    for part in filter(None, (p.strip() for p in s.split(';'))):
        name, _, lvl = part.partition(':')
        if name == 'raw_hi':
            v |= int(lvl) << 26
            continue
        idx = [b.lower() for b in BLOODS].index(name.lower())
        lv = {'major': 2, 'minor': 1}.get(lvl.lower()) if not lvl.isdigit() else int(lvl)
        v |= lv << (2 * idx)
    return v.to_bytes(4, 'little')


# Skill bit -> name maps for the three places a skill can come from.  They follow
# the game's skill tables (fe4skills.py sets them from the ROM or skills.csv).
SKILL_MAPS = {
    'personal': dict(SKILL_BITS),
    'class': {0: 'Canto', 1: 'Pavise', 2: 'Wrath', 3: 'Pursuit', 4: 'Adept', 5: 'Steal', 7: 'Dance',
              9: 'Troubadour?', 10: 'Lord?', 11: 'Charm', 12: 'Critical'},
    'item': {0: 'Steal', 3: 'Miracle', 4: 'Critical', 5: 'Renewal', 6: 'Paragon', 8: 'Recover',
             9: 'Bargain', 10: 'Return', 11: 'Pursuit', 12: 'Canto'},
}
_SKILL_WIDTH = {'personal': 24, 'class': 16, 'item': 16}


def skillset_decode(src, b):
    v = int.from_bytes(b, 'little')
    m = SKILL_MAPS[src]
    return ';'.join(m.get(i, 'bit%d' % i) for i in range(_SKILL_WIDTH[src]) if v >> i & 1)


def skillset_encode(src, s):
    inv = {}
    for bit, name in SKILL_MAPS[src].items():
        inv.setdefault(name.lower(), bit)
    v = 0
    for part in filter(None, (p.strip() for p in s.split(';'))):
        p = part.lower()
        if p.startswith('bit') and p[3:].isdigit():
            v |= 1 << int(p[3:])
        elif p in inv:
            v |= 1 << inv[p]
        else:
            where = {'personal': 'a unit', 'class': 'a class', 'item': 'an item'}[src]
            extra = {'personal': " or name the unit in that skill's units column",
                     'class': " or name the class in that skill's classes column", 'item': ''}[src]
            raise ValueError(f'{part} cannot be given to {where}: give it a {src}_bit in skills.csv{extra}')
    return v.to_bytes(_SKILL_WIDTH[src] // 8, 'little')


def skills_decode(b3):
    return skillset_decode('personal', b3)


def skills_encode(s):
    return skillset_encode('personal', s)


# --------------------------------------------------------------------------
# Table locations (headerless offsets)
# --------------------------------------------------------------------------
CHAR_NAMES = 0x500000       # 16-byte slots by name_id; +2 = VWF tile pointer, name text at +8
CLASS_NAMES = 0x506200      # 16-byte slots; class 10 (female Paladin) has no entry
ITEM_NAMES = 0x506700       # 16-byte slots; one name per *group* of 3 broken items
SKILL_NAMES = 0x507A00

CLASSES = 0x038FC5          # 72 x 31 bytes
CLASS_COUNT = 72
ITEMS = 0x03EAE4            # 106 x 19 bytes (weapons + staves, IDs 0-105)
ITEM_COUNT = 106
RINGS = 0x03F2C2            # 16 x 10 bytes (IDs 106-121)
RING_COUNT = 16
INSTANCES = 0x03F488        # 141 bytes: physical item instance -> item type ID
INSTANCE_COUNT = 141

BROKEN_NAME_IDX = {25, 35, 42, 49, 77, 93}  # each expands to 3 IDs (rank A/B/C)


def item_names(rom):
    raw = read_names(rom, ITEM_NAMES, 110)
    out = []
    for i, n in enumerate(raw[:94]):
        if i in BROKEN_NAME_IDX:
            out += [n + ' (A)', n + ' (B)', n + ' (C)']
        else:
            out.append(n)
    out += raw[94:110]  # rings, IDs 106-121
    return out


def class_names(rom):
    raw = read_names(rom, CLASS_NAMES, 71)
    return raw[:10] + ['Paladin (F)'] + raw[10:]


# --------------------------------------------------------------------------
# Field layouts: (column, offset, kind)
#   kind: 'u8' | 'u16' | 'rank' | ('raw', n) | 'blood' | 'skills'
# --------------------------------------------------------------------------

CLASS_FIELDS = [
    ('unk0', 0, 'u8'), ('base_hp', 1, 'u8'),
    *[('base_' + s, 2 + i, 'u8') for i, s in enumerate(CLASS_STATS)],
    ('g_hp', 8, 'u8'), *[('g_' + s, 9 + i, 'u8') for i, s in enumerate(CLASS_STATS)],
    *[('rank_' + w, 15 + i, 'rank') for i, w in enumerate(WEAPON_TYPES)],
    ('move', 25, 'u8'), ('group', 26, 'u8'), ('flier', 27, 'u8'),
    ('skills', 28, 'cskills'), ('unk30', 30, 'u8'),
]
CLASS_SIZE = 31

ITEM_FIELDS = [
    ('id', 0, 'u8'), ('category', 1, 'u8'), ('uses', 2, 'u8'), ('price', 3, 'u16'),
    ('blood_lock', 5, 'u8'), ('staff_effect', 6, 'u8'), ('rank', 7, 'rank'),
    ('skills', 8, 'iskills'), ('weapon_type', 10, 'u8'),
    ('mt', 11, 'u8'), ('hit', 12, 'u8'), ('wt', 13, 'u8'),
    ('min_range', 14, 'u8'), ('max_range', 15, 'u8'),
    ('effective', 16, 'u8'), ('special', 17, 'u8'), ('special_arg', 18, 'u8'),
]
ITEM_SIZE = 19

RING_FIELDS = [
    ('id', 0, 'u8'), ('category', 1, 'u8'), ('uses', 2, 'u8'), ('price', 3, 'u16'),
    ('stat_bonus', 5, 'u8'), ('unk6', 6, 'u8'), ('rank', 7, 'rank'), ('skills', 8, 'iskills'),
]
RING_SIZE = 10


def get_field(rec, off, kind):
    if kind == 'u8':
        return rec[off]
    if kind == 'u16':
        return rec[off] | rec[off + 1] << 8
    if kind == 'rank':
        return RANKS.get(rec[off], str(rec[off]))
    if kind == 'blood':
        return blood_decode(rec[off:off + 4])
    if kind == 'skills':
        return skills_decode(rec[off:off + 3])
    if kind in ('cskills', 'iskills'):
        return skillset_decode('class' if kind == 'cskills' else 'item', rec[off:off + 2])
    if kind == 'heir':
        return 'father' if rec[off] else 'mother'
    raise ValueError(kind)


def put_field(rec, off, kind, val):
    val = str(val).strip()
    if kind == 'u8':
        n = int(val, 0)
        if not 0 <= n <= 255:
            raise ValueError('value %s out of range 0-255' % val)
        rec[off] = n
    elif kind == 'u16':
        n = int(val, 0)
        if not 0 <= n <= 0xFFFF:
            raise ValueError('value %s out of range 0-65535' % val)
        rec[off:off + 2] = n.to_bytes(2, 'little')
    elif kind == 'rank':
        rec[off] = RANKS_INV[val.upper()] if val.upper() in RANKS_INV else int(val, 0)
    elif kind == 'blood':
        rec[off:off + 4] = blood_encode(val)
    elif kind == 'skills':
        rec[off:off + 3] = skills_encode(val)
    elif kind in ('cskills', 'iskills'):
        rec[off:off + 2] = skillset_encode('class' if kind == 'cskills' else 'item', val)
    elif kind == 'heir':
        v = val.lower()
        if v in ('father', 'f', '1'):
            rec[off] = 1
        elif v in ('mother', 'm', '0'):
            rec[off] = 0
        else:
            raise ValueError('heir must be father or mother (who passes on major blood and items)')
    else:
        raise ValueError(kind)



# --------------------------------------------------------------------------
# Unit table: 569 records of 4 types, located through the bank $83
# pointer table (ID n -> file 0x38000 + UNIT_PTRS_OFF + word[n-1]).
# --------------------------------------------------------------------------
UNIT_DIR = 0x038002          # word: offset of the unit pointer table inside bank $83
UNIT_COUNT = 569
UNIT_SIZES = {0: 38, 1: 12, 2: 38, 3: 13}
UNIT_KIND = {0: 'playable', 1: 'child', 2: 'npc', 3: 'generic'}


UNIT_BANK = 0x30000          # file offset of bank $83 ($83:8000 = file 0x38000)


def _w16(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def unit_count(rom):
    """Number of unit IDs: the first table word is also the table size in bytes
    (the game's own bound check at $84:8491 relies on that)."""
    base = _w16(rom, UNIT_DIR)
    return _w16(rom, 0x38000 + base) // 2


def unit_addrs(rom):
    base = _w16(rom, UNIT_DIR)
    out = []
    for i in range(unit_count(rom)):
        p = _w16(rom, 0x38000 + base + 2 * i)
        out.append(UNIT_BANK + _rec16(base, p))
    return out


def _rec16(base, p):
    # $84:849D: CLC; ADC base; ADC #$8000 -- the carry of the first add is kept
    s = p + base
    return ((s & 0xFFFF) + 0x8000 + (s >> 16)) & 0xFFFF


def _ptr_for(base, rec16):
    for p in ((rec16 - 0x8000 - base) & 0xFFFF, (rec16 - 0x8001 - base) & 0xFFFF):
        if _rec16(base, p) == rec16:
            return p
    return None


GAME_UNITS = 569             # unit records in FE4
RESERVED_IDS = 768           # ids 570-768 name dialogue speakers (portrait table); new units start after
SAVE_ID_BITS = 0x11EFC4      # $91:EFC4: bit width of the unit id in the save format
LOOKUP_CMP = 0x048491        # CMP $838000,X in the unit lookup ($84:8481): index bound check


def first_new_id(rom):
    n = unit_count(rom)
    return RESERVED_IDS + 1 if n == GAME_UNITS else n + 1


def _reserved(rom, i):
    """True for the padding ids 570-768 of a table the kit extended past them."""
    return GAME_UNITS < i <= RESERVED_IDS and unit_count(rom) > RESERVED_IDS


def add_units(rom, types, space, reserve=True):
    """Append unit records of the given types (3 = class-based generic, 1 = child);
    returns their file offsets.  New records start zeroed except for the type byte.

    Ids 570-768 are what the game's scripts use for dialogue portraits of people who are not
    units, so the first new unit gets id 769: the table is padded with entries the unit
    lookup treats as missing (a small check after its bound test).
    The pointer table is rebuilt in bank $83's free tail as
    [table][copy of unit 1][new records], so its first word (unit 1's pointer)
    still equals the table size that the game uses as the ID bound."""
    old = unit_addrs(rom)
    n = len(types)
    pad = max(0, RESERVED_IDS - len(old)) if reserve else 0
    cnt = len(old) + pad + n
    u1 = rom[old[0]:old[0] + UNIT_SIZES[rom[old[0]]]]
    size = 2 * cnt + len(u1) + sum(UNIT_SIZES[t] for t in types)
    fo, sn = space.alloc(0x830000, size + 1)
    base = (sn & 0xFFFF) - 0x8000
    recs16 = [r - UNIT_BANK for r in old[1:]]
    if any(_ptr_for(base, r) is None for r in recs16):   # one-off carry edge case: shift by a byte
        fo, base = fo + 1, base + 1
    u1a = fo + 2 * cnt
    recs = [u1a] + old[1:] + [u1a] * pad
    new = []
    a = u1a + len(u1)
    rom[u1a:a] = u1
    for t in types:
        new.append(a)
        rom[a:a + UNIT_SIZES[t]] = bytes([t]) + bytes(UNIT_SIZES[t] - 1)
        a += UNIT_SIZES[t]
    for i, r in enumerate(recs + new):
        p = _ptr_for(base, r - UNIT_BANK)
        rom[fo + 2 * i:fo + 2 * i + 2] = p.to_bytes(2, 'little')
    rom[UNIT_DIR:UNIT_DIR + 2] = base.to_bytes(2, 'little')
    if pad:
        _install_reserved_check(rom, space)
    if 1 in types:
        _install_name_by_record(rom, space)
    if rom[SAVE_ID_BITS] == 9:          # saves keep unit ids in 9 bits (up to 511): make it 10
        rom[SAVE_ID_BITS] = 10
    assert unit_count(rom) == cnt and unit_addrs(rom)[cnt - n:] == new
    return new


def _install_reserved_check(rom, space):
    """The unit lookup answers 'no such unit' for the reserved ids, as it did before."""
    if rom[LOOKUP_CMP] != 0xDF:
        return
    from asm65816 import Asm
    fo, sn = space.alloc(0x840000, 24)
    a = Asm(sn)
    a.op('cmp', 'long,x', 0x838000)          # what the game did: past the table -> carry set
    a.op('bcs', 'rel', 'done')
    a.op('cmp', '#', 2 * GAME_UNITS)
    a.op('bcc', 'rel', 'ok')
    a.op('cmp', '#', 2 * RESERVED_IDS)
    a.op('bcs', 'rel', 'ok')
    a.op('sec')
    a.op('rtl')
    a.label('ok')
    a.op('clc')
    a.label('done')
    a.op('rtl')
    code = a.assemble()
    rom[fo:fo + len(code)] = code
    rom[LOOKUP_CMP:LOOKUP_CMP + 4] = bytes([0x22]) + sn.to_bytes(3, 'little')


NAME_BY_ID = 0x0484FB        # $84:84F6 (name of a unit id, e.g. battle screen): DEC A; BMI; ASL A


def _install_name_by_record(rom, space):
    """FE4 draws some names (the battle screen, a child's parents) from name slot id - 1.
    New units' ids are past the character slots, so for them use the record's name_id."""
    if rom[NAME_BY_ID:NAME_BY_ID + 4] != bytes.fromhex('3a30200a'):
        return
    from asm65816 import Asm
    fo, sn = space.alloc(0x840000, 64)
    a = Asm(sn)
    a.op('cmp', '#', GAME_UNITS + 1)
    a.op('bcc', 'rel', 'van')
    a.op('phx')
    a.op('jsl', 'long', 0x848481)
    a.op('bcs', 'rel', 'nf')
    a.op('tax')
    a.op('lda', 'long,x', 0x830000)
    a.op('and', '#', 0xFF)
    a.op('cmp', '#', 1)
    a.op('beq', 'rel', 'child')
    a.op('cmp', '#', 3)
    a.op('beq', 'rel', 'gen')
    a.op('lda', 'long,x', 0x83000F)
    a.op('bra', 'rel', 'got')
    a.label('child')
    a.op('lda', 'long,x', 0x830005)
    a.op('bra', 'rel', 'got')
    a.label('gen')
    a.op('lda', 'long,x', 0x830003)
    a.label('got')
    a.op('plx')
    a.op('asl')
    a.op('rtl')
    a.label('nf')
    a.op('plx')
    a.op('lda', '#', 0)
    a.op('rtl')
    a.label('van')
    a.op('dec')
    a.op('bpl', 'rel', 'ok')
    a.op('lda', '#', 0)
    a.label('ok')
    a.op('asl')
    a.op('rtl')
    code = a.assemble()
    assert len(code) <= 64
    rom[fo:fo + len(code)] = code
    rom[NAME_BY_ID:NAME_BY_ID + 4] = bytes([0x22]) + sn.to_bytes(3, 'little')


def unit_ids(rom):
    """Ids that are real units (skips the reserved speaker ids 570-768 after padding)."""
    n = unit_count(rom)
    return [i for i in range(1, n + 1) if not (n > RESERVED_IDS and GAME_UNITS < i <= RESERVED_IDS)]


def add_generic_units(rom, n, space):
    return add_units(rom, [3] * n, space)


PORTRAIT_OP = 0x048625      # operand of LDA $8B9A88,X at $84:8624: one word per unit (id - 1)
NO_PORTRAIT = 243           # what generic soldiers use


def portrait_table(rom):
    from dis65816 import snes_to_file
    return snes_to_file(rom[PORTRAIT_OP] | rom[PORTRAIT_OP + 1] << 8 | rom[PORTRAIT_OP + 2] << 16)


def portraits(rom, count=None):
    """{id: portrait number} for every unit id and the dialogue speaker ids 570-768;
    ids past the table's end (new units) read as NO_PORTRAIT."""
    fo = portrait_table(rom)
    n = max(count or unit_count(rom), RESERVED_IDS)
    size = _portrait_len(rom)
    return {i: (_w16(rom, fo + 2 * (i - 1)) if i <= size else NO_PORTRAIT) for i in range(1, n + 1)}


def _portrait_len(rom):
    """Entries in the current table: the game's own has 569; a moved one stores its length before it."""
    fo = portrait_table(rom)
    if fo == 0x0B9A88:
        return RESERVED_IDS
    return _w16(rom, fo - 2)


def set_portraits(rom, want, far):
    """want: {unit id: portrait}.  Rewrites the table into free space when it changes or must grow."""
    n = max(unit_count(rom), RESERVED_IDS)
    cur = portraits(rom, n)
    new = dict(cur)
    new.update(want)
    if new == cur and _portrait_len(rom) >= n:
        return 0
    data = n.to_bytes(2, 'little') + b''.join(new[i].to_bytes(2, 'little') for i in range(1, n + 1))
    fo = far.alloc(len(data))
    rom[fo:fo + len(data)] = data
    rom[PORTRAIT_OP:PORTRAIT_OP + 3] = (fo + 2).to_bytes(3, 'little')   # banks $40-$7D: snes == file
    return 1


class FreeSpace:
    """Bump allocator over the empty banks $70:0000-$7D:EFFF (all zero in the clean ROM).

    Dialogue, scenes, maps and name graphics share it, so nothing can land inside
    another block's zero bytes.  Banks $40-$7D map 1:1 to file offsets."""
    START, END = 0x700000, 0x7DD000   # $7D:D000+ holds the kit's code hooks

    def __init__(self):
        self.cur = self.START

    def alloc(self, size, upper_half=False):
        a = self.cur
        while True:
            if upper_half and (a & 0xFFFF) < 0x8000:
                a = (a & 0xFF0000) | 0x8000
            if (a >> 16) != ((a + size - 1) >> 16):
                a = ((a >> 16) + 1) << 16
                continue
            break
        if a + size > self.END:
            raise SystemExit('out of free space in banks $70-$7D')
        self.cur = a + size
        return a


class BankSpace:
    """Hands out the zero-filled tail of a ROM bank, after a 32-byte gap."""
    GUARD = 32

    def __init__(self, rom):
        self.rom = rom
        self.cur = {}

    def alloc(self, bank_snes, size):
        from dis65816 import snes_to_file
        fbase = snes_to_file(bank_snes & 0xFF0000 | 0x8000) & ~0xFFFF
        end = fbase + 0x10000
        if fbase not in self.cur:
            i = end
            while i > fbase and self.rom[i - 1] == 0:
                i -= 1
            self.cur[fbase] = i + self.GUARD
        a = self.cur[fbase]
        if a + size > end - 16:
            raise SystemExit('no free space left in bank $%02X for this data' % (bank_snes >> 16))
        self.cur[fbase] = a + size
        return a, (bank_snes & 0xFF0000) | (a & 0xFFFF)


_name_cache = {}


def unit_name_table(rom):
    """name_id -> display name. Generic names share a VWF tile pointer with a named slot."""
    key = id(rom)
    if key in _name_cache:
        return _name_cache[key]
    names, by_ptr = [], {}
    for i in range(1024):
        a = 0x500000 + 16 * i
        n = decode(rom[a + 8:a + 16])
        p = rom[a + 2] | rom[a + 3] << 8
        names.append((n, p))
        if n and not n.startswith('{') and p not in by_ptr:
            by_ptr[p] = n
    out = [n if n and not n.startswith('{') else by_ptr.get(p, '') for n, p in names]
    _name_cache[key] = out
    return out


# type 0 (playable, fixed stats) and type 2 (named NPC/boss) share this layout
START_FIELDS = [
    ('hp', 1, 'u8'), *[(s, 2 + i, 'u8') for i, s in enumerate(STATS)],
    ('class', 9, 'u8'), ('level', 10, 'u8'), ('authority', 11, 'u8'), ('gold_x1000', 12, 'u8'),
]
PERSONAL_FIELDS = [
    ('char_id', 13, 'u16'), ('name_id', 15, 'u16'), ('slot', 17, 'u8'),
    ('gender', 18, 'u8'), ('unk19', 19, 'u8'),
    ('g_hp', 20, 'u8'), *[('g_' + s, 21 + i, 'u8') for i, s in enumerate(STATS)],
    ('skills', 28, 'skills'), ('holy_blood', 31, 'blood'),
    ('item1', 35, 'u8'), ('item2', 36, 'u8'), ('item3', 37, 'u8'),
]
FIXED_FIELDS = START_FIELDS + PERSONAL_FIELDS
CHILD_FIELDS = [
    ('class', 1, 'u8'), ('level', 2, 'u8'), ('char_id', 3, 'u16'), ('name_id', 5, 'u16'),
    ('slot', 7, 'u8'), ('gender', 8, 'u8'), ('item1', 9, 'u8'), ('item2', 10, 'u8'), ('heir', 11, 'heir'),
]
GENERIC_FIELDS = [
    ('char_id', 1, 'u16'), ('name_id', 3, 'u16'), ('class', 5, 'u8'), ('unk6', 6, 'u8'),
    ('level', 7, 'u8'), ('authority', 8, 'u8'), ('unk9', 9, 'u8'),
    ('item1', 10, 'u8'), ('item2', 11, 'u8'), ('item3', 12, 'u8'),
]
UNIT_FIELDS = {0: FIXED_FIELDS, 1: CHILD_FIELDS, 2: FIXED_FIELDS, 3: GENERIC_FIELDS}


def unit_rows(rom, rtype):
    """(index=char_id, addr, size, label) for every unit record of one type."""
    names = unit_name_table(rom)
    rows = []
    padded = unit_count(rom) > RESERVED_IDS
    for i, a in enumerate(unit_addrs(rom)):
        if rom[a] != rtype or (padded and GAME_UNITS < i + 1 <= RESERVED_IDS):
            continue
        nid_off = {0: 15, 2: 15, 1: 5, 3: 3}[rtype]
        nid = rom[a + nid_off] | rom[a + nid_off + 1] << 8
        rows.append((i + 1, a, UNIT_SIZES[rtype], names[nid] if nid < len(names) else ''))
    return rows


# --------------------------------------------------------------------------
# Deployment lists: directory of word offsets at 0x1C000 ($81:C000), one
# list per event "deploy" command; 8-byte entries ended by char_id 0xFFFF.
# --------------------------------------------------------------------------
DEPLOY_DIR = 0x01C000
DEPLOY_LISTS = 58
DEPLOY_HARD_END = 0x01EBBC   # list 57 has no terminator before unrelated data
DEPLOY_FIELDS = [
    ('char_id', 0, 'u16'), ('x', 2, 'u8'), ('y', 3, 'u8'), ('leader_flag', 4, 'u8'),
    ('orders', 5, 'u8'), ('army_slot', 6, 'u8'), ('slot', 7, 'u8'),
]
# columns renamed in v7 (old projects still build)
COLUMN_ALIASES = {'orders': 'army', 'army_slot': 'faction', 'heir': 'unk11'}
# older raw skill columns, read when a project has no 'skills' column: (low byte, high byte)
RAW_SKILL_COLUMNS = {'classes': ('class_skills_raw', 'unk29'), 'items': ('bonus_flags', 'unk9'),
                     'rings': ('skill_bits', None)}


def deploy_rows(rom):
    names = unit_name_table(rom)
    addrs = unit_addrs(rom)
    rows = []
    for li in range(DEPLOY_LISTS):
        a = DEPLOY_DIR + (rom[DEPLOY_DIR + 2 * li] | rom[DEPLOY_DIR + 2 * li + 1] << 8)
        n = 0
        end = DEPLOY_HARD_END if a < DEPLOY_HARD_END else 0x20000   # relocated lists live after it
        while a + 8 <= end:
            cid = rom[a] | rom[a + 1] << 8
            if cid in (0, 0xFFFF):
                break
            lab = ''
            if 1 <= cid <= len(addrs):
                r = addrs[cid - 1]
                t = rom[r]
                off = {0: 15, 2: 15, 1: 5, 3: 3}.get(t)
                if off is not None:
                    nid = rom[r + off] | rom[r + off + 1] << 8
                    lab = names[nid] if nid < len(names) else ''
            rows.append(('%d.%d' % (li, n), a, 8, lab))
            a += 8
            n += 1
    return rows


def fixed_rows(base, count, size, labels):
    def f(rom):
        names = labels(rom)
        return [(i, base + i * size, size, names[i] if i < len(names) else '') for i in range(count)]
    return f


# name: (row provider, fields)
TABLES = {
    'units_playable': (lambda rom: unit_rows(rom, 0), FIXED_FIELDS),
    'units_children': (lambda rom: unit_rows(rom, 1), CHILD_FIELDS),
    'units_npc': (lambda rom: unit_rows(rom, 2), FIXED_FIELDS),
    'units_generic': (lambda rom: unit_rows(rom, 3), GENERIC_FIELDS),
    'deploy': (deploy_rows, DEPLOY_FIELDS),
    'classes': (fixed_rows(CLASSES, CLASS_COUNT, CLASS_SIZE, class_names), CLASS_FIELDS),
    'items': (fixed_rows(ITEMS, ITEM_COUNT, ITEM_SIZE, lambda rom: item_names(rom)[:ITEM_COUNT]), ITEM_FIELDS),
    'rings': (fixed_rows(RINGS, RING_COUNT, RING_SIZE, lambda rom: item_names(rom)[ITEM_COUNT:]), RING_FIELDS),
}
