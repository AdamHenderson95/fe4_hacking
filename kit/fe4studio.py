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
import fe4sprites                  # noqa: E402
import fe4maptiles                 # noqa: E402
import fe4battle                  # noqa: E402
import fe4spellfx                  # noqa: E402
from fe4project import Project, load_settings, save_settings   # noqa: E402

APP = 'Builder of the Holy War'
VERSION = '36'
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
          'item_instances', 'skills', 'names', 'lovers', 'gen2_rules', 'deploy', 'locations', 'arena', 'armies', 'talks', 'map_sprites', 'map_terrain', 'battle_anims', 'spells'}


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
        n = fe4battle.spell_count(rom_data())
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


class Handler(BaseHTTPRequestHandler):
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
                data = spell_sheet(n, scale) if 'spellsheet' in path else spell_preview(n, scale)
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
            'port': port_exe(), 'hoverStats': bool(settings.get('hover_stats', False)),
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
    return job_json_of(run_job(f'Building {os.path.basename(out)}', lambda: (fe4hack.build(rom, p.path, out, ips, hover), out)[1]))


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
        threading.Thread(target=fe4spellfx.survey, args=(rom0,), daemon=True).start()
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
    rom = rom_data()
    it = p.table('items')
    items = {int(r['index']): r.get('_name', '') for r in it.rows} if it else {}
    names = fe4battle.spell_names(rom, items)
    n = fe4battle.spell_count(rom)
    return {'rows': [{**r, '_item': items.get(int(r['item']), r.get('_item', ''))} for r in t.rows],
            'spells': [[k, names.get(k, '')] for k in range(n)], 'items': [[k, v] for k, v in sorted(items.items()) if v]}


def _spell_pictures():
    """The survey of spell pictures (clean ROM) and the project's redrawn tile bytes per record."""
    rom = rom_data()
    recs, by_spell = fe4spellfx.survey(rom)
    over = {}
    if project():
        for r, d in recs.items():
            png = _project_reader(f'{fe4spellfx.FOLDER}/r{r:03d}.png')
            if png and d['kind'] != 'map':
                try:
                    over[r] = fe4spellfx.sheet_from_png(png, len(d['data']), fe4spellfx.bpp_of(d['kind']))
                except ValueError:
                    pass
    return rom, recs, by_spell, over


SPELL_KINDS = {'tiles4': 'Background tiles · 16 colours', 'tiles2': 'Overlay tiles · 4 colours',
               'sprite': 'Sprite tiles · 16 colours'}


def _spell_label(rom, items=None):
    p = project()
    it = p.table('items') if p else None
    items = {int(r['index']): r.get('_name', '') for r in it.rows} if it else dict(enumerate(L.item_names(rom)))
    return fe4battle.spell_names(rom, items)


def api_spellgfx(b, q):
    """Spells with pictures ({list: true}), or one spell's pictures ({spell})."""
    rom, recs, by_spell, over = _spell_pictures()
    names = _spell_label(rom)
    if 'spell' not in q:
        out = []
        for s, rs in by_spell.items():
            pics = [r for r in rs if recs[r]['kind'] != 'map']
            if pics:
                out.append({'spell': s, 'name': names.get(s, ''), 'pictures': len(pics),
                            'edited': sum(r in over for r in pics)})
        return {'spells': out}
    s = int(q['spell'][0])
    pics = []
    for r in by_spell.get(s, []):
        d = recs[r]
        if d['kind'] == 'map':
            continue
        bpp = fe4spellfx.bpp_of(d['kind'])
        w, hh = fe4spellfx.sheet_size(len(d['data']), bpp)
        pics.append({'record': r, 'kind': d['kind'], 'label': SPELL_KINDS[d['kind']], 'w': w, 'h': hh,
                     'tiles': len(d['data']) // (8 * bpp), 'edited': r in over,
                     'shared': [names.get(x, f'Effect {x}') or f'Effect {x}' for x in d['spells'] if x != s]})
    return {'spell': s, 'name': names.get(s, ''), 'pictures': pics,
            'preview': any(recs[r]['kind'] == 'map' for r in by_spell.get(s, []))}


def api_spellgfxset(b, q):
    """Import a picture for a spell record ({record, png base64}) or go back to the game's ({record, png: null})."""
    p = need_project()
    rom, recs, _, _ = _spell_pictures()
    r = int(b['record'])
    if r not in recs or recs[r]['kind'] == 'map':
        raise ValueError('That isn\'t a spell picture.')
    rel = f'{fe4spellfx.FOLDER}/r{r:03d}.png'
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


