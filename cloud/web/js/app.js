// The app: the front page, the frame around every page, Home ("My stocks") and the stock page.
import { el, icon, logoMark, googleMark, pct, tone, money, num, day, ago, sig, confidence, split, spark, ring, meter, stars, priceChart, toast, skeleton, safeUrl, SIGNAL_SAYS, COLOR } from './ui.js';
import { data, portfolio, forYou, cleanTicker, friendly } from './data.js';
import { go, has, stockTable, rowMenu, addModal, holdingModal, addStocks, search, welcome, ideas, analysts, analyst, calendar, account, status, tile, callsTable } from './pages.js';

const app = document.getElementById('app');
const NAV = [['', 'My stocks', 'home'], ['ideas', 'Ideas', 'bulb'], ['analysts', 'Analysts', 'users'], ['calendar', 'Calendar', 'cal']];
const signIn = () => data.signIn().catch(e => toast(e.message));

// ---------------------------------------------------------------- the front page
async function landing() {
  document.title = 'Market Digest: Yes or No on your stocks, from the analysts';
  const peek = el('.peek', {}, el('.bar-t', {}, el('i'), el('i'), el('i')), skeleton(300));
  const example = el('button.btn.lg', { onclick: async () => { example.disabled = true; try { await data.startExample(); render(); } catch (e) { toast(e.message || friendly(e)); example.disabled = false; } } }, 'See a live example');
  app.replaceChildren(el('.land', {},
    el('header', {}, el('a.logo', { href: '#/' }, logoMark(), el('span', { text: 'Market Digest' })), el('span.sp'), el('button.btn', { onclick: signIn }, 'Sign in')),
    el('.hero-l', {},
      el('div', {}, el('h1', {}, 'Yes or No on your stocks, ', el('em', { text: 'from what the analysts say.' })),
        el('p.lede', { text: 'We watch the finance channels and Wall Street’s ratings every day, and turn them into one clear signal for each stock you follow, with the numbers behind it.' }),
        el('.cta', {}, el('button.btn.primary.lg.gbtn', { onclick: signIn }, el('span', { style: { background: '#fff', borderRadius: '4px', padding: '2px', display: 'grid' } }, googleMark()), 'Continue with Google'), example),
        el('p.fine', {}, 'Free during the beta · No card · Nothing to install · Ready in 30 seconds', el('br'), 'By continuing you agree to the ', el('a', { href: '/terms.html', text: 'terms' }), ' and the ', el('a', { href: '/privacy.html', text: 'privacy policy' }), '.')),
      peek),
    el('.how', {},
      ...[['Pick your stocks', 'Choose a starter list, search, or paste your Google Finance watchlist. That is the whole setup.'],
        ['We do the reading', 'Every day we go through the analysts’ videos and Wall Street’s ratings, so you do not have to.'],
        ['You get a clear signal', 'Yes, No or Wait for each stock, how confident it is, and what changed, on one page and by email.']]
        .map(([h, p], i) => el('.card', {}, el('.n', { text: i + 1 }), el('h3', { text: h }), el('p', { text: p })))),
    el('footer', {}, 'The signals sum up what analysts said. They are not personal financial advice, and analysts are often wrong.', el('br'),
      el('a', { href: '/privacy.html', text: 'Privacy' }), ' · ', el('a', { href: '/terms.html', text: 'Terms' }))));
  try {
    const d = await data.publicExample();
    peek.replaceChildren(el('.bar-t', {}, el('i'), el('i'), el('i')), stockTable('peek', d.cards.slice(0, 6), () => el('span')));
    peek.querySelectorAll('tr.link').forEach(tr => { tr.onclick = () => example.click(); });
  } catch (e) { peek.querySelector('.skel').replaceWith(el('.empty', { text: 'Sign in to see your stocks here.' })); }
}

