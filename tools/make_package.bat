@echo off
rem Builds market-digest-setup.zip, the file customers download. Run it from anywhere: it works on the project folder.
rem It holds the installers, the guides and the program files listed in app\MANIFEST, copied into a clean folder first,
rem so your own settings, keys and saved data can never end up in it.
cd /d "%~dp0.."
powershell -NoProfile -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$stage = Join-Path $env:TEMP ('market-digest-' + [guid]::NewGuid()); New-Item -ItemType Directory -Path (Join-Path $stage 'app') | Out-Null;" ^
  "foreach ($f in 'install.bat','install.ps1','install-mac.command','docs\USER_GUIDE.md','docs\TROUBLESHOOTING.md') { Copy-Item $f $stage }" ^
  "foreach ($f in (Get-Content app\MANIFEST | ForEach-Object { $_.Trim() } | Where-Object { $_ })) { Copy-Item (Join-Path 'app' $f) (Join-Path $stage 'app') }" ^
  "Compress-Archive -Force -Path (Join-Path $stage '*') -DestinationPath market-digest-setup.zip; Remove-Item -Recurse -Force $stage"
echo Made %cd%\market-digest-setup.zip
pause
