#!/usr/bin/env python3
"""FE4 randomizer.  Works on a kit project (the CSVs), so it can randomize the clean game or
your own hack, and the result can still be edited before building.

    python fe4rando.py ROM out.smc [--seed N] [--preset standard|chaos|light] [--opt name=value ...]
    python fe4rando.py ROM out.smc --project myhack        # randomize a hack instead of the clean game

Every option is listed in OPTIONS below (and in the editor's Randomizer tab).  A spoiler log
is written next to the output ROM.
"""
import csv
import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- options
# name: (default, kind, choices or range, label, help)
OPTIONS = {
    'growths': ('redistribute', 'choice', ['off', 'variance', 'redistribute', 'random'],
                'Growth rates',
                'variance: each growth moves by up to the amount below. redistribute: same total, new spread. '
                'random: anything between the min and max'),
    'growth_amount': (30, 'int', (0, 100), 'Growth variance', 'how far each growth may move (variance)'),
    'growth_min': (5, 'int', (0, 100), 'Lowest growth', ''),
    'growth_max': (90, 'int', (0, 255), 'Highest growth', ''),
    'bases': ('variance', 'choice', ['off', 'variance', 'redistribute'], 'Personal base stats',
              'the bonuses each character adds to their class bases'),
    'base_amount': (3, 'int', (0, 10), 'Base stat variance', ''),
    'classes': ('on', 'choice', ['off', 'on'], 'Playable classes',
                'random class of the same tier (unpromoted / promoted) and gender; starting items follow'),
    'keep_lords': ('on', 'choice', ['off', 'on'], 'Keep Sigurd, Seliph and Julia', 'story units keep their class'),
    'keep_dancers': ('on', 'choice', ['off', 'on'], 'Keep dancers', 'Sylvia, Lene and Leylia stay dancers'),
    'keep_healers': ('on', 'choice', ['off', 'on'], 'Healers stay healers',
                     'units who start with staves get a class that can use them'),
    'holy_weapons': ('on', 'choice', ['off', 'on'], 'Holy blood keeps its weapon',
                     'major holy blood (and holy weapons carried) get a class that can use that weapon'),
    'skills': ('on', 'choice', ['off', 'on'], 'Personal skills', 'random personal skills, as many as each unit had'),
    'extra_skills': (1, 'int', (0, 3), 'Extra skills', 'skills added on top of the original count'),
    'new_skills': ('on', 'choice', ['off', 'on'], 'Skills from later games',
                   'Aether, Galeforce, Vengeance, Great Shield… join the pool'),
    'minor_blood': ('off', 'choice', ['off', 'on'], 'Random minor holy blood',
                    'generation-1 units without major blood may get a minor blood'),
    'parents': ('split', 'choice', ['off', 'split', 'any_parent'], 'Child parents',
                'split: sibling pairs go to different mothers. any_parent: children can be tied to fathers too'),
    'max_children': (2, 'int', (1, 4), 'Children per parent', ''),
    'inheritance': ('off', 'choice', ['off', 'variance'], 'Inheritance weights',
                    'how much of each parent the children get'),
    'lovers': ('off', 'choice', ['off', 'random'], 'Love affinities', 'random starting love and growth for every pair'),
    'weapons': ('off', 'choice', ['off', 'variance'], 'Weapon stats', 'Mt, Hit and Wt of ordinary weapons vary'),
    'weapon_amount': (3, 'int', (0, 10), 'Weapon variance (Mt/Wt; Hit x5)', ''),
    'enemy_classes': ('off', 'choice', ['off', 'on'], 'Enemy classes',
                      'generic enemies get a class that moves on the same terrain; weapons follow'),
    'keep_bosses': ('on', 'choice', ['off', 'on'], 'Keep bosses', 'enemies with a portrait keep their class'),
}
PRESETS = {
    'light': {'growths': 'variance', 'growth_amount': 15, 'bases': 'off', 'classes': 'off', 'skills': 'on',
              'extra_skills': 0, 'parents': 'off'},
    'standard': {},
    'chaos': {'growths': 'random', 'bases': 'redistribute', 'keep_healers': 'off', 'extra_skills': 2,
              'minor_blood': 'on', 'parents': 'any_parent', 'max_children': 3, 'inheritance': 'variance',
              'lovers': 'random', 'weapons': 'variance', 'enemy_classes': 'on'},
}


