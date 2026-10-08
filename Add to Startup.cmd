@echo off
rem Makes Voice Typing start every time you sign in to Windows (puts a shortcut in your
rem Startup folder). Undo with "Remove from Startup.cmd".
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Startup'), 'Voice Typing.lnk')); $s.TargetPath = '%~dp0Start Voice Typing.cmd'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Description = 'Voice Typing - hold Right Alt to dictate, tap Right Ctrl to record a meeting'; $s.Save(); Write-Host 'Voice Typing will now start when you sign in.'"
pause
