// The live site, as a visitor sees it before signing in: the front page, the example, every example stock, the help
// page, phones, dark mode, the files the page needs, the security headers and what the rules let a stranger read.
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

  // ---- 2. the front page
  const p = await open();
  await p.waitForSelector('.peek tbody tr', { timeout: 20000 }); await wait(p, 1500);
  ok('front page: today\'s example signals', await p.locator('.peek tbody tr').count() >= 5);
  const fontOk = await p.evaluate(() => document.fonts.check('16px Inter'));
  ok('the Inter typeface is loaded', fontOk);
  ok('front page: the proof numbers', await p.locator('.proof:not([hidden]) b').count() >= 3, await p.locator('.proof').textContent().catch(() => ''));
  ok('front page: one stock with everything behind its signal', await p.locator('section.working:not([hidden]) .factors .chip').count() >= 2
    && await p.locator('section.working blockquote').count() === 2);
  const sayLine = await p.locator('section.working .signal p').first().textContent().catch(() => '');
  const conf = parseInt(await p.locator('section.working .ring b').textContent().catch(() => '0'), 10);
  ok('its words match its confidence', !/clearly/i.test(sayLine) || conf >= 70, `${conf}%: ${sayLine}`);
  ok('front page: how it works, honest by design, a closing call', await p.locator('#how .card').count() === 3 && await p.locator('.honest h3').count() === 3 && await p.locator('.cta-band .gbtn').count() === 1);
  ok('the legal pages are linked', await p.locator('footer a[href="/privacy.html"]').count() === 1 && await p.locator('footer a[href="/terms.html"]').count() === 1);

  // ---- 3. what a stranger may read
  const fire = (fn, arg) => p.evaluate(async ([src, a]) => {
    const fs = await import('/vendor/firebase-firestore-lite.js'), app = (await import('/vendor/firebase-app.js')).getApp(), db = fs.getFirestore(app);
    try { return await (new Function('fs', 'db', 'a', `return (${src})(fs, db, a)`))(fs, db, a); } catch (e) { return 'DENIED:' + (e.code || e.message); }
  }, [fn.toString(), arg]);
  ok('signed out: the public example can be read', (await fire(async (fs, db) => (await fs.getDoc(fs.doc(db, 'public', 'demo'))).exists())) === true);
  ok('signed out: stock cards cannot be read', String(await fire(async (fs, db) => (await fs.getDoc(fs.doc(db, 'stocks', 'AAPL'))).exists())).startsWith('DENIED'));
  ok('signed out: accounts cannot be listed', String(await fire(async (fs, db) => (await fs.getDocs(fs.collection(db, 'users'))).size)).startsWith('DENIED'));
  ok('signed out: the engine\'s records are closed', String(await fire(async (fs, db) => (await fs.getDoc(fs.doc(db, 'engine', 'state'))).exists())).startsWith('DENIED'));
  problems.splice(0);   // the refusals above log errors on purpose

  // ---- 4. the example
  await p.click('.hero-l >> text=See a live example'); await p.waitForSelector('.shell'); await wait(p, 2000);
  const tickers = await p.locator('.card.flush tbody tr.link .badge').allTextContents();
  ok('example: the dashboard lists the starter stocks', tickers.length >= 5, tickers.join(' '));
  ok('example: the market card is there', await p.locator('.card h2', { hasText: 'Market' }).count() === 1);
  ok('example: a sign-in banner', await p.locator('.banner').count() === 1);
  for (const t of tickers) {
    await p.evaluate(x => { location.hash = '#/s/' + x; }, t); await p.waitForSelector('.signal', { timeout: 15000 }); await wait(p, 600);
    const text = await p.locator('.page').textContent();
    const divText = (text.match(/Dividend yield([^A-Z]*?)(Sector|None)/) || [])[1] || '';
    const div = parseFloat(divText);
    const c = parseInt(await p.locator('.signal .ring b').textContent(), 10), line = await p.locator('.signal .ringrow p').first().textContent();
    const bad = [];
    if (!['Should I invest?', 'Wall Street', 'Key numbers', 'Bulls say', 'Bears say'].every(x => text.includes(x))) bad.push('missing a card');
    if (/LCr|\bCr\b|lakh/i.test(text)) bad.push('Indian notation on a dollar figure');
    if (!isNaN(div) && div > 15) bad.push(`dividend ${div}%`);
    if (/clearly/i.test(line) && c < 70) bad.push(`"${line}" at ${c}%`);
    if (await p.locator('.chart svg polyline').count() !== 1) bad.push('no price chart');
    ok(`stock page ${t}: complete and plausible`, !bad.length, bad.join('; ') || `${(await p.locator('.signal .sig').textContent())} ${c}%`);
  }
  await p.evaluate(() => { location.hash = '#/help'; }); await wait(p, 800);
  ok('how it works: the questions and the words, the new rules included', (await p.locator('.page').textContent()).includes('How calls are counted'));
  await p.evaluate(() => { location.hash = '#/ideas'; }); await wait(p, 800);
  ok('example: other pages ask to sign in', (await p.locator('.page').textContent()).includes('Sign in to see'));

  // ---- 5. phones and dark
  const phone = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await phone.waitForSelector('.peek tbody tr', { timeout: 20000 }); await wait(phone, 1200);
  ok('phone: the front page does not scroll sideways', !(await sideways(phone)));
  await phone.click('.hero-l >> text=See a live example'); await phone.waitForSelector('.shell'); await wait(phone, 1500);
  ok('phone: the example does not scroll sideways, and has the tab bar', !(await sideways(phone)) && await phone.locator('.tabbar').isVisible());
  const searchW = await phone.locator('.top .search').evaluate(e => e.getBoundingClientRect().width);
  ok('phone: the search box has room', searchW > 180, `${Math.round(searchW)}px`);
  await phone.evaluate(x => { location.hash = '#/s/' + x; }, tickers[0] || 'AAPL'); await phone.waitForSelector('.signal'); await wait(phone);
  ok('phone: a stock page does not scroll sideways', !(await sideways(phone)));
  const dark = await open({ colorScheme: 'dark' });
  ok('dark: follows the device', (await dark.evaluate(() => getComputedStyle(document.body).backgroundColor)) === 'rgb(13, 19, 28)');

  ok('no errors in the browser', !problems.length, problems.slice(0, 3).join(' | '));
  await browser.close();
  const passed = results.filter(Boolean).length;
  console.log(`\n${passed} of ${results.length} passed`);
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