def defaults(preset='standard'):
    o = {k: v[0] for k, v in OPTIONS.items()}
    o.update(PRESETS.get(preset, {}))
    return o


def check(opts):
    o = defaults()
    for k, v in opts.items():
        if k not in OPTIONS:
            raise ValueError(f'unknown option {k}')
        d, kind, rng, _, _ = OPTIONS[k]
        if kind == 'int':
            v = int(v)
            if not rng[0] <= v <= rng[1]:
                raise ValueError(f'{k} must be {rng[0]}-{rng[1]}')
        elif v not in rng:
            raise ValueError(f'{k} must be one of {", ".join(rng)}')
        o[k] = v
    return o


# ---------------------------------------------------------------- game facts
WEAPON_TYPES = ['sword', 'lance', 'axe', 'bow', 'staff', 'fire', 'thunder', 'wind', 'light', 'dark']
STAT_COLS = ['str', 'mag', 'skl', 'spd', 'def', 'res', 'lck']
GROWTH_COLS = ['g_hp', 'g_str', 'g_mag', 'g_skl', 'g_spd', 'g_def', 'g_res', 'g_lck']
PROMOTED = {6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 20, 23, 24, 25, 26, 27, 28, 41, 45, 48, 49, 56, 57, 58, 62, 64}
PROMOTES = {0: 9, 1: 7, 2: 11, 3: 14, 4: 12, 5: 10, 15: 16, 16: 17, 18: 19, 19: 20, 21: 24, 22: 23, 37: 26,
            39: 41, 44: 6, 46: 8, 47: 49, 51: 56, 52: 58, 54: 48, 55: 58, 59: 58, 63: 64}
NOT_FOR_PLAYERS = {6, 44, 46, 50, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 38, 40, 42, 43, 53, 61, 62,
                   65, 66, 67, 68, 69, 70, 71}
STORY_UNITS = {1, 25, 43}            # Sigurd, Seliph, Julia
DANCERS = {22, 47, 62}               # Sylvia, Leylia, Lene
FIXED_CHILDREN = {25, 29, 44}        # Seliph (Deirdre), Leif and Altena (Ethlyn)
GEN1_MEN = list(range(2, 16))        # Noish..Dew (not Sigurd)
GEN1_WOMEN = list(range(18, 25))     # Raquesis..Bridget (not Deirdre, Ethlyn)
FINN = (5, 34)
PLAYER_SKILLS = ['Wrath', 'Pursuit', 'Adept', 'Charm', 'Nihil', 'Miracle', 'Critical', 'Vantage', 'Accost',
                 'Astra', 'Luna', 'Sol', 'Renewal', 'Paragon', 'Recover', 'Bargain']
ENEMY_SKIP = {5, 10, 15, 16, 17, 27, 28, 44, 46, 47, 48, 49, 50, 60, 61, 62, 65, 66, 67, 68, 69, 70, 71}
BLOODS = ['Baldur', 'Naga', 'Dain', 'Nova', 'Odo', 'Ullur', 'Neir', 'Fala',
          'Tordo', 'Forseti', 'Bragi', 'Hezul', 'Loptyr']
MINOR_POOL = ['Baldur', 'Dain', 'Nova', 'Odo', 'Ullur', 'Neir', 'Fala', 'Tordo', 'Forseti', 'Bragi', 'Hezul']

