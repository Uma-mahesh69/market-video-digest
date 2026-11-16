"""The emails, sent by us from one address: the user gives nothing but the address they signed in with.

Two kinds: the daily brief (every weekday, or only when a signal changed, as each user chose) and the weekly summary.
Each is a short table of the user's own stocks with what changed, never a wall of text."""
import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

SIGNAL = {"yes": ("YES", "#1A7F37"), "no": ("NO", "#B42318"), "wait": ("WAIT", "#8A5A00"), "none": ("—", "#5C6878")}
e = lambda x: html.escape(str(x if x is not None else ""))


def pct(x):
    return "—" if x is None else f"{'+' if x > 0 else ''}{x:.1f}%"


def money(x, cur="USD"):
    if x is None:
        return "—"
    sym = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(cur or "USD", "")
    return f"{sym}{x:,.0f}" if abs(x) >= 1000 else f"{sym}{x:,.2f}"


def user_view(user, cards):
    """The user's stocks with their cards, what they hold, and the short notes worth their attention."""
    rows, total = [], 0.0
    for s in user.get("stocks") or []:
        card = cards.get(s.get("t"))
        if not card or card.get("unknown"):
            continue
        shares = s.get("shares") or 0
        value = shares * card["price"] if shares and card.get("price") else None
        total += value or 0
        rows.append({**card, "shares": shares, "value": value})
    notes = []
    for r in rows:
        r["weight"] = round(100 * r["value"] / total) if r["value"] and total else None
        ch = r.get("changed")
        if ch:
            notes.append({"tone": "good" if ch["to"] == "yes" else "bad" if ch["to"] == "no" else "warn", "changed": True, "on": ch["on"],
                          "text": f"{r['ticker']} turned {SIGNAL[ch['to']][0]} (was {SIGNAL[ch['from']][0]})"})
        if r["shares"] and r["signal"] == "no":
            notes.append({"tone": "bad", "text": f"You own {r['ticker']}: analysts say No"})
        if r.get("days_to_earnings") is not None and r["days_to_earnings"] <= 5:
            d = int(r["days_to_earnings"])
            notes.append({"tone": "warn", "text": f"{r['ticker']} reports earnings {'today' if d == 0 else 'tomorrow' if d == 1 else f'in {d} days'}"})
        if r["weight"] and r["weight"] >= 35:
            notes.append({"tone": "warn", "text": f"{r['ticker']} is {r['weight']}% of your portfolio"})
    return {"rows": rows, "total": total or None, "notes": notes}


def wants(user, kind, view, today):
    """Should this user get this email today?"""
    prefs = user.get("prefs") or {}
    if not user.get("email") or not view["rows"]:
        return False
    if kind == "weekly":
        return prefs.get("weekly", True) is not False
    choice = prefs.get("daily", "every")
    if choice == "off" or today.weekday() >= 5 and choice != "changes":
        return False
    if choice == "changes":
        return any(n.get("changed") and n.get("on") == today.isoformat() for n in view["notes"])
    return True


