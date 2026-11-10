#!/usr/bin/env python3
"""fe4kit editor: starts Builder of the Holy War (the visual editor); "classic" starts the table-style editor below,
and extract / build / diff / rando run the command-line tools."""
import csv
import io
import json
import os
import queue
import random
import subprocess
import sys
import threading
import traceback
import webbrowser

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

HERE = os.path.dirname(os.path.abspath(getattr(sys, '_MEIPASS', None) and sys.executable or __file__))
KIT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KIT)

import fe4lib as L       # noqa: E402
import fe4hack           # noqa: E402
import fe4rando as R     # noqa: E402

APP = 'Builder of the Holy War (classic editor)'
VERSION = '20'

# ---------------------------------------------------------------- what the sidebar shows
SECTIONS = [
    ('Characters', [
        ('Generation 1 & substitutes', 'units_playable'),
        ('Children (generation 2)', 'units_children'),
        ('NPCs and bosses', 'units_npc'),
        ('Enemy types', 'units_generic'),
    ]),
    ('Generation 2', [
        ('Love affinities', 'lovers'),
        ('Inheritance rules', 'gen2_rules'),
    ]),
    ('Game data', [
        ('Classes', 'classes'),
        ('Weapons and staves', 'items'),
        ('Rings', 'rings'),
        ('Item instances', 'item_instances'),
        ('Skills', 'skills'),
        ('Names', 'names'),
    ]),
    ('World', [
        ('Deployments', 'deploy'),
        ('Castles and villages', 'locations'),
        ('Arena', 'arena'),
        ('Armies', 'armies'),
    ]),
    ('Scripts', [
        ('Chapter events and scenes', ':events'),
        ('Dialogue', ':dialogue'),
        ('Enemy AI', ':ai'),
    ]),
    ('Tools', [
        ('Maps', ':maps'),
        ('Randomizer', ':rando'),
    ]),
]
ADDABLE = {'units_generic', 'units_children', 'deploy'}

HELP = {
    'units_playable': 'Gen-1 characters and the gen-2 substitutes. Stats are bonuses on top of the class; hp and lck are absolute.',
    'units_children': 'The children. Their stats come from their parents. "parent" ties a child to anyone, man or woman; '
                      'add a row (id 769+) for a brand-new child.',
    'units_npc': 'Named NPCs and bosses with their own stats, growths and blood.',
    'units_generic': 'Class-based units: most enemies. Add rows (id 769+) for new enemy types.',
    'lovers': 'Love at chapter start (points, 499, or "no") and growth per turn for every pair. 500 = lovers.',
    'gen2_rules': "Children's gold, and the cap on inherited stats.",
    'classes': 'Class bases, growths, weapon ranks (A/B/C/-), movement and class skills.',
    'items': 'Weapons and staves.',
    'rings': 'Rings and their bonuses.',
    'item_instances': 'Every physical item in the campaign and which item type it is.',
    'skills': "FE4's skills and new ones from later games. 'units' / 'classes' give a new skill without bits.",
    'names': 'Names as drawn in game. Character slots 570-575 are free for new units.',
    'deploy': 'Where units appear: list.entry, unit id, x/y, orders. Add rows with the next entry number.',
    'locations': 'Castles and villages: shops, armory stock, village gold.',
    'arena': 'Arena opponents per chapter and rank.',
    'armies': 'Armies: members and castles held.',
}

STAT_HINT = {'gender': '0 = male, 1 = female', 'heir': 'father or mother', 'joins': 'chapter 6-11 (new children)',
             'always': 'yes = born even if that parent died', 'portrait': 'number, or a unit name to borrow theirs'}


from fe4project import settings_path, load_settings, save_settings, CsvTable, Project  # noqa: E402,F401


