// Battle animations: which animation, body, upper body and palette each class shows in battle (per
// weapon kind, gender and a few characters), with a player for every motion the animation has.
import { api, h, toast, refreshSession, watchJob } from '../app.js';

const st = { cls: null, row: null, motion: 1, speed: 1, mirror: false, item: null, playing: true, override: null };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-battle') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-battle', JSON.stringify({ cls: st.cls, row: st.row, motion: st.motion, speed: st.speed, mirror: st.mirror, view: st.view, spell: st.spell, skill: st.skill })); } catch (e) { /* none */ } };
const FIELDS = [['anim', 'Animation', 'Moves and frames'], ['body', 'Body graphics', 'The frames\' drawings'],
  ['upper', 'Upper body', 'Rider, torso and head tiles'], ['palette', 'Palette', 'Colours']];
const SCALE = 3;
// SNES colours (BGR555) <-> CSS
const toRgb = c => [(c & 31) * 255 / 31, (c >> 5 & 31) * 255 / 31, (c >> 10 & 31) * 255 / 31].map(Math.round);
const toHex = c => '#' + toRgb(c).map(v => v.toString(16).padStart(2, '0')).join('');
const fromHex = x => { const n = parseInt(x.slice(1), 16); const r = n >> 16, g = n >> 8 & 255, b = n & 255;
  return Math.round(r * 31 / 255) | Math.round(g * 31 / 255) << 5 | Math.round(b * 31 / 255) << 10; };
