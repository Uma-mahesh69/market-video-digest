"""Market Digest: the app on this computer for the settings, the daily run's status and the chat.

Start it with Market Digest on the desktop, or: python app.py.
It opens http://127.0.0.1:8765 in your browser and only listens on this computer.
    python app.py --setup            the installer's settings page; Finish closes it
    python app.py --schedule         set the daily run again from the saved settings (used by updates)
    python app.py --daily            the scheduled run: digest.py, tried again 3 times if it fails, logged to digest.log
    python app.py --stop             ask a running Market Digest to quit (the installer does this before an update)
    python app.py --notify T TEXT    show a desktop notice
Keys and passwords never go back to the page: it only learns whether one is saved, and its last 4 characters.
Standard library only.
"""
import argparse
import io
import json
import os
import plistlib
import re
import smtplib
import socket
import ssl
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import chat
import digest as dg
import tipranks
from market_data import read_watchlist

PORT = 8765
LABEL = "com.nugenix.market-digest"   # the launchd job on a Mac
TASK = "Market video digest"          # the Task Scheduler task on Windows
SECRETS = ("gemini_api_key", "smtp_password", "tipranks_api_key")
DEFAULTS = {"channels": ["https://www.youtube.com/@TheStreet"], "email_to": [], "smtp_user": "", "json_dir": "", "watchlist_csv": "",
            "daily_time": "07:30", "schedule_on": True, "lookback_hours": 26, "max_videos": 20, "analysts": [], "markets_only": True,
            "notify": True}
REPO = "Uma-mahesh69/market-video-digest"


def program_files(manifest):
    """The program's own files, from the text of MANIFEST (one name a line): what the installers copy and an update
    replaces. Settings, saved videos, digests and chats are never in it. Only plain file names are accepted."""
    names = [line.strip() for line in manifest.splitlines() if line.strip() and not line.startswith("#")]
    bad = [n for n in names if not re.fullmatch(r"[\w.\-]+", n) or n.startswith(".")]
    if bad or "app.py" not in names or "VERSION" not in names:
        raise ValueError(f"MANIFEST is not a list of program files ({(bad or ['app.py or VERSION is missing'])[0]})")
    return tuple(dict.fromkeys(names))
# Offered on the settings page so nobody has to hunt for a channel address or spell a name.
POPULAR_CHANNELS = [("CNBC Television", "https://www.youtube.com/@CNBCtelevision"), ("Bloomberg Television", "https://www.youtube.com/@markets"),
                    ("Yahoo Finance", "https://www.youtube.com/@YahooFinance"), ("TheStreet", "https://www.youtube.com/@TheStreet"),
                    ("Fox Business", "https://www.youtube.com/@FoxBusiness"), ("Schwab Network", "https://www.youtube.com/@SchwabNetwork")]
POPULAR_ANALYSTS = ["Dan Ives", "Tom Lee / Thomas Lee", "Mike Wilson", "Ed Yardeni", "Liz Ann Sonders", "Jeremy Siegel",
                    "Mohamed El-Erian", "Cathie Wood", "Gene Munster", "Sam Stovall", "Savita Subramanian", "Jim Cramer"]
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
CHANNEL = re.compile(r"^(https?://)?(www\.|m\.)?youtube\.com/(@[\w.\-]+|channel/UC[\w-]{22}|c/[\w.\-]+|user/[\w.\-]+)/?(videos|featured|streams)?/?$|^@[\w.\-]+$", re.I)
DIGEST_FILE = re.compile(r"^digest-[\d-]+\.html$")


# ---------------------------------------------------------------- settings

def read_config():
    """The saved settings as they are in digest_config.json ({} when there are none yet)."""
    try:
        return json.loads(dg.CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {"_broken": True}


def real(value):
    """A saved secret, or "" for none (the example file's PASTE placeholders count as none)."""
    v = str(value or "").strip()
    return "" if not v or "PASTE" in v else v


def public(cfg):
    """The settings for the page. Secrets become {"saved", "hint"}: the page never sees a key or password."""
    out = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    out["daily_time"] = daily_time(cfg)
    out["open_when_ready"] = open_when_ready(cfg)
    if isinstance(out["email_to"], str):
        out["email_to"] = [out["email_to"]]
    for k in SECRETS:
        v = real(cfg.get(k))
        # a key shows its last 4 characters, so you can tell which one is saved; the password shows nothing
        out[k] = {"saved": bool(v), "hint": ("ends in " + v[-4:]) if len(v) >= 12 and k != "smtp_password" else ("saved" if v else "")}
    out["first_time"] = not real(cfg.get("gemini_api_key"))
    out["broken"] = bool(cfg.get("_broken"))
    return out


def open_when_ready(cfg):
    """Open each new digest in the browser. Unless chosen, on when there is no email: the digest still reaches you."""
    return bool(cfg.get("open_when_ready", not cfg.get("email_to")))


def split_list(value):
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,;\s]+", str(value or ""))
    return [str(x).strip() for x in items if str(x).strip()]


