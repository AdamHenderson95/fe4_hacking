// Title screen: its three layers (background, logo, emblem) as pictures you can replace (kit v53).
// A picture is fitted to 256 x 224 here; the editor reduces it to the colours and tiles the SNES allows.
import { api, h, toast, refreshSession } from '../app.js';

const LAYERS = {
  background: { title: 'Background', what: 'The picture behind everything.',
    limits: 'Two palettes of 15 colours (pure black is free), up to 512 different 8 × 8 tiles; similar tiles are merged when there are more.',
    opaque: true },
  logo: { title: 'Logo', what: 'The title text, subtitle and anything else in front. Transparent everywhere else.',
    limits: 'Three palettes (15, 15 and 8 colours), up to 270 different 8 × 8 tiles. When the opening runs into the title, the logo flies in with only its top part (above y = 168) showing; the rest appears with the title.' },
  emblem: { title: 'Emblem', what: 'The sword and book: sprites between the background and the logo.',
    limits: 'Two palettes of 15 colours, at most 128 sprites (16 × 16 squares) and 356 sprite tiles: roughly a picture the size of the original emblem.' },
};

const CAP_FONTS = ['Georgia', 'Palatino Linotype', 'Book Antiqua', 'Garamond', 'Times New Roman', 'Cambria', 'Constantia', 'serif'];
const CAP_GREYS = [0, 0, 8, 16, 40, 48, 56, 64, 72, 80, 88, 104, 120, 144, 168, 200];

/** Words as a caption picture: 256 x 16 colour numbers 0-15 (hex digits), light grey on black, centred. */
export function renderCaption(text, { font = 'Georgia', size = 12 } = {}) {
  const S = 4, c = document.createElement('canvas'), g = c.getContext('2d');
  const f = `${size * S}px "${font}", serif`;
  g.font = f;
  const tw = Math.ceil(g.measureText(text).width);
  c.width = tw + 8 * S; c.height = 16 * S;
  g.font = f; g.fillStyle = '#fff'; g.strokeStyle = '#fff'; g.lineWidth = 0.45 * S; g.lineJoin = 'round';
  g.textBaseline = 'alphabetic';
  g.fillText(text, 4 * S, 12 * S);
  g.strokeText(text, 4 * S, 12 * S);            // a little heavier, like Naga's letters
  const w = Math.max(1, Math.round(c.width / S));
  const d = document.createElement('canvas'); d.width = w; d.height = 16;
  const dg = d.getContext('2d');
  dg.imageSmoothingEnabled = true; dg.imageSmoothingQuality = 'high';
  dg.drawImage(c, 0, 0, w, 16);
  const a = dg.getImageData(0, 0, w, 16).data;
  let x0 = w, x1 = -1;
  for (let x = 0; x < w; x++) for (let y = 0; y < 16; y++) if (a[(y * w + x) * 4 + 3] > 16) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); }
  const out = new Array(4096).fill('0');
  if (x1 < 0) return { px: out.join(''), wide: false };
  const tw2 = x1 - x0 + 1, ox = Math.floor((256 - tw2) / 2);
  for (let y = 0; y < 16; y++) for (let x = x0; x <= x1; x++) {
    const v = a[(y * w + x) * 4 + 3] * 200 / 255, X = ox + x - x0;
    if (X < 0 || X >= 256 || v < 6) continue;
    let best = 0;
    for (let k = 2; k < 16; k++) if (Math.abs(CAP_GREYS[k] - v) < Math.abs(CAP_GREYS[best] - v)) best = k;
    out[y * 256 + X] = best.toString(16);
  }
  return { px: out.join(''), wide: tw2 > 256 };
}

