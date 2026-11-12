#!/bin/bash
# Sets up the market video digest on this Mac. The Windows version is install.bat.
# Start it by double-clicking it in Finder (the first time, macOS may ask: then right-click it > Open > Open).
# It installs what is needed, then opens the settings page in your browser, where you paste your keys.
# Safe to run again: it updates the program files and keeps the settings, saved videos and chats.
set -uo pipefail

INSTALL_DIR="${MARKET_DIGEST_DIR:-$HOME/market-digest}"
SRC="$(cd "$(dirname "$0")" && pwd)/app"   # the program's files are in the app folder next to this installer

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mSTOPPED: %s\033[0m\n' "$1"; exit 1; }
# MANIFEST lists the program's files, one a line (the same list the app's own updater uses).
[ -f "$SRC/MANIFEST" ] || fail "The app folder is missing next to install-mac.command. Unzip the whole folder first, then run the installer from it."
FILES=()
while IFS= read -r f || [ -n "$f" ]; do
    f="${f%$'\r'}"   # a zip made on Windows can carry Windows line endings
    [ -n "$f" ] && FILES+=("$f")
done < "$SRC/MANIFEST"
for f in "${FILES[@]}"; do
    [ -e "$SRC/$f" ] || fail "app/$f is missing next to install-mac.command. Unzip the whole folder first, then run the installer from it."
done

step "1. Python"
PY=""
OWN_PY="$INSTALL_DIR/python/bin/python3"   # the private copy this installer puts there when the Mac has no Python
for exe in "$OWN_PY" /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$(command -v python3 || true)"; do
    [ -n "$exe" ] && [ -x "$exe" ] || continue
    if "$exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
        PY="$("$exe" -c "import sys; print(sys.executable)")"
        break
    fi
done
if [ -z "$PY" ]; then
    # No Python on this Mac: fetch a private copy into the program folder, so nobody has to install anything by hand.
    # It is the standalone Python build that tools like uv use (github.com/astral-sh/python-build-standalone),
    # checked against the release's published checksums, and used by Market Digest only.
    PBS_TAG="20241016"; PBS_VER="3.12.7"
    case "$(uname -m)" in arm64) PBS_ARCH="aarch64" ;; *) PBS_ARCH="x86_64" ;; esac
    PBS_FILE="cpython-$PBS_VER+$PBS_TAG-$PBS_ARCH-apple-darwin-install_only.tar.gz"
    PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG"
    echo "Python is not on this Mac. Downloading a private copy for Market Digest (about 17 MB)..."
    TMP="$(mktemp -d)"
    if curl -fsSL "$PBS_URL/$PBS_FILE" -o "$TMP/py.tar.gz" && curl -fsSL "$PBS_URL/SHA256SUMS" -o "$TMP/SHA256SUMS"; then
        want="$(grep " $PBS_FILE\$" "$TMP/SHA256SUMS" | cut -d' ' -f1)"
        got="$(shasum -a 256 "$TMP/py.tar.gz" | cut -d' ' -f1)"
        if [ -n "$want" ] && [ "$want" = "$got" ]; then
            mkdir -p "$INSTALL_DIR" && rm -rf "$INSTALL_DIR/python" && tar -xzf "$TMP/py.tar.gz" -C "$INSTALL_DIR" && [ -x "$OWN_PY" ] && PY="$OWN_PY"
        else
            echo "The download did not match its published checksum, so it was not used."
        fi
    fi
    rm -rf "$TMP"
fi
case "$PY" in "$INSTALL_DIR/python/"*)
    # This Python does not read the Mac's keychain for web certificates: give it a copy of the Mac's own root
    # certificates, read at every start by sitecustomize (refreshed each time the installer runs).
    PYDIR="$INSTALL_DIR/python"
    security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain > "$PYDIR/certs.pem" 2>/dev/null
    SITE="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    cat > "$SITE/sitecustomize.py" <<'PYEOF'
# Written by the Market Digest installer: this Python uses the Mac's own root certificates for https.
import os
_certs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "certs.pem")
if os.path.isfile(_certs) and os.path.getsize(_certs) > 0:
    os.environ.setdefault("SSL_CERT_FILE", os.path.normpath(_certs))
PYEOF
    ;;
esac
if [ -z "$PY" ]; then
    open "https://www.python.org/downloads/macos/" 2>/dev/null
    fail "Python could not be set up automatically. Install it from the page that just opened (the macOS 64-bit universal installer), then run this installer again."
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
# An update: close a Market Digest that is open, so it does not keep running the old version.
# The new app.py asks, because it knows how to close older versions too.
(cd "$SRC" && "$PY" app.py --stop >/dev/null 2>&1)
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

# The launchers use this Mac's own Python, and the yt-dlp in bin/. The daily run needs no launcher: launchd starts
# "python app.py --daily" itself (set up by the settings page).
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
chmod +x "$INSTALL_DIR/run_app.command" "$INSTALL_DIR/run_chat.command"

cd "$INSTALL_DIR" || fail "Could not open $INSTALL_DIR."
if ! "$PY" ytmd doctor >/dev/null 2>&1; then
    "$PY" ytmd doctor
    fail "The caption reader (ytmd) is not ready. See the lines above."
fi

step "4. Settings (in your browser)"
echo "The setup page is opening in your browser. Follow its three short steps, then click Finish."
echo "(If no page opens, copy the address below into your browser.)"
"$PY" app.py --setup || fail "The settings page stopped. Run this installer again."

step "5. Daily schedule"
"$PY" app.py --schedule || fail "No settings were saved, or the schedule could not be set. Run this installer again and click Save on the page."

step "6. Market Digest on the desktop"
# A small app that starts Market Digest in the background (no Terminal window) and opens its page.
# Double-clicking it again just opens the page. To close Market Digest, click Quit at the top of the page.
rm -f "$HOME/Desktop/Digest chat.command" "$HOME/Desktop/Market Digest.command"   # shortcuts made by older versions
APP="$HOME/Desktop/Market Digest.app"
rm -rf "$APP"
if mkdir -p "$APP/Contents/MacOS" 2>/dev/null; then
    cat > "$APP/Contents/MacOS/MarketDigest" <<EOF
#!/bin/bash
cd "$INSTALL_DIR" || exit 1
export PATH="$INSTALL_DIR/bin:\$PATH"
nohup "$PY" app.py >/dev/null 2>&1 &
EOF
    chmod +x "$APP/Contents/MacOS/MarketDigest"
    cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Market Digest</string>
    <key>CFBundleIdentifier</key><string>com.nugenix.market-digest.app</string>
    <key>CFBundleExecutable</key><string>MarketDigest</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo 1)</string>
    <key>LSUIElement</key><true/>
</dict>
</plist>
EOF
    echo "Added 'Market Digest' to the desktop: it shows whether the digest ran, your settings, and the chat."
else
    echo "Could not add it to the desktop (macOS may have asked Terminal for access). Use $INSTALL_DIR/run_app.command instead."
fi

printf '\n\033[32mDone. You can close this window.\033[0m\n'
echo "To check on the digest, change a setting or chat about the videos: double-click 'Market Digest' on the desktop."
echo "Program folder: $INSTALL_DIR. Updates: Market Digest tells you when one is ready and installs it in one click."
