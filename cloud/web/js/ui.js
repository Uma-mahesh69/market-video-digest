// Small building blocks used by every page: elements, formats, icons, charts, modal and toast.
export const $ = (sel, root = document) => root.querySelector(sel);
export function el(tag, attrs, ...kids) {
  const [name, ...cls] = tag.split('.');
  const e = document.createElement(name || 'div');
  if (cls.length) e.className = cls.join(' ');
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'text') e.textContent = v;
    else if (k === 'html') e.innerHTML = v;   // only ever given our own icon markup
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className += ' ' + v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
}
const NS = 'http://www.w3.org/2000/svg';
export function svg(tag, attrs, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid) e.append(kid);
  return e;
}

// ---------------------------------------------------------------- formats
export const pct = (x, digits = 1) => x == null || isNaN(x) ? '—' : `${x > 0 ? '+' : ''}${Number(x).toFixed(Math.abs(x) >= 100 ? 0 : digits)}%`;
export const tone = x => x == null ? 'mut' : x > 0 ? 'up' : x < 0 ? 'down' : 'mut';
export function money(x, cur = 'USD', compact = false) {
  if (x == null || isNaN(x)) return '—';
  const opts = cur && cur.length === 3 ? { style: 'currency', currency: cur } : {};
  // compact: T, B, M for every currency but the rupee (an Indian browser would otherwise write $3T as "$3.00LCr")
  if (compact) return x.toLocaleString(cur === 'INR' ? 'en-IN' : 'en-US', { ...opts, notation: 'compact', maximumFractionDigits: 2 });
  const big = Math.abs(x) >= 10000;
  return x.toLocaleString(undefined, { ...opts, maximumFractionDigits: big ? 0 : 2, minimumFractionDigits: big ? 0 : 2 });
}
export const num = (x, d = 1) => x == null || isNaN(x) ? '—' : Number(x).toLocaleString(undefined, { maximumFractionDigits: d });
export const day = (d, long) => d ? new Date(d.length === 10 ? d + 'T12:00:00' : d).toLocaleDateString(undefined, long ? { day: 'numeric', month: 'long', year: 'numeric' } : { day: 'numeric', month: 'short' }) : '';
export function ago(iso) {
  if (!iso) return '';
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 2 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
}
export const safeUrl = u => (typeof u === 'string' && /^https:\/\//i.test(u) ? u : null);   // links from data: https only
// The experts' view, in words that describe them rather than tell anyone what to do (see docs/PRODUCT.md).
export const SIGNAL = { yes: 'Bullish', no: 'Bearish', wait: 'Split', none: '—' };
export const SIGNAL_SAYS = { yes: 'Experts clearly favour it', no: 'Experts are clearly against it', wait: 'Experts are split', none: 'No expert views yet' };
// The sentence under a signal, as strong as the confidence behind it: "clearly" only when it is.
export function says(signal, conf) {
  if (signal !== 'yes' && signal !== 'no') return SIGNAL_SAYS[signal] || SIGNAL_SAYS.none;
  const yes = signal === 'yes';
  if (conf == null || conf >= 70) return SIGNAL_SAYS[signal];
  if (conf >= 45) return yes ? 'Experts lean in favour' : 'Experts lean against it';
  return yes ? 'Leaning bullish, on thin or mixed evidence' : 'Leaning bearish, on thin or mixed evidence';
}
export const COLOR = { yes: 'var(--green)', no: 'var(--red)', wait: 'var(--amber)', none: 'var(--grey)' };

// ---------------------------------------------------------------- icons (Lucide-style strokes, drawn here)
const P = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  bulb: '<path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.3h6c0-1 .4-1.800 1-2.300A7 7 0 0 0 12 2z"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.870M16 3.130a4 4 0 0 1 0 7.750"/>',
  cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.300-4.300"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  up: '<path d="m5 12 7-7 7 7M12 19V5"/>',
  down: '<path d="m19 12-7 7-7-7M12 5v14"/>',
  swap: '<path d="M17 3l4 4-4 4M3 7h18M7 21l-4-4 4-4M21 17H3"/>',
  alert: '<path d="M10.300 3.900 1.800 18a2 2 0 0 0 1.700 3h17a2 2 0 0 0 1.700-3L13.700 3.900a2 2 0 0 0-3.400 0zM12 9v4M12 17h.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  pie: '<path d="M21.200 15.900A10 10 0 1 1 8 2.800"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
  more: '<circle cx="12" cy="5" r="1.300"/><circle cx="12" cy="12" r="1.300"/><circle cx="12" cy="19" r="1.300"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  play: '<path d="m6 3 14 9-14 9z"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  spark: '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
  edit: '<path d="M12 20h9M16.500 3.500a2.100 2.100 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  trash: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  wallet: '<path d="M20 7H5a2 2 0 0 1 0-4h13v4M3 5v14a2 2 0 0 0 2 2h15V7"/><path d="M16 14h.01"/>',
  trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
};
export function icon(name) {
  const s = svg('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
  s.innerHTML = P[name] || '';
  return s;
}
export function logoMark() {
  const s = svg('svg', { viewBox: '0 0 28 28', 'aria-hidden': 'true' });
  s.innerHTML = '<rect width="28" height="28" rx="8" fill="var(--brand)"/><path d="M7 18.500 11.500 13l3.500 3.500L21 9.500" fill="none" stroke="var(--on-brand)" stroke-width="2.400" stroke-linecap="round" stroke-linejoin="round"/><circle cx="21" cy="9.500" r="1.900" fill="var(--on-brand)"/>';
  return s;
}
export function googleMark() {
  const s = svg('svg', { viewBox: '0 0 18 18', 'aria-hidden': 'true' });
  s.innerHTML = '<path fill="#4285F4" d="M17.640 9.200c0-.640-.060-1.250-.160-1.840H9v3.480h4.840a4.140 4.140 0 0 1-1.800 2.720v2.260h2.920c1.700-1.570 2.680-3.880 2.680-6.620z"/><path fill="#34A853" d="M9 18c2.430 0 4.470-.800 5.960-2.180l-2.920-2.260c-.800.540-1.840.860-3.040.860-2.340 0-4.330-1.580-5.040-3.710H.960v2.330A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.960 10.710a5.410 5.410 0 0 1 0-3.420V4.960H.960a9 9 0 0 0 0 8.080z"/><path fill="#EA4335" d="M9 3.580c1.320 0 2.500.450 3.440 1.350l2.580-2.580C13.460.890 11.430 0 9 0A9 9 0 0 0 .960 4.960l3 2.330C4.670 5.160 6.660 3.580 9 3.580z"/>';
  return s;
}
export function stars(n) {
  if (n == null) return null;   // not rated yet: say nothing rather than tag every new name
  const box = el('span.stars', { title: `${n} of 5`, role: 'img', 'aria-label': `${n} of 5 stars` });
  for (let i = 1; i <= 5; i++) {
    const fill = n >= i ? 1 : n >= i - 0.5 ? 0.5 : 0, id = 'h' + Math.random().toString(36).slice(2, 8);
    const s = svg('svg', { viewBox: '0 0 24 24' });
    s.innerHTML = `<defs><linearGradient id="${id}"><stop offset="${fill * 100}%" stop-color="var(--star)"/><stop offset="${fill * 100}%" stop-color="var(--line)"/></linearGradient></defs><path fill="url(#${id})" d="m12 2 3.100 6.300 6.900 1-5 4.900 1.200 6.900L12 17.800 5.800 21.100 7 14.200 2 9.300l6.900-1z"/>`;
    box.append(s);
  }
  return box;
}

// ---------------------------------------------------------------- small visuals
export const sig = (s, big) => el('span.sig.' + s + (big ? '.lg' : ''), { text: SIGNAL[s] || '—', title: SIGNAL_SAYS[s] });
export function confidence(card) {
  if (card.confidence_pct == null) return el('span.mut', { text: '—' });
  return el('.conf', {}, el('.track', {}, el('i', { style: { width: card.confidence_pct + '%', background: card.signal === 'wait' ? 'var(--grey)' : COLOR[card.signal] } })),
    el('b', { text: card.confidence_pct + '%' }));
}
export function meter(parts) {   // [[count, color], ...]
  const total = parts.reduce((a, p) => a + p[0], 0) || 1, m = el('.meter');
  for (const [n, color] of parts) if (n) m.append(el('i', { style: { width: (100 * n / total) + '%', background: color } }));
  return m;
}
export function split(calls) {
  const bull = calls.bullish || 0, bear = calls.bearish || 0, other = (calls.neutral || 0) + (calls.mixed || 0);
  if (!bull && !bear && !other) return el('span.mut', { text: '—' });
  return el('.split', { title: `${bull} bullish, ${bear} bearish${other ? `, ${other} neutral or mixed` : ''} calls` },
    el('.t', {}, el('span.up', { text: `${bull} ▲` }), '  ', el('span.down', { text: `${bear} ▼` })),
    meter([[bull, 'var(--green)'], [other, 'var(--grey)'], [bear, 'var(--red)']]));
}
export function range(card) {
  if (card.price == null || card.low_52w == null || card.high_52w == null || card.high_52w <= card.low_52w) return el('span.mut', { text: '—' });
  const at = Math.max(0, Math.min(100, 100 * (card.price - card.low_52w) / (card.high_52w - card.low_52w)));
  return el('.range', { title: `Past year: low ${money(card.low_52w, card.currency)}, high ${money(card.high_52w, card.currency)}` }, el('i', { style: { left: at + '%' } }));
}
export function spark(values, w = 84, h = 26) {
  const s = svg('svg', { viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: 'img' });
  if (!values || values.length < 2) return s;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => `${(2 + i * (w - 4) / (values.length - 1)).toFixed(1)},${(2 + (h - 4) * (1 - (v - min) / span)).toFixed(1)}`);
  s.setAttribute('aria-label', `Three months: ${pct((values[values.length - 1] / values[0] - 1) * 100)}`);
  s.append(svg('polyline', { points: pts.join(' '), fill: 'none', stroke: values[values.length - 1] >= values[0] ? 'var(--green)' : 'var(--red)', 'stroke-width': 1.6, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  return s;
}
export function ring(pctValue, color) {
  const r = 44, c = 2 * Math.PI * r, s = svg('svg', { viewBox: '0 0 104 104' });
  s.append(svg('circle', { cx: 52, cy: 52, r, fill: 'none', stroke: 'var(--line-2)', 'stroke-width': 10 }));
  if (pctValue != null) s.append(svg('circle', { cx: 52, cy: 52, r, fill: 'none', stroke: color, 'stroke-width': 10, 'stroke-linecap': 'round', 'stroke-dasharray': `${c * pctValue / 100} ${c}` }));
  return el('.ring', {}, s, el('.in', {}, el('b', { text: pctValue == null ? '—' : pctValue + '%' }), el('span', { text: 'confidence' })));
}

// The price chart: a line, its area, and a marker for every analyst call (green up, red down). Hover for the price.
export function priceChart(dates, closes, calls, currency) {
  const box = el('.chart'), W = 760, H = 260, padT = 14, padB = 22;
  if (!closes || closes.length < 2) { box.append(el('.empty', { text: 'No prices yet.' })); return box; }
  const min = Math.min(...closes), max = Math.max(...closes), span = max - min || 1;
  const x = i => i * W / (closes.length - 1), y = v => padT + (H - padT - padB) * (1 - (v - min) / span);
  const up = closes[closes.length - 1] >= closes[0], color = up ? 'var(--green)' : 'var(--red)';
  const line = closes.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': `Price chart, ${pct((closes[closes.length - 1] / closes[0] - 1) * 100)} over the period` });
  for (const v of [min, (min + max) / 2, max]) s.append(svg('line', { x1: 0, x2: W, y1: y(v), y2: y(v), stroke: 'var(--line-2)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke' }));
  s.append(svg('path', { d: `M0,${H - padB} L${line.replace(/ /g, ' L')} L${W},${H - padB} Z`, fill: color, opacity: .08 }));
  s.append(svg('polyline', { points: line, fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke' }));
  const cursor = svg('line', { y1: padT, y2: H - padB, stroke: 'var(--grey)', 'stroke-width': 1, 'stroke-dasharray': '3 3', 'vector-effect': 'non-scaling-stroke', visibility: 'hidden' });
  s.append(cursor);
  box.append(s);
  // call markers sit in HTML over the chart so they stay round whatever the width
  const index = new Map(dates.map((d, i) => [d, i]));
  const seen = {};
  for (const c of calls || []) {
    if (c.view !== 'bullish' && c.view !== 'bearish') continue;
    let i = index.get(c.day);
    if (i == null) i = dates.findIndex(d => d >= c.day);
    if (i == null || i < 0) continue;
    const key = i + c.view; seen[key] = (seen[key] || 0) + 1;
    if (seen[key] > 1) continue;
    const bull = c.view === 'bullish';
    box.append(el('a', { href: c.link, target: '_blank', rel: 'noopener', title: `${day(c.day)} · ${c.analyst || c.channel}: ${c.view}`,
      style: { position: 'absolute', left: `calc(${100 * x(i) / W}% - 7px)`, top: `calc(${100 * y(closes[i]) / H}% ${bull ? '+ 6px' : '- 20px'})`, width: '14px', height: '14px', color: bull ? 'var(--green)' : 'var(--red)', fontSize: '12px', lineHeight: '14px', textAlign: 'center', textDecoration: 'none' } }, bull ? '▲' : '▼'));
  }
  const tip = el('.tip', { hidden: true }); box.append(tip);
  const move = ev => {
    const r = s.getBoundingClientRect(), i = Math.max(0, Math.min(closes.length - 1, Math.round((ev.clientX - r.left) / r.width * (closes.length - 1))));
    cursor.setAttribute('x1', x(i)); cursor.setAttribute('x2', x(i)); cursor.setAttribute('visibility', 'visible');
    tip.hidden = false; tip.textContent = `${day(dates[i])} · ${money(closes[i], currency)}`;
    tip.style.left = Math.max(60, Math.min(r.width - 60, (x(i) / W) * r.width)) + 'px'; tip.style.top = (y(closes[i]) / H) * r.height + 'px';
  };
  s.addEventListener('pointermove', move); s.addEventListener('pointerdown', move);
  s.addEventListener('pointerleave', () => { tip.hidden = true; cursor.setAttribute('visibility', 'hidden'); });
  box.append(el('.axis', {}, el('span', { text: day(dates[0]) }), el('span', { text: `${money(min, currency)} – ${money(max, currency)}` }), el('span', { text: day(dates[dates.length - 1]) })));
  return box;
}

// ---------------------------------------------------------------- modal, toast, menu
export function modal(title, body, actions) {
  const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  const box = el('.modal', { role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, el('h2', { text: title }), body, actions ? el('.acts', {}, actions(close)) : null);
  const overlay = el('.overlay', { onpointerdown: e => { if (e.target === overlay) close(); } }, box);
  document.addEventListener('keydown', onKey);
  document.body.append(overlay);
  const first = box.querySelector('input,textarea,button');
  if (first) first.focus();
  return close;
}
let toastTimer;
export function toast(text) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = el('.toast', { role: 'status', text }); document.body.append(t);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.remove(), 3200);
}
export function menu(anchor, items) {   // items: [[label, iconName, fn, cls]]
  document.querySelectorAll('.menu').forEach(m => m.remove());
  const m = el('.menu', { role: 'menu' });
  for (const [label, ic, fn, cls] of items) m.append(el('button', { role: 'menuitem', class: cls || '', onclick: e => { e.stopPropagation(); m.remove(); fn(); } }, ic ? icon(ic) : null, label));
  m.querySelectorAll('svg').forEach(s => { s.style.width = '16px'; s.style.height = '16px'; });
  anchor.style.position = 'relative'; anchor.append(m);
  setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }), 0);
}
export const skeleton = (h = 120) => el('.skel', { style: { height: h + 'px' } });
