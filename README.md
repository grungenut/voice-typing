# Voice Typing

Hold **Right Alt**, talk, let go, and the words are typed wherever your cursor is. Tap
**Right Ctrl** to record a meeting and get a transcript with speaker labels.

Everything runs on your own PC or Mac. No account, no subscription, no API key, and no audio
ever leaves the machine.

- **Dictation** works in any program: email, Word, a browser, a chat box, a terminal.
  Punctuation and capitalization come out right.
- **Meeting mode** records your microphone *and* whatever the computer is playing, so people
  on a Zoom, Teams or Meet call are included. The transcript opens when you stop, with
  `[00:12:40] Speaker 2: …` lines, and the audio file is kept next to it.

Speech recognition is OpenAI's open-source [Whisper](https://github.com/openai/whisper)
model. Speaker labeling uses [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) with the
pyannote segmentation model and a 3D-Speaker embedding model.

## Install on Windows (the easy way)

1. Download **`VoiceTyping-Setup-<version>.exe`** from the
   [Releases](../../releases) page (about 180 MB).
2. Run it. Windows may show a blue "Windows protected your PC" box because the installer is
   not signed with a paid certificate; click **More info → Run anyway**. No admin password
   is needed; it installs for your user only.
3. Tick "Start Voice Typing when I sign in" if you want it always on. Finish.
4. The first start downloads the speech model (about 140 MB) once. A small gray pill near
   the bottom of the screen shows progress; a green "ready" pill means it is working.

A microphone icon appears in the notification area (bottom right, by the clock; it may be
under the **^** "hidden icons" arrow). Click it to **transcribe a file**, open **settings**,
your **transcripts folder**, the **log**, or **Quit**. Uninstall from
Windows Settings → Apps like any other program.

Requirements: Windows 10 or 11 (64-bit), a microphone, about 1 GB of disk space.

## Install on a Mac

