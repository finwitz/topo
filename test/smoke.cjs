// Smoke-test a built Topo map in headless Chromium: console errors, frame rate, screenshots.
// usage: node test/smoke.cjs maps/<name>/dist/index.html out/ [--d3 path/to/d3.min.js]
//   --d3 serves a local copy of d3 in place of the CDN (for machines without internet access).
//   TOPO_FPS_FLOOR (default 30) is the lowest desktop frame rate that passes; 0 logs the rate only, as
//   continuous integration does, since a headless run with no screen is throttled.
// needs: npm i -D playwright  (or a global Playwright install with NODE_PATH set)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const FPS_FLOOR = (v => (Number.isFinite(v) ? v : 30))(Number(process.env.TOPO_FPS_FLOOR ?? 30));
const page_ = args[0], out = args[1] || 'topo-smoke';
const d3i = args.indexOf('--d3');
const D3 = d3i > -1 ? fs.readFileSync(args[d3i + 1]) : null;
if (!page_) { console.error('usage: node test/smoke.cjs PAGE.html OUTDIR [--d3 d3.min.js]'); process.exit(2); }
if (!fs.existsSync(page_)) { console.error(`smoke: no page at ${path.resolve(page_)}`); process.exit(2); }
fs.mkdirSync(out, { recursive: true });

const LAUNCH_SKIP_CODE = 77;

