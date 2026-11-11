/**
 * Market Digest email service: sends each user's digest from the developer's Gmail, so users only type their address.
 *
 * Runs as a Google Apps Script web app, under the account that deploys it. Setup: email_service/README.md.
 *
 * How it stays safe, although the app (and so this address) is public:
 * - It only emails an address after its owner typed a 6-digit code that was sent to that address. So it cannot be
 *   used to send mail to strangers, only to yourself.
 * - Each confirmed address gets its own secret key, kept on that user's computer; a digest is sent only with it.
 * - Per address: at most 3 codes and 8 emails a day. Overall: at most 40 codes a day.
 * - The "Users" tab of the spreadsheet lists every address. Type "blocked" in its Status to stop one.
 * Gmail sends at most 100 emails a day from a personal account through Apps Script (1,500 with Google Workspace);
 * the "status" action reports what is left today.
 */

const APP_TOKEN = 'md-7Kq2vX9pL4nR8sT1wY6z';   // must match service.json in the app; it identifies the app, it is not a password
const MAX_CODES_PER_ADDRESS = 3;
const MAX_CODES_PER_DAY = 40;
const MAX_EMAILS_PER_ADDRESS = 8;
const CODE_MINUTES = 30;
const MAX_BODY = 180000;   // characters: Gmail via Apps Script refuses bigger bodies, so bigger digests go as an attachment
const SENDER_NAME = 'Market Digest';

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return reply({ ok: false, error: 'bad request' }); }
  if (!req || req.token !== APP_TOKEN) return reply({ ok: false, error: 'not allowed' });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const email = String(req.email || '').trim().toLowerCase();
    if (req.action === 'status') return reply({ ok: true, remaining_today: MailApp.getRemainingDailyQuota() });
    if (!/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(email)) return reply({ ok: false, error: 'That is not an email address.' });
    if (req.action === 'code') return reply(sendCode(email));
    if (req.action === 'confirm') return reply(confirm(email, String(req.code || '').trim()));
    if (req.action === 'send') return reply(send(email, String(req.key || ''), req));
    return reply({ ok: false, error: 'unknown action' });
  } catch (err) {
    return reply({ ok: false, error: String(err.message || err) });
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  return ContentService.createTextOutput('Market Digest email service is running.');
}

// ---------------------------------------------------------------- the actions

function sendCode(email) {
  const u = user(email, true);
  if (u.get('status') === 'blocked') return { ok: false, error: 'This address cannot use the Market Digest email service.' };
  if (daily(u, 'codes') >= MAX_CODES_PER_ADDRESS) return { ok: false, error: 'Too many codes for this address today. Try again tomorrow.' };
  if (allCodes() >= MAX_CODES_PER_DAY) return { ok: false, error: 'The email service is busy today. Try again tomorrow.' };
  const code = String(Math.floor(100000 + Math.random() * 900000));
  u.set('code_hash', hash(code));
  u.set('code_until', new Date(Date.now() + CODE_MINUTES * 60000).toISOString());
  MailApp.sendEmail({
    to: email, name: SENDER_NAME, subject: 'Your Market Digest code: ' + code,
    body: 'Your code is ' + code + '. Type it into Market Digest to get your digests at this address.\n\n'
        + 'It works for ' + CODE_MINUTES + ' minutes. If you did not ask for it, ignore this email: nothing will be sent to you.',
  });
  bumpDaily(u, 'codes'); bumpAllCodes();
  return { ok: true };
}

function confirm(email, code) {
  const u = user(email, false);
  if (!u || !u.get('code_hash')) return { ok: false, error: 'Ask for a code first.' };
  if (new Date(u.get('code_until')) < new Date()) return { ok: false, error: 'That code has expired. Ask for a new one.' };
  if (hash(code) !== u.get('code_hash')) {
    bumpDaily(u, 'wrong');
    if (daily(u, 'wrong') >= 5) u.set('code_hash', '');   // too many guesses: a new code is needed
    return { ok: false, error: 'That code is not right. Check the email and type the 6 digits.' };
  }
  const key = Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '');
  u.set('key_hash', hash(key));
  u.set('code_hash', '');
  if (u.get('status') !== 'blocked') u.set('status', 'confirmed');
  u.set('confirmed', new Date().toISOString());
  return { ok: true, key: key };
}

