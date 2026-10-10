"""
Local title + summary for a transcript, with nothing leaving the computer.

The language model (Qwen3-4B, Apache 2.0, about 2.5 GB) and the program that runs it
(llama.cpp's llama-server, MIT) are not part of the installer. They are downloaded on request
from the Summaries page into <data dir>/summary and <data dir>/llama, and can be removed there.

    summarize.status()                     -> what is installed
    summarize.download(progress, cancel)   -> fetch runtime + model (resumable)
    summarize.remove()
    Summarizer().summarize_file(path, progress)   -> writes title + summary into the transcript

llama-server runs as a separate process on 127.0.0.1 while a summary is made and is stopped
afterwards, so the model's memory is freed between meetings.
"""

import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.request
import zipfile

import datetime

import sysglue
import transcripts

log = logging.getLogger("voice_typing.summary")

LLAMA_BUILD = "b11541"
LLAMA_URLS = {
    "win": f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/llama-{LLAMA_BUILD}-bin-win-cpu-x64.zip",
    "mac-arm64": f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/llama-{LLAMA_BUILD}-bin-macos-arm64.tar.gz",
    "mac-x64": f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/llama-{LLAMA_BUILD}-bin-macos-x64.tar.gz",
}
MODEL_NAME = "Qwen3-4B-Q4_K_M.gguf"
MODEL_LABEL = "Qwen3 4B (Apache 2.0)"
MODEL_URL = f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/{MODEL_NAME}"
MODEL_BYTES = 2_497_280_256
RUNTIME_BYTES = 19_518_702 if sysglue.IS_WIN else 12_100_000

CONTEXT = 6144                 # tokens the model sees at once; keeps memory near 1 GB on top of the model
CHUNK_WORDS = 1800             # a transcript longer than this is summarized in pieces, then merged
USER_AGENT = "VoiceTyping (https://github.com/grungenut/voice-typing)"

DEFAULT_INSTRUCTIONS = (
    "Write a summary of this recording: 2 to 4 sentences on what it was about and the outcome, then "
    "'Key points:' with 3 to 8 bullets, then 'Action items:' with who does what by when (or: none mentioned)."
)

SYSTEM_PROMPT = (
    "You summarize transcripts of recorded conversations and meetings for the person who recorded "
    "them. Be accurate and concrete. Use only what the transcript says; never add facts, names or "
    "numbers that are not in it. Keep names, dates, numbers, dosages and instructions exactly as "
    "spoken. Plain American English, no markdown headings."
)


def runtime_dir():
    return os.path.join(sysglue.data_dir(), "llama")


def model_dir():
    return os.path.join(sysglue.data_dir(), "summary")


def model_path():
    return os.path.join(model_dir(), MODEL_NAME)


def server_path():
    return os.path.join(runtime_dir(), "llama-server.exe" if sysglue.IS_WIN else "llama-server")


def _runtime_key():
    if sysglue.IS_WIN:
        return "win"
    return "mac-arm64" if platform.machine() == "arm64" else "mac-x64"


def status():
    """{'ready': bool, 'runtime': bool, 'model': bool, 'model_bytes': int, 'partial_bytes': int}"""
    part = model_path() + ".part"
    return {
        "runtime": os.path.exists(server_path()),
        "model": os.path.exists(model_path()) and os.path.getsize(model_path()) == MODEL_BYTES,
        "model_bytes": os.path.getsize(model_path()) if os.path.exists(model_path()) else 0,
        "partial_bytes": os.path.getsize(part) if os.path.exists(part) else 0,
        "ready": os.path.exists(server_path()) and os.path.exists(model_path())
                 and os.path.getsize(model_path()) == MODEL_BYTES,
    }


def total_download_bytes():
    return MODEL_BYTES + RUNTIME_BYTES


# ---- download ----------------------------------------------------------------------------
class Canceled(Exception):
    pass


def _fetch(url, dest, progress, cancel, done_before=0, total=None, resume=False):
    """Download url to dest (.part first). progress(bytes_so_far_overall, total_overall)."""
    part = dest + ".part"
    have = os.path.getsize(part) if resume and os.path.exists(part) else 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req, timeout=60) as resp:
        if have and resp.status != 206:              # server ignored the range: start over
            have = 0
        mode = "ab" if have else "wb"
        with open(part, mode) as f:
            got = have
            while True:
                if cancel is not None and cancel.is_set():
                    raise Canceled()
                block = resp.read(1 << 20)
                if not block:
                    break
                f.write(block)
                got += len(block)
                progress(done_before + got, total)
    os.replace(part, dest)


