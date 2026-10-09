"""
Voice Typing - hold Right Alt, talk, let go, and the words are typed where the cursor is.

Modeled on Warp's voice input. Everything runs on this computer: audio never leaves the
machine. Speech recognition is OpenAI's Whisper (open-source model), run locally through
PyTorch on the GPU when one is available.

How it works
  1. A low-level keyboard hook watches for Right Alt. The key is swallowed so that apps never
     see a bare Alt press (which would otherwise jump focus to their menu bar).
  2. While the key is down, the microphone is recorded at 16 kHz mono.
  3. On release, the audio goes to Whisper. The text comes back punctuated and capitalized.
  4. The text is put on the clipboard and pasted with Ctrl+V into whatever has focus, then
     the previous clipboard text is restored.

Settings are in settings.ini (tray icon > Settings...). Run with pythonw.exe for no console
window (see "Start Voice Typing.cmd" next to this file). On macOS see mac/Install.command;
the platform differences live in sysglue.py and mac_hotkeys.py.
"""

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

# As a windowed exe (or under pythonw) there is no console: stdout/stderr are None, and
# libraries that print progress bars (Whisper's model download uses tqdm) crash on them.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import numpy as np
import pyperclip
import sounddevice as sd

import sysglue
from meeting import MeetingSession
from transcribe_file import MEDIA_TYPES, FileTranscription, ensure_ffmpeg
from settings_window import SettingsWindow
if sysglue.IS_WIN:
    from tray import Tray

# ----------------------------------------------------------------------------- SETTINGS --
HOTKEY = sysglue.DEFAULT_HOTKEY            # hold to talk (right alt; right option on a Mac)
DICTATION_MODE = "hold"    # hold = hold the key while talking; toggle = tap to start, tap again to stop
LANGUAGE = "en"            # None = auto-detect (slower, and the .en models can't)
GPU_MODEL = "turbo"        # used when a CUDA GPU is found: large-v3-turbo, best accuracy, ~1.6 GB download
CPU_MODEL = "base.en"      # used when there is no GPU: small and quick enough on a CPU
MIN_SECONDS = 0.35         # taps shorter than this are ignored
BEEPS = True               # short tone on start and on stop
SHOW_OVERLAY = True        # little "Listening..." pill at the bottom of the screen
TRAILING_SPACE = True      # add a space after the text so the next dictation doesn't run into it
SAMPLE_RATE = 16000        # Whisper's native rate; do not change

# Meeting mode: tap the key once to start a long recording, tap again to stop. The transcript
# (with speaker labels) and the audio land in MEETING_DIR and the transcript opens when done.
MEETING_HOTKEY = sysglue.DEFAULT_MEETING_HOTKEY   # right ctrl; right command on a Mac
MEETING_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Meeting Transcripts")
MEETING_AUDIO_DIR = ""     # where the WAV files go; "" = next to the transcripts
MEETING_SUBFOLDERS = False # True = each meeting gets its own folder holding its transcript and audio
MEETING_SPEAKERS = 0       # 0 = work out how many speakers; or force a number (2, 3, ...)
MEETING_CHUNK_SECONDS = 30 # how often the live transcript file is updated while recording
MEETING_THREADS = 8        # CPU threads for speaker labeling at the end
FILE_TRANSCRIPT_DIR = ""   # where transcripts of existing files go; "" = next to the file
MEETING_HOLD_SECONDS = 0   # hold the meeting key this long to start/stop a recording (0 = a tap does it)
MEETING_PASTE_PATH = "stop"  # paste the recording's file location where the cursor is: start, stop, both, no
MEETING_OPEN = "transcript"  # when the transcript is ready, open: transcript, folder (audio selected), both, no
# ------------------------------------------------------------------------------------------

__version__ = "1.2.1"

