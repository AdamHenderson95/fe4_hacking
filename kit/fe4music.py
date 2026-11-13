"""Music: which song plays where, the game's song list, and the MSU-1 hooks for custom music.

Found for the editor (kit v49) by tracing the Prologue (ROM_MAP "Music"):
  The game asks for a song by writing its number (1-160) to $04BA; the sound script engine ($80:9677)
  runs the song's script from $F7:943E (a word pointer per song, bank $F7): upload the music data to the
  sound chip (command 10), then start it (command 16: C8-CA play, CB-CD play as map music that comes back
  after a battle).  Battle music scripts (command 17) also pick a variant for the fighters' classes.
  Sound commands go to the chip through a queue ($80:8F6F / $80:8FA3 / $80:8FAD): E0-E2 fade the music
  out (fast to slow), C0/C2/F8 stop it.

  $81:AB0E  12 words: the song when a chapter's map first starts (your first phase)
  $81:AA4D  12 words: your phase's song for each chapter
  $81:AA65  53 words: an army's phase song, by the army's name (its castle name number, army record +0)
            (some armies play $1D or $2A instead: set in code at $81:AA40 / $81:AA45)
Kit v50: $91:F7B7 chapter openings, songs fixed in code (opening, title, chronology), the battle music
rules at $84:D694 and the boss list they check, and scene command $0E (PLAY_SONG) in scenes.evt.
"""
import csv
import os

import fe4lib as L
from dis65816 import snes_to_file

SONG_TABLE = 0xF7943E
SONGS = 160
FIRST_PHASE = 0x81AB0E
YOUR_PHASE = 0x81AA4D
ARMY_PHASE = 0x81AA65
CHAPTERS = 12
ARMY_NAMES = 53
FILE = 'music.csv'
CHAPTER_NAMES = ['Prologue'] + ['Chapter %d' % i for i in range(1, 11)] + ['Final Chapter']
FOLDER = 'music'
AUDIO = ('.ogg', '.flac', '.mp3', '.wav', '.pcm')


def _w(rom, fo):
    return rom[fo] | rom[fo + 1] << 8


def song_script(rom, n):
    """[(command, argument, wait)] of song n's script (command -1 = wait only)."""
    p = _w(rom, snes_to_file(SONG_TABLE) + 2 * (n - 1))
    fo = snes_to_file(0xF70000 | p)
    out = []
    for _ in range(40):
        x = _w(rom, fo)
        fo += 2
        if x == 0:
            break
        c, t = x >> 10, x & 0x3FF
        if c:
            out.append((c - 1, _w(rom, fo), t))
            fo += 2
        else:
            out.append((-1, 0, t))
    return out


def song_kind(rom, n):
    """'music', 'map' (comes back after a battle), 'battle', 'sound' (a sound effect) or 'other'."""
    s = song_script(rom, n)
    cmds = [c for c, a, t in s]
    if 17 in cmds:
        return 'battle'
    starts = [a for c, a, t in s if c == 16]
    if any(0xCB <= a <= 0xCD for a in starts):
        return 'map'
    if 10 in cmds or 12 in cmds:
        return 'music'
    if cmds and all(c in (0, 1, 2, 3) for c in cmds):
        return 'sound'
    return 'other'


def same_as(rom, n):
    """The lowest song number with the same script (FE4 has several numbers for one song), or None."""
    base = snes_to_file(SONG_TABLE)
    p = _w(rom, base + 2 * (n - 1))
    for k in range(1, n):
        if _w(rom, base + 2 * (k - 1)) == p:
            return k
    return None


# every place a song number lives: table -> [(SNES address of the word, label)]
OPENING = 0x91F7B7         # 12 words: the song when a chapter opens (0 = none)
FIXED = [(0x9BFB8B, 'Opening (the story pictures before the title)'), (0x9BFBAA, 'Title screen'),
         (0x91E70A, 'The Jugdral Chronology (a new game)')]
# $84:D694 picks a battle's music: the first rule that fits wins
BATTLE = [(0x84D6EC, 'Seliph or Julia fights Julius'), (0x84D6E7, 'Someone fights Julia'),
          (0x84D6E2, 'Someone fights Arvis'), (0x84D6DD, 'Someone fights a boss (the list below)'),
          (0x84D6D3, 'A special case for your side, chosen in the game\'s code'),
          (0x84D6D8, 'Another special case for your side, chosen in the game\'s code'),
          (0x84D6CE, 'Your army or an ally fights'), (0x84D6C9, 'Other battles')]
# battles that set their music elsewhere (LDA #song / STA $4EB3)
BATTLE_MORE = [(0x84E024, 'A battle started by an event (like the Prologue\'s first fight)')] + [
    (a, 'Set at $%02X:%04X (not identified yet)' % (a >> 16, (a - 1) & 0xFFFF))
    for a in (0x84AC16, 0x84B543, 0x84E1BE, 0x84E997, 0x84E9DC, 0x84EA30, 0x84EAD1, 0x84EB68, 0x84EBCE,
              0x84EC79, 0x84EDA7, 0x84EE2B, 0x84EEAA)]
BOSSES = [0x84D742 + 5 * i for i in range(20)]   # CMP #unit operands: who plays the boss music
BOSS_FILE = 'music_bosses.csv'


def places():
    return {'first': [(FIRST_PHASE + 2 * i, CHAPTER_NAMES[i]) for i in range(CHAPTERS)],
            'phase': [(YOUR_PHASE + 2 * i, CHAPTER_NAMES[i]) for i in range(CHAPTERS)],
            'army': [(ARMY_PHASE + 2 * i, None) for i in range(ARMY_NAMES)],
            'opening': [(OPENING + 2 * i, CHAPTER_NAMES[i]) for i in range(CHAPTERS)],
            'fixed': FIXED, 'battle': BATTLE, 'battle_more': BATTLE_MORE}


