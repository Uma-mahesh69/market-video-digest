"""Is everything set up? Run by the "Check setup" workflow after the secrets are added, and safe to run again.
It tries each thing the engine needs for real, and says in plain words what works and what to fix.

    python -m cloud.tools.check
"""
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from cloud.engine import run as engine, videos  # noqa: E402
import digest as dg  # noqa: E402
import tipranks  # noqa: E402

results = []


def check(name, needed, fn):
    try:
        note = fn()
        results.append((name, "OK", note))
    except Exception as err:
        results.append((name, "FAILED" if needed else "NOT SET UP", f"{type(err).__name__}: {str(err)[:300]}"))
    print(f"{results[-1][1]:<10} {name}: {results[-1][2]}", flush=True)


def firebase():
    if not os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip() and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("the secret FIREBASE_SERVICE_ACCOUNT is empty")
    from cloud.engine.store import FirestoreStore
    store = FirestoreStore()
    stamp = datetime.now(timezone.utc).isoformat()
    store.set("engine", "check", {"at": stamp})
    if (store.get("engine", "check") or {}).get("at") != stamp:
        raise RuntimeError("wrote a test document but could not read it back")
    store.delete("engine", "check")
    return f"connected to project {store.db.project}; can write and read"


def youtube(found):
    sources = engine.load_sources()
    state = {}
    for ch in sources["channels"][:3]:
        ups = [u for u in videos.feed(dg.channel_id(ch["url"], {"channel_ids": state})) if not u["short"]]
        if ups:
            found.append(ups[min(3, len(ups) - 1)])
            return f"{ch['name']}: {len(ups)} recent videos listed"
    raise RuntimeError("no channel returned any video")


def gemini(found):
    settings = engine.settings_from_env()
    if not settings["gemini_api_key"]:
        raise RuntimeError("the secret GEMINI_API_KEY is empty")
    cfg = {"gemini_api_key": settings["gemini_api_key"], "models": settings["models"]}
    if not found:
        raise RuntimeError("no video to try (the YouTube check failed)")
    notes = videos.read(cfg, found[0], engine.load_sources()["limits"])
    return (f"watched \"{found[0]['title'][:50]}\": {len(notes.get('stocks') or [])} stock calls, "
            f"{len(notes.get('key_points') or [])} key points, speakers: {', '.join(s['name'] for s in dg.note_speakers(notes)[:3]) or 'none named'}")


def street():
    key = os.environ.get("TIPRANKS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("the secret TIPRANKS_API_KEY is empty (Wall Street's ratings will be missing)")
    tr = tipranks.Client(key)
    tr.start()
    usage = tipranks.usage_now(tr, tr.tools()) or {}
    return f"key accepted; {usage.get('remaining', '?')} of {usage.get('limit', '?')} calls left this month"


def email():
    s = engine.settings_from_env()
    if not s["smtp_user"] or not s["smtp_password"]:
        raise RuntimeError("SMTP_USER or SMTP_PASSWORD is empty (no emails will be sent)")
    with smtplib.SMTP_SSL(s.get("smtp_host") or "smtp.gmail.com", int(s.get("smtp_port") or 465), context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(s["smtp_user"], s["smtp_password"])
    return f"login accepted; emails will come from this address and link to {s['site']}"


def members():
    from cloud.engine import access
    found = access.parse(os.environ.get("BETA_MEMBERS"))
    if found is None:
        raise RuntimeError("the secret BETA_MEMBERS is empty: nobody new can get into the private beta")
    if not found:
        raise RuntimeError("BETA_MEMBERS has no valid email address in it")
    return f"{len(found)} address(es) on the private beta's members list"   # the addresses themselves are not printed


def main():
    found = []
    check("Firebase (the database)", True, firebase)
    check("Members (who may use the site)", True, members)
    check("YouTube (listing new videos)", True, lambda: youtube(found))
    check("Gemini (watching a video)", True, lambda: gemini(found))
    check("TipRanks (Wall Street's ratings)", False, street)
    check("Email (sending the digests)", False, email)
    failed = [r for r in results if r[1] == "FAILED"]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("| Check | Result | Details |\n|---|---|---|\n" + "".join(f"| {n} | {s} | {d.replace('|', '/')} |\n" for n, s, d in results))
    print("\n" + ("Everything needed is working." if not failed else f"{len(failed)} thing(s) to fix: " + ", ".join(r[0] for r in failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
