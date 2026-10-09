"""
File transcription for Voice Typing: an existing audio or video file -> a transcript with
speaker labels, written the same way meeting mode writes one.

Used by voice_typing.py (tray menu "Transcribe a file..." or files given on the command line).

  - The file is decoded to 16 kHz mono: WAV with the standard library, everything else (MP3,
    M4A, MP4, MOV, MKV, WebM, ...) by running FFmpeg as a separate program. FFmpeg is the
    LGPL build from https://github.com/BtbN/FFmpeg-Builds (no GPL components); it is bundled
    with the installer, or downloaded once (about 75 MB) into %LOCALAPPDATA%\\VoiceTyping\\ffmpeg
    the first time a non-WAV file is transcribed from a source install.
  - The audio is transcribed in ~5-minute pieces cut at quiet points, so dictation keeps
    working in between and a ".live.txt" grows as it goes.
  - Then speaker labeling and the final "[hh:mm:ss] Speaker N:" transcript, exactly as for a
    meeting, next to the source file (or in file_transcript_dir from settings).
"""

import datetime
import logging
import os
import shutil
import subprocess
import time
import wave
import zipfile

import numpy as np

import sysglue
from meeting import SR, MeetingSession, _hms, _ms, _resample

log = logging.getLogger("voice_typing.file")

MEDIA_TYPES = [
    ("Audio and video files",
     "*.mp3 *.m4a *.wav *.mp4 *.mov *.mkv *.avi *.webm *.ogg *.opus *.flac *.aac *.wma *.wmv *.m4v *.3gp *.aiff *.mts *.m4b"),
    ("All files", "*.*"),
]
PIECE_SECONDS = 5 * 60
FFMPEG_ZIP_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                  "ffmpeg-n8.1-latest-win64-lgpl-shared-8.1.zip")


# ---- FFmpeg ------------------------------------------------------------------------------
def find_ffmpeg(bundle_dir: str, data_dir: str):
    """ffmpeg: bundled with the exe, downloaded into app data, on the PATH, or (macOS) from Homebrew."""
    exe = "ffmpeg.exe" if sysglue.IS_WIN else "ffmpeg"
    for d in (os.path.join(bundle_dir, "ffmpeg"), os.path.join(data_dir, "ffmpeg")):
        p = os.path.join(d, exe)
        if os.path.exists(p):
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.exists(p):
            return p
    return None


def download_ffmpeg(dest_dir: str, progress=lambda text: None) -> str:
    """Fetch the LGPL FFmpeg build and keep only bin\\ (ffmpeg.exe + DLLs) and its LICENSE."""
    import urllib.request
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "ffmpeg.zip")
    log.info("downloading FFmpeg from %s", FFMPEG_ZIP_URL)

    def hook(blocks, block_size, total):
        if total > 0:
            progress(f"Downloading the media decoder (FFmpeg)... {blocks * block_size * 100 // total}%")

    urllib.request.urlretrieve(FFMPEG_ZIP_URL, zip_path, hook)
    progress("Unpacking the media decoder...")
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            parts = member.split("/")
            if len(parts) >= 3 and parts[1] == "bin" and parts[-1] and parts[-1] not in ("ffplay.exe", "ffprobe.exe"):
                with z.open(member) as src, open(os.path.join(dest_dir, parts[-1]), "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif len(parts) == 2 and parts[1].upper().startswith("LICENSE"):
                with z.open(member) as src, open(os.path.join(dest_dir, parts[1]), "wb") as dst:
                    shutil.copyfileobj(src, dst)
    os.remove(zip_path)
    exe = os.path.join(dest_dir, "ffmpeg.exe")
    if not os.path.exists(exe):
        raise RuntimeError("FFmpeg download did not contain ffmpeg.exe")
    log.info("FFmpeg installed in %s", dest_dir)
    return exe


def ensure_ffmpeg(bundle_dir: str, data_dir: str, progress=lambda text: None):
    """Windows: find or download FFmpeg. macOS: find it if installed, else None (afconvert is used)."""
    found = find_ffmpeg(bundle_dir, data_dir)
    if found or not sysglue.IS_WIN:
        return found
    return download_ffmpeg(os.path.join(data_dir, "ffmpeg"), progress)


# ---- decoding ----------------------------------------------------------------------------
def decode_wav(path: str) -> np.ndarray:
    with wave.open(path) as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, np.int32).astype(np.float32) / 2147483648.0
    elif sw == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError("unusual WAV sample width")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return _resample(x, sr, SR)


