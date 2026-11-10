// Events & dialogue: each chapter's script as "when … then …" cards, and conversations as speech
// bubbles with portraits, measured with the game's own glyph widths.
import { api, h, app, toast, refreshSession, loadTables, go } from '../app.js';
import { setMapChapter } from './maps.js';

const st = { ch: null, sel: null, filter: 'all', q: '', codes: false };
const COND = new Set([0x02, 0x04, 0x05, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x16, 0x1A, 0x21]);
const QUIET = new Set([0x00, 0x20, 0x25, 0x2E]);             // block ends and 2-byte no-ops
const TAIL = new Set([0x20, 0x25, 0x2E]);                    // the structured end of a trigger list
const STATS = ['HP', 'Strength', 'Magic', 'Skill', 'Speed', 'Defense', 'Resistance', 'Luck'];
// text codes the game draws as letters but the kit's text table doesn't name
const EXTRA = { '4A': '"', '4C': ':', '89': 'á', '91': 'é', '9E': 'ö' };
const EXTRA_INV = Object.fromEntries(Object.entries(EXTRA).map(([k, v]) => [v, k]));
const FILTERS = [['all', 'All'], ['talk', 'Talks'], ['turn', 'Turns'], ['visit', 'Villages'], ['battle', 'Battles'], ['area', 'Areas'], ['other', 'Other']];

let people = null, text = null;

/** Open the events page on the event whose condition or step is on that line of the chapter script. */
export function openEventAt(ch, line) { st.ch = ch; st.q = ''; st.pendingLine = line; }