def merged(form, saved):
    """Settings from the page on top of the saved ones, and {field: problem} for anything wrong.
    A secret left blank keeps the saved one; "<name>_clear": true removes it."""
    cfg = {k: v for k, v in saved.items() if not k.startswith("_")}
    errors = {}
    for k in SECRETS:
        v = form.get(k)
        if isinstance(v, str) and v.strip():
            cfg[k] = re.sub(r"\s", "", v) if k == "smtp_password" else v.strip()
        elif form.get(k + "_clear"):
            cfg[k] = ""

    key = real(cfg.get("gemini_api_key"))
    if not key:
        errors["gemini_api_key"] = "Paste your Gemini API key. It is free from Google AI Studio (the link above)."
    elif re.search(r"\s", key) or len(key) < 30:
        errors["gemini_api_key"] = f"That is not a whole Gemini key ({len(key)} characters; a key is about 39, with no spaces). Copy it again."

    if "channels" in form:
        cfg["channels"] = split_list(form["channels"]) if isinstance(form["channels"], list) else split_list(str(form["channels"]).replace(" ", ","))
    bad = [c for c in cfg.get("channels", []) if not CHANNEL.match(c)]
    if not cfg.get("channels"):
        errors["channels"] = "Add at least one YouTube channel."
    elif bad:
        errors["channels"] = (f"“{bad[0][:80]}” is not a YouTube channel link. Open the channel on YouTube and copy the address, "
                              "like https://www.youtube.com/@TheStreet, or type its handle, like @TheStreet.")

    if "email_to" in form:
        cfg["email_to"] = split_list(form["email_to"])
    if "smtp_user" in form:
        cfg["smtp_user"] = str(form["smtp_user"] or "").strip()
    to = cfg.get("email_to") or []
    to = [to] if isinstance(to, str) else to
    if [t for t in to if not EMAIL.match(t)]:
        errors["email_to"] = f"“{next(t for t in to if not EMAIL.match(t))}” is not an email address."
    if to:
        if not cfg.get("smtp_user"):
            cfg["smtp_user"] = to[0]
        if not EMAIL.match(cfg["smtp_user"]):
            errors["smtp_user"] = "Type the Gmail address that sends the digest."
        pw = real(cfg.get("smtp_password"))
        gmail = "gmail" in str(cfg.get("smtp_host") or "smtp.gmail.com")
        if not pw:
            errors["smtp_password"] = "Paste a Gmail app password, or leave the addresses empty to skip email."
        elif gmail and len(pw) != 16:
            errors["smtp_password"] = (f"A Gmail app password is 16 letters (Google shows it as 4 groups of 4); this one has {len(pw)}. "
                                       "Your normal Gmail password does not work here.")

    if "json_dir" in form:
        folder = str(form["json_dir"] or "").strip().strip("'\"").replace("\\ ", " ")
        cfg["json_dir"] = os.path.expanduser(folder) if folder else ""
    if "analysts" in form:
        items = form["analysts"] if isinstance(form["analysts"], list) else str(form["analysts"]).splitlines()
        cfg["analysts"] = list(dict.fromkeys(re.sub(r"\s+", " ", str(a)).strip() for a in items if str(a).strip()))
    if [a for a in cfg.get("analysts") or [] if len(a.split("/")[0].strip()) < 3 or len(a) > 120]:
        errors["analysts"] = "Write each analyst's full name, like Dan Ives (other spellings after a slash: Tom Lee / Thomas Lee)."
    for k in ("markets_only", "notify", "open_when_ready"):
        if k in form:
            cfg[k] = bool(form[k])
    if "watchlist_csv" in form:
        cfg["watchlist_csv"] = str(form["watchlist_csv"] or "").strip()
    if cfg.get("watchlist_csv") and not re.match(r"^https?://", cfg["watchlist_csv"]):
        errors["watchlist_csv"] = "Paste the whole link, starting https://docs.google.com/..."

    tr = real(cfg.get("tipranks_api_key"))
    if tr and tipranks.key_problem(tr):
        errors["tipranks_api_key"] = tipranks.key_problem(tr)[0].upper() + tipranks.key_problem(tr)[1:] + "."

    if "daily_time" in form:
        cfg["daily_time"] = str(form["daily_time"] or "").strip()[:5]
    if not TIME.match(cfg.get("daily_time") or daily_time(cfg)):
        errors["daily_time"] = "Choose a time, like 07:30."
    if "schedule_on" in form:
        cfg["schedule_on"] = bool(form["schedule_on"])
    for k, low, high in (("lookback_hours", 1, 168), ("max_videos", 1, 50)):
        if k in form:
            try:
                cfg[k] = int(form[k])
                if not low <= cfg[k] <= high:
                    raise ValueError
            except (TypeError, ValueError):
                errors[k] = f"Use a whole number from {low} to {high}."
    cfg.setdefault("daily_time", daily_time(cfg))
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    cfg.setdefault("models", list(dg.DEFAULT_MODELS))
    cfg.setdefault("smtp_host", "smtp.gmail.com")
    cfg.setdefault("smtp_port", 465)
    return cfg, errors


def write_config(cfg):
    tmp = dg.CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)   # only this user can read the key and password
    tmp.replace(dg.CONFIG)


def models(cfg):
    return list(dict.fromkeys(m for m in [*(cfg.get("models") or []), *dg.DEFAULT_MODELS] if m))


# ---------------------------------------------------------------- the daily schedule

def run_hidden(args, timeout=60, **kw):
    if os.name == "nt":
        kw.setdefault("creationflags", 0x08000000)   # CREATE_NO_WINDOW: no black window flashing up
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def platform():
    return "mac" if sys.platform == "darwin" else "windows" if os.name == "nt" else "other"


def console_python():
    """This Python with normal output streams: python.exe even when the app itself runs under pythonw.exe (no window)."""
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def windowless_python():
    """pythonw.exe on Windows, so nothing flashes on screen; the normal Python elsewhere."""
    w = Path(console_python()).with_name("pythonw.exe")
    return str(w) if os.name == "nt" and w.exists() else console_python()


