# Voice Typing

Hold **Right Alt**, talk, let go, and the words are typed wherever your cursor is. Tap
**Right Ctrl** to record a meeting and get a transcript with speaker labels.

Everything runs on your own Windows PC. No account, no subscription, no API key, and no audio
ever leaves the machine.

- **Dictation** works in any program: email, Word, a browser, a chat box, a terminal.
  Punctuation and capitalization come out right.
- **Meeting mode** records your microphone *and* whatever the computer is playing, so people
  on a Zoom, Teams or Meet call are included. The transcript opens when you stop, with
  `[00:12:40] Speaker 2: …` lines, and the audio file is kept next to it.

Speech recognition is OpenAI's open-source [Whisper](https://github.com/openai/whisper)
model. Speaker labeling uses [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) with the
pyannote segmentation model and a 3D-Speaker embedding model.

## Install (the easy way)

1. Download **`VoiceTyping-Setup-<version>.exe`** from the
   [Releases](../../releases) page (about 180 MB).
2. Run it. Windows may show a blue "Windows protected your PC" box because the installer is
   not signed with a paid certificate; click **More info → Run anyway**. No admin password
   is needed; it installs for your user only.
3. Tick "Start Voice Typing when I sign in" if you want it always on. Finish.
4. The first start downloads the speech model (about 140 MB) once. A small gray pill near
   the bottom of the screen shows progress; a green "ready" pill means it is working.

A microphone icon appears in the notification area (bottom right, by the clock). Click it
for **settings**, your **transcripts folder**, the **log**, and **Quit**. Uninstall from
Windows Settings → Apps like any other program.

Requirements: Windows 10 or 11 (64-bit), a microphone, about 1 GB of disk space.

## Install from source (for NVIDIA graphics cards)

The installer above runs on the CPU with a compact English model, which is accurate and fast
enough for most people. If your PC has an NVIDIA card, the source version uses the large
`turbo` model on the GPU instead: more accurate, any language, and nearly instant.

1. Click the green **Code** button → **Download ZIP** and unzip it somewhere permanent, or
   `git clone` it.
2. Double-click **`Install.cmd`**. It installs Python if needed, the GPU or CPU build of
   PyTorch, the libraries and the models (about 5 GB with an NVIDIA card). Rerun it any time.
3. Double-click **`Start Voice Typing.cmd`**. `Add to Startup.cmd` makes it start at sign-in;
   `Remove from Startup.cmd` undoes that; `Stop Voice Typing.cmd` stops it.

## Using it

**Dictate:** put the cursor where you want text, hold Right Alt, speak, let go. A short beep
and a red "Listening…" pill show while the key is down; a lower beep when you release. The
text is pasted a moment later. Taps shorter than a third of a second are ignored.

**Record a meeting:** tap Right Ctrl (rising two-tone beep; purple "Recording 00:00" pill with
a running clock). Tap it again to stop (falling beep). The transcript is written to
`Documents\Meeting Transcripts\` and opens in Notepad when ready. When you stop, the file's
location is typed where your cursor is, so your notes say where the recording went (see
settings to change or turn that off). Labeling speakers takes
about two to three minutes per hour of audio. While recording, a `.live.txt` file in the same
folder is updated every 30 seconds, so nothing is lost if the PC crashes mid-meeting.

Right Alt and Right Ctrl are reserved for Voice Typing while it runs (programs never see
them). Left Alt and Left Ctrl work as usual.

## Settings

Tray icon → **Open settings** opens `settings.ini` in Notepad (it lives in
`%LOCALAPPDATA%\VoiceTyping`). Every line is explained in the file. Quit and start Voice
Typing again after saving. New versions add their new settings to your file automatically.

| Setting | Default | What it does |
|---|---|---|
| `hotkey` | `right alt` | The hold-to-talk key (any single key: `right shift`, `caps lock`, `scroll lock`, `pause`, `f8`, …) |
| `meeting_hotkey` | `right ctrl` | The tap-to-record key |
| `meeting_hold_seconds` | `0` | Hold the meeting key this long to start or stop, so a stray tap does nothing (`0` = tap) |
| `meeting_paste_path` | `stop` | Type the recording's file location where the cursor is: `start`, `stop`, `both`, `no` |
| `meeting_open` | `transcript` | When done, open the `transcript`, the `folder` with the audio selected, `both`, or `no` |
| `language` | `en` | Language spoken, or `auto` (needs the GPU model) |
| `gpu_model` / `cpu_model` | `turbo` / `base.en` | Whisper model with / without an NVIDIA card |
| `beeps`, `show_overlay` | `yes` | The beeps and the on-screen pill |
| `trailing_space` | `yes` | Add a space after dictated text |
| `meeting_dir` | `Documents\Meeting Transcripts` | Where meeting transcripts (and audio) go. Any folder, even a network share |
| `meeting_audio_dir` | blank | Put the WAV files in a different folder; blank keeps them beside the transcripts |
| `meeting_subfolders` | `no` | `yes` = each meeting gets its own folder holding its transcript and audio |
| `meeting_speakers` | `0` | `0` = detect the number of speakers, or force it (`2`, `3`, …) |
| `meeting_chunk_seconds` | `30` | How often the live transcript file is updated |
| `meeting_threads` | `8` | CPU threads for speaker labeling |

## Recording other people

Meeting mode records everyone in the room and everyone on the call. In many places the law
requires you to tell participants a conversation is being recorded, and some places (for
example several US states, and much of Europe) require everyone's consent. Say it at the
start of the meeting. You are responsible for following the law where you and the other
participants are. Voice Typing does not announce itself to the other side of a call.

## Good to know

- Speaker labels are "Speaker 1, 2, 3…", numbered by who talks first. Two people talking
  at once, very similar voices, or a one-word interjection can land on the wrong speaker.
- Meeting audio captures what Windows sends to the **default** playback device. If you use
  headphones that aren't the default device, callers won't be recorded; set them as default.
- Dictation pastes through the clipboard and then restores the text that was there. If the
  clipboard held an image or a file, that is replaced by the dictated text.
- Programs running as administrator don't accept the paste unless Voice Typing also runs as
  administrator.
- Whisper does not take spoken commands such as "new line" or "period".
- Problems? Tray icon → **View log**.

## Privacy

Audio is processed by models running on your PC and is never uploaded. Meeting recordings
and transcripts are ordinary files in your Documents folder; delete them whenever you like.
Setup downloads the speech model from OpenAI's public servers once; the source install also
downloads libraries from PyPI and the speaker models from GitHub.

## Building the installer yourself

`powershell -ExecutionPolicy Bypass -File build\build_exe.ps1` makes `dist\VoiceTyping-Setup-<version>.exe`.
It needs Python 3.10+ and [Inno Setup 6](https://jrsoftware.org/isdl.php). The script creates a
CPU-only build environment, regenerates `THIRD-PARTY-NOTICES.md`, runs PyInstaller, then Inno Setup.

## License

Voice Typing is MIT-licensed (see `LICENSE`). It is built from open-source components; their
licenses are listed with full text in `THIRD-PARTY-NOTICES.md`, which is also installed with
the program (Start menu → Third-party notices). Whisper is MIT; sherpa-onnx and the
3D-Speaker model are Apache 2.0; the pyannote segmentation model is MIT; PyTorch is BSD-style.
Nothing in the program is under a copyleft license.