export async function eventsPage(root) {
  [people, text] = await Promise.all([
    people || api('people').then(r => r.people),
    text || api('textinfo'),
  ]);
  await loadTables(['item_instances', 'armies']);
  const { chapters } = await api('chapters');
  if (!chapters.length) { root.append(h('div', { class: 'empty' }, 'This project has no events folder.')); return {}; }
  if (st.ch === null || !chapters.some(c => c.ch === st.ch)) st.ch = chapters[0].ch;

  if (!document.getElementById('evpeople')) {
    document.body.append(h('datalist', { id: 'evpeople' }, h('option', { value: 'anyone' }),
      people.filter(p => p.name && !p.speaker).map(p => h('option', { value: `${p.name} (${p.id})` }))));
  }
  let E = null;                  // chapter data
  let msgs = {};                 // message key -> {text, where, uses}
  let groups = [];

  // ------------------------------------------------------------ layout
  const chapterSel = h('select', { class: 'in', 'aria-label': 'Chapter' }, chapters.map(c => h('option', { value: c.ch, selected: c.ch === st.ch }, c.title)));
  const search = h('input', { class: 'search', type: 'search', placeholder: 'Search all dialogue', 'aria-label': 'Search all dialogue', value: st.q });
  const filters = h('div', { class: 'evfilters', role: 'group', 'aria-label': 'Show' });
  const list = h('div', { class: 'evlist' });
  const newBtn = h('button', { class: 'btn btn-gilt', title: 'Add a talk, turn, village, area, battle or death event to this chapter', onclick: () => newEventDialog() }, '+ New event');
  const detail = h('div', { class: 'evdetail' });
  root.append(h('div', { class: 'evedit' },
    h('div', { class: 'evside' }, h('div', { class: 'evside-tools' }, h('div', { class: 'evside-row' }, chapterSel, newBtn), search, filters), list),
    detail));

  chapterSel.onchange = () => { st.ch = Number(chapterSel.value); st.sel = null; st.q = ''; search.value = ''; load(); };
  let qTimer;
  search.oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(() => { st.q = search.value.trim(); drawList(); }, 220); };

  async function load() {
    E = await api('events?ch=' + st.ch);
    const keys = new Set();
    for (const s of Object.values(E.scenes)) s.messages.forEach(k => keys.add(k));
    for (const b of E.blocks) for (const c of b.cmds) if (c.msg) keys.add(c.msg);
    msgs = keys.size ? await api('messages', { keys: [...keys] }) : {};
    groups = makeGroups(E.blocks);
    if (st.pendingLine !== undefined) {
      const g = groups.find(x => x.cond?.line === st.pendingLine || x.steps.some(c => c.line === st.pendingLine));
      if (g) st.sel = g.id;
      st.pendingLine = undefined;
    }
    if (!groups.some(g => g.id === st.sel)) st.sel = groups.find(g => g.kind !== 'start')?.id ?? groups[0]?.id ?? null;
    drawFilters(); drawList(); drawDetail();
  }

  // ------------------------------------------------------------ names
  const person = id => people[id - 1];
  const unitName = id => id === 0 || id === 0xFFFF ? 'anyone' : (person(id)?.name || `unit #${id}`);
  const locName = n => {
    const l = E.locations.find(x => Number(x.index) === n);
    return !l ? `location ${n}` : l.kind === 'castle' ? (l.name || 'a castle') : `village ${n}`;
  };
  const itemName = n => app.tables.item_instances?.rows.find(r => Number(r.instance) === n)?._item_name || `item #${n}`;
  const armyName = slot => {
    const a = app.tables.armies?.rows.find(r => (r._used_in || '').split(';').includes(`ch${E.ch}/slot${slot}`));
    return a?._name || '';
  };

  // ------------------------------------------------------------ grouping and wording
  function makeGroups(blocks) {
    const out = [];
    blocks.forEach((b, bi) => {
      if (b.label === 'init') {
        out.push({ id: `${bi}:start`, kind: 'start', cond: null, steps: b.cmds, block: b });
        return;
      }
      let cur = null;
      for (const c of b.cmds) {
        const op = bytesOf(c.hex)[0];
        if (COND.has(op)) { cur = { id: `${bi}:${c.line}`, cond: c, steps: [], block: b, editable: op !== 0x21 }; out.push(cur); continue; }
        if (TAIL.has(op) && cur?.cond) cur = null;
        if (!cur) { cur = { id: `${bi}:${c.line}`, cond: null, steps: [], block: b }; out.push(cur); }
        cur.steps.push(c);
      }
    });
    for (const g of out) {
      g.visible = g.steps.filter(c => !isQuiet(c));
      if (!g.kind) g.kind = kindOf(g.cond);
    }
    return out.filter(g => g.cond || g.visible.length);
  }
  const isQuiet = c => { const b = bytesOf(c.hex); return QUIET.has(b[0]) || (b[0] === 0xFF && b[1] === 0xFF); };

  function kindOf(c) {
    if (!c) return 'other';
    const op = bytesOf(c.hex)[0];
    return { 0x02: 'turn', 0x04: 'talk', 0x16: 'talk', 0x0C: 'talk', 0x0A: 'visit', 0x0B: 'area', 0x0D: 'battle', 0x0E: 'battle', 0x1A: 'battle' }[op] || 'other';
  }

  function condTitle(c) {
    if (!c) return 'Steps with no condition';
    const b = bytesOf(c.hex), w = i => b[i] | b[i + 1] << 8;
    switch (b[0]) {
      case 0x02: return w(2) ? `Turn ${w(4)}, army slot ${w(2)}'s phase` : `Turn ${w(4)}`;
      case 0x04: case 0x16: return `${unitName(w(2))} talks to ${unitName(w(4))}`;
      case 0x07: return `${w(2) === 0xFFFF ? '' : unitName(w(2)) + ': '}${locName(w(4))} is taken (guess)`;
      case 0x0C: return `${unitName(w(2))} comes next to ${unitName(w(4))}`;
      case 0x0A: return `Someone visits ${locName(w(4))}`;
      case 0x0B: return `${unitName(w(2))} reaches (${b[4]}, ${b[5]})–(${b[6]}, ${b[7]})`;
      case 0x0D: return `${unitName(w(4))} fights ${unitName(w(8))}`;
      case 0x0E: return `After ${unitName(w(4))} fights ${unitName(w(8))}`;
      case 0x1A: return `${unitName(w(2))} dies`;
      case 0x0F: return `Condition 0F on ${unitName(w(2))}`;
      default: return `Condition ${hex2(b[0])}`;
    }
  }
  const KNOWN_COND = new Set([0x02, 0x04, 0x16, 0x0A, 0x0B, 0x0D, 0x1A]);

  function groupTitle(g) { return g.kind === 'start' ? 'When the chapter starts' : condTitle(g.cond); }

  function firstLine(g) {
    for (const c of g.steps) {
      const b = bytesOf(c.hex);
      const keys = b[0] === 0x30 ? (E.scenes[b[2] | b[3] << 8]?.messages || []) : [c.msg].filter(Boolean);
      for (const k of keys) {
        const m = msgs[k];
        if (!m) continue;
        const p = parseMsg(m.text).runs[0];
        if (p) return { who: p.cid ? (person(p.cid)?.name || '') : '', said: plainOf(p.text) };
      }
      if (b[0] === 0x30) return { who: '', said: `Scene ${b[2] | b[3] << 8} (no dialogue)` };
    }
    return null;
  }

  // ------------------------------------------------------------ left column
  function drawFilters() {
    const count = k => k === 'all' ? groups.length : groups.filter(g => (g.kind === 'start' ? 'other' : g.kind) === k).length;
    filters.replaceChildren(...FILTERS.filter(([k]) => count(k)).map(([k, label]) =>
      h('button', { class: 'chip', 'aria-pressed': String(st.filter === k), onclick: () => { st.filter = k; drawFilters(); drawList(); } }, `${label} ${count(k)}`)));
  }

  function drawList() {
    filters.hidden = !!st.q;
    if (st.q) return drawSearch();
    const shown = groups.filter(g => st.filter === 'all' || (g.kind === 'start' ? 'other' : g.kind) === st.filter);
    list.replaceChildren(...shown.map(g => {
      const fl = firstLine(g);
      return h('button', { class: `evitem k-${g.kind}`, 'aria-pressed': String(g.id === st.sel), onclick: () => { st.sel = g.id; drawList(); drawDetail(); } },
        h('span', { class: 'evicon', 'aria-hidden': 'true' }, ICON[g.kind] || '•'),
        h('span', { class: 'evtext' }, h('b', {}, groupTitle(g)),
          fl ? h('span', { class: 'sub' }, fl.who ? h('i', {}, fl.who + ': ') : null, fl.said) : null));
    }));
  }

  async function drawSearch() {
    const q = st.q;
    list.replaceChildren(h('p', { class: 'hint', style: 'padding:8px 16px' }, 'Searching…'));
    const { results } = await api('dsearch?q=' + encodeURIComponent(q));
    if (q !== st.q) return;
    if (!results.length) { list.replaceChildren(h('p', { class: 'hint', style: 'padding:8px 16px' }, `No dialogue has "${q}".`)); return; }
    list.replaceChildren(...results.map(r => {
      const i = r.at, s = r.snippet;
      return h('button', { class: 'evitem', 'aria-pressed': String(st.sel === 'msg:' + r.key), onclick: () => openMessage(r) },
        h('span', { class: 'evicon', 'aria-hidden': 'true' }, '❝'),
        h('span', { class: 'evtext' },
          h('span', {}, (i > 0 ? '…' : '') + s.slice(0, i), h('mark', {}, s.slice(i, i + q.length)), s.slice(i + q.length) + '…'),
          h('span', { class: 'sub' }, r.chapters.length ? r.chapters.map(c => chapters.find(x => x.ch === c)?.title.split(':')[0] || `Chapter ${c}`).join(', ') : 'not used by any chapter script')));
    }));
  }

  async function openMessage(r) {
    st.sel = 'msg:' + r.key;
    drawList();
    const m = (await api('messages', { keys: [r.key] }))[r.key];
    msgs[r.key] = m;
    detail.replaceChildren();
    const uses = h('ul', { class: 'evuses' });
    for (const u of m.uses) {
      if (u.scene !== undefined) {
        uses.append(h('li', {}, `Scene ${u.scene}`, r.chapters.length ? ` · ${r.chapters.map(c => chapters.find(x => x.ch === c)?.title || c).join(', ')}` : '',
          ...r.chapters.map(c => h('button', { class: 'btn btn-line', onclick: () => jumpToScene(c, u.scene) }, 'Open the event'))));
      } else {
        const c = Number(u.file.slice(2, 4));
        uses.append(h('li', {}, `${chapters.find(x => x.ch === c)?.title || u.file}, line ${u.line + 1}`,
          h('button', { class: 'btn btn-line', onclick: () => jumpToLine(c, u.line) }, 'Open the event')));
      }
    }
    detail.append(h('article', { class: 'evcard' },
      h('h2', {}, 'Message'), uses, convo(r.key)));
  }

  function findSceneGroup(sid) {
    return groups.find(g => g.steps.some(c => { const b = bytesOf(c.hex); return b[0] === 0x30 && (b[2] | b[3] << 8) === sid; }));
  }
  async function jumpToScene(ch, sid) {
    st.q = ''; search.value = '';
    if (st.ch !== ch) { st.ch = ch; chapterSel.value = ch; await load(); }
    let g = findSceneGroup(sid);
    if (!g) {            // started by another scene: find the event whose scene runs it
      const parent = Object.entries(E.scenes).find(([, s]) => s.runs.includes(sid));
      if (parent) g = findSceneGroup(Number(parent[0]));
    }
    st.sel = g ? g.id : st.sel; drawList(); drawDetail();
    if (!g) toast(`Scene ${sid} is started by another scene, not directly by the chapter script.`);
  }
  async function jumpToLine(ch, line) {
    st.q = ''; search.value = '';
    if (st.ch !== ch) { st.ch = ch; chapterSel.value = ch; await load(); }
    const g = groups.find(x => x.cond?.line === line || x.steps.some(c => c.line === line));
    if (g) st.sel = g.id;
    drawList(); drawDetail();
  }

  // ------------------------------------------------------------ detail
  function drawDetail() {
    detail.replaceChildren();
    const g = groups.find(x => x.id === st.sel);
    if (!g) { detail.append(h('div', { class: 'empty' }, 'Pick an event on the left.')); return; }
    const card = h('article', { class: 'evcard' });
    card.append(h('div', { class: 'evhead' }, h('span', { class: `evicon big k-${g.kind}`, 'aria-hidden': 'true' }, ICON[g.kind] || '•'),
      h('h2', {}, groupTitle(g)),
      g.cond && g.editable ? h('button', { class: 'btn btn-line danger', title: 'Remove this event and its steps', onclick: () => removeLine(g.cond, true) }, 'Delete event') : null));
    if (g.cond) {
      const b = bytesOf(g.cond.hex);
      card.append(h('section', { class: 'evwhen' }, h('h3', {}, 'When'),
        condFields(g.cond),
        (b[0] === 0x04 || b[0] === 0x16) ? talkMenuLine(g.cond, b) : null,
        KNOWN_COND.has(b[0]) ? null : h('p', { class: 'hint' }, 'What this condition checks isn\'t known yet. Its bytes can still be changed below.'),
        rawBytes(g.cond)));
    }
    const then = h('section', { class: 'evthen' }, h('h3', {}, g.kind === 'start' ? 'Steps' : 'Then'));
    if (!g.visible.length) then.append(h('p', { class: 'hint' }, 'Nothing happens: this condition only marks the event as done.'));
    for (const c of g.visible) {
      const el = step(c);
      if (g.cond && g.editable) el.querySelector('.evstep-head')?.append(h('button', { class: 'x', title: 'Remove this step', 'aria-label': 'Remove this step', onclick: () => removeLine(c, false) }, '×'));
      then.append(el);
    }
    if (g.cond && g.editable) then.append(addStepBar(g));
    card.append(then);
    detail.append(card);
  }

  // talk events need an entry in the chapter's Talk list, or the map menu never offers "Talk"
  function talkMenuLine(c, b) {
    if (!E.talks) return null;
    const a = b[2] | b[3] << 8, t = b[4] | b[5] << 8;
    const on = E.talks.some(([f, x, y]) => f === b[1] && x === a && y === t);
    const nm = v => v === 0xFFFF ? 'Anyone' : person(v)?.name || `Unit ${v}`;
    const set = async v => {
      try { await api('talkmenu', { file: E.file, line: c.line, on: v }); await refreshSession(); await reloadKeepSelection(); toast(v ? 'Added to the Talk menu' : 'Removed from the Talk menu'); }
      catch (e) { toast(e.message, true); }
    };
    return on
      ? h('p', { class: 'talkmenu on' }, h('span', { class: 'chip' }, '✓ Talk command'), ` ${nm(a)} sees “Talk” next to ${nm(t)} until this event has played.`,
          h('button', { class: 'btn btn-line', title: 'Keep the event but take it out of the map menu', onclick: () => set(false) }, 'Remove from menu'))
      : h('p', { class: 'talkmenu' }, h('span', { class: 'chip' }, 'No Talk command'), ' The map menu doesn\'t offer “Talk” for this pair; the event only plays if something else starts the talk (some story talks happen when an ally walks up).',
          h('button', { class: 'btn btn-line', onclick: () => set(true) }, 'Add to the Talk menu'));
  }

  async function removeLine(c, whole) {
    try {
      await api('delstep', { file: E.file, line: c.line });
      await refreshSession();
      toast(whole ? 'Event removed' : 'Step removed');
      if (whole) { st.sel = null; await load(); } else await reloadKeepSelection();
    } catch (e) { toast(e.message, true); }
  }

  function addStepBar(g) {
    const kindSel = h('select', { class: 'in', 'aria-label': 'Add a step' },
      h('option', { value: '' }, 'Add a step…'),
      h('option', { value: 'message' }, g.kind === 'battle' ? 'A quote in the battle' : 'Someone says something'),
      h('option', { value: 'item' }, 'Give an item'), h('option', { value: 'stat' }, 'Raise a stat'),
      h('option', { value: 'deploy' }, 'Units arrive (deploy list)'));
    const extra = h('div', { class: 'evfields' });
    const go_ = h('button', { class: 'btn', hidden: true }, 'Add');
    let read = () => ({});
    kindSel.onchange = () => {
      extra.replaceChildren(); go_.hidden = !kindSel.value;
      const unitIn = (label, one) => {
        const e = h('input', { class: 'in', list: 'evpeople', value: g.kind === 'visit' ? 'anyone' : '', placeholder: one ? 'Name' : 'Name, or anyone', 'aria-label': label });
        extra.append(h('label', { class: 'lbl' }, h('span', {}, label), e));
        return () => parseUnit(e.value, one);
      };
      if (kindSel.value === 'message') {
        const who = unitIn('Who speaks', false);
        read = () => { const n = who(); if (n === null || n === 0xFFFF) throw new Error('Pick who speaks.'); return { who: n }; };
      } else if (kindSel.value === 'item') {
        const who = unitIn('Who gets it (anyone = the visitor)', false);
        const it = h('select', { class: 'in', 'aria-label': 'Item' }, (app.tables.item_instances?.rows || []).map(r => h('option', { value: r.instance }, `${r._item_name} (#${r.instance})`)));
        extra.append(h('label', { class: 'lbl' }, h('span', {}, 'Item'), it));
        read = () => { const n = who(); if (n === null) throw new Error('Pick who gets it.'); return { unit: n, instance: Number(it.value) }; };
      } else if (kindSel.value === 'stat') {
        const who = unitIn('Who (anyone = the visitor)', true);
        const sSel = h('select', { class: 'in', 'aria-label': 'Stat' }, STATS.map((x, i) => h('option', { value: i }, x)));
        const amt = h('input', { class: 'in num', value: 1, inputmode: 'numeric', 'aria-label': 'Amount' });
        extra.append(h('label', { class: 'lbl' }, h('span', {}, 'Stat'), sSel), h('label', { class: 'lbl' }, h('span', {}, 'Amount'), amt));
        read = () => { const n = who(); if (n === null) throw new Error('Pick who.'); return { unit: n, stat: Number(sSel.value), amount: Number(amt.value) }; };
      } else if (kindSel.value === 'deploy') {
        const n = h('input', { class: 'in num', value: '', inputmode: 'numeric', 'aria-label': 'Deploy list' });
        extra.append(h('label', { class: 'lbl' }, h('span', {}, 'Deploy list'), n));
        read = () => ({ list: Number(n.value) });
      }
    };
    go_.onclick = async () => {
      try {
        const args = read();
        await api('addstep', { file: E.file, line: g.cond.line, kind: kindSel.value, ...args });
        await refreshSession(); toast('Step added');
        await reloadKeepSelection();
      } catch (e) { toast(e.message, true); }
    };
    return h('div', { class: 'evadd' }, h('div', { class: 'evadd-row' }, kindSel, go_), extra,
      h('p', { class: 'hint' }, 'A new message goes into the scene this event already plays, or a new scene if it has none. Items and stats are given as the event starts.'));
  }

  // ------------------------------------------------------------ new events
  function newEventDialog() {
    document.querySelector('.modal')?.remove();
    const KINDS = [
      ['talk', '❝', 'Talk', 'A unit can Talk to another unit and they have a conversation.'],
      ['turn', '⧗', 'Turn', 'Someone says something at the start of a turn.'],
      ['visit', '⌂', 'Village', 'Visiting a village shows a message (add items or stat boosts after).'],
      ['area', '⌖', 'Area', 'A unit reaches part of the map and someone says something.'],
      ['battle', '⚔', 'Battle quote', 'A line when two units fight (the second one speaks).'],
      ['death', '✝', 'Death quote', 'A unit\'s last words.'],
    ];
    let kind = 'talk';
    const fieldsBox = h('div', { class: 'evfields' });
    const kinds = h('div', { class: 'newkinds', role: 'radiogroup', 'aria-label': 'Kind of event' });
    let read = () => ({});
    const unitIn = (label, val = '', anyone = false) => {
      const e = h('input', { class: 'in', list: 'evpeople', value: val, placeholder: anyone ? 'Name, or anyone' : 'Name', 'aria-label': label });
      fieldsBox.append(h('label', { class: 'lbl' }, h('span', {}, label), e));
      return () => { const n = parseUnit(e.value, false); if (n === null || (!anyone && n === 0xFFFF)) throw new Error(`${label}: pick someone from the list.`); return n; };
    };
    const lordLabel = E.ch >= 6 ? `${unitName(25)} (25)` : `${unitName(1)} (1)`;
    const numIn = (label, val) => {
      const e = h('input', { class: 'in num', value: val, inputmode: 'numeric', 'aria-label': label });
      fieldsBox.append(h('label', { class: 'lbl' }, h('span', {}, label), e));
      return () => { const n = Number(e.value); if (!Number.isInteger(n) || n < 0) throw new Error(`${label}: enter a number.`); return n; };
    };
    function drawFields() {
      fieldsBox.replaceChildren();
      kinds.querySelectorAll('button').forEach(b => b.setAttribute('aria-checked', String(b.dataset.k === kind)));
      if (kind === 'talk') { const a = unitIn('Who talks', lordLabel), b = unitIn('To whom'); read = () => ({ a: a(), b: b() }); }
      if (kind === 'turn') { const t = numIn('Turn', 2), w = unitIn('Who speaks', lordLabel); read = () => ({ turn: t(), who: w() }); }
      if (kind === 'visit') {
        const used = new Set(groups.filter(x => x.kind === 'visit').map(x => { const b = bytesOf(x.cond.hex); return b[4] | b[5] << 8; }));
        const free = E.locations.filter(l => l.kind === 'village' && !used.has(Number(l.index)));
        const sel = h('select', { class: 'in', 'aria-label': 'Village' }, free.map(l => h('option', { value: l.index }, `Village ${l.index} at ${l.x}, ${l.y}`)));
        fieldsBox.append(h('label', { class: 'lbl' }, h('span', {}, 'Village'), sel),
          free.length ? '' : h('p', { class: 'hint' }, 'Every village in this chapter already has a visit event; open it to add to it.'));
        read = () => { if (!sel.value) throw new Error('No village without an event.'); return { loc: Number(sel.value) }; };
      }
      if (kind === 'area') {
        const u = unitIn('Who', lordLabel, true), x1 = numIn('Left x', 0), y1 = numIn('Top y', 0), x2 = numIn('Right x', 5), y2 = numIn('Bottom y', 5);
        read = () => ({ unit: u(), x1: x1(), y1: y1(), x2: x2(), y2: y2() });
      }
      if (kind === 'battle') { const a = unitIn('Fighting', 'anyone', true), b = unitIn('Against (speaks)'); read = () => ({ a: a(), b: b() }); }
      if (kind === 'death') { const u = unitIn('Who dies'); read = () => ({ unit: u() }); }
    }
    for (const [k, icon, label, tip] of KINDS) {
      const b = h('button', { role: 'radio', 'data-k': k, title: tip, onclick: () => { kind = k; drawFields(); desc.textContent = tip; } },
        h('span', { class: 'evicon' }, icon), h('span', {}, label));
      kinds.append(b);
    }
    const desc = h('p', { class: 'hint' }, KINDS[0][3]);
    const create = h('button', { class: 'btn btn-gilt' }, 'Create event');
    const cancel = h('button', { class: 'btn btn-line' }, 'Cancel');
    const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'New event' },
      h('div', { class: 'modal-box' }, h('h2', {}, `New event in ${E.title.split(':')[0]}`), kinds, desc, fieldsBox,
        h('p', { class: 'hint' }, 'The event gets a starter conversation: write the words afterwards in its speech bubbles.'),
        h('div', { class: 'modal-actions' }, cancel, create)));
    cancel.onclick = () => modal.remove();
    modal.addEventListener('keydown', e => { if (e.key === 'Escape') modal.remove(); });
    create.onclick = async () => {
      try {
        const args = read();
        create.disabled = true;
        const r = await api('newevent', { ch: E.ch, kind, ...args });
        modal.remove();
        await refreshSession();
        st.pendingLine = r.line;
        await load();
        toast(r.merged ? 'That turn already has a scene: the message was added to it' : 'Event created');
      } catch (e) { create.disabled = false; toast(e.message, true); }
    };
    document.body.append(modal);
    drawFields();
    kinds.querySelector('button').focus();
  }

  // field specs per opcode: [label, kind, byte position, size]
  const SPEC = {
    0x02: [['Turn', 'num', 4, 2], ['Whose phase (army slot)', 'num', 2, 2]],
    0x04: [['Who talks', 'unit', 2, 2], ['To whom', 'unit', 4, 2]],
    0x16: [['Who talks', 'unit', 2, 2], ['To whom', 'unit', 4, 2]],
    0x07: [['Unit', 'unit', 2, 2], ['Castle', 'loc', 4, 2]],
    0x0C: [['Unit', 'unit', 2, 2], ['Next to', 'unit', 4, 2]],
    0x0A: [['Village or castle', 'loc', 4, 2]],
    0x0B: [['Unit', 'unit', 2, 2], ['Left x', 'num', 4, 1], ['Top y', 'num', 5, 1], ['Right x', 'num', 6, 1], ['Bottom y', 'num', 7, 1]],
    0x0D: [['Unit', 'unit', 4, 2], ['Against', 'unit', 8, 2]],
    0x0E: [['Unit', 'unit', 4, 2], ['Against', 'unit', 8, 2]],
    0x0F: [['Unit', 'unit', 2, 2]],
    0x1A: [['Unit', 'unit', 2, 2]],
    0x30: [['Scene', 'num', 2, 2]],
    0x4E: [['Deploy list', 'num', 1, 1]],
    0x4B: [['Army slot', 'num', 1, 1], ['Army', 'num', 2, 1]],
    0x57: [['Who gets it', 'unit', 1, 2], ['Item', 'item', 3, 1]],
    0x70: [['Who', 'unit1', 1, 1], ['Stat', 'stat', 2, 1], ['Amount', 'num', 3, 1]],
  };

  function condFields(c) { return fields(c, SPEC[bytesOf(c.hex)[0]] || []); }

  function fields(c, spec) {
    const b = bytesOf(c.hex);
    const box = h('div', { class: 'evfields' });
    for (const [label, kind, pos, size] of spec) {
      if (pos + size > b.length) continue;
      const v = size === 2 ? b[pos] | b[pos + 1] << 8 : b[pos];
      let el;
      if (kind === 'unit' || kind === 'unit1') {
        el = h('input', { class: 'in', list: 'evpeople', value: unitLabel(v, kind === 'unit1'), 'aria-label': label });
        el.onchange = () => {
          const n = parseUnit(el.value, kind === 'unit1');
          if (n === null) { el.classList.add('bad'); toast('Pick someone from the list, or type a number.', true); return; }
          writeField(c, pos, size, n, el);
        };
      } else if (kind === 'loc') {
        el = h('select', { class: 'in', 'aria-label': label },
          E.locations.map(l => h('option', { value: l.index, selected: Number(l.index) === v }, l.kind === 'castle' ? `${l.name || 'Castle'} (${l.index})` : `Village ${l.index} at ${l.x}, ${l.y}`)),
          E.locations.some(l => Number(l.index) === v) ? null : h('option', { value: v, selected: true }, `Location ${v}`));
        el.onchange = () => writeField(c, pos, size, Number(el.value), el);
      } else if (kind === 'stat') {
        el = h('select', { class: 'in', 'aria-label': label }, STATS.map((s, i) => h('option', { value: i, selected: i === v }, s)));
        el.onchange = () => writeField(c, pos, size, Number(el.value), el);
      } else if (kind === 'item') {
        el = h('select', { class: 'in', 'aria-label': label }, (app.tables.item_instances?.rows || []).map(r => h('option', { value: r.instance, selected: Number(r.instance) === v }, `${r._item_name} (#${r.instance})`)));
        el.onchange = () => writeField(c, pos, size, Number(el.value), el);
      } else {
        el = h('input', { class: 'in num', value: v, inputmode: 'numeric', 'aria-label': label });
        el.onchange = () => {
          const n = Number(el.value), max = size === 2 ? 65535 : 255;
          if (!Number.isInteger(n) || n < 0 || n > max) { el.classList.add('bad'); toast(`Enter a whole number from 0 to ${max}.`, true); return; }
          writeField(c, pos, size, n, el);
        };
      }
      const extra = label === 'Whose phase (army slot)' ? (v ? armyName(v) : 'yours') : label === 'Army slot' ? armyName(v) : '';
      box.append(h('label', { class: 'lbl' }, h('span', {}, label, extra ? h('em', {}, extra) : null), el));
    }
    if (!box.children.length) return null;
    return box;
  }

  const unitLabel = (v, one) => v === (one ? 0xFF : 0xFFFF) ? 'anyone' : person(v)?.name ? `${person(v).name} (${v})` : String(v);
  function parseUnit(s, one) {
    s = s.trim();
    if (/^(anyone|any|visitor)$/i.test(s)) return one ? 0xFF : 0xFFFF;
    const m = s.match(/\((\d+)\)\s*$/) || s.match(/^(\d+)$/);
    if (m) { const n = Number(m[1]); return n <= (one ? 255 : 65535) ? n : null; }
    const p = people.find(x => x.name && x.name.toLowerCase() === s.toLowerCase() && !x.speaker);
    return p ? p.id : null;
  }

  async function writeField(c, pos, size, v, el) {
    const b = bytesOf(c.hex);
    b[pos] = v & 0xFF;
    if (size === 2) b[pos + 1] = v >> 8;
    await writeCmd(c, b, el);
  }

  async function writeCmd(c, b, el) {
    try {
      const r = await api('evtcmd', { file: fileOf(c), line: c.line, hex: [...b].map(hex2).join(' ') });
      c.hex = r.hex; c.name = r.name; c.note = r.note;
      el?.classList.remove('bad');
      await refreshSession();
      await reloadKeepSelection();
    } catch (e) { el?.classList.add('bad'); toast(e.message, true); }
  }

  const fileOf = c => c._file || E.file;

  function rawBytes(c) {
    const inp = h('input', { class: 'in mono', value: c.hex, 'aria-label': 'Bytes', spellcheck: 'false' });
    inp.onchange = () => {
      const parts = inp.value.trim().split(/\s+/);
      if (!parts.every(x => /^[0-9a-fA-F]{2}$/.test(x))) { inp.classList.add('bad'); toast('Write the bytes as hex pairs, like 02 00 00 00 03 00.', true); return; }
      writeCmd(c, Uint8Array.from(parts.map(x => parseInt(x, 16))), inp);
    };
    return h('details', { class: 'evraw' }, h('summary', {}, 'Bytes'),
      h('div', { class: 'evraw-row' }, inp, h('span', { class: 'note' }, `${c.name}${c.addr ? ' at ' + c.addr : ''}`)));
  }

  function step(c) {
    const b = bytesOf(c.hex), op = b[0];
    const box = h('div', { class: 'evstep' });
    const spec = SPEC[op];
    if (op === 0x30) {
      const sid = b[2] | b[3] << 8, sc = E.scenes[sid];
      box.append(h('div', { class: 'evstep-head' }, h('b', {}, 'Play scene ' + sid),
        b[1] !== 0xFF ? h('span', { class: 'note' }, ' · once') : null));
      box.append(fields(c, spec), rawBytes(c));
      if (sc?.messages.length) for (const k of sc.messages) box.append(convo(k));
      else box.append(h('p', { class: 'hint' }, 'This scene has no dialogue (camera moves, music, units walking…).'));
      return box;
    }
    if (op === 0x31 || op === 0x32) {
      box.append(h('div', { class: 'evstep-head' }, h('b', {}, op === 0x31 ? 'Show a message' : 'Show a message (with scene)')), rawBytes(c));
      if (c.msg) box.append(convo(c.msg));
      return box;
    }
    const titles = {
      0x4E: () => `Units arrive: deploy list ${b[1]}`, 0x4B: () => `Army slot ${b[1]} = army ${b[2]}`,
      0x57: () => `${(b[1] | b[2] << 8) === 0xFFFF ? 'The visitor' : unitName(b[1] | b[2] << 8)} gets ${itemName(b[3])}`,
      0x70: () => `${b[1] === 0xFF ? 'The visitor' : unitName(b[1])}: ${STATS[b[2]] || 'stat ' + b[2]} +${b[3]}`,
      0x2B: () => 'Go to another part of the script',
      0x4D: () => 'Army relations (guess)', 0x21: () => 'Army orders (guess)',
    };
    const t = titles[op]?.() || (c.name && !/^OP_/.test(c.name) ? c.name.replace(/_/g, ' ').toLowerCase().replace(/^./, x => x.toUpperCase()) + (c.note ? ': ' + c.note : '') : `Step ${hex2(op)} (not identified yet)`);
    box.append(h('div', { class: 'evstep-head' }, h('b', {}, t),
      op === 0x4E ? h('button', { class: 'btn btn-line', onclick: () => { setMapChapter(E.ch, b[1]); go('maps'); } }, 'See them on the map') : null));
    if (spec) box.append(fields(c, spec));
    box.append(rawBytes(c));
    return box;
  }

  // ------------------------------------------------------------ conversations
  function convo(key) {
    const wrap = h('div', { class: 'convo' });
    const draw = () => {
      const m = msgs[key];
      wrap.replaceChildren();
      if (!m) { wrap.append(h('p', { class: 'hint' }, `Message @${key} isn't in dialogue.txt.`)); return; }
      const codesBtn = h('button', { class: 'btn btn-line', 'aria-pressed': String(st.codes), title: 'Show the control codes and edit the message as text' }, st.codes ? 'Hide codes' : 'Show codes');
      codesBtn.onclick = () => { st.codes = !st.codes; detail.querySelectorAll('.convo').forEach(x => x._draw?.()); };
      wrap.append(h('div', { class: 'convo-head' }, h('span', { class: 'note' }, `Message @${key}`), codesBtn));
      if (st.codes) { wrap.append(rawEditor(key)); return; }
      const P = parseMsg(m.text);
      if (!P.runs.length) wrap.append(h('p', { class: 'hint' }, 'No text (only control codes).'));
      P.runs.forEach((run, i) => wrap.append(bubble(key, P, run, i)));
    };
    wrap._draw = draw;
    draw();
    return wrap;
  }

  function bubble(key, P, run, idx) {
    // the message as it is now (another bubble of it may have been saved since this one was drawn)
    const fresh = () => { const Q = parseMsg(msgs[key].text); return { Q, r: Q.runs[idx] }; };
    const p = run.cid ? person(run.cid) : null;
    const face = h('button', { class: 'face', title: run.portraitTok !== null ? 'Change who is speaking' : 'Speaker', disabled: run.portraitTok === null },
      p?.portrait != null ? h('img', { src: `/gfx/portrait/${p.portrait}.png?s=1`, alt: '' }) : h('span', { class: 'noface' }, '?'));
    const name = h('span', { class: 'who' }, p ? (p.name || `Speaker #${run.cid}`) : (run.cid ? `#${run.cid}` : 'Narration'));
    const ta = h('textarea', { class: 'fe4box', rows: 3, wrap: 'off', spellcheck: 'true', 'aria-label': `${p?.name || 'Text'}: page` });
    ta.value = toEditable(run.text);
    const meter = h('div', { class: 'meter' });
    const measure = () => {
      const lines = ta.value.replace(/\n$/, '').split('\n');
      const ws = lines.map(widthOf), widest = Math.max(0, ...ws), over = ws.map((w, i) => w > text.boxWidth ? i + 1 : 0).filter(Boolean);
      const bar = h('i', { style: `width:${Math.min(100, widest / text.boxWidth * 100)}%` });
      meter.replaceChildren(h('span', { class: 'gauge' + (over.length ? ' over' : ''), title: 'Width of the widest line, measured with the game\'s letter widths' }, bar),
        over.length ? h('span', { class: 'over' }, `Line ${over.join(', ')} is too wide for the box (${Math.max(...ws)} of ${text.boxWidth} pixels)`)
          : h('span', {}, `Widest line ${widest} of ${text.boxWidth} pixels`),
        lines.length > text.boxLines ? h('span', { class: 'over' }, `${lines.length} lines: the box shows ${text.boxLines}`) : '');
      ta.rows = Math.max(3, lines.length);
    };
    ta.oninput = measure;
    ta.onchange = async () => {
      let enc;
      try { enc = fromEditable(ta.value); } catch (e) { ta.classList.add('bad'); toast(e.message, true); return; }
      const { Q, r } = fresh();
      const toks = Q.tokens.slice(0, r.start).concat([enc], Q.tokens.slice(r.end));
      await saveMsg(key, toks.join(''), ta);
    };
    face.onclick = () => pickSpeaker(face, async id => {
      const { Q, r } = fresh();
      const toks = [...Q.tokens];
      toks[r.portraitTok] = `{00 3F ${hex2(id & 0xFF)} ${hex2(id >> 8)}}`;
      await saveMsg(key, toks.join(''));
      msgs[key] && rerender(key);
    });
    measure();
    return h('div', { class: `bubble ${run.side === 'R' ? 'right' : 'left'}` }, face,
      h('div', { class: 'bubble-body' }, name, ta, meter));
  }

  function rerender(key) {
    detail.querySelectorAll('.convo').forEach(x => x._draw?.());
    drawList();
    void key;
  }

  async function saveMsg(key, value, el) {
    try {
      await api('msg', { key, text: value });
      msgs[key].text = value;
      el?.classList.remove('bad');
      await refreshSession();
      drawList();
    } catch (e) { el?.classList.add('bad'); toast(e.message, true); }
  }

  function rawEditor(key) {
    const ta = h('textarea', { class: 'in mono rawmsg', rows: 8, spellcheck: 'false', 'aria-label': `Message ${key} with codes` });
    ta.value = msgs[key].text.replace(/(\{0[12]\})/g, '$1\n').replace(/\n$/, '');
    ta.onchange = () => saveMsg(key, ta.value.replace(/\n/g, ''), ta);
    return h('div', {}, ta, h('p', { class: 'hint' }, '{02} new line · {08} wait for a button · {06}/{07} left/right speaker · {00 3F nn 00} portrait (character ID in hex) · {01} end. Line breaks here don\'t count.'));
  }

  function pickSpeaker(anchor, done) {
    document.querySelector('.speaker-pop')?.remove();
    const q = h('input', { class: 'search', type: 'search', placeholder: 'Find a face', 'aria-label': 'Find a face' });
    const grid = h('div', { class: 'speaker-grid' });
    const pop = h('div', { class: 'speaker-pop', role: 'dialog', 'aria-label': 'Choose who speaks' }, q, grid);
    const seen = new Set();
    const choices = people.filter(p => p.portrait != null && !seen.has(p.portrait) && seen.add(p.portrait));
    const fill = () => {
      const s = q.value.trim().toLowerCase();
      grid.replaceChildren(...choices.filter(p => !s || (p.name || '').toLowerCase().includes(s) || String(p.id) === s).slice(0, 120).map(p =>
        h('button', { title: `${p.name || 'Speaker'} (${p.id})`, onclick: () => { pop.remove(); done(p.id); } },
          h('img', { src: `/gfx/portrait/${p.portrait}.png?s=1`, alt: '' }), h('span', {}, p.name || `#${p.id}`))));
    };
    q.oninput = fill; fill();
    document.body.append(pop);
    const r = anchor.getBoundingClientRect();
    pop.style.left = Math.min(innerWidth - 380, r.left) + 'px';
    pop.style.top = Math.min(innerHeight - 420, r.bottom + 6) + 'px';
    q.focus();
    const close = e => { if (!pop.contains(e.target)) { pop.remove(); removeEventListener('pointerdown', close, true); } };
    setTimeout(() => addEventListener('pointerdown', close, true));
    pop.addEventListener('keydown', e => { if (e.key === 'Escape') pop.remove(); });
  }

  async function reloadKeepSelection() {
    const sel = st.sel;
    await load();
    st.sel = sel;
    drawList(); drawDetail();
  }

  await load();
  return {
    async refresh(change) {
      if (!change || change.events?.length || change.messages?.length || change.tables?.includes('talks')) {
        if (st.sel?.startsWith('msg:')) { const k = st.sel.slice(4); msgs[k] = (await api('messages', { keys: [k] }))[k]; detail.querySelectorAll('.convo').forEach(x => x._draw?.()); }
        else await reloadKeepSelection();
      }
    },
  };
}