# Where things live. As a script, the log sits beside the script; as an exe (PyInstaller), the
# program folder may not be writable, so everything the app writes goes to local app data.
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)        # bundled read-only files (models, icon)
DATA_DIR = sysglue.data_dir()           # %LOCALAPPDATA%\VoiceTyping, or ~/Library/Application Support/VoiceTyping
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.ini")
LOG_PATH = os.path.join(DATA_DIR if FROZEN else APP_DIR, "voice_typing.log")

SETTINGS_TEMPLATE = """; Voice Typing settings. Lines starting with ; are comments.
; Restart Voice Typing after editing (tray icon > Quit, then start it again).

[voice typing]
; The hold-to-talk key for dictation, and the tap-to-record key for meetings. One key each.
; Key names you can use: @KEY_NAMES@.
; Whatever key you pick stops working for everything else while Voice Typing runs.
hotkey = @HOTKEY@
meeting_hotkey = @MEETING_HOTKEY@

; How the dictation key works: hold = hold it down while you talk and let go to type;
; toggle = tap once to start listening, tap again to stop and type.
dictation_mode = hold

; Hold the meeting key this many seconds to start (and to stop) a recording, so a stray tap
; does nothing. A countdown shows while you hold. 0 = a quick tap starts and stops.
meeting_hold_seconds = 0

; Type the recording's file location where the cursor is, so your notes say where it went:
;   start = when the recording starts, stop = when you stop it, both, or no.
meeting_paste_path = stop

; When the transcript is ready, open: transcript (in Notepad), folder (the file folder with the
; audio selected), both, or no.
meeting_open = transcript

; Language spoken: en, es, fr, de, ... or auto. (auto needs an NVIDIA card; the CPU model is English-only.)
language = en

; Speech model with an NVIDIA card / without one. Bigger = more accurate but slower.
;   with a card:  turbo (best), small.en, base.en
;   without one:  base.en (default), small.en (better, slower), tiny.en (fastest)
gpu_model = turbo
cpu_model = base.en

; Beeps and the little on-screen pill: yes or no.
beeps = yes
show_overlay = yes

; Add a space after dictated text so the next dictation does not run into it.
trailing_space = yes

; Where meeting transcripts (and, unless changed below, the audio) go. Any folder you like.
meeting_dir = @MEETING_DIR@

; Put the audio (WAV) files in a different folder. Leave blank to keep them next to the transcripts.
meeting_audio_dir =

; yes = each meeting gets its own folder (named after the meeting) holding its transcript and audio.
meeting_subfolders = no

; Speakers in a meeting: 0 = work it out automatically, or a number to force it (2, 3, ...).
meeting_speakers = 0

; How often (seconds) the live transcript file is updated during a meeting.
meeting_chunk_seconds = 30

; CPU threads used for speaker labeling at the end of a meeting.
meeting_threads = 8

; Where transcripts of existing recordings (tray icon > Transcribe a file) go.
; Leave blank to put each transcript next to its file.
file_transcript_dir =
""".replace("@KEY_NAMES@", sysglue.KEY_NAME_HELP).replace("@HOTKEY@", sysglue.DEFAULT_HOTKEY) \
   .replace("@MEETING_HOTKEY@", sysglue.DEFAULT_MEETING_HOTKEY) \
   .replace("@MEETING_DIR@", "%USERPROFILE%\\Documents\\Meeting Transcripts" if sysglue.IS_WIN
            else "~/Documents/Meeting Transcripts")


def add_new_settings():
    """Append settings from the template that an older settings.ini does not have yet."""
    try:
        with open(SETTINGS_PATH, encoding="utf-8-sig") as f:
            existing = f.read()
        have = {ln.split("=", 1)[0].strip().lower() for ln in existing.splitlines()
                if "=" in ln and not ln.lstrip().startswith(";")}
        blocks, block = [], []
        for ln in SETTINGS_TEMPLATE.splitlines():
            if ln.startswith("["):
                block = []
                continue
            block.append(ln)
            if "=" in ln and not ln.lstrip().startswith(";"):
                key = ln.split("=", 1)[0].strip().lower()
                if key not in have:
                    blocks.append("\n".join(block).strip("\n"))
                block = []
            elif not ln.strip():
                block = []
        if blocks:
            with open(SETTINGS_PATH, "a", encoding="utf-8") as f:
                f.write(("" if existing.endswith("\n") else "\n") + "\n" + "\n\n".join(blocks) + "\n")
            log.info("settings.ini: added %d new setting(s)", len(blocks))
    except Exception:
        log.exception("could not update settings.ini with new settings")