def _install_runtime(archive):
    """Keep llama-server and the libraries it needs; the other tools are not used."""
    os.makedirs(runtime_dir(), exist_ok=True)
    kept = 0
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                base = name.rsplit("/", 1)[-1]
                if not base or (base.endswith(".exe") and base != "llama-server.exe"):
                    continue
                with open(os.path.join(runtime_dir(), base), "wb") as f:
                    f.write(z.read(name))
                kept += 1
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if not m.isfile():
                    continue
                base = os.path.basename(m.name)
                if base.endswith((".dylib", ".so")) or base == "llama-server":
                    with open(os.path.join(runtime_dir(), base), "wb") as f:
                        f.write(t.extractfile(m).read())
                    if base == "llama-server":
                        os.chmod(os.path.join(runtime_dir(), base), 0o755)
                    kept += 1
    if not os.path.exists(server_path()):
        raise RuntimeError("the llama.cpp archive did not contain llama-server")
    log.info("summary runtime installed (%d files) in %s", kept, runtime_dir())


def download(progress, cancel=None):
    """Fetch the runtime (if missing) and the model (resumes a partial download).
    progress(label, fraction_0_to_1). Raises Canceled when the cancel event is set."""
    total = total_download_bytes()
    done = 0
    if not os.path.exists(server_path()):
        os.makedirs(runtime_dir(), exist_ok=True)
        url = LLAMA_URLS[_runtime_key()]
        archive = os.path.join(runtime_dir(), os.path.basename(url))
        progress("Downloading the program that runs the model...", 0)
        _fetch(url, archive, lambda got, _: progress("Downloading the program that runs the model...", got / total),
               cancel, 0, total)
        _install_runtime(archive)
        os.remove(archive)
    done += RUNTIME_BYTES
    if not status()["model"]:
        os.makedirs(model_dir(), exist_ok=True)
        _fetch(MODEL_URL, model_path(),
               lambda got, _: progress(f"Downloading the summary model ({got / 1e9:.2f} of {total / 1e9:.1f} GB)...", got / total),
               cancel, done, total, resume=True)
        if os.path.getsize(model_path()) != MODEL_BYTES:
            os.remove(model_path())
            raise RuntimeError("the model file came down incomplete - please try again")
    progress("Ready", 1.0)
    log.info("summary model ready: %s", model_path())


def remove():
    for d in (runtime_dir(), model_dir()):
        shutil.rmtree(d, ignore_errors=True)
    log.info("summary model and runtime removed")


