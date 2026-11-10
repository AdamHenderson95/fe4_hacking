// Classes: bases, growths, weapon ranks, movement and class skills.
import { h, app, toast, setField, loadTables } from '../app.js';

const STATS = [['hp', 'HP'], ['str', 'Strength'], ['mag', 'Magic'], ['skl', 'Skill'], ['spd', 'Speed'], ['def', 'Defense'], ['res', 'Resistance']];
const WEAPONS = [['sword', 'Sword'], ['lance', 'Lance'], ['axe', 'Axe'], ['bow', 'Bow'], ['staff', 'Staff'], ['fire', 'Fire'], ['thunder', 'Thunder'], ['wind', 'Wind'], ['light', 'Light'], ['dark', 'Dark']];

let sel = null, query = '';

export async function classesPage(root) {
  await loadTables(['classes', 'skills', 'units_playable', 'units_npc', 'units_children']);
  const T = app.tables;
  const split = h('div', { class: 'split' });
  const roster = h('div', { class: 'roster' });
  const sheetWrap = h('div', { class: 'sheet-wrap' });
  split.append(roster, sheetWrap);
  root.append(split);

  const search = h('input', { class: 'search', type: 'search', placeholder: 'Find a class', 'aria-label': 'Find a class', value: query });
  const list = h('div', { class: 'list' });
  roster.append(h('div', { class: 'roster-tools' }, search), list);
  search.oninput = () => { query = search.value; drawList(); };

  const users = c => [...(T.units_playable?.rows || []), ...(T.units_npc?.rows || []), ...(T.units_children?.rows || [])]
    .filter(u => u.class === c.index && u._name).map(u => u._name);

  function drawList() {
    const q = query.trim().toLowerCase();
    list.replaceChildren(...T.classes.rows.filter(c => !q || c._name.toLowerCase().includes(q)).map(c => {
      const u = users(c);
      return h('button', { 'aria-pressed': String(c._row === sel), onclick: () => { sel = c._row; drawList(); drawSheet(); } },
        h('span', {}, c._name || `Class ${c.index}`), h('span', { class: 'sub' }, u.length ? u.slice(0, 3).join(', ') + (u.length > 3 ? ` +${u.length - 3}` : '') : ''));
    }));
  }

  function input(row, field, opts = {}) {
    const c = T.classes.rows[row];
    const e = h('input', { class: 'in' + (opts.num !== false ? ' num' : ''), value: c[field] ?? '', 'aria-label': opts.label || field, title: opts.title || null });
    e.onchange = async () => {
      try { e.value = await setField('classes', row, field, e.value); e.classList.remove('bad'); opts.after?.(); }
      catch (err) { e.classList.add('bad'); toast(err.message, true); }
    };
    return e;
  }
  const labeled = (label, el) => h('label', { class: 'lbl' }, h('span', {}, label), el);

  function drawSheet() {
    sheetWrap.replaceChildren();
    if (sel === null) {
      sheetWrap.append(h('div', { class: 'empty' }, h('p', {}, 'A unit\'s stats are its class bases plus its own. Growths add up the same way.'), h('p', {}, 'Choose a class on the left.')));
      return;
    }
    const c = T.classes.rows[sel], row = sel;
    const sheet = h('article', { class: 'sheet' });
    const u = users(c);
    sheet.append(h('div', { class: 'sheet-head', style: 'grid-template-columns:1fr' },
      h('div', { class: 'who' }, h('h2', {}, c._name || `Class ${c.index}`),
        h('p', { class: 'note', style: 'margin:0 0 10px' }, u.length ? 'Used by ' + u.join(', ') + '.' : 'No named unit starts in this class.'),
        h('div', { class: 'facts' }, labeled('Movement', input(row, 'move')),
          labeled('Flying', sel2(row, 'flier', [['0', 'No'], ['1', 'Yes']])),
          labeled('Group', input(row, 'group', { title: 'Class group number (used for effectiveness and promotion)' }))))));
    const body = h('div', { class: 'sheet-body' });
    const st = h('div', { class: 'stats', style: 'grid-template-columns: 92px 70px 70px 1fr' },
      h('span', {}), h('span', { class: 'h' }, 'Base'), h('span', { class: 'h' }, 'Growth %'), h('span', {}));
    for (const [f, label] of STATS) {
      const bar = h('div', { class: 'bar' });
      const max = f === 'hp' ? 80 : 30;
      const paint = () => bar.replaceChildren(h('i', { class: 'own', style: `width:${Math.min(100, Number(c['base_' + f] || 0) / max * 100)}%` }));
      paint();
      st.append(h('span', { class: 'name' }, label), input(row, 'base_' + f, { label: `${label} base`, after: paint }), input(row, 'g_' + f, { label: `${label} growth` }), bar);
    }
    const left = h('section', {}, h('h3', {}, 'Bases & growths'), st,
      h('p', { class: 'hint', style: 'margin-top:10px' }, 'Luck has no class base: it is always the unit\'s own.'));
    const ranks = h('div', { class: 'ranks' });
    for (const [w, label] of WEAPONS) ranks.append(labeled(label, sel2(row, 'rank_' + w, [['-', '–'], ['C', 'C'], ['B', 'B'], ['A', 'A']])));
    const right = h('section', {}, h('h3', {}, 'Weapons'), h('p', { class: 'hint' }, 'The best rank this class can use for each weapon type.'), ranks,
      h('h3', {}, 'Class skills'), chips(row));
    body.append(left, right);
    sheet.append(body);
    sheetWrap.append(sheet);
  }

  function sel2(row, field, options) {
    const c = T.classes.rows[row];
    const e = h('select', { class: 'in', 'aria-label': field });
    for (const [v, t] of options) { const o = h('option', { value: v }, t); if (v === c[field]) o.selected = true; e.append(o); }
    e.onchange = async () => { try { await setField('classes', row, field, e.value); } catch (err) { toast(err.message, true); drawSheet(); } };
    return e;
  }

  function chips(row) {
    const c = T.classes.rows[row];
    const have = new Set((c.skills || '').split(';').filter(Boolean));
    let names = (T.skills?.rows || []).filter(s => s.class_bit !== '').map(s => s.name);
    for (const n of have) if (!names.includes(n)) names.push(n);
    names = names.filter(n => have.has(n) || !(/^(Hidden|Unused)\d*/.test(n) || n.endsWith('?')));
    const desc = Object.fromEntries((T.skills?.rows || []).map(s => [s.name, s.description || s._notes || '']));
    const box = h('div', { class: 'chips' });
    for (const n of names) {
      const b = h('button', { class: 'chip', 'aria-pressed': String(have.has(n)), title: desc[n] || n }, n);
      b.onclick = async () => {
        const next = new Set(have); next.has(n) ? next.delete(n) : next.add(n);
        const v = names.filter(x => next.has(x)).join(';');
        try { await setField('classes', row, 'skills', v); have.clear(); v.split(';').filter(Boolean).forEach(x => have.add(x)); b.setAttribute('aria-pressed', String(have.has(n))); }
        catch (e) { toast(e.message, true); }
      };
      box.append(b);
    }
    return box;
  }

  drawList(); drawSheet();
  return { refresh() { drawList(); drawSheet(); } };
}
