"""Builder of the Holy War self-test.

    python3 dev/selftest.py ROM WORKDIR [phase ...]

Phases (all by default):
  roundtrip  extract the ROM, build it unedited: must be byte-identical
  reads      every read-only API call for every chapter must answer without an error
  edits      one edit per feature through the API, then save, build and re-extract: each edit must be
             in the rebuilt project, and the project must build again from its own output unchanged
WORKDIR gets the projects and ROMs (t_clean, t_edit, edit.smc ...).  Prints one line per check and a
summary; the exit code is the number of failures.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)

FAILS = []
COUNT = [0]


def check(name, fn):
    COUNT[0] += 1
    t = time.time()
    try:
        r = fn()
    except Exception as e:          # noqa: BLE001
        FAILS.append(name)
        print(f'FAIL {name}: {type(e).__name__}: {e}')
        tb = traceback.format_exc().strip().splitlines()
        print('     ' + '\n     '.join(tb[-4:]))
        return None
    dt = time.time() - t
    print(f'ok   {name}' + (f'  ({dt:.1f}s)' if dt > 2 else ''))
    return r


def hack(*args):
    r = subprocess.run([sys.executable, os.path.join(KIT, 'fe4hack.py'), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[-800:])
    return r.stdout


# ---------------------------------------------------------------- phases
def roundtrip(rom, work):
    proj = os.path.join(work, 't_clean')
    out = os.path.join(work, 'clean.smc')

    def go():
        shutil.rmtree(proj, ignore_errors=True)
        hack('extract', rom, proj)
        hack('build', rom, proj, out)
        a, b = open(rom, 'rb').read(), open(out, 'rb').read()
        if a != b:
            diff = sum(1 for x, y in zip(a, b) if x != y)
            raise AssertionError(f'{diff} bytes differ')
    check('roundtrip: unedited build is byte-identical', go)


def studio(rom, proj):
    import fe4studio as S
    S.settings['rom'] = rom
    S.open_project(proj)
    return S


def q(**k):
    return {a: [str(v)] for a, v in k.items()}


def reads(rom, work):
    proj = os.path.join(work, 't_clean')
    if not os.path.isdir(proj):
        hack('extract', rom, proj)
    S = studio(rom, proj)
    p = S.project()
    check('read session', lambda: S.api_session({}, {}))
    chs = check('read chapters', lambda: S.api_chapters({}, {}))
    nch = 12
    for name in sorted(p.tables):
        check(f'read table {name}', lambda name=name: S.api_table({}, q(name=name)))
    for fn in ('people', 'textinfo', 'portraits', 'mapsprites', 'skills', 'music', 'title', 'maps', 'itemuse',
               'battleanims', 'battlespells', 'skillanims', 'spellgfx', 'mapbattle', 'mapspells', 'patchinfo',
               'eventinfo'):
        check(f'read {fn}', lambda fn=fn: getattr(S, 'api_' + fn)({}, {}))
    check('read dsearch', lambda: S.api_dsearch({}, q(q='Sigurd')))
    check('read scene 1', lambda: S.api_scene({}, q(id=1)))
    check('read battlemotions', lambda: S.api_battlemotions({}, q(row=0)))
    check('read mbplayer', lambda: S.api_mbplayer({}, q(fig=0)))
    for ch in range(nch):
        for fn in ('events', 'map', 'mapinfo', 'armies', 'villages', 'wincond', 'losecond', 'timeline', 'opening', 'chaptitle', 'tileset'):
            check(f'read {fn} ch{ch}', lambda fn=fn, ch=ch: getattr(S, 'api_' + fn)({}, q(ch=ch)))
        check(f'read tileinfo ch{ch}', lambda ch=ch: S.api_tileinfo({}, q(ch=ch, k=5)))
    def clean_check():
        r = S.api_check({}, {})
        bad = [f['text'] for f in r['findings'] if f['level'] != 'info']
        if bad:
            raise AssertionError('the unedited game has findings: ' + '; '.join(bad[:3]))
    check('Check my hack: nothing to report on the unedited game', clean_check)
    return chs


# ---------------------------------------------------------------- edits
def edits(rom, work):
    proj = os.path.join(work, 't_edit')
    out = os.path.join(work, 'edit.smc')
    shutil.rmtree(proj, ignore_errors=True)
    check('edits: extract', lambda: hack('extract', rom, proj))
    S = studio(rom, proj)
    p = S.project()
    expect = []        # (description, function(project dir) -> bool)

    def table_row(t, key, val):
        tb = p.table(t)
        return next(i for i, r in enumerate(tb.rows) if r.get(key) == val)

    # characters / classes / items: plain table edits
    def e_unit():
        tb = p.table('units_playable')
        i = next(i for i, r in enumerate(tb.rows) if r.get('_name') == 'Sigurd')
        S.api_set({'table': 'units_playable', 'row': i, 'field': 'level', 'value': '7'}, {})
        expect.append(('Sigurd level 7', lambda d: _csv(d, 'units_playable.csv')[i]['level'] == '7'))
    check('edit: character level', e_unit)

    def e_item():
        S.api_set({'table': 'items', 'row': 1, 'field': 'mt', 'value': '9'}, {})
        expect.append(('item 1 might 9', lambda d: _csv(d, 'items.csv')[1]['mt'] == '9'))
    check('edit: item might', e_item)

    def e_class():
        tb = p.table('classes')
        col = 'move' if 'move' in tb.rows[0] else next(c for c in tb.rows[0] if 'mov' in c)
        S.api_set({'table': 'classes', 'row': 3, 'field': col, 'value': '6'}, {})
        expect.append(('class 3 move 6', lambda d: _csv(d, 'classes.csv')[3][col] == '6'))
    check('edit: class move', e_class)

    # map unit: add a new enemy
    def e_mapunit():
        r = S.api_mapunit({'op': 'add', 'ch': 0, 'x': 50, 'y': 12, 'list': 0, 'slot': 1, 'orders': 1,
                           'generic': {'class': 2, 'level': 7, 'items': [3], 'name_id': 65}}, {})
        row = p.table('deploy').rows[r['rows'][0]]
        expect.append(('new enemy at 50,12', lambda d: any(x['x'] == '50' and x['y'] == '12' and x['index'].startswith('0.')
                                                            for x in _csv(d, 'deploy.csv'))))
        return row
    check('edit: add a map unit', e_mapunit)

    # win condition: rout, then boss, then turn (last one stays)
    def e_win():
        w = S.api_wincond({}, q(ch=1))
        line = w['endings'][0]['line']
        S.api_wincond({'ch': 1, 'line': line, 'kind': 'rout', 'slots': [w['armies'][0]['slot']]}, {})
        w2 = S.api_wincond({}, q(ch=1))
        assert w2['endings'][0]['kind'] == 'rout', w2['endings'][0]
        people = [x for x in w2['people'] if not x['shared']]
        S.api_wincond({'ch': 1, 'line': line, 'kind': 'boss', 'unit': people[0]['id']}, {})
        w3 = S.api_wincond({}, q(ch=1))
        assert w3['endings'][0]['kind'] == 'boss', w3['endings'][0]
        S.api_wincond({'ch': 3, 'line': S.api_wincond({}, q(ch=3))['endings'][0]['line'], 'kind': 'rout',
                       'slots': [S.api_wincond({}, q(ch=3))['armies'][0]['slot']]}, {})
        expect.append(('ch1 boss ending', lambda d: _evt_has(d, 1, '1A ')))
        expect.append(('ch3 rout ending', lambda d: _evt_has(d, 3, '03 ')))
    check('edit: win conditions (rout, boss)', e_win)

    # arrival: join + enemy, several triggers
    def e_arrival():
        finn = next(x['id'] for x in S.api_people({}, {})['people'] if x.get('name') == 'Finn')
        S.api_arrival({'ch': 0, 'unit': finn, 'side': 'join', 'x': 40, 'y': 12, 'entrance': 'walk', 'fx': 63, 'fy': 12,
                       'when': {'kind': 'turn', 'turn': 2},
                       'talk': {'a': finn, 'b': 1, 'lines': [{'who': 'a', 'text': 'Hello.'}, {'who': 'b', 'text': 'Welcome.'}]}}, {})
        S.api_arrival({'ch': 0, 'unit': 69, 'side': 'other', 'slot': 1, 'orders': 1, 'x': 30, 'y': 10, 'entrance': 'appear',
                       'when': {'kind': 'area', 'unit': 1, 'x1': 30, 'y1': 5, 'x2': 40, 'y2': 15}}, {})
        S.api_arrival({'ch': 0, 'unit': 69, 'side': 'other', 'slot': 1, 'orders': 1, 'x': 31, 'y': 10, 'fx': 25, 'fy': 10,
                       'when': {'kind': 'opening'}}, {})
        S.api_arrival({'ch': 0, 'unit': 69, 'side': 'other', 'slot': 1, 'orders': 1, 'x': 32, 'y': 10, 'fx': 25, 'fy': 11,
                       'when': {'kind': 'seize', 'loc': 1, 'by': 0}}, {})
        expect.append(('arrival scenes in the Prologue', lambda d: _evt_has(d, 0, '0B ') and _evt_has(d, 0, '01 ')))
    check('edit: arrivals (turn, area, opening, castle taken)', e_arrival)

    def e_newevent():
        S.api_newevent({'ch': 0, 'kind': 'talk', 'a': 1, 'b': 2, 'line1': 'Test line.', 'line2': 'Reply.'}, {})
    check('edit: new talk event', e_newevent)

    def e_title():
        S.api_chaptitle_set({'ch': 0, 'title': 'The Test'}, {}) if 'digits' not in S.api_chaptitle.__doc__ else None
    # chapter titles need a browser-drawn picture; covered by the page test

    def e_castleless():
        tb = p.table('armies')
        i = next(i for i, r in enumerate(tb.rows) if r.get('army') == '0')
        S.api_set({'table': 'armies', 'row': i, 'field': 'castles', 'value': ''}, {})
        expect.append(('army 0 has no castles', lambda d: _csv(d, 'armies.csv')[i]['castles'] == ''))
    check('edit: castle-less Prologue', e_castleless)

    def e_lose():
        S.api_losecond({'ch': 0, 'kind': 'death', 'unit': 6, 'text': 'Quan has fallen...\nWe cannot go on.'}, {})
        S.api_losecond({'ch': 0, 'kind': 'castle', 'loc': 1}, {})
        rules = S.api_losecond({}, q(ch=0))['rules']
        assert sorted(r['kind'] for r in rules) == ['castle', 'death'], rules
        expect.append(('lose if Quan is defeated', lambda d: _evt_has(d, 0, '1A FF 06 00 FF FF')))
        expect.append(('lose scenes end the game', lambda d: '45 81 ED 80' in open(os.path.join(d, 'events', 'scenes.evt')).read()))
    check('edit: lose conditions (someone defeated, a castle taken)', e_lose)

    def e_check():
        r = S.api_check({}, {})
        texts = [f['text'] for f in r['findings']]
        assert any("can't use" in t for t in texts), texts      # the soldier added above (class 2, item 3)
    check('edit: Check my hack finds the added soldier\'s unusable weapon', e_check)

    def e_timeline():
        T = S.api_timeline({}, q(ch=0))
        beats = [b['text'] for e in T['turns'] for b in e['beats']] + [b['text'] for b in T['opening']]
        assert any('joins your army' in t for t in beats), beats[:5]            # Finn's arrival at turn 2
        assert any(e.get('loses') for sec in T['when'].values() for e in sec), 'lose rules not marked'
        assert len(T['loses']) >= 4, T['loses']
    check('edit: the timeline shows arrivals and lose rules', e_timeline)

    def e_narration():
        T = S.api_timeline({}, q(ch=1))
        assert len(T['narration']) >= 3, T['narration']
        k = T['narration'][0]['key']
        d = S.project().dialogue()
        S.api_msg({'key': k, 'text': d.text[k].replace('Sigurd', 'Sigurd the Test', 1)}, {})
        expect.append(('chapter 1 narration edited', lambda dd: 'Sigurd the Test' in open(os.path.join(dd, 'events', 'dialogue.txt'), encoding='utf-8').read()))
    check('edit: world map narration text', e_narration)

    def e_caption():
        C = S.api_captions({}, {})
        assert len(C['captions']) == 13, len(C['captions'])
        px = ['0'] * 4096
        for y in range(4, 12):                       # a bar in the middle of the strip
            for x in range(96, 160):
                px[y * 256 + x] = 'f'
        S.api_captions({'i': 4, 'text': 'A test caption', 'px': ''.join(px)}, {})
        captions_px.append(''.join(px))
    captions_px = []
    check('edit: an opening caption', e_caption)

    def e_undo_redo():
        n = len(p.table('deploy').rows)
        S.api_mapunit({'op': 'add', 'ch': 0, 'x': 51, 'y': 13, 'list': 0, 'slot': 1, 'orders': 1, 'char_id': 69}, {})
        assert len(p.table('deploy').rows) == n + 1
        S.api_undo({}, {})
        assert len(p.table('deploy').rows) == n, 'undo'
        S.api_redo({}, {})
        assert len(p.table('deploy').rows) == n + 1, 'redo'
        S.api_undo({}, {})
    check('edit: undo and redo', e_undo_redo)

    check('edits: save', lambda: S.api_save({}, {}))
    check('edits: build', lambda: hack('build', rom, proj, out))
    back = os.path.join(work, 't_back')

    def reextract():
        shutil.rmtree(back, ignore_errors=True)
        hack('extract', out, back)
    check('edits: re-extract the built ROM', reextract)
    for desc, fn in expect:
        check(f'kept: {desc}', lambda fn=fn: _assert(fn(back)))

    def caption_kept():
        import fe4captions
        rom2 = open(out, 'rb').read()
        pics = fe4captions.read(rom2)
        got = ''.join('%x' % v for v in pics[4])
        assert got == captions_px[0], 'caption 5 differs in the built ROM'
        o = fe4captions._fo(fe4captions.SCROLLS) + 4
        assert rom2[o] == fe4captions.CENTRED, rom2[o]
    if captions_px:
        check('kept: caption 5 in the built ROM, centred', caption_kept)

    def rebuild_same():
        out2 = os.path.join(work, 'edit2.smc')
        hack('build', rom, proj, out2)
        if open(out, 'rb').read() != open(out2, 'rb').read():
            raise AssertionError('building twice gave different ROMs')
    check('edits: building again gives the same ROM', rebuild_same)
    return out


def _assert(v):
    if not v:
        raise AssertionError('not found')


def _csv(d, name):
    import csv
    with open(os.path.join(d, name), encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def _evt_has(d, ch, hexstart):
    ev = os.path.join(d, 'events')
    for f in os.listdir(ev):
        if f.startswith('ch%02d' % ch) and f.endswith('.evt'):
            for line in open(os.path.join(ev, f), encoding='utf-8'):
                h = line.split(';', 1)[0].split(':', 1)
                if len(h) == 2 and h[1].strip().startswith(hexstart):
                    return True
    return False


def main():
    rom, work = sys.argv[1], sys.argv[2]
    phases = sys.argv[3:] or ['roundtrip', 'reads', 'edits']
    os.makedirs(work, exist_ok=True)
    os.environ.setdefault('HOME', work)
    t = time.time()
    for ph in phases:
        print(f'--- {ph}')
        globals()[ph](rom, work)
    print(f'--- {COUNT[0]} checks, {len(FAILS)} failed, {time.time() - t:.0f}s')
    for f in FAILS:
        print('  failed:', f)
    sys.exit(len(FAILS))


if __name__ == '__main__':
    main()