function send(email, key, req) {
  const u = user(email, false);
  if (!u || u.get('status') !== 'confirmed' || !key || hash(key) !== u.get('key_hash')) {
    return { ok: false, error: 'This address is not confirmed for this computer. Confirm it again in Market Digest > Settings.' };
  }
  if (daily(u, 'mails') >= MAX_EMAILS_PER_ADDRESS) return { ok: false, error: 'This address has had its emails for today.' };
  if (MailApp.getRemainingDailyQuota() < 1) return { ok: false, error: "The email service has used today's Gmail quota. The digest is still in Market Digest." };
  const subject = String(req.subject || 'Your market digest').slice(0, 200);
  let html = String(req.html || ''), text = String(req.text || '').slice(0, MAX_BODY);
  const message = { to: email, name: SENDER_NAME, subject: subject, body: text || 'Your market digest is attached.' };
  if (html.length <= MAX_BODY) {
    message.htmlBody = html;
  } else {   // too big for an email body: send it as a page to open
    message.htmlBody = '<p>Your digest is long today, so it is attached. Open <b>digest.html</b> to read it.</p>';
    message.attachments = [Utilities.newBlob(html, 'text/html', 'digest.html')];
  }
  MailApp.sendEmail(message);
  bumpDaily(u, 'mails');
  u.set('last_sent', new Date().toISOString());
  u.set('sent', Number(u.get('sent') || 0) + 1);
  return { ok: true };
}

// ---------------------------------------------------------------- the Users tab

const COLUMNS = ['email', 'status', 'confirmed', 'last_sent', 'sent', 'code_hash', 'code_until', 'key_hash', 'day', 'codes', 'wrong', 'mails'];

function sheet() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  let s = book.getSheetByName('Users');
  if (!s) {
    s = book.insertSheet('Users');
    s.appendRow(COLUMNS);
    s.setFrozenRows(1);
  }
  return s;
}

function user(email, create) {
  const s = sheet();
  const data = s.getDataRange().getValues();
  let row = data.findIndex((r, i) => i > 0 && String(r[0]).toLowerCase() === email);
  if (row < 0) {
    if (!create) return null;
    s.appendRow([email, 'pending', '', '', 0, '', '', '', today(), 0, 0, 0]);
    row = s.getLastRow() - 1;
  }
  const r = row + 1;
  return {
    get: (col) => s.getRange(r, COLUMNS.indexOf(col) + 1).getValue(),
    set: (col, value) => s.getRange(r, COLUMNS.indexOf(col) + 1).setValue(value),
  };
}

// ---------------------------------------------------------------- small helpers

function today() { return Utilities.formatDate(new Date(), 'UTC', 'yyyy-MM-dd'); }
// Today's counts per address live in the Users tab; they restart when the day changes.
function daily(u, col) { return String(u.get('day')) === today() ? Number(u.get(col) || 0) : 0; }
function bumpDaily(u, col) {
  if (String(u.get('day')) !== today()) { u.set('day', today()); ['codes', 'wrong', 'mails'].forEach((c) => u.set(c, 0)); }
  u.set(col, daily(u, col) + 1);
}
function allCodes() {
  const p = PropertiesService.getScriptProperties();
  return p.getProperty('codes_day') === today() ? Number(p.getProperty('codes') || 0) : 0;
}
function bumpAllCodes() {
  const p = PropertiesService.getScriptProperties(), n = allCodes() + 1;
  p.setProperties({ codes_day: today(), codes: String(n) });
}
function hash(s) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(s))
    .map((b) => ('0' + (b & 255).toString(16)).slice(-2)).join('');
}
function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
