// The pages other than Home and the stock page, and two pieces they share with them: the stock table and the picker.
import { el, icon, pct, tone, money, day, sig, confidence, split, range, spark, stars, modal, toast, menu, skeleton, SIGNAL } from './ui.js';
import { data, cleanTicker, tickersIn, friendly } from './data.js';

export const go = hash => { location.hash = hash; };
export const has = t => !!(data.profile && data.profile.stocks.some(s => s.t === t));

// ---------------------------------------------------------------- the stock table
const COLS = [
  ['Stock', '', r => r.ticker], ['Price', 'r', r => r.price, 'The latest closing price'], ['Today', 'r hide-s', r => r.change_pct_day, 'The change on the latest market day'],
  ['Invest?', 'c', r => ({ yes: 3, wait: 2, no: 1, none: 0 })[r.signal], 'What the analysts\' views add up to: Yes, No, or Wait when they are split'],
  ['Confidence', 'conf-h', r => r.confidence_pct, 'How much stands behind the signal, from 5% to 95%'],
  ['Analysts', 'hide-x4', r => (r.calls.bullish || 0) - (r.calls.bearish || 0), 'Bullish and bearish calls in the videos, last 30 days'],
  ['Wall St', 'hide-x3', r => (r.street || {}).consensus || '', 'The consensus of professional analysts, from TipRanks'],
  ['Target', 'r hide-x4', r => (r.street || {}).upside_pct, 'How far Wall Street\'s 12-month price target is from today\'s price'],
  ['3 months', 'c hide-x2', r => r.spark && r.spark.length > 1 ? r.spark[r.spark.length - 1] / r.spark[0] : null, 'The price over the last three months'],
  ['52-week range', 'c hide-x1', r => r.high_52w > r.low_52w ? (r.price - r.low_52w) / (r.high_52w - r.low_52w) : null, 'Where the price sits between the year\'s low (left) and high (right)'], ['', 'c', null]];
const sorts = {};

// rows: cards (with shares/weight when they are the user's). action(row) gives the last cell.
export function stockTable(id, rows, action) {
  const wrap = el('.scroll');
  const draw = () => {
    wrap.textContent = '';
    const sort = sorts[id];
    const list = sort ? [...rows].sort((a, b) => { const g = COLS[sort.col][2], x = g(a), y = g(b); return x == null ? 1 : y == null ? -1 : (x > y ? 1 : x < y ? -1 : 0) * sort.dir; }) : rows;
    const head = el('tr');
    COLS.forEach(([label, cls, get, tip], i) => {
      const th = el('th', { class: cls + (get ? ' sort' : ''), text: label, title: tip ? tip + '. Click to sort.' : null });
      if (get) {
        if (sort && sort.col === i) th.setAttribute('aria-sort', sort.dir > 0 ? 'ascending' : 'descending');
        th.onclick = () => { if (sort && sort.col === i) { if (sort.dir < 0) sorts[id] = { col: i, dir: 1 }; else delete sorts[id]; } else sorts[id] = { col: i, dir: -1 }; draw(); };
      }
      head.append(th);
    });
    const body = el('tbody');
    for (const r of list) {
      const st = r.street || {};
      const tr = el('tr.link', { tabindex: 0, onclick: () => go('#/s/' + encodeURIComponent(r.ticker)), onkeydown: e => { if (e.key === 'Enter') go('#/s/' + encodeURIComponent(r.ticker)); } });
      const names = el('div', {}, el('.n', { text: r.name || r.ticker, title: r.name || '' }));
      if (r.owned) names.append(el('.o', {}, 'You own', r.weight != null ? el('span.hide-s', { text: ` · ${r.weight}%` }) : null));
      else if (r.pending) names.append(el('.o', { text: 'Fetching…' }));
      tr.append(el('td', {}, el('.sym', {}, el('span.badge', { text: r.ticker }), names)),
        el('td.r', {}, r.price == null ? '—' : money(r.price, r.currency), r.change_pct_day != null ? el('.day2', { class: tone(r.change_pct_day), text: pct(r.change_pct_day) }) : null),
        el('td.r.hide-s', { class: tone(r.change_pct_day), text: pct(r.change_pct_day) }),
        el('td.c', {}, sig(r.signal)), el('td', {}, confidence(r)), el('td.hide-x4', {}, split(r.calls)),
        el('td.hide-x3', { text: st.consensus || '—', class: st.consensus ? '' : 'mut', style: { whiteSpace: 'nowrap' } }),
        el('td.r.hide-x4', { class: tone(st.upside_pct), text: pct(st.upside_pct) }),
        el('td.c.hide-x2', {}, r.spark && r.spark.length > 1 ? spark(r.spark) : '—'), el('td.c.hide-x1', {}, range(r)),
        el('td.c', { onclick: e => e.stopPropagation() }, action ? action(r) : el('span.mut', {}, icon('right'))));
      body.append(tr);
    }
    wrap.append(el('table', {}, el('thead', {}, head), body));
    wrap.querySelectorAll('td:last-child>span svg').forEach(s => { s.style.width = '16px'; s.style.height = '16px'; });
  };
  draw();
  return wrap;
}
export function addButton(r, after) {
  if (has(r.ticker)) return el('span.chip.good', {}, 'In my list');
  return el('button.btn.sm', { onclick: async e => { e.stopPropagation(); await addStocks([r.ticker]); toast(`${r.ticker} added to your stocks`); if (after) after(); } }, icon('plus'), 'Add');
}
export async function addStocks(tickers) {
  const have = new Set(data.profile.stocks.map(s => s.t));
  const fresh = tickers.map(cleanTicker).filter(t => t && !have.has(t));
  if (!fresh.length) return 0;
  await data.save({ stocks: [...data.profile.stocks, ...fresh.map(t => ({ t }))].slice(0, 60), onboarded: true });
  return fresh.length;
}

