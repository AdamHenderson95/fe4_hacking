#!/usr/bin/env python3
"""Builder of the Holy War: the kit's visual editor.

A small web server on 127.0.0.1 serves the interface in studio/ and a JSON API over the kit's
project files; the interface opens in its own window (Edge or Chrome in app mode, else the
default browser). Only pages that know this session's token can use the API.

  python fe4studio.py            # or BuilderOfTheHolyWar.exe
"""
import csv
import base64
import contextlib
import io
import json
import mimetypes
import os
import queue
import re
import zlib
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(getattr(sys, '_MEIPASS', None) and sys.executable or __file__))
KIT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)

import fe4lib as L                 # noqa: E402
import fe4hack                     # noqa: E402
import fe4gfx                      # noqa: E402
import fe4maps                     # noqa: E402
import fe4events                   # noqa: E402
import fe4locations                # noqa: E402
import fe4conds                    # noqa: E402
import fe4sprites                  # noqa: E402
import fe4walk                     # noqa: E402
import fe4mapbattle                # noqa: E402
import fe4mapfx                    # noqa: E402
import fe4maptiles                 # noqa: E402
import fe4mapset                  # noqa: E402
import fe4title                    # noqa: E402
import fe4chaptitle                 # noqa: E402
import fe4skillmenu                # noqa: E402
import fe4music                    # noqa: E402
import fe4battle                  # noqa: E402
import fe4spellfx                  # noqa: E402
import fe4skillanim                # noqa: E402
from fe4project import Project, load_settings, save_settings   # noqa: E402

APP = 'Builder of the Holy War'
VERSION = '1.3'
STATIC = os.path.join(KIT, 'studio')

# ---------------------------------------------------------------- state
settings = load_settings()
state = {'project': None, 'rom': None, 'rom_data': None, 'job': None, 'last_ping': None}
lock = threading.RLock()
dialogs = queue.Queue()            # (kind, kwargs, reply-queue): run on the main thread (tkinter)


def rom_path():
    r = settings.get('rom')
    return r if r and os.path.exists(r) else None


def rom_data():
    r = rom_path()
    if not r:
        return None
    if state['rom'] != r:
        try:
            _, data = L.load_rom(r)
        except OSError:
            return None
        state['rom'], state['rom_data'] = r, bytes(data)
    return state['rom_data']


def project():
    return state['project']


def warm_portraits():
    """Decode the portraits in the background so the roster shows up quickly."""
    def go():
        rom = rom_data()
        if rom is None:
            return
        for n in range(fe4gfx.PORTRAIT_COUNT):
            fe4gfx.portrait_png(rom, n, 2)
    threading.Thread(target=go, daemon=True).start()


def open_project(d):
    if not os.path.exists(os.path.join(d, 'units_playable.csv')):
        raise ValueError(f"{d} isn't a kit project (it has no units_playable.csv).")
    rom = rom_data()
    if rom is not None:
        for ch, what in fe4maps.upgrade_v15_maps(rom, os.path.join(d, 'maps')):
            print(f'chapter {ch} map: ' + ('re-read from the ROM (older kits read it wrongly)' if what == 'fixed'
                                           else 'exported by an older kit and edited since; re-export it'))
        if not os.path.exists(os.path.join(d, 'talks.csv')):     # kits before v19 had no Talk lists
            fe4locations.export_talks(rom, os.path.join(d, 'talks.csv'))
        if not os.path.exists(os.path.join(d, 'map_terrain.csv')):   # kits before v24
            fe4maptiles.export_terrain(rom, os.path.join(d, 'map_terrain.csv'))
        if not os.path.exists(os.path.join(d, fe4maps.SIZES_FILE)):   # kits before v57
            fe4maps.export_sizes(rom, os.path.join(d, fe4maps.SIZES_FILE))
        if not os.path.exists(os.path.join(d, 'skill_anims.csv')):   # kits before v40
            import fe4skillanim, fe4skills
            fe4skillanim.export(rom, os.path.join(d, 'skill_anims.csv'), dict(enumerate(fe4skills.NAMES)))
        if not os.path.exists(os.path.join(d, 'map_spells.csv')):   # kits before v44
            fe4mapfx.export(rom, d, L.item_names(rom))
        else:                                                        # kits before v46 / v47
            fe4mapfx.upgrade_colours(rom, d, L.item_names(rom))
        fe4music.upgrade(rom, d, fe4music.CHAPTER_NAMES, lambda i: fe4locations.castle_name(rom, i))   # kits before v50
        if not os.path.exists(os.path.join(d, 'map_battle.csv')):   # kits before v43
            import fe4mapbattle
            fe4mapbattle.export(rom, os.path.join(d, 'map_battle.csv'), L.class_names(rom)[:72])
        if not os.path.exists(os.path.join(d, 'spells.csv')):   # kits before v35
            fe4battle.export_spells(rom, os.path.join(d, 'spells.csv'), dict(enumerate(L.item_names(rom))))
        if not os.path.exists(os.path.join(d, 'battle_anims.csv')):   # kits before v32
            names = [r.get('_name', '') for r in csv.DictReader(open(os.path.join(d, 'classes.csv'), newline=''))] \
                if os.path.exists(os.path.join(d, 'classes.csv')) else []
            fe4battle.export(rom, os.path.join(d, 'battle_anims.csv'), dict(enumerate(names)))
        if not os.path.exists(os.path.join(d, 'map_sprites.csv')):   # kits before v23
            import fe4hack
            names = [r.get('_name', '') for r in csv.DictReader(open(os.path.join(d, 'classes.csv'), newline=''))] \
                if os.path.exists(os.path.join(d, 'classes.csv')) else []
            fe4hack.export_map_sprites(rom, d, names)
    state['project'] = Project(d)
    warm_portraits()
    settings['project'] = d
    recent = [p for p in settings.get('recent', []) if p != d]
    settings['recent'] = [d] + recent[:7]
    save_settings(settings)


if settings.get('project') and os.path.exists(os.path.join(settings['project'], 'units_playable.csv')):
    try:
        open_project(settings['project'])
    except Exception:              # noqa: BLE001
        pass


# ---------------------------------------------------------------- jobs (build, extract, test play)
def run_job(what, fn):
    with lock:
        if state['job'] and state['job']['running']:
            raise RuntimeError('Still working on: ' + state['job']['what'])
        job = {'what': what, 'running': True, 'ok': None, 'log': '', 'result': None, 'id': secrets.token_hex(4)}
        state['job'] = job

    def worker():
        class Tee(io.TextIOBase):
            def write(self, s):
                job['log'] += s
                return len(s)
        old = sys.stdout
        sys.stdout = Tee()
        try:
            job['result'] = fn()
            job['ok'] = True
        except SystemExit as e:
            job['log'] += f'\n{e}\n'
            job['ok'] = False
        except Exception as e:     # noqa: BLE001
            job['log'] += '\n' + ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            job['ok'] = False
        finally:
            sys.stdout = old
            job['running'] = False
    threading.Thread(target=worker, daemon=True).start()
    return job


def port_exe():
    p = settings.get('port')
    if p and os.path.isfile(p):
        return p
    names = ['FE4.exe'] if sys.platform.startswith('win') else ['fe4', 'FE4.exe']
    up = os.path.dirname(HERE)
    for d in (HERE, up, os.path.join(HERE, 'FE4Port'), os.path.join(up, 'FE4Port')):
        for n in names:
            c = os.path.join(d, n)
            if os.path.isfile(c):
                return c
    return None


# ---------------------------------------------------------------- data for the pages
TABLES = {'units_playable', 'units_children', 'units_npc', 'units_generic', 'classes', 'items', 'rings',
          'item_instances', 'skills', 'names', 'lovers', 'gen2_rules', 'deploy', 'locations', 'arena', 'armies', 'talks', 'map_sprites', 'map_terrain', 'battle_anims', 'spells', 'skill_anims', 'map_battle', 'map_spells', 'map_palettes', 'map_colour_words', 'map_spell_block', 'music', 'music_bosses'}


def unit_portrait(table, row):
    """Portrait number for a unit row (children name their portrait; others by character ID)."""
    rom = rom_data()
    if rom is None:
        return None
    if table == 'units_children':
        p = (row.get('portrait') or '').strip()
        if p.isdigit():
            n = int(p)
            return n if n < fe4gfx.PORTRAIT_COUNT and n != fe4gfx.NO_PORTRAIT else None
        if p:   # a unit name: borrow theirs
            for t in ('units_playable', 'units_npc', 'units_children'):
                tb = project().table(t)
                for r in tb.rows if tb else []:
                    if r.get('_name') == p and r is not row:
                        return unit_portrait(t, r)
        return None
    cid = row.get('char_id') or row.get('index') or ''
    return fe4gfx.portrait_of_char(rom, int(cid)) if cid.isdigit() else None


# ---------------------------------------------------------------- portraits
PORTRAIT_DIR = 'portraits'
_pcache = {}


def portrait_rel(n):
    return f'{PORTRAIT_DIR}/p{n:03d}.png'


def portrait_custom(n):
    """The project's own picture for portrait n (PNG bytes), or None."""
    p = project()
    if p is None:
        return None
    return p.blob(portrait_rel(n)).data


def portrait_sheet(n):
    """(indices, palette, custom) of portrait n: the project's picture if it has one, else the ROM's."""
    data = portrait_custom(n)
    if data is not None:
        key = ('sheet', hash(data))
        if key not in _pcache:
            _pcache[key] = fe4gfx.sheet_from_png(data)
        return (*_pcache[key], True)
    rom = rom_data()
    if rom is None:
        return None
    key = ('rom', id(rom), n)
    if key not in _pcache:
        _pcache[key] = fe4gfx.portrait_sheet(rom, n)
    return (*_pcache[key], False) if _pcache[key] else None


def portrait_image(n, scale, sheet=False):
    if sheet:
        got = portrait_sheet(n)
        return fe4gfx.indexed_png(fe4gfx.SHEET_W, fe4gfx.SHEET_H, got[0], got[1], scale) if got else None
    if portrait_custom(n) is None:
        rom = rom_data()
        return fe4gfx.portrait_png(rom, n, scale) if rom else None
    got = portrait_sheet(n)
    return fe4gfx.face_png(got[0], got[1], scale) if got else None


def api_portraits(b, q):
    """Every portrait number with who uses it and whether the project replaced it."""
    p = need_project()
    users = {}
    for t in ('units_playable', 'units_children', 'units_npc'):
        tb = p.table(t)
        for r in tb.rows if tb else []:
            n = unit_portrait(t, r)
            if n is not None and r.get('_name'):
                users.setdefault(n, []).append(r['_name'])
    gt = p.table('units_generic')
    for r in gt.rows if gt else []:
        pn = (r.get('portrait') or '').strip()
        if pn.isdigit():
            users.setdefault(int(pn), [])
            nm = r.get('_class_name') or r.get('_name') or ''
            if nm and nm not in users[int(pn)]:
                users[int(pn)].append(nm)
    for x in people():
        if x.get('speaker') and x['portrait'] is not None and x['name'] not in users.get(x['portrait'], []):
            users.setdefault(x['portrait'], []).append(x['name'])
    out = []
    for n in range(fe4gfx.PORTRAIT_COUNT):
        if n == fe4gfx.NO_PORTRAIT:
            continue
        data = portrait_custom(n)
        out.append({'n': n, 'users': sorted(set(users.get(n, [])), key=str.lower)[:12],
                    'custom': data is not None, 'ver': '%08x' % zlib.crc32(data) if data is not None else 'rom'})
    return {'portraits': out}


def api_portrait(b, q):
    """Replace portrait n with a PNG (base64): 48x64 or 80x64, at most 15 colours + transparency."""
    import base64
    p = need_project()
    n = int(b['n'])
    if not 0 <= n < fe4gfx.PORTRAIT_COUNT or n == fe4gfx.NO_PORTRAIT:
        raise ValueError('No such portrait.')
    if b.get('reset'):
        p.set_blob(portrait_rel(n), None)
        return {'ok': True}
    try:
        idx, pal = fe4gfx.sheet_from_png(base64.b64decode(b['png']))
    except (ValueError, KeyError) as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(portrait_rel(n), fe4gfx.indexed_png(fe4gfx.SHEET_W, fe4gfx.SHEET_H, idx, pal))
    return {'ok': True}


# ---------------------------------------------------------------- title screen (kit v53)

_title_cache = {}


def title_game():
    """The game's own title layers (read once per ROM)."""
    rom = rom_data()
    if rom is None:
        raise RuntimeError('The editor needs the game ROM for this page.')
    if _title_cache.get('rom') is not rom:
        _title_cache['rom'], _title_cache['layers'] = rom, fe4title.read_layers(bytearray(rom))
    return _title_cache['layers']


def title_blob(name):
    p = project()
    return p.blob(f'{fe4title.FOLDER}/{name}.png').data if p else None


def title_layers(src):
    lay = dict(title_game())
    if src != 'game' and project():
        for name in fe4title.LAYERS:
            data = title_blob(name)
            if data:
                lay[name] = fe4title.converted(project().path, name, data)[0]
    return lay


def api_title(b, q):
    """The title's three layers: whether the project replaced each, and how the new one fits."""
    need_project()
    out = []
    for name in fe4title.LAYERS:
        data = title_blob(name)
        note = None
        if data:
            try:
                note = fe4title.converted(project().path, name, data)[1]
            except ValueError as e:
                note = {'error': str(e)}
        out.append({'name': name, 'custom': data is not None, 'note': note,
                    'ver': '%08x' % zlib.crc32(data) if data else 'rom'})
    return {'layers': out, 'w': fe4title.W, 'h': fe4title.H}


def api_title_set(b, q):
    """Replace a title layer with a PNG (base64, 256x224), hide the emblem, or go back to the game's."""
    p = need_project()
    name = b.get('layer')
    if name not in fe4title.LAYERS:
        raise ValueError('No such part of the title.')
    rel = f'{fe4title.FOLDER}/{name}.png'
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    if b.get('hide'):
        data = fe4gfx.png(fe4title.W, fe4title.H, [bytes(4 * fe4title.W)] * fe4title.H)
    else:
        try:
            data = base64.b64decode(b['png'])
        except (KeyError, ValueError):
            raise ValueError('That file could not be read as a PNG picture.')
    note = fe4title.converted(p.path, name, data)[1]       # ValueError: the reason it doesn't fit
    p.set_blob(rel, data)
    return {'ok': True, 'note': note}


def chaptitle_data():
    p = project()
    blob = p.blob(fe4chaptitle.FILE).data if p else None
    return fe4chaptitle.parse(blob)


def api_chaptitle(b, q):
    """A chapter's title card: the game's label and title pictures, the project's new title."""
    rom = rom_data()
    if rom is None:
        raise ValueError('Open a ROM first.')
    if not fe4chaptitle.known(rom):
        raise ValueError("This ROM's chapter title card is not the one the editor knows.")
    ch = int(q.get('ch', ['0'])[0])
    out = fe4chaptitle.info(rom, chaptitle_data(), ch)
    out.update(out.pop('chapters')[0])
    return out


def api_chaptitle_set(b, q):
    """{ch, text, px} (px: 256x24 colour numbers 0-8 as a string), or {ch, reset: true}.  One undo step."""
    p = need_project()
    rom = rom_data()
    ch = int(b.get('ch', -1))
    if not 0 <= ch < fe4chaptitle.CHAPTERS:
        raise ValueError('No such chapter.')
    data = chaptitle_data()
    if b.get('reset'):
        data.pop(ch, None)
    else:
        text = ' '.join(str(b.get('text', '')).split())
        if not text:
            raise ValueError('Type the title first.')
        if len(text) > fe4chaptitle.TEXT_MAX:
            raise ValueError(f'Titles can be at most {fe4chaptitle.TEXT_MAX} letters long.')
        fe4chaptitle.encode(text)                              # ValueError: a letter the game lacks
        px = str(b.get('px', ''))
        sheet, mp = fe4chaptitle.read(rom)
        fe4chaptitle.build_card(sheet, mp, ch, px)              # ValueError: doesn't fit
        data[ch] = {'text': text, 'px': px}
        if b.get('look'):
            data[ch]['look'] = {k: b['look'][k] for k in ('font', 'size', 'width') if k in b['look']}
    p.set_blob(fe4chaptitle.FILE, fe4chaptitle.dump(data))
    return {'ok': True}


def title_image(which, src, scale):
    lay = title_layers(src)
    return fe4title.png(lay, None if which == 'title' else which, scale)


# ---------------------------------------------------------------- skill icons (kit v54)

def skill_icon_tiles():
    """{icon name (as the icon column takes it): sprite tile} for the game's icons and the unused ones."""
    import fe4skills
    rom = rom_data()
    if rom is None:
        return {}
    out = {k: v for k, v in fe4skillmenu.icon_names(rom, fe4skills.NAMES).items()}
    return {(k if k.startswith('spare') else next((n for n in fe4skills.NAMES[1:] if n and n.lower() == k), k)): v
            for k, v in out.items()}


def skill_icon_image(which, scale):
    """/gfx/skillicon/<tile>.png (the game's) or /gfx/skillicon/mine/<file>.png (the project's picture,
    in the icons' colours)."""
    rom = rom_data()
    if rom is None:
        return None
    if which.startswith('mine/'):
        p = project()
        data = p.blob(f'{fe4skillmenu.ICON_DIR}/{os.path.basename(which[5:])}.png').data if p else None
        if not data:
            return None
        try:
            px = fe4skillmenu.icon_from_png(rom, data)
        except ValueError:
            return None
        return fe4skillmenu.icon_png(rom, 0x20, scale, px)
    t = int(which, 16) if which.lower().startswith('0x') else int(which)
    if not 0x20 <= t <= 0x6E:
        return None
    return fe4skillmenu.icon_png(rom, t, scale)


def api_skillicon(b, q):
    """A picture of your own for a skill's icon: PNG (base64, 16x16) -> skill_icons/<name>.png."""
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', str(b.get('name') or 'icon')).strip('_').lower() or 'icon'
    try:
        data = base64.b64decode(b['png'])
        fe4skillmenu.icon_from_png(rom, data)
    except (KeyError, ValueError) as e:
        raise ValueError(str(e) if 'icon' in str(e) else 'That file could not be read as a PNG picture.')
    p.set_blob(f'{fe4skillmenu.ICON_DIR}/{name}.png', data)
    return {'file': f'{name}.png'}


def table_json(name):
    t = project().table(name)
    if t is None:
        raise KeyError(f'no table {name}')
    rows = []
    for i, r in enumerate(t.rows):
        x = dict(r)
        x['_row'] = i
        if name.startswith('units_') and name != 'units_generic':
            x['_portrait'] = unit_portrait(name, r)
        rows.append(x)
    return {'name': name, 'fields': t.fields, 'rows': rows}


# value checks: (min, max) for numbers; a function for the rest
STAT_FIELDS = ['hp', 'str', 'mag', 'skl', 'spd', 'def', 'res', 'lck']
NUMERIC = {f: (0, 255) for f in STAT_FIELDS + ['g_' + s for s in STAT_FIELDS] + ['level', 'authority', 'gold_x1000',
                                                                                 'class', 'item1', 'item2', 'item3',
                                                                                 'gender', 'name_id', 'slot']}
NUMERIC.update({f: (0, 255) for f in ['base_hp', 'base_str', 'base_mag', 'base_skl', 'base_spd', 'base_def',
                                       'base_res', 'move', 'mt', 'hit', 'wt', 'uses', 'min_range', 'max_range']})
NUMERIC.update({'x': (0, 63), 'y': (0, 63), 'orders': (0, 255), 'leader_flag': (0, 255), 'army_slot': (0, 255),
                'char_id': (0, 65535), 'gold': (0, 65535)})
NUMERIC.update({'price': (0, 65535), 'level': (1, 30), 'gender': (0, 1), 'authority': (0, 5), 'move': (1, 15)})
NUMERIC.update({'blood_lock': (0, 15), 'staff_effect': (0, 255), 'weapon_type': (0, 9), 'effective': (0, 255),
                'special': (0, 255), 'special_arg': (0, 255), 'item_type': (0, 121), 'stat_bonus': (0, 255),
                'melee': (0, 65535), 'ranged': (0, 65535)})


