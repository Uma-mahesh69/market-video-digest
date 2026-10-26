#!/bin/bash
# Sets up the market video digest on this Mac. The Windows version is install.bat.
# Easiest way to start it: open Terminal, type "bash " (with the space), drag this file into the window, press Return.
# Safe to run again: it updates the program files and keeps the settings, saved videos and chats.
set -uo pipefail

INSTALL_DIR="${MARKET_DIGEST_DIR:-$HOME/market-digest}"
LABEL="com.nugenix.market-digest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SRC="$(cd "$(dirname "$0")" && pwd)"
FILES=(digest.py digest_export.py digest_schema.json tickers.json chat.py chat.html ytmd README.md digest_config.example.json)

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mSTOPPED: %s\033[0m\n' "$1"; exit 1; }
ask() {   # ask "question" "default"  -> prints the answer
    local answer
    read -r -p "$1 [$2] " answer
    printf '%s' "${answer:-$2}"
}
ask_secret() {   # ask_secret "question" min_length  -> prints the answer; typing is hidden
    local value
    while true; do
        read -r -s -p "$1 (paste with Cmd+V; it stays hidden): " value
        printf '\n' >&2
        value="$(printf '%s' "$value" | tr -d '[:space:]')"
        if [ "${#value}" -lt "$2" ]; then
            printf 'That is too short to be right (%s characters). Try again.\n' "${#value}" >&2
            continue
        fi
        printf '%s' "$value"
        return
    done
}

for f in "${FILES[@]}"; do
    [ -e "$SRC/$f" ] || fail "$f is missing next to install-mac.command. Unzip the whole folder first, then run the installer from it."
done

step "1. Python"
PY=""
for exe in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$(command -v python3 || true)"; do
    [ -n "$exe" ] && [ -x "$exe" ] || continue
    if "$exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
        PY="$("$exe" -c "import sys; print(sys.executable)")"
        break
    fi
done
if [ -z "$PY" ]; then
    open "https://www.python.org/downloads/macos/" 2>/dev/null
    fail "Python 3.9 or newer is not installed. Install it from the page that just opened (the macOS 64-bit universal installer), then run this installer again."
fi
echo "Using $PY"

# Python from python.org needs its certificates installed once, or every https request fails.
if "$PY" -c "import urllib.request; urllib.request.urlopen('https://www.youtube.com', timeout=20)" 2>&1 | grep -q CERTIFICATE_VERIFY_FAILED; then
    certs="/Applications/Python $("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')/Install Certificates.command"
    [ -f "$certs" ] || fail "Python cannot check web certificates. Open Applications > Python 3.x and double-click 'Install Certificates.command', then run this installer again."
    echo "Installing Python's web certificates ($certs)..."
    bash "$certs" >/dev/null || fail "Installing the certificates did not work. Double-click '$certs' in Finder, then run this installer again."
fi

step "2. Program files -> $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/bin" || fail "Could not create $INSTALL_DIR."
if [ "$(cd "$INSTALL_DIR" && pwd)" != "$SRC" ]; then
    for f in "${FILES[@]}"; do cp -f "$SRC/$f" "$INSTALL_DIR/" || fail "Could not copy $f."; done
fi
echo "Copied. Your settings, saved videos and chats in that folder are kept."

step "3. yt-dlp (reads YouTube captions)"
YTDLP="$INSTALL_DIR/bin/yt-dlp"
if command -v yt-dlp >/dev/null; then
    echo "Already installed: $(command -v yt-dlp)"
elif [ -x "$YTDLP" ]; then
    echo "Updating $YTDLP"
    "$YTDLP" -U || true
else
    echo "Downloading the official yt-dlp for macOS from GitHub..."
    curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" -o "$YTDLP" || fail "Could not download yt-dlp. Check the internet connection and run this again."
    chmod +x "$YTDLP"
fi
export PATH="$INSTALL_DIR/bin:$PATH"

# The launchers use this Mac's own Python, and the yt-dlp in bin/.
cat > "$INSTALL_DIR/run_digest.sh" <<EOF
#!/bin/bash
# Runs the daily digest and keeps a log next to this file. Started every day by launchd ($PLIST).
# A failed run (no internet yet, email down) is tried again every 30 minutes, 3 times.
cd "\$(dirname "\$0")"
export PATH="\$PWD/bin:\$PATH"
for attempt in 1 2 3 4; do
    "$PY" digest.py >> digest.log 2>&1 && exit 0
    [ "\$attempt" = 4 ] || { echo "\$(date '+%H:%M:%S') The run failed; trying again in 30 minutes." >> digest.log; sleep 1800; }
done
exit 1
EOF
cat > "$INSTALL_DIR/run_chat.command" <<EOF
#!/bin/bash
# Starts the chat page. Keep this window open while you use it.
cd "$INSTALL_DIR"
export PATH="$INSTALL_DIR/bin:\$PATH"
"$PY" chat.py
EOF
chmod +x "$INSTALL_DIR/run_digest.sh" "$INSTALL_DIR/run_chat.command"

cd "$INSTALL_DIR" || fail "Could not open $INSTALL_DIR."
if ! "$PY" ytmd doctor >/dev/null 2>&1; then
    "$PY" ytmd doctor
    fail "The caption reader (ytmd) is not ready. See the lines above."
fi

step "4. Settings"
CONFIG="$INSTALL_DIR/digest_config.json"
write=yes
if [ -f "$CONFIG" ]; then
    case "$(ask "Settings already exist. Enter them again?" "n")" in [yY]*) write=yes ;; *) write=no ;; esac
