// Portraits: every face the game can show, who uses it, and replacing one with your own picture
// (any image: it is fitted to 48x64 and reduced to the 15 colours a portrait can have).
import { api, h, toast, refreshSession } from '../app.js';

const st = { sel: 0, q: '', k: Date.now().toString(36) };  // k: new for each editor run (another ROM)
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-portraits') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-portraits', JSON.stringify({ sel: st.sel, q: st.q })); } catch (e) { /* none */ } };

export function showPortrait(n) { st.sel = n; remember(); }

export async function portraitsPage(root) {
  let P = (await api('portraits')).portraits;
  const search = h('input', { class: 'search', type: 'search', placeholder: 'Find by name or number', 'aria-label': 'Find a portrait', value: st.q });
  const onlyMine = h('input', { type: 'checkbox' });
  const grid = h('div', { class: 'ptgrid', role: 'listbox', 'aria-label': 'Portraits' });
  const detail = h('div', { class: 'ptdetail' });
  root.append(h('div', { class: 'ptpage' },
    h('div', { class: 'ptside' }, h('div', { class: 'pttools' }, search, h('label', { class: 'pick-check' }, onlyMine, 'Only replaced ones')), grid),
    detail));
  search.oninput = () => { st.q = search.value; remember(); drawGrid(); };
  onlyMine.onchange = () => drawGrid();

  const ver = n => P.find(x => x.n === n)?.ver || 'rom';
  const img = (n, s) => `/gfx/portrait/${n}.png?s=${s}&c=${ver(n)}-${st.k}`;

  function drawGrid() {
    const q = st.q.trim().toLowerCase();
    grid.replaceChildren(...P.filter(p => (!onlyMine.checked || p.custom) &&
      (!q || String(p.n) === q || p.users.some(u => u.toLowerCase().includes(q)))).map(p => {
      const b = h('button', { class: 'ptcell', role: 'option', 'aria-selected': String(p.n === st.sel), title: `${p.n}${p.users.length ? ': ' + p.users.join(', ') : ''}`,
        onclick: () => { st.sel = p.n; remember(); drawGrid(); drawDetail(); } },
      h('img', { src: img(p.n, 1), alt: '', loading: 'lazy', width: 48, height: 64 }),
      h('span', { class: 'ptnum' }, p.n), p.custom ? h('span', { class: 'ptmine', title: 'Replaced in this project' }, '●') : null,
      h('span', { class: 'ptname' }, p.users[0] || ''));
      return b;
    }));
  }

  function drawDetail() {
    detail.replaceChildren();
    const p = P.find(x => x.n === st.sel);
    if (!p) { detail.append(h('div', { class: 'empty' }, 'Pick a portrait.')); return; }
    const big = h('img', { class: 'ptbig', src: img(p.n, 4), alt: `Portrait ${p.n}`, width: 192, height: 256 });
    const talk = h('canvas', { class: 'pttalk', width: 48, height: 64, style: 'width:96px;height:128px', 'aria-label': 'Talking preview' });
    animate(talk, p.n);
    const file = h('input', { type: 'file', accept: 'image/*', hidden: true });
    const replace = h('button', { class: 'btn btn-gilt', onclick: () => file.click() }, 'Replace with a picture…');
    const download = h('a', { class: 'btn btn-line', href: `/gfx/portrait/sheet/${p.n}.png?s=1&c=${ver(p.n)}-${st.k}`, download: `portrait_${String(p.n).padStart(3, '0')}.png` }, 'Download PNG');
    const reset = p.custom ? h('button', { class: 'btn btn-line danger', onclick: async () => {
      try { await api('portrait', { n: p.n, reset: true }); await changed('Back to the game\'s own picture'); } catch (e) { toast(e.message, true); }
    } }, 'Use the original') : null;
    file.onchange = async () => {
      const f = file.files[0]; file.value = '';
      if (f) importDialog(p, f);
    };
    detail.append(h('article', { class: 'sheet ptsheet' },
      h('div', { class: 'ptsheet-head' }, h('h2', {}, `Portrait ${p.n}`), p.custom ? h('span', { class: 'chip ptchip' }, 'Replaced in this project') : null),
      h('div', { class: 'ptshow' }, big, h('div', { class: 'ptside2' },
        h('div', { class: 'ptlabel' }, 'Talking'), talk,
        h('div', { class: 'ptlabel' }, 'Used by'),
        p.users.length ? h('ul', { class: 'ptusers' }, p.users.map(u => h('li', {}, u))) : h('p', { class: 'hint' }, 'Nobody in the unit tables (a scene may still show it).'))),
      h('div', { class: 'ptactions' }, replace, download, reset, file),
      h('p', { class: 'hint' }, 'Any picture works: it is fitted to 48 × 64 and reduced to 15 colours. Transparent parts show the map behind the face. ',
        'For full control, edit the downloaded PNG (80 × 64: the face, and two talking-mouth frames at the right) and replace with it.')));
  }

  async function changed(msg) {
    P = (await api('portraits')).portraits;
    await refreshSession(); drawGrid(); drawDetail(); toast(msg);
  }

  // ------------------------------------------------------------ talking preview: frames over the mouth
  function animate(cv, n) {
    const im = new Image();
    im.onload = () => {
      const ctx = cv.getContext('2d');
      let f = 0, timer = null;
      const draw = () => {
        if (!cv.isConnected && f > 0) { clearInterval(timer); return; }
        ctx.clearRect(0, 0, 48, 64);
        ctx.drawImage(im, 0, 0, 48, 64, 0, 0, 48, 64);
        if (f % 4 === 1) ctx.drawImage(im, 48, 0, 32, 16, 0, 32, 32, 16);
        if (f % 4 === 2) ctx.drawImage(im, 48, 16, 32, 16, 0, 32, 32, 16);
        if (f % 4 === 3) ctx.drawImage(im, 48, 0, 32, 16, 0, 32, 32, 16);
        f++;
      };
      draw(); timer = setInterval(draw, 160);
    };
    im.src = `/gfx/portrait/sheet/${n}.png?s=1&c=${ver(n)}-${st.k}`;
  }

  // ------------------------------------------------------------ import
  function importDialog(p, file) {
    const url = URL.createObjectURL(file);
    const src = new Image();
    src.onerror = () => { URL.revokeObjectURL(url); toast('That file isn\'t a picture the browser can open.', true); };
    src.onload = () => {
      URL.revokeObjectURL(url);
      const exact = (src.width === 80 || src.width === 48) && src.height === 64;
      let fit = exact ? 'exact' : 'cover', keepBg = false;
      const out = h('canvas', { class: 'ptprev', width: 48, height: 64 });
      const before = h('img', { class: 'ptprev', src: img(p.n, 1), alt: 'Now' });
      const info = h('p', { class: 'hint' });
      const fitSel = h('select', { class: 'in', 'aria-label': 'Fit' },
        exact ? h('option', { value: 'exact' }, src.width === 80 ? 'As is (face + talking frames)' : 'As is (48 × 64)') : null,
        h('option', { value: 'cover' }, 'Fill the frame (crop the edges)'), h('option', { value: 'contain' }, 'Fit inside the frame'));
      const bgBox = h('input', { type: 'checkbox' });
      let result = null;
      const redo = () => {
        fit = fitSel.value; keepBg = bgBox.checked;
        result = convert(src, fit, keepBg);
        const ctx = out.getContext('2d');
        out.width = 48; out.height = 64;
        ctx.putImageData(new ImageData(result.face, 48, 64), 0, 0);
        info.textContent = `${result.colors} colour${result.colors === 1 ? '' : 's'}${result.reduced ? ` (reduced from ${result.reduced})` : ''}${result.frames ? ', with its own talking frames' : ', the mouth stays still while talking'}.`;
      };
      fitSel.onchange = bgBox.onchange = redo;
      const ok = h('button', { class: 'btn btn-gilt' }, 'Use this picture');
      const cancel = h('button', { class: 'btn btn-line' }, 'Cancel');
      const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Replace portrait' },
        h('div', { class: 'modal-box' }, h('h2', {}, `Replace portrait ${p.n}`),
          h('div', { class: 'ptcompare' }, h('figure', {}, before, h('figcaption', {}, 'Now')), h('span', { class: 'ptarrow' }, '→'),
            h('figure', {}, out, h('figcaption', {}, 'New'))),
          info,
          h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'Fit'), fitSel)),
          h('label', { class: 'pick-check' }, bgBox, 'Keep the background (otherwise the colour in the corners becomes transparent)'),
          h('div', { class: 'modal-actions' }, cancel, ok)));
      cancel.onclick = () => modal.remove();
      modal.addEventListener('keydown', e => { if (e.key === 'Escape') modal.remove(); });
      ok.onclick = async () => {
        ok.disabled = true;
        try {
          await api('portrait', { n: p.n, png: result.png });
          modal.remove();
          await changed(`Portrait ${p.n} replaced`);
        } catch (e) { ok.disabled = false; toast(e.message, true); }
      };
      document.body.append(modal);
      redo(); ok.focus();
    };
    src.src = url;
  }

  await Promise.resolve(drawGrid());
  drawDetail();
  grid.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'center' });
  return {
    async refresh(change) {
      if (!change || change.files?.length) { P = (await api('portraits')).portraits; drawGrid(); drawDetail(); }
    },
  };
}