// ---------------------------------------------------------------- choosing stocks: starter lists, search, paste
export function picker(chosen, onChange) {
  const box = el('div'), picked = el('.picked'), results = el('.results', { hidden: true }), input = el('input.input', { placeholder: 'Search a company or ticker, like Apple or AAPL', autocomplete: 'off', 'aria-label': 'Search a stock' });
  const packs = el('.packs');
  const set = list => { chosen.splice(0, chosen.length, ...[...new Set(list)].slice(0, 60)); draw(); onChange(chosen); };
  function draw() {
    picked.textContent = '';
    if (!chosen.length) picked.append(el('span.small', { text: 'Nothing chosen yet.' }));
    for (const t of chosen) picked.append(el('span.chip.brand', {}, t, el('button', { 'aria-label': 'Remove ' + t, onclick: () => set(chosen.filter(x => x !== t)) }, '×')));
    packs.querySelectorAll('.pack').forEach(p => p.classList.toggle('on', p._t.every(t => chosen.includes(t))));
  }
  data.market('meta').then(meta => {
    for (const p of (meta && meta.packs) || FALLBACK_PACKS) {
      const b = el('button.pack', { type: 'button', onclick: () => set(b.classList.contains('on') ? chosen.filter(t => !p.tickers.includes(t)) : [...chosen, ...p.tickers]) },
        el('b', { text: p.name }), el('span', { text: p.tickers.slice(0, 4).join(', ') + (p.tickers.length > 4 ? '…' : '') }));
      b._t = p.tickers; packs.append(b);
    }
    draw();
  }).catch(() => {});
  let timer;
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(async () => {
    const q = input.value.trim().toUpperCase(); results.textContent = '';
    if (!q) { results.hidden = true; return; }
    const hits = search(await data.symbols(), q);
    const typed = cleanTicker(q);
    if (typed && !hits.some(h => h[0] === typed)) hits.push([typed, 'Add this ticker']);
    for (const [t, name] of hits.slice(0, 8)) results.append(el('button', { type: 'button', onclick: () => { set([...chosen, t]); input.value = ''; results.hidden = true; input.focus(); } },
      el('span.badge', { text: t }), el('span.nm', { text: name }), chosen.includes(t) ? el('span.small', { text: 'chosen' }) : icon('plus')));
    results.querySelectorAll('svg').forEach(s => { s.style.width = '16px'; s.style.height = '16px'; s.style.color = 'var(--muted)'; });
    results.hidden = !hits.length;
  }, 120); };
  input.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); const b = results.querySelector('button'); if (b && !results.hidden) b.click(); } };
  const paste = el('textarea.input', { placeholder: 'Paste here', 'aria-label': 'Paste your list' });
  const pasteBox = el('div', { hidden: true }, el('p.small', { style: { margin: '10px 0 6px' }, text: 'On google.com/finance (or your broker), select the whole page with Ctrl+A, copy with Ctrl+C, and paste it here. We pick out the tickers.' }),
    paste, el('div', { style: { marginTop: '8px' } }, el('button.btn.sm', { type: 'button', onclick: async () => {
      const found = tickersIn(paste.value, await data.symbols());
      if (!found.length) { toast('No tickers found in that text'); return; }
      set([...chosen, ...found]); paste.value = ''; pasteBox.hidden = true; toast(`${found.length} stock${found.length === 1 ? '' : 's'} found`);
    } }, 'Find my stocks')));
  box.append(el('.eyebrow', { text: 'Start with a list', style: { marginBottom: '8px' } }), packs,
    el('.eyebrow', { text: 'Or search', style: { margin: '18px 0 8px' } }), el('div', { style: { position: 'relative' } }, input, results),
    el('button.btn.ghost.sm', { type: 'button', style: { marginTop: '8px', marginLeft: '-8px' }, onclick: () => { pasteBox.hidden = !pasteBox.hidden; if (!pasteBox.hidden) paste.focus(); } }, 'Or paste a list from Google Finance or a broker'),
    pasteBox, el('.eyebrow', { text: 'Your stocks', style: { margin: '18px 0 8px' } }), picked);
  draw();
  return box;
}
const FALLBACK_PACKS = [{ name: 'Big Tech', tickers: ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA'] }];
export function search(symbols, q) {
  const exact = [], starts = [], named = [];
  for (const s of symbols) {
    if (s[0] === q) exact.push(s); else if (s[0].startsWith(q)) starts.push(s); else if (q.length > 1 && s[1].toUpperCase().includes(q)) named.push(s);
    if (starts.length > 40) break;
  }
  named.sort((a, b) => a[1].toUpperCase().indexOf(q) - b[1].toUpperCase().indexOf(q));
  return [...exact, ...starts, ...named].slice(0, 8);
}
export function addModal(after) {
  const chosen = [];
  let save;
  const close = modal('Add stocks', picker(chosen, c => { if (save) save.disabled = !c.length; }), done => {
    save = el('button.btn.primary', { disabled: true, onclick: async () => { save.disabled = true; try { const n = await addStocks(chosen); done(); toast(n ? `${n} stock${n === 1 ? '' : 's'} added` : 'Already in your list'); after(); } catch (e) { toast(friendly(e)); save.disabled = false; } } }, 'Add to my stocks');
    return [el('button.btn', { onclick: done }, 'Cancel'), save];
  });
  return close;
}
export function holdingModal(row, after) {
  const s = data.profile.stocks.find(x => x.t === row.ticker) || { t: row.ticker };
  const shares = el('input.input', { type: 'number', min: 0, step: 'any', inputmode: 'decimal', value: s.shares || '', placeholder: 'Leave empty if you only watch it' });
  const cost = el('input.input', { type: 'number', min: 0, step: 'any', inputmode: 'decimal', value: s.cost || '', placeholder: 'Optional: shows your gain' });
  modal(`${row.ticker}: what you hold`, el('div', { style: { marginTop: '12px' } },
    el('.field', {}, el('label', { text: 'Shares you own' }), shares), el('.field', {}, el('label', { text: `Average price you paid${row.currency ? ' (' + row.currency + ')' : ''}` }), cost),
    el('p.small', { text: 'Only you can see this. It is used to show your value, gain and how much of your portfolio it is.' })),
  done => [el('button.btn.danger', { style: { marginRight: 'auto' }, onclick: async () => { await data.save({ stocks: data.profile.stocks.filter(x => x.t !== row.ticker) }); done(); toast(`${row.ticker} removed`); after(); } }, 'Remove from my stocks'),
    el('button.btn', { onclick: done }, 'Cancel'),
    el('button.btn.primary', { onclick: async () => {
      const next = { t: row.ticker, shares: Number(shares.value) || undefined, cost: Number(cost.value) || undefined };
      await data.save({ stocks: has(row.ticker) ? data.profile.stocks.map(x => x.t === row.ticker ? next : x) : [...data.profile.stocks, next] });
      done(); toast('Saved'); after();
    } }, 'Save')]);
}
export function rowMenu(row, after) {
  const b = el('button.icon-btn', { 'aria-label': `Options for ${row.ticker}`, onclick: e => { e.stopPropagation(); menu(b.parentElement, [
    ['Edit what I hold', 'edit', () => holdingModal(row, after)],
    ['Remove', 'trash', async () => { await data.save({ stocks: data.profile.stocks.filter(x => x.t !== row.ticker) }); toast(`${row.ticker} removed`); after(); }, 'danger']]); } }, icon('more'));
  return b;
}

// ---------------------------------------------------------------- first visit: choose your stocks
export function welcome(root, done) {
  const chosen = data.profile.stocks.map(s => s.t);
  const next = el('button.btn.primary.lg', { disabled: !chosen.length, onclick: async () => {
    next.disabled = true;
    try { await data.save({ stocks: chosen.map(t => data.profile.stocks.find(s => s.t === t) || { t }), onboarded: true }); done(); }
    catch (e) { toast(friendly(e)); next.disabled = false; }
  } }, 'Show my dashboard');
  root.append(el('.onb', {}, el('.eyebrow', { text: 'One step' }), el('h1', { text: 'Which stocks do you follow?' }),
    el('p.mut', { style: { margin: '6px 0 22px', fontSize: '15px' }, text: 'Pick a list or search. You can change this any time, and add how many shares you own later.' }),
    el('.card', {}, picker(chosen, c => { next.disabled = !c.length; })),
    el('.row', { style: { marginTop: '18px' } }, next, el('span.small', { text: 'Free during the beta. No card needed.' }))));
}

// ---------------------------------------------------------------- ideas
export async function ideas(root, refresh) {
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'Ideas' }), el('.sub', { text: 'What the analysts are saying about stocks beyond your list.' }))));
  const hold = el('div', {}, skeleton(320)); root.append(hold);
  const o = await data.market('overview'); hold.textContent = '';
  if (!o) { hold.append(el('.card.empty', {}, el('h3', { text: 'Nothing here yet' }), 'This fills in after the first videos are read.')); return; }
  const tabs = [['yes', 'Strongest Yes'], ['no', 'Strongest No'], ['discussed', 'Most discussed'], ['split', 'Analysts split'], ['changed', 'Just changed']];
  let tab = sessionStorage.getItem('md.ideas') || 'yes';
  if (!(o.lists[tab] || []).length) tab = (tabs.find(([k]) => (o.lists[k] || []).length) || tabs[0])[0];   // open on a list that has something
  const seg = el('.seg', { role: 'group', 'aria-label': 'Which ideas' }), card = el('.card.flush');
  if (!o.videos) hold.append(el('.banner', { style: { marginBottom: '14px' } }, 'No videos have been read yet. For now the signals come from Wall Street’s ratings alone; analysts’ calls appear here as the videos are read.'));
  const draw = () => {
    seg.textContent = ''; card.textContent = '';
    for (const [k, label] of tabs) seg.append(el('button', { 'aria-pressed': String(k === tab), onclick: () => { tab = k; sessionStorage.setItem('md.ideas', k); draw(); } }, label, el('span.mut', { text: ' ' + (o.lists[k] || []).length })));
    const rows = (o.lists[tab] || []).map(t => o.rows[t]).filter(Boolean);
    if (!rows.length) card.append(el('.empty', { text: tab === 'changed' ? 'No signal changed in the last week.' : 'Nothing in this list right now.' }));
    else card.append(stockTable('ideas-' + tab, rows, r => addButton(r, draw)));
  };
  hold.append(el('.grid.g4', { style: { marginBottom: '14px' } },
    tile('Videos read', o.videos, `${o.channels} channel${o.channels === 1 ? '' : 's'}, last 30 days`),
    tile('Analyst mood', o.mood_pct == null ? '—' : o.mood_pct + '% bullish', `${o.views.bullish} bullish, ${o.views.bearish} bearish calls`, o.mood_pct == null ? '' : o.mood_pct >= 50 ? 'up' : 'down'),
    tile('Bullish calls that beat the market', o.scorecard.bullish.hit_pct == null ? '—' : o.scorecard.bullish.hit_pct + '%', o.scorecard.bullish.scored ? `${o.scorecard.bullish.right} of ${o.scorecard.bullish.scored} scored calls` : 'Scored after 3 trading days'),
    tile('Bearish calls that proved right', o.scorecard.bearish.hit_pct == null ? '—' : o.scorecard.bearish.hit_pct + '%', o.scorecard.bearish.scored ? `${o.scorecard.bearish.right} of ${o.scorecard.bearish.scored} scored calls` : 'Scored after 3 trading days')),
    el('.row', { style: { marginBottom: '12px' } }, seg), card);
  if (o.top_calls && o.top_calls.length) hold.append(el('.card', { style: { marginTop: '14px' } }, el('h2', { text: 'Fresh bullish calls from the best-rated analysts' }),
    el('.list', {}, o.top_calls.map(c => el('div', { style: { alignItems: 'center' } }, el('span.when', { text: day(c.day) }), el('a.badge', { href: '#/s/' + encodeURIComponent(c.ticker), text: c.ticker }),
      el('.body', {}, el('a', { href: '#/a/' + encodeURIComponent(c.analyst), style: { fontWeight: 600 }, text: c.analyst }), ' ', stars(c.stars), el('.small', { text: c.reason })),
      sig(c.signal), el('a.icon-btn', { href: c.link, target: '_blank', rel: 'noopener', title: 'Watch this moment', 'aria-label': 'Watch this moment' }, icon('play')))))));
  if (o.themes && o.themes.length) hold.append(el('.card', { style: { marginTop: '14px' } }, el('h2', { text: "Today's themes" }), o.themes.map(t => el('.theme', {}, el('b', { text: t.theme }), el('span', { text: t.detail })))));
  draw();
}
export const tile = (k, v, s, cls) => el('.card.tile', {}, el('.k', { text: k }), el('.v', { class: cls || '', text: v }), el('.s', { text: s || '' }));

