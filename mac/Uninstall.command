#!/bin/bash
# Removes Voice Typing from this Mac: the app, its private Python environment, models,
# settings and log. Meeting transcripts in ~/Documents are not touched.
# The Whisper model cache (~/.cache/whisper) is removed too; delete this line's section to keep it.

APP="$HOME/Applications/Voice Typing.app"
SUPPORT="$HOME/Library/Application Support/VoiceTyping"

pkill -f "VoiceTyping/app/voice_typing.py" 2>/dev/null
osascript -e 'tell application "System Events" to delete login item "Voice Typing"' >/dev/null 2>&1
rm -rf "$APP" "$SUPPORT" "$HOME/.cache/whisper"
echo "Voice Typing has been removed. Your transcripts in ~/Documents are untouched."
read -r -p "Press Return to close this window. "