// ---------------------------------------------------------------- picture -> portrait
// Returns {png (base64 of a W x 64 PNG with <= 15 colours + transparency), face (RGBA 48x64),
// colors, reduced, frames}.
function convert(src, fit, keepBg) {
  const W = fit === 'exact' ? src.width : 48;
  const c = document.createElement('canvas');
  c.width = W; c.height = 64;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  if (fit === 'exact') ctx.drawImage(src, 0, 0);
  else {
    const k = fit === 'cover' ? Math.max(48 / src.width, 64 / src.height) : Math.min(48 / src.width, 64 / src.height);
    const w = src.width * k, hh = src.height * k;
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(src, (48 - w) / 2, fit === 'cover' ? 0 : (64 - hh) / 2, w, hh);
  }
  const d = ctx.getImageData(0, 0, W, 64);
  const px = d.data;
  // transparent background: flood the picture's border areas that have the corners' colour
  if (!keepBg) {
    const H = 64, FW = Math.min(W, 48);
    const c5 = i => [px[i] >> 3, px[i + 1] >> 3, px[i + 2] >> 3];
    const corners = [[0, 0], [FW - 1, 0], [0, H - 1], [FW - 1, H - 1]].map(([x, y]) => (y * W + x) * 4).filter(i => px[i + 3] >= 128);
    const close = (a, b) => Math.abs(a[0] - b[0]) <= 2 && Math.abs(a[1] - b[1]) <= 2 && Math.abs(a[2] - b[2]) <= 2;
    const seen = new Uint8Array(W * H);
    for (const ci of corners) {
      const bg = c5(ci);
      const stack = [];
      for (let x = 0; x < FW; x++) stack.push(x, (H - 1) * W + x);
      for (let y = 0; y < H; y++) stack.push(y * W, y * W + FW - 1);
      while (stack.length) {
        const k = stack.pop();
        if (seen[k]) continue;
        const i = k * 4;
        if (px[i + 3] < 128 || !close(c5(i), bg)) continue;
        seen[k] = 1; px[i + 3] = 0;
        const x = k % W, y = (k / W) | 0;
        if (x > 0) stack.push(k - 1);
        if (x < FW - 1) stack.push(k + 1);
        if (y > 0) stack.push(k - W);
        if (y < H - 1) stack.push(k + W);
      }
    }
  }
  // 5 bits per channel, as the SNES shows it
  const cols = new Map();
  for (let i = 0; i < px.length; i += 4) {
    if (px[i + 3] < 128) { px[i + 3] = 0; continue; }
    px[i + 3] = 255;
    const key = (px[i] >> 3) << 10 | (px[i + 1] >> 3) << 5 | px[i + 2] >> 3;
    cols.set(key, (cols.get(key) || 0) + 1);
  }
  let pal = [...cols.keys()];
  const reduced = pal.length > 15 ? pal.length : 0;
  if (pal.length > 15) pal = medianCut(cols, 15);
  const map = new Map();
  const near = key => {
    if (map.has(key)) return map.get(key);
    const r = key >> 10, g = key >> 5 & 31, b = key & 31;
    let best = 0, bd = 1e9;
    pal.forEach((p, i) => { const dr = r - (p >> 10), dg = g - (p >> 5 & 31), db = b - (p & 31); const dd = 3 * dr * dr + 4 * dg * dg + 2 * db * db; if (dd < bd) { bd = dd; best = i; } });
    map.set(key, pal[best]); return pal[best];
  };
  for (let i = 0; i < px.length; i += 4) {
    if (!px[i + 3]) { px[i] = px[i + 1] = px[i + 2] = 0; continue; }
    const k = near((px[i] >> 3) << 10 | (px[i + 1] >> 3) << 5 | px[i + 2] >> 3);
    px[i] = (k >> 10) * 255 / 31 | 0; px[i + 1] = (k >> 5 & 31) * 255 / 31 | 0; px[i + 2] = (k & 31) * 255 / 31 | 0;
  }
  ctx.putImageData(d, 0, 0);
  const face = new Uint8ClampedArray(48 * 64 * 4);
  for (let y = 0; y < 64; y++) face.set(px.subarray(y * W * 4, y * W * 4 + 48 * 4), y * 48 * 4);
  const png = c.toDataURL('image/png').split(',')[1];
  return { png, face, colors: pal.length, reduced, frames: W === 80 };
}

