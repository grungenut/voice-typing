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

Settings are in the SETTINGS block just below. Run with pythonw.exe for no console window
(see "Start Voice Typing.cmd" next to this file).
"""

import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winsound

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd

from meeting import MeetingSession

# ----------------------------------------------------------------------------- SETTINGS --
HOTKEY = "right alt"       # hold to talk
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
MEETING_HOTKEY = "right ctrl"
MEETING_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Meeting Transcripts")
MEETING_SPEAKERS = 0       # 0 = work out how many speakers; or force a number (2, 3, ...)
MEETING_CHUNK_SECONDS = 30 # how often the live transcript file is updated while recording
MEETING_THREADS = 8        # CPU threads for speaker labeling at the end
# ------------------------------------------------------------------------------------------

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_typing.log")


def models_dir() -> str:
    """Speaker models: where install.ps1 puts them (local app data), else a models\\ folder here."""
    local = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VoiceTyping", "models")
    beside = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    return local if os.path.isdir(local) else beside


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

    # ---- model -------------------------------------------------------------------------
    def load_model(self):
        import torch
        import whisper

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        name = GPU_MODEL if self.device == "cuda" else CPU_MODEL
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
    def on_press(self, event):
        if self.recording:              # Windows auto-repeats a held key; ignore repeats
            return
        self.recording = True
        self.pressed_at = time.time()
        try:
            self.recorder.start()
        except Exception as e:
            self.recording = False
            log.error("could not open microphone: %s", e)
            self.ui.put(("Microphone error", "#7f8c8d", 2000))
            return
        if BEEPS:
            threading.Thread(target=winsound.Beep, args=(880, 70), daemon=True).start()
        self.ui.put(("●  Listening...", "#c0392b", None))

    def on_release(self, event):
        if not self.recording:
            return
        self.recording = False
        audio = self.recorder.stop()
        held = time.time() - self.pressed_at
        if BEEPS:
            threading.Thread(target=winsound.Beep, args=(660, 70), daemon=True).start()
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
        if self.meeting is None or self.meeting.state == "done":
            try:
                self.meeting = MeetingSession(
                    self.model, self.model_lock, self.device, MEETING_DIR, models_dir(),
                    self.ui, speakers=MEETING_SPEAKERS, chunk_seconds=MEETING_CHUNK_SECONDS,
                    threads=MEETING_THREADS, language=LANGUAGE)
                self.meeting.start()
            except Exception:
                log.exception("could not start meeting recording")
                self.meeting = None
                self.ui.put(("Meeting recording failed to start - see log", "#7f8c8d", 4000))
                return
            if BEEPS:
                threading.Thread(target=lambda: (winsound.Beep(880, 70), winsound.Beep(1100, 90)), daemon=True).start()
        elif self.meeting.state == "recording":
            self.meeting.stop()
            if BEEPS:
                threading.Thread(target=lambda: (winsound.Beep(1100, 70), winsound.Beep(660, 90)), daemon=True).start()
        # else: still finalizing the last one - ignore the tap

    def on_meeting_release(self, event):
        self.meeting_key_down = False

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
        keyboard.send("ctrl+v")
        time.sleep(0.25)                    # let the app read the clipboard before we restore it
        if previous:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

    # ---- main --------------------------------------------------------------------------
    def run(self):
        root = tk.Tk()
        root.withdraw()
        overlay = Overlay(root) if SHOW_OVERLAY else None

        def pump():
            try:
                while True:
                    msg = self.ui.get_nowait()
                    if overlay is None:
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
            threading.Thread(target=self.worker, daemon=True).start()
            keyboard.on_press_key(HOTKEY, self.on_press, suppress=True)
            keyboard.on_release_key(HOTKEY, self.on_release, suppress=True)
            keyboard.on_press_key(MEETING_HOTKEY, self.on_meeting_press, suppress=True)
            keyboard.on_release_key(MEETING_HOTKEY, self.on_meeting_release, suppress=True)
            log.info("ready - hold %s to talk, tap %s for a meeting", HOTKEY, MEETING_HOTKEY)
            self.ui.put(("Voice Typing ready - hold Right Alt to talk, tap Right Ctrl for a meeting", "#27ae60", 3000))

        threading.Thread(target=startup, daemon=True).start()
        root.after(40, pump)
        root.mainloop()


if __name__ == "__main__":
    VoiceTyping().run()