def check_value(table, field, value):
    """Returns (value, warning) or raises ValueError with a message for the person."""
    v = value.strip() if isinstance(value, str) else str(value)
    if table == 'music':
        if field != 'song' or not v.isdigit() or not 0 <= int(v) <= fe4music.SONGS:
            raise ValueError(f'Songs are 1 to {fe4music.SONGS}.')
        return str(int(v)), None
    if table == 'music_bosses':
        if field != 'unit' or not v.isdigit() or not 0 <= int(v) <= 0x3FF:
            raise ValueError('Pick a unit.')
        return str(int(v)), None
    if table == 'locations' and field == 'gold':
        if v == '':
            return v, None
        if not v.isdigit() or not 1 <= int(v) <= 50000:
            raise ValueError('Village gold is 1 to 50,000.')
        return str(int(v)), None
    if table == 'locations' and field == 'facilities':
        import fe4locations
        try:
            fe4locations._fac_parse(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v or '-', None
    if table == 'locations' and field == 'shop':
        parts = [x.strip() for x in v.split(';') if x.strip()]
        if not all(x.isdigit() and int(x) < L.INSTANCE_COUNT for x in parts):
            raise ValueError(f'A shop lists item copies 0 to {L.INSTANCE_COUNT - 1}.')
        if len(set(parts)) != len(parts):
            raise ValueError('Each item copy exists once, so a shop can\'t sell the same copy twice.')
        return ';'.join(parts), None
    if table == 'lovers' and field == 'start':
        lv = v.lower()
        if lv in ('no', 'never'):
            return 'no', None
        if not v.isdigit() or not (int(v) == 499 or (0 <= int(v) <= 2530 and int(v) % 10 == 0)):
            raise ValueError('Starting love is 0 to 2530 in steps of 10 (500 = lovers), 499, or "no".')
        return str(int(v)), None
    if table == 'lovers' and field == 'growth':
        if not re.fullmatch(r'-?\d+', v) or not -127 <= int(v) <= 127:
            raise ValueError('Love per turn is -127 to 127.')
        return str(int(v)), None
    if table == 'gen2_rules' and field == 'value':
        if not v.isdigit():
            raise ValueError('Enter a whole number.')
        return str(int(v)), None
    if table == 'spells' and field in ('spell', 'spell_far'):
        n = fe4battle.spell_count(spell_rom()[0])
        if not v.isdigit() or not 0 <= int(v) < n:
            raise ValueError(f'Spells are 0 to {n - 1}.')
        return str(int(v)), None
    if table == 'spells' and field == 'item':
        t = project().table('spells')
        if not v.isdigit() or not 0 <= int(v) <= 254:
            raise ValueError('Pick an item.')
        return str(int(v)), None
    if table == 'battle_anims' and field in ('anim', 'body', 'upper', 'palette'):
        hi = fe4battle.id_limits(rom_data())[field]
        extra = dict(zip(('anim', 'body'), battle_ids())).get(field, set())
        if not v.isdigit() or not (0 <= int(v) <= hi or int(v) in extra):
            raise ValueError(f'Enter a number from 0 to {hi}' + (' or one of your redrawn looks.' if extra else '.'))
        return str(int(v)), None
    if table == 'map_terrain' and field == 'terrain':
        if not v.isdigit() or not 0 <= int(v) <= 255:
            raise ValueError('Terrain is a number from 0 to 255.')
        return str(int(v)), None
    if table == 'map_sprites' and field == 'sprite':
        try:
            return fe4sprites.sprite_name(fe4sprites.parse_sprite(v)), None
        except ValueError as e:
            raise ValueError(str(e))
    if field in NUMERIC:
        lo, hi = NUMERIC[field]
        if not v.lstrip('-').isdigit():
            raise ValueError('Enter a whole number.')
        n = int(v)
        if not lo <= n <= hi:
            raise ValueError(f'Enter a number from {lo} to {hi}.')
        return str(n), None
    if field.startswith('rank_'):
        if v.upper() not in ('A', 'B', 'C', '-', ''):
            raise ValueError('Weapon rank is A, B, C or - (none).')
        return (v.upper() or '-'), None
    if field == 'holy_blood':
        parts = [p for p in v.split(';') if p]
        for p in parts:
            b, _, k = p.partition(':')
            if b not in L.BLOODS or k not in ('minor', 'major'):
                raise ValueError(f'"{p}": holy blood is written like Baldur:major;Naga:minor.')
        return ';'.join(parts), None
    if field == 'skills' and table in ('items', 'rings'):
        st_ = project().table('skills')
        ok = {r['name'] for r in (st_.rows if st_ else []) if (r.get('item_bit') or '').strip() != ''}
        bad = [s_ for s_ in v.split(';') if s_ and s_ not in ok]
        if bad:
            raise ValueError('Items can\'t carry ' + ', '.join(bad) + '. Item skills: ' + ', '.join(sorted(ok)) + '.')
        return v, None
    if field == 'skills':
        known = set(project().skill_names())
        bad = [s for s in v.split(';') if s and s not in known]
        if bad:
            raise ValueError('Unknown skill: ' + ', '.join(bad))
        return v, None
    return v, None


# ---------------------------------------------------------------- HTTP
TOKEN = secrets.token_urlsafe(16)


class Server(ThreadingHTTPServer):
    # The page loads a dozen scripts at once.  Windows refuses connections past the listen queue (5 by
    # default) instead of letting them wait, which left the editor blank on some PCs (kit v47).
    request_queue_size = 128
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'     # keep connections open: every reply carries Content-Length
    server_version = 'BuilderOfTheHolyWar/' + VERSION

    def log_message(self, fmt, *args):
        if os.environ.get('FE4STUDIO_LOG'):
            sys.__stderr__.write('%s %s\n' % (self.address_string(), fmt % args))

    def _host_ok(self):
        host = (self.headers.get('Host') or '').split(':')[0]
        return host in ('127.0.0.1', 'localhost')

    def _send(self, code, body, ctype='application/json; charset=utf-8', cache=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'max-age=3600' if cache else 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {'error': 'forbidden'})
        u = urlparse(self.path)
        path = unquote(u.path)
        if path.startswith('/api/'):
            if self.headers.get('X-Studio-Token') != TOKEN:
                return self._send(403, {'error': 'This page is out of date. Close it and start the editor again.'})
            return self.api('GET', path[5:], parse_qs(u.query), None)
        if path.startswith('/gfx/portrait/'):
            rom = rom_data()
            try:
                n = int(path.rsplit('/', 1)[1].split('.')[0])
                scale = int(parse_qs(u.query).get('s', ['1'])[0])
            except ValueError:
                return self._send(404, 'no')
            data = portrait_image(n, max(1, min(scale, 4)), sheet=path.startswith('/gfx/portrait/sheet'))
            # ?c=<version> URLs (the Portraits page) change whenever the picture does, so they can be cached
            return (self._send(200, data, 'image/png', cache='c' in parse_qs(u.query)) if data
                    else self._send(404, 'no'))
        if path.startswith('/gfx/mapbg/'):
            q = parse_qs(u.query)
            try:
                data = mapbg_image(int(path.rsplit('/', 1)[1].split('.')[0]), max(1, min(int(q.get('s', ['1'])[0]), 3)))
            except (ValueError, KeyError):
                return self._send(404, 'no')
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/mapfx/'):
            q = parse_qs(u.query)
            try:
                sp = int(path.rsplit('/', 1)[1].split('.')[0])
                data = mapfx_image(sp, max(1, min(int(q.get('s', ['1'])[0]), 6)), indexed=path.endswith('.idx.png'))
            except (ValueError, KeyError):
                return self._send(404, 'no')
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/mbplay/'):
            q = parse_qs(u.query)
            try:
                fig, k, sec = path.rsplit('/', 1)[1].split('.')[0].split('_')
                data = mapbattle_strip(int(fig, 16), int(k), int(sec), int(q.get('a', ['0'])[0]),
                                       max(1, min(int(q.get('s', ['1'])[0]), 4)))
            except ValueError:
                return self._send(404, 'no')
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/mbsheet/'):
            q = parse_qs(u.query)
            try:
                fig, k = path.rsplit('/', 1)[1].split('.')[0].split('_')
                army = int(q.get('a', ['0'])[0])
                scale = max(1, min(int(q.get('s', ['1'])[0]), 6))
                data = mapbattle_image(int(fig, 16), int(k), army, scale, indexed=path.endswith('.idx.png'))
            except ValueError:
                return self._send(404, 'no')
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/skillicon/'):
            q = parse_qs(u.query)
            try:
                with lock:
                    data = skill_icon_image(path[len('/gfx/skillicon/'):].rsplit('.png', 1)[0],
                                            max(1, min(int(q.get('s', ['1'])[0]), 6)))
            except ValueError:
                return self._send(404, 'no')
            return self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no')
        if path.startswith('/gfx/title/'):
            q = parse_qs(u.query)
            which = path.rsplit('/', 1)[1].split('.')[0]
            if which not in ('title',) + fe4title.LAYERS:
                return self._send(404, 'no')
            try:
                with lock:
                    data = title_image(which, q.get('src', ['project'])[0], max(1, min(int(q.get('s', ['1'])[0]), 4)))
            except (ValueError, RuntimeError):
                return self._send(404, 'no')
            return self._send(200, data, 'image/png', cache='c' in q)
        if path.startswith('/music/'):
            try:
                song = int(path.rsplit('/', 1)[1].split('.')[0])
                got = music_audio(song)
            except (ValueError, KeyError, RuntimeError):
                return self._send(404, 'no')
            return self._send(200, got[0], got[1]) if got else self._send(404, 'no')
        if path.startswith('/gfx/walk/'):
            q = parse_qs(u.query)
            try:
                sid = fe4sprites.parse_sprite(path.rsplit('/', 1)[1].split('.')[0])
                army = int(q.get('a', ['0'])[0])
                scale = max(1, min(int(q.get('s', ['1'])[0]), 8))
                data = walk_image(sid, army, scale, indexed=path.endswith('.idx.png'))
            except ValueError:
                return self._send(404, 'no')
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/sprite/'):
            q = parse_qs(u.query)
            try:
                name = path.rsplit('/', 1)[1].split('.')[0]
                sid = fe4sprites.parse_sprite(name)
                army = int(q.get('a', ['0'])[0])
                scale = max(1, min(int(q.get('s', ['1'])[0]), 8))
            except ValueError:
                return self._send(404, 'no')
            data = sprite_image(sid, army, scale, indexed=path.endswith('.idx.png'))
            return (self._send(200, data, 'image/png', cache='c' in q) if data else self._send(404, 'no'))
        if path.startswith('/gfx/spellsheet/') or path.startswith('/gfx/spellview/'):
            q = parse_qs(u.query)
            try:
                n = int(q.get('r', q.get('s', ['-1']))[0])
                scale = max(1, min(int(q.get('x', ['1'])[0]), 4))
                c = int(q['c'][0]) if 'c' in q else None
                data = spell_sheet(n, scale, c) if 'spellsheet' in path else spell_preview(n, scale, c is not None)
            except (ValueError, KeyError):
                return self._send(404, 'no')
            return self._send(200, data, 'image/png') if data else self._send(404, 'no')
        if path.startswith('/gfx/battledraw/'):
            q = parse_qs(u.query)
            try:
                data = battle_drawing(int(q.get('row', ['-1'])[0]))
            except (ValueError, KeyError):
                return self._send(404, 'no')
            return self._send(200, data, 'image/png') if data else self._send(404, 'no')
        if path.startswith('/gfx/battle/'):
            q = parse_qs(u.query)
            try:
                a, bd, up, pl, it = (int(q.get(k, ['-1'])[0]) for k in ('a', 'b', 'u', 'p', 'i'))
            except ValueError:
                return self._send(404, 'no')
            got = battle_strip(a, bd, up, pl, it)
            return self._send(200, got[0], 'image/png', cache=True) if got else self._send(404, 'no')
        if path.startswith('/gfx/tiles/'):
            rom = rom_data()
            try:
                ch = int(path.rsplit('/', 1)[1].split('.')[0])
            except ValueError:
                return self._send(404, 'no')
            if rom is None or not 0 <= ch < fe4maps.MAP_COUNT:
                return self._send(404, 'no')
            if tiles_version(ch) == 'rom':
                return self._send(200, fe4gfx.map_atlas(rom, ch)[0], 'image/png', cache=True)
            g = chapter_gfx(ch)
            return self._send(200, g.atlas_png(), 'image/png', cache='c' in parse_qs(u.query))
        if path.startswith('/gfx/mappicture/'):
            try:
                ch = int(path.rsplit('/', 1)[1].split('.')[0])
            except ValueError:
                return self._send(404, 'no')
            p = project()
            m = p.map(ch) if p and rom_data() is not None and 0 <= ch < fe4maps.MAP_COUNT else None
            if m is None:
                return self._send(404, 'no')
            return self._send(200, fe4mapset.map_png(chapter_gfx(ch), m.words, box=map_area(ch)), 'image/png')
        if path.startswith('/gfx/tile/'):
            q = parse_qs(u.query)
            try:
                _, _, _, ch, k = path.split('.')[0].split('/')
                ch, k = int(ch), int(k)
                scale = max(1, min(int(q.get('s', ['1'])[0]), 16))
            except ValueError:
                return self._send(404, 'no')
            if rom_data() is None or not 0 <= ch < fe4maps.MAP_COUNT or not 0 <= k < 1024:
                return self._send(404, 'no')
            return self._send(200, chapter_gfx(ch).metatile_png(k, scale), 'image/png', cache='c' in q)
        # static files
        if path in ('/', ''):
            path = '/index.html'
        f = os.path.normpath(os.path.join(STATIC, path.lstrip('/')))
        if not f.startswith(os.path.normpath(STATIC) + os.sep) or not os.path.isfile(f):
            return self._send(404, 'not found', 'text/plain')
        ctype = mimetypes.guess_type(f)[0] or 'application/octet-stream'
        if f.endswith('.js'):
            ctype = 'text/javascript; charset=utf-8'
        with open(f, 'rb') as fh:
            self._send(200, fh.read(), ctype, cache=f.endswith('.woff2'))

    def do_POST(self):
        if not self._host_ok() or self.headers.get('X-Studio-Token') != TOKEN:
            return self._send(403, {'error': 'This page is out of date. Close it and start the editor again.'})
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self._send(400, {'error': 'bad request'})
        u = urlparse(self.path)
        return self.api('POST', unquote(u.path)[5:], parse_qs(u.query), body)

    def api(self, method, name, q, body):
        try:
            res = API.get((method, name))
            if res is None:
                return self._send(404, {'error': 'no such call: ' + name})
            with lock:
                out = res(body or {}, q)
            return self._send(200, out)
        except (ValueError, KeyError, RuntimeError) as e:
            return self._send(400, {'error': str(e).strip("'")})
        except Exception as e:     # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})


def need_project():
    if project() is None:
        raise RuntimeError('Open or create a project first.')
    return project()


def api_session(b, q):
    p = project()
    rp = rom_path()
    rom_ok = None
    if rp and rom_data() is not None:
        rom_ok = L.sha1(rom_data()) == L.EXPECTED_SHA1
    return {'app': APP, 'version': VERSION, 'project': p.path if p else None,
            'projectName': os.path.basename(os.path.normpath(p.path)) if p else None,
            'rom': rp, 'romIsNaga': rom_ok, 'recent': [r for r in settings.get('recent', []) if os.path.isdir(r)],
            'dirty': bool(p and p.dirty()), 'canUndo': bool(p and p.undo_stack), 'canRedo': bool(p and p.redo_stack),
            'port': port_exe(), 'hoverStats': bool(settings.get('hover_stats', False)), 'msu': bool(settings.get('msu', False)),
            'job': job_json()}


def job_json():
    j = state['job']
    if not j:
        return None
    return {k: j[k] for k in ('id', 'what', 'running', 'ok', 'log')}


def api_ping(b, q):
    state['last_ping'] = time.time()
    return {'ok': True}


def api_table(b, q):
    need_project()
    return table_json(q.get('name', [''])[0] or b.get('name'))


def api_tables(b, q):
    need_project()
    return {n: table_json(n) for n in b.get('names', []) if n in TABLES and project().table(n) is not None}


def api_set(b, q):
    p = need_project()
    table, row, field = b['table'], int(b['row']), b['field']
    if table not in TABLES:
        raise ValueError('That table can\'t be edited here.')
    value, warn = check_value(table, field, b.get('value', ''))
    if table == 'music' and value == '0' and p.table('music').rows[row].get('table') != 'opening':
        raise ValueError(f'Songs are 1 to {fe4music.SONGS}.')
    p.set(table, row, field, value)
    out = {'ok': True, 'value': value, 'warning': warn}
    if table.startswith('units_') and field in ('portrait', 'char_id'):
        out['portrait'] = unit_portrait(table, p.table(table).rows[row])
    return out


def ops_json(ops):
    """What an undo or redo touched, so the page can reload just that."""
    if ops is None:
        return {'change': None}
    tables = sorted({o[1] for o in ops if o[0] in ('cell', 'rows')})
    maps = sorted({o[1] for o in ops if o[0] == 'map'})
    cells = [{'table': o[1], 'row': o[2], 'field': o[3]} for o in ops if o[0] == 'cell'][:50]
    evts = sorted({o[1] for o in ops if o[0] in ('evt', 'lines')})
    msgs = sorted({o[1] for o in ops if o[0] in ('msg', 'msgadd', 'msgdel')})
    blobs = sorted({o[1] for o in ops if o[0] == 'blob'})
    return {'change': {'tables': tables, 'maps': maps, 'cells': cells, 'events': evts, 'messages': msgs, 'files': blobs,
                       'count': len(ops)}}


def api_undo(b, q):
    return ops_json(need_project().undo())


def api_redo(b, q):
    return ops_json(need_project().redo())


def api_setmany(b, q):
    """Several fields as one undo step: [{table, row, field, value}]."""
    p = need_project()
    changes = []
    for c in b.get('changes', []):
        if c['table'] not in TABLES:
            raise ValueError('That table can\'t be edited here.')
        value, _ = check_value(c['table'], c['field'], c.get('value', ''))
        changes.append((c['table'], int(c['row']), c['field'], value))
    p.set_many(changes)
    return {'ok': True, 'values': [v for _, _, _, v in changes]}


def api_save(b, q):
    need_project().save()
    return {'ok': True}


def api_open(b, q):
    open_project(b['path'])
    return api_session(b, q)


def api_set_rom(b, q):
    path = b['path']
    try:
        _, data = L.load_rom(path)
    except OSError as e:
        raise ValueError(f"Couldn't read that file: {e}")
    if len(data) < 0x400000 or data[0x40FFC0:0x40FFCB] != b'FIREEMBLEM4' and b'FIREEMBLEM' not in data[0xFFC0:0xFFD5]:
        pass
    settings['rom'] = path
    save_settings(settings)
    return api_session(b, q)


def api_new_project(b, q):
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    out = os.path.join(b['folder'], b['name'].strip())
    if not b['name'].strip():
        raise ValueError('Give the project a name.')
    if os.path.exists(out) and os.listdir(out):
        raise ValueError(f'{out} already exists and isn\'t empty.')

    def go():
        fe4hack.extract(rom, out)
        with lock:
            open_project(out)
        return out
    return job_json_of(run_job('Reading the ROM into a new project', go))


def job_json_of(job):
    return {k: job[k] for k in ('id', 'what', 'running', 'ok', 'log')}


def api_job(b, q):
    return {'job': job_json()}


def api_build(b, q):
    p = need_project()
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    out = b.get('out') or settings.get('out', {}).get(p.path) or (os.path.normpath(p.path) + '.smc')
    settings.setdefault('out', {})[p.path] = out
    save_settings(settings)
    p.save()
    ips = os.path.splitext(out)[0] + '.ips'
    hover = bool(settings.get('hover_stats', False))
    msu = bool(settings.get('msu', False))

    def go():
        fe4hack.build(rom, p.path, out, ips, hover, msu=msu)
        if msu:
            write_msu_tracks(p.path, out)
        return out
    return job_json_of(run_job(f'Building {os.path.basename(out)}', go))


def write_msu_tracks(proj, out):
    """name.msu and name-N.pcm next to the built ROM, from the project's music files (the PC port converts)."""
    base = os.path.splitext(out)[0]
    files = fe4music.music_files(proj)
    open(base + '.msu', 'wb').close()
    exe = port_exe()
    can = bool(exe and port_knows(exe, b'--make-pcm'))
    done, skipped = 0, []
    for song, f in sorted(files.items()):
        src = os.path.join(proj, fe4music.FOLDER, f)
        dst = '%s-%d.pcm' % (base, song)
        if f.lower().endswith('.pcm'):
            shutil.copyfile(src, dst)
            done += 1
            continue
        if not can:
            skipped.append(f)
            continue
        flags = 0x08000000 if sys.platform.startswith('win') else 0      # CREATE_NO_WINDOW
        r = subprocess.run([exe, '--make-pcm', src, dst], capture_output=True, creationflags=flags, timeout=600)
        if r.returncode == 0 and os.path.exists(dst):
            done += 1
        else:
            skipped.append(f)
    print(f'MSU-1: {os.path.basename(base)}.msu and {done} track(s) next to the ROM')
    if skipped:
        print('MSU-1: not converted (needs the PC port 0.11 or newer, from FE4Port.zip): ' + ', '.join(skipped))


def _patch_name(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', (s or '').strip()).strip(' .')
    return s[:60]


def api_ipspatch(b, q):
    """Create IPS patch: {name, author?, notes?, out?} -> builds, writes <out>.ips and a <out>.txt
    read-me next to it (what it is, which ROM it needs, how to apply it). Runs as a job."""
    import zlib
    p = need_project()
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    name = _patch_name(b.get('name')) or os.path.basename(os.path.normpath(p.path))
    author, notes = (b.get('author') or '').strip()[:80], (b.get('notes') or '').strip()[:4000]
    out = b.get('out') or os.path.join(os.path.dirname(os.path.normpath(p.path)), name + '.ips')
    if not out.lower().endswith('.ips'):
        out += '.ips'
    settings.setdefault('patch', {})[p.path] = {'name': name, 'author': author, 'notes': notes, 'out': out}
    save_settings(settings)
    p.save()
    hover = bool(settings.get('hover_stats', False))

    def go():
        d = os.path.join(p.path, '_patch')
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, 'patched.smc')
        fe4hack.build(rom, p.path, tmp, out, hover)
        copier, clean = L.load_rom(rom)
        _, new = L.load_rom(tmp)
        # check the patch: apply it to the clean ROM and compare
        if fe4hack.apply_ips(bytes(copier) + bytes(clean), open(out, 'rb').read()) != bytes(copier) + bytes(new):
            raise RuntimeError('the patch did not reproduce the built ROM, so do not use it (please report this)')
        sha = L.sha1(clean)
        hdr = 'with a 512-byte copier header' if copier else 'without a copier header (headerless)'
        lines = [name, '=' * len(name)]
        if author:
            lines.append('by ' + author)
        lines.append('')
        if notes:
            lines += [notes, '']
        lines += ['How to play it',
                  '--------------',
                  '1. You need your own copy of Fire Emblem: Genealogy of the Holy War (Seisen no Keifu)',
                  '   with the Project Naga English translation. This patch is for that ROM ' + hdr + ':',
                  '     SHA-1 (no header): ' + sha,
                  '     CRC32 (no header): %08X' % (zlib.crc32(bytes(clean)) & 0xFFFFFFFF),
                  ]
        if sha != L.EXPECTED_SHA1:
            lines.append('   (Not the usual Naga ROM: the usual one has SHA-1 %s.)' % L.EXPECTED_SHA1)
        lines += ['2. Apply %s with an IPS patcher such as Flips or Lunar IPS, or give it the same' % os.path.basename(out),
                  '   name as the ROM and put it next to it (most emulators then load it by themselves).',
                  '3. Play the patched ROM in an emulator, or in the FE4 PC port.',
                  '',
                  'The patch holds only the changes, not the game: the ROM is not included.',
                  'Made with Builder of the Holy War v%s on %s.' % (VERSION, time.strftime('%Y-%m-%d')),
                  ]
        txt = os.path.splitext(out)[0] + '.txt'
        with open(txt, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write('\n'.join(lines) + '\n')
        os.remove(tmp)
        try:
            os.rmdir(d)
        except OSError:
            pass
        print('wrote', txt)
        print('patch checked: applying it to your ROM gives the built ROM (%d bytes of patch)' % os.path.getsize(out))
        return out
    return job_json_of(run_job('Creating IPS patch', go))


def api_patchinfo(b, q):
    """What the Create IPS patch dialog starts with: last values for this project."""
    p = need_project()
    last = settings.get('patch', {}).get(p.path) or {}
    name = last.get('name') or os.path.basename(os.path.normpath(p.path))
    return {'name': name, 'author': last.get('author', ''), 'notes': last.get('notes', ''),
            'out': last.get('out') or os.path.join(os.path.dirname(os.path.normpath(p.path)), name + '.ips')}


def api_reveal(b, q):
    """Show a file in the system file manager."""
    path = b.get('path') or ''
    if not os.path.exists(path):
        raise ValueError('That file is gone.')
    if os.name == 'nt':
        subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', path])
    else:
        subprocess.Popen(['xdg-open', os.path.dirname(path)])
    return {'ok': True}


# ---------------------------------------------------------------- battle animations
BATTLE_ITEMS = {0: 0, 1: 28, 2: 40, 3: 49, 4: 58, 5: 31, 6: 45, 7: 62, 8: 88, 9: 0}
_battle_cache = {}


def _project_reader(rel):
    p = project()
    if p is None or not rel:
        return None
    return p.blob(rel).data


_battle_rom = {'key': None, 'rom': None}


def battle_rom():
    """The clean ROM, or a copy with the project's redrawn battle looks written in (for previews)."""
    rom = rom_data()
    p = project()
    if rom is None or p is None:
        return rom
    looks = fe4battle.read_looks(_project_reader)
    if not looks:
        return rom
    import hashlib
    h = hashlib.sha1(json.dumps(looks, sort_keys=True).encode())
    for lk in looks:
        h.update((_project_reader(lk['png']) if lk.get('png') else None) or b'')
    key = h.hexdigest()
    if _battle_rom['key'] != key:
        r = bytearray(rom)
        with contextlib.redirect_stdout(io.StringIO()):
            fe4battle.apply_custom(r, _project_reader, L.FreeSpace())
        _battle_rom.update(key=key, rom=bytes(r))
    return _battle_rom['rom']


def battle_ids():
    """Animation and body ids a row may use: the game's plus the project's redrawn looks."""
    looks = fe4battle.read_looks(_project_reader) if project() else []
    return ({int(x['anim']) for x in looks}, {int(x['body']) for x in looks})


def battle_strip(a, bd, up, pl, it):
    """(png bytes, info) for one look; cached by the look and the project's redrawn looks."""
    try:
        rom = battle_rom()
    except SystemExit:
        return None
    if rom is None:
        return None
    lim = fe4battle.id_limits(rom)
    ca, cb = battle_ids()
    if not ((0 <= a <= lim['anim'] or a in ca) and (0 <= bd <= lim['body'] or bd in cb)
            and 0 <= up <= lim['upper'] and 0 <= pl <= lim['palette']):
        return None
    key = (a, bd, up, pl, it, _battle_rom['key'] if (a in ca or bd in cb) else None)
    if key not in _battle_cache:
        try:
            look = fe4battle.Look(rom, a, bd, up, pl, it if 0 <= it < 256 else None)
            png, cell, origin = look.strip()
        except Exception as e:                # noqa: BLE001  (a bad combination: show nothing, say why)
            _battle_cache[key] = (None, {'error': f'{type(e).__name__}: {e}'})
        else:
            _battle_cache[key] = (png, {'cell': cell, 'origin': origin, 'frames': len(look.layouts),
                                                    'motions': [[list(c) for c in m] for m in look.motions]})
        if len(_battle_cache) > 300:
            _battle_cache.pop(next(iter(_battle_cache)))
    png, info = _battle_cache[key]
    return (png, info) if png else None


def api_battleanims(b, q):
    """The class/weapon -> battle animation table, with names, for the Battle animations page."""
    p = need_project()
    rom0 = rom_data()
    if rom0 is not None:     # read the spell pictures in the background; the Spell pictures view needs them
        threading.Thread(target=lambda: fe4spellfx.survey(spell_rom()[0]), daemon=True).start()
    t = p.table('battle_anims')
    if t is None:
        raise KeyError('This project has no battle_anims.csv; reopen it with this version to add one.')
    rom = rom_data()
    ct = p.table('classes')
    cnames = {int(r['index']): r.get('_name', '') for r in ct.rows} if ct else {}
    chars = {}
    for tn in ('units_playable', 'units_children', 'units_npc'):
        tt = p.table(tn)
        for r in tt.rows if tt else []:
            if (r.get('char_id') or '').isdigit():
                chars.setdefault(int(r['char_id']), r.get('_name', ''))
    it = p.table('items')
    items = [[int(r['index']), r.get('_name', ''), r.get('weapon_type', '')] for r in it.rows] if it else []
    custom = {int(x['anim']): x for x in fe4battle.read_looks(_project_reader)}
    rows = [{**r, '_redrawn': bool(int(r['anim']) in custom), '_class': cnames.get(int(r['class']), r.get('_class', '')),
             '_char': chars.get(int(r['character']), '') if r['character'] not in ('', '0') else ''} for r in t.rows]
    return {'rows': rows, 'limits': fe4battle.id_limits(rom), 'weapons': {str(k): v for k, v in fe4battle.WEAPON_KINDS.items()},
            'defaultItems': {str(k): v for k, v in BATTLE_ITEMS.items()}, 'items': items}


def _row_look(r):
    return tuple(int(r[k]) for k in ('anim', 'body', 'upper', 'palette'))


def _custom_for(r):
    """The redrawn look a row uses (by its animation id), or None."""
    for i, lk in enumerate(fe4battle.read_looks(_project_reader)):
        if int(lk['anim']) == int(r['anim']):
            return i, lk
    return None


def battle_drawing(row):
    """The PNG to draw on for a row: its look's stored drawing, else the frames as they are."""
    p = need_project()
    t = p.table('battle_anims')
    r = t.rows[row]
    c = _custom_for(r)
    rom = rom_data()
    if c:
        lk = c[1]
        if lk.get('png') and _project_reader(lk['png']):
            return _project_reader(lk['png'])
        look = fe4battle.extended_look(rom, tuple(int(x) for x in lk['from']), lk.get('extra'))
        return fe4battle.Drawing(look).png()
    a, bd, up, pl = _row_look(r)
    return fe4battle.Drawing(fe4battle.Look(rom, a, bd, up, pl)).png()


def _edit_look(row, every, change):
    """Make (or update) the redrawn look a row uses and point the row(s) at it, as one undo step.
    change(look dict, base) edits 'png' bytes (key '_png'), 'motions' or 'extra' in place."""
    import json as _json
    p = need_project()
    t = p.table('battle_anims')
    r = t.rows[row]
    looks = [dict(x) for x in fe4battle.read_looks(_project_reader)]
    c = _custom_for(r)
    if c:
        i = c[0]
    else:
        base = _row_look(r)
        aid = max([fe4battle.ANIM_N - 1] + [int(x['anim']) for x in looks]) + 1
        bid = max([fe4battle.BODY_N - 1] + [int(x['body']) for x in looks]) + 1
        if aid > 0xFE or bid > 0xFE:
            raise ValueError('There is no room for more redrawn looks.')
        looks.append({'anim': aid, 'body': bid, 'from': list(base), 'png': None, 'motions': {}, 'extra': [],
                      'name': r.get('_class', '')})
        i = len(looks) - 1
    lk = looks[i]
    lk.setdefault('motions', {})
    lk.setdefault('extra', [])
    base = tuple(int(x) for x in lk['from'])
    old_png = _project_reader(lk['png']) if lk.get('png') else None
    lk['_png'] = old_png
    change(lk, base)
    new_png = lk.pop('_png')
    if new_png is not None and not lk.get('png'):
        lk['png'] = f'battle/look_{int(lk["anim"]):02X}.png'
    try:
        got = fe4battle.import_drawing(rom_data(), base, new_png, lk['motions'], lk['extra'])
    except ValueError as e:
        raise ValueError(str(e))
    ops = [('blob', fe4battle.LOOKS, p.blob(fe4battle.LOOKS).data, _json.dumps(looks, indent=1).encode())]
    if new_png is not None and new_png != old_png:
        ops.append(('blob', lk['png'], p.blob(lk['png']).data, new_png))
    look_now = _row_look(r)
    rows = [k for k, x in enumerate(t.rows) if (_row_look(x) == look_now if every else k == row)]
    for k in rows:
        for f, v in (('anim', lk['anim']), ('body', lk['body'])):
            if t.rows[k][f] != str(v):
                ops.append(('cell', 'battle_anims', k, f, t.rows[k][f], str(v)))
    p.edit(ops)
    return {'ok': True, 'changed': got['changed'], 'tiles': got['tiles'], 'anim': lk['anim'], 'body': lk['body'],
            'rows': len(rows)}


def api_battleimport(b, q):
    """Import a drawing for a row: {row, png (base64), every (bool: all rows with this look)}."""
    try:
        data = base64.b64decode(b.get('png', ''), validate=True)
    except ValueError:
        raise ValueError('That file could not be read.')

    def change(lk, base):
        lk['_png'] = data
    return _edit_look(int(b['row']), bool(b.get('every')), change)


def api_battlemotion(b, q):
    """Change one motion of a row's look: {row, motion, steps: [[byte, value]] or null to restore, every}."""
    m = str(int(b['motion']))
    steps = b.get('steps')

    def change(lk, base):
        if steps is None:
            lk['motions'].pop(m, None)
        else:
            lk['motions'][m] = [[int(c), int(v)] for c, v in steps]
    return _edit_look(int(b['row']), bool(b.get('every')), change)


def api_battleframe(b, q):
    """Add a frame to a row's look as a copy of frame {copy}: {row, copy, every}."""
    src = int(b['copy'])

    def change(lk, base):
        look = fe4battle.extended_look(rom_data(), base, lk['extra'])
        if not 0 <= src < len(look.layouts):
            raise ValueError(f'Frame {src} doesn\'t exist.')
        if len(look.layouts) >= 0xE6:
            raise ValueError('An animation can have at most 230 frames.')
        if lk['_png'] is not None:
            lk['_png'] = fe4battle.grow_drawing(lk['_png'], fe4battle.Drawing(look).cell, src)
        lk['extra'].append(src)
    return _edit_look(int(b['row']), bool(b.get('every')), change)


def api_battlespells(b, q):
    """The item -> spell effect table, with names."""
    p = need_project()
    t = p.table('spells')
    if t is None:
        raise KeyError('This project has no spells.csv; reopen it with this version to add one.')
    rom, _ = spell_rom()
    it = p.table('items')
    items = {int(r['index']): r.get('_name', '') for r in it.rows} if it else {}
    names = _spell_label(rom)
    n = fe4battle.spell_count(rom)
    gone = {e['id'] for e in _effects() if e['deleted']}
    return {'rows': [{**r, '_item': items.get(int(r['item']), r.get('_item', ''))} for r in t.rows],
            'spells': [[k, names.get(k, '')] for k in range(n) if k not in gone],
            'items': [[k, v] for k, v in sorted(items.items()) if v]}


_spell_rom = {'key': None}


def _effects():
    try:
        return fe4spellfx.read_effects(_project_reader(f'{fe4spellfx.FOLDER}/{fe4spellfx.EFFECTS}'))
    except ValueError:
        return []


def _steps():
    try:
        return fe4spellfx.read_steps(_project_reader(f'{fe4spellfx.FOLDER}/{fe4spellfx.STEPS}'))
    except ValueError:
        return {}


def _timing():
    try:
        return fe4spellfx.read_json(_project_reader(f'{fe4spellfx.FOLDER}/{fe4spellfx.TIMING}'), fe4spellfx.TIMING)
    except ValueError:
        return {}


def _motions_keyed():
    try:
        return fe4spellfx.read_motions(_project_reader(f'{fe4spellfx.FOLDER}/{fe4spellfx.MOTIONS}'))
    except ValueError:
        return {}


def spell_rom():
    """(ROM with the project's new effects, changed steps and motions written in, their copy map or None)."""
    rom = rom_data()
    eff = _effects() if project() else []
    steps = _steps() if project() else {}
    mots = _motions_keyed() if project() else {}
    if not (eff or steps or mots) or rom is None:
        return rom, None
    key = (id(rom), json.dumps(eff), json.dumps(sorted(steps.items())), json.dumps({k: v.hex() for k, v in sorted(mots.items())}))
    if _spell_rom['key'] != key:
        r = bytearray(rom)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                fxmap = fe4spellfx.apply_effects(r, eff, L.FreeSpace(), steps, fe4spellfx.motions_for_build(mots))
            except SystemExit:
                r, fxmap = bytearray(rom), None
        _spell_rom.update(key=key, rom=bytes(r), fxmap=fxmap)
    return _spell_rom['rom'], _spell_rom['fxmap']


def _spell_pictures():
    """(ROM with new effects, survey records, records per spell, redrawn tile bytes per record, copy map)."""
    rom, fxmap = spell_rom()
    recs, by_spell = fe4spellfx.survey(rom)
    over = {}
    if project():
        for r, d in recs.items():
            png = _project_reader(fe4spellfx.picture_file(r, fxmap))
            if png and d['kind'] != 'map':
                try:
                    over[r] = fe4spellfx.sheet_from_png(png, len(d['data']), fe4spellfx.bpp_of(d['kind']))
                except ValueError:
                    pass
    return rom, recs, by_spell, over, fxmap


SPELL_KINDS = {'tiles4': 'Background tiles · 16 colours', 'tiles2': 'Overlay tiles · 4 colours',
               'sprite': 'Sprite tiles · 16 colours'}


def _spell_label(rom, items=None):
    """{effect: name}: the game's named after the items using them, new ones by their own names."""
    p = project()
    it = p.table('items') if p else None
    items = {int(r['index']): r.get('_name', '') for r in it.rows} if it else dict(enumerate(L.item_names(rom_data())))
    names = fe4battle.spell_names(rom_data(), items)
    for e in _effects() if p else []:
        names[e['id']] = (e['name'] or f'New effect {e["id"]}') + (' (deleted)' if e['deleted'] else '')
    return names


def api_spellgfx(b, q):
    """Spells with pictures ({list: true}), or one spell's pictures ({spell})."""
    rom, recs, by_spell, over, fxmap = _spell_pictures()
    names = _spell_label(rom)
    eff = {e['id']: e for e in _effects()}
    if 'spell' not in q:
        out = []
        for s, rs in by_spell.items():
            pics = [r for r in rs if recs[r]['kind'] != 'map']
            if (pics or s in eff) and not (s in eff and eff[s]['deleted']):
                out.append({'spell': s, 'name': names.get(s, ''), 'pictures': len(pics),
                            'edited': sum(r in over for r in pics), 'new': s in eff})
        return {'spells': out}
    s = int(q['spell'][0])
    pics = []
    for r in by_spell.get(s, []):
        d = recs[r]
        if d['kind'] == 'map':
            continue
        bpp = fe4spellfx.bpp_of(d['kind'])
        w, hh = fe4spellfx.sheet_size(len(d['data']), bpp)
        pics.append({'record': r, 'number': fxmap['pictures'][r][1] if fxmap and r in fxmap['pictures'] else r,
                     'kind': d['kind'], 'label': SPELL_KINDS[d['kind']], 'w': w, 'h': hh,
                     'tiles': len(d['data']) // (8 * bpp), 'edited': r in over,
                     'shared': [names.get(x, f'Effect {x}') or f'Effect {x}' for x in d['spells'] if x != s]})
    over_c = _spell_colours()
    cols = []
    for u in fe4spellfx.colour_sets(rom, over_c).get(s, []):
        per = u['n'] if u['kind'] == 'frames' else 16
        key = fe4spellfx.colour_key(u['addr'], fxmap)
        delays = fe4spellfx.stream_delays(u['tokens'])
        tm = _timing().get(key)
        cols.append({'addr': key, 'label': _colour_label(u), 'kind': u['kind'],
                     'frames': int(tm) if tm else (delays[0] if delays else (1 if u['tokens'] is not None else None)),
                     'frames_varies': bool(not tm and len(set(delays)) > 1), 'frames_edited': tm is not None,
                     'colours': [c & 0x7FFF for c in u['colours']], 'game': [c & 0x7FFF for c in u['game']],
                     'per': max(1, min(per, 16)), 'lead': 0 if u['kind'] in ('frames', 'cycle') else u['start'] % 16,
                     'edited': u['addr'] in over_c,
                     'shared': [names.get(x, f'Effect {x}') or f'Effect {x}' for x in u['spells'] if x != s]})
    e = eff.get(s)
    steps = []
    for x in fe4spellfx.script_words(rom, s):
        kind, label, val = fe4spellfx.describe(x)
        st = {'word': x, 'kind': kind, 'label': label, 'value': val}
        if kind == 'sound':
            f = fe4spellfx.snes_to_file(fe4spellfx.SOUNDS + 2 * (val or 0))
            st['sound'] = rom[f] | rom[f + 1] << 8
        if kind == 'motion':
            data = fe4spellfx.motion_bytes(rom, val)
            label, params = fe4spellfx.describe_motion(data)
            st.update(motion=label, params=params, key=fe4spellfx.motion_key(val, fxmap),
                      motion_edited=fe4spellfx.motion_key(val, fxmap) in _motions_keyed())
        steps.append(st)
    return {'spell': s, 'name': names.get(s, ''), 'pictures': pics, 'colours': cols, 'steps': steps,
            'steps_edited': s in _steps(),
            'preview': any(recs[r]['kind'] == 'map' for r in by_spell.get(s, [])),
            'new': bool(e), 'from': e['from'] if e else None, 'from_name': names.get(e['from'], '') if e else None,
            'own_name': e['name'] if e else None,
            'items': [it for it, a, b2 in _project_spell_rows() if s in (a, b2)]}


def _project_spell_rows():
    """[(item name, spell, spell at range)] from the project's spells.csv."""
    p = project()
    t = p.table('spells') if p else None
    if t is None:
        return []
    out = []
    for r in t.rows:
        try:
            out.append((r.get('_item') or f'Item {r["item"]}', int(r['spell']), int(r.get('spell_far') or r['spell'])))
        except ValueError:
            pass
    return out


def api_spellgfxset(b, q):
    """Import a picture for a spell record ({record, png base64}) or go back to the game's ({record, png: null})."""
    p = need_project()
    rom, recs, _, _, fxmap = _spell_pictures()
    r = int(b['record'])
    if r not in recs or recs[r]['kind'] == 'map':
        raise ValueError('That isn\'t a spell picture.')
    rel = fe4spellfx.picture_file(r, fxmap)
    if b.get('png') is None:
        p.set_blob(rel, None)
        return {'ok': True}
    try:
        data = base64.b64decode(b['png'], validate=True)
    except ValueError:
        raise ValueError('That file could not be read.')
    d = recs[r]
    bpp = fe4spellfx.bpp_of(d['kind'])
    tiles = fe4spellfx.sheet_from_png(data, len(d['data']), bpp)
    if tiles == d['data']:
        p.set_blob(rel, None)
        return {'ok': True, 'same': True}
    changed = sum(tiles[k:k + 8 * bpp] != d['data'][k:k + 8 * bpp] for k in range(0, len(tiles), 8 * bpp))
    p.set_blob(rel, fe4spellfx.sheet_png(tiles, bpp))
    return {'ok': True, 'tiles': changed}


def _spell_colours_keyed():
    try:
        return fe4spellfx.read_colours(_project_reader(f'{fe4spellfx.FOLDER}/colors.json'))
    except ValueError:
        return {}


def _spell_colours():
    """The project's changed spell colours: {address in spell_rom(): [colour words]}."""
    return fe4spellfx.colours_by_address(_spell_colours_keyed(), spell_rom()[1])


def spell_sheet(r, scale, spell=None):
    """A picture's sheet: in the stand-in ramp (the file to paint on), or with spell's battle colours."""
    rom, recs, _, over, _ = _spell_pictures()
    if r not in recs or recs[r]['kind'] == 'map':
        return None
    d = recs[r]
    data, bpp = over.get(r, d['data']), fe4spellfx.bpp_of(d['kind'])
    if spell is None or d['kind'] == 'sprite':
        return fe4spellfx.sheet_png(data, bpp, scale)
    pal = fe4spellfx.record_palette(rom, r, spell)
    return fe4spellfx.sheet_colour_png(data, bpp, fe4spellfx.cgram(rom, spell, _spell_colours()), pal or 0, scale)


def spell_preview(s, scale, colour=False):
    rom, recs, _, over, _ = _spell_pictures()
    cg = fe4spellfx.cgram(rom, s, _spell_colours()) if colour else None
    return fe4spellfx.preview_png(rom, s, over, scale, cg)


COLOUR_KINDS = {'set': 'set when the spell starts', 'copy': 'set when the spell starts',
                'frames': 'changes every few frames', 'cycle': 'cycles', 'fade': 'fades to these'}


def _colour_label(u):
    a, b = u['start'], u['start'] + u['n'] - 1
    pa, pb = a // 16, b // 16
    who, off = ('Sprite palette', 8) if a >= 128 else ('Palette', 0)
    where = (f'{who} {pa - off}, colours {a % 16}-{b % 16}' if pa == pb else f'{who}s {pa - off}-{pb - off}')
    return f'{where} · {COLOUR_KINDS[u["kind"]]}'


def api_spellcolours(b, q):
    """Change spell colours: {sets: {key: [colour words] or null}} (null = the game's); one undo step."""
    p = need_project()
    rom, fxmap = spell_rom()
    allsets = {fe4spellfx.colour_key(u['addr'], fxmap): u for lst in fe4spellfx.colour_sets(rom).values() for u in lst}
    cur = _spell_colours_keyed()
    for k, v in (b.get('sets') or {}).items():
        if k not in allsets:
            raise ValueError('Those aren\'t spell colours.')
        if v is None:
            cur.pop(k, None)
            continue
        cols = [int(c) & 0x7FFF for c in v]
        game = allsets[k]['game']
        if len(cols) != len(game):
            raise ValueError(f'That colour set has {len(game)} colours.')
        cols = [g if c == (g & 0x7FFF) else c for c, g in zip(cols, game)]   # keep the game's own bits
        if cols == game:
            cur.pop(k, None)
        else:
            cur[k] = cols
    ops = []
    rel = f'{fe4spellfx.FOLDER}/colors.json'
    new = fe4spellfx.dump_colours(cur) if cur else None
    if new != p.blob(rel).data:
        ops.append(('blob', rel, p.blob(rel).data, new))
    if b.get('frames'):
        tm = dict(_timing())
        for k, v in b['frames'].items():
            if k not in allsets or allsets[k]['tokens'] is None:
                raise ValueError('Those colours don\'t change by steps.')
            if v is None:
                tm.pop(k, None)
            else:
                v = int(v)
                if not 1 <= v <= 128:
                    raise ValueError('Frames per step are 1 to 128.')
                tm[k] = v
        trel = f'{fe4spellfx.FOLDER}/{fe4spellfx.TIMING}'
        tnew = json.dumps(tm, indent=1, sort_keys=True).encode() if tm else None
        if tnew != p.blob(trel).data:
            ops.append(('blob', trel, p.blob(trel).data, tnew))
    if ops:
        p.edit(ops)
    return {'ok': True, 'changed': len(cur)}


def api_spellsteps(b, q):
    """Change an effect's steps: {spell, words: [numbers]} or {spell, words: null} for the game's; one undo step."""
    p = need_project()
    s = int(b['spell'])
    rom, fxmap = spell_rom()
    if not 0 <= s < fe4spellfx.spell_count(rom):
        raise ValueError('There is no such effect.')
    steps = dict(_steps())
    if 'words' not in b:
        pass
    elif b.get('words') is None:
        steps.pop(s, None)
    else:
        words = [int(w) & 0xFFFF for w in b['words']]
        fe4spellfx.check_steps(words)
        n0 = fe4spellfx.spell_count(rom_data())
        if s >= n0:
            words = fe4spellfx.to_source_terms(words, s, fxmap)
            base = next(e['from'] for e in _effects() if e['id'] == s)
            game = fe4spellfx.script_words(rom_data(), base)
        else:
            game = fe4spellfx.script_words(rom_data(), s)
        if words == game:
            steps.pop(s, None)
        else:
            steps[s] = words
    ops = []
    rel = f'{fe4spellfx.FOLDER}/{fe4spellfx.STEPS}'
    new = fe4spellfx.dump_steps(steps) if steps else None
    if new != p.blob(rel).data:
        ops.append(('blob', rel, p.blob(rel).data, new))
    if b.get('motions'):
        mots = dict(_motions_keyed())
        game_rom = rom_data()
        for k, params in b['motions'].items():
            r_orig = int(k.split(':')[-1])
            if not 0 <= r_orig < fe4spellfx._offset_count(game_rom, fe4spellfx.table(game_rom, 'motions')):
                raise ValueError('There is no such motion.')
            game = fe4spellfx.motion_bytes(game_rom, r_orig)
            if params is None:
                mots.pop(k, None)
                continue
            data = fe4spellfx.set_motion(mots.get(k, game), params)
            if data == game:
                mots.pop(k, None)
            else:
                mots[k] = data
        mrel = f'{fe4spellfx.FOLDER}/{fe4spellfx.MOTIONS}'
        mnew = json.dumps({k: v.hex() for k, v in sorted(mots.items())}, indent=1).encode() if mots else None
        if mnew != p.blob(mrel).data:
            ops.append(('blob', mrel, p.blob(mrel).data, mnew))
    if ops:
        p.edit(ops)
    return {'ok': True}


def api_spelleffect(b, q):
    """New effects: {new: effect, name} copies one (with the project's changes to it), {rename: id, name},
    {delete: id}.  One undo step."""
    p = need_project()
    eff = _effects()
    rel = f'{fe4spellfx.FOLDER}/{fe4spellfx.EFFECTS}'
    n0 = fe4spellfx.spell_count(rom_data())
    if 'new' in b:
        src = int(b['new'])
        by_id = {e['id']: e for e in eff}
        base = by_id[src]['from'] if src in by_id else src
        if not 0 <= base < n0:
            raise ValueError('That effect can\'t be copied.')
        new_id = n0 + len(eff)
        if new_id > 254:
            raise ValueError('There is no room for more effects.')
        name = (b.get('name') or '').strip()[:40] or f'New effect {new_id}'
        eff2 = eff + [{'id': new_id, 'from': base, 'name': name, 'deleted': False}]
        rom2 = bytearray(rom_data())
        with contextlib.redirect_stdout(io.StringIO()):
            fx2 = fe4spellfx.apply_effects(rom2, eff2, L.FreeSpace())
        _, fx1 = spell_rom()
        ops = [('blob', rel, p.blob(rel).data, fe4spellfx.dump_effects(eff2))]
        # carry over the source's own changes: pictures, then colours
        for r, (eid, orig) in fx2['pictures'].items():
            if eid != new_id:
                continue
            src_file = fe4spellfx.effect_file(src, orig) if src in by_id else f'{fe4spellfx.FOLDER}/r{orig:03d}.png'
            data = _project_reader(src_file)
            if data:
                ops.append(('blob', fe4spellfx.effect_file(new_id, orig), p.blob(fe4spellfx.effect_file(new_id, orig)).data, data))
        cur = _spell_colours_keyed()
        add = {}
        for a, (eid, orig) in fx2['colours'].items():
            if eid != new_id:
                continue
            k = f's{src}:{orig:06X}' if src in by_id else f'{orig:06X}'
            if k in cur:
                add[f's{new_id}:{orig:06X}'] = cur[k]
        if add:
            crel = f'{fe4spellfx.FOLDER}/colors.json'
            ops.append(('blob', crel, p.blob(crel).data, fe4spellfx.dump_colours({**cur, **add})))
        tm = _timing()
        tadd = {}
        for a, (eid, orig) in fx2['colours'].items():
            k = f's{src}:{orig:06X}' if src in by_id else f'{orig:06X}'
            if eid == new_id and k in tm:
                tadd[f's{new_id}:{orig:06X}'] = tm[k]
        if tadd:
            trel = f'{fe4spellfx.FOLDER}/{fe4spellfx.TIMING}'
            ops.append(('blob', trel, p.blob(trel).data, json.dumps({**tm, **tadd}, indent=1, sort_keys=True).encode()))
        mots = _motions_keyed()
        madd = {}
        for k2, (eid, orig) in fx2.get('motions', {}).items():
            mk = f's{src}:{orig}' if src in by_id else str(orig)
            if eid == new_id and mk in mots:
                madd[f's{new_id}:{orig}'] = mots[mk]
        if madd:
            mrel = f'{fe4spellfx.FOLDER}/{fe4spellfx.MOTIONS}'
            ops.append(('blob', mrel, p.blob(mrel).data,
                        json.dumps({k: v.hex() for k, v in sorted({**mots, **madd}.items())}, indent=1).encode()))
        st = _steps()
        if src in st:      # the source's changed steps (already in the original's terms)
            srel = f'{fe4spellfx.FOLDER}/{fe4spellfx.STEPS}'
            ops.append(('blob', srel, p.blob(srel).data, fe4spellfx.dump_steps({**st, new_id: st[src]})))
        p.edit(ops)
        return {'ok': True, 'id': new_id}
    k = int(b.get('rename', b.get('delete', -1)))
    e = next((x for x in eff if x['id'] == k), None)
    if e is None:
        raise ValueError('That isn\'t one of your new effects.')
    if 'rename' in b:
        e['name'] = (b.get('name') or '').strip()[:40]
        p.set_blob(rel, fe4spellfx.dump_effects(eff))
        return {'ok': True}
    users = [it for it, a, b2 in _project_spell_rows() if k in (a, b2)]
    if users:
        raise ValueError(f'{", ".join(users[:3])} still use{"s" if len(users) == 1 else ""} this effect; give '
                         f'{"it" if len(users) == 1 else "them"} another one on the Spells tab first.')
    e['deleted'] = True
    while eff and eff[-1]['deleted']:         # numbers stay put; only the last ones really go
        eff.pop()
    ops = [('blob', rel, p.blob(rel).data, fe4spellfx.dump_effects(eff) if eff else None)]
    p.edit(ops)
    return {'ok': True}


def _skill_names():
    import fe4skills
    p = project()
    t = p.table('skills') if p else None
    names = dict(enumerate(fe4skills.NAMES))
    if t:
        for r in t.rows:
            try:
                names[int(r['id'])] = r.get('name') or names.get(int(r['id']), '')
            except ValueError:
                pass
    return names


def api_skillanims(b, q):
    """Skills that play an animation when they activate, with what they play; and the effects that can play."""
    import fe4skillfx
    p = need_project()
    t = p.table('skill_anims')
    if t is None:
        raise KeyError('This project has no skill_anims.csv; reopen it with this version to add one.')
    rom, fxmap = spell_rom()
    names = _skill_names()
    game = fe4skillanim.game_rows(rom_data())
    rows = {}
    for i, r in enumerate(t.rows):
        try:
            got = fe4skillanim.parse_rows([r])
        except SystemExit as e:
            continue
        sid = int(r['skill'])
        eff, rea, cols = got[sid]
        rows[sid] = {'row': i, 'effect': eff, 'reaction': rea, 'colours': cols}
    out = []
    order = [0x13, 0x14, 0x15, 0x02]
    for sid in order:
        g = game[sid]
        cur = rows.get(sid, {'effect': g[0], 'reaction': g[1], 'colours': g[2]})
        out.append({'skill': sid, 'name': names.get(sid, ''), 'kind': 'game', 'defend': sid == 0x02,
                    **{k: cur[k] for k in ('effect', 'reaction', 'colours')},
                    'game': {'effect': g[0], 'reaction': g[1], 'colours': g[2]},
                    'edited': (cur['effect'], cur['reaction'], cur['colours']) != g})
    for sid in (5, 17, 3):        # the game's skills that show nothing; the kit adds their event
        cur = rows.get(sid, {'effect': None, 'reaction': 0, 'colours': game[0x14][2]})
        about = {5: 'Adept: attacks again (rate: Speed). The sparkle plays before the extra strike',
                 17: 'Vantage: strikes first when HP is at or below half, even when attacked. The sparkle plays '
                     'when it makes the defender strike first',
                 3: 'Wrath: sure critical hits when HP is at or below half. The sparkle plays before each such strike'}[sid]
        out.append({'skill': sid, 'name': names.get(sid, ''), 'kind': 'engine', 'defend': False, 'about': about,
                    **{k: cur[k] for k in ('effect', 'reaction', 'colours')},
                    'game': {'effect': None, 'reaction': 0, 'colours': game[0x14][2]}, 'edited': sid in rows})
    sk = p.table('skills')
    for r in (sk.rows if sk else []):
        eff_name = (r.get('effect') or '').strip()
        if not eff_name or eff_name not in fe4skillfx.EFFECTS:
            continue
        sid = int(r['id'])
        kind, _, _, _, _, anim, _, _, desc = fe4skillfx.EFFECTS[eff_name]
        base = game.get(anim) if anim else None
        dflt = {'effect': base[0] if base else None, 'reaction': base[1] if base else 0,
                'colours': base[2] if base else game[0x14][2]}
        cur = rows.get(sid, dflt)
        out.append({'skill': sid, 'name': r.get('name') or f'Skill {sid}', 'kind': 'new', 'effect_kind': eff_name,
                    'defend': kind == fe4skillfx.K_DEFEND, 'about': desc,
                    **{k: cur[k] for k in ('effect', 'reaction', 'colours')}, 'game': dflt, 'edited': sid in rows,
                    'borrows': names.get(anim, '') if anim else None})
    spell_names = _spell_label(rom)
    eff = {e['id']: e for e in _effects()}
    choices = [[e, spell_names.get(e) or f'Effect {e}'] for e in fe4skillanim.SPARKLES]
    for e in eff.values():
        if not e['deleted'] and e['from'] in fe4skillanim.SPARKLES:
            choices.append([e['id'], e['name'] or f'New effect {e["id"]}'])
    sparkle_names = {0x36: 'Astra sparkle', 0x37: 'Luna sparkle', 0x38: 'Sol sparkle', 0x39: 'Sparkle (unused skill 22)',
                     0x3A: 'Sparkle (unused skill 23)', 0x3F: 'Pavise sparkle'}
    choices = [[k, sparkle_names.get(k, n)] for k, n in choices]
    return {'skills': out, 'effects': choices,
            'reactions': [[k, v] for k, v in fe4skillanim.REACTION_NAMES.items()]}


def api_skillanimset(b, q):
    """Set what a skill plays: {skill, effect (or null = nothing), reaction, colours} or {skill, reset: true}."""
    p = need_project()
    t = p.table('skill_anims')
    sid = int(b['skill'])
    names = _skill_names()
    idx = next((i for i, r in enumerate(t.rows) if r.get('skill', '').strip() == str(sid)), None)
    game = fe4skillanim.game_rows(rom_data())
    if b.get('reset'):
        if sid in game:
            e, rea, cols = game[sid]
            new = {'skill': str(sid), '_name': names.get(sid, ''), 'effect': str(e),
                   'reaction': fe4skillanim.REACTIONS[rea], 'colours': ' '.join(f'{c:04x}' for c in cols)}
            p.edit([('rows', 'skill_anims', idx, [dict(t.rows[idx])], [new])] if idx is not None else
                   [('rows', 'skill_anims', len(t.rows), [], [new])])
        elif idx is not None:
            p.edit([('rows', 'skill_anims', idx, [dict(t.rows[idx])], [])])
        return {'ok': True}
    eff = b.get('effect')
    n = fe4spellfx.spell_count(spell_rom()[0])
    if eff is not None and not 0 <= int(eff) < n:
        raise ValueError('There is no such effect.')
    rea = int(b.get('reaction') or 0)
    if rea not in fe4skillanim.REACTIONS:
        raise ValueError('Pick a reaction.')
    cols = [int(c) & 0x7FFF for c in b.get('colours') or []]
    if len(cols) != 5:
        raise ValueError('A sparkle has five colours.')
    new = {'skill': str(sid), '_name': names.get(sid, ''), 'effect': '' if eff is None else str(int(eff)),
           'reaction': fe4skillanim.REACTIONS[rea], 'colours': ' '.join(f'{c:04x}' for c in cols)}
    if idx is None:
        p.edit([('rows', 'skill_anims', len(t.rows), [], [new])])
    else:
        p.edit([('rows', 'skill_anims', idx, [dict(t.rows[idx])], [new])])
    return {'ok': True}


# ---------------------------------------------------------------- map battles
def _figure_labels(rom):
    names = L.class_names(rom)[:72]
    labels = {f: names[f] for f in range(min(72, fe4mapbattle.FIGURES))}
    for c, (m, w) in enumerate(fe4mapbattle.class_figures(rom, 72)):
        if w != c and w not in labels:
            labels[w] = f'{names[c]} (women)'
    items = L.item_names(rom)
    labels[0x5D] = f'{names[6]} with {items[0x19] if len(items) > 0x19 else "item 25"}'
    for f in range(fe4mapbattle.FIGURES):
        labels.setdefault(f, 'Figure %02X' % f)
    return labels


def api_mapbattle(b, q):
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    t = p.table('map_battle')
    if t is None:
        raise KeyError('This project has no map_battle.csv; reopen it with this version to add one.')
    game = fe4mapbattle.class_figures(rom, 72)
    names = [r.get('_name', '') for r in p.table('classes').rows] if p.table('classes') else []
    classes = []
    for i, r in enumerate(t.rows):
        c = int(r['class'])
        if c >= 72:
            continue
        classes.append({'row': i, 'c': c, 'name': (names[c] if c < len(names) and names[c] else r.get('_class_name', '')),
                        'figure': int(r['figure'], 16), 'women': int(r['women'], 16),
                        'gameFigure': game[c][0], 'gameWomen': game[c][1]})
    labels = _figure_labels(rom)
    figures = []
    for f in range(fe4mapbattle.FIGURES):
        sh = []
        for addr, ks in fe4mapbattle.sheets(rom, f):
            data = p.blob(fe4mapbattle.sheet_file(f, ks[0])).data
            sh.append({'k': ks[0], 'dirs': [fe4mapbattle.DIRS[k] for k in ks], 'custom': data is not None,
                       'ver': '%08x' % zlib.crc32(data) if data is not None else 'rom'})
        figures.append({'fig': f, 'label': labels[f], 'sheets': sh})
    return {'classes': classes, 'figures': figures, 'armies': [a for a, _ in fe4sprites.ARMIES]}


def api_mapbattleset(b, q):
    """{class, figure?, women?} (figure numbers) or {class, reset: true}."""
    p = need_project()
    t = p.table('map_battle')
    c = int(b['class'])
    idx = next((i for i, r in enumerate(t.rows) if r.get('class', '').strip() == str(c)), None)
    if idx is None:
        raise ValueError('There is no such class.')
    row = dict(t.rows[idx])
    if b.get('reset'):
        m, w = fe4mapbattle.class_figures(rom_data(), 72)[c]
        row['figure'], row['women'] = '%02X' % m, '%02X' % w
    for key in ('figure', 'women'):
        if key in b:
            v = int(b[key])
            if not 0 <= v < fe4mapbattle.FIGURES:
                raise ValueError('There is no such figure.')
            row[key] = '%02X' % v
    p.edit([('rows', 'map_battle', idx, [dict(t.rows[idx])], [row])])
    return {'ok': True}


def mapbattle_rows(fig, k):
    rom = rom_data()
    if rom is None:
        return None
    p = project()
    data = p.blob(fe4mapbattle.sheet_file(fig, k)).data if p else None
    if data is not None:
        return fe4mapbattle.rows_from_png(data, fe4sprites.palette(rom, 0))
    key = (id(rom), len(rom), 'mb', fig, k)
    if key not in _walk_cache:
        if len(_walk_cache) > 200:
            _walk_cache.clear()
        _walk_cache[key] = fe4mapbattle.rows_from_bytes(
            fe4mapbattle.sheet_bytes(rom, fe4mapbattle.pointers(rom, fig)[k][1]))
    return _walk_cache[key]


def mapbattle_image(fig, k, army, scale, indexed=False):
    rom = rom_data()
    rows = mapbattle_rows(fig, k)
    if rows is None:
        return None
    if indexed:
        return fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0))
    offs = dict(fe4sprites.ARMIES)
    pal = fe4sprites.palette(rom, list(offs.values())[army] if 0 <= army < len(offs) else 0)
    return fe4sprites.rows_png(rows, pal, scale)