// ---------------------------------------------------------------- the frame
let fresh = null;
function shell(active, page) {
  const p = data.profile || {}, name = (p.name || p.email || 'You');
  const nav = cls => el(cls, {}, NAV.map(([h, label, ic]) => el('a', { href: '#/' + h, 'aria-current': active === h ? 'page' : null }, icon(ic), el('span', { text: label }))));
  const input = el('input', { placeholder: 'Search stocks', autocomplete: 'off', 'aria-label': 'Search a stock' }), results = el('.results', { hidden: true });
  let timer;
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(async () => {
    const q = input.value.trim().toUpperCase(); results.textContent = '';
    if (!q) { results.hidden = true; return; }
    const hits = search(await data.symbols(), q), typed = cleanTicker(q);
    if (typed && !hits.some(h => h[0] === typed)) hits.push([typed, 'Look up this ticker']);
    for (const [t, nm] of hits) results.append(el('button', { onclick: () => { input.value = ''; results.hidden = true; go('#/s/' + encodeURIComponent(t)); } }, el('span.badge', { text: t }), el('span.nm', { text: nm })));
    results.hidden = !hits.length;
  }, 120); };
  input.onkeydown = e => { if (e.key === 'Enter') { const b = results.querySelector('button'); if (b && !results.hidden) b.click(); } if (e.key === 'Escape') { results.hidden = true; input.blur(); } };
  input.onblur = () => setTimeout(() => { results.hidden = true; }, 180);
  const freshBox = el('.fresh');
  const top = el('.top', {}, el('a.logo', { href: '#/' }, logoMark()), el('.search', {}, icon('search'), input, results), el('span', { style: { flex: 1 } }),
    data.example ? el('button.btn.primary.sm', { onclick: signIn }, 'Sign in to save') :
      el('a', { href: '#/account', 'aria-label': 'Account', class: 'hide-desktop' }, data.user && data.user.photoURL ? el('img.avatar', { src: data.user.photoURL, alt: '', referrerpolicy: 'no-referrer' }) : el('.avatar', { text: name[0].toUpperCase() })));
  const main = el('.main', {}, top, page);
  app.replaceChildren(el('.shell', {},
    el('aside.side', {}, el('a.logo', { href: '#/' }, logoMark(), el('span', { text: 'Market Digest' })), nav('nav.nav'), el('.fill'), freshBox,
      data.example ? el('button.btn.primary', { onclick: signIn }, 'Sign in to save') :
        el('a.me', { href: '#/account' }, data.user && data.user.photoURL ? el('img.avatar', { src: data.user.photoURL, alt: '', referrerpolicy: 'no-referrer' }) : el('.avatar', { text: name[0].toUpperCase() }),
          el('.who', {}, el('b', { text: p.name || 'Account' }), el('span.small', { text: p.email || '' })))),
    main, nav('nav.tabbar')));
  window.onscroll = () => top.classList.toggle('scrolled', window.scrollY > 4);
  const showFresh = s => { if (s && s.last_run) freshBox.replaceChildren(el('b', { text: 'Signals updated' }), `${ago(s.last_run)}` + (s.prices_as_of ? ` · prices ${day(s.prices_as_of)}` : '')); };
  if (fresh) showFresh(fresh); else if (!data.example) data.market('status').then(s => { fresh = s; showFresh(s); }).catch(() => {});
}

