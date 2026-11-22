"""One run of the engine. Safe to run every hour: each step does only what is new, and a run with nothing new writes
nothing. Order: new videos, prices, Wall Street's ratings, the cards and market pages, then the emails when due."""
import json
import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import CLOUD, ROOT, access, cards as cards_mod, mail, street as street_mod, videos
from .store import doc_id
import digest as dg
import prices

KEEP_DAYS = 125
MAX_UNIVERSE = 900


def load_sources():
    return json.loads((CLOUD / "sources.json").read_text(encoding="utf-8"))


def settings_from_env():
    env = os.environ.get
    models = [m.strip() for m in env("GEMINI_MODELS", "").split(",") if m.strip()]
    return {"gemini_api_key": env("GEMINI_API_KEY", "").strip(), "models": models or list(dg.DEFAULT_MODELS),
            "tipranks_api_key": env("TIPRANKS_API_KEY", "").strip(), "members": env("BETA_MEMBERS"), **mail.settings_from_env()}


class Work:
    """The engine's scratch folder, kept between runs by the workflow's cache so that most runs read nothing from
    Firestore. Everything in it can be rebuilt from Firestore, which is what happens when the cache is gone."""

    def __init__(self, folder):
        self.dir = Path(folder)
        (self.dir / "notes").mkdir(parents=True, exist_ok=True)
        self.warm = (self.dir / "warm").exists()

    def json(self, name, default):
        try:
            return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def put(self, name, data):
        tmp = self.dir / (name + ".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / name)

    def notes(self, store, now, log):
        cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
        if not self.warm:   # a new runner with no cache: fetch the notes once
            got = store.since("videos", "published", cutoff)
            for vid, doc in got.items():
                (self.dir / "notes" / f"{vid}.json").write_text(doc.get("notes") or "{}", encoding="utf-8")
            log(f"Notes: {len(got)} loaded from Firestore (no local cache)")
        out = []
        for f in (self.dir / "notes").glob("*.json"):
            try:
                n = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if str((n.get("_video") or {}).get("published") or "") < cutoff:
                f.unlink()
                continue
            out.append(n)
        return out

    def add_note(self, notes):
        (self.dir / "notes" / f"{notes['_video']['id']}.json").write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")


def user_tickers(users):
    out = []
    for u in users.values():
        for s in (u.get("stocks") or [])[:80]:
            t = prices.clean(s.get("t") if isinstance(s, dict) else "")
            if t:
                out.append(t)
    return sorted(set(out))


def themes_of(cfg, made_today, log):
    """A few short themes of the day's videos (one Gemini request). Empty when there is too little to sum up."""
    if len(made_today) < 4 or not cfg.get("gemini_api_key"):
        return None
    try:
        s = dg.day_summary(cfg, [{"video": n["_video"], "notes": n} for n in made_today[:25]])
        return [{"theme": str(t.get("theme") or "")[:80], "detail": str(t.get("detail") or "")[:400]} for t in s.get("themes") or [] if t.get("theme")][:5]
    except Exception as err:
        log(f"Themes: skipped ({type(err).__name__}: {str(err)[:120]})")
        return None


def run(store, settings, sources=None, now=None, log=print, work=None, read_videos=True, force_mail=None, reader=videos.read,
        price_fetcher=None, tipranks_client=None, mail_sender=mail.send):
    now = now or datetime.now(timezone.utc)
    today = now.date()
    sources = sources or load_sources()
    work = Work(work or os.environ.get("ENGINE_WORK") or ROOT / ".engine-cache")
    prices.CACHE = work.dir / "prices.json"
    prices.MAX_SYMBOLS = MAX_UNIVERSE + 10
    dg.log = log
    state = store.get("engine", "state") or {}
    errors = []

    def step(name, fn, default=None):
        try:
            return fn()
        except Exception as err:   # one step failing must not lose the rest of the run
            errors.append(f"{name}: {type(err).__name__}: {str(err)[:200]}")
            log(f"{name} failed: {traceback.format_exc(limit=3)}")
            return default

    # 1. videos: read the new ones once, for everybody
    notes = work.notes(store, now, log)
    cfg = {"gemini_api_key": settings.get("gemini_api_key"), "models": settings.get("models") or list(dg.DEFAULT_MODELS)}
    made = []
    if read_videos and cfg["gemini_api_key"]:
        made = step("Videos", lambda: videos.read_new(cfg, sources, state, store, now, log, reader=reader,
                                                      pause=0 if reader is not videos.read else 13), []) or []
        for n in made:
            work.add_note(n)
        notes += made
    elif read_videos:
        log("Videos: GEMINI_API_KEY is not set, so no new videos are read")
    pairs = videos.as_pairs(notes)

    # 2. who may use it (the private beta's members), then who wants what: all users once a day (and when emailing)
    members = step("Members", lambda: access.sync(store, settings.get("members"), today, log), None)
    mail_hour = sources.get("email", {}).get("hour_utc", 2)
    mail_due = force_mail or (state.get("mail_day") != today.isoformat() and 0 <= now.hour - mail_hour < 6 and "daily")
    users = None
    if state.get("users_day") != today.isoformat() or mail_due:
        users = step("Users", lambda: store.all("users"), None)
        if users is not None and members is not None:
            users = access.only_members(users, members)   # an account not on the list gets no emails and no coverage
        if users is not None:
            state.update(users_day=today.isoformat(), user_tickers=user_tickers(users), users=len(users))
            for uid in step("Mail records", lambda: store.all("mail"), {}) or {}:
                if uid not in users:   # an account that was deleted: nothing of it is kept
                    store.delete("mail", uid)
    requests = step("Requests", lambda: store.all("requests"), {}) or {}
    asked = [t for t in (prices.clean(k.replace("_", "^")) for k in requests) if t]
    called = [t for t, _ in Counter(c["ticker"] for c in cards_mod.insights.calls_in(
        [(v, n) for v, n in pairs if cards_mod.local_day(v) >= today - timedelta(days=90)])).most_common(400)]
    packs = [t for p in sources.get("packs") or [] for t in p["tickers"]]
    mine = list(dict.fromkeys([*(state.get("user_tickers") or []), *asked]))
    universe = list(dict.fromkeys(t for t in (prices.clean(x) for x in [*mine, *sources["base_tickers"], *packs, *called]) if t))[:MAX_UNIVERSE]

    # 3. prices: once a day a symbol
    step("Prices", lambda: prices.refresh(universe, log, fetcher=price_fetcher, pause=0.15 if price_fetcher is None else 0,
                                                  now=now, limit=len(universe) + 1))
    cache = prices.load()

    # 4. Wall Street's ratings, a few batches a weekday
    prev = work.json("cards.json", None)
    if prev is None:
        prev = {c.get("ticker"): c for c in (step("Cards", lambda: store.all("stocks"), {}) or {}).values() if c.get("ticker")}
    street = {t: street_mod.upgrade({**c["street"], "ticker": t, "name": c.get("name")}) for t, c in prev.items() if c.get("street")}
    street = step("TipRanks", lambda: street_mod.refresh(settings.get("tipranks_api_key"), state, street, universe, mine, today,
                                                         sources["limits"], log, client=tipranks_client), street) or street

    # 5. the cards and the market pages; only what changed is written
    made_today = [n for n in notes if str((n.get("_video") or {}).get("published") or "")[:10] >= (today - timedelta(days=1)).isoformat()]
    if made and (state.get("themes") or {}).get("day") != today.isoformat():
        got = themes_of(cfg, made_today, log)
        if got:
            state["themes"] = {"day": today.isoformat(), "items": got}
    themes = (state.get("themes") or {}).get("items") or []
    built = step("Build", lambda: cards_mod.build(pairs, cache, street, prev, universe, today, sources, themes))
    written = 0
    if built:
        new_cards, charts, docs = built
        chart_last = work.json("chart_last.json", {})
        for t, card in new_cards.items():
            if (prev.get(t) or {}).get("h") != card["h"]:
                store.set("stocks", doc_id(t), card)
                written += 1
            ch = charts.get(t)
            if ch and chart_last.get(t) != ch["d"][-1]:
                store.set("charts", doc_id(t), ch)
                chart_last[t] = ch["d"][-1]
                written += 1
        hashes = work.json("market_h.json", {})
        for name, doc in docs.items():
            h = cards_mod.fingerprint(doc)
            if hashes.get(name) != h:
                store.set("market", name, doc)
                hashes[name] = h
                written += 1
        # the example on the front page, for people who have not signed in yet: the first pack, as it really stands today
        sample = [t for t in ((sources.get("packs") or [{}])[0].get("tickers") or []) if t in new_cards and not new_cards[t].get("unknown")]
        demo = {"cards": [new_cards[t] for t in sample], "charts": {doc_id(t): charts[t] for t in sample if t in charts}, "date": today.isoformat(),
                "overview": cards_mod.public_overview(docs, new_cards)}
        if hashes.get("public/demo") != cards_mod.fingerprint(demo):
            store.set("public", "demo", demo)
            hashes["public/demo"] = cards_mod.fingerprint(demo)
            written += 1
        for key in requests:
            store.delete("requests", key)
        work.put("cards.json", new_cards)
        work.put("chart_last.json", chart_last)
        work.put("market_h.json", hashes)
        log(f"Cards: {len(new_cards)} stocks, {written} documents written")

        # 6. the emails, once a day
        if mail_due and users is not None:
            # an email sent in the small hours (UTC) is about the market day before
            session = today - timedelta(days=1) if mail_hour < 12 else today
            weekly_day = today.weekday() == sources.get("email", {}).get("weekly_weekday", 5)
            kinds = [force_mail] if force_mail else (["weekly"] if weekly_day else []) + ["daily"]
            for kind in kinds:
                step("Email", lambda k=kind: mail.send_all(store, settings, users, new_cards, k, today, log, sender=mail_sender, session=session))
            state["mail_day"] = today.isoformat()

    state["last_run"] = now.isoformat(timespec="seconds")
    step("State", lambda: store.set("engine", "state", state))
    used = state.get("videos_read") or {}
    status = {"last_run": state["last_run"], "ok": not errors, "errors": errors[:5], "videos_today": used.get("count", 0),
              "videos_kept": len(pairs), "stocks": len(universe), "users": state.get("users", 0),
              "tipranks": {k: (state.get("tipranks") or {}).get(k) for k in ("limit", "remaining", "today")},
              "prices_as_of": max((e.get("closes") or [[""]])[-1][0] for e in cache.values()) if cache else None}
    step("Status", lambda: store.set("market", "status", status))
    (work.dir / "warm").write_text(state["last_run"], encoding="utf-8")
    log(f"Run finished{' with errors: ' + '; '.join(errors) if errors else ''}")
    return status
