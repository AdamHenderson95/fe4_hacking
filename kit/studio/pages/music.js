// Music: which song plays on each chapter's map and in each army's phase, and your own music files
// (the PC port plays a song's file instead of the game's music; Test play uses this project's files).
import { api, h, toast, refreshSession, setField, loadTables } from '../app.js';

const st = { tab: 'where', filter: 'all' };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-music') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-music', JSON.stringify({ tab: st.tab, filter: st.filter })); } catch (e) { /* none */ } };

const KIND = { map: 'Map music', battle: 'Battle music', music: 'Music', sound: 'Sound effect', other: 'Other' };

export async function musicPage(root) {
  let M = await api('music');
  await loadTables(['music']);
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const body = h('div', { class: 'mubody' });
  root.append(h('div', { class: 'mupage' }, h('div', { class: 'mutop' }, tabs), body));

  function drawTabs() {
    tabs.replaceChildren(...[['where', 'Where songs play'], ['songs', 'Songs & your music']].map(([k, t]) =>
      h('button', { role: 'tab', 'aria-selected': String(st.tab === k), onclick: () => { st.tab = k; remember(); drawTabs(); draw(); } }, t)));
  }
  const songLabel = n => {
    const s = M.songs[n - 1];
    if (!s) return String(n);
    return `${n} · ${KIND[s.kind] || s.kind}${s.sameAs ? ` (same as ${s.sameAs})` : ''}${s.file ? ' · your file' : ''}`;
  };
  const listen = n => {
    const s = M.songs[n - 1];
    return s?.file ? h('audio', { class: 'muaudio', controls: true, preload: 'none', src: `/music/${n}?v=${s.size}` }) : null;
  };

  function songSelect(cell, label) {
    const sel = h('select', { class: 'in musel', 'aria-label': label });
    for (const s of M.songs) if (s.kind !== 'sound') sel.append(h('option', { value: s.n, selected: s.n === cell.song }, songLabel(s.n)));
    sel.onchange = async () => {
      try {
        await setField('music', cell.row, 'song', sel.value);
        M = await api('music'); draw(); toast('Song changed');
      } catch (e) { toast(e.message, true); sel.value = cell.song; }
    };
    return sel;
  }

  function draw() { body.replaceChildren(st.tab === 'where' ? where() : songs()); }

  // ------------------------------------------------------------ where songs play
  function where() {
    const ch = h('table', { class: 'mutable' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Chapter'), h('th', {}, 'When the map starts'), h('th', {}, 'Your phase'))),
      h('tbody', {}, M.chapters.map(c => h('tr', {},
        h('th', { scope: 'row' }, c.title),
        h('td', {}, c.first ? songSelect(c.first, c.title + ': when the map starts') : '–'),
        h('td', {}, c.phase ? songSelect(c.phase, c.title + ': your phase') : '–')))));
    const ar = h('table', { class: 'mutable' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Army'), h('th', {}, 'Its phase'))),
      h('tbody', {}, M.armies.map(a => h('tr', {},
        h('th', { scope: 'row' }, a.name, h('span', { class: 'mudim' }, ` (${a.index})`)),
        h('td', {}, songSelect(a, a.name + ' army: its phase'))))));
    return h('div', { class: 'musheet' },
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Your army'),
        h('p', { class: 'hint' }, 'The song when a chapter\'s map first starts, and the song in your phase after that. ',
          '(In some situations the game\'s code picks song 32 instead.)'),
        ch),
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Other armies'),
        h('p', { class: 'hint' }, 'The song in an army\'s phase, by the army\'s name (the name it shows on the map; the number is its name number). ',
          'A few armies get song 29 or 42 instead, chosen in the game\'s code.'),
        ar));
  }

  // ------------------------------------------------------------ songs and files
  function songs() {
    const filters = [['all', 'All'], ['map', 'Map music'], ['battle', 'Battle music'], ['music', 'Other music'], ['mine', 'With your file']];
    const chips = h('div', { class: 'chips' }, filters.map(([k, t]) =>
      h('button', { class: 'chip', 'aria-pressed': String(st.filter === k), onclick: () => { st.filter = k; remember(); draw(); } }, t)));
    const list = M.songs.filter(s => s.kind !== 'sound' && (st.filter === 'all' || (st.filter === 'mine' ? s.file : s.kind === st.filter)));
    const rows = list.map(s => {
      const file = h('input', { type: 'file', accept: '.ogg,.flac,.mp3,.wav,.pcm,audio/*', hidden: true });
      file.onchange = async () => {
        const f = file.files[0]; file.value = '';
        if (!f) return;
        if (f.size > 64 * 1024 * 1024) { toast('That file is over 64 MB.', true); return; }
        try {
          const data = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result.split(',')[1]); r.onerror = bad; r.readAsDataURL(f); });
          await api('musicfile', { song: s.n, name: f.name, data });
          M = await api('music'); await refreshSession(); draw(); toast(`Song ${s.n} now plays ${f.name} in the PC port`);
        } catch (e) { toast(e.message, true); }
      };
      const remove = s.file ? h('button', { class: 'btn btn-line danger', onclick: async () => {
        try { await api('musicfile', { song: s.n, remove: true }); M = await api('music'); await refreshSession(); draw(); toast(`Song ${s.n}: the game's own music again`); }
        catch (e) { toast(e.message, true); }
      } }, 'Remove') : null;
      return h('tr', {},
        h('th', { scope: 'row', class: 'munum' }, s.n),
        h('td', {}, h('div', {}, KIND[s.kind] || s.kind, s.sameAs ? h('span', { class: 'mudim' }, ` · same as ${s.sameAs}`) : null),
          s.uses.length ? h('div', { class: 'muuses' }, s.uses.join(', ')) : null),
        h('td', { class: 'mufile' },
          s.file ? h('div', { class: 'mufname' }, s.file, h('span', { class: 'mudim' }, ` · ${(s.size / 1048576).toFixed(1)} MB`)) : h('span', { class: 'mudim' }, 'The game\'s own music'),
          listen(s.n),
          h('div', { class: 'muacts' }, h('button', { class: 'btn btn-line', onclick: () => file.click() }, s.file ? 'Replace…' : 'Use a music file…'), remove, file)));
    });
    return h('div', { class: 'musheet' },
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Your own music'),
        h('p', { class: 'hint' }, 'Give any song a music file (.ogg, .flac, .mp3, .wav, or an MSU-1 .pcm) and the PC port plays it instead of the game\'s music, ',
          'with the game\'s sound effects on top. Test play uses these files. The files are kept in this project\'s music folder.'),
        h('p', { class: 'hint' }, 'To share them, give players the files in the music folder: they go in the PC port\'s own music folder, where any ',
          'song number named at the start of a file name plays (17.ogg, "017 Prologue.flac"). Loops: LOOPSTART / LOOPLENGTH tags in .ogg files, ',
          'or a .txt file with the same name saying loop_start = 12.5 (seconds).'),
        h('p', { class: 'hint' }, 'To find a song\'s number, play the game in the PC port: its menu (F1) shows the song playing now under Audio.'),
        M.portMusic ? null : h('p', { class: 'hint muwarn' }, 'Your PC port is older than 0.10 and can\'t play music files. Use the FE4Port.zip that comes with this kit.'),
        chips),
      h('section', { class: 'sheet musec' }, h('table', { class: 'mutable musongs' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Song'), h('th', {}, 'What it is'), h('th', {}, 'In the PC port'))),
        h('tbody', {}, rows))));
  }

  drawTabs(); draw();
  return {
    async refresh() { M = await api('music'); await loadTables(['music'], true); draw(); }
  };
}
