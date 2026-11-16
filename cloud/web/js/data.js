// Everything the pages know about the outside world: who is signed in, their list, and the shared stock data.
// Signed in, it reads Firestore. Not signed in, it can show the public example (the first pack, as it stands today).
import { initializeApp } from '../vendor/firebase-app.js';
import { getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signInWithRedirect, signInWithCredential, signOut, deleteUser, connectAuthEmulator }
  from '../vendor/firebase-auth.js';
import { getFirestore, doc, getDoc, setDoc, deleteDoc, collection, query, where, getDocs, documentId, connectFirestoreEmulator }
  from '../vendor/firebase-firestore-lite.js';

const LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
const TTL = 10 * 60 * 1000;
export const docId = t => String(t).replace(/\//g, '-').replace(/\^/g, '_');
export const cleanTicker = s => { const t = String(s || '').trim().toUpperCase().replace(/\s+/g, ''); return /^\^?[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(t) ? t : ''; };

let auth, db;
const cache = { cards: new Map(), market: new Map(), charts: new Map() };

export const data = {
  user: null,        // the Firebase user, or null
  profile: null,     // { email, name, photo, stocks: [{t, shares, cost}], prefs, onboarded }
  example: false,    // true while looking at the public example without signing in
  problem: null,     // why the service could not be reached, if it could not

  async start(onChange) {
    try {
      const config = LOCAL ? { apiKey: 'demo-key', projectId: 'demo-md', authDomain: 'demo-md.firebaseapp.com' }
        : await (await fetch('/__/firebase/init.json')).json();
      // Sign-in runs on this site's own address (Firebase Hosting serves the sign-in helper here too), so browsers
      // that block third-party storage, like Safari, do not break it.
      if (/\.(web\.app|firebaseapp\.com)$/.test(location.hostname)) config.authDomain = location.hostname;
      const app = initializeApp(config);
      auth = getAuth(app); db = getFirestore(app);
      if (LOCAL) {
        connectAuthEmulator(auth, 'http://127.0.0.1:9099', { disableWarnings: true });
        connectFirestoreEmulator(db, '127.0.0.1', 8080);
        // the emulator takes a made-up Google account, which is how the tests sign in
        window.__mdSignInAs = (email, name) => signInWithCredential(auth, GoogleAuthProvider.credential(JSON.stringify({ sub: 'u-' + email, email, email_verified: true, name })));
      }
    } catch (e) {
      this.problem = 'Market Digest could not start. Check your connection and reload the page.';
      onChange(); return;
    }
    onAuthStateChanged(auth, async user => {
      this.user = user; this.profile = null;
      if (user) {
        this.example = false;
        try { await this.loadProfile(); } catch (e) { this.problem = friendly(e); }
      }
      onChange();
    });
  },

  async signIn() {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    try { await signInWithPopup(auth, provider); }
    catch (e) {
      if (/popup-closed|cancelled-popup/.test(e.code || '')) return;
      if (/popup-blocked|operation-not-supported/.test(e.code || '')) { await signInWithRedirect(auth, provider); return; }   // no pop-ups here: use the whole page
      throw new Error(friendly(e));
    }
  },
  async signOut() { cache.cards.clear(); cache.market.clear(); cache.charts.clear(); await signOut(auth); },
  async deleteAccount() {
    await deleteDoc(doc(db, 'users', this.user.uid));
    try { await deleteUser(this.user); }
    catch (e) { await signOut(auth); }   // Google asks for a fresh sign-in before deleting: the data is gone either way
  },

  async loadProfile() {
    const ref = doc(db, 'users', this.user.uid), snap = await getDoc(ref);
    if (snap.exists()) { this.profile = { stocks: [], prefs: {}, ...snap.data() }; return; }
    const kept = readLocal();   // stocks picked in the example before signing in come along
    this.profile = { email: this.user.email, name: this.user.displayName || '', photo: this.user.photoURL || '',
      stocks: kept, prefs: { daily: 'every', weekly: true }, onboarded: kept.length > 0, created: new Date().toISOString() };
    await setDoc(ref, this.profile);
    localStorage.removeItem('md.example');
  },

  // Change the profile (the list of stocks, the email choices) and save it.
  async save(patch) {
    this.profile = { ...this.profile, ...patch };
    if (this.example) { localStorage.setItem('md.example', JSON.stringify(this.profile.stocks)); return; }
    const p = this.profile;
    const clean = { email: this.user.email, name: String(p.name || '').slice(0, 80), photo: String(p.photo || '').slice(0, 600),
      stocks: (p.stocks || []).slice(0, 60).map(tidy), prefs: { daily: p.prefs.daily || 'every', weekly: p.prefs.weekly !== false },
      onboarded: !!p.onboarded, created: p.created || new Date().toISOString(), updated: new Date().toISOString() };
    await setDoc(doc(db, 'users', this.user.uid), clean);
    const missing = clean.stocks.map(s => s.t).filter(t => { const c = cache.cards.get(t); return !c || !c.card; });
    for (const t of missing.slice(0, 20)) this.request(t);
  },

  _example: null,
  async publicExample() {
    if (!this._example) {
      const snap = await getDoc(doc(db, 'public', 'demo'));
      if (!snap.exists()) throw new Error('The example is not ready yet. Sign in to start.');
      this._example = snap.data();
    }
    return this._example;
  },
  async startExample() {
    const d = await this.publicExample();
    for (const c of d.cards || []) cache.cards.set(c.ticker, { card: c, at: Date.now() + 1e12 });
    for (const [k, ch] of Object.entries(d.charts || {})) cache.charts.set(k, ch);
    const kept = readLocal();
    this.example = true;
    this.profile = { name: '', email: '', stocks: kept.length ? kept : (d.cards || []).map((c, i) => i < 3 ? { t: c.ticker, shares: [10, 12, 5][i] } : { t: c.ticker }),
      prefs: { daily: 'every', weekly: true }, onboarded: true };
  },
  leaveExample() { this.example = false; this.profile = null; },

  // The cards for these tickers: { TICKER: card or null }. Read once, then kept for ten minutes.
  async cards(tickers) {
    const want = [...new Set(tickers.map(cleanTicker).filter(Boolean))], out = {}, need = [];
    for (const t of want) { const c = cache.cards.get(t); if (c && Date.now() - c.at < TTL) out[t] = c.card; else need.push(t); }
    if (need.length && !this.example) {
      const byId = new Map(need.map(t => [docId(t), t]));
      const ids = [...byId.keys()];
      for (let i = 0; i < ids.length; i += 30) {
        const snap = await getDocs(query(collection(db, 'stocks'), where(documentId(), 'in', ids.slice(i, i + 30))));
        snap.forEach(d => { const t = byId.get(d.id); cache.cards.set(t, { card: d.data(), at: Date.now() }); });
      }
    }
    for (const t of need) { if (!cache.cards.has(t) || Date.now() - cache.cards.get(t).at >= TTL) cache.cards.set(t, { card: null, at: Date.now() - TTL + 60000 }); out[t] = cache.cards.get(t).card; }
    return out;
  },
  async card(t) { return (await this.cards([t]))[cleanTicker(t)] || null; },
  remember(rows) { for (const r of Object.values(rows || {})) if (r && r.ticker && !cache.cards.has(r.ticker)) cache.cards.set(r.ticker, { card: null, row: r, at: 0 }); },

  async chart(t) {
    const id = docId(cleanTicker(t));
    if (cache.charts.has(id)) return cache.charts.get(id);
    if (this.example) return null;
    const snap = await getDoc(doc(db, 'charts', id)), ch = snap.exists() ? snap.data() : null;
    cache.charts.set(id, ch); return ch;
  },
  async market(name) {
    const c = cache.market.get(name);
    if (c && Date.now() - c.at < TTL) return c.doc;
    if (this.example) return null;
    const snap = await getDoc(doc(db, 'market', name)), d = snap.exists() ? snap.data() : null;
    cache.market.set(name, { doc: d, at: Date.now() }); return d;
  },
  // "Please start covering this stock": the engine picks it up on its next run.
  async request(t) {
    if (this.example || !this.user) return;
    try { await setDoc(doc(db, 'requests', docId(t)), { by: this.user.uid, at: new Date().toISOString() }); } catch (e) { /* already asked for */ }
  },

  _symbols: null,
  async symbols() {
    if (!this._symbols) {
      try { this._symbols = await (await fetch('/symbols.json')).json(); } catch (e) { this._symbols = []; }
    }
    return this._symbols;
  },
};

function tidy(s) {
  const out = { t: cleanTicker(s.t) };
  const shares = Number(s.shares), cost = Number(s.cost);
  if (shares > 0 && isFinite(shares)) out.shares = shares;
  if (cost > 0 && isFinite(cost)) out.cost = cost;
  return out;
}
function readLocal() {
  try { return (JSON.parse(localStorage.getItem('md.example') || '[]') || []).map(tidy).filter(s => s.t).slice(0, 60); } catch (e) { return []; }
}
function friendly(e) {
  const code = (e && e.code) || '';
  if (/popup-blocked/.test(code)) return 'Your browser blocked the sign-in window. Allow pop-ups for this site and try again.';
  if (/network/.test(code)) return 'No connection. Check the internet and try again.';
  if (/permission-denied/.test(code)) return 'That is not allowed for this account.';
  if (/resource-exhausted/.test(code)) return 'Market Digest is very busy right now. Please try again in a few minutes.';
  return 'Something went wrong. Please try again.';
}
export { friendly };

// A user's stocks joined with their cards, with what they hold worked out: rows for the table, and totals.
export function portfolio(profile, cards) {
  const rows = [];
  for (const s of (profile && profile.stocks) || []) {
    const c = cards[s.t];
    const base = c || { ticker: s.t, name: '', signal: 'none', confidence_pct: null, calls: { bullish: 0, bearish: 0, neutral: 0, mixed: 0, analysts: [] }, factors: [], pending: true };
    const value = s.shares && base.price != null ? s.shares * base.price : null;
    rows.push({ ...base, shares: s.shares || null, cost: s.cost || null, value, owned: !!s.shares,
      gain_pct: s.cost && base.price != null ? (base.price / s.cost - 1) * 100 : null });
  }
  const owned = rows.filter(r => r.value != null), currencies = new Set(owned.map(r => r.currency || 'USD'));
  const total = owned.length && currencies.size === 1 ? owned.reduce((a, r) => a + r.value, 0) : null;
  for (const r of rows) r.weight = total && r.value != null ? Math.round(1000 * r.value / total) / 10 : null;
  const dayChange = total ? owned.reduce((a, r) => a + r.value * (r.change_pct_day || 0) / (100 + (r.change_pct_day || 0)), 0) / total * 100 : null;
  const cost = owned.every(r => r.cost) && owned.length ? owned.reduce((a, r) => a + r.cost * r.shares, 0) : null;
  return { rows, total, currency: [...currencies][0] || 'USD', dayChange, gain_pct: total && cost ? (total / cost - 1) * 100 : null,
    counts: { yes: rows.filter(r => r.signal === 'yes').length, wait: rows.filter(r => r.signal === 'wait').length, no: rows.filter(r => r.signal === 'no').length } };
}

// The few things worth a user's attention today, most pressing first. Each is one short line about one stock.
export function forYou(rows) {
  const W = { yes: 'YES', no: 'NO', wait: 'WAIT', none: '—' }, out = [];
  for (const r of rows) {
    const add = (pri, tone, icon, text) => out.push({ pri, tone, icon, text, ticker: r.ticker });
    if (r.changed) add(100, r.changed.to === 'yes' ? 'good' : r.changed.to === 'no' ? 'bad' : 'warn', 'swap', `turned ${W[r.changed.to]} (was ${W[r.changed.from]})`);
    if (r.owned && r.signal === 'no') add(90, 'bad', 'alert', 'You own it and analysts say No');
    if (r.days_to_earnings != null && r.days_to_earnings <= 7) {
      const d = Math.round(r.days_to_earnings);
      add(80 - d, 'warn', 'clock', `reports earnings ${d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`}: expect a bigger move`);
    }
    if (r.weight != null && r.weight >= 35) add(70, 'warn', 'pie', `is ${Math.round(r.weight)}% of your portfolio: a lot on one stock`);
    if (r.signal === 'yes' && (r.confidence_pct || 0) >= 75 && !r.owned) add(55 + r.confidence_pct / 10, 'good', 'up', `Strong Yes (${r.confidence_pct}%) and you do not own it`);
    if (Math.abs(r.change_pct_day || 0) >= 5) add(50, r.change_pct_day > 0 ? 'good' : 'bad', r.change_pct_day > 0 ? 'up' : 'down', `moved ${r.change_pct_day > 0 ? '+' : ''}${r.change_pct_day.toFixed(1)}% today`);
    if ((r.factors || []).some(f => /disagree/i.test(f.text))) add(40, 'info', 'info', 'Video analysts and Wall Street disagree');
  }
  out.sort((a, b) => b.pri - a.pri);
  const kinds = {};   // at most two of a kind, so three earnings dates do not crowd out everything else
  return out.filter(x => (kinds[x.icon] = (kinds[x.icon] || 0) + 1) <= 2).slice(0, 5);
}

// Tickers in pasted text: a Google Finance page, a broker export, or a typed list. Only symbols we know, or typed plainly.
export function tickersIn(text, known) {
  const names = new Set(known.map(s => s[0])), out = [];
  const typed = /^[\sA-Za-z0-9.,;:^\-]+$/.test(text) && text.length < 400;
  for (const raw of String(text).split(/[\s,;|]+/)) {
    let w = raw.replace(/^(NASDAQ|NYSE|NYSEARCA|NSE|BSE|LON):/i, '').replace(/:(NASDAQ|NYSE|NSE|BSE)$/i, '');
    const t = cleanTicker(w);
    if (!t || /^\d+([.-]\d+)?$/.test(t)) continue;
    if (names.has(t) ? (w === w.toUpperCase() || typed) : (typed && /^[A-Z]{1,5}([.-][A-Z]{1,2})?$/.test(w))) out.push(t);
  }
  return [...new Set(out)].slice(0, 60);
}