def child_env():
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
            "PATH": str(dg.HERE / "bin") + os.pathsep + os.environ.get("PATH", "")}   # the yt-dlp the installer put in bin


def daily_run(attempts=4, wait=1800):
    """The scheduled run. digest.py's output is added to digest.log. A failed run (no internet yet, YouTube or email
    down) is tried again every 30 minutes, 3 times; then a desktop notice says so. Returns the exit code."""
    for attempt in range(1, attempts + 1):
        with open(dg.HERE / "digest.log", "a", encoding="utf-8") as log:
            code = subprocess.run([console_python(), "-u", str(dg.HERE / "digest.py")], cwd=dg.HERE, env=child_env(),
                                  stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=0x08000000 if os.name == "nt" else 0).returncode
            if code == 0:
                return 0
            if attempt < attempts:
                log.write(f"{datetime.now():%H:%M:%S} The run failed; trying again in {wait // 60} minutes.\n")
        if attempt < attempts:
            time.sleep(wait)
    notify("Market digest did not run", "Open Market Digest on the desktop to see why.")
    return 1


def plist_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def schedule(on, at):
    """Turn the daily run on at HH:MM, or off. Returns a sentence for the page. Raises RuntimeError."""
    hour, minute = (int(x) for x in at.split(":"))
    if sys.platform == "darwin":
        uid = os.getuid()
        run_hidden(["launchctl", "bootout", f"gui/{uid}/{LABEL}"])
        if not on:
            plist_path().unlink(missing_ok=True)
            return "The daily digest is off."
        plist_path().parent.mkdir(parents=True, exist_ok=True)
        with open(plist_path(), "wb") as f:
            plistlib.dump({"Label": LABEL, "ProgramArguments": [console_python(), str(dg.HERE / "app.py"), "--daily"], "WorkingDirectory": str(dg.HERE),
                           "StartCalendarInterval": {"Hour": hour, "Minute": minute}}, f)
        r = run_hidden(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path())])
        if r.returncode and run_hidden(["launchctl", "load", str(plist_path())]).returncode:
            raise RuntimeError(f"macOS did not accept the daily schedule: {(r.stderr or r.stdout).strip()[:200]}")
        return f"Scheduled every day at {at} (if the Mac is asleep then, it runs when it wakes)."
    if os.name == "nt":
        env = {**os.environ, "MD_TASK": TASK, "MD_EXE": windowless_python(), "MD_ARGS": f'"{dg.HERE / "app.py"}" --daily',
               "MD_DIR": str(dg.HERE), "MD_TIME": at}
        if on:
            # StartWhenAvailable: a time missed while the PC was off runs as soon as it is back on.
            # The run retries itself (3 waits of 30 minutes; Task Scheduler's own "restart on failure" ignores exit codes),
            # so the time limit leaves room for that. pythonw: no window appears.
            ps = ("$a = New-ScheduledTaskAction -Execute $env:MD_EXE -Argument $env:MD_ARGS -WorkingDirectory $env:MD_DIR; "
                  "$t = New-ScheduledTaskTrigger -Daily -At $env:MD_TIME; "
                  "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
                  "-ExecutionTimeLimit (New-TimeSpan -Hours 3); "
                  "Register-ScheduledTask -TaskName $env:MD_TASK -Action $a -Trigger $t -Settings $s "
                  "-Description 'Makes the daily market video digest. Set up by Market Digest.' -Force | Out-Null")
        else:
            ps = "Unregister-ScheduledTask -TaskName $env:MD_TASK -Confirm:$false -ErrorAction SilentlyContinue"
        r = run_hidden(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env)
        if r.returncode:
            raise RuntimeError(f"Windows did not accept the daily schedule: {(r.stderr or r.stdout).strip()[:200]}")
        return (f"Scheduled every day at {at} (while you are logged in; a missed time runs when the PC is next on)."
                if on else "The daily digest is off.")
    raise RuntimeError("Scheduling works on Windows and macOS only. On this computer, run python digest.py from cron.")


def is_scheduled():
    """True or False from the system's own scheduler; None when that cannot be asked here."""
    try:
        if sys.platform == "darwin":
            return plist_path().exists()
        if os.name == "nt":
            return run_hidden(["schtasks", "/query", "/tn", TASK]).returncode == 0
    except Exception:
        pass
    return None


def system_time():
    """The daily time of a schedule made by an older installer (it did not save the time in the settings), or None."""
    try:
        if sys.platform == "darwin" and plist_path().exists():
            with open(plist_path(), "rb") as f:
                when = plistlib.load(f).get("StartCalendarInterval") or {}
            return f"{int(when['Hour']):02d}:{int(when['Minute']):02d}"
        if os.name == "nt":
            r = run_hidden(["schtasks", "/query", "/tn", TASK, "/xml"])
            m = re.search(r"<StartBoundary>[\d-]+T(\d{2}:\d{2})", r.stdout or "")
            return m.group(1) if m else None
    except Exception:
        pass
    return None


def daily_time(cfg):
    at = cfg.get("daily_time") or system_time() or DEFAULTS["daily_time"]
    return at if TIME.match(at) else DEFAULTS["daily_time"]


def next_run(at, now=None):
    now = now or datetime.now()
    hour, minute = (int(x) for x in at.split(":"))
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return ("today" if when.date() == now.date() else "tomorrow") + f" at {at}"


# ---------------------------------------------------------------- tests for each setting, in plain words

def result(ok, message, **extra):
    return {"ok": ok, "message": message, **extra}


