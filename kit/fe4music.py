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
            (an army allied to you plays $1D, ... $2A: set in code at $81:AA40 / $81:AA45)
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


def tables(rom):
    return {'first': [_w(rom, snes_to_file(FIRST_PHASE) + 2 * i) for i in range(CHAPTERS)],
            'phase': [_w(rom, snes_to_file(YOUR_PHASE) + 2 * i) for i in range(CHAPTERS)],
            'army': [_w(rom, snes_to_file(ARMY_PHASE) + 2 * i) for i in range(ARMY_NAMES)]}


def export(rom, path, chapter_titles, castle_name):
    t = tables(rom)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['table', 'index', 'song', '_name'])
        for i in range(CHAPTERS):
            w.writerow(['first', i, t['first'][i], chapter_titles[i] if i < len(chapter_titles) else ''])
        for i in range(CHAPTERS):
            w.writerow(['phase', i, t['phase'][i], chapter_titles[i] if i < len(chapter_titles) else ''])
        for i in range(ARMY_NAMES):
            w.writerow(['army', i, t['army'][i], castle_name(i)])


def read(proj):
    p = os.path.join(proj, FILE)
    if not os.path.exists(p):
        return None
    out = {'first': {}, 'phase': {}, 'army': {}}
    with open(p, newline='') as f:
        for r in csv.DictReader(f):
            if r.get('table') in out:
                out[r['table']][int(r['index'])] = int(r['song'])
    return out


def apply(rom, proj):
    t = read(proj)
    if not t:
        return 0
    n = 0
    for name, base, count in (('first', FIRST_PHASE, CHAPTERS), ('phase', YOUR_PHASE, CHAPTERS),
                              ('army', ARMY_PHASE, ARMY_NAMES)):
        for i, song in t[name].items():
            if not 0 <= i < count:
                continue
            if not 1 <= song <= SONGS:
                raise SystemExit(f'{FILE}: {name} {i}: song {song} (songs are 1-{SONGS})')
            fo = snes_to_file(base) + 2 * i
            if _w(rom, fo) != song:
                rom[fo] = song & 0xFF
                rom[fo + 1] = song >> 8
                n += 1
    return n


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
    out.setdefault(0x1D, []).append('allied army phase')
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