_mb_player = {}


def mapbattle_player(fig, k, s):
    """(strip rows, motions) for the figure's motions in direction k with weapon section s, drawn from the
    project's sheet when it has one; cached by sheet version."""
    rom = rom_data()
    if rom is None:
        return None
    p = project()
    sheet_k = next((ks[0] for a, ks in fe4mapbattle.sheets(rom, fig) if k in ks), k)
    data = p.blob(fe4mapbattle.sheet_file(fig, sheet_k)).data if p else None
    key = (id(rom), len(rom), fig, k, s, zlib.crc32(data) if data is not None else None)
    if key not in _mb_player:
        if len(_mb_player) > 64:
            _mb_player.clear()
        gfx = fe4mapbattle.bytes_from_rows(mapbattle_rows(fig, sheet_k)) if data is not None else None
        _mb_player[key] = fe4mapbattle.player(rom, fig, k, s, gfx)
    return _mb_player[key]


def api_mbplayer(b, q):
    """{fig, k, s} -> which weapon sections the figure has in that direction, and the motions of s."""
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    fig, k = int(q.get('fig', ['0'])[0]), int(q.get('k', ['4'])[0])
    s = int(q.get('s', ['-1'])[0])
    if not 0 <= fig < fe4mapbattle.FIGURES or not 0 <= k < 8:
        raise ValueError('There is no such figure.')
    script = fe4mapbattle.script_bytes(rom, fig, k)
    have = [i for i in range(len(fe4mapbattle.SECTIONS)) if fe4mapbattle.parse_section(script, i)]
    if s not in have:
        s = have[0] if have else -1
    r = mapbattle_player(fig, k, s) if s >= 0 else None
    return {'sections': [[i, fe4mapbattle.SECTIONS[i]] for i in have], 's': s, 'cell': fe4mapbattle.CELL,
            'motions': r[1] if r else [], 'cells': len(r[0][0]) // fe4mapbattle.CELL if r else 0}


def mapbattle_strip(fig, k, s, army, scale):
    rom = rom_data()
    r = mapbattle_player(fig, k, s)
    if not r:
        return None
    offs = dict(fe4sprites.ARMIES)
    pal = fe4sprites.palette(rom, list(offs.values())[army] if 0 <= army < len(offs) else 0)
    return fe4sprites.rows_png(r[0], pal, scale)


def api_mapbattlesheet(b, q):
    """Replace one of a figure's sheets with a PNG (base64), or {reset: true}."""
    import base64
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    fig, k = int(b['fig']), int(b['k'])
    if not 0 <= fig < fe4mapbattle.FIGURES or not 0 <= k < 8:
        raise ValueError('There is no such sheet.')
    rel = fe4mapbattle.sheet_file(fig, k)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    try:
        rows = fe4mapbattle.rows_from_png(base64.b64decode(b['png']), fe4sprites.palette(rom, 0))
    except ValueError as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(rel, fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0)))
    return {'ok': True}


def api_mapbattlepreview(b, q):
    """Watch a map battle: Midir fights Gandolf on the Prologue map with the figure given."""
    fig = int(b['fig'])
    if not 0 <= fig < fe4mapbattle.FIGURES:
        raise ValueError('There is no such figure.')
    label = _figure_labels(rom_data()).get(fig, 'figure')
    return _battle_preview(f'Watch a map battle: {label}', lambda r: 0,
                           extra=[('1454E', '%02X' % fig), ('1454F', '00')], timing=MAP_PREVIEW)


# ---------------------------------------------------------------- spell effects on the map
def _mapfx_tables():
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    ts, tp = p.table('map_spells'), p.table('map_palettes')
    if ts is None or tp is None:
        raise KeyError('This project has no map_spells.csv; reopen it with this version to add one.')
    return p, rom, ts, tp


def _mapfx_palette(tp, k):
    r = next((r for r in tp.rows if r.get('palette', '').strip() == str(k)), None)
    return [int(x, 16) & 0x7FFF for x in r['colours'].split()] if r else None


def mapfx_rows(s):
    p, rom = project(), rom_data()
    data = p.blob(fe4mapfx.sheet_file(s)).data if p else None
    if data is not None:
        return fe4mapfx.rows_from_png(data, fe4mapfx.STAND_IN)
    return fe4mapfx.rows_from_bytes(fe4mapfx.sheet_bytes(rom, s))


def mapfx_image(s, scale, indexed=False):
    p, rom, ts, tp = _mapfx_tables()
    r = next((r for r in ts.rows if r.get('spell', '').strip() == str(s)), None)
    if r is None:
        return None
    pal = [fe4mapfx.rgb(c) for c in _mapfx_palette(tp, int(r['palette']))]
    rows = mapfx_rows(s)
    return fe4sprites.indexed_sheet_png(rows, pal) if indexed else fe4sprites.rows_png(rows, pal, scale)


def _bg_colour_info(rom, s, words, block, names):
    if s in fe4mapfx.COLOUR_LISTS:
        rows = [[{'a': a, 'c': words.get(a, c), 'game': c} for a, c in row] for row in fe4mapfx.colour_rows(rom, s)]
        shared = sorted({names[fe4mapfx.FIRST_ITEM + o] for o, l in fe4mapfx.COLOUR_LISTS.items()
                         if o != s and set(l) & set(fe4mapfx.COLOUR_LISTS[s])})
        return {'kind': 'lists', 'rows': rows, 'shared': shared}
    if s in fe4mapfx.BLOCK:
        game = fe4mapfx.block_colours(rom, s)
        cols = block.get(s, game)
        return {'kind': 'block', 'rows': [[{'c': cols[i], 'game': game[i]} for i in range(7)],
                                          [{'c': cols[i], 'game': game[i]} for i in range(7, 14)]]}
    return {'kind': None}


def api_mapspells(b, q):
    p, rom, ts, tp = _mapfx_tables()
    names = L.item_names(rom)
    spells = []
    words = _colour_word_values()
    tb = p.table('map_spell_block')
    block = {int(r['spell']): [int(x, 16) for x in r['colours'].split()] for r in (tb.rows if tb else [])}
    rows = {int(r['spell']): (i, r) for i, r in enumerate(ts.rows)}
    for s in range(fe4mapfx.BG_COUNT):
        it = fe4mapfx.FIRST_ITEM + s
        data = p.blob(fe4mapfx.sheet_file(s)).data
        bg = p.blob(fe4mapfx.bg_file(s)).data
        x = {'spell': s, 'item': it, 'name': names[it] if it < len(names) else f'Spell {s}',
             'attack': it < 0x58, 'sprite': s in rows, 'bgColours': _bg_colour_info(rom, s, words, block, names),
             'bgCustom': bg is not None, 'bgVer': '%08x' % zlib.crc32(bg) if bg is not None else 'rom'}
        if s in rows:
            i, r = rows[s]
            x.update({'row': i, 'palette': int(r['palette']), 'gamePalette': fe4mapfx.palette_index(fe4mapfx.entry(rom, s)[0]),
                      'custom': data is not None, 'ver': '%08x' % zlib.crc32(data) if data is not None else 'rom'})
        spells.append(x)
    pals = []
    for k in range(len(fe4mapfx.PALETTES)):
        cols = _mapfx_palette(tp, k)
        pals.append({'p': k, 'colours': cols, 'game': fe4mapfx.colours(rom, k),
                     'users': [x['name'] for x in spells if x.get('palette') == k]})
    return {'spells': spells, 'palettes': pals}


def api_mapspellset(b, q):
    """{spell, palette} or {palette: k, colours: [16]} or {palette: k, reset: true}."""
    p, rom, ts, tp = _mapfx_tables()
    if 'spell' in b:
        s, k = int(b['spell']), int(b['palette'])
        if not 0 <= k < len(fe4mapfx.PALETTES):
            raise ValueError('There is no such palette.')
        idx = next((i for i, r in enumerate(ts.rows) if r.get('spell', '').strip() == str(s)), None)
        if idx is None:
            raise ValueError('That spell has no map effect.')
        row = dict(ts.rows[idx])
        row['palette'] = str(k)
        p.edit([('rows', 'map_spells', idx, [dict(ts.rows[idx])], [row])])
        return {'ok': True}
    k = int(b['palette'])
    idx = next((i for i, r in enumerate(tp.rows) if r.get('palette', '').strip() == str(k)), None)
    if idx is None:
        raise ValueError('There is no such palette.')
    cols = fe4mapfx.colours(rom, k) if b.get('reset') else [int(c) & 0x7FFF for c in b.get('colours') or []]
    if len(cols) != 16:
        raise ValueError('A palette has 16 colours.')
    row = dict(tp.rows[idx])
    row['colours'] = ' '.join('%04x' % c for c in cols)
    p.edit([('rows', 'map_palettes', idx, [dict(tp.rows[idx])], [row])])
    return {'ok': True}


def api_mapspellsheet(b, q):
    """Replace a spell's map sheet with a PNG in its palette's colours (base64), or {reset: true}."""
    import base64
    p, rom, ts, tp = _mapfx_tables()
    s = int(b['spell'])
    r = next((r for r in ts.rows if r.get('spell', '').strip() == str(s)), None)
    if r is None:
        raise ValueError('That spell has no map effect.')
    rel = fe4mapfx.sheet_file(s)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    pal = [fe4mapfx.rgb(c) for c in _mapfx_palette(tp, int(r['palette']))]
    try:
        rows = fe4mapfx.rows_from_png(base64.b64decode(b['png']), pal)
    except ValueError as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(rel, fe4mapfx.stand_in_png(rows))
    return {'ok': True}


def _bg_shown_colours(s):
    """The 14 colours (palette 6 then 7, colours 9-15) a spell's background shows first, with the project's
    changes; None when the block's own are right."""
    p, rom = project(), rom_data()
    if s in fe4mapfx.BLOCK:
        t = p.table('map_spell_block') if p else None
        r = next((r for r in (t.rows if t else []) if r.get('spell', '').strip() == str(s)), None)
        return [int(x, 16) for x in r['colours'].split()] if r else None
    if s in fe4mapfx.COLOUR_LISTS:
        words = _colour_word_values()
        a, n = fe4mapfx.COLOUR_LISTS[s][0]
        first = [words.get(a + 2 * i, fe4mapfx.word(rom, a + 2 * i)) for i in range(min(7, n))]
        if s == 8:      # Mjolnir: colours 9-12 from one list, 13-15 from the other
            b = fe4mapfx.COLOUR_LISTS[s][1][0]
            first = first[:4] + [words.get(b + 2 * i, fe4mapfx.word(rom, b + 2 * i)) for i in range(3)]
        return first + [None] * 7
    return None


def _colour_word_values():
    p = project()
    t = p.table('map_colour_words') if p else None
    return {int(r['address'], 16): int(r['colour'], 16) for r in (t.rows if t else [])}


def mapbg_image(s, scale):
    rom = rom_data()
    p = project()
    data = p.blob(fe4mapfx.bg_file(s)).data if p else None
    t, mp, cols = fe4mapfx.bg_blocks(rom, s)
    shown = _bg_shown_colours(s)
    view = list(cols)
    if shown:
        for i, c in enumerate(shown):
            if c is not None:
                view[105 + i if i < 7 else 121 + i - 7] = c
    if data is not None:
        t, mp = fe4mapfx.bg_from_png(data, mp, cols, t)
    return fe4mapfx.bg_png(rom, s, t, mp, view, scale)


def api_mapspellcolour(b, q):
    """{address, colour} (a word of a spell's colour list), {spell, colours: [14]} (block spells) or
    {spell, reset: true}."""
    p = need_project()
    rom = rom_data()
    if 'address' in b:
        a = int(b['address'])
        t = p.table('map_colour_words')
        idx = next((i for i, r in enumerate(t.rows) if int(r['address'], 16) == a), None)
        if idx is None:
            raise ValueError('That colour is not part of a map spell.')
        row = dict(t.rows[idx])
        row['colour'] = '%04x' % (int(b['colour']) & 0x7FFF)
        p.edit([('rows', 'map_colour_words', idx, [dict(t.rows[idx])], [row])])
        return {'ok': True}
    s = int(b['spell'])
    if b.get('reset'):
        edits = []
        t = p.table('map_colour_words')
        mine = {a + 2 * i for a, n in fe4mapfx.COLOUR_LISTS.get(s, []) for i in range(n)}
        for i, r in enumerate(t.rows):
            a = int(r['address'], 16)
            if a in mine and int(r['colour'], 16) != fe4mapfx.word(rom, a):
                new = dict(r)
                new['colour'] = '%04x' % fe4mapfx.word(rom, a)
                edits.append(('rows', 'map_colour_words', i, [dict(r)], [new]))
        if s in fe4mapfx.BLOCK:
            tb = p.table('map_spell_block')
            i = next(i for i, r in enumerate(tb.rows) if r.get('spell', '').strip() == str(s))
            new = dict(tb.rows[i])
            new['colours'] = ' '.join('%04x' % c for c in fe4mapfx.block_colours(rom, s))
            edits.append(('rows', 'map_spell_block', i, [dict(tb.rows[i])], [new]))
        if edits:
            p.edit(edits)
        return {'ok': True}
    if s not in fe4mapfx.BLOCK:
        raise ValueError('That spell cycles its own colours; change them one by one.')
    cols = [int(c) & 0x7FFF for c in b.get('colours') or []]
    if len(cols) != 14:
        raise ValueError('A background has 14 colours here.')
    tb = p.table('map_spell_block')
    i = next(i for i, r in enumerate(tb.rows) if r.get('spell', '').strip() == str(s))
    new = dict(tb.rows[i])
    new['colours'] = ' '.join('%04x' % c for c in cols)
    p.edit([('rows', 'map_spell_block', i, [dict(tb.rows[i])], [new])])
    return {'ok': True}


def api_mapspellbg(b, q):
    """Replace a spell's background picture with a PNG (base64, 256 x 256), or {reset: true}."""
    import base64
    p = need_project()
    rom = rom_data()
    s = int(b['spell'])
    if not 0 <= s < fe4mapfx.BG_COUNT:
        raise ValueError('There is no such spell.')
    rel = fe4mapfx.bg_file(s)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    t, mp, cols = fe4mapfx.bg_blocks(rom, s)
    try:
        nt, nm = fe4mapfx.bg_from_png(base64.b64decode(b['png']), mp, cols, t)
    except ValueError as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(rel, fe4mapfx.bg_png(rom, s, nt, nm, cols))
    return {'ok': True}


def api_mapspellpreview(b, q):
    """Watch a spell on the map: Midir casts it on Gandolf in the Prologue map battle."""
    s = int(b['spell'])
    rom = rom_data()
    if not 0 <= s < fe4mapfx.BG_COUNT:
        raise ValueError('There is no such spell.')
    item = fe4mapfx.FIRST_ITEM + s
    name = L.item_names(rom)[item]
    return _battle_preview(f'Watch on the map: {name}', lambda r: 0,
                           extra=[('04EDD', '%02X' % item), ('04EDE', '00')], timing=MAP_PREVIEW)


def api_spellrow(b, q):
    """Add an item to the spell table ({add: item, spell}) or remove a row ({delete: row}); one undo step."""
    p = need_project()
    t = p.table('spells')
    if 'delete' in b:
        k = int(b['delete'])
        p.edit([('rows', 'spells', k, [dict(t.rows[k])], [])])
        return {'ok': True}
    item = int(b['add'])
    if any(int(r['item']) == item for r in t.rows):
        raise ValueError('That item already has an effect; change it in its row.')
    sp = int(b.get('spell', 2))
    it = p.table('items')
    name = next((r.get('_name', '') for r in it.rows if int(r['index']) == item), '') if it else ''
    row = {'item': str(item), '_item': name, 'spell': str(sp), 'spell_far': str(sp)}
    p.edit([('rows', 'spells', len(t.rows), [], [row])])
    return {'ok': True}


def api_battlemotions(b, q):
    """A row's motions as the game will play them, plus which ones you changed."""
    p = need_project()
    row = int(q.get('row', ['0'])[0])
    r = p.table('battle_anims').rows[row]
    c = _custom_for(r)
    rom = battle_rom()
    a = int(r['anim'])
    mot = fe4battle.motions(rom, a)
    n = len(fe4battle.layouts(rom, a))
    base_n = len(fe4battle.layouts(rom_data(), int(c[1]['from'][0]) if c else a))
    return {'motions': [[list(x) for x in m] for m in mot], 'frames': n, 'baseFrames': base_n,
            'edited': sorted(int(k) for k in (c[1].get('motions') or {})) if c else [],
            'commands': {str(k): list(v) for k, v in fe4battle.COMMANDS.items()}}


def api_battlereset(b, q):
    """Put a row back on its look's original drawings (the drawing file stays for other rows)."""
    p = need_project()
    t = p.table('battle_anims')
    row = int(b['row'])
    r = t.rows[row]
    c = _custom_for(r)
    if not c:
        raise ValueError('This row uses the game\'s own drawings.')
    a0, b0 = c[1]['from'][0], c[1]['from'][1]
    ops = [('cell', 'battle_anims', row, f, r[f], str(v)) for f, v in (('anim', a0), ('body', b0)) if r[f] != str(v)]
    p.edit(ops)
    return {'ok': True}


def api_battleinfo(b, q):
    """Frame size, frame count and motion scripts for one look (the image is /gfx/battle/?a=..)."""
    def g(k):
        return int((q.get(k) or [b.get(k, -1)])[0])
    got = battle_strip(g('a'), g('b'), g('u'), g('p'), g('i'))
    if not got:
        rom = rom_data()
        key = (g('a'), g('b'), g('u'), g('p'), g('i'))
        err = (_battle_cache.get(key) or (None, {}))[1].get('error')
        raise ValueError('This combination can\'t be shown' + (f' ({err}).' if err else '.'))
    return got[1]


def api_testplay(b, q):
    p = need_project()
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    exe = port_exe()
    if not exe:
        raise ValueError('The FE4 PC port wasn\'t found. Choose where FE4.exe is (Settings).')
    p.save()
    d = os.path.join(p.path, '_testplay')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, os.path.basename(os.path.normpath(p.path)) + '.smc')
    hover = bool(settings.get('hover_stats', False))

    args = [exe, '--play', out]
    if fe4music.music_files(p.path) and port_knows(exe, b'--music'):
        args += ['--music', os.path.join(p.path, fe4music.FOLDER)]

    def go():
        fe4hack.build(rom, p.path, out, None, hover)
        subprocess.Popen(args, cwd=os.path.dirname(exe))
        print('started the PC port')
        return out
    return job_json_of(run_job('Building for test play', go))


def api_testchapter(b, q):
    """Build, make a copy whose New Game goes to chapter `ch` (fe4teststart), and open the PC port."""
    import fe4teststart
    p = need_project()
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    exe = port_exe()
    if not exe:
        raise ValueError('The FE4 PC port wasn\'t found. Choose where FE4.exe is (Settings).')
    ch = int(b.get('ch', 0))
    p.save()
    d = os.path.join(p.path, '_testplay')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, os.path.basename(os.path.normpath(p.path)) + f'_ch{ch:02d}.smc')
    hover = bool(settings.get('hover_stats', False))
    args = [exe, '--play', out]
    if fe4music.music_files(p.path) and port_knows(exe, b'--music'):
        args += ['--music', os.path.join(p.path, fe4music.FOLDER)]

    def go():
        fe4hack.build(rom, p.path, out, None, hover)
        copier, data = L.load_rom(out)
        msg = fe4teststart.apply(data, ch)
        L.save_rom(out, copier, data)
        print(msg)
        subprocess.Popen(args, cwd=os.path.dirname(exe))
        print('started the PC port: choose New Game')
        return out
    title = CHAPTER_TITLES[ch].split(':')[0] if ch < len(CHAPTER_TITLES) else f'chapter {ch}'
    return job_json_of(run_job(f'Building to test {title}', go))


PREVIEW = {'start': 25300, 'end': 26250, 'from': 25200, 'events_from': 25000, 'item': 0x3E,
           'freeze': [('0D5C', '35'), ('0D60', '3E'), ('0D69', '74')]}   # Gandolf: Fire Mage, Fire, magic


# Map battle preview: the Prologue fight made a calculated one ($84:B69E JSL $84:DF87 -> JSL $84:DCA3), which
# the game shows as a map battle; Midir (the attacker, figure $7F:454E) gets the figure being watched.
MAP_PREVIEW = {'start': 25590, 'end': 25960, 'from': 25000, 'freeze': [], 'map': True}
MAP_PATCH = (0x84B69E, bytes.fromhex('2287df84'), bytes.fromhex('22a3dc84'))


def _battle_preview(title, change, extra=(), loop_extra=0, timing=None):
    """Build a copy of the ROM with only the project's battle, spell and skill-animation changes (then
    change(rom) on it) and run it in the PC port: fast from power-on with the preview input movie to the
    Prologue battle where Gandolf (made a Fire Mage) attacks Midir, then that battle over and over.
    extra: more (address, value) or (address, value, from frame) RAM freezes."""
    T = timing or PREVIEW
    p = need_project()
    rom = rom_path()
    if not rom:
        raise ValueError('Choose your FE4 ROM first.')
    exe = port_exe()
    if not exe:
        raise ValueError('The FE4 PC port wasn\'t found. Choose where FE4.exe is (Settings).')
    try:
        with open(exe, 'rb') as fh:
            new_port = b'--turbo-until' in fh.read()
    except OSError:
        new_port = False
    if not new_port:
        raise ValueError('Watching in battle needs the PC port 0.9 or newer (it comes with this kit in FE4Port.zip).')
    movie = os.path.join(KIT, 'dev', 'battle_preview.txt')
    if not os.path.exists(movie):
        raise ValueError('The battle preview input is missing from this kit.')
    p.save()
    d = os.path.join(p.path, '_testplay')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, 'battle_preview.smc')

    def go():
        import fe4skillanim
        copier, r = L.load_rom(rom)
        far = L.FreeSpace()
        fe4battle.apply(r, p.path)
        fe4spellfx.apply_all(r, p.path, far)
        fe4skillanim.apply(r, p.path, fe4spellfx.spell_count(r))
        fe4battle.apply_custom(r, lambda rel: fe4hack._read_file(p.path, rel), far)
        if T.get('map'):
            import fe4mapbattle
            fe4mapbattle.apply(r, p.path, far, 72)
            fe4mapfx.apply(r, p.path, far)
            a, was, now = MAP_PATCH
            f = fe4spellfx.snes_to_file(a)
            if bytes(r[f:f + 4]) != was:
                raise SystemExit('This ROM\'s Prologue battle code is different; the map battle preview can\'t run.')
            r[f:f + 4] = now
        loop = change(r) or 0
        L.save_rom(out, copier, r)
        import hashlib
        from fe4project import settings_path
        freezes = [tuple(f) + (T['from'],) if len(f) == 2 else tuple(f) for f in list(T['freeze']) + list(extra)]
        sha = hashlib.sha1(bytes(L.load_rom(rom)[1]) + repr(freezes).encode() + (b'map' if T.get('map') else b'')).hexdigest()[:12]
        cache = os.path.join(os.path.dirname(settings_path()), f'battle_preview_{sha}.state')
        args = [exe, '--play', out, '--movie', movie, '--turbo-until', str(T['start']), '--state-cache', cache,
                '--loop-at', str(T['end'] + loop + loop_extra), '--title', title]
        for a, v, fr in freezes:
            args += ['--freeze', a, v, str(fr)]
        subprocess.Popen(args, cwd=os.path.dirname(exe))
        print('started the PC port: it plays the Prologue at full speed up to the battle, then shows it over and over')
        return out
    return job_json_of(run_job('Building the battle preview', go))


def api_spellpreview(b, q):
    """Watch an effect in battle: the Fire tome plays it (see _battle_preview)."""
    s = int(b['spell'])
    names = _spell_label(spell_rom()[0])

    def change(r):
        if not 0 <= s < fe4spellfx.spell_count(r):
            raise SystemExit(f'There is no effect {s}.')
        f = fe4spellfx.snes_to_file(fe4battle.SPELL_TABLE)
        rows = fe4battle.spell_rows(r)
        k = next(i for i, row in enumerate(rows) if row[0] == PREVIEW['item'])
        r[f + 3 * k + 1] = r[f + 3 * k + 2] = s
        return sum(x & 0x1FF for x in fe4spellfx.script_words(r, s) if x < 0xFF00 and (x >> 9) & 0x1F in (0x0A, 0x18))
    return _battle_preview(f'Watch in battle: {names.get(s) or f"effect {s}"}', change)


