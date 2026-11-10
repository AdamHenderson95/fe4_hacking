// Picking a part of a chapter map: a modal for area events, and a small preview of an area.
import { api, h } from '../app.js';
import { ARMY_COLORS, FOOT } from './maps.js';

const images = {};
function atlasOf(ch) {
  images[ch] ??= new Promise((ok, bad) => {
    const i = new Image();
    i.onload = () => ok(i);
    i.onerror = () => { delete images[ch]; bad(new Error('Couldn\'t draw the map: choose your FE4 ROM on the Project page.')); };
    i.src = `/gfx/tiles/${ch}.png`;
  });
  return images[ch];
}

// the whole map at 16 px a tile, drawn once per open
async function mapCanvas(ch) {
  const [M, atlas] = await Promise.all([api('map?ch=' + ch), atlasOf(ch)]);
  const c = document.createElement('canvas');
  c.width = M.width * 16; c.height = M.height * 16;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < M.words.length; i++) {
    const k = M.words[i] & 0x3FF;
    ctx.drawImage(atlas, (k % 32) * 16, (k >> 5) * 16, 16, 16, (i % M.width) * 16, Math.floor(i / M.width) * 16, 16, 16);
  }
  return { M, img: c };
}

// previews share one drawing per chapter; the events page forgets them when it reloads
let cache = {};
export function forgetMaps() { cache = {}; }
const cached = ch => (cache[ch] ??= mapCanvas(ch).catch(e => { delete cache[ch]; throw e; }));

const norm = r => ({ x1: Math.min(r.x1, r.x2), y1: Math.min(r.y1, r.y2), x2: Math.max(r.x1, r.x2), y2: Math.max(r.y1, r.y2) });
const sizeText = r => `${r.x2 - r.x1 + 1} × ${r.y2 - r.y1 + 1} tiles`;

function drawSites(ctx, M, s) {
  ctx.lineWidth = 2;
  for (const L of M.locations) {
    const f = FOOT[L.kind] || [0, 0, 0, 0];
    const x = Number(L.x) + f[0], y = Number(L.y) + f[1];
    ctx.strokeStyle = L.kind === 'castle' ? 'rgba(243,227,184,.9)' : 'rgba(255,255,255,.7)';
    ctx.strokeRect(x * s + 1, y * s + 1, (f[2] - f[0] + 1) * s - 2, (f[3] - f[1] + 1) * s - 2);
  }
}

function drawRect(ctx, r, s, fill, stroke, dash) {
  const x = r.x1 * s, y = r.y1 * s, w = (r.x2 - r.x1 + 1) * s, hh = (r.y2 - r.y1 + 1) * s;
  if (fill) { ctx.fillStyle = fill; ctx.fillRect(x, y, w, hh); }
  ctx.setLineDash(dash || []); ctx.lineWidth = 2; ctx.strokeStyle = stroke;
  ctx.strokeRect(x + 1, y + 1, w - 2, hh - 2); ctx.setLineDash([]);
}