def load_settings():
    """Read settings.ini (creating it with defaults the first time) over the constants above."""
    import configparser

    if not os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            f.write(SETTINGS_TEMPLATE)
    else:
        add_new_settings()
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(SETTINGS_PATH, encoding="utf-8-sig")
    except Exception:
        log.exception("settings.ini could not be read - using defaults")
        return
    if not cp.has_section("voice typing"):
        return
    g = globals()
    for key, raw in cp.items("voice typing"):
        name = key.upper()
        if name not in g:
            log.warning("settings.ini: unknown setting %r ignored", key)
            continue
        default, raw = g[name], raw.strip()
        try:
            if name == "LANGUAGE":
                value = None if raw.lower() in ("", "auto", "none") else raw
            elif isinstance(default, bool):
                value = raw.lower() in ("1", "yes", "true", "on")
            elif isinstance(default, int):
                value = int(raw)
            else:
                value = os.path.expanduser(os.path.expandvars(raw))
        except ValueError:
            log.warning("settings.ini: bad value for %s (%r) - using default %r", key, raw, default)
            continue
        g[name] = value


def models_dir() -> str:
    """Speaker models: bundled in the exe, else where install.ps1 put them, else beside the script."""
    for d in (os.path.join(BUNDLE_DIR, "models"), os.path.join(DATA_DIR, "models"), os.path.join(APP_DIR, "models")):
        if os.path.isdir(d):
            return d
    return os.path.join(APP_DIR, "models")


def icon_path():
    for d in (BUNDLE_DIR, APP_DIR):
        p = os.path.join(d, "assets", "voice_typing.ico")
        if os.path.exists(p):
            return p
    return None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("voice_typing")


class Recorder:
    """Collects microphone audio between start() and stop()."""

    def __init__(self):
        self._chunks = []
        self._stream = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning("audio status: %s", status)
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self):
        with self._lock:
            self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=self._callback, blocksize=1024
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")