# ---------------------------------------------------------------- small widgets
class Checklist(tk.Toplevel):
    """Pick several names: returns 'a;b;c'."""
    def __init__(self, master, title, names, current, sep=';'):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.result = None
        cur = {x.strip() for x in current.split(sep) if x.strip()}
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill='both', expand=True)
        canvas = tk.Canvas(frm, width=260, height=360, highlightthickness=0)
        sb = ttk.Scrollbar(frm, orient='vertical', command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.vars = []
        extra = [x for x in cur if x not in names]
        for n in list(names) + extra:
            v = tk.BooleanVar(value=n in cur)
            ttk.Checkbutton(inner, text=n, variable=v).pack(anchor='w')
            self.vars.append((n, v))
        bf = ttk.Frame(self, padding=(8, 0, 8, 8))
        bf.pack(fill='x')
        ttk.Button(bf, text='OK', command=lambda: self.done(sep)).pack(side='right')
        ttk.Button(bf, text='Cancel', command=self.destroy).pack(side='right', padx=4)
        self.grab_set()

    def done(self, sep):
        self.result = sep.join(n for n, v in self.vars if v.get())
        self.destroy()


class BloodDialog(tk.Toplevel):
    def __init__(self, master, current):
        super().__init__(master)
        self.title('Holy blood')
        self.transient(master)
        self.result = None
        cur = {}
        for p in current.split(';'):
            if ':' in p:
                b, k = p.split(':')
                cur[b.strip()] = k.strip()
        frm = ttk.Frame(self, padding=8)
        frm.pack()
        self.vars = []
        for i, b in enumerate(L.BLOODS):
            ttk.Label(frm, text=b, width=10).grid(row=i, column=0, sticky='w')
            v = tk.StringVar(value=cur.get(b, ''))
            for j, (lab, val) in enumerate((('none', ''), ('minor', 'minor'), ('major', 'major'))):
                ttk.Radiobutton(frm, text=lab, value=val, variable=v).grid(row=i, column=1 + j, padx=3)
            self.vars.append((b, v))
        bf = ttk.Frame(self, padding=(8, 0, 8, 8))
        bf.pack(fill='x')
        ttk.Button(bf, text='OK', command=self.done).pack(side='right')
        ttk.Button(bf, text='Cancel', command=self.destroy).pack(side='right', padx=4)
        self.grab_set()

    def done(self):
        self.result = ';'.join(f'{b}:{v.get()}' for b, v in self.vars if v.get())
        self.destroy()


# ---------------------------------------------------------------- table page
class TablePage(ttk.Frame):
    def __init__(self, master, app, name):
        super().__init__(master)
        self.app = app
        self.name = name
        self.table = app.project.table(name)
        self.cur = None
        self.widgets = {}
        if self.table is None:
            ttk.Label(self, text=f'{name}.csv is not in this project.', padding=20).pack()
            return
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill='x')
        ttk.Label(top, text=HELP.get(name, ''), foreground='#555', wraplength=900).pack(side='left')
        bar = ttk.Frame(self, padding=(8, 0, 8, 4))
        bar.pack(fill='x')
        ttk.Label(bar, text='Filter:').pack(side='left')
        self.filter = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.filter, width=30)
        e.pack(side='left', padx=4)
        self.filter.trace_add('write', lambda *a: self.fill())
        if name in ADDABLE:
            ttk.Button(bar, text='Add row', command=self.add_row).pack(side='right')
            ttk.Button(bar, text='Duplicate', command=self.dup_row).pack(side='right', padx=4)
            ttk.Button(bar, text='Delete', command=self.del_row).pack(side='right')
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        right = ttk.Frame(body, width=430)
        right.pack(side='right', fill='y')
        right.pack_propagate(False)
        left = ttk.Frame(body)
        left.pack(side='left', fill='both', expand=True, padx=(0, 8))
        cols = self.table.fields
        self.tree = ttk.Treeview(left, columns=cols, show='headings', selectmode='browse', height=8)
        first = cols[:1] + [c for c in cols[1:] if c.startswith('_')] + [c for c in cols[1:] if not c.startswith('_')]
        self.tree.configure(displaycolumns=first)
        for c in cols:
            self.tree.heading(c, text=c)
            w = 60 if c in ('index', 'id', 'hp', 'level') or c.startswith(('g_', 'rank_')) else 90
            if c in ('_name', 'name', '_class_name', '_items', 'skills', 'description', '_notes', 'units'):
                w = 130
            self.tree.column(c, width=w, stretch=False)
        ys = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        xs = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.select())
        ttk.Label(right, text='Selected row', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=6)
        self.form_canvas = tk.Canvas(right, highlightthickness=0, width=410)
        fsb = ttk.Scrollbar(right, orient='vertical', command=self.form_canvas.yview)
        self.form = ttk.Frame(self.form_canvas, padding=6)
        self.form.bind('<Configure>', lambda e: self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')))
        self.form_canvas.create_window((0, 0), window=self.form, anchor='nw')
        self.form_canvas.configure(yscrollcommand=fsb.set)
        self.form_canvas.pack(side='left', fill='both', expand=True)
        fsb.pack(side='right', fill='y')
        wheel = lambda e: self.form_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')   # noqa: E731
        self.form_canvas.bind('<Enter>', lambda e: self.form_canvas.bind_all('<MouseWheel>', wheel))
        self.form_canvas.bind('<Leave>', lambda e: self.form_canvas.unbind_all('<MouseWheel>'))
        self.build_form()
        self.fill()

    # -- list
    def fill(self):
        f = self.filter.get().lower()
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.table.rows):
            vals = [r.get(c, '') for c in self.table.fields]
            if f and not any(f in str(v).lower() for v in vals):
                continue
            self.tree.insert('', 'end', iid=str(i), values=vals)

    def select(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.commit()
        self.cur = int(sel[0])
        r = self.table.rows[self.cur]
        for c, (var, _) in self.widgets.items():
            v = r.get(c, '')
            labels = self.coded.get(c)
            if labels:
                v = next((x for x in labels if x.split(' ', 1)[0] == v), v)
            var.set(v)
        self.form_canvas.yview_moveto(0)

    # -- form
    def build_form(self):
        p = self.app.project
        self.coded = {}
        choices = {'class': p.class_names}
        if self.name in ('units_playable', 'units_children'):
            item_choices = p.instance_names
        else:
            item_choices = p.item_type_names
        for c in self.table.fields:
            if c.startswith('_') and c not in ('_name',):
                continue
        row = 0
        for c in self.table.fields:
            ro = c.startswith('_') or c == self.table.fields[0]
            ttk.Label(self.form, text=c, foreground='#888' if ro else '#000').grid(row=row, column=0, sticky='w', pady=1)
            var = tk.StringVar()
            if ro:
                w = ttk.Label(self.form, textvariable=var, foreground='#666', wraplength=240)
            elif c == 'class' or (c == 'item_type' and self.name == 'item_instances'):
                vals = choices['class']() if c == 'class' else p.item_type_names()
                w = self.combo(var, vals, col=c)
            elif c in ('item1', 'item2', 'item3'):
                w = self.combo(var, item_choices(), col=c)
            elif c in ('parent', 'substitute'):
                w = self.combo(var, [''] + p.unit_names(), keep_text=True)
            elif c == 'gender':
                w = self.combo(var, ['0 male', '1 female'], col=c)
            elif c == 'heir':
                w = ttk.Combobox(self.form, textvariable=var, values=['father', 'mother'], width=28)
            elif c.startswith('rank') or c == 'rank':
                w = ttk.Combobox(self.form, textvariable=var, values=['A', 'B', 'C', '-', '*'], width=28)
            elif c in ('skills', 'inherit_skills') or (c == 'units' and self.name == 'skills') or \
                    (c == 'classes' and self.name == 'skills'):
                w = self.picker(var, c)
            elif c == 'holy_blood':
                w = self.picker(var, c)
            else:
                w = ttk.Entry(self.form, textvariable=var, width=30)
            w.grid(row=row, column=1, sticky='w', pady=1, padx=4)
            if c in STAT_HINT:
                ttk.Label(self.form, text=STAT_HINT[c], foreground='#888').grid(row=row, column=2, sticky='w')
            self.widgets[c] = (var, ro)
            row += 1
        ttk.Button(self.form, text='Apply', command=self.commit).grid(row=row, column=1, sticky='w', pady=8, padx=4)

    def combo(self, var, values, keep_text=False, col=None):
        if col and not keep_text:
            self.coded[col] = list(values)
        return ttk.Combobox(self.form, textvariable=var, values=values, width=34)

    def picker(self, var, col):
        f = ttk.Frame(self.form)
        ttk.Entry(f, textvariable=var, width=25).pack(side='left')

        def go():
            if col == 'holy_blood':
                d = BloodDialog(self, var.get())
            elif col == 'units':
                d = Checklist(self, 'Units', self.app.project.unit_names(), var.get())
            elif col == 'classes' and self.name == 'skills':
                d = Checklist(self, 'Classes', [c.split(' ', 1)[1] for c in self.app.project.class_names()], var.get())
            else:
                d = Checklist(self, 'Skills', self.app.project.skill_names(), var.get())
            self.wait_window(d)
            if d.result is not None:
                var.set(d.result)
        ttk.Button(f, text='…', width=3, command=go).pack(side='left', padx=2)
        return f

    def commit(self):
        if self.cur is None or self.cur >= len(self.table.rows):
            return
        r = self.table.rows[self.cur]
        changed = False
        for c, (var, ro) in self.widgets.items():
            if ro:
                continue
            v = var.get()
            if c in self.coded and ' ' in v and v.split(' ', 1)[0].lstrip('-').isdigit():
                v = v.split(' ', 1)[0]
            if r.get(c, '') != v:
                r[c] = v
                changed = True
        if changed:
            self.table.dirty = True
            self.tree.item(str(self.cur), values=[r.get(c, '') for c in self.table.fields])
            self.app.set_dirty()

    # -- rows
    def next_index(self):
        if self.name == 'deploy':
            return None
        ids = [int(r[self.table.fields[0]]) for r in self.table.rows if r[self.table.fields[0]].isdigit()]
        n = max(ids) + 1 if ids else 1
        p = self.app.project
        allids = []
        for t in ('units_generic', 'units_children'):
            tt = p.table(t)
            if tt:
                allids += [int(r['index']) for r in tt.rows if r['index'].isdigit()]
        n = max(allids) + 1
        return max(n, L.RESERVED_IDS + 1)

    def add_row(self, base=None):
        r = dict(base) if base else {c: '' for c in self.table.fields}
        if self.name == 'deploy':
            src = base or (self.table.rows[self.cur] if self.cur is not None else self.table.rows[-1])
            li = src['index'].split('.')[0]
            n = max(int(x['index'].split('.')[1]) for x in self.table.rows if x['index'].split('.')[0] == li) + 1
            r = dict(src)
            r['index'] = f'{li}.{n}'
        else:
            r[self.table.fields[0]] = str(self.next_index())
            if self.name == 'units_children':
                r.update({'char_id': '', 'name_id': '', 'slot': '', 'born_flag': ''})
        self.table.rows.append(r)
        self.table.dirty = True
        self.app.set_dirty()
        self.fill()
        iid = str(len(self.table.rows) - 1)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def dup_row(self):
        if self.cur is None:
            return
        self.add_row(self.table.rows[self.cur])

    def del_row(self):
        if self.cur is None:
            return
        r = self.table.rows[self.cur]
        key = r[self.table.fields[0]]
        if self.name != 'deploy' and int(key) <= L.GAME_UNITS:
            messagebox.showinfo(APP, "The game's own units can't be deleted, only new ones (769+).")
            return
        if not messagebox.askyesno(APP, f'Delete row {key}?'):
            return
        del self.table.rows[self.cur]
        self.cur = None
        self.table.dirty = True
        self.app.set_dirty()
        self.fill()


# ---------------------------------------------------------------- text page (scripts)
class TextPage(ttk.Frame):
    def __init__(self, master, app, kind):
        super().__init__(master)
        self.app = app
        self.kind = kind
        self.path = None
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        ev = os.path.join(app.project.path, 'events')
        if kind == ':events':
            files = sorted(f for f in os.listdir(ev) if f.endswith('.evt')) if os.path.isdir(ev) else []
            self.files = [os.path.join(ev, f) for f in files]
            hint = ('Each line is a command: edit the hex. A line starting with + adds a command; '
                    'delete a line to remove one. Blocks that grow move to free space.')
        elif kind == ':dialogue':
            self.files = [os.path.join(ev, 'dialogue.txt')]
            hint = 'Every message. Change the words freely; keep the {..} codes. {02} = new line, {01} = end.'
        else:
            self.files = [os.path.join(app.project.path, 'ai_orders.evt')]
            hint = 'Enemy AI programs: which castle to seize, which turn to march, what to attack.'
        self.pick = ttk.Combobox(bar, values=[os.path.basename(f) for f in self.files], width=30, state='readonly')
        self.pick.pack(side='left')
        self.pick.bind('<<ComboboxSelected>>', lambda e: self.load(self.files[self.pick.current()]))
        ttk.Label(bar, text='Find:').pack(side='left', padx=(16, 2))
        self.find = tk.StringVar()
        fe = ttk.Entry(bar, textvariable=self.find, width=24)
        fe.pack(side='left')
        fe.bind('<Return>', lambda e: self.search())
        ttk.Button(bar, text='Next', command=self.search).pack(side='left', padx=4)
        ttk.Button(bar, text='Save', command=self.save).pack(side='right')
        ttk.Label(self, text=hint, foreground='#555', padding=(8, 0), wraplength=900).pack(anchor='w')
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill='both', expand=True)
        self.text = tk.Text(frm, wrap='none', undo=True, font=('Consolas', 10))
        ys = ttk.Scrollbar(frm, orient='vertical', command=self.text.yview)
        xs = ttk.Scrollbar(frm, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.text.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        self.text.tag_configure('found', background='#ffe08a')
        self.text.bind('<<Modified>>', self.modified)
        if self.files:
            self.pick.current(0)
            self.load(self.files[0])

    def load(self, path):
        if self.path and self.text.edit_modified():
            if messagebox.askyesno(APP, f'Save {os.path.basename(self.path)} first?'):
                self.save()
        self.path = path
        self.text.delete('1.0', 'end')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                self.text.insert('1.0', f.read())
        self.text.edit_modified(False)

    def modified(self, e=None):
        if self.text.edit_modified():
            self.app.set_dirty()

    def save(self):
        if not self.path:
            return
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(self.text.get('1.0', 'end-1c'))
        self.text.edit_modified(False)
        self.app.status(f'saved {os.path.basename(self.path)}')

    def search(self):
        s = self.find.get()
        if not s:
            return
        self.text.tag_remove('found', '1.0', 'end')
        start = self.text.index('insert +1c')
        pos = self.text.search(s, start, nocase=True, stopindex='end') or self.text.search(s, '1.0', nocase=True)
        if pos:
            end = f'{pos}+{len(s)}c'
            self.text.tag_add('found', pos, end)
            self.text.mark_set('insert', end)
            self.text.see(pos)

    def dirty(self):
        return self.path and self.text.edit_modified()


# ---------------------------------------------------------------- maps page
class MapsPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=16)
        self.app = app
        ttk.Label(self, text='Maps', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(self, wraplength=700, foreground='#444', text=(
            'Each battlefield is a CSV of tile numbers in the maps folder, with a picture of the map and its tile '
            'sheet. The map painter opens in your browser: load a map CSV and its _tiles.png, paint, and save the '
            'CSV back into the maps folder.')).pack(anchor='w', pady=8)
        b = ttk.Frame(self)
        b.pack(anchor='w')
        ttk.Button(b, text='Open the map painter', command=self.painter).pack(side='left')
        ttk.Button(b, text='Open the maps folder', command=self.folder).pack(side='left', padx=8)
        mp = os.path.join(app.project.path, 'maps')
        lst = tk.Listbox(self, height=14, width=50)
        lst.pack(anchor='w', pady=12)
        if os.path.isdir(mp):
            for f in sorted(os.listdir(mp)):
                if f.endswith('.csv'):
                    lst.insert('end', f)

    def painter(self):
        p = os.path.join(KIT, 'map_editor.html')
        webbrowser.open('file:///' + p.replace('\\', '/'))

    def folder(self):
        open_folder(os.path.join(self.app.project.path, 'maps'))


def open_folder(p):
    if sys.platform.startswith('win'):
        os.startfile(p)          # noqa
    else:
        webbrowser.open('file://' + p)


# ---------------------------------------------------------------- randomizer page
class RandoPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        f = ttk.Frame(canvas, padding=16)
        f.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=f, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        ttk.Label(f, text='Randomizer', font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(f, foreground='#444', wraplength=760, text=(
            'Makes a randomized ROM (and a spoiler log) from the clean game or from the open project. '
            'Children follow their new parents, classes keep holy weapons usable, and the result is checked by the '
            'same build as any hack.')).grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 12))
        r = 2
        ttk.Label(f, text='Preset').grid(row=r, column=0, sticky='w')
        self.preset = ttk.Combobox(f, values=list(R.PRESETS), state='readonly', width=16)
        self.preset.set('standard')
        self.preset.grid(row=r, column=1, sticky='w')
        self.preset.bind('<<ComboboxSelected>>', lambda e: self.apply_preset())
        r += 1
        ttk.Label(f, text='Seed').grid(row=r, column=0, sticky='w')
        sf = ttk.Frame(f)
        sf.grid(row=r, column=1, sticky='w')
        self.seed = tk.StringVar(value=str(random.randrange(1, 10 ** 9)))
        ttk.Entry(sf, textvariable=self.seed, width=14).pack(side='left')
        ttk.Button(sf, text='New', command=lambda: self.seed.set(str(random.randrange(1, 10 ** 9)))).pack(side='left',
                                                                                                         padx=4)
        r += 1
        self.source = tk.StringVar(value='clean')
        ttk.Radiobutton(f, text='Start from the clean game', value='clean', variable=self.source).grid(
            row=r, column=1, sticky='w')
        r += 1
        ttk.Radiobutton(f, text='Start from the open project (your hack)', value='project',
                        variable=self.source).grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        r += 1
        self.vars = {}
        for k, (d, kind, rng, label, hlp) in R.OPTIONS.items():
            ttk.Label(f, text=label).grid(row=r, column=0, sticky='w', pady=2)
            v = tk.StringVar(value=str(d))
            if kind == 'int':
                w = ttk.Spinbox(f, from_=rng[0], to=rng[1], textvariable=v, width=8)
            else:
                w = ttk.Combobox(f, values=rng, textvariable=v, state='readonly', width=14)
            w.grid(row=r, column=1, sticky='w', padx=6)
            ttk.Label(f, text=hlp, foreground='#777', wraplength=440).grid(row=r, column=2, sticky='w')
            self.vars[k] = v
            r += 1
        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky='ew', pady=8)
        r += 1
        bf = ttk.Frame(f)
        bf.grid(row=r, column=0, columnspan=3, sticky='w')
        ttk.Button(bf, text='Randomize and build ROM…', command=self.build).pack(side='left')
        ttk.Button(bf, text='Randomize into a new project…', command=self.to_project).pack(side='left', padx=8)

    def apply_preset(self):
        o = R.defaults(self.preset.get())
        for k, v in o.items():
            self.vars[k].set(str(v))

    def opts(self):
        o = {}
        for k, v in self.vars.items():
            kind = R.OPTIONS[k][1]
            o[k] = int(v.get()) if kind == 'int' else v.get()
        return R.check(o)

    def seed_val(self):
        try:
            return int(self.seed.get())
        except ValueError:
            return abs(hash(self.seed.get())) % 10 ** 9

    def build(self):
        rom = self.app.need_rom()
        if not rom:
            return
        out = filedialog.asksaveasfilename(title='Save the randomized ROM', defaultextension='.smc',
                                           initialfile=f'fe4_rando_{self.seed.get()}.smc',
                                           filetypes=[('SNES ROM', '*.smc *.sfc')])
        if not out:
            return
        try:
            opts = self.opts()
        except ValueError as e:
            messagebox.showerror(APP, str(e))
            return
        proj = None
        if self.source.get() == 'project':
            self.app.save_all()
            proj = self.app.project.path
        seed = self.seed_val()
        ips = os.path.splitext(out)[0] + '.ips'
        self.app.run_job('Randomizing', lambda: R.randomize_rom(rom, out, seed, opts, proj, ips),
                         done=lambda res: self.app.status(f'seed {seed}: wrote {out}, the .ips and the spoiler log'))

    def to_project(self):
        rom = self.app.need_rom()
        if not rom:
            return
        d = filedialog.askdirectory(title='Folder for the randomized project (it will be created)')
        if not d:
            return
        try:
            opts = self.opts()
        except ValueError as e:
            messagebox.showerror(APP, str(e))
            return
        name = simpledialog.askstring(APP, 'Project name:', initialvalue=f'rando_{self.seed.get()}')
        if not name:
            return
        out = os.path.join(d, name)
        src_proj = self.app.project.path if self.source.get() == 'project' else None
        seed = self.seed_val()

        def job():
            import tempfile
            import shutil
            src = src_proj
            tmp = None
            if src is None:
                tmp = tempfile.mkdtemp()
                src = os.path.join(tmp, 'clean')
                fe4hack.extract(rom, src)
            R.randomize_project(src, out, seed, opts)
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
            return out
        self.app.run_job('Randomizing', job, done=lambda res: self.app.open_project(out))


