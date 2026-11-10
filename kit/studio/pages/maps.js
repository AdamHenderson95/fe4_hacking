// Maps: paint chapter maps with the game's own tiles; drag castles, villages and units into place.
import { api, h, app, toast, refreshSession, go } from '../app.js';
import { openEventAt } from './events.js';

const TOOLS = [
  ['select', 'Select', 'V', 'Select and drag castles, villages and units', 'M4 3l11 6-5 1.5L8 16z'],
  ['brush', 'Paint', 'B', 'Paint the chosen tiles (right-click picks a tile)', 'M13 3l4 4-8 8H5v-4z M11 5l4 4'],
  ['fill', 'Fill', 'G', 'Fill an area of the same tile', 'M4 10l6-6 6 6-6 6z M16 12c1 2 2 3 2 4a2 2 0 0 1-4 0c0-1 1-2 2-4z'],
  ['pick', 'Pick', 'I', 'Pick a tile, or drag to copy a block of tiles', 'M14 3l3 3-2 2-3-3z M12 5l3 3-7 7H5v-3z'],
];
const ZOOMS = [1, 1.5, 2, 3, 4];
export const ARMY_COLORS = ['#3B6FD8', '#C8343F', '#D9822B', '#8A4FC2', '#2E9A5B', '#1F8A8A', '#8B6A3E', '#B83E8C'];
const TERRAIN_TINT = {
  0: '#6B5A4A', 7: '#8C7458', 2: '#A2673A', 1: '#1F5A2A', 4: '#2F8A3C', 5: '#1D4FA8', 6: '#3E86D6', 8: '#E0C26A',
  9: '#E1A92C', 10: '#E1A92C', 12: '#E1A92C', 13: '#B9852A', 14: '#9C8E6E', 15: '#C9C1AE', 18: '#3CC4D6', 22: '#3CC4D6',
  24: '#D65A9A', 25: '#D9B98A', 26: '#AAAAAA',
};
const AREA_COLORS = ['#E5484D', '#3E63DD', '#30A46C', '#F76B15', '#8E4EC6', '#12A594'];
// castle / village footprints from the game's table at $87:F455: (dx1, dy1, dx2, dy2)
export const FOOT = { castle: [-1, -1, 1, 2], village: [-1, -1, 1, 0], site1: [0, 0, 1, 0] };

const st = {
  ch: null, tool: 'select', zoom: 2, stamp: { w: 1, h: 1, tiles: [0] }, palZoom: 1,
  layers: { grid: true, terrain: false, areas: false, sites: true, units: true, events: true },
  hidden: new Set(), terrainFilter: '', sel: null,
};

export function setMapChapter(ch, list) {
  st.ch = ch;
  if (list !== undefined) st.focusList = list;
}