class Overlay:
    """A small always-on-top label near the bottom of the screen. Must live on the Tk thread."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.92)
        self.label = tk.Label(
            self.win, text="", font=("Segoe UI", 12, "bold"), fg="white", bg="#c0392b", padx=18, pady=8
        )
        self.label.pack()
        self.win.withdraw()
        self._hide_job = None

    def show(self, text, color, hide_after_ms=None):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self.label.config(text=text, bg=color)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 90}")
        self.win.deiconify()
        if hide_after_ms:
            self._hide_job = self.root.after(hide_after_ms, self.hide)

    def hide(self):
        self._hide_job = None
        self.win.withdraw()


class PillMenu:
    """macOS stand-in for the tray icon: a tiny always-on-top pill in the bottom-right corner
    that opens the same menu when clicked."""

    def __init__(self, root: tk.Tk, items):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.85)
        label = tk.Label(self.win, text="Voice Typing", font=("Helvetica", 10, "bold"), fg="white",
                         bg="#5b2c8f", padx=10, pady=4, cursor="hand2")
        label.pack()
        self.menu = tk.Menu(self.win, tearoff=0)
        for item in items:
            if item is None:
                self.menu.add_separator()
            else:
                self.menu.add_command(label=item[0], command=item[1])
        label.bind("<Button-1>", self.popup)
        label.bind("<Button-2>", self.popup)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{sw - w - 16}+{sh - h - 60}")

    def popup(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root - 10)
        finally:
            self.menu.grab_release()


class VoiceTyping:
    def __init__(self):
        self.recorder = Recorder()
        self.recording = False
        self.pressed_at = 0.0
        self.jobs = queue.Queue()           # audio arrays waiting to be transcribed
        self.ui = queue.Queue()             # (text, color, hide_ms) messages for the overlay, or None = hide
        self.model = None
        self.model_lock = threading.Lock()  # dictation and meeting chunks share one GPU model
        self.device = "cpu"
        self.meeting = None                 # the running MeetingSession, if any
        self.meeting_key_down = False
        self.hotkey_down = False            # dictation key physically down (toggle mode ignores auto-repeat)
        self.hotkey_names = self.meeting_hotkey_names = set()   # set in run() after settings load
        self.meeting_press_id = 0           # bumps on each meeting-key press (hold mode)
        self.files = []                     # files to transcribe when started from the command line
        self.restart_requested = False      # settings saved: start a fresh copy after quitting
        self.file_queue = queue.Queue()     # files picked from the tray menu
        self.key_events = queue.Queue()     # hotkey events, handled off the hook thread (see key_hook)

    # ---- model -------------------------------------------------------------------------
    def load_model(self):
        import torch
        import whisper

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        name = GPU_MODEL if self.device == "cuda" else CPU_MODEL
        cache = os.path.join(os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "whisper", name + ".pt")
        if not os.path.exists(cache):
            self.ui.put((f"Downloading the speech model ({name}) - one time only...", "#7f8c8d", None))
        log.info("loading Whisper model %r on %s ...", name, self.device)
        t0 = time.time()
        self.model = whisper.load_model(name, device=self.device)
        log.info("model ready in %.1fs", time.time() - t0)
        # Warm up so the first real dictation isn't slow.
        self.transcribe(np.zeros(SAMPLE_RATE, dtype="float32"))
        log.info("warm-up done")

    def transcribe(self, audio: np.ndarray) -> str:
        with self.model_lock:
            result = self.model.transcribe(
                audio,
                language=LANGUAGE,
                fp16=(self.device == "cuda"),
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
            )
        # Drop segments Whisper itself thinks are silence (it tends to hallucinate "Thank you." there).
        parts = [s["text"] for s in result["segments"] if s.get("no_speech_prob", 0) < 0.6]
        return " ".join(p.strip() for p in parts).strip()

    # ---- hotkey ------------------------------------------------------------------------
    @staticmethod
    def key_names(setting: str) -> set:
        """Event names that mean this key (Windows calls the left modifiers plain alt / ctrl / shift)."""
        return sysglue.key_name_variants(setting)

    def key_hook(self, event):
        """Runs inside the OS keyboard hook for every key event. Returns False to swallow the
        event (only our two keys). It must return within a fraction of a second: Windows drops
        a hook that is slow and passes the key on to the app, which then sees the Alt go down
        but never come up (keyboard "stuck", Ctrl+V turns into Alt+Ctrl+V). So nothing slow
        happens here - the event is handed to key_worker and dealt with there."""
        try:
            if event.name in self.hotkey_names:
                self.key_events.put(("dictation", event))
                return False
            if event.name in self.meeting_hotkey_names:
                self.key_events.put(("meeting", event))
                return False
        except Exception:
            log.exception("key hook failed")
        return True

    def key_worker(self):
        """Handles hotkey events one after another, in the order they arrived."""
        while True:
            kind, event = self.key_events.get()
            try:
                if kind == "dictation":
                    if DICTATION_MODE.lower() == "toggle":
                        if event.down:
                            if not self.hotkey_down:            # first down event of this tap, not a repeat
                                (self.on_release if self.recording else self.on_press)(event)
                            self.hotkey_down = True
                        else:
                            self.hotkey_down = False
                    else:
                        (self.on_press if event.down else self.on_release)(event)
                else:
                    (self.on_meeting_press if event.down else self.on_meeting_release)(event)
            except Exception:
                log.exception("hotkey handling failed")

    def on_press(self, event):
        if self.recording:              # Windows auto-repeats a held key; ignore repeats
            return
        self.recording = True
        self.pressed_at = time.time()
        try:
            self.recorder.start()
            opened = time.time() - self.pressed_at
            if opened > 0.3:
                log.info("microphone took %.2fs to open", opened)
        except Exception as e:
            self.recording = False
            log.error("could not open microphone: %s", e)
            self.ui.put(("Microphone error", "#7f8c8d", 2000))
            return
        if BEEPS:
            threading.Thread(target=sysglue.beep, args=(880, 70), daemon=True).start()
        self.ui.put(("●  Listening..." + ("  (tap again to stop)" if DICTATION_MODE.lower() == "toggle" else ""),
                     "#c0392b", None))

    def on_release(self, event):
        if not self.recording:
            return
        self.recording = False
        audio = self.recorder.stop()
        held = time.time() - self.pressed_at
        if BEEPS:
            threading.Thread(target=sysglue.beep, args=(660, 70), daemon=True).start()
        if held < MIN_SECONDS or len(audio) < SAMPLE_RATE * MIN_SECONDS:
            self.ui.put(None)
            return
        self.ui.put(("...  Typing", "#2980b9", None))
        self.jobs.put(audio)

    # ---- meeting mode (tap to start, tap to stop) --------------------------------------
    def on_meeting_press(self, event):
        if self.meeting_key_down:           # auto-repeat while held
            return
        self.meeting_key_down = True
        if MEETING_HOLD_SECONDS <= 0:
            self.toggle_meeting()
            return
        # Hold mode: count down on screen; fire only if the key is still down at the end.
        self.meeting_press_id += 1
        press_id = self.meeting_press_id
        starting = self.meeting is None or self.meeting.state != "recording"
        verb = "start" if starting else "stop"

        def countdown():
            end = time.time() + MEETING_HOLD_SECONDS
            while True:
                left = end - time.time()
                if press_id != self.meeting_press_id or not self.meeting_key_down:
                    self.ui.put(None)
                    return
                if left <= 0:
                    break
                self.ui.put((f"Keep holding to {verb} recording... {int(left) + 1}", "#8e44ad", None))
                time.sleep(min(0.1, left))
            self.toggle_meeting()

        threading.Thread(target=countdown, daemon=True).start()

    def paste_meeting_path(self, when: str):
        if self.meeting is None or MEETING_PASTE_PATH.lower() not in (when, "both"):
            return
        path = self.meeting.final_path
        log.info("pasting the recording location (%s)", when)
        # In a thread: the hook callback must not block, and the key may still be held.
        threading.Thread(target=lambda: (time.sleep(0.3), self.type_text(f"Meeting recording: {path} ")),
                         daemon=True).start()

    def toggle_meeting(self):
        if self.meeting is None or self.meeting.state == "done":
            try:
                self.meeting = MeetingSession(
                    self.model, self.model_lock, self.device, MEETING_DIR, models_dir(),
                    self.ui, speakers=MEETING_SPEAKERS, chunk_seconds=MEETING_CHUNK_SECONDS,
                    threads=MEETING_THREADS, language=LANGUAGE, open_mode=MEETING_OPEN.lower(),
                    audio_dir=MEETING_AUDIO_DIR.strip() or None, subfolders=MEETING_SUBFOLDERS)
                self.meeting.start()
            except Exception:
                log.exception("could not start meeting recording")
                self.meeting = None
                self.ui.put(("Meeting recording failed to start - see log", "#7f8c8d", 4000))
                return
            if BEEPS:
                threading.Thread(target=lambda: (sysglue.beep(880, 70), sysglue.beep(1100, 90)), daemon=True).start()
            self.paste_meeting_path("start")
        elif self.meeting.state == "recording":
            self.paste_meeting_path("stop")
            self.meeting.stop()
            if BEEPS:
                threading.Thread(target=lambda: (sysglue.beep(1100, 70), sysglue.beep(660, 90)), daemon=True).start()
        # else: still finalizing the last one - ignore the tap

    def on_meeting_release(self, event):
        self.meeting_key_down = False

    # ---- transcribe existing files -----------------------------------------------------
    def pick_files(self, root):
        """Runs on the tk thread (from pump): file dialog, then queue the files."""
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(parent=root, title="Transcribe a recording or video",
                                            filetypes=MEDIA_TYPES)
        for p in paths:
            self.file_queue.put(p)

    def transcribe_file(self, path):
        ffmpeg = lambda: ensure_ffmpeg(BUNDLE_DIR, DATA_DIR, lambda text: self.ui.put((text, "#2980b9", None)))
        job = FileTranscription(path, self.model, self.model_lock, self.device, models_dir(), self.ui, ffmpeg,
                                out_dir=FILE_TRANSCRIPT_DIR.strip() or None, speakers=MEETING_SPEAKERS,
                                threads=MEETING_THREADS, language=LANGUAGE, open_mode=MEETING_OPEN.lower())
        job.run()

    def file_worker(self):
        """Transcribes files picked from the tray menu, one after another."""
        while True:
            path = self.file_queue.get()
            if path is None:
                return
            try:
                self.transcribe_file(path)
            except Exception:
                log.exception("file transcription failed: %s", path)

    # ---- worker ------------------------------------------------------------------------
    def worker(self):
        while True:
            audio = self.jobs.get()
            try:
                rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
                if rms < 0.003:
                    log.info("skipped: %.1fs of near-silence (rms %.4f)", len(audio) / SAMPLE_RATE, rms)
                    self.ui.put(None)
                    continue
                t0 = time.time()
                text = self.transcribe(audio)
                log.info("%.1fs audio -> %.2fs transcribe: %r", len(audio) / SAMPLE_RATE, time.time() - t0, text)
                if text:
                    self.type_text(text + (" " if TRAILING_SPACE else ""))
                    self.ui.put(("✓", "#27ae60", 500))
                else:
                    self.ui.put(None)
            except Exception:
                log.exception("transcription failed")
                self.ui.put(("Error - see log", "#7f8c8d", 2500))

    @staticmethod
    def type_text(text: str):
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        time.sleep(0.05)
        sysglue.send_paste()
        time.sleep(0.25)                    # let the app read the clipboard before we restore it
        if previous:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    # ---- main --------------------------------------------------------------------------
    def run(self):
        load_settings()
        self.hotkey_names = self.key_names(HOTKEY)
        self.meeting_hotkey_names = self.key_names(MEETING_HOTKEY)
        if self.hotkey_names & self.meeting_hotkey_names:
            log.warning("hotkey and meeting_hotkey are the same key (%s) - meeting mode disabled", HOTKEY)
            self.meeting_hotkey_names = set()
        self.files = [a for a in sys.argv[1:] if os.path.isfile(a)]
        log.info("Voice Typing %s starting (%s); settings: %s%s", __version__, "exe" if FROZEN else "script",
                 SETTINGS_PATH, f"; {len(self.files)} file(s) to transcribe" if self.files else "")
        root = tk.Tk()
        root.withdraw()
        overlay = Overlay(root) if SHOW_OVERLAY else None
        quitting = {"on": False}

        def open_transcripts():
            os.makedirs(MEETING_DIR, exist_ok=True)
            sysglue.open_path(MEETING_DIR)

        menu_items = [
            ("Transcribe a file...", lambda: self.ui.put("pick_file")),
            ("Settings...", lambda: self.ui.put("settings")),
            ("Open transcripts folder", open_transcripts),
            ("View log", lambda: sysglue.open_path(LOG_PATH)),
            None,
            ("Quit Voice Typing", lambda: self.ui.put("quit")),
        ]
        tray = None
        if not self.files:                  # a command-line run just does its files and exits
            if sysglue.IS_WIN:
                tray = Tray(f"Voice Typing {__version__} - hold {HOTKEY} to dictate, tap {MEETING_HOTKEY} for a meeting",
                            icon_path(), menu_items)
                tray.start()
            else:
                PillMenu(root, menu_items)  # macOS: a small always-visible pill with the same menu

        def shutdown():
            # A meeting in progress is stopped and allowed to finish writing its transcript first.
            if self.meeting is not None and self.meeting.state == "recording":
                self.meeting.stop()
            if self.meeting is not None and self.meeting.state == "finalizing":
                root.after(250, shutdown)
                return
            log.info("quit")
            try:
                sysglue.remove_hooks()
            except Exception:
                pass
            if tray is not None:
                tray.stop()
            root.quit()

        def pump():
            try:
                while True:
                    msg = self.ui.get_nowait()
                    if msg == "pick_file":
                        self.pick_files(root)
                        continue
                    if msg == "settings":
                        SettingsWindow(root, SETTINGS_PATH, SETTINGS_TEMPLATE, lambda: self.ui.put("restart"),
                                       icon_path(), __version__)
                        continue
                    if msg == "restart":
                        self.restart_requested = True
                        msg = "quit"
                    if msg == "quit":
                        if not quitting["on"]:
                            quitting["on"] = True
                            if overlay:
                                overlay.show("Closing Voice Typing...", "#7f8c8d", None)
                            shutdown()
                        continue
                    if overlay is None or quitting["on"]:
                        continue
                    if msg is None:
                        overlay.hide()
                    else:
                        overlay.show(*msg)
            except queue.Empty:
                pass
            root.after(40, pump)

        def startup():
            self.ui.put(("Loading speech model...", "#7f8c8d", None))
            try:
                self.load_model()
            except Exception:
                log.exception("model failed to load")
                self.ui.put(("Speech model failed to load - see log", "#7f8c8d", 6000))
                return
            if self.files:
                for path in self.files:
                    try:
                        self.transcribe_file(path)
                    except Exception:
                        log.exception("file transcription failed: %s", path)
                self.ui.put("quit")
                return
            threading.Thread(target=self.worker, daemon=True).start()
            threading.Thread(target=self.file_worker, daemon=True).start()
            threading.Thread(target=self.key_worker, daemon=True).start()
            # One global hook, matched by key *name*. (On Windows, keyboard.on_press_key() matches
            # by scan code, and Left and Right Alt share one, so it fired - and swallowed - both.)
            # On macOS the hook needs the Accessibility permission; ask, then keep trying.
            if not sysglue.install_hook(self.key_hook):
                sysglue.accessibility_prompt()
                log.warning("hotkeys unavailable - waiting for the Accessibility permission")
                while not sysglue.install_hook(self.key_hook):
                    self.ui.put(("Allow Voice Typing (or Python) under System Settings > Privacy & Security > "
                                 "Accessibility, then wait a moment", "#7f8c8d", None))
                    time.sleep(3)
            verb = "tap" if DICTATION_MODE.lower() == "toggle" else "hold"
            log.info("ready - %s %s to talk, tap %s for a meeting", verb, HOTKEY, MEETING_HOTKEY)
            self.ui.put((f"Voice Typing ready - {verb} {HOTKEY.title()} to talk, tap {MEETING_HOTKEY.title()} for a meeting",
                         "#27ae60", 3000))

        threading.Thread(target=startup, daemon=True).start()
        root.after(40, pump)
        root.mainloop()
        if self.restart_requested:
            log.info("restarting to apply settings")
            args = [sys.executable] if FROZEN else [sys.executable, os.path.abspath(__file__)]
            subprocess.Popen(args, close_fds=True, cwd=APP_DIR)


if __name__ == "__main__":
    VoiceTyping().run()