# ---------------------------------------------------------------- the app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP)
        self.geometry('1280x800')
        self.minsize(900, 600)
        self.settings = load_settings()
        self.project = None
        self.page = None
        self.pages = {}
        self.jobq = queue.Queue()
        self.busy = False
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        elif 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Treeview', rowheight=22)
        self.make_menu()
        self.make_layout()
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        last = self.settings.get('project')
        if last and os.path.isdir(last):
            self.open_project(last)
        else:
            self.welcome()
        self.after(100, self.poll)

    # -- layout
    def make_menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label='New project from ROM…', command=self.new_project)
        fm.add_command(label='Open project…', command=self.choose_project)
        fm.add_command(label='Save', accelerator='Ctrl+S', command=self.save_all)
        fm.add_separator()
        fm.add_command(label='Set the clean ROM…', command=self.choose_rom)
        fm.add_command(label='Open the project folder', command=lambda: self.project and open_folder(self.project.path))
        fm.add_separator()
        fm.add_command(label='Quit', command=self.quit_app)
        m.add_cascade(label='File', menu=fm)
        bm = tk.Menu(m, tearoff=0)
        bm.add_command(label='Build ROM and patch…', accelerator='F5', command=self.build)
        bm.add_command(label='Test generation 2 (start at chapter 6)…', command=self.build_ch6)
        bm.add_separator()
        bm.add_command(label='Test play in the PC port', accelerator='F6', command=self.test_play)
        bm.add_command(label='Test play generation 2 in the PC port (chapter 6)', command=lambda: self.test_play(True))
        bm.add_command(label='Set where the PC port is…', command=lambda: self.port_exe(force=True))
        bm.add_separator()
        self.hover_var = tk.BooleanVar(value=bool(self.settings.get('hover_stats', False)))
        bm.add_checkbutton(label='Add unit stats to the map box (MT / HIT / AS / AVO)', variable=self.hover_var,
                           command=self.set_hover)
        m.add_cascade(label='Build', menu=bm)
        hm = tk.Menu(m, tearoff=0)
        hm.add_command(label='Read the manual (README)', command=self.readme)
        hm.add_command(label='About', command=lambda: messagebox.showinfo(
            APP, f'{APP} v{VERSION}\nFire Emblem: Genealogy of the Holy War hacking kit\n(Project Naga translation).'))
        m.add_cascade(label='Help', menu=hm)
        self.config(menu=m)
        self.bind('<Control-s>', lambda e: self.save_all())
        self.bind('<F5>', lambda e: self.build())
        self.bind('<F6>', lambda e: self.test_play())

    def make_layout(self):
        tb = ttk.Frame(self, padding=(8, 6))
        tb.pack(fill='x')
        self.title_lbl = ttk.Label(tb, text='No project', font=('Segoe UI', 11, 'bold'))
        self.title_lbl.pack(side='left')
        ttk.Button(tb, text='Test play', command=self.test_play).pack(side='right', padx=(6, 0))
        ttk.Button(tb, text='Build ROM', command=self.build).pack(side='right')
        ttk.Button(tb, text='Save', command=self.save_all).pack(side='right', padx=6)
        body = ttk.PanedWindow(self, orient='vertical')
        body.pack(fill='both', expand=True)
        top = ttk.PanedWindow(body, orient='horizontal')
        self.nav = ttk.Treeview(top, show='tree', selectmode='browse')
        self.nav.column('#0', width=220)
        top.add(self.nav, weight=0)
        self.content = ttk.Frame(top)
        top.add(self.content, weight=1)
        body.add(top, weight=8)
        logf = ttk.Frame(body)
        self.log = tk.Text(logf, height=5, font=('Consolas', 9), state='disabled', background='#f6f6f6')
        lsb = ttk.Scrollbar(logf, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side='left', fill='both', expand=True)
        lsb.pack(side='right', fill='y')
        self.log.tag_configure('err', foreground='#b00020')
        self.log.tag_configure('ok', foreground='#1b6e20')
        body.add(logf, weight=1)
        self.statusbar = ttk.Label(self, text='', padding=(8, 2), relief='sunken')
        self.statusbar.pack(fill='x')
        for sec, items in SECTIONS:
            pid = self.nav.insert('', 'end', text=sec, open=True)
            for label, key in items:
                self.nav.insert(pid, 'end', iid=key, text=label)
        self.nav.bind('<<TreeviewSelect>>', lambda e: self.show(self.nav.selection()[0]))

    def welcome(self):
        for w in self.content.winfo_children():
            w.destroy()
        f = ttk.Frame(self.content, padding=40)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=APP, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(f, foreground='#444', wraplength=640, text=(
            'Make Fire Emblem: Genealogy of the Holy War hacks. Start a project from your own copy of the game '
            '(the Project Naga translation): the editor reads everything out of it into a project folder. Edit, then '
            'Build to get a playable ROM and a shareable .ips patch.')).pack(anchor='w', pady=12)
        ttk.Button(f, text='New project from ROM…', command=self.new_project).pack(anchor='w', pady=4)
        ttk.Button(f, text='Open a project…', command=self.choose_project).pack(anchor='w', pady=4)
        ttk.Button(f, text='Randomizer…', command=self.rando_only).pack(anchor='w', pady=4)

    # -- project handling
    def need_rom(self):
        rom = self.settings.get('rom')
        if rom and os.path.exists(rom):
            return rom
        return self.choose_rom()

    def choose_rom(self):
        rom = filedialog.askopenfilename(title='Your clean FE4 ROM (Project Naga translation)',
                                         filetypes=[('SNES ROM', '*.smc *.sfc'), ('All files', '*.*')])
        if not rom:
            return None
        try:
            _, data = L.load_rom(rom)
        except OSError as e:
            messagebox.showerror(APP, str(e))
            return None
        if L.sha1(data) != L.EXPECTED_SHA1:
            if not messagebox.askyesno(APP, "This ROM isn't the one the kit was made for (FE4 with the Project Naga "
                                            "patch, unmodified). Use it anyway?"):
                return None
        self.settings['rom'] = rom
        save_settings(self.settings)
        return rom

    def new_project(self):
        rom = self.need_rom()
        if not rom:
            return
        d = filedialog.askdirectory(title='Where to put the project folder')
        if not d:
            return
        name = simpledialog.askstring(APP, 'Project name:', initialvalue='myhack')
        if not name:
            return
        out = os.path.join(d, name)
        if os.path.exists(out) and os.listdir(out):
            messagebox.showerror(APP, f'{out} already exists and is not empty.')
            return
        self.run_job('Reading the ROM', lambda: fe4hack.extract(rom, out), done=lambda r: self.open_project(out))

    def choose_project(self):
        d = filedialog.askdirectory(title='Open a project folder')
        if d:
            self.open_project(d)

    def open_project(self, d):
        if not os.path.exists(os.path.join(d, 'units_playable.csv')):
            messagebox.showerror(APP, f'{d} is not a kit project (no units_playable.csv).')
            return
        if self.project and not self.confirm_discard():
            return
        self.project = Project(d)
        self.pages = {}
        self.settings['project'] = d
        save_settings(self.settings)
        self.title_lbl.config(text=os.path.basename(d))
        self.title(f'{os.path.basename(d)} - {APP}')
        self.status(f'opened {d}')
        self.nav.selection_set('units_playable')

    def rando_only(self):
        if self.project is None:
            # the randomizer works without a project: use a throwaway one
            self.project = Project(os.path.expanduser('~'))
        self.show(':rando')

    def show(self, key):
        if key in [s for s, _ in SECTIONS] or self.project is None:
            return
        if self.page is not None:
            if isinstance(self.page, TablePage):
                self.page.commit()
            self.page.pack_forget()
        if key not in self.pages:
            if key == ':rando':
                p = RandoPage(self.content, self)
            elif key == ':maps':
                p = MapsPage(self.content, self)
            elif key.startswith(':'):
                p = TextPage(self.content, self, key)
            else:
                p = TablePage(self.content, self, key)
            self.pages[key] = p
        for w in self.content.winfo_children():
            if w not in self.pages.values():
                w.destroy()
        self.page = self.pages[key]
        self.page.pack(fill='both', expand=True)

    def set_dirty(self):
        self.title_lbl.config(text=os.path.basename(self.project.path) + ' *')

    def save_all(self):
        if self.project is None:
            return
        if isinstance(self.page, TablePage):
            self.page.commit()
        self.project.save()
        for p in self.pages.values():
            if isinstance(p, TextPage) and p.dirty():
                p.save()
        self.title_lbl.config(text=os.path.basename(self.project.path))
        self.status('saved')

    def confirm_discard(self):
        dirty = self.project.dirty() or any(isinstance(p, TextPage) and p.dirty() for p in self.pages.values())
        if not dirty:
            return True
        a = messagebox.askyesnocancel(APP, 'Save your changes first?')
        if a is None:
            return False
        if a:
            self.save_all()
        return True

    def quit_app(self):
        if self.project is None or self.confirm_discard():
            self.destroy()

    # -- building
    def build(self):
        if self.project is None:
            return
        rom = self.need_rom()
        if not rom:
            return
        self.save_all()
        last = self.settings.get('out', {}).get(self.project.path)
        out = filedialog.asksaveasfilename(
            title='Build: save the hacked ROM as', defaultextension='.smc',
            initialfile=os.path.basename(last) if last else os.path.basename(self.project.path) + '.smc',
            initialdir=os.path.dirname(last) if last else os.path.dirname(self.project.path),
            filetypes=[('SNES ROM', '*.smc *.sfc')])
        if not out:
            return
        self.settings.setdefault('out', {})[self.project.path] = out
        save_settings(self.settings)
        ips = os.path.splitext(out)[0] + '.ips'
        hover = self.hover_var.get()
        self.run_job('Building', lambda: fe4hack.build(rom, self.project.path, out, ips, hover),
                     done=lambda r: self.status(f'built {out} and {os.path.basename(ips)}'))

    def build_ch6(self):
        if self.project is None:
            return
        rom = self.need_rom()
        if not rom:
            return
        self.save_all()
        out = filedialog.asksaveasfilename(title='Save the chapter-6 test ROM as', defaultextension='.smc',
                                           initialfile=os.path.basename(self.project.path) + '_ch6test.smc',
                                           filetypes=[('SNES ROM', '*.smc *.sfc')])
        if not out:
            return

        hover = self.hover_var.get()
        self.run_job('Building the chapter-6 test', lambda: self.build_ch6_rom(rom, out, hover),
                     done=lambda r: self.status(f'{out}: New Game opens on chapter 6 (for testing only)'))

    def build_ch6_rom(self, rom, out, hover):
        import tempfile
        sys.path.insert(0, os.path.join(KIT, 'dev'))
        tmp = os.path.join(tempfile.gettempdir(), 'fe4kit_ch6.smc')
        fe4hack.build(rom, self.project.path, tmp, None, hover)
        import ch6start
        sys.argv = ['ch6start', tmp, out]
        ch6start.main()

    # -- test play in the PC port
    def set_hover(self):
        self.settings['hover_stats'] = bool(self.hover_var.get())
        save_settings(self.settings)

    def port_exe(self, force=False):
        """The PC port's program: remembered, found next to the kit, or picked once."""
        p = self.settings.get('port')
        if p and os.path.isfile(p) and not force:
            return p
        if not force:
            names = ['FE4.exe'] if sys.platform.startswith('win') else ['fe4', 'FE4.exe']
            up = os.path.dirname(HERE)
            for d in (HERE, up, os.path.join(HERE, 'FE4Port'), os.path.join(up, 'FE4Port')):
                for n in names:
                    c = os.path.join(d, n)
                    if os.path.isfile(c):
                        return c
            messagebox.showinfo(APP, 'Test play runs your hack in the FE4 PC port (FE4Port.zip). '
                                     'Please show the editor where FE4.exe is; it\'s remembered after that.')
        p = filedialog.askopenfilename(title='Where is FE4.exe (the FE4 PC port)?',
                                       filetypes=[('FE4 PC port', 'FE4.exe fe4'), ('All files', '*.*')])
        if not p:
            return None
        self.settings['port'] = p
        save_settings(self.settings)
        return p

    def test_play(self, gen2=False):
        """Build the project to <project>/_testplay/ and run it in the PC port (no mods, saves kept per project)."""
        if self.project is None:
            return
        rom = self.need_rom()
        if not rom:
            return
        exe = self.port_exe()
        if not exe:
            return
        self.save_all()
        d = os.path.join(self.project.path, '_testplay')
        os.makedirs(d, exist_ok=True)
        name = os.path.basename(os.path.normpath(self.project.path)) + ('_ch6test' if gen2 else '') + '.smc'
        out = os.path.join(d, name)
        hover = self.hover_var.get()

        def job():
            if gen2:
                self.build_ch6_rom(rom, out, hover)
            else:
                fe4hack.build(rom, self.project.path, out, None, hover)

        def started(r):
            try:
                subprocess.Popen([exe, '--play', out], cwd=os.path.dirname(exe))
                self.status(f'test play: {name} is starting in the PC port')
            except OSError as e:
                messagebox.showerror(APP, f'Couldn\'t start the PC port ({exe}): {e}')
        self.run_job('Building for test play', job, done=started)

    def run_job(self, what, fn, done=None):
        if self.busy:
            messagebox.showinfo(APP, 'Still working on the last job.')
            return
        self.busy = True
        self.write_log(f'\n{what}…\n')
        self.status(what + '…')
        self.config(cursor='watch')

        def worker():
            out = io.StringIO()

            class Tee:
                def write(s2, s):
                    self.jobq.put(('log', s))

                def flush(s2):
                    pass
            old = sys.stdout
            sys.stdout = Tee()
            try:
                res = fn()
                self.jobq.put(('done', (res, done)))
            except SystemExit as e:
                self.jobq.put(('err', str(e)))
            except Exception:              # noqa: BLE001
                self.jobq.put(('err', traceback.format_exc()))
            finally:
                sys.stdout = old
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, data = self.jobq.get_nowait()
                if kind == 'log':
                    self.write_log(data)
                elif kind == 'done':
                    self.busy = False
                    self.config(cursor='')
                    self.write_log('Done.\n', 'ok')
                    res, cb = data
                    if cb:
                        cb(res)
                else:
                    self.busy = False
                    self.config(cursor='')
                    self.write_log(data + '\n', 'err')
                    self.status('failed: see the log below')
                    messagebox.showerror(APP, data[-1500:])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def write_log(self, s, tag=None):
        self.log.configure(state='normal')
        self.log.insert('end', s, tag)
        self.log.see('end')
        self.log.configure(state='disabled')

    def status(self, s):
        self.statusbar.config(text=s)

    def readme(self):
        p = os.path.join(KIT, 'README.html')
        if not os.path.exists(p):
            p = os.path.join(KIT, 'README.md')
        webbrowser.open('file:///' + p.replace('\\', '/'))


def main():
    a = sys.argv[1:]
    if a and a[0] in ('extract', 'build', 'diff'):          # the command-line tools, without Python
        if a[0] == 'extract' and len(a) >= 3:
            fe4hack.extract(a[1], a[2])
        elif a[0] == 'build' and len(a) >= 4:
            fe4hack.build(a[1], a[2], a[3], a[a.index('--ips') + 1] if '--ips' in a else None, '--hover-stats' in a)
        elif a[0] == 'diff' and len(a) == 3:
            fe4hack.diff(a[1], a[2])
        else:
            print(fe4hack.__doc__)
        return
    if a and a[0] == 'rando':
        R.main(a[1:])
        return
    if a and a[0] == 'classic':                # the table-style editor
        App().mainloop()
        return
    import fe4studio                           # Builder of the Holy War, the visual editor (opens its own window)
    fe4studio.main()


if __name__ == '__main__':
    main()