function shiftColour(c, hue, sat, light) {
  let [r, g, b] = toRgb(c).map(v => v / 255);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  let hh = 0, ss = 0;
  if (d) { ss = d / (1 - Math.abs(2 * l - 1)); hh = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; hh *= 60; }
  hh = (hh + hue + 360) % 360; ss = Math.min(1, Math.max(0, ss * sat)); const L = Math.min(1, Math.max(0, l + light));
  const C = (1 - Math.abs(2 * L - 1)) * ss, X = C * (1 - Math.abs((hh / 60) % 2 - 1)), m = L - C / 2;
  const [a, bb, cc] = hh < 60 ? [C, X, 0] : hh < 120 ? [X, C, 0] : hh < 180 ? [0, C, X] : hh < 240 ? [0, X, C] : hh < 300 ? [X, 0, C] : [C, 0, X];
  return fromHex('#' + [a + m, bb + m, cc + m].map(v => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join(''));
}

export async function battlePage(root) {
  let D = await api('battleanims');
  const list = h('div', { class: 'list' });
  const detail = h('div', { class: 'sheet-wrap' });
  const find = h('input', { class: 'in', type: 'search', placeholder: 'Find a class', 'aria-label': 'Find a class' });
  const viewBar = h('div', { class: 'chips', role: 'tablist', 'aria-label': 'Show' });
  let rosterHint = null;
  const HINTS = { classes: 'What each class looks like in battle, for each weapon it can use.', spells: '', spellgfx: 'The pictures each spell effect is drawn from.',
    skillanims: 'The sparkle each skill shows when it activates in battle.',
    mapbattle: 'The little figures that fight on the map when battle animations are off.',
    mapspells: 'What tomes and staves show on the map when battle animations are off.' };
  const drawViewBar = () => viewBar.replaceChildren(...[['classes', 'Classes'], ['spells', 'Spells'], ['spellgfx', 'Spell pictures'], ['skillanims', 'Skill animations'], ['mapbattle', 'Map battles'], ['mapspells', 'Map spells']].map(([k, t]) =>
    h('button', { class: 'chip', role: 'tab', 'aria-selected': String((st.view || 'classes') === k), onclick: () => { st.view = k; remember(); drawViewBar(); drawList(); drawDetail(); } }, t)));
  drawViewBar();
  root.append(h('div', { class: 'split' },
    h('div', { class: 'roster' }, h('div', { class: 'roster-tools' }, viewBar, find,
      (rosterHint = h('p', { class: 'hint' }))), list),
    detail));

  const classes = () => {
    const seen = new Map();
    for (const r of D.rows) { const c = Number(r.class); if (!seen.has(c)) seen.set(c, { id: c, name: r._class || `Class ${c}`, rows: [] }); seen.get(c).rows.push(r); }
    return [...seen.values()];
  };
  const usedBy = (field, v) => [...new Set(D.rows.filter(r => Number(r[field]) === Number(v)).map(r => r._class))];
  const weaponName = r => D.weapons[r.weapon] || `kind ${r.weapon}`;
  const rowLabel = r => [weaponName(r), r.gender === '1' ? 'female' : null, r._char ? `${r._char} only` : null].filter(Boolean).join(', ');

  function drawList() {
    const q = find.value.trim().toLowerCase();
    find.hidden = st.view === 'spells' || st.view === 'skillanims';
    find.placeholder = st.view === 'spellgfx' || st.view === 'mapspells' ? 'Find a spell' : 'Find a class';
    rosterHint.textContent = HINTS[st.view || 'classes'] || ''; rosterHint.hidden = !rosterHint.textContent;
    if (st.view === 'skillanims') { drawSkillList(); return; }
    if (st.view === 'mapbattle') { drawMbList(q); return; }
    if (st.view === 'mapspells') { drawMsList(q); return; }
    if (st.view === 'spellgfx') { drawPicList(q); return; }
    if (st.view === 'spells') { list.replaceChildren(h('p', { class: 'hint baspellhint' }, 'Tomes, staves and magic swords play a spell effect when they attack or heal. Pick which effect each one plays, or give one to another item.')); return; }
    list.replaceChildren(...classes().filter(c => !q || c.name.toLowerCase().includes(q)).map(c =>
      h('button', { 'aria-pressed': String(c.id === st.cls), onclick: () => { st.cls = c.id; st.row = null; remember(); drawList(); drawDetail(); } },
        h('span', {}, c.name), h('span', { class: 'sub' }, `${c.rows.length} weapon${c.rows.length === 1 ? '' : 's'}`))));
  }
  find.oninput = drawList;

  // ------------------------------------------------------------ player
  let timer = null;
  function player(r) {
    const item = st.item ?? D.defaultItems[r.weapon] ?? 0;
    const q = `a=${r.anim}&b=${r.body}&u=${r.upper}&p=${r.palette}&i=${item}`;
    const canvas = h('canvas', { class: 'bacanvas', width: 10, height: 10, role: 'img', 'aria-label': `Battle animation of ${r._class}` });
    const motionSel = h('select', { class: 'in', 'aria-label': 'Motion' });
    const frameLbl = h('span', { class: 'bafr' }, '');
    const playBtn = h('button', { class: 'btn btn-line', type: 'button' }, st.playing ? 'Pause' : 'Play');
    const speed = h('select', { class: 'in', 'aria-label': 'Speed' }, [[0.25, '¼×'], [0.5, '½×'], [1, '1×'], [2, '2×']].map(([v, t]) => h('option', { value: v, selected: v === st.speed }, t)));
    const mirror = h('label', { class: 'bacheck' }, h('input', { type: 'checkbox', checked: st.mirror }), ' Left side');
    const items = D.items.filter(([, n]) => n);
    const itemSel = h('select', { class: 'in', 'aria-label': 'Weapon shown' }, items.map(([i, n]) => h('option', { value: i, selected: i === item }, n)));
    const strip = h('div', { class: 'bastrip' });
    const wrap = h('div', { class: 'baplayer' },
      h('div', { class: 'bastage' }, canvas),
      h('div', { class: 'bacontrols' }, h('label', { class: 'lbl' }, h('span', {}, 'Motion'), motionSel),
        h('label', { class: 'lbl' }, h('span', {}, 'Speed'), speed), h('label', { class: 'lbl' }, h('span', {}, 'Weapon shown'), itemSel),
        h('div', { class: 'bacbtns' }, playBtn, h('button', { class: 'btn btn-line', type: 'button', onclick: () => step() }, 'Next frame'), mirror, frameLbl)),
      h('h4', {}, 'All frames'), strip,
      h('p', { class: 'hint' }, h('a', { href: `/gfx/battle/?${q}`, download: `battle_${r._class || 'class'}_${weaponName(r)}.png` }, 'Download the frames as a PNG'),
        '. Motions are the game\'s own scripts: frame numbers with how long each shows (1/60 s), plus loops and cues for sounds and hits.'));
    const img = new Image();
    let info = null, seq = [], pos = 0, left = 0, cur = 0;
    const ctx = canvas.getContext('2d');

    // play the motion the way the game reads it: frames with times, waits, jumps; ends pause and repeat
    function build() {
      const m = (st.override && st.override.motion === st.motion ? st.override.steps : info.motions[st.motion]) || [];
      seq = []; let i = 0, total = 0, guard = 0, last = 0;
      while (i < m.length && total < 1500 && guard++ < 3000) {
        const [c, v] = m[i];
        if (c < 0xE7) { last = c; if (c < info.frames) { if (v) { seq.push([c, v]); total += v; } } i++; }
        else if (c === 0xFA) { seq.push([last, Math.max(1, v)]); total += v; i++; }
        else if (c === 0xFB || c === 0xF3) { i = Math.max(0, i - Math.max(1, v)); }
        else if (c === 0xFC) { i = 0; if (!seq.length) break; }
        else if (c === 0xFE || c === 0xFD || c === 0xF1 || c === 0xFF) break;
        else i++;
      }
      if (!seq.length) seq = [[last, 30]];
      seq.push([seq[seq.length - 1][0], 40]);      // hold the last frame a moment before repeating
      pos = 0; left = seq[0][1]; cur = seq[0][0];
    }
    function draw() {
      const [cw, chh] = info.cell;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#2B3150'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#3A4166'; ctx.fillRect(0, (info.origin[1] + 4) * SCALE, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = false;
      ctx.save();
      if (st.mirror) { ctx.translate(canvas.width, 0); ctx.scale(-1, 1); }
      ctx.drawImage(img, cur * cw, 0, cw, chh, 0, 0, cw * SCALE, chh * SCALE);
      ctx.restore();
      frameLbl.textContent = `Frame ${cur}`;
      for (const [i, b] of [...strip.children].entries()) b.setAttribute('aria-pressed', String(i === cur));
    }
    function step() {
      if (!info) return;
      pos = (pos + 1) % seq.length; cur = seq[pos][0]; left = seq[pos][1]; draw();
    }
    function tickFn() {
      if (!canvas.isConnected) { clearInterval(timer); timer = null; return; }
      if (!info || !st.playing) return;
      left -= st.speed;
      while (left <= 0) { pos = (pos + 1) % seq.length; cur = seq[pos][0]; left += seq[pos][1]; }
      draw();
    }
    playBtn.onclick = () => { st.playing = !st.playing; playBtn.textContent = st.playing ? 'Pause' : 'Play'; };
    speed.onchange = () => { st.speed = Number(speed.value); remember(); };
    mirror.querySelector('input').onchange = e => { st.mirror = e.target.checked; remember(); draw(); };
    itemSel.onchange = () => { st.item = Number(itemSel.value); drawDetail(); };
    motionSel.onchange = () => { const was = st.motion; st.motion = Number(motionSel.value); remember(); build(); draw(); if (was !== st.motion) detail.querySelector('.bamotion')?._reload?.(); };
    (async () => {
      try {
        info = await api('battleinfo?' + q);
      } catch (e) { wrap.replaceChildren(h('p', { class: 'hint' }, e.message)); return; }
      img.onload = () => {
        const [cw, chh] = info.cell;
        canvas.width = cw * SCALE; canvas.height = chh * SCALE;
        motionSel.replaceChildren(...info.motions.map((m, i) => {
          const fr = new Set(m.filter(([c]) => c < info.frames).map(([c]) => c));
          return h('option', { value: i, selected: i === st.motion }, `Motion ${i}${fr.size ? ` (${fr.size} frame${fr.size === 1 ? '' : 's'})` : ' (empty)'}`);
        }));
        if (st.motion >= info.motions.length) st.motion = Math.min(1, info.motions.length - 1);
        motionSel.value = String(st.motion);
        strip.replaceChildren(...Array.from({ length: info.frames }, (_, k) => {
          const c = h('canvas', { width: cw, height: chh, class: 'baframe' });
          c.getContext('2d').drawImage(img, k * cw, 0, cw, chh, 0, 0, cw, chh);
          return h('button', { type: 'button', class: 'babtn', title: `Frame ${k}`, onclick: () => { st.playing = false; playBtn.textContent = 'Play'; cur = k; draw(); } }, c, h('span', {}, k));
        }));
        build(); draw();
        if (!timer) timer = setInterval(tickFn, 1000 / 60);
      };
      img.src = `/gfx/battle/?${q}`;
    })();
    wrap._replay = () => { if (info) { build(); draw(); } };
    wrap._frames = () => info ? info.frames : 0;
    wrap._thumb = k => { const c = h('canvas', { width: info.cell[0], height: info.cell[1], class: 'bathumb' }); if (img.complete) c.getContext('2d').drawImage(img, k * info.cell[0], 0, info.cell[0], info.cell[1], 0, 0, info.cell[0], info.cell[1]); return c; };
    return wrap;
  }

  // ------------------------------------------------------------ detail
  async function drawSpells() {
    let S;
    try { S = await api('battlespells'); } catch (e) { detail.replaceChildren(h('div', { class: 'empty' }, e.message)); return; }
    const spellOpts = v => S.spells.map(([k, n]) => h('option', { value: k, selected: String(k) === String(v) }, `${k}${n ? ` · ${n}` : ''}`));
    const set = async (i, field, value) => {
      try { await api('setmany', { changes: [{ table: 'spells', row: i, field, value: String(value) }] }); await refreshSession(); drawSpells(); }
      catch (e) { toast(e.message, true); }
    };
    const rows = S.rows.map((r, i) => {
      const a = h('select', { class: 'in', 'aria-label': `Effect for ${r._item}` }, spellOpts(r.spell));
      const f = h('select', { class: 'in', 'aria-label': `Effect at range for ${r._item}` }, spellOpts(r.spell_far));
      a.onchange = () => set(i, 'spell', a.value);
      f.onchange = () => set(i, 'spell_far', f.value);
      return h('tr', {}, h('th', { scope: 'row' }, r._item || `Item ${r.item}`), h('td', {}, a), h('td', {}, f),
        h('td', {}, h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Remove ${r._item}`, onclick: async () => {
          try { await api('spellrow', { delete: i }); await refreshSession(); drawSpells(); toast(`${r._item} has no effect now (Undo brings it back)`); } catch (e) { toast(e.message, true); } } }, '✕')));
    });
    const have = new Set(S.rows.map(r => Number(r.item)));
    const addItem = h('select', { class: 'in', 'aria-label': 'Item to add' }, h('option', { value: '' }, 'Choose an item…'),
      S.items.filter(([k]) => !have.has(k)).map(([k, n]) => h('option', { value: k }, n)));
    const addSpell = h('select', { class: 'in', 'aria-label': 'Its effect' }, spellOpts(2));
    const addBtn = h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
      if (!addItem.value) { toast('Choose an item.', true); return; }
      try { await api('spellrow', { add: Number(addItem.value), spell: Number(addSpell.value) }); await refreshSession(); drawSpells(); } catch (e) { toast(e.message, true); }
    } }, 'Add');
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, 'Spell effects'), h('p', { class: 'sub' }, `${S.rows.length} items · ${S.spells.length} effects in the game`)),
      h('div', { class: 'baspells' }, h('table', { class: 'batable' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Item'), h('th', {}, 'Effect'), h('th', {}, 'Effect at range'), h('th', {}, ''))),
        h('tbody', {}, rows))),
      h('div', { class: 'bacopy' }, h('span', {}, 'Give an item an effect:'), addItem, addSpell, addBtn),
      h('p', { class: 'hint' }, 'Effects are named after the first item that uses them in the game; the unnamed ones are used by other battle events. "At range" is what the game plays in some situations instead: Physic and the status staves use it when cast from far away. An effect only plays if the attacker\'s battle animation casts (tomes, staves, magic swords); a plain sword swing or thrown axe ignores it.')));
  }

  // ------------------------------------------------------------ spell pictures
  let PL = null;
  async function drawPicList(q) {
    if (!PL) {
      list.replaceChildren(h('p', { class: 'hint' }, 'Reading the spell pictures…'));
      try { PL = await api('spellgfx'); } catch (e) { list.replaceChildren(h('p', { class: 'hint' }, e.message)); return; }
    }
    const items = PL.spells.filter(x => !q || (x.name || '').toLowerCase().includes(q) || String(x.spell) === q);
    list.replaceChildren(...items.map(x => h('button', { 'aria-pressed': String(x.spell === st.spell), onclick: () => { st.spell = x.spell; remember(); drawList(); drawDetail(); } },
      h('span', {}, x.name || `Effect ${x.spell}`, x.new ? h('span', { class: 'sfxnew' }, 'new') : null),
      h('span', { class: 'sub' }, `${x.pictures} picture${x.pictures === 1 ? '' : 's'}${x.edited ? ` · ${x.edited} redrawn ✎` : ''}`))));
    if (st.spell == null && PL.spells.length) { st.spell = PL.spells.find(x => x.spell === 2)?.spell ?? PL.spells[0].spell; drawDetail(); }
  }

  async function drawPictures() {
    if (st.spell == null) { detail.replaceChildren(h('div', { class: 'empty' }, 'Reading the spell pictures…')); return; }
    let P;
    try { P = await api(`spellgfx?spell=${st.spell}`); } catch (e) { detail.replaceChildren(h('div', { class: 'empty' }, e.message)); return; }
    const v = Date.now();
    const name = P.name || `Effect ${P.spell}`;
    const after = async msg => { PL = null; await refreshSession(); drawList(); drawPictures(); if (msg) toast(msg); };
    const hasColours = P.colours.length > 0;
    const real = hasColours && st.colourView !== 'standin';
    const cq = real ? `&c=${P.spell}` : '';
    const viewChips = hasColours ? h('div', { class: 'chips', role: 'tablist', 'aria-label': 'Show pictures in' },
      [['battle', 'Battle colours'], ['standin', 'Stand-in colours']].map(([k, t]) => h('button', { class: 'chip', role: 'tab',
        'aria-selected': String((real ? 'battle' : 'standin') === k), onclick: () => { st.colourView = k; drawPictures(); } }, t))) : null;
    const setColours = async (sets, msg) => {
      try { await api('spellcolours', { sets }); await after(msg); } catch (e) { toast(e.message, true); }
    };
    // colour sets
    let shifted = null;          // live hue shift preview: {addr: colours}
    const shiftBox = h('div', { class: 'sfxshift' });
    const setRows = h('div', { class: 'sfxsets' });
    const drawSets = () => setRows.replaceChildren(...P.colours.map(cs => {
      const cols = shifted ? shifted[cs.addr] : cs.colours;
      const cells = [...Array(cs.lead).fill(null), ...cols.map((c, k) => [c, k])];
      const rows = [];
      for (let i = 0; i < cells.length; i += cs.per) rows.push(cells.slice(i, i + cs.per).map(cell => {
        if (!cell) return h('span', { class: 'sfxsw empty', 'aria-hidden': 'true' });
        const [c, k] = cell;
        const pick = h('input', { type: 'color', value: toHex(c), 'aria-label': `${cs.label}, colour ${k + 1}`, title: `${toHex(c)}${c !== cs.game[k] ? ` (the game's: ${toHex(cs.game[k])})` : ''}` });
        pick.onchange = () => { const next = cs.colours.slice(); next[k] = fromHex(pick.value); setColours({ [cs.addr]: next }, 'Colour changed'); };
        return h('label', { class: 'sfxsw' + (c !== cs.game[k] ? ' changed' : ''), style: `--c:${toHex(c)}` }, pick);
      }));
      let speed = null;
      if (cs.frames != null) {
        const inp = h('input', { class: 'in num', type: 'number', min: 1, max: 128, value: cs.frames, 'aria-label': `${cs.label}: frames per step` });
        inp.onchange = () => { const n = Math.round(Number(inp.value)); if (!(n >= 1 && n <= 128)) { toast('Frames per step are 1 to 128.', true); inp.value = cs.frames; return; }
          api('spellcolours', { frames: { [cs.addr]: n } }).then(() => after(`${cs.label.split(' · ')[0]} now changes every ${n} frame${n === 1 ? '' : 's'}`)).catch(e => toast(e.message, true)); };
        speed = h('label', { class: 'sfxspeed' }, 'Changes every ', inp, ` frame${cs.frames === 1 ? '' : 's'}${cs.frames_varies ? ' (varies: setting it makes every step the same)' : ''}`,
          cs.frames_edited ? h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => api('spellcolours', { frames: { [cs.addr]: null } }).then(() => after('Back to the game\'s speed')).catch(e => toast(e.message, true)) }, 'Game\'s speed') : null);
      }
      return h('div', { class: 'sfxset' },
        h('div', { class: 'sfxsethead' }, h('strong', {}, cs.label), cs.edited ? h('span', { class: 'sub' }, ' ✎') : null,
          cs.edited ? h('button', { class: 'btn btn-line btn-sm', type: 'button', onclick: () => setColours({ [cs.addr]: null }, 'Back to the game\'s colours (Undo brings yours back)') }, 'Use the game\'s') : null),
        cs.shared.length ? h('p', { class: 'hint' }, `Also used by ${cs.shared.slice(0, 3).join(', ')}${cs.shared.length > 3 ? ` and ${cs.shared.length - 3} more` : ''}: they change too.`) : null,
        speed, h('div', { class: 'sfxrows' }, rows.map(r => h('div', { class: 'sfxrow' }, r))));
    }));
    if (hasColours) {
      const hue = h('input', { type: 'range', min: -180, max: 180, value: 0, 'aria-label': 'Hue' });
      const sat = h('input', { type: 'range', min: 0, max: 200, value: 100, 'aria-label': 'Saturation' });
      const lit = h('input', { type: 'range', min: -50, max: 50, value: 0, 'aria-label': 'Brightness' });
      const live = () => {
        const H = Number(hue.value), S = Number(sat.value) / 100, L = Number(lit.value) / 100;
        shifted = H || S !== 1 || L ? Object.fromEntries(P.colours.map(cs => [cs.addr, cs.colours.map(c => shiftColour(c, H, S, L))])) : null;
        drawSets(); apply.disabled = !shifted;
      };
      hue.oninput = sat.oninput = lit.oninput = live;
      const apply = h('button', { class: 'btn btn-gilt', type: 'button', disabled: true, onclick: () => setColours(shifted, `Recoloured ${name}`) }, 'Apply to this spell');
      const anyEdited = P.colours.some(cs => cs.edited);
      shiftBox.replaceChildren(h('div', { class: 'sfxsliders' },
        h('label', { class: 'lbl' }, h('span', {}, 'Hue'), hue), h('label', { class: 'lbl' }, h('span', {}, 'Saturation'), sat),
        h('label', { class: 'lbl' }, h('span', {}, 'Brightness'), lit)),
        h('div', { class: 'sfxbtns' }, apply, anyEdited ? h('button', { class: 'btn btn-line', type: 'button',
          onclick: () => setColours(Object.fromEntries(P.colours.map(cs => [cs.addr, null])), 'Back to the game\'s colours (Undo brings yours back)') }, 'Use the game\'s colours') : null));
    }
    drawSets();
    // steps
    let steps = P.steps.map(x => ({ ...x }));
    let stepsDirty = false;
    const motionEdits = {};
    const stepList = h('ol', { class: 'basteplist sfxsteps' });
    const saveSteps = h('button', { class: 'btn btn-gilt', type: 'button', disabled: true, onclick: async () => {
      try { await api('spellsteps', { spell: P.spell, words: steps.map(x => x.word), motions: motionEdits }); await after('Saved the steps'); } catch (e) { toast(e.message, true); } } }, 'Save steps');
    const dirty = () => { stepsDirty = true; saveSteps.disabled = false; drawSteps(); };
    const mk = (word, kind, label, value) => ({ word, kind, label, value });
    function drawSteps() {
      stepList.replaceChildren(...steps.map((x, i) => {
        let body;
        if (x.kind === 'pause' || x.kind === 'sound') {
          const inp = h('input', { class: 'in num', type: 'number', min: 0, max: 511, value: x.value, 'aria-label': `${x.label} (step ${i + 1})` });
          inp.onchange = () => { const n = Math.round(Number(inp.value)); if (!(n >= 0 && n <= 511)) { toast('Use 0 to 511.', true); inp.value = x.value; return; }
            x.value = n; x.word = (x.word & ~0x1FF) | n; dirty(); };
          body = x.kind === 'pause' ? [h('span', { class: 'baslabel' }, 'Pause'), inp, ' frames'] : [h('span', { class: 'baslabel' }, x.label), ' number ', inp];
        } else if (x.kind === 'motion') {
          const pr = motionEdits[x.key] || x.params || {};
          const num = (name, lo, hi, lab) => {
            const inp = h('input', { class: 'in num', type: 'number', min: lo, max: hi, value: pr[name], 'aria-label': `${lab} (step ${i + 1})` });
            inp.onchange = () => { const n = Math.round(Number(inp.value)); if (!(n >= lo && n <= hi)) { toast(`Use ${lo} to ${hi}.`, true); inp.value = pr[name]; return; }
              motionEdits[x.key] = { ...pr, [name]: n }; dirty(); };
            return inp;
          };
          const p0 = x.params || {};
          body = [h('span', { class: 'baslabel' }, 'Background: ' + x.motion + (x.motion_edited || motionEdits[x.key] ? ' ✎' : ''))];
          if ('x' in p0) body.push(' by ', num('x', -128, 127, 'Pixels a frame across'), ' across, ', num('y', -128, 127, 'Pixels a frame down'), ' down a frame, for ', num('frames', 1, 9999, 'Frames'), ' frames');
          else if ('speed' in p0) body.push(' at speed ', num('speed', 1, 255, 'Speed'));
          else body.push(h('span', { class: 'sub' }, ` ${x.value}`));
        } else {
          body = [h('span', { class: 'baslabel' + (x.kind === 'control' ? ' sfxctl' : '') }, x.label), x.value != null ? h('span', { class: 'sub' }, ` ${x.value}`) : null];
        }
        const mv = (d) => { const j = i + d; if (j < 0 || j >= steps.length) return; [steps[i], steps[j]] = [steps[j], steps[i]]; dirty(); };
        return h('li', { class: 'bastep' + (x.kind === 'control' ? ' cmd' : '') }, ...body,
          h('span', { class: 'bastepbtns' },
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Move step ${i + 1} up`, onclick: () => mv(-1) }, '↑'),
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Move step ${i + 1} down`, onclick: () => mv(1) }, '↓'),
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Copy step ${i + 1}`, title: 'Copy', onclick: () => { steps.splice(i + 1, 0, { ...x }); dirty(); } }, '⧉'),
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Remove step ${i + 1}`, onclick: () => { steps.splice(i, 1); dirty(); } }, '✕')));
      }));
    }
    drawSteps();
    const stepsBox = h('div', { class: 'baredraw sfxstepsbox' },
      h('h3', {}, 'Steps', P.steps_edited ? ' ✎' : ''),
      h('p', { class: 'hint' }, 'What the effect does, in order: the game runs a step each frame and stops at a Pause or a Wait until it is over. Make it faster or slower with the Pause lengths (60 frames = 1 second), change the sounds, or move, copy and remove steps. Wait for the steps above to finish holds things until the pictures, motions and colour changes above are done.'),
      stepList,
      h('div', { class: 'bacbtns' },
        h('button', { class: 'btn btn-line', type: 'button', onclick: () => { steps.push(mk(0x5400 | 30, 'pause', 'Pause', 30)); dirty(); } }, 'Add a pause'),
        h('button', { class: 'btn btn-line', type: 'button', onclick: () => { steps.push(mk(0x2A00 | 1, 'sound', 'Sound', 1)); dirty(); } }, 'Add a sound'),
        saveSteps,
        (P.steps_edited || P.steps.some(x => x.motion_edited)) ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
          try { await api('spellsteps', { spell: P.spell, words: null, motions: Object.fromEntries(P.steps.filter(x => x.motion_edited).map(x => [x.key, null])) });
            await after('Back to the game\'s steps (Undo brings yours back)'); } catch (e) { toast(e.message, true); } } }, 'Use the game\'s steps') : null),
      h('p', { class: 'hint' }, 'New steps go at the end; move them up to where they belong. Background steps move the effect\'s pictures: a Move slides them a few pixels each frame (negative goes left or up; the game mirrors it for the other side), Fly to the target sends them at the target (higher speed is faster). Other effects can share a background step and change with it; make a new effect to keep them apart. Removing the Signal or Hit steps can leave a fighter waiting, so check changes with Watch in battle.'));
    // new effects: make one from this, rename or delete it
    const nameIn = h('input', { class: 'in', placeholder: 'Name, e.g. Blue Fire', maxlength: 40, 'aria-label': 'New effect name' });
    const makeBox = h('div', { class: 'sfxmake', hidden: true }, nameIn,
      h('button', { class: 'btn btn-gilt', type: 'button', onclick: async () => {
        try { const res = await api('spelleffect', { new: P.spell, name: nameIn.value }); st.spell = res.id; remember();
          await after(`Made ${nameIn.value.trim() || 'a new effect'}: a copy of ${name}. Give it to an item on the Spells tab.`); }
        catch (e) { toast(e.message, true); } } }, 'Make it'),
      h('button', { class: 'btn btn-line', type: 'button', onclick: () => { makeBox.hidden = true; } }, 'Cancel'));
    const watch = h('button', { class: 'btn btn-gilt', type: 'button', title: 'Opens the PC port on a copy of your ROM: it races through the Prologue to a battle where Gandolf casts this effect, then replays the battle until you close it', onclick: async () => {
      watch.disabled = true; watch.textContent = 'Building…';
      try { await watchJob(await api('spellpreview', { spell: P.spell }), () =>
        toast('The PC port is opening: it plays up to the battle at full speed, then shows the effect again and again until you close it.'));
      } catch (e) { toast(e.message, true); }
      watch.disabled = false; watch.textContent = 'Watch in battle'; } }, 'Watch in battle');
    const tools = h('div', { class: 'sfxtools' }, watch,
      h('button', { class: 'btn btn-line', type: 'button', onclick: () => { makeBox.hidden = false; nameIn.focus(); } }, 'New effect from this one…'),
      P.new ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
        const nm = prompt('New name for this effect', P.own_name || '');
        if (nm == null) return;
        try { await api('spelleffect', { rename: P.spell, name: nm }); await after('Renamed'); } catch (e) { toast(e.message, true); } } }, 'Rename…') : null,
      P.new ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
        try { await api('spelleffect', { delete: P.spell }); st.spell = P.from; remember(); await after(`Deleted ${name} (Undo brings it back)`); } catch (e) { toast(e.message, true); } } }, 'Delete') : null);
    const about = P.new ? h('p', { class: 'hint sfxabout' }, `Your effect: a copy of ${P.from_name || `effect ${P.from}`} with its own pictures and colours. `,
      P.items.length ? `Used by ${P.items.join(', ')}.` : 'No item uses it yet: pick it for one on the Spells tab.') :
      h('p', { class: 'hint sfxabout' }, 'Changes here show wherever the game uses this effect. To keep the original and make a variant (Fire in another colour, say), make a new effect from this one.');
    const cards = P.pictures.map(pc => {
      const fileIn = h('input', { type: 'file', accept: '.png,image/png', hidden: true });
      const imp = h('button', { class: 'btn btn-gilt', type: 'button', onclick: () => fileIn.click() }, 'Import…');
      fileIn.onchange = async () => {
        const f = fileIn.files[0]; fileIn.value = '';
        if (!f) return;
        const buf = new Uint8Array(await f.arrayBuffer());
        let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
        imp.disabled = true; imp.textContent = 'Importing…';
        try {
          const res = await api('spellgfxset', { record: pc.record, png: btoa(bin) });
          await after(res.same ? 'That picture is the same as the game\'s.' : `Redrew ${res.tiles} tile${res.tiles === 1 ? '' : 's'} of ${name}`);
        } catch (e) { toast(e.message, true); imp.disabled = false; imp.textContent = 'Import…'; }
      };
      const fname = `${name.split(' / ')[0].replace(/[^A-Za-z0-9]+/g, '_')}_picture_${pc.number}.png`;
      return h('figure', { class: 'sfxcard' },
        h('div', { class: 'sfximg' }, h('img', { src: `/gfx/spellsheet/?r=${pc.record}&x=2&v=${v}${pc.kind === 'sprite' ? '' : cq}`, width: pc.w * 2, height: pc.h * 2, alt: `${name}, picture ${pc.number}` })),
        h('figcaption', {},
          h('strong', {}, `Picture ${pc.number}${pc.edited ? ' ✎' : ''}`), h('span', { class: 'sub' }, ` ${pc.label} · ${pc.tiles} tiles`),
          pc.shared.length ? h('p', { class: 'hint' }, `Also used by ${pc.shared.slice(0, 3).join(', ')}${pc.shared.length > 3 ? ` and ${pc.shared.length - 3} more` : ''}: they change too.`) : null,
          h('div', { class: 'sfxbtns' },
            h('a', { class: 'btn btn-line', href: `/gfx/spellsheet/?r=${pc.record}&v=${v}`, download: fname }, 'Download'), imp, fileIn,
            pc.edited ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
              try { await api('spellgfxset', { record: pc.record, png: null }); await after('Back to the game\'s picture (Undo brings yours back)'); } catch (e) { toast(e.message, true); }
            } }, 'Use the game\'s') : null)));
    });
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, name), h('p', { class: 'sub' }, `Effect ${P.spell} · ${P.pictures.length} picture${P.pictures.length === 1 ? '' : 's'}`)),
      h('div', { class: 'sfxhead' }, about, tools, makeBox),
      viewChips,
      P.preview ? h('div', { class: 'sfxpreview' }, h('h3', {}, 'How the pictures are laid out'),
        h('div', { class: 'sfxscroll' }, h('img', { src: `/gfx/spellview/?s=${P.spell}&v=${v}${real ? '&c=1' : ''}`, alt: `${name} laid out on screen` })),
        h('p', { class: 'hint' }, real ? 'The backgrounds this effect builds from its pictures, one screen after another, in the colours the spell sets. In battle they also slide, flash, blend with the scene and cycle their colours.' : 'The backgrounds this effect builds from its pictures, one screen after another. In battle they slide, flash and get recoloured; this shows where each piece ends up.')) : null,
      hasColours ? h('div', { class: 'sfxcolours' }, h('h3', {}, 'Colours'),
        h('p', { class: 'hint' }, 'The colours this spell sets, in the order the game uses them. Click a colour to change it, or shift them all at once with the sliders. Colours that cycle or change every few frames are listed step by step. In the pictures above, colour numbers the spell doesn\'t set show in stand-in colours: in battle they take whatever the scene has there, so draw with the numbers listed here.'),
        shiftBox, setRows) : null,
      stepsBox,
      h('h3', {}, 'Pictures'),
      h('p', { class: 'hint' }, 'Download a picture, paint over it in any paint program, and import it. The downloaded file uses stand-in colours, one for each colour number, so the same picture works whatever colours the spell gives it (change those under Colours). Paint with the colours already in the file; other colours are matched to the nearest one. Transparent pixels show what\'s behind. Keep the size.'),
      h('div', { class: 'sfxgrid' }, cards)));
  }

  // ------------------------------------------------------------ skill animations
  let SA = null;
  async function loadSkills() { SA = await api('skillanims'); }
  async function drawSkillList() {
    if (!SA) { list.replaceChildren(h('p', { class: 'hint' }, 'Reading…')); try { await loadSkills(); } catch (e) { list.replaceChildren(h('p', { class: 'hint' }, e.message)); return; } }
    if (st.skill == null || !SA.skills.some(x => x.skill === st.skill)) st.skill = SA.skills[0]?.skill;
    list.replaceChildren(...SA.skills.map(x => h('button', { 'aria-pressed': String(x.skill === st.skill), onclick: () => { st.skill = x.skill; remember(); drawSkillList(); drawSkillAnim(); } },
      h('span', {}, x.name, x.kind === 'new' ? h('span', { class: 'sfxnew' }, 'new skill') : x.kind === 'engine' && x.effect == null ? h('span', { class: 'sub' }, ' (none yet)') : null),
      h('span', { class: 'sub' }, (x.effect == null ? 'no animation' : (SA.effects.find(e => e[0] === x.effect)?.[1] || `effect ${x.effect}`)) + (x.edited ? ' ✎' : '')))));
  }
  async function drawSkillAnim() {
    if (!SA) { try { await loadSkills(); } catch (e) { detail.replaceChildren(h('div', { class: 'empty' }, e.message)); return; } }
    const x = SA.skills.find(k => k.skill === st.skill) || SA.skills[0];
    if (!x) { detail.replaceChildren(h('div', { class: 'empty' }, 'No skills.')); return; }
    let cols = x.colours.slice(), hue = 0, sat = 1, lit = 0;
    const shown = () => cols.map(c => shiftColour(c, hue, sat, lit));
    const save = async (patch, msg) => {
      try { await api('skillanimset', { skill: x.skill, effect: x.effect, reaction: x.reaction, colours: shown(), ...patch });
        SA = null; await refreshSession(); await loadSkills(); drawSkillList(); drawSkillAnim(); if (msg) toast(msg); } catch (e) { toast(e.message, true); }
    };
    const effSel = h('select', { class: 'in', 'aria-label': 'Animation' },
      x.kind !== 'game' ? h('option', { value: '', selected: x.effect == null }, 'Nothing') : null,
      SA.effects.map(([k, n]) => h('option', { value: k, selected: k === x.effect }, n)));
    effSel.onchange = () => save({ effect: effSel.value === '' ? null : Number(effSel.value) }, 'Animation changed');
    const reaSel = h('select', { class: 'in', 'aria-label': 'Reaction when hit' }, SA.reactions.map(([k, n]) => h('option', { value: k, selected: k === x.reaction }, n)));
    reaSel.onchange = () => save({ reaction: Number(reaSel.value) }, 'Reaction changed');
    const sw = h('div', { class: 'sfxrow' });
    const drawSw = () => sw.replaceChildren(...shown().map((c, i) => {
      const pick = h('input', { type: 'color', value: toHex(c), 'aria-label': `Sparkle colour ${i + 1}` });
      pick.onchange = () => { cols[i] = fromHex(pick.value); hue = 0; sat = 1; lit = 0; save({}, 'Colour changed'); };
      return h('label', { class: 'sfxsw' + (c !== x.game.colours[i] ? ' changed' : ''), style: `--c:${toHex(c)}` }, pick);
    }));
    drawSw();
    const sl = (lab, min, max, val, set) => { const r = h('input', { type: 'range', min, max, value: val, 'aria-label': lab }); r.oninput = () => { set(Number(r.value)); drawSw(); apply.disabled = false; }; return h('label', { class: 'lbl' }, h('span', {}, lab), r); };
    const apply = h('button', { class: 'btn btn-gilt', type: 'button', disabled: true, onclick: () => save({}, 'Colours changed') }, 'Apply colours');
    const makeNew = h('button', { class: 'btn btn-line', type: 'button', disabled: x.effect == null, onclick: async () => {
      try { const res = await api('spelleffect', { new: x.effect, name: `${x.name} sparkle` }); await save({ effect: res.id }, `Made "${x.name} sparkle": its pictures, colours and steps are its own. Edit them under Spell pictures.`); }
      catch (e) { toast(e.message, true); } } }, 'Make it its own sparkle');
    const watchSk = h('button', { class: 'btn btn-gilt', type: 'button', disabled: x.effect == null, title: 'Opens the PC port on a copy of your ROM: the Prologue battle where Gandolf attacks Midir, with this skill activating at the start', onclick: async () => {
      try { await watchJob(await api('skillpreview', { skill: x.skill }), () => toast('The PC port is opening: it plays up to the battle at full speed, then shows the skill activating again and again until you close it.')); }
      catch (e) { toast(e.message, true); } } }, 'Watch in battle');
    const editIt = h('button', { class: 'btn btn-line', type: 'button', disabled: x.effect == null, onclick: () => { st.view = 'spellgfx'; st.spell = x.effect; remember(); drawViewBar(); drawList(); drawDetail(); } }, 'Edit its pictures and steps');
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, x.name), h('p', { class: 'sub' }, x.kind === 'new' ? `Skill ${x.skill} · ${x.effect_kind.replace(/_/g, ' ')}` : `Skill ${x.skill} · the game's`)),
      h('div', { class: 'sfxhead' },
        h('p', { class: 'hint' }, x.kind === 'engine' ? `${x.about}. The game shows nothing for it; pick an animation to give it one.` :
          x.kind === 'new' ? `${x.about}. ${x.borrows ? `Out of the box it shows ${x.borrows}'s sparkle.` : 'Out of the box it shows no animation.'}` :
          `What plays when ${x.name} activates. The colours are the sparkle's own (5 colours); the animation decides the shapes, sounds and timing.`)),
      h('div', { class: 'baredraw' },
        h('div', { class: 'itgrid wide' },
          h('label', { class: 'lbl' }, h('span', {}, 'Animation'), effSel),
          x.defend ? h('label', { class: 'lbl' }, h('span', {}, 'When the hit lands'), reaSel) : null),
        h('h3', {}, 'Sparkle colours', x.edited ? ' ✎' : ''),
        sw,
        h('div', { class: 'sfxsliders' }, sl('Hue', -180, 180, 0, v => { hue = v; }), sl('Saturation', 0, 200, 100, v => { sat = v / 100; }), sl('Brightness', -50, 50, 0, v => { lit = v / 100; })),
        h('div', { class: 'sfxbtns' }, apply, watchSk, makeNew, editIt,
          x.edited ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
            try { await api('skillanimset', { skill: x.skill, reset: true }); SA = null; await refreshSession(); await loadSkills(); drawSkillList(); drawSkillAnim(); toast('Back to the game\'s (Undo brings yours back)'); } catch (e) { toast(e.message, true); } } }, 'Use the game\'s') : null)),
      h('p', { class: 'hint' }, 'A sparkle shared by several skills (Luna\'s is borrowed by most new attack skills) changes for all of them; "Make it its own sparkle" gives this skill a copy whose pictures, colours and steps you can change under Spell pictures. The new skills come from the Skills page (later games\' skills such as Aether, Lethality or Great Shield).')));
  }

  // ------------------------------------------------------------ map battles
  let MB = null;
  const mbPlayers = new Set();
  setInterval(() => { for (const cv of mbPlayers) { if (!cv.isConnected) { mbPlayers.delete(cv); continue; } cv._tick(); } }, 1000 / 60);
  const mbKey = Date.now().toString(36);
  async function loadMb() { MB = await api('mapbattle'); }
  async function drawMbList(q) {
    if (!MB) { list.replaceChildren(h('p', { class: 'hint' }, 'Reading…')); try { await loadMb(); } catch (e) { list.replaceChildren(h('p', { class: 'hint' }, e.message)); return; } }
    if (st.mbcls == null || !MB.classes.some(c => c.c === st.mbcls)) st.mbcls = MB.classes[0]?.c;
    const figName = f => MB.figures[f]?.label || `Figure ${f}`;
    list.replaceChildren(...MB.classes.filter(c => !q || c.name.toLowerCase().includes(q)).map(c =>
      h('button', { 'aria-pressed': String(c.c === st.mbcls), onclick: () => { st.mbcls = c.c; drawMbList(find.value.trim().toLowerCase()); drawMapBattle(); } },
        h('span', {}, c.name), h('span', { class: 'sub' }, (c.figure === c.c ? 'own figure' : figName(c.figure)) + (c.figure !== c.gameFigure || c.women !== c.gameWomen ? ' ✎' : '')))));
  }
  async function drawMapBattle() {
    if (!MB) { try { await loadMb(); } catch (e) { detail.replaceChildren(h('div', { class: 'empty' }, e.message)); return; } }
    const c = MB.classes.find(x => x.c === st.mbcls) || MB.classes[0];
    if (!c) { detail.replaceChildren(h('div', { class: 'empty' }, 'No map battle table in this project.')); return; }
    const army = st.mbarmy || 0;
    const reload = async msg => { MB = null; await refreshSession(); await loadMb(); drawMbList(find.value.trim().toLowerCase()); drawMapBattle(); if (msg) toast(msg); };
    const set = async (patch, msg) => { try { await api('mapbattleset', { class: c.c, ...patch }); await reload(msg); } catch (e) { toast(e.message, true); } };
    const figSel = (key, label) => {
      const sel = h('select', { class: 'in', 'aria-label': label }, MB.figures.map(f => h('option', { value: f.fig, selected: f.fig === c[key] }, `${f.label}${f.fig === c.c ? ' (its own)' : ''}`)));
      sel.onchange = () => set({ [key]: Number(sel.value) }, `${label}: ${MB.figures[Number(sel.value)].label}`);
      return sel;
    };
    const watch = fig => h('button', { class: 'btn btn-gilt', type: 'button', title: 'Opens the PC port on a copy of your ROM: the Prologue fight as a map battle, with Midir shown as this figure',
      onclick: async () => {
        try { await watchJob(await api('mapbattlepreview', { fig }), () => toast('The PC port is opening: it plays up to the fight at full speed, then shows the map battle again and again until you close it.')); }
        catch (e) { toast(e.message, true); } } }, 'Watch a map battle');
    const armyBar = h('div', { class: 'chips', role: 'radiogroup', 'aria-label': 'Colours' }, MB.armies.map((a, i) =>
      h('button', { class: 'chip', role: 'radio', 'aria-checked': String(i === army), onclick: () => { st.mbarmy = i; drawMapBattle(); } }, { player: 'Player', enemy: 'Enemy', ally: 'Ally', other: 'Other', moved: 'Has moved' }[a] || a)));
    const sheetCards = fig => {
      const f = MB.figures[fig];
      return h('div', { class: 'mbsheets' }, f.sheets.map(sh => {
        const file = h('input', { type: 'file', accept: 'image/png,image/*', hidden: true });
        file.onchange = () => { const fl = file.files[0]; file.value = ''; if (fl) importSheet(fig, sh.k, fl); };
        const src = `/gfx/mbsheet/${fig.toString(16).padStart(2, '0')}_${sh.k}`;
        return h('figure', { class: 'mbsheet' },
          h('img', { src: `${src}.png?a=${army}&s=2&c=${sh.ver}-${mbKey}`, width: 256, height: 256, alt: `${f.label}, foe ${sh.dirs.join(' or ')}` }),
          h('figcaption', {}, h('b', {}, `Foe ${sh.dirs.join(' / ')}`), sh.custom ? ' · redrawn' : ''),
          h('div', { class: 'spbtns' },
            h('button', { class: 'btn btn-line', type: 'button', onclick: () => file.click() }, 'Replace…'),
            h('a', { class: 'btn btn-line', href: `${src}.idx.png?c=${sh.ver}-${mbKey}`, download: `mapbattle_${fig.toString(16).padStart(2, '0')}_${sh.k}.png` }, 'Download'),
            sh.custom ? h('button', { class: 'btn btn-line danger', type: 'button', onclick: async () => {
              try { await api('mapbattlesheet', { fig, k: sh.k, reset: true }); await reload('Back to the game\'s sheet'); } catch (e) { toast(e.message, true); } } }, 'Use the original') : null, file));
      }));
    };
    async function importSheet(fig, k, fl) {
      const u = URL.createObjectURL(fl);
      const im = new Image();
      im.onerror = () => { URL.revokeObjectURL(u); toast('That file isn\'t a picture the browser can open.', true); };
      im.onload = async () => {
        URL.revokeObjectURL(u);
        const n = im.width / 128;
        if (!Number.isInteger(n) || n < 1 || n > 6 || im.height !== 128 * n) { toast(`A sheet is 128 × 128 pixels (or 2×, 3×, 4× that); the picture is ${im.width} × ${im.height}.`, true); return; }
        const cv = document.createElement('canvas'); cv.width = 128; cv.height = 128;
        const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false; ctx.drawImage(im, 0, 0, 128, 128);
        try { await api('mapbattlesheet', { fig, k, png: cv.toDataURL('image/png').split(',')[1] }); await reload('Sheet replaced (Ctrl+Z undoes it)'); } catch (e) { toast(e.message, true); }
      };
      im.src = u;
    }
    // the figure's motions, played from its script: pick the way it faces and the weapon it holds
    const moves = h('div', { class: 'mbmoves' }, h('p', { class: 'hint' }, 'Reading…'));
    const DIRS = ['left', 'up-left', 'up', 'up-right', 'right', 'down-right', 'down', 'down-left'];
    (async () => {
      const fig = c.figure, k = st.mbdir ?? 4;
      let P;
      try { P = await api(`mbplayer?fig=${fig}&k=${k}&s=${st.mbsec ?? -1}`); } catch (e) { moves.replaceChildren(h('p', { class: 'hint' }, e.message)); return; }
      const sh = MB.figures[fig].sheets.find(x => x.dirs.includes(DIRS[k]));
      const dirSel = h('select', { class: 'in', 'aria-label': 'Foe is' }, DIRS.map((d, i) => h('option', { value: i, selected: i === k }, d)));
      dirSel.onchange = () => { st.mbdir = Number(dirSel.value); drawMapBattle(); };
      const secSel = h('select', { class: 'in', 'aria-label': 'Weapon' }, P.sections.map(([i, n]) => h('option', { value: i, selected: i === P.s }, n)));
      secSel.onchange = () => { st.mbsec = Number(secSel.value); drawMapBattle(); };
      const img = new Image();
      img.src = `/gfx/mbplay/${fig.toString(16).padStart(2, '0')}_${k}_${P.s}.png?a=${army}&s=3&c=${sh?.ver || 'rom'}-${mbKey}`;
      const S3 = P.cell * 3;
      const cards = P.motions.map(m => {
        const cv = h('canvas', { class: 'mbplay', width: S3, height: S3, role: 'img', 'aria-label': `${MB.figures[fig].label}: ${m.name}` });
        const ctx = cv.getContext('2d');
        let i = 0, left = 0;
        cv._tick = () => {
          if (!img.complete || !img.naturalWidth || !cv.isConnected) return;
          if (left-- > 0) return;
          const [cell, ticks] = m.steps[i];
          ctx.clearRect(0, 0, S3, S3);
          ctx.drawImage(img, cell * S3, 0, S3, S3, 0, 0, S3, S3);
          left = Math.min(40, Math.max(6, ticks));
          i = (i + 1) % m.steps.length;
          if (i === 0) left += 30;
        };
        mbPlayers.add(cv);
        return h('figure', { class: 'mbplayfig' }, cv, h('figcaption', {}, m.name));
      });
      moves.replaceChildren(
        h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'Foe is'), dirSel),
          P.sections.length ? h('label', { class: 'lbl' }, h('span', {}, 'Weapon'), secSel) : null),
        P.motions.length ? h('div', { class: 'mbplays' }, cards) : h('p', { class: 'hint' }, 'This figure has no moves for that.'),
        h('p', { class: 'hint' }, 'Played from the figure\'s own script with an iron weapon of that kind (magic shows no weapon). The game also waits for the other fighter between steps, so its fights run slower. Redrawn sheets show here straight away.'));
    })();
    const edited = c.figure !== c.gameFigure || c.women !== c.gameWomen;
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, c.name), h('p', { class: 'sub' }, `Class ${c.c} · in map battles`)),
      h('div', { class: 'baredraw' },
      h('p', { class: 'hint' }, 'With battle animations off, two little figures fight on the map. Each class shows a figure (most show their own; some have another for women). Any class can show any figure.'),
      h('div', { class: 'itgrid wide' },
        h('label', { class: 'lbl' }, h('span', {}, 'Figure'), figSel('figure', 'Figure')),
        h('label', { class: 'lbl' }, h('span', {}, 'Women show'), figSel('women', 'Women\'s figure'))),
      h('div', { class: 'sfxbtns' }, watch(c.figure), edited ? h('button', { class: 'btn btn-line', type: 'button', onclick: () => set({ reset: true }, 'Back to the game\'s figures') }, 'Use the game\'s') : null),
      h('h3', {}, `How ${MB.figures[c.figure].label} moves`),
      moves,
      h('h3', {}, `Sheets of ${MB.figures[c.figure].label}`),
      h('div', { class: 'spbar' }, h('span', { class: 'sub' }, 'Colours'), armyBar),
      h('p', { class: 'hint' }, 'A figure has a sheet for each way it can face its foe (up-right uses the right sheet, down-left the left one). A sheet is 256 tiles as the game keeps them, 16 across: the figure\'s poses are drawn in 16 × 16 pieces, with weapons and mounts further down. Download one, paint over the pieces in any paint program (same size, the map palette\'s colours) and replace it; Watch a map battle shows the result. A sheet is used by every class that shows this figure.'),
      sheetCards(c.figure),
      c.women !== c.figure ? h('h3', {}, `Sheets of ${MB.figures[c.women].label} (women)`) : null,
      c.women !== c.figure ? sheetCards(c.women) : null)));
  }

  // ------------------------------------------------------------ spell effects on the map
  let MS = null;
  async function loadMs() { MS = await api('mapspells'); }
  async function drawMsList(q) {
    if (!MS) { list.replaceChildren(h('p', { class: 'hint' }, 'Reading…')); try { await loadMs(); } catch (e) { list.replaceChildren(h('p', { class: 'hint' }, e.message)); return; } }
    if (st.msp == null || !MS.spells.some(x => x.spell === st.msp)) st.msp = MS.spells[0]?.spell;
    list.replaceChildren(...MS.spells.filter(x => !q || x.name.toLowerCase().includes(q)).map(x =>
      h('button', { 'aria-pressed': String(x.spell === st.msp), onclick: () => { st.msp = x.spell; drawMsList(find.value.trim().toLowerCase()); drawMapSpell(); } },
        h('span', {}, x.name), h('span', { class: 'sub' }, (x.sprite ? `colours ${x.palette + 1}` : 'background only') + (x.custom || x.bgCustom || (x.sprite && x.palette !== x.gamePalette) ? ' ✎' : '')))));
  }
  async function drawMapSpell() {
    if (!MS) { try { await loadMs(); } catch (e) { detail.replaceChildren(h('div', { class: 'empty' }, e.message)); return; } }
    const x = MS.spells.find(k => k.spell === st.msp) || MS.spells[0];
    if (!x) { detail.replaceChildren(h('div', { class: 'empty' }, 'No spells with a map effect.')); return; }
    const P = x.sprite ? MS.palettes[x.palette] : { colours: [], game: [], users: [] };
    const reload = async msg => { MS = null; await refreshSession(); await loadMs(); drawMsList(find.value.trim().toLowerCase()); drawMapSpell(); if (msg) toast(msg); };
    const call = async (body, msg) => { try { await api('mapspellset', body); await reload(msg); } catch (e) { toast(e.message, true); } };
    const ver = `${x.ver}-${P.colours.map(c => c.toString(16)).join('')}-${mbKey}`;
    const file = h('input', { type: 'file', accept: 'image/png,image/*', hidden: true });
    file.onchange = () => { const fl = file.files[0]; file.value = ''; if (fl) importFx(fl); };
    async function importFx(fl) {
      const u = URL.createObjectURL(fl);
      const im = new Image();
      im.onerror = () => { URL.revokeObjectURL(u); toast('That file isn\'t a picture the browser can open.', true); };
      im.onload = async () => {
        URL.revokeObjectURL(u);
        const n = im.width / 128;
        if (!Number.isInteger(n) || n < 1 || n > 6 || im.height !== 16 * n) { toast(`A map spell sheet is 128 × 16 pixels (or 2×, 3×, 4× that); the picture is ${im.width} × ${im.height}.`, true); return; }
        const cv = document.createElement('canvas'); cv.width = 128; cv.height = 16;
        const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false; ctx.drawImage(im, 0, 0, 128, 16);
        try { await api('mapspellsheet', { spell: x.spell, png: cv.toDataURL('image/png').split(',')[1] }); await reload(`${x.name}: new sheet (Ctrl+Z undoes it)`); } catch (e) { toast(e.message, true); }
      };
      im.src = u;
    }
    let cols = P.colours.slice(), hue = 0, sat = 1, lit = 0;
    const shown = () => cols.map((c, i) => i ? shiftColour(c, hue, sat, lit) : c);
    const sw = h('div', { class: 'sfxrow' });
    const apply = h('button', { class: 'btn btn-gilt', type: 'button', disabled: true, onclick: () => call({ palette: x.palette, colours: shown() }, 'Colours changed') }, 'Apply colours');
    const drawSw = () => sw.replaceChildren(...shown().slice(1).map((c, j) => {
      const pick = h('input', { type: 'color', value: toHex(c), 'aria-label': `Colour ${j + 1}` });
      pick.onchange = () => { cols = shown(); cols[j + 1] = fromHex(pick.value); hue = 0; sat = 1; lit = 0; call({ palette: x.palette, colours: cols }, 'Colour changed'); };
      return h('label', { class: 'sfxsw' + (c !== P.game[j + 1] ? ' changed' : ''), style: `--c:${toHex(c)}`, title: `Colour ${j + 1}` }, pick);
    }));
    drawSw();
    const sl = (lab, min, max, val, set) => { const r = h('input', { type: 'range', min, max, value: val, 'aria-label': lab }); r.oninput = () => { set(Number(r.value)); drawSw(); apply.disabled = false; }; return h('label', { class: 'lbl' }, h('span', {}, lab), r); };
    const palSel = h('select', { class: 'in', 'aria-label': 'Colours' }, MS.palettes.map(pp => h('option', { value: pp.p, selected: pp.p === x.palette }, `Colours ${pp.p + 1}${pp.users.length ? ' — ' + pp.users.slice(0, 4).join(', ') + (pp.users.length > 4 ? '…' : '') : ''}`)));
    palSel.onchange = () => call({ spell: x.spell, palette: Number(palSel.value) }, `${x.name} uses colours ${Number(palSel.value) + 1}`);
    const watch = h('button', { class: 'btn btn-gilt', type: 'button', disabled: !x.attack, title: x.attack ? 'Opens the PC port on a copy of your ROM: the Prologue fight as a map battle, with Midir casting this' : 'Staves are used, not fought with, so this preview can\'t show them',
      onclick: async () => { try { await watchJob(await api('mapspellpreview', { spell: x.spell }), () => toast('The PC port is opening: it plays up to the fight at full speed, then shows the map battle again and again until you close it.')); } catch (e) { toast(e.message, true); } } }, 'Watch on the map');
    const bgFile = h('input', { type: 'file', accept: 'image/png,image/*', hidden: true });
    bgFile.onchange = () => { const fl = bgFile.files[0]; bgFile.value = ''; if (fl) importBg(fl); };
    async function importBg(fl) {
      const u = URL.createObjectURL(fl);
      const im = new Image();
      im.onerror = () => { URL.revokeObjectURL(u); toast('That file isn\'t a picture the browser can open.', true); };
      im.onload = async () => {
        URL.revokeObjectURL(u);
        const n = im.width / 256;
        if (!Number.isInteger(n) || n < 1 || n > 4 || im.height !== 256 * n) { toast(`A background is 256 × 256 pixels (or 2×, 3× that); the picture is ${im.width} × ${im.height}.`, true); return; }
        const cv = document.createElement('canvas'); cv.width = 256; cv.height = 256;
        const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false; ctx.drawImage(im, 0, 0, 256, 256);
        try { await api('mapspellbg', { spell: x.spell, png: cv.toDataURL('image/png').split(',')[1] }); await reload(`${x.name}: new background (Ctrl+Z undoes it)`); } catch (e) { toast(e.message, true); }
      };
      im.src = u;
    }
    const BC = x.bgColours || { kind: null };
    const bgVer = `${x.bgVer}-${(BC.rows || []).flat().map(k => k.c.toString(16)).join('').slice(0, 400)}-${mbKey}`;
    const colourBox = h('div', { class: 'mbcolours' });
    if (BC.kind) {
      const rows = BC.rows.map((row, ri) => h('div', { class: 'sfxrow' }, row.map((k, i) => {
        const pick = h('input', { type: 'color', value: toHex(k.c), 'aria-label': BC.kind === 'block' ? `Palette ${6 + ri} colour ${9 + i}` : `Colour ${i + 1} of list ${ri + 1}` });
        pick.onchange = async () => {
          try {
            if (BC.kind === 'lists') await api('mapspellcolour', { address: k.a, colour: fromHex(pick.value) });
            else { const all = BC.rows.flat().map(z => z.c); all[ri * 7 + i] = fromHex(pick.value); await api('mapspellcolour', { spell: x.spell, colours: all }); }
            await reload('Colour changed');
          } catch (e) { toast(e.message, true); }
        };
        return h('label', { class: 'sfxsw' + (k.c !== k.game ? ' changed' : ''), style: `--c:${toHex(k.c)}` }, pick);
      })));
      const edited = BC.rows.flat().some(k => k.c !== k.game);
      colourBox.append(h('h4', {}, 'Colours while it plays'),
        h('p', { class: 'hint' }, BC.kind === 'block' ? 'The background\'s colours 9-15 (top: palette 6, bottom: palette 7). Click one to change it.' :
          `${x.name} cycles its background through ${BC.rows.length > 1 ? 'these lists, 7 at a time or a few steps further each frame' : 'this list'}. Click a colour to change it${BC.shared.length ? `; ${BC.shared.join(', ')} use${BC.shared.length === 1 ? 's' : ''} the same colours` : ''}. The picture above shows the first ones.`),
        ...rows,
        edited ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => { try { await api('mapspellcolour', { spell: x.spell, reset: true }); await reload('Back to the game\'s colours'); } catch (e) { toast(e.message, true); } } }, 'Use the game\'s colours') : null);
    } else {
      colourBox.append(h('p', { class: 'hint' }, x.attack ? '' : 'Staves\' background colours come from code the kit hasn\'t traced yet; the colours shown are close, not exact.'));
    }
    const bgSection = [
      h('h3', {}, 'Background'),
      h('p', { class: 'hint' }, `The big picture drawn over the map while ${x.name} plays (the map darkens, then this moves across it).${x.sprite ? '' : ' This spell has no flying piece, only this.'}`),
      h('img', { class: 'mbg', src: `/gfx/mapbg/${x.spell}.png?s=2&c=${bgVer}`, width: 512, height: 512, alt: `${x.name}: background effect` }),
      h('div', { class: 'sfxbtns' },
        h('button', { class: 'btn btn-line', type: 'button', onclick: () => bgFile.click() }, 'Replace…'),
        h('a', { class: 'btn btn-line', href: `/gfx/mapbg/${x.spell}.png?c=${bgVer}`, download: `mapspell_bg_${x.spell}.png` }, 'Download'),
        x.bgCustom ? h('button', { class: 'btn btn-line danger', type: 'button', onclick: async () => { try { await api('mapspellbg', { spell: x.spell, reset: true }); await reload('Back to the game\'s background'); } catch (e) { toast(e.message, true); } } }, 'Use the original') : null,
        x.sprite ? null : watch, bgFile),
      h('p', { class: 'hint' }, 'The picture is 256 × 256 pixels, built from up to 128 different 8 × 8 tiles (mirrored tiles count once). Each 8 × 8 square keeps the colours the game gives it there; paint with the colours in the downloaded picture. Spells that share a background (Wind, Heal, Warp…) each get their own when you replace one.'),
      colourBox];
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, x.name), h('p', { class: 'sub' }, `Map spell ${x.spell} · item ${x.item}`)),
      !x.sprite ? h('div', { class: 'baredraw' }, ...bgSection) :
      h('div', { class: 'baredraw' },
        h('p', { class: 'hint' }, `With battle animations off, ${x.name} shows these pieces on the map (the fireball, bolt or sparkle that flies to the target). Each spell has its own sheet; colours are one of six sets that several spells share.`),
        h('img', { class: 'msheet', src: `/gfx/mapfx/${x.spell}.png?s=4&c=${ver}`, width: 512, height: 64, alt: `${x.name} on the map` }),
        h('div', { class: 'sfxbtns' },
          h('button', { class: 'btn btn-line', type: 'button', onclick: () => file.click() }, 'Replace…'),
          h('a', { class: 'btn btn-line', href: `/gfx/mapfx/${x.spell}.idx.png?c=${ver}`, download: `mapspell_${x.spell}.png` }, 'Download'),
          x.custom ? h('button', { class: 'btn btn-line danger', type: 'button', onclick: async () => { try { await api('mapspellsheet', { spell: x.spell, reset: true }); await reload('Back to the game\'s sheet'); } catch (e) { toast(e.message, true); } } }, 'Use the original') : null,
          watch, file),
        h('p', { class: 'hint' }, 'A sheet is 128 × 16 pixels: 32 tiles as the game keeps them, the pieces in 16 × 16 squares (2× to 4× bigger works too). Paint with the spell\'s colours below; other colours become the nearest one.' + (x.attack ? '' : ' Staves show their effect when used on the map; Watch on the map only works for tomes.')),
        h('h3', {}, 'Colours'),
        h('label', { class: 'lbl' }, h('span', {}, 'This spell uses'), palSel),
        sw,
        h('div', { class: 'sfxsliders' }, sl('Hue', -180, 180, 0, v => { hue = v; }), sl('Saturation', 0, 200, 100, v => { sat = v / 100; }), sl('Brightness', -50, 50, 0, v => { lit = v / 100; })),
        h('div', { class: 'sfxbtns' }, apply,
          P.colours.some((c, i) => c !== P.game[i]) ? h('button', { class: 'btn btn-line', type: 'button', onclick: () => call({ palette: x.palette, reset: true }, 'Back to the game\'s colours') }, 'Use the game\'s colours') : null),
        h('p', { class: 'hint' }, `Colours ${x.palette + 1} are shared by ${P.users.join(', ')}: changing them changes all of these. Colours 1 (Return, Restore, Sleep) are all black in the ROM; the game fades them in itself.`),
        ...bgSection)));
  }

  function drawDetail() {
    if (st.view === 'mapspells') { drawMapSpell(); return; }
    if (st.view === 'mapbattle') { drawMapBattle(); return; }
    if (st.view === 'skillanims') { drawSkillAnim(); return; }
    if (st.view === 'spellgfx') { drawPictures(); return; }
    if (st.view === 'spells') { drawSpells(); return; }
    const c = classes().find(x => x.id === st.cls) || classes()[0];
    if (!c) { detail.replaceChildren(h('div', { class: 'empty' }, 'No battle animation table in this project.')); return; }
    st.cls = c.id;
    const r = c.rows.find(x => x.row === st.row) || c.rows[0];
    st.row = r.row; remember();
    const tabs = h('div', { class: 'chips', role: 'tablist', 'aria-label': 'Weapon' }, c.rows.map(x =>
      h('button', { class: 'chip', role: 'tab', 'aria-selected': String(x === r), onclick: () => { st.row = x.row; st.item = null; drawDetail(); } }, rowLabel(x), x._redrawn ? ' ✎' : '')));
    const fields = h('div', { class: 'itgrid wide' }, FIELDS.map(([f, label, hint]) => {
      const inp = h('input', { class: 'in num', value: r[f], inputmode: 'numeric', 'aria-label': label, title: hint });
      inp.onchange = () => setCells([{ field: f, value: inp.value.trim() }], r, inp);
      const others = usedBy(f, r[f]).filter(n => n !== r._class);
      return h('label', { class: 'lbl' }, h('span', {}, label), inp,
        h('span', { class: 'hint baused' }, others.length ? `Also used by ${others.slice(0, 4).join(', ')}${others.length > 4 ? ` and ${others.length - 4} more` : ''}` : 'Only this class'));
    }));
    // copy another class's look
    const from = h('select', { class: 'in', 'aria-label': 'Class to copy from' }, h('option', { value: '' }, 'Choose a class…'),
      classes().filter(x => x.id !== c.id).map(x => h('option', { value: x.id }, x.name)));
    const copyBtn = h('button', { class: 'btn btn-line', type: 'button' }, 'Use its look');
    copyBtn.onclick = () => {
      const o = classes().find(x => String(x.id) === from.value);
      if (!o) { toast('Choose a class to copy from.', true); return; }
      const m = o.rows.find(x => x.weapon === r.weapon && x.gender === r.gender) || o.rows.find(x => x.weapon === r.weapon) || o.rows[0];
      setCells(FIELDS.map(([f]) => ({ field: f, value: m[f] })), r, null, `${r._class} (${rowLabel(r)}) now looks like ${o.name} (${rowLabel(m)})`);
    };
    // redraw frames
    const fileIn = h('input', { type: 'file', accept: '.png,image/png', hidden: true });
    const every = h('input', { type: 'checkbox' });
    const drawUrl = `/gfx/battledraw/?row=${r.row}&v=${Date.now()}`;
    const importBtn = h('button', { class: 'btn btn-gilt', type: 'button', onclick: () => fileIn.click() }, 'Import drawn frames…');
    fileIn.onchange = async () => {
      const f = fileIn.files[0]; fileIn.value = '';
      if (!f) return;
      const buf = new Uint8Array(await f.arrayBuffer());
      let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      importBtn.disabled = true; importBtn.textContent = 'Importing…';
      try {
        const res = await api('battleimport', { row: Number(r.row), png: btoa(bin), every: every.checked });
        D = await api('battleanims'); await refreshSession(); drawDetail();
        toast(`Redrew frame${res.changed.length === 1 ? '' : 's'} ${res.changed.join(', ')} (${res.tiles} tiles) for ${res.rows} row${res.rows === 1 ? '' : 's'}`);
      } catch (e) { toast(e.message, true); importBtn.disabled = false; importBtn.textContent = 'Import drawn frames…'; }
    };
    const resetBtn = r._redrawn ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
      try { await api('battlereset', { row: Number(r.row) }); D = await api('battleanims'); await refreshSession(); drawDetail(); toast('Back to the game\'s drawings (Undo brings yours back)'); }
      catch (e) { toast(e.message, true); }
    } }, 'Use the game\'s animation') : null;
    const redraw = h('div', { class: 'baredraw' },
      h('h3', {}, 'Redraw frames'),
      h('p', { class: 'hint' }, r._redrawn ? 'This row uses your drawings. Download them, change more, and import again.' :
        'Download the frames, paint over them in any paint program, then import the PNG.'),
      h('ol', { class: 'basteps' },
        h('li', {}, h('a', { href: drawUrl, download: `${(r._class || 'class').replace(/[^A-Za-z0-9]+/g, '_')}_${weaponName(r)}_frames.png` }, 'Download frames to draw on'),
          ': the body and rider of every frame, side by side, with the two palettes as swatches along the top. The weapon and the shadow aren\'t in it; they stay as they are.'),
        h('li', {}, 'Paint with the swatch colours only and keep the picture\'s size. Transparent stays empty. Each 8×8 square of a frame may use both palettes; frames you don\'t touch stay exactly as they were.'),
        h('li', {}, importBtn, ' ', h('label', { class: 'bacheck' }, every, ` Every row that looks like this (${D.rows.filter(x => ['anim', 'body', 'upper', 'palette'].every(k => x[k] === r[k])).length})`), fileIn, ' ', resetBtn)),
      h('p', { class: 'hint' }, 'Imported drawings become a new animation and body graphics just for the rows you choose, so other classes that shared the old ones don\'t change. A frame can use up to 64 tiles of 8×8.'));
    let pl = null;
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, c.name), h('p', { class: 'sub' }, `Row ${r.row} of the game's table · class ${c.id}`)),
      tabs, (pl = player(r)), motionEditor(r), redraw,
      h('h3', {}, 'What it uses'), fields,
      h('div', { class: 'bacopy' }, h('span', {}, `Look like another class (with ${weaponName(r)}):`), from, copyBtn),
      h('p', { class: 'hint' }, 'The game picks a row by class, weapon kind, gender and (for a few) the character. A class with no row for a weapon uses its first row. Named characters such as bosses can have their own colours on top of the palette shown here. Editing here changes which animation, drawings and colours are used; new drawings and new animations come in a later version.')));
  }

  // ------------------------------------------------------------ motion editor
  function motionEditor(r) {
    const box = h('div', { class: 'baredraw bamotion' });
    let M = null, steps = null, dirty = false;
    const every = h('input', { type: 'checkbox' });
    const hex = n => `$${n.toString(16).toUpperCase().padStart(2, '0')}`;
    async function load() {
      M = await api(`battlemotions?row=${r.row}`);
      if (st.motion >= M.motions.length) st.motion = 0;
      steps = M.motions[st.motion].map(x => [...x]); dirty = false; st.override = null;
      draw();
    }
    function preview() { st.override = { motion: st.motion, steps }; detail.querySelector('.baplayer')?._replay?.(); }
    function draw() {
      const cmds = M.commands;
      const name = c => (cmds[c] || [hex(c)])[0];
      const sel = h('select', { class: 'in', 'aria-label': 'Motion to edit' }, M.motions.map((m, i) =>
        h('option', { value: i, selected: i === st.motion }, `Motion ${i}${M.edited.includes(i) ? ' (changed)' : ''}`)));
      sel.onchange = () => {
        if (dirty && !confirm('Drop the unsaved changes to this motion?')) { sel.value = st.motion; return; }
        const ms = detail.querySelector('select[aria-label="Motion"]');
        if (ms && ms.options.length > Number(sel.value)) { ms.value = sel.value; ms.dispatchEvent(new Event('change')); }
        else { st.motion = Number(sel.value); load(); }
      };
      const list = h('ol', { class: 'basteplist' }, steps.map(([c, v], i) => {
        const isFrame = c < 0xE7;
        const move = d => () => { const j = i + d; if (j < 0 || j >= steps.length) return; [steps[i], steps[j]] = [steps[j], steps[i]]; dirty = true; draw(); preview(); };
        const num = (val, lo, hi, label, set) => { const inp = h('input', { class: 'in num', value: val, inputmode: 'numeric', 'aria-label': label }); inp.onchange = () => { const n = Number(inp.value); if (!Number.isInteger(n) || n < lo || n > hi) { inp.classList.add('bad'); toast(`${label}: ${lo} to ${hi}.`, true); return; } set(n); dirty = true; draw(); preview(); }; return inp; };
        const body = isFrame
          ? [h('span', { class: 'baslabel' }, 'Frame'), num(c, 0, M.frames - 1, 'Frame', n => { steps[i][0] = n; }), h('span', {}, 'for'), num(v, 0, 255, 'Time (1/60 s)', n => { steps[i][1] = n; }), h('span', { class: 'hint' }, '/60 s')]
          : [h('span', { class: 'baslabel', title: (cmds[c] || [])[2] || '' }, name(c)), (cmds[c] || [])[1] ? num(v, 0, 255, name(c), n => { steps[i][1] = n; }) : null, h('span', { class: 'hint' }, (cmds[c] || [])[2] || '')];
        return h('li', { class: 'bastep' + (isFrame ? '' : ' cmd') }, ...body.filter(Boolean),
          h('span', { class: 'bastepbtns' }, h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Move step ${i + 1} up`, onclick: move(-1) }, '↑'),
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Move step ${i + 1} down`, onclick: move(1) }, '↓'),
            h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Remove step ${i + 1}`, onclick: () => { steps.splice(i, 1); dirty = true; draw(); preview(); } }, '✕')));
      }));
      const add = (label, c, v) => h('button', { class: 'btn btn-line', type: 'button', onclick: () => {
        const at = steps.findIndex(x => [0xFE, 0xFD, 0xFC, 0xF1].includes(x[0]));
        steps.splice(at < 0 ? steps.length : at, 0, [c, v]); dirty = true; draw(); preview();
      } }, label);
      const save = h('button', { class: 'btn btn-gilt', type: 'button', disabled: !dirty }, 'Save motion');
      save.onclick = async () => {
        try { await api('battlemotion', { row: Number(r.row), motion: st.motion, steps, every: every.checked }); await afterEdit(`Motion ${st.motion} saved`); }
        catch (e) { toast(e.message, true); }
      };
      const revert = h('button', { class: 'btn btn-line', type: 'button', disabled: !dirty, onclick: () => load() }, 'Undo these changes');
      const restore = M.edited.includes(st.motion) ? h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
        try { await api('battlemotion', { row: Number(r.row), motion: st.motion, steps: null }); await afterEdit(`Motion ${st.motion} is the game's again`); } catch (e) { toast(e.message, true); }
      } }, 'Use the game\'s motion') : null;
      const src = h('input', { class: 'in num', value: '0', inputmode: 'numeric', 'aria-label': 'Frame to copy' });
      const addFrame = h('button', { class: 'btn btn-line', type: 'button', onclick: async () => {
        try { const res = await api('battleframe', { row: Number(r.row), copy: Number(src.value), every: every.checked }); await afterEdit(`Added frame ${M.frames} (a copy of frame ${src.value}); redraw it with Redraw frames below`); }
        catch (e) { toast(e.message, true); }
      } }, 'Add frame');
      box.replaceChildren(h('h3', {}, 'Edit motions'),
        h('p', { class: 'hint' }, 'A motion is a list of steps the game plays: frames with how long they show, and commands. The player above shows your changes before you save. The fighter standing still is motion 0, which the game doesn\'t time, so a standing loop won\'t move in battle.'),
        h('div', { class: 'bamhead' }, h('label', { class: 'lbl' }, h('span', {}, 'Motion'), sel), h('span', { class: 'hint' }, `${M.frames} frames (${M.baseFrames} from the game)`)),
        list,
        h('div', { class: 'bacbtns' }, add('+ Frame', 0, 8), add('+ Wait', 0xFA, 8), add('+ Signal', 0xF7, 0), add('+ Wait for signal', 0xF4, 0), add('+ Go back', 0xFB, 1)),
        h('div', { class: 'bacbtns' }, save, revert, restore, h('label', { class: 'bacheck' }, every, ' Every row that looks like this')),
        h('div', { class: 'bacbtns baaddframe' }, h('span', {}, 'New frame: a copy of frame'), src, addFrame));
    }
    async function afterEdit(msg) { D = await api('battleanims'); await refreshSession(); st.override = null; drawDetail(); toast(msg); }
    box._reload = () => load();
    load().catch(e => box.replaceChildren(h('p', { class: 'hint' }, e.message)));
    return box;
  }

  async function setCells(changes, r, inp, msg) {
    try {
      await api('setmany', { changes: changes.map(ch => ({ table: 'battle_anims', row: Number(r.row), field: ch.field, value: String(ch.value) })) });
      D = await api('battleanims'); await refreshSession();
      drawDetail(); if (msg) toast(msg);
    } catch (e) { if (inp) inp.classList.add('bad'); toast(e.message, true); }
  }

  drawList(); drawDetail();
  list.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: 'center' });
  return {
    async refresh(change) {
      if (!change || change.tables?.includes('map_battle') || change.files?.some(f => f.startsWith('mapbattle/'))) MB = null;
      if (!change || change.tables?.some(t => t.startsWith('map_spell') || t === 'map_palettes' || t === 'map_colour_words') || change.files?.some(f => f.startsWith('mapfx/'))) MS = null;
      if (!change || change.tables?.includes('battle_anims') || change.tables?.includes('spells') || change.tables?.includes('map_battle') || change.tables?.includes('map_spells') || change.tables?.includes('map_palettes') || change.files?.length) { D = await api('battleanims'); drawList(); drawDetail(); }
    },
  };
}
