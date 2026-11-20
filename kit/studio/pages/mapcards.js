// Map cards (1.1): right-click anything on the Maps page for what you can do there. Place an
// enemy or ally, bring reinforcements in, make talks, recruits, quotes, village and area events,
// copy and paste units, and see where enemies can reach (danger zones). Each action is one small
// card with sensible defaults filled in; Enter confirms, Escape closes.
import { api, h, app, toast, refreshSession, go, loadTables } from '../app.js';
import { openEventAt } from './events.js';
import { pickArea } from './mappick.js';

const TITLE_FONTS = ['Georgia', 'Palatino Linotype', 'Book Antiqua', 'Garamond', 'Times New Roman', 'Cambria', 'Constantia', 'serif'];

/** Draw a title the way the game's card letters look: greys 3-8 (by coverage), colour 1 as a one-pixel
 *  outline, 24 rows with the baseline on row 16, centred in 256 columns. Returns {px, wide}. */
export function renderTitle(text, { font = 'Georgia', size = 18, width = 82 } = {}) {
  const S = 4, c = document.createElement('canvas'), g = c.getContext('2d');
  const f = `${size * S}px "${font}", serif`;
  g.font = f;
  const tw = Math.ceil(g.measureText(text).width);
  c.width = tw + 16 * S; c.height = 24 * S;
  g.font = f; g.fillStyle = '#fff'; g.textBaseline = 'alphabetic';
  g.fillText(text, 8 * S, 16 * S);
  const w = Math.max(1, Math.round(c.width * width / 100 / S));
  const d = document.createElement('canvas'); d.width = w; d.height = 24;
  const dg = d.getContext('2d');
  dg.imageSmoothingEnabled = true; dg.imageSmoothingQuality = 'high';
  dg.drawImage(c, 0, 0, w, 24);
  const a = dg.getImageData(0, 0, w, 24).data;
  const al = (x, y) => a[(y * w + x) * 4 + 3];
  let x0 = w, x1 = -1;
  for (let x = 0; x < w; x++) for (let y = 0; y < 24; y++) if (al(x, y) > 24) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); }
  const px = new Uint8Array(256 * 24);
  if (x1 < 0) return { px: '0'.repeat(256 * 24), wide: false };
  const tw2 = x1 - x0 + 3, ox = Math.floor((256 - tw2) / 2) + 1;
  const TH = [24, 48, 80, 110, 150, 200];
  for (let y = 0; y < 24; y++) for (let x = x0; x <= x1; x++) {
    const v = al(x, y), lvl = TH.filter(t => v >= t).length, X = ox + x - x0;
    if (lvl && X >= 0 && X < 256) px[y * 256 + X] = 2 + lvl;
  }
  const out = px.slice();
  for (let y = 0; y < 24; y++) for (let x = 0; x < 256; x++) {
    if (px[y * 256 + x]) continue;
    let near = false;
    for (let dy = -1; dy <= 1 && !near; dy++) for (let dx = -1; dx <= 1; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy >= 0 && yy < 24 && xx >= 0 && xx < 256 && px[yy * 256 + xx] >= 3) { near = true; break; }
    }
    if (near) out[y * 256 + x] = 1;
  }
  return { px: Array.from(out).join(''), wide: tw2 > 254 };
}

const STAT_LINE = 'Write what is said, or leave it for later: the words can be changed on the Events page.';