// ---------------------------------------------------------------- analysts
function outcome(o) {
  if (!o) return el('span.small', { text: 'too early' });
  return el('span', { class: o.right ? 'up' : 'down', title: `Stock ${pct(o.stock_pct)}, S&P 500 ${pct(o.sp500_pct)} since the call`, text: `${o.right ? 'Right' : 'Wrong'} · ${o.edge > 0 ? '+' : ''}${o.edge} pts` });
}
export function callsTable(calls, withStock) {
  const body = el('tbody');
  for (const c of calls) {
    body.append(el('tr', {}, el('td', { class: 'small', style: { whiteSpace: 'nowrap' }, text: day(c.day) }),
      withStock ? el('td', {}, el('a.badge', { href: '#/s/' + encodeURIComponent(c.ticker), text: c.ticker })) :
        el('td', {}, c.analyst ? el('a', { href: '#/a/' + encodeURIComponent(c.analyst), style: { fontWeight: 600 }, text: c.analyst }) : el('span', { text: c.channel }), c.analyst_stars != null ? el('div', {}, stars(c.analyst_stars)) : null),
      el('td', {}, el('span.pill.' + c.view, { text: c.view })), el('td.hide-s', { style: { maxWidth: '380px' }, text: c.reason || '' }),
      el('td.r', {}, outcome(c.outcome)),
      el('td.c', {}, el('a.icon-btn', { href: c.link, target: '_blank', rel: 'noopener', title: 'Watch this moment', 'aria-label': 'Watch this moment' }, icon('play')))));
  }
  return el('.scroll', {}, el('table', {}, el('thead', {}, el('tr', {}, el('th', { text: 'Date' }), el('th', { text: withStock ? 'Stock' : 'Analyst' }), el('th', { text: 'Call' }),
    el('th.hide-s', { text: 'Reason' }), el('th.r', { text: 'Result vs S&P 500' }), el('th.c', { text: 'Video' }))), body));
}
export async function analysts(root) {
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'Analysts' }), el('.sub', { text: 'Who makes the calls, and how often they have been right over the last four months.' }))));
  const hold = el('div', {}, skeleton(360)); root.append(hold);
  const a = await data.market('analysts'); hold.textContent = '';
  if (!a || !a.rows.length) { hold.append(el('.card.empty', {}, el('h3', { text: 'No analysts yet' }), 'This fills in after the first videos are read.')); return; }
  const body = el('tbody');
  a.rows.forEach((r, i) => body.append(el('tr.link', { tabindex: 0, onclick: () => go('#/a/' + encodeURIComponent(r.analyst)), onkeydown: e => { if (e.key === 'Enter') go('#/a/' + encodeURIComponent(r.analyst)); } },
    el('td.c.mut.hide-s', { text: i + 1 }),
    el('td', {}, el('div', { style: { fontWeight: 700 }, text: r.analyst }), el('.small', { text: r.role || '' })),
    el('td', {}, stars(r.stars)),
    el('td.r', {}, r.scored ? el('b', { text: r.hit_pct + '%' }) : '—', r.scored ? el('.small', { text: `${r.right} of ${r.scored}` }) : null),
    el('td.r', { class: tone(r.edge), text: r.edge == null ? '—' : `${r.edge > 0 ? '+' : ''}${r.edge} pts` }),
    el('td.r.hide-s', { text: r.calls }), el('td.hide-m', {}, split({ bullish: r.bullish, bearish: r.bearish, neutral: Math.max(0, r.calls - r.bullish - r.bearish) })),
    el('td.hide-m', {}, r.stocks.slice(0, 4).map(t => el('span.badge', { style: { marginRight: '4px' }, text: t }))))));
  hold.append(el('.card.flush', {}, el('.scroll', {}, el('table', {}, el('thead', {}, el('tr', {}, el('th.c.hide-s', { text: '#' }), el('th', { text: 'Analyst' }), el('th', { text: 'Rating' }),
    el('th.r', { text: 'Calls right' }), el('th.r', { text: 'Avg vs S&P 500' }), el('th.r.hide-s', { text: 'Calls' }), el('th.hide-m', { text: 'Bull / bear' }), el('th.hide-m', { text: 'Talks about' }))), body))),
  el('p.small', { style: { marginTop: '10px' }, text: 'A call is right when the stock then did better than the S&P 500 (bullish) or worse (bearish), from the next close after the video. The rating needs at least 3 scored calls.' }));
}
export async function analyst(root, name) {
  root.append(el('a.crumb', { href: '#/analysts' }, icon('left'), 'Analysts'));
  const hold = el('div', {}, skeleton(300)); root.append(hold);
  const a = await data.market('analysts'), r = a && a.rows.find(x => x.analyst === name); hold.textContent = '';
  if (!r) { hold.append(el('.card.empty', {}, el('h3', { text: name }), 'No recent calls from this analyst.')); return; }
  hold.append(el('.head', {}, el('div', {}, el('h1', { text: r.analyst }), el('.sub', { text: r.role || 'Analyst' })), el('.sp'), stars(r.stars)),
    el('.grid.g4', { style: { marginBottom: '14px' } }, tile('Calls right', r.scored ? r.hit_pct + '%' : '—', r.scored ? `${r.right} of ${r.scored} scored calls` : 'Not enough scored calls yet'),
      tile('Average vs S&P 500', r.edge == null ? '—' : `${r.edge > 0 ? '+' : ''}${r.edge} pts`, 'per call, since it was made', tone(r.edge)),
      tile('Calls', r.calls, `${r.bullish} bullish, ${r.bearish} bearish`), tile('Talks about', r.stocks.slice(0, 3).join(', ') || '—', 'most often')),
    el('.card.flush', {}, el('h2', { style: { padding: '16px 20px 0' }, text: 'Latest calls' }), callsTable(r.recent, true)));
}