def explain_gemini(err):
    text, code = str(err), getattr(err, "code", None)
    if code == 400 and ("API_KEY_INVALID" in text or "API key not valid" in text):
        return "Google says this key is not valid. Copy it again from Google AI Studio (the link above) and paste the whole key."
    if code in (401, 403):
        return "This key may not use Gemini (error 403). In Google AI Studio, make a new key and paste it here."
    if code == 429:
        return "The key works, but it has used its free requests for now. They reset every day."
    if code == 404:
        return "None of the Gemini models in the settings is available to this key right now. Try again later."
    if code is None:
        return "Could not reach Google. Check the internet connection and try again."
    return f"Google's Gemini service had a problem (error {code}). Try again in a few minutes."


def test_gemini(cfg):
    body = {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}], "generationConfig": {"temperature": 0}}
    try:
        dg.call_gemini({**cfg, "models": models(cfg)}, body, patient=False)
        return result(True, "The key works.")
    except dg.GeminiError as err:
        return result(err.code == 429, explain_gemini(err), warn=err.code == 429)


def ago(published):
    try:
        hours = (datetime.now(timezone.utc) - datetime.fromisoformat(published.replace("Z", "+00:00"))).total_seconds() / 3600
    except (TypeError, ValueError):
        return ""
    return f"{hours:.0f} hours ago" if hours < 48 else f"{hours / 24:.0f} days ago"


def test_channel(ch, state):
    try:
        cid = dg.channel_id(ch, state)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return result(False, "YouTube has no channel at this address. Open it in your browser, and copy the address of the channel's page again.", channel=ch)
        return result(False, f"YouTube did not answer (error {err.code}). Try again in a few minutes.", channel=ch)
    except (urllib.error.URLError, OSError):
        return result(False, "Could not reach YouTube. Check the internet connection and try again.", channel=ch)
    except Exception:
        return result(False, "Could not find this channel. Open the link in your browser, check it is the channel's page, and copy the address again.", channel=ch)
    try:
        ups = dg.latest_uploads(cid)
    except Exception:
        return result(False, "Found the channel, but YouTube did not list its videos just now. Try again in a few minutes.", channel=ch)
    if not ups:
        return result(True, "Found the channel, but it has no videos yet.", channel=ch, warn=True)
    return result(True, f"Found it. Newest video: “{ups[0]['title'][:80]}”, {ago(ups[0]['published'])}.", channel=ch)


def test_channels(cfg):
    chans = cfg.get("channels") or []
    if not chans:
        return result(False, "Add at least one channel first.", channels=[])
    state = dg.load_state()
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(lambda c: test_channel(c, state), chans))
    bad = sum(not f["ok"] for f in found)
    return result(not bad, "All channels found." if not bad else f"{bad} of {len(found)} channels have a problem.", channels=found)


def explain_smtp(err):
    if isinstance(err, smtplib.SMTPAuthenticationError):
        return ("Gmail did not accept this address and app password. Make a new app password (the link above; 2-Step Verification "
                "must be on), paste it here, and check the sending address. Your normal Gmail password does not work here.")
    if isinstance(err, (socket.gaierror, TimeoutError, ConnectionError, OSError)):
        return "Could not reach Gmail. Check the internet connection and try again."
    return f"Gmail said: {err}"


def smtp(cfg, message=None):
    with smtplib.SMTP_SSL(cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 465)), context=ssl.create_default_context(), timeout=30) as s:
        s.login(cfg["smtp_user"], real(cfg.get("smtp_password")))
        if message:
            s.send_message(message)


def test_email(cfg, send=False):
    to = cfg.get("email_to") or []
    if not to:
        return result(True, "Email is off: digests are saved on this computer and shown on the home page.", warn=True)
    msg = None
    if send:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = "Market digest: test email", cfg["smtp_user"], ", ".join(to)
        msg.set_content(f"This test shows the daily market video digest can reach you.\n\n"
                        f"Sent by Market Digest on {socket.gethostname()} at {datetime.now():%H:%M on %d %b %Y}.")
    try:
        smtp(cfg, msg)
    except Exception as err:
        return result(False, explain_smtp(err))
    return result(True, f"Sent a test email to {', '.join(to)}. Check the inbox (and Spam)." if send else f"Gmail accepted the login for {cfg['smtp_user']}.")


def test_folder(cfg):
    folder = Path(cfg.get("json_dir") or dg.JSON_DIR)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        hint = " For a Google Drive folder, Google Drive for desktop must be running and signed in." if "drive" in str(folder).lower() else ""
        return result(False, f"Cannot save files in {folder} ({err.strerror or err}).{hint}")
    where = "the program folder (not shared)" if not cfg.get("json_dir") else str(folder)
    return result(True, f"Can save the daily files in {where}.")


def test_watchlist(cfg):
    if not cfg.get("watchlist_csv"):
        return result(True, "No watchlist: the digest works without one.", warn=True)
    try:
        prices = read_watchlist(cfg["watchlist_csv"])
    except Exception as err:
        return result(False, f"Could not read the sheet: {err}.")
    rows = prices["watchlist"]
    priced = sum(1 for w in rows if w["price"] is not None)
    sp = prices["benchmarks"].get("sp500")
    return result(True, f"Read {len(rows)} stocks, {priced} with prices" + (f"; S&P 500 at {sp['value']:,.0f}" if sp else "") + ".")


def tipranks_usage():
    use = dg.load_state().get("tipranks") or {}
    return use.get("calls", 0)


