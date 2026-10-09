#!/bin/bash
# Voice Typing - macOS installer. Double-click it in Finder.
# (The first time, macOS may refuse because it was downloaded: right-click > Open > Open.)
#
# What it does
#   1. Finds Python 3.10 or newer (installs it with Homebrew if Homebrew is present).
#   2. Creates a private Python environment in ~/Library/Application Support/VoiceTyping/.venv
#   3. Installs PyTorch (CPU), Whisper, the audio libraries and the macOS hotkey libraries.
#   4. Downloads the two speaker-labeling models (33 MB) and the Whisper base.en model (140 MB).
#   5. Copies the program into ~/Library/Application Support/VoiceTyping/app and makes
#      ~/Applications/Voice Typing.app to start it (double-click, or add to Login Items).
#
# Safe to run again: it only redoes what is missing. Uninstall with Uninstall.command.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"                      # the Project folder
SUPPORT="$HOME/Library/Application Support/VoiceTyping"
VENV="$SUPPORT/.venv"
APPDIR="$SUPPORT/app"
APP="$HOME/Applications/Voice Typing.app"

say()  { printf '\n==> %s\n' "$1"; }
fail() { printf '\n!! %s\n\n' "$1"; read -r -p "Press Return to close this window. "; exit 1; }

mkdir -p "$SUPPORT" "$HOME/Applications"

# --- 1. Python --------------------------------------------------------------------------
say "Looking for Python 3.10 or newer"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
    p="$(command -v "$c" 2>/dev/null || true)"
    [ -z "$p" ] && continue
    # /usr/bin/python3 is only a stub until the Xcode command line tools are installed
    if [ "$p" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
    if "$p" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then
        PY="$p"; break
    fi
done
if [ -z "$PY" ]; then
    if command -v brew >/dev/null 2>&1; then
        say "No suitable Python found - installing Python 3.12 with Homebrew"
        brew install python@3.12 || fail "Homebrew could not install Python."
        PY="$(brew --prefix python@3.12)/bin/python3.12"
    else
        fail "Python 3.10 to 3.13 is needed. Install it from https://www.python.org/downloads/macos/ (the macOS 64-bit universal2 installer), then double-click Install.command again."
    fi
fi
echo "   Using $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"
if ! "$PY" -c 'import tkinter' 2>/dev/null; then
    fail "This Python has no tkinter (needed for the on-screen pill and settings window). Install Python from python.org, which includes it."
fi

# --- 2. Virtual environment -------------------------------------------------------------
if [ ! -x "$VENV/bin/python3" ]; then
    say "Creating a private Python environment in $VENV"
    "$PY" -m venv "$VENV" || fail "Could not create the Python environment."
else
    say "Private Python environment already exists"
fi
VPY="$VENV/bin/python3"
"$VPY" -m pip install --quiet --upgrade pip

# --- 3. Libraries -----------------------------------------------------------------------
say "Installing PyTorch (CPU build, about 200 MB)"
"$VPY" -m pip install --quiet torch || fail "PyTorch did not install."
say "Installing the speech, audio and hotkey libraries"
"$VPY" -m pip install --quiet -r "$SRC/requirements-mac.txt" || fail "The libraries did not install."

# --- 4. Models --------------------------------------------------------------------------
MODELS="$SUPPORT/models"
mkdir -p "$MODELS"
SEG="$MODELS/pyannote-segmentation-3-0.onnx"
EMB="$MODELS/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx"
if [ ! -f "$SEG" ]; then
    say "Downloading the speaker segmentation model (7 MB)"
    TMP="$(mktemp -d)"
    curl -sSL -o "$TMP/seg.tar.bz2" "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" || fail "Download failed."
    tar -xjf "$TMP/seg.tar.bz2" -C "$TMP"
    cp "$TMP/sherpa-onnx-pyannote-segmentation-3-0/model.onnx" "$SEG"
    cp "$TMP/sherpa-onnx-pyannote-segmentation-3-0/LICENSE" "$MODELS/pyannote-segmentation-3-0.LICENSE" 2>/dev/null || true
    rm -rf "$TMP"
fi
if [ ! -f "$EMB" ]; then
    say "Downloading the speaker embedding model (26 MB)"
    curl -sSL -o "$EMB" "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx" || fail "Download failed."
fi
say "Downloading the Whisper speech model (base.en, 140 MB) so the first start is quick"
"$VPY" -c "import whisper; whisper.load_model('base.en'); print('   Whisper model ready')" || fail "The speech model did not download."

# --- 5. Program files and the app -------------------------------------------------------
say "Installing the program into $APPDIR"
mkdir -p "$APPDIR/assets"
cp "$SRC"/*.py "$APPDIR/"
cp "$SRC"/assets/* "$APPDIR/assets/" 2>/dev/null || true
cp "$SRC/LICENSE" "$SRC/README.md" "$APPDIR/" 2>/dev/null || true

say "Making $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/Voice Typing" <<EOF
#!/bin/bash
exec "$VPY" "$APPDIR/voice_typing.py" "\$@"
EOF
chmod +x "$APP/Contents/MacOS/Voice Typing"
if [ -f "$SRC/assets/voice_typing_1024.png" ]; then
    sips -s format icns "$SRC/assets/voice_typing_1024.png" --out "$APP/Contents/Resources/voice_typing.icns" >/dev/null 2>&1 || true
fi
cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>Voice Typing</string>
    <key>CFBundleDisplayName</key>       <string>Voice Typing</string>
    <key>CFBundleIdentifier</key>        <string>com.jamesbeadle.voicetyping</string>
    <key>CFBundleVersion</key>           <string>1.2.0</string>
    <key>CFBundleShortVersionString</key><string>1.2.0</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleExecutable</key>        <string>Voice Typing</string>
    <key>CFBundleIconFile</key>          <string>voice_typing</string>
    <key>LSMinimumSystemVersion</key>    <string>12.0</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>Voice Typing records your voice to turn it into text. Nothing leaves this Mac.</string>
    <key>NSHighResolutionCapable</key>   <true/>
</dict>
</plist>
EOF
touch "$APP"

# --- 6. Login item (optional) -----------------------------------------------------------
echo
read -r -p "Start Voice Typing automatically when you log in? [y/N] " ans
if [[ "$ans" =~ ^[Yy] ]]; then
    osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP\", hidden:false}" >/dev/null 2>&1 \
        && echo "   Added to Login Items." || echo "   Could not add the login item (System Settings > General > Login Items does it too)."
fi

cat <<EOF

==> Done. Voice Typing is in ~/Applications. Opening it now.

   First-run permissions (macOS asks once each):
     - Microphone: click Allow.
     - Accessibility: System Settings > Privacy & Security > Accessibility - switch on
       "Voice Typing" (it may be listed as "Python"). Needed to see the hotkeys and to paste.
   Then: hold RIGHT OPTION and talk; tap RIGHT COMMAND to record a meeting.
   Settings: click the small "Voice Typing" pill at the bottom right of the screen.

EOF
open "$APP"
read -r -p "Press Return to close this window. "