/** ctx: { M(), ch(), reload(), select(rows), redraw(), hover() } */
export function mapActions(ctx) {
  let info = null, infoCh = null, armies = null, people = null;
  const danger = { rows: new Set(), all: false };
  let clip = null;                                      // {ch, units: [{...}]}
  try { clip = JSON.parse(sessionStorage.getItem('fe4studio-mapclip') || 'null'); } catch (e) { clip = null; }

  if (!window.__mcardHash) {                          // a card belongs to the page it was opened on
    window.__mcardHash = true;
    addEventListener('hashchange', () => document.querySelector('.modal.mcard')?.remove());
  }

  async function load(force) {
    const ch = ctx.ch();
    if (!force && info && infoCh === ch) return info;
    [info, armies] = await Promise.all([api('mapinfo?ch=' + ch), api('armies?ch=' + ch)]);
    infoCh = ch;
    if (!people) people = (await api('people')).people.filter(p => p.name && !p.speaker);
    if (!document.getElementById('mcpeople')) {
      document.body.append(h('datalist', { id: 'mcpeople' }, h('option', { value: 'anyone' }),
        people.map(p => h('option', { value: `${p.name} (${p.id})` }))));
    }
    return info;
  }

  // ------------------------------------------------------------ helpers
  const units = () => ctx.M().deploy.flatMap(l => l.units.map(u => ({ ...u, list: l.list })));
  const unitAt = row => units().find(u => u._row === row);
  const className = id => info.classes.find(c => c.id === id)?.name || `Class ${id}`;
  const itemName = id => info.items.find(i => i.id === id)?.name || `Item ${id}`;
  const armyName = slot => info.armies.find(([s]) => s === slot)?.[1] || `Army slot ${slot}`;
  const listWhen = n => { const l = info.lists.find(x => x.list === n); return l ? l.when : `Deploy list ${n}`; };
  const parsePerson = (s, anyone) => {
    s = String(s || '').trim();
    if (anyone && (!s || /^any(one)?$/i.test(s))) return 0xFFFF;
    const m = s.match(/\((\d+)\)\s*$/) || s.match(/^(\d+)$/);
    if (m) return Number(m[1]);
    const p = people.find(x => x.name.toLowerCase() === s.toLowerCase());
    return p ? p.id : null;
  };
  const personLabel = id => id === 0xFFFF ? 'anyone' : (people.find(p => p.id === id)?.name ? `${people.find(p => p.id === id).name} (${id})` : String(id));
  const terrainAt = (x, y) => { const M = ctx.M(); return M.terrain[M.words[y * M.width + x] & 0x3FF]; };
  const terrainName = t => ctx.M().terrainNames[t] || `Terrain ${t}`;
  const inArea = (x, y) => { const M = ctx.M(); const [ax, ay, aw, ah] = M.area || [0, 0, M.width, M.height]; return x >= ax && y >= ay && x < ax + aw && y < ay + ah; };
  const occupied = (x, y, except) => units().some(u => Number(u.x) === x && Number(u.y) === y && !(except || []).includes(u._row));
  const siteAt = (x, y) => ctx.M().locations.find(L => {
    const f = { castle: [-1, -1, 1, 2], village: [-1, -1, 1, 0] }[L.kind] || [0, 0, 0, 0];
    return x >= Number(L.x) + f[0] && x <= Number(L.x) + f[2] && y >= Number(L.y) + f[1] && y <= Number(L.y) + f[3];
  });

  function programs(slot) {
    const a = armies.armies.find(x => x.slot === slot);
    if (!a) return [[0, 'Stand still (no program)']];
    return [[0, 'Stand still (no program)'], ...a.programs.map(p => [p.k, `Program ${p.k}: ${summary(p)}`])];
  }
  function summary(p) {
    if (p.shared) return 'same as an earlier one';
    const acts = p.steps.filter(s => s.op !== 0xFF && s.op !== 0x01).map(s => s.text.replace(/ \(.*?\)/g, ''));
    const s = acts.slice(0, 2).join(', then ');
    return s.length > 60 ? s.slice(0, 58) + '…' : s || 'does nothing';
  }

  // defaults for a new unit: copy the nearest enemy (not your army) in this chapter
  function nearestTemplate(x, y) {
    // the nearest soldier: a named character's class and items (a boss, a prince) make a poor default
    let best = null, bd = 1e9;
    const all = units().filter(u => Number(u.army_slot) !== 0);
    const soldiers = all.filter(u => u.table === 'units_generic');
    for (const u of soldiers.length ? soldiers : all) {
      const d = Math.abs(Number(u.x) - x) + Math.abs(Number(u.y) - y);
      if (d < bd) { bd = d; best = u; }
    }
    return best;
  }

  // ------------------------------------------------------------ the context menu
  let menuEl = null;
  function closeMenu() { menuEl?.remove(); menuEl = null; }

  async function menu(ev, hit) {
    ev.preventDefault();
    closeMenu();
    try { await load(); } catch (e) { toast(e.message, true); return; }
    const items = [];
    const add = (label, fn, opts = {}) => items.push({ label, fn, ...opts });
    const sep = () => items.push({ sep: true });
    const M = ctx.M();
    const { x, y } = hit;
    const sel = (hit.rows || []).map(unitAt).filter(Boolean);
    let head;
    if (sel.length > 1) {
      head = `${sel.length} units`;
      add(`Change ${sel.length} units…`, () => multiCard(sel), { key: 'Enter' });
      add(`Copy ${sel.length} units`, () => copy(sel), { key: 'Ctrl+C' });
      add(danger.rows.has(sel[0]._row) ? 'Hide their danger zones' : 'Show their danger zones', () => toggleDanger(sel.map(u => u._row)));
      sep();
      add(`Remove ${sel.length} units`, () => remove(sel), { key: 'Del', danger: true });
    } else if (hit.unit) {
      const u = hit.unit;
      head = `${u.name}${u.class ? ' · ' + u.class : ''}${u.level ? ' Lv ' + u.level : ''} · ${armyName(Number(u.army_slot))}`;
      add('Edit unit…', () => unitCard({ edit: u }), { key: 'Enter' });
      add('Copy', () => copy([u]), { key: 'Ctrl+C' });
      add('Duplicate next to it', () => duplicate([u]), { key: 'Ctrl+D' });
      add(danger.rows.has(u._row) ? 'Hide danger zone' : 'Show danger zone', () => toggleDanger([u._row]));
      sep();
      const named = u.table && u.table !== 'units_generic';
      add(`Talk event with ${u.name}…`, () => eventCard('talk', { b: u.char_id }));
      if (Number(u.army_slot) !== 0) add(`Recruit ${u.name} by talking…`, () => eventCard('recruit', { b: u.char_id }), { note: named ? '' : 'every unit that shares this record' });
      add(`Battle quote for ${u.name}…`, () => eventCard('battle', { b: u.char_id }));
      add(`Death quote for ${u.name}…`, () => eventCard('death', { unit: u.char_id }));
      sep();
      add('Remove', () => remove([u]), { key: 'Del', danger: true });
    } else {
      const t = terrainAt(x, y);
      head = `${x}, ${y} · ${terrainName(t)}`;
      const site = siteAt(x, y);
      if (!inArea(x, y)) add('Outside the map\'s area (see Map size)', null, { disabled: true });
      add('Place an enemy here…', () => unitCard({ x, y }), { key: 'E', disabled: !inArea(x, y) });
      add('Reinforcements arrive here…', () => unitCard({ x, y, reinforce: true }), { disabled: !inArea(x, y) });
      if (clip?.units.length) add(`Paste ${clip.units.length} unit${clip.units.length > 1 ? 's' : ''} here`, () => paste(x, y), { key: 'Ctrl+V' });
      sep();
      add('Event when someone reaches here…', () => eventCard('area', { x1: Math.max(0, x - 1), y1: Math.max(0, y - 1), x2: x + 1, y2: y + 1 }));
      if (site?.kind === 'village') add('Village visit event…', () => eventCard('visit', { loc: Number(site.index) }));
      if (site?.kind === 'castle' && site.holderSlot !== 0 && !(M.endings || []).some(e => e.kind === 'seize' && e.loc === Number(site.index))) {
        add(`Taking ${site.name || 'this castle'} wins the chapter`, () => setWin({ kind: 'seize', loc: Number(site.index) }));
      }
      if (!site && inArea(x, y)) add('A character arrives here…', () => arrivalCard(x, y));
      if (site) add(`Remove this ${site.kind === 'castle' ? (site.name || 'castle') : 'village'}`, () => removeSite(site), { danger: true });
      else if (inArea(x, y)) {
        add('Add a castle here…', () => siteCard('castle', x, y));
        add('Add a village here…', () => siteCard('village', x, y));
      }
      sep();
      add('Win condition…', () => winCard());
      add('Chapter title…', () => titleCard());
      add('Opening scene…', () => openingCard({ x, y }));
      add('Message at the start of a turn…', () => eventCard('turn', {}));
      sep();
      add(danger.all ? 'Hide all danger zones' : 'Show all enemy danger zones', () => toggleDanger('all'));
    }
    menuEl = h('div', { class: 'mctx', role: 'menu', 'aria-label': head },
      h('div', { class: 'mctx-head' }, head),
      items.map(it => it.sep ? h('div', { class: 'mctx-sep', role: 'separator' }) :
        h('button', { role: 'menuitem', class: it.danger ? 'danger' : '', disabled: it.disabled || !it.fn, onclick: () => { closeMenu(); it.fn?.(); } },
          h('span', {}, it.label, it.note ? h('small', {}, ' · ' + it.note) : null), it.key ? h('kbd', {}, it.key) : null)));
    document.body.append(menuEl);
    const r = menuEl.getBoundingClientRect();
    menuEl.style.left = Math.min(ev.clientX, innerWidth - r.width - 8) + 'px';
    menuEl.style.top = Math.min(ev.clientY, innerHeight - r.height - 8) + 'px';
    const btns = [...menuEl.querySelectorAll('button:not([disabled])')];
    btns[0]?.focus();
    menuEl.addEventListener('keydown', e => {
      const i = btns.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { btns[(i + 1) % btns.length]?.focus(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { btns[(i - 1 + btns.length) % btns.length]?.focus(); e.preventDefault(); }
      else if (e.key === 'Escape') { closeMenu(); e.preventDefault(); }
    });
    setTimeout(() => addEventListener('pointerdown', function off(e) { if (!menuEl?.contains(e.target)) { closeMenu(); removeEventListener('pointerdown', off, true); } }, true));
  }

  // ------------------------------------------------------------ card frame
  function card(title, sub, body, actions, cls = '') {
    document.querySelector('.modal.mcard')?.remove();
    const box = h('div', { class: 'modal-box mcard-box' },
      h('div', { class: 'mcard-head' }, h('div', {}, h('h2', {}, title), sub ? h('p', { class: 'sub' }, sub) : null),
        h('button', { class: 'icon-btn', 'aria-label': 'Close', title: 'Close (Esc)', onclick: () => modal.remove() }, '×')),
      body, h('div', { class: 'modal-actions' }, actions));
    const modal = h('div', { class: `modal mcard ${cls}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, box);
    modal.addEventListener('keydown', e => {
      if (e.key === 'Escape') { modal.remove(); e.preventDefault(); }
      if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'BUTTON') {
        const ok = modal.querySelector('.modal-actions .btn-gilt:not([disabled])');
        if (ok) { ok.click(); e.preventDefault(); }
      }
    });
    modal.addEventListener('pointerdown', e => { if (e.target === modal) modal.remove(); });
    modal.tabIndex = -1;
    document.body.append(modal);
    setTimeout(() => { if (!modal.contains(document.activeElement)) modal.focus(); }, 0);
    return modal;
  }
  const field = (label, el, extra) => h('label', { class: 'lbl' }, h('span', {}, label, extra || null), el);
  const select = (opts, val, aria) => h('select', { class: 'in', 'aria-label': aria }, opts.map(([v, t]) => h('option', { value: v, selected: String(v) === String(val) }, t)));
  const num = (v, aria, min, max) => h('input', { class: 'in num', type: 'number', value: v, min, max, 'aria-label': aria });

  // ------------------------------------------------------------ place / edit a unit
  async function unitCard({ x, y, edit, reinforce, preset }) {
    try { await load(); } catch (e) { toast(e.message, true); return; }
    const M = ctx.M();
    const u = edit || null;
    const tpl = u || preset || nearestTemplate(x, y);
    const enemySlots = info.armies.filter(([s]) => s !== 0);
    const startList = info.lists.find(l => l.start)?.list ?? info.lists[0]?.list ?? 0;
    const cur = {
      named: u ? u.table !== 'units_generic' : false,
      cls: tpl?.cls >= 0 ? tpl.cls : (info.classes.find(c => c.name === 'Fighter')?.id ?? 0),
      level: Number(tpl?.level) || 1,
      items: tpl?.items?.length ? [...tpl.items] : [],
      nameId: tpl?.nameId >= 0 && info.nameOf[String(tpl.nameId)] ? tpl.nameId : (info.names.find(([n]) => n === armyName(tpl ? Number(tpl.army_slot) : enemySlots[0]?.[0]))?.[1] ?? info.names.find(([n]) => n === 'Soldier')?.[1] ?? info.names[0]?.[1]),
      slot: tpl ? Number(tpl.army_slot) : (enemySlots[0]?.[0] ?? 1),
      orders: tpl ? Number(tpl.orders) || 0 : 0,
      leader: u ? !!u.leader : false,
      list: u ? u.list : reinforce ? 'new' : (tpl && !preset ? tpl.list : startList),
      x: u ? Number(u.x) : x, y: u ? Number(u.y) : y,
    };
    if (preset?.list !== undefined) cur.list = preset.list;
    let share = null;
    if (u && u.table === 'units_generic') {
      try { share = await api('unitshare?cid=' + u.char_id); } catch (e) { share = null; }
    }

    // who
    const kindGen = h('button', { type: 'button', role: 'radio', 'aria-checked': String(!cur.named) }, 'Soldier (class and level)');
    const kindNamed = h('button', { type: 'button', role: 'radio', 'aria-checked': String(cur.named) }, 'Named character');
    const kinds = h('div', { class: 'mseg2', role: 'radiogroup', 'aria-label': 'Who' }, kindGen, kindNamed);
    const clsSel = select(info.classes.map(c => [c.id, c.name]), cur.cls, 'Class');
    const lvl = num(cur.level, 'Level', 1, 30);
    // weapons the class can use come first; changing to a class that can't use any of them picks one it can
    const RANK = { E: 1, D: 2, C: 3, B: 4, A: 5, '*': 6 };
    const usable = (clsId, it) => {
      const c = info.classes.find(k => k.id === clsId);
      if (!c || !it || it.type > 9) return true;
      const r = c.ranks[it.type];
      return r && r !== '-' && (RANK[r] || 0) >= (RANK[it.rank] || 0) && it.rank !== '*';
    };
    const itemSels = [0, 1, 2].map(i => h('select', { class: 'in', 'aria-label': `Weapon or item ${i + 1}` }));
    const itemWarn = h('p', { class: 'hint mcard-warn' });
    function drawItems(keep) {
      const cid = Number(clsSel.value);
      const fit = info.items.filter(it => usable(cid, it)), other = info.items.filter(it => !usable(cid, it));
      itemSels.forEach((sel, i) => {
        const v = keep ? Number(sel.value || (cur.items[i] ?? 255)) : Number(sel.value);
        sel.replaceChildren(h('option', { value: 255 }, '—'),
          h('optgroup', { label: 'This class can use' }, fit.map(it => h('option', { value: it.id }, it.name))),
          h('optgroup', { label: 'Others' }, other.map(it => h('option', { value: it.id }, it.name))));
        sel.value = String(v);
      });
      const chosen = itemSels.map(s => info.items.find(it => it.id === Number(s.value))).filter(Boolean);
      const weapons = chosen.filter(it => it.type <= 9 && it.type !== 4);
      if (!keep && weapons.length && !weapons.some(it => usable(cid, it))) {
        const best = fit.filter(it => it.type <= 9 && it.type !== 4).sort((a, b) => (RANK[a.rank] || 0) - (RANK[b.rank] || 0) || a.id - b.id)[0];
        if (best) { itemSels[itemSels.findIndex(s => info.items.find(it => it.id === Number(s.value))?.type <= 9)].value = String(best.id); }
      }
      const bad = itemSels.map(s => info.items.find(it => it.id === Number(s.value))).filter(it => it && !usable(cid, it));
      itemWarn.textContent = bad.length ? `${className(cid)}: can't use ${bad.map(it => it.name).join(', ')}.` : '';
    }
    // one entry per name; the template's own name slot stands for its name, so an identical soldier is reused
    const tplName = info.nameOf[String(cur.nameId)];
    const nameSel = select(info.names.map(([n, id]) => [n === tplName ? cur.nameId : id, n]), cur.nameId, 'Name shown');
    const personIn = h('input', { class: 'in', list: 'mcpeople', value: u && cur.named ? personLabel(u.char_id) : '', placeholder: 'Name', 'aria-label': 'Character' });
    const genBox = h('div', { class: 'mcard-grid' }, field('Class', clsSel), field('Level', lvl),
      h('div', { class: 'mcard-wide mcard-items' }, h('span', { class: 'lbl' }, 'Weapons and items'), h('div', { class: 'mcard-row3' }, itemSels), itemWarn),
      field('Name shown on the map', nameSel));
    const namedBox = h('div', { class: 'mcard-grid' }, h('div', { class: 'mcard-wide' }, field('Character', personIn)),
      h('p', { class: 'hint mcard-wide' }, 'A named character keeps their own stats and items (Characters page).'));
    const setKind = named => {
      cur.named = named;
      kindGen.setAttribute('aria-checked', String(!named)); kindNamed.setAttribute('aria-checked', String(named));
      genBox.hidden = named; namedBox.hidden = !named;
      drawArmy();
    };
    kindGen.onclick = () => setKind(false); kindNamed.onclick = () => setKind(true);

    // army, behaviour, arrival
    const armySel = h('select', { class: 'in', 'aria-label': 'Army' });
    const progSel = h('select', { class: 'in', 'aria-label': 'What it does' });
    const leaderCb = h('input', { type: 'checkbox', checked: cur.leader });
    function drawArmy() {
      const slots = cur.named ? info.armies : enemySlots;
      armySel.replaceChildren(...slots.map(([s, n]) => h('option', { value: s, selected: s === cur.slot }, s === 0 ? 'Your army' : n)));
      if (!slots.some(([s]) => s === cur.slot)) cur.slot = slots[0]?.[0] ?? 1;
      armySel.value = cur.slot;
      progSel.replaceChildren(...programs(cur.slot).map(([k, t]) => h('option', { value: k, selected: k === cur.orders }, t)));
    }
    armySel.onchange = () => { cur.slot = Number(armySel.value); cur.orders = 0; drawArmy(); };
    progSel.onchange = () => { cur.orders = Number(progSel.value); };
    const listSel = h('select', { class: 'in', 'aria-label': 'When it arrives' },
      info.lists.map(l => h('option', { value: l.list, selected: l.list === cur.list }, `${l.when}${l.start ? '' : ''} (list ${l.list}, ${l.units} unit${l.units === 1 ? '' : 's'})`)),
      h('option', { value: 'new', selected: cur.list === 'new' }, 'New reinforcements…'));
    // new reinforcements
    const whenKind = select([['turn', 'At the start of a turn'], ['area', 'When someone reaches an area']], 'turn', 'When');
    const turnIn = num(2, 'Turn', 2, 99);
    const whoIn = h('input', { class: 'in', list: 'mcpeople', value: 'anyone', 'aria-label': 'Who reaches the area' });
    const area = { x1: Math.max(0, cur.x - 2), y1: Math.max(0, cur.y - 2), x2: cur.x + 2, y2: cur.y + 2 };
    const areaTxt = h('span', { class: 'note' });
    const showArea = () => { areaTxt.textContent = `(${area.x1}, ${area.y1}) to (${area.x2}, ${area.y2})`; };
    const pickBtn = h('button', { type: 'button', class: 'btn btn-line', onclick: async () => {
      const r = await pickArea(ctx.ch(), { rect: area, unitName: whoIn.value.replace(/\s*\(\d+\)$/, '') || 'someone' });
      if (r) { Object.assign(area, r); showArea(); }
    } }, 'Pick on map…');
    showArea();
    const turnRow = h('div', { class: 'mcard-grid' }, field('Turn', turnIn),
      h('p', { class: 'hint', style: 'align-self:end;margin:0' }, 'They appear as your phase of that turn starts, and act in their army\'s phase.'));
    const areaRow = h('div', { class: 'mcard-grid' }, field('Who', whoIn), h('div', { class: 'lbl' }, h('span', {}, 'Area'), h('div', { class: 'mcard-inline' }, areaTxt, pickBtn)));
    const newBox = h('div', { class: 'mcard-new' }, field('They arrive', whenKind), turnRow, areaRow,
      h('p', { class: 'hint' }, 'More units can join this group later: choose it under "Arrives" when you place them.'));
    const drawNew = () => { newBox.hidden = listSel.value !== 'new'; turnRow.hidden = whenKind.value !== 'turn'; areaRow.hidden = whenKind.value !== 'area'; };
    listSel.onchange = drawNew; whenKind.onchange = drawNew;

    const xIn = num(cur.x, 'X'), yIn = num(cur.y, 'Y');
    const posWarn = h('p', { class: 'hint mcard-warn mcard-wide' });
    const checkPos = () => {
      const px = Number(xIn.value), py = Number(yIn.value);
      const t = Number.isInteger(px) && Number.isInteger(py) && px >= 0 && py >= 0 && px < M.width && py < M.height ? terrainAt(px, py) : null;
      posWarn.textContent = t === null || !inArea(px, py) ? 'That spot is outside the map.'
        : occupied(px, py, u ? [u._row] : []) ? 'Another unit already stands there; if both are on the map at once, the game puts this one on the nearest free spot.'
          : (info.costs[info.classes.find(k => k.id === Number(clsSel.value))?.group ?? 0]?.[t] ?? 0) >= 128 && !cur.named ? `A ${className(Number(clsSel.value))} can't stand on ${terrainName(t)}.` : '';
    };
    xIn.oninput = yIn.oninput = checkPos;
    const scopeBox = h('div', { class: 'mcard-scope', hidden: true });
    let scopeVal = 'one';
    if (share && share.uses.length > 1) {
      const others = share.uses.filter(s => s.row !== u._row);
      const where = others.slice(0, 4).map(s => `${s.title} at ${s.x}, ${s.y}`).join('; ') + (others.length > 4 ? `; and ${others.length - 4} more` : '');
      const r1 = h('input', { type: 'radio', name: 'mcscope', value: 'one', checked: true });
      const r2 = h('input', { type: 'radio', name: 'mcscope', value: 'all' });
      r1.onchange = r2.onchange = () => { scopeVal = r1.checked ? 'one' : 'all'; };
      scopeBox.append(h('p', {}, h('b', {}, `${share.uses.length} units share this soldier`), ` (${where}). Changing class, level, weapons or name:`),
        h('label', { class: 'mcard-radio' }, r1, ' Just this one (it gets its own copy)'),
        h('label', { class: 'mcard-radio' }, r2, ` All ${share.uses.length} of them`));
    }
    const genChanged = () => !u || cur.named !== (u.table !== 'units_generic') || Number(clsSel.value) !== u.cls || Number(lvl.value) !== Number(u.level) ||
      Number(nameSel.value) !== u.nameId || itemSels.map(s => Number(s.value)).filter(v => v !== 255).join() !== (u.items || []).join();
    for (const e of [clsSel, lvl, nameSel, ...itemSels]) e.addEventListener('input', () => { scopeBox.hidden = !(share && share.uses.length > 1 && genChanged()); });

    const body = h('div', { class: 'mcard-body' },
      h('section', {}, h('h3', {}, 'Who'), kinds, genBox, namedBox),
      h('section', {}, h('h3', {}, 'Side and behaviour'),
        h('div', { class: 'mcard-grid' }, field('Army', armySel), field('What it does', progSel),
          h('label', { class: 'mcard-check mcard-wide' }, leaderCb, ' Army leader (boss: the army is beaten when this unit falls)'))),
      h('section', {}, h('h3', {}, 'Where and when'),
        h('div', { class: 'mcard-grid' }, field('X', xIn), field('Y', yIn), posWarn, h('div', { class: 'mcard-wide' }, field('Arrives', listSel))), newBox),
      scopeBox);
    const ok = h('button', { class: 'btn btn-gilt' }, u ? 'Save' : 'Place unit');
    const actions = [];
    if (u) actions.push(h('button', { class: 'btn btn-line danger mcard-left', onclick: () => { modal.remove(); remove([u]); } }, 'Remove'));
    actions.push(h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'), ok);
    const title = u ? `${u.name}` : cur.list === 'new' ? 'Reinforcements' : 'Place a unit';
    const modal = card(title, `${u ? 'At' : 'At'} ${cur.x}, ${cur.y} · ${terrainName(terrainAt(cur.x, cur.y))}${u ? ` · list ${u.list}` : ''}`, body, actions);
    drawItems(true); checkPos();
    clsSel.addEventListener('change', () => { drawItems(false); checkPos(); scopeBox.hidden = !(share && share.uses.length > 1 && genChanged()); });
    for (const sel of itemSels) sel.addEventListener('change', () => drawItems(true));
    setKind(cur.named); drawNew();
    ok.onclick = async () => {
      const b = { ch: ctx.ch(), x: Number(xIn.value), y: Number(yIn.value), slot: Number(armySel.value), orders: Number(progSel.value),
        leader: leaderCb.checked, list: listSel.value === 'new' ? 'new' : Number(listSel.value) };
      if (cur.named) {
        const id = parsePerson(personIn.value, false);
        if (id === null || id === 0xFFFF) { personIn.classList.add('bad'); toast('Pick a character from the list.', true); return; }
        if (!u || id !== u.char_id) b.char_id = id;
      } else if (genChanged()) {
        b.generic = { class: Number(clsSel.value), level: Number(lvl.value), name_id: Number(nameSel.value), items: itemSels.map(s => Number(s.value)) };
        b.scope = scopeVal;
      }
      if (b.list === 'new') {
        if (whenKind.value === 'turn') b.when = { kind: 'turn', turn: Number(turnIn.value) };
        else {
          const who = parsePerson(whoIn.value, true);
          if (who === null) { whoIn.classList.add('bad'); toast('Pick who reaches the area, or anyone.', true); return; }
          b.when = { kind: 'area', unit: who, ...area };
        }
      }
      ok.disabled = true;
      try {
        const r = await api('mapunit', u ? { op: 'edit', row: u._row, ...b } : { op: 'add', ...b });
        modal.remove();
        await afterEdit(r.rows);
        toast(u ? 'Unit changed (Ctrl+Z undoes it)' : r.note ? `Placed. It arrives ${r.note.charAt(0).toLowerCase()}${r.note.slice(1)}.` : 'Unit placed (Ctrl+Z undoes it)');
      } catch (e) { ok.disabled = false; toast(e.message, true); }
    };
    (u ? ok : clsSel).focus();
  }

  // several units at once: army, behaviour, arrival, leader off
  async function multiCard(sel) {
    await load();
    const slots = [...new Set(sel.map(u => Number(u.army_slot)))];
    const armySel = select([['', 'Keep each one\'s'], ...info.armies.filter(([s]) => s !== 0).map(([s, n]) => [s, n])], slots.length === 1 ? slots[0] : '', 'Army');
    const progSel = h('select', { class: 'in', 'aria-label': 'What they do' });
    const drawProg = () => {
      const s = armySel.value === '' ? (slots.length === 1 ? slots[0] : null) : Number(armySel.value);
      progSel.replaceChildren(h('option', { value: '' }, 'Keep each one\'s'), ...(s === null ? [] : programs(s)).map(([k, t]) => h('option', { value: k }, t)));
    };
    armySel.onchange = drawProg; drawProg();
    const listSel = select([['', 'Keep each one\'s'], ...info.lists.map(l => [l.list, `${l.when} (list ${l.list})`])], '', 'Arrives');
    const ok = h('button', { class: 'btn btn-gilt' }, `Change ${sel.length} units`);
    const modal = card(`${sel.length} units`, sel.slice(0, 6).map(u => u.name).join(', ') + (sel.length > 6 ? '…' : ''),
      h('div', { class: 'mcard-body' }, h('div', { class: 'mcard-grid' }, field('Army', armySel), field('What they do', progSel), h('div', { class: 'mcard-wide' }, field('Arrive', listSel)))),
      [h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'), ok]);
    ok.onclick = async () => {
      ok.disabled = true;
      try {
        // one request per unit would be several undo steps: do them as one by a paste-free batch
        const edits = sel.map(u => ({ row: u._row, ...(armySel.value !== '' ? { slot: Number(armySel.value) } : {}),
          ...(progSel.value !== '' ? { orders: Number(progSel.value) } : {}), ...(listSel.value !== '' ? { list: Number(listSel.value) } : {}) }));
        await api('mapunit', { op: 'editmany', ch: ctx.ch(), edits });
        modal.remove(); await afterEdit(sel.map(u => u._row)); toast(`${sel.length} units changed`);
      } catch (e) { ok.disabled = false; toast(e.message, true); }
    };
    armySel.focus();
  }

  async function afterEdit(rows) {
    await refreshSession();
    await loadTables(['deploy'], true).catch(() => {});
    info = null;
    await ctx.reload();
    await load(true);
    if (rows) ctx.select(rows);
  }

  // ------------------------------------------------------------ copy, paste, duplicate, remove
  function copy(sel) {
    if (!sel.length) return;
    const x0 = Math.min(...sel.map(u => Number(u.x))), y0 = Math.min(...sel.map(u => Number(u.y)));
    clip = { ch: ctx.ch(), units: sel.map(u => ({ char_id: u.char_id, dx: Number(u.x) - x0, dy: Number(u.y) - y0, slot: Number(u.army_slot),
      orders: Number(u.orders) || 0, leader: !!u.leader, list: u.list, name: u.name })) };
    try { sessionStorage.setItem('fe4studio-mapclip', JSON.stringify(clip)); } catch (e) { /* none */ }
    toast(`Copied ${sel.length} unit${sel.length > 1 ? 's' : ''}: right-click a spot (or point at it and press Ctrl+V) to paste`);
  }

  async function paste(x, y, viaKey) {
    if (!clip?.units.length) { toast('Nothing copied yet: select units and press Ctrl+C.', true); return; }
    await load();
    const same = clip.ch === ctx.ch();
    const placed = clip.units.map(c => ({ ...c, x: x + c.dx, y: y + c.dy }));
    const off = placed.filter(p => !inArea(p.x, p.y));
    if (off.length) { toast(`${off.length} of them would be off the map: paste further from the edge.`, true); return; }
    if (same) {
      // same chapter: each keeps its army, behaviour and arrival
      const byList = {};
      for (const p of placed) (byList[p.list] ??= []).push(p);
      try {
        const rows = [];
        const r = await api('mapunit', { op: 'pastemany', ch: ctx.ch(), groups: Object.entries(byList).map(([l, us]) => ({ list: Number(l), units: us })) });
        rows.push(...r.rows);
        await afterEdit(rows); toast(`Pasted ${placed.length} unit${placed.length > 1 ? 's' : ''} (Ctrl+Z undoes it)`);
      } catch (e) { toast(e.message, true); }
      return;
    }
    // another chapter: choose their army and when they arrive here
    const enemySlots = info.armies.filter(([s]) => s !== 0);
    const armySel = select(enemySlots.map(([s, n]) => [s, n]), enemySlots[0]?.[0], 'Army');
    const progSel = h('select', { class: 'in', 'aria-label': 'What they do' });
    const drawProg = () => progSel.replaceChildren(...programs(Number(armySel.value)).map(([k, t]) => h('option', { value: k }, t)));
    armySel.onchange = drawProg; drawProg();
    const startList = info.lists.find(l => l.start)?.list ?? info.lists[0]?.list ?? 0;
    const listSel = select(info.lists.map(l => [l.list, `${l.when} (list ${l.list})`]), startList, 'Arrive');
    const ok = h('button', { class: 'btn btn-gilt' }, `Paste ${placed.length} unit${placed.length > 1 ? 's' : ''}`);
    const modal = card(`Paste ${placed.length} unit${placed.length > 1 ? 's' : ''}`, `From another chapter, at ${x}, ${y}`,
      h('div', { class: 'mcard-body' }, h('div', { class: 'mcard-grid' }, field('Army', armySel), field('What they do', progSel), h('div', { class: 'mcard-wide' }, field('Arrive', listSel)))),
      [h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'), ok]);
    ok.onclick = async () => {
      ok.disabled = true;
      try {
        const us = placed.map(p => ({ ...p, slot: Number(armySel.value), orders: Number(progSel.value) }));
        const r = await api('mapunit', { op: 'paste', ch: ctx.ch(), list: Number(listSel.value), units: us });
        modal.remove(); await afterEdit(r.rows); toast(`Pasted ${placed.length} unit${placed.length > 1 ? 's' : ''}`);
      } catch (e) { ok.disabled = false; toast(e.message, true); }
    };
    void viaKey;
    ok.focus();
  }

  async function duplicate(sel) {
    // the first free spot next to each unit, nearest first
    await load();
    const taken = new Set(units().map(u => `${u.x},${u.y}`));
    const groups = {};
    for (const u of sel) {
      let spot = null;
      for (let r = 1; r <= 3 && !spot; r++) {
        for (const [dx, dy] of ring(r)) {
          const nx = Number(u.x) + dx, ny = Number(u.y) + dy;
          if (inArea(nx, ny) && !taken.has(`${nx},${ny}`) && (info.costs[0]?.[terrainAt(nx, ny)] ?? 0) < 128) { spot = [nx, ny]; break; }
        }
      }
      if (!spot) continue;
      taken.add(`${spot[0]},${spot[1]}`);
      (groups[u.list] ??= []).push({ char_id: u.char_id, x: spot[0], y: spot[1], slot: Number(u.army_slot), orders: Number(u.orders) || 0, leader: false });
    }
    if (!Object.keys(groups).length) { toast('No free spot next to it.', true); return; }
    try {
      const r = await api('mapunit', { op: 'pastemany', ch: ctx.ch(), groups: Object.entries(groups).map(([l, us]) => ({ list: Number(l), units: us })) });
      await afterEdit(r.rows); toast('Duplicated (Ctrl+Z undoes it)');
    } catch (e) { toast(e.message, true); }
  }
  function ring(r) {
    const out = [];
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) if (Math.max(Math.abs(dx), Math.abs(dy)) === r) out.push([dx, dy]);
    return out.sort((a, b) => (Math.abs(a[0]) + Math.abs(a[1])) - (Math.abs(b[0]) + Math.abs(b[1])));
  }

  async function remove(sel) {
    if (!sel.length) return;
    try {
      await api('mapunit', { op: 'remove', rows: sel.map(u => u._row) });
      for (const u of sel) danger.rows.delete(u._row);
      await afterEdit([]);
      toast(`Removed ${sel.length > 1 ? sel.length + ' units' : sel[0].name} (Ctrl+Z undoes it)`);
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ events from the map
  async function eventCard(kind, preset) {
    try { await load(); } catch (e) { toast(e.message, true); return; }
    const lord = info.lord;
    const pin = (label, val, anyone) => {
      const e = h('input', { class: 'in', list: 'mcpeople', value: val === undefined ? '' : personLabel(val), placeholder: anyone ? 'Name, or anyone' : 'Name', 'aria-label': label });
      return [field(label, e), () => {
        const n = parsePerson(e.value, anyone);
        if (n === null) { e.classList.add('bad'); throw new Error(`${label}: pick someone from the list${anyone ? ', or anyone' : ''}.`); }
        return n;
      }];
    };
    const text = (label, ph) => {
      const e = h('textarea', { class: 'in mcard-text', rows: 2, placeholder: ph, 'aria-label': label });
      return [field(label, e), () => e.value.trim()];
    };
    const T = {
      talk: ['A talk', 'Choose who can Talk to whom on the map; they get a short conversation.'],
      recruit: ['Recruit by talking', 'When the first unit talks to the second, the second joins your army.'],
      battle: ['A battle quote', 'Said when the second unit is in a fight (with anyone, or one unit).'],
      death: ['A death quote', 'The unit\'s last words when it falls.'],
      visit: ['A village visit', 'What the villagers say; add gifts on the Events page.'],
      area: ['When someone reaches an area', 'Someone says something when a unit enters the area.'],
      turn: ['A message on a turn', 'Someone says something as a turn starts (turn 2 on; for turn 1 add to the chapter\'s opening).'],
    }[kind];
    const rows = [], reads = [];
    const add = ([el, rd], key) => { rows.push(el); reads.push([key, rd]); };
    const area = { x1: preset.x1 ?? 0, y1: preset.y1 ?? 0, x2: preset.x2 ?? 2, y2: preset.y2 ?? 2 };
    if (kind === 'talk' || kind === 'recruit') {
      add(pin('Who talks', preset.a ?? lord), 'a'); add(pin(kind === 'recruit' ? 'To (joins you)' : 'To whom', preset.b), 'b');
      add(text('First says', 'Write the first line'), 'line1'); add(text('The other replies', kind === 'recruit' ? 'Their reply (then they join)' : 'The reply'), 'line2');
    } else if (kind === 'battle') {
      add(pin('Fighting', preset.a ?? 0xFFFF, true), 'a'); add(pin('Speaker', preset.b), 'b'); add(text('Quote', 'What they say'), 'line');
    } else if (kind === 'death') {
      add(pin('Who', preset.unit), 'unit'); add(text('Last words', 'What they say'), 'line');
    } else if (kind === 'visit') {
      const vs = ctx.M().locations.filter(L => L.kind === 'village');
      const sel = select(vs.map(L => [L.index, `Village ${L.index} at ${L.x}, ${L.y}`]), preset.loc, 'Village');
      rows.push(field('Village', sel)); reads.push(['loc', () => Number(sel.value)]);
      add(text('Villager says', 'Welcome, traveler! Please, take this.'), 'line');
    } else if (kind === 'area') {
      add(pin('Who reaches it', lord, true), 'unit');
      const at = h('span', { class: 'note' });
      const show = () => { at.textContent = `(${area.x1}, ${area.y1}) to (${area.x2}, ${area.y2})`; };
      show();
      rows.push(h('div', { class: 'lbl' }, h('span', {}, 'Area'), h('div', { class: 'mcard-inline' }, at,
        h('button', { type: 'button', class: 'btn btn-line', onclick: async () => {
          const r = await pickArea(ctx.ch(), { rect: area, unitName: 'the unit' });
          if (r) { Object.assign(area, r); show(); }
        } }, 'Pick on map…'))));
      add(pin('Who speaks', lord), 'who'); add(text('Says', 'What they say'), 'line');
    } else if (kind === 'turn') {
      const t = num(preset.turn ?? 2, 'Turn', 2, 99);
      rows.push(field('Turn', t)); reads.push(['turn', () => Number(t.value)]);
      add(pin('Who speaks', lord), 'who'); add(text('Says', 'What they say'), 'line');
    }
    const ok = h('button', { class: 'btn btn-gilt' }, 'Make event');
    const modal = card(T[0], T[1], h('div', { class: 'mcard-body' }, h('div', { class: 'mcard-grid' }, rows.map(r => h('div', { class: 'mcard-wide' }, r))),
      h('p', { class: 'hint' }, STAT_LINE)),
    [h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'), ok]);
    ok.onclick = async () => {
      let args;
      try { args = Object.fromEntries(reads.map(([k, rd]) => [k, rd()])); } catch (e) { toast(e.message, true); return; }
      if (kind === 'area') Object.assign(args, area);
      if (kind === 'battle' && args.b === 0xFFFF) { toast('Choose who speaks.', true); return; }
      ok.disabled = true;
      try {
        const r = await api('newevent', { ch: ctx.ch(), kind, ...args });
        await refreshSession();
        await ctx.reload();
        const box = modal.querySelector('.mcard-box');
        box.replaceChildren(h('div', { class: 'mcard-head' }, h('div', {}, h('h2', {}, 'Event made'),
          h('p', { class: 'sub' }, r.merged ? 'That turn already had a conversation: the message was added to it.' : `${T[0]} in ${ctx.M().title.split(':')[0]}.`))),
        h('p', {}, 'You can change its words, add gifts or more lines on the Events page. Ctrl+Z undoes it.'),
        h('div', { class: 'modal-actions' },
          h('button', { class: 'btn btn-line', onclick: () => { modal.remove(); openEventAt(ctx.ch(), r.line); go('events'); } }, 'Open on the Events page'),
          h('button', { class: 'btn btn-gilt', onclick: () => modal.remove() }, 'Done')));
        box.querySelector('.btn-gilt').focus();
      } catch (e) { ok.disabled = false; toast(e.message, true); }
    };
    modal.querySelector('input, select, textarea')?.focus();
  }

  // ------------------------------------------------------------ how the chapter is won
  // The game ends a chapter with an event whose scene runs $78 (chapter clear). Its condition is usually
  // `02`: your army takes a castle. The card points it at another castle, or turns it into "survive until
  // turn N starts" (`01`); the ending scene itself (and its words) stays.
  async function winCard() {
    let w;
    try { w = await api('wincond?ch=' + ctx.ch()); } catch (e) { toast(e.message, true); return; }
    const editable = w.endings.filter(e => e.kind !== 'other');
    if (!editable.length) {
      const m = card('How this chapter is won', ctx.M().title, h('div', { class: 'mcard-body' },
        h('p', {}, w.endings.length ? `This chapter ends with: ${w.endings.map(e => e.words).join('; ')}. The editor can only change endings it understands (take a castle, defeat someone, rout armies, survive until a turn).`
          : 'This chapter ends through its scripted story sequence (not one event the editor can change). The Prologue and chapters 1 and 3-11 end with one event, and those can be changed here.')),
      [h('button', { class: 'btn btn-gilt', onclick: () => m.remove() }, 'OK')]);
      return;
    }
    const e = editable[0];
    const radio = k => h('input', { type: 'radio', name: 'mcwin', checked: e.kind === k });
    const seize = radio('seize'), boss = radio('boss'), rout = radio('rout'), turn = radio('turn');
    const castleSel = select(w.castles.map(c => [c.index, `${c.name}${c.holder ? ' (held by ' + c.holder + ')' : ''}`]), e.loc ?? w.castles[w.castles.length - 1]?.index, 'Castle');
    const people = w.people.filter(p => !p.shared);
    const bossSel = select(people.map(p => [p.id, `${p.name} (${p.army})`]), e.unit ?? people[0]?.id, 'Who');
    const sel = new Set(e.slots || w.armies.filter(a => a.units).slice(0, 1).map(a => a.slot));
    const boxes = w.armies.map(a => {
      const c = h('input', { type: 'checkbox', checked: sel.has(a.slot) });
      c.dataset.slot = a.slot;
      c.onchange = () => { rout.checked = true; };
      return h('label', { class: 'mcard-radio' }, c, ' ' + a.name + (a.units ? ` (${a.units} unit${a.units > 1 ? 's' : ''} placed)` : ' (no units placed)'));
    });
    const turnIn = num(e.turn ?? 10, 'Turn', 2, 99);
    const sub = (...k) => h('div', { class: 'mcard-sub' }, ...k);
    const ok = h('button', { class: 'btn btn-gilt' }, 'Save');
    const m = card('How this chapter is won', `Now: ${e.words}`, h('div', { class: 'mcard-body' },
      h('label', { class: 'mcard-radio' }, seize, ' Take a castle (seize)'),
      sub(field('Castle', castleSel)),
      h('label', { class: 'mcard-radio' }, boss, ' Defeat a commander (boss)'),
      sub(people.length ? field('Who', bossSel) : h('p', { class: 'hint', style: 'margin:0' }, 'No one on this map can be chosen: every enemy here shares a character with another unit.'),
        h('p', { class: 'hint', style: 'margin:6px 0 0' }, 'The chapter ends the moment they fall, whoever defeats them.')),
      h('label', { class: 'mcard-radio' }, rout, ' Rout: defeat every unit of these armies'),
      sub(w.armies.length ? h('div', {}, ...boxes) : h('p', { class: 'hint', style: 'margin:0' }, 'This chapter has no other armies.'),
        h('p', { class: 'hint', style: 'margin:6px 0 0' }, 'Checked as each army\'s phase begins, so the chapter ends at the start of the next phase after the last of them falls. An army with no one on the map yet counts as gone, so leave out armies that only arrive later, and your allies.')),
      h('label', { class: 'mcard-radio' }, turn, ' Defend: survive until a turn starts'),
      sub(field('Turn', turnIn), h('p', { class: 'hint', style: 'margin:6px 0 0' }, 'The chapter ends as your phase of that turn begins.')),
      h('p', { class: 'hint' }, 'Whichever you pick, the chapter\'s own ending scene plays, then the Save Game screen and the next chapter. Change the scene\'s words on the Events page.'),
      w.endings.length > 1 ? h('p', { class: 'hint' }, `This chapter has ${w.endings.length} ending events; the card changes the first.`) : null),
    [h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'), ok]);
    castleSel.onfocus = () => { seize.checked = true; };
    bossSel.onfocus = () => { boss.checked = true; };
    turnIn.onfocus = () => { turn.checked = true; };
    ok.onclick = async () => {
      let spec;
      if (seize.checked) spec = { kind: 'seize', loc: Number(castleSel.value) };
      else if (boss.checked) spec = { kind: 'boss', unit: Number(bossSel.value) };
      else if (rout.checked) spec = { kind: 'rout', slots: [...m.querySelectorAll('input[type=checkbox][data-slot]')].filter(c => c.checked).map(c => Number(c.dataset.slot)) };
      else spec = { kind: 'turn', turn: Number(turnIn.value) };
      ok.disabled = true;
      if (await setWin(spec, e.line)) m.remove();
      else ok.disabled = false;
    };
  }

  async function setWin(spec, line) {
    try {
      if (line === undefined) {
        const w = await api('wincond?ch=' + ctx.ch());
        const e = w.endings.find(x => x.kind !== 'other');
        if (!e) { winCard(); return; }
        line = e.line;
      }
      const r = await api('wincond', { ch: ctx.ch(), line, ...spec });
      await refreshSession();
      await ctx.reload();
      toast(`The chapter is won: ${r.endings.find(x => x.line === line)?.words || 'changed'} (Ctrl+Z undoes it)`);
      return true;
    } catch (er) { toast(er.message, true); return false; }
  }

  // ------------------------------------------------------------ a character arrives
  // Someone comes onto the map during the chapter: into your army at once (as Azel and Lex do), or into
  // another army (enemy or neutral) to be recruited by talking. They walk in from a cell you pick or
  // just appear, at the end of the opening, as a turn starts, when someone reaches an area, or when a
  // castle is taken. An optional conversation follows.
  async function arrivalCard(x, y) {
    try { await load(true); } catch (e) { toast(e.message, true); return; }
    const M = ctx.M();
    const [ax, ay, aw, ah] = M.area || [0, 0, M.width, M.height];
    const edges = [[ax, y, x - ax], [ax + aw - 1, y, ax + aw - 1 - x], [x, ay, y - ay], [x, ay + ah - 1, ay + ah - 1 - y]];
    const near = edges.sort((a, b) => a[2] - b[2])[0];
    let from = { x: near[0], y: near[1] };
    const area = { x1: Math.max(ax, x - 3), y1: Math.max(ay, y - 3), x2: Math.min(ax + aw - 1, x + 3), y2: Math.min(ay + ah - 1, y + 3) };
    const whoIn = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'Who arrives', placeholder: 'e.g. Azel' });
    const join = h('input', { type: 'radio', name: 'arrside', checked: true });
    const other = h('input', { type: 'radio', name: 'arrside' });
    const others = info.armies.filter(([sl]) => sl !== 0);
    const armySel = select(others.map(([sl, n]) => [sl, `${n} (slot ${sl})`]), others[0]?.[0], 'Army');
    const ordersSel = select(programs(Number(armySel.value)), 0, 'What it does');
    armySel.addEventListener('change', () => ordersSel.replaceChildren(...programs(Number(armySel.value)).map(([v, t]) => h('option', { value: v }, t))));
    const recruit = h('input', { type: 'checkbox', checked: true });
    const talker = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'Who recruits them', value: personLabel(info.lord ?? 1) });
    const otherBox = h('div', { class: 'mcard-sub', hidden: true },
      h('div', { class: 'mcard-grid' }, field('Army', armySel), field('What it does', ordersSel)),
      h('label', { class: 'mcard-radio' }, recruit, ' Can be recruited by talking to them'), field('Who talks to them', talker));
    const sideSync = () => { otherBox.hidden = !other.checked; };
    join.onchange = other.onchange = sideSync;
    const walk = h('input', { type: 'radio', name: 'arrent', checked: true });
    const appear = h('input', { type: 'radio', name: 'arrent' });
    const fromTxt = h('span', { class: 'note' });
    const showFrom = () => { fromTxt.textContent = `from (${from.x}, ${from.y}) to (${x}, ${y})`; };
    showFrom();
    const fromBtn = h('button', { type: 'button', class: 'btn btn-line', onclick: async () => {
      const r = await pickArea(ctx.ch(), { rect: { x1: from.x, y1: from.y, x2: from.x, y2: from.y }, unitName: 'where they come from (one cell)' });
      if (r) { from = { x: r.x1, y: r.y1 }; showFrom(); }
    } }, 'Pick on map…');
    const whenSel = select([['opening', 'At the end of the chapter\'s opening'], ['turn', 'As a turn starts'], ['area', 'When someone reaches an area'], ['seize', 'When a castle is taken']], 'turn', 'When');
    const turnIn = num(2, 'Turn', 2, 99);
    const castles = M.locations.filter(L => L.kind === 'castle');
    const castleSel = select(castles.map(L => [L.index, L.name || `Castle ${L.index}`]), castles[0]?.index, 'Castle');
    const bySel = select(info.armies.map(([sl, n]) => [sl, sl === 0 ? `${n} (you)` : n]), 0, 'Taken by');
    const areaWho = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'Who reaches it', value: 'anyone' });
    const areaTxt = h('span', { class: 'note' });
    const showArea = () => { areaTxt.textContent = `(${area.x1}, ${area.y1}) to (${area.x2}, ${area.y2})`; };
    showArea();
    const whenBoxes = {
      turn: h('div', { class: 'mcard-grid' }, field('Turn', turnIn)),
      area: h('div', { class: 'mcard-grid' }, field('Who reaches it', areaWho), h('div', { class: 'lbl' }, h('span', {}, 'Area'),
        h('div', { class: 'mcard-inline' }, areaTxt, h('button', { type: 'button', class: 'btn btn-line', onclick: async () => {
          const r = await pickArea(ctx.ch(), { rect: area, unitName: areaWho.value.replace(/\s*\(\d+\)$/, '') || 'someone' });
          if (r) { Object.assign(area, r); showArea(); }
        } }, 'Pick on map…')))),
      seize: h('div', { class: 'mcard-grid' }, field('Castle', castleSel), field('Taken by', bySel)),
    };
    const whenSync = () => { for (const [k, el] of Object.entries(whenBoxes)) el.hidden = whenSel.value !== k; };
    whenSel.addEventListener('change', whenSync);
    const aIn = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'First speaker', placeholder: 'the newcomer' });
    const bIn = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'Second speaker', placeholder: 'nobody' });
    const talkIn = h('textarea', { class: 'in', rows: 3, 'aria-label': 'What they say', placeholder: 'Optional. One line each; start a line with 2: for the second speaker.' });
    const ok = h('button', { class: 'btn btn-gilt' }, 'Add');
    const m = card('A character arrives', `At (${x}, ${y})`, h('div', { class: 'mcard-body' },
      field('Who', whoIn),
      h('label', { class: 'mcard-radio' }, join, ' Joins your army at once'),
      h('label', { class: 'mcard-radio' }, other, ' Arrives in another army (enemy or neutral)'), otherBox,
      h('label', { class: 'mcard-radio' }, walk, ' Walks in ', fromTxt, ' ', fromBtn),
      h('label', { class: 'mcard-radio' }, appear, ' Just appears there'),
      field('When', whenSel), ...Object.values(whenBoxes),
      h('div', { class: 'mcard-grid' }, field('Speaker 1', aIn), field('Speaker 2', bIn)),
      field('Conversation', talkIn),
      h('p', { class: 'hint' }, 'Units in your army walk from where you pick to this cell. Someone arriving in another army is placed here and is shown walking in first. A character should arrive only once per chapter.')),
    [h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'), ok], 'mcard-wide');
    whenSync();
    ok.onclick = async () => {
      const uid = parsePerson(whoIn.value);
      if (uid === null) { toast('Who arrives?', true); return; }
      const body = { ch: ctx.ch(), unit: uid, x, y, side: join.checked ? 'join' : 'army', entrance: walk.checked ? 'walk' : 'appear', fx: from.x, fy: from.y, when: { kind: whenSel.value } };
      if (!join.checked) { body.slot = Number(armySel.value); body.orders = Number(ordersSel.value); }
      if (whenSel.value === 'turn') body.when.turn = Number(turnIn.value);
      if (whenSel.value === 'area') Object.assign(body.when, area, { unit: parsePerson(areaWho.value, true) ?? 0xFFFF });
      if (whenSel.value === 'seize') Object.assign(body.when, { loc: Number(castleSel.value), by: Number(bySel.value) });
      if (talkIn.value.trim()) {
        const a = aIn.value.trim() ? parsePerson(aIn.value) : uid, b2 = bIn.value.trim() ? parsePerson(bIn.value) : null;
        if (a === null) { toast('Who is the first speaker?', true); return; }
        const lines = talkIn.value.split('\n').map(t => t.trim()).filter(Boolean).map(t => /^2\s*:/.test(t) ? { who: 'b', text: t.replace(/^2\s*:\s*/, '') } : { who: 'a', text: t.replace(/^1\s*:\s*/, '') });
        body.talk = { a, b: b2 ?? undefined, lines };
      }
      ok.disabled = true;
      try {
        const r = await api('arrival', body);
        if (!join.checked && recruit.checked) {
          const t = parsePerson(talker.value);
          if (t !== null) await api('newevent', { ch: ctx.ch(), kind: 'recruit', a: t, b: uid });
        }
        await refreshSession(); await ctx.reload(); m.remove();
        toast(`${personLabel(uid)} arrives: ${r.when} (Ctrl+Z undoes it)`);
      } catch (e) { toast(e.message, true); ok.disabled = false; }
    };
    whoIn.focus();
  }

  // ------------------------------------------------------------ add or take away castles and villages
  // A site is a record the game reads (index, kind, x, y; castles add a name, town buttons and an
  // armory) plus the tiles on the map. The card can copy the tiles around one of the chapter's own
  // castles or villages so the new one looks right straight away.
  async function siteCard(kind, x, y) {
    try { await load(true); } catch (e) { toast(e.message, true); return; }
    const M = ctx.M();
    const same = M.locations.filter(L => L.kind === kind);
    const lookSel = select([['', 'Leave the map tiles as they are'], ...same.map(L => [L.index, `Copy the tiles of ${L.kind === 'castle' ? (L.name || 'castle ' + L.index) : 'village ' + L.index} (${L.x}, ${L.y})`])],
      same.length ? same[0].index : '', 'Look');
    const names = (armies.castleNames || []).map((n, i) => [i, n ? `${n} (${i})` : `Name ${i}`]).filter(([i, n]) => !/^Name /.test(n));
    const nameSel = kind === 'castle' ? select(names, names[0]?.[0], 'Castle name') : null;
    const holderSel = kind === 'castle' ? select([['', 'Nobody (empty)'], ...info.armies.map(([s, n]) => [s, s === 0 ? `${n} (you)` : n])], '', 'Held by') : null;
    const goldIn = kind === 'village' ? num(5000, 'Gold', 1, 50000) : null;
    const ok = h('button', { class: 'btn btn-gilt' }, kind === 'castle' ? 'Add castle' : 'Add village');
    const foot = kind === 'castle' ? '3 wide and 4 tall, with the gate (where units seize it) on the cell you clicked' : '3 wide and 2 tall, with the door on the cell you clicked';
    const m = card(kind === 'castle' ? 'New castle' : 'New village', `At (${x}, ${y}) · ${M.locations.length + 1} of 16 castles and villages`, h('div', { class: 'mcard-body' },
      kind === 'castle' ? h('div', { class: 'mcard-grid' }, field('Name', nameSel), field('Held by', holderSel)) : h('div', { class: 'mcard-grid' }, field('Gold for visiting', goldIn)),
      field('Look on the map', lookSel),
      h('p', { class: 'hint' }, `A ${kind} takes ${foot}. Town buttons, armory and visit events are set from the castle or village afterwards.`)),
    [h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'), ok]);
    ok.onclick = async () => {
      ok.disabled = true;
      try {
        const body = { ch: ctx.ch(), add: kind, x, y };
        if (lookSel.value !== '') body.look = Number(lookSel.value);
        if (nameSel) body.castle_id = Number(nameSel.value);
        if (holderSel && holderSel.value !== '') body.army = Number(holderSel.value);
        if (goldIn) body.gold = Number(goldIn.value);
        await api('sites', body);
        await refreshSession();
        await ctx.reload();
        m.remove();
        toast(`Added a ${kind} at (${x}, ${y}) (Ctrl+Z undoes it)`);
      } catch (e) { toast(e.message, true); ok.disabled = false; }
    };
  }

  async function removeSite(site) {
    const M = ctx.M();
    const last = M.locations.reduce((a, L) => Math.max(a, Number(L.index)), -1);
    const what = site.kind === 'castle' ? (site.name || 'this castle') : `village ${site.index}`;
    const m = card(`Remove ${what}?`, `(${site.x}, ${site.y})`, h('div', { class: 'mcard-body' },
      h('p', {}, 'The game will no longer treat this spot as a ' + site.kind + '. Its own events stop playing and its army no longer holds it. The map tiles stay: paint over them with the Paint tool.'),
      Number(site.index) !== last ? h('p', { class: 'hint' }, `Castles and villages are numbered without gaps, so the last one (number ${last}) takes number ${site.index}; its events, army and enemy orders are updated to match.`) : null),
    [h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'),
      h('button', { class: 'btn btn-gilt', onclick: async () => {
        try {
          await api('sites', { ch: ctx.ch(), remove: Number(site.index) });
          await refreshSession(); await ctx.reload(); m.remove();
          toast(`Removed ${what} (Ctrl+Z undoes it)`);
        } catch (e) { toast(e.message, true); }
      } }, 'Remove')]);
  }

  // ------------------------------------------------------------ the chapter's opening scene
  // What plays when the chapter starts, as a list of simple steps: music, move the camera, units arrive,
  // a conversation over the map, a pause, fade the music. Steps the editor doesn't know (the game's own
  // animations) stay as "game steps" unless taken out.
  async function openingCard(at) {
    let o;
    try { await load(); o = await api('opening?ch=' + ctx.ch()); } catch (e) { toast(e.message, true); return; }
    const steps = o.steps.map(s => ({ ...s, _orig: true }));
    let mode = 'replace';
    const listBox = h('ol', { class: 'opsteps' });
    const songName = n => { const s = o.songs.find(([k]) => k === n); return s && s[1] ? `${n}: ${s[1]}` : `Song ${n}`; };
    const words = st => ({
      music: () => `Music: ${songName(Number(st.song))}`,
      camera: () => `Camera moves to (${st.x}, ${st.y})`,
      units: () => `Units arrive: group ${st.list}${(o.lists.find(l => l.list === Number(st.list)) || {}).when ? '' : ''}`,
      talk: () => `Conversation: ${st.lines ? st.lines.map(l => l.text).join(' / ') : String(st.text || '').replace(/\{[^}]*\}/g, ' ').replace(/\s+/g, ' ').trim()}`,
      wait: () => `Pause ${st.frames} frames (${(st.frames / 60).toFixed(1)} s)`,
      fade: () => 'Fade the music out',
      game: () => `Game step: ${st.what || st.hex}`,
      setup: () => `Map set-up (always kept): ${st.what || st.hex}`,
    }[st.kind] || (() => st.kind))();
    const draw = () => {
      listBox.replaceChildren(...steps.map((st, i) => h('li', { class: 'opstep' + (st.kind === 'game' || st.kind === 'setup' ? ' game' : '') },
        h('span', {}, words(st)),
        st.kind === 'setup' ? null : h('span', { class: 'opstep-btns' },
          h('button', { class: 'icon-btn', title: 'Up', disabled: i === 0 || steps[i - 1].kind === 'setup', onclick: () => { [steps[i - 1], steps[i]] = [steps[i], steps[i - 1]]; draw(); } }, '↑'),
          h('button', { class: 'icon-btn', title: 'Down', disabled: i === steps.length - 1, onclick: () => { [steps[i + 1], steps[i]] = [steps[i], steps[i + 1]]; draw(); } }, '↓'),
          h('button', { class: 'icon-btn', title: 'Take out', onclick: () => { steps.splice(i, 1); draw(); } }, '×')))));
      if (!steps.length) listBox.append(h('li', { class: 'hint' }, 'No steps yet: add some below.'));
    };
    // adding steps
    const songSel = select(o.songs.map(([n, nm]) => [n, nm ? `${n}: ${nm}` : `Song ${n}`]), 0x70, 'Song');
    const camX = num(at?.x ?? 8, 'Camera x', 0, 63), camY = num(at?.y ?? 7, 'Camera y', 0, 63);
    const listSel = select(o.lists.map(l => [l.list, `Group ${l.list} · ${l.when}`]), o.lists[0]?.list, 'Units');
    const aIn = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'First person', value: personLabel(info.lord ?? 1) });
    const bIn = h('input', { class: 'in', list: 'mcpeople', 'aria-label': 'Second person', placeholder: 'nobody' });
    const talkIn = h('textarea', { class: 'in', rows: 3, 'aria-label': 'Conversation', placeholder: 'One line each. Start a line with 2: for the second person; other lines are the first person\'s.' });
    const waitIn = num(60, 'Pause frames', 1, 600);
    const add = st => { steps.push(st); draw(); };
    const addTalk = () => {
      const a = parsePerson(aIn.value), b = bIn.value.trim() ? parsePerson(bIn.value) : null;
      if (a === null) { toast('Who is the first person?', true); return; }
      const lines = talkIn.value.split('\n').map(t => t.trim()).filter(Boolean).map(t => /^2\s*:/.test(t) ? { who: 'b', text: t.replace(/^2\s*:\s*/, '') } : { who: 'a', text: t.replace(/^1\s*:\s*/, '') });
      if (!lines.length) { toast('Write what is said.', true); return; }
      add({ kind: 'talk', a, b: b ?? undefined, lines }); talkIn.value = '';
    };
    const tabs = h('div', { class: 'opadd' },
      h('div', { class: 'opadd-row' }, field('Music', songSel), h('button', { class: 'btn btn-line', onclick: () => add({ kind: 'music', song: Number(songSel.value) }) }, '+ Music')),
      h('div', { class: 'opadd-row' }, field('Camera x', camX), field('y', camY), h('button', { class: 'btn btn-line', onclick: () => add({ kind: 'camera', x: Number(camX.value), y: Number(camY.value) }) }, '+ Camera')),
      o.lists.length ? h('div', { class: 'opadd-row' }, field('Units', listSel), h('button', { class: 'btn btn-line', onclick: () => add({ kind: 'units', list: Number(listSel.value) }) }, '+ Units arrive')) : null,
      h('div', { class: 'opadd-row' }, field('Speaker 1', aIn), field('Speaker 2', bIn)),
      h('div', { class: 'opadd-row' }, field('Conversation', talkIn), h('button', { class: 'btn btn-line', onclick: addTalk }, '+ Conversation')),
      h('div', { class: 'opadd-row' }, field('Pause (frames, 60 = 1 s)', waitIn), h('button', { class: 'btn btn-line', onclick: () => add({ kind: 'wait', frames: Number(waitIn.value) }) }, '+ Pause'),
        h('button', { class: 'btn btn-line', onclick: () => add({ kind: 'fade' }) }, '+ Fade music')));
    const rep = h('input', { type: 'radio', name: 'opmode', checked: true, onchange: () => { mode = 'replace'; } });
    const bef = h('input', { type: 'radio', name: 'opmode', onchange: () => { mode = 'after'; } });
    const ok = h('button', { class: 'btn btn-gilt' }, 'Save opening');
    const m = card('Opening scene', `${ctx.M().title} · scene ${o.scene}`, h('div', { class: 'mcard-body' },
      listBox, tabs,
      h('label', { class: 'mcard-radio' }, rep, ' These steps are the whole opening'),
      h('label', { class: 'mcard-radio' }, bef, ' Keep the game\'s own opening and play my new steps after it'),
      o.complex ? h('p', { class: 'hint' }, 'The game\'s opening for this chapter jumps around inside itself, so its game steps can\'t be kept one by one: take them all out to replace it, or keep it and play your new steps after it.') : null,
      h('p', { class: 'hint' }, 'Camera x, y is the cell to look at (right-click the map and choose Opening scene to start from that cell). Groups of units come in where the Maps page shows them. Keep the "Units arrive" steps of the game\'s own opening, or its enemies never appear.')),
    [h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'), ok], 'mcard-wide');
    draw();
    ok.onclick = async () => {
      let send = steps;
      if (mode === 'after') send = steps.filter(s => !s._orig);
      else send = [...steps.filter(s => s.kind === 'setup'), ...steps.filter(s => s.kind !== 'setup')];
      if (mode === 'replace' && o.complex && steps.some(s => s.kind === 'game')) { toast('Take out the game steps first (see the note), or choose to play your steps first.', true); return; }
      ok.disabled = true;
      try {
        await api('opening', { ch: ctx.ch(), mode, steps: send.map(({ what, text, _orig, ...s }) => s) });
        await refreshSession(); await ctx.reload(); m.remove();
        toast('Opening saved (Ctrl+Z undoes it). Test it with ▶ Test this chapter.');
      } catch (e) { toast(e.message, true); ok.disabled = false; }
    };
  }

  // ------------------------------------------------------------ the chapter's title card
  // The card that opens a chapter ("Chapter 3 / Eldigan the Lionheart") is a picture: Project Naga drew
  // the titles. A new title is drawn here with a font on this computer, styled like the game's (light
  // letters, a black outline) and stored as that picture, so the build always looks like the preview.
  async function titleCard() {
    let t;
    try { t = await api('chaptitle?ch=' + ctx.ch()); } catch (e) { toast(e.message, true); return; }
    const look = { font: 'Georgia', size: 18, width: 82, ...(t.look || {}) };
    const textIn = h('input', { class: 'in', value: t.text || t.gameText, maxlength: t.textMax, 'aria-label': 'Title', spellcheck: 'false' });
    const fontSel = select(TITLE_FONTS.map(f => [f, f]), look.font, 'Font');
    const sizeIn = num(look.size, 'Letter size', 12, 26);
    const widthIn = num(look.width, 'Letter width (%)', 50, 120);
    const cv = h('canvas', { class: 'mtitle-cv', width: 512, height: 112, 'aria-label': 'Preview of the title card' });
    const warn = h('p', { class: 'mcard-warn', hidden: true });
    const ok = h('button', { class: 'btn btn-gilt' }, 'Save');
    let cur = null, touched = false;
    const draw = px => {
      const g = cv.getContext('2d'), img = g.createImageData(256, 56);
      const tint = [1.55, 1.25, 1.05];
      for (let y = 0; y < 56; y++) for (let x = 0; x < 256; x++) {
        const src = y < 4 ? 0 : y < 28 ? Number(t.label[(y - 4) * 256 + x]) : y < 52 ? Number(px[(y - 28) * 256 + x]) : 0;
        const o = (y * 256 + x) * 4, gv = src ? t.greys[src - 1] : null;
        if (gv === null) { img.data.set([16, 8, 8, 255], o); continue; }
        img.data.set([Math.min(255, gv * tint[0]), Math.min(255, gv * tint[1]), Math.min(255, gv * tint[2]), 255], o);
      }
      const tmp = h('canvas', { width: 256, height: 56 });
      tmp.getContext('2d').putImageData(img, 0, 0);
      g.imageSmoothingEnabled = false;
      g.drawImage(tmp, 0, 0, 512, 112);
    };
    const update = () => {
      const text = textIn.value.replace(/\s+/g, ' ').trim();
      const bad = [...text].filter(c => !t.chars.includes(c));
      warn.hidden = true;
      ok.disabled = false;
      if (!text) { draw(t.orig); ok.disabled = true; cur = null; return; }
      if (bad.length) { warn.textContent = `The game has no letter for: ${[...new Set(bad)].join(' ')}`; warn.hidden = false; ok.disabled = true; return; }
      const r = renderTitle(text, { font: fontSel.value, size: Number(sizeIn.value), width: Number(widthIn.value) });
      if (r.wide) { warn.textContent = 'Too wide for the screen: make it shorter, smaller or narrower.'; warn.hidden = false; ok.disabled = true; }
      cur = { text, px: r.px };
      draw(r.px);
    };
    for (const el of [textIn, fontSel, sizeIn, widthIn]) el.addEventListener('input', () => { touched = true; update(); });
    const m = card('Chapter title', `${t.name}${t.custom ? ' · your title' : ' · the game\'s title'}`, h('div', { class: 'mcard-body' },
      cv,
      field('Title', textIn),
      h('div', { class: 'mcard-grid' }, field('Font', fontSel), field('Size', sizeIn), field('Width %', widthIn)),
      warn,
      h('p', { class: 'hint' }, `Shown when the chapter starts, and used as the chapter's name in the game's text (save screen, end-of-game record). Up to ${t.textMax} letters. Fonts come from this computer; the saved title keeps its look everywhere.`)),
    [t.custom ? h('button', { class: 'btn btn-line', onclick: async () => {
      try { await api('chaptitle', { ch: ctx.ch(), reset: true }); await refreshSession(); m.remove(); toast('The game\'s own title is back (Ctrl+Z undoes it)'); } catch (e) { toast(e.message, true); }
    } }, 'Use the game\'s title') : null,
    h('button', { class: 'btn btn-line', onclick: () => m.remove() }, 'Cancel'), ok]);
    if (t.custom && t.px) { draw(t.px); cur = { text: t.text, px: t.px }; } else draw(t.orig);
    ok.onclick = async () => {
      if (!touched && !t.custom) update();
      if (!cur) return;
      ok.disabled = true;
      try {
        await api('chaptitle', { ch: ctx.ch(), text: cur.text, px: cur.px, look: { font: fontSel.value, size: Number(sizeIn.value), width: Number(widthIn.value) } });
        await refreshSession();
        m.remove();
        toast(`${t.name} is now "${cur.text}" (Ctrl+Z undoes it)`);
      } catch (e) { toast(e.message, true); ok.disabled = false; }
    };
    textIn.focus();
    textIn.select();
  }

  // ------------------------------------------------------------ danger zones
  // Movement: entering a cell costs the game's per-terrain value + 1 for the unit's movement type
  // (the grid $87:B394 builds: roads and bridges 1, plains 2, 128 = can't enter) out of 2 x Move, so
  // Move is the number of plains a unit crosses and roads take half. Then its weapons' reach.
  // Units in the way and skills like Pass are left out: treat it as a guide.
  function reach(u) {
    const M = ctx.M();
    const c = info.classes.find(k => k.id === u.cls);
    if (!c) return null;
    const costs = info.costs[c.group] || info.costs[0] || [];
    const budget = 2 * c.move;
    const W = M.width, Hh = M.height;
    const dist = new Map();
    const start = Number(u.y) * W + Number(u.x);
    dist.set(start, 0);
    const q = [[0, start]];
    while (q.length) {
      q.sort((a, b) => a[0] - b[0]);
      const [d, i] = q.shift();
      if (d > dist.get(i)) continue;
      const x = i % W, y = (i / W) | 0;
      for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]) {
        if (nx < 0 || ny < 0 || nx >= W || ny >= Hh || !inArea(nx, ny)) continue;
        const cv = costs[M.terrain[M.words[ny * W + nx] & 0x3FF]] ?? 128;
        if (cv >= 128) continue;
        const nd = d + cv + 1, j = ny * W + nx;
        if (nd <= budget && nd < (dist.get(j) ?? 1e9)) { dist.set(j, nd); q.push([nd, j]); }
      }
    }
    let lo = 99, hi = 0;
    for (const id of u.items || []) {
      const it = info.items.find(k => k.id === id);
      if (it && it.max > 0 && it.type !== 255) { lo = Math.min(lo, it.min || 1); hi = Math.max(hi, it.max); }
    }
    const atk = new Set();
    if (hi > 0) for (const i of dist.keys()) {
      const x = i % W, y = (i / W) | 0;
      for (let dy = -hi; dy <= hi; dy++) for (let dx = -hi; dx <= hi; dx++) {
        const r = Math.abs(dx) + Math.abs(dy);
        if (r < lo || r > hi) continue;
        const nx = x + dx, ny = y + dy;
        if (nx >= 0 && ny >= 0 && nx < W && ny < Hh && !dist.has(ny * W + nx)) atk.add(ny * W + nx);
      }
    }
    return { move: dist, atk };
  }

  function toggleDanger(rows) {
    if (rows === 'all') { danger.all = !danger.all; if (!danger.all) danger.rows.clear(); }
    else {
      const on = !danger.rows.has(rows[0]);
      for (const r of rows) on ? danger.rows.add(r) : danger.rows.delete(r);
    }
    ctx.redraw();
  }

  function drawDanger(c2d, s) {
    if (!info || (!danger.all && !danger.rows.size)) return;
    const M = ctx.M();
    const shown = units().filter(u => danger.rows.has(u._row) || (danger.all && Number(u.army_slot) !== 0));
    const mv = new Map(), at = new Set();
    for (const u of shown) {
      const r = reach(u);
      if (!r) continue;
      for (const i of r.move.keys()) mv.set(i, (mv.get(i) || 0) + 1);
      for (const i of r.atk) at.add(i);
    }
    for (const [i, n] of mv) {
      c2d.fillStyle = `rgba(214, 48, 64, ${Math.min(0.5, 0.22 + 0.06 * (n - 1))})`;
      c2d.fillRect((i % M.width) * s, ((i / M.width) | 0) * s, s, s);
    }
    c2d.fillStyle = 'rgba(240, 150, 40, .28)';
    for (const i of at) if (!mv.has(i)) c2d.fillRect((i % M.width) * s, ((i / M.width) | 0) * s, s, s);
  }

  return { menu, unitCard, eventCard, winCard, setWin, titleCard, siteCard, removeSite, openingCard, arrivalCard, copy, paste, duplicate, remove, toggleDanger, drawDanger, closeMenu, danger,
    load, hasClip: () => !!clip?.units.length, unitAt };
}
