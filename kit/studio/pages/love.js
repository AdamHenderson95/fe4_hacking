// Love & children: the love table for each generation (who starts how close, how fast love grows),
// the families (which child belongs to which parent, who stands in when they aren't born), and the
// inheritance rules.  The page checks the result by building it into a copy of the ROM.
import { api, h, app, toast, setField, loadTables, refreshSession } from '../app.js';
import { openCharacter } from './characters.js';

const st = { tab: 'love', gen: 0 };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-love') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-love', JSON.stringify(st)); } catch (e) { /* none */ } };
const portraitUrl = n => `/gfx/portrait/${n}.png?s=1`;

export async function lovePage(root) {
  const NEED = ['lovers', 'units_children', 'units_playable', 'units_npc', 'gen2_rules'];
  await loadTables(NEED);
  const T = app.tables;
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const status = h('div', { class: 'skstatus', 'aria-live': 'polite' });
  const body = h('div', { class: 'lvbody' });
  root.append(h('div', { class: 'lvpage' }, h('div', { class: 'lvtop' }, tabs, status), body));

  let seq = 0;
  async function check() {
    const n = ++seq;
    status.className = 'skstatus busy'; status.textContent = 'Checking…';
    const r = await api('gen2check', {}).catch(e => ({ ok: false, error: e.message }));
    if (n !== seq) return;
    status.className = 'skstatus ' + (r.ok ? 'ok' : 'bad');
    status.textContent = r.ok ? '✓ Children, love and inheritance build.' + (r.note ? ' ' + r.note : '') : r.error;
  }
  async function set(table, row, field, value, el) {
    try { await setField(table, row, field, String(value)); el?.classList.remove('bad'); draw(); check(); }
    catch (e) { el?.classList.add('bad'); toast(e.message, true); }
  }
  async function setMany(changes, msg) {
    try {
      await api('setmany', { changes }); await refreshSession(); await loadTables(NEED, true);
      draw(); check(); if (msg) toast(msg);
    } catch (e) { toast(e.message, true); }
  }

  function drawTabs() {
    tabs.replaceChildren(...[['love', 'Love'], ['families', 'Families'], ['rules', 'Inheritance rules']].map(([k, t]) =>
      h('button', { role: 'tab', 'aria-selected': String(st.tab === k), onclick: () => { st.tab = k; remember(); drawTabs(); draw(); } }, t)));
  }

  // ------------------------------------------------------------ love tables
  function generations() {
    // women pair with the men of their own generation: group women by the set of men they have rows with
    const rows = T.lovers.rows;
    const byWoman = new Map();
    rows.forEach((r, i) => {
      if (!byWoman.has(r.woman)) byWoman.set(r.woman, { id: r.woman, name: r._woman, cells: new Map() });
      byWoman.get(r.woman).cells.set(r.man, i);
    });
    const groups = [];
    for (const w of byWoman.values()) {
      const key = [...w.cells.keys()].sort().join(',');
      let g = groups.find(x => x.key === key);
      if (!g) { g = { key, women: [], men: [...w.cells.keys()].map(m => ({ id: m, name: rows[w.cells.get(m)]._man })) }; groups.push(g); }
      g.women.push(w);
    }
    return groups;
  }

  const startText = v => (v === 'no' || v === '' ? '—' : v);
  function heat(r) {
    if ((r.start || '').toLowerCase() === 'no') return 'none';
    const g = Number(r.growth);
    if (!(g > 0)) return g < 0 ? 'neg' : 'zero';
    return g >= 4 ? 'h4' : g >= 3 ? 'h3' : g >= 2 ? 'h2' : 'h1';
  }

  function loveTab() {
    const gens = generations();
    if (st.gen >= gens.length) st.gen = 0;
    const g = gens[st.gen];
    const genBar = h('div', { class: 'chips' }, gens.map((x, i) => h('button', { class: 'chip', 'aria-pressed': String(i === st.gen),
      onclick: () => { st.gen = i; remember(); draw(); } }, i === 0 ? 'Generation 1' : i === 1 ? 'Generation 2' : `Group ${i + 1}`)));
    const tbl = h('table', { class: 'lvgrid' });
    tbl.append(h('thead', {}, h('tr', {}, h('th', { class: 'corner' }, h('span', {}, 'women ↓ · men →')),
      g.men.map(m => h('th', { scope: 'col' }, h('button', { class: 'lvhead', title: `Set love growth with ${m.name} for every woman`, onclick: ev => fill(ev, `with ${m.name}`, g.women.map(w => w.cells.get(m.id)).filter(x => x !== undefined)) }, m.name))))));
    const tb = h('tbody');
    for (const w of g.women) {
      const tr = h('tr', {}, h('th', { scope: 'row' }, h('button', { class: 'lvhead', title: `Set love growth for ${w.name} with every man`, onclick: ev => fill(ev, `for ${w.name}`, [...w.cells.values()]) }, w.name)));
      for (const m of g.men) {
        const i = w.cells.get(m.id);
        if (i === undefined) { tr.append(h('td', { class: 'lvnone' })); continue; }
        const r = T.lovers.rows[i];
        tr.append(h('td', {}, h('button', { class: `lvcell ${heat(r)}`, 'aria-label': `${w.name} and ${m.name}: start ${startText(r.start)}, growth ${r.growth}`,
          title: `${w.name} & ${m.name}`, onclick: ev => cellEditor(ev, i) },
        h('b', {}, (r.start || '').toLowerCase() === 'no' ? '×' : (Number(r.growth) > 0 ? '+' : '') + r.growth), h('small', {}, startText(r.start)))));
      }
      tb.append(tr);
    }
    tbl.append(tb);
    return h('div', {}, h('div', { class: 'lvintro' }, genBar,
      h('p', { class: 'hint' }, 'Each square is one couple: the big number is the love they gain each turn they stand near each other, the small one is where they start (500 makes them lovers). × = they never fall in love. Click a square to change it, or a name to set a whole row or column.')),
    h('div', { class: 'lvscroll' }, tbl),
    h('div', { class: 'lvlegend' }, h('span', { class: 'lvcell h1' }, '+1'), h('span', { class: 'lvcell h2' }, '+2'), h('span', { class: 'lvcell h3' }, '+3'), h('span', { class: 'lvcell h4' }, '+4 or more'),
      h('span', { class: 'lvcell zero' }, '0'), h('span', { class: 'lvcell none' }, 'never')));
  }

  function popover(ev, content) {
    document.querySelector('.lvpop')?.remove();
    const b = ev.currentTarget.getBoundingClientRect();
    const pop = h('div', { class: 'lvpop', role: 'dialog', 'aria-label': 'Edit love' }, content);
    pop.style.left = `${Math.min(window.innerWidth - 300, b.left)}px`;
    pop.style.top = `${b.bottom + 6}px`;
    const close = e => { if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener('pointerdown', close, true); } };
    setTimeout(() => document.addEventListener('pointerdown', close, true));
    pop.addEventListener('keydown', e => { if (e.key === 'Escape') pop.remove(); });
    document.body.append(pop);
    pop.querySelector('input,select')?.focus();
    return pop;
  }

  function cellEditor(ev, i) {
    const r = T.lovers.rows[i];
    const never = (r.start || '').toLowerCase() === 'no';
    const start = h('input', { class: 'in num', value: never ? '' : r.start, placeholder: '0', 'aria-label': 'Love at the start', disabled: never });
    const growth = h('input', { class: 'in num', value: r.growth, 'aria-label': 'Love per turn' });
    const nv = h('input', { type: 'checkbox', checked: never });
    nv.onchange = () => { start.disabled = nv.checked; };
    const ok = h('button', { class: 'btn btn-gilt' }, 'Set');
    const pop = popover(ev, [h('b', {}, `${r._woman} & ${r._man}`),
      h('label', { class: 'lbl' }, h('span', {}, 'Love per turn near each other (−127 to 127)'), growth),
      h('label', { class: 'lbl' }, h('span', {}, 'Love at the start (0–2530, steps of 10; 500 = lovers)'), start),
      h('label', { class: 'pick-check' }, nv, 'They never fall in love'), ok]);
    const go = () => {
      const s = nv.checked ? 'no' : (start.value.trim() || '0');
      const changes = [];
      if (s !== r.start) changes.push({ table: 'lovers', row: i, field: 'start', value: s });
      if (growth.value.trim() !== r.growth) changes.push({ table: 'lovers', row: i, field: 'growth', value: growth.value.trim() });
      pop.remove();
      if (changes.length) setMany(changes);
    };
    ok.onclick = go;
    pop.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  }

  function fill(ev, label, rows) {
    const growth = h('input', { class: 'in num', value: '', placeholder: 'e.g. 2', 'aria-label': 'Love per turn' });
    const ok = h('button', { class: 'btn btn-gilt' }, 'Set all');
    const pop = popover(ev, [h('b', {}, `Love per turn ${label}`), growth,
      h('p', { class: 'hint' }, `Sets ${rows.length} couples. Starting love stays as it is.`), ok]);
    const go = () => {
      const v = growth.value.trim();
      if (!/^-?\d+$/.test(v)) { growth.classList.add('bad'); return; }
      pop.remove();
      setMany(rows.map(i => ({ table: 'lovers', row: i, field: 'growth', value: v })), `Love per turn ${label}: ${v}`);
    };
    ok.onclick = go;
    pop.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
  }

  // ------------------------------------------------------------ families
  function familiesTab() {
    const kids = T.units_children.rows.map((r, i) => ({ r, i }));
    const byParent = new Map();
    for (const k of kids) {
      const p = k.r.parent || '(no parent: never born)';
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(k);
    }
    const parents = [...(T.units_playable?.rows || []), ...(T.units_npc?.rows || [])];
    const portraitOf = name => parents.find(u => u._name === name)?.portrait;
    const names = [...new Set(parents.map(u => u._name).filter(Boolean))].sort();
    const grid = h('div', { class: 'lvfams' });
    for (const [p, ks] of byParent) {
      const pp = portraitOf(p);
      grid.append(h('section', { class: 'lvfam' }, h('div', { class: 'lvparent' },
        pp !== undefined ? h('img', { src: portraitUrl(pp), alt: '', width: 48, height: 64 }) : null,
        h('div', {}, h('b', {}, p), h('div', { class: 'sub' }, 'and whoever they marry'))),
      h('div', { class: 'lvkids' }, ks.map(({ r, i }) => {
        const sel = h('select', { class: 'in', 'aria-label': `${r._name}'s parent` }, h('option', { value: '' }, 'none (never born)'),
          names.map(n => h('option', { value: n, selected: n === r.parent }, n)));
        sel.onchange = () => set('units_children', i, 'parent', sel.value, sel);
        return h('div', { class: 'lvkid' }, h('img', { src: portraitUrl(r.portrait), alt: '', width: 48, height: 64 }),
          h('div', {}, h('button', { class: 'linkbtn', onclick: () => openCharacter('units_children', i) }, r._name),
            h('div', { class: 'sub' }, `${r._class_name || ''}${r.substitute ? ` · stand-in: ${r.substitute}` : ''}${r.always === 'yes' ? ' · born even if the parent died' : ''}`),
            h('div', { class: 'sub' }, `Gets ${r.heir === 'mother' ? 'the mother' : 'the father'}'s holy blood and weapon · growths ${r.growth_father}% / ${r.growth_mother}%`),
            h('label', { class: 'lbl lvparentsel' }, h('span', {}, 'Parent'), sel)));
      }))));
    }
    return h('div', {}, h('p', { class: 'hint lvintro' }, 'Each child is tied to one parent and is born to that parent and whoever they married, at the end of chapter 5. Change a parent here; click a child for everything else (inheritance, stand-in, skills).'), grid);
  }

  // ------------------------------------------------------------ rules
  function rulesTab() {
    const R = T.gen2_rules.rows;
    const row = k => R.findIndex(r => r.rule === k);
    const num = (k, label, hint) => {
      const i = row(k);
      if (i < 0) return null;
      const el = h('input', { class: 'in num', value: R[i].value, 'aria-label': label });
      el.onchange = () => set('gen2_rules', i, 'value', el.value.trim(), el);
      return h('label', { class: 'lbl' }, h('span', {}, label), el, h('small', { class: 'hint' }, hint));
    };
    const div = Number(R[row('gold_divisor')]?.value) || 10, base = Number(R[row('gold_base')]?.value) || 0;
    return h('section', { class: 'sheet lvrules' }, h('div', { class: 'arsec' }, h('h3', {}, 'Gold'),
      h('div', { class: 'itgrid wide' }, num('gold_divisor', 'Divide the parents\' gold by', 'FE4: 10'), num('gold_base', 'Then add', 'FE4: 2000')),
      h('p', { class: 'hint' }, `A child whose parents have 20,000 and 10,000 gold starts with ${Math.floor(30000 / div + base).toLocaleString()}.`)),
    h('div', { class: 'arsec' }, h('h3', {}, 'Stats'),
      h('div', { class: 'itgrid wide' }, num('stat_cap', 'Highest stat a child can inherit', 'FE4: 15. Str, Mag, Skl, Spd, Def and Res; not HP or Luck.'))),
    h('div', { class: 'arsec' }, h('p', { class: 'hint' }, 'How much of each parent\'s growths and stats a child gets is set per child (click a child on the Families tab).')));
  }

  function draw() {
    document.querySelector('.lvpop')?.remove();
    body.replaceChildren(st.tab === 'love' ? loveTab() : st.tab === 'families' ? familiesTab() : rulesTab());
  }

  drawTabs(); draw(); check();
  return {
    async refresh(change) {
      if (!change || change.tables?.some(t => NEED.includes(t))) { await loadTables(NEED, true); draw(); check(); }
    },
  };
}
