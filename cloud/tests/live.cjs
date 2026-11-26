// The live site, as a visitor sees it before signing in: the private-beta front page, phones, dark mode, the files
// the page needs, the security headers, and that the rules let a stranger read nothing.
// It changes nothing. Real Google sign-in cannot be automated, so the signed-in pages are covered by e2e.cjs.
//   node cloud/tests/live.cjs                 (needs Playwright: npm i -g playwright)
//   BASE=https://your-project.web.app node cloud/tests/live.cjs
const { chromium } = require('playwright');
const BASE = (process.env.BASE || 'https://econova-digest.web.app').replace(/\/$/, '');
const results = [];
const ok = (name, pass, note = '') => { results.push(!!pass); console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${note ? '  (' + note + ')' : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  const open = async (opts = {}) => {
    // an Indian locale on purpose: it is where number formats went wrong before ("$3.00LCr")
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, locale: 'en-IN', ...opts });
    const page = await ctx.newPage();
    page.on('pageerror', e => problems.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error' && !/favicon/i.test(m.text())) problems.push('console: ' + m.text().slice(0, 200)); });
    await page.goto(BASE + '/'); await page.waitForSelector('.land, .shell', { timeout: 20000 });
    return page;
  };
  const wait = (p, ms = 800) => p.waitForTimeout(ms);
  const sideways = p => p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);

  // ---- 1. the files and headers
  const req = await (await browser.newContext()).request;
  const head = await req.get(BASE + '/');
  const h = head.headers();
  ok('the page is served, with the security headers', head.ok() && h['x-frame-options'] === 'DENY' && h['x-content-type-options'] === 'nosniff');
  const html = await head.text();
  ok('share preview: title, description and image', /og:image" content="https:\/\/[^"]+\/og\.png"/.test(html) && /twitter:card/.test(html) && /<meta name="description"/.test(html));
  for (const [path, type] of [['/og.png', 'image/png'], ['/icon-180.png', 'image/png'], ['/icon-512.png', 'image/png'], ['/icon.svg', 'image/svg'],
    ['/vendor/inter-var-latin.woff2', 'font/woff2'], ['/manifest.webmanifest', 'manifest'], ['/symbols.json', 'json'], ['/styles.css', 'css']]) {
    const r = await req.get(BASE + path);
    ok(`${path} is there`, r.ok() && (r.headers()['content-type'] || '').includes(type.split('/').pop()), `${r.status()} ${r.headers()['content-type'] || ''}`);
  }
  const symbols = await (await req.get(BASE + '/symbols.json')).json();
  ok('the search list is the full US list', symbols.length > 8000, `${symbols.length} symbols`);
  for (const page of ['/privacy.html', '/terms.html']) {
    const t = await (await req.get(BASE + page)).text();
    ok(`${page} has a real contact address`, !t.includes('CONTACT_EMAIL') && /mailto:[^"@]+@[^"]+"/.test(t));
  }

  // ---- 2. the front page: a private beta shows a stranger no live data
  const p = await open();
  await wait(p, 1500);
  const front = await p.locator('.land').textContent();
  ok('front page: private beta, members sign in, no live data', front.includes('Private beta') && front.includes('Member sign in')
    && await p.locator('.peek tbody tr').count() === 0 && await p.locator('text=See a live example').count() === 0);
  ok('the Inter typeface is loaded', await p.evaluate(() => document.fonts.check('16px Inter')));
  ok('front page: what members see, how it works, honest by design, a closing call', await p.locator('.member-list > div').count() === 5
    && await p.locator('#how .card').count() === 3 && await p.locator('.honest h3').count() === 3 && await p.locator('.cta-band .gbtn').count() === 1);
  ok('the legal pages are linked', await p.locator('footer a[href="/privacy.html"]').count() === 1 && await p.locator('footer a[href="/terms.html"]').count() === 1);

  // ---- 3. what a stranger may read: nothing (members only, enforced by the database rules)
  const fire = (fn, arg) => p.evaluate(async ([src, a]) => {
    const fs = await import('/vendor/firebase-firestore-lite.js'), app = (await import('/vendor/firebase-app.js')).getApp(), db = fs.getFirestore(app);
    try { return await (new Function('fs', 'db', 'a', `return (${src})(fs, db, a)`))(fs, db, a); } catch (e) { return 'DENIED:' + (e.code || e.message); }
  }, [fn.toString(), arg]);
  const refused = async (what, fn) => ok(`signed out: ${what} cannot be read`, String(await fire(fn)).startsWith('DENIED'));
  await refused('the example', async (fs, db) => (await fs.getDoc(fs.doc(db, 'public', 'demo'))).exists());
  await refused('stock cards', async (fs, db) => (await fs.getDoc(fs.doc(db, 'stocks', 'AAPL'))).exists());
  await refused('charts', async (fs, db) => (await fs.getDoc(fs.doc(db, 'charts', 'AAPL'))).exists());
  await refused('market pages', async (fs, db) => (await fs.getDoc(fs.doc(db, 'market', 'overview'))).exists());
  await refused('the members list', async (fs, db) => (await fs.getDocs(fs.collection(db, 'members'))).size);
  await refused('accounts', async (fs, db) => (await fs.getDocs(fs.collection(db, 'users'))).size);
  await refused('the engine’s records', async (fs, db) => (await fs.getDoc(fs.doc(db, 'engine', 'state'))).exists());
  problems.splice(0);   // the refusals above log errors on purpose

  // ---- 4. phones and dark (the pages behind sign-in are covered by e2e.cjs against the emulators)
  const phone = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await wait(phone, 1200);
  ok('phone: the front page does not scroll sideways', !(await sideways(phone)));
  const dark = await open({ colorScheme: 'dark' });
  ok('dark: follows the device', (await dark.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(13, 19, 28)');

  ok('no errors in the browser', !problems.length, problems.slice(0, 3).join(' | '));
  await browser.close();
  const passed = results.filter(Boolean).length;
  console.log(`\n${passed} of ${results.length} passed`);
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