def api_skillpreview(b, q):
    """Watch a skill's animation: the battle's event list starts with the skill's event (FE nn), then the
    game's own strike (the Prologue battle's list is 35 20 FF FF from $7E:4F85). The game writes that list at
    frame 25193, so these freezes start earlier than the others."""
    sid = int(b['skill'])
    if not 1 <= sid <= 0xFE:
        raise ValueError('There is no such skill.')
    ev = [(a, v, PREVIEW['events_from']) for a, v in
          [('4F85', 'FE'), ('4F86', f'{sid:02X}'), ('4F87', '35'), ('4F88', '20'), ('4F89', 'FF'), ('4F8A', 'FF')]]
    return _battle_preview(f'Watch in battle: {_skill_names().get(sid) or f"skill {sid}"}', lambda r: 0, ev, 120)


def api_settings(b, q):
    if 'hoverStats' in b:
        settings['hover_stats'] = bool(b['hoverStats'])
    if 'msu' in b:
        settings['msu'] = bool(b['msu'])
    if 'port' in b:
        settings['port'] = b['port']
    save_settings(settings)
    return api_session(b, q)


def api_dialog(b, q):
    """Native file picker (the page can't see full paths): runs on the main thread."""
    reply = queue.Queue()
    dialogs.put((b.get('kind'), b, reply))
    return {'path': reply.get()}


def api_classic(b, q):
    """Open the table-style editor (fe4editor) for what the studio doesn't cover yet."""
    if getattr(sys, 'frozen', False):
        subprocess.Popen([sys.executable, 'classic'])
    else:
        subprocess.Popen([sys.executable, os.path.join(KIT, 'fe4editor.py'), 'classic'])
    return {'ok': True}


def api_quit(b, q):
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return {'ok': True}

# ---------------------------------------------------------------- maps
def chapter_title(ch):
    """'Chapter 3: <title>' with the project's own title when it has one."""
    t = CHAPTER_TITLES[ch]
    try:
        own = chaptitle_data().get(ch, {}).get('text')
    except Exception:
        own = None
    return t.split(':')[0] + ': ' + own if own else t


CHAPTER_TITLES = ['Prologue: Birth of a Crusader', "Chapter 1: The Spirit Forest's Maiden", 'Chapter 2: Crisis in Agustria',
                  'Chapter 3: Eldigan the Lionheart', 'Chapter 4: Dance in the Skies', 'Chapter 5: Threshold of Fate',
                  'Chapter 6: Heirs to the Light', 'Chapter 7: Beyond the Desert',
                  'Chapter 8: The Dracoknights of Thracia', 'Chapter 9: For Whose Sake',
                  'Chapter 10: Light and Darkness', 'Endgame: The Final Holy War']
# terrain types 0-7 are named by the game's terrain window text; the rest are named from how they look
TERRAIN_NAMES = {0: 'Peak', 1: 'Thicket', 2: 'Cliff', 3: 'Plain', 4: 'Forest', 5: 'Sea', 6: 'River', 7: 'Mountain',
                 8: 'Desert', 9: 'Castle', 10: 'Gate', 12: 'Castle gate', 13: 'Castle walls', 14: 'Wasteland',
                 15: 'Bridge', 18: 'Houses', 22: 'Village', 24: 'Tower', 25: 'Road', 26: 'Floor'}
IMPASSABLE = {0, 5}


def deploy_chapters(evdir):
    """Deploy list -> chapter, from the chapter scripts and the scenes they run."""
    import re
    scene_lists, cur = {}, None
    proj = project()
    same = proj is not None and os.path.normpath(evdir) == os.path.normpath(os.path.join(proj.path, 'events'))

    def lines(f):                  # the open project's files as edited, else the files on disk
        if same and proj.evt(f) is not None:
            return proj.evt(f).lines
        return open(os.path.join(evdir, f), encoding='utf-8', errors='replace')
    p = os.path.join(evdir, 'scenes.evt')
    if os.path.exists(p):
        for line in lines('scenes.evt'):
            m = re.match(r'== scene (\d+)', line)
            if m:
                cur = int(m.group(1))
                continue
            m = re.search(r'deploy list (\d+)', line)
            if m and cur is not None:
                scene_lists.setdefault(cur, set()).add(int(m.group(1)))
    out = {}
    if os.path.isdir(evdir):
        for f in sorted(os.listdir(evdir)):
            m = re.match(r'ch(\d+)_.*\.evt$', f)
            if not m:
                continue
            ch = int(m.group(1))
            for line in lines(f):
                for m2 in re.finditer(r'deploy list (\d+)', line):
                    out.setdefault(int(m2.group(1)), ch)
                for m2 in re.finditer(r'scene (\d+)', line):
                    for lst in scene_lists.get(int(m2.group(1)), ()):
                        out.setdefault(lst, ch)
    return out


def unit_lookup():
    """char_id -> (table, row) over all unit tables (playable first)."""
    p = project()
    out = {}
    for t in ('units_playable', 'units_children', 'units_npc', 'units_generic'):
        tb = p.table(t)
        for r in tb.rows if tb else []:
            cid = (r.get('char_id') or '').strip()
            if cid.isdigit():
                out.setdefault(int(cid), (t, r))
    return out


def api_maps(b, q):
    p = need_project()
    out = []
    for f in p.map_files():
        ch = int(f[2:4])
        out.append({'ch': ch, 'file': f, 'title': chapter_title(ch) if ch < len(CHAPTER_TITLES) else f})
    return {'maps': out}


def api_map(b, q):
    p = need_project()
    ch = int(q.get('ch', ['0'])[0])
    m = p.map(ch)
    if m is None:
        raise KeyError(f'no map for chapter {ch}')
    rom = rom_data()
    terrain = list(fe4gfx.map_atlas(rom, ch)[1]) if rom is not None else [0] * 1024
    for k, t_ in chapter_terrain(ch).items():
        terrain[k] = t_
    # castles and villages
    locs = []
    lt = p.table('locations')
    for i, r in enumerate(lt.rows if lt else []):
        if str(r.get('chapter')) == str(ch):
            locs.append({'_row': i, 'index': r.get('index'), 'kind': r.get('kind'), 'name': r.get('_castle_name') or '',
                         'x': r.get('x'), 'y': r.get('y'), 'gold': r.get('gold', ''), 'facilities': r.get('facilities', '')})
    # deploy lists that belong to this chapter
    dch = deploy_chapters(os.path.join(p.path, 'events'))
    lists = {}
    dt = p.table('deploy')
    known = sorted(dch)

    def chapter_of(n):
        if n in dch:
            return dch[n], True
        before = [k for k in known if k < n]
        return (dch[before[-1]] if before else 0), False
    armies = {}
    at = p.table('armies')
    for r in at.rows if at else []:
        for use in (r.get('_used_in') or '').split(';'):
            if use.startswith(f'ch{ch}/slot'):
                armies[use.split('slot')[1]] = r.get('_name') or ('Army ' + r.get('army', ''))
    units = unit_lookup()
    itb = p.table('item_instances')
    inst = {_num(r.get('instance'), -1): _num(r.get('item_type'), 255) for r in (itb.rows if itb else [])}
    for i, r in enumerate(dt.rows if dt else []):
        lst, _, ent = (r.get('index') or '').partition('.')
        if not lst.isdigit():
            continue
        c, sure = chapter_of(int(lst))
        if c != ch:
            continue
        cid = int(r['char_id']) if (r.get('char_id') or '').isdigit() else -1
        t, ur = units.get(cid, (None, None))
        portrait = None
        cls = lvl = ''
        if ur is not None:
            cls, lvl = ur.get('_class_name', ''), ur.get('level', '')
            if t == 'units_generic':
                pn = ur.get('portrait', '')
                portrait = int(pn) if pn.isdigit() and int(pn) < fe4gfx.PORTRAIT_COUNT and int(pn) != fe4gfx.NO_PORTRAIT else None
            else:
                portrait = unit_portrait(t, ur)
        L_ = lists.setdefault(int(lst), {'list': int(lst), 'sure': sure, 'units': []})
        ur_ = ur or {}
        L_['units'].append({'_row': i, 'entry': ent, 'char_id': cid, 'name': ur_.get('_name') or r.get('_name') or f'Unit {cid}',
                            'table': t, 'class': cls, 'level': lvl, 'portrait': portrait, 'x': r.get('x'), 'y': r.get('y'),
                            'cls': _num(ur_.get('class'), -1), 'nameId': _num(ur_.get('name_id'), -1),
                            'items': [v for v in (_num(ur_.get(k), 255) for k in ('item1', 'item2', 'item3')) if v != 255]
                            if t == 'units_generic' else [inst.get(v, 255) for v in (_num(ur_.get(k), 255) for k in ('item1', 'item2', 'item3')) if v != 255],
                            'army_slot': r.get('army_slot'), 'army': armies.get(str(r.get('army_slot')), ''),
                            'leader': r.get('leader_flag') not in ('', '0', None), 'orders': r.get('orders')})
    try:
        whens = chapter_lists(ch)
        endings = chapter_endings(ch)
    except KeyError:
        whens, endings = {}, []
    return {'ch': ch, 'title': chapter_title(ch) if ch < len(CHAPTER_TITLES) else '', 'width': m.WIDTH,
            'height': (len(m.words) + m.WIDTH - 1) // m.WIDTH, 'words': m.words, 'terrain': terrain,
            'terrainNames': {str(k): v for k, v in TERRAIN_NAMES.items()}, 'impassable': sorted(IMPASSABLE),
            'locations': locs, 'deploy': [dict(lists[k], when=whens.get(k, {}).get('when', '')) for k in sorted(lists)], 'areas': chapter_areas(ch),
            'endings': endings,
            'tilesVer': tiles_version(ch), 'area': list(map_area(ch))}


def map_area(ch):
    """(x, y, width, height) of the part of the 64 x 64 layout the chapter shows (map_sizes.csv, kit v57)."""
    rom = rom_data()
    t = need_project().table('map_sizes')
    for r in t.rows if t else []:
        if r.get('chapter') == str(ch):
            try:
                return int(r.get('x') or 0), int(r.get('y') or 0), int(r['width']), int(r['height'])
            except (KeyError, ValueError):
                break
    return fe4maps.rom_size(rom, ch) if rom is not None else (0, 0, 64, 64)


def api_mapsize(b, q):
    """{ch, x, y, w, h}: the part of the layout the chapter shows.  One undo step."""
    p = need_project()
    ch = int(b['ch'])
    x, y, w, h = (int(b[k]) for k in ('x', 'y', 'w', 'h'))
    if not (fe4maps.MIN_W <= w and fe4maps.MIN_H <= h and x >= 0 and y >= 0 and x + w <= 64 and y + h <= 64):
        raise ValueError(f'A map is at least {fe4maps.MIN_W} x {fe4maps.MIN_H} cells (one screen) and fits in 64 x 64.')
    t = p.table('map_sizes')
    if t is None:
        fe4maps.export_sizes(rom_data(), os.path.join(p.path, fe4maps.SIZES_FILE))
        t = p.table('map_sizes')
    row = next((i for i, r in enumerate(t.rows) if r.get('chapter') == str(ch)), None)
    if row is None:
        raise KeyError(f'map_sizes.csv has no row for chapter {ch}')
    ops = [('cell', 'map_sizes', row, k, t.rows[row].get(k, ''), str(v))
           for k, v in (('x', x), ('y', y), ('width', w), ('height', h)) if t.rows[row].get(k, '') != str(v)]
    if ops:
        p.edit(ops)
    return {'ok': True}


def chapter_areas(ch):
    """Area events (condition $0B) of a chapter: [{file, line, unit, who, x1, y1, x2, y2}]."""
    try:
        name = chapter_file(ch)
    except KeyError:
        return []
    com = commenter() if rom_data() is not None else None
    out = []
    for cnd, steps in chapter_triggers(name):
        b = cmd_bytes(cnd)
        if b[0] == 0x0B and len(b) >= 8:
            u = b[2] | b[3] << 8
            out.append({'file': name, 'line': cnd['line'], 'unit': u, 'x1': b[4], 'y1': b[5], 'x2': b[6], 'y2': b[7],
                        'who': 'Anyone' if u == 0xFFFF else (com.unit(u).rsplit('(', 1)[0].strip() if com else f'Unit {u}')})
    return out


def api_paint(b, q):
    """{ch, cells: [[index, word], ...]} as one undo step."""
    p = need_project()
    ops = p.paint(int(b['ch']), [(int(i), int(v)) for i, v in b.get('cells', [])])
    return {'ok': True, 'changed': len(ops)}


# ---------------------------------------------------------------- events and dialogue
_commenter = {}


def commenter():
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    if id(rom) not in _commenter:
        _commenter.clear()
        _commenter[id(rom)] = fe4events.Commenter(rom)
    return _commenter[id(rom)]


def _ptr(b, i):
    return '%06X' % (b[i] | b[i + 1] << 8 | b[i + 2] << 16)


def message_refs(name, b, toks=None):
    """Message keys a command shows: (key, kind). toks = the command's hex tokens, where a new
    message is written @Nxxxxx in place of its 3 address bytes."""
    if not b:
        return []

    def at(i):
        if toks is not None:
            pos = 0
            for t in toks:
                if pos == i and t.startswith('@'):
                    return t[1:]
                pos += 3 if t.startswith('@') else 1
        return _ptr(b, i)
    if name == 'scenes.evt':
        if b[0] in (0x0C, 0x14) and len(b) >= 4:
            return [(at(1), 'TEXT' if b[0] == 0x0C else 'TEXT_WINDOW')]
        if b[0] in (0x4A, 0x4D) and len(b) >= 6 and b[1] in (0x31, 0x32):
            return [(at(3), 'TALK')]
        return []
    if b[0] in (0x31, 0x32) and len(b) >= 5:
        return [(at(2), 'TALK')]
    return []


def cmd_msg(name, c):
    r = message_refs(name, cmd_bytes(c), c['hex'].split())
    return r[0][0] if r else None


def scene_refs(name, b):
    if name == 'scenes.evt':
        return [b[3] | b[4] << 8] if len(b) >= 5 and b[0] in (0x4A, 0x4D) and b[1] == 0x30 else []
    return [b[2] | b[3] << 8] if len(b) >= 4 and b[0] == 0x30 else []


def cmd_bytes(c):
    """The command's bytes; a new message token (@Nxxxxx) counts as three zero bytes."""
    out = bytearray()
    for t in c['hex'].split():
        if t.startswith('@L'):
            out += b'\0\0'                  # a jump to another command of the block
        elif t.startswith('@'):
            out += b'\0\0\0'
        else:
            try:
                out.append(int(t, 16))
            except ValueError:
                return b''
    return bytes(out)


_index = {'key': None}


def story_index():
    """Who shows which message, and which chapter runs which scene (rebuilt after event edits)."""
    p = need_project()
    key = (id(p), tuple((n, f.version) for n, f in sorted(p.evts.items())))
    if _index['key'] == key:
        return _index
    scenes, msg_uses, chapter_scenes = {}, {}, {}
    for name in p.evt_files():
        f = p.evt(name)
        for blk in f.blocks():
            sid = None
            if name == 'scenes.evt':
                m = re.match(r'scene\s+(\d+)', blk['label'])
                sid = int(m.group(1)) if m else None
                scenes[sid] = {'block': blk, 'messages': [], 'runs': []}
            for c in blk['cmds']:
                b = cmd_bytes(c)
                for k, kind in message_refs(name, b, c['hex'].split()):
                    if sid is not None:
                        scenes[sid]['messages'].append(k)
                        msg_uses.setdefault(k, []).append({'scene': sid, 'kind': kind})
                    else:
                        msg_uses.setdefault(k, []).append({'file': name, 'line': c['line'], 'kind': kind})
                for t in scene_refs(name, b):
                    if sid is not None:
                        scenes[sid]['runs'].append(t)
                    else:
                        chapter_scenes.setdefault(t, set()).add(name)
    # scenes started by other scenes belong to the same chapters
    changed = True
    while changed:
        changed = False
        for sid, sc in scenes.items():
            for t in sc['runs']:
                for f in chapter_scenes.get(sid, ()):
                    if f not in chapter_scenes.setdefault(t, set()):
                        chapter_scenes[t].add(f)
                        changed = True
    _index.update(key=key, scenes=scenes, msg_uses=msg_uses, chapter_scenes=chapter_scenes)
    return _index


def people():
    """Character IDs 1-768 with a name and a portrait (IDs from 570 are speakers only)."""
    rom = rom_data()
    c = commenter()
    by_portrait, out = {}, []
    for i in range(1, 769):
        n = re.sub(r'\(\d+\)$', '', c.unit(i)) if i <= len(c.addrs) else ''
        if n in ('unit', 'any') or n.startswith('#'):
            n = ''
        pt = fe4gfx.portrait_of_char(rom, i)
        if n and pt is not None:
            by_portrait.setdefault(pt, n)
        out.append({'id': i, 'name': n, 'portrait': pt})
    for x in out:
        if not x['name'] and x['portrait'] is not None and x['portrait'] in by_portrait:
            x['name'] = by_portrait[x['portrait']]
            x['speaker'] = True
    return out


TEXT_WIDTHS = 0x119971      # $91:9971: glyph width in pixels per text code - $10 (read by Naga's VWF at $51:0083)
TEXT_BOX_WIDTH = 224        # widest line in the game's own dialogue is 223 px
TEXT_BOX_LINES = 3


def api_textinfo(b, q):
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    widths = {chr_: rom[TEXT_WIDTHS + code - 0x10] for code, chr_ in fe4events._CH.items() if 0x10 <= code < 0x100}
    codes = {'%02X' % code: rom[TEXT_WIDTHS + code - 0x10] for code in range(0x10, 0x100)}
    return {'widths': widths, 'codeWidths': codes, 'chars': ''.join(sorted(fe4events._CH_INV)),
            'boxWidth': TEXT_BOX_WIDTH, 'boxLines': TEXT_BOX_LINES}


def api_people(b, q):
    need_project()
    return {'people': people()}


def evt_json(name):
    f = need_project().evt(name)
    if f is None:
        raise KeyError(f'no events file {name}')
    return [{'label': blk['label'], 'start': blk['start'],
             'cmds': [dict(c, name=c['comment'].split(' ')[0] if c['comment'] else '', msg=cmd_msg(name, c),
                           note=' '.join(c['comment'].split()[1:])) for c in blk['cmds']]}
            for blk in f.blocks()]


def api_events(b, q):
    p = need_project()
    ch = int(q.get('ch', ['0'])[0])
    name = next((f for f in p.evt_files() if f.startswith('ch%02d_' % ch)), None)
    if name is None:
        raise KeyError(f'no events for chapter {ch}')
    idx = story_index()
    locs = []
    lt = p.table('locations')
    for i, r in enumerate(lt.rows if lt else []):
        if str(r.get('chapter')) == str(ch):
            locs.append({'index': r.get('index'), 'kind': r.get('kind'), 'name': r.get('_castle_name') or '',
                         'x': r.get('x'), 'y': r.get('y')})
    scenes = {}
    for blk in evt_json(name):
        for c in blk['cmds']:
            for sid in scene_refs(name, cmd_bytes(c)):
                sc = idx['scenes'].get(sid)
                if sc:
                    extras = []                     # gifts and arrivals inside the scene (and the ones it starts)
                    for g in scene_gifts(sid, idx):
                        extras.append(dict(g))
                    for c2 in sc['block']['cmds']:
                        b2 = cmd_bytes(c2)
                        if len(b2) >= 3 and b2[0] == 0x4A and b2[1] == 0x4E:
                            extras.append({'kind': 'deploy', 'list': b2[2], 'file': 'scenes.evt', 'line': c2['line']})
                    scenes[sid] = {'messages': sc['messages'], 'runs': sc['runs'], 'extras': extras}
    tt = p.table('talks')
    talks = [list(k[1:]) for k in (_talk_key(r) for r in (tt.rows if tt else [])) if k and k[0] == ch]
    return {'ch': ch, 'title': CHAPTER_TITLES[ch] if ch < len(CHAPTER_TITLES) else name, 'file': name,
            'blocks': evt_json(name), 'locations': locs, 'scenes': scenes,
            'talks': talks if tt else None}


def api_talkmenu(b, q):
    """Add or remove the Talk-list entry of the talk event whose condition is on `line`: {file, line, on}."""
    p = need_project()
    name, line = b['file'], int(b['line'])
    if p.table('talks') is None:
        raise ValueError('This project has no talks.csv; reopen it with this version to add one.')
    c = next((c for blk in p.evt(name).blocks() for c in blk['cmds'] if c['line'] == line), None)
    cb = cmd_bytes(c) if c else b''
    if not name.startswith('ch') or len(cb) < 6 or cb[0] not in (0x04, 0x16):
        raise ValueError('That line is not a talk event.')
    ops = {'list': []}
    talk_row_ops(int(name[2:4]), cb[1], cb[2] | cb[3] << 8, cb[4] | cb[5] << 8, bool(b.get('on')), ops)
    p.edit(ops['list'])
    return {'ok': True}


def api_chapters(b, q):
    p = need_project()
    out = []
    for f in p.evt_files():
        m = re.match(r'ch(\d+)_', f)
        if m and int(m.group(1)) < len(CHAPTER_TITLES):
            out.append({'ch': int(m.group(1)), 'title': CHAPTER_TITLES[int(m.group(1))]})
    return {'chapters': out}


def api_scene(b, q):
    need_project()
    sid = int(q.get('id', ['0'])[0])
    sc = story_index()['scenes'].get(sid)
    if sc is None:
        raise KeyError(f'no scene {sid}')
    blk = sc['block']
    cur = next((x for x in evt_json('scenes.evt') if x['label'] == blk['label']), blk)
    return {'id': sid, 'start': blk['start'], 'cmds': cur['cmds'], 'messages': sc['messages'], 'runs': sc['runs']}


def api_messages(b, q):
    d = need_project().dialogue()
    if d is None:
        raise KeyError('This project has no events/dialogue.txt.')
    uses = story_index()['msg_uses']
    return {k: {'text': d.text[k], 'where': d.where[k], 'uses': uses.get(k, [])} for k in b.get('keys', []) if k in d.text}


def api_msg(b, q):
    p = need_project()
    key, text = b['key'].upper(), b.get('text', '')
    try:
        enc = fe4events.text_encode(text)
    except ValueError as e:
        raise ValueError(str(e).replace('use {XX}', 'it can\'t be shown in the game'))
    if not enc.endswith(b'\x01'):
        raise ValueError('A message has to end with {01}.')
    p.set_message(key, text)
    return {'ok': True, 'text': text}


def api_evtcmd(b, q):
    p = need_project()
    name, line = b['file'], int(b['line'])
    f = p.evt(name)
    if f is None:
        raise KeyError(f'no events file {name}')
    old = next((c for blk in f.blocks() for c in blk['cmds'] if c['line'] == line), None)
    if old is None:
        raise KeyError(f'line {line + 1} of {name} is not a command')
    if '@' in old['hex']:
        raise ValueError('This step shows a new message; change its text in the conversation below.')
    try:
        new = bytes(int(x, 16) for x in b['hex'].split())
    except ValueError:
        raise ValueError('Write the bytes as hex pairs, like 02 00 00 00 03 00.')
    if len(new) != len(cmd_bytes(old)):
        raise ValueError(f'This step is {len(cmd_bytes(old))} bytes; keep the same length.')
    if new[0] != cmd_bytes(old)[0]:
        raise ValueError('Changing what kind of step this is isn\'t possible here.')
    com = commenter()
    hexs = ' '.join('%02X' % x for x in new)
    if name == 'scenes.evt':
        nm, note = com.sc(int(old['addr'] or '0', 16), new)
    elif new == b'\xff\xff':
        nm, note = 'END', ''
    else:
        nm, note = fe4events.EV_NAMES.get(new[0], 'OP_%02X' % new[0]), com.ev(new)
    comment = ('%-14s %s' % (nm, note)).rstrip() if name != 'scenes.evt' else ('%-13s %s' % (nm, note)).rstrip()
    ops = []
    line_new = f.set_command(line, hexs, comment)
    if f.lines[line] != line_new:
        ops.append(('evt', name, line, f.lines[line], line_new))
    ob = cmd_bytes(old)
    tb = p.table('talks')
    if tb and name.startswith('ch') and ob[0] in (0x04, 0x16) and len(ob) >= 6:
        # keep the chapter's Talk-list entry in step with the talk event
        okey = (int(name[2:4]), ob[1], ob[2] | ob[3] << 8, ob[4] | ob[5] << 8)
        for i, r in enumerate(tb.rows):
            if _talk_key(r) == okey:
                vals = {'flag': '0x%02X' % new[1], 'from': 'any' if new[2] | new[3] << 8 == 0xFFFF else str(new[2] | new[3] << 8),
                        'to': str(new[4] | new[5] << 8)}
                nmf = lambda u: 'anyone' if u == 0xFFFF else com.unit(u).rsplit('(', 1)[0]  # noqa: E731
                vals['_from_name'], vals['_to_name'] = nmf(new[2] | new[3] << 8), nmf(new[4] | new[5] << 8)
                for k, v in vals.items():
                    if k in tb.fields and r.get(k, '') != v:
                        ops.append(('cell', 'talks', i, k, r.get(k, ''), v))
    p.edit(ops)
    return {'ok': True, 'hex': hexs, 'name': nm, 'note': note}


def api_dsearch(b, q):
    d = need_project().dialogue()
    if d is None:
        return {'results': []}
    words = (q.get('q', [''])[0]).strip().lower()
    if len(words) < 2:
        return {'results': []}
    uses = story_index()['msg_uses']
    idx = story_index()
    out = []
    for k in d.order:
        plain = re.sub(r'\{[0-9A-F ]+\}', ' ', d.text[k])
        plain = re.sub(r'\s+', ' ', plain).strip()
        i = plain.lower().find(words)
        if i < 0:
            continue
        chs = set()
        for u in uses.get(k, []):
            if 'file' in u:
                chs.add(u['file'])
            else:
                chs |= idx['chapter_scenes'].get(u['scene'], set())
        out.append({'key': k, 'snippet': plain[max(0, i - 50):i + 90], 'at': min(i, 50), 'uses': uses.get(k, []),
                    'chapters': sorted(int(c[2:4]) for c in chs)})
        if len(out) >= 150:
            break
    return {'results': out}


# ---------------------------------------------------------------- items, shops and villages
COND_OPS = {0x01, 0x02, 0x03, 0x04, 0x05, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x16, 0x1A, 0x21}


def gift_of(name, c):
    """A GIVE_ITEM or STAT_UP command as a dict, or None. Scenes run them through EVENT ($4A)."""
    b = cmd_bytes(c)
    o = 1 if name == 'scenes.evt' and len(b) > 1 and b[0] == 0x4A else 0
    if name == 'scenes.evt' and not o:
        return None
    if len(b) >= o + 4 and b[o] == 0x57:
        u = b[o + 1] | b[o + 2] << 8
        return {'file': name, 'line': c['line'], 'hex': c['hex'], 'kind': 'item', 'pos': o,
                'unit': None if u == 0xFFFF else u, 'instance': b[o + 3]}
    if len(b) >= o + 4 and b[o] == 0x70:
        return {'file': name, 'line': c['line'], 'hex': c['hex'], 'kind': 'stat', 'pos': o,
                'unit': None if b[o + 1] == 0xFF else b[o + 1], 'stat': b[o + 2], 'amount': b[o + 3]}
    return None


def scene_gifts(sid, idx, seen=None):
    """Gifts in a scene and the scenes it starts."""
    seen = seen if seen is not None else set()
    if sid in seen or sid not in idx['scenes']:
        return []
    seen.add(sid)
    sc = idx['scenes'][sid]
    out = [dict(g, scene=sid) for g in (gift_of('scenes.evt', c) for c in sc['block']['cmds']) if g]
    for t in sc['runs']:
        out += scene_gifts(t, idx, seen)
    return out


def chapter_triggers(name):
    """[(condition command, [steps])] of a chapter file's trigger blocks."""
    f = need_project().evt(name)
    out = []
    for blk in f.blocks():
        if blk['label'] == 'init':
            continue
        cur = None
        for c in blk['cmds']:
            b = cmd_bytes(c)
            if b and b[0] in COND_OPS and b[0] not in STRUCT_OPS:
                cur = (c, [])
                out.append(cur)
            elif b and (b[0] in STRUCT_OPS or b == b'\xff\xff'):
                cur = None                   # the list's structured tail is not part of an event
            elif cur:
                cur[1].append(c)
    return out


def api_villages(b, q):
    """Each village and castle of a chapter with what visiting it gives."""
    p = need_project()
    ch = int(q.get('ch', ['0'])[0])
    name = next((f for f in p.evt_files() if f.startswith('ch%02d_' % ch)), None)
    idx = story_index()
    visits = {}
    for cond, steps in (chapter_triggers(name) if name else []):
        cb = cmd_bytes(cond)
        if cb[0] != 0x0A or len(cb) < 6:
            continue
        loc = cb[4] | cb[5] << 8
        v = {'line': cond['line'], 'file': name, 'scenes': [], 'gifts': []}
        for c in steps:
            sb = cmd_bytes(c)
            if sb and sb[0] == 0x30 and len(sb) >= 4:
                sid = sb[2] | sb[3] << 8
                v['scenes'].append(sid)
                v['gifts'] += scene_gifts(sid, idx)
            g = gift_of(name, c)
            if g:
                v['gifts'].append(g)
        visits.setdefault(loc, []).append(v)
    return {'ch': ch, 'file': name, 'visits': {str(k): v for k, v in visits.items()}}


def api_itemuse(b, q):
    """Where each item instance is: who starts with it, which shop sells it, which event gives it."""
    p = need_project()
    use = {}

    def add(inst, what):
        if inst is not None and 0 <= inst < 255:
            use.setdefault(str(inst), []).append(what)
    for t in ('units_playable', 'units_children'):
        tb = p.table(t)
        for i, r in enumerate(tb.rows if tb else []):
            for k in ('item1', 'item2', 'item3'):
                v = (r.get(k) or '').strip()
                if v.isdigit() and int(v) != 255:
                    add(int(v), {'kind': 'unit', 'table': t, 'row': i, 'name': r.get('_name') or ''})
    lt = p.table('locations')
    for i, r in enumerate(lt.rows if lt else []):
        for v in (r.get('shop') or '').split(';'):
            if v.strip().isdigit():
                add(int(v), {'kind': 'shop', 'ch': int(r['chapter']), 'name': r.get('_castle_name') or 'castle', 'row': i})
    idx = story_index()
    for name in p.evt_files():
        f = p.evt(name)
        for blk in f.blocks():
            for c in blk['cmds']:
                g = gift_of(name, c)
                if g and g['kind'] == 'item':
                    if name == 'scenes.evt':
                        m = re.match(r'scene\s+(\d+)', blk['label'])
                        sid = int(m.group(1)) if m else None
                        chs = sorted(int(x[2:4]) for x in idx['chapter_scenes'].get(sid, ()))
                    else:
                        sid, chs = None, [int(name[2:4])] if name.startswith('ch') else []
                    add(g['instance'], {'kind': 'event', 'chapters': chs, 'scene': sid, 'file': name, 'line': c['line'],
                                        'unit': g['unit']})
    return {'use': use}


# ---------------------------------------------------------------- adding and removing events
STRUCT_OPS = {0x20, 0x25, 0x2E, 0x21}     # these start the structured tail of a trigger list
LORDS = (1, 25)                                               # Sigurd, Seliph (character IDs)
VILLAGER = 0x2AD                                              # a villager speaker the game uses


def _w(n):
    return '%02X %02X' % (n & 0xFF, n >> 8)


def _hx(*parts):
    return ' '.join(str(p) for p in parts)


def chapter_file(ch):
    p = need_project()
    name = next((f for f in p.evt_files() if f.startswith('ch%02d_' % ch)), None)
    if name is None:
        raise KeyError(f'no events for chapter {ch}')
    return name


def free_flag(name):
    """An event flag (0-79) nothing in this chapter's script or its scenes uses."""
    p = need_project()
    used = set()
    for blk in p.evt(name).blocks():
        for c in blk['cmds']:
            b = cmd_bytes(c)
            if len(b) > 1 and (b[0] in COND_OPS or b[0] in (0x30, 0x31, 0x32)) and b[1] != 0xFF:
                used.add(b[1] & 0x7F)
    idx = story_index()
    for sid, chs in idx['chapter_scenes'].items():
        if name in chs and sid in idx['scenes']:
            for c in idx['scenes'][sid]['block']['cmds']:
                b = cmd_bytes(c)
                if len(b) == 2 and b[0] == 0x07:
                    used.add(b[1] & 0x7F)
    t = p.table('talks')
    for r in (t.rows if t else []):
        if r.get('chapter') == str(int(name[2:4])):
            try:
                used.add(int(r['flag'], 0) & 0x7F)
            except ValueError:
                pass
    for n in range(80):
        if n not in used:
            return n
    return 0xFF


def _talk_key(r):
    try:
        a = r['from'].strip().lower()
        return (int(r['chapter']), int(r['flag'], 0), 0xFFFF if a in ('any', 'anyone', '') else int(a, 0),
                int(r['to'], 0))
    except (ValueError, KeyError):
        return None


def talk_row_ops(ch, flag, a, t, add, ops):
    """Add (or remove) the chapter's Talk-list entry for a talk event, so the map menu offers "Talk"."""
    p = need_project()
    tb = p.table('talks')
    if tb is None:
        return
    key = (ch, flag, a, t)
    rows = tb.rows
    hit = [i for i, r in enumerate(rows) if _talk_key(r) == key]
    if add and not hit:
        nm = lambda u: 'anyone' if u == 0xFFFF else commenter().unit(u).rsplit('(', 1)[0]  # noqa: E731
        row = {f: '' for f in tb.fields}
        row.update({'chapter': str(ch), 'flag': '0x%02X' % flag, 'from': 'any' if a == 0xFFFF else str(a),
                    '_from_name': nm(a), 'to': str(t), '_to_name': nm(t), 'needs': '', 'flag_chapter': str(ch)})
        at = max([i + 1 for i, r in enumerate(rows) if _talk_key(r) and _talk_key(r)[0] <= ch] or [0])
        ops['list'].append(('rows', 'talks', at, [], [row]))
    elif not add:
        for i in reversed(hit):
            ops['list'].append(('rows', 'talks', i, [dict(rows[i])], []))


def spare_scenes():
    """Scenes that are empty (just END) and that nothing starts: free for new conversations."""
    idx = story_index()
    started = set(idx['chapter_scenes'])
    for sc in idx['scenes'].values():
        started |= set(sc['runs'])
    out = []
    for sid in sorted(idx['scenes']):
        blk = idx['scenes'][sid]['block']
        if sid not in started and len(blk['cmds']) == 1 and blk['cmds'][0]['hex'] == 'FF FF':
            out.append(sid)
    return out


def _comment(name, hexs):
    if '@' in hexs:
        op = int(hexs.split()[0], 16)
        nm = {0x0C: 'TEXT', 0x14: 'TEXT_WINDOW', 0x31: 'TALK', 0x32: 'TALK_SCENE'}.get(op, 'OP_%02X' % op)
        return '%-14s (new message)' % nm
    b = bytes(int(x, 16) for x in hexs.split())
    com = commenter()
    if name == 'scenes.evt':
        nm, note = com.sc(0, b)
        return ('%-13s %s' % (nm, note)).rstrip()
    if b == b'\xff\xff':
        return 'END'
    return ('%-14s %s' % (fe4events.EV_NAMES.get(b[0], 'OP_%02X' % b[0]), com.ev(b))).rstrip()


def _plus(name, cmds):
    return [('+ %-24s ; %s' % (h, _comment(name, h))) for h in cmds]


def new_scene_ops(cmds, ops):
    """Claim a spare scene and fill it with cmds (hex strings, ending FF FF). Returns the scene ID."""
    p = need_project()
    spare = [s_ for s_ in spare_scenes() if s_ not in ops.get('_claimed', set())]
    if not spare:
        raise ValueError('There are no spare scenes left for new conversations.')
    sid = spare[0]
    ops.setdefault('_claimed', set()).add(sid)
    blk = story_index()['scenes'][sid]['block']
    end = blk['cmds'][0]
    f = p.evt('scenes.evt')
    old = f.lines[end['line']]
    first = '%s: %-24s ; %s' % (end['addr'], cmds[0], _comment('scenes.evt', cmds[0]))
    ops['list'].append(('lines', 'scenes.evt', end['line'], [old], [first] + _plus('scenes.evt', cmds[1:])))
    return sid


