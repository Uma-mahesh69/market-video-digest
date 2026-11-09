#!/bin/bash
# Sets up the market video digest on this Mac. The Windows version is install.bat.
# Start it by double-clicking it in Finder (the first time, macOS may ask: then right-click it > Open > Open).
# It installs what is needed, then opens the settings page in your browser, where you paste your keys.
# Safe to run again: it updates the program files and keeps the settings, saved videos and chats.
set -uo pipefail

INSTALL_DIR="${MARKET_DIGEST_DIR:-$HOME/market-digest}"
SRC="$(cd "$(dirname "$0")" && pwd)"
FILES=(app.py app.html digest.py digest_export.py digest_schema.json tickers.json market_data.py market_schema.json tipranks.py chat.py chat.html ytmd README.md digest_config.example.json)

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mSTOPPED: %s\033[0m\n' "$1"; exit 1; }
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
# Runs the daily digest and keeps a log next to this file. Started every day by launchd (set up by Market Digest).
# A failed run (no internet yet, email down) is tried again every 30 minutes, 3 times; then a notice says so.
cd "\$(dirname "\$0")"
export PATH="\$PWD/bin:\$PATH"
for attempt in 1 2 3 4; do
    "$PY" digest.py >> digest.log 2>&1 && exit 0
    [ "\$attempt" = 4 ] || { echo "\$(date '+%H:%M:%S') The run failed; trying again in 30 minutes." >> digest.log; sleep 1800; }
done
"$PY" app.py --notify-failure
exit 1
EOF
cat > "$INSTALL_DIR/run_app.command" <<EOF
#!/bin/bash
# Opens Market Digest (status, settings and chat) in your browser. Keep this window open while you use it.
cd "$INSTALL_DIR"
export PATH="$INSTALL_DIR/bin:\$PATH"
"$PY" app.py
EOF
# Older "Digest chat" shortcuts keep working: they open the same app, on its Chat page.
cat > "$INSTALL_DIR/run_chat.command" <<EOF
#!/bin/bash
cd "$INSTALL_DIR"
export PATH="$INSTALL_DIR/bin:\$PATH"
"$PY" chat.py
EOF
chmod +x "$INSTALL_DIR/run_digest.sh" "$INSTALL_DIR/run_app.command" "$INSTALL_DIR/run_chat.command"

cd "$INSTALL_DIR" || fail "Could not open $INSTALL_DIR."
if ! "$PY" ytmd doctor >/dev/null 2>&1; then
    "$PY" ytmd doctor
    fail "The caption reader (ytmd) is not ready. See the lines above."
fi

step "4. Settings (in your browser)"
echo "The settings page is opening in your browser. Paste your keys there, test them, click Save, then Finish."
echo "(If no page opens, copy the address below into your browser.)"
"$PY" app.py --setup || fail "The settings page stopped. Run this installer again."

step "5. Daily schedule"
"$PY" app.py --schedule || fail "No settings were saved, or the schedule could not be set. Run this installer again and click Save on the page."

step "6. Market Digest on the desktop"
rm -f "$HOME/Desktop/Digest chat.command"   # replaced by Market Digest, which has the chat too
if cp -f "$INSTALL_DIR/run_app.command" "$HOME/Desktop/Market Digest.command" 2>/dev/null; then
    chmod +x "$HOME/Desktop/Market Digest.command"
    echo "Added 'Market Digest' to the desktop: it shows whether the digest ran, your settings, and the chat."
else
    echo "Could not add it to the desktop (macOS may have asked Terminal for access). Use $INSTALL_DIR/run_app.command instead."
fi

printf '\n\033[32mDone. You can close this window.\033[0m\n'
echo "To check on the digest, change a setting or chat about the videos: double-click 'Market Digest' on the desktop."
echo "Program folder: $INSTALL_DIR (run this installer again to update; your settings are kept)."
