// Map cards (1.1): right-click anything on the Maps page for what you can do there. Place an
// enemy or ally, bring reinforcements in, make talks, recruits, quotes, village and area events,
// copy and paste units, and see where enemies can reach (danger zones). Each action is one small
// card with sensible defaults filled in; Enter confirms, Escape closes.
import { api, h, app, toast, refreshSession, go, loadTables } from '../app.js';
import { openEventAt } from './events.js';
import { pickArea } from './mappick.js';

const STAT_LINE = 'Write what is said, or leave it for later: the words can be changed on the Events page.';

/** ctx: { M(), ch(), reload(), select(rows), redraw(), hover() } */
export function mapActions(ctx) {
  let info = null, infoCh = null, armies = null, people = null;
  const danger = { rows: new Set(), all: false };
  let clip = null;                                      // {ch, units: [{...}]}
  try { clip = JSON.parse(sessionStorage.getItem('fe4studio-mapclip') || 'null'); } catch (e) { clip = null; }

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
    let best = null, bd = 1e9;
    for (const u of units()) {
      if (Number(u.army_slot) === 0) continue;
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
    document.body.append(modal);
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

  return { menu, unitCard, eventCard, copy, paste, duplicate, remove, toggleDanger, drawDanger, closeMenu, danger,
    load, hasClip: () => !!clip?.units.length, unitAt };
}