def test_tipranks(cfg, live=False):
    key = real(cfg.get("tipranks_api_key"))
    if not key:
        return result(True, "No TipRanks key: the digest works without one.", warn=True)
    problem = tipranks.key_problem(key)
    if problem:
        return result(False, problem[0].upper() + problem[1:] + ".")
    if not live:
        return result(True, f"The key looks right. The digest has used {tipranks_usage()} TipRanks calls this month. "
                            "“Test with TipRanks” checks it for real and uses 1 call.")
    state = dg.load_state()
    out = io.StringIO()
    with redirect_stdout(out):
        ok = tipranks.check(cfg, state)
    dg.save_state(state)
    lines = [ln.strip() for ln in out.getvalue().splitlines()]
    said = next((ln for ln in lines if ln.startswith("TipRanks says:")), "")
    if ok:
        return result(True, "TipRanks answered with Apple's analyst data. " + said)
    why = next((ln for ln in lines if "FAILED" in ln), "TipRanks did not answer.")
    return result(False, why.replace("TipRanks: FAILED: ", "TipRanks said: "))


TESTS = {"gemini": test_gemini, "channels": test_channels, "email": test_email, "send_email": lambda c: test_email(c, send=True),
         "folder": test_folder, "watchlist": test_watchlist, "tipranks": test_tipranks, "tipranks_live": lambda c: test_tipranks(c, live=True)}


def drive_folders():
    """Google Drive for desktop folders on this computer, as suggestions for the JSON folder."""
    roots = []
    if sys.platform == "darwin":
        roots = sorted((Path.home() / "Library" / "CloudStorage").glob("GoogleDrive-*/My Drive"))
    elif os.name == "nt":
        roots = [Path(f"{d}:\\My Drive") for d in string.ascii_uppercase[3:] if os.path.isdir(f"{d}:\\My Drive")]
    out = []
    for root in roots:
        econova = root / "Econova" / "Video Digests" / "json"
        out.append(str(econova if econova.parent.exists() else root))
    return out


def analyst_suggestions(limit=24):
    """Speakers in the saved videos, most frequent first, as suggestions for "Analysts to follow"."""
    seen = {}
    for f in dg.CACHE_DIR.glob("*.json") if dg.CACHE_DIR.exists() else []:
        try:
            notes = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        names = {}
        for s in dg.note_speakers(notes):
            names.setdefault(s["name"].strip(), s.get("role") or "")
        for name, role in names.items():
            if len(name.split()) < 2:   # "Sam" or "Host" is not enough to follow someone by
                continue
            key = name.lower()
            row = seen.setdefault(key, {"name": name, "role": role, "videos": 0})
            row["videos"] += 1
            row["role"] = row["role"] or role
    return sorted(seen.values(), key=lambda r: (-r["videos"], r["name"]))[:limit]


def pick_folder():
    """Open the system's own folder chooser. Returns the chosen path, or "" when cancelled."""
    if sys.platform == "darwin":
        r = run_hidden(["osascript", "-e", "activate", "-e",
                        'POSIX path of (choose folder with prompt "Choose the folder for the daily JSON files")'], timeout=600)
        return r.stdout.strip().rstrip("/") if r.returncode == 0 else ""
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
              "$d.Description = 'Choose the folder for the daily JSON files'; "
              "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "
              "if ($d.ShowDialog($o) -eq 'OK') { $d.SelectedPath }")
        r = run_hidden(["powershell", "-NoProfile", "-STA", "-Command", ps], timeout=600)
        return r.stdout.strip()
    raise RuntimeError("Type the folder's path instead.")


# ---------------------------------------------------------------- running the digest from the app

class Job:
    """One digest run at a time, started from the home page. Its output goes to a file, not to this app, so the run
    finishes even if Market Digest is closed meanwhile: a real run appends to digest.log, a preview writes preview.log."""
    lock = threading.Lock()
    proc = None
    kind = ""
    started = ""
    log = None
    offset = 0

    @classmethod
    def start(cls, kind):
        args = {"preview": ["--hours", "72", "--dry-run", "--open"], "now": []}[kind]
        with cls.lock:
            if cls.proc and cls.proc.poll() is None:
                raise ValueError("A digest is already being made. Wait for it to finish.")
            cls.kind, cls.started = kind, datetime.now().isoformat(timespec="seconds")
            cls.log = dg.HERE / ("digest.log" if kind == "now" else "preview.log")
            env = child_env()
            with open(cls.log, "a" if kind == "now" else "w", encoding="utf-8") as out:
                out.seek(0, os.SEEK_END)
                cls.offset = out.tell()
                # its own session (Mac) or hidden console (Windows): closing the Market Digest window does not stop it
                cls.proc = subprocess.Popen([console_python(), "-u", str(dg.HERE / "digest.py"), *args], cwd=dg.HERE, env=env,
                                            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                            creationflags=0x08000000 if os.name == "nt" else 0, start_new_session=os.name != "nt")

    @classmethod
    def snapshot(cls):
        if not cls.proc:
            return {"running": False, "kind": "", "started": "", "exit": None, "lines": []}
        exit_code = cls.proc.poll()
        try:
            with open(cls.log, "rb") as f:
                f.seek(cls.offset)
                lines = f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            lines = []
        return {"running": exit_code is None, "kind": cls.kind, "started": cls.started, "exit": exit_code, "lines": lines[-60:]}


# ---------------------------------------------------------------- what the home page shows

# ---------------------------------------------------------------- updates

def version():
    try:
        return (dg.HERE / "VERSION").read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def version_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])