/** Opens the picker. opts: {rect, unitName, exceptLine}. Resolves to {x1, y1, x2, y2} or null. */
export function pickArea(ch, opts = {}) {
  return new Promise(resolve => {
    let rect = opts.rect ? norm(opts.rect) : null, drag = null, hover = null, data = null;
    let zoom = 1;
    const cv = h('canvas', { class: 'pick-canvas', 'aria-label': 'Map: drag to mark the area' });
    const wrap = h('div', { class: 'pick-view' }, cv);
    const readout = h('div', { class: 'pick-readout', 'aria-live': 'polite' });
    const hoverOut = h('span', { class: 'pick-hover' });
    const showUnits = h('input', { type: 'checkbox', checked: true });
    const showOthers = h('input', { type: 'checkbox', checked: true });
    const ok = h('button', { class: 'btn btn-gilt' }, 'Use this area');
    const cancel = h('button', { class: 'btn btn-line' }, 'Cancel');
    const zoomBtn = d => h('button', { class: 'btn btn-line', 'aria-label': d > 0 ? 'Zoom in' : 'Zoom out', onclick: () => setZoom(zoom * (d > 0 ? 1.25 : 0.8)) }, d > 0 ? '+' : '−');
    const modal = h('div', { class: 'modal pick', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Pick an area on the map' },
      h('div', { class: 'modal-box pick-box' },
        h('div', { class: 'pick-head' }, h('h2', {}, 'Pick the area'),
          h('p', { class: 'hint' }, `Drag across the map. The event plays when ${opts.unitName || 'the unit'} ends a move inside the box.`)),
        h('div', { class: 'pick-tools' },
          h('div', { class: 'pick-zoom' }, zoomBtn(-1), zoomBtn(1)),
          h('label', { class: 'pick-check' }, showUnits, 'Units where they start'),
          h('label', { class: 'pick-check' }, showOthers, 'Other area events'), hoverOut),
        wrap,
        h('div', { class: 'pick-foot' }, readout, h('div', { class: 'modal-actions' }, cancel, ok))));
    const close = v => { modal.remove(); resolve(v); };
    cancel.onclick = () => close(null);
    ok.onclick = () => rect && close(rect);
    modal.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(null); } });
    showUnits.onchange = showOthers.onchange = () => draw();
    document.body.append(modal);
    wrap.append(h('div', { class: 'pick-loading' }, 'Drawing the map…'));

    function setZoom(z) {
      if (!data) return;
      const fit = Math.min((wrap.clientWidth - 4) / data.img.width, 1.5);
      zoom = Math.max(Math.min(z, 3), Math.max(fit, .4));
      draw(); if (rect) scrollTo(rect);
    }
    function scrollTo(r) {
      const s = 16 * zoom;
      wrap.scrollLeft = (r.x1 + r.x2 + 1) / 2 * s - wrap.clientWidth / 2;
      wrap.scrollTop = (r.y1 + r.y2 + 1) / 2 * s - wrap.clientHeight / 2;
    }
    function draw() {
      if (!data) return;
      const { M, img } = data, s = 16 * zoom;
      cv.width = Math.round(img.width * zoom); cv.height = Math.round(img.height * zoom);
      const ctx = cv.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0, cv.width, cv.height);
      drawSites(ctx, M, s);
      if (showUnits.checked) for (const l of M.deploy) for (const u of l.units) {
        const x = Number(u.x), y = Number(u.y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        ctx.fillStyle = ARMY_COLORS[(Number(u.army_slot) || 0) % ARMY_COLORS.length];
        ctx.beginPath(); ctx.arc((x + .5) * s, (y + .5) * s, Math.max(3, s * .28), 0, 7); ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 1.5; ctx.stroke();
      }
      if (showOthers.checked) {
        ctx.font = `600 ${Math.max(11, Math.round(s * .7))}px Inter, sans-serif`;
        for (const a of M.areas) {
          if (a.line === opts.exceptLine) continue;
          drawRect(ctx, a, s, 'rgba(255,255,255,.12)', 'rgba(255,255,255,.85)', [6, 4]);
          ctx.fillStyle = 'rgba(14,18,38,.75)';
          const t = a.who, tw = ctx.measureText(t).width + 8;
          ctx.fillRect(a.x1 * s + 2, a.y1 * s + 2, tw, Math.max(15, s * .9));
          ctx.fillStyle = '#fff'; ctx.fillText(t, a.x1 * s + 6, a.y1 * s + Math.max(13, s * .72));
        }
      }
      const r = drag ? norm(drag) : rect;
      if (r) drawRect(ctx, r, s, 'rgba(200,52,63,.28)', '#F3E3B8');
      if (hover && !drag) { ctx.strokeStyle = 'rgba(255,255,255,.7)'; ctx.lineWidth = 1.5; ctx.strokeRect(hover.x * s + .5, hover.y * s + .5, s - 1, s - 1); }
      const rr = r || null;
      readout.replaceChildren(rr
        ? h('span', {}, h('b', {}, `(${rr.x1}, ${rr.y1}) to (${rr.x2}, ${rr.y2})`), ` · ${sizeText(rr)}`)
        : h('span', { class: 'hint' }, 'No area yet: drag across the map.'));
      ok.disabled = !rect;
    }
    function cellAt(e) {
      const b = cv.getBoundingClientRect(), s = 16 * zoom;
      const x = Math.floor((e.clientX - b.left) / s), y = Math.floor((e.clientY - b.top) / s);
      const { M } = data;
      return { x: Math.max(0, Math.min(M.width - 1, x)), y: Math.max(0, Math.min(M.height - 1, y)) };
    }
    cv.onpointerdown = e => {
      if (!data || e.button !== 0) return;
      const c = cellAt(e);
      drag = { x1: c.x, y1: c.y, x2: c.x, y2: c.y };
      cv.setPointerCapture(e.pointerId); draw();
    };
    cv.onpointermove = e => {
      if (!data) return;
      const c = cellAt(e);
      hover = c;
      const t = data.M.terrain[data.M.words[c.y * data.M.width + c.x] & 0x3FF];
      hoverOut.textContent = `(${c.x}, ${c.y}) ${data.M.terrainNames[t] || ''}`;
      if (drag) { drag.x2 = c.x; drag.y2 = c.y; }
      draw();
    };
    cv.onpointerup = () => { if (drag) { rect = norm(drag); drag = null; draw(); ok.focus(); } };
    cv.onpointerleave = () => { hover = null; hoverOut.textContent = ''; if (!drag) draw(); };

    (cache[ch] = mapCanvas(ch)).then(d => {
      data = d;
      wrap.querySelector('.pick-loading')?.remove();
      setZoom(Math.max((wrap.clientWidth - 4) / d.img.width, 1));
      if (rect) scrollTo(rect);
    }).catch(e => { wrap.replaceChildren(h('p', { class: 'hint' }, e.message)); });
  });
}

/** A small picture of the map around an area. Click it to pick again. */
export function areaPreview(ch, r, onclick) {
  r = norm(r);
  const cv = h('canvas', { class: 'area-preview', title: 'Pick on the map', role: 'button', tabindex: '0', 'aria-label': `Area (${r.x1}, ${r.y1}) to (${r.x2}, ${r.y2}): pick on the map` });
  cv.onclick = onclick;
  cv.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onclick(); } };
  cached(ch).then(({ M, img }) => {
    const pad = 4, s = 12;
    const x0 = Math.max(0, r.x1 - pad), y0 = Math.max(0, r.y1 - pad);
    const x1 = Math.min(M.width - 1, r.x2 + pad), y1 = Math.min(M.height - 1, r.y2 + pad);
    let w = x1 - x0 + 1, hh = y1 - y0 + 1;
    const k = Math.min(1, 300 / (w * s), 180 / (hh * s));
    cv.width = Math.round(w * s * k); cv.height = Math.round(hh * s * k);
    const ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, x0 * 16, y0 * 16, w * 16, hh * 16, 0, 0, cv.width, cv.height);
    const t = s * k;
    drawRect(ctx, { x1: r.x1 - x0, y1: r.y1 - y0, x2: r.x2 - x0, y2: r.y2 - y0 }, t, 'rgba(200,52,63,.28)', '#F3E3B8');
  }).catch(() => cv.remove());
  return cv;
}