// ---------------------------------------------------------------- calendar and videos
export async function calendar(root) {
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'Calendar' }), el('.sub', { text: 'Earnings dates, market events and the latest videos read.' }))));
  const hold = el('div', {}, skeleton(300)); root.append(hold);
  const [cal, vids] = await Promise.all([data.market('calendar'), data.market('videos')]); hold.textContent = '';
  const mine = new Set((data.profile.stocks || []).map(s => s.t));
  let all = sessionStorage.getItem('md.cal') === 'all';
  const earn = el('.list');
  const draw = () => {
    earn.textContent = '';
    const rows = ((cal && cal.earnings) || []).filter(e => all || mine.has(e.ticker)).slice(0, 40);
    if (!rows.length) earn.append(el('p.small', { text: all ? 'No earnings dates known yet.' : 'No earnings in the next six weeks for your stocks.' }));
    for (const e of rows) earn.append(el('a', { href: '#/s/' + encodeURIComponent(e.ticker), style: { color: 'inherit', alignItems: 'center' } },
      el('span.when', { text: day(e.date) }), el('span.badge', { text: e.ticker }), el('span.body', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, text: e.name || '' }),
      el('span.small', { text: e.days === 0 ? 'today' : e.days === 1 ? 'tomorrow' : `in ${e.days} days` }), sig(e.signal)));
  };
  const seg = el('.seg', {}, ...[['mine', 'My stocks'], ['all', 'All covered']].map(([k, label]) => { const b = el('button', { 'aria-pressed': String((k === 'all') === all), onclick: () => { all = k === 'all'; sessionStorage.setItem('md.cal', k); seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); draw(); } }, label); return b; }));
  draw();
  const events = el('.list');
  if (!cal || !cal.events.length) events.append(el('p.small', { text: 'No dated events were mentioned in the videos.' }));
  for (const e of (cal && cal.events) || []) events.append(el('div', {}, el('span.when', { text: e.date ? day(e.date) : (e.when || 'Soon') }), el('a.body', { href: e.link, target: '_blank', rel: 'noopener', text: e.event })));
  const videos = el('.list');
  if (!vids || !vids.rows.length) videos.append(el('p.small', { text: 'No videos read yet.' }));
  for (const v of ((vids && vids.rows) || []).slice(0, 25)) videos.append(el('div', {}, el('span.when', { text: day(v.day) }),
    el('.body', {}, el('a', { href: v.link, target: '_blank', rel: 'noopener', style: { fontWeight: 600 }, text: v.title }), el('.small', { text: [v.channel, ...(v.speakers || [])].join(' · ') }),
      el('div', { style: { marginTop: '4px', display: 'flex', gap: '4px', flexWrap: 'wrap' } }, (v.stocks || []).map(s => el('a.chip.' + (s.view === 'bullish' ? 'good' : s.view === 'bearish' ? 'bad' : 'info'), { href: '#/s/' + encodeURIComponent(s.ticker), text: s.ticker }))))));
  hold.append(el('.grid.g2', {}, el('.card', {}, el('h2', {}, 'Earnings', el('span.sp'), seg), earn), el('.card', {}, el('h2', { text: 'Market events' }), events)),
    el('.card', { style: { marginTop: '14px' } }, el('h2', { text: 'Latest videos read' }), videos));
}