// ---------------------------------------------------------------- Home: my stocks
async function home(root) {
  const p = data.profile, first = (p.name || '').split(' ')[0];
  const hour = new Date().getHours();
  root.append(el('.head', {}, el('div', {}, el('h1', { text: `Good ${hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'}${first ? ', ' + first : ''}` }),
    el('.sub', { text: new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' }) })), el('span.sp'),
    el('button.btn.primary', { onclick: () => addModal(render) }, icon('plus'), 'Add stocks')));
  if (data.example) root.append(el('.banner', { style: { marginBottom: '14px' } }, 'This is a live example with today’s real signals. Make it yours: your stocks, your emails.', el('span.sp'), el('button.btn.primary.sm', { onclick: signIn }, 'Continue with Google')));
  const hold = el('div', {}, el('.grid.g4', {}, skeleton(96), skeleton(96), skeleton(96), skeleton(96)), el('div', { style: { height: '14px' } }), skeleton(360));
  root.append(hold);
  if (!p.stocks.length) { hold.replaceChildren(el('.card.empty', {}, el('h3', { text: 'Add your stocks to see their signals' }), 'Pick a starter list, search, or paste your watchlist.', el('div', {}, el('button.btn.primary', { onclick: () => addModal(render) }, icon('plus'), 'Add stocks')))); return; }
  const [cards, overview] = await Promise.all([data.cards(p.stocks.map(s => s.t)), data.market('overview').catch(() => null)]);
  const pf = portfolio(p, cards), rows = pf.rows, bull = rows.reduce((a, r) => a + (r.calls.bullish || 0), 0), bear = rows.reduce((a, r) => a + (r.calls.bearish || 0), 0);
  const next = rows.filter(r => r.days_to_earnings != null).sort((a, b) => a.days_to_earnings - b.days_to_earnings)[0];

  const tiles = el('.grid.g4', {},
    pf.total != null ? el('.card.tile', {}, el('.k', { text: 'Portfolio value' }), el('.v', { text: money(pf.total, pf.currency) }),
      el('.s', {}, el('span', { class: tone(pf.dayChange), text: pct(pf.dayChange, 2) }), ' today', pf.gain_pct != null ? [' · ', el('span', { class: tone(pf.gain_pct), text: pct(pf.gain_pct) }), ' overall'] : null))
      : el('.card.tile', {}, el('.k', { text: 'Your list' }), el('.v', { text: `${rows.length} stock${rows.length === 1 ? '' : 's'}` }), el('.s', {}, el('a', { href: '#', onclick: e => { e.preventDefault(); holdingModal(rows[0], render); } }, 'Add your shares'), ' to see your portfolio value')),
    el('.card.tile', {}, el('.k', { text: 'Should I invest?' }),
      el('.counts', {}, el('div', {}, el('b.up', { text: pf.counts.yes }), el('span.up', { text: 'Yes' })), el('div', {}, el('b', { text: pf.counts.wait }), el('span.mut', { text: 'Wait' })), el('div', {}, el('b.down', { text: pf.counts.no }), el('span.down', { text: 'No' }))),
      meter([[pf.counts.yes, 'var(--green)'], [pf.counts.wait, 'var(--grey)'], [pf.counts.no, 'var(--red)']])),
    tile('Analyst mood on your stocks', bull + bear ? Math.round(100 * bull / (bull + bear)) + '% bullish' : '—', bull + bear ? `${bull} bullish, ${bear} bearish calls in 30 days` : 'No calls on your stocks yet', bull + bear ? (bull >= bear ? 'up' : 'down') : ''),
    tile('Next earnings', next ? next.ticker : '—', next ? `${day((next.street || {}).next_earnings)} · ${next.days_to_earnings === 0 ? 'today' : next.days_to_earnings === 1 ? 'tomorrow' : `in ${next.days_to_earnings} days`}` : 'None known for your stocks'));

  const todo = forYou(rows);
  const todoCard = el('.card', {}, el('h2', { text: 'For you today' }), todo.length ? el('.todo', {}, todo.map(t => el('a', { href: '#/s/' + encodeURIComponent(t.ticker) },
    el('span.dot.' + t.tone, {}, icon(t.icon)), el('span.tx', {}, el('b', { text: t.ticker + ' ' }), t.text), el('span.go', {}, icon('right')))))
    : el('p.small', { text: 'Nothing needs your attention today. Signals on your stocks are unchanged.' }));

  let filter = 'all';
  const tableCard = el('.card.flush');
  const drawTable = () => {
    const list = rows.filter(r => filter === 'all' || (filter === 'own') === r.owned);
    const seg = el('.seg', {}, [['all', `All ${rows.length}`], ['own', `Owned ${rows.filter(r => r.owned).length}`], ['watch', `Watching ${rows.filter(r => !r.owned).length}`]]
      .map(([k, label]) => el('button', { 'aria-pressed': String(k === filter), onclick: () => { filter = k; drawTable(); } }, label)));
    tableCard.replaceChildren(el('.row', { style: { padding: '14px 16px 6px', flexWrap: 'wrap' } }, el('h2.h2', { style: { margin: 0 }, text: 'My stocks' }), el('span.sp'), seg),
      list.length ? stockTable('mine', list, r => rowMenu(r, render)) : el('.empty', { text: filter === 'own' ? 'No shares typed yet. Open a stock’s menu and choose “Edit what I hold”.' : 'Nothing here.' }));
  };
  drawTable();

  const side = el('.stack');
  if (overview && overview.sp500) {
    const sp = overview.sp500;
    side.append(el('.card', {}, el('h2', { text: 'Market' }),
      el('.row', {}, el('div', {}, el('.small', { text: 'S&P 500' }), el('.big', { text: num(sp.price, 0) }), el('span', { class: tone(sp.change_pct_day), text: pct(sp.change_pct_day, 2) }), el('span.small', { text: ' today' })), el('span.sp'), spark(sp.spark, 120, 44)),
      el('div', { style: { marginTop: '14px' } }, el('.row', { style: { justifyContent: 'space-between' } }, el('span.small', { text: 'Analyst mood, all stocks' }), el('b', { class: overview.mood_pct >= 50 ? 'up' : 'down', text: overview.mood_pct == null ? '—' : overview.mood_pct + '% bullish' })),
        el('div', { style: { marginTop: '6px' } }, meter([[overview.views.bullish, 'var(--green)'], [overview.views.neutral + overview.views.mixed, 'var(--grey)'], [overview.views.bearish, 'var(--red)']]))),
      overview.themes && overview.themes.length ? el('div', { style: { marginTop: '12px' } }, overview.themes.slice(0, 2).map(t => el('.theme', {}, el('b', { text: t.theme }), el('span', { text: t.detail })))) : null));
    const picks = (overview.lists.yes || []).map(t => overview.rows[t]).filter(r => r && !has(r.ticker)).slice(0, 4);
    if (picks.length) side.append(el('.card', {}, el('h2', {}, 'Strongest Yes right now', el('span.sp'), el('a.small', { href: '#/ideas', text: 'All ideas' })),
      el('.list', {}, picks.map(r => el('a', { href: '#/s/' + encodeURIComponent(r.ticker), style: { color: 'inherit', alignItems: 'center' } }, el('span.badge', { text: r.ticker }),
        el('span.body', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, text: r.name || '' }), el('b.up', { text: r.confidence_pct + '%' }))))));
  }
  side.classList.add('f3'); tableCard.classList.add('f2');   // on a phone the table comes before the market cards
  hold.classList.add('flow');
  hold.replaceChildren(tiles, el('.cols', {}, todoCard, side), tableCard,
    el('p.small', { class: 'f4', text: 'The signals sum up what analysts said; they are not personal financial advice and can be wrong.' }));
  if (!side.children.length) hold.querySelector('.cols').style.gridTemplateColumns = '1fr';
}

// ---------------------------------------------------------------- one stock
const SCALE = ['Strong Sell', 'Moderate Sell', 'Hold', 'Moderate Buy', 'Strong Buy'];
const kv = (label, value, cls) => el('div', {}, el('span', { text: label }), el('b', { class: cls || '', text: value == null || value === '' ? '—' : value }));
async function stock(root, t) {
  t = cleanTicker(t);
  root.append(el('a.crumb', { href: '#/' }, icon('left'), 'My stocks'));
  const hold = el('div', {}, skeleton(60), el('div', { style: { height: '14px' } }), skeleton(320)); root.append(hold);
  if (!t) { hold.replaceChildren(el('.card.empty', {}, el('h3', { text: 'That is not a ticker' }), 'Search for a company in the box at the top.')); return; }
  const [c, ch] = await Promise.all([data.card(t), data.chart(t).catch(() => null)]);
  if (!c || c.unknown) {
    if (!c) data.request(t);
    hold.replaceChildren(el('.card.empty', {}, el('h3', { text: c ? `We could not find ${t}` : `We are starting to cover ${t}` }),
      c ? 'Check the ticker. US stocks are written as they are (AAPL); for other markets add the exchange, like RELIANCE.NS.' : 'Its price and signal arrive within the hour. Add it to your stocks and it will be on your dashboard when ready.',
      !c && !has(t) && data.profile ? el('div', {}, el('button.btn.primary', { onclick: async () => { await addStocks([t]); toast(`${t} added`); go('#/'); } }, icon('plus'), 'Add to my stocks')) : null));
    return;
  }
  document.title = `${t} ${SIGNAL_SAYS[c.signal] ? '· ' + (c.signal === 'none' ? 'no signal yet' : c.signal.toUpperCase()) : ''} · Market Digest`;
  const st = c.street || {}, mine = data.profile && data.profile.stocks.find(s => s.t === t);
  const act = el('span');
  const drawAct = () => act.replaceChildren(has(t) ? el('button.btn', { onclick: () => holdingModal({ ...c, ticker: t }, () => { drawAct(); render(); }) }, icon('edit'), 'In my stocks') :
    el('button.btn.primary', { onclick: async () => { await addStocks([t]); toast(`${t} added to your stocks`); drawAct(); } }, icon('plus'), 'Add to my stocks'));
  drawAct();

  // the chart, with a choice of period
  const chartBox = el('div'); let span = 66;
  const dates = (ch && ch.d) || [], closes = (ch && ch.c) || c.spark || [];
  const fallbackDates = dates.length ? dates : closes.map((_, i) => '');
  const seg = el('.seg');
  const drawChart = () => {
    seg.replaceChildren(...[[22, '1M'], [66, '3M'], [130, '6M'], [260, '1Y']].filter(([n]) => n <= 66 || closes.length > n * 0.7).map(([n, label]) => el('button', { 'aria-pressed': String(n === span), onclick: () => { span = n; drawChart(); } }, label)));
    const d = fallbackDates.slice(-span), v = closes.slice(-span);
    chartBox.replaceChildren(priceChart(d, v, (c.calls_list || []).filter(x => !d[0] || x.day >= d[0]), c.currency));
  };
  drawChart();
  const move = closes.length > 1 ? (closes[closes.length - 1] / closes.slice(-span)[0] - 1) * 100 : null;

  // the signal
  const history = (c.history || []).slice(-4);
  const signalCard = el('.card.signal', {}, el('.eyebrow', { text: 'Should I invest?' }),
    el('.ringrow', {}, ring(c.confidence_pct, COLOR[c.signal]), el('div', {}, sig(c.signal, true), el('p', { style: { marginTop: '8px', fontWeight: 600 }, text: SIGNAL_SAYS[c.signal] }), el('p.small', { text: c.signal === 'none' ? 'Nobody in the videos or on Wall Street has given a view yet.' : 'Based on ' + c.basis.replace("your channels' videos", 'the videos') + '.' }))),
    el('.factors', {}, (c.factors || []).map(f => el('span.chip.' + f.tone, { text: f.text }))),
    history.length > 1 ? el('.hist', {}, 'Signal history: ', history.map((h, i) => [i ? ' → ' : '', el('span', { style: { fontWeight: 700, color: COLOR[h.s] }, text: h.s === 'none' ? '—' : h.s.toUpperCase() }), el('span', { text: ' ' + day(h.d) })])) : null,
    mine && mine.shares && c.price != null ? el('div', { style: { borderTop: '1px solid var(--line-2)', paddingTop: '12px', marginTop: 'auto' } }, el('.eyebrow', { text: 'Your position', style: { marginBottom: '6px' } }),
      el('.kv', {}, kv('Shares', num(mine.shares, 4)), kv('Value', money(mine.shares * c.price, c.currency)), kv('You paid', mine.cost ? money(mine.cost, c.currency) : null), kv('Your gain', mine.cost ? pct((c.price / mine.cost - 1) * 100) : null, mine.cost ? tone(c.price / mine.cost - 1) : ''))) : null);

  // the analysts in the videos
  const calls = c.calls_list || [], voices = [];
  for (const x of calls) if (x.analyst && !voices.some(v => v.analyst === x.analyst)) voices.push(x);
  const videoCard = el('.card', {}, el('h2', { text: 'Analysts in the videos' }),
    c.mentions ? el('div', {}, el('.row', { style: { justifyContent: 'space-between', alignItems: 'baseline' } }, el('span', {}, el('b.big.up', { text: c.calls.bullish }), el('span.small', { text: ' bullish' })), el('span', {}, el('b.big.down', { text: c.calls.bearish }), el('span.small', { text: ' bearish' }))),
      el('div', { style: { margin: '8px 0 4px' } }, meter([[c.calls.bullish, 'var(--green)'], [c.calls.neutral + c.calls.mixed, 'var(--grey)'], [c.calls.bearish, 'var(--red)']])),
      el('p.small', { text: `Calls in the last 30 days${c.track ? ` · ${c.track.right} of ${c.track.scored} earlier calls proved right` : ''}` }))
      : el('p.small', { text: 'No bullish or bearish call on it in the last 30 days.' }),
    voices.length ? el('.list', { style: { marginTop: '10px' } }, voices.slice(0, 5).map(v => el('div', { style: { alignItems: 'center' } }, el('.body', {}, el('a', { href: '#/a/' + encodeURIComponent(v.analyst), style: { fontWeight: 600 }, text: v.analyst }), ' ', stars(v.analyst_stars)), el('span.pill.' + v.view, { text: v.view }), el('span.small', { text: day(v.day) })))) : null);

  // Wall Street
  const at = SCALE.indexOf(st.consensus);
  const colors = ['var(--red)', 'var(--red)', 'var(--grey)', 'var(--green)', 'var(--green)'];
  const bar01 = (label, v) => v == null ? null : [el('span.small', { text: label }), meter([[v, v >= 0.6 ? 'var(--green)' : v <= 0.4 ? 'var(--red)' : 'var(--grey)'], [1 - v, 'transparent']]), el('b', { text: Math.round(v * 100) })];
  const streetCard = el('.card', {}, el('h2', {}, 'Wall Street', el('span.sp'), safeUrl(st.url) ? el('a.small', { href: safeUrl(st.url), target: '_blank', rel: 'noopener', text: 'TipRanks' }) : null),
    st.consensus ? el('div', {},
      el('.row', { style: { justifyContent: 'space-between', alignItems: 'baseline' } }, el('b.big', { class: at > 2 ? 'up' : at >= 0 && at < 2 ? 'down' : '', text: st.consensus }), st.best_consensus && st.best_consensus !== st.consensus ? el('span.small', { text: `Top analysts: ${st.best_consensus}` }) : null),
      at >= 0 ? [el('.scale', {}, SCALE.map((_, i) => el('i', { class: i === at ? 'on' : '', style: { background: i === at ? colors[i] : null } }))), el('.scale-l', {}, el('span', { text: 'Strong Sell' }), el('span', { text: 'Hold' }), el('span', { text: 'Strong Buy' }))] : null,
      st.price_target != null ? el('div', { style: { marginTop: '14px' } }, el('.row', { style: { justifyContent: 'space-between' } }, el('span.small', { text: '12-month price target' }), el('b', {}, money(st.price_target, c.currency), ' ', el('span', { class: tone(st.upside_pct), text: `(${pct(st.upside_pct)})` })))) : null,
      st.smart_score != null ? el('div', { style: { marginTop: '14px' } }, el('.row', { style: { justifyContent: 'space-between', alignItems: 'baseline' } }, el('span.small', { text: 'Smart Score' }), el('.score', {}, el('b', { class: st.smart_score >= 8 ? 'up' : st.smart_score <= 3 ? 'down' : '', text: st.smart_score }), el('span', { text: '/ 10' }))),
        el('.scale', { style: { gridTemplateColumns: 'repeat(10,1fr)', margin: '6px 0 0' } }, Array.from({ length: 10 }, (_, i) => el('i', { style: { background: i < st.smart_score ? (st.smart_score >= 8 ? 'var(--green)' : st.smart_score <= 3 ? 'var(--red)' : 'var(--grey)') : null } })))) : null,
      el('.mini', { style: { marginTop: '14px' } }, bar01('News sentiment', st.news_sentiment), bar01('Hedge funds', st.hedge_fund_score), bar01('Insiders', st.insider_score)),
      st.at ? el('p.small', { style: { marginTop: '10px' }, text: `Read ${day(st.at)}` }) : null)
      : el('p.small', { text: 'Wall Street’s rating for this stock has not been read yet. Stocks are refreshed in turn, the ones in users’ lists first.' }));

  const stats = el('.card', {}, el('h2', { text: 'Key numbers' }), el('.kv', {},
    kv('Market cap', st.market_cap ? money(st.market_cap, c.currency, true) : null), kv('P/E', c.pe != null ? num(c.pe) : null),
    kv('Dividend yield', st.dividend_yield_pct != null ? st.dividend_yield_pct + '%' : null), kv('Sector', c.sector),
    kv('Week', pct(c.change_pct_week), tone(c.change_pct_week)), kv('Month', pct(c.change_pct_month), tone(c.change_pct_month)),
    kv('This year', pct(st.ytd_pct), tone(st.ytd_pct)), kv('12 months', pct(st.year_pct), tone(st.year_pct)),
    kv('1-year low', money(c.low_52w, c.currency)), kv('1-year high', money(c.high_52w, c.currency)),
    kv('Off 1-year high', pct(c.from_high_pct), tone(c.from_high_pct)), kv('Next earnings', st.next_earnings ? `${day(st.next_earnings)}${c.days_to_earnings != null ? ` (${c.days_to_earnings}d)` : ''}` : null)));

  const says = (title, list, cls) => el('.card', {}, el('h2', { text: title }), list.length ? el('.say.' + cls, {}, list.map(b => el('blockquote', {}, b.text, el('cite', {}, b.analyst ? el('a', { href: '#/a/' + encodeURIComponent(b.analyst), text: b.analyst }) : b.channel, ` · ${day(b.day)} · `, el('a', { href: b.link, target: '_blank', rel: 'noopener', text: 'watch' })))))
    : el('p.small', { text: 'Nobody made this case in the last three months.' }));

  hold.replaceChildren(
    el('.quote', {}, el('div', {}, el('.row', {}, el('span.badge', { text: t }), c.sector ? el('span.chip', { text: c.sector }) : null), el('h1', { style: { marginTop: '6px' }, text: c.name || t })), el('span.sp'),
      el('div', { style: { textAlign: 'right' } }, el('.px', { text: money(c.price, c.currency) }), el('div', {}, el('b', { class: tone(c.change_pct_day), text: pct(c.change_pct_day, 2) }), el('span.small', { text: ` today · close of ${day(c.as_of)}` }))), act),
    el('.hero', {}, el('.card', {}, el('h2', {}, 'Price', move != null ? el('span', { class: tone(move), style: { fontWeight: 600 }, text: pct(move) }) : null, el('span.sp'), seg), chartBox,
      el('p.small', { style: { marginTop: '6px' }, text: '▲ ▼ mark the days an analyst made a bullish or bearish call. Click one to watch it.' })), signalCard),
    el('.grid.g3', { style: { marginTop: '14px' } }, videoCard, streetCard, stats),
    el('.grid.g2', { style: { marginTop: '14px' } }, says('Bulls say', c.bulls || [], 'bull'), says('Bears say', c.bears || [], 'bear')),
    calls.length ? el('.card.flush', { style: { marginTop: '14px' } }, el('h2', { style: { padding: '16px 20px 0' }, text: `Every call in the last three months (${calls.length})` }), callsTable(calls, false)) : null,
    el('p.small', { style: { marginTop: '14px' }, text: 'The signal sums up what analysts said; it is not personal financial advice and can be wrong. Prices are daily closes and can be delayed.' }));
}

// ---------------------------------------------------------------- which page
function gate(root, what) {
  root.append(el('.card.empty', { style: { marginTop: '20px' } }, el('h3', { text: `Sign in to see ${what}` }), 'It is free and takes one click.', el('div', {}, el('button.btn.primary', { onclick: signIn }, 'Continue with Google'))));
}
export function render() {
  if (data.problem) { app.replaceChildren(el('.center', {}, el('.card.empty', {}, el('h3', { text: 'Something is not working' }), data.problem, el('div', {}, el('button.btn.primary', { onclick: () => location.reload() }, 'Reload'))))); return; }
  if (!data.user && !data.example) { landing(); return; }
  if (!data.profile) { app.replaceChildren(el('.center', {}, skeleton(40))); return; }
  if (data.user && !data.profile.onboarded && !data.profile.stocks.length) { app.replaceChildren(el('div')); welcome(app.firstChild, () => { go('#/'); render(); }); document.title = 'Welcome · Market Digest'; return; }
  const [name, ...rest] = location.hash.replace(/^#\/?/, '').split('/'), arg = decodeURIComponent(rest.join('/'));
  const page = el('.page');
  const active = name === 's' ? '' : name === 'a' ? 'analysts' : name;
  shell(active, page);
  window.scrollTo(0, 0);
  const titles = { '': 'My stocks', ideas: 'Ideas', analysts: 'Analysts', calendar: 'Calendar', account: 'Account' };
  document.title = `${titles[name] || arg || 'Market Digest'} · Market Digest`;
  const run = fn => Promise.resolve(fn()).catch(e => { console.error(e); page.append(el('.card.empty', {}, el('h3', { text: 'This page could not load' }), friendly(e), el('div', {}, el('button.btn', { onclick: render }, 'Try again')))); });
  if (name === 's') run(() => stock(page, arg));
  else if (name === 'account') run(() => account(page, render));
  else if (data.example && name) gate(page, { ideas: 'ideas beyond this list', analysts: 'the analysts and their records', a: 'this analyst', calendar: 'the calendar' }[name] || 'this page');
  else if (name === 'ideas') run(() => ideas(page, render));
  else if (name === 'analysts') run(() => analysts(page));
  else if (name === 'a') run(() => analyst(page, arg));
  else if (name === 'calendar') run(() => calendar(page));
  else if (name === 'status') run(() => status(page));
  else run(() => home(page));
}

window.addEventListener('hashchange', render);
app.replaceChildren(el('.center', {}, el('div', { style: { width: '220px' } }, skeleton(40))));
data.start(render);
