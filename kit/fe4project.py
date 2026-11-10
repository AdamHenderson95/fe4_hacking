"""A kit project on disk: the CSV tables, loaded on demand, with undo-able edits.

Shared by the classic editor (fe4editor.py) and Builder of the Holy War (fe4studio.py)."""
import csv
import json
import os
import re


def settings_path():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'fe4kit')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'settings.json')


def load_settings():
    try:
        with open(settings_path(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    try:
        with open(settings_path(), 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=1)
    except OSError:
        pass


class CsvTable:
    def __init__(self, path):
        self.path = path
        with open(path, newline='', encoding='utf-8') as f:
            rd = csv.DictReader(f)
            self.fields = list(rd.fieldnames or [])
            self.rows = [dict(r) for r in rd]
        self._saved = [dict(r) for r in self.rows]
        self._dirty = False

    # dirty = differs from the file (so undoing back to the saved state isn't "unsaved")
    @property
    def dirty(self):
        return self._dirty and self.rows != self._saved

    @dirty.setter
    def dirty(self, v):
        self._dirty = v

    def save(self):
        if not self.dirty:
            return
        with open(self.path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=self.fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(self.rows)
        self._saved = [dict(r) for r in self.rows]
        self._dirty = False


class MapGrid:
    """A chapter map: maps/chNN_name.csv, 64 tile numbers per row (the last row may be shorter)."""
    WIDTH = 64

    def __init__(self, path):
        self.path = path
        self.words = []
        with open(path, newline='') as f:
            for row in csv.reader(f):
                self.words += [int(v, 0) for v in row if v.strip()]
        self._saved = list(self.words)

    @property
    def dirty(self):
        return self.words != self._saved

    def save(self):
        if not self.dirty:
            return
        with open(self.path, 'w', newline='') as f:
            w = csv.writer(f)
            for r in range(0, len(self.words), self.WIDTH):
                w.writerow(self.words[r:r + self.WIDTH])
        self._saved = list(self.words)


EVT_LINE = re.compile(r'^(\s*)([0-9A-Fa-f]{6}|\+)(\s*:?\s*)((?:[0-9A-Fa-f]{2}|@N\d{5})(?:\s+(?:[0-9A-Fa-f]{2}|@N\d{5}))*)(\s*)(;.*)?$')
EVT_HEAD = re.compile(r'^==\s*(.*?)\s*@([0-9A-Fa-f]{6})')


class EvtFile:
    """An events/*.evt file kept as its lines, so edits change just the command's bytes."""

    def __init__(self, path):
        self.path = path
        with open(path, encoding='utf-8') as f:
            self.lines = f.read().split('\n')
        self._saved = list(self.lines)
        self.version = 0

    @property
    def dirty(self):
        return self.lines != self._saved

    def blocks(self):
        """[{'label', 'start', 'cmds': [{'line', 'addr', 'hex', 'comment'}]}] (line numbers from 0)."""
        out, cur = [], None
        for i, line in enumerate(self.lines):
            h = EVT_HEAD.match(line)
            if h:
                cur = {'label': h.group(1), 'start': h.group(2).upper(), 'cmds': []}
                out.append(cur)
                continue
            if line.lstrip().startswith(';') or cur is None:
                continue
            m = EVT_LINE.match(line)
            if m:
                cur['cmds'].append({'line': i, 'addr': None if m.group(2) == '+' else m.group(2).upper(),
                                    'hex': ' '.join(t if t.startswith('@') else t.upper() for t in m.group(4).split()),
                                    'comment': (m.group(6) or '').lstrip(';').strip()})
        return out

    def set_command(self, i, hexs, comment):
        """Replace the bytes (and the comment) of the command on line i; returns the new line."""
        m = EVT_LINE.match(self.lines[i])
        if not m:
            raise ValueError(f'line {i + 1} of {os.path.basename(self.path)} is not a command')
        addr = m.group(2)
        return ('%s: %-24s ; %s' % (addr, hexs, comment)).rstrip() if addr != '+' else ('+ %-24s ; %s' % (hexs, comment)).rstrip()

    def save(self):
        if not self.dirty:
            return
        with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(self.lines))
        self._saved = list(self.lines)


class Dialogue:
    """events/dialogue.txt: one block per message, '@ADDR ; where' then the text. File line breaks
    don't count (the game's line break is {02}); blank lines and lines starting with ';' are skipped."""

    def __init__(self, path):
        self.path = path
        self.head = []                 # lines before the first message
        self.order = []                # message keys ('60597B') in file order
        self.where = {}                # key -> the comment after the address
        self.text = {}                 # key -> message text with its {..} codes, no line breaks
        cur = None
        with open(path, encoding='utf-8') as f:
            for line in f.read().split('\n'):
                if line.startswith('@'):
                    cur = line[1:7].upper()
                    self.order.append(cur)
                    self.where[cur] = line[7:].strip().lstrip(';').strip()
                    self.text[cur] = ''
                elif cur is None:
                    self.head.append(line)
                elif line.startswith(';') or line.strip() == '':
                    continue
                else:
                    self.text[cur] += line
        while self.head and self.head[-1] == '':
            self.head.pop()
        self._saved = dict(self.text)

    @property
    def dirty(self):
        return self.text != self._saved

    def new_key(self):
        n = 1
        while 'N%05d' % n in self.text:
            n += 1
        return 'N%05d' % n

    @staticmethod
    def file_lines(text):
        """The text as file lines: a break after each {02} and {01}; no line may be blank or start with ';'."""
        out = []
        for part in re.split(r'(?<=\{02\})|(?<=\{01\})', text):
            if not part:
                continue
            if out and (part.strip() == '' or part.startswith(';')):
                out[-1] += part
            else:
                out.append(part)
        return out

    def save(self):
        if not self.dirty:
            return
        lines = list(self.head) + ['']
        for k in self.order:
            lines.append('@%s  ; %s' % (k, self.where[k]) if self.where[k] else '@' + k)
            lines += self.file_lines(self.text[k])
            lines.append('')
        with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        self._saved = dict(self.text)


class Project:
    """Edits are grouped: one undo step can change several cells or map tiles at once."""

    def __init__(self, path):
        self.path = path
        self.tables = {}
        self.maps = {}
        self.evts = {}
        self._dialogue = None
        self.undo_stack = []      # [[op, ...]]: ('cell', table, row, field, old, new) | ('map', ch, i, old, new)
        #                           | ('rows', table, start, old_rows, new_rows)
        #                           | ('evt', file, line, old, new) | ('msg', key, old, new)
        self.redo_stack = []

    def table(self, name):
        if name not in self.tables:
            p = os.path.join(self.path, name + '.csv')
            if not os.path.exists(p):
                return None
            self.tables[name] = CsvTable(p)
        return self.tables[name]

    def map_files(self):
        d = os.path.join(self.path, 'maps')
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.startswith('ch') and f.endswith('.csv'))

    def map(self, ch):
        if ch not in self.maps:
            for f in self.map_files():
                if f.startswith('ch%02d_' % ch):
                    self.maps[ch] = MapGrid(os.path.join(self.path, 'maps', f))
                    break
            else:
                return None
        return self.maps[ch]

    def evt_files(self):
        d = os.path.join(self.path, 'events')
        return sorted(f for f in os.listdir(d) if f.endswith('.evt')) if os.path.isdir(d) else []

    def evt(self, name):
        if name not in self.evts:
            if name not in self.evt_files():
                return None
            self.evts[name] = EvtFile(os.path.join(self.path, 'events', name))
        return self.evts[name]

    def dialogue(self):
        if self._dialogue is None:
            p = os.path.join(self.path, 'events', 'dialogue.txt')
            if not os.path.exists(p):
                return None
            self._dialogue = Dialogue(p)
        return self._dialogue

    def _files(self):
        return (list(self.tables.values()) + list(self.maps.values()) + list(self.evts.values())
                + ([self._dialogue] if self._dialogue else []))

    def dirty(self):
        return any(f.dirty for f in self._files())

    def save(self):
        for f in self._files():
            f.save()

    # -- edits with undo
    def _apply(self, op, back=False):
        if op[0] == 'cell':
            _, table, row, field, old, new = op
            t = self.table(table)
            t.rows[row][field] = old if back else new
            t.dirty = True
        elif op[0] == 'map':
            _, ch, i, old, new = op
            self.map(ch).words[i] = old if back else new
        elif op[0] == 'evt':
            _, name, i, old, new = op
            f = self.evt(name)
            f.lines[i] = old if back else new
            f.version += 1
        elif op[0] == 'lines':
            _, name, i, old, new = op
            f = self.evt(name)
            a, b = (new, old) if back else (old, new)
            assert f.lines[i:i + len(a)] == list(a), 'event file changed under an undo step'
            f.lines[i:i + len(a)] = list(b)
            f.version += 1
        elif op[0] == 'rows':                  # ('rows', table, start, old rows, new rows)
            _, table, i, old, new = op
            t = self.table(table)
            a, b = (new, old) if back else (old, new)
            assert t.rows[i:i + len(a)] == [dict(r) for r in a], 'table changed under an undo step'
            t.rows[i:i + len(a)] = [dict(r) for r in b]
            t.dirty = True
        elif op[0] in ('msgadd', 'msgdel'):
            _, key, where, text = op
            d = self.dialogue()
            if back == (op[0] == 'msgadd'):
                d.order.remove(key)
                del d.text[key], d.where[key]
            else:
                d.order.append(key)
                d.text[key], d.where[key] = text, where
        else:
            _, key, old, new = op
            self.dialogue().text[key] = old if back else new

    def _record(self, ops):
        if ops:
            self.undo_stack.append(ops)
            self.redo_stack.clear()

    def set(self, table, row, field, value, record=True):
        return bool(self.set_many([(table, row, field, value)]))

    def set_many(self, changes):
        """[(table, row, field, value)] as one undo step; returns the ops applied."""
        ops = []
        for table, row, field, value in changes:
            t = self.table(table)
            if t is None or not (0 <= row < len(t.rows)) or field not in t.fields:
                raise KeyError(f'{table}[{row}].{field}')
            old = t.rows[row].get(field, '')
            if old != value:
                op = ('cell', table, row, field, old, value)
                self._apply(op)
                ops.append(op)
        self._record(ops)
        return ops

    def paint(self, ch, cells):
        """[(index, word)] on chapter ch's map as one undo step. word & $3FF is the metatile; the
        bits above it are per-cell area flags, which the painter keeps."""
        m = self.map(ch)
        if m is None:
            raise KeyError(f'no map for chapter {ch}')
        ops = []
        for i, v in cells:
            if not (0 <= i < len(m.words)) or not (0 <= v < 0x10000):
                raise ValueError(f'tile {v} at cell {i} is out of range')
            if m.words[i] != v:
                op = ('map', ch, i, m.words[i], v)
                self._apply(op)
                ops.append(op)
        self._record(ops)
        return ops

    def set_command(self, name, line, hexs, comment):
        """New bytes for one event command (same length; the build checks the layout)."""
        f = self.evt(name)
        if f is None:
            raise KeyError(f'no events file {name}')
        new = f.set_command(line, hexs, comment)
        ops = []
        if f.lines[line] != new:
            op = ('evt', name, line, f.lines[line], new)
            self._apply(op)
            ops.append(op)
        self._record(ops)
        return ops

    def edit(self, ops):
        """Apply a list of ('lines', file, start, old, new) / ('msgadd', key, where, text) /
        ('evt', ...) ops as one undo step; line numbers are as they are when each op runs."""
        done = []
        try:
            for op in ops:
                self._apply(op)
                done.append(op)
        except Exception:
            for op in reversed(done):
                self._apply(op, back=True)
            raise
        self._record(done)
        return done

    def set_message(self, key, text):
        d = self.dialogue()
        if d is None or key not in d.text:
            raise KeyError(f'no message @{key}')
        ops = []
        if d.text[key] != text:
            op = ('msg', key, d.text[key], text)
            self._apply(op)
            ops.append(op)
        self._record(ops)
        return ops

    def undo(self):
        if not self.undo_stack:
            return None
        ops = self.undo_stack.pop()
        for op in reversed(ops):
            self._apply(op, back=True)
        self.redo_stack.append(ops)
        return ops

    def redo(self):
        if not self.redo_stack:
            return None
        ops = self.redo_stack.pop()
        for op in ops:
            self._apply(op)
        self.undo_stack.append(ops)
        return ops

    # lookups for the friendly widgets
    def class_names(self):
        t = self.table('classes')
        return [f"{r['index']} {r['_name']}" for r in t.rows] if t else []

    def unit_names(self):
        out = []
        for n in ('units_playable', 'units_children', 'units_npc'):
            t = self.table(n)
            if t:
                out += [r['_name'] or r['index'] for r in t.rows]
        return sorted(set(x for x in out if x))

    def instance_names(self):
        t = self.table('item_instances')
        return [f"{r['instance']} {r['_item_name']}" for r in t.rows] + ['255 (none)'] if t else []

    def item_type_names(self):
        out = []
        for n in ('items', 'rings'):
            t = self.table(n)
            if t:
                out += [f"{r['index']} {r['_name']}" for r in t.rows]
        return out + ['255 (none)']

    def skill_names(self):
        t = self.table('skills')
        return [r['name'] for r in t.rows] if t else []