// ---------------------------------------------------------------- message parsing
// tokens are the message split into {..} codes and plain text; a "run" is one page of text
// between codes (letters, {02} line breaks and letter codes such as {91} é).
function parseMsg(s) {
  const tokens = s.match(/\{[0-9A-Fa-f ]+\}|[^{]+|\{/g) || [];
  const runs = [];
  let side = 'L', cid = { L: 0, R: 0 }, ptok = { L: null, R: null }, cur = null;
  tokens.forEach((t, i) => {
    const isText = !t.startsWith('{') || t === '{02}' || /^\{[0-9A-Fa-f]{2}\}$/.test(t) && parseInt(t.slice(1, 3), 16) >= 0x10;
    if (isText) {
      if (!cur) { cur = { start: i, end: i + 1, side, cid: cid[side], portraitTok: ptok[side], text: '' }; runs.push(cur); }
      cur.end = i + 1; cur.text += t;
      return;
    }
    cur = null;
    const b = t.slice(1, -1).trim().split(/\s+/).map(x => parseInt(x, 16));
    if (b[0] === 0x06) side = 'L';
    else if (b[0] === 0x07) side = 'R';
    else if (b[0] === 0x00 && b[1] === 0x3F && b.length >= 4) { cid[side] = b[2] | b[3] << 8; ptok[side] = i; }
  });
  return { tokens, runs };
}

function toEditable(s) {
  return s.replace(/\{02\}/g, '\n').replace(/\{([0-9A-F]{2})\}/g, (m, c) => EXTRA[c] ?? m);
}

function fromEditable(s) {
  let out = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '\n') { out += '{02}'; continue; }
    if (ch === '{') {
      const j = s.indexOf('}', i);
      if (j < 0 || !/^\{[0-9A-Fa-f]{2}( [0-9A-Fa-f]{2})*\}$/.test(s.slice(i, j + 1))) throw new Error('A { starts a code like {4C}; close it with }.');
      out += s.slice(i, j + 1).toUpperCase(); i = j; continue;
    }
    if (EXTRA_INV[ch]) { out += `{${EXTRA_INV[ch]}}`; continue; }
    if (!text.chars.includes(ch)) throw new Error(`"${ch}" isn't a letter the game has. It has A–Z, a–z, 0–9, space and . , : ? ! ' - " á é ö.`);
    out += ch;
  }
  return out;
}

function widthOf(line) {
  let w = 0;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '{') { const j = line.indexOf('}', i); if (j > 0) { w += text.codeWidths[line.slice(i + 1, i + 3).toUpperCase()] || 0; i = j; continue; } }
    if (EXTRA_INV[ch]) { w += text.codeWidths[EXTRA_INV[ch]] || 0; continue; }
    w += text.widths[ch] ?? 0;
  }
  return w;
}

function plainOf(s) {
  return toEditable(s).replace(/\{[0-9A-F ]+\}/g, '').replace(/\s+/g, ' ').trim().slice(0, 110);
}

const ICON = { start: '⚑', turn: '⧗', talk: '❝', visit: '⌂', area: '⌖', battle: '⚔', other: '•' };
const hex2 = n => n.toString(16).toUpperCase().padStart(2, '0');
function bytesOf(hx) { return Uint8Array.from((hx || '').trim().split(/\s+/).filter(Boolean).flatMap(x => x.startsWith('@') ? [0, 0, 0] : [parseInt(x, 16)])); }
function talkKey(b, inScene) {
  if (!inScene && (b[0] === 0x31 || b[0] === 0x32) && b.length >= 5) return [b[4], b[3], b[2]].map(hex2).join('');
  return null;
}