def compose(user, view, kind, today, site):
    """(subject, html, text) for one user."""
    rows, notes = view["rows"], view["notes"]
    changed = [n for n in notes if n.get("changed")]
    counts = {k: sum(r["signal"] == k for r in rows) for k in ("yes", "wait", "no")}
    lead = changed[0]["text"] if changed else f"{counts['yes']} Yes, {counts['wait']} Wait, {counts['no']} No on your stocks"
    subject = (f"Your week: {lead}" if kind == "weekly" else lead + (f" and {len(notes) - 1} more" if changed and len(notes) > 1 else "")) + " · Market Digest"
    tone = {"good": ("#E6F4EA", "#1A7F37"), "bad": ("#FDECEA", "#B42318"), "warn": ("#FFF4D6", "#8A5A00")}
    chips = "".join(f'<div style="margin:0 0 6px;padding:8px 12px;border-radius:8px;background:{tone[n["tone"]][0]};color:{tone[n["tone"]][1]};font-size:14px;font-weight:600">{e(n["text"])}</div>'
                    for n in notes[:6])
    td = 'style="padding:9px 8px;border-bottom:1px solid #E5E9F0;font-size:14px"'
    body = ""
    for r in rows[:30]:
        word, color = SIGNAL[r["signal"]]
        move = r.get("change_pct_week") if kind == "weekly" else r.get("change_pct_day")
        body += (f'<tr><td {td}><b>{e(r["ticker"])}</b><div style="color:#5C6878;font-size:12px">{e((r.get("name") or "")[:28])}</div></td>'
                 f'<td {td} align="center"><span style="display:inline-block;min-width:44px;padding:3px 8px;border-radius:6px;background:{color};color:#fff;font-weight:700;font-size:12px">{word}</span></td>'
                 f'<td {td} align="right">{str(r["confidence_pct"]) + "%" if r.get("confidence_pct") is not None else "—"}</td>'
                 f'<td {td} align="right">{e(money(r.get("price"), r.get("currency")))}</td>'
                 f'<td align="right" style="padding:9px 8px;border-bottom:1px solid #E5E9F0;font-size:14px;color:{"#1A7F37" if (move or 0) > 0 else "#B42318" if (move or 0) < 0 else "#5C6878"}">{pct(move)}</td></tr>')
    th = 'style="padding:6px 8px;font-size:11px;color:#5C6878;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #E5E9F0"'
    name = (user.get("name") or "").split(" ")[0]
    page = f"""<div style="background:#F4F6F9;padding:24px 12px;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#16202E">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #DCE2EA;border-radius:12px;padding:22px">
<div style="font-weight:700;font-size:16px;margin-bottom:14px">Market Digest</div>
<div style="font-size:20px;font-weight:700;margin-bottom:4px">{e('Your week in stocks' if kind == 'weekly' else 'Your stocks today')}{', ' + e(name) if name else ''}</div>
<div style="color:#5C6878;font-size:13px;margin-bottom:14px">{today:%A %d %B %Y} · {counts['yes']} Yes · {counts['wait']} Wait · {counts['no']} No</div>
{chips}
<table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-top:8px">
<tr><th {th} align="left">Stock</th><th {th}>Invest?</th><th {th} align="right">Confidence</th><th {th} align="right">Price</th><th {th} align="right">{'Week' if kind == 'weekly' else 'Today'}</th></tr>
{body}</table>
<div style="margin:18px 0 6px"><a href="{e(site)}" style="display:inline-block;background:#2447C5;color:#fff;text-decoration:none;font-weight:600;padding:10px 18px;border-radius:8px">Open my dashboard</a></div>
<div style="color:#5C6878;font-size:12px;margin-top:16px;line-height:1.5">The signals sum up what analysts said; they are not personal financial advice and can be wrong.<br>
You get this because you signed up to Market Digest. <a href="{e(site)}#/account" style="color:#2447C5">Change or stop these emails</a>.</div>
</div></div>"""
    text = "\n".join([lead, ""] + [n["text"] for n in notes[:6]] + [""] +
                     [f"{r['ticker']:<7} {SIGNAL[r['signal']][0]:<5} {str(r.get('confidence_pct') or '—'):>3}%  {money(r.get('price'), r.get('currency'))}" for r in rows[:30]] +
                     ["", f"Open your dashboard: {site}", f"Change or stop these emails: {site}#/account",
                      "The signals sum up what analysts said; they are not personal financial advice."])
    return subject, page, text


def send(settings, to, subject, html_body, text_body):
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = formataddr((settings.get("mail_from_name") or "Market Digest", settings["smtp_user"]))
    msg["List-Unsubscribe"] = f"<{settings['site']}#/account>"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL(settings.get("smtp_host") or "smtp.gmail.com", int(settings.get("smtp_port") or 465),
                          context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(settings["smtp_user"], settings["smtp_password"])
        smtp.send_message(msg)


def send_all(store, settings, users, cards, kind, today, log=print, sender=send):
    """Send this kind of email to every user who wants it and has not had it today. Returns how many went out."""
    if not settings.get("smtp_user") or not settings.get("smtp_password"):
        log("Email: not set up (SMTP_USER and SMTP_PASSWORD), so none sent")
        return 0
    sent = failed = 0
    for uid, user in users.items():
        view = user_view(user, cards)
        if not wants(user, kind, view, today):
            continue
        record = store.get("mail", uid) or {}
        if record.get(kind) == today.isoformat():
            continue
        try:
            sender(settings, user["email"], *compose(user, view, kind, today, settings["site"]))
            store.set("mail", uid, {kind: today.isoformat()}, merge=True)
            sent += 1
        except Exception as err:
            failed += 1
            if failed <= 3:
                log(f"Email: one not sent ({type(err).__name__}: {str(err)[:120]})")
            if isinstance(err, smtplib.SMTPAuthenticationError):
                break   # a wrong password fails for everyone
    log(f"Email ({kind}): {sent} sent" + (f", {failed} failed" if failed else ""))
    return sent


def settings_from_env():
    env = os.environ.get
    return {"smtp_user": env("SMTP_USER", ""), "smtp_password": env("SMTP_PASSWORD", ""), "smtp_host": env("SMTP_HOST", ""),
            "smtp_port": env("SMTP_PORT", ""), "mail_from_name": env("MAIL_FROM_NAME", ""), "site": env("SITE_URL", "").rstrip("/") + "/"}