def decode_audio(path: str, ffmpeg) -> np.ndarray:
    """Any audio or video file -> float32 mono at 16 kHz. `ffmpeg` is a path or a callable
    returning one (so the download only happens when it is really needed)."""
    if path.lower().endswith(".wav"):
        try:
            return decode_wav(path)
        except Exception as e:                   # float WAV, odd header: let FFmpeg have a go
            log.info("wave module could not read %s (%s); using FFmpeg", os.path.basename(path), e)
    exe = ffmpeg() if callable(ffmpeg) else ffmpeg
    if exe is None and sysglue.IS_MAC:
        return decode_with_afconvert(path)
    if exe is None:
        raise ValueError("FFmpeg is not available to decode this file")
    cmd = [exe, "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, **sysglue.NO_WINDOW)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ValueError(err[-1] if err else f"FFmpeg exited with code {r.returncode}")
    if len(r.stdout) < 2:
        raise ValueError("this file has no audio")
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0


def decode_with_afconvert(path: str) -> np.ndarray:
    """macOS without FFmpeg: the system's own converter handles MP3, M4A/AAC, MP4/MOV audio,
    AIFF, CAF and more (not MKV, WebM or Opus - install FFmpeg with Homebrew for those)."""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = ["afconvert", "-f", "WAVE", "-d", f"LEI16@{SR}", "-c", "1", path, tmp]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines()
            raise ValueError((err[-1] if err else "afconvert failed") +
                             " - for this file type install FFmpeg: brew install ffmpeg")
        return decode_wav(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    n, candidate = 2, path
    while os.path.exists(candidate):
        candidate = f"{base} ({n}){ext}"
        n += 1
    return candidate


# ---- the job -----------------------------------------------------------------------------
class FileTranscription(MeetingSession):
    """Reuses MeetingSession's chunk transcription, speaker labeling and transcript writer."""

    def __init__(self, source, model, model_lock, device, models_dir, ui, ffmpeg, out_dir=None,
                 speakers=0, threads=8, language="en", open_mode="transcript"):
        # MeetingSession.__init__ is deliberately not called: it sets up live capture.
        self.model, self.model_lock, self.device = model, model_lock, device
        self.models_dir, self.ui, self.ffmpeg = models_dir, ui, ffmpeg
        self.speakers, self.threads, self.language, self.open_mode = speakers, threads, language, open_mode
        self.source = os.path.abspath(source)
        self.started = datetime.datetime.now()
        name = os.path.splitext(os.path.basename(self.source))[0]
        folder = out_dir or os.path.dirname(self.source)
        os.makedirs(folder, exist_ok=True)
        self.final_path = _unique(os.path.join(folder, f"{name} transcript.txt"))
        self.live_path = self.final_path[:-4] + ".live.txt"
        self.wav_path = self.source                    # named on the transcript's "Audio:" line
        self.title = f"Transcript of {os.path.basename(self.source)}"
        self.words = []
        self._pending, self._pending_len, self._pending_offset = [], 0, 0
        self.state = "transcribing"

    def run(self):
        """Blocking; run it in a thread."""
        short = os.path.basename(self.source)
        try:
            self.ui.put((f"Reading {short}...", "#2980b9", None))
            t0 = time.time()
            audio = decode_audio(self.source, self.ffmpeg)
            length = len(audio) / SR
            log.info("file %s: %s of audio decoded in %.1fs", short, _hms(length), time.time() - t0)
            if length < 0.5:
                raise ValueError("the file holds less than half a second of audio")
            with open(self.live_path, "w", encoding="utf-8") as f:
                f.write(f"{self.title} - in progress (no speaker labels yet)\n\n")

            piece = PIECE_SECONDS * SR
            pos = 0
            while pos < len(audio):
                chunk = audio[pos:pos + piece]
                pos += len(chunk)
                self._pending.append(chunk)
                self._pending_len += len(chunk)
                self.ui.put((f"Transcribing {short}... {_ms(pos / SR)} of {_ms(length)}", "#2980b9", None))
                self._transcribe_pending(final=pos >= len(audio))

            self.ui.put((f"Labeling speakers in {short}...", "#8e44ad", None))
            turns = None
            try:
                turns = self._diarize(audio)
            except Exception:
                log.exception("speaker labeling failed - writing transcript without labels")
            self._write_final(length, turns)
            try:
                os.remove(self.live_path)
            except OSError:
                pass
            log.info("transcript -> %s (%.0fs for %s of audio)", self.final_path, time.time() - t0, _hms(length))
            self.ui.put(("Transcript saved", "#27ae60", 3000))
            try:
                if self.open_mode in ("transcript", "both"):
                    sysglue.open_path(self.final_path)
                if self.open_mode in ("folder", "both"):
                    sysglue.reveal_path(self.final_path)
            except Exception:
                log.exception("could not open the transcript or its folder")
        except Exception as e:
            log.exception("file transcription failed: %s", self.source)
            self.ui.put((f"Could not transcribe {short}: {e}", "#7f8c8d", 6000))
        finally:
            self.state = "done"
