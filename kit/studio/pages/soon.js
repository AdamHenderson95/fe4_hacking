// Placeholder for the parts of the studio that come in later rounds.
import { api, h, toast } from '../app.js';

const TEXT = {
  items: ['Items, shops and villages are next', 'Weapons, staves and rings, what each village gives, and what shops and the arena offer.'],
};

export function soonPage(key) {
  const [title, what] = TEXT[key];
  const root = document.getElementById('page');
  root.append(h('div', { class: 'soon-page' },
    h('h2', {}, title),
    h('p', {}, what),
    h('p', {}, 'Until then, the classic editor has all of it as tables.'),
    h('button', { class: 'btn btn-ink', onclick: () => { api('classic', {}); toast('Opening the classic editor'); } }, 'Open the classic editor')));
  return {};
}
