@echo off
rem Starts Voice Typing with no console window. Double-click to run.
rem Stop it with "Stop Voice Typing.cmd" (or end pythonw.exe in Task Manager).
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Voice Typing is not set up yet. Double-click Install.cmd first.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0voice_typing.py"
