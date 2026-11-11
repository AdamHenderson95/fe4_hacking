// Characters: a roster of portraits and a status-screen style sheet for the selected unit.
import { api, h, app, toast, setField, loadTables, go } from '../app.js';
import { showPortrait } from './portraits.js';

const GROUPS = [
  { key: 'units_playable', label: 'Generation 1', hint: 'Generation 1 and the generation 2 substitutes. Stats are added to the class; HP and Luck are the unit\'s own.' },
  { key: 'units_children', label: 'Children', hint: 'Generation 2 children. Their stats come from their parents; set who the parent is and how much they inherit.' },
  { key: 'units_npc', label: 'Bosses & NPCs', hint: 'Named NPCs and bosses with their own stats, growths and holy blood.' },
];
const STATS = [['hp', 'HP'], ['str', 'Strength'], ['mag', 'Magic'], ['skl', 'Skill'], ['spd', 'Speed'], ['def', 'Defense'], ['res', 'Resistance'], ['lck', 'Luck']];
const ABSOLUTE = new Set(['hp', 'lck']);    // not added to a class base
const BLOODS = ['Baldur', 'Naga', 'Dain', 'Nova', 'Odo', 'Ullur', 'Neir', 'Fala', 'Tordo', 'Forseti', 'Bragi', 'Hezul', 'Loptyr'];
const NEEDED = ['units_playable', 'units_children', 'units_npc', 'classes', 'item_instances', 'skills', 'names', 'lovers'];

