"""
Meeting mode for Voice Typing: a long recording with a live transcript and speaker labels.

Used by voice_typing.py. One MeetingSession lives from start() to the end of finalize().

While recording
  - The microphone and the computer's own sound (WASAPI loopback, so Zoom/Teams callers are
    heard) are captured, mixed to 16 kHz mono and written straight to a WAV file as they come,
    so a crash or a sleep loses nothing already recorded.
  - Every CHUNK_SECONDS or so the newest audio is cut at a quiet point and transcribed with
    Whisper (word timestamps on). The text is appended to "<name>.live.txt" right away.

When stopped
  - The tail is transcribed, the whole WAV is run through speaker diarization (sherpa-onnx:
    pyannote segmentation + a speaker-embedding model, clustered), each word is given the
    speaker talking at that moment, and the final transcript "<name>.txt" is written as
    "[hh:mm:ss] Speaker N: ..." lines. The live file is then removed and the final one opened.
"""

import datetime
import logging
import os
import queue
import subprocess
import threading
import time
import wave

import numpy as np
import sounddevice as sd

import sysglue

sc = None
if sysglue.IS_WIN:
    try:
        import soundcard as sc               # WASAPI loopback; must be imported on the main thread
    except Exception:                        # pragma: no cover - app still works, mic only
        sc = None
# On macOS there is no loopback device without extra software, so meetings record the mic only.

log = logging.getLogger("voice_typing.meeting")
SR = 16000


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x.astype(np.float32, copy=False)
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _ms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