# skills from later games (the same rows as the kit's example project)
NEW_SKILLS = [
    {'name': 'Aether', 'effect': 'aether'}, {'name': 'Galeforce', 'effect': 'galeforce'},
    {'name': 'Vengeance', 'effect': 'vengeance'}, {'name': 'Great Shield', 'effect': 'great_shield'},
    {'name': 'Lifetaker', 'effect': 'lifetaker'},
    {'name': 'Fortune', 'effect': 'combat', 'bonus': 'foe_crit-100', 'icon': 'Miracle'},
    {'name': 'Rally', 'effect': 'combat', 'when': 'ally_near', 'bonus': 'atk+3;def+3', 'icon': 'Charm'},
    {'name': 'Pray', 'effect': 'pray', 'icon': 'Miracle'}, {'name': 'Counter', 'effect': 'counter', 'icon': 'Vantage'},
    {'name': 'Ignis', 'effect': 'ignis', 'icon': 'spare3'}, {'name': 'Aegis', 'effect': 'aegis', 'icon': 'spare4'},
    {'name': 'Death Blow', 'effect': 'combat', 'when': 'attacking', 'bonus': 'atk+6', 'menu': 'no'},
    {'name': 'Sure Strike', 'effect': 'sure_strike', 'menu': 'no'},
    {'name': 'Lethality', 'effect': 'lethality', 'menu': 'no'}, {'name': 'Deadeye', 'effect': 'deadeye', 'menu': 'no'},
    {'name': 'Colossus', 'effect': 'colossus', 'menu': 'no'},
    {'name': 'Darting Blow', 'effect': 'combat', 'when': 'attacking', 'bonus': 'speed+5', 'menu': 'no'},
    {'name': 'Defiant Str', 'effect': 'combat', 'when': 'hp<=25', 'bonus': 'atk+7', 'menu': 'no'},
]


# ---------------------------------------------------------------- CSV helpers
class Table:
    def __init__(self, proj, name):
        self.path = os.path.join(proj, name + '.csv')
        with open(self.path, newline='', encoding='utf-8') as f:
            rd = csv.DictReader(f)
            self.fields = list(rd.fieldnames)
            self.rows = list(rd)
        self.by = {r[self.fields[0]]: r for r in self.rows}

    def save(self, out_proj):
        p = os.path.join(out_proj, os.path.basename(self.path))
        for r in self.rows:
            for k in r:
                if k not in self.fields:
                    self.fields.append(k)
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=self.fields)
            w.writeheader()
            w.writerows(self.rows)


class Game:
    def __init__(self, proj):
        self.proj = proj
        self.t = {n: Table(proj, n) for n in ('units_playable', 'units_children', 'units_generic', 'classes', 'items',
                                               'item_instances', 'skills', 'lovers')
                  if os.path.exists(os.path.join(proj, n + '.csv'))}
        self.classes = {int(r['index']): r for r in self.t['classes'].rows}
        self.items = {int(r['index']): r for r in self.t['items'].rows}
        self.inst = {int(r['instance']): r for r in self.t['item_instances'].rows}
        self.play = {int(r['index']): r for r in self.t['units_playable'].rows}
        self.kids = {int(r['index']): r for r in self.t['units_children'].rows}
        self.names = {i: r['_name'] for i, r in list(self.play.items()) + list(self.kids.items())}
        for r in self.t['units_generic'].rows:
            self.names.setdefault(int(r['index']), r['_name'])

    def rank(self, cls, wtype):
        return self.classes[cls]['rank_' + WEAPON_TYPES[wtype]]

    def usable(self, cls, item):
        it = self.items.get(item)
        if it is None:
            return True                                  # rings and other non-weapons
        need = it['rank']
        have = self.rank(cls, int(it['weapon_type']))
        if have == '-':
            return False
        if need == '*':
            return True                                  # holy weapons: the blood decides
        return 'ABC'.index(have) <= 'ABC'.index(need) if need in 'ABC' else True

    def weapon_types(self, cls):
        return [t for t in range(10) if self.rank(cls, t) != '-']

    def item_name(self, i):
        it = self.items.get(i)
        return it['_name'] if it else str(i)


def _int(v, d=0):
    try:
        return int(str(v).strip(), 0)
    except ValueError:
        return d


