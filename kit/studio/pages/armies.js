// Armies & AI: which armies a chapter sets up, who is in them, the castles they hold, the units
// they field and the AI programs those units follow (in words, with fields).
import { api, h, app, toast, setField, loadTables, refreshSession, go } from '../app.js';
import { setMapChapter } from './maps.js';

const st = { ch: 0, sel: null };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-armies') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-armies', JSON.stringify(st)); } catch (e) { /* none */ } };
const hex2 = v => v.toString(16).toUpperCase().padStart(2, '0');

export async function armiesPage(root) {
  await loadTables(['armies', 'deploy']);
  const [{ chapters }, { people }] = await Promise.all([api('chapters'), api('people')]);
  let A = null;

  const chapterSel = h('select', { class: 'in', 'aria-label': 'Chapter' },
    chapters.map(c => h('option', { value: c.ch, selected: c.ch === st.ch }, c.title)));
  const list = h('div', { class: 'list' });
  const sheetWrap = h('div', { class: 'sheet-wrap' });
  const dl = h('datalist', { id: 'arpeople' }, people.filter(p => p.name && !p.speaker).map(p => h('option', { value: `${p.name} (${p.id})` })));
  root.append(dl, h('div', { class: 'split' },
    h('div', { class: 'roster' }, h('div', { class: 'roster-tools' }, chapterSel,
      h('p', { class: 'hint' }, 'The armies this chapter sets up, by slot. Slot 0 is yours.')), list),
    sheetWrap));
  chapterSel.onchange = () => { st.ch = Number(chapterSel.value); st.sel = null; remember(); load(); };

  async function load() {
    A = await api('armies?ch=' + st.ch);
    if (!A.armies.some(a => a.slot === st.sel)) st.sel = A.armies.find(a => a.slot > 0)?.slot ?? A.armies[0]?.slot ?? null;
    drawList(); drawSheet();
  }

  const personName = id => people.find(p => p.id === id)?.name || `Unit ${id}`;
  const parseUnit = s => {
    s = s.trim();
    const m = s.match(/\((\d+)\)\s*$/) || s.match(/^(\d+)$/);
    if (m) return Number(m[1]);
    const p = people.find(x => x.name && x.name.toLowerCase() === s.toLowerCase() && !x.speaker);
    return p ? p.id : null;
  };
  const locLabel = l => l.kind === 'castle' ? (l.name || `Castle ${l.index}`) : `Village ${l.index} at ${l.x}, ${l.y}`;

  function drawList() {
    list.replaceChildren(...A.armies.map(a => {
      const b = h('button', { 'aria-pressed': String(a.slot === st.sel), onclick: () => { st.sel = a.slot; remember(); drawList(); drawSheet(); } },
        h('span', {}, h('b', {}, a.name), h('div', { class: 'sub' }, `Slot ${a.slot}${a.slot === 0 ? ' · your army' : ''} · army ${a.army}`)),
        h('span', { class: 'sub' }, a.units.length ? `${a.units.length} unit${a.units.length > 1 ? 's' : ''}` : ''));
      return b;
    }));
    if (!A.armies.length) list.append(h('p', { class: 'hint', style: 'padding: 0 16px' }, 'This chapter sets up no armies.'));
  }

  async function set(table, row, field, value, el) {
    try { await setField(table, row, field, String(value)); el?.classList.remove('bad'); await load(); }
    catch (e) { el?.classList.add('bad'); toast(e.message, true); }
  }

  function drawSheet() {
    sheetWrap.replaceChildren();
    const a = A.armies.find(x => x.slot === st.sel);
    if (!a) { sheetWrap.append(h('div', { class: 'empty' }, 'Pick an army on the left.')); return; }
    const sheet = h('article', { class: 'sheet arsheet' });
    sheet.append(h('div', { class: 'arhead' }, h('h2', {}, a.name),
      h('p', { class: 'sub' }, `Slot ${a.slot} in ${A.title} · army ${a.army}${a.slot === 0 ? ' · the player\'s army' : ''}`)));

    // ---- the army itself
    const sec = h('section', { class: 'arsec' }, h('h3', {}, 'The army'));
    const nameSel = h('select', { class: 'in', 'aria-label': 'Name' },
      h('option', { value: 255, selected: a.nameId === 255 }, 'No name'),
      A.castleNames.map((n, i) => n ? h('option', { value: i, selected: i === a.nameId }, `${n} (${i})`) : null));
    nameSel.onchange = () => set('armies', a.row, 'name', nameSel.value, nameSel);
    const castleChips = h('div', { class: 'chips' }, A.locations.filter(l => l.kind === 'castle').map(l => {
      const on = a.castles.includes(l.index);
      return h('button', { class: 'chip', 'aria-pressed': String(on), onclick: () => {
        const next = on ? a.castles.filter(c => c !== l.index) : [...a.castles, l.index];
        set('armies', a.row, 'castles', next.join(';'));
      } }, locLabel(l));
    }));
    const members = h('div', { class: 'chips' }, a.members.map(m => h('span', { class: 'chip artag' }, m.name,
      h('button', { class: 'x', 'aria-label': `Remove ${m.name}`, title: 'Remove', onclick: () => set('armies', a.row, 'members', a.members.filter(x => x !== m).map(x => x.id).join(';')) }, '×'))));
    const addIn = h('input', { class: 'in', list: 'arpeople', placeholder: 'Add someone', 'aria-label': 'Add a member' });
    addIn.onchange = () => {
      const n = parseUnit(addIn.value);
      if (n === null) { addIn.classList.add('bad'); toast('Pick someone from the list.', true); return; }
      set('armies', a.row, 'members', [...a.members.map(x => x.id), n].join(';'), addIn);
    };
    sec.append(h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'Name (shown on the map)'), nameSel)),
      h('h4', {}, 'Castles it holds'), castleChips.children.length ? castleChips : h('p', { class: 'hint' }, 'No castles in this chapter.'),
      h('h4', {}, 'Members'), h('p', { class: 'hint' }, 'Units that join when the chapter sets this army up (your starting units, allies who arrive with the army). Enemies on the map come from deploy lists, below.'),
      members, h('div', { class: 'aradd' }, addIn));
    sheet.append(sec);

    // ---- programs
    const psec = h('section', { class: 'arsec' }, h('h3', {}, 'What its units do ', h('small', {}, 'AI programs')),
      h('p', { class: 'hint' }, 'Each turn a unit reads its program from step 1. The first step that can act does; the others are skipped. Steps marked ? are best guesses.'));
    if (!a.programs.length) psec.append(h('p', { class: 'hint' }, 'This army has no programs: its units stand still unless an event moves them.'));
    for (const p of a.programs) psec.append(programCard(a, p));
    sheet.append(psec);
    // ---- units on the map
    if (a.units.length) {
      const progName = k => k === 0 ? 'None (stands still)' : `Program ${k}${a.programs[k - 1] ? ': ' + summary(a.programs[k - 1]) : ''}`;
      const byList = {};
      for (const u of a.units) (byList[u.list] ??= []).push(u);
      const usec = h('section', { class: 'arsec' }, h('h3', {}, 'Units on the map ', h('small', {}, `${a.units.length} from deploy lists`)));
      for (const [lst, us] of Object.entries(byList)) {
        const counts = {};
        for (const u of us) counts[u.orders] = (counts[u.orders] || 0) + 1;
        const mix = Object.entries(counts).map(([k, n]) => `${n} × ${k === '0' ? 'none' : 'program ' + k}`).join(', ');
        const all = h('select', { class: 'in', 'aria-label': `Program for all of deploy list ${lst}` },
          h('option', { value: '' }, 'Set all to…'), [0, ...a.programs.map(p => p.k)].map(k => h('option', { value: k }, progName(k))));
        all.onchange = async () => {
          if (all.value === '') return;
          try {
            await api('setmany', { changes: us.map(u => ({ table: 'deploy', row: u.row, field: 'orders', value: all.value })) });
            await refreshSession(); await loadTables(['deploy'], true); await load();
          } catch (e) { toast(e.message, true); }
        };
        const det = h('details', { class: 'arlist', open: Object.keys(byList).length === 1 || us.length <= 8 },
          h('summary', {}, h('b', {}, `Deploy list ${lst}`), h('span', { class: 'sub' }, ` · ${us.length} unit${us.length > 1 ? 's' : ''} · ${mix}`)));
        usec.append(det);
        det.append(h('div', { class: 'arlist-head' }, all,
          h('button', { class: 'btn btn-line', onclick: () => { setMapChapter(A.ch, Number(lst)); go('maps'); } }, 'See them on the map')));
        const tbl = h('div', { class: 'arunits' });
        for (const u of us) {
          const sel = h('select', { class: 'in', 'aria-label': `Program for ${u.name}` },
            [0, ...a.programs.map(p => p.k)].map(k => h('option', { value: k, selected: k === u.orders }, progName(k))));
          sel.onchange = () => set('deploy', u.row, 'orders', sel.value, sel);
          tbl.append(h('div', { class: 'arunit' }, h('span', {}, h('b', {}, u.name), u.leader ? h('span', { class: 'badge' }, 'Leader') : null,
            h('div', { class: 'sub' }, [u.class, u.level ? `Lv ${u.level}` : '', `at ${u.x}, ${u.y}`].filter(Boolean).join(' · '))), sel));
        }
        det.append(tbl);
      }
      sheet.append(usec);
    }

    sheetWrap.append(sheet);
  }

  function summary(p) {
    if (p.shared) return 'same as an earlier one';
    const acts = p.steps.filter(s => s.op !== 0xFF && s.op !== 0x01).map(s => s.text.replace(/ \(.*?\)/g, ''));
    const s = acts.slice(0, 2).join(', then ');
    return s.length > 60 ? s.slice(0, 58) + '…' : s;
  }

  function programCard(a, p) {
    const users = a.units.filter(u => u.orders === p.k).length;
    const card = h('div', { class: 'itcard arprog' }, h('div', { class: 'itcard-head' }, h('h4', {}, `Program ${p.k}`),
      h('span', { class: 'sub' }, users ? `${users} unit${users > 1 ? 's' : ''} here` : 'not used in this chapter')));
    if (p.shared) {
      card.append(h('p', { class: 'hint' }, 'This program is the same code as one listed earlier (in another army or chapter). Changing it there changes both.'));
      return card;
    }
    const ol = h('ol', { class: 'arsteps' });
    for (const s of p.steps) {
      const li = h('li', { class: s.op === 0xFF ? 'end' : '' }, h('span', { class: 'artext' }, s.text, s.known ? null : h('em', { class: 'q', title: 'Not confirmed yet' }, '')));
      const f = stepFields(s);
      if (f) li.append(f);
      ol.append(li);
    }
    card.append(ol);
    if (p.editable) card.append(recipe(a, p));
    else card.append(h('p', { class: 'hint' }, 'This program jumps into steps another program owns, so it can be edited step by step but not rewritten here.'));
    return card;
  }

  function stepFields(s) {
    if (!s.fields.length) return null;
    const toks = s.hex.split(' ');
    const slots = [];                       // byte position -> token index
    toks.forEach((t, i) => { slots.push(i); if (t.startsWith('@L')) slots.push(-1); });
    const val = (pos, size) => {
      const b = k => parseInt(toks[slots[k]], 16);
      return size === 2 ? b(pos) | b(pos + 1) << 8 : b(pos);
    };
    const write = async (pos, size, v, el) => {
      const t = [...toks];
      t[slots[pos]] = hex2(v & 0xFF);
      if (size === 2) t[slots[pos + 1]] = hex2(v >> 8);
      try { await api('aicmd', { line: s.line, hex: t.join(' ') }); await refreshSession(); await load(); }
      catch (e) { el?.classList.add('bad'); toast(e.message, true); }
    };
    const box = h('div', { class: 'arfields' });
    for (const [label, kind, pos, size] of s.fields) {
      const v = val(pos, size);
      let el;
      if (kind === 'loc') {
        el = h('select', { class: 'in', 'aria-label': label }, A.locations.map(l => h('option', { value: l.index, selected: l.index === v }, locLabel(l))),
          A.locations.some(l => l.index === v) ? null : h('option', { value: v, selected: true }, `Location ${v}`));
        el.onchange = () => write(pos, size, Number(el.value), el);
      } else if (kind === 'unit') {
        el = h('input', { class: 'in', list: 'arpeople', value: `${personName(v)} (${v})`, 'aria-label': label });
        el.onchange = () => { const n = parseUnit(el.value); if (n === null) { el.classList.add('bad'); toast('Pick someone from the list.', true); return; } write(pos, size, n, el); };
      } else {
        el = h('input', { class: 'in num', value: v, inputmode: 'numeric', 'aria-label': label });
        el.onchange = () => { const n = Number(el.value); if (!Number.isInteger(n) || n < 0 || n > 255) { el.classList.add('bad'); toast('Enter 0 to 255.', true); return; } write(pos, size, n, el); };
      }
      box.append(h('label', { class: 'lbl' }, h('span', {}, label), el));
    }
    return box;
  }

  function recipe(a, p) {
    const box = h('details', { class: 'arrecipe' }, h('summary', {}, 'Change what it does…'));
    const act = h('select', { class: 'in', 'aria-label': 'What it does' }, A.actions.map(([k, t]) => h('option', { value: k }, t)));
    const castles = A.locations.filter(l => l.kind === 'castle');
    const castle = h('select', { class: 'in', 'aria-label': 'Castle' }, castles.map(l => h('option', { value: l.index }, locLabel(l))));
    const unit = h('input', { class: 'in', list: 'arpeople', placeholder: 'Name', 'aria-label': 'Who' });
    const turn = h('input', { class: 'in num', placeholder: 'now', inputmode: 'numeric', 'aria-label': 'Starting on turn' });
    const wait = h('select', { class: 'in', 'aria-label': 'Until then' }, h('option', { value: 'reach' }, 'attack only what comes in reach'), h('option', { value: 'stay' }, 'stay put'));
    const castleL = h('label', { class: 'lbl' }, h('span', {}, 'Castle'), castle);
    const unitL = h('label', { class: 'lbl' }, h('span', {}, 'Who'), unit);
    const waitL = h('label', { class: 'lbl' }, h('span', {}, 'Until then'), wait);
    const sync = () => {
      castleL.hidden = !['seize', 'guard'].includes(act.value);
      unitL.hidden = act.value !== 'attack_unit';
      waitL.hidden = !turn.value.trim();
    };
    act.onchange = turn.oninput = sync; sync();
    const goBtn = h('button', { class: 'btn btn-gilt' }, 'Rewrite program');
    goBtn.onclick = async () => {
      const body = { army: a.army, k: p.k, action: act.value };
      if (!castleL.hidden) body.castle = Number(castle.value);
      if (!unitL.hidden) { const n = parseUnit(unit.value); if (n === null) { toast('Pick who to go after.', true); return; } body.unit = n; }
      if (turn.value.trim()) { body.until_turn = Number(turn.value); body.wait = wait.value; }
      try { await api('airecipe', body); await refreshSession(); toast(`Program ${p.k} rewritten`); await load(); }
      catch (e) { toast(e.message, true); }
    };
    const others = a.units.length ? '' : ' (no units use it in this chapter; other chapters may)';
    box.append(h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'What it does'), act), castleL, unitL,
      h('label', { class: 'lbl' }, h('span', {}, 'Starting on turn'), turn), waitL),
      h('p', { class: 'hint' }, `Replaces all the steps above for every unit with program ${p.k}${others}. Undo puts them back.`), goBtn);
    return box;
  }

  await load();
  return {
    async refresh(change) {
      if (!change || change.tables?.some(t => t === 'armies' || t === 'deploy') || change.events?.includes('ai_orders.evt')) {
        await loadTables(['armies', 'deploy'], true);
        await load();
      }
    },
  };
}
