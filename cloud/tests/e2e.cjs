// The whole product in a real browser, against the local Firebase emulators filled with example data:
// the front page, the example, sign-in, choosing stocks, every page, the account, and the security rules.
//   1. cd cloud && npx firebase-tools emulators:start --only auth,firestore,hosting --project demo-md
//   2. FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=demo-md python cloud/tools/demo_data.py
//   3. node cloud/tests/e2e.cjs            (needs Playwright: npm i -g playwright)
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://127.0.0.1:5000';
const results = [];
const ok = (name, pass, note = '') => { results.push(pass); console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${note ? '  (' + note + ')' : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  const open = async (opts = {}) => {
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true, ...opts });
    const page = await ctx.newPage();
    page.on('pageerror', e => problems.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error' && !/permission|403|Failed to load resource/i.test(m.text())) problems.push('console: ' + m.text().slice(0, 200)); });
    await page.goto(BASE + '/'); await page.waitForSelector('.land, .shell, .onb', { timeout: 15000 });
    return page;
  };
  const wait = (p, ms = 700) => p.waitForTimeout(ms);
  const rows = p => p.locator('.card.flush tbody tr.link').count();
  const email = `e2e-${Date.now()}@example.com`;
  const signIn = async (p, who = email, name = 'Test Person') => { await p.evaluate(([e, n]) => window.__mdSignInAs(e, n), [who, name]); await p.waitForSelector('.shell, .onb', { timeout: 15000 }); await wait(p); };
  // Firestore from inside the page, as the signed-in (or signed-out) browser: what the rules allow and refuse
  const fire = (p, fn, arg) => p.evaluate(async ([src, a]) => {
    const fs = await import('/vendor/firebase-firestore-lite.js'), app = (await import('/vendor/firebase-app.js')).getApp();
    const auth = (await import('/vendor/firebase-auth.js')).getAuth(app), db = fs.getFirestore(app);
    try { return await (new Function('fs', 'db', 'auth', 'a', `return (${src})(fs, db, auth, a)`))(fs, db, auth, a); } catch (e) { return 'DENIED:' + (e.code || e.message); }
  }, [fn.toString(), arg]);
  const denied = r => typeof r === 'string' && /DENIED:.*permission-denied/.test(r);

  // ---- 1. the front page and the example, signed out
  let p = await open();
  await p.waitForSelector('.peek tr.link', { timeout: 10000 }).catch(() => {});
  ok('front page shows today\'s example signals', await p.locator('.peek tr.link').count() >= 5);
  ok('signed out: the public example can be read', (await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'public', 'demo'))).exists())) === true);
  ok('signed out: stock cards cannot be read', denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'stocks', 'NVDA'))).exists())));
  ok('signed out: nobody\'s account can be read', denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'users', 'demo-user'))).exists())));
  await p.click('text=See a live example'); await p.waitForSelector('.shell'); await wait(p, 1200);
  ok('example: dashboard with rows and a sign-in banner', await rows(p) >= 5 && await p.locator('.banner').count() === 1);
  await p.locator('.card.flush tbody tr.link').first().click(); await p.waitForSelector('.signal'); await wait(p);
  ok('example: a stock page opens with its signal and chart', await p.locator('.signal .sig').count() === 1 && await p.locator('.chart svg').count() === 1);
  await p.goto(BASE + '/#/ideas'); await wait(p);
  ok('example: other pages ask to sign in', (await p.locator('.page').textContent()).includes('Sign in to see'));
  await p.context().close();

  // ---- 2. a new person signs in and chooses stocks
  p = await open();
  await signIn(p);
  ok('first sign-in asks which stocks you follow', await p.locator('.onb').count() === 1);
  ok('cannot continue with nothing chosen', await p.locator('.onb .btn.primary').isDisabled());
  await p.locator('.pack').first().click();
  await p.fill('.onb input.input', 'jpm'); await wait(p, 400); await p.locator('.onb .results button').first().click();
  await p.click('text=Or paste a list'); await p.fill('.onb textarea', 'My watchlist\nORCL\nOracle Corp\n$290.86\n-3.2%\nNASDAQ:PLTR\nsome words here'); await p.click('text=Find my stocks'); await wait(p, 300);
  const chosen = await p.locator('.picked .chip').allTextContents();
  ok('a list, a search and a paste all add stocks', chosen.length === 10 && chosen.some(c => c.startsWith('ORCL')) && chosen.some(c => c.startsWith('PLTR')) && chosen.some(c => c.startsWith('JPM')), chosen.length + ' chosen');
  await p.click('text=Show my dashboard'); await p.waitForSelector('.shell'); await wait(p, 1500);
  ok('the dashboard shows every chosen stock', await rows(p) === 10);
  ok('"For you today" has something to say', await p.locator('.todo a').count() >= 1);

  // ---- 3. holdings, adding and removing
  await p.locator('.card.flush tbody tr.link').first().locator('.icon-btn').click(); await p.click('text=Edit what I hold');
  await p.locator('.modal input').nth(0).fill('10'); await p.locator('.modal input').nth(1).fill('100'); await p.click('.modal >> text=Save'); await wait(p, 1200);
  ok('typing shares shows the portfolio value', (await p.locator('.tile .k').first().textContent()).includes('Portfolio value'));
  await p.click('text=Add stocks'); await p.fill('.modal input.input', 'costco'); await wait(p, 400); await p.locator('.modal .results button').first().click();
  await p.click('.modal >> text=Add to my stocks'); await wait(p, 1500);
  ok('a stock can be added from the dashboard', await rows(p) === 11);
  await p.locator('.card.flush tbody tr.link').last().locator('.icon-btn').click(); await p.click('.menu >> text=Remove'); await wait(p, 1200);
  ok('and removed', await rows(p) === 10);
  await p.reload(); await p.waitForSelector('.shell'); await wait(p, 1500);
  ok('the list is still there after a reload', await rows(p) === 10 && (await p.locator('.tile .k').first().textContent()).includes('Portfolio value'));

  // ---- 4. every page
  await p.fill('.search input', 'nvid'); await wait(p, 400); await p.locator('.search .results button').first().click(); await p.waitForSelector('.signal'); await wait(p);
  ok('search opens a stock page', (await p.evaluate(() => location.hash)) === '#/s/NVDA');
  const text = await p.locator('.page').textContent();
  ok('stock page: signal, Wall Street, key numbers, bulls and bears, calls', ['Should I invest?', 'Wall Street', 'Key numbers', 'Bulls say', 'Bears say', 'Every call'].every(t => text.includes(t)));
  ok('stock page: the chart marks analyst calls', await p.locator('.chart a').count() >= 1);
  await p.click('.seg >> text=1Y'); await wait(p, 300);
  ok('stock page: the period can be changed', await p.locator('.seg button[aria-pressed=true]').first().textContent() === '1Y');
  await p.goto(BASE + '/#/s/ZZZZZ'); await wait(p, 1200);
  ok('an unknown ticker is explained and asked for', (await p.locator('.page').textContent()).includes('We are starting to cover ZZZZZ'));
  await p.goto(BASE + '/#/ideas'); await p.waitForSelector('.seg'); await wait(p);
  const before = await p.locator('.card.flush .btn.sm').count();
  ok('ideas: lists with stocks to add', await rows(p) >= 1 && before >= 1);
  await p.locator('.card.flush .btn.sm').first().click(); await wait(p, 1200);
  ok('ideas: Add puts the stock in my list', await p.locator('.card.flush .btn.sm').count() === before - 1);
  await p.click('.seg >> text=Most discussed'); await wait(p, 300);
  ok('ideas: other lists open', await rows(p) >= 5);
  await p.goto(BASE + '/#/analysts'); await p.waitForSelector('tbody tr.link'); await wait(p);
  ok('analysts: a ranked table with ratings', await p.locator('tbody tr.link').count() >= 5 && await p.locator('.stars').count() >= 5);
  await p.locator('tbody tr.link').first().click(); await wait(p, 900);
  ok('an analyst\'s page lists their calls with results', (await p.locator('.page').textContent()).includes('Latest calls') && await p.locator('tbody tr').count() >= 3);
  await p.goto(BASE + '/#/calendar'); await wait(p, 1200);
  ok('calendar: earnings for my stocks and the latest videos', await p.locator('.list a .badge').count() >= 3 && (await p.locator('.page').textContent()).includes('Latest videos read'));
  await p.goto(BASE + '/#/status'); await wait(p, 900);
  ok('status page shows the last run', (await p.locator('.page').textContent()).includes('Last run'));

  // ---- 5. the account
  await p.goto(BASE + '/#/account'); await wait(p, 900);
  await p.click('text=Only when a signal changes'); await wait(p, 900);
  await p.reload(); await p.waitForSelector('.shell'); await wait(p, 1200);
  ok('email choices are saved', await p.locator('input[name=daily]').nth(1).isChecked());
  const [download] = await Promise.all([p.waitForEvent('download'), p.click('text=Download my data')]);
  ok('my data can be downloaded', download.suggestedFilename() === 'market-digest-my-data.json');

  // ---- 6. the security rules, as this signed-in user
  const uid = await fire(p, async (fs, db, auth) => auth.currentUser.uid);
  ok('rules: I can read my own account', (await fire(p, async (fs, db, auth) => (await fs.getDoc(fs.doc(db, 'users', auth.currentUser.uid))).data().email)) === email);
  ok('rules: I cannot read someone else\'s', denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'users', 'demo-user'))).exists())));
  ok('rules: I cannot list the accounts', denied(await fire(p, async (fs, db) => (await fs.getDocs(fs.collection(db, 'users'))).size)));
  ok('rules: I cannot write someone else\'s', denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'users', 'demo-user'), { email: auth.currentUser.email, stocks: [] }))));
  ok('rules: I cannot put another address on my account', denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'users', auth.currentUser.uid), { email: 'victim@example.com', stocks: [] }))));
  ok('rules: I cannot add fields of my own (like a paid plan)', denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'users', auth.currentUser.uid), { email: auth.currentUser.email, plan: 'pro' }))));
  ok('rules: email choices must be the known ones', denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'users', auth.currentUser.uid), { email: auth.currentUser.email, prefs: { daily: 'hourly' } }))));
  ok('rules: a list is at most 60 stocks', denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'users', auth.currentUser.uid), { email: auth.currentUser.email, stocks: Array.from({ length: 61 }, (_, i) => ({ t: 'A' + i })) }))));
  ok('rules: stock cards are read-only', denied(await fire(p, async (fs, db) => fs.setDoc(fs.doc(db, 'stocks', 'NVDA'), { signal: 'yes' }))));
  ok('rules: market pages are read-only', denied(await fire(p, async (fs, db) => fs.setDoc(fs.doc(db, 'market', 'overview'), { x: 1 }))));
  ok('rules: the engine\'s own records are closed', denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'engine', 'state'))).exists())) && denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'mail', 'demo-user'))).exists()))
    && denied(await fire(p, async (fs, db) => (await fs.getDocs(fs.collection(db, 'videos'))).size)));
  ok('rules: a request must be in my name and a real ticker', denied(await fire(p, async (fs, db) => fs.setDoc(fs.doc(db, 'requests', 'HACK'), { by: 'someone-else', at: 'x' })))
    && denied(await fire(p, async (fs, db, auth) => fs.setDoc(fs.doc(db, 'requests', 'not a ticker'), { by: auth.currentUser.uid, at: 'x' }))));
  ok('rules: the ticker I looked up was asked for', denied(await fire(p, async (fs, db) => (await fs.getDoc(fs.doc(db, 'requests', 'ZZZZZ'))).exists())) );   // written, and not readable back

  // ---- 7. a phone
  const phone = await open({ viewport: { width: 390, height: 844 } });
  await signIn(phone);
  const fits = async () => !(await phone.evaluate(() => document.documentElement.scrollWidth > innerWidth));
  let allFit = await fits();
  for (const h of ['#/s/NVDA', '#/ideas', '#/analysts', '#/calendar', '#/account']) { await phone.goto(BASE + '/' + h); await wait(phone, 1100); allFit = allFit && await fits(); }
  ok('phone: no page scrolls sideways', allFit);
  ok('phone: the tab bar replaces the side menu', await phone.locator('.tabbar').isVisible() && !(await phone.locator('.side').isVisible()));
  await phone.context().close();

  // ---- 8. deleting the account
  await p.click('text=Delete my account'); await p.click('.modal >> text=Delete everything'); await p.waitForSelector('.land', { timeout: 15000 });
  ok('deleting the account signs out and returns to the front page', true);
  await signIn(p);
  ok('and the data is gone: signing in again starts from nothing', await p.locator('.onb').count() === 1);

  ok('no errors in the browser', problems.length === 0, problems.slice(0, 3).join(' | '));
  await browser.close();
  const failed = results.filter(r => !r).length;
  console.log(`\n${results.length - failed} of ${results.length} passed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
