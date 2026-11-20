// Builder of the Holy War page tour: opens every page, every chapter where a page has a chapter picker,
// and the main map cards, and reports page errors, console errors and failed requests.
//   node dev/pagetour.js URL SHOTDIR        (URL = the editor's address with its #token)
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const [url, shots] = process.argv.slice(2);
  fs.mkdirSync(shots, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1500, height: 950 } });
  const problems = [];
  let where = 'start';
  p.on('pageerror', e => problems.push(`${where}: page error: ${e.message}`));
  p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) problems.push(`${where}: console: ${m.text()}`); });
  p.on('response', r => { if (r.status() >= 400) problems.push(`${where}: HTTP ${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`); });
  p.on('dialog', d => { problems.push(`${where}: browser dialog: ${d.message()}`); d.dismiss(); });
  await p.goto(url); await p.waitForTimeout(2500);
  const token = url.split('#')[1];
  const go = async page => { where = page; await p.evaluate(h => { location.hash = h; }, token + '/' + page); await p.waitForTimeout(3500); };
  const closeCards = async () => { for (let i = 0; i < 3; i++) { await p.keyboard.press('Escape'); await p.waitForTimeout(150); } };
  const pages = ['home', 'characters', 'skills', 'love', 'classes', 'maps', 'events', 'items', 'armies',
    'portraits', 'sprites', 'battle', 'music', 'title'];
  for (const pg of pages) {
    await go(pg);
    await p.screenshot({ path: `${shots}/${pg}.png` });
    // chapter pickers: a <select> offering the Prologue
    const sel = await p.$$eval('select', ss => ss.findIndex(s => [...s.options].some(o => /Prologue/.test(o.text))));
    if (sel >= 0) {
      const n = await p.$$eval('select', (ss, i) => ss[i].options.length, sel);
      for (let k = 0; k < n; k++) {
        where = `${pg} chapter option ${k}`;
        await p.$$eval('select', (ss, [i, k]) => { ss[i].selectedIndex = k; ss[i].dispatchEvent(new Event('change', { bubbles: true })); }, [sel, k]);
        await p.waitForTimeout(pg === 'maps' ? 3000 : 1500);
        if (pg === 'maps') {
          for (const label of ['Win condition', 'Lose conditions', 'Opening scene', 'Chapter title']) {
            const btn = await p.$(`button:has-text("${label}")`);
            if (btn) { where = `${pg} ch option ${k} ${label}`; await btn.click().catch(() => {}); await p.waitForTimeout(1200); await closeCards(); }
          }
        }
      }
    }
    // tabs inside a page (buttons with role=tab)
    const tabs = await p.$$('[role=tab]');
    for (let t = 0; t < tabs.length && t < 8; t++) {
      const name = (await tabs[t].innerText().catch(() => '')).trim().slice(0, 30);
      where = `${pg} tab ${name}`;
      await tabs[t].click().catch(() => {});
      await p.waitForTimeout(1500);
    }
    if (tabs.length) await p.screenshot({ path: `${shots}/${pg}_lasttab.png` });
  }
  // maps: every right-click menu item on an empty cell, a castle, a village and a unit (Prologue)
  await go('maps');
  await p.$$eval('select', ss => { const s = ss.find(s => [...s.options].some(o => /Prologue/.test(o.text))); s.selectedIndex = 0; s.dispatchEvent(new Event('change', { bubbles: true })); });
  await p.waitForTimeout(3000);
  const cellAt = async (x, y) => p.evaluate(([x, y]) => {
    const v = document.querySelector('.mview'), st = v.firstElementChild;
    const cw = st.getBoundingClientRect().width / 64;
    v.scrollLeft = x * cw - v.clientWidth / 2; v.scrollTop = y * cw - v.clientHeight / 2;
    const r = st.getBoundingClientRect();
    return [r.left + (x + 0.5) * cw, r.top + (y + 0.5) * cw];
  }, [x, y]);
  const menuAt = async (x, y) => {
    await closeCards();
    const [px, py] = await cellAt(x, y);
    await p.mouse.click(px, py, { button: 'right' }); await p.waitForTimeout(500);
    return p.$$eval('.mctx button:not([disabled])', bs => bs.map(x => x.textContent.trim()));
  };
  const skip = /^(Remove|Delete|Hide|Show all|Cut)/;
  for (const [x, y, tag] of [[45, 20, 'empty cell'], [60, 10, 'Chalphy castle'], [61, 12, 'unit near Chalphy']]) {
    const items = await menuAt(x, y);
    console.log(`menu at ${tag}: ${items.join(' | ')}`);
    for (let i = 0; i < items.length; i++) {
      if (skip.test(items[i])) continue;
      where = `maps ${tag} > ${items[i]}`;
      await menuAt(x, y);
      const bs = await p.$$('.mctx button:not([disabled])');
      if (!bs[i]) continue;
      await bs[i].click().catch(e => problems.push(`${where}: click failed ${e.message}`));
      await p.waitForTimeout(1500);
      await p.screenshot({ path: `${shots}/card_${tag.replace(/ /g, '_')}_${i}.png` });
    }
  }
  await closeCards();
  // the chapter timeline for every chapter
  await go('events');
  const evSel = await p.$$eval('select', ss => ss.findIndex(s => [...s.options].some(o => /Prologue/.test(o.text))));
  const nEv = await p.$$eval('select', (ss, i) => ss[i].options.length, evSel);
  await p.click('button:has-text("Chapter timeline")'); await p.waitForTimeout(3000);
  for (let k = 0; k < nEv; k++) {
    where = `events timeline chapter option ${k}`;
    await p.$$eval('select', (ss, [i, k]) => { ss[i].selectedIndex = k; ss[i].dispatchEvent(new Event('change', { bubbles: true })); }, [evSel, k]);
    await p.waitForSelector('.tl', { timeout: 120000 }).catch(() => problems.push(`${where}: no timeline`));
    await p.waitForTimeout(500);
  }
  await p.screenshot({ path: `${shots}/timeline.png` });
  // Check my hack
  where = 'Check my hack';
  await p.click('#btnCheck');
  await p.waitForSelector('.check-items, .check-ok, .check-fail', { timeout: 180000 }).catch(() => problems.push('Check my hack: no result'));
  console.log('check:', (await p.$eval('.checklist', e => e.innerText).catch(() => '?')).split('\n')[0]);
  await p.screenshot({ path: `${shots}/check.png` });
  await p.keyboard.press('Escape');
  console.log(`${problems.length} problem(s)`);
  for (const x of [...new Set(problems)]) console.log('  ' + x);
  await b.close();
  process.exit(problems.length ? 1 : 0);
})();
