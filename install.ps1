# Sets up the market video digest on this Windows computer. Started by install.bat.
# It installs what is needed, then opens the settings page in your browser, where you paste your keys.
# Safe to run again: it updates the program files and keeps the settings, saved videos and chats.
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE "market-digest"),
    [switch]$Unattended   # an update: keep the settings and the daily time, open no page
)
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$files = "app.py", "app.html", "digest.py", "digest_export.py", "digest_schema.json", "tickers.json", "market_data.py", "market_schema.json", "tipranks.py", "chat.py", "chat.html", "ytmd", "README.md", "digest_config.example.json"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }
function Find-Python {
    # The "python" that ships with Windows can be a shortcut to the Store, so ask each candidate for its real path.
    $candidates = @("py", "python") + @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object { $_.FullName })
    foreach ($exe in $candidates) {
        try {
            $pre = @(); if ($exe -eq "py") { $pre = @("-3") }
            $out = & $exe @pre -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out -and (Test-Path ($out | Select-Object -Last 1).Trim())) { return ($out | Select-Object -Last 1).Trim() }
        } catch { }
    }
    return $null
}

foreach ($f in $files) { if (-not (Test-Path (Join-Path $src $f))) { Fail "$f is missing next to install.bat. Unzip the whole folder first, then run install.bat from it." } }

Step "1. Python"
$py = Find-Python
if (-not $py) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Start-Process "https://www.python.org/downloads/windows/"
        Fail "Python is not installed. Install it from the page that just opened (tick 'Add python.exe to PATH'), then run install.bat again."
    }
    Write-Host "Installing Python 3.13 for this user (a few minutes)..."
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
    $py = Find-Python
    if (-not $py) { Fail "Python did not install. Install it from https://www.python.org/downloads/windows/ and run install.bat again." }
}
Write-Host "Using $py"

Step "2. Program files -> $InstallDir"
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "bin") | Out-Null
if ((Resolve-Path $src).Path.TrimEnd("\") -ne (Resolve-Path $InstallDir).Path.TrimEnd("\")) {
    foreach ($f in $files) { Copy-Item (Join-Path $src $f) $InstallDir -Force }
}
Write-Host "Copied. Your settings, saved videos and chats in that folder are kept."

Step "3. yt-dlp (reads YouTube captions)"
$ytdlp = Join-Path $InstallDir "bin\yt-dlp.exe"
if (Get-Command yt-dlp -ErrorAction SilentlyContinue) {
    Write-Host "Already installed: $((Get-Command yt-dlp).Source)"
} elseif (Test-Path $ytdlp) {
    Write-Host "Updating $ytdlp"
    & $ytdlp -U | Out-Host
} else {
    Write-Host "Downloading the official yt-dlp.exe from GitHub..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile $ytdlp -UseBasicParsing
}
$env:PATH = (Join-Path $InstallDir "bin") + ";" + $env:PATH

# The launchers use this computer's own Python, and the yt-dlp in bin\.
# Task Scheduler's "restart on failure" ignores a program's exit code, so the launcher retries a failed run itself,
# as run_digest.sh does on a Mac.
$runDigest = @(
    "@echo off",
    "rem Runs the daily digest and keeps a log next to this file. Started every day by Task Scheduler.",
    "rem A failed run (no internet yet, YouTube or email down) is tried again every 30 minutes, 3 times.",
    "cd /d `"%~dp0`"",
    "set `"PATH=%~dp0bin;%PATH%`"",
    "set attempt=1",
    ":run",
    "`"$py`" digest.py >> digest.log 2>&1 && exit /b 0",
    "if %attempt% geq 4 goto failed",
    "set /a attempt+=1",
    "echo %time:~0,8% The run failed; trying again in 30 minutes.>> digest.log",
    "`"$py`" -c `"import time; time.sleep(1800)`"",
    "goto run",
    ":failed",
    "`"$py`" app.py --notify-failure",
    "exit /b 1",
    ""
) -join "`r`n"
$runApp = "@echo off`r`nrem Opens Market Digest (status, settings and chat) in your browser. Keep this window open while you use it.`r`ntitle Market Digest`r`ncd /d `"%~dp0`"`r`nset `"PATH=%~dp0bin;%PATH%`"`r`n`"$py`" app.py`r`npause`r`n"
# Older "Digest chat" shortcuts keep working: they open the same app, on its Chat page.
$runChat = "@echo off`r`ntitle Market Digest`r`ncd /d `"%~dp0`"`r`nset `"PATH=%~dp0bin;%PATH%`"`r`n`"$py`" chat.py`r`npause`r`n"
[IO.File]::WriteAllText((Join-Path $InstallDir "run_digest.bat"), $runDigest)
[IO.File]::WriteAllText((Join-Path $InstallDir "run_app.bat"), $runApp)
[IO.File]::WriteAllText((Join-Path $InstallDir "run_chat.bat"), $runChat)

Push-Location $InstallDir
try {
    & $py ytmd doctor | Out-Null
    if ($LASTEXITCODE -ne 0) { & $py ytmd doctor | Out-Host; Fail "The caption reader (ytmd) is not ready. See the lines above." }

    if (-not $Unattended) {
        Step "4. Settings (in your browser)"
        Write-Host "The settings page is opening in your browser. Paste your keys there, test them, click Save, then Finish."
        Write-Host "(If no page opens, copy the address below into your browser.)"
        & $py app.py --setup
        if ($LASTEXITCODE -ne 0) { Fail "The settings page stopped. Run install.bat again." }
    }

    Step "5. Daily schedule"
    & $py app.py --schedule | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "No settings were saved, or the schedule could not be set. Run install.bat again (without -Unattended) and click Save on the page." }

    if (-not $Unattended) {
        Step "6. Market Digest on the desktop"
        $desktop = [Environment]::GetFolderPath("Desktop")
        Remove-Item (Join-Path $desktop "Digest chat.lnk") -ErrorAction SilentlyContinue   # replaced by Market Digest, which has the chat too
        $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop "Market Digest.lnk"))
        $lnk.TargetPath = Join-Path $InstallDir "run_app.bat"
        $lnk.WorkingDirectory = $InstallDir
        $lnk.Save()
        Write-Host "Added 'Market Digest' to the desktop: it shows whether the digest ran, your settings, and the chat."
    }
} finally { Pop-Location }

Write-Host ""
Write-Host "Done. You can close this window." -ForegroundColor Green
Write-Host "To check on the digest, change a setting or chat about the videos: double-click 'Market Digest' on the desktop."
Write-Host "Program folder: $InstallDir (run install.bat again to update; your settings are kept)."
