@echo off
rem Builds market-digest-setup.zip to send to someone else. It never includes your settings, keys or saved data.
cd /d "%~dp0"
powershell -NoProfile -Command "Compress-Archive -Force -Path install.bat,install.ps1,digest.py,digest_export.py,digest_schema.json,tickers.json,chat.py,chat.html,ytmd,README.md,USER_GUIDE.md,TROUBLESHOOTING.md,digest_config.example.json -DestinationPath market-digest-setup.zip"
echo Made %~dp0market-digest-setup.zip
pause
