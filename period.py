"""The weekly and monthly digests: what a week's (or a month's) videos added up to.

The numbers come from insights.py (code, not AI): the stocks discussed most and which way the calls lean, how the
calls did against the S&P 500, the analysts' records, what is coming up. Gemini writes only the opening paragraph and
"what to watch next", from those numbers. If Gemini cannot be reached, the digest goes out without that paragraph.

    python period.py --week            make last week's digest now (and email it, if email is set up)
    python period.py --month --dry-run last month's, not emailed, opened in the browser
    python period.py --due             whichever is due (the daily run calls this after the daily digest)
A week runs Saturday to Friday and is made on the Saturday (or the first run after it); a month on the 1st.
Standard library only.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta

import digest as dg
import insights
from digest import C, bullets, change, e, section, table

MIN_VIDEOS = 2
PERIOD_SYSTEM = """You write the opening of a {kind} digest of finance videos for a busy professional.
You receive numbers computed from the period's videos: the stocks discussed most with bullish and bearish call counts,
how the calls did against the S&P 500, the analysts' records, the main themes and what is coming up. Use only these.
Report views as the analysts' views. Do not tell the reader what to buy or sell.
Return one JSON object:
{{"headline": "one sentence: the period's main story",
  "overview": "4 to 6 sentences: the mood, the stocks that dominated and which way the calls leaned, where analysts disagreed, and how earlier calls have done",
  "watch_next": ["3 short items to watch next {unit}, taken from what is coming up and the open disagreements"]}}"""


def bounds(kind, today):
    """(start, end, key) of the latest complete period: end is exclusive."""
    if kind == "week":
        end = today - timedelta(days=(today.weekday() - 5) % 7)   # the latest Saturday, today included
        return end - timedelta(days=7), end, end.isoformat()
    end = today.replace(day=1)
    start = (end - timedelta(days=1)).replace(day=1)
    return start, end, f"{start:%Y-%m}"


def label(kind, start, end):
    last = end - timedelta(days=1)
    if kind == "week":
        return f"{start:%d %b} to {last:%d %b %Y}".lstrip("0")
    return f"{start:%B %Y}"


def themes(videos, n=6):
    counts, shown = Counter(), {}
    for _, notes in videos:
        for t in notes.get("sectors_and_themes") or []:
            name = str(t.get("name") or "").strip()
            if name:
                counts[name.lower()] += 1
                shown.setdefault(name.lower(), name[0].upper() + name[1:])   # as first written: "AI infrastructure", not "Ai"
    return [shown[t] for t, _ in counts.most_common(n)]


def opening(cfg, kind, ov, theme_list):
    """Gemini's headline, overview and watch-next list, or {} when it cannot be had."""
    facts = {
        "period": f"{ov['start']} to {ov['end']}", "videos": ov["videos"], "calls": ov["calls"], "mood_pct_bullish": ov["mood_pct"],
        "scorecard_vs_sp500": ov["scorecard"], "themes": theme_list,
        "stocks": [{k: r[k] for k in ("ticker", "name", "calls", "bullish", "bearish", "lean", "move_since_pct", "analysts")} | {"latest_reason": r["latest"]["reason"]}
                   for r in ov["stocks"][:12]],
        "analysts": [{k: a[k] for k in ("analyst", "calls", "bullish", "bearish", "scored", "right", "edge")} for a in ov["analysts"][:10]],
        "coming_up": [{"event": u["event"], "date": u["date"] or u["when"]} for u in ov["upcoming"][:8]],
    }
    try:
        out = dg.gemini(cfg, PERIOD_SYSTEM.format(kind="weekly" if kind == "week" else "monthly", unit=kind),
                        json.dumps(facts, ensure_ascii=False))
        return out if isinstance(out, dict) else {}
    except Exception as err:
        dg.log(f"The {kind}'s opening paragraph was not written ({err}); the digest goes out without it.")
        return {}


