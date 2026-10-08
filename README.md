# Voice Typing

Hold **Right Alt**, talk, let go, and the words are typed wherever your cursor is. Tap
**Right Ctrl** to record a meeting and get a transcript with speaker labels.

Everything runs on your own Windows PC. No account, no subscription, no API key, and no audio
ever leaves the machine.

- **Dictation** works in any program: email, Word, a browser, a chat box, a terminal.
  Punctuation and capitalization come out right. On a PC with an NVIDIA card it is nearly
  instant; without one there is a short pause after you let go of the key.
- **Meeting mode** records your microphone *and* whatever the computer is playing, so people
  on a Zoom, Teams or Meet call are included. The transcript opens when you stop, with
  `[00:12:40] Speaker 2: …` lines, and the audio file is kept next to it.

Speech recognition is OpenAI's open-source [Whisper](https://github.com/openai/whisper)
model. Speaker labeling uses [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) with the
pyannote segmentation model and a 3D-Speaker embedding model.

## Requirements

- Windows 10 or 11, 64-bit, and a microphone.
- About 4 GB of free disk space (most of it is PyTorch and the speech model).
- An NVIDIA graphics card is **optional**. With one, the large, most accurate model is used
  and dictation is instant. Without one, a smaller English-only model runs on the CPU.
- Internet access during setup only.

## Install

1. Click the green **Code** button on GitHub → **Download ZIP**, and unzip it somewhere
   permanent (for example `C:\Users\<you>\Voice Typing`). Or `git clone` it.
2. Double-click **`Install.cmd`**. It installs Python if you don't have it (no admin
   needed), downloads the libraries and models, and takes a few minutes. Run it again any
   time; it only redoes what is missing.
3. Double-click **`Start Voice Typing.cmd`**. A small gray "Loading speech model…" pill
   appears near the bottom of the screen, then a green "ready" pill. That's it.
4. Optional: double-click **`Add to Startup.cmd`** so it starts every time you sign in.
   `Remove from Startup.cmd` undoes that. `Stop Voice Typing.cmd` stops it.

The first start after setup can take 20 seconds or so; later starts are faster.

Setup puts the Python environment and the speaker models in `%LOCALAPPDATA%\VoiceTyping`
(about 3–5 GB) and the Whisper model in `%USERPROFILE%\.cache\whisper`, so the unzipped
folder itself stays small and can live anywhere, even on a network drive or a USB stick.
To uninstall, delete those two folders and the unzipped folder, and run
`Remove from Startup.cmd` if you had added it.

## Using it

**Dictate:** put the cursor where you want text, hold Right Alt, speak, let go. A short beep
and a red "Listening…" pill show while the key is down; a lower beep when you release. The
text is pasted a moment later. Taps shorter than a third of a second are ignored.

**Record a meeting:** tap Right Ctrl (rising two-tone beep; purple "Recording 00:00" pill with
a running clock). Tap it again to stop (falling beep). The transcript is written to
`Documents\Meeting Transcripts\` and opens in Notepad when it is ready. Labeling speakers
takes about two to three minutes per hour of audio. While recording, a `.live.txt` file in the
same folder is updated every 30 seconds, so nothing is lost if the PC crashes mid-meeting.

Right Alt and Right Ctrl are reserved for Voice Typing while it runs (programs never see
them). Left Alt and Left Ctrl work as usual.

## Settings

Open `voice_typing.py` in Notepad; the `SETTINGS` block at the top is plain English:

| Setting | Default | What it does |
|---|---|---|
| `HOTKEY` | `right alt` | The hold-to-talk key |
| `MEETING_HOTKEY` | `right ctrl` | The tap-to-record key |
| `LANGUAGE` | `en` | Language spoken (`None` = detect, needs the GPU model) |
| `GPU_MODEL` / `CPU_MODEL` | `turbo` / `base.en` | Whisper model used with / without an NVIDIA card |
| `BEEPS`, `SHOW_OVERLAY` | `True` | The beeps and the on-screen pill |
| `TRAILING_SPACE` | `True` | Add a space after dictated text |
| `MEETING_DIR` | `Documents\Meeting Transcripts` | Where meeting files go |
| `MEETING_SPEAKERS` | `0` | `0` = detect the number of speakers; or force it (`2`, `3`, …) |
| `MEETING_THREADS` | `8` | CPU threads for speaker labeling |

Restart Voice Typing after changing a setting.

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
- Problems? Look at `voice_typing.log` next to the script.

## Privacy

Audio is processed by models running on your PC and is never uploaded. Meeting recordings
and transcripts are ordinary files in your Documents folder; delete them whenever you like.
Setup downloads the models from GitHub and PyPI once.

## License

MIT (see `LICENSE`). Whisper is MIT; sherpa-onnx is Apache 2.0; the pyannote segmentation
model is MIT; the 3D-Speaker embedding model is Apache 2.0.