fi
if [ "$write" = yes ]; then
    echo "Your answers are saved only on this Mac, in $CONFIG"
    key="$(ask_secret "Gemini API key (from https://aistudio.google.com/apikey)" 30)"
    channels="$(ask "YouTube channels to follow, separated by commas" "https://www.youtube.com/@TheStreet")"
    to="$(ask "Email address that should receive the digest (blank = no email, just save it)" "")"
    user=""; pass=""
    if [ -n "$to" ]; then
        user="$(ask "Gmail address that sends it" "${to%%,*}")"
        echo "Gmail needs an app password: Google Account > Security > 2-Step Verification > App passwords."
        pass="$(ask_secret "Gmail app password (16 letters)" 16)"
    fi
    echo "Each digest is also saved as a JSON file for the Econova hub. To share it, give a Google Drive folder."
    drive="$(ls -d "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive" 2>/dev/null | head -1)"
    [ -n "$drive" ] && echo "Your Google Drive is at: $drive   (for example: $drive/Econova/Video Digests/json)"
    jsondir="$(ask "Folder for the daily JSON file (blank = digest_json in the program folder)" "")"
    KEY="$key" CHANNELS="$channels" TO="$to" SMTP_USER="$user" SMTP_PASS="$pass" JSON_DIR="$jsondir" "$PY" - "$CONFIG" <<'EOF' || fail "Could not save the settings."
import json, os, sys
split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
settings = {
    "channels": split(os.environ["CHANNELS"]),
    "gemini_api_key": os.environ["KEY"],
    "models": ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "lookback_hours": 26,
    "max_videos": 20,
    "email_to": split(os.environ["TO"]),
    "smtp_user": os.environ["SMTP_USER"],
    "smtp_password": os.environ["SMTP_PASS"],
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    # A folder dragged into Terminal arrives as /Users/x/My\ Drive or in quotes.
    "json_dir": os.path.expanduser(os.environ["JSON_DIR"].strip().strip("'\"").replace("\\ ", " ")),
}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
EOF
    chmod 600 "$CONFIG"   # only this user can read the key and password
    echo "Saved."
fi
while true; do
    time="$(ask "Time to make the digest each day (24-hour, HH:MM)" "07:30")"
    [[ "$time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] && break
done

step "5. Testing channels, Gemini key, JSON folder and email"
"$PY" digest.py --check || fail "A test failed (see FAILED above). Fix it by running this installer again and re-entering the settings."

step "6. Daily schedule"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key><array><string>/bin/bash</string><string>$INSTALL_DIR/run_digest.sh</string></array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
    <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$((10#${time%%:*}))</integer><key>Minute</key><integer>$((10#${time##*:}))</integer></dict>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST" || fail "Could not schedule the daily run."
echo "Scheduled every day at $time (while you are logged in; if the Mac is asleep then, it runs when it wakes)."

step "7. Desktop shortcut for the chat page"
if cp -f "$INSTALL_DIR/run_chat.command" "$HOME/Desktop/Digest chat.command" 2>/dev/null; then
    chmod +x "$HOME/Desktop/Digest chat.command"
    echo "Added 'Digest chat' to the desktop."
else
    echo "Could not add it to the desktop (macOS may have asked Terminal for access). Use $INSTALL_DIR/run_chat.command instead."
fi

case "$(ask "Make a test digest of the last 3 days now? It opens in the browser and is not emailed (y/n)" "y")" in
    [yY]*) "$PY" digest.py --hours 72 --dry-run --open ;;
esac

printf '\n\033[32mDone. The digest arrives by email every day at %s.\033[0m\n' "$time"
echo "Chat about the videos: double-click 'Digest chat' on the desktop."
echo "Program folder: $INSTALL_DIR (run this installer again to change settings or update)."