def new_message_op(text, where, ops):
    d = need_project().dialogue()
    if d is None:
        raise ValueError('This project has no events/dialogue.txt.')
    taken = ops.setdefault('_keys', set())
    n = 1
    while 'N%05d' % n in d.text or 'N%05d' % n in taken:
        n += 1
    key = 'N%05d' % n
    taken.add(key)
    fe4events.text_encode(text)
    ops['list'].append(('msgadd', key, where, text))
    return key


def portrait_code(cid):
    return '{00 3F %02X %02X}' % (cid & 0xFF, cid >> 8)


def say(cid, line):
    return '{07}{00 3D}%s{09}%s{08}{01}' % (portrait_code(cid), line)


def talk_scene(msg, target, gifts=()):
    return ['12 E0 00', '34 23 00', 'FD', '0E 70', 'FD', '0C @' + msg, 'FD', '45 18 DE 84', *gifts,
            '42 %s 00' % _w(target), '45 94 BD 91', 'FD', '12 E0 00', '34 23 00', 'FD', '13', 'FD', 'FF FF']


def map_scene(msg, gifts=()):
    return [*gifts, '12 F7 7F', '0C @' + msg, 'FD', '12 E8 00', 'FD', 'FF FF']


def trigger_insert_line(name):
    """Where a new trigger goes: after the last simple trigger, before the list's structured tail."""
    f = need_project().evt(name)
    blk = next((x for x in f.blocks() if x['label'].startswith('triggers')), None)
    if blk is None or not blk['cmds']:
        raise ValueError('This chapter has no trigger list.')
    for c in blk['cmds']:
        b = cmd_bytes(c)
        if b == b'\xff\xff' or (b and b[0] in STRUCT_OPS):
            return c['line']
    return blk['cmds'][-1]['line']


SMART = {'\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u2014': '-', '\u2013': '-'}


def wrap_words(text, default):
    """Plain words as FE4 dialogue: lines that fit the box ({02}), a button wait ({08}) every
    three lines.  Empty text gives `default`."""
    text = ' '.join(''.join(SMART.get(c, c) for c in str(text or '')).split())
    if not text:
        return default
    rom = rom_data()
    width = lambda w: sum(rom[TEXT_WIDTHS + fe4events._CH_INV[c] - 0x10] if rom is not None and 0x10 <= fe4events._CH_INV[c] < 0x100 else 6 for c in w)  # noqa: E731
    bad = sorted({c for c in text if c not in fe4events._CH_INV and c != ' '})
    if bad:
        raise ValueError('The game\'s font has no ' + ' '.join(repr(c) for c in bad) + '.')
    lines, cur = [], ''
    for word in text.split(' '):
        t = (cur + ' ' + word) if cur else word
        if cur and width(t) > TEXT_BOX_WIDTH:
            lines.append(cur)
            cur = word
        else:
            cur = t
    lines.append(cur)
    out = ''
    for i, ln in enumerate(lines):
        out += ln
        if i < len(lines) - 1:
            out += '{08}' if i % 3 == 2 else '{02}'
    return out


def api_newevent(b, q):
    """A new trigger in a chapter: {ch, kind, ...}. One undo step; returns the condition's line."""
    p = need_project()
    ch = int(b['ch'])
    name = chapter_file(ch)
    kind = b['kind']
    ops = {'list': []}
    lord = LORDS[1] if ch >= 6 else LORDS[0]
    u = lambda k, d=None: int(b.get(k, d) if b.get(k, d) is not None else 0xFFFF)  # noqa: E731
    title = 'new event'
    if kind == 'talk':
        a, t = u('a', lord), u('b')
        flag = free_flag(name)
        msg = new_message_op('{06}{00 3D}%s{07}{00 3D}%s{06}{09}%s{07}{00 1D 10}%s{08}{01}'
                             % (portrait_code(a), portrait_code(t), wrap_words(b.get('line1'), 'Write the first line here.'),
                                wrap_words(b.get('line2'), 'And the reply here.')), f'{name[:4]} new talk', ops)
        sid = new_scene_ops(talk_scene(msg, t), ops)
        cond = _hx('04' if ch < 6 else '16', '%02X' % flag, _w(a), _w(t), 'FF FF')
        steps = ['30 FF ' + _w(sid)]
        talk_row_ops(ch, flag, a, t, True, ops)
    elif kind == 'recruit':                  # a talk whose scene moves the second unit into your army
        a, t = u('a', lord), u('b')
        if t == 0xFFFF:
            raise ValueError('Choose who joins.')
        flag = free_flag(name)
        msg = new_message_op('{06}{00 3D}%s{07}{00 3D}%s{06}{09}%s{07}{00 1D 10}%s{08}{01}'
                             % (portrait_code(a), portrait_code(t), wrap_words(b.get('line1'), 'Write what is said here.'),
                                wrap_words(b.get('line2'), 'And their reply. Then they join you.')), f'{name[:4]} new recruit', ops)
        sid = new_scene_ops(talk_scene(msg, t, gifts=['4A 53 %s 00' % _w(t)]), ops)
        cond = _hx('04' if ch < 6 else '16', '%02X' % flag, _w(a), _w(t), 'FF FF')
        steps = ['30 FF ' + _w(sid)]
        talk_row_ops(ch, flag, a, t, True, ops)
    elif kind == 'visit':
        loc = int(b['loc'])
        for cnd, steps in chapter_triggers(name):
            cb = cmd_bytes(cnd)
            if cb[0] == 0x0A and cb[4] | cb[5] << 8 == loc:
                raise ValueError('That village already has a visit event: open it and add to it.')
        msg = new_message_op(say(VILLAGER, wrap_words(b.get('line'), 'Welcome, traveler! Please, take this.')), f'{name[:4]} new village', ops)
        sid = new_scene_ops(map_scene(msg), ops)
        cond = _hx('0A FF FF FF', _w(loc))
        steps = ['30 FF ' + _w(sid)]
    elif kind == 'turn':
        turn, who = int(b['turn']), u('who', lord)
        if not 2 <= turn <= 99:
            raise ValueError('Turn is 2 to 99 (for turn 1, add to the chapter\'s opening on the Events page).')
        msg = new_message_op(say(who, wrap_words(b.get('line'), 'Write what is said here.')), f'{name[:4]} new turn {turn}', ops)
        # one event per check: a turn that already starts with a scene gets the message in it
        sid = turn_scene(name, turn)
        if sid is not None:
            add_text_to_scene(sid, msg, ops)
            p.edit(ops['list'])
            line = next(c['line'] for c, st_ in chapter_triggers(name) if scene_of(st_) == sid)
            return {'ok': True, 'file': name, 'line': line, 'merged': True}
        sid = new_scene_ops(map_scene(msg), ops)
        line = first_trigger_ops(name, [turn_cond(name, turn), '30 FF ' + _w(sid)], ops)
        p.edit(ops['list'])
        return {'ok': True, 'file': name, 'line': line}
    elif kind == 'area':
        unit = u('unit', lord)
        x1, y1, x2, y2 = (int(b[k]) for k in ('x1', 'y1', 'x2', 'y2'))
        if not all(0 <= v < 64 for v in (x1, y1, x2, y2)):
            raise ValueError('Corners are 0 to 63.')
        msg = new_message_op(say(int(b['who']) if b.get('who') not in (None, '') else unit if unit != 0xFFFF else lord,
                                 wrap_words(b.get('line'), 'Write what is said here.')), f'{name[:4]} new area', ops)
        sid = new_scene_ops(map_scene(msg), ops)
        cond = _hx('0B', '%02X' % free_flag(name), _w(unit), '%02X %02X %02X %02X' % (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), 'FF')
        steps = ['30 FF ' + _w(sid)]
    elif kind == 'battle':
        a, t = u('a'), u('b')
        if t == 0xFFFF:
            raise ValueError('Choose who the quote is for (the second unit speaks).')
        msg = new_message_op(say(t, wrap_words(b.get('line'), 'Write the battle quote here.')), f'{name[:4]} new battle quote', ops)
        cond = _hx('0D FF 00 00', _w(a), 'FF FF', _w(t))
        steps = ['31 %02X @%s 00' % (free_flag(name), msg)]
    elif kind == 'death':
        unit = u('unit')
        if unit == 0xFFFF:
            raise ValueError('Choose who dies.')
        msg = new_message_op(say(unit, wrap_words(b.get('line'), 'Write the last words here.')), f'{name[:4]} new death quote', ops)
        cond = _hx('1A', '%02X' % free_flag(name), _w(unit), 'FF FF')
        steps = ['31 FF @%s 01' % msg]
    else:
        raise ValueError(f'unknown event kind {kind}')
    at = trigger_insert_line(name)
    f = p.evt(name)
    ins = _plus(name, [cond] + steps)
    # insert before line `at`: replace that line with the new lines followed by itself
    ops['list'].append(('lines', name, at, [f.lines[at]], ins + [f.lines[at]]))
    p.edit(ops['list'])
    return {'ok': True, 'file': name, 'line': at, 'title': title}


def _group_at(name, line):
    """(start line, end line exclusive) of the trigger group whose condition is on `line`."""
    for cond, steps in chapter_triggers(name):
        if cond['line'] == line:
            last = steps[-1]['line'] if steps else line
            return line, last + 1
    return None


def api_delstep(b, q):
    """Remove one step, or a whole event when the line is its condition."""
    p = need_project()
    name, line = b['file'], int(b['line'])
    f = p.evt(name)
    if f is None:
        raise KeyError(f'no events file {name}')
    cmd = next((c for blk in f.blocks() for c in blk['cmds'] if c['line'] == line), None)
    if cmd is None:
        raise KeyError(f'line {line + 1} of {name} is not a command')
    blk = next(x for x in f.blocks() if any(c['line'] == line for c in x['cmds']))
    if cmd['hex'] == 'FF FF':
        raise ValueError('The end marker can\'t be removed.')
    if len(blk['cmds']) <= 1:
        raise ValueError('A script needs at least one command.')
    rng = _group_at(name, line) if name != 'scenes.evt' else None
    a, z = rng if rng else (line, line + 1)
    gone = f.lines[a:z]
    ops = [('lines', name, a, gone, [])]
    cb = cmd_bytes(cmd)
    if rng and cb[0] in (0x04, 0x16) and len(cb) >= 6:       # a talk: its Talk-list entry goes too
        tops = {'list': []}
        talk_row_ops(int(name[2:4]), cb[1], cb[2] | cb[3] << 8, cb[4] | cb[5] << 8, False, tops)
        ops += tops['list']
    # new messages only these lines used go too
    d = p.dialogue()
    keys = set(re.findall(r'@(N\d{5})', '\n'.join(gone)))
    if keys and d:
        rest = '\n'.join(l for fn in p.evt_files() for i, l in enumerate(p.evt(fn).lines) if not (fn == name and a <= i < z))
        for k in sorted(keys):
            if '@' + k not in rest and k in d.text:
                ops.append(('msgdel', k, d.where[k], d.text[k]))
    p.edit(ops)
    return {'ok': True}


def api_addstep(b, q):
    """Add a step to the event whose condition is on `line`: {file, line, kind, ...}."""
    p = need_project()
    name, line, kind = b['file'], int(b['line']), b['kind']
    rng = _group_at(name, line)
    if rng is None:
        raise KeyError('That isn\'t an event condition.')
    f = p.evt(name)
    cond = next(c for c, _ in chapter_triggers(name) if c['line'] == line)
    cb = cmd_bytes(cond)
    ops = {'list': []}
    ch = int(name[2:4])
    lord = LORDS[1] if ch >= 6 else LORDS[0]
    # A trigger is a condition and ONE action ($86:84ED: on a match the VM runs the next command and
    # skips to the list's `20 66 66`; otherwise it steps over that one command, and a second command
    # would run on every pass).  So more steps go into the event's scene, as the game's own do.
    steps = next(st_ for c, st_ in chapter_triggers(name) if c['line'] == line)
    sid0 = scene_of(steps)
    if kind == 'message':
        who = int(b.get('who') or lord)
        if cb[0] in (0x0D, 0x0E, 0x1A):            # battle screen: a quote
            if steps:
                raise ValueError('A battle or death quote shows one message. Make another quote event for more.')
            msg = new_message_op(say(who, 'Write what is said here.'), f'{name[:4]} new quote', ops)
            step = '31 FF @%s %s' % (msg, '01' if cb[0] == 0x1A else '00')
        else:
            msg = new_message_op(say(who, 'Write what is said here.'), f'{name[:4]} new message', ops)
            # an event plays one scene: put the message into the scene it already plays, if any
            sid = next((cmd_bytes(c)[2] | cmd_bytes(c)[3] << 8 for c in chapter_triggers(name)[[x[0]['line'] for x in
                        chapter_triggers(name)].index(line)][1] if cmd_bytes(c)[:1] == b'\x30'), None)
            if sid is not None:
                add_text_to_scene(sid, msg, ops)
                p.edit(ops['list'])
                return {'ok': True, 'file': name, 'line': line}
            if steps:
                raise ValueError('This event already does something that isn\'t a scene, so it can\'t show more. Make another event.')
            step = '30 FF ' + _w(new_scene_ops(map_scene(msg), ops))
    elif kind == 'item':
        inst = int(b['instance'])
        if not 0 <= inst < L.INSTANCE_COUNT:
            raise ValueError('Pick an item copy.')
        unit = int(b.get('unit', 0xFFFF))
        step = _hx('57', _w(unit), '%02X' % inst)
    elif kind == 'stat':
        unit, stat, amt = int(b.get('unit', 0xFF)), int(b['stat']), int(b['amount'])
        if not (0 <= stat <= 7 and 0 <= amt <= 255 and 0 <= unit <= 255):
            raise ValueError('Stat 0-7, amount 0-255; the unit must be one of the first 255 characters.')
        step = '70 %02X %02X %02X' % (unit, stat, amt)
    elif kind == 'deploy':
        n = int(b['list'])
        if not 0 <= n <= 255:
            raise ValueError('Deploy list is 0 to 255.')
        step = '4E %02X' % n
    else:
        raise ValueError(f'unknown step {kind}')
    if kind in ('item', 'stat', 'deploy'):
        cmd = '4A ' + step
        if sid0 is not None:
            if kind == 'deploy':
                add_cmds_to_scene(sid0, [cmd], ops)
            else:                                  # gifts are given as the event starts
                prepend_to_scene(sid0, [cmd], ops)
            p.edit(ops['list'])
            return {'ok': True, 'file': name, 'line': line}
        if steps:
            raise ValueError('This event already does something that isn\'t a scene, so it can\'t do more. Make another event.')
        step = '30 FF ' + _w(new_scene_ops([cmd, 'FF FF'], ops))
    z = rng[1]
    ops['list'].append(('lines', name, z, [], _plus(name, [step])))
    p.edit(ops['list'])
    return {'ok': True, 'file': name, 'line': line}


def add_text_to_scene(sid, msg, ops):
    """Show one more message in a scene: right after its last message (and the YIELD after it),
    or before its end when it has none."""
    sc = story_index()['scenes'].get(sid)
    if sc is None:
        raise KeyError(f'no scene {sid}')
    cmds = sc['block']['cmds']
    at = None
    for i, c in enumerate(cmds):
        if cmd_bytes(c)[:1] in (b'\x0c', b'\x14'):
            at = i + 1
            if at < len(cmds) and cmds[at]['hex'] == 'FD':
                at += 1
    if at is None:
        at = next(i for i, c in enumerate(cmds) if c['hex'] == 'FF FF')
        new = ['12 F7 7F', '0C @' + msg, 'FD', '12 E8 00', 'FD']
    else:
        new = ['0C @' + msg, 'FD']
    f = need_project().evt('scenes.evt')
    ln = cmds[at]['line'] if at < len(cmds) else cmds[-1]['line'] + 1
    # new lines go before line `ln` (a '+' line adds after the line above it)
    ops['list'].append(('lines', 'scenes.evt', ln, [], _plus('scenes.evt', new)))


def api_eventinfo(b, q):
    """Spare scenes left, for the new-event dialog."""
    need_project()
    return {'spareScenes': len(spare_scenes())}


# ---------------------------------------------------------------- units and events placed from the map (1.1)
# A generic unit's record (units_generic.csv) holds its class, level, weapons and shown name; deploy
# list entries (deploy.csv) put a record on the map.  Many entries share one record, so the map
# editor finds an identical record or makes a new one, and asks before changing a shared one.
GEN_FIELDS = ('name_id', 'class', 'unk6', 'level', 'authority', 'unk9', 'item1', 'item2', 'item3', 'portrait')
NEW_UNITS_MAX = 1023 - L.RESERVED_IDS     # saves keep unit IDs in 10 bits once units are added


def _num(v, d=0):
    try:
        return int(str(v).strip(), 0)
    except (TypeError, ValueError):
        return d


def unit_label(cid):
    """A unit's name from the project (new units too), else from the ROM."""
    t, r = unit_lookup().get(cid, (None, None))
    if r is not None and r.get('_name'):
        return r['_name']
    if cid in (0, 0xFFFF):
        return 'anyone'
    try:
        return commenter().unit(cid).rsplit('(', 1)[0].strip()
    except Exception:
        return f'Unit {cid}'


def army_names(ch):
    """{army slot: name shown on the map} for a chapter; slot 0 is the player's."""
    p = need_project()
    at = p.table('armies')
    names = castle_names()
    out = {}
    for slot, army in _chapter_slots(ch).items():
        row = next((r for r in at.rows if r.get('army') == str(army)), None) if at else None
        nm = _num(row.get('name'), 255) if row else 255
        out[slot] = (names[nm] if nm < 0x40 else '') or f'Army {army}'
    out[0] = 'your army'
    return out


def scene_lists(sid, idx, seen=None):
    """Deploy lists a scene (and the scenes it starts) brings onto the map."""
    seen = seen if seen is not None else set()
    if sid in seen or sid not in idx['scenes']:
        return set()
    seen.add(sid)
    out = set()
    for c in idx['scenes'][sid]['block']['cmds']:
        b = cmd_bytes(c)
        if len(b) >= 3 and b[0] == 0x4A and b[1] == 0x4E:
            out.add(b[2])
    for t in idx['scenes'][sid]['runs']:
        out |= scene_lists(t, idx, seen)
    return out


def cmd_lists(c, idx):
    """Deploy lists one chapter-script command brings in (directly, or through the scene it runs)."""
    b = cmd_bytes(c)
    if len(b) >= 2 and b[0] == 0x4E:
        return {b[1]}
    if len(b) >= 4 and b[0] == 0x30:
        return scene_lists(b[2] | b[3] << 8, idx)
    return set()


def loc_label(ch, n):
    lt = need_project().table('locations')
    for r in lt.rows if lt else []:
        if r.get('chapter') == str(ch) and _num(r.get('index'), -1) == n:
            return (r.get('_castle_name') or f'castle {n}') if r.get('kind') == 'castle' else f'village {n}'
    return f'location {n}'


def cond_words(b, ch):
    """A trigger condition in words."""
    w = lambda i: b[i] | b[i + 1] << 8 if i + 1 < len(b) else 0  # noqa: E731
    op = b[0]
    if op == 0x01:
        return 'At the start of every turn' if w(2) == 0xFFFF else f'At the start of turn {w(2) + 1}'
    if op == 0x02:
        who = w(2)
        return ('You take' if who == 0 else 'Anyone takes' if who == 0xFFFF else
                f"{army_names(ch).get(who, 'army slot %d' % who)} takes") + f' {loc_label(ch, w(4))}'
    if op in (0x04, 0x16):
        return f'{unit_label(w(2))} talks to {unit_label(w(4))}'
    if op == 0x0C:
        return f'{unit_label(w(2))} comes next to {unit_label(w(4))}'
    if op == 0x0A:
        return f'Someone visits {loc_label(ch, w(4))}'
    if op == 0x0B:
        return f'{unit_label(w(2))} reaches ({b[4]}, {b[5]})–({b[6]}, {b[7]})'
    if op == 0x0D:
        return f'{unit_label(w(4))} fights {unit_label(w(8))}'
    if op == 0x0E:
        return f'After {unit_label(w(4))} fights {unit_label(w(8))}'
    if op == 0x1A:
        if w(2) == 0xFFFF:
            return f'Someone is defeated by {unit_label(w(4))}'
        return f'{unit_label(w(2))} is defeated' + ('' if w(4) == 0xFFFF else f' by {unit_label(w(4))}')
    if op == 0x03:
        nm = army_names(ch)
        return 'Every unit of ' + ', '.join(nm.get(s, f'army slot {s}') for s in fe4conds.rout_slots(b)) + ' is gone'
    if op == 0x07:
        return f'{loc_label(ch, w(4))} is taken'
    return f'A story event (condition {op:02X})'


def chapter_lists(ch):
    """{list: {list, when, line, start}}: when each deploy list of the chapter comes onto the map."""
    p = need_project()
    name = chapter_file(ch)
    idx = story_index()
    f = p.evt(name)
    out = {}

    def add(n, when, line, start=False):
        out.setdefault(n, {'list': n, 'when': when, 'line': line, 'start': start})
    for blk in f.blocks():
        if blk['label'] == 'init':
            for c in blk['cmds']:
                for n in cmd_lists(c, idx):
                    add(n, 'At the start of the chapter', None, True)
    for cnd, steps in chapter_triggers(name):
        for c in steps:
            for n in cmd_lists(c, idx):
                add(n, cond_words(cmd_bytes(cnd), ch), cnd['line'])
    for blk in f.blocks():                      # the story events of the list's structured tail
        for c in blk['cmds']:
            for n in cmd_lists(c, idx):
                add(n, 'During the chapter (a story event)', None)
    return out


def move_costs():
    """Per movement type: the bytes the game reads as cost per terrain ($87:B394: row + terrain;
    128 = can't enter).  Terrain types past 25 read on into the next row, as in the game."""
    rom = rom_data()
    if rom is None:
        return []
    B = 0x30000
    w = lambda a: rom[a] | rom[a + 1] << 8  # noqa: E731
    t = w(B + 0x8008)
    out = []
    for mt in range(16):
        row = (w(B + 0x8000 + t + 2 * mt) + t + 0x8000) & 0xFFFF
        out.append(list(rom[B + row:B + row + 64]))
    return out


def new_unit_ids():
    """IDs of units the project adds (units_generic.csv and units_children.csv rows past the game's)."""
    p = need_project()
    cnt = L.unit_count(rom_data()) if rom_data() is not None else L.GAME_UNITS
    out = []
    for t in ('units_generic', 'units_children', 'units_playable'):
        tb = p.table(t)
        for r in tb.rows if tb else []:
            i = _num(r.get('index'), 0)
            if i > cnt:
                out.append(i)
    return sorted(out)


def new_units_left():
    """How many more units fit: the old pointer table (1,138 bytes) and bank $83's tail
    (2,108 bytes, which also holds the new table) -- see fe4lib.add_units."""
    n = len(new_unit_ids())
    low = 1138 // 13
    for k in range(NEW_UNITS_MAX - n, -1, -1):
        tot = n + k
        high = max(0, tot - low)
        if 2 * (L.RESERVED_IDS + tot) + 38 + 1 + 13 * high <= 2108 - 32 - 16 - 1:
            return k
    return 0


def unit_in_events(cid):
    """True when a chapter script names the unit in a condition or a gift."""
    p = need_project()
    for name in p.evt_files():
        if name == 'scenes.evt':
            continue
        for blk in p.evt(name).blocks():
            for c in blk['cmds']:
                b = cmd_bytes(c)
                w = lambda i: b[i] | b[i + 1] << 8 if i + 1 < len(b) else -1  # noqa: E731
                pos = {0x04: (2, 4), 0x16: (2, 4), 0x0C: (2, 4), 0x0B: (2,), 0x0D: (4, 8), 0x0E: (4, 8),
                       0x1A: (2,), 0x0F: (2,), 0x57: (1,)}.get(b[0] if b else -1, ())
                if any(w(i) == cid for i in pos):
                    return True
    tk = p.table('talks')
    return any(_num(r.get('to'), -1) == cid or _num(r.get('from'), -1) == cid for r in (tk.rows if tk else []))


def _gen_norm(r):
    return tuple(str(_num(r.get(k), 255 if k in ('item1', 'item2', 'item3', 'unk9') else 0)) for k in GEN_FIELDS)


def generic_for(spec, deploy_rows, ops):
    """The char ID of a generic record with exactly these fields: an existing one, a new record the
    project added that nothing uses any more (rewritten), or a new one.  Adds the ops it needs."""
    p = need_project()
    gt = p.table('units_generic')
    want = _gen_norm(spec)
    for r in gt.rows:
        if _gen_norm(r) == want:
            return _num(r['index'])
    used = {_num(r.get('char_id'), -1) for r in deploy_rows}
    cnt = L.unit_count(rom_data()) if rom_data() is not None else L.GAME_UNITS
    cls = p.table('classes')
    items = p.table('items')
    cname = lambda k: cls.rows[k]['_name'] if cls and 0 <= k < len(cls.rows) else ''  # noqa: E731
    iname = lambda k: items.rows[k]['_name'] if items and 0 <= k < len(items.rows) else ''  # noqa: E731
    label = {'_class_name': cname(_num(spec['class'])),
             '_items': ' / '.join(x for x in (iname(_num(spec.get(f), 255)) for f in ('item1', 'item2', 'item3')) if x)}
    gname = next((r.get('_name') for r in gt.rows if r.get('name_id') == str(_num(spec.get('name_id')))), '')
    for i, r in enumerate(gt.rows):
        cid = _num(r['index'])
        if cid > cnt and cid not in used and cid not in ops.get('_made', ()) and not unit_in_events(cid):
            for k, v in zip(GEN_FIELDS, want):
                if r.get(k, '') != v:
                    ops['list'].append(('cell', 'units_generic', i, k, r.get(k, ''), v))
            for k, v in list(label.items()) + [('_name', gname)]:
                if k in gt.fields and r.get(k, '') != v:
                    ops['list'].append(('cell', 'units_generic', i, k, r.get(k, ''), v))
            ops.setdefault('_made', set()).add(cid)
            ops.setdefault('_labels', {})[cid] = gname
            return cid
    if new_units_left() <= len(ops.get('_new', [])):
        raise ValueError('There is no room for another kind of unit: the game\'s unit table is full. '
                         'Give this unit the same class, level and weapons as one already on a map.')
    ids = new_unit_ids() + ops.get('_new', [])
    cid = (max(ids) + 1) if ids else L.first_new_id(rom_data())
    row = {f_: '' for f_ in gt.fields}
    row.update(dict(zip(GEN_FIELDS, want)))
    row.update({'index': str(cid), 'char_id': str(cid), '_name': gname, **{k: v for k, v in label.items() if k in gt.fields}})
    ops['list'].append(('rows', 'units_generic', len(gt.rows) + len(ops.get('_new', [])), [], [row]))
    ops.setdefault('_labels', {})[cid] = gname
    ops.setdefault('_new', []).append(cid)
    ops.setdefault('_made', set()).add(cid)
    return cid


def _renumber(rows):
    """Deploy rows ordered by list, with each list's entries numbered 0, 1, ... in their order."""
    def key(r):
        a, _, e = r['index'].partition('.')
        return (_num(a), _num(e))
    rows = sorted(rows, key=key)
    seen = {}
    for r in rows:
        a = r['index'].partition('.')[0]
        n = seen.get(a, 0)
        seen[a] = n + 1
        r['index'] = f'{a}.{n}'
    return rows


def free_list():
    """A deploy list number nothing uses: no deploy entries, no script brings it in."""
    p = need_project()
    used = {_num(r['index'].partition('.')[0]) for r in p.table('deploy').rows}
    for name in p.evt_files():
        for line in p.evt(name).lines:
            for m in re.finditer(r'deploy list (\d+)', line):
                used.add(int(m.group(1)))
    for n in range(L.DEPLOY_LISTS, L.DEPLOY_LISTS_MAX):
        if n not in used:
            return n
    raise ValueError('All the deploy lists are used.')


def scene_of(steps):
    return next((cmd_bytes(c)[2] | cmd_bytes(c)[3] << 8 for c in steps if cmd_bytes(c)[:1] == b'\x30'), None)


def add_cmds_to_scene(sid, cmds, ops):
    """Commands after a scene's last wait for the player (YIELD), so they run once its dialogue is
    over but before the commands that close it (some story scenes end with event calls that leave
    the scene, so anything after them would never run); before END when it has no YIELD."""
    sc = story_index()['scenes'].get(sid)
    if sc is None:
        raise KeyError(f'no scene {sid}')
    cs = sc['block']['cmds']
    end = next(i for i, c in enumerate(cs) if c['hex'] == 'FF FF')
    ys = [i for i, c in enumerate(cs[:end]) if c['hex'] == 'FD']
    at = cs[ys[-1] + 1]['line'] if ys else cs[end]['line']
    ops['list'].append(('lines', 'scenes.evt', at, [], _plus('scenes.evt', cmds)))


def prepend_to_scene(sid, cmds, ops):
    """Commands at the very start of a scene (the first command keeps the scene's address)."""
    sc = story_index()['scenes'].get(sid)
    if sc is None:
        raise KeyError(f'no scene {sid}')
    first = sc['block']['cmds'][0]
    f = need_project().evt('scenes.evt')
    old = f.lines[first['line']]
    lead = '%s: %-24s ; %s' % (first['addr'], cmds[0], _comment('scenes.evt', cmds[0]))
    rest = _plus('scenes.evt', cmds[1:] + [first['hex']])
    ops['list'].append(('lines', 'scenes.evt', first['line'], [old], [lead] + rest))


def turn_cond(name, turn):
    """`01 [flag] [turn word]`: the check the game makes as each turn starts ($81:AD08, mode $20, with
    the turn number from before the turn goes up), so it fires at the start of turn n + 1 (verified:
    `01 .. 02 00` brought its list in as turn 3 started).  The `02` turn condition is checked by an
    army's phase task (mode 1) that didn't run in testing, so the editor doesn't write it."""
    return _hx('01', '%02X' % free_flag(name), _w(turn - 1))


def turn_scene(name, turn):
    """The scene of an existing start-of-turn event for that turn, or None."""
    for cnd, steps in chapter_triggers(name):
        cb = cmd_bytes(cnd)
        if cb[0] == 0x01 and len(cb) >= 4 and (cb[2] | cb[3] << 8) == turn - 1:
            sid = scene_of(steps)
            if sid is not None:
                return sid
    return None


def first_trigger_ops(name, cmds, ops):
    """New trigger lines at the start of the chapter's trigger list: on each check the VM runs the
    first trigger that matches and skips the rest ($86:84ED), so one further down could lose to an
    earlier one for good."""
    f = need_project().evt(name)
    blk = next((x for x in f.blocks() if x['label'].startswith('triggers')), None)
    if blk is None or not blk['cmds']:
        raise ValueError('This chapter has no trigger list.')
    first = blk['cmds'][0]
    lead = '%s: %-24s ; %s' % (first['addr'], cmds[0], _comment(name, cmds[0]))
    ops['list'].append(('lines', name, first['line'], [f.lines[first['line']]],
                        [lead] + _plus(name, cmds[1:] + [first['hex']])))
    return first['line']


def reinforce_ops(ch, lst, when, ops, say_who=None):
    """The event that brings deploy list `lst` onto the map: {kind: 'turn', turn, slot} or
    {kind: 'area', unit, x1, y1, x2, y2}.  Returns a description of when."""
    p = need_project()
    name = chapter_file(ch)
    kind = when.get('kind')
    deploy = '4A 4E %02X' % lst
    msg_cmds = []
    if say_who is not None:
        msg = new_message_op(say(int(say_who), 'Write what is said here.'), f'{name[:4]} reinforcements', ops)
        msg_cmds = ['12 F7 7F', '0C @' + msg, 'FD', '12 E8 00', 'FD']
    if kind == 'turn':
        turn = int(when['turn'])
        if not 2 <= turn <= 99:
            raise ValueError('Reinforcements arrive at the start of turn 2 to 99 (turn 1 is the chapter\'s start).')
        sid = turn_scene(name, turn)
        if sid is not None:                    # that turn already starts with an event: join its scene
            add_cmds_to_scene(sid, msg_cmds + [deploy], ops)
            return f'At the start of turn {turn}'
        cond = turn_cond(name, turn)
    elif kind == 'area':
        unit = int(when.get('unit', 0xFFFF))
        x1, y1, x2, y2 = (int(when[k]) for k in ('x1', 'y1', 'x2', 'y2'))
        if not all(0 <= v < 64 for v in (x1, y1, x2, y2)):
            raise ValueError('Corners are 0 to 63.')
        cond = _hx('0B', '%02X' % free_flag(name), _w(unit),
                   '%02X %02X %02X %02X' % (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), 'FF')
    else:
        raise ValueError('Choose when the units arrive.')
    sid = new_scene_ops(msg_cmds + [deploy, 'FF FF'], ops)
    first_trigger_ops(name, [cond, '30 FF ' + _w(sid)], ops)
    return cond_words(bytes(int(x, 16) for x in cond.split()), ch)


def scene_ends(sid, idx, seen=None):
    """True when the scene (or one it starts) ends the chapter: event $78 (`4A 78`)."""
    seen = seen if seen is not None else set()
    if sid in seen or sid not in idx['scenes']:
        return False
    seen.add(sid)
    for c in idx['scenes'][sid]['block']['cmds']:
        b = cmd_bytes(c)
        if len(b) >= 2 and b[0] == 0x4A and b[1] == 0x78:
            return True
    return any(scene_ends(t, idx, seen) for t in idx['scenes'][sid]['runs'])


def chapter_endings(ch):
    """The chapter's ending events: triggers whose action is the chapter clear ($78) or a scene that
    reaches it.  kind 'seize' = `02 flag [army slot][location]` (the game's own: you take a castle),
    'turn' = `01 flag [turn - 1]` (survive until a turn starts), 'other' = anything else."""
    name = chapter_file(ch)
    idx = story_index()
    out = []
    for cnd, steps in chapter_triggers(name):
        if not steps:
            continue
        sb = cmd_bytes(steps[0])
        ends = sb[:1] == b'\x78' or (sb[:1] == b'\x30' and len(sb) >= 4 and scene_ends(sb[2] | sb[3] << 8, idx))
        if not ends:
            continue
        cb = cmd_bytes(cnd)
        w = lambda i: cb[i] | cb[i + 1] << 8 if i + 1 < len(cb) else 0  # noqa: E731
        e = {'line': cnd['line'], 'hex': cnd['hex'], 'words': cond_words(cb, ch), 'kind': 'other'}
        if cb[0] == 0x02:
            e.update(kind='seize', loc=w(4), who=w(2))
        elif cb[0] == 0x01 and w(2) != 0xFFFF:
            e.update(kind='turn', turn=w(2) + 1)
        elif cb[0] == 0x1A and w(2) != 0xFFFF and w(4) == 0xFFFF:
            e.update(kind='boss', unit=w(2))
        elif cb[0] == 0x03:
            e.update(kind='rout', slots=fe4conds.rout_slots(cb))
        out.append(e)
    return out


