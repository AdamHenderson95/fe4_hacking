// Builder of the Holy War: app shell (session, navigation, saving, undo, build / test play, jobs).
import { homePage } from './pages/home.js';
import { charactersPage } from './pages/characters.js';
import { classesPage } from './pages/classes.js';
import { mapsPage } from './pages/maps.js';
import { eventsPage } from './pages/events.js';
import { itemsPage } from './pages/items.js';
import { armiesPage } from './pages/armies.js';
import { portraitsPage } from './pages/portraits.js';
import { spritesPage } from './pages/sprites.js';
import { battlePage } from './pages/battle.js';
import { skillsPage } from './pages/skills.js';
import { lovePage } from './pages/love.js';
import { soonPage } from './pages/soon.js';
import { musicPage } from './pages/music.js';

const TOKEN = location.hash.slice(1).split('/')[0] || sessionStorage.getItem('fe4studio-token') || '';
try { sessionStorage.setItem('fe4studio-token', TOKEN); } catch (e) { /* storage may be off */ }

// ---------------------------------------------------------------- API
export async function api(name, body) {
  const opt = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Studio-Token': TOKEN } };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch('/api/' + name, opt); }
  catch (e) { throw new Error('The editor stopped running. Start Builder of the Holy War again.'); }
  const data = await r.json().catch(() => ({ error: 'Unexpected reply from the editor.' }));
  if (!r.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

// ---------------------------------------------------------------- tiny DOM helper
export function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'text') e.textContent = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) e.append(k instanceof Node ? k : document.createTextNode(k));
  return e;
}

// ---------------------------------------------------------------- feedback
let toastTimer;
export function toast(msg, err) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = 'toast' + (err ? ' err' : ''); }, err ? 4200 : 2200);
}

// ---------------------------------------------------------------- session and tables
export const app = { session: null, tables: {}, page: null };

export async function refreshSession() {
  app.session = await api('session');
  const s = app.session;
  document.getElementById('projectName').textContent = s.projectName ? s.projectName : 'No project open';
  document.getElementById('dirty').hidden = !s.dirty;
  document.getElementById('btnUndo').disabled = !s.canUndo;
  document.getElementById('btnRedo').disabled = !s.canRedo;
  for (const id of ['btnSave', 'btnBuild', 'btnIps', 'btnPlay']) document.getElementById(id).disabled = !s.project;
  document.getElementById('btnSave').disabled = !s.dirty;
  document.title = (s.projectName ? s.projectName + (s.dirty ? ' (unsaved)' : '') + ' - ' : '') + 'Builder of the Holy War';
  return s;
}

export async function loadTables(names, force) {
  const need = names.filter(n => force || !app.tables[n]);
  if (need.length) Object.assign(app.tables, await api('tables', { names: need }));
  return app.tables;
}

// Change one field. Returns the stored value, or throws with a message for the person.
export async function setField(table, row, field, value) {
  const r = await api('set', { table, row, field, value });
  const t = app.tables[table];
  if (t) {
    t.rows[row][field] = r.value;
    if ('portrait' in r) t.rows[row]._portrait = r.portrait;
  }
  if (r.warning) toast(r.warning);
  await refreshSession();
  return r.value;
}

async function undoRedo(which) {
  const r = await api(which, {});
  if (!r.change) return;
  const c = r.change;
  const stale = c.tables.filter(t => app.tables[t]);
  if (stale.length) await loadTables(stale, true);
  await refreshSession();
  await app.page?.refresh?.(c);
  toast(which === 'undo' ? 'Undid a change' : 'Redid a change');
}

export async function save() {
  if (!app.session?.dirty) return;
  await api('save', {});
  await refreshSession();
  toast('Saved');
}