# ---------------------------------------------------------------- the randomizer
class Rando:
    def __init__(self, game, opts, seed):
        self.g = game
        self.o = opts
        self.rng = random.Random(seed)
        self.seed = seed
        self.log = []
        self.new_class = {}

    def section(self, title):
        self.log.append('')
        self.log.append(title)
        self.log.append('-' * len(title))

    # ---- classes
    def gender_pools(self):
        """classes seen for each gender in the game's own playable units, plus their promotions"""
        seen = {0: set(), 1: set()}
        for r in list(self.g.play.values()) + list(self.g.kids.values()):
            seen[_int(r['gender'])].add(_int(r['class']))
        pools = {}
        for gen, s in seen.items():
            s = set(s) | {PROMOTES[c] for c in s if c in PROMOTES}
            s -= NOT_FOR_PLAYERS
            pools[gen] = sorted(s)
        return pools

    def holy_types(self, row, uid):
        """weapon types this unit must keep: its major bloods' holy weapons and holy weapons it carries"""
        need = set()
        if self.o['holy_weapons'] != 'on':
            return need
        for part in (row.get('holy_blood') or '').split(';'):
            if ':major' in part:
                b = part.split(':')[0]
                for it in self.g.items.values():
                    if it['rank'] == '*' and _int(it['blood_lock']) == BLOODS.index(b) + 1:
                        need.add(int(it['weapon_type']))
                if b == 'Bragi':
                    need.add(4)
        for k in ('item1', 'item2', 'item3'):
            i = _int(row.get(k, 255), 255)
            if i != 255 and i in self.g.inst:
                t = _int(self.g.inst[i]['item_type'])
                it = self.g.items.get(t)
                if it and it['rank'] == '*':
                    need.add(int(it['weapon_type']))
        return need

    def pick_class(self, uid, row, pools, need_types=(), share_with=None):
        cur = _int(row['class'])
        gen = _int(row['gender'])
        tier = cur in PROMOTED
        cands = [c for c in pools[gen] if (c in PROMOTED) == tier]
        if self.o['keep_healers'] == 'on' and self.g.rank(cur, 4) != '-':
            cands = [c for c in cands if self.g.rank(c, 4) != '-']
        for t in need_types:
            cands = [c for c in cands if self.g.rank(c, t) != '-']
        if share_with is not None:
            st = set(self.g.weapon_types(share_with))
            c2 = [c for c in cands if st & set(self.g.weapon_types(c))]
            cands = c2 or cands
        if not cands:
            return cur
        return self.rng.choice(cands)

    def fix_items(self, uid, row, cls, item_cols, owners):
        """make each starting item usable by its owners' classes (instances may be shared)"""
        for k in item_cols:
            i = _int(row.get(k, 255), 255)
            if i == 255 or i not in self.g.inst:
                continue
            cur_t = _int(self.g.inst[i]['item_type'])
            classes = [self.new_class.get(o, cls) for o in owners.get(i, [uid])]
            if all(self.g.usable(c, cur_t) for c in classes):
                continue
            new_t = self.replacement(cur_t, classes)
            if new_t is not None:
                self.g.inst[i]['item_type'] = str(new_t)
                self.g.inst[i]['_item_name'] = self.g.item_name(new_t)

    def replacement(self, cur_t, classes):
        cur = self.g.items.get(cur_t)
        want = cur['rank'] if cur and cur['rank'] in 'ABC' else 'C'
        types = set(range(10))
        for c in classes:
            types &= set(self.g.weapon_types(c))
        if not types:
            types = set(self.g.weapon_types(classes[0]))
        staff = cur is not None and int(cur['weapon_type']) == 4
        order = sorted(types, key=lambda t: (t != 4) if staff else (t == 4))
        for t in order[:1] + self.rng.sample(order[1:], len(order) - 1) if order else []:
            cands = [i for i, it in self.g.items.items()
                     if int(it['weapon_type']) == t and it['rank'] in 'ABC' and 'Broken' not in it['_name']
                     and 'Drained' not in it['_name'] and 'allista' not in it['_name']
                     and all(self.g.usable(c, i) for c in classes)]
            if not cands:
                continue
            same = [i for i in cands if self.g.items[i]['rank'] == want]
            return self.rng.choice(same or cands)
        return None

    def do_classes(self):
        if self.o['classes'] != 'on':
            return
        self.section('Classes')
        pools = self.gender_pools()
        owners = {}
        for uid, r in list(self.g.play.items()) + list(self.g.kids.items()):
            for k in ('item1', 'item2', 'item3'):
                i = _int(r.get(k, 255), 255)
                if i != 255:
                    owners.setdefault(i, []).append(uid)
        keep = set()
        if self.o['keep_lords'] == 'on':
            keep |= STORY_UNITS
        if self.o['keep_dancers'] == 'on':
            keep |= DANCERS
        subs = {}
        for cid, r in self.g.kids.items():
            s = (r.get('substitute') or '').strip()
            if s:
                sid = next((i for i, n in self.g.names.items() if n == s or str(i) == s), None)
                if sid:
                    subs[sid] = cid
        # children first (their anchors' blood decides), then everyone else; subs share with their child
        order = list(self.g.kids.items()) + [(u, r) for u, r in self.g.play.items() if u not in subs and u != FINN[1]] \
            + [(u, r) for u, r in self.g.play.items() if u in subs]
        for uid, r in order:
            if uid in keep:
                continue
            need = self.holy_types(r, uid)
            if uid in self.g.kids:
                need |= self.anchor_types(r)
            share = self.new_class.get(subs[uid], _int(self.g.kids[subs[uid]]['class'])) if uid in subs else None
            c = self.pick_class(uid, r, pools, need, share)
            self.new_class[uid] = c
        if FINN[0] in self.new_class and FINN[1] in self.g.play:      # the same Finn in both generations
            self.new_class[FINN[1]] = self.new_class[FINN[0]]
        for uid, c in self.new_class.items():
            r = self.g.play.get(uid) or self.g.kids[uid]
            old = r['_class_name']
            r['class'] = str(c)
            r['_class_name'] = self.g.classes[c]['_name']
        for uid in self.new_class:
            r = self.g.play.get(uid) or self.g.kids[uid]
            self.fix_items(uid, r, self.new_class[uid], ('item1', 'item2', 'item3'), owners)
        for uid, c in self.new_class.items():
            r = self.g.play.get(uid) or self.g.kids[uid]
            items = []
            for k in ('item1', 'item2', 'item3'):
                i = _int(r.get(k, 255), 255)
                if i != 255 and i in self.g.inst:
                    t = _int(self.g.inst[i]['item_type'])
                    items.append(self.g.item_name(t) if t in self.g.items else self.g.inst[i].get('_item_name', str(t)))
            r['_items'] = ' / '.join(items)
            self.log.append(f'{self.g.names[uid]:<10} {self.g.classes[c]["_name"]:<15} {r["_items"]}')

    def anchor_types(self, kid):
        """a child must use the holy weapon of the parent it is tied to (it inherits their blood)"""
        if self.o['holy_weapons'] != 'on':
            return set()
        p = (kid.get('parent') or '').strip()
        pid = next((i for i, n in self.g.names.items() if n == p or str(i) == p), None)
        if pid in self.g.play:
            return self.holy_types({'holy_blood': self.g.play[pid].get('holy_blood', '')}, pid)
        return set()

    # ---- numbers
    def do_growths(self):
        mode = self.o['growths']
        if mode == 'off':
            return
        self.section('Growth rates (HP Str Mag Skl Spd Def Res Lck)')
        lo, hi, amt = self.o['growth_min'], self.o['growth_max'], self.o['growth_amount']
        for uid, r in self.g.play.items():
            g = [_int(r[c]) for c in GROWTH_COLS]
            if mode == 'variance':
                g = [v + self.rng.randint(-amt, amt) for v in g]
            elif mode == 'redistribute':
                total = sum(g)
                w = [self.rng.random() + 0.2 for _ in g]
                g = [total * x / sum(w) for x in w]
            else:
                g = [self.rng.randint(lo, hi) for _ in g]
            g = [max(lo if mode != 'variance' else 0, min(hi if mode != 'variance' else 255, int(round(v / 5) * 5)))
                 for v in g]
            for c, v in zip(GROWTH_COLS, g):
                r[c] = str(v)
            self.log.append(f'{self.g.names[uid]:<10} ' + ' '.join(f'{v:>3}' for v in g))

    def do_bases(self):
        mode = self.o['bases']
        if mode == 'off':
            return
        self.section('Personal base stats (Str Mag Skl Spd Def Res Lck)')
        amt = self.o['base_amount']
        for uid, r in self.g.play.items():
            s = [_int(r[c]) for c in STAT_COLS]
            if mode == 'variance':
                s = [max(0, v + self.rng.randint(-amt, amt)) for v in s]
            else:
                total = sum(s)
                s = [0] * len(s)
                for _ in range(total):
                    s[self.rng.randrange(len(s))] += 1
            s = [min(v, 30) for v in s]
            for c, v in zip(STAT_COLS, s):
                r[c] = str(v)
            self.log.append(f'{self.g.names[uid]:<10} ' + ' '.join(f'{v:>3}' for v in s))

    # ---- skills
    def do_skills(self):
        if self.o['skills'] != 'on':
            return
        self.section('Personal skills')
        sk = self.g.t['skills']
        have_names = {r['name'] for r in sk.rows}
        pool = [s for s in PLAYER_SKILLS if s in have_names]
        new_rows = []
        if self.o['new_skills'] == 'on':
            nid = max(_int(r['id']) for r in sk.rows) + 1
            for d in NEW_SKILLS:
                row = next((r for r in sk.rows if r['name'] == d['name']), None)
                if row is None:
                    row = {f: '' for f in sk.fields}
                    row.update(d)
                    row['id'] = str(nid)
                    row['_added'] = True
                    nid += 1
                    sk.rows.append(row)
                row['_was'] = (row.get('units', ''), row.get('classes', ''))
                row['units'] = ''
                row['classes'] = ''
                new_rows.append(row)
        pool_all = pool + [r['name'] for r in new_rows]
        given = {r['name']: [] for r in new_rows}
        for uid, r in self.g.play.items():
            cur = [s for s in (r['skills'] or '').split(';') if s]
            keep = [s for s in cur if s not in PLAYER_SKILLS]          # hidden / story bits stay
            n = len([s for s in cur if s in PLAYER_SKILLS]) + self.o['extra_skills']
            picks = self.rng.sample(pool_all, min(n, len(pool_all)))
            r['skills'] = ';'.join(keep + [p for p in picks if p in pool])
            for p in picks:
                if p in given:
                    given[p].append(str(uid))
            self.log.append(f'{self.g.names[uid]:<10} {", ".join(picks) or "-"}')
        for row in new_rows:
            row['units'] = ';'.join(given[row['name']])
            if not row['units']:                       # nobody got it: drop it, or keep its old owners
                if row.get('_added'):
                    sk.rows.remove(row)
                else:
                    row['units'], row['classes'] = row['_was']
        base = max(_int(r['id']) for r in sk.rows if not r.get('_added'))
        for r in sk.rows:
            if r.get('_added'):
                base += 1
                r['id'] = str(base)
        for row in new_rows:
            row.pop('_added', None)
            row.pop('_was', None)

    def do_minor_blood(self):
        if self.o['minor_blood'] != 'on':
            return
        self.section('Minor holy blood')
        for uid in range(2, 25):
            r = self.g.play.get(uid)
            if r is None or ':major' in (r.get('holy_blood') or ''):
                continue
            if self.rng.random() < 0.6:
                b = self.rng.choice(MINOR_POOL)
                r['holy_blood'] = f'{b}:minor'
                self.log.append(f'{self.g.names[uid]:<10} {b}')

    # ---- generation 2
    def do_parents(self):
        mode = self.o['parents']
        if mode == 'off':
            return
        if 'parent' not in self.g.t['units_children'].fields:
            raise SystemExit('this project has no generation-2 columns; extract it again with this kit')
        self.section('Children and the parent they are tied to')
        anchors = list(GEN1_WOMEN) + (GEN1_MEN if mode == 'any_parent' else [])
        anchors = [a for a in anchors if a in self.g.play]
        cap = self.o['max_children']
        load = {a: 0 for a in anchors}
        kids = [k for k in self.g.kids if k not in FIXED_CHILDREN and self.g.kids[k].get('parent')]
        self.rng.shuffle(kids)
        old = {k: self.g.kids[k]['parent'] for k in kids}
        siblings = {}
        for k in kids:
            siblings.setdefault(old[k], []).append(k)
        for k in kids:
            sib_parents = {self.g.kids[s].get('_newparent') for s in siblings[old[k]] if s != k}
            free = [a for a in anchors if load[a] < cap and a not in sib_parents] or \
                   [a for a in anchors if load[a] < cap] or anchors
            a = self.rng.choice(free)
            load[a] += 1
            r = self.g.kids[k]
            r['_newparent'] = a
            r['parent'] = str(a)
            r['heir'] = 'father' if a in GEN1_MEN else 'mother'
            self.log.append(f'{self.g.names[k]:<10} {self.g.names[a]}  (was {old[k]})')
        for r in self.g.kids.values():
            r.pop('_newparent', None)
        if self.o['inheritance'] == 'variance':
            self.section('Inheritance weights (growth father/mother, stats father/mother)')
            for k, r in self.g.kids.items():
                w = []
                for c in ('growth_father', 'growth_mother', 'stats_father', 'stats_mother'):
                    v = _int(r.get(c) or 0)
                    v = max(0, v + self.rng.randint(-v // 2, v // 2))
                    r[c] = str(v)
                    w.append(v)
                self.log.append(f'{self.g.names[k]:<10} ' + ' '.join(f'{v:>3}' for v in w))

    def do_lovers(self):
        if self.o['lovers'] != 'random' or 'lovers' not in self.g.t:
            return
        for r in self.g.t['lovers'].rows:
            if r['start'] == '499':
                continue                          # Sigurd and Deirdre, Quan and Ethlyn
            r['start'] = 'no' if self.rng.random() < 0.05 else str(self.rng.choice(range(0, 210, 10)))
            r['growth'] = str(self.rng.randint(0, 12))

    # ---- items and enemies
    def do_weapons(self):
        if self.o['weapons'] != 'variance':
            return
        self.section('Weapons (Mt Hit Wt)')
        a = self.o['weapon_amount']
        for i, it in self.g.items.items():
            if it['rank'] not in 'ABC' or int(it['weapon_type']) == 4 or 'Broken' in it['_name'] \
                    or 'Drained' in it['_name'] or 'allista' in it['_name']:
                continue
            mt = max(0, _int(it['mt']) + self.rng.randint(-a, a))
            hit = max(30, min(120, _int(it['hit']) + 5 * self.rng.randint(-a, a)))
            wt = max(0, _int(it['wt']) + self.rng.randint(-a, a))
            it['mt'], it['hit'], it['wt'] = str(mt), str(hit), str(wt)
            self.log.append(f'{it["_name"]:<16} {mt:>3} {hit:>4} {wt:>3}')

    def do_enemies(self):
        if self.o['enemy_classes'] != 'on':
            return
        self.section('Enemy classes')
        groups = {}
        for c, r in self.g.classes.items():
            if c in ENEMY_SKIP:
                continue
            groups.setdefault((r['group'], c in PROMOTED), []).append(c)
        n = 0
        for r in self.g.t['units_generic'].rows:
            c = _int(r['class'])
            if c in ENEMY_SKIP or (self.o['keep_bosses'] == 'on' and r.get('portrait', '243') not in ('243', '')):
                continue
            cands = groups.get((self.g.classes[c]['group'], c in PROMOTED), [c])
            nc = self.rng.choice(cands)
            if nc == c:
                continue
            r['class'] = str(nc)
            r['_class_name'] = self.g.classes[nc]['_name']
            for k in ('item1', 'item2', 'item3'):
                t = _int(r[k], 255)
                if t != 255 and t < 106 and not self.g.usable(nc, t):
                    nt = self.replacement(t, [nc])
                    r[k] = str(nt if nt is not None else 255)
            n += 1
        self.log.append(f'{n} enemy unit types changed class')

    def run(self):
        self.log = [f'FE4 randomizer  seed {self.seed}', 'options: ' +
                    ', '.join(f'{k}={v}' for k, v in self.o.items())]
        self.do_growths()
        self.do_bases()
        self.do_minor_blood()
        self.do_parents()                 # before classes: children follow their new parent's blood
        self.do_classes()
        self.do_skills()
        self.do_lovers()
        self.do_weapons()
        self.do_enemies()
        return '\n'.join(self.log) + '\n'


def copy_tree(src, dst):
    """Plain copy (shutil's Windows fast path isn't available everywhere, e.g. under Wine)."""
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        a, b = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(a):
            copy_tree(a, b)
        else:
            with open(a, 'rb') as f, open(b, 'wb') as g:
                g.write(f.read())


def randomize_project(proj_in, proj_out, seed, opts):
    """Copy proj_in to proj_out with randomized CSVs; returns the spoiler log text."""
    if os.path.abspath(proj_in) != os.path.abspath(proj_out):
        if os.path.exists(proj_out):
            shutil.rmtree(proj_out)
        copy_tree(proj_in, proj_out)
    g = Game(proj_out)
    log = Rando(g, check(opts), seed).run()
    for t in g.t.values():
        t.save(proj_out)
    with open(os.path.join(proj_out, 'spoiler.txt'), 'w', encoding='utf-8') as f:
        f.write(log)
    return log


def randomize_rom(rom_path, out_rom, seed=None, opts=None, project=None, ips=None, keep_project=None):
    import fe4hack
    seed = seed if seed is not None else random.randrange(1, 10 ** 9)
    tmp = tempfile.mkdtemp(prefix='fe4rando_')
    try:
        src = project
        if src is None:
            src = os.path.join(tmp, 'clean')
            fe4hack.extract(rom_path, src)
        out = keep_project or os.path.join(tmp, 'rando')
        log = randomize_project(src, out, seed, opts or {})
        fe4hack.build(rom_path, out, out_rom, ips)
        with open(os.path.splitext(out_rom)[0] + '_spoiler.txt', 'w', encoding='utf-8') as f:
            f.write(log)
        return seed, log
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_tsv(path):
    """Options and presets for other programs (the PC port's randomizer window)."""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for k, (d, kind, rng, label, hlp) in OPTIONS.items():
            r = '%d,%d' % rng if kind == 'int' else ','.join(rng)
            f.write('\t'.join(['O', k, str(d), kind, r, label, hlp.replace('\t', ' ')]) + '\n')
        for name, kv in PRESETS.items():
            f.write('\t'.join(['P', name, ';'.join('%s=%s' % (k, v) for k, v in kv.items())]) + '\n')


def main(argv):
    argv = list(argv)
    if '--log' in argv:            # run from another program (the PC port): output and errors go to a file
        i = argv.index('--log')
        log = open(argv[i + 1], 'w', encoding='utf-8', buffering=1)
        del argv[i:i + 2]
        sys.stdout = sys.stderr = log
        try:
            _main(argv)
        except SystemExit as e:
            if e.code not in (None, 0):
                print(e.code if isinstance(e.code, str) else 'error')
                log.close()
                os._exit(1)
        except BaseException:
            import traceback
            traceback.print_exc()
            log.close()
            os._exit(1)
        log.close()
        return
    _main(argv)


def _main(argv):
    import argparse
    if '--list-tsv' in argv:
        write_tsv(argv[argv.index('--list-tsv') + 1])
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('out')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--preset', default='standard', choices=list(PRESETS))
    ap.add_argument('--opt', action='append', default=[], help='name=value, e.g. growths=random')
    ap.add_argument('--project', help='randomize this project instead of the clean game')
    ap.add_argument('--ips')
    ap.add_argument('--keep-project', help='also save the randomized project here')
    ap.add_argument('--list', action='store_true', help='list the options')
    if '--list' in argv:
        for k, (d, kind, rng, label, hlp) in OPTIONS.items():
            print(f'{k:<15} {label}: {rng if kind != "int" else "%d-%d" % rng} (default {d}). {hlp}')
        return
    a = ap.parse_args(argv)
    opts = defaults(a.preset)
    for kv in a.opt:
        k, v = kv.split('=', 1)
        opts[k] = v
    seed, _ = randomize_rom(a.rom, a.out, a.seed, opts, a.project, a.ips, a.keep_project)
    print(f'seed {seed} -> {a.out}  (spoiler log: {os.path.splitext(a.out)[0]}_spoiler.txt)')


if __name__ == '__main__':
    main(sys.argv[1:])