// ---------------------------------------------------------------- how to read it
const WORDS = [
  ['Invest? Yes / No / Wait', 'What the analysts\u2019 views on a stock add up to. YES: they clearly favour it. NO: they are clearly against it. WAIT: they are split. A dash means nobody has given a view yet. It is the same for everyone who follows that stock; it does not know your finances.'],
  ['Confidence', 'How much stands behind the signal, from 5% to 95%. It rises when the views are one-sided, when there are many of them, when the video analysts and Wall Street agree, and when earlier calls on that stock turned out right.'],
  ['Bullish, bearish', 'A bullish call expects the stock to rise; a bearish call expects it to fall.'],
  ['Analyst rating (stars)', 'How an analyst\u2019s past calls did: how often they were right, and by how much they beat the market. It needs at least 3 calls old enough to judge. A call counts more toward the signal when it comes from a well-rated analyst.'],
  ['Right or wrong, vs S&P 500', 'A bullish call is right when the stock then did better than the S&P 500 (an index of 500 large US companies: the usual yardstick for "the market"); a bearish call, when it did worse. "+4 pts" means it beat the market by 4 percentage points.'],
  ['Wall Street rating', 'The consensus of professional analysts at banks and brokers, from TipRanks: Strong Buy, Moderate Buy, Hold, Moderate Sell or Strong Sell.'],
  ['Price target', 'The price those analysts expect in about 12 months. "+18%" means 18% above today\u2019s price.'],
  ['Smart Score', 'TipRanks\u2019 own 1 to 10 score from eight factors. 8 and above is good; 3 and below is poor.'],
  ['52-week range', 'Where today\u2019s price sits between the lowest and the highest price of the past year.'],
  ['P/E', 'Price divided by a year\u2019s profit per share. Higher usually means more growth is expected.'],
  ['Market cap', 'What the whole company is worth at today\u2019s share price.'],
  ['Dividend yield', 'The yearly dividend as a share of the price. 2% means 2 back each year for every 100 invested, on top of any price change.'],
  ['Earnings', 'The day a company reports its results, four times a year. The price often moves a lot that day.'],
];
const FAQ = [
  ['Where do the signals come from?', 'Every day we go through new videos on the main finance channels and note each call an analyst makes on a stock, with the reason and the moment it was said. We add Wall Street\u2019s rating from TipRanks and the price. Code, not opinion, turns that into the signal.'],
  ['How fresh is it?', 'Videos are read through the day. Prices are daily closing prices. Wall Street\u2019s ratings are refreshed every few days, the stocks in people\u2019s lists first. The side menu shows when the last update ran.'],
  ['Why does my stock say "Fetching\u2026" or show a dash?', 'A stock nobody followed before is picked up within the hour. A dash under Invest? means no analyst has made a call on it lately and there is no Wall Street rating yet; smaller and non-US companies are covered less.'],
  ['Is this financial advice?', 'No. It sums up what analysts said, for everyone alike. Analysts are often wrong, and the reading of videos is automatic and can mishear. Use it to decide what to look at, then make your own decision or talk to a licensed adviser.'],
  ['What do you know about me?', 'Your Google name and email, your list, and the shares and prices you choose to type. Nothing else, and it is never sold. You can download or delete it under Account.'],
];
export function help(root) {
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'How it works' }), el('.sub', { text: 'What every number on Market Digest means, in plain words.' }))),
    el('.grid.g2', {}, el('.card', {}, el('h2', { text: 'Questions' }), FAQ.map(([q, a]) => el('.theme', {}, el('b', { text: q }), el('span', { text: a })))),
      el('.card', {}, el('h2', { text: 'The words' }), WORDS.map(([w, d]) => el('.theme', {}, el('b', { text: w }), el('span', { text: d }))))));
}
export function setTheme(t) {
  if (t) { document.documentElement.dataset.theme = t; localStorage.setItem('md.theme', t); }
  else { delete document.documentElement.dataset.theme; localStorage.removeItem('md.theme'); }
}