def api_wincond(b, q):
    """GET ?ch: how the chapter is won and what can win it.  POST {ch, line, kind: 'seize', loc},
    {ch, line, kind: 'turn', turn}, {kind: 'boss', unit} or {kind: 'rout', slots}: rewrites that ending's condition (its flag and action stay)."""
    p = need_project()
    ch = int((b or {}).get('ch', q.get('ch', ['0'])[0]))
    name = chapter_file(ch)
    lt, at = p.table('locations'), p.table('armies')
    holders = {}
    names = army_names(ch)
    for slot, army in _chapter_slots(ch).items():
        row = next((r for r in at.rows if r.get('army') == str(army)), None) if at else None
        for c in (row.get('castles') or '').split(';') if row else []:
            if c.strip().isdigit():
                holders[int(c)] = names.get(slot, f'army slot {slot}')
    castles = [{'index': _num(r['index']), 'name': r.get('_castle_name') or f"castle {r['index']}", 'x': r.get('x'), 'y': r.get('y'),
                'holder': holders.get(_num(r['index']), '')}
               for r in (lt.rows if lt else []) if r.get('chapter') == str(ch) and r.get('kind') == 'castle']
    slots = _chapter_slots(ch)
    dep = chapter_deploy(ch)
    count = {}
    for _i, r, _lst, _ent, _sure in dep:
        count[_num(r.get('army_slot'), 0)] = count.get(_num(r.get('army_slot'), 0), 0) + 1
    armies = [{'slot': sl, 'name': names.get(sl, f'army slot {sl}'), 'units': count.get(sl, 0)} for sl in sorted(slots) if 1 <= sl <= 7]
    people, seen = [], {}
    for _i, r, _lst, _ent, _sure in dep:
        cid, sl = _num(r.get('char_id'), -1), _num(r.get('army_slot'), 0)
        if cid < 0 or sl == 0:
            continue
        seen[cid] = seen.get(cid, 0) + 1
        if seen[cid] == 1:
            nm = unit_label(cid)
            if nm.lower() in ('', 'unit'):
                ur = unit_lookup().get(cid, (None, {}))[1] or {}
                nm = f"{ur.get('_class_name') or 'Unit'} (character {cid})"
            people.append({'id': cid, 'name': nm, 'slot': sl, 'army': names.get(sl, f'army slot {sl}')})
    for pp in people:
        pp['shared'] = seen[pp['id']] > 1
    if not b or 'kind' not in b:
        return {'endings': chapter_endings(ch), 'castles': castles, 'armies': armies, 'people': people}
    line = int(b['line'])
    e = next((x for x in chapter_endings(ch) if x['line'] == line), None)
    if e is None:
        raise ValueError('That isn\'t one of this chapter\'s ending events.')
    flag = e['hex'].split()[1]
    if b['kind'] == 'seize':
        loc = int(b['loc'])
        if loc not in [c['index'] for c in castles]:
            raise ValueError('Choose one of this chapter\'s castles.')
        for c2, _st in chapter_triggers(name):          # the first matching trigger plays, the rest don't
            b2 = cmd_bytes(c2)
            if c2['line'] != line and b2[0] == 0x02 and (b2[2] | b2[3] << 8) in (0, 0xFFFF) and (b2[4] | b2[5] << 8) == loc:
                raise ValueError(f'Taking {loc_label(ch, loc)} already plays another event ({cond_words(b2, ch)}), and only '
                                 'one plays. Delete that event on the Events page first, or choose another castle.')
        new = _hx('02', flag, '00 00', _w(loc))
    elif b['kind'] == 'turn':
        turn = int(b['turn'])
        if not 2 <= turn <= 99:
            raise ValueError('The chapter can end at the start of turn 2 to 99.')
        sid = turn_scene(name, turn)
        if sid is not None:
            raise ValueError(f'Turn {turn} already starts with another event, and only one plays. Choose another turn.')
        new = _hx('01', flag, _w(turn - 1))
    elif b['kind'] == 'boss':
        uid = int(b['unit'])
        pp = next((x for x in people if x['id'] == uid), None)
        if pp is None:
            raise ValueError('Choose someone who is on this chapter\'s map in another army.')
        if pp['shared']:
            raise ValueError(f"{pp['name']} is used by more than one unit on this map, so defeating any of them would "
                             'end the chapter. Choose a named character, or give that unit its own character first.')
        new = _hx('1A', flag, _w(uid), 'FF FF')
    elif b['kind'] == 'rout':
        sl = [int(x) for x in b.get('slots') or []]
        if not sl:
            raise ValueError('Choose at least one army to rout.')
        for x in sl:
            if x not in [a['slot'] for a in armies]:
                raise ValueError(f'Army slot {x} isn\'t in this chapter.')
        new = fe4conds.rout_cond(int(flag, 16), sl)
    else:
        raise ValueError('Choose how the chapter is won.')
    f = p.evt(name)
    old = f.lines[line]
    addr = old.split(':', 1)[0]
    text = '%s: %-24s ; %s' % (addr, new, _comment(name, new))
    p.edit([('lines', name, line, [old], [text])])
    return {'ok': True, 'endings': chapter_endings(ch)}


SITE_FOOT = {'castle': (-1, -1, 1, 2), 'village': (-1, -1, 1, 0)}     # x0, y0, x1, y1 around the record's x, y


def _site_rows(ch):
    lt = need_project().table('locations')
    return sorted(((i, r) for i, r in enumerate(lt.rows) if r.get('chapter') == str(ch)), key=lambda t: _num(t[1]['index']))


def _loc_refs(ch, loc):
    """[(file, line, bytes, position of the location byte(s), size)] for what names location loc in chapter ch:
    the chapter's "takes castle" / "visits" conditions and its armies' AI commands."""
    p = need_project()
    out = []
    name = chapter_file(ch)
    for blk in p.evt(name).blocks():
        for c in blk['cmds']:
            bb = cmd_bytes(c)
            if len(bb) >= 6 and bb[0] in (0x02, 0x0A) and (bb[4] | bb[5] << 8) == loc:
                out.append((name, c['line'], bb, 4, 2))
    armies = set(_chapter_slots(ch).values())
    try:
        blocks = _ai_blocks()
    except KeyError:
        blocks = {}
    for (army, _k), blk in blocks.items():
        if army not in armies:
            continue
        for c in blk['cmds']:
            bb = cmd_bytes(c)
            if len(bb) >= 2 and bb[0] in (0x06, 0x07, 0x08) and bb[1] == loc:
                out.append((AI, c['line'], bb, 1, 1))
    return out


def _relocate_ops(ch, old, new):
    """Ops that point what names location old at location new."""
    p = need_project()
    ops = []
    for fname, line, bb, pos, size in _loc_refs(ch, old):
        nb = bytearray(bb)
        nb[pos:pos + size] = new.to_bytes(size, 'little')
        f = p.evt(fname)
        hexs = ' '.join('%02X' % x for x in nb)
        mc = EVT_COMMENT.search(f.lines[line])
        com = re.sub(r'location \d+(\s*\([^)]*\))?', 'location %d' % new if new != 0xFF else 'no location (removed)',
                     mc.group(1) if mc else '')
        ops.append(('lines', fname, line, [f.lines[line]], [f.set_command(line, hexs, com)]))
    return ops


EVT_COMMENT = re.compile(r';\s*(.*)$')


def api_sites(b, q):
    """Add a castle or village to a chapter ({ch, add: 'castle'|'village', x, y, castle_id?, army?, look?}),
    or take one away ({ch, remove: index}).  One undo step.

    A new site gets the next index.  Taking one away that isn't the last moves the last one into its
    number (its events, its army and its armies' AI orders follow), so the numbers stay 0, 1, 2, ..."""
    p = need_project()
    ch = int(b.get('ch', -1))
    lt, at = p.table('locations'), p.table('armies')
    if lt is None:
        raise KeyError('This project has no locations.csv.')
    rows = _site_rows(ch)
    m = p.map(ch)
    ops = []
    if b.get('add'):
        kind = b['add']
        if kind not in SITE_FOOT:
            raise ValueError('Add a castle or a village.')
        if len(rows) >= fe4locations.MAX_SITES:
            raise ValueError(f'A chapter can have at most {fe4locations.MAX_SITES} castles and villages.')
        x, y = int(b['x']), int(b['y'])
        if not (0 <= x < 64 and 0 <= y < 64):
            raise ValueError('That cell is outside the map.')
        for _, r in rows:
            if _num(r['x']) == x and _num(r['y']) == y:
                raise ValueError('Another castle or village is already there.')
        idx = len(rows)
        new = {k: '' for k in lt.fields}
        new.update({'chapter': str(ch), 'index': str(idx), 'kind': kind, 'x': str(x), 'y': str(y)})
        if kind == 'castle':
            cid = int(b.get('castle_id', 0))
            new.update({'castle_id': str(cid), '_castle_name': castle_names()[cid] if 0 <= cid < 0x40 else '', 'facilities': '-', 'shop': ''})
        else:
            new.update({'castle_id': '0', 'gold': str(int(b.get('gold') or 5000))})
        pos = (rows[-1][0] + 1) if rows else len(lt.rows)
        ops.append(('rows', 'locations', pos, [], [new]))
        if kind == 'castle' and b.get('army') not in (None, ''):
            slot = int(b['army'])
            army = _chapter_slots(ch).get(slot)
            row = next((i for i, r in enumerate(at.rows) if r.get('army') == str(army)), None) if at and army is not None else None
            if row is not None:
                old = at.rows[row].get('castles') or ''
                lst = [c for c in old.split(';') if c.strip()] + [str(idx)]
                ops.append(('cell', 'armies', row, 'castles', old, ';'.join(lst)))
        look = b.get('look')
        if look is not None and m is not None:          # copy the tiles around another site of the chapter
            src = next((r for _, r in rows if _num(r['index']) == int(look)), None)
            if src is not None:
                x0, y0, x1, y1 = SITE_FOOT[src.get('kind')] if src.get('kind') in SITE_FOOT else SITE_FOOT[kind]
                sx, sy = _num(src['x']), _num(src['y'])
                for dy in range(y0, y1 + 1):
                    for dx in range(x0, x1 + 1):
                        if 0 <= sx + dx < 64 and 0 <= sy + dy < 64 and 0 <= x + dx < 64 and 0 <= y + dy < 64:
                            i_src, i_dst = (sy + dy) * 64 + sx + dx, (y + dy) * 64 + x + dx
                            if m.words[i_dst] != m.words[i_src]:
                                ops.append(('map', ch, i_dst, m.words[i_dst], m.words[i_src]))
        p.edit(ops)
        return {'ok': True, 'index': idx}
    if 'remove' in b:
        idx = int(b['remove'])
        byidx = {_num(r['index']): (i, r) for i, r in rows}
        if idx not in byidx:
            raise ValueError('No such castle or village in this chapter.')
        last = len(rows) - 1
        gone = [r for r in _loc_refs(ch, idx) if r[0] == AI]
        if gone:
            raise ValueError('Enemy orders still name this place (Armies & AI: '
                             + ', '.join(sorted({'army %s' % l for l in _ai_armies_naming(ch, idx)})) + '). Change those orders first.')
        ops += _relocate_ops(ch, idx, 0xFF)                    # its own events: never again
        if idx != last:
            ops += _relocate_ops(ch, last, idx)
        if at is not None:
            for ar in set(_chapter_slots(ch).values()):
                row = next((i for i, r in enumerate(at.rows) if r.get('army') == str(ar)), None)
                if row is None:
                    continue
                old = at.rows[row].get('castles') or ''
                lst = []
                for c in old.split(';'):
                    c = c.strip()
                    if not c.isdigit() or int(c) == idx:
                        continue
                    lst.append(str(idx) if int(c) == last and idx != last else c)
                if ';'.join(lst) != old:
                    ops.append(('cell', 'armies', row, 'castles', old, ';'.join(lst)))
        ri, rr = byidx[idx]
        li, lr = byidx[last]
        if idx != last:
            moved = dict(lr)
            moved['index'] = str(idx)
            ops.append(('rows', 'locations', ri, [dict(rr)], [moved]))
        ops.append(('rows', 'locations', li, [dict(lr)], []))
        p.edit(ops)
        return {'ok': True, 'moved': last if idx != last else None}
    raise ValueError('Nothing to do.')


def _ai_armies_naming(ch, loc):
    out = []
    for (army, _k), blk in _ai_blocks().items():
        if army in set(_chapter_slots(ch).values()):
            for c in blk['cmds']:
                bb = cmd_bytes(c)
                if len(bb) >= 2 and bb[0] in (0x06, 0x07, 0x08) and bb[1] == loc:
                    out.append(army)
    return out


def api_mapinfo(b, q):
    """What the map's unit and event cards offer for a chapter."""
    p = need_project()
    ch = int(q.get('ch', ['0'])[0])
    ct, it, gt = p.table('classes'), p.table('items'), p.table('units_generic')
    ranks = ('sword', 'lance', 'axe', 'bow', 'staff', 'fire', 'thunder', 'wind', 'light', 'dark')   # weapon_type order
    classes = [{'id': _num(r['index']), 'name': r.get('_name', ''), 'move': _num(r.get('move')),
                'group': _num(r.get('group')), 'flier': _num(r.get('flier')),
                'ranks': [(r.get('rank_' + k) or '-').strip() for k in ranks]} for r in (ct.rows if ct else [])]
    items = [{'id': _num(r['index']), 'name': r.get('_name', ''), 'type': _num(r.get('weapon_type'), 255),
              'cat': _num(r.get('category')), 'min': _num(r.get('min_range')), 'max': _num(r.get('max_range')),
              'rank': (r.get('rank') or '').strip()}
             for r in (it.rows if it else [])]
    gnames, name_of = {}, {}
    for r in gt.rows if gt else []:
        nm = r.get('_name') or ''
        if nm and r.get('name_id', '').isdigit():
            gnames.setdefault(nm, int(r['name_id']))
            name_of[r['name_id']] = nm
    lists = chapter_lists(ch)
    counts = {}
    for i, r, lst, ent, sure in chapter_deploy(ch):
        counts[lst] = counts.get(lst, 0) + 1
        lists.setdefault(lst, {'list': lst, 'when': 'Not brought in by this chapter\'s script', 'line': None, 'start': False})
    for k, v in lists.items():
        v['units'] = counts.get(k, 0)
    share = {}
    for r in p.table('deploy').rows:
        cid = _num(r.get('char_id'), -1)
        share[cid] = share.get(cid, 0) + 1
    return {'ch': ch, 'classes': classes, 'items': items,
            'names': sorted([[k, v] for k, v in gnames.items()], key=lambda x: x[0].lower()), 'nameOf': name_of,
            'armies': [[k, v] for k, v in sorted(army_names(ch).items())],
            'lists': [lists[k] for k in sorted(lists)], 'costs': move_costs(),
            'newUnitsLeft': new_units_left(), 'spareScenes': len(spare_scenes()), 'shared': share,
            'lord': LORDS[1] if ch >= 6 else LORDS[0]}


def api_unitshare(b, q):
    """Every deploy entry that uses one unit record: [{ch, title, list, entry, x, y, row}]."""
    p = need_project()
    cid = int(q.get('cid', ['0'])[0])
    dch = deploy_chapters(os.path.join(p.path, 'events'))
    out = []
    for i, r in enumerate(p.table('deploy').rows):
        if _num(r.get('char_id'), -1) == cid:
            lst, _, ent = r['index'].partition('.')
            c = dch.get(_num(lst))
            out.append({'row': i, 'list': _num(lst), 'entry': _num(ent), 'x': r.get('x'), 'y': r.get('y'),
                        'ch': c, 'title': (CHAPTER_TITLES[c].split(':')[0] if c is not None and c < len(CHAPTER_TITLES) else 'another chapter')})
    return {'uses': out, 'inEvents': unit_in_events(cid)}


def _gen_spec(src, base=None):
    """A generic record's fields from a card ({class, level, items, name_id, portrait}), defaults from base."""
    base = base or {}
    spec = {k: base.get(k, '') for k in GEN_FIELDS}
    if not base:
        spec.update({'unk6': '255', 'authority': '0', 'unk9': '255', 'portrait': str(fe4gfx.NO_PORTRAIT)})
    for k in ('class', 'level', 'name_id', 'portrait'):
        if src.get(k) not in (None, ''):
            spec[k] = str(int(src[k]))
    its = list(src.get('items') or [])
    if 'items' in src:
        its = [int(x) for x in its if str(x) not in ('', '255')][:3]
        for k, v in zip(('item1', 'item2', 'item3'), its + [255, 255, 255]):
            spec[k] = str(v)
    if not str(spec['name_id']).strip().isdigit():
        raise ValueError('Choose the name the unit shows.')
    lv = _num(spec['level'], 1)
    if not 1 <= lv <= 30:
        raise ValueError('Level is 1 to 30.')
    return spec


def api_mapunit(b, q):
    """Place, change, copy or remove units on a chapter's map, as one undo step.
    {op: 'add', ch, x, y, list | 'new', when?, slot, orders, leader, char_id | generic}
    {op: 'edit', row, x?, y?, slot?, orders?, leader?, list?, char_id?, generic?, scope: 'one' | 'all'}
    {op: 'remove', rows}   {op: 'paste', ch, list, units: [{char_id, x, y, slot, orders, leader}]}"""
    p = need_project()
    dt, gt = p.table('deploy'), p.table('units_generic')
    old = [dict(r) for r in dt.rows]
    rows = [dict(r) for r in dt.rows]
    ops = {'list': []}
    op = b.get('op')
    m = None
    note = ''
    units = unit_lookup()

    def check_xy(ch, x, y):
        ax, ay, aw, ah = map_area(ch)
        if not (ax <= x < ax + aw and ay <= y < ay + ah):
            raise ValueError(f'Keep it on the map: x {ax}–{ax + aw - 1}, y {ay}–{ay + ah - 1}.')

    def generic(cid):
        return cid in ops.get('_made', ()) or units.get(cid, (None,))[0] == 'units_generic'

    def entry(lst, cid, x, y, slot, orders, leader):
        if int(slot) == 0 and generic(cid):
            raise ValueError('Units in your army come from its members (Armies page); a deploy list only places them. '
                             'Put this unit in another army.')
        return {'index': f'{lst}.9999', '_name': ops.get('_labels', {}).get(cid) or unit_label(cid), 'char_id': str(cid), 'x': str(int(x)), 'y': str(int(y)),
                'leader_flag': '1' if leader else '0', 'orders': str(int(orders or 0)), 'army_slot': str(int(slot)), 'slot': '0'}

    def unit_of(src):
        if src.get('char_id') not in (None, ''):
            cid = int(src['char_id'])
            if cid not in units and cid not in ops.get('_made', ()):
                raise ValueError(f'There is no unit {cid}.')
            return cid
        return generic_for(_gen_spec(src['generic']), rows, ops)

    if op in ('add', 'paste', 'pastemany'):
        ch = int(b['ch'])
        groups = b['groups'] if op == 'pastemany' else [{'list': b.get('list'), 'units': b['units'] if op == 'paste' else [b]}]
        made = []
        for g in groups:
            lst = g.get('list')
            if lst == 'new':
                lst = free_list()
                note = reinforce_ops(ch, lst, b.get('when') or {}, ops, b.get('sayWho'))
            lst = int(lst)
            if not 0 <= lst < L.DEPLOY_LISTS_MAX:
                raise ValueError('Choose when the unit arrives.')
            for s in g['units']:
                x, y = int(s['x']), int(s['y'])
                check_xy(ch, x, y)
                cid = unit_of(s)
                e = entry(lst, cid, x, y, s.get('slot', 1), s.get('orders', 0), s.get('leader'))
                rows.append(e)
                made.append(e)
        rows = _renumber(rows)
        m = [rows.index(e) for e in made]
    elif op == 'editmany':
        moved = []
        for ed in b.get('edits', []):
            r = rows[int(ed['row'])]
            if 'slot' in ed:
                if int(ed['slot']) == 0 and generic(_num(r['char_id'])):
                    raise ValueError('Generic units can\'t be in your army (the game only places your army\'s own members).')
                r['army_slot'] = str(int(ed['slot']))
            if 'orders' in ed:
                r['orders'] = str(int(ed['orders']))
            if 'x' in ed or 'y' in ed:
                x, y = int(ed.get('x', r['x'])), int(ed.get('y', r['y']))
                check_xy(int(b['ch']), x, y)
                r['x'], r['y'] = str(x), str(y)
            if 'list' in ed and str(ed['list']) != r['index'].partition('.')[0]:
                r['index'] = f"{int(ed['list'])}.9999"
            moved.append(r)
        rows = _renumber(rows)
        m = [rows.index(r) for r in moved]
    elif op == 'edit':
        i = int(b['row'])
        r = rows[i]
        cid = _num(r['char_id'], -1)
        t, ur = units.get(cid, (None, None))
        if 'generic' in b:
            if t != 'units_generic':
                raise ValueError('Only generic units take a class and level here; named units are on the Characters page.')
            spec = _gen_spec(b['generic'], {k: ur.get(k, '') for k in GEN_FIELDS})
            if b.get('scope') == 'all':
                gi = gt.rows.index(ur)
                for k in GEN_FIELDS:
                    if ur.get(k, '') != spec[k]:
                        ops['list'].append(('cell', 'units_generic', gi, k, ur.get(k, ''), spec[k]))
                cls = p.table('classes')
                if cls and 0 <= _num(spec['class']) < len(cls.rows) and '_class_name' in gt.fields:
                    ops['list'].append(('cell', 'units_generic', gi, '_class_name', ur.get('_class_name', ''), cls.rows[_num(spec['class'])]['_name']))
            else:
                others = [x for x in rows if x is not r]
                r['char_id'] = str(generic_for(spec, others, ops))
        elif b.get('char_id') not in (None, ''):
            r['char_id'] = str(unit_of(b))
        if 'x' in b or 'y' in b:
            x, y = int(b.get('x', r['x'])), int(b.get('y', r['y']))
            if 'ch' in b:
                check_xy(int(b['ch']), x, y)
            r['x'], r['y'] = str(x), str(y)
        for k, f_ in (('slot', 'army_slot'), ('orders', 'orders')):
            if k in b:
                r[f_] = str(int(b[k]))
        if 'leader' in b:
            r['leader_flag'] = '1' if b['leader'] else '0'
        if int(r['army_slot']) == 0 and generic(_num(r['char_id'])):
            raise ValueError('Generic units can\'t be in your army (the game only places your army\'s own members).')
        r['_name'] = ops.get('_labels', {}).get(_num(r['char_id'])) or unit_label(_num(r['char_id']))
        if 'list' in b and str(b['list']) != r['index'].partition('.')[0]:
            r['index'] = f"{int(b['list'])}.9999"
        rows = _renumber(rows)
        m = [rows.index(r)]
    elif op == 'remove':
        gone = {int(i) for i in b.get('rows', [])}
        rows = _renumber([r for i, r in enumerate(rows) if i not in gone])
        m = []
    else:
        raise ValueError(f'unknown map unit action {op}')
    if rows != old:
        ops['list'].insert(0, ('rows', 'deploy', 0, old, rows))
    if ops['list']:
        p.edit(ops['list'])
    return {'ok': True, 'rows': m, 'note': note, 'new': ops.get('_new', [])}



# ---------------------------------------------------------------- armies and enemy AI
import fe4armies                   # noqa: E402

AI = 'ai_orders.evt'
# words for each AI command: (sentence, fields [(label, kind, byte pos, size)]); {k} = argument names
AI_WORDS = {
    0x00: ('Stay where it is this turn', []),
    0x01: ('Go to step {jump}', []),
    0x02: ('Fight style from here on: {mode}', [('Style', 'mode', 1, 1)]),
    0x03: ('Group pace: {pace}', [('Pace', 'pace', 1, 1)]),
    0x04: ('Never attack {slot}', [('Spare', 'slot', 1, 1)]),
    0x05: ('Set an unknown switch (bit 9 of $7E:2000)?', []),
    0x06: ('Seize {loc} (skipped once it is taken), fighting {mode2}', [('Castle', 'loc', 1, 1), ('Style', 'mode', 2, 1)]),
    0x07: ('Guard {loc} while its army holds it, fighting {mode2}', [('Castle', 'loc', 1, 1), ('Style', 'mode', 2, 1)]),
    0x08: ('Raid {loc}', [('Village', 'loc', 1, 1)]),
    0x09: ('Move to ({b4}, {b5}) once', [('x', 'num', 4, 1), ('y', 'num', 5, 1)]),
    0x0A: ('Attack anyone in reach; otherwise stay', []),
    0x0B: ('Attack anyone in reach; otherwise go on to the next step', []),
    0x0C: ('March in formation: {formation}, facing {facing}?', [('Shape', 'formation', 1, 1), ('Facing', 'facing', 2, 1)]),
    0x0D: ('Attack {unit}', [('Target', 'unit', 1, 2)]),
    0x0E: ('Follow {unit}, staying within {b3}', [('Unit', 'unit', 1, 2), ('Within', 'num', 3, 1)]),
    0x0F: ('Go back to its castle', []),
    0x10: ('If no enemy is near, go back to its castle', []),
    0x11: ('When under {pct} of its group is left, go back to its castle', [('Group left', 'pct', 1, 1)]),
    0x12: ('Fall back toward its target while attacking?', []),
    0x13: ('Hold its position', []),
    0x14: ('Every {b1} turn(s), send out group members who are off the map?', [('Turns', 'num', 1, 1)]),
    0x15: ('Set event flag {flag}', []),
    0x16: ('Clear event flag {flag}', []),
    0x17: ('Raid the nearest village', []),
    0x18: ('Attack anyone (marches on the nearest enemy)', []),
    0x19: ('Attack anyone, as a Hunter', []),
    0x1A: ('Close in on an enemy with free sides around it', []),
    0x1B: ('Close in on an enemy with free sides around it', []),
    0x1C: ('Close in on an enemy with free sides around it', []),
    0x1D: ('Close in on an enemy with free sides around it', []),
    0x1E: ('Go back to its castle to heal when its HP is at or below {pct}', [('HP', 'pct', 1, 1)]),
    0x1F: ('From turn {b1} on, go to step {jump}', [('Turn', 'num', 1, 1)]),
    0x20: ('If event flag {flag} is set, go to step {jump}', []),
    0x21: ('If event flag {flag} is not set, go to step {jump}', []),
    0x22: ('If nothing can be attacked this turn, go to step {jump}', []),
    0x23: ('If routine {asm} says so, go to step {jump}', []),
    0xFF: ('End', []),
}
# whole programs the editor can write: action -> lines (hex with {c} castle, {u} unit word)
AI_ACTIONS = {
    'attack_any': ('Attack anyone', ['18', 'FF']),
    'attack_reach': ('Attack anyone in reach, otherwise stay', ['0A', 'FF']),
    'seize': ('Seize a castle, then attack anyone', ['06 {c} 01', '18', 'FF']),
    'guard': ('Guard a castle', ['07 {c} 04', '0A', 'FF']),
    'raid': ('Raid villages, then attack anyone', ['17', '18', 'FF']),
    'attack_unit': ('Go after one unit, then attack anyone', ['0D {u}', '18', 'FF']),
    'stay': ('Stay put (never moves or attacks)', ['00']),
}


def _ai_blocks():
    f = need_project().evt(AI)
    if f is None:
        raise KeyError('This project has no ai_orders.evt.')
    out = {}
    for blk in f.blocks():
        m = re.match(r'army (\d+) orders (\d+)$', blk['label'])
        if m:
            out[(int(m.group(1)), int(m.group(2)))] = blk
    at = need_project().table('armies')
    for r in at.rows if at else []:                # new armies share the programs of the army they copy
        like = (r.get('orders_like') or '').strip()
        if like.isdigit():
            for (a, k), blk in list(out.items()):
                if a == int(like):
                    out[(_num(r['army']), k)] = blk
    return out


def slot_names():
    """{army slot: 'Sigurd / Seliph'}: who sits in each player slot, generation 1 then 2."""
    p = need_project()
    out = {}
    for t in ('units_playable', 'units_children'):
        tb = p.table(t)
        for r in tb.rows if tb else []:
            v = (r.get('slot') or '').strip()
            if v.isdigit() and int(v) < 128 and r.get('_name'):
                out.setdefault(int(v), [])
                if r['_name'] not in out[int(v)]:
                    out[int(v)].append(r['_name'])
    return {k: ' / '.join(v) for k, v in out.items()}


def _ai_steps(blk, com, locname):
    """The program's commands in words, with jump targets as step numbers."""
    cmds = blk['cmds']
    sn = slot_names()
    slot_name = lambda n: sn.get(n, 'slot %d' % n)  # noqa: E731
    index = {c['addr']: i for i, c in enumerate(cmds) if c['addr']}
    bank = blk['start'][:2]
    steps, inside = [], True
    for i, c in enumerate(cmds):
        b = cmd_bytes(c)
        toks = c['hex'].split()
        op = b[0] if b else 0xFF
        jump = None
        spec = fe4armies.AI_OPS.get(op)
        if spec and spec[2] is not None:
            pos = 1 + spec[2]
            if pos < len(toks) and toks[pos].startswith('@L'):
                jump = int(toks[pos][2:])
            else:
                a = '%s%02X%02X' % (bank, b[pos + 1], b[pos])
                jump = index.get(a)
                if jump is None:
                    inside = False
        words, fields = AI_WORDS.get(op, ('Unknown command %02X (bytes %s)' % (op, c['hex']), []))
        w = lambda k: b[k] | b[k + 1] << 8 if k + 1 < len(b) else 0  # noqa: E731
        vals = {'jump': (jump + 1) if jump is not None else 'outside this program',
                'loc': locname(b[1]) if len(b) > 1 else '', 'unit': com.unit(w(1)).rsplit('(', 1)[0] if len(b) > 2 else '',
                'flag': '%d.%d' % (w(1), b[3]) if len(b) > 3 else ''}
        vals.update({'b%d' % k: b[k] for k in range(1, len(b))})
        if len(b) > 1:
            vals['pct'] = '%d%%' % round(b[1] * 100 / 256)
            vals['pace'] = 'full move' if b[1] == 0 else 'about %d%% of its move' % round(b[1] * 100 / 256)
            vals['slot'] = slot_name(b[1])
            vals['formation'] = fe4armies.FORMATIONS[b[1]] if b[1] < len(fe4armies.FORMATIONS) else 'shape %d' % b[1]
            vals['mode'] = fe4armies.mode_name(b[1])
        if len(b) > 2:
            vals['mode2'] = fe4armies.mode_name(b[2])
            vals['facing'] = fe4armies.FACINGS[b[2] & 3]
        if op == 0x23 and len(b) > 3:
            vals['asm'] = '$%02X:%02X%02X' % (b[3], b[2], b[1])
        try:
            text = words.format(**vals)
        except (KeyError, IndexError):
            text = words
        steps.append({'line': c['line'], 'hex': c['hex'], 'op': op, 'text': text, 'jump': jump,
                      'fields': [list(f_) for f_ in fields], 'new': c['addr'] is None,
                      'known': op in AI_WORDS and '?' not in words})
    return steps, inside


def _chapter_slots(ch):
    """{slot: army} from the chapter's $4B commands (the last one for a slot wins)."""
    out = {}
    f = need_project().evt(chapter_file(ch))
    for blk in f.blocks():
        for c in blk['cmds']:
            b = cmd_bytes(c)
            if len(b) == 3 and b[0] == 0x4B:
                out.setdefault(b[1], b[2])
    return out


def chapter_deploy(ch):
    """[(row index, row, list, entry, sure)] of deploy.csv entries that belong to chapter ch."""
    p = need_project()
    dch = deploy_chapters(os.path.join(p.path, 'events'))
    known = sorted(dch)
    out = []
    dt = p.table('deploy')
    for i, r in enumerate(dt.rows if dt else []):
        lst, _, ent = (r.get('index') or '').partition('.')
        if not lst.isdigit():
            continue
        n = int(lst)
        if n in dch:
            c, sure = dch[n], True
        else:
            before = [k for k in known if k < n]
            c, sure = (dch[before[-1]] if before else 0), False
        if c == ch:
            out.append((i, r, n, ent, sure))
    return out


def castle_names():
    rom = rom_data()
    return [fe4locations.castle_name(rom, i) if rom is not None else '' for i in range(0x40)]


def api_armies(b, q):
    p = need_project()
    ch = int(q.get('ch', ['0'])[0])
    com = commenter()
    at = p.table('armies')
    blocks = _ai_blocks()
    locs = []
    lt = p.table('locations')
    for r in lt.rows if lt else []:
        if str(r.get('chapter')) == str(ch):
            locs.append({'index': int(r['index']), 'kind': r.get('kind'), 'name': r.get('_castle_name') or '',
                         'x': r.get('x'), 'y': r.get('y')})
    lname = {l['index']: (l['name'] or 'castle %d' % l['index']) if l['kind'] == 'castle' else 'village %d' % l['index']
             for l in locs}
    locname = lambda i: lname.get(i, 'location %d' % i)  # noqa: E731
    slots = _chapter_slots(ch)
    units = unit_lookup()
    dep = chapter_deploy(ch)
    names = castle_names()
    armies = []
    for slot, army in sorted(slots.items()):
        row = next((r for r in at.rows if r.get('army') == str(army)), None) if at else None
        if row is None:
            continue
        ids = lambda t: [int(x) for x in (t or '').replace(',', ';').split(';') if x.strip().lstrip('-').isdigit()]  # noqa: E731
        progs = []
        k = 1
        while (army, k) in blocks:
            blk = blocks[(army, k)]
            if blk['cmds']:
                steps, inside = _ai_steps(blk, com, locname)
            else:
                steps, inside = [], False
            ends = bool(steps) and steps[-1]['op'] in (0x00, 0x01, 0xFF)
            progs.append({'k': k, 'start': blk['start'], 'steps': steps, 'shared': not blk['cmds'],
                          'editable': bool(blk['cmds']) and inside and ends})
            k += 1
        us = []
        for i, r, lst, ent, sure in dep:
            if str(r.get('army_slot')) != str(slot):
                continue
            cid = int(r['char_id']) if (r.get('char_id') or '').isdigit() else -1
            t, ur = units.get(cid, (None, None))
            us.append({'row': i, 'list': lst, 'entry': ent, 'char_id': cid, 'orders': int(r.get('orders') or 0),
                       'name': (ur or {}).get('_name') or r.get('_name') or f'Unit {cid}',
                       'class': (ur or {}).get('_class_name', ''), 'level': (ur or {}).get('level', ''),
                       'leader': r.get('leader_flag') not in ('', '0', None), 'x': r.get('x'), 'y': r.get('y')})
        nm = int(row.get('name') or 255)
        armies.append({'slot': slot, 'army': army, 'row': at.rows.index(row), 'nameId': nm,
                       'name': (names[nm] if nm < 0x40 else '') or ('Army %d' % army),
                       'unk1': row.get('unk1'), 'unk2': row.get('unk2'),
                       'members': [{'id': u, 'name': com.unit(u).rsplit('(', 1)[0]} for u in ids(row.get('members'))],
                       'castles': ids(row.get('castles')), 'programs': progs, 'units': us})
    return {'ch': ch, 'title': CHAPTER_TITLES[ch] if ch < len(CHAPTER_TITLES) else '', 'armies': armies,
            'locations': locs, 'castleNames': names,
            'actions': [[k, v[0]] for k, v in AI_ACTIONS.items()],
            'formations': fe4armies.FORMATIONS, 'facings': fe4armies.FACINGS, 'modes': fe4armies.MODES,
            'slots': sorted([k, v] for k, v in slot_names().items())}


def api_aicmd(b, q):
    """Same-length edit of one AI command: {line, hex}."""
    p = need_project()
    f = p.evt(AI)
    line = int(b['line'])
    old = next((c for blk in f.blocks() for c in blk['cmds'] if c['line'] == line), None)
    if old is None:
        raise KeyError(f'line {line + 1} of {AI} is not a command')
    toks = b['hex'].split()
    ot = old['hex'].split()
    if len(toks) != len(ot) or toks[0].upper() != ot[0].upper():
        raise ValueError('Keep the same kind of command and length.')
    for t, o in zip(toks, ot):
        if o.startswith('@') and t != o:
            raise ValueError('The jump of this step can\'t be changed here.')
        if not o.startswith('@') and not re.fullmatch(r'[0-9A-Fa-f]{2}', t):
            raise ValueError('Write the bytes as hex pairs.')
    hexs = ' '.join(t if t.startswith('@') else t.upper() for t in toks)
    nb = cmd_bytes({'hex': hexs})
    name, note = fe4armies.ai_comment(rom_data(), nb, commenter(), {}) if nb[0] in fe4armies.AI_OPS or nb[0] == 0xFF else ('?', '')
    if '@L' in hexs:
        note = _step_note(nb, hexs)
    p.set_command(AI, line, hexs, ('%-17s %s' % (name, note)).rstrip())
    return {'ok': True}


def _step_note(nb, hexs):
    """Comment for a command whose jump is @Lk."""
    k = int(re.search(r'@L(\d+)', hexs).group(1)) + 1
    if nb[0] == 0x1F:
        return f'turn >= {nb[1]} -> step {k}'
    return f'-> step {k}'


