// Skills: FE4's own skills (who has them, their numbers) and new ones (what they do, who has them,
// how they look in the Skills menu).  Every change is checked by building the skills into a copy of
// the ROM, and the result shows at the top of the sheet.
import { api, h, toast, setField, loadTables, refreshSession } from '../app.js';

const st = { sel: 19 };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-skills') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-skills', JSON.stringify(st)); } catch (e) { /* none */ } };

const STATS = ['Str', 'Mag', 'Skl', 'Spd', 'Def', 'Res', 'Lck'];
const BONUS_FIELDS = [['atk', 'Attack'], ['def', 'Defence'], ['hit', 'Hit'], ['avoid', 'Avoid'], ['crit', 'Critical'], ['speed', 'Attack speed']];
const WHEN_LABELS = { '': 'always', attacking: 'when it starts the fight', defending: 'when attacked', 'hp<=50': 'at half HP or less', 'hp<=25': 'at a quarter HP or less', hp_full: 'at full HP', ally_near: 'to allies within 3 spaces (aura)' };
const EFFECT_LABELS = {
  stat: 'Stat bonus', combat: 'Battle bonuses', aether: 'Aether', ignis: 'Ignis', colossus: 'Colossus', vengeance: 'Vengeance',
  deadeye: 'Deadeye', lethality: 'Lethality', sure_strike: 'Sure Strike', great_shield: 'Great Shield', aegis: 'Aegis',
  pray: 'Pray', counter: 'Counter', galeforce: 'Galeforce', lifetaker: 'Lifetaker',
};