(async () => {
  let browser;
  try {
    browser = await chromium.launch();
  } catch (e) {
    const firstLine = String((e && e.message) || e || '').split(/\r?\n/).find(l => l.trim()) || 'unknown error';
    const cmd = `node test/smoke.cjs ${page_} ${out}${d3i > -1 ? ` --d3 ${args[d3i + 1]}` : ''}`;
    console.error(`smoke: could not start headless Chromium (${firstLine}); run outside the sandbox: ${cmd}`);
    process.exit(LAUNCH_SKIP_CODE);
  }
  let failed = false;
  const views = [
    ['desktop-light', { width: 1440, height: 860 }, 'light'],
    ['desktop-dark', { width: 1440, height: 860 }, 'dark'],
    ['phone', { width: 390, height: 780 }, 'light'],
  ];
  for (const [name, viewport, scheme] of views) {
    // the phone view emulates a real device, so the page's viewport tag is honoured as on a phone
    const phone = name === 'phone' ? { deviceScaleFactor: 2, isMobile: true, hasTouch: true } : { deviceScaleFactor: 1 };
    const ctx = await browser.newContext({ viewport, colorScheme: scheme, ...phone });
    const page = await ctx.newPage();
    const problems = [];
    page.on('console', m => { if (['error', 'warning'].includes(m.type())) problems.push(m.text()); });
    page.on('pageerror', e => problems.push('page error: ' + e.message));
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    // wait for the first painted frame: on a cold browser the first load can take longer than the pause below
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    await page.waitForTimeout(400);
    const shot = async f => page.screenshot({ path: path.join(out, `${name}-${f}.png`) });
    await shot('overview');
    const desktop = name !== 'phone';
    if (desktop) await page.screenshot({ path: path.join(out, `${name}-bar.png`), clip: { x: 0, y: 0, width: viewport.width, height: 56 } });
    // the stat strip says what the page data says (counted here independently), and only for what it shows
    const stats = await page.evaluate(() => {
      const { NODES, EDGES } = window.__topo, got = window.__topo.stats();
      const want = { apps: NODES.filter(n => !n.p && n.kind === 'app').length, boxes: NODES.length, conn: EDGES.filter(e => !e.idea).length,
        unfinished: NODES.filter(n => ['partial', 'stub', 'planned'].includes(n.status)).length,
        docs: NODES.filter(n => n.source === 'docs').length, ext: NODES.filter(n => n.kind === 'external').length };
      const shown = [...document.querySelectorAll('#stats [data-stat]')].map(b => [b.dataset.stat, Number(b.querySelector('b').textContent.replace(/,/g, ''))]);
      const bad = Object.keys(want).filter(k => got[k] !== want[k]).concat(shown.filter(([k, v]) => v !== want[k]).map(([k]) => k + ' (shown)'));
      return { bad, particles: window.__topo.particles() };
    });
    if (stats.bad.length) problems.push('stat strip disagrees with the page data: ' + stats.bad.join(', '));
    if (stats.particles > 24 * 8) problems.push(`${stats.particles} particles: more than the cap of 24 lines x 8`);
    // biggest app, then its biggest subsystem, then a deep card with code
    const ids = await page.evaluate(() => {
      const N = window.__topo.NODES;
      const app = N.filter(n => !n.p).sort((a, b) => b.desc - a.desc)[0];
      const sub = app.kids.slice().sort((a, b) => b.desc - a.desc)[0];
      const leaf = N.find(n => !n.kids.length && n.code) || N.find(n => !n.kids.length && n.depth >= 3);
      // a mid-zoom card: inside a box whose parts carry badges, chips and their connections in and out
      const conn = n => n.cIn + n.cOut;
      const card = N.filter(n => n.depth === 2 && n.kids.length >= 4).sort((a, b) => conn(b) - conn(a))[0];
      const busy = N.filter(n => n.depth >= 2 && n.p).sort((a, b) => conn(b) - conn(a))[0];
      return { app: app.id, sub: sub && sub.id, card: card && card.id, leaf: leaf && leaf.id, busy: busy && busy.id, flow: window.__topo.FLOWS[0] && window.__topo.FLOWS[0].id };
    });
    for (const [label, id] of [['app', ids.app], ['subsystem', ids.sub], ['card', ids.card], ['code', ids.leaf]]) {
      if (!id) continue;
      await page.evaluate(i => window.__topo.zoomTo(i), id);
      await page.waitForTimeout(400);
      await shot(label);
    }
    // a focused box: its lines lit, with particles where motion is allowed
    if (ids.busy) {
      await page.evaluate(i => { window.__topo.zoomTo(window.__topo.byId.get(i).p.id); window.__topo.select(i); }, ids.busy);
      await page.waitForTimeout(600);
      await shot('focus');
      const n = await page.evaluate(() => window.__topo.particles());
      if (n > 24 * 8) problems.push(`${n} particles on a focused box: more than the cap`);
      await page.evaluate(() => window.__topo.select(null));
    }
    if (ids.flow) { await page.evaluate(f => window.__topo.startFlow(f), ids.flow); await page.waitForTimeout(1200); await shot('flow'); }
    // the Features view, where the map has a feature tree: every feature drawn, no sideways scroll,
    // Escape closes it, and a feature lights up its boxes on the map
    if (await page.evaluate(() => !document.querySelector('#btn-features').hidden)) {
      if (ids.flow) await page.keyboard.press('Escape');
      await page.click('#btn-features');
      await page.waitForTimeout(400);
      await shot('features');
      const fv = await page.evaluate(() => {
        const data = JSON.parse(document.getElementById('topo-data').textContent), f = document.getElementById('fview');
        return { want: data.features.length - data.features.filter(x => !x.parent && data.features.some(k => k.parent === x.id)).length,
          got: document.querySelectorAll('.fv-leaf[data-feat]').length, overflow: f.scrollWidth > f.clientWidth + 1,
          lines: document.querySelectorAll('#fv-lines path').length, areas: document.querySelectorAll('.fv-area').length };
      });
      if (fv.got !== fv.want) problems.push(`the Features view draws ${fv.got} features of ${fv.want}`);
      if (fv.overflow) problems.push('the Features view scrolls sideways');
      if (desktop && fv.lines < fv.areas) problems.push(`the Features view draws ${fv.lines} lines for ${fv.areas} areas`);
      await page.keyboard.press('Escape');
      if (!(await page.evaluate(() => document.getElementById('fview').hidden))) problems.push('Escape leaves the Features view open');
      await page.click('#btn-features');
      await page.click('.fv-leaf[data-feat]');
      await page.waitForTimeout(800);
      const lit = await page.evaluate(() => !document.getElementById('capbar').hidden && /Feature/.test(document.getElementById('capbar').textContent));
      if (!lit) problems.push('a feature does not light up its boxes on the map');
      await shot('feature-on-map');
      await page.keyboard.press('Escape');
    }
    const fps = await page.evaluate(async () => {
      const t0 = performance.now(); let frames = 0;
      await new Promise(res => { const tick = () => { frames++; window.dispatchEvent(new Event('resize')); performance.now() - t0 < 1000 ? requestAnimationFrame(tick) : res(); }; requestAnimationFrame(tick); });
      return frames;
    });
    // the view switch, where the map has sibling views: every link there, exactly one marked current
    const views = await page.evaluate(() => { const a = [...document.querySelectorAll('#views a')]; return { n: a.length, current: a.filter(x => x.getAttribute('aria-current') === 'page').length, hidden: document.querySelector('#views').hidden, overflow: document.querySelector('.bar').scrollWidth > document.querySelector('.bar').clientWidth }; });
    if (!views.hidden && (views.n < 2 || views.current !== 1)) problems.push(`view switch: ${views.n} links, ${views.current} current`);
    if (views.overflow) problems.push('the header overflows its width');
    if (desktop && FPS_FLOOR && fps < FPS_FLOOR) problems.push(`${fps} frames/s while re-rendering, under the floor of ${FPS_FLOOR}`);
    console.log(`${name}: ${problems.length ? problems.length + ' problem(s): ' + problems.join(' | ') : 'no console errors'}; ~${fps} frames/s while re-rendering${FPS_FLOOR ? '' : ' (no floor)'}${views.hidden ? '' : `; view switch with ${views.n} views`}`);
    if (problems.length) failed = true;
    await ctx.close();
  }
  // P1: the Boundaries rail, a replay with its log, a command, the location line and a PNG of the view
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 } });
    const page = await ctx.newPage();
    const problems = [];
    page.on('pageerror', e => problems.push('page error: ' + e.message));
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    await page.click('#btn-bounds'); await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(out, 'boundaries.png') });
    const dock = await page.evaluate(() => document.querySelector('#dock-body').innerText);
    // only the map's own facts: no repository addresses, no rules
    if (!/Scope/.test(dock) || !/Evidence/.test(dock)) problems.push('the Boundaries rail is missing its scope or evidence');
    if (/https?:\/\/|rules\.json|generalized\.json/.test(dock)) problems.push('the Boundaries rail shows an address or a rules file');
    await page.keyboard.press('Escape');
    if (!(await page.evaluate(() => document.querySelector('#dock').hidden))) problems.push('Escape leaves the Boundaries rail open');
    // the level rail has one level per tier the map has, each named
    const rail = await page.evaluate(() => {
      let deepest = 0;
      for (const n of window.__topo.NODES) deepest = Math.max(deepest, n.depth);
      return { levels: [...document.querySelectorAll('#rail button .name')].map(x => x.textContent), want: deepest + 2 };
    });
    if (rail.levels.length !== rail.want || rail.levels.some(l => !l || /undefined/.test(l)))
      problems.push(`the level rail shows ${JSON.stringify(rail.levels)} for a map ${rail.want} levels deep`);
    if (rail.levels.some((l, i) => i && l === rail.levels[i - 1])) problems.push(`the level rail repeats a name: ${JSON.stringify(rail.levels)}`);
    const loc = await page.evaluate(() => window.__topo.location());
    if (!/^topo · (.+ · )?Ecosystem · \S/.test(loc)) problems.push(`location line reads ${JSON.stringify(loc)}`);
    const featured = await page.evaluate(() => window.__topo.FLOWS.some(f => f.featured));
    if (featured) {
      await page.evaluate(() => window.__topo.replay());
      await page.waitForTimeout(4700);
      const on = await page.evaluate(() => window.__topo.flowState());
      await page.screenshot({ path: path.join(out, 'replay.png') });
      if (!on.replay || on.step < 1 || on.log < 2) problems.push(`replay did not move on by itself: ${JSON.stringify(on)}`);
      await page.keyboard.press(' '); await page.waitForTimeout(200);
      const spaced = await page.evaluate(() => window.__topo.flowState());
      if (spaced.step !== on.step + 1 && spaced.on) problems.push(`Space did not move the replay on: ${JSON.stringify(spaced)}`);
      await page.keyboard.press('Escape');
      if ((await page.evaluate(() => window.__topo.flowState())).on) problems.push('Escape did not end the replay');
      const manual = await page.evaluate(() => { window.__topo.startFlow(window.__topo.FLOWS[0].id); return window.__topo.flowState(); });
      await page.waitForTimeout(4300);
      const still = await page.evaluate(() => window.__topo.flowState());
      if (!manual.on || manual.replay || still.step !== 0) problems.push(`a manual flow moved by itself: ${JSON.stringify(still)}`);
      await page.keyboard.press('Escape');
    }
    await page.keyboard.press('/'); await page.keyboard.type('theme dark'); await page.keyboard.press('Enter');
    if ((await page.evaluate(() => document.documentElement.dataset.theme)) !== 'dark') problems.push('the command "theme dark" did not set the theme');
    await page.evaluate(() => window.__topo.select(null));
    const png = await page.evaluate(() => window.__topo.exportBlob());
    if (!png || png.type !== 'image/png' || png.size < 5000) problems.push(`PNG export: ${JSON.stringify(png)}`);
    console.log(`boundaries, replay, commands, export: ${problems.length ? 'FAILED ' + problems.join(' | ') : `ok (${png.name}, ${Math.round(png.size / 1024)} KB)`}`);
    if (problems.length) failed = true;
    await ctx.close();
  }
  // the theme control: light, dark, then back to the system's, kept across a reload
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 }, colorScheme: 'dark' });
    const page = await ctx.newPage();
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    const state = () => page.evaluate(() => ({ attr: document.documentElement.getAttribute('data-theme'), paper: getComputedStyle(document.documentElement).getPropertyValue('--paper').trim(), kept: localStorage.getItem('topo:theme') }));
    const seen = [];
    seen.push(await state());                                   // system, emulated dark
    await page.click('#theme-btn'); seen.push(await state());   // light
    await page.click('#theme-btn'); seen.push(await state());   // dark
    await page.reload(); await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0); seen.push(await state());
    await page.click('#theme-btn'); seen.push(await state());   // system again
    await page.reload(); await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0); seen.push(await state());
    const [sys, light, dark, reloaded, back, after] = seen;
    // the system's theme is emulated dark, so its paper is the dark theme's, whatever the palette's values
    const ok = sys.attr === null && sys.paper === dark.paper && light.attr === 'light' && light.paper !== dark.paper && dark.attr === 'dark' &&
      reloaded.attr === 'dark' && reloaded.kept === '"dark"' && back.attr === null && back.kept === null && after.attr === null && after.paper === dark.paper;
    console.log(`theme: ${ok ? 'system, light, dark, kept across a reload, back to the system' : 'FAILED ' + JSON.stringify(seen)}`);
    if (!ok) failed = true;
    await ctx.close();
  }
  // reduced motion: no particles, no frames once the view is still, and a fly-to that lands at once
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    await page.waitForTimeout(600);
    const still = await page.evaluate(async () => {
      const f0 = window.__topo.frames(); await new Promise(r => setTimeout(r, 1000));
      const idle = window.__topo.frames() - f0, p0 = window.__topo.particles();
      const N = window.__topo.NODES, busy = N.filter(n => n.depth >= 2 && n.p).sort((a, b) => (b.cIn + b.cOut) - (a.cIn + a.cOut))[0];
      const k0 = window.__topo.state().k; window.__topo.flyTo(busy.p.id); const k1 = window.__topo.state().k;
      window.__topo.select(busy.id);
      await new Promise(r => setTimeout(r, 800));
      const f1 = window.__topo.frames(); await new Promise(r => setTimeout(r, 1000));
      return { idle, p0, landed: k1 !== k0 && window.__topo.state().k === k1, p1: window.__topo.particles(), idle2: window.__topo.frames() - f1 };
    });
    const ok = still.p0 === 0 && still.p1 === 0 && still.idle <= 2 && still.idle2 <= 2 && still.landed;
    console.log(`reduced motion: ${ok ? 'no particles, no frames while still, fly-to lands at once' : 'FAILED ' + JSON.stringify(still)}`);
    if (!ok) failed = true;
    await ctx.close();
  }
  // engagement view: steps in process order and lined up across rows, the capability
  // highlight and the comparison in Insights (maps without a process skip this)
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 } });
    const page = await ctx.newPage();
    const problems = [];
    page.on('pageerror', e => problems.push('page error: ' + e.message));
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    const eng = await page.evaluate(() => {
      const N = window.__topo.NODES, rows = N.filter(n => n.stepRow);
      if (rows.length < 2) return null;
      const cols = new Map();
      for (const r of rows) for (const k of r.kids) { if (!cols.has(k.stepIx)) cols.set(k.stepIx, []); cols.get(k.stepIx).push([k.x0, k.x1]); }
      const aligned = [...cols.values()].every(xs => xs.every(([a, b]) => Math.abs(a - xs[0][0]) < 0.5 && Math.abs(b - xs[0][1]) < 0.5));
      const ordered = rows.every(r => r.kids.every(k => r.kids.every(o => (o.stepIx < k.stepIx) === (o.x0 < k.x0) || o === k)));
      // engagement actions get the comparison in Insights; any box with capabilities can be highlighted
      const action = N.find(n => n.phase && n.kind !== 'group' && n.capabilities && n.capabilities.length);
      const tagged = action || N.find(n => n.capabilities && n.capabilities.length);
      const lit = tagged ? window.__topo.highlight(tagged.capabilities[0]) : 1;
      window.__topo.highlight(null);
      document.querySelector('#btn-insights').click();
      const ins = document.querySelector('#insights-body').innerText;
      document.querySelector('#insights-close').click();
      return { rows: rows.length, aligned, ordered, lit, actions: !!action, insights: !action || (/Steps covered/i.test(ins) && /Across engagements/i.test(ins)) };
    });
    if (eng) {
      const matrix = await page.evaluate(() => { const r = window.__topo.NODES.find(n => n.matrix); return r && r.id; });
      if (matrix) { await page.evaluate(i => window.__topo.zoomTo(i), matrix); await page.waitForTimeout(400); await page.screenshot({ path: path.join(out, 'engagements.png') }); }
      const ok = eng.aligned && eng.ordered && eng.lit > 0 && eng.insights && !problems.length;
      console.log(`step rows: ${ok ? `${eng.rows} in process order and lined up, highlight lights ${eng.lit} boxes${eng.actions ? ', comparison in Insights' : ''}` : `FAILED ${JSON.stringify(eng)} ${problems.join(' | ')}`}`);
      if (!ok) failed = true;
    }
    await ctx.close();
  }
  // a page that opens small (a pane still growing) fits the whole map once it grows,
  // and a view someone has moved keeps its zoom through a resize
  {
    const ctx = await browser.newContext({ viewport: { width: 320, height: 240 } });
    const page = await ctx.newPage();
    if (D3) await page.route('https://cdnjs.cloudflare.com/**', r => r.fulfill({ body: D3, contentType: 'application/javascript' }));
    await page.goto('file://' + path.resolve(page_));
    await page.waitForFunction(() => window.__topo && window.__topo.state().visible > 0, null, { timeout: 15000 });
    await page.setViewportSize({ width: 1440, height: 860 });
    await page.waitForTimeout(300);
    const grown = await page.evaluate(() => { const k = window.__topo.state().k; window.__topo.goHome(); return k / window.__topo.state().k; });
    const app = await page.evaluate(() => window.__topo.NODES.filter(n => !n.p).sort((a, b) => b.desc - a.desc)[0].id);
    await page.evaluate(i => window.__topo.zoomTo(i), app);
    // a moved view stays on its box through a resize (a re-flow may change the zoom, not what is in view)
    const seen = i => { const n = window.__topo.byId.get(i), s = window.__topo.state(), cx = (s.w / 2 - s.x) / s.k, cy = (s.h / 2 - s.y) / s.k;
      return { inside: cx >= n.x0 && cx <= n.x1 && cy >= n.y0 && cy <= n.y1, width: (n.x1 - n.x0) * s.k, home: s.k <= s.kFit * 1.1 }; };
    const before = await page.evaluate(seen, app);
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.waitForTimeout(300);
    const after = await page.evaluate(seen, app);
    const kept = after.width / before.width;
    const ok = Math.abs(grown - 1) < 0.02 && after.inside && !after.home && kept > 0.75 && kept < 1.33;
    console.log(`opened small: ${ok ? 'fits the whole map once grown, keeps a moved view' : `FAILED (fit ratio ${grown.toFixed(2)}, moved view: ${JSON.stringify(after)}, width ratio ${kept.toFixed(2)})`}`);
    if (!ok) failed = true;
    await ctx.close();
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
