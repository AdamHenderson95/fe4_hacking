#!/usr/bin/env python3
"""Builder of the Holy War: the kit's visual editor.

A small web server on 127.0.0.1 serves the interface in studio/ and a JSON API over the kit's
project files; the interface opens in its own window (Edge or Chrome in app mode, else the
default browser). Only pages that know this session's token can use the API.

  python fe4studio.py            # or BuilderOfTheHolyWar.exe
"""
import io
import json
import mimetypes
import os
import queue
import re
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
from fe4project import Project, load_settings, save_settings   # noqa: E402

APP = 'Builder of the Holy War'
VERSION = '18'
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
          'item_instances', 'skills', 'names', 'lovers', 'gen2_rules', 'deploy', 'locations', 'arena', 'armies'}


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
            data = fe4gfx.portrait_png(rom, n, max(1, min(scale, 4))) if rom else None
            return self._send(200, data, 'image/png', cache=True) if data else self._send(404, 'no')
        if path.startswith('/gfx/tiles/'):
            rom = rom_data()
            try:
                ch = int(path.rsplit('/', 1)[1].split('.')[0])
            except ValueError:
                return self._send(404, 'no')
            if rom is None or not 0 <= ch < fe4maps.MAP_COUNT:
                return self._send(404, 'no')
            return self._send(200, fe4gfx.map_atlas(rom, ch)[0], 'image/png', cache=True)
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
    tables = sorted({o[1] for o in ops if o[0] == 'cell'})
    maps = sorted({o[1] for o in ops if o[0] == 'map'})
    cells = [{'table': o[1], 'row': o[2], 'field': o[3]} for o in ops if o[0] == 'cell'][:50]
    evts = sorted({o[1] for o in ops if o[0] == 'evt'})
    msgs = sorted({o[1] for o in ops if o[0] == 'msg'})
    return {'change': {'tables': tables, 'maps': maps, 'cells': cells, 'events': evts, 'messages': msgs,
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
    terrain = fe4gfx.map_atlas(rom, ch)[1] if rom is not None else [0] * 1024
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
            'locations': locs, 'deploy': [lists[k] for k in sorted(lists)]}


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


def message_refs(name, b):
    """Message keys a command shows: (key, kind)."""
    if not b:
        return []
    if name == 'scenes.evt':
        if b[0] in (0x0C, 0x14) and len(b) >= 4:
            return [(_ptr(b, 1), 'TEXT' if b[0] == 0x0C else 'TEXT_WINDOW')]
        if b[0] in (0x4A, 0x4D) and len(b) >= 6 and b[1] in (0x31, 0x32):
            return [(_ptr(b, 3), 'TALK')]
        return []
    if b[0] in (0x31, 0x32) and len(b) >= 5:
        return [(_ptr(b, 2), 'TALK')]
    return []


def scene_refs(name, b):
    if name == 'scenes.evt':
        return [b[3] | b[4] << 8] if len(b) >= 5 and b[0] in (0x4A, 0x4D) and b[1] == 0x30 else []
    return [b[2] | b[3] << 8] if len(b) >= 4 and b[0] == 0x30 else []


def cmd_bytes(c):
    try:
        return bytes(int(x, 16) for x in c['hex'].split())
    except ValueError:
        return b''


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
                for k, kind in message_refs(name, b):
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
             'cmds': [dict(c, name=c['comment'].split(' ')[0] if c['comment'] else '',
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
    return {'ch': ch, 'title': CHAPTER_TITLES[ch] if ch < len(CHAPTER_TITLES) else name, 'file': name,
            'blocks': evt_json(name), 'locations': locs, 'scenes': scenes}


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
    p.set_command(name, line, hexs, ('%-14s %s' % (nm, note)).rstrip() if name != 'scenes.evt' else ('%-13s %s' % (nm, note)).rstrip())
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
            if b and b[0] in COND_OPS:
                cur = (c, [])
                out.append(cur)
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



API = {('GET', 'session'): api_session, ('POST', 'ping'): api_ping, ('GET', 'table'): api_table,
       ('POST', 'tables'): api_tables, ('POST', 'set'): api_set, ('POST', 'undo'): api_undo,
       ('POST', 'redo'): api_redo, ('POST', 'save'): api_save, ('POST', 'open'): api_open,
       ('POST', 'rom'): api_set_rom, ('POST', 'new'): api_new_project, ('GET', 'job'): api_job,
       ('POST', 'build'): api_build, ('POST', 'testplay'): api_testplay, ('POST', 'settings'): api_settings,
       ('POST', 'dialog'): api_dialog, ('POST', 'quit'): api_quit, ('POST', 'classic'): api_classic,
       ('POST', 'setmany'): api_setmany, ('GET', 'people'): api_people, ('GET', 'textinfo'): api_textinfo, ('GET', 'events'): api_events,
       ('GET', 'chapters'): api_chapters, ('GET', 'scene'): api_scene, ('POST', 'messages'): api_messages,
       ('POST', 'msg'): api_msg, ('POST', 'evtcmd'): api_evtcmd, ('GET', 'dsearch'): api_dsearch, ('GET', 'villages'): api_villages, ('GET', 'itemuse'): api_itemuse, ('GET', 'maps'): api_maps, ('GET', 'map'): api_map, ('POST', 'paint'): api_paint}


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
                                                    defaultextension='.smc', initialfile=b.get('initial') or '',
                                                    filetypes=[('SNES ROM', '*.smc *.sfc')])
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