class Update:
    """The newest released version, looked up in the background so no page waits for the internet."""
    latest = None
    checked = 0
    lock = threading.Lock()

    @classmethod
    def fetch_latest(cls):
        req = urllib.request.Request(f"https://raw.githubusercontent.com/{REPO}/master/VERSION", headers=dg.UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", "replace").strip()[:20]

    @classmethod
    def refresh(cls):
        try:
            cls.latest = cls.fetch_latest()
        except Exception:
            pass

    @classmethod
    def info(cls):
        with cls.lock:
            if time.time() - cls.checked > 6 * 3600:
                cls.checked = time.time()
                threading.Thread(target=cls.refresh, daemon=True).start()
        mine = version()
        newer = bool(cls.latest and version_key(cls.latest) > version_key(mine))
        return {"version": mine, "latest": cls.latest if newer else None}


def download_release():
    req = urllib.request.Request(f"https://codeload.github.com/{REPO}/zip/refs/heads/master", headers=dg.UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def apply_update(download=None):
    """Replace the program files with the newest release. Returns the new version. Raises RuntimeError and changes
    nothing if the download is incomplete or a file in it is broken."""
    try:
        archive = zipfile.ZipFile(io.BytesIO((download or download_release)()))
    except Exception as err:
        raise RuntimeError(f"The update could not be downloaded ({err}). Check the internet connection and try again.")
    with archive:
        names = {n.split("/", 1)[1]: n for n in archive.namelist() if "/" in n}
        try:   # the release says which files it is made of, so a version that adds a file still updates fully
            wanted = program_files(archive.read(names["MANIFEST"]).decode("utf-8"))
        except (KeyError, ValueError) as err:
            raise RuntimeError(f"The update is incomplete ({err}), so nothing was changed.")
        missing = [f for f in wanted if f not in names]
        if missing:
            raise RuntimeError(f"The update is incomplete ({missing[0]} is missing), so nothing was changed.")
        files = {f: archive.read(names[f]) for f in wanted}
    new = files["VERSION"].decode("utf-8", "replace").strip()
    if version_key(new) <= version_key(version()):
        raise RuntimeError("You already have the newest version.")
    for name, data in files.items():   # a broken file must never replace a working one
        try:
            if name.endswith(".py"):
                compile(data, name, "exec")
            elif name.endswith(".json"):
                json.loads(data)
        except (SyntaxError, ValueError) as err:
            raise RuntimeError(f"The update has a broken file ({name}: {err}), so nothing was changed.")
    for name, data in files.items():
        (dg.HERE / (name + ".new")).write_bytes(data)
    for name in files:
        (dg.HERE / (name + ".new")).replace(dg.HERE / name)
    return new


# ---------------------------------------------------------------- Claude (optional): your digest as tools in the Claude app

def claude_config_paths():
    """Where the Claude desktop app keeps its settings on this computer (the folder exists once Claude has been opened)."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    if os.name == "nt":
        roaming = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        store = sorted((local / "Packages").glob("*Claude*/LocalCache/Roaming/Claude")) if (local / "Packages").exists() else []
        return [d / "claude_desktop_config.json" for d in store] + [roaming / "Claude" / "claude_desktop_config.json"]
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def claude_entry():
    return {"command": console_python(), "args": [str(dg.HERE / "mcp_server.py")]}


def claude_status():
    paths = [p for p in claude_config_paths() if p.parent.exists()]
    connected = False
    for p in paths:
        try:
            connected = connected or json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {}).get("market-digest") == claude_entry()
        except (OSError, ValueError, AttributeError):
            pass
    return {"installed": bool(paths), "connected": connected}


def claude_connect(on=True):
    """Add (or remove) Market Digest in the Claude desktop app's list of local tools. Claude must be restarted after."""
    paths = [p for p in claude_config_paths() if p.parent.exists()]
    if not paths:
        raise ValueError("The Claude desktop app was not found on this computer. Install it from claude.ai/download, open it once, then try again.")
    for p in paths:
        try:
            doc = json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
            if not isinstance(doc, dict):
                raise ValueError
        except ValueError:
            raise ValueError(f"Claude's settings file could not be read, so it was not changed ({p}).")
        if p.exists() and not p.with_suffix(".before-market-digest.json").exists():
            p.with_suffix(".before-market-digest.json").write_bytes(p.read_bytes())   # a copy of the file as it was
        servers = doc.setdefault("mcpServers", {})
        if on:
            servers["market-digest"] = claude_entry()
        else:
            servers.pop("market-digest", None)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(p)
    return claude_status()


def json_folder(cfg):
    return Path(cfg.get("json_dir") or dg.JSON_DIR)


def made_at(path):
    """When a digest was made, from its name (digest-2026-11-09-0731.html), else from the file's time."""
    m = re.match(r"digest-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})", path.name)
    when = datetime(*map(int, m.groups())) if m else datetime.fromtimestamp(path.stat().st_mtime)
    return when.isoformat(timespec="minutes")


def status():
    cfg = read_config()
    at = daily_time(cfg)
    on = cfg.get("schedule_on", True)
    try:
        last = json.loads(dg.LAST_RUN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        last = None
    digests = sorted(dg.OUT_DIR.glob("digest-*.html"), reverse=True)[:8] if dg.OUT_DIR.exists() else []
    tests = {last["digest_file"]} if last and last.get("test") and last.get("digest_file") else set()
    try:
        latest_json = max((p.name for p in json_folder(cfg).glob("video-digest_*.json")), default="")
    except OSError:
        latest_json = ""
    to = cfg.get("email_to") or []
    return {
        "configured": bool(real(cfg.get("gemini_api_key"))),
        "schedule": {"on": on, "time": at, "active": is_scheduled(), "next": next_run(at) if on and TIME.match(at) else ""},
        "last_run": last,
        "digests": [{"name": p.name, "when": made_at(p), "test": p.name in tests} for p in digests],
        "email_to": [to] if isinstance(to, str) else to,
        "channels": len(cfg.get("channels") or []),
        "analysts": cfg.get("analysts") or [], "markets_only": cfg.get("markets_only", True),
        "json_dir": str(json_folder(cfg)), "latest_json": latest_json, "json_shared": bool(cfg.get("json_dir")),
        "watchlist": bool(cfg.get("watchlist_csv")),
        "tipranks": {"on": bool(real(cfg.get("tipranks_api_key"))), "calls": tipranks_usage()},
        "videos_saved": len(list(dg.CACHE_DIR.glob("*.json"))) if dg.CACHE_DIR.exists() else 0,
        "job": Job.snapshot(),
        "platform": platform(),
        "notify": cfg.get("notify", True), "open_when_ready": open_when_ready(cfg),
        "update": Update.info(), "claude": claude_status(),
    }


def log_tail(lines=300):
    try:
        with open(dg.HERE / "digest.log", encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=lines))
    except OSError:
        return []


def notify(title, text):
    """A desktop notice. Best effort: it never raises."""
    try:
        if sys.platform == "darwin":
            quote = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
            run_hidden(["osascript", "-e", f"display notification {quote(text)} with title {quote(title)}"])
        elif os.name == "nt":
            env = {**os.environ, "MD_TITLE": title, "MD_TEXT": text}
            ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                  "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                  "$t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode($env:MD_TITLE)) > $null; "
                  "$t.Item(1).AppendChild($x.CreateTextNode($env:MD_TEXT)) > $null; "
                  "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'; "
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($x))")
            run_hidden(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env)
    except Exception:
        pass