1. Click the green **Code** button → **Download ZIP**, unzip it.
2. In the `mac` folder, right-click **`Install.command`** → **Open** → **Open** (macOS blocks a
   plain double-click on downloaded scripts). It needs Python 3.10–3.13: if none is installed it
   says so and points to [python.org](https://www.python.org/downloads/macos/). It then installs
   the libraries and models (about 600 MB) and makes **Voice Typing** in your Applications folder.
3. Open Voice Typing. Allow the **Microphone** when asked, then switch on Voice Typing (it may
   appear as "Python") under **System Settings → Privacy & Security → Accessibility**. That is
   what lets it see the hotkeys and paste.
4. Hold **Right Option** and talk; tap **Right Command** to record a meeting. The small "Voice
   Typing" pill at the bottom right of the screen is the menu (settings, transcribe a file, quit).

Mac notes: it runs on the processor (no NVIDIA), so the compact English model is used. Meeting
mode records the microphone only, since macOS has no built-in way to capture call audio; put the
call on speaker. MP3, M4A, MP4 and MOV files transcribe out of the box; for MKV, WebM or Opus,
install FFmpeg (`brew install ffmpeg`). `Uninstall.command` removes everything. The Mac version
is new and has had less testing than the Windows one.

## Install from source on Windows (for NVIDIA graphics cards)

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
text is pasted a moment later. Taps shorter than a third of a second are ignored. Prefer not to
hold the key? Set *Dictation key works as* to **toggle** in Settings: tap to start, tap to stop.

**Record a meeting:** tap Right Ctrl (rising two-tone beep; purple "Recording 00:00" pill with
a running clock). Tap it again to stop (falling beep). The transcript is written to
`Documents\Meeting Transcripts\` and opens in Notepad when ready; its header names the
recording's location. Labeling speakers takes about two to three minutes per hour of audio.
While recording, a `.live.txt` file in the same folder is updated every 30 seconds, so nothing
is lost if the PC crashes mid-meeting.

**The window:** click the tray icon (on a Mac, the small "Voice Typing" pill) to open it.
**Recordings** lists every meeting with its date, length, speakers and summary, with search
across titles, summaries and the words spoken; open the transcript, play the recording, show
it in its folder, or summarize it. **Transcribe a file** turns an existing recording or video
into a transcript. **Summaries** installs the optional local summary model. The settings and
About pages are there too. Closing the window leaves Voice Typing running in the tray.

Right Alt and Right Ctrl are reserved for Voice Typing while it runs (programs never see
them). Left Alt and Left Ctrl work as usual. On a Mac the keys are Right Option and Right Command.

## Transcribing an existing recording or video

Tray icon → **Transcribe a file...** and pick an MP3, M4A, WAV, MP4, MOV, MKV, WebM or most
other audio or video files (several at once is fine). The transcript, with speaker labels and
time stamps, is written next to the file as `<name> transcript.txt` and opens when ready. A
one-hour recording takes a few minutes with an NVIDIA card, longer on the CPU. You can also
drag files onto `Voice Typing.exe` (or run `voice_typing.py <file>`): that copy transcribes
them and exits.

Anything other than WAV is decoded by [FFmpeg](https://ffmpeg.org) (LGPL build). The
installer includes it; the source install downloads it once (about 75 MB) when first needed.

## Summaries (optional, on your computer)

The Summaries page of the window can download a small language model (Qwen3 4B, Apache 2.0,
about 2.5 GB with the llama.cpp program that runs it). From then on each new meeting or
transcribed file gets a title and a summary written into the top of its transcript: what it
was about, the key points, and any action items. Older recordings can be summarized from the
Recordings page. Everything runs on your computer; the transcript is never sent anywhere.
Expect a minute or a few per meeting on a computer without an NVIDIA card. The installer
offers the download as an option; it can also be removed from the Summaries page.

**Note styles.** What gets written is a *template*, chosen on the Summaries page (for new
recordings) or beside the Write button on the Recordings page (for any recording). Built in:

- **Meeting summary** - what it was about, key points, action items, written into the top of
  the transcript. The default.
- **SOAP note** - Subjective, Objective, Assessment, Plan from a recorded clinical visit,
  written as its own file beside the transcript, with medication names and doses, vitals and
  dates kept exactly as spoken and "not discussed" where something was not said.
- **Narrative** - a chronological account of the encounter in plain prose, as its own file.

Every note is a draft for the person who recorded it to review. The **Note templates** page
edits these or makes new ones: a name, a description, where the note goes, and the
instructions to the model (the sections you want, in what order, and what to do when
something was not said). Your templates are kept in your own folder; a built-in one you edit
can be restored.

**Recording patients or clients.** Get consent before recording, keep the transcripts folder
on an encrypted drive (BitLocker or FileVault), and treat every note as a draft until a
clinician has reviewed and signed it.

## Settings

Tray icon → **Settings...** (or the window's sidebar) shows every setting, grouped into
Dictation, Meetings and Files. Click the **?** in the corner, then rest the pointer on any
setting to see what it does and its options. **Save and restart** applies them. The same settings live in `settings.ini` in `%LOCALAPPDATA%\VoiceTyping` if you
prefer a text editor. New versions add their new settings automatically.

| Setting | Default | What it does |
|---|---|---|
| `hotkey` | `right alt` | The hold-to-talk key (any single key: `right shift`, `caps lock`, `scroll lock`, `pause`, `f8`, …) |
| `meeting_hotkey` | `right ctrl` | The tap-to-record key |
| `dictation_mode` | `hold` | `hold` = hold the key while talking; `toggle` = tap to start, tap again to stop |
| `meeting_hold_seconds` | `0` | Hold the meeting key this long to start or stop, so a stray tap does nothing (`0` = tap) |
| `meeting_type_location` | `no` | Type the recording's file location where the cursor is: `no`, `start`, `stop`, `both`. The transcript names it anyway |
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
| `summaries` | `no` | Title and summary for each new transcript, by the local summary model (window → Summaries) |
| `summary_template` | `Meeting summary` | Which note template the summary step uses: `Meeting summary`, `SOAP note`, `Narrative`, or your own |
| `file_transcript_dir` | blank | Where transcripts of existing files go; blank = next to the file |

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

Audio and transcripts are processed by models running on your PC and are never uploaded -
that includes the optional summaries. Meeting recordings and transcripts are ordinary files in
your Documents folder; delete them whenever you like. Setup downloads the speech model from
OpenAI's public servers once; the source install also downloads libraries from PyPI and the
speaker models from GitHub. The summary model (Hugging Face) and llama.cpp (GitHub) are
downloaded only if you ask for them on the Summaries page.

## Building the installer yourself

`powershell -ExecutionPolicy Bypass -File build\build_exe.ps1` makes `dist\VoiceTyping-Setup-<version>.exe`.
It needs Python 3.10+ and [Inno Setup 6](https://jrsoftware.org/isdl.php). The script creates a
CPU-only build environment, regenerates `THIRD-PARTY-NOTICES.md`, runs PyInstaller, then Inno Setup.

## License

Voice Typing is MIT-licensed (see `LICENSE`). It is built from open-source components; their
licenses are listed with full text in `THIRD-PARTY-NOTICES.md`, which is also installed with
the program (Start menu → Third-party notices). Whisper is MIT; sherpa-onnx and the
3D-Speaker model are Apache 2.0; the pyannote segmentation model is MIT; PyTorch is BSD-style.
FFmpeg is LGPL 2.1 and is shipped as a separate program, unmodified, with its source
available from the build's project page. Nothing is under the GPL.
