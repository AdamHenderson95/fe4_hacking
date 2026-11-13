// Project page: your ROM, open / create a project, recent projects, settings.
import { api, h, app, toast, refreshSession, watchJob, go, loadTables } from '../app.js';

export async function homePage(root) {
  const page = h('div', { class: 'home' });
  root.append(page);

  async function render() {
    const s = app.session;
    page.replaceChildren();

    // ROM
    const romSec = h('section', {},
      h('h2', {}, 'Your ROM'),
      h('p', {}, 'Projects are made from your copy of the game: FE4 with the Project Naga translation. ' +
        'The studio reads it for new projects, portraits and builds; it never changes the file.'));
    if (s.rom) {
      romSec.append(h('div', { class: 'row' }, h('span', { class: 'path' }, s.rom),
        h('button', { class: 'btn btn-line', onclick: chooseRom }, 'Change')));
      if (s.romIsNaga === false) romSec.append(h('p', { class: 'warn' },
        "This isn't the unmodified Project Naga image the kit was made for. It may still work if it's close to it."));
    } else {
      romSec.append(h('button', { class: 'btn btn-ink', onclick: chooseRom }, 'Choose your ROM…'));
    }
    page.append(romSec);

    // projects
    const proj = h('section', {}, h('h2', {}, 'Projects'),
      h('p', {}, 'A project is a folder of editable files for one hack. Build turns it into a ROM and a shareable .ips patch.'));
    if (s.project) proj.append(h('p', {}, 'Open now: ', h('b', {}, s.projectName), h('span', { class: 'note' }, '  ' + s.project)));
    proj.append(h('div', { class: 'row' },
      h('button', { class: 'btn btn-ink', onclick: newProject, disabled: !s.rom }, 'New project…'),
      h('button', { class: 'btn btn-line', onclick: openProject }, 'Open a project folder…')));
    if (s.recent.length) {
      const ul = h('ul', { class: 'recent' });
      for (const p of s.recent) {
        const name = p.split(/[\\/]/).filter(Boolean).pop();
        ul.append(h('li', {}, h('button', { onclick: () => open(p) }, h('span', {}, name), h('span', { class: 'where' }, p))));
      }
      proj.append(h('h2', { style: 'font-size:21px;margin-top:18px' }, 'Recent'), ul);
    }
    page.append(proj);

    // settings
    const hover = h('input', { type: 'checkbox', id: 'hoverOpt', checked: s.hoverStats });
    hover.onchange = async () => { await api('settings', { hoverStats: hover.checked }); await refreshSession(); toast(hover.checked ? 'Builds include unit stats' : 'Builds without unit stats'); };
    const msu = h('input', { type: 'checkbox', id: 'msuOpt', checked: s.msu });
    msu.onchange = async () => { await api('settings', { msu: msu.checked }); await refreshSession(); toast(msu.checked ? 'Builds make MSU-1 music for emulators' : 'Builds without MSU-1 music'); };
    page.append(h('section', {}, h('h2', {}, 'Building'),
      h('p', {}, h('label', {}, hover, ' Add unit stats (MT, HIT, AS, AVO) to the map box in the ROMs you build, for players on emulators.')),
      h('p', {}, h('label', {}, msu, ' Make an MSU-1 music version for emulators: Build ROM also writes your music files (Music page) next to the ROM ',
        'as MSU-1 tracks, for bsnes, Snes9x and RetroArch (bsnes / Snes9x cores), which play them like the PC port does.')),
      h('div', { class: 'field-row' },
        h('span', {}, 'FE4 PC port'),
        h('div', { class: 'row' }, h('span', { class: 'path' }, s.port || 'Not found yet'),
          h('button', { class: 'btn btn-line', onclick: choosePort }, 'Choose FE4.exe…'))),
      h('p', { class: 'note', style: 'margin-top:12px' }, 'Test play builds your project and opens it in the PC port, with its own saves.'),
      h('p', { class: 'note' }, 'Not everything is in the studio yet. ',
        h('a', { href: '#', onclick: e => { e.preventDefault(); api('classic', {}); toast('Opening the classic editor'); } }, 'Open the classic editor'),
        ' for maps, scripts, items and the other tables.')));
  }

  async function chooseRom() {
    const { path } = await api('dialog', { kind: 'rom', title: 'Your FE4 ROM (Project Naga translation)' });
    if (!path) return;
    try { await api('rom', { path }); await refreshSession(); render(); }
    catch (e) { toast(e.message, true); }
  }
  async function open(path) {
    try {
      await api('open', { path });
      app.tables = {};
      await refreshSession();
      go('characters');
    } catch (e) { toast(e.message, true); }
  }
  async function openProject() {
    const { path } = await api('dialog', { kind: 'folder', title: 'Open a project folder' });
    if (path) open(path);
  }
  async function newProject() {
    const { path } = await api('dialog', { kind: 'folder', title: 'Where to put the new project folder' });
    if (!path) return;
    const name = prompt('Name of the new project (a folder with this name is made):', 'myhack');
    if (!name) return;
    try {
      await watchJob(await api('new', { folder: path, name }), async () => { app.tables = {}; go('characters'); });
    } catch (e) { toast(e.message, true); }
  }
  async function choosePort() {
    const { path } = await api('dialog', { kind: 'exe', title: 'Where is FE4.exe (the FE4 PC port)?' });
    if (!path) return;
    await api('settings', { port: path }); await refreshSession(); render();
  }

  await render();
  return { refresh: render };
}
