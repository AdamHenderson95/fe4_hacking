// Music: which song plays on each chapter's map and in each army's phase, and your own music files
// (the PC port plays a song's file instead of the game's music; Test play uses this project's files).
import { api, h, toast, refreshSession, setField, loadTables } from '../app.js';

const st = { tab: 'where', filter: 'all', open: {} };
try { Object.assign(st, JSON.parse(sessionStorage.getItem('fe4studio-music') || '{}')); } catch (e) { /* none */ }
const remember = () => { try { sessionStorage.setItem('fe4studio-music', JSON.stringify({ tab: st.tab, filter: st.filter, open: st.open })); } catch (e) { /* none */ } };

const KIND = { map: 'Map music', battle: 'Battle music', music: 'Music', sound: 'Sound effect', other: 'Other' };

export async function musicPage(root) {
  let M = await api('music');
  await loadTables(['music', 'music_bosses']);
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
    return `${n} · ${s.name || KIND[s.kind] || s.kind}${s.sameAs ? ` (same as ${s.sameAs})` : ''}${s.file ? ' · your file' : ''}`;
  };
  const listen = n => {
    const s = M.songs[n - 1];
    return s?.file ? h('audio', { class: 'muaudio', controls: true, preload: 'none', src: `/music/${n}?v=${s.size}` }) : null;
  };

  function songOptions(sel, cur, none) {
    if (none) sel.append(h('option', { value: 0, selected: cur === 0 }, 'None'));
    for (const s of M.songs) if (s.kind !== 'sound' || s.n === cur) sel.append(h('option', { value: s.n, selected: s.n === cur }, songLabel(s.n)));
  }
  function songSelect(cell, label, none) {
    const sel = h('select', { class: 'in musel', 'aria-label': label });
    songOptions(sel, cell.song, none);
    sel.onchange = async () => {
      try {
        await setField('music', cell.row, 'song', sel.value);
        await changed('Song changed');
      } catch (e) { toast(e.message, true); sel.value = cell.song; }
    };
    return sel;
  }
  async function changed(msg) {
    const y = body.scrollTop;
    M = await api('music'); draw(); body.scrollTop = y; if (msg) toast(msg);
  }
  // a scene's PLAY_SONG command: same-length edit of its bytes in scenes.evt
  function sceneSelect(sc) {
    const sel = h('select', { class: 'in musel', 'aria-label': `Scene ${sc.scene}: song` });
    songOptions(sel, sc.song);
    sel.onchange = async () => {
      try {
        await api('evtcmd', { file: sc.file, line: sc.line, hex: '0E ' + Number(sel.value).toString(16).toUpperCase().padStart(2, '0') });
        await refreshSession(); await changed('Song changed');
      } catch (e) { toast(e.message, true); sel.value = sc.song; }
    };
    return sel;
  }
  function unitSelect(b) {
    const sel = h('select', { class: 'in musel', 'aria-label': `Boss ${b.row + 1}` });
    const known = M.units.some(u => u.n === b.unit);
    if (!known) sel.append(h('option', { value: b.unit, selected: true }, `Unit ${b.unit}`));
    for (const u of M.units) sel.append(h('option', { value: u.n, selected: u.n === b.unit }, `${u.name} (${u.n})`));
    sel.onchange = async () => {
      try { await setField('music_bosses', b.row, 'unit', sel.value); await changed('Boss list changed'); }
      catch (e) { toast(e.message, true); sel.value = b.unit; }
    };
    return sel;
  }
  const fold = (key, title, ...kids) => {
    const d = h('details', { class: 'mufold', open: st.open[key] ? true : null }, h('summary', {}, title), ...kids);
    d.ontoggle = () => { st.open[key] = d.open; remember(); };
    return d;
  };

  function draw() { body.replaceChildren(st.tab === 'where' ? where() : songs()); }

  // ------------------------------------------------------------ where songs play
  function where() {
    const row2 = (label, ...cells) => h('tr', {}, h('th', { scope: 'row' }, label), ...cells.map(c => h('td', {}, c)));
    const fixed = h('table', { class: 'mutable' }, h('tbody', {}, M.fixed.map(f => row2(f.name, songSelect(f, f.name)))));
    const ch = h('table', { class: 'mutable' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Chapter'), h('th', {}, 'When it opens'), h('th', {}, 'When the map starts'), h('th', {}, 'Your phase'))),
      h('tbody', {}, M.chapters.map(c => row2(c.title,
        c.opening ? songSelect(c.opening, c.title + ': when it opens', true) : '–',
        c.first ? songSelect(c.first, c.title + ': when the map starts') : '–',
        c.phase ? songSelect(c.phase, c.title + ': your phase') : '–'))));
    const ar = h('table', { class: 'mutable' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Army'), h('th', {}, 'Its phase'))),
      h('tbody', {}, M.armies.map(a => row2([a.name, h('span', { class: 'mudim' }, ` (${a.index})`)], songSelect(a, a.name + ' army: its phase')))));
    const bt = h('table', { class: 'mutable' },
      h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', {}, 'Battle music'))),
      h('tbody', {}, M.battle.map((b, i) => row2(`${i + 1}. ${b.name}`, songSelect(b, b.name)))));
    const bosses = h('div', { class: 'mubosses' }, M.bosses.map(b => unitSelect(b)));
    const more = h('table', { class: 'mutable' }, h('tbody', {}, M.battleMore.map(b => row2(b.name, songSelect(b, b.name)))));
    // story scenes, by chapter
    const groups = new Map();
    for (const sc of M.scenes) {
      const k = sc.chapters.length ? sc.chapters[0] : -1;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(sc);
    }
    const keys = [...groups.keys()].sort((a, b) => (a < 0) - (b < 0) || a - b);
    const scenes = keys.map(k => {
      const list = groups.get(k);
      const title = k < 0 ? 'Scenes no chapter script starts' : (M.chapters[k]?.title || `Chapter ${k}`);
      return fold('sc' + k, `${title} · ${list.length} song${list.length === 1 ? '' : 's'}`,
        h('table', { class: 'mutable muscenes' }, h('tbody', {}, list.map(sc => h('tr', {},
          h('th', { scope: 'row', class: 'munum' }, `Scene ${sc.scene}`),
          h('td', { class: 'mutext' }, sc.text || h('span', { class: 'mudim' }, 'No dialogue')),
          h('td', {}, sceneSelect(sc)))))));
    });
    return h('div', { class: 'musheet' },
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Start of the game'),
        fixed),
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Chapters and your army'),
        h('p', { class: 'hint' }, 'The song when a chapter opens (its first scene; the final chapter has none), when its map first starts, ',
          'and in your phase after that. (In some situations the game\'s code picks song 32 for your phase instead.)'),
        ch),
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Other armies'),
        h('p', { class: 'hint' }, 'The song in an army\'s phase, by the army\'s name (the name it shows on the map; the number is its name number). ',
          'A few armies get song 29 or 42 instead, chosen in the game\'s code.'),
        ar),
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Battles'),
        h('p', { class: 'hint' }, 'A battle plays the music of the first line that fits, from the top.'),
        bt,
        h('h3', { class: 'muh3' }, 'Bosses'),
        h('p', { class: 'hint' }, 'Fighting any of these units plays the boss music (line 4). Some appear twice because the game has several copies of them.'),
        bosses,
        h('h3', { class: 'muh3' }, 'More battle music'),
        h('p', { class: 'hint' }, 'Other kinds of battle set their own music. Only the first is known so far; the rest are listed by where the game sets them.'),
        more),
      h('section', { class: 'sheet musec' },
        h('h2', {}, 'Story scenes'),
        h('p', { class: 'hint' }, 'Scenes that start a song, with their first line of dialogue. A scene can start more than one song.'),
        ...scenes));
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
        h('td', {}, s.name ? h('div', { class: 'muname' }, s.name) : null, h('div', {}, KIND[s.kind] || s.kind, s.sameAs ? h('span', { class: 'mudim' }, ` · same as ${s.sameAs}`) : null),
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
    async refresh() { await loadTables(['music', 'music_bosses'], true); await changed(); }
  };
}
