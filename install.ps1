# Sets up the market video digest on this Windows computer. Started by install.bat.
# Safe to run again: it updates the program files and keeps the settings, saved videos and chats.
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE "market-digest"),
    [string]$TaskName = "Market video digest",
    [switch]$Unattended   # keep the existing settings, ask nothing, no desktop shortcut or test digest
)
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$files = "digest.py", "digest_export.py", "digest_schema.json", "tickers.json", "chat.py", "chat.html", "ytmd", "README.md", "digest_config.example.json"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }
function Ask($question, $default) {
    $answer = Read-Host "$question [$default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}
function AskSecret($question, $minLength) {
    while ($true) {
        $secure = Read-Host "$question (paste with RIGHT-click; Ctrl+V does not work here)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if ($value -match "[\x00-\x1F]") { Write-Host "That included a Ctrl key instead of the text. Right-click to paste, then press Enter." -ForegroundColor Yellow; continue }
        if ($value.Length -lt $minLength) { Write-Host "That is too short to be right ($($value.Length) characters). Try again." -ForegroundColor Yellow; continue }
        return $value
    }
}
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
$runDigest = "@echo off`r`nrem Runs the daily digest and keeps a log next to this file.`r`ncd /d `"%~dp0`"`r`nset `"PATH=%~dp0bin;%PATH%`"`r`n`"$py`" digest.py >> digest.log 2>&1`r`n"
$runChat = "@echo off`r`nrem Starts the chat page. Keep this window open while you use it.`r`ncd /d `"%~dp0`"`r`nset `"PATH=%~dp0bin;%PATH%`"`r`n`"$py`" chat.py`r`npause`r`n"
[IO.File]::WriteAllText((Join-Path $InstallDir "run_digest.bat"), $runDigest)
[IO.File]::WriteAllText((Join-Path $InstallDir "run_chat.bat"), $runChat)

Push-Location $InstallDir
try {
    & $py ytmd doctor | Out-Null
    if ($LASTEXITCODE -ne 0) { & $py ytmd doctor | Out-Host; Fail "The caption reader (ytmd) is not ready. See the lines above." }

    Step "4. Settings"
    $config = Join-Path $InstallDir "digest_config.json"
    $time = "07:30"
    $write = -not (Test-Path $config)
    if (-not $write -and -not $Unattended) { $write = (Ask "Settings already exist. Enter them again?" "n") -match "^y" }
    if (-not $write -and -not (Test-Path $config)) { Fail "No settings. Run install.bat without -Unattended." }
    if ($write) {
        Write-Host "Your answers are saved only on this computer, in $config"
        Write-Host "Typed keys and passwords are hidden as you type or paste them."
        $key = AskSecret "Gemini API key (from https://aistudio.google.com/apikey)" 30
        $channels = Ask "YouTube channels to follow, separated by commas" "https://www.youtube.com/@TheStreet"
        $to = Ask "Email address that should receive the digest (blank = no email, just save it)" ""
        $user = ""; $pass = ""
        if ($to) {
            $user = Ask "Gmail address that sends it" $to
            Write-Host "Gmail needs an app password: Google Account > Security > 2-Step Verification > App passwords."
            $pass = (AskSecret "Gmail app password (16 letters)" 16) -replace "\s", ""
        }
        Write-Host "Each digest is also saved as a JSON file for the Econova hub. To share it, give a Google Drive for desktop folder,"
        Write-Host "for example G:\My Drive\Econova\Video Digests\json"
        $jsonDir = Ask "Folder for the daily JSON file (blank = digest_json in the program folder)" ""
        $settings = [ordered]@{
            channels = @($channels -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            gemini_api_key = $key
            models = @("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
            lookback_hours = 26
            max_videos = 20
            email_to = @($to -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            smtp_user = $user
            smtp_password = $pass
            smtp_host = "smtp.gmail.com"
            smtp_port = 465
            json_dir = $jsonDir
        }
        [IO.File]::WriteAllText($config, ($settings | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
        Write-Host "Saved."
    }
    if (-not $Unattended) {
        do { $time = Ask "Time to make the digest each day (24-hour, HH:MM)" "07:30" } while ($time -notmatch "^([01]\d|2[0-3]):[0-5]\d$")
    }

    Step "5. Testing channels, Gemini key and email"
    & $py digest.py --check | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "A test failed (see FAILED above). Fix it by running install.bat again and re-entering the settings." }

    Step "6. Daily schedule"
    $action = New-ScheduledTaskAction -Execute (Join-Path $InstallDir "run_digest.bat") -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    # StartWhenAvailable: if the computer was off at that time, run as soon as it is back on.
    # Restart: a failed run (no internet yet, email down) is tried again every 30 minutes, 3 times.
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $taskSettings -Description "Emails the market video digest. Installed by install.bat." -Force | Out-Null
    Write-Host "Scheduled '$TaskName' every day at $time (while you are logged in; a missed time runs when the computer is next on)."

    if (-not $Unattended) {
        Step "7. Desktop shortcut for the chat page"
        $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Digest chat.lnk"))
        $lnk.TargetPath = Join-Path $InstallDir "run_chat.bat"
        $lnk.WorkingDirectory = $InstallDir
        $lnk.Save()
        Write-Host "Added 'Digest chat' to the desktop."

        if ((Ask "Make a test digest of the last 3 days now? It opens in the browser and is not emailed (y/n)" "y") -match "^y") {
            & $py digest.py --hours 72 --dry-run --open | Out-Host
        }
    }
} finally { Pop-Location }

Write-Host ""
Write-Host "Done. The digest arrives by email every day at $time." -ForegroundColor Green
Write-Host "Chat about the videos: double-click 'Digest chat' on the desktop."
Write-Host "Program folder: $InstallDir (run install.bat again to change settings or update)."