def spell_sheet(r, scale):
    rom, recs, _, over = _spell_pictures()
    if r not in recs or recs[r]['kind'] == 'map':
        return None
    d = recs[r]
    return fe4spellfx.sheet_png(over.get(r, d['data']), fe4spellfx.bpp_of(d['kind']), scale)


def spell_preview(s, scale):
    rom, recs, _, over = _spell_pictures()
    return fe4spellfx.preview_png(rom, s, over, scale)


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

    def go():
        fe4hack.build(rom, p.path, out, None, hover)
        subprocess.Popen([exe, '--play', out], cwd=os.path.dirname(exe))
        print('started the PC port')
        return out
    return job_json_of(run_job('Building for test play', go))


def api_settings(b, q):
    if 'hoverStats' in b:
        settings['hover_stats'] = bool(b['hoverStats'])
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
    p = os.path.join(evdir, 'scenes.evt')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8', errors='replace'):
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
            for line in open(os.path.join(evdir, f), encoding='utf-8', errors='replace'):
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
        out.append({'ch': ch, 'file': f, 'title': CHAPTER_TITLES[ch] if ch < len(CHAPTER_TITLES) else f})
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
        L_['units'].append({'_row': i, 'entry': ent, 'char_id': cid, 'name': (ur or {}).get('_name') or r.get('_name') or f'Unit {cid}',
                            'table': t, 'class': cls, 'level': lvl, 'portrait': portrait, 'x': r.get('x'), 'y': r.get('y'),
                            'army_slot': r.get('army_slot'), 'army': armies.get(str(r.get('army_slot')), ''),
                            'leader': r.get('leader_flag') not in ('', '0', None), 'orders': r.get('orders')})
    return {'ch': ch, 'title': CHAPTER_TITLES[ch] if ch < len(CHAPTER_TITLES) else '', 'width': m.WIDTH,
            'height': (len(m.words) + m.WIDTH - 1) // m.WIDTH, 'words': m.words, 'terrain': terrain,
            'terrainNames': {str(k): v for k, v in TERRAIN_NAMES.items()}, 'impassable': sorted(IMPASSABLE),
            'locations': locs, 'deploy': [lists[k] for k in sorted(lists)], 'areas': chapter_areas(ch),
            'tilesVer': tiles_version(ch)}


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
                    scenes[sid] = {'messages': sc['messages'], 'runs': sc['runs']}
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
COND_OPS = {0x02, 0x04, 0x05, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x16, 0x1A, 0x21}


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
        nm = {0x0C: 'TEXT', 0x31: 'TALK', 0x32: 'TALK_SCENE'}.get(op, 'OP_%02X' % op)
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
        msg = new_message_op('{06}{00 3D}%s{07}{00 3D}%s{06}{09}Write the first line here.{07}{00 1D 10}And the reply here.{08}{01}'
                             % (portrait_code(a), portrait_code(t)), f'{name[:4]} new talk', ops)
        sid = new_scene_ops(talk_scene(msg, t), ops)
        cond = _hx('04' if ch < 6 else '16', '%02X' % flag, _w(a), _w(t), 'FF FF')
        steps = ['30 FF ' + _w(sid)]
        talk_row_ops(ch, flag, a, t, True, ops)
    elif kind == 'visit':
        loc = int(b['loc'])
        for cnd, steps in chapter_triggers(name):
            cb = cmd_bytes(cnd)
            if cb[0] == 0x0A and cb[4] | cb[5] << 8 == loc:
                raise ValueError('That village already has a visit event: open it and add to it.')
        msg = new_message_op(say(VILLAGER, 'Welcome, traveler! Please, take this.'), f'{name[:4]} new village', ops)
        sid = new_scene_ops(map_scene(msg), ops)
        cond = _hx('0A FF FF FF', _w(loc))
        steps = ['30 FF ' + _w(sid)]
    elif kind == 'turn':
        turn, who = int(b['turn']), u('who', lord)
        if not 1 <= turn <= 99:
            raise ValueError('Turn is 1 to 99.')
        msg = new_message_op(say(who, 'Write what is said here.'), f'{name[:4]} new turn {turn}', ops)
        # the game plays one scene at a time: a turn that already has a scene gets the message in it
        for cnd, steps in chapter_triggers(name):
            cb = cmd_bytes(cnd)
            if cb[0] == 0x02 and cb[2:4] == b'\0\0' and cb[4] | cb[5] << 8 == turn:
                sid = next((cmd_bytes(c)[2] | cmd_bytes(c)[3] << 8 for c in steps if cmd_bytes(c)[:1] == b'\x30'), None)
                if sid is not None:
                    add_text_to_scene(sid, msg, ops)
                    p.edit(ops['list'])
                    return {'ok': True, 'file': name, 'line': cnd['line'], 'merged': True}
        sid = new_scene_ops(map_scene(msg), ops)
        cond = _hx('02', '%02X' % free_flag(name), '00 00', _w(turn))
        steps = ['30 FF ' + _w(sid)]
    elif kind == 'area':
        unit = u('unit', lord)
        x1, y1, x2, y2 = (int(b[k]) for k in ('x1', 'y1', 'x2', 'y2'))
        if not all(0 <= v < 64 for v in (x1, y1, x2, y2)):
            raise ValueError('Corners are 0 to 63.')
        msg = new_message_op(say(unit if unit != 0xFFFF else lord, 'Write what is said here.'), f'{name[:4]} new area', ops)
        sid = new_scene_ops(map_scene(msg), ops)
        cond = _hx('0B', '%02X' % free_flag(name), _w(unit), '%02X %02X %02X %02X' % (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), 'FF')
        steps = ['30 FF ' + _w(sid)]
    elif kind == 'battle':
        a, t = u('a'), u('b')
        if t == 0xFFFF:
            raise ValueError('Choose who the quote is for (the second unit speaks).')
        msg = new_message_op(say(t, 'Write the battle quote here.'), f'{name[:4]} new battle quote', ops)
        cond = _hx('0D FF 00 00', _w(a), 'FF FF', _w(t))
        steps = ['31 %02X @%s 00' % (free_flag(name), msg)]
    elif kind == 'death':
        unit = u('unit')
        if unit == 0xFFFF:
            raise ValueError('Choose who dies.')
        msg = new_message_op(say(unit, 'Write the last words here.'), f'{name[:4]} new death quote', ops)
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
    if kind == 'message':
        who = int(b.get('who') or lord)
        if cb[0] in (0x0D, 0x0E, 0x1A):            # battle screen: a quote
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