let state = { group: 'units_playable', row: null, query: '' };
try { Object.assign(state, JSON.parse(sessionStorage.getItem('fe4studio-chars') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-chars', JSON.stringify(state)); } catch (e) { /* none */ } };

/** Open the Characters page on one unit (from another page). */
export function openCharacter(group, row) { state.group = group; state.row = row; state.query = ''; remember(); go('characters'); }

const portraitUrl = (n, s) => `/gfx/portrait/${n}.png?s=${s}`;

function unitName(t, r) {
  return r._name || (app.tables.names?.rows.find(n => n.kind === 'character' && n.id === r.name_id)?.name) || `Unit ${r.index}`;
}

export async function charactersPage(root) {
  await loadTables(NEEDED);
  const T = app.tables;
  const split = h('div', { class: 'split' });
  const roster = h('div', { class: 'roster' });
  const sheetWrap = h('div', { class: 'sheet-wrap' });
  split.append(roster, sheetWrap);
  root.append(split);

  // ---------------------------------------------------------------- roster
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const search = h('input', { class: 'search', type: 'search', placeholder: 'Find a unit', 'aria-label': 'Find a unit', value: state.query });
  const grid = h('div', { class: 'grid' });
  roster.append(h('div', { class: 'roster-tools' }, tabs, search), grid);
  search.oninput = () => { state.query = search.value; remember(); drawGrid(); };

  function drawTabs() {
    tabs.replaceChildren(...GROUPS.filter(g => T[g.key]).map(g => h('button', {
      role: 'tab', 'aria-selected': String(g.key === state.group),
      onclick: () => { state.group = g.key; state.row = null; remember(); drawTabs(); drawGrid(); drawSheet(); },
    }, g.label)));
  }

  function drawGrid() {
    const t = T[state.group];
    const q = state.query.trim().toLowerCase();
    const rows = t.rows.filter(r => !q || unitName(t, r).toLowerCase().includes(q) || (r._class_name || '').toLowerCase().includes(q));
    grid.replaceChildren(...rows.map(r => {
      const pic = h('div', { class: 'tile-pic' });
      if (r._portrait !== null && r._portrait !== undefined) pic.append(h('img', { src: portraitUrl(r._portrait, 2), alt: '', loading: 'lazy' }));
      else pic.append(h('span', { class: 'noface' }, unitName(t, r)[0] || '?'));
      return h('button', {
        class: 'tile', 'aria-pressed': String(r._row === state.row), title: `${unitName(t, r)}, ${r._class_name || ''}`,
        onclick: () => { state.row = r._row; remember(); drawGrid(); drawSheet(); },
      }, pic, h('span', { class: 'tile-name' }, unitName(t, r)));
    }));
    if (!rows.length) grid.append(h('p', { class: 'note' }, 'No unit matches.'));
  }

  // ---------------------------------------------------------------- inputs that save on change
  function input(table, row, field, opts = {}) {
    const r = T[table].rows[row];
    const e = h('input', { class: 'in' + (opts.num ? ' num' : ''), value: r[field] ?? '', inputmode: opts.num ? 'numeric' : null,
      'aria-label': opts.label || field, maxlength: opts.max || null, title: opts.title || null });
    e.onchange = async () => {
      try {
        e.value = await setField(table, row, field, e.value);
        e.classList.remove('bad');
        opts.after?.();
      } catch (err) { e.classList.add('bad'); toast(err.message, true); }
    };
    return e;
  }
  function select(table, row, field, options, opts = {}) {
    const r = T[table].rows[row];
    const e = h('select', { class: 'in', 'aria-label': opts.label || field });
    let found = false;
    for (const [v, text] of options) {
      const o = h('option', { value: v }, text);
      if (String(v) === String(r[field])) { o.selected = true; found = true; }
      e.append(o);
    }
    if (!found) { const o = h('option', { value: r[field] }, r[field] || '(none)'); o.selected = true; e.prepend(o); }
    e.onchange = async () => {
      try { await setField(table, row, field, e.value); opts.after?.(); }
      catch (err) { toast(err.message, true); drawSheet(); }
    };
    return e;
  }
  const labeled = (label, el, extra) => h('label', { class: 'lbl' }, h('span', {}, label, extra || ''), el);

  const classOptions = () => T.classes.rows.map(c => [c.index, c._name]);
  const classOf = r => T.classes.rows.find(c => c.index === r.class);

  // which units hold each item instance (one physical item can only have one owner)
  function holders() {
    const m = {};
    for (const g of GROUPS) for (const r of T[g.key]?.rows || []) for (const f of ['item1', 'item2', 'item3']) {
      const v = r[f]; if (v && v !== '255') (m[v] ||= []).push(unitName(g.key, r));
    }
    return m;
  }
  function itemOptions() {
    return [['255', '(none)']].concat(T.item_instances.rows.map(i => [i.instance, `${i._item_name}  (#${i.instance})`]));
  }

  // ---------------------------------------------------------------- sheet
  function drawSheet() {
    const table = state.group, t = T[table];
    const r = state.row !== null ? t.rows[state.row] : null;
    sheetWrap.replaceChildren();
    if (!r) {
      sheetWrap.append(h('div', { class: 'empty' }, h('p', {}, GROUPS.find(g => g.key === table).hint), h('p', {}, 'Choose a unit on the left.')));
      return;
    }
    const row = r._row;
    const sheet = h('article', { class: 'sheet', 'aria-label': unitName(table, r) });
    sheetWrap.append(sheet);

    // head: portrait, name, class and the basics
    const pic = h('div', { class: 'portrait' });
    if (r._portrait !== null && r._portrait !== undefined) pic.append(h('img', { src: portraitUrl(r._portrait, 3), alt: `Portrait of ${unitName(table, r)}` }));
    else pic.append(h('span', { class: 'noface' }, unitName(table, r)[0] || '?'));
    const nameRow = T.names?.rows.findIndex(n => n.kind === 'character' && n.id === r.name_id);
    const nameEl = nameRow >= 0
      ? input('names', nameRow, 'name', { label: 'Name', max: 8, title: 'The name as the game draws it (up to 8 letters)', after: () => { drawGrid(); } })
      : null;
    if (nameEl) T.names.rows[nameRow]._row = nameRow;
    const facts = h('div', { class: 'facts' },
      labeled('Class', select(table, row, 'class', classOptions(), { after: () => { r._class_name = classOf(r)?._name; drawSheet(); drawGrid(); } })),
      labeled('Level', input(table, row, 'level', { num: true })),
      labeled('Gender', select(table, row, 'gender', [['0', 'Male'], ['1', 'Female']])));
    if ('authority' in r) facts.append(labeled('Leadership stars', input(table, row, 'authority', { num: true, title: '0 to 5 stars' })));
    if ('gold_x1000' in r) facts.append(labeled('Gold', input(table, row, 'gold_x1000', { num: true }), h('em', { class: 'note' }, '× 1,000')));
    const who = h('div', { class: 'who' }, h('h2', {}, unitName(table, r)));
    if (nameEl) who.append(h('div', { style: 'max-width:220px;margin:-4px 0 12px' }, labeled('Name in the game', nameEl)));
    who.append(facts);
    const picBox = r._portrait !== null && r._portrait !== undefined
      ? h('div', {}, pic, h('button', { class: 'btn btn-line ptlink', title: 'Replace this picture on the Portraits page', onclick: () => { showPortrait(r._portrait); go('portraits'); } }, 'Change picture'))
      : pic;
    sheet.append(h('div', { class: 'sheet-head' }, picBox, who));

    const body = h('div', { class: 'sheet-body' });
    sheet.append(body);
    if (table === 'units_children') childBody(body, table, r, row); else unitBody(body, table, r, row);
  }

  function unitBody(body, table, r, row) {
    const cls = classOf(r) || {};
    // stats
    const st = h('div', { class: 'stats' },
      h('span', { class: 'h' }, ''), h('span', { class: 'h', style: 'text-align:right' }, 'Total'),
      h('span', { class: 'h' }, 'Own'), h('span', { class: 'h' }, 'Growth %'), h('span', { class: 'h' }, ''));
    const totals = {};
    for (const [f, label] of STATS) {
      const base = ABSOLUTE.has(f) ? 0 : Number(cls['base_' + f] || 0);
      const own = Number(r[f] || 0);
      const total = h('span', { class: 'total' }, String(base + own));
      const bar = h('div', { class: 'bar' });
      const max = f === 'hp' ? 80 : 30;
      const paint = (o, g) => {
        bar.replaceChildren(h('i', { class: 'base', style: `width:${Math.min(100, base / max * 100)}%` }),
          h('i', { class: 'own', style: `left:${Math.min(100, base / max * 100)}%;width:${Math.max(0, Math.min(100 - base / max * 100, o / max * 100))}%` }));
      };
      paint(own);
      const ownIn = input(table, row, f, { num: true, label: `${label}${ABSOLUTE.has(f) ? '' : ' added to the class'}`,
        after: () => { const v = Number(r[f]); total.textContent = String(base + v); paint(v); } });
      const gIn = input(table, row, 'g_' + f, { num: true, label: `${label} growth` });
      totals[f] = total;
      st.append(h('span', { class: 'name', title: ABSOLUTE.has(f) ? `${label}: the unit's own value` : `${label}: class base ${base} + own` }, label),
        total, ownIn, gIn, bar);
    }
    const left = h('section', {}, h('h3', {}, 'Fighting skill', h('small', {}, cls._name ? `with the ${cls._name} class` : '')), st,
      h('div', { class: 'legend' }, h('span', {}, h('b', { style: 'background:#A9B9B6' }), 'from the class'),
        h('span', {}, h('b', { style: 'background:var(--verdigris)' }), 'the unit\'s own'),
        h('span', {}, 'HP and Luck are the unit\'s own values')));

    // holy blood
    left.append(h('h3', {}, 'Holy blood'), bloodEditor(table, row, 'holy_blood'));

    // right column: items, skills, love, IDs
    const right = h('section', { class: 'stack' });
    const hold = holders();
    const items = h('div', { class: 'items' });
    for (const f of ['item1', 'item2', 'item3']) if (f in r) {
      const others = (hold[r[f]] || []).filter(n => n !== unitName(table, r));
      items.append(h('div', { class: 'item-row' }, h('span', { class: 'n' }, f.slice(-1)),
        select(table, row, f, itemOptions(), { label: `Item ${f.slice(-1)}`, after: drawSheet })));
      if (others.length && r[f] !== '255') items.append(h('p', { class: 'note warn', style: 'margin:0 0 0 30px' }, `This item is also given to ${others.join(', ')}. Each item can only have one owner.`));
    }
    right.append(h('h3', {}, 'Items'), items);
    right.append(h('h3', {}, 'Skills'), skillChips(table, row, 'skills', true));
    const extra = newSkillsOf(r);
    if (extra.length) right.append(h('p', { class: 'note', style: 'margin-top:8px' }, 'Also has: ' + extra.join(', ') + ' (new skills, given on the Skills table).'));
    if (table === 'units_playable') right.append(...loveSection(r));
    const ids = h('div', { class: 'ids' });
    for (const [f, label] of [['char_id', 'Character ID'], ['name_id', 'Name ID'], ['slot', 'Army slot'], ['unk19', 'Unknown (byte 19)']]) if (f in r) ids.append(labeled(label, input(table, row, f, { num: true })));
    right.append(h('details', { class: 'more' }, h('summary', {}, 'Game IDs'), ids));
    body.append(left, right);
  }

  function childBody(body, table, r, row) {
    const units = [...(T.units_playable?.rows || []), ...(T.units_npc?.rows || [])].map(u => u._name).filter(Boolean);
    const left = h('section', {});
    left.append(h('h3', {}, 'Parents'),
      h('p', { class: 'hint' }, 'A child inherits from one parent you choose (man or woman) and from that parent\'s lover.'),
      h('div', { class: 'facts', style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px 18px' },
        labeled('Parent', select(table, row, 'parent', units.map(n => [n, n]))),
        labeled('Inherits the holy weapon of', select(table, row, 'heir', [['father', 'the father'], ['mother', 'the mother']])),
        labeled('Born even if that parent died', select(table, row, 'always', [['yes', 'Yes'], ['', 'No']])),
        labeled('Portrait', input(table, row, 'portrait', { title: 'A portrait number, or a unit name to borrow theirs', after: () => { drawSheet(); drawGrid(); } })),
        labeled('Joins in chapter', input(table, row, 'joins', { title: 'Chapter 6 to 11, for new children' })),
        labeled('Substitute', input(table, row, 'substitute', { title: 'Who replaces this child when they aren\'t born' }))));
    left.append(h('h3', {}, 'Inheritance'),
      h('p', { class: 'hint' }, 'How much of each parent\'s growths and stats the child gets, in percent.'),
      h('div', { class: 'facts', style: 'display:grid;grid-template-columns:1fr 1fr;gap:10px 18px' },
        labeled('Growths from the father', input(table, row, 'growth_father', { num: true })),
        labeled('Growths from the mother', input(table, row, 'growth_mother', { num: true })),
        labeled('Stats from the father', input(table, row, 'stats_father', { num: true })),
        labeled('Stats from the mother', input(table, row, 'stats_mother', { num: true }))));
    const right = h('section', { class: 'stack' });
    const items = h('div', { class: 'items' });
    for (const f of ['item1', 'item2']) if (f in r) items.append(h('div', { class: 'item-row' }, h('span', { class: 'n' }, f.slice(-1)), select(table, row, f, itemOptions(), { label: `Item ${f.slice(-1)}` })));
    right.append(h('h3', {}, 'Items'), items);
    right.append(h('h3', {}, 'Skills they can inherit'), skillChips(table, row, 'inherit_skills', false));
    const ids = h('div', { class: 'ids' });
    for (const [f, label] of [['char_id', 'Character ID'], ['name_id', 'Name ID'], ['slot', 'Army slot'], ['born_flag', 'Born flag']]) if (f in r) ids.append(labeled(label, input(table, row, f)));
    right.append(h('details', { class: 'more' }, h('summary', {}, 'Game IDs'), ids));
    body.append(left, right);
  }

  function newSkillsOf(r) {
    const n = r._name;
    return (T.skills?.rows || []).filter(s => s.units && s.units.split(';').some(u => u.trim() === n || u.trim() === r.index)).map(s => s.name);
  }

  function skillChips(table, row, field, personalOnly) {
    const r = T[table].rows[row];
    const have = new Set((r[field] || '').split(';').filter(Boolean));
    let names = (T.skills?.rows || []).filter(s => !personalOnly || s.personal_bit !== '').map(s => s.name);
    names = names.filter(n => have.has(n) || !(/^(Hidden|Unused|bit)\d*/.test(n) || n.endsWith('?')));
    for (const n of have) if (!names.includes(n)) names.push(n);
    const desc = Object.fromEntries((T.skills?.rows || []).map(s => [s.name, s.description || s._notes || '']));
    const box = h('div', { class: 'chips' });
    for (const n of names) {
      const b = h('button', { class: 'chip', 'aria-pressed': String(have.has(n)), title: desc[n] || n }, n);
      b.onclick = async () => {
        const next = new Set(have); next.has(n) ? next.delete(n) : next.add(n);
        const order = names.filter(x => next.has(x));
        try { await setField(table, row, field, order.join(';')); have.clear(); order.forEach(x => have.add(x)); b.setAttribute('aria-pressed', String(have.has(n))); }
        catch (e) { toast(e.message, true); }
      };
      box.append(b);
    }
    return box;
  }

  function bloodEditor(table, row, field) {
    const r = T[table].rows[row];
    const cur = Object.fromEntries((r[field] || '').split(';').filter(Boolean).map(p => p.split(':')));
    const box = h('div', { class: 'blood' });
    for (const b of BLOODS) {
      const crest = h('div', { class: 'crest ' + (cur[b] || '') }, h('span', { class: 'bn' }, b));
      const seg = h('div', { class: 'seg', role: 'group', 'aria-label': `${b} blood` });
      for (const [v, label] of [['', 'none'], ['minor', 'minor'], ['major', 'major']]) {
        seg.append(h('button', { 'aria-pressed': String((cur[b] || '') === v), onclick: async () => {
          const next = { ...cur }; if (v) next[b] = v; else delete next[b];
          const val = BLOODS.filter(x => next[x]).map(x => `${x}:${next[x]}`).join(';');
          try { await setField(table, row, field, val); drawSheet(); } catch (e) { toast(e.message, true); }
        } }, label));
      }
      crest.append(seg);
      box.append(crest);
    }
    return box;
  }

  function loveSection(r) {
    const L = T.lovers; if (!L) return [];
    const id = r.index;
    const rows = L.rows.filter(x => x.woman === id || x.man === id);
    if (!rows.length) return [];
    const isWoman = rows[0].woman === id;
    const list = h('div', { class: 'ids', style: 'grid-template-columns: 1fr 90px 90px; align-items:center' },
      h('span', { class: 'h note' }, 'Partner'), h('span', { class: 'note' }, 'At the start'), h('span', { class: 'note' }, 'Per turn'));
    for (const x of rows) {
      const partner = isWoman ? x._man : x._woman;
      list.append(h('span', {}, partner || '?'),
        input('lovers', L.rows.indexOf(x), 'start', { num: false, label: `Love with ${partner} at the start`, title: 'Points at the start of the game (500 = lovers), or "no" for never' }),
        input('lovers', L.rows.indexOf(x), 'growth', { num: true, label: `Love with ${partner} per turn` }));
    }
    return [h('details', { class: 'more' }, h('summary', {}, `Love (${rows.length} possible partners)`),
      h('p', { class: 'hint', style: 'margin-top:8px' }, 'Love points at the start of the game and how many they gain per turn together. 500 makes them lovers.'), list)];
  }

  drawTabs(); drawGrid(); drawSheet();
  return {
    async refresh(change) {
      if (change && change.table && !app.tables[change.table]) await loadTables([change.table], true);
      drawGrid(); drawSheet();
    },
  };
}
