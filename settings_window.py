"""
The settings schema (every setting, its control and its help text), settings.ini reading and
writing, and the shared look (colors, the Switch and Tooltip widgets). The window itself is
main_window.py, which builds one page per section from SCHEMA.
"""

import configparser
import os
import tkinter as tk

from sysglue import IS_MAC, KEY_NAMES, TEXT_EDITOR, open_path

LANGUAGES = ["en", "auto", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "ja", "zh", "ko", "ar", "hi"]

FONT = "Helvetica Neue" if IS_MAC else "Segoe UI"
BG, CARD, LINE = "#f2f2f7", "#ffffff", "#e5e5ea"         # window, card, hairline
TEXT, MUTED, ACCENT, GREEN, OFF = "#1d1d1f", "#6e6e73", "#0a84ff", "#34c759", "#d1d1d6"
HOVER = "#e4e4e9"

# (section, key, label, kind, options, help)   kind: key | text | int | bool | choice | folder
SCHEMA = [
    ("Dictation", "hotkey", "Dictation key", "key", KEY_NAMES,
     "Hold this key, speak, let go: the words are pasted where the cursor is.\n\n"
     "The key stops working for everything else while Voice Typing runs. Pick one from the "
     "list or type a name.\n\nOptions: " + ", ".join(KEY_NAMES)),
    ("Dictation", "dictation_mode", "Dictation key works as", "choice", ["hold", "toggle"],
     "hold = hold the key down while you talk; let go and the words are typed (default).\n\n"
     "toggle = tap the key once to start listening, talk as long as you like, tap again to stop "
     "and type. The red pill stays up while it listens."),
    ("Dictation", "language", "Language", "choice", LANGUAGES,
     "The language you speak.\n\nen = English (default). auto = detect it each time, which is "
     "slower and needs the NVIDIA model; the CPU model is English-only.\n\nOther codes: es Spanish, "
     "fr French, de German, it Italian, pt Portuguese, nl Dutch, pl Polish, ru Russian, ja Japanese, "
     "zh Chinese, ko Korean, ar Arabic, hi Hindi."),
    ("Dictation", "gpu_model", "Speech model with an NVIDIA card", "choice", ["turbo", "small.en", "base.en", "medium", "large-v3"],
     "Which Whisper model to use when an NVIDIA graphics card is found.\n\n"
     "turbo = best mix of accuracy and speed (default)\nlarge-v3 = most accurate, slower\n"
     "medium, small.en, base.en = smaller and faster, less accurate"),
    ("Dictation", "cpu_model", "Speech model without one", "choice", ["base.en", "small.en", "tiny.en"],
     "Which Whisper model to use on the processor alone (no NVIDIA card, or a Mac).\n\n"
     "base.en = quick, good (default)\nsmall.en = more accurate, 2-3x slower\ntiny.en = fastest, rougher"),
    ("Dictation", "beeps", "Beeps", "bool", None,
     "A short high tone when recording starts and a lower one when it stops, so you know the key "
     "registered without looking."),
    ("Dictation", "show_overlay", "On-screen status pill", "bool", None,
     "The small colored pill near the bottom of the screen: red while listening, blue while typing, "
     "purple while a meeting records, with a clock."),
    ("Dictation", "trailing_space", "Space after dictated text", "bool", None,
     "Adds one space after each dictation so the next one does not run into it."),

    ("Meetings", "meeting_hotkey", "Record-a-meeting key", "key", KEY_NAMES,
     "Tap once to start recording a meeting, tap again to stop. Must be a different key from "
     "the dictation key.\n\nOptions: " + ", ".join(KEY_NAMES)),
    ("Meetings", "meeting_hold_seconds", "Hold the key this many seconds", "int", None,
     "0 = a quick tap starts and stops a recording (default).\n\n3 or 5 = you must hold the key that "
     "long; a countdown shows while you hold, and letting go early does nothing. Stops a stray tap "
     "from starting or ending a recording."),
    ("Meetings", "meeting_dir", "Transcripts folder", "folder", None,
     "Where meeting transcripts go (and the audio too, unless you set an audio folder below).\n\n"
     "Any folder works, including a network share or a synced folder."),
    ("Meetings", "meeting_audio_dir", "Audio folder (optional)", "folder", None,
     "Put the WAV audio files in a different folder from the transcripts.\n\nLeave blank to keep "
     "them next to the transcripts. The transcript always names the audio file's full location."),
    ("Meetings", "meeting_subfolders", "One folder per meeting", "bool", None,
     "Each meeting gets its own folder, named like 'Meeting 2026-10-09 14-30', holding that "
     "meeting's transcript and audio.\n\nCombines with the audio folder: both get a per-meeting folder."),
    ("Meetings", "meeting_speakers", "Number of speakers", "int", None,
     "0 = work out how many people spoke (default).\n\nA number (2, 3, ...) forces that many speakers. "
     "Use it if a meeting comes back split into too many or too few."),
    ("Meetings", "meeting_open", "When the transcript is ready, open", "choice", ["transcript", "folder", "both", "no"],
     f"What opens when speaker labeling finishes.\n\ntranscript = the text file in {TEXT_EDITOR} (default)\n"
     f"folder = the folder, with the audio file selected\nboth\nno = nothing"),
    ("Meetings", "meeting_type_location", "Type the recording's location", "choice", ["no", "stop", "start", "both"],
     "Types 'Meeting recording: <file location>' where your cursor is, for notes that should say "
     "where the recording went.\n\nno = never (default) - the transcript file names the recording's "
     "location anyway\nstop = when you stop the recording\nstart = when it starts\nboth"),
    ("Meetings", "meeting_chunk_seconds", "Live transcript update (seconds)", "int", None,
     "During a meeting a '.live.txt' file grows as the meeting goes, so nothing is lost if the "
     "computer crashes. This is how often it is updated. 30 is a good default."),
    ("Meetings", "meeting_threads", "CPU threads for speaker labeling", "int", None,
     "How many processor threads speaker labeling may use at the end of a meeting. 8 is a good "
     "default; lower it if the computer must stay responsive for other work."),

    ("Files", "file_transcript_dir", "Transcripts of existing files go to", "folder", None,
     "Where the transcript of an existing recording or video lands.\n\nBlank = next to the file "
     "itself, as '<name> transcript.txt' (default)."),
]