export async function titlePage(root) {
  let T = await api('title');
  const k = Date.now().toString(36);
  let src = 'project';
  const ver = () => T.layers.map(l => l.ver).join('-');
  const url = (which, s, from) => `/gfx/title/${which}.png?s=${s}&src=${from || src}&c=${ver()}-${k}`;

  const big = h('img', { class: 'tibig', width: 512, height: 448, alt: 'The title screen' });
  const viewSel = h('div', { class: 'mlayers', role: 'group', 'aria-label': 'Show' });
  const cards = h('div', { class: 'ticards' });
  const capsBox = h('section', { class: 'sheet ticaps' }, h('p', { class: 'hint' }, 'Loading the opening\'s captions…'));
  const picsBox = h('section', { class: 'sheet ticaps' }, h('p', { class: 'hint' }, 'Loading the opening\'s pictures…'));
  root.append(h('div', { class: 'tipage' },
    h('section', { class: 'tishow' },
      h('div', { class: 'tihead' }, h('span', { class: 'hint' }, 'Show'), viewSel),
      big,
      h('p', { class: 'hint' }, 'This is the title after Start or after the opening. The menu and the Jugdral Chronology screens keep the game\'s own picture of the knights; the logo\'s moving shine works with any logo.')),
    h('div', { class: 'ticol' }, cards, picsBox, capsBox)));

  function drawView() {
    viewSel.replaceChildren(...[['project', 'Your title'], ['game', 'The game\'s']].map(([v, label]) =>
      h('button', { class: 'chip', 'aria-pressed': String(src === v), onclick: () => { src = v; drawView(); } }, label)));
    big.src = url('title', 2);
  }

  function noteText(name, n) {
    if (!n) return '';
    if (n.error) return n.error;
    if (name === 'emblem') return n.hidden ? 'Hidden: no sword and book.' : `${n.sprites} of ${n.sprite_limit} sprites, ${n.colours} colours${n.exact ? '' : ' (reduced)'}.`;
    return `${n.tiles} of ${n.tile_limit} tiles${n.merged ? ` (${n.merged} merged with similar ones)` : ''}, ${n.colours} colours${n.exact ? '' : ' (reduced)'}.`;
  }

  function drawCards() {
    cards.replaceChildren(...T.layers.map(l => {
      const L = LAYERS[l.name];
      const file = h('input', { type: 'file', accept: 'image/*', hidden: true });
      file.onchange = () => { const f = file.files[0]; file.value = ''; if (f) importDialog(l.name, f); };
      const acts = [
        h('button', { class: 'btn btn-gilt', onclick: () => file.click() }, 'Replace with a picture…'),
        h('a', { class: 'btn btn-line', href: url(l.name, 1, 'project'), download: `title_${l.name}.png` }, 'Download PNG'),
      ];
      if (l.name === 'emblem' && !l.note?.hidden) acts.push(h('button', { class: 'btn btn-line', onclick: () => set({ layer: 'emblem', hide: true }, 'Emblem hidden') }, 'Hide it'));
      if (l.custom) acts.push(h('button', { class: 'btn btn-line danger', onclick: () => set({ layer: l.name, reset: true }, 'Back to the game\'s own') }, 'Use the original'));
      return h('article', { class: 'sheet ticard' },
        h('div', { class: 'ticard-head' }, h('h3', {}, L.title), l.custom ? h('span', { class: 'chip ptchip' }, 'Replaced in this project') : null),
        h('div', { class: 'ticard-body' },
          h('img', { class: 'tithumb' + (L.opaque ? '' : ' checker'), src: url(l.name, 1, 'project'), width: 256, height: 224, alt: L.title }),
          h('div', {}, h('p', {}, L.what), l.custom ? h('p', { class: 'tinote' + (l.note?.error ? ' bad' : '') }, noteText(l.name, l.note)) : null,
            h('p', { class: 'hint' }, L.limits))),
        h('div', { class: 'ptactions' }, ...acts, file));
    }));
  }

  async function set(body, msg) {
    try {
      await api('titleset', body);
      T = await api('title');
      await refreshSession(); drawView(); drawCards(); toast(msg);
    } catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------ import: fit the picture to 256 x 224
  function importDialog(name, file) {
    const u = URL.createObjectURL(file);
    const im = new Image();
    im.onerror = () => { URL.revokeObjectURL(u); toast('That file isn\'t a picture the browser can open.', true); };
    im.onload = () => {
      URL.revokeObjectURL(u);
      const exact = im.width === T.w && im.height === T.h;
      const cv = h('canvas', { class: 'tiprev' + (LAYERS[name].opaque ? '' : ' checker'), width: T.w, height: T.h });
      const fitSel = h('select', { class: 'in', 'aria-label': 'Fit' },
        exact ? h('option', { value: 'exact' }, 'As is (256 × 224)') : null,
        h('option', { value: 'contain' }, 'Fit inside the screen'), h('option', { value: 'cover' }, 'Fill the screen (crop the edges)'));
      const draw = () => {
        const ctx = cv.getContext('2d');
        ctx.clearRect(0, 0, T.w, T.h);
        ctx.imageSmoothingEnabled = !exact;
        const f = fitSel.value;
        if (f === 'exact') { ctx.drawImage(im, 0, 0); return; }
        const s = (f === 'cover' ? Math.max : Math.min)(T.w / im.width, T.h / im.height);
        const w = Math.round(im.width * s), hh = Math.round(im.height * s);
        ctx.drawImage(im, Math.round((T.w - w) / 2), Math.round((T.h - hh) / 2), w, hh);
      };
      fitSel.onchange = draw;
      const ok = h('button', { class: 'btn btn-gilt' }, 'Use this picture');
      const cancel = h('button', { class: 'btn btn-line' }, 'Cancel');
      const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Replace the ${LAYERS[name].title.toLowerCase()}` },
        h('div', { class: 'modal-box' }, h('h2', {}, `Replace the ${LAYERS[name].title.toLowerCase()}`),
          cv, h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'Fit'), fitSel)),
          h('p', { class: 'hint' }, LAYERS[name].limits),
          h('div', { class: 'modal-actions' }, cancel, ok)));
      cancel.onclick = () => modal.remove();
      modal.addEventListener('keydown', e => { if (e.key === 'Escape') modal.remove(); });
      ok.onclick = async () => {
        ok.disabled = true; ok.textContent = 'Converting…';
        try {
          const png = cv.toDataURL('image/png').split(',')[1];
          await api('titleset', { layer: name, png });
          modal.remove();
          T = await api('title');
          await refreshSession(); drawView(); drawCards();
          toast(`${LAYERS[name].title} replaced`);
        } catch (e) { ok.disabled = false; ok.textContent = 'Use this picture'; toast(e.message, true); }
      };
      document.body.append(modal);
      draw(); ok.focus();
    };
    im.src = u;
  }

  // ------------------------------------------------------------ the opening's captions (1.7)
  async function drawCaptions() {
    let C;
    try { C = await api('captions'); } catch (e) { capsBox.replaceChildren(h('p', { class: 'hint' }, e.message)); return; }
    const grey = C.greys;
    const paint = (cv, px) => {
      const g = cv.getContext('2d'), im = g.createImageData(256, 16);
      for (let i = 0; i < 4096; i++) { const v = grey[parseInt(px[i], 16)]; im.data.set([v, v, v, 255], i * 4); }
      g.putImageData(im, 0, 0);
    };
    capsBox.replaceChildren(
      h('h3', {}, 'The opening\'s captions'),
      h('p', { class: 'hint' }, 'The line of words under each story picture of the opening, before the title. Project Naga drew them as pictures; type new words and the editor draws them in the same style (light letters on black, 256 × 16 pixels).'),
      ...C.captions.map(c => {
        const look = { font: 'Georgia', size: 12, ...(c.look || {}) };
        const cv = h('canvas', { class: 'ticap-cv', width: 256, height: 16, 'aria-label': `Caption ${c.i + 1}` });
        const textIn = h('input', { class: 'in', value: c.text, placeholder: 'New words for this caption', 'aria-label': `Words for caption ${c.i + 1}` });
        const fontSel = h('select', { class: 'in', 'aria-label': 'Font' }, CAP_FONTS.map(f => h('option', { value: f, selected: f === look.font }, f)));
        const sizeIn = h('input', { class: 'in', type: 'number', min: 8, max: 16, value: look.size, 'aria-label': 'Size' });
        const warn = h('span', { class: 'hint ticap-warn' });
        let cur = null;
        const show = () => {
          const t = textIn.value.trim();
          if (!t) { cur = null; warn.textContent = ''; paint(cv, c.custom ? c.px : c.orig); return; }
          const r = renderCaption(t, { font: fontSel.value, size: Number(sizeIn.value) });
          cur = r.px; paint(cv, r.px);
          warn.textContent = r.wide ? 'Too wide: it is cut at the edges. Use fewer words or a smaller size.' : '';
        };
        for (const el of [textIn, fontSel, sizeIn]) el.addEventListener('input', show);
        const save = h('button', { class: 'btn btn-gilt btn-sm', onclick: async () => {
          if (!cur) { toast('Type the new words first.', true); return; }
          try {
            await api('captions', { i: c.i, text: textIn.value.trim(), px: cur, look: { font: fontSel.value, size: Number(sizeIn.value) } });
            await refreshSession(); toast(`Caption ${c.i + 1} saved (Ctrl+Z undoes it)`); drawCaptions();
          } catch (e) { toast(e.message, true); }
        } }, 'Save');
        const reset = c.custom ? h('button', { class: 'btn btn-line btn-sm', onclick: async () => {
          try { await api('captions', { i: c.i, reset: true }); await refreshSession(); toast(`Caption ${c.i + 1}: the game's own again`); drawCaptions(); }
          catch (e) { toast(e.message, true); }
        } }, 'Use the original') : null;
        const orig = h('canvas', { class: 'ticap-cv ticap-orig', width: 256, height: 16, title: 'The game\'s own caption' });
        paint(orig, c.orig);
        if (c.custom) paint(cv, c.px); else paint(cv, c.orig);
        return h('div', { class: 'ticap' },
          h('div', { class: 'ticap-num' }, String(c.i + 1)),
          h('div', { class: 'ticap-main' },
            h('div', { class: 'ticap-pics' }, h('div', {}, h('span', { class: 'hint' }, c.custom ? 'Yours' : 'Now'), cv),
              c.custom ? h('div', {}, h('span', { class: 'hint' }, 'The game\'s'), orig) : null),
            h('div', { class: 'ticap-row' }, textIn, fontSel, sizeIn, save, reset), warn));
      }));
  }

  // ------------------------------------------------------------ the opening's story pictures (1.8)
  let picVer = Date.now().toString(36);
  async function drawPictures() {
    let P;
    try { P = await api('storypics'); } catch (e) { picsBox.replaceChildren(h('p', { class: 'hint' }, e.message)); return; }
    const purl = (key, src) => `/gfx/story/${key}.png?src=${src}&c=${picVer}`;
    const card = sc => {
      const file = h('input', { type: 'file', accept: 'image/*', hidden: true });
      file.onchange = () => { const f = file.files[0]; file.value = ''; if (f) importPicture(sc, f); };
      const note = sc.note ? `${sc.note.tiles} of ${sc.note.tile_limit} tiles, ${sc.note.colours} of ${sc.note.colour_limit} colours${sc.note.exact ? '' : ' (reduced)'}.` : `${sc.w} × ${sc.h}; up to ${sc.tile_limit} tiles and ${sc.colour_limit} colours.`;
      return h('article', { class: 'tipic' + (sc.w < 512 ? ' tipic-sq' : '') },
        h('div', { class: 'ticard-head' }, h('h4', {}, sc.title), sc.custom ? h('span', { class: 'chip ptchip' }, 'Replaced in this project') : null),
        h('p', { class: 'hint', style: 'margin:0 0 6px' }, sc.when),
        h('img', { class: 'tipic-img checker', src: purl(sc.key, 'project'), width: sc.w, height: sc.h, alt: `${sc.scene}: ${sc.title}` }),
        h('p', { class: 'hint' }, note),
        h('div', { class: 'ticap-row' },
          h('button', { class: 'btn btn-gilt btn-sm', onclick: () => file.click() }, 'Replace with a picture…'),
          h('a', { class: 'btn btn-line btn-sm', href: purl(sc.key, 'project'), download: `story_${sc.key}.png` }, 'Download PNG'),
          sc.custom ? h('button', { class: 'btn btn-line btn-sm danger', onclick: async () => {
            try { await api('storypics', { key: sc.key, reset: true }); picVer = Date.now().toString(36); await refreshSession(); toast(`${sc.scene}, ${sc.title.toLowerCase()}: the game's own again`); drawPictures(); }
            catch (e) { toast(e.message, true); }
          } }, 'Use the original') : null),
        file);
    };
    const scenes = [];
    for (const sc of P.scenes) {
      let g = scenes.find(x => x.name === sc.scene);
      if (!g) scenes.push(g = { name: sc.scene, layers: [] });
      g.layers.push(sc);
    }
    picsBox.replaceChildren(
      h('h3', {}, 'The opening\'s story pictures'),
      h('p', { class: 'hint' }, 'The background layers of the opening\'s scenes, front layer first. The camera pans across the wide ones, so the screen shows part of each at a time. Transparent parts show the layers behind. Download one to see its layout, paint over it and put it back. The burst of light, the rays, the flames and the weapons stay the game\'s: their colours are made as they play.'),
      ...scenes.map(g => h('section', { class: 'tiscene' }, h('h3', { class: 'tiscene-h' }, g.name), ...g.layers.map(card))));

    function importPicture(sc, f) {
      const u = URL.createObjectURL(f);
      const im = new Image();
      im.onload = () => {
        const W = sc.w, H = sc.h;
        const cv = h('canvas', { class: 'tipic-img checker', width: W, height: H });
        const fitSel = h('select', { class: 'in', 'aria-label': 'Fit' },
          [['fill', 'Fill the picture (crop)'], ['fit', 'Fit inside (transparent around)'], ['as', 'As it is (top left)']].map(([v, t]) => h('option', { value: v }, t)));
        if (im.width === W && im.height === H) fitSel.value = 'as';
        const draw = () => {
          const g = cv.getContext('2d'); g.clearRect(0, 0, W, H); g.imageSmoothingQuality = 'high';
          const k = fitSel.value === 'as' ? 1 : fitSel.value === 'fill' ? Math.max(W / im.width, H / im.height) : Math.min(W / im.width, H / im.height);
          const w = im.width * k, hh = im.height * k;
          const x = fitSel.value === 'as' ? 0 : (W - w) / 2, y = fitSel.value === 'as' ? 0 : (H - hh) / 2;
          g.drawImage(im, x, y, w, hh);
        };
        fitSel.onchange = draw;
        const cancel = h('button', { class: 'btn btn-line' }, 'Cancel');
        const ok = h('button', { class: 'btn btn-gilt' }, 'Use this picture');
        const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Replace ${sc.scene}: ${sc.title}` },
          h('div', { class: 'modal-box tipic-dlg' }, h('h2', {}, `Replace "${sc.scene}: ${sc.title.toLowerCase()}"`),
            cv, h('div', { class: 'itgrid wide' }, h('label', { class: 'lbl' }, h('span', {}, 'Fit'), fitSel)),
            h('p', { class: 'hint' }, `The editor reduces it to ${sc.colour_limit} colours and ${sc.tile_limit} different 8 × 8 tiles (mirrored tiles count once; similar ones are merged when there are too many).`),
            h('div', { class: 'modal-actions' }, cancel, ok)));
        cancel.onclick = () => modal.remove();
        modal.addEventListener('keydown', e => { if (e.key === 'Escape') modal.remove(); });
        ok.onclick = async () => {
          ok.disabled = true; ok.textContent = 'Converting…';
          try {
            const png = cv.toDataURL('image/png').split(',')[1];
            const r = await api('storypics', { key: sc.key, png });
            modal.remove(); picVer = Date.now().toString(36);
            await refreshSession(); drawPictures();
            toast(`${sc.scene}, ${sc.title.toLowerCase()} replaced: ${r.note.tiles} tiles, ${r.note.colours} colours (Ctrl+Z undoes it)`);
          } catch (e) { ok.disabled = false; ok.textContent = 'Use this picture'; toast(e.message, true); }
        };
        document.body.append(modal); draw(); ok.focus();
        URL.revokeObjectURL(u);
      };
      im.onerror = () => toast('That file is not a picture the browser can read.', true);
      im.src = u;
    }
  }

  drawView(); drawCards(); drawPictures(); drawCaptions();
  return {
    async refresh(change) {
      if (!change || change.files?.length) { T = await api('title'); picVer = Date.now().toString(36); drawView(); drawCards(); drawPictures(); drawCaptions(); }
    },
  };
}
