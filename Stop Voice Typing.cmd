@echo off
rem Stops every running copy of Voice Typing.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*voice_typing.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