def api_airecipe(b, q):
    """Rewrite army N's program K: {army, k, action, castle?, unit?, until_turn?, wait?,
    spare? (slot), formation? + facing?, retreat? (HP %)}. One undo step."""
    p = need_project()
    f = p.evt(AI)
    army, k = int(b['army']), int(b['k'])
    blk = _ai_blocks().get((army, k))
    if blk is None:
        raise KeyError(f'army {army} has no program {k}')
    if not blk['cmds']:
        raise ValueError('This program is the same code as one listed earlier; change that one.')
    act = b.get('action')
    if act not in AI_ACTIONS:
        raise ValueError(f'unknown action {act}')
    body = list(AI_ACTIONS[act][1])
    vals = {}
    if '{c}' in ' '.join(body):
        c = int(b.get('castle', -1))
        if not 0 <= c < 64:
            raise ValueError('Choose a castle.')
        vals['c'] = '%02X' % c
    if '{u}' in ' '.join(body):
        u = int(b.get('unit', -1))
        if not 0 < u < 0xFFFF:
            raise ValueError('Choose who to go after.')
        vals['u'] = '%02X %02X' % (u & 0xFF, u >> 8)
    body = [x.format(**vals) for x in body]
    style = b.get('style')
    if style not in (None, ''):
        style = int(style)
        if not 0 <= style < len(fe4armies.MODES):
            raise ValueError('Unknown fight style.')
        if body[0].startswith(('06 ', '07 ')):          # seize / guard set their own style while they act
            body[0] = body[0][:6] + '%02X' % style
    turn = int(b.get('until_turn') or 0)
    if turn:
        if not 2 <= turn <= 99:
            raise ValueError('The waiting turn is 2 to 99.')
        # until that turn: only the waiting behaviour; from it on: jump to the action
        pre = ['00'] if b.get('wait') == 'stay' else ['0A', 'FF']
        body = ['1F %02X @L%d' % (turn, len(pre) + 1)] + pre + body
    # optional settings that run before everything else (each falls through)
    setup = []
    if b.get('spare') not in (None, ''):
        n = int(b['spare'])
        if not 0 < n < 128:
            raise ValueError('Pick who to spare.')
        setup.append('04 %02X' % n)
    if b.get('formation') not in (None, ''):
        shape, facing = int(b['formation']), int(b.get('facing') or 0)
        if not (0 <= shape < len(fe4armies.FORMATIONS) and 0 <= facing < 4):
            raise ValueError('Unknown formation.')
        setup.append('0C %02X %02X' % (shape, facing))
    if style not in (None, ''):
        setup.append('02 %02X' % style)
    if b.get('retreat') not in (None, ''):
        pc = int(b['retreat'])
        if not 1 <= pc <= 99:
            raise ValueError('Retreat at 1 to 99% HP.')
        setup.append('1E %02X 00 01' % round(pc * 256 / 100))
    if setup:
        body = setup + [re.sub(r'@L(\d+)', lambda m: '@L%d' % (int(m.group(1)) + len(setup)), x) for x in body]
    com = commenter()
    lines = []
    for hx in body:
        nb = cmd_bytes({'hex': hx})
        name, note = fe4armies.ai_comment(rom_data(), nb, com, {}) if nb[0] in fe4armies.AI_OPS or nb[0] == 0xFF else ('?', '')
        if '@L' in hx:
            note = _step_note(nb, hx)
        lines.append(('+ %-18s ; %-17s %s' % (hx, name, note)).rstrip())
    a, z = blk['cmds'][0]['line'], blk['cmds'][-1]['line'] + 1
    p.edit([('lines', AI, a, f.lines[a:z], lines)])
    return {'ok': True}


# ---------------------------------------------------------------- map sprites
def sprite_rows(sid):
    """Index rows of a sprite's three frames: the project's drawing if it has one, else the ROM's."""
    rom = rom_data()
    if rom is None:
        return None
    p = project()
    data = p.blob(fe4sprites.sprite_file(sid)).data if p else None
    if data is not None:
        return fe4sprites.rows_from_png(sid, data, fe4sprites.palette(rom, 0))
    return fe4sprites.sprite_rows(rom, sid)


def sprite_image(sid, army, scale, indexed=False):
    rom = rom_data()
    rows = sprite_rows(sid)
    if rows is None:
        return None
    if indexed:
        return fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0))
    offs = dict(fe4sprites.ARMIES)
    pal = fe4sprites.palette(rom, list(offs.values())[army] if 0 <= army < len(offs) else 0)
    return fe4sprites.rows_png(rows, pal, scale)


_walk_cache = {}


def walk_rows(sid):
    """Index rows of a sprite's walking set: the project's drawing if it has one, else the ROM's."""
    rom = rom_data()
    if rom is None:
        return None
    p = project()
    data = p.blob(fe4walk.walk_file(sid)).data if p else None
    if data is not None:
        return fe4walk.rows_from_png(sid, data, fe4sprites.palette(rom, 0))
    key = (id(rom), len(rom), sid)
    if key not in _walk_cache:
        if len(_walk_cache) > 200:
            _walk_cache.clear()
        _walk_cache[key] = fe4walk.set_rows(rom, sid)
    return _walk_cache[key]


def walk_image(sid, army, scale, indexed=False):
    rom = rom_data()
    rows = walk_rows(sid)
    if rows is None:
        return None
    if indexed:
        return fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0))
    offs = dict(fe4sprites.ARMIES)
    pal = fe4sprites.palette(rom, list(offs.values())[army] if 0 <= army < len(offs) else 0)
    return fe4sprites.rows_png(rows, pal, scale)


# ---------------------------------------------------------------- music
AUDIO_TYPES = {'.ogg': 'audio/ogg', '.flac': 'audio/flac', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.pcm': 'application/octet-stream'}


def port_knows(exe, word):
    try:
        with open(exe, 'rb') as fh:
            return word in fh.read()
    except OSError:
        return False


def music_folder_files(p):
    """{song: relative path} of the project's music files, counting unsaved changes."""
    out = {s: fe4music.FOLDER + '/' + f for s, f in fe4music.music_files(p.path).items()}
    for rel, bl in p.blobs.items():
        if not rel.startswith(fe4music.FOLDER + '/'):
            continue
        f = rel.split('/', 1)[1]
        num = re.match(r'(\d+)', f)
        if not num:
            continue
        n = int(num.group(1))
        if bl.data is None:
            if out.get(n) == rel:
                del out[n]
        elif f.lower().endswith(fe4music.AUDIO):
            out[n] = rel
    return out


def music_audio(song):
    p = need_project()
    rel = music_folder_files(p).get(song)
    if not rel:
        return None
    data = p.blob(rel).data
    if data is None:
        return None
    return data, AUDIO_TYPES.get(os.path.splitext(rel)[1].lower(), 'application/octet-stream')


def _plain(text, n=90):
    t = re.sub(r'\{[^}]*\}', ' ', text or '')
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:n] + ('…' if len(t) > n else '')


def music_scenes(p):
    """[{scene, file, line, song, chapters, text}] for every PLAY_SONG in scenes.evt."""
    f = p.evt('scenes.evt')
    if f is None:
        return []
    idx = story_index()
    d = p.dialogue()
    out = []
    for blk in f.blocks():
        m = re.match(r'scene\s+(\d+)', blk['label'])
        if not m:
            continue
        sid = int(m.group(1))
        sc = idx['scenes'].get(sid) or {}
        text = ''
        if d is not None:
            for k in sc.get('messages', []):
                if k in d.text:
                    text = _plain(d.text[k])
                    break
        chs = sorted(int(c[2:4]) for c in idx['chapter_scenes'].get(sid, ()) if c.startswith('ch') and c[2:4].isdigit())
        for c in blk['cmds']:
            b = cmd_bytes(c)
            if len(b) == 2 and b[0] == 0x0E:
                out.append({'scene': sid, 'file': 'scenes.evt', 'line': c['line'], 'song': b[1], 'chapters': chs, 'text': text})
    return out


def api_music(b, q):
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM first.')
    t = p.table('music')
    rows = {k: {} for k in fe4music.places()}
    for i, r in enumerate(t.rows):
        if r.get('table') in rows:
            rows[r['table']][int(r['index'])] = {'row': i, 'song': int(r['song'] or 0), 'name': r.get('_name', '')}
    P = fe4music.places()
    for k in ('fixed', 'battle', 'battle_more'):          # labels come from the kit (the CSV keeps the old ones)
        for i, r in rows[k].items():
            if i < len(P[k]):
                r['name'] = P[k][i][1]
    files = music_folder_files(p)
    uses = {}
    chap = lambda i: CHAPTER_TITLES[i].split(':')[0] if i < len(CHAPTER_TITLES) else str(i)  # noqa: E731
    for i, r in rows['opening'].items():
        uses.setdefault(r['song'], []).append('%s opens' % chap(i))
    for name, label in (('first', 'map starts'), ('phase', 'your phase')):
        for i, r in rows[name].items():
            uses.setdefault(r['song'], []).append('%s: %s' % (chap(i), label))
    for i, r in rows['army'].items():
        if r['name']:
            uses.setdefault(r['song'], []).append('%s army\'s phase' % r['name'])
    for k in ('fixed', 'battle', 'battle_more'):
        for i, r in rows[k].items():
            if k != 'battle_more' or i == 0:
                uses.setdefault(r['song'], []).append(('Battle: ' if k != 'fixed' else '') + r['name'])
    scenes = music_scenes(p)
    by_song = {}
    for sc in scenes:
        by_song.setdefault(sc['song'], set()).add(sc['scene'])
    for s_, sids in by_song.items():
        uses.setdefault(s_, []).append('scene%s %s' % ('s' if len(sids) > 1 else '', ', '.join(str(x) for x in sorted(sids)[:8])
                                                       + (' and %d more' % (len(sids) - 8) if len(sids) > 8 else '')))
    songs = []
    for n in range(1, fe4music.SONGS + 1):
        rel = files.get(n)
        songs.append({'n': n, 'kind': fe4music.song_kind(rom, n), 'sameAs': fe4music.same_as(rom, n),
                      'name': fe4music.NAMED.get(n, ''),
                      'uses': uses.get(n, []), 'file': rel.split('/', 1)[1] if rel else None,
                      'size': len(p.blob(rel).data or b'') if rel else 0})
    bt = p.table('music_bosses')
    names = {}
    for tn in ('units_playable', 'units_children', 'units_npc', 'units_generic'):
        tt = p.table(tn)
        for r in (tt.rows if tt else []):
            try:
                if r.get('_name'):
                    names.setdefault(int(r['index']), r['_name'])
            except (KeyError, ValueError):
                pass
    bosses = [{'row': i, 'unit': int(r['unit'], 0)} for i, r in enumerate(bt.rows)] if bt else []
    exe = port_exe()
    lst = lambda k: [dict(r, index=i) for i, r in sorted(rows[k].items())]  # noqa: E731
    return {'songs': songs,
            'chapters': [{'title': CHAPTER_TITLES[i] if i < len(CHAPTER_TITLES) else str(i), 'opening': rows['opening'].get(i),
                          'first': rows['first'].get(i), 'phase': rows['phase'].get(i)} for i in range(fe4music.CHAPTERS)],
            'armies': [r for r in lst('army') if r['name']], 'fixed': lst('fixed'), 'battle': lst('battle'),
            'battleMore': lst('battle_more'), 'bosses': bosses,
            'units': sorted(({'n': k, 'name': v} for k, v in names.items()), key=lambda x: (x['name'], x['n'])),
            'scenes': scenes,
            'portMusic': bool(exe and port_knows(exe, b'--music')), 'folder': os.path.join(p.path, fe4music.FOLDER)}


def api_musicfile(b, q):
    """Give a song a music file ({song, name, data: base64}) or take it away ({song, remove: true})."""
    p = need_project()
    song = int(b['song'])
    if not 1 <= song <= 999:
        raise ValueError('Songs are numbered 1 to 999.')
    old = music_folder_files(p).get(song)
    ops = []
    if b.get('remove'):
        if old:
            ops += p.set_blob(old, None)
        return {'ok': True}
    ext = os.path.splitext(b.get('name', ''))[1].lower()
    if ext not in AUDIO_TYPES:
        raise ValueError('Music files can be .ogg, .flac, .mp3, .wav or MSU-1 .pcm.')
    data = base64.b64decode(b.get('data', ''), validate=True)
    if len(data) < 64:
        raise ValueError('That file is empty.')
    if ext == '.pcm' and data[:4] != b'MSU1':
        raise ValueError('That .pcm file isn\'t an MSU-1 track (it should start with MSU1).')
    rel = '%s/%d%s' % (fe4music.FOLDER, song, ext)
    if old and old != rel:
        p.set_blob(old, None)
    p.set_blob(rel, data)
    return {'ok': True, 'file': rel.split('/', 1)[1]}


def api_mapwalk(b, q):
    """Replace a sprite's walking pictures with a PNG (base64), or {reset: true}."""
    import base64
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    sid = fe4sprites.parse_sprite(str(b['name']))
    rel = fe4walk.walk_file(sid)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    try:
        rows = fe4walk.rows_from_png(sid, base64.b64decode(b['png']), fe4sprites.palette(rom, 0))
    except ValueError as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(rel, fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0)))
    return {'ok': True}


def api_mapsprites(b, q):
    p = need_project()
    t = p.table('map_sprites')
    if t is None:
        raise KeyError('This project has no map_sprites.csv; reopen it with this version to add one.')
    classes = {}
    users = {}
    for i, r in enumerate(t.rows):
        c = int(r['class'])
        e = classes.setdefault(c, {'c': c, 'name': r.get('_class_name') or f'Class {c}', 'entries': []})
        e['entries'].append({'row': i, 'entry': int(r['entry']), 'gender': r['gender'],
                             'character': r.get('character', ''), 'who': r.get('_character_name', ''),
                             'sprite': r['sprite']})
        users.setdefault(r['sprite'].upper(), [])
        if e['name'] not in users[r['sprite'].upper()]:
            users[r['sprite'].upper()].append(e['name'])
    sprites = []
    rom = rom_data()
    for sid in fe4sprites.all_ids():
        nm = fe4sprites.sprite_name(sid)
        data = p.blob(fe4sprites.sprite_file(sid)).data
        walk = p.blob(fe4walk.walk_file(sid)).data
        sprites.append({'name': nm, 'tall': fe4sprites.is_tall(sid), 'users': users.get(nm, []),
                        'custom': data is not None, 'ver': '%08x' % zlib.crc32(data) if data is not None else 'rom',
                        'walkCustom': walk is not None, 'walkVer': '%08x' % zlib.crc32(walk) if walk is not None else 'rom',
                        'offsets': fe4walk.offsets(rom, sid) if rom is not None else None})
    return {'classes': [classes[k] for k in sorted(classes)], 'sprites': sprites,
            'armies': [a for a, _ in fe4sprites.ARMIES], 'dirs': list(fe4walk.DIRS)}


def api_mapsprite(b, q):
    """Replace a sprite's drawing with a PNG (base64), or {reset: true}."""
    import base64
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    sid = fe4sprites.parse_sprite(str(b['name']))
    rel = fe4sprites.sprite_file(sid)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    try:
        rows = fe4sprites.rows_from_png(sid, base64.b64decode(b['png']), fe4sprites.palette(rom, 0))
    except ValueError as e:
        raise ValueError(str(e))
    except Exception:          # noqa: BLE001
        raise ValueError('That file could not be read as a PNG picture.')
    p.set_blob(rel, fe4sprites.indexed_sheet_png(rows, fe4sprites.palette(rom, 0)))
    return {'ok': True}


# ---------------------------------------------------------------- map tiles
_gfx_cache = {}


def chapter_terrain(ch):
    """{metatile: terrain} from map_terrain.csv for chapter ch (all 1024 when the table is there)."""
    p = project()
    t = p.table('map_terrain') if p else None
    if t is None:
        return {}
    out = {}
    for r in t.rows[ch * 1024:(ch + 1) * 1024]:
        if r.get('chapter') == str(ch) and r.get('terrain', '').isdigit():
            out[int(r['tile'])] = int(r['terrain'])
    return out


def chapter_drawings(ch):
    p = project()
    if p is None:
        return {}
    out = {}
    d = os.path.join(p.path, 'maps', 'tiles', fe4maps.MAP_NAMES[ch])
    names = set(os.listdir(d)) if os.path.isdir(d) else set()
    names |= {rel.rsplit('/', 1)[1] for rel in p.blobs if rel.startswith(f'maps/tiles/{fe4maps.MAP_NAMES[ch]}/')}
    for f in names:
        m = re.fullmatch(r't(\d{3})\.png', f)
        if m:
            data = p.blob(fe4maptiles.drawing_file(ch, int(m.group(1)))).data
            if data is not None:
                out[int(m.group(1))] = data
    return out


def tiles_version(ch):
    ts = tileset_blob(ch)
    if ts:
        m = project().map(ch)
        ids = sorted({w & 0x3FF for w in m.words}) if m else []
        return 's%08x%08x' % (zlib.crc32(ts), zlib.crc32(bytes(str(ids), 'ascii')))
    dr = chapter_drawings(ch)
    if not dr:
        return 'rom'
    return '%08x' % zlib.crc32(b''.join(b'%d:' % k + dr[k] for k in sorted(dr)))


def chapter_gfx(ch, drawings=None):
    """The chapter's tiles with the project's drawings (or its own whole tile set).  Earlier chapters'
    drawings come first, since they take from the shared tile pool before this one (as the build does)."""
    rom = rom_data()
    if tileset_blob(ch) and drawings is None:
        key = (id(rom), ch, tiles_version(ch))
        if key not in _gfx_cache:
            if len(_gfx_cache) > 24:
                _gfx_cache.clear()
            _gfx_cache[key] = fe4mapset.chapter_gfx(rom, ch, tileset_conv(ch)[0])
        return _gfx_cache[key]
    dr = {c: chapter_drawings(c) for c in range(ch + 1)}
    if drawings is not None:
        dr[ch] = drawings
    key = (id(rom), ch, tuple(tiles_version(c) for c in range(ch + 1)))
    if drawings is None and key in _gfx_cache:
        return _gfx_cache[key]
    pool = list(fe4maptiles.pool_tiles(rom))
    for c in range(ch):
        if dr[c] and not tileset_blob(c):
            pool = list(fe4maptiles.load_project(rom, None, c, None, dr[c], pool).pool)
    g = fe4maptiles.load_project(rom, None, ch, None, dr[ch], pool)
    if drawings is None:
        if len(_gfx_cache) > 24:
            _gfx_cache.clear()
        _gfx_cache[key] = g
    return g


# ---------------------------------------------------------------- whole tile sets and map pictures (kit v55)
def tileset_blob(ch):
    p = project()
    if p is None or not 0 <= ch < fe4maps.MAP_COUNT:
        return None
    return p.blob(fe4mapset.atlas_file(ch)).data


def tileset_conv(ch, data=None):
    """(converted set, note) of the chapter's tile set picture (or the given one)."""
    p = project()
    m = p.map(ch)
    return fe4mapset.converted(p.path, ch, data or tileset_blob(ch), rom_data(), m.words if m else None)


def api_tileset(b, q):
    """Whether chapter ch has its own whole tile set, how it fits, and the tiles the game changes."""
    p = need_project()
    ch = int(q['ch'][0])
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    data = tileset_blob(ch)
    note = None
    if data:
        try:
            note = tileset_conv(ch)[1]
        except ValueError as e:
            note = {'error': str(e)}
    m = p.map(ch)
    return {'ch': ch, 'custom': data is not None, 'note': note, 'reserved': sorted(fe4mapset.reserved(rom, ch)),
            'ver': tiles_version(ch), 'w': map_area(ch)[2] * 16, 'h': map_area(ch)[3] * 16,
            'tileLimit': len(fe4mapset.FREE_TILES)}


def _terrain_ops(p, ch, new):
    t = p.table('map_terrain')
    if t is None:
        return []
    ops = []
    for k in range(1024):
        row = ch * 1024 + k
        if row < len(t.rows) and t.rows[row].get('chapter') == str(ch) and t.rows[row].get('tile') == str(k):
            old = t.rows[row].get('terrain', '')
            if old != str(new[k]):
                ops.append(('cell', 'map_terrain', row, 'terrain', old, str(new[k])))
    return ops


def api_tileset_set(b, q):
    """{ch, png, kind: 'tiles'} a new tile set picture; {ch, png, kind: 'map', terrain: 'place'|'look'}
    a whole-map picture (makes the tile set, the map and the tiles' terrain); {ch, reset: true} back
    to the game's tiles, map and terrain.  One undo step."""
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    ch = int(b['ch'])
    if not 0 <= ch < fe4maps.MAP_COUNT:
        raise ValueError('No such chapter.')
    m = p.map(ch)
    rel = fe4mapset.atlas_file(ch)
    old = p.blob(rel).data
    if b.get('reset'):
        orig_words = fe4maps.load_map(rom, ch)
        ops = [('blob', rel, old, None)] if old else []
        if m:
            ops += [('map', ch, i, w, orig_words[i]) for i, w in enumerate(m.words) if i < len(orig_words) and w != orig_words[i]]
        ops += _terrain_ops(p, ch, fe4maptiles.ChapterGfx(rom, ch).terrain)
        p.edit(ops)
        return {'ok': True}
    try:
        data = base64.b64decode(b['png'])
    except (KeyError, ValueError):
        raise ValueError('That file could not be read as a PNG picture.')
    if b.get('kind') == 'map':
        if m is None:
            raise KeyError(f'no map for chapter {ch}')
        g = chapter_gfx(ch)
        terr = list(g.terrain)
        for k, t_ in chapter_terrain(ch).items():
            terr[k] = t_
        atlas, words, terrain, note = fe4mapset.import_map(rom, ch, data, g, list(m.words), terr,
                                                          'look' if b.get('terrain') == 'look' else 'place', map_area(ch))
        conv = fe4mapset.converted(p.path, ch, atlas, rom, words)[1]
        ops = [('blob', rel, old, atlas)]
        ops += [('map', ch, i, w, words[i]) for i, w in enumerate(m.words) if w != words[i]]
        ops += _terrain_ops(p, ch, terrain)
        p.edit(ops)
        return {'ok': True, 'note': note, 'conv': conv}
    conv = fe4mapset.converted(p.path, ch, data, rom, m.words if m else None)[1]    # ValueError: why it doesn't fit
    p.set_blob(rel, data)
    return {'ok': True, 'conv': conv}


def api_tileinfo(b, q):
    p = need_project()
    ch, k = int(q['ch'][0]), int(q['k'][0])
    m = p.map(ch)
    g = chapter_gfx(ch)
    terr = chapter_terrain(ch)
    used = sum(1 for w in m.words if w & 0x3FF == k)
    rom = rom_data()
    orig = fe4maptiles.ChapterGfx(rom, ch).terrain[k] if rom is not None else 0
    if tileset_blob(ch):
        note = tileset_conv(ch)[1]
        return {'ch': ch, 'k': k, 'own': True, 'tileset': True, 'onMap': used, 'terrain': terr.get(k, g.terrain[k]),
                'origTerrain': orig, 'row': ch * 1024 + k, 'custom': False, 'reserved': k in fe4mapset.reserved(rom, ch),
                'free': max(0, note['tile_limit'] - note['tiles']), 'freeShared': 0, 'merged': note['merged'],
                'ver': tiles_version(ch)}
    custom = k in chapter_drawings(ch)
    return {'ch': ch, 'k': k, 'own': k < 256, 'onMap': used, 'terrain': terr.get(k, g.terrain[k]), 'origTerrain': orig,
            'row': ch * 1024 + k, 'custom': custom, 'free': sum(g.room()), 'freeShared': g.room()[1],
            'ver': tiles_version(ch)}


def api_tiledraw(b, q):
    """Redraw chapter tile k from a PNG (base64), or {reset: true}.  One undo step."""
    import base64
    p = need_project()
    ch, k = int(b['ch']), int(b['k'])
    ts = tileset_blob(ch) if 0 <= ch < fe4maps.MAP_COUNT else None
    if ts:                     # the chapter's own whole tile set: any of the 1024, drawn into the set picture
        if not 0 <= k < 1024:
            raise ValueError('Tiles are numbered 0-1023.')
        if b.get('reset'):
            rgba = fe4maptiles.ChapterGfx(rom_data(), ch).metatile_rgba(k)
        else:
            rgba = fe4maptiles.rgba_from_png(base64.b64decode(b['png']))
        new = fe4mapset.draw_tile(ts, k, rgba)
        note = tileset_conv(ch, new)[1]
        p.set_blob(fe4mapset.atlas_file(ch), new)
        return {'ok': True, 'free': max(0, note['tile_limit'] - note['tiles'])}
    if not 0 <= ch < fe4maps.MAP_COUNT or not 0 <= k < 256:
        raise ValueError('Only the chapter\'s own tiles (0-255) can be redrawn; 256-1023 are shared by every chapter.')
    rel = fe4maptiles.drawing_file(ch, k)
    if b.get('reset'):
        p.set_blob(rel, None)
        return {'ok': True}
    data = base64.b64decode(b['png'])
    try:
        fe4maptiles.rgba_from_png(data)
        dr = dict(chapter_drawings(ch))
        dr[k] = data
        g = chapter_gfx(ch, dr)          # raises when the chapter runs out of 8x8 tiles
    except ValueError as e:
        raise ValueError(str(e))
    # later chapters take from the shared pool after this one: make sure they still fit
    alld = {c: chapter_drawings(c) for c in range(fe4maps.MAP_COUNT)}
    alld[ch] = dr
    try:
        fe4maptiles.load_chapters(rom_data(), {}, alld)
    except ValueError as e:
        c = getattr(e, 'ch', ch)
        raise ValueError(f'This picture needs shared tiles that {CHAPTER_TITLES[c] if c < len(CHAPTER_TITLES) else c} '
                         'already uses for its own redrawn tiles. Reuse more of the map\'s tiles in this picture.')
    p.set_blob(rel, data)
    return {'ok': True, 'free': sum(g.room())}


def api_spriteentry(b, q):
    """Add a per-character (or per-gender) sprite to a class: {class, character?, gender?, sprite}, or
    remove one: {row}.  One undo step; the class's rows are renumbered."""
    p = need_project()
    t = p.table('map_sprites')
    if t is None:
        raise KeyError('This project has no map_sprites.csv.')
    rows = t.rows
    if 'row' in b:                                     # remove
        i = int(b['row'])
        if not 0 <= i < len(rows) or rows[i].get('gender') == 'default':
            raise ValueError('The class\'s last ("everyone else") sprite can\'t be removed.')
        c = rows[i]['class']
        idx = [j for j, r in enumerate(rows) if r['class'] == c]
        old = [dict(rows[j]) for j in idx]
        new = [dict(r) for j, r in zip(idx, old) if j != i]
    else:
        c = str(int(b['class']))
        idx = [j for j, r in enumerate(rows) if r['class'] == c]
        if not idx:
            raise KeyError(f'class {c} has no sprite rows')
        sprite = fe4sprites.sprite_name(fe4sprites.parse_sprite(str(b['sprite'])))
        ch = int(b.get('character') or 0)
        g = b.get('gender')
        if g not in ('male', 'female'):
            g = 'male'
            if ch:
                hit = unit_lookup().get(ch)
                if hit and str(hit[1].get('gender', '0')).strip() == '1':
                    g = 'female'
        if len(idx) >= 30:
            raise ValueError('A class can have at most 30 sprite rows.')
        old = [dict(rows[j]) for j in idx]
        who = commenter().unit(ch).rsplit('(', 1)[0].strip() if ch else ''
        add = {f: '' for f in t.fields}
        add.update({'class': c, '_class_name': old[0].get('_class_name', ''), 'gender': g,
                    'character': str(ch), '_character_name': who, 'sprite': sprite})
        new = [dict(r) for r in old[:-1]] + [add] + [dict(old[-1])]    # before "everyone else"
    for k, r in enumerate(new):
        r['entry'] = str(k)
    p.edit([('rows', 'map_sprites', idx[0], old, new)])
    return {'ok': True}


# ---------------------------------------------------------------- skills
SKILL_HOLDERS = (('units_playable', 'skills'), ('units_npc', 'skills'), ('classes', 'skills'), ('items', 'skills'))
SKILL_TUNING = {3: ['amount'], 12: ['amount'], 15: ['amount', 'amount2'], 24: ['amount', 'amount2'],
                19: ['stat', 'amount', 'amount2', 'weapons'], 20: ['stat', 'amount', 'amount2', 'weapons'],
                21: ['stat', 'amount', 'amount2', 'weapons']}


def _split(v):
    return [x.strip() for x in (v or '').replace(',', ';').split(';') if x.strip()]


def api_skills(b, q):
    import fe4skillfx
    import fe4skills
    p = need_project()
    t = p.table('skills')
    if t is None:
        raise KeyError('This project has no skills.csv.')
    holders = {}
    for tname, field in SKILL_HOLDERS:
        tb = p.table(tname)
        for i, r in enumerate(tb.rows if tb else []):
            for sk in _split(r.get(field)):
                nm = r.get('_name') or f'{tname} {i}'
                holders.setdefault(sk, {}).setdefault(tname, []).append({'row': i, 'name': nm,
                                                                         'index': r.get('index', '')})
    out = []
    for i, r in enumerate(t.rows):
        sid = int(r['id'])
        out.append({'row': i, 'id': sid, 'new': sid >= fe4skills.VANILLA_COUNT, 'name': r['name'],
                    'notes': r.get('_notes', ''), 'inMenu': r.get('_in_menu', '') == 'yes',
                    'bits': {k: r.get(k + '_bit', '') for k in ('personal', 'class', 'item')},
                    'fields': {k: r.get(k, '') for k in fe4skills.FIELDS},
                    'holders': holders.get(r['name'], {}), 'tuning': SKILL_TUNING.get(sid, [])})
    effects = [{'key': k, 'kind': v[0], 'help': v[-1], 'power': v[7]} for k, v in fe4skillfx.EFFECTS.items()]
    return {'skills': out, 'effects': effects,
            'when': [k for k in fe4skillfx.WHEN if k], 'icons': sorted(set(fe4skills.NAMES[1:]) - {None}),
            'iconTiles': skill_icon_tiles(),
            'classes': [r.get('_name', '') for r in (p.table('classes').rows if p.table('classes') else [])]}


def api_skillcheck(b, q):
    """Build the project's current skills table into a copy of the ROM: {ok} or {error}."""
    import tempfile
    import fe4skills
    p = need_project()
    rom = rom_data()
    if rom is None:
        return {'ok': False, 'error': 'Choose your FE4 ROM on the Project page to check skills.'}
    t = p.table('skills')
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, 'skills.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=t.fields)
            w.writeheader()
            w.writerows(t.rows)
        for r in t.rows:                     # pictures of your own for icons
            ic = (r.get('icon') or '').strip()
            if ic.lower().endswith('.png'):
                data = p.blob(f'{fe4skillmenu.ICON_DIR}/{os.path.basename(ic)}').data
                if data:
                    os.makedirs(os.path.join(d, fe4skillmenu.ICON_DIR), exist_ok=True)
                    open(os.path.join(d, fe4skillmenu.ICON_DIR, os.path.basename(ic)), 'wb').write(data)
        try:
            r2 = bytearray(rom)
            fe4skills.apply(r2, d, L.BankSpace(r2), L.FreeSpace())
        except SystemExit as e:
            msg = str(e).replace(os.path.join(d, 'skills.csv'), 'skills.csv')
            return {'ok': False, 'error': msg}
        except Exception as e:          # noqa: BLE001
            return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
    return {'ok': True}


def api_skilledit(b, q):
    """Skill-level edits that touch several rows, as one undo step:
       {op: 'new'} | {op: 'delete', row} | {op: 'rename', row, name} | {op: 'holder', row, table, holder, on}"""
    import fe4skills
    p = need_project()
    t = p.table('skills')
    rows = t.rows
    op = b.get('op')
    ops = []
    if op == 'new':
        nid = max(int(r['id']) for r in rows) + 1
        names = {r['name'] for r in rows}
        n = 1
        while f'New skill {n}' in names:
            n += 1
        row = {f: '' for f in t.fields}
        row.update({'id': str(nid), 'name': f'New skill {n}', 'effect': 'combat', 'bonus': 'atk+3'})
        ops.append(('rows', 'skills', len(rows), [], [row]))
    elif op == 'delete':
        i = int(b['row'])
        if int(rows[i]['id']) < fe4skills.VANILLA_COUNT:
            raise ValueError('FE4\'s own skills can\'t be deleted.')
        name = rows[i]['name']
        new = []
        for r in rows[i + 1:]:
            r2 = dict(r)
            r2['id'] = str(int(r['id']) - 1)      # ids stay 1, 2, 3 ... with no gaps
            new.append(r2)
        ops.append(('rows', 'skills', i, [dict(r) for r in rows[i:]], new))
        ops += _holder_ops(p, name, None)
    elif op == 'rename':
        i = int(b['row'])
        name = str(b['name']).strip()
        old = rows[i]['name']
        if int(rows[i]['id']) < fe4skills.VANILLA_COUNT:
            raise ValueError('Renaming FE4\'s own skills isn\'t supported yet.')
        if not name or len(name) > 15 or not all(32 <= ord(c) < 127 for c in name) or ';' in name or ',' in name:
            raise ValueError('A skill name is 1 to 15 plain letters, numbers or spaces.')
        if name != old and name in {r['name'] for r in rows}:
            raise ValueError('Another skill already has that name.')
        ops.append(('cell', 'skills', i, 'name', old, name))
        ops += _holder_ops(p, old, name)
    elif op == 'holder':
        i = int(b['row'])
        name = rows[i]['name']
        new_skill = int(rows[i]['id']) >= fe4skills.VANILLA_COUNT
        table, holder, on = b['table'], str(b['holder']), bool(b.get('on'))
        if new_skill and table in ('units', 'classes'):     # lists in the skill's own row
            cur = _split(rows[i].get(table))
            nxt = [x for x in cur if x != holder] + ([holder] if on and holder not in cur else [])
            if nxt != cur:
                ops.append(('cell', 'skills', i, table, rows[i].get(table, ''), ';'.join(nxt)))
        elif table in ('units_playable', 'units_npc', 'classes'):
            tb = p.table(table)
            k = int(holder)
            cur = _split(tb.rows[k].get('skills'))
            nxt = [x for x in cur if x != name] + ([name] if on and name not in cur else [])
            if nxt != cur:
                ops.append(('cell', table, k, 'skills', tb.rows[k].get('skills', ''), ';'.join(nxt)))
        else:
            raise ValueError('That can\'t hold a skill here.')
    else:
        raise ValueError('unknown skill edit')
    p.edit(ops)
    return {'ok': True}


def _holder_ops(p, old, new):
    """Rename (or with new=None remove) a skill in every unit, class and item skills column."""
    ops = []
    for tname, field in SKILL_HOLDERS:
        tb = p.table(tname)
        for i, r in enumerate(tb.rows if tb else []):
            cur = _split(r.get(field))
            if old in cur:
                nxt = [new if x == old else x for x in cur if new is not None or x != old]
                ops.append(('cell', tname, i, field, r.get(field, ''), ';'.join(nxt)))
    return ops


# ---------------------------------------------------------------- love and children
def api_gen2check(b, q):
    """Build the project's children, love and inheritance rules into a copy of the ROM: {ok, note} or {error}."""
    import contextlib
    import io as _io
    import tempfile
    import fe4gen2
    p = need_project()
    rom = rom_data()
    if rom is None:
        return {'ok': False, 'error': 'Choose your FE4 ROM on the Project page to check this.'}
    with tempfile.TemporaryDirectory() as d:
        for name in ('units_children', 'units_generic', 'lovers', 'gen2_rules', 'skills'):
            t = p.table(name)
            if t is None:
                continue
            with open(os.path.join(d, name + '.csv'), 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=t.fields)
                w.writeheader()
                w.writerows(t.rows)
        out = _io.StringIO()
        try:
            r2 = bytearray(rom)
            import fe4skills
            with contextlib.redirect_stdout(out):
                if os.path.exists(os.path.join(d, 'skills.csv')):     # skill names, as the build sets them
                    fe4skills.set_maps(fe4skills.read_rows(os.path.join(d, 'skills.csv')))
                import fe4hack
                space = L.BankSpace(r2)
                added = fe4hack._add_units(r2, d, space)       # new children need their unit records
                fe4gen2.apply(r2, d, space, added)
        except SystemExit as e:
            return {'ok': False, 'error': str(e).replace(d + os.sep, '')}
        except Exception as e:          # noqa: BLE001
            return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
    return {'ok': True, 'note': out.getvalue().strip()}