class MeetingSession:
    def __init__(self, model, model_lock, device, out_dir, models_dir, ui, speakers=0,
                 chunk_seconds=30, threads=8, language="en", open_mode="transcript",
                 audio_dir=None, subfolders=False):
        self.model, self.model_lock, self.device = model, model_lock, device
        self.open_mode = open_mode           # transcript | folder | both | no
        self.out_dir, self.models_dir, self.ui = out_dir, models_dir, ui
        self.speakers, self.chunk_seconds, self.threads, self.language = speakers, chunk_seconds, threads, language

        self.started = datetime.datetime.now()
        stamp = self.started.strftime("%Y-%m-%d %H-%M")
        name = f"Meeting {stamp}"
        # Transcript folder, audio folder (same unless audio_dir is set), optional folder per meeting.
        txt_dir = os.path.join(out_dir, name) if subfolders else out_dir
        if audio_dir:
            wav_dir = os.path.join(audio_dir, name) if subfolders else audio_dir
        else:
            wav_dir = txt_dir
        os.makedirs(txt_dir, exist_ok=True)
        os.makedirs(wav_dir, exist_ok=True)
        self.wav_path = os.path.join(wav_dir, name + ".wav")
        self.live_path = os.path.join(txt_dir, name + ".live.txt")
        self.final_path = os.path.join(txt_dir, name + ".txt")

        self._stop = threading.Event()
        self._mic_q, self._lb_q = queue.Queue(), queue.Queue()
        self._mic_stream = None
        self._threads = []
        self._wav = None
        self._emitted = 0                    # mixed samples written so far
        self._pending = []                   # mixed chunks not yet transcribed
        self._pending_len = 0
        self._pending_offset = 0             # sample index where _pending starts
        self.words = []                      # (start_s, end_s, text) absolute times
        self.state = "recording"

    # ---- capture -----------------------------------------------------------------------
    def start(self):
        self._wav = wave.open(self.wav_path, "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(SR)
        with open(self.live_path, "w", encoding="utf-8") as f:
            f.write(f"Meeting started {self.started:%Y-%m-%d %I:%M %p} - live transcript (no speaker labels yet)\n\n")

        self._mic_stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=1600,
                                          callback=self._mic_cb)
        self._mic_stream.start()
        for target in (self._loopback_loop, self._mix_loop, self._timer_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        log.info("meeting started -> %s", self.wav_path)

    def _mic_cb(self, indata, frames, time_info, status):
        if status:
            log.warning("mic status: %s", status)
        self._mic_q.put(indata[:, 0].copy())

    def _loopback_loop(self):
        """Capture what the computer is playing (remote callers). Silence if there is no speaker."""
        # soundcard initializes COM (multithreaded) when first imported, which must happen on
        # the main thread at startup (see the import at the top); worker threads then join
        # that apartment implicitly. Calling CoInitializeEx here ourselves breaks its import.
        try:
            if sc is None:
                raise RuntimeError("no loopback capture on this platform")
            spk = sc.default_speaker()
            mic = sc.get_microphone(spk.name, include_loopback=True)
            rate = 48000
            with mic.recorder(samplerate=rate, channels=1, blocksize=rate // 10) as rec:
                log.info("loopback capture from %r", spk.name)
                while not self._stop.is_set():
                    block = rec.record(numframes=rate // 10)
                    self._lb_q.put(_resample(block[:, 0] if block.ndim > 1 else block, rate, SR))
        except Exception as e:
            log.warning("loopback capture unavailable (%s) - recording microphone only", e)
            while not self._stop.is_set():
                time.sleep(0.1)
                self._lb_q.put(np.zeros(SR // 10, dtype=np.float32))

    def _mix_loop(self):
        mic_buf, lb_buf = np.zeros(0, np.float32), np.zeros(0, np.float32)
        while not self._stop.is_set() or not self._mic_q.empty():
            time.sleep(0.2)
            mic_buf = self._drain(self._mic_q, mic_buf)
            lb_buf = self._drain(self._lb_q, lb_buf)
            n = min(len(mic_buf), len(lb_buf))
            if self._stop.is_set():          # flush whatever is left, padding the shorter side
                n = max(len(mic_buf), len(lb_buf))
                mic_buf = np.pad(mic_buf, (0, n - len(mic_buf)))
                lb_buf = np.pad(lb_buf, (0, n - len(lb_buf)))
            if n == 0:
                continue
            mixed = np.clip(mic_buf[:n] + lb_buf[:n], -1.0, 1.0)
            mic_buf, lb_buf = mic_buf[n:], lb_buf[n:]
            self._wav.writeframes((mixed * 32767).astype(np.int16).tobytes())
            self._emitted += n
            self._pending.append(mixed)
            self._pending_len += n
            if self._pending_len >= self.chunk_seconds * SR:
                self._transcribe_pending(final=False)
        self._transcribe_pending(final=True)
        self._wav.close()
        self._wav = None

    @staticmethod
    def _drain(q, buf):
        parts = [buf]
        try:
            while True:
                parts.append(q.get_nowait())
        except queue.Empty:
            pass
        return np.concatenate(parts) if len(parts) > 1 else buf

    def _timer_loop(self):
        while not self._stop.is_set():
            self.ui.put((f"●  Recording {_ms(self._emitted / SR)}", "#8e44ad", None))
            time.sleep(1.0)

    # ---- transcription -------------------------------------------------------------------
    def _transcribe_pending(self, final: bool):
        if self._pending_len == 0:
            return
        audio = np.concatenate(self._pending)
        if final:
            chunk, rest = audio, audio[:0]
        else:
            cut = self._quiet_cut(audio)
            chunk, rest = audio[:cut], audio[cut:]
        offset = self._pending_offset
        self._pending, self._pending_len, self._pending_offset = [rest], len(rest), offset + len(chunk)
        if len(chunk) < SR * 0.5:
            return
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if rms < 0.002:
            return
        t0 = time.time()
        try:
            with self.model_lock:
                result = self.model.transcribe(chunk, language=self.language, fp16=(self.device == "cuda"),
                                               condition_on_previous_text=False, word_timestamps=True,
                                               no_speech_threshold=0.6)
        except Exception:
            log.exception("chunk transcription failed")
            return
        base = offset / SR
        new_words, text = [], []
        for seg in result["segments"]:
            if seg.get("no_speech_prob", 0) >= 0.6:
                continue
            for w in seg.get("words", []):
                new_words.append((base + w["start"], base + w["end"], w["word"]))
            text.append(seg["text"].strip())
        self.words.extend(new_words)
        line = " ".join(t for t in text if t)
        log.info("chunk %.0fs @%s -> %.2fs: %d words", len(chunk) / SR, _ms(base), time.time() - t0, len(new_words))
        if line:
            with open(self.live_path, "a", encoding="utf-8") as f:
                f.write(f"[{_hms(base)}] {line}\n")

    @staticmethod
    def _quiet_cut(audio: np.ndarray) -> int:
        """Index of the quietest 0.3 s window inside the last 8 s, so we don't cut mid-word."""
        win, hop = int(0.3 * SR), int(0.05 * SR)
        lo = max(0, len(audio) - 8 * SR)
        best, best_i = None, len(audio)
        for i in range(lo, len(audio) - win, hop):
            e = float(np.mean(audio[i:i + win] ** 2))
            if best is None or e < best:
                best, best_i = e, i + win // 2
        return best_i

    # ---- stop & finalize -----------------------------------------------------------------
    def stop(self):
        """Stop capture, then label speakers and write the final transcript (runs in a thread)."""
        self.state = "finalizing"
        self._stop.set()
        if self._mic_stream is not None:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
        threading.Thread(target=self._finalize, daemon=True).start()

    def _finalize(self):
        try:
            self.ui.put(("Transcribing the last bit...", "#8e44ad", None))
            for t in self._threads:
                t.join(timeout=120)
            length = self._emitted / SR
            log.info("meeting recorded %.0fs, %d words; labeling speakers ...", length, len(self.words))
            self.ui.put(("Labeling speakers... (about 2-3 min per hour of audio)", "#8e44ad", None))
            turns = None
            try:
                turns = self._diarize()
            except Exception:
                log.exception("speaker labeling failed - writing transcript without labels")
            self._write_final(length, turns)
            try:
                os.remove(self.live_path)
            except OSError:
                pass
            self.ui.put(("Transcript saved", "#27ae60", 3000))
            log.info("transcript -> %s", self.final_path)
            try:
                if self.open_mode in ("transcript", "both"):
                    sysglue.open_path(self.final_path)
                if self.open_mode in ("folder", "both"):
                    sysglue.reveal_path(self.wav_path)
            except Exception:
                log.exception("could not open the transcript or its folder")
        except Exception:
            log.exception("finalize failed")
            self.ui.put(("Meeting transcript failed - see log", "#7f8c8d", 5000))
        finally:
            self.state = "done"

    def _diarize(self, audio=None):
        import sherpa_onnx

        if audio is None:
            with wave.open(self.wav_path) as w:
                audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        seg_model = os.path.join(self.models_dir, "pyannote-segmentation-3-0.onnx")
        emb_model = os.path.join(self.models_dir, "3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")
        cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=seg_model),
                num_threads=self.threads),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=emb_model, num_threads=self.threads),
            # Threshold tuned 2026-10-08 on a room-microphone recording of two voices: 0.5 split
            # them into five "speakers"; 0.7-1.0 all gave exactly two with the right turns.
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=self.speakers if self.speakers > 0 else -1, threshold=0.8),
            min_duration_on=0.3, min_duration_off=0.5)
        if not cfg.validate():
            raise RuntimeError("diarization config invalid - are the model files in Project/models?")
        t0 = time.time()
        result = sherpa_onnx.OfflineSpeakerDiarization(cfg).process(audio).sort_by_start_time()
        turns = [(s.start, s.end, s.speaker) for s in result]
        log.info("diarization: %.1fs, %d turns, %d speakers", time.time() - t0, len(turns),
                 len({t[2] for t in turns}))
        return turns

    def _write_final(self, length, turns):
        # Give each word the speaker whose turn covers its midpoint (or the nearest turn within 1 s).
        labeled = []
        last = None
        for (ws, we, text) in self.words:
            spk = last
            if turns:
                mid = (ws + we) / 2
                hit = [t for t in turns if t[0] <= mid <= t[1]]
                if hit:
                    spk = hit[0][2]
                else:
                    near = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))
                    if min(abs(near[0] - mid), abs(near[1] - mid)) <= 1.0:
                        spk = near[2]
            labeled.append((ws, we, text, spk))
            last = spk
        # Number speakers in order of first appearance.
        order = {}
        for *_, spk in labeled:
            if spk is not None and spk not in order:
                order[spk] = len(order) + 1

        lines, cur = [], None
        for ws, we, text, spk in labeled:
            if cur is None or spk != cur["spk"] or ws - cur["end"] > 3.0:
                if cur:
                    lines.append(cur)
                cur = {"start": ws, "end": we, "spk": spk, "text": []}
            cur["text"].append(text)
            cur["end"] = we
        if cur:
            lines.append(cur)

        n_spk = len(order)
        with open(self.final_path, "w", encoding="utf-8") as f:
            f.write(getattr(self, "title", None) or f"Meeting transcript - {self.started:%A, %B %d, %Y, %I:%M %p}")
            f.write("\n")
            f.write(f"Length {_hms(length)} - {n_spk} speaker{'s' if n_spk != 1 else ''} detected"
                    + (" (labels unavailable)" if not turns else "") + "\n")
            same_folder = os.path.dirname(self.wav_path) == os.path.dirname(self.final_path)
            f.write(f"Audio: {os.path.basename(self.wav_path) if same_folder else self.wav_path}\n\n")
            for ln in lines:
                who = f"Speaker {order[ln['spk']]}" if ln["spk"] in order else "Unknown"
                f.write(f"[{_hms(ln['start'])}] {who}: {''.join(ln['text']).strip()}\n\n")