export async function skillsPage(root) {
  await loadTables(['skills', 'units_playable', 'units_npc', 'classes']);
  let K = await api('skills');
  const { people } = await api('people');
  const list = h('div', { class: 'list' });
  const sheetWrap = h('div', { class: 'sheet-wrap' });
  const newBtn = h('button', { class: 'btn btn-gilt', onclick: () => edit({ op: 'new' }, 'New skill added', true) }, '+ New skill');
  root.append(h('datalist', { id: 'skpeople' }, people.filter(p => p.name && !p.speaker).map(p => h('option', { value: `${p.name} (${p.id})` }))),
    h('datalist', { id: 'skclasses' }, K.classes.map(c => h('option', { value: c }))),
    h('div', { class: 'split' }, h('div', { class: 'roster' }, h('div', { class: 'roster-tools' }, newBtn,
      h('p', { class: 'hint' }, 'FE4\'s own skills, then the ones you add.')), list), sheetWrap));

  let checkSeq = 0;
  const status = h('div', { class: 'skstatus', 'aria-live': 'polite' });
  async function check() {
    const n = ++checkSeq;
    status.className = 'skstatus busy'; status.textContent = 'Checking…';
    const r = await api('skillcheck', {}).catch(e => ({ ok: false, error: e.message }));
    if (n !== checkSeq) return;
    status.className = 'skstatus ' + (r.ok ? 'ok' : 'bad');
    status.textContent = r.ok ? '✓ The skills build.' : r.error;
  }

  async function reload() {
    K = await api('skills');
    await loadTables(['skills', 'units_playable', 'units_npc', 'classes'], true);
    drawList(); drawSheet(); check();
  }
  async function edit(body, msg, selectLast) {
    try {
      await api('skilledit', body); await refreshSession();
      K = await api('skills');
      if (selectLast) { st.sel = K.skills[K.skills.length - 1].id; remember(); }
      await reload(); if (msg) toast(msg);
    } catch (e) { toast(e.message, true); }
  }
  async function set(row, field, value, el) {
    try { await setField('skills', row, field, value); el?.classList.remove('bad'); await reload(); }
    catch (e) { el?.classList.add('bad'); toast(e.message, true); }
  }

  function drawList() {
    const btn = s => h('button', { 'aria-pressed': String(s.id === st.sel), onclick: () => { st.sel = s.id; remember(); drawList(); drawSheet(); } },
      h('span', {}, h('b', {}, s.name), h('div', { class: 'sub' }, s.new ? (EFFECT_LABELS[s.fields.effect] || s.fields.effect || 'new') : (s.notes || '').slice(0, 48))),
      h('span', { class: 'sub' }, String(s.id)));
    const own = K.skills.filter(s => !s.new && !/^(Unused|Hidden)/.test(s.name));
    const hidden = K.skills.filter(s => !s.new && /^(Unused|Hidden)/.test(s.name));
    const mine = K.skills.filter(s => s.new);
    list.replaceChildren(h('div', { class: 'listhead' }, 'FE4\'s skills'), ...own.map(btn),
      h('div', { class: 'listhead' }, `New skills (${mine.length})`), ...(mine.length ? mine.map(btn) : [h('p', { class: 'hint', style: 'padding:0 16px' }, 'None yet. "+ New skill" adds one.')]),
      h('div', { class: 'listhead' }, 'Unused and story flags'), ...hidden.map(btn));
  }

  // ---- inputs
  const field = (label, el, hint) => h('label', { class: 'lbl' }, h('span', {}, label), el, hint ? h('small', { class: 'hint' }, hint) : null);
  function textIn(s, f, opts = {}) {
    const el = h('input', { class: 'in' + (opts.num ? ' num' : ''), value: s.fields[f] || '', placeholder: opts.placeholder || '', 'aria-label': opts.label || f, inputmode: opts.num ? 'numeric' : undefined });
    el.onchange = () => set(s.row, f, el.value.trim(), el);
    return el;
  }
  function selectIn(s, f, options, label) {
    const cur = s.fields[f] || '';
    const el = h('select', { class: 'in', 'aria-label': label }, options.map(([v, t]) => h('option', { value: v, selected: v.toLowerCase() === cur.toLowerCase() }, t)));
    el.onchange = () => set(s.row, f, el.value, el);
    return el;
  }

  function drawSheet() {
    sheetWrap.replaceChildren();
    const s = K.skills.find(x => x.id === st.sel) || K.skills[0];
    if (!s) return;
    const sheet = h('article', { class: 'sheet sksheet' });
    const nameEl = s.new ? h('input', { class: 'in skname', value: s.name, 'aria-label': 'Skill name', maxlength: 15 }) : h('h2', {}, s.name);
    if (s.new) nameEl.onchange = () => edit({ op: 'rename', row: s.row, name: nameEl.value }, `Renamed to ${nameEl.value}`);
    sheet.append(h('div', { class: 'arhead skhead' }, nameEl,
      h('p', { class: 'sub' }, `Skill ${s.id}${s.new ? ' · new' : ' · FE4\'s own'}${s.inMenu ? ' · in the Skills menu' : ''}`),
      s.new ? h('button', { class: 'btn btn-line danger', onclick: () => edit({ op: 'delete', row: s.row }, `${s.name} deleted`) }, 'Delete skill') : null),
    status);

    // what it does
    const what = h('section', { class: 'arsec' }, h('h3', {}, 'What it does'));
    if (!s.new) {
      what.append(h('p', {}, s.notes || 'Its effect is built into the game.'));
      if (s.tuning.length) {
        const g = h('div', { class: 'itgrid wide' });
        for (const f of s.tuning) {
          if (f === 'stat') g.append(field('Rate stat', selectIn(s, 'stat', [...STATS, 'Lv', 'none'].map(x => [x, x]), 'Rate stat')));
          else if (f === 'weapons') g.append(field('Weapons', selectIn(s, 'weapons', [['sword', 'Swords only (FE4)'], ['any', 'Any weapon but staves']], 'Weapons')));
          else g.append(field(f === 'amount' ? 'Amount' : 'Amount 2', textIn(s, f, { num: true, label: f })));
        }
        what.append(g);
        if (s.tuning.includes('stat')) what.append(h('p', { class: 'hint' }, 'Activation % = rate stat × amount / 100 + amount 2.'));
      } else what.append(h('p', { class: 'hint' }, 'Its numbers are fixed in the game\'s code; who has it can still change.'));
    } else {
      const eff = s.fields.effect || 'combat';
      const effSel = h('select', { class: 'in', 'aria-label': 'Effect' },
        [['stat', 'Stat bonus (like a ring)'], ['combat', 'Battle bonuses'], ...K.effects.map(e => [e.key, `${EFFECT_LABELS[e.key] || e.key}: ${e.help}`])]
          .map(([v, t]) => h('option', { value: v, selected: v === eff }, t)));
      effSel.onchange = () => set(s.row, 'effect', effSel.value, effSel);
      what.append(field('Effect', effSel));
      const g = h('div', { class: 'itgrid wide' });
      if (eff === 'stat') {
        g.append(field('Stat', selectIn(s, 'stat', STATS.map(x => [x, x]), 'Stat')), field('Bonus (1–30)', textIn(s, 'amount', { num: true, label: 'Bonus' })));
        what.append(g);
      } else if (eff === 'combat') {
        what.append(bonusEditor(s));
        what.append(field('When', selectIn(s, 'when', Object.entries(WHEN_LABELS), 'When')));
      } else {
        const e = K.effects.find(x => x.key === eff);
        g.append(field('Rate stat', selectIn(s, 'stat', [['', 'Default'], ...[...STATS, 'Lv', 'none'].map(x => [x, x])], 'Rate stat')),
          field('Amount %', textIn(s, 'amount', { num: true, placeholder: 'default', label: 'Amount' })),
          field('Plus %', textIn(s, 'amount2', { num: true, placeholder: 'default', label: 'Amount 2' })));
        if (e && e.power) g.append(field('Power', textIn(s, 'power', { placeholder: String(e.power), label: 'Power' }), eff === 'ignis' || eff === 'colossus' ? 'e.g. Def 50 = half Def' : '%'));
        if (e && e.kind === 1) g.append(field('Weapons', selectIn(s, 'weapons', [['', 'Any but staves'], ['sword', 'Swords only']], 'Weapons')));
        what.append(h('p', { class: 'hint' }, e ? `${e.help}. Activation % = rate stat × amount / 100 + plus.` : ''), g);
      }
    }
    sheet.append(what);
    sheet.append(holdersSection(s));
    if (s.new) sheet.append(menuSection(s));
    sheetWrap.append(sheet);
  }

  // combat bonuses as rows of (number, field, mine/foe)
  function bonusEditor(s) {
    const parts = (s.fields.bonus || '').split(/[;,]/).map(x => x.trim()).filter(Boolean).map(p => {
      const foe = p.toLowerCase().startsWith('foe_'); const q = foe ? p.slice(4) : p;
      const m = q.match(/^([a-z]+)\s*([+-]\s*\d+)$/i);
      return m ? { foe, f: m[1].toLowerCase(), n: Number(m[2].replace(/\s/g, '')) } : null;
    }).filter(Boolean);
    const box = h('div', { class: 'skbonus' });
    const save = () => set(s.row, 'bonus', parts.map(p => `${p.foe ? 'foe_' : ''}${p.f}${p.n >= 0 ? '+' : ''}${p.n}`).join(';'));
    parts.forEach((p, i) => {
      const who = h('select', { class: 'in', 'aria-label': 'Whose' }, h('option', { value: '', selected: !p.foe }, 'Its own'), h('option', { value: 'foe', selected: p.foe }, 'The foe\'s'));
      const what = h('select', { class: 'in', 'aria-label': 'Number' }, BONUS_FIELDS.map(([k, t]) => h('option', { value: k, selected: k === p.f }, t)));
      const n = h('input', { class: 'in num', value: (p.n >= 0 ? '+' : '') + p.n, 'aria-label': 'Change' });
      who.onchange = () => { p.foe = who.value === 'foe'; save(); };
      what.onchange = () => { p.f = what.value; save(); };
      n.onchange = () => { const v = parseInt(n.value, 10); if (!Number.isFinite(v)) { n.classList.add('bad'); return; } p.n = v; save(); };
      box.append(h('div', { class: 'skbrow' }, who, what, n, h('button', { class: 'btn btn-line', 'aria-label': 'Remove this bonus', onclick: () => { parts.splice(i, 1); save(); } }, '×')));
    });
    box.append(h('button', { class: 'btn btn-line', onclick: () => { parts.push({ foe: false, f: 'atk', n: 3 }); save(); } }, '+ Add a bonus'));
    return h('div', {}, h('span', { class: 'lbl-text' }, 'Bonuses'), box);
  }

  function holdersSection(s) {
    const sec = h('section', { class: 'arsec' }, h('h3', {}, 'Who has it'));
    const chips = (items, onRemove) => h('div', { class: 'chips' }, items.map(it => h('span', { class: 'chip artag' }, it.label,
      h('button', { class: 'x', 'aria-label': `Remove ${it.label}`, onclick: () => onRemove(it) }, '×'))));
    const unitInput = (onAdd, ph) => {
      const el = h('input', { class: 'in', list: 'skpeople', placeholder: ph, 'aria-label': ph });
      el.onchange = () => onAdd(el.value.trim(), el);
      return el;
    };
    const findUnit = text => {
      const m = text.match(/\((\d+)\)\s*$/);
      const id = m ? Number(m[1]) : people.find(p => p.name && p.name.toLowerCase() === text.toLowerCase())?.id;
      if (!id) return null;
      for (const t of ['units_playable', 'units_npc']) {
        const rows = app_rows(t);
        const i = rows.findIndex(r => Number(r.char_id) === id);
        if (i >= 0) return { table: t, row: i, name: rows[i]._name, id };
      }
      return { id, name: people.find(p => p.id === id)?.name };
    };
    if (s.new) {
      const us = (s.fields.units || '').split(/[;,]/).map(x => x.trim()).filter(Boolean);
      const cs = (s.fields.classes || '').split(/[;,]/).map(x => x.trim()).filter(Boolean);
      sec.append(h('h4', {}, 'Units'), chips(us.map(u => ({ label: u, v: u })), it => edit({ op: 'holder', row: s.row, table: 'units', holder: it.v, on: false })),
        unitInput((text, el) => {
          const u = findUnit(text);
          if (!u) { el.classList.add('bad'); toast('Pick someone from the list.', true); return; }
          if (u.table === undefined) { el.classList.add('bad'); toast('Pick a unit from the list (playable units, bosses and NPCs).', true); return; }
          // the kit reads names (a playable unit wins when a name repeats); otherwise the unit's index
          const same = t => app_rows(t).filter(r => r._name === u.name).length;
          const byName = same('units_playable') === 1 ? u.table === 'units_playable' : same('units_playable') + same('units_npc') === 1;
          edit({ op: 'holder', row: s.row, table: 'units', holder: byName ? u.name : String(app_rows(u.table)[u.row].index), on: true }, `${u.name} has ${s.name}`);
        }, 'Add a unit'),
        h('h4', {}, 'Classes'), chips(cs.map(c => ({ label: c, v: c })), it => edit({ op: 'holder', row: s.row, table: 'classes', holder: it.v, on: false })),
        classInput(c => edit({ op: 'holder', row: s.row, table: 'classes', holder: c, on: true }, `${c} has ${s.name}`)),
        h('p', { class: 'hint' }, 'Every unit of a listed class has the skill, as well as the listed units.'));
      return sec;
    }
    const H = s.holders;
    if (s.bits.personal !== '') {
      const us = [...(H.units_playable || []).map(x => ({ ...x, t: 'units_playable' })), ...(H.units_npc || []).map(x => ({ ...x, t: 'units_npc' }))];
      sec.append(h('h4', {}, 'Units'), us.length ? chips(us.map(u => ({ label: u.name, ...u })), it => edit({ op: 'holder', row: s.row, table: it.t, holder: it.row, on: false })) : h('p', { class: 'hint' }, 'No unit has it.'),
        unitInput((text, el) => {
          const u = findUnit(text);
          if (!u || u.table === undefined) { el.classList.add('bad'); toast('Pick a unit from the list (playable units, bosses and NPCs).', true); return; }
          edit({ op: 'holder', row: s.row, table: u.table, holder: u.row, on: true }, `${u.name} has ${s.name}`);
        }, 'Give it to a unit'));
    }
    if (s.bits.class !== '') {
      const cs = H.classes || [];
      sec.append(h('h4', {}, 'Classes'), cs.length ? chips(cs.map(c => ({ label: c.name, ...c })), it => edit({ op: 'holder', row: s.row, table: 'classes', holder: it.row, on: false })) : h('p', { class: 'hint' }, 'No class has it.'),
        classInput(c => {
          const i = K.classes.indexOf(c);
          if (i < 0) { toast('Pick a class from the list.', true); return; }
          edit({ op: 'holder', row: s.row, table: 'classes', holder: i, on: true }, `${c} has ${s.name}`);
        }));
    }
    if (s.bits.item !== '') {
      const it = H.items || [];
      sec.append(h('h4', {}, 'Weapons and items'), h('p', {}, it.length ? it.map(x => x.name).join(', ') : 'No item gives it.'),
        h('p', { class: 'hint' }, 'Give it to an item on the Items page.'));
    }
    if (s.bits.personal === '' && s.bits.class === '' && s.bits.item === '') sec.append(h('p', { class: 'hint' }, 'Nothing can hold this skill in FE4.'));
    return sec;
  }

  function classInput(onAdd) {
    const el = h('input', { class: 'in', list: 'skclasses', placeholder: 'Add a class', 'aria-label': 'Add a class' });
    el.onchange = () => { const v = el.value.trim(); if (v) onAdd(v); };
    return el;
  }
  const tablesCache = {};
  const app_rows = t => tablesCache[t] || [];

  function menuSection(s) {
    const sec = h('section', { class: 'arsec' }, h('h3', {}, 'In the Skills menu'));
    const show = h('input', { type: 'checkbox', checked: !['no', 'n', '0', 'false'].includes((s.fields.menu || '').toLowerCase()) });
    show.onchange = () => set(s.row, 'menu', show.checked ? '' : 'no');
    const icon = selectIn(s, 'icon', [['', 'Default'], ...K.icons.filter(n => !/^(Unused|Hidden)/.test(n)).map(n => [n, n]), ...[1, 2, 3, 4, 5, 6].map(k => [`spare${k}`, `Unused icon ${k}`])], 'Icon');
    const type = selectIn(s, 'type', [['', 'Default'], ['Combat', 'Combat'], ['Field', 'Field'], ['Sword', 'Sword']], 'Type');
    const desc = h('textarea', { class: 'in skdesc', rows: 3, placeholder: 'Leave empty for a short description of the effect', 'aria-label': 'Help text' }, s.fields.description || '');
    desc.onchange = () => set(s.row, 'description', desc.value.trim().replace(/\n/g, '/'), desc);
    sec.append(h('label', { class: 'pick-check' }, show, 'List it in the map menu\'s Skills list'),
      h('div', { class: 'itgrid wide' }, field('Icon', icon), field('Type', type)),
      field('Help text', desc, 'Three lines of about 24 letters; / starts a new line. The check above says when it doesn\'t fit.'));
    return sec;
  }

  // the unit tables, for finding a unit's row
  for (const t of ['units_playable', 'units_npc']) tablesCache[t] = (await api('table?name=' + t)).rows;
  drawList(); drawSheet(); check();
  return {
    async refresh(change) {
      if (!change || change.tables?.some(t => ['skills', 'units_playable', 'units_npc', 'classes', 'items'].includes(t))) {
        for (const t of ['units_playable', 'units_npc']) tablesCache[t] = (await api('table?name=' + t)).rows;
        await reload();
      }
    },
  };
}