// ---------------------------------------------------------------- how the engine is doing (for whoever runs the service)
export async function status(root) {
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'Service status' }), el('.sub', { text: 'How the last run of the engine went.' }))));
  const s = await data.market('status');
  if (!s) { root.append(el('.card.empty', {}, el('h3', { text: 'The engine has not run yet' }), 'It runs every hour once it is set up.')); return; }
  const tr = s.tipranks || {};
  root.append(el('.grid.g4', {}, tile('Last run', new Date(s.last_run).toLocaleString(), s.ok ? 'Finished without errors' : 'Finished with errors', s.ok ? 'up' : 'down'),
    tile('Videos read today', s.videos_today, `${s.videos_kept} kept from the last four months`), tile('Stocks covered', s.stocks, `prices as of ${day(s.prices_as_of)}`),
    tile('TipRanks calls left', tr.remaining == null ? '—' : tr.remaining, tr.limit ? `of ${tr.limit} this month · ${tr.today || 0} used today` : 'No key, or not read yet')),
    el('.card', { style: { marginTop: '14px' } }, el('h2', { text: 'Problems in the last run' }), s.errors && s.errors.length ? el('.list', {}, s.errors.map(e => el('div', {}, el('span.body', { text: e })))) : el('p.small', { text: 'None.' })),
    el('p.small', { style: { marginTop: '10px' }, text: `${s.users} account${s.users === 1 ? '' : 's'}.` }));
}