# ---- running the model -------------------------------------------------------------------
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Summarizer:
    """Starts llama-server when needed, talks to it over HTTP on localhost, stops it afterwards."""

    def __init__(self, threads=None):
        self.threads = threads
        self.proc = None
        self.port = None
        self.lock = threading.Lock()

    # -- server lifecycle --
    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        if not status()["ready"]:
            raise RuntimeError("the summary model is not installed")
        self.port = _free_port()
        args = [server_path(), "-m", model_path(), "-c", str(CONTEXT), "--host", "127.0.0.1",
                "--port", str(self.port), "-np", "1", "--no-webui", "--log-disable",
                "--chat-template-kwargs", '{"enable_thinking": false}']
        if self.threads:
            args += ["-t", str(self.threads)]
        kw = {}
        if sysglue.IS_WIN:
            kw["creationflags"] = 0x08000000        # CREATE_NO_WINDOW
        log.info("starting llama-server on port %d", self.port)
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        deadline = time.time() + 180
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited with code {self.proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                time.sleep(0.5)
        self.stop()
        raise RuntimeError("llama-server did not become ready in time")

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def chat(self, user, max_tokens=700):
        body = json.dumps({
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user + "\n/no_think"}],
            "max_tokens": max_tokens, "temperature": 0.3, "top_p": 0.9,
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3600) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()

    # -- summarizing --
    @staticmethod
    def _chunks(text):
        words = text.split()
        if len(words) <= CHUNK_WORDS:
            return [text]
        lines, out, cur, n = text.splitlines(), [], [], 0
        for ln in lines:
            w = len(ln.split())
            if cur and n + w > CHUNK_WORDS:
                out.append("\n".join(cur))
                cur, n = [], 0
            cur.append(ln)
            n += w
        if cur:
            out.append("\n".join(cur))
        return out

    @staticmethod
    def _parse(answer):
        title, summary = "", answer.strip()
        m = re.search(r"^\s*TITLE:\s*(.+?)\s*$", answer, re.M | re.I)
        if m:
            title = m.group(1).strip().strip('"*')
            summary = answer[m.end():]
        summary = re.sub(r"^\s*SUMMARY:\s*", "", summary.strip(), flags=re.I)
        summary = re.split(r"\n\s*(?:NOTES|TRANSCRIPT)\b.*:", summary, maxsplit=1)[0]   # echoed input, if any
        summary = "\n".join(ln.rstrip() for ln in summary.splitlines())
        summary = re.sub(r"\n{3,}", "\n\n", summary).strip()
        return title, summary

    def summarize_text(self, text, progress=lambda t: None, template=None):
        instructions = (template or {}).get("instructions") or DEFAULT_INSTRUCTIONS
        chunks = self._chunks(text)
        notes = []
        if len(chunks) > 1:
            for i, chunk in enumerate(chunks, 1):
                progress(f"Summarizing... part {i} of {len(chunks)}")
                notes.append(self.chat(
                    f"This is part {i} of {len(chunks)} of a transcript. Write detailed notes on this part only: "
                    f"what was discussed, what was decided, questions raised, and anything to do (with who and when). "
                    f"Use short plain sentences or bullets, at most 200 words.\n\nTRANSCRIPT PART {i}:\n{chunk}",
                    max_tokens=450))
            source = "NOTES FROM EACH PART OF THE TRANSCRIPT:\n\n" + "\n\n".join(f"Part {i + 1}:\n{n}" for i, n in enumerate(notes))
            while len(source.split()) > CHUNK_WORDS:        # very long meetings: fold the notes once more
                progress("Summarizing... combining notes")
                source = "NOTES:\n" + self.chat("Condense these notes to at most 400 words, keeping every decision, "
                                                "name, number and action item:\n\n" + source, max_tokens=700)
        else:
            source = "TRANSCRIPT:\n" + chunks[0]
        progress("Summarizing... writing the " + ((template or {}).get("name") or "summary").lower())
        answer = self.chat(
            "Answer in exactly this form: a first line\n"
            "TITLE: <at most 8 words saying what the recording was about>\n"
            "and then the text described below, with no other preamble.\n\n"
            + instructions.strip() + "\n\n" + source, max_tokens=1200)
        return self._parse(answer)

    def summarize_file(self, path, progress=lambda t: None, template=None):
        """Title + note for one transcript. The title always goes into the transcript's header;
        the note goes into its Summary block (template output = summary) or into its own file
        beside the transcript (output = file). Returns (title, text, note_path or None)."""
        text = transcripts.body_text(path)
        if len(text.split()) < 15:
            raise ValueError("the transcript is too short to summarize")
        with self.lock:
            t0 = time.time()
            progress("Starting the summary model...")
            self.start()
            try:
                title, body = self.summarize_text(text, progress, template)
            finally:
                self.stop()
        if not body:
            raise RuntimeError("the model returned nothing")
        note_path = None
        if template and template.get("output") == "file":
            info = transcripts.parse(path) or {}
            transcripts.write_summary(path, title or info.get("title", ""), info.get("summary", ""))
            base, kind = os.path.splitext(path)[0], template["name"].strip()
            note_path = f"{base} - {kind}.txt"
            n = 2
            while os.path.exists(note_path):                 # never overwrite a note someone may have edited
                note_path = f"{base} - {kind} ({n}).txt"
                n += 1
            when = datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " ")
            with open(note_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(f"{title or kind}\nNote: {kind} - a draft to review, written by the local summary model on {when}\n"
                        f"From: {os.path.abspath(path)}\n\n{body}\n")
        else:
            transcripts.write_summary(path, title, body)
        log.info("%s (%d words in, %.0fs): %r -> %s", (template or {}).get("name", "summary"), len(text.split()),
                 time.time() - t0, title, note_path or path)
        return title, body, note_path
