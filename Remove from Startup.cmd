@echo off
rem Stops Voice Typing from starting when you sign in (removes the Startup shortcut).
powershell -NoProfile -Command "$p = [IO.Path]::Combine([Environment]::GetFolderPath('Startup'), 'Voice Typing.lnk'); if (Test-Path $p) { Remove-Item $p; Write-Host 'Removed. Voice Typing will no longer start when you sign in.' } else { Write-Host 'It was not in Startup.' }"
pause