# ---------------------------------------------------------------- the web server (this computer only)

class Handler(BaseHTTPRequestHandler):
    setup_mode = False   # started by the installer: Finish closes it
    port = PORT

    def log_message(self, *a):
        pass

    def allowed(self):
        # Only pages opened from this computer's own address may use it (this also blocks DNS rebinding).
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def send(self, code, body, ctype="application/json", headers=()):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def page(self, name):
        return self.send(200, (dg.HERE / name).read_text(encoding="utf-8"), "text/html")

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/" and "video" in q:   # "Ask a question about this video" links in saved digests
            return self.page("chat.html")
        if u.path in ("/", "/settings"):
            return self.page("app.html")
        if u.path == "/chat":
            return self.page("chat.html")
        if u.path == "/api/settings":
            return self.send(200, {**public(read_config()), "setup": self.setup_mode, "drive_folders": drive_folders(),
                                   "popular_channels": [{"name": n, "url": u} for n, u in POPULAR_CHANNELS],
                                   "popular_analysts": POPULAR_ANALYSTS, "claude": claude_status(), "version": version(),
                                   "analyst_suggestions": analyst_suggestions(),
                                   "platform": platform(), "program_folder": str(dg.HERE)})
        if u.path == "/api/status":
            return self.send(200, {**status(), "setup": self.setup_mode})
        if u.path == "/api/log":
            return self.send(200, {"lines": log_tail()})
        if u.path.startswith("/digests/"):
            name = u.path.rsplit("/", 1)[-1]
            f = dg.OUT_DIR / name
            if DIGEST_FILE.match(name) and f.is_file():
                return self.send(200, f.read_bytes(), "text/html")
            return self.send(404, "That digest is no longer saved.", "text/plain")
        if u.path == "/api/state":
            vids = [{"id": v["id"], "title": v.get("title"), "channel": v.get("channel"), "date": v["date"].strftime("%d %b") if v["date"] else ""}
                    for v, _ in chat.library()]
            with chat.LOCK:
                chats = [{"id": c["id"], "title": c["title"], "updated": c.get("updated", c["created"])} for c in chat.load_chats()]
            return self.send(200, {"videos": vids, "chats": chats})
        if u.path == "/api/chat":
            cid = q.get("id", [""])[0]
            with chat.LOCK:
                found = next((c for c in chat.load_chats() if c["id"] == cid), None)
            return self.send(200, found) if found else self.send(404, {"error": "That chat no longer exists."})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        # A JSON body cannot be sent by another website without the browser asking first, which this server never allows.
        if not self.allowed() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send(403, {"error": "forbidden"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "bad request"})
        try:
            return self.route(self.path, req)
        except ValueError as err:
            return self.send(400, {"error": str(err)})
        except Exception as err:
            return self.send(502, {"error": f"{err}"})

    def route(self, path, req):
        if path.startswith("/api/test/"):
            name = path.rsplit("/", 1)[-1]
            if name not in TESTS:
                return self.send(404, {"error": "not found"})
            cfg, _ = merged(req, read_config())
            return self.send(200, TESTS[name](cfg))
        if path == "/api/save":
            saved = read_config()
            cfg, errors = merged(req, saved)
            if errors:
                return self.send(400, {"error": "Some settings need fixing (marked in red).", "fields": errors})
            write_config(cfg)
            try:
                said = schedule(cfg["schedule_on"], cfg["daily_time"])
                sched_ok = True
            except RuntimeError as err:
                said, sched_ok = str(err), False
            return self.send(200, {"ok": True, "schedule": said, "schedule_ok": sched_ok, "settings": public(cfg)})
        if path == "/api/pick-folder":
            return self.send(200, {"path": pick_folder()})
        if path == "/api/run":
            if not real(read_config().get("gemini_api_key")):
                raise ValueError("Save your settings first.")
            Job.start(req.get("kind", "preview"))
            return self.send(200, Job.snapshot())
        if path in ("/api/finish", "/api/quit"):
            self.send(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None
        if path == "/api/claude":
            return self.send(200, claude_connect(on=req.get("action") != "disconnect"))
        if path == "/api/update":
            if Job.snapshot()["running"]:
                raise ValueError("A digest is being made. Update when it has finished.")
            try:
                new = apply_update()
            except RuntimeError as err:
                raise ValueError(str(err))
            self.send(200, {"ok": True, "version": new})
            # not a daemon thread (request threads are, and their children inherit it): it must outlive the server loop
            threading.Thread(target=restart, args=(self.server,), daemon=False).start()
            return None
        if path == "/api/ask":
            try:
                cfg = dg.load_config()
            except SystemExit:
                raise ValueError("Add your Gemini key in Settings first.")
            return self.send(200, chat.answer(cfg, req))
        if path == "/api/delete":
            with chat.LOCK:
                chat.save_chats([c for c in chat.load_chats() if c["id"] != req.get("id")])
            return self.send(200, {"ok": True})
        if path == "/api/rename":
            with chat.LOCK:
                chats = chat.load_chats()
                for c in chats:
                    if c["id"] == req.get("id") and (req.get("title") or "").strip():
                        c["title"] = req["title"].strip()[:80]
                chat.save_chats(chats)
            return self.send(200, {"ok": True})
        return self.send(404, {"error": "not found"})


def restart(server):
    """Start the (updated) app again in place of this one. The open page reconnects by itself."""
    time.sleep(0.5)   # let the answer to the page go out first
    server.shutdown()
    server.server_close()
    subprocess.Popen([sys.executable, str(dg.HERE / "app.py"), "--no-browser", "--wait-for-port"], cwd=dg.HERE,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=0x08000000 if os.name == "nt" else 0, start_new_session=os.name != "nt")
    os._exit(0)


def stop_running():
    """Ask a Market Digest that is already open to quit. True if one answered."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/quit", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).read()
        time.sleep(1)
        return True
    except Exception:
        return False


def bind(wait=False):
    for attempt in range(8 if wait else 1):
        try:
            return ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError:
            if attempt < (7 if wait else 0):
                time.sleep(0.7)
    raise OSError("port in use")


def serve(setup=False, page="/", open_browser=True, wait_for_port=False):
    os.environ["PATH"] = str(dg.HERE / "bin") + os.pathsep + os.environ.get("PATH", "")   # the yt-dlp the installer put in bin
    try:
        server = bind(wait_for_port)
    except OSError:
        if not setup:   # the app is already open in another window
            print(f"Market Digest is already running. Opening http://127.0.0.1:{PORT}{page}")
            webbrowser.open(f"http://127.0.0.1:{PORT}{page}")
            return
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)   # the installer's page can use any free port
    Handler.setup_mode, Handler.port = setup, server.server_address[1]
    url = f"http://127.0.0.1:{Handler.port}{page}"
    print(f"Market Digest: {url}  (only this computer can open it)")
    print("Click Finish on the page when you are done." if setup else "To stop it, click Quit at the top of the page.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Market Digest: settings, status and chat in your browser.")
    ap.add_argument("--setup", action="store_true", help="the installer's settings page; Finish closes it")
    ap.add_argument("--schedule", action="store_true", help="set the daily run again from the saved settings, then stop")
    ap.add_argument("--daily", action="store_true", help="the scheduled run: make the digest, trying again if it fails, then stop")
    ap.add_argument("--stop", action="store_true", help="ask a running Market Digest to quit, then stop")
    ap.add_argument("--notify", nargs=2, metavar=("TITLE", "TEXT"), help="show a desktop notice, then stop")
    ap.add_argument("--notify-failure", action="store_true", help="show a desktop notice that the daily run failed, then stop")
    ap.add_argument("--wait-for-port", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--page", default="/", help="the page to open: /, /settings or /chat")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)
    if args.notify_failure:
        notify("Market digest did not run", "Open Market Digest on the desktop to see why.")
        return
    if args.notify:
        notify(*args.notify)
        return
    if args.stop:
        print("Closed the Market Digest that was open." if stop_running() else "Market Digest was not open.")
        return
    if args.daily:
        sys.exit(daily_run())
    if args.schedule:
        cfg = read_config()
        if not real(cfg.get("gemini_api_key")):
            sys.exit("No settings yet. Run the installer without -Unattended.")
        at = daily_time(cfg)
        if cfg.get("daily_time") != at:   # remember a time an older installer set, so later updates keep it
            write_config({**cfg, "daily_time": at})
        try:
            print(schedule(cfg.get("schedule_on", True), at))
        except RuntimeError as err:
            sys.exit(str(err))
        return
    if not dg.YTMD.exists():
        sys.exit(f"Put app.py in the same folder as the ytmd script (looked for {dg.YTMD}).")
    if args.wait_for_port:   # just updated: point the daily schedule at this version's own command
        cfg = read_config()
        try:
            if real(cfg.get("gemini_api_key")):
                schedule(cfg.get("schedule_on", True), daily_time(cfg))
        except Exception:
            pass
    serve(setup=args.setup, page="/settings?setup=1" if args.setup else args.page, open_browser=not args.no_browser,
          wait_for_port=args.wait_for_port)


if __name__ == "__main__":
    main()
