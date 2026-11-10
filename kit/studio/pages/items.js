// Items, shops & villages: the weapon and ring tables, every copy of each item in the campaign,
// castle-town shops, village rewards and the arena.
import { api, h, app, toast, setField, loadTables, refreshSession, go } from '../app.js';
import { openEventAt } from './events.js';

const TYPES = ['Sword', 'Lance', 'Axe', 'Bow', 'Staff', 'Fire', 'Thunder', 'Wind', 'Light', 'Dark'];
const BLOODS = ['Baldur', 'Naga', 'Dain', 'Nova', 'Odo', 'Ullur', 'Neir', 'Fala', 'Thrud', 'Forseti', 'Bragi', 'Hezul', 'Loptous'];
const STAFF = ['', 'Heal', 'Mend', 'Recover', 'Physic', 'Fortify', 'Return', 'Warp', 'Rescue', 'Charm', 'Restore', 'Valkyria', 'Silence', 'Sleep', 'Berserk', 'Thief'];
// $08 effect + argument, as far as the game's own weapons show them
const SPECIALS = [
  [0, 'None'], [1, 'Magic sword: at range it casts a spell', 'spell'], [2, 'Magic sword: drains HP like a spell', 'spell'],
  [3, 'Drains HP (Nosferatu)'], [4, 'Brave: attacks twice'], [5, 'Long range (siege tome or ballista)'],
  [6, 'Inflicts a status', 'status'], [7, 'Loptous tome'], [8, 'Naga: protects against a weapon', 'item'],
  [9, 'Hel: leaves the target at 1 HP'], [10, 'Miracle sword'],
];
const STATUS = [[4, 'Silence'], [5, 'Sleep'], [6, 'Berserk']];
const EFFECTIVE = [[2, 'Fliers'], [8, 'Armored units']];
const RING_STAT = ['None', 'Speed', 'Magic', 'Strength', 'Defense', 'Resistance', 'Movement', 'Skill'];
const STATS = ['HP', 'Strength', 'Magic', 'Skill', 'Speed', 'Defense', 'Resistance', 'Luck'];
const FACILITIES = ['Armory', 'Pawnbroker', 'Blacksmith', 'Supply', 'Augury', 'Arena'];
const CHAPTERS = ['Prologue', 'Chapter 1', 'Chapter 2', 'Chapter 3', 'Chapter 4', 'Chapter 5', 'Chapter 6', 'Chapter 7', 'Chapter 8', 'Chapter 9', 'Chapter 10', 'Endgame'];
const NICE = { '{89}': 'á', '{9E}': 'ö', '{91}': 'é', '{4A}': '"', '{4C}': ':' };
const nice = s => String(s || '').replace(/\{[0-9A-F]{2}\}/g, m => NICE[m] ?? m);

const st = { tab: 'items', item: null, q: '', ch: 1, arenaCh: 1 };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-items') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-items', JSON.stringify(st)); } catch (e) { /* none */ } };