def tables(rom):
    return {k: [_w(rom, snes_to_file(a)) for a, _ in v] for k, v in places().items()}


def bosses(rom):
    return [_w(rom, snes_to_file(a)) for a in BOSSES]


def export(rom, path, chapter_titles, castle_name):
    t = tables(rom)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['table', 'index', 'song', '_name'])
        for k, v in places().items():
            for i, (a, label) in enumerate(v):
                if k == 'army':
                    label = castle_name(i)
                elif k in ('first', 'phase', 'opening'):
                    label = chapter_titles[i] if i < len(chapter_titles) else label
                w.writerow([k, i, t[k][i], label])
    export_bosses(rom, os.path.join(os.path.dirname(path), BOSS_FILE))


def project_unit_names(proj):
    """{unit number: name} from the project's unit tables."""
    out = {}
    for t in ('units_generic', 'units_npc', 'units_children', 'units_playable'):
        p = os.path.join(proj, t + '.csv')
        if os.path.exists(p):
            with open(p, newline='') as f:
                for r in csv.DictReader(f):
                    try:
                        out[int(r['index'])] = r.get('_name') or out.get(int(r['index']), '')
                    except (KeyError, ValueError):
                        pass
    return out


def export_bosses(rom, path, unit_name=None):
    if unit_name is None:
        names = project_unit_names(os.path.dirname(path))
        unit_name = lambda u: names.get(u, '')  # noqa: E731
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['index', 'unit', '_name'])
        for i, u in enumerate(bosses(rom)):
            w.writerow([i, u, unit_name(u) if unit_name else ''])


def upgrade(rom, proj, chapter_titles, castle_name):
    """Projects from kit v49 have only the map tables: add the rest."""
    p = os.path.join(proj, FILE)
    have = set()
    if os.path.exists(p):
        with open(p, newline='') as f:
            have = {r['table'] for r in csv.DictReader(f)}
    if not os.path.exists(p) or not set(places()) <= have:
        old = read(proj) if os.path.exists(p) else None
        export(rom, p, chapter_titles, castle_name)
        if old:                                    # keep what the project changed
            rows = list(csv.reader(open(p, newline='')))
            for r in rows[1:]:
                if r[0] in old and int(r[1]) in old[r[0]]:
                    r[2] = str(old[r[0]][int(r[1])])
            with open(p, 'w', newline='') as f:
                csv.writer(f).writerows(rows)
        return True
    if not os.path.exists(os.path.join(proj, BOSS_FILE)):
        export_bosses(rom, os.path.join(proj, BOSS_FILE))
        return True
    return False


def read(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return None
    out = {}
    with open(p, newline='') as f:
        for r in csv.DictReader(f):
            out.setdefault(r.get('table'), {})[int(r['index'])] = int(r['song'])
    return out


def apply(rom, proj):
    t = read(proj)
    n = 0
    if t:
        P = places()
        for name, vals in t.items():
            if name not in P:
                continue
            for i, song in vals.items():
                if not 0 <= i < len(P[name]):
                    continue
                if not (1 <= song <= SONGS or (name == 'opening' and song == 0)):
                    raise SystemExit(f'{FILE}: {name} {i}: song {song} (songs are 1-{SONGS})')
                fo = snes_to_file(P[name][i][0])
                if _w(rom, fo) != song:
                    rom[fo] = song & 0xFF
                    rom[fo + 1] = song >> 8
                    n += 1
    bp = os.path.join(proj, BOSS_FILE)
    if os.path.exists(bp):
        with open(bp, newline='') as f:
            for r in csv.DictReader(f):
                i, u = int(r['index']), int(r['unit'], 0)
                if not 0 <= i < len(BOSSES):
                    continue
                if not 0 <= u <= 0x3FF:
                    raise SystemExit(f'{BOSS_FILE}: row {i}: unit {u}')
                fo = snes_to_file(BOSSES[i])
                if _w(rom, fo) != u:
                    rom[fo], rom[fo + 1] = u & 0xFF, u >> 8
                    n += 1
    return n


NAMED = {1: 'Opening (story pictures)', 3: 'Title screen', 4: 'The Jugdral Chronology',
         94: 'Opening narration (the map of Jugdral)'}


def uses(rom, chapter_titles, castle_name):
    """{song: [what plays it]} from the tables."""
    t = tables(rom)
    out = {}
    for i, s in enumerate(t['first']):
        out.setdefault(s, []).append('%s: map starts' % _short(chapter_titles, i))
    for i, s in enumerate(t['phase']):
        out.setdefault(s, []).append('%s: your phase' % _short(chapter_titles, i))
    for i, s in enumerate(t['army']):
        nm = castle_name(i)
        if nm:
            out.setdefault(s, []).append('%s army phase' % nm)
    return out


def _short(titles, i):
    return titles[i].split(':')[0] if i < len(titles) else 'Chapter %d' % i


def music_files(proj):
    """{song: file name} in the project's music folder (named like the port's: 17.ogg, 017 Name.flac)."""
    d = os.path.join(proj, FOLDER)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(AUDIO):
            continue
        num = ''
        for ch in f:
            if ch.isdigit():
                num += ch
            else:
                break
        if num and 1 <= int(num) <= 999 and int(num) not in out:
            out[int(num)] = f
    return out


def apply_msu(rom):
    """The MSU-1 hooks (the PC port adds them itself): returns True if they went in."""
    from fe4msu_data import PATCHES
    for off, orig, new in PATCHES:
        if rom[off:off + len(new)] == new:
            continue
        if rom[off:off + len(orig)] != orig:
            return False
    for off, orig, new in PATCHES:
        rom[off:off + len(new)] = new
    return True