SECTION_NOTES = {
    "Dictation": "Hold a key and talk; the words are typed where the cursor is.",
    "Meetings": "Tap a key to record a meeting; a transcript with speaker labels follows.",
    "Files": "Tray icon > Transcribe a file... turns an existing recording or video into a transcript.",
}


def template_defaults(template):
    """key -> default value, as written in SETTINGS_TEMPLATE."""
    out = {}
    for line in template.splitlines():
        if "=" in line and not line.lstrip().startswith(";"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def read_values(settings_path):
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(settings_path, encoding="utf-8-sig")
    return dict(cp.items("voice typing")) if cp.has_section("voice typing") else {}


def write_values(settings_path, template, values):
    """Rewrite settings.ini from the template, substituting the values, so the comments stay."""
    out = []
    for line in template.splitlines():
        if "=" in line and not line.lstrip().startswith(";"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                line = f"{key} = {values[key]}"
        out.append(line)
    with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


class Switch(tk.Canvas):
    """A macOS-style on/off switch bound to a BooleanVar."""
    W, H = 42, 24

    def __init__(self, parent, var, bg=CARD):
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0, cursor="hand2")
        self.var = var
        self.bind("<Button-1>", lambda e: self.var.set(not self.var.get()))
        self.var.trace_add("write", lambda *a: self.draw())
        self.draw()

    def draw(self):
        self.delete("all")
        on = bool(self.var.get())
        color = GREEN if on else OFF
        h, r = self.H, self.H / 2
        self.create_oval(0, 0, h, h, fill=color, outline=color)
        self.create_oval(self.W - h, 0, self.W, h, fill=color, outline=color)
        self.create_rectangle(r, 0, self.W - r, h, fill=color, outline=color)
        x = self.W - h + 2 if on else 2
        self.create_oval(x, 2, x + h - 4, h - 2, fill="white", outline="#c7c7cc")


class Tooltip:
    """One shared tooltip window, shown under a setting's row while help mode is on."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self._hide_job = None

    def show(self, row, text):
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            frame = tk.Frame(self.win, bg=CARD, highlightbackground="#c7c7cc", highlightthickness=1)
            frame.pack()
            self.label = tk.Label(frame, text="", bg=CARD, fg=TEXT, justify="left",
                                  wraplength=400, padx=12, pady=10, font=(FONT, 10))
            self.label.pack()
        self.label.config(text=text)
        self.win.update_idletasks()
        x = row.winfo_rootx()
        y = row.winfo_rooty() + row.winfo_height() + 2
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(10, min(x, sw - w - 10))
        if y + h > sh - 10:
            y = row.winfo_rooty() - h - 2
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.lift()

    def hide_soon(self):
        """Hide after a moment - moving between a row's label and its control fires Leave/Enter."""
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(80, self.hide)

    def hide(self):
        self._hide_job = None
        if self.win is not None:
            self.win.withdraw()

    def destroy(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None