export async function mapsPage(root) {
  const { maps } = await api('maps');
  if (!maps.length) {
    root.append(h('div', { class: 'empty' }, 'This project has no maps folder. Make a new project from your ROM to get the chapter maps.'));
    return {};
  }
  if (st.ch === null || !maps.some(m => m.ch === st.ch)) st.ch = maps[0].ch;
  let focus = st.focusList; st.focusList = undefined;

  let M = null;                 // map data from the editor
  let atlas = null;             // the chapter's 1024 tiles as an image
  let hover = null;             // {x, y}
  let drag = null;              // what the pointer is doing

  // ------------------------------------------------------------ layout
  const chapterSel = h('select', { class: 'in', 'aria-label': 'Chapter' },
    maps.map(m => h('option', { value: m.ch, selected: m.ch === st.ch }, m.title)));
  const toolBtns = {};
  const toolbar = h('div', { class: 'mtools' }, chapterSel,
    h('div', { class: 'mseg', role: 'group', 'aria-label': 'Tools' }, TOOLS.map(([id, label, key, tip, d]) => {
      const b = h('button', { class: 'mtool', title: `${tip} (${key})`, 'aria-pressed': String(st.tool === id), onclick: () => setTool(id) },
        svg(d), h('span', {}, label));
      toolBtns[id] = b;
      return b;
    })),
    h('div', { class: 'mseg' },
      h('button', { class: 'mtool', title: 'Zoom out (-)', 'aria-label': 'Zoom out', onclick: () => zoomBy(-1) }, '−'),
      h('span', { class: 'mzoom', id: 'mzoom' }),
      h('button', { class: 'mtool', title: 'Zoom in (+)', 'aria-label': 'Zoom in', onclick: () => zoomBy(1) }, '+')),
    h('div', { class: 'mlayers', role: 'group', 'aria-label': 'Show' },
      [['grid', 'Grid'], ['terrain', 'Terrain'], ['areas', 'Area flags'], ['sites', 'Castles & villages'], ['units', 'Units'], ['events', 'Event areas']].map(([k, label]) =>
        h('button', { class: 'chip', 'aria-pressed': String(st.layers[k]), onclick: e => { st.layers[k] = !st.layers[k]; e.currentTarget.setAttribute('aria-pressed', String(st.layers[k])); drawOverlay(); drawObjects(); } }, label))));

  const base = h('canvas', { class: 'mbase' });
  const over = h('canvas', { class: 'mover' });
  const objs = h('div', { class: 'mobjs' });
  const stage = h('div', { class: 'mstage' }, base, over, objs);
  const view = h('div', { class: 'mview', tabindex: '0', 'aria-label': 'Map' }, stage);
  const inspector = h('section', { class: 'mpanel minspect' });
  const palCanvas = h('canvas', { class: 'mpal' });
  const palOver = h('canvas', { class: 'mpal-over' });
  const terrainSel = h('select', { class: 'in', 'aria-label': 'Show tiles of terrain' });
  const stampInfo = h('span', { class: 'note' });
  const palette = h('section', { class: 'mpanel' },
    h('div', { class: 'mpanel-head' }, h('h3', {}, 'Tiles'), stampInfo),
    h('div', { class: 'mpal-tools' }, terrainSel,
      h('button', { class: 'btn btn-line', title: 'Palette size', onclick: () => { st.palZoom = st.palZoom === 1 ? 2 : 1; drawPalette(); } }, '1× / 2×')),
    h('div', { class: 'mpal-wrap' }, h('div', { class: 'mpal-stage' }, palCanvas, palOver)),
    h('p', { class: 'hint' }, 'Click a tile, or drag across several to paint them as a block. Terrain comes with the tile: painting water makes the cell water to the game too.'));
  const listsBox = h('div', { class: 'mlists' });
  const unitsPanel = h('section', { class: 'mpanel' }, h('div', { class: 'mpanel-head' }, h('h3', {}, 'Units')), listsBox);
  const side = h('div', { class: 'mside' }, inspector, palette, unitsPanel);
  const status = h('div', { class: 'mstatus', 'aria-live': 'off' });
  root.append(h('div', { class: 'mapedit' }, toolbar, view, side, status));

  chapterSel.onchange = () => { st.ch = Number(chapterSel.value); st.sel = null; load(); };
  terrainSel.onchange = () => { st.terrainFilter = terrainSel.value; drawPalette(); };

  // ------------------------------------------------------------ loading
  async function load() {
    view.classList.add('loading');
    M = await api('map?ch=' + st.ch);
    atlas = await loadImage(`/gfx/tiles/${st.ch}.png`);
    view.classList.remove('loading');
    const used = [...new Set(M.terrain)].sort((a, b) => a - b);
    terrainSel.replaceChildren(h('option', { value: '' }, 'All terrain'),
      ...used.map(t => h('option', { value: t, selected: String(t) === st.terrainFilter }, terrainName(t))));
    if (!used.map(String).includes(st.terrainFilter)) st.terrainFilter = '';
    if (focus !== undefined && M.deploy.some(l => l.list === focus)) {
      M.deploy.forEach(l => (l.list === focus ? st.hidden.delete(`${M.ch}:${l.list}`) : st.hidden.add(`${M.ch}:${l.list}`)));
      st.layers.units = true; focus = undefined;
    }
    layout(); drawBase(); drawOverlay(); drawObjects(); drawPalette(); drawLists(); drawInspector();
  }

  function loadImage(src) {
    return new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => bad(new Error('Couldn\'t draw the map: choose your FE4 ROM on the Project page.')); i.src = src; });
  }

  const terrainName = t => M.terrainNames[t] || `Terrain ${t}`;
  const tileAt = (x, y) => M.words[y * M.width + x];
  const inMap = (x, y) => x >= 0 && y >= 0 && x < M.width && y < M.height && y * M.width + x < M.words.length;

  // ------------------------------------------------------------ drawing
  function layout() {
    const W = M.width * 16, H = M.height * 16, z = st.zoom;
    base.width = W; base.height = H;
    for (const c of [base, over]) { c.style.width = W * z + 'px'; c.style.height = H * z + 'px'; }
    over.width = Math.round(W * z); over.height = Math.round(H * z);
    stage.style.width = W * z + 'px'; stage.style.height = H * z + 'px';
    document.getElementById('mzoom').textContent = Math.round(z * 100) + '%';
  }

  function drawCell(ctx, i) {
    const k = M.words[i] & 0x3FF, x = i % M.width, y = Math.floor(i / M.width);
    ctx.drawImage(atlas, (k % 32) * 16, (k >> 5) * 16, 16, 16, x * 16, y * 16, 16, 16);
  }

  function drawBase() {
    const ctx = base.getContext('2d');
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, base.width, base.height);
    for (let i = 0; i < M.words.length; i++) drawCell(ctx, i);
  }

  function drawOverlay() {
    if (!M) return;
    const ctx = over.getContext('2d'), s = 16 * st.zoom;
    ctx.clearRect(0, 0, over.width, over.height);
    if (st.layers.terrain || st.layers.areas) {
      ctx.globalAlpha = .42;
      for (let i = 0; i < M.words.length; i++) {
        const x = i % M.width, y = Math.floor(i / M.width);
        if (st.layers.terrain) {
          const c = TERRAIN_TINT[M.terrain[M.words[i] & 0x3FF]];
          if (c) { ctx.fillStyle = c; ctx.fillRect(x * s, y * s, s, s); }
        }
        if (st.layers.areas) {
          const a = M.words[i] >> 10;
          for (let b = 0; b < 6; b++) if (a & (1 << b)) { ctx.fillStyle = AREA_COLORS[b]; ctx.fillRect(x * s, y * s + b * s / 6, s, s / 6); }
        }
      }
      ctx.globalAlpha = 1;
    }
    if (st.layers.grid && st.zoom >= 1.5) {
      ctx.strokeStyle = 'rgba(0,0,0,.22)'; ctx.lineWidth = 1; ctx.beginPath();
      for (let x = 1; x < M.width; x++) { ctx.moveTo(Math.round(x * s) + .5, 0); ctx.lineTo(Math.round(x * s) + .5, over.height); }
      for (let y = 1; y < M.height; y++) { ctx.moveTo(0, Math.round(y * s) + .5); ctx.lineTo(over.width, Math.round(y * s) + .5); }
      ctx.stroke();
    }
    // what the pointer would do
    let r = null;
    if (drag?.kind === 'pick') r = rectOf(drag.x0, drag.y0, drag.x, drag.y);
    else if (hover && (st.tool === 'brush')) r = { x: anchorX(hover.x), y: anchorY(hover.y), w: st.stamp.w, h: st.stamp.h };
    else if (hover && st.tool !== 'select') r = { x: hover.x, y: hover.y, w: 1, h: 1 };
    else if (hover) r = { x: hover.x, y: hover.y, w: 1, h: 1, faint: true };
    if (r && st.tool === 'brush' && !drag) {
      ctx.globalAlpha = .7;
      for (let dy = 0; dy < r.h; dy++) for (let dx = 0; dx < r.w; dx++) {
        if (!inMap(r.x + dx, r.y + dy)) continue;
        const k = st.stamp.tiles[dy * r.w + dx];
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(atlas, (k % 32) * 16, (k >> 5) * 16, 16, 16, (r.x + dx) * s, (r.y + dy) * s, s, s);
      }
      ctx.globalAlpha = 1;
    }
    if (r) {
      ctx.lineWidth = 2;
      ctx.strokeStyle = r.faint ? 'rgba(255,255,255,.55)' : '#F3E3B8';
      ctx.strokeRect(r.x * s + 1, r.y * s + 1, r.w * s - 2, r.h * s - 2);
      if (!r.faint) { ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 1; ctx.strokeRect(r.x * s - .5, r.y * s - .5, r.w * s + 1, r.h * s + 1); }
    }
    if (st.sel?.type === 'cell') {
      ctx.strokeStyle = '#B98B2F'; ctx.lineWidth = 3; ctx.setLineDash([5, 3]);
      ctx.strokeRect(st.sel.x * s + 1.5, st.sel.y * s + 1.5, s - 3, s - 3); ctx.setLineDash([]);
    }
  }

  function visibleUnits() {
    return st.layers.units ? M.deploy.filter(l => !st.hidden.has(`${M.ch}:${l.list}`)).flatMap(l => l.units.map(u => ({ ...u, list: l.list }))) : [];
  }

  function drawObjects() {
    if (!M) return;
    const s = 16 * st.zoom;
    objs.replaceChildren();
    objs.classList.toggle('live', st.tool === 'select');
    if (st.layers.events) for (const a of M.areas || []) {
      const e = h('div', { class: 'mevarea', title: `${a.who} reaches (${a.x1}, ${a.y1})–(${a.x2}, ${a.y2}): open the event`,
        style: `left:${a.x1 * s}px;top:${a.y1 * s}px;width:${(a.x2 - a.x1 + 1) * s}px;height:${(a.y2 - a.y1 + 1) * s}px` },
      h('button', { type: 'button', onpointerdown: e => e.stopPropagation(), onclick: () => { openEventAt(M.ch, a.line); go('events'); } }, `⌖ ${a.who}`));
      objs.append(e);
    }
    if (st.layers.sites) for (const L of M.locations) {
      const f = FOOT[L.kind] || [0, 0, 0, 0];
      const x = Number(L.x) + f[0], y = Number(L.y) + f[1], w = f[2] - f[0] + 1, hh = f[3] - f[1] + 1;
      const label = L.kind === 'castle' ? (L.name || 'Castle') : L.kind === 'village' ? 'Village' : L.kind;
      const e = h('div', { class: `msite ${L.kind}`, title: `${label} (${L.kind} ${L.index}) at ${L.x}, ${L.y}`,
        style: `left:${x * s}px;top:${y * s}px;width:${w * s}px;height:${hh * s}px`,
        'aria-selected': String(st.sel?.type === 'site' && st.sel.row === L._row) },
      h('span', {}, label));
      e.onpointerdown = ev => startMove(ev, { type: 'site', row: L._row }, Number(L.x), Number(L.y));
      objs.append(e);
    }
    for (const u of visibleUnits()) {
      const slot = Number(u.army_slot) || 0;
      const e = h('div', { class: 'munit' + (u.leader ? ' leader' : ''), title: `${u.name}${u.class ? ', ' + u.class : ''}${u.level ? ' Lv ' + u.level : ''} (list ${u.list})`,
        style: `left:${Number(u.x) * s}px;top:${Number(u.y) * s}px;width:${s}px;height:${s}px;--c:${ARMY_COLORS[slot % ARMY_COLORS.length]}`,
        'aria-selected': String(st.sel?.type === 'unit' && st.sel.row === u._row) },
      u.portrait != null ? h('img', { src: `/gfx/portrait/${u.portrait}.png?s=1`, alt: '', draggable: 'false' })
        : h('b', {}, (u.class || u.name || '?').slice(0, 2)));
      e.onpointerdown = ev => startMove(ev, { type: 'unit', row: u._row }, Number(u.x), Number(u.y));
      objs.append(e);
    }
  }

  function drawPalette() {
    if (!atlas) return;
    const z = st.palZoom, S = 16 * z;
    palCanvas.width = 512; palCanvas.height = 512;
    palCanvas.style.width = palOver.style.width = 512 * z + 'px';
    palCanvas.style.height = palOver.style.height = 512 * z + 'px';
    const ctx = palCanvas.getContext('2d');
    ctx.clearRect(0, 0, 512, 512);
    ctx.drawImage(atlas, 0, 0);
    palOver.width = 512 * z; palOver.height = 512 * z;
    const o = palOver.getContext('2d');
    o.clearRect(0, 0, palOver.width, palOver.height);
    if (st.terrainFilter !== '') {
      o.fillStyle = 'rgba(20,22,40,.72)';
      for (let k = 0; k < 1024; k++) if (String(M.terrain[k]) !== st.terrainFilter) o.fillRect((k % 32) * S, (k >> 5) * S, S, S);
    }
    if (st.stamp.src) {
      const { x, y } = st.stamp.src;
      o.lineWidth = 2; o.strokeStyle = '#F3E3B8';
      o.strokeRect(x * S + 1, y * S + 1, st.stamp.w * S - 2, st.stamp.h * S - 2);
      o.strokeStyle = 'rgba(0,0,0,.7)'; o.lineWidth = 1;
      o.strokeRect(x * S - .5, y * S - .5, st.stamp.w * S + 1, st.stamp.h * S + 1);
    }
    const k0 = st.stamp.tiles[0];
    stampInfo.textContent = st.stamp.w * st.stamp.h > 1 ? `${st.stamp.w}×${st.stamp.h} block` : `Tile ${k0} · ${terrainName(M.terrain[k0])}`;
  }

  function drawLists() {
    listsBox.replaceChildren();
    if (!M.deploy.length) { listsBox.append(h('p', { class: 'hint' }, 'No enemy or allied units are placed on this map by its deploy lists.')); return; }
    listsBox.append(h('p', { class: 'hint' }, 'Units come onto the map in groups (deploy lists) as the chapter goes on. Show the ones you\'re working on.'));
    for (const l of M.deploy) {
      const key = `${M.ch}:${l.list}`;
      const armies = [...new Set(l.units.map(u => u.army).filter(Boolean))];
      const cb = h('input', { type: 'checkbox', checked: !st.hidden.has(key) });
      cb.onchange = () => { cb.checked ? st.hidden.delete(key) : st.hidden.add(key); drawObjects(); };
      const slots = [...new Set(l.units.map(u => Number(u.army_slot) || 0))];
      listsBox.append(h('label', { class: 'mlist' }, cb,
        h('span', { class: 'mlist-dots' }, slots.map(sl => h('i', { style: `background:${ARMY_COLORS[sl % ARMY_COLORS.length]}` }))),
        h('span', {}, h('b', {}, `List ${l.list}`), ` · ${l.units.length} unit${l.units.length === 1 ? '' : 's'}`,
          armies.length ? h('span', { class: 'sub' }, ' · ' + armies.slice(0, 3).join(', ')) : null,
          l.sure ? null : h('span', { class: 'sub', title: 'No chapter script names this list; it is shown with the chapter whose lists come just before it.' }, ' (probably)'))));
    }
    listsBox.append(h('div', { class: 'row', style: 'display:flex;gap:8px;margin-top:8px' },
      h('button', { class: 'btn btn-line', onclick: () => { M.deploy.forEach(l => st.hidden.delete(`${M.ch}:${l.list}`)); drawLists(); drawObjects(); } }, 'Show all'),
      h('button', { class: 'btn btn-line', onclick: () => { M.deploy.forEach(l => st.hidden.add(`${M.ch}:${l.list}`)); drawLists(); drawObjects(); } }, 'Hide all')));
  }

  // ------------------------------------------------------------ inspector
  function numIn(label, value, onset, opts = {}) {
    const e = h('input', { class: 'in num', value, 'aria-label': label, inputmode: 'numeric' });
    e.onchange = async () => { try { await onset(e.value); e.classList.remove('bad'); } catch (err) { e.classList.add('bad'); toast(err.message, true); } };
    return h('label', { class: 'lbl' }, h('span', {}, label), e);
  }

  function drawInspector() {
    inspector.replaceChildren();
    const sel = st.sel;
    if (sel?.type === 'unit') {
      const u = M.deploy.flatMap(l => l.units.map(x => ({ ...x, list: l.list }))).find(x => x._row === sel.row);
      if (!u) { st.sel = null; return drawInspector(); }
      inspector.append(h('div', { class: 'mins-head' },
        h('div', { class: 'mins-face' }, u.portrait != null ? h('img', { src: `/gfx/portrait/${u.portrait}.png?s=2`, alt: '' }) : h('span', { class: 'noface' }, (u.class || '?').slice(0, 1))),
        h('div', {}, h('h3', {}, u.name), h('p', { class: 'note', style: 'margin:0' },
          [u.class, u.level ? 'Lv ' + u.level : '', u.army ? u.army + ' army' : `Army slot ${u.army_slot}`].filter(Boolean).join(' · ')),
        h('p', { class: 'note', style: 'margin:0' }, `Deploy list ${u.list}, entry ${u.entry}${u.leader ? ' · leader' : ''}`))),
      h('div', { class: 'mins-grid' },
        numIn('X', u.x, v => moveTo(sel, Number(v), Number(u.y))),
        numIn('Y', u.y, v => moveTo(sel, Number(u.x), Number(v))),
        numIn('AI orders', u.orders, v => setMany([['deploy', u._row, 'orders', v]]))),
      h('p', { class: 'hint' }, u.table === 'units_generic' ? 'A generic unit: its stats come from its class and level.' :
        'Stats, items and skills are on the Characters page.'));
      return;
    }
    if (sel?.type === 'site') {
      const L = M.locations.find(x => x._row === sel.row);
      if (!L) { st.sel = null; return drawInspector(); }
      inspector.append(h('h3', {}, L.kind === 'castle' ? (L.name || 'Castle') : 'Village'),
        h('p', { class: 'note', style: 'margin:0 0 8px' }, `${L.kind === 'castle' ? 'Castle' : L.kind === 'village' ? 'Village' : L.kind} ${L.index} of this chapter${L.facilities && L.facilities !== '-' ? ' · ' + L.facilities.split(';').join(', ') : ''}`),
        h('div', { class: 'mins-grid' },
          numIn('X', L.x, v => moveTo(sel, Number(v), Number(L.y))),
          numIn('Y', L.y, v => moveTo(sel, Number(L.x), Number(v))),
          L.kind === 'village' ? numIn('Gold', L.gold || '', v => setMany([['locations', L._row, 'gold', v]])) : null),
        h('p', { class: 'hint' }, 'Moving the marker moves where the game counts the castle or village as being (seizing, visiting). The picture is the map tiles: paint those to match.'));
      return;
    }
    if (sel?.type === 'cell' && inMap(sel.x, sel.y)) {
      const w = tileAt(sel.x, sel.y), k = w & 0x3FF, t = M.terrain[k];
      const c = h('canvas', { width: 16, height: 16, class: 'mins-tile' });
      c.getContext('2d').drawImage(atlas, (k % 32) * 16, (k >> 5) * 16, 16, 16, 0, 0, 16, 16);
      inspector.append(h('div', { class: 'mins-head' }, c,
        h('div', {}, h('h3', {}, terrainName(t)), h('p', { class: 'note', style: 'margin:0' }, `Cell ${sel.x}, ${sel.y} · tile ${k}${w >> 10 ? ` · area flags ${w >> 10}` : ''}`),
          M.impassable.includes(t) ? h('p', { class: 'note', style: 'margin:0' }, 'Most units can\'t enter this terrain.') : null)),
      h('button', { class: 'btn btn-line', onclick: () => { setStamp({ w: 1, h: 1, tiles: [k] }); setTool('brush'); } }, 'Paint with this tile'));
      return;
    }
    inspector.append(h('h3', {}, M.title),
      h('p', { class: 'hint', style: 'margin:0' }, `${M.width} × ${M.height} cells · ${M.locations.length} castles and villages · ${M.deploy.reduce((n, l) => n + l.units.length, 0)} deployed units`),
      h('p', { class: 'hint', style: 'margin:6px 0 0' }, 'Click a castle, village or unit to edit it, or drag it to a new spot. Paint (B) changes the ground; right-click picks the tile under the pointer.'));
  }

  // ------------------------------------------------------------ edits
  async function setMany(rows) {
    await api('setmany', { changes: rows.map(([table, row, field, value]) => ({ table, row, field, value: String(value) })) });
    await reloadData();
  }

  async function moveTo(sel, x, y) {
    if (!inMap(x, y)) throw new Error(`Keep it on the map: x 0–${M.width - 1}, y 0–${M.height - 1}.`);
    if (sel.type === 'unit') await setMany([['deploy', sel.row, 'x', x], ['deploy', sel.row, 'y', y]]);
    else await setMany([['locations', sel.row, 'x', x], ['locations', sel.row, 'y', y]]);
  }

  async function reloadData() {
    const fresh = await api('map?ch=' + st.ch);
    const sameWords = fresh.words.length === M.words.length && fresh.words.every((w, i) => w === M.words[i]);
    M = fresh;
    if (!sameWords) drawBase();
    drawOverlay(); drawObjects(); drawLists(); drawInspector();
    await refreshSession();
  }

  function setTool(id) {
    st.tool = id;
    for (const [k, b] of Object.entries(toolBtns)) b.setAttribute('aria-pressed', String(k === id));
    view.dataset.tool = id;
    drawObjects(); drawOverlay();
  }

  function setStamp(s) {
    const k = s.tiles[0];
    st.stamp = { ...s, src: s.src || { x: k % 32, y: k >> 5 } };
    if (s.w * s.h > 1 && !s.src) st.stamp.src = null;
    drawPalette();
  }

  const anchorX = x => drag?.kind === 'paint' ? drag.ax + Math.floor((x - drag.ax) / st.stamp.w) * st.stamp.w : x;
  const anchorY = y => drag?.kind === 'paint' ? drag.ay + Math.floor((y - drag.ay) / st.stamp.h) * st.stamp.h : y;
  const rectOf = (x0, y0, x1, y1) => ({ x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0) + 1, h: Math.abs(y1 - y0) + 1 });

  function put(stroke, x, y, k) {
    if (!inMap(x, y)) return;
    const i = y * M.width + x, w = (M.words[i] & ~0x3FF) | k;
    if (M.words[i] === w) return;
    M.words[i] = w; stroke.set(i, w);
    drawCell(base.getContext('2d'), i);
  }

  function stampAt(stroke, x, y) {
    const { w, h: hh, tiles } = st.stamp;
    for (let dy = 0; dy < hh; dy++) for (let dx = 0; dx < w; dx++) put(stroke, x + dx, y + dy, tiles[dy * w + dx]);
  }

  function fill(x, y) {
    const target = tileAt(x, y) & 0x3FF, stroke = new Map(), seen = new Uint8Array(M.words.length);
    const { w, h: hh, tiles } = st.stamp;
    const q = [[x, y]];
    if (w * hh === 1 && tiles[0] === target) return stroke;
    while (q.length) {
      const [cx, cy] = q.pop();
      if (!inMap(cx, cy)) continue;
      const i = cy * M.width + cx;
      if (seen[i] || (M.words[i] & 0x3FF) !== target) continue;
      seen[i] = 1;
      q.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
    }
    for (let i = 0; i < seen.length; i++) if (seen[i]) {
      const cx = i % M.width, cy = Math.floor(i / M.width);
      put(stroke, cx, cy, tiles[(((cy - y) % hh + hh) % hh) * w + (((cx - x) % w + w) % w)]);
    }
    return stroke;
  }

  async function commit(stroke, what) {
    if (!stroke.size) return;
    try {
      const r = await api('paint', { ch: M.ch, cells: [...stroke] });
      await refreshSession();
      if (what) toast(`${what}: ${r.changed} cell${r.changed === 1 ? '' : 's'}`);
    } catch (e) { toast(e.message, true); await reloadData(); }
  }

  function pickRect(r) {
    const tiles = [];
    for (let dy = 0; dy < r.h; dy++) for (let dx = 0; dx < r.w; dx++) tiles.push(inMap(r.x + dx, r.y + dy) ? tileAt(r.x + dx, r.y + dy) & 0x3FF : 0);
    const s = { w: r.w, h: r.h, tiles };
    // a single tile, or a block that sits in the palette as it does on the map, is shown there
    const k = tiles[0];
    const asInAtlas = tiles.every((t, j) => t === k + (j % r.w) + Math.floor(j / r.w) * 32) && (k % 32) + r.w <= 32;
    st.stamp = { ...s, src: asInAtlas ? { x: k % 32, y: k >> 5 } : null };
    drawPalette();
  }

  // ------------------------------------------------------------ pointer: map
  function cellOf(ev) {
    const b = stage.getBoundingClientRect(), s = 16 * st.zoom;
    return { x: Math.floor((ev.clientX - b.left) / s), y: Math.floor((ev.clientY - b.top) / s) };
  }

  function startMove(ev, sel, x, y) {
    if (st.tool !== 'select' || ev.button !== 0) return;
    ev.stopPropagation(); ev.preventDefault();
    st.sel = sel;
    const c = cellOf(ev);
    drag = { kind: 'move', sel, ox: c.x - x, oy: c.y - y, x, y, x0: x, y0: y, el: ev.currentTarget };
    ev.currentTarget.setPointerCapture(ev.pointerId);
    ev.currentTarget.onpointermove = e => {
      const p = cellOf(e), nx = p.x - drag.ox, ny = p.y - drag.oy;
      if (!inMap(nx, ny) || (nx === drag.x && ny === drag.y)) return;
      const s = 16 * st.zoom;
      drag.el.style.left = (parseFloat(drag.el.style.left) + (nx - drag.x) * s) + 'px';
      drag.el.style.top = (parseFloat(drag.el.style.top) + (ny - drag.y) * s) + 'px';
      drag.x = nx; drag.y = ny;
      status.textContent = `Moving to ${nx}, ${ny}`;
    };
    ev.currentTarget.onpointerup = async e => {
      const d = drag; drag = null;
      e.currentTarget.onpointermove = e.currentTarget.onpointerup = null;
      if (d.x !== d.x0 || d.y !== d.y0) {
        try { await moveTo(d.sel, d.x, d.y); } catch (err) { toast(err.message, true); await reloadData(); }
      } else { drawObjects(); drawInspector(); drawOverlay(); }
    };
  }

  view.addEventListener('contextmenu', e => { if (st.tool !== 'select') e.preventDefault(); });
  stage.addEventListener('pointerdown', ev => {
    if (!M) return;
    const c = cellOf(ev);
    if (ev.button === 1 || (ev.button === 0 && ev.shiftKey && st.tool === 'select')) {   // pan
      drag = { kind: 'pan', sx: ev.clientX, sy: ev.clientY, l: view.scrollLeft, t: view.scrollTop };
      stage.setPointerCapture(ev.pointerId); ev.preventDefault(); return;
    }
    if (!inMap(c.x, c.y)) return;
    if (ev.button === 2 || (ev.button === 0 && ev.altKey)) {         // pick under the pointer
      if (st.tool === 'select') return;
      pickRect({ x: c.x, y: c.y, w: 1, h: 1 }); drawOverlay(); ev.preventDefault(); return;
    }
    if (ev.button !== 0) return;
    stage.setPointerCapture(ev.pointerId);
    if (st.tool === 'select') { st.sel = { type: 'cell', x: c.x, y: c.y }; drawObjects(); drawInspector(); drawOverlay(); return; }
    if (st.tool === 'brush') {
      drag = { kind: 'paint', ax: c.x, ay: c.y, stroke: new Map() };
      stampAt(drag.stroke, c.x, c.y);
    } else if (st.tool === 'fill') {
      commit(fill(c.x, c.y), 'Filled'); drawOverlay();
    } else if (st.tool === 'pick') {
      drag = { kind: 'pick', x0: c.x, y0: c.y, x: c.x, y: c.y };
    }
    drawOverlay();
  });
  stage.addEventListener('pointermove', ev => {
    if (!M) return;
    if (drag?.kind === 'pan') { view.scrollLeft = drag.l - (ev.clientX - drag.sx); view.scrollTop = drag.t - (ev.clientY - drag.sy); return; }
    const c = cellOf(ev);
    const moved = !hover || hover.x !== c.x || hover.y !== c.y;
    hover = inMap(c.x, c.y) ? c : null;
    if (!moved) return;
    if (drag?.kind === 'paint' && hover) stampAt(drag.stroke, anchorX(c.x), anchorY(c.y));
    if (drag?.kind === 'pick' && hover) { drag.x = c.x; drag.y = c.y; }
    showStatus(); drawOverlay();
  });
  stage.addEventListener('pointerleave', () => { if (!drag) { hover = null; showStatus(); drawOverlay(); } });
  stage.addEventListener('pointerup', () => {
    const d = drag;
    if (!d || d.kind === 'move') return;
    drag = null;
    if (d.kind === 'paint') commit(d.stroke);
    if (d.kind === 'pick') { pickRect(rectOf(d.x0, d.y0, d.x, d.y)); setTool('brush'); }
    drawOverlay();
  });

  function showStatus() {
    if (!hover) { status.textContent = ''; return; }
    const w = tileAt(hover.x, hover.y), k = w & 0x3FF;
    const here = [];
    for (const L of st.layers.sites ? M.locations : []) {
      const f = FOOT[L.kind] || [0, 0, 0, 0];
      if (hover.x >= Number(L.x) + f[0] && hover.x <= Number(L.x) + f[2] && hover.y >= Number(L.y) + f[1] && hover.y <= Number(L.y) + f[3])
        here.push(L.kind === 'castle' ? (L.name || 'castle') : 'village');
    }
    for (const u of visibleUnits()) if (Number(u.x) === hover.x && Number(u.y) === hover.y) here.push(`${u.name}${u.class ? ' (' + u.class + ')' : ''}`);
    status.replaceChildren(h('b', {}, `${hover.x}, ${hover.y}`), ` · ${terrainName(M.terrain[k])} · tile ${k}`,
      w >> 10 ? ` · area flags ${w >> 10}` : '', here.length ? h('span', { class: 'sub' }, ' · ' + here.join(', ')) : '');
  }

  // ------------------------------------------------------------ pointer: palette
  let palDrag = null;
  const palCell = ev => { const b = palCanvas.getBoundingClientRect(), S = 16 * st.palZoom; return { x: Math.max(0, Math.min(31, Math.floor((ev.clientX - b.left) / S))), y: Math.max(0, Math.min(31, Math.floor((ev.clientY - b.top) / S))) }; };
  palOver.addEventListener('pointerdown', ev => {
    const c = palCell(ev); palDrag = { x0: c.x, y0: c.y };
    palOver.setPointerCapture(ev.pointerId); selectPal(c);
  });
  palOver.addEventListener('pointermove', ev => {
    const c = palCell(ev), k = c.y * 32 + c.x;
    palOver.title = `Tile ${k} · ${terrainName(M.terrain[k])}`;
    if (palDrag) selectPal(c);
  });
  palOver.addEventListener('pointerup', () => { if (palDrag) { palDrag = null; if (st.tool !== 'fill') setTool('brush'); } });
  function selectPal(c) {
    const r = rectOf(palDrag.x0, palDrag.y0, c.x, c.y), tiles = [];
    for (let dy = 0; dy < r.h; dy++) for (let dx = 0; dx < r.w; dx++) tiles.push((r.y + dy) * 32 + r.x + dx);
    st.stamp = { w: r.w, h: r.h, tiles, src: { x: r.x, y: r.y } };
    drawPalette();
  }

  // ------------------------------------------------------------ zoom and keys
  function zoomBy(d, cx, cy) {
    const i = ZOOMS.indexOf(st.zoom), z = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, (i < 0 ? 2 : i) + d))];
    if (z === st.zoom) return;
    const vb = view.getBoundingClientRect();
    cx ??= vb.width / 2; cy ??= vb.height / 2;
    const mx = (view.scrollLeft + cx) / st.zoom, my = (view.scrollTop + cy) / st.zoom;
    st.zoom = z; layout(); drawOverlay(); drawObjects();
    view.scrollLeft = mx * z - cx; view.scrollTop = my * z - cy;
  }
  view.addEventListener('wheel', e => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const vb = view.getBoundingClientRect();
    zoomBy(e.deltaY < 0 ? 1 : -1, e.clientX - vb.left, e.clientY - vb.top);
  }, { passive: false });

  const onKey = e => {
    if (!document.body.contains(root) || !root.querySelector('.mapedit')) { removeEventListener('keydown', onKey); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || document.activeElement?.matches('input, select, textarea')) return;
    const k = e.key.toLowerCase();
    const t = { v: 'select', b: 'brush', g: 'fill', i: 'pick' }[k];
    if (t) { setTool(t); e.preventDefault(); }
    else if (k === '+' || k === '=') zoomBy(1);
    else if (k === '-') zoomBy(-1);
    else if (k === 'escape') { st.sel = null; drawObjects(); drawInspector(); drawOverlay(); }
  };
  addEventListener('keydown', onKey);

  view.dataset.tool = st.tool;
  try { await load(); } catch (e) { view.replaceChildren(h('div', { class: 'empty' }, e.message)); }

  return {
    async refresh(change) {
      if (!M) return;
      if (!change || change.maps?.includes(M.ch) || change.tables?.some(t => t === 'deploy' || t === 'locations')) await reloadData();
    },
  };
}

function svg(d) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 20 20'); s.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor');
  p.setAttribute('stroke-width', '1.6'); p.setAttribute('stroke-linejoin', 'round'); p.setAttribute('stroke-linecap', 'round');
  s.append(p);
  return s;
}