// ---------------------------------------------------------------- account
export function account(root, refresh) {
  const p = data.profile, u = data.user;
  root.append(el('.head', {}, el('div', {}, el('h1', { text: 'Account' }), el('.sub', { text: 'Your emails and your data.' }))));
  if (data.example) { root.append(el('.card.empty', {}, el('h3', { text: 'This is the example' }), 'Sign in to save your stocks and get your emails.', el('div', {}, el('button.btn.primary', { onclick: () => data.signIn().catch(e => toast(e.message)) }, 'Continue with Google')))); return; }
  const save = async patch => { try { await data.save({ prefs: { ...data.profile.prefs, ...patch } }); toast('Saved'); } catch (e) { toast(friendly(e)); } };
  const daily = [['every', 'Every weekday', 'A short table of your stocks after the US market closes.'], ['changes', 'Only when a signal changes', 'Nothing unless one of your stocks turns Yes, No or Wait.'], ['off', 'Never', 'No daily email.']];
  root.append(el('.grid.g2', {},
    el('.card', {}, el('h2', { text: 'Profile' }), el('.row', {}, u.photoURL ? el('img.avatar', { src: u.photoURL, alt: '', referrerpolicy: 'no-referrer', style: { width: '44px', height: '44px' } }) : el('.avatar', { style: { width: '44px', height: '44px' }, text: (p.name || p.email || '?')[0].toUpperCase() }),
      el('div', {}, el('b', { text: p.name || 'You' }), el('.small', { text: p.email }))),
      el('p.small', { style: { margin: '14px 0' }, text: `${p.stocks.length} stock${p.stocks.length === 1 ? '' : 's'} in your list. Free during the beta.` }),
      el('.eyebrow', { text: 'Appearance', style: { marginBottom: '8px' } }),
      (() => { const now = localStorage.getItem('md.theme') || ''; const seg = el('.seg', { style: { marginBottom: '16px' } });
        for (const [k, label] of [['', 'Match my device'], ['light', 'Light'], ['dark', 'Dark']]) seg.append(el('button', { 'aria-pressed': String(k === now), onclick: e => { setTheme(k); seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === e.currentTarget))); } }, label));
        return seg; })(),
      el('div', {}, el('button.btn', { onclick: () => data.signOut() }, icon('out'), 'Sign out'))),
    el('.card', {}, el('h2', { text: 'Emails' }), el('p.small', { style: { marginBottom: '12px' }, text: `Sent to ${p.email}. Nothing else to set up.` }),
      el('.eyebrow', { text: 'Daily brief', style: { marginBottom: '8px' } }),
      daily.map(([k, label, hint]) => el('label.opt', {}, el('input', { type: 'radio', name: 'daily', checked: (p.prefs.daily || 'every') === k, onchange: () => save({ daily: k }) }), el('div', {}, el('b', { text: label }), el('span', { text: hint })))),
      el('label.switch', { style: { marginTop: '14px' } }, el('input', { type: 'checkbox', checked: p.prefs.weekly !== false, onchange: e => save({ weekly: e.target.checked }) }), el('div', {}, el('b', { text: 'Weekly summary' }), el('.small', { text: 'Every Saturday: the week on your stocks.' })))),
    el('.card', {}, el('h2', { text: 'Your data' }), el('p.small', { style: { marginBottom: '12px' }, text: 'We keep your email, your list of stocks, the shares and prices you typed, and your email choices. Nothing else.' }),
      el('.row', { style: { flexWrap: 'wrap' } }, el('button.btn', { onclick: () => {
        const blob = new Blob([JSON.stringify({ email: p.email, name: p.name, stocks: p.stocks, emails: p.prefs, created: p.created }, null, 2)], { type: 'application/json' });
        const a = el('a', { href: URL.createObjectURL(blob), download: 'market-digest-my-data.json' }); a.click(); URL.revokeObjectURL(a.href);
      } }, 'Download my data'), el('button.btn.danger', { onclick: () => modal('Delete your account?', el('p', { style: { marginTop: '8px' }, text: 'Your list, your holdings and your email choices are deleted now and cannot be brought back. The emails stop.' }),
        done => [el('button.btn', { onclick: done }, 'Keep my account'), el('button.btn.danger', { onclick: async () => { try { await data.deleteAccount(); done(); } catch (e) { toast(friendly(e)); } } }, 'Delete everything')]) }, 'Delete my account'))),
    el('.card', {}, el('h2', { text: 'How the signals work' }),
      el('p.small', { style: { lineHeight: 1.6 }, text: 'We read the finance channels every day and note each analyst call on a stock. A stock gets YES when the calls and Wall Street’s rating clearly favour it, NO when they are clearly against it, and WAIT when they are split. A call counts more from an analyst whose past calls beat the market. Confidence (5% to 95%) grows with how one-sided the views are, how many there are, and how earlier calls on that stock turned out.' }),
      el('p.small', { style: { marginTop: '10px', lineHeight: 1.6 }, text: 'The signals sum up what analysts said. They are not personal financial advice, and analysts are often wrong. For decisions that matter, talk to a licensed adviser.' }),
      el('p.small', { style: { marginTop: '10px' } }, el('a', { href: '#/help', text: 'How it works, in full' }), ' · ', el('a', { href: '/privacy.html', text: 'Privacy' }), ' · ', el('a', { href: '/terms.html', text: 'Terms' }), ' · ', el('a', { href: '#/status', text: 'Service status' })))));
}