# ---------------------------------------------------------------- armies and enemy AI
import fe4armies                   # noqa: E402

AI = 'ai_orders.evt'
# words for each AI command: (sentence, fields [(label, kind, byte pos, size)]); {k} = argument names
AI_WORDS = {
    0x00: ('Stay where it is this turn', []),
    0x01: ('Go to step {jump}', []),
    0x02: ('Set behaviour mode {b1}?', [('Mode', 'num', 1, 1)]),
    0x03: ('Group pace: {pace}', [('Pace', 'pace', 1, 1)]),
    0x04: ('Never attack {slot}', [('Spare', 'slot', 1, 1)]),
    0x05: ('Set an unknown switch (bit 9 of $7E:2000)?', []),
    0x06: ('Seize {loc} (skipped once it is taken)', [('Castle', 'loc', 1, 1), ('Mode?', 'num', 2, 1)]),
    0x07: ('Guard {loc} while its army holds it', [('Castle', 'loc', 1, 1), ('Mode?', 'num', 2, 1)]),
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
    0x19: ('Attack anyone (mode 7)?', []),
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
        if len(b) > 2:
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
            'formations': fe4armies.FORMATIONS, 'facings': fe4armies.FACINGS,
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
    for sid in fe4sprites.all_ids():
        nm = fe4sprites.sprite_name(sid)
        data = p.blob(fe4sprites.sprite_file(sid)).data
        sprites.append({'name': nm, 'tall': fe4sprites.is_tall(sid), 'users': users.get(nm, []),
                        'custom': data is not None, 'ver': '%08x' % zlib.crc32(data) if data is not None else 'rom'})
    return {'classes': [classes[k] for k in sorted(classes)], 'sprites': sprites,
            'armies': [a for a, _ in fe4sprites.ARMIES]}


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
    dr = chapter_drawings(ch)
    if not dr:
        return 'rom'
    return '%08x' % zlib.crc32(b''.join(b'%d:' % k + dr[k] for k in sorted(dr)))


def chapter_gfx(ch, drawings=None):
    """The chapter's tiles with the project's drawings.  Earlier chapters' drawings come first, since
    they take from the shared tile pool before this one (as the build does)."""
    rom = rom_data()
    dr = {c: chapter_drawings(c) for c in range(ch + 1)}
    if drawings is not None:
        dr[ch] = drawings
    key = (id(rom), ch, tuple(tiles_version(c) for c in range(ch + 1)))
    if drawings is None and key in _gfx_cache:
        return _gfx_cache[key]
    pool = list(fe4maptiles.pool_tiles(rom))
    for c in range(ch):
        if dr[c]:
            pool = list(fe4maptiles.load_project(rom, None, c, None, dr[c], pool).pool)
    g = fe4maptiles.load_project(rom, None, ch, None, dr[ch], pool)
    if drawings is None:
        if len(_gfx_cache) > 24:
            _gfx_cache.clear()
        _gfx_cache[key] = g
    return g


def api_tileinfo(b, q):
    p = need_project()
    ch, k = int(q['ch'][0]), int(q['k'][0])
    m = p.map(ch)
    g = chapter_gfx(ch)
    terr = chapter_terrain(ch)
    custom = k in chapter_drawings(ch)
    used = sum(1 for w in m.words if w & 0x3FF == k)
    rom = rom_data()
    orig = fe4maptiles.ChapterGfx(rom, ch).terrain[k] if rom is not None else 0
    return {'ch': ch, 'k': k, 'own': k < 256, 'onMap': used, 'terrain': terr.get(k, g.terrain[k]), 'origTerrain': orig,
            'row': ch * 1024 + k, 'custom': custom, 'free': sum(g.room()), 'freeShared': g.room()[1],
            'ver': tiles_version(ch)}


def api_tiledraw(b, q):
    """Redraw chapter tile k from a PNG (base64), or {reset: true}.  One undo step."""
    import base64
    p = need_project()
    ch, k = int(b['ch']), int(b['k'])
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
        top = max([int(x['index']) for t in (kids, gen) for x in t.rows if x['index'].isdigit()])
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
    ids = [int(x['index']) for t in (kids, gen) for x in t.rows if x['index'].isdigit()]
    new_ids = [i for i in ids if i > cnt]
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


API = {('GET', 'session'): api_session, ('POST', 'ping'): api_ping, ('GET', 'table'): api_table,
       ('POST', 'tables'): api_tables, ('POST', 'set'): api_set, ('POST', 'undo'): api_undo,
       ('POST', 'redo'): api_redo, ('POST', 'save'): api_save, ('POST', 'open'): api_open,
       ('POST', 'rom'): api_set_rom, ('POST', 'new'): api_new_project, ('GET', 'job'): api_job,
       ('POST', 'build'): api_build, ('GET', 'battleanims'): api_battleanims, ('GET', 'battleinfo'): api_battleinfo,
       ('POST', 'battleimport'): api_battleimport, ('POST', 'battlemotion'): api_battlemotion,
       ('POST', 'battleframe'): api_battleframe, ('GET', 'battlemotions'): api_battlemotions,
       ('GET', 'battlespells'): api_battlespells, ('POST', 'spellrow'): api_spellrow, ('GET', 'spellgfx'): api_spellgfx, ('POST', 'spellgfxset'): api_spellgfxset, ('POST', 'battlereset'): api_battlereset,
       ('POST', 'ipspatch'): api_ipspatch, ('POST', 'reveal'): api_reveal,
       ('GET', 'patchinfo'): api_patchinfo, ('POST', 'testplay'): api_testplay, ('POST', 'settings'): api_settings,
       ('POST', 'dialog'): api_dialog, ('POST', 'quit'): api_quit, ('POST', 'classic'): api_classic,
       ('POST', 'setmany'): api_setmany, ('GET', 'people'): api_people, ('GET', 'textinfo'): api_textinfo, ('GET', 'events'): api_events,
       ('GET', 'chapters'): api_chapters, ('GET', 'scene'): api_scene, ('POST', 'messages'): api_messages,
       ('POST', 'msg'): api_msg, ('POST', 'evtcmd'): api_evtcmd, ('GET', 'dsearch'): api_dsearch, ('GET', 'villages'): api_villages, ('GET', 'itemuse'): api_itemuse, ('POST', 'newevent'): api_newevent, ('POST', 'talkmenu'): api_talkmenu, ('POST', 'delstep'): api_delstep,
       ('POST', 'addstep'): api_addstep, ('GET', 'eventinfo'): api_eventinfo, ('GET', 'maps'): api_maps, ('GET', 'map'): api_map, ('POST', 'paint'): api_paint,
       ('GET', 'armies'): api_armies, ('GET', 'portraits'): api_portraits, ('GET', 'mapsprites'): api_mapsprites, ('GET', 'skills'): api_skills, ('POST', 'gen2check'): api_gen2check, ('POST', 'newchild'): api_newchild, ('POST', 'skillcheck'): api_skillcheck, ('POST', 'skilledit'): api_skilledit, ('POST', 'spriteentry'): api_spriteentry, ('GET', 'tileinfo'): api_tileinfo, ('POST', 'tiledraw'): api_tiledraw, ('POST', 'mapsprite'): api_mapsprite, ('POST', 'portrait'): api_portrait, ('POST', 'aicmd'): api_aicmd, ('POST', 'airecipe'): api_airecipe}


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
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
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