// ---------------------------------------------------------------- jobs (build, test play, new project)
export async function watchJob(job, onDone, keepOpen = false) {
  const box = document.getElementById('job');
  box.querySelector('.ipsreveal')?.remove();
  box.hidden = false; box.className = 'job';
  document.getElementById('jobTitle').textContent = job.what + '…';
  const log = document.getElementById('jobLog');
  for (;;) {
    log.textContent = job.log; log.scrollTop = log.scrollHeight;
    if (!job.running) break;
    await new Promise(r => setTimeout(r, 400));
    job = (await api('job')).job;
  }
  box.className = 'job ' + (job.ok ? 'ok' : 'err');
  document.getElementById('jobTitle').textContent = job.ok ? job.what + ': done' : job.what + ': stopped with an error';
  log.textContent = job.log; log.scrollTop = log.scrollHeight;
  if (job.ok && !keepOpen) setTimeout(() => { if (!box.matches(':hover')) box.hidden = true; }, 6000);
  await refreshSession();
  if (job.ok && onDone) onDone(job);
}

async function build() {
  try { await watchJob(await api('build', {})); }
  catch (e) { toast(e.message, true); }
}

async function ipsPatch() {
  document.querySelector('.modal.ipsdlg')?.remove();
  let info;
  try { info = await api('patchinfo'); } catch (e) { toast(e.message, true); return; }
  const name = h('input', { class: 'in', value: info.name, maxlength: 60, 'aria-label': 'Patch name' });
  const author = h('input', { class: 'in', value: info.author, maxlength: 80, placeholder: 'optional', 'aria-label': 'Made by' });
  const notes = h('textarea', { class: 'in', rows: 5, maxlength: 4000, placeholder: 'What your hack changes (optional; goes in the read-me)', 'aria-label': 'Description' }, info.notes);
  let out = info.out;
  const where = h('span', { class: 'ipswhere' }, out);
  const pick = h('button', { class: 'btn btn-line', type: 'button' }, 'Change…');
  pick.onclick = async () => {
    const r = await api('dialog', { kind: 'save', ext: '.ips', title: 'Save the IPS patch as', initial: (name.value.trim() || 'patch') + '.ips' }).catch(() => ({}));
    if (r.path) { out = r.path; where.textContent = out; }
  };
  name.oninput = () => {
    // follow the name until a place was picked by hand
    if (out === info.out || out.endsWith(`${info.name}.ips`)) {
      const dir = out.slice(0, Math.max(out.lastIndexOf('/'), out.lastIndexOf('\\')) + 1);
      out = dir + (name.value.trim() || 'patch') + '.ips'; where.textContent = out; info.out = out; info.name = name.value.trim();
    }
  };
  const ok = h('button', { class: 'btn btn-gilt' }, 'Create IPS patch');
  const modal = h('div', { class: 'modal ipsdlg', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Create IPS patch' },
    h('div', { class: 'modal-box' }, h('h2', {}, 'Create IPS patch'),
      h('p', { class: 'hint' }, 'Builds your hack and saves only the changes as an .ips file, with a .txt read-me that says which ROM it needs and how to apply it. Players apply it to their own ROM; the game itself is never in the patch.'),
      h('div', { class: 'itgrid wide' },
        h('label', { class: 'lbl' }, h('span', {}, 'Patch name'), name), h('label', { class: 'lbl' }, h('span', {}, 'Made by'), author)),
      h('label', { class: 'lbl ipsnotes' }, h('span', {}, 'Description'), notes),
      h('div', { class: 'ipsout' }, h('span', { class: 'lbl-t' }, 'Saved to'), where, pick),
      h('div', { class: 'modal-actions' }, h('button', { class: 'btn btn-line', onclick: () => modal.remove() }, 'Cancel'), ok)));
  ok.onclick = async () => {
    try {
      const job = await api('ipspatch', { name: name.value.trim(), author: author.value.trim(), notes: notes.value, out });
      modal.remove();
      await watchJob(job, () => {
        const box = document.getElementById('job');
        const btn = h('button', { class: 'btn btn-line ipsreveal', onclick: () => api('reveal', { path: out }).catch(e => toast(e.message, true)) }, 'Show the patch');
        box.querySelector('.ipsreveal')?.remove(); box.append(btn);
        toast('IPS patch created');
      }, true);
    } catch (e) { toast(e.message, true); }
  };
  modal.addEventListener('keydown', e => { if (e.key === 'Escape') modal.remove(); });
  document.body.append(modal);
  name.focus();
}

async function testPlay() {
  try {
    if (!app.session.port) {
      const { path } = await api('dialog', { kind: 'exe', title: 'Where is FE4.exe (the FE4 PC port)?' });
      if (!path) return;
      await api('settings', { port: path });
    }
    await watchJob(await api('testplay', {}));
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- pages
const PAGES = {
  home: { title: 'Project', make: homePage },
  characters: { title: 'Characters', make: charactersPage, needsProject: true },
  skills: { title: 'Skills', make: skillsPage, needsProject: true },
  love: { title: 'Love & children', make: lovePage, needsProject: true },
  classes: { title: 'Classes', make: classesPage, needsProject: true },
  maps: { title: 'Maps', make: mapsPage, needsProject: true },
  events: { title: 'Events & dialogue', make: eventsPage, needsProject: true },
  items: { title: 'Items, shops & villages', make: itemsPage, needsProject: true },
  armies: { title: 'Armies & AI', make: armiesPage, needsProject: true },
  portraits: { title: 'Portraits', make: portraitsPage, needsProject: true },
  sprites: { title: 'Map sprites', make: spritesPage, needsProject: true },
  battle: { title: 'Battle animations', make: battlePage, needsProject: true },
  music: { title: 'Music', make: musicPage, needsProject: true },
};

async function show() {
  let key = (location.hash.split('/')[1] || '').replace(/[^a-z]/g, '');
  if (!PAGES[key]) key = app.session?.project ? 'characters' : 'home';
  if (PAGES[key].needsProject && !app.session?.project) key = 'home';
  const p = PAGES[key];
  document.getElementById('pageTitle').textContent = p.title;
  for (const a of document.querySelectorAll('#nav a')) {
    if (a.dataset.page === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  const root = document.getElementById('page');
  root.replaceChildren();
  try {
    app.page = await p.make(root);
  } catch (e) {
    root.append(h('div', { class: 'empty' }, e.message));
  }
}

export function go(page) { location.hash = TOKEN + '/' + page; }

// ---------------------------------------------------------------- start
async function start() {
  for (const a of document.querySelectorAll('#nav a')) a.href = '#' + TOKEN + '/' + a.dataset.page;
  document.getElementById('btnSave').onclick = () => save().catch(e => toast(e.message, true));
  document.getElementById('btnBuild').onclick = build;
  document.getElementById('btnIps').onclick = ipsPatch;
  document.getElementById('btnPlay').onclick = testPlay;
  document.getElementById('btnUndo').onclick = () => undoRedo('undo').catch(e => toast(e.message, true));
  document.getElementById('btnRedo').onclick = () => undoRedo('redo').catch(e => toast(e.message, true));
  document.getElementById('jobClose').onclick = () => { document.getElementById('job').hidden = true; };
  addEventListener('keydown', e => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 's') { e.preventDefault(); save().catch(er => toast(er.message, true)); }
    else if ((e.ctrlKey || e.metaKey) && (k === 'y' || (k === 'z' && e.shiftKey))) {
      if (document.activeElement?.matches('input, textarea')) return;
      e.preventDefault(); undoRedo('redo').catch(er => toast(er.message, true));
    } else if ((e.ctrlKey || e.metaKey) && k === 'z') {
      if (document.activeElement?.matches('input, textarea')) return;
      e.preventDefault(); undoRedo('undo').catch(er => toast(er.message, true));
    } else if (e.key === 'F6') { e.preventDefault(); if (app.session?.project) testPlay(); }
  });
  addEventListener('beforeunload', e => { if (app.session?.dirty) { e.preventDefault(); e.returnValue = ''; } });
  addEventListener('hashchange', show);
  setInterval(() => api('ping', {}).catch(() => {}), 10000);
  api('ping', {}).catch(() => {});
  try {
    await refreshSession();
  } catch (e) {
    document.getElementById('page').append(h('div', { class: 'empty' }, e.message));
    return;
  }
  const job = app.session.job;
  if (job && job.running) watchJob(job);
  show();
}
start();