function medianCut(cols, n) {
  let boxes = [[...cols.entries()]];
  const ch = (k, c) => c === 0 ? k >> 10 : c === 1 ? k >> 5 & 31 : k & 31;
  while (boxes.length < n) {
    let bi = -1, bestRange = -1, bc = 0;
    boxes.forEach((b, i) => {
      if (b.length < 2) return;
      for (let c = 0; c < 3; c++) {
        let lo = 31, hi = 0;
        for (const [k] of b) { const v = ch(k, c); if (v < lo) lo = v; if (v > hi) hi = v; }
        const weight = b.reduce((s, [, w]) => s + w, 0);
        const score = (hi - lo) * Math.sqrt(weight);
        if (score > bestRange) { bestRange = score; bi = i; bc = c; }
      }
    });
    if (bi < 0) break;
    const b = boxes[bi].sort((x, y) => ch(x[0], bc) - ch(y[0], bc));
    const total = b.reduce((s, [, w]) => s + w, 0);
    let acc = 0, cut = 1;
    for (let i = 0; i < b.length - 1; i++) { acc += b[i][1]; if (acc >= total / 2) { cut = i + 1; break; } cut = i + 1; }
    boxes.splice(bi, 1, b.slice(0, cut), b.slice(cut));
  }
  return boxes.map(b => {
    let r = 0, g = 0, bl = 0, w = 0;
    for (const [k, c] of b) { r += (k >> 10) * c; g += (k >> 5 & 31) * c; bl += (k & 31) * c; w += c; }
    return Math.round(r / w) << 10 | Math.round(g / w) << 5 | Math.round(bl / w);
  });
}