def render(kind, ov, words, theme_list, start, end):
    title = "Your week in market videos" if kind == "week" else "Your month in market videos"
    parts = [f'<p style="margin:0;color:{C["muted"]};font-size:13px">{e(label(kind, start, end))}. {ov["videos"]} videos from {ov["channels"]} '
             f'channel{"s" if ov["channels"] != 1 else ""}, {ov["calls"]} stock calls.</p>',
             f'<h1 style="font:600 26px/1.25 Georgia,serif;color:{C["ink"]};margin:6px 0 10px">{title}</h1>']
    if words.get("headline"):
        parts.append(f'<p style="font-size:18px;line-height:1.45;margin:0 0 10px"><b>{e(words["headline"])}</b></p>')
    if words.get("overview"):
        parts.append(f'<p style="font-size:16px;line-height:1.6">{e(words["overview"])}</p>')
    card = ov["scorecard"]
    marks = []
    if ov["mood_pct"] is not None:
        marks.append(f'Mood: <b>{ov["mood_pct"]}% bullish</b> ({ov["views"]["bullish"]} bullish, {ov["views"]["bearish"]} bearish calls)')
    for view, verb in (("bullish", "beat"), ("bearish", "lagged")):
        s = card[view]
        if s["scored"]:
            marks.append(f'{view.capitalize()} calls that {verb} the S&amp;P 500: <b>{s["right"]} of {s["scored"]}</b> ({s["hit_pct"]}%)')
    if marks:
        parts.append(f'<p style="padding:10px 12px;background:{C["soft"]};border-radius:6px;font-size:14px;margin:12px 0">{"<br>".join(marks)}</p>')
    if ov["signals"]:
        parts.append(section("What matters", bullets([e(s["text"]) + (f' <a href="{e(s["link"])}" style="color:{C["blue"]}">watch</a>' if s["link"] else "")
                                                      for s in ov["signals"]])))
    if ov["stocks"]:
        rows = []
        for r in ov["stocks"][:12]:
            lt = r["latest"]
            rows.append([f'<b>{e(r["ticker"])}</b>' + (f'<br><span style="font-size:12px;color:{C["muted"]}">{e(r["name"])}</span>' if r["name"] else ""),
                         f'{r["calls"]} <span style="font-size:12px;color:{C["muted"]}">({r["bullish"]}&#8593; {r["bearish"]}&#8595;)</span>',
                         f'<span style="color:{C.get(r["lean"], C["muted"])}">{e(r["lean"])}</span>', change(r["move_since_pct"]),
                         f'<a href="{e(lt["link"])}" style="color:{C["blue"]}">{e(lt["analyst"] or lt["channel"])}</a>: {e(lt["view"])}. '
                         f'<span style="font-size:13px">{e(lt["reason"][:140])}</span>'])
        parts.append(section("Stocks the analysts talked about most", table(["Stock", "Calls", "Lean", "Since first call", "Latest call"], rows)))
    named = [a for a in ov["analysts"] if a["calls"] >= 2][:8]
    if named:
        parts.append(section("The analysts", table(["Analyst", "Calls", "Right vs S&amp;P 500", "Average edge"], [
            [e(a["analyst"]) + (" &#9733;" if a["followed"] else ""), a["calls"],
             f'{a["right"]} of {a["scored"]}' if a["scored"] else "not yet", "-" if a["edge"] is None else f'{a["edge"]:+.1f} pts'] for a in named])))
    xs = ov["extremes"]
    if xs["best"] or xs["worst"]:
        items = [f'<b>{kind_}</b>: {e(x["ticker"])} {e(x["view"])} by <a href="{e(x["link"])}" style="color:{C["blue"]}">{e(x["analyst"] or x["channel"])}</a> '
                 f'({e(x["day"])}): stock {x["stock_pct"]:+.1f}%, S&amp;P 500 {x["sp500_pct"]:+.1f}%' for kind_, group in (("Best", xs["best"]), ("Worst", xs["worst"])) for x in group]
        parts.append(section("Best and worst calls so far", bullets(items)))
    if theme_list:
        parts.append(section("Themes", f'<p>{e(", ".join(theme_list))}.</p>'))
    if words.get("watch_next") or ov["upcoming"]:
        items = [e(str(w)) for w in (words.get("watch_next") or [])[:4]]
        items += [f'{e(u["date"] or u["when"] or "")} {e(u["event"])} <span style="color:{C["muted"]}">({e(u["channel"])})</span>' for u in ov["upcoming"][:6]]
        parts.append(section("Coming up", bullets(items)))
    parts.append(f'<p style="margin:28px 0 0;font-size:12px;color:{C["muted"]};line-height:1.5">Numbers computed by Market Digest from the videos\' notes and '
                 f'daily closing prices; the opening paragraph is written by Gemini from those numbers. A call is right when the stock then did better (bullish) '
                 f'or worse (bearish) than the S&amp;P 500. This reports what analysts said and what prices did. It is not investment advice.</p>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>'
            f'<body style="margin:0;background:{C["soft"]}"><div style="max-width:720px;margin:0 auto;padding:24px 20px;background:#fff;'
            f'font:15px/1.55 -apple-system,\'Segoe UI\',Roboto,Arial,sans-serif;color:{C["ink"]}">{"".join(parts)}</div></body></html>')


