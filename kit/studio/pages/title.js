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

export async function titlePage(root) {
  let T = await api('title');
  const k = Date.now().toString(36);
  let src = 'project';
  const ver = () => T.layers.map(l => l.ver).join('-');
  const url = (which, s, from) => `/gfx/title/${which}.png?s=${s}&src=${from || src}&c=${ver()}-${k}`;

  const big = h('img', { class: 'tibig', width: 512, height: 448, alt: 'The title screen' });
  const viewSel = h('div', { class: 'mlayers', role: 'group', 'aria-label': 'Show' });
  const cards = h('div', { class: 'ticards' });
  root.append(h('div', { class: 'tipage' },
    h('section', { class: 'tishow' },
      h('div', { class: 'tihead' }, h('span', { class: 'hint' }, 'Show'), viewSel),
      big,
      h('p', { class: 'hint' }, 'This is the title after Start or after the opening. The menu and the Jugdral Chronology screens keep the game\'s own picture of the knights; the logo\'s moving shine works with any logo.')),
    cards));

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

  drawView(); drawCards();
  return {
    async refresh(change) {
      if (!change || change.files?.length) { T = await api('title'); drawView(); drawCards(); }
    },
  };
}
