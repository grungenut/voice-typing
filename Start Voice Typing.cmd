@echo off
rem Starts Voice Typing with no console window. Double-click to run.
rem Stop it with "Stop Voice Typing.cmd" (or end pythonw.exe in Task Manager).
set "PYW=%LOCALAPPDATA%\VoiceTyping\.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo Voice Typing is not set up on this PC yet. Double-click Install.cmd first.
    pause
    exit /b 1
)
start "" "%PYW%" "%~dp0voice_typing.py"