export async function itemsPage(root) {
  await loadTables(['items', 'rings', 'item_instances', 'names', 'skills', 'locations', 'arena', 'units_generic', 'units_playable', 'units_children', 'classes']);
  const T = app.tables;
  let use = (await api('itemuse')).use;

  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const body = h('div', { class: 'itbody' });
  root.append(h('div', { class: 'itpage' }, h('div', { class: 'ittabs' }, tabs), body));
  const TABS = [['items', 'Weapons & items'], ['shops', 'Shops & villages'], ['arena', 'Arena']];
  function drawTabs() {
    tabs.replaceChildren(...TABS.map(([k, label]) => h('button', { role: 'tab', 'aria-selected': String(st.tab === k), onclick: () => { st.tab = k; remember(); drawTabs(); draw(); } }, label)));
  }

  // ------------------------------------------------------------ shared helpers
  const allItems = () => [...T.items.rows.map(r => ({ ...r, table: 'items' })), ...T.rings.rows.map(r => ({ ...r, table: 'rings' }))];
  const itemById = id => allItems().find(r => Number(r.id) === Number(id));
  const typeName = id => nice(itemById(id)?._name) || `item ${id}`;
  const instType = i => Number(T.item_instances.rows[i]?.item_type);
  const instName = i => i == null || i === 255 ? 'nothing' : `${typeName(instType(i))} #${i}`;
  const people = () => [...T.units_playable.rows, ...T.units_children.rows];

  async function set(table, row, field, value, el) {
    try { const v = await setField(table, row, field, value); el?.classList.remove('bad'); return v; }
    catch (e) { el?.classList.add('bad'); toast(e.message, true); throw e; }
  }
  function num(table, row, field, label, opts = {}) {
    const r = T[table].rows[row];
    const e = h('input', { class: 'in num', value: r[field] ?? '', inputmode: 'numeric', 'aria-label': label });
    e.onchange = async () => { try { e.value = await set(table, row, field, e.value, e); opts.after?.(); } catch (_) { /* shown */ } };
    return h('label', { class: 'lbl' }, h('span', {}, label), e);
  }
  function sel(table, row, field, label, options, opts = {}) {
    const r = T[table].rows[row];
    const cur = String(r[field] ?? '');
    const e = h('select', { class: 'in', 'aria-label': label },
      options.map(([v, t]) => h('option', { value: v, selected: String(v) === cur }, t)),
      options.some(([v]) => String(v) === cur) ? null : h('option', { value: cur, selected: true }, `${cur} (not known)`));
    e.onchange = async () => { try { await set(table, row, field, e.value, e); opts.after?.(); } catch (_) { e.value = cur; } };
    return h('label', { class: 'lbl' }, h('span', {}, label), e);
  }
  const lbl = (label, el) => h('label', { class: 'lbl' }, h('span', {}, label), el);

  function useText(u) {
    if (u.kind === 'unit') return `${u.name} starts with it`;
    if (u.kind === 'shop') return `sold in ${u.name} (${CHAPTERS[u.ch]})`;
    const where = u.chapters?.length ? u.chapters.map(c => CHAPTERS[c]).join(', ') : 'an event';
    return `given in ${where}${u.scene != null ? ` (scene ${u.scene})` : ''}`;
  }
  async function refreshUse() { use = (await api('itemuse')).use; }

  // ------------------------------------------------------------ weapons & items
  function itemsTab() {
    const split = h('div', { class: 'split' });
    const roster = h('div', { class: 'roster' });
    const sheetWrap = h('div', { class: 'sheet-wrap' });
    split.append(roster, sheetWrap);
    const search = h('input', { class: 'search', type: 'search', placeholder: 'Find an item', 'aria-label': 'Find an item', value: st.q });
    const list = h('div', { class: 'list itlist' });
    roster.append(h('div', { class: 'roster-tools' }, search), list);
    search.oninput = () => { st.q = search.value; remember(); drawList(); };

    function groupOf(r) { return r.table === 'rings' ? 'Rings' : Number(r.category) === 1 ? 'Staves' : TYPES[Number(r.weapon_type)] + (Number(r.weapon_type) >= 5 ? ' tomes' : 's'); }
    function drawList() {
      const q = st.q.trim().toLowerCase();
      const rows = allItems().filter(r => !q || nice(r._name).toLowerCase().includes(q));
      const groups = new Map();
      for (const r of rows) { const g = groupOf(r); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(r); }
      list.replaceChildren();
      for (const [g, rs] of groups) {
        list.append(h('div', { class: 'itgroup' }, g));
        for (const r of rs) {
          const key = `${r.table}:${r._row}`;
          const sub = r.table === 'rings' ? (r.skills ? r.skills.replace(/;/g, ', ') : RING_STAT[Number(r.stat_bonus)] ? `+ ${RING_STAT[Number(r.stat_bonus)]}` : '')
            : Number(r.category) === 1 ? (STAFF[Number(r.staff_effect)] ? `${r.uses} uses · range ${r.min_range}–${r.max_range}` : '')
              : `Mt ${r.mt} · Hit ${r.hit} · Wt ${r.wt}${r.rank === '*' ? ' · ★' : ' · ' + r.rank}`;
          const n = (Object.entries(use).filter(([i, us]) => instType(Number(i)) === Number(r.id) && us.length).length);
          list.append(h('button', { 'aria-pressed': String(st.item === key), onclick: () => { st.item = key; remember(); drawList(); drawSheet(); } },
            h('span', {}, nice(r._name)), h('span', { class: 'sub' }, sub, n ? h('em', {}, ` · ${n} cop${n === 1 ? 'y' : 'ies'}`) : '')));
        }
      }
      if (!rows.length) list.append(h('p', { class: 'note', style: 'padding:0 16px' }, 'No item matches.'));
    }

    function drawSheet() {
      sheetWrap.replaceChildren();
      const [table, rowS] = (st.item || '').split(':');
      const row = Number(rowS);
      const r = T[table]?.rows[row];
      if (!r) { sheetWrap.append(h('div', { class: 'empty' }, h('p', {}, 'Every weapon, staff and ring, and where each copy of it is in the campaign.'), h('p', {}, 'Choose an item on the left.'))); return; }
      const ring = table === 'rings', staff = !ring && Number(r.category) === 1;
      const sheet = h('article', { class: 'sheet' });
      const nameRow = T.names.rows.findIndex(n => n.kind === 'item' && Number(n.id) === Number(r.id));
      const nameIn = h('input', { class: 'in itname', value: nice(T.names.rows[nameRow]?.name ?? r._name), 'aria-label': 'Name', title: 'The name as the game draws it' });
      nameIn.onchange = async () => {
        const v = nameIn.value.replace(/á/g, '{89}').replace(/ö/g, '{9E}').replace(/é/g, '{91}');
        try { await set('names', nameRow, 'name', v, nameIn); r._name = v; drawList(); } catch (_) { /* shown */ }
      };
      sheet.append(h('div', { class: 'sheet-head', style: 'grid-template-columns:1fr' }, h('div', { class: 'who' },
        nameRow >= 0 ? nameIn : h('h2', {}, nice(r._name)),
        h('p', { class: 'note', style: 'margin:4px 0 0' }, ring ? 'Ring: works while carried.' : staff ? 'Staff' : `${TYPES[Number(r.weapon_type)]} · item ${r.id}`))));
      const main = h('section', {});
      const side = h('section', {});
      const grid = (...kids) => h('div', { class: 'itgrid' }, ...kids.filter(Boolean));
      const rankOpts = [['A', 'A'], ['B', 'B'], ['C', 'C'], ['*', '★ (holy weapon)']];
      if (ring) {
        main.append(h('h3', {}, 'Ring'), grid(num(table, row, 'price', 'Price'), sel(table, row, 'rank', 'Rank', rankOpts),
          sel(table, row, 'stat_bonus', 'Stat bonus', RING_STAT.map((s, i) => [i, s]), { after: drawList })));
      } else {
        main.append(h('h3', {}, staff ? 'Staff' : 'Combat'),
          grid(staff ? null : num(table, row, 'mt', 'Might', { after: drawList }), num(table, row, 'hit', 'Hit', { after: drawList }),
            staff ? null : num(table, row, 'wt', 'Weight', { after: drawList }),
            num(table, row, 'min_range', 'Range from'), num(table, row, 'max_range', 'Range to'),
            num(table, row, 'uses', 'Uses'), num(table, row, 'price', 'Price'),
            sel(table, row, 'rank', 'Rank needed', rankOpts, { after: drawList }),
            staff ? sel(table, row, 'staff_effect', 'What it does', STAFF.map((s, i) => [i, s || 'Nothing'])) :
              sel(table, row, 'weapon_type', 'Weapon type', TYPES.map((s, i) => [i, s]).filter(([i]) => i !== 4), { after: () => { drawList(); drawSheet(); } })));
        if (!staff) {
          // effective against: bit flags
          const eff = Number(r.effective) || 0;
          const chips = h('div', { class: 'chips' });
          for (const [bit, label] of EFFECTIVE) {
            const b = h('button', { class: 'chip', 'aria-pressed': String(!!(eff & bit)) }, label);
            b.onclick = async () => { const nv = (Number(T[table].rows[row].effective) || 0) ^ bit; try { await set(table, row, 'effective', String(nv)); drawSheet(); } catch (_) { /* shown */ } };
            chips.append(b);
          }
          const other = eff & ~EFFECTIVE.reduce((a, [b]) => a | b, 0);
          main.append(...[h('h3', {}, 'Effective against'), chips, other ? h('p', { class: 'hint' }, `Other flags set: ${other} (not identified).`) : null].filter(Boolean));
          // special effect
          const sp = Number(r.special) || 0, spec = SPECIALS.find(s => s[0] === sp);
          const spSel = sel(table, row, 'special', 'Special effect', SPECIALS.map(([v, t]) => [v, t]), { after: drawSheet });
          let argEl = null;
          if (spec?.[2] === 'spell' || spec?.[2] === 'item') argEl = sel(table, row, 'special_arg', spec[2] === 'spell' ? 'Spell' : 'Against', T.items.rows.filter(x => spec[2] === 'item' || Number(x.weapon_type) >= 5).map(x => [x.id, nice(x._name)]));
          else if (spec?.[2] === 'status') argEl = sel(table, row, 'special_arg', 'Status', STATUS);
          main.append(...[h('h3', {}, 'Special'), h('div', { class: 'itgrid wide' }, ...[spSel, argEl].filter(Boolean)),
            spec ? null : h('p', { class: 'hint' }, 'This effect number isn\'t one the game\'s own weapons use.')].filter(Boolean));
          main.append(h('h3', {}, 'Holy weapon'), h('div', { class: 'itgrid wide' }, sel(table, row, 'blood_lock', 'Only usable with', [[0, 'Anyone'], ...BLOODS.map((b, i) => [i + 1, `${b} blood (major)`]), [14, 'Shield sword bonus'], [15, 'Barrier sword bonus']])),
            h('p', { class: 'hint' }, 'A holy weapon gives the bonuses of its bloodline\'s weapon. The Shield and Barrier swords use slots 14 and 15 for their Defense and Resistance bonuses.'));
        }
      }
      // skills
      const have = new Set((r.skills || '').split(';').filter(Boolean));
      const names = T.skills.rows.filter(s => (s.item_bit ?? '') !== '' && !/^Hidden|\?$/.test(s.name)).map(s => s.name);
      const chips = h('div', { class: 'chips' });
      for (const n of names) {
        const b = h('button', { class: 'chip', 'aria-pressed': String(have.has(n)) }, n);
        b.onclick = async () => {
          const next = new Set(have); next.has(n) ? next.delete(n) : next.add(n);
          try { await set(table, row, 'skills', names.filter(x => next.has(x)).join(';')); have.clear(); next.forEach(x => have.add(x)); b.setAttribute('aria-pressed', String(have.has(n))); drawList(); } catch (_) { /* shown */ }
        };
        chips.append(b);
      }
      main.append(h('h3', {}, 'Skills while equipped'), chips);
      // copies
      side.append(h('h3', {}, 'Copies in the game'), copies(r));
      sheet.append(h('div', { class: 'sheet-body' }, main, side));
      sheetWrap.append(sheet);
    }

    function copies(r) {
      const box = h('div', { class: 'copies' });
      const mine = T.item_instances.rows.filter(x => Number(x.item_type) === Number(r.id));
      if (!mine.length) box.append(h('p', { class: 'hint' }, 'No copy of this item exists in the campaign. Turn an unused copy into it below.'));
      for (const x of mine) {
        const i = Number(x.instance), us = use[i] || [];
        const typeSel = h('select', { class: 'in', 'aria-label': `Copy #${i} is a` }, allItems().map(it => h('option', { value: it.id, selected: Number(it.id) === Number(r.id) }, nice(it._name))));
        typeSel.onchange = async () => { try { await set('item_instances', x._row, 'item_type', typeSel.value, typeSel); drawList(); drawSheet(); toast(`Copy #${i} is now ${typeName(typeSel.value)}`); } catch (_) { /* shown */ } };
        box.append(h('div', { class: 'copy' }, h('b', {}, `#${i}`),
          h('span', { class: us.length ? '' : 'sub' }, us.length ? us.map(useText).join('; ') : 'not used: no one starts with it, no shop sells it, no event gives it'),
          typeSel));
      }
      const spare = T.item_instances.rows.filter(x => !(use[x.instance] || []).length && Number(x.item_type) !== Number(r.id));
      if (spare.length) {
        const pick = h('select', { class: 'in', 'aria-label': 'Unused copy to turn into this item' }, h('option', { value: '' }, 'Turn an unused copy into this…'),
          spare.map(x => h('option', { value: x._row }, `#${x.instance} (now ${nice(x._item_name)})`)));
        pick.onchange = async () => { if (pick.value === '') return; try { await set('item_instances', Number(pick.value), 'item_type', r.id); drawList(); drawSheet(); } catch (_) { /* shown */ } };
        box.append(h('div', { class: 'copy-add' }, pick, h('p', { class: 'hint' }, 'FE4 has 141 numbered item copies. A copy only exists in a chapter if someone starts with it, a shop sells it or an event gives it: add it to a shop on the Shops & villages tab.')));
      }
      return box;
    }

    drawList(); drawSheet();
    return split;
  }

  // ------------------------------------------------------------ shops & villages
  function chapterPicker(key, onchange) {
    const e = h('select', { class: 'in', 'aria-label': 'Chapter' }, CHAPTERS.map((c, i) => h('option', { value: i, selected: i === st[key] }, c)));
    e.onchange = () => { st[key] = Number(e.value); remember(); onchange(); };
    return e;
  }

  function shopsTab() {
    const wrap = h('div', { class: 'itshops' });
    const content = h('div', {});
    wrap.append(h('div', { class: 'ittools' }, chapterPicker('ch', drawShops)), content);
    async function drawShops() {
      const ch = st.ch;
      const V = await api('villages?ch=' + ch);
      if (ch !== st.ch) return;
      const locs = T.locations.rows.filter(r => Number(r.chapter) === ch);
      content.replaceChildren();
      const castles = locs.filter(r => r.kind === 'castle'), villages = locs.filter(r => r.kind === 'village');
      content.append(h('h3', { class: 'itsec' }, `Castles (${castles.length})`));
      const cg = h('div', { class: 'itcards' });
      for (const c of castles) cg.append(castleCard(c));
      content.append(cg, h('h3', { class: 'itsec' }, `Villages (${villages.length})`));
      const vg = h('div', { class: 'itcards' });
      for (const v of villages) vg.append(villageCard(v, V.visits[v.index] || [], V.file));
      content.append(vg);
      if (!villages.length) vg.append(h('p', { class: 'hint' }, 'This chapter has no villages.'));
    }

    function castleCard(c) {
      const card = h('article', { class: 'itcard' });
      const fac = new Set((c.facilities || '').split(';').filter(x => x && x !== '-'));
      const chips = h('div', { class: 'chips' });
      for (const f of FACILITIES) {
        const b = h('button', { class: 'chip', 'aria-pressed': String(fac.has(f)) }, f);
        b.onclick = async () => {
          const next = new Set(fac); next.has(f) ? next.delete(f) : next.add(f);
          try { await set('locations', c._row, 'facilities', FACILITIES.filter(x => next.has(x)).join(';') || '-'); fac.clear(); next.forEach(x => fac.add(x)); b.setAttribute('aria-pressed', String(fac.has(f))); drawStock(); } catch (_) { /* shown */ }
        };
        chips.append(b);
      }
      const stock = h('div', { class: 'stock' });
      function drawStock() {
        const ids = (c.shop || '').split(';').filter(Boolean).map(Number);
        stock.replaceChildren();
        if (!ids.length && !fac.has('Armory')) { stock.append(h('p', { class: 'hint' }, 'No armory.')); return; }
        stock.append(h('div', { class: 'stock-head' }, h('b', {}, 'Armory sells'), !fac.has('Armory') && ids.length ? h('span', { class: 'warn' }, 'Turn on Armory, or nobody can buy these') : null));
        if (!ids.length) stock.append(h('p', { class: 'hint' }, 'Nothing yet.'));
        for (const i of ids) {
          const owner = (use[i] || []).find(u => u.kind === 'unit');
          stock.append(h('div', { class: 'stock-row' }, h('span', {}, typeName(instType(i))), h('span', { class: 'sub' }, `#${i}`),
            owner ? h('span', { class: 'warn', title: 'An item only goes on sale if nobody owns it when the chapter starts.' }, `${owner.name} starts with it`) : h('span', {}),
            h('button', { class: 'x', title: 'Stop selling this', 'aria-label': `Stop selling ${typeName(instType(i))}`, onclick: () => setShop(ids.filter(x => x !== i)) }, '×')));
        }
        const free = T.item_instances.rows.filter(x => !ids.includes(Number(x.instance)));
        const unowned = free.filter(x => !(use[x.instance] || []).some(u => u.kind === 'unit'));
        const add = h('select', { class: 'in', 'aria-label': 'Add an item to this shop' }, h('option', { value: '' }, 'Add an item…'),
          h('optgroup', { label: 'Copies nobody starts with' }, unowned.map(x => h('option', { value: x.instance }, `${nice(x._item_name)} #${x.instance}${(use[x.instance] || []).length ? ' · ' + use[x.instance].map(useText).join('; ') : ''}`))),
          h('optgroup', { label: 'Copies someone starts with (won\'t go on sale)' }, free.filter(x => !unowned.includes(x)).map(x => h('option', { value: x.instance }, `${nice(x._item_name)} #${x.instance}`))));
        add.onchange = () => { if (add.value !== '') setShop([...ids, Number(add.value)]); };
        stock.append(add);
      }
      async function setShop(ids) {
        try { c.shop = await set('locations', c._row, 'shop', ids.join(';')); await refreshUse(); drawStock(); } catch (_) { /* shown */ }
      }
      drawStock();
      card.append(h('div', { class: 'itcard-head' }, h('h4', {}, c._castle_name || `Castle ${c.index}`), h('span', { class: 'sub' }, `at ${c.x}, ${c.y}`)), chips, stock);
      return card;
    }

    function villageCard(v, visits, file) {
      const card = h('article', { class: 'itcard' });
      const gold = h('input', { class: 'in num', value: v.gold || '', inputmode: 'numeric', 'aria-label': `Village ${v.index} gold` });
      gold.onchange = async () => { try { gold.value = await set('locations', v._row, 'gold', gold.value, gold); } catch (_) { /* shown */ } };
      card.append(h('div', { class: 'itcard-head' }, h('h4', {}, `Village ${v.index}`), h('span', { class: 'sub' }, `at ${v.x}, ${v.y}`)),
        h('div', { class: 'itgrid' }, lbl('Gold on the first visit', gold)));
      const gifts = visits.flatMap(x => x.gifts);
      if (gifts.length) {
        card.append(h('b', { class: 'gifts-head' }, 'Visiting also gives'));
        for (const g of gifts) card.append(giftRow(g));
      } else if (visits.length) card.append(h('p', { class: 'hint' }, 'Visiting shows a conversation; no item or stat.'));
      else card.append(h('p', { class: 'hint' }, 'No visit event: the game\'s default (gold only).'));
      if (visits.length) card.append(h('button', { class: 'btn btn-line', onclick: () => { openEventAt(st.ch, visits[0].line); go('events'); } }, 'Open the visit event'));
      void file;
      return card;
    }

    function giftRow(g) {
      const b = g.hex.split(' ').map(x => parseInt(x, 16)), o = g.pos;
      const write = async (bytes, el) => {
        try {
          await api('evtcmd', { file: g.file, line: g.line, hex: bytes.map(x => x.toString(16).toUpperCase().padStart(2, '0')).join(' ') });
          g.hex = bytes.map(x => x.toString(16).toUpperCase().padStart(2, '0')).join(' ');
          el?.classList.remove('bad'); await refreshSession(); await refreshUse();
        } catch (e) { el?.classList.add('bad'); toast(e.message, true); }
      };
      const who = g.unit == null ? 'the visitor' : (people().find(p => Number(p.char_id) === g.unit)?._name || `unit ${g.unit}`);
      if (g.kind === 'item') {
        const s = h('select', { class: 'in', 'aria-label': 'Item given' }, T.item_instances.rows.map(x => h('option', { value: x.instance, selected: Number(x.instance) === g.instance }, `${nice(x._item_name)} #${x.instance}`)));
        s.onchange = () => { const nb = [...b]; nb[o + 3] = Number(s.value); write(nb, s); };
        return h('div', { class: 'gift' }, h('span', {}, `Item to ${who}`), s);
      }
      const s = h('select', { class: 'in', 'aria-label': 'Stat raised' }, STATS.map((n, i) => h('option', { value: i, selected: i === g.stat }, n)));
      const a = h('input', { class: 'in num', value: g.amount, inputmode: 'numeric', 'aria-label': 'Amount' });
      s.onchange = () => { const nb = [...b]; nb[o + 2] = Number(s.value); write(nb, s); };
      a.onchange = () => { const n = Number(a.value); if (!Number.isInteger(n) || n < 0 || n > 255) { a.classList.add('bad'); toast('Enter a number from 0 to 255.', true); return; } const nb = [...b]; nb[o + 3] = n; write(nb, a); };
      return h('div', { class: 'gift' }, h('span', {}, `Stat boost for ${who}`), s, h('span', {}, '+'), a);
    }

    drawShops();
    return wrap;
  }

  // ------------------------------------------------------------ arena
  function arenaTab() {
    const wrap = h('div', { class: 'itshops' });
    const content = h('div', {});
    wrap.append(h('div', { class: 'ittools' }, chapterPicker('arenaCh', draw2)), content);
    const gen = T.units_generic.rows;
    if (!document.getElementById('arenafighters')) {
      document.body.append(h('datalist', { id: 'arenafighters' }, gen.map(u => h('option', { value: `${u._name || 'Unit'} · ${u._class_name} Lv ${u.level} (${u.index})` }))));
    }
    function fighter(r, field) {
      const id = Number(r[field]);
      const u = gen.find(x => Number(x.index) === id);
      const inp = h('input', { class: 'in', list: 'arenafighters', value: u ? `${u._name} (${id})` : String(id), 'aria-label': `Rank ${r.rank} ${field}` });
      inp.onchange = async () => {
        const m = inp.value.match(/\((\d+)\)\s*$/) || inp.value.match(/^(\d+)$/);
        if (!m) { inp.classList.add('bad'); toast('Pick a unit from the list.', true); return; }
        try { await set('arena', r._row, field, m[1], inp); draw2(); } catch (_) { /* shown */ }
      };
      const box = h('div', { class: 'fighter' }, inp);
      if (u) {
        const gr = gen.indexOf(u);
        box.append(h('div', { class: 'itgrid tight' },
          sel('units_generic', gr, 'class', 'Class', T.classes.rows.map(c => [c.index, c._name]), { after: draw2 }),
          num('units_generic', gr, 'level', 'Level')),
        h('span', { class: 'sub' }, u._items ? nice(u._items) : 'no items'));
      }
      return box;
    }
    function draw2() {
      const rows = T.arena.rows.filter(r => Number(r.chapter) === st.arenaCh);
      content.replaceChildren();
      if (!rows.length) { content.append(h('p', { class: 'hint' }, `${CHAPTERS[st.arenaCh]} has no arena table.`)); return; }
      content.append(h('p', { class: 'hint' }, 'Seven opponents per chapter, one per win. Melee opponents fight units with swords, lances and axes; ranged ones fight bows and magic. A castle needs the Arena button (Shops & villages) for its arena to open.'));
      const t = h('div', { class: 'arena' }, h('b', {}, 'Rank'), h('b', {}, 'Melee opponent'), h('b', {}, 'Ranged opponent'));
      for (const r of rows) t.append(h('span', { class: 'rank' }, r.rank), fighter(r, 'melee'), fighter(r, 'ranged'));
      content.append(t);
    }
    draw2();
    return wrap;
  }

  function draw() {
    body.replaceChildren(st.tab === 'shops' ? shopsTab() : st.tab === 'arena' ? arenaTab() : itemsTab());
  }
  drawTabs(); draw();
  return {
    async refresh() { await loadTables(['items', 'rings', 'item_instances', 'names', 'locations', 'arena', 'units_generic'], true); await refreshUse(); draw(); },
  };
}
