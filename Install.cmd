@echo off
rem One-time setup. Double-click this. It takes a few minutes (it downloads about 3 GB on a
rem PC with an NVIDIA card, about 500 MB without). Safe to run again.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
if errorlevel 1 (echo Setup did not finish - see the messages above.) else (echo Setup finished.)
pause
