// Battle animations: which animation, body, upper body and palette each class shows in battle (per
// weapon kind, gender and a few characters), with a player for every motion the animation has.
import { api, h, toast, refreshSession } from '../app.js';

const st = { cls: null, row: null, motion: 1, speed: 1, mirror: false, item: null, playing: true };
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

    function build() {
      const m = info.motions[st.motion] || [];
      seq = []; const stack = [];
      for (let i = 0; i < m.length && seq.length < 400; i++) {
        const [c, v] = m[i];
        if (c === 0xEF) stack.push({ at: seq.length, n: v });
        else if (c === 0xEE) { const s = stack.pop(); if (s) { const part = seq.slice(s.at); for (let k = 1; k < Math.max(1, s.n); k++) seq.push(...part); } }
        else if (c === 0xFE || c === 0xFF) break;
        else if (c < info.frames) seq.push([c, Math.max(1, v)]);
      }
      if (!seq.length) seq = [[0, 30]];
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
    motionSel.onchange = () => { st.motion = Number(motionSel.value); remember(); build(); draw(); };
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
      h('button', { class: 'chip', role: 'tab', 'aria-selected': String(x === r), onclick: () => { st.row = x.row; st.item = null; drawDetail(); } }, rowLabel(x))));
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
    detail.replaceChildren(h('div', { class: 'sheet basheet' },
      h('div', { class: 'sheet-head' }, h('h2', {}, c.name), h('p', { class: 'sub' }, `Row ${r.row} of the game's table · class ${c.id}`)),
      tabs, player(r),
      h('h3', {}, 'What it uses'), fields,
      h('div', { class: 'bacopy' }, h('span', {}, `Look like another class (with ${weaponName(r)}):`), from, copyBtn),
      h('p', { class: 'hint' }, 'The game picks a row by class, weapon kind, gender and (for a few) the character. A class with no row for a weapon uses its first row. Named characters such as bosses can have their own colours on top of the palette shown here. Editing here changes which animation, drawings and colours are used; new drawings and new animations come in a later version.')));
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
