// Battle animations: which animation, body, upper body and palette each class shows in battle (per
// weapon kind, gender and a few characters), with a player for every motion the animation has.
import { api, h, toast, refreshSession } from '../app.js';

const st = { cls: null, row: null, motion: 1, speed: 1, mirror: false, item: null, playing: true, override: null };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-battle') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-battle', JSON.stringify({ cls: st.cls, row: st.row, motion: st.motion, speed: st.speed, mirror: st.mirror })); } catch (e) { /* none */ } };
const FIELDS = [['anim', 'Animation', 'Moves and frames'], ['body', 'Body graphics', 'The frames\' drawings'],
  ['upper', 'Upper body', 'Rider, torso and head tiles'], ['palette', 'Palette', 'Colours']];
const SCALE = 3;

export async function battlePage(root) {
  let D = await api('battleanims');
  const list = h('div', { class: 'list' });
  const detail = h('div', { class: 'sheet-wrap' });
  const find = h('input', { class: 'in', type: 'search', placeholder: 'Find a class', 'aria-label': 'Find a class' });
  root.append(h('div', { class: 'split' },
    h('div', { class: 'roster' }, h('div', { class: 'roster-tools' }, find,
      h('p', { class: 'hint' }, 'What each class looks like in battle, for each weapon it can use.')), list),
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
  function drawDetail() {
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
      if (!change || change.tables?.includes('battle_anims')) { D = await api('battleanims'); drawList(); drawDetail(); }
    },
  };
}