def api_newchild(b, q):
    """Add a new child (units_children row + its name in names.csv) as one undo step:
    {name, gender, class, level, parent, joins, heir?, substitute?, portrait?}  or delete one: {delete: row}."""
    import fe4names
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    kids, gen, names = p.table('units_children'), p.table('units_generic'), p.table('names')
    cnt = L.unit_count(rom)
    if 'delete' in b:
        i = int(b['delete'])
        r = kids.rows[i]
        idx = int(r['index'])
        if idx <= cnt:
            raise ValueError('Only children you added can be deleted.')
        top = max(new_unit_ids() or [0])
        if idx != top:
            raise ValueError('Delete the newest added unit first (new units are numbered without gaps).')
        ops = [('rows', 'units_children', i, [dict(r)], [])]
        nid = r.get('name_id', '')
        for k, nr in enumerate(names.rows):
            if nr['kind'] == 'character' and nr['id'] == nid and nr['name']:
                ops.append(('cell', 'names', k, 'name', nr['name'], ''))
        p.edit(ops)
        return {'ok': True}
    name = str(b.get('name', '')).strip()
    if not name:
        raise ValueError('Give the child a name.')
    try:
        _, w = fe4names.render(name)
    except ValueError as e:
        raise ValueError(str(e))
    if w > fe4names.KINDS['character'][2]:
        raise ValueError(f'"{name}" is too wide for a name ({w} tiles; {fe4names.KINDS["character"][2]} fit).')
    new_ids = new_unit_ids()
    nid_unit = (max(new_ids) + 1) if new_ids else L.first_new_id(rom)
    used = {x.get('name_id') for t in ('units_playable', 'units_children', 'units_npc', 'units_generic')
            for x in (p.table(t).rows if p.table(t) else [])}
    slot = next((nr for nr in names.rows if nr['kind'] == 'character' and 570 <= int(nr['id']) <= 575
                 and not nr['name'] and nr['id'] not in used), None)
    if slot is None:
        raise ValueError('All six free name slots (570-575) are taken by other new units.')
    for f, lo, hi in (('level', 1, 30), ('joins', 6, 11)):
        if not str(b.get(f, '')).isdigit() or not lo <= int(b[f]) <= hi:
            raise ValueError(f'{f.capitalize()} must be {lo} to {hi}.')
    row = {f: '' for f in kids.fields}
    row.update({'index': str(nid_unit), '_name': name, 'class': str(int(b['class'])), 'level': str(int(b['level'])),
                'name_id': slot['id'], 'gender': '1' if str(b.get('gender')) in ('1', 'female') else '0',
                'parent': str(b.get('parent', '')), 'joins': str(int(b['joins'])),
                'heir': b.get('heir') if b.get('heir') in ('father', 'mother') else
                ('mother' if str(b.get('gender')) in ('1', 'female') else 'father'),
                'substitute': str(b.get('substitute', '')), 'portrait': str(b.get('portrait', '')),
                'item1': '255', 'item2': '255'})
    # same weights as the game's own children: the heir parent counts double
    for f, (a, m) in zip(('growth_father', 'growth_mother', 'stats_father', 'stats_mother'),
                         ((100, 50), (50, 100), (20, 10), (10, 20))):
        if f in row:
            row[f] = str(a if row['heir'] == 'father' else m)
    ct = p.table('classes')
    if ct and int(b['class']) < len(ct.rows):
        row['_class_name'] = ct.rows[int(b['class'])].get('_name', '')
    if not row['parent']:
        raise ValueError('A new child needs a parent.')
    k = names.rows.index(slot)
    p.edit([('rows', 'units_children', len(kids.rows), [], [row]), ('cell', 'names', k, 'name', '', name)])
    return {'ok': True, 'row': len(kids.rows) - 1, 'index': nid_unit}


def api_newarmy(b, q):
    """A new enemy (or other) army in a chapter, as one undo step: an armies.csv row past the game's 72 and
    a SET_ARMY ($4B) in the chapter's opening for the next free slot.
    {ch, name: castle name id, like: army id (copied: look, side and AI programs)}"""
    p = need_project()
    ch = int(b.get('ch', -1))
    at = p.table('armies')
    if at is None:
        raise KeyError('This project has no armies.csv.')
    like = str(int(b.get('like', -1)))
    base = next((r for r in at.rows if r.get('army') == like), None)
    if base is None or int(like) >= 72:
        raise ValueError('Choose an army to copy.')
    slots = _chapter_slots(ch)
    slot = next((s for s in range(1, 16) if s not in slots), None)
    if slot is None:
        raise ValueError('This chapter has no free army slot.')
    if slot > 0x0B:
        raise ValueError('This chapter already uses 12 army slots, as many as any chapter of the game.')
    ids = [_num(r['army']) for r in at.rows]
    aid = max(ids) + 1
    if aid > 255:
        raise ValueError('No more armies fit.')
    name = int(b.get('name', base.get('name') or 255))
    row = {k: '' for k in at.fields}
    row.update({'army': str(aid), 'name': str(name), '_name': castle_names()[name] if name < 0x40 else '',
                'unk1': base.get('unk1', '0'), 'unk2': base.get('unk2', '0'), 'members': '', 'castles': '',
                'orders_like': like, '_orders': base.get('_orders', '')})
    ops = [('rows', 'armies', len(at.rows), [], [row])]
    if 'orders_like' not in at.fields:
        at.fields.append('orders_like')
    # the opening's set-up: $4B slot = army, $4D relations between slots (1 = enemies, 2 = allies),
    # $50 slot = set the army up. The new slot copies the relations of the army it works like (whose slot
    # it finds from that army's $4B) and is allied with it.
    name_f = chapter_file(ch)
    f = p.evt(name_f)
    base_slot = next((s_ for s_, a_ in slots.items() if str(a_) == like), None)
    last = {}
    rel = []
    for blk in f.blocks():
        for c in blk['cmds']:
            bb = cmd_bytes(c)
            if bb[:1] == b'\x4B' and len(bb) == 3:
                last[0x4B] = c['line']
            elif bb[:1] == b'\x4D' and len(bb) == 4:
                last[0x4D] = c['line']
                rel.append(bb)
            elif bb[:1] == b'\x50' and len(bb) == 6:
                last[0x50] = c['line']
        if last:
            break
    if 0x4B not in last:
        raise ValueError('This chapter\'s opening sets up no armies, so the editor can\'t add one.')
    adds = {0x4B: ['4B %02X %02X' % (slot, aid)]}
    new_rel = []
    if base_slot is not None:
        for bb in rel:
            r, x, y = bb[1], bb[2], bb[3]
            if x == base_slot and y != slot:
                new_rel.append((r, slot, y))
            elif y == base_slot and x != slot:
                new_rel.append((r, x, slot))
        new_rel.append((2, slot, base_slot))
    else:
        new_rel.append((1, slot, 0))
    adds[0x4D] = ['4D %02X %02X %02X' % t for t in new_rel]
    adds[0x50] = ['50 %02X 00 00 00 00' % slot]
    for op in sorted(adds, key=lambda o: -last.get(o, last[0x4B])):
        at_line = last.get(op, last[0x4B]) + 1
        ops.append(('lines', name_f, at_line, [], _plus(name_f, adds[op])))
    p.edit(ops)
    return {'ok': True, 'army': aid, 'slot': slot}


# ---------------------------------------------------------------- opening scene (1.2)
# The scene a chapter's opening runs ($30 RUN_SCENE in its init block), as simple steps:
#   music     0E nn, FD                               (the scene's song)
#   camera    3A x y, 3B 80, 34 02 00, FD            (the first: 3A = the view's top-left cell, set before the
#             40 x y 04, FD                           map fades in with SC_46 04; later ones scroll there, SC_40)
#   units     4A 4E nn                                (a deploy list comes onto the map)
#   talk      0C msg, FD, 34 14 00, FD               (portraits over the map, as the game's map scenes do)
#   wait      34 nn nn, FD                            (frames)
#   fade      12 E0 00, 34 23 00, FD                  (music fades out)
# Anything else is a game step, kept as it is unless taken out.
JUMP_OPS = {0x02, 0x03, 0x04, 0x05, 0x06}


def _opening_scene(ch):
    name = chapter_file(ch)
    for blk in need_project().evt(name).blocks():
        if blk['label'] == 'init':
            for c in blk['cmds']:
                bb = cmd_bytes(c)
                if len(bb) == 4 and bb[0] == 0x30:
                    return bb[2] | bb[3] << 8
    return None


def _opening_steps(sid):
    blk = story_index()['scenes'][sid]['block']
    d = need_project().dialogue()
    cmds = blk['cmds']
    out, i, complex_ = [], 0, False

    def hx(k):
        return cmds[k]['hex'] if k < len(cmds) else ''
    while i < len(cmds):
        c = cmds[i]
        h_ = c['hex']
        bb = cmd_bytes(c)
        if h_ == 'FD':
            i += 1
            continue
        if bb[:2] == b'\xff\xff':
            break
        if bb[0] == 0x4A and bb[1:2] != b'\x4e' and all(x['kind'] == 'setup' for x in out):
            out.append({'kind': 'setup', 'hex': h_, 'what': c.get('comment', '')})   # the map's set-up: always kept
        elif bb[0] == 0x0E and len(bb) == 2:
            out.append({'kind': 'music', 'song': bb[1]})
        elif bb[0] == 0x3A and len(bb) == 3:
            out.append({'kind': 'camera', 'x': bb[1] + 8, 'y': bb[2] + 7})
            while hx(i + 1) in ('3B 80', '34 02 00', 'FD'):
                i += 1
        elif bb[0] == 0x40 and len(bb) == 4:
            out.append({'kind': 'camera', 'x': bb[1] + 8, 'y': bb[2] + 7})
        elif bb[:2] == b'\x4a\x4e' and len(bb) == 3:
            out.append({'kind': 'units', 'list': bb[2]})
        elif h_.startswith('0C @'):
            key = h_.split('@', 1)[1].split()[0]
            out.append({'kind': 'talk', 'key': key, 'text': (d.text.get(key, '') if d else '')})
        elif bb[0] == 0x34 and len(bb) == 3 and h_ != '34 23 00':
            out.append({'kind': 'wait', 'frames': bb[1] | bb[2] << 8})
        elif h_ == '12 E0 00':
            out.append({'kind': 'fade'})
            while hx(i + 1) in ('34 23 00', 'FD'):
                i += 1
        else:
            if bb[0] in JUMP_OPS or '@L' in h_:
                complex_ = True
            out.append({'kind': 'game', 'hex': h_, 'what': c.get('comment', '')})
        i += 1
    return out, complex_


def _talk_text(st):
    """{a, b, lines: [{who: 'a'|'b', text}]} -> a message with the two portraits."""
    a = int(st.get('a', 0xFFFF))
    b2 = st.get('b')
    b2 = int(b2) if b2 not in (None, '', 0xFFFF, '65535') else None
    lines = [ln for ln in st.get('lines') or [] if str(ln.get('text', '')).strip()]
    if not lines:
        lines = [{'who': 'a', 'text': 'Write what is said here.'}]
    head = '{06}{00 3D}%s' % portrait_code(a)
    if b2 is not None:
        head += '{07}{00 3D}%s' % portrait_code(b2)
    out, prev = head, None
    merged = []
    for ln in lines:                               # one window per run of lines by the same person
        who = 'b' if ln.get('who') == 'b' and b2 is not None else 'a'
        if merged and merged[-1][0] == who:
            merged[-1][1].append(str(ln['text']))
        else:
            merged.append((who, [str(ln['text'])]))
    for k, (who, texts) in enumerate(merged):
        out += ('{06}' if who == 'a' else '{07}') + ('{09}' if k == 0 else '{00 1D 10}')
        out += '{08}'.join(wrap_words(t, '...') for t in texts)
    return out + '{08}{01}'


def api_opening(b, q):
    """GET ?ch: the chapter's opening scene as steps.  POST {ch, steps, mode: 'replace'|'after'}: write them
    (replace: the scene becomes the steps; after: the steps play once the game's opening is done).  One undo step."""
    p = need_project()
    ch = int((q.get('ch', ['0'])[0]) if not b else b.get('ch', 0))
    sid = _opening_scene(ch)
    if sid is None:
        raise ValueError('This chapter\'s opening runs no scene the editor can change.')
    if not b:
        steps, complex_ = _opening_steps(sid)
        lists = [{'list': k, 'when': v.get('when', '')} for k, v in sorted(chapter_lists(ch).items())]
        return {'ch': ch, 'scene': sid, 'steps': steps, 'complex': complex_, 'lists': lists,
                'songs': [[n, fe4music.NAMED.get(n, '')] for n in range(1, fe4music.SONGS + 1)]}
    mode = b.get('mode', 'replace')
    ops = {'list': []}
    cmds = []
    for st in b.get('steps') or []:
        k = st.get('kind')
        if k == 'music':
            n = int(st['song'])
            if not 1 <= n <= fe4music.SONGS:
                raise ValueError('Choose a song.')
            cmds += ['0E %02X' % n, 'FD']
        elif k == 'camera':
            x, y = min(63, max(0, int(st['x']) - 8)), min(63, max(0, int(st['y']) - 7))
            if not any(c.startswith(('3A ', '40 ')) for c in cmds):     # the first: placed before the map fades in
                cmds += ['3A %02X %02X' % (x, y), '3B 80', '34 02 00', 'FD']
            else:                                                          # later ones scroll there (SC_40, speed 4)
                cmds += ['40 %02X %02X 04' % (x, y), 'FD']
        elif k == 'units':
            cmds += ['4A 4E %02X' % int(st['list'])]
        elif k == 'talk':
            key = st.get('key')
            if not key or st.get('lines'):
                key = new_message_op(_talk_text(st), f'{chapter_file(ch)[:4]} opening', ops)
            cmds += ['0C @' + key, 'FD', '34 14 00', 'FD']
        elif k == 'wait':
            n = max(1, min(600, int(st.get('frames', 60))))
            cmds += ['34 %02X %02X' % (n & 0xFF, n >> 8), 'FD']
        elif k == 'fade':
            cmds += ['12 E0 00', '34 23 00', 'FD']
        elif k == 'setup':
            h_ = ' '.join(str(st['hex']).split()).upper()
            if not re.fullmatch(r'4A( [0-9A-F]{2})+', h_):
                raise ValueError('A set-up step has bad bytes.')
            cmds += [h_]
        elif k == 'game':
            h_ = ' '.join(str(st['hex']).split()).upper()
            if not re.fullmatch(r'[0-9A-F]{2}( [0-9A-F]{2})*|[0-9A-F]{2}( [0-9A-F]{2})* @[A-Z0-9]+', h_) and '@' not in h_:
                raise ValueError('A game step has bad bytes.')
            if int(h_.split()[0], 16) in JUMP_OPS or '@L' in h_:
                raise ValueError('This opening jumps around inside itself; the editor can only replace it as a whole '
                                 '(take out the game\'s steps) or play your steps before it.')
            cmds += [h_]
        else:
            raise ValueError('Unknown step.')
    if not cmds:
        raise ValueError('Add at least one step.')
    if mode == 'after':
        # after the game's own opening, before its END: the map is up and running there (verified: a
        # conversation over the map with the camera scrolled to it, on the Prologue)
        cmds = [('40 %s 04' % c[3:]) if c.startswith('3A ') else c for c in cmds]
        cmds = [c for c in cmds if c not in ('3B 80', '34 02 00')]
        blk = story_index()['scenes'][sid]['block']
        endc = next((c for c in reversed(blk['cmds']) if cmd_bytes(c)[:2] == b'\xff\xff'), None)
        if endc is None:
            raise ValueError('The game\'s opening for this chapter has no end the editor can find.')
        ops['list'].append(('lines', 'scenes.evt', endc['line'], [], _plus('scenes.evt', cmds)))
    else:
        # the map starts dark: SC_46 04 brings it in (the openings do it after placing the camera), and
        # SC_2A waits for it before anything else happens
        if not any(c.split()[0] == '46' for c in cmds):
            lead = 0
            while lead < len(cmds) and cmds[lead].startswith('4A ') and not cmds[lead].startswith('4A 4E'):
                lead += 1
            at = next((i + 4 for i, c in enumerate(cmds) if c.startswith('3A ')), lead)
            cmds[at:at] = ['46 04', '2A', 'FD', '34 19 00', 'FD']
        blk = story_index()['scenes'][sid]['block']
        f = p.evt('scenes.evt')
        first = blk['cmds'][0]['line']
        end = first
        while end + 1 < len(f.lines) and not f.lines[end + 1].startswith('=='):
            end += 1
        while end > first and not f.lines[end].strip():
            end -= 1
        old = f.lines[first:end + 1]
        cmds += ['FF FF']
        lead = '%s: %-24s ; %s' % (blk['cmds'][0]['addr'], cmds[0], _comment('scenes.evt', cmds[0]))
        ops['list'].append(('lines', 'scenes.evt', first, old, [lead] + _plus('scenes.evt', cmds[1:])))
    p.edit(ops['list'])
    return {'ok': True, 'scene': sid}


# ---------------------------------------------------------------- a character arrives (1.3)
# How the game brings people in (traced on the Prologue, verified with Finn and Dew in lsrun):
#   join your army:   4A 49 uu uu          load unit uu into your army (off the map)
#                     24 uu uu 00 sx sy dx dy 04 02 00   walk it from (sx, sy) to (dx, dy) (same cell = appear)
#                     29, 2A, FD           wait for the walk
#                     4A 68 uu cc          its home castle = location cc (unit byte; Azel/Lex: 1)
#   another army:     23 ll ee ee sx sy 04 04   walk deploy list ll's entry ee (1-based) from (sx, sy) to
#                                          its deploy cell (only a picture; Prologue scene 1 does this)
#                     29, 2A, FD, 4A 4E ll  then the list comes onto the map for real
def arrival_cmds(ch, b, ops, rows):
    """Scene commands for {unit, side: 'join'|'army', slot, orders, x, y, entrance: 'walk'|'appear', fx, fy,
    talk?}.  Adds a deploy row to rows for 'army'."""
    uid = int(b['unit'])
    units = unit_lookup()
    if uid not in units:
        raise ValueError('Choose who arrives.')
    x, y = int(b['x']), int(b['y'])
    ax, ay, aw, ah = map_area(ch)
    if not (ax <= x < ax + aw and ay <= y < ay + ah):
        raise ValueError('Pick a spot on the map.')
    walk = b.get('entrance', 'walk') == 'walk'
    fx, fy = (int(b.get('fx', x)), int(b.get('fy', y))) if walk else (x, y)
    if not (0 <= fx < 64 and 0 <= fy < 64):
        raise ValueError('Pick where they walk in from.')
    cx, cy = min(63, max(0, x - 8)), min(63, max(0, y - 7))
    cmds = ['40 %02X %02X 04' % (cx, cy), 'FD', '34 14 00', 'FD']
    if b.get('side', 'join') == 'join':
        if units[uid][0] == 'units_generic':
            raise ValueError('Only named characters can join your army (soldiers can\'t).')
        cmds += ['4A 49 ' + _w(uid), '24 %s 00 %02X %02X %02X %02X 04 02 00' % (_w(uid), fx, fy, x, y),
                 '29', '2A', 'FD']
        home = _home_castle(ch)
        if uid < 256 and home is not None:
            cmds += ['4A 68 %02X %02X' % (uid, home)]
    else:
        slot = int(b.get('slot', 1))
        if slot == 0:
            raise ValueError('For your army choose "Joins your army".')
        if slot not in army_names(ch):
            raise ValueError('That army isn\'t in this chapter.')
        lst = free_list()
        if lst in ops.get('_lists', ()):
            lst = max(ops['_lists']) + 1
        ops.setdefault('_lists', []).append(lst)
        rows.append({'index': f'{lst}.0', '_name': unit_label(uid), 'char_id': str(uid), 'x': str(x), 'y': str(y),
                     'leader_flag': '1' if b.get('leader') else '0', 'orders': str(int(b.get('orders') or 0)),
                     'army_slot': str(slot), 'slot': '0'})
        if walk and (fx, fy) != (x, y):
            cmds += ['23 %02X 01 00 %02X %02X 04 04' % (lst, fx, fy), '29', '2A', 'FD']
        cmds += ['4A 4E %02X' % lst, '34 0A 00', 'FD']
    t = b.get('talk')
    if t and any(str(ln.get('text', '')).strip() for ln in t.get('lines') or []):
        key = new_message_op(_talk_text(t), f'{chapter_file(ch)[:4]} arrival', ops)
        cmds += ['0C @' + key, 'FD', '34 14 00', 'FD']
    return cmds


def _home_castle(ch):
    """Your army's first castle in this chapter (location number), or None when it holds none."""
    at = need_project().table('armies')
    army = _chapter_slots(ch).get(0)
    row = next((r for r in (at.rows if at else []) if r.get('army') == str(army)), None)
    if row is None:
        return None
    cs = [c for c in (row.get('castles') or '').split(';') if c.strip().isdigit()]
    return int(cs[0]) if cs else None


def trigger_scene_ops(ch, when, cmds, ops):
    """Run cmds when {kind: 'opening'} (at the end of the chapter's opening), {kind: 'turn', turn},
    {kind: 'area', unit, x1, y1, x2, y2} or {kind: 'seize', loc, by (army slot, 0 = you)}.
    Returns words for when."""
    name = chapter_file(ch)
    kind = when.get('kind')
    if kind == 'opening':
        sid = _opening_scene(ch)
        if sid is None:
            raise ValueError('This chapter\'s opening runs no scene the editor can add to.')
        blk = story_index()['scenes'][sid]['block']
        endc = next((c for c in reversed(blk['cmds']) if cmd_bytes(c)[:2] == b'\xff\xff'), None)
        if endc is None:
            raise ValueError('The opening has no end the editor can find.')
        ops['list'].append(('lines', 'scenes.evt', endc['line'], [], _plus('scenes.evt', cmds)))
        return 'At the end of the chapter\'s opening'
    if kind == 'turn':
        turn = int(when['turn'])
        if not 2 <= turn <= 99:
            raise ValueError('Choose turn 2 to 99 (for turn 1, use the opening).')
        sid = turn_scene(name, turn)
        if sid is not None:
            add_cmds_to_scene(sid, cmds, ops)
            return f'At the start of turn {turn}'
        cond = turn_cond(name, turn)
    elif kind == 'area':
        unit = int(when.get('unit', 0xFFFF))
        x1, y1, x2, y2 = (int(when[k]) for k in ('x1', 'y1', 'x2', 'y2'))
        if not all(0 <= v < 64 for v in (x1, y1, x2, y2)):
            raise ValueError('Corners are 0 to 63.')
        cond = _hx('0B', '%02X' % free_flag(name), _w(unit),
                   '%02X %02X %02X %02X' % (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), 'FF')
    elif kind == 'seize':
        loc, by = int(when['loc']), int(when.get('by', 0))
        cond = _hx('02', '%02X' % free_flag(name), _w(by), _w(loc))
    else:
        raise ValueError('Choose when they arrive.')
    sid = new_scene_ops(cmds + ['FF FF'], ops)
    first_trigger_ops(name, [cond, '30 FF ' + _w(sid)], ops)
    return cond_words(bytes(int(v, 16) for v in cond.split()), ch)


def api_arrival(b, q):
    """A character arrives on the map, as one undo step: {ch, unit, side, slot?, orders?, x, y, entrance, fx?, fy?,
    when, talk?}.  side 'join' = into your army at once (as Azel and Lex do), 'army' = into another army of
    the chapter (enemy or neutral; recruit them by talking)."""
    p = need_project()
    ch = int(b['ch'])
    dt = p.table('deploy')
    old = [dict(r) for r in dt.rows]
    rows = [dict(r) for r in dt.rows]
    ops = {'list': []}
    cmds = arrival_cmds(ch, b, ops, rows)
    words = trigger_scene_ops(ch, b.get('when') or {}, cmds, ops)
    if len(rows) != len(old):
        rows = _renumber(rows)
        ops['list'].insert(0, ('rows', 'deploy', 0, old, rows))
    p.edit(ops['list'])
    return {'ok': True, 'when': words, 'lists': ops.get('_lists', [])}


def api_newchar(b, q):
    """Add a new first-generation character as one undo step: a units_playable row (a copy of the character
    whose place it takes: the game keeps 24 character places, and every one is used) and its name.
    {name, takes: unit id, class?, level?, portrait?, start?: true = in Sigurd's army from the Prologue}
    or delete the newest one: {delete: row}."""
    import fe4names
    p = need_project()
    rom = rom_data()
    if rom is None:
        raise ValueError('Choose your FE4 ROM on the Project page first.')
    up, names, at = p.table('units_playable'), p.table('names'), p.table('armies')
    cnt = L.unit_count(rom)
    if 'delete' in b:
        i = int(b['delete'])
        r = up.rows[i]
        idx = int(r['index'])
        if idx <= cnt:
            raise ValueError('Only characters you added can be deleted.')
        if idx != max(new_unit_ids() or [0]):
            raise ValueError('Delete the newest added unit first (new units are numbered without gaps).')
        ops = [('rows', 'units_playable', i, [dict(r)], [])]
        nid = r.get('name_id', '')
        for k, nr in enumerate(names.rows):
            if nr['kind'] == 'character' and nr['id'] == nid and nr['name']:
                ops.append(('cell', 'names', k, 'name', nr['name'], ''))
        for k, ar in enumerate(at.rows if at else []):
            mem = [m for m in (ar.get('members') or '').split(';') if m.strip()]
            if str(idx) in mem:
                ops.append(('cell', 'armies', k, 'members', ar['members'], ';'.join(m for m in mem if m != str(idx))))
        p.edit(ops)
        return {'ok': True}
    name = str(b.get('name', '')).strip()
    if not name:
        raise ValueError('Give the character a name.')
    try:
        _, w = fe4names.render(name)
    except ValueError as e:
        raise ValueError(str(e))
    if w > fe4names.KINDS['character'][2]:
        raise ValueError(f'"{name}" is too wide for a name ({w} tiles; {fe4names.KINDS["character"][2]} fit).')
    takes = str(int(b.get('takes', 0)))
    base = next((r for r in up.rows if r['index'] == takes), None)
    if base is None or int(takes) > cnt:
        raise ValueError('Choose whose place the new character takes.')
    new_ids = new_unit_ids()
    uid = (max(new_ids) + 1) if new_ids else L.first_new_id(rom)
    used = {x.get('name_id') for t in ('units_playable', 'units_children', 'units_npc', 'units_generic')
            for x in (p.table(t).rows if p.table(t) else [])}
    slot = next((nr for nr in names.rows if nr['kind'] == 'character' and 570 <= int(nr['id']) <= 575
                 and not nr['name'] and nr['id'] not in used), None)
    if slot is None:
        raise ValueError('All six free name slots (570-575) are taken by other new units.')
    row = dict(base)
    row.update({'index': str(uid), '_name': name, 'char_id': str(uid), 'name_id': slot['id']})
    if b.get('class') not in (None, ''):
        row['class'] = str(int(b['class']))
        ct = p.table('classes')
        if ct and int(b['class']) < len(ct.rows) and '_class_name' in row:
            row['_class_name'] = ct.rows[int(b['class'])].get('_name', '')
    if b.get('level') not in (None, ''):
        if not 1 <= int(b['level']) <= 30:
            raise ValueError('Level must be 1 to 30.')
        row['level'] = str(int(b['level']))
    if b.get('portrait') not in (None, ''):
        row['portrait'] = str(int(b['portrait']))
    if b.get('gender') not in (None, '') and 'gender' in row:
        row['gender'] = '1' if str(b['gender']) in ('1', 'female') else '0'
    ops = [('rows', 'units_playable', len(up.rows), [], [row]), ('cell', 'names', names.rows.index(slot), 'name', '', name)]
    if b.get('start') and at is not None:
        k = next((i for i, r in enumerate(at.rows) if r.get('army') == '0'), None)
        if k is not None:
            mem = [m for m in (at.rows[k].get('members') or '').split(';') if m.strip()]
            if takes in mem:
                mem[mem.index(takes)] = str(uid)
            else:
                mem.append(str(uid))
            ops.append(('cell', 'armies', k, 'members', at.rows[k].get('members') or '', ';'.join(mem)))
        dt = p.table('deploy')                 # and where they are placed in your army
        for k, r in enumerate(dt.rows if dt else []):
            if r.get('char_id') == takes and r.get('army_slot') == '0':
                ops.append(('cell', 'deploy', k, 'char_id', takes, str(uid)))
                if '_name' in r:
                    ops.append(('cell', 'deploy', k, '_name', r['_name'], name))
    p.edit(ops)
    return {'ok': True, 'row': len(up.rows) - 1, 'index': uid}


API = {('GET', 'session'): api_session, ('POST', 'ping'): api_ping, ('GET', 'table'): api_table,
       ('POST', 'tables'): api_tables, ('POST', 'set'): api_set, ('POST', 'undo'): api_undo,
       ('GET', 'chaptitle'): api_chaptitle, ('POST', 'sites'): api_sites, ('POST', 'newchar'): api_newchar, ('POST', 'newarmy'): api_newarmy, ('POST', 'arrival'): api_arrival, ('GET', 'opening'): api_opening, ('POST', 'opening'): api_opening, ('POST', 'chaptitle'): api_chaptitle_set,
       ('POST', 'redo'): api_redo, ('POST', 'save'): api_save, ('POST', 'open'): api_open,
       ('POST', 'rom'): api_set_rom, ('POST', 'new'): api_new_project, ('GET', 'job'): api_job,
       ('POST', 'build'): api_build, ('GET', 'battleanims'): api_battleanims, ('GET', 'battleinfo'): api_battleinfo,
       ('POST', 'battleimport'): api_battleimport, ('POST', 'battlemotion'): api_battlemotion,
       ('POST', 'battleframe'): api_battleframe, ('GET', 'battlemotions'): api_battlemotions,
       ('GET', 'battlespells'): api_battlespells, ('POST', 'spellrow'): api_spellrow, ('GET', 'skillanims'): api_skillanims, ('POST', 'skillanimset'): api_skillanimset, ('GET', 'spellgfx'): api_spellgfx, ('POST', 'spellgfxset'): api_spellgfxset, ('POST', 'spellcolours'): api_spellcolours, ('POST', 'spelleffect'): api_spelleffect, ('POST', 'spellsteps'): api_spellsteps, ('POST', 'spellpreview'): api_spellpreview, ('POST', 'skillpreview'): api_skillpreview, ('POST', 'battlereset'): api_battlereset,
       ('POST', 'ipspatch'): api_ipspatch, ('POST', 'reveal'): api_reveal,
       ('GET', 'patchinfo'): api_patchinfo, ('POST', 'testplay'): api_testplay, ('POST', 'settings'): api_settings,
       ('POST', 'dialog'): api_dialog, ('POST', 'quit'): api_quit, ('POST', 'classic'): api_classic,
       ('POST', 'setmany'): api_setmany, ('GET', 'people'): api_people, ('GET', 'textinfo'): api_textinfo, ('GET', 'events'): api_events,
       ('GET', 'chapters'): api_chapters, ('GET', 'scene'): api_scene, ('POST', 'messages'): api_messages,
       ('POST', 'msg'): api_msg, ('POST', 'evtcmd'): api_evtcmd, ('GET', 'dsearch'): api_dsearch, ('GET', 'villages'): api_villages, ('GET', 'itemuse'): api_itemuse, ('POST', 'newevent'): api_newevent, ('POST', 'talkmenu'): api_talkmenu, ('POST', 'delstep'): api_delstep,
       ('POST', 'addstep'): api_addstep, ('GET', 'eventinfo'): api_eventinfo, ('GET', 'maps'): api_maps, ('GET', 'map'): api_map, ('POST', 'paint'): api_paint,
       ('GET', 'armies'): api_armies, ('GET', 'portraits'): api_portraits, ('GET', 'mapsprites'): api_mapsprites, ('GET', 'skills'): api_skills, ('POST', 'gen2check'): api_gen2check, ('POST', 'newchild'): api_newchild, ('GET', 'mapinfo'): api_mapinfo, ('GET', 'unitshare'): api_unitshare, ('POST', 'mapunit'): api_mapunit, ('POST', 'testchapter'): api_testchapter, ('GET', 'wincond'): api_wincond, ('POST', 'wincond'): api_wincond, ('POST', 'skillcheck'): api_skillcheck, ('POST', 'skilledit'): api_skilledit, ('POST', 'spriteentry'): api_spriteentry, ('GET', 'tileinfo'): api_tileinfo, ('POST', 'tiledraw'): api_tiledraw, ('POST', 'mapsprite'): api_mapsprite, ('POST', 'mapwalk'): api_mapwalk, ('GET', 'mapbattle'): api_mapbattle, ('GET', 'mbplayer'): api_mbplayer, ('GET', 'mapspells'): api_mapspells, ('POST', 'mapspellset'): api_mapspellset, ('POST', 'mapspellsheet'): api_mapspellsheet, ('POST', 'mapspellbg'): api_mapspellbg, ('POST', 'mapspellcolour'): api_mapspellcolour, ('POST', 'mapspellpreview'): api_mapspellpreview, ('POST', 'mapbattleset'): api_mapbattleset, ('POST', 'mapbattlesheet'): api_mapbattlesheet, ('POST', 'mapbattlepreview'): api_mapbattlepreview, ('POST', 'portrait'): api_portrait, ('POST', 'aicmd'): api_aicmd, ('POST', 'airecipe'): api_airecipe, ('GET', 'music'): api_music, ('POST', 'musicfile'): api_musicfile,
       ('GET', 'title'): api_title, ('POST', 'titleset'): api_title_set,
       ('POST', 'skillicon'): api_skillicon,
       ('GET', 'tileset'): api_tileset, ('POST', 'tilesetset'): api_tileset_set, ('POST', 'mapsize'): api_mapsize}


# ---------------------------------------------------------------- window
def find_browser():
    """Edge or Chrome/Chromium, to open the editor as an app window."""
    cands = []
    if sys.platform.startswith('win'):
        for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
            if base:
                cands += [os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                          os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    elif sys.platform == 'darwin':
        cands += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
    else:
        for n in ('chromium', 'chromium-browser', 'google-chrome', 'microsoft-edge'):
            p = shutil.which(n)
            if p:
                cands.append(p)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def open_window(url):
    b = None if os.environ.get('FE4STUDIO_NOWINDOW') else find_browser()
    if b:
        prof = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'fe4kit', 'studio-window')
        os.makedirs(prof, exist_ok=True)
        try:
            return subprocess.Popen([b, f'--app={url}', f'--user-data-dir={prof}', '--window-size=1400,900',
                                     '--no-first-run', '--no-default-browser-check'])
        except OSError:
            pass
    if not os.environ.get('FE4STUDIO_NOWINDOW'):
        import webbrowser
        webbrowser.open(url)
    return None


def main_loop(win, httpd):
    """Main thread: file dialogs for the page, and quitting when the window is gone."""
    tk = None
    try:
        import tkinter
        from tkinter import filedialog
        tk = tkinter.Tk()
        tk.withdraw()
    except Exception:              # noqa: BLE001
        filedialog = None
    started = time.time()
    while True:
        try:
            kind, b, reply = dialogs.get(timeout=0.5)
        except queue.Empty:
            # quit once the window is gone: our browser process ended (or there is none) and the page
            # stopped checking in (a browser that was already open takes over the window and ends ours)
            gone = win is None or win.poll() is not None
            lp = state['last_ping'] or started
            if gone and time.time() - lp > (45 if state['last_ping'] else 90):
                break
            if tk:
                tk.update()
            continue
        path = ''
        if filedialog:
            tk.lift()
            tk.attributes('-topmost', True)
            if kind == 'rom':
                path = filedialog.askopenfilename(parent=tk, title=b.get('title') or 'Your FE4 ROM',
                                                  filetypes=[('SNES ROM', '*.smc *.sfc'), ('All files', '*.*')])
            elif kind == 'folder':
                path = filedialog.askdirectory(parent=tk, title=b.get('title') or 'Choose a folder')
            elif kind == 'save':
                path = filedialog.asksaveasfilename(parent=tk, title=b.get('title') or 'Save as',
                                                    defaultextension=b.get('ext') or '.smc', initialfile=b.get('initial') or '',
                                                    filetypes=[('IPS patch', '*.ips')] if b.get('ext') == '.ips'
                                                    else [('SNES ROM', '*.smc *.sfc')])
            elif kind == 'exe':
                path = filedialog.askopenfilename(parent=tk, title=b.get('title') or 'Where is FE4.exe?',
                                                  filetypes=[('FE4 PC port', 'FE4.exe fe4'), ('All files', '*.*')])
            tk.attributes('-topmost', False)
        reply.put(path or '')
    httpd.shutdown()


def main():
    port = int(os.environ.get('FE4STUDIO_PORT', '0'))
    httpd = Server(('127.0.0.1', port), Handler)
    port = httpd.server_address[1]
    url = f'http://127.0.0.1:{port}/#{TOKEN}'
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f'{APP} running at {url}', flush=True)
    if os.environ.get('FE4STUDIO_URLFILE'):
        with open(os.environ['FE4STUDIO_URLFILE'], 'w') as f:
            f.write(url)
    win = open_window(url)
    main_loop(win, httpd)


if __name__ == '__main__':
    main()
