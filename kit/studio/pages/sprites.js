// Map sprites: which little unit each class shows on the chapter map (with the game's per-character
// and per-gender choices), and the drawings themselves.
import { api, h, toast, setField, loadTables, refreshSession } from '../app.js';

const st = { sel: 0, army: 0, k: Date.now().toString(36) };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-sprites') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-sprites', JSON.stringify({ sel: st.sel, army: st.army })); } catch (e) { /* none */ } };
const ARMY_LABELS = { player: 'Player', enemy: 'Enemy', ally: 'Ally', other: 'Other', moved: 'Has moved' };

// one animation clock for every sprite on the page: frames 0 1 2 1, like the map
const sprites = new Set();
let tick = 0;
setInterval(() => {
  tick++;
  for (const c of sprites) { if (!c.isConnected) { sprites.delete(c); continue; } c._draw(); }
}, 220);

export async function spritesPage(root) {
  await loadTables(['map_sprites']);
  let D = await api('mapsprites');
  const list = h('div', { class: 'list' });
  const detail = h('div', { class: 'sheet-wrap' });
  const armyBar = h('div', { class: 'chips', role: 'radiogroup', 'aria-label': 'Army colours' });
  root.append(h('div', { class: 'split' },
    h('div', { class: 'roster' }, h('div', { class: 'roster-tools' }, h('p', { class: 'hint' }, 'Each class and the unit it shows on the map.')), list),
    detail));

  const info = name => D.sprites.find(s => s.name === name.toUpperCase());
  const url = (name, scale) => `/gfx/sprite/${name}.png?a=${st.army}&s=${scale}&c=${info(name)?.ver || 'rom'}-${st.k}`;

  // an animated canvas for a sprite
  function anim(name, scale, label) {
    const s = info(name);
    const w = 16, hh = s?.tall ? 24 : 16;
    const c = h('canvas', { class: 'spanim', width: w * scale, height: hh * scale, role: 'img', 'aria-label': label || `Sprite ${name}` });
    const im = new Image();
    im.src = url(name, scale);
    const ctx = c.getContext('2d');
    c._draw = () => {
      if (!im.complete || !im.naturalWidth) return;
      const f = [0, 1, 2, 1][tick % 4];
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.drawImage(im, f * w * scale, 0, w * scale, hh * scale, 0, 0, w * scale, hh * scale);
    };
    im.onload = () => c._draw();
    sprites.add(c);
    return c;
  }

  function drawArmyBar() {
    armyBar.replaceChildren(...D.armies.map((a, i) => h('button', { class: 'chip', role: 'radio', 'aria-checked': String(i === st.army), 'aria-pressed': String(i === st.army),
      onclick: () => { st.army = i; remember(); drawArmyBar(); drawList(); drawDetail(); } }, ARMY_LABELS[a] || a)));
  }

  function drawList() {
    list.replaceChildren(...D.classes.map(c => {
      const def = c.entries[c.entries.length - 1];
      return h('button', { 'aria-pressed': String(c.c === st.sel), onclick: () => { st.sel = c.c; remember(); drawList(); drawDetail(); } },
        h('span', { class: 'sprow' }, h('span', { class: 'spbox' }, anim(def.sprite, 2)),
          h('span', {}, h('b', {}, c.name), h('div', { class: 'sub' }, c.entries.length > 1 ? `${c.entries.length} sprites` : def.sprite))));
    }));
  }

  function entryLabel(e) {
    if (e.gender === 'default') return 'Everyone else';
    const g = e.gender === 'female' ? 'women' : e.gender === 'male' ? 'men' : `gender ${e.gender}`;
    if (e.character && e.character !== '0') return `${e.who || 'Unit ' + e.character} (${g === 'women' ? 'female' : 'male'})`;
    return g[0].toUpperCase() + g.slice(1);
  }

  function drawDetail() {
    detail.replaceChildren();
    const c = D.classes.find(x => x.c === st.sel) || D.classes[0];
    if (!c) return;
    const sheet = h('article', { class: 'sheet spsheet' });
    sheet.append(h('div', { class: 'arhead' }, h('h2', {}, c.name), h('p', { class: 'sub' }, `Class ${c.c}`)), h('div', { class: 'spbar' }, h('span', { class: 'sub' }, 'Colours'), armyBar));
    const rows = h('section', { class: 'arsec' }, h('h3', {}, 'On the map'),
      h('p', { class: 'hint' }, c.entries.length > 1 ? 'The game checks these from the top; the first that fits the unit is used.' : 'Every unit of this class looks like this.'));
    for (const e of c.entries) {
      const s = info(e.sprite);
      rows.append(h('div', { class: 'sprowbig' }, h('span', { class: 'spbox big' }, anim(e.sprite, 4)),
        h('div', {}, h('b', {}, entryLabel(e)), h('div', { class: 'sub' }, `${e.sprite} · ${s?.tall ? 'tall (mounted / flying)' : 'on foot'}${s?.custom ? ' · redrawn' : ''}`),
          h('div', { class: 'spbtns' }, h('button', { class: 'btn btn-line', onclick: () => picker(e) }, 'Use another sprite…'),
            h('button', { class: 'btn btn-line', onclick: () => drawing(e.sprite) }, 'Edit drawing')))));
    }
    sheet.append(rows);
    sheet.append(drawingSection(st.drawing && c.entries.some(e => e.sprite === st.drawing) ? st.drawing : c.entries[c.entries.length - 1].sprite));
    detail.append(sheet);
  }

  function drawing(name) { st.drawing = name; drawDetail(); detail.querySelector('.spdraw')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }

  function drawingSection(name) {
    const s = info(name);
    const sec = h('section', { class: 'arsec spdraw' }, h('h3', {}, `Drawing ${name} `, h('small', {}, s.tall ? 'three 16 × 24 frames' : 'three 16 × 16 frames')));
    const big = h('img', { class: 'spframes', src: url(name, 6), alt: `Frames of ${name}`, width: 48 * 6, height: (s.tall ? 24 : 16) * 6 });
    const file = h('input', { type: 'file', accept: 'image/png,image/*', hidden: true });
    file.onchange = async () => { const f = file.files[0]; file.value = ''; if (f) importSprite(s, f); };
    sec.append(h('div', { class: 'spdrawrow' }, big, h('div', { class: 'spanimbig' }, anim(name, 6))),
      h('p', { class: 'sub' }, s.users.length ? `Used by ${s.users.join(', ')}.` : 'No class uses it.'),
      h('div', { class: 'ptactions' },
        h('button', { class: 'btn btn-gilt', onclick: () => file.click() }, 'Replace drawing…'),
        h('a', { class: 'btn btn-line', href: `/gfx/sprite/${name}.idx.png?c=${s.ver}-${st.k}`, download: `sprite_${name}.png` }, 'Download PNG'),
        s.custom ? h('button', { class: 'btn btn-line danger', onclick: () => send({ name, reset: true }, 'Back to the game\'s drawing') }, 'Use the original') : null, file),
      h('p', { class: 'hint' }, `A drawing is ${s.tall ? '48 × 24' : '48 × 16'} pixels: three frames side by side (2× to 4× bigger works too). `,
        'Colours become the nearest of the map palette, which every army recolours; transparent pixels show the map. Sprites are shared: every class that uses this one changes.'));
    return sec;
  }

  async function send(body, msg) {
    try { await api('mapsprite', body); await reload(); toast(msg); } catch (e) { toast(e.message, true); }
  }

  function importSprite(s, f) {
    const w = 48, hh = s.tall ? 24 : 16;
    const u = URL.createObjectURL(f);
    const im = new Image();
    im.onerror = () => { URL.revokeObjectURL(u); toast('That file isn\'t a picture the browser can open.', true); };
    im.onload = () => {
      URL.revokeObjectURL(u);
      const k = im.width / w;
      if (!Number.isInteger(k) || k < 1 || k > 8 || im.height !== hh * k) {
        toast(`This sprite is ${w} × ${hh} pixels (or 2×, 3×, 4× that); the picture is ${im.width} × ${im.height}.`, true);
        return;
      }
      const c = document.createElement('canvas');
      c.width = w; c.height = hh;
      const ctx = c.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(im, 0, 0, w, hh);
      send({ name: s.name, png: c.toDataURL('image/png').split(',')[1] }, `${s.name} redrawn (Ctrl+Z undoes it)`);
    };
    im.src = u;
  }

  function picker(e) {
    const cur = e.sprite.toUpperCase();
    const grid = name => h('button', { class: 'spcell', 'aria-pressed': String(name === cur), title: `${name}${info(name).users.length ? ': ' + info(name).users.join(', ') : ''}`,
      onclick: async () => {
        modal.remove();
        try { await setField('map_sprites', e.row, 'sprite', name); await reload(); toast(`${entryLabel(e)}: ${name}`); } catch (er) { toast(er.message, true); }
      } }, anim(name, 2), h('span', {}, name));
    const foot = D.sprites.filter(s => !s.tall).map(s => grid(s.name));
    const tall = D.sprites.filter(s => s.tall).map(s => grid(s.name));
    const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Choose a sprite' },
      h('div', { class: 'modal-box spmodal' }, h('h2', {}, `Sprite for ${e.gender === 'default' || !e.character || e.character === '0' ? entryLabel(e).toLowerCase() : entryLabel(e)}`),
        h('h4', {}, 'On foot'), h('div', { class: 'spgrid' }, foot),
        h('h4', {}, 'Mounted and flying'), h('div', { class: 'spgrid' }, tall),
        h('div', { class: 'modal-actions' }, h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'))));
    modal.addEventListener('keydown', ev => { if (ev.key === 'Escape') modal.remove(); });
    document.body.append(modal);
    modal.querySelector('[aria-pressed="true"]')?.focus();
  }

  async function reload() {
    D = await api('mapsprites');
    await refreshSession();
    drawArmyBar(); drawList(); drawDetail();
  }

  drawArmyBar(); drawList(); drawDetail();
  list.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: 'center' });
  return {
    async refresh(change) {
      if (!change || change.files?.length || change.tables?.includes('map_sprites')) { await loadTables(['map_sprites'], true); await reload(); }
    },
  };
}