def plain(kind, ov, words, start, end):
    lines = [f"{'Week' if kind == 'week' else 'Month'}: {label(kind, start, end)}", words.get("headline", ""), words.get("overview", ""), ""]
    lines += [f"{r['ticker']}: {r['calls']} calls ({r['bullish']} bullish, {r['bearish']} bearish), leans {r['lean']}" for r in ov["stocks"][:10]]
    return "\n".join(lines)


def make(cfg, state, kind, today=None, test=False, open_it=False):
    """Make one period's digest. Returns the saved file, or None when there were too few videos."""
    today = today or date.today()
    start, end, key = bounds(kind, today)
    ov = insights.overview(cfg=cfg, start=start, end=end)
    if not test:
        state[f"last_{kind}"] = key   # done for this period, even with too few videos: it is not tried again every day
    if ov["videos"] < MIN_VIDEOS:
        dg.log(f"The {kind}ly digest for {label(kind, start, end)}: only {ov['videos']} video(s), so none was made.")
        return None
    theme_list = themes(insights.window(start, end))
    words = opening(cfg, kind, ov, theme_list)
    page = render(kind, ov, words, theme_list, start, end)
    dg.OUT_DIR.mkdir(exist_ok=True)
    out = dg.OUT_DIR / (f"weekly-{end - timedelta(days=1):%Y-%m-%d}.html" if kind == "week" else f"monthly-{start:%Y-%m}.html")
    out.write_text(page, encoding="utf-8")
    dg.log(f"Saved {out}")
    subject = f"{'Your week' if kind == 'week' else 'Your month'} in market videos, {label(kind, start, end)}"
    emailed = False
    if not test:
        try:
            emailed = dg.send(cfg, subject, page, plain(kind, ov, words, start, end))
        except Exception as err:
            dg.log(f"The {kind}ly digest was saved but not emailed: {err}")
        if emailed:
            dg.log("Emailed the " + kind + "ly digest")
    if open_it:
        dg.show(out)
    elif not test:
        dg.announce(cfg, ov["videos"], out, what=f"Your {kind}ly market digest is ready")
    return out


def due(cfg, state, today=None):
    """The periods whose digest is due now, by the settings ("weekly", "monthly": on unless turned off)."""
    today = today or date.today()
    out = []
    for kind in ("week", "month"):
        if cfg.get("weekly" if kind == "week" else "monthly", True) and state.get(f"last_{kind}") != bounds(kind, today)[2]:
            out.append(kind)
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="The weekly and monthly market video digests.")
    ap.add_argument("--week", action="store_true", help="make the latest complete week's digest now")
    ap.add_argument("--month", action="store_true", help="make the latest complete month's digest now")
    ap.add_argument("--due", action="store_true", help="make whichever is due (the daily run calls this)")
    ap.add_argument("--dry-run", action="store_true", help="do not email, do not mark as done, open it in the browser")
    args = ap.parse_args()
    cfg, state = dg.load_config(), dg.load_state()
    kinds = (["week"] if args.week else []) + (["month"] if args.month else []) + (due(cfg, state) if args.due else [])
    if not kinds:
        print("Nothing to do: weekly and monthly digests are up to date." if args.due else "Say --week, --month or --due.")
        return
    first_ever = args.due and not state.get("last_week") and not state.get("last_month")
    for kind in kinds:
        if first_ever:   # just installed: start counting from now, rather than sending summaries of days before it
            state[f"last_{kind}"] = bounds(kind, date.today())[2]
            continue
        dg.log(f"--- {datetime.now():%A %d %B %Y}: {kind}ly digest" + (" (test, not emailed)" if args.dry_run else ""))
        make(cfg, state, kind, test=args.dry_run, open_it=args.dry_run)
    if not args.dry_run:
        dg.save_state(state)


if __name__ == "__main__":
    main()
