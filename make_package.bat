@echo off
rem Builds market-digest-setup.zip to send to someone else. It never includes your settings, keys or saved data:
rem it holds only the installers, the guides and the program files listed in MANIFEST.
cd /d "%~dp0"
powershell -NoProfile -Command "$files = @('install.bat','install.ps1','install-mac.command','USER_GUIDE.md','TROUBLESHOOTING.md','watchlist_template.csv','price_sheet.py') + @(Get-Content MANIFEST | ForEach-Object { $_.Trim() } | Where-Object { $_ }); Compress-Archive -Force -Path $files -DestinationPath market-digest-setup.zip"
echo Made %~dp0market-digest-setup.zip
pause
