"""
Settings window for Voice Typing (tkinter). Opened from the tray icon (Windows) or the
Voice Typing pill menu (macOS).

It reads settings.ini, shows every setting as a labeled control with a "?" beside it (hover
or click for the explanation and the options), and on Save rewrites settings.ini from
SETTINGS_TEMPLATE with the new values, so the comments stay. Settings take effect when the
app restarts; Save does that.
"""

import configparser
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from sysglue import KEY_NAMES, PASTE_KEYS, TEXT_EDITOR, open_path

LANGUAGES = ["en", "auto", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "ja", "zh", "ko", "ar", "hi"]

# (section, key, label, kind, options, help)   kind: key | text | int | bool | choice | folder
SCHEMA = [
    ("Dictation", "hotkey", "Hold-to-talk key", "key", KEY_NAMES,
     "Hold this key, speak, let go: the words are pasted where the cursor is.\n\n"
     "The key stops working for everything else while Voice Typing runs. Pick one from the "
     "list or type a name.\n\nOptions: " + ", ".join(KEY_NAMES)),
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
    ("Dictation", "trailing_space", "Add a space after dictated text", "bool", None,
     "Adds one space after each dictation so the next one does not run into it."),

    ("Meetings", "meeting_hotkey", "Record-a-meeting key", "key", KEY_NAMES,
     "Tap once to start recording a meeting, tap again to stop. Must be a different key from "
     "the hold-to-talk key.\n\nOptions: " + ", ".join(KEY_NAMES)),
    ("Meetings", "meeting_hold_seconds", "Hold the key this many seconds", "int", None,
     "0 = a quick tap starts and stops a recording (default).\n\n3 or 5 = you must hold the key that "
     "long; a countdown shows while you hold, and letting go early does nothing. Stops a stray tap "
     "from starting or ending a recording."),
    ("Meetings", "meeting_dir", "Transcripts folder", "folder", None,
     "Where meeting transcripts go (and the audio too, unless you set an audio folder below).\n\n"
     "Any folder works, including a network share or a synced folder."),
    ("Meetings", "meeting_audio_dir", "Audio folder (optional)", "folder", None,
     "Put the WAV audio files in a different folder from the transcripts.\n\nLeave blank to keep "
     "them next to the transcripts. The transcript then names the audio file's full location."),
    ("Meetings", "meeting_subfolders", "One folder per meeting", "bool", None,
     "Each meeting gets its own folder, named like 'Meeting 2026-10-09 14-30', holding that "
     "meeting's transcript and audio.\n\nCombines with the audio folder: both get a per-meeting folder."),
    ("Meetings", "meeting_speakers", "Number of speakers", "int", None,
     "0 = work out how many people spoke (default).\n\nA number (2, 3, ...) forces that many speakers. "
     "Use it if a meeting comes back split into too many or too few."),
    ("Meetings", "meeting_paste_path", "Type the recording's location", "choice", ["stop", "start", "both", "no"],
     f"Types 'Meeting recording: <file location>' where your cursor is, so your notes say where the "
     f"recording went.\n\nstop = when you stop the recording (default)\nstart = when it starts\n"
     f"both\nno = never"),
    ("Meetings", "meeting_open", "When the transcript is ready, open", "choice", ["transcript", "folder", "both", "no"],
     f"What opens when speaker labeling finishes.\n\ntranscript = the text file in {TEXT_EDITOR} (default)\n"
     f"folder = the folder, with the audio file selected\nboth\nno = nothing"),
    ("Meetings", "meeting_chunk_seconds", "Live transcript update (seconds)", "int", None,
     "During a meeting a '.live.txt' file grows as the meeting goes, so nothing is lost if the "
     "computer crashes. This is how often it is updated. 30 is a good default."),
    ("Meetings", "meeting_threads", "CPU threads for speaker labeling", "int", None,
     "How many processor threads speaker labeling may use at the end of a meeting. 8 is a good "
     "default; lower it if the computer must stay responsive for other work."),

    ("Transcribing files", "file_transcript_dir", "Transcripts of existing files go to", "folder", None,
     "Where the transcript of an existing recording or video lands.\n\nBlank = next to the file "
     "itself, as '<name> transcript.txt' (default)."),
]


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


class Tooltip:
    """One shared tooltip window. Hover a '?' to see it; click the '?' to pin it open."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.pinned = None
        self.text = None

    def show(self, widget, text):
        if self.pinned is not None and self.pinned is not widget:
            return
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            frame = tk.Frame(self.win, bg="#fffbe6", bd=1, relief="solid")
            frame.pack()
            self.label = tk.Label(frame, text="", bg="#fffbe6", fg="#222222", justify="left",
                                  wraplength=360, padx=10, pady=8, font=("Segoe UI", 10))
            self.label.pack()
        self.label.config(text=text)
        self.win.update_idletasks()
        x = widget.winfo_rootx() + widget.winfo_width() + 8
        y = widget.winfo_rooty() - 4
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        if x + w > sw - 10:
            x = widget.winfo_rootx() - w - 8
        if y + h > sh - 10:
            y = sh - h - 10
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.lift()

    def hide(self, widget=None):
        if self.pinned is not None and self.pinned is not widget:
            return
        if self.win is not None:
            self.win.withdraw()

    def toggle_pin(self, widget, text):
        if self.pinned is widget:
            self.pinned = None
            self.hide()
        else:
            self.pinned = None
            self.show(widget, text)
            self.pinned = widget

    def destroy(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


class SettingsWindow:
    def __init__(self, root, settings_path, template, on_restart, icon_path=None, version=""):
        self.settings_path, self.template, self.on_restart = settings_path, template, on_restart
        self.vars = {}
        values = read_values(settings_path)

        win = self.win = tk.Toplevel(root)
        win.title(f"Voice Typing settings {version}".strip())
        if icon_path:
            try:
                win.iconbitmap(icon_path)
            except Exception:
                pass
        win.resizable(False, False)
        self.tip = Tooltip(win)
        win.bind("<Destroy>", lambda e: self.tip.destroy() if e.widget is win else None)
        body = ttk.Frame(win, padding=14)
        body.grid(sticky="nsew")

        row, section = 0, None
        for sec, key, label, kind, options, help_text in SCHEMA:
            if sec != section:
                section = sec
                ttk.Label(body, text=sec, font=("Segoe UI", 11, "bold")).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(12 if row else 0, 4))
                row += 1
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            current = values.get(key, "")
            if kind == "bool":
                var = tk.BooleanVar(value=current.strip().lower() in ("1", "yes", "true", "on"))
                ttk.Checkbutton(body, variable=var).grid(row=row, column=1, sticky="w")
            elif kind in ("key", "choice"):
                var = tk.StringVar(value=current)
                ttk.Combobox(body, textvariable=var, values=options, width=22).grid(row=row, column=1, sticky="w")
            elif kind == "folder":
                var = tk.StringVar(value=current)
                frame = ttk.Frame(body)
                frame.grid(row=row, column=1, sticky="w")
                ttk.Entry(frame, textvariable=var, width=40).pack(side="left")
                ttk.Button(frame, text="Browse...", command=lambda v=var: self.browse(v)).pack(side="left", padx=(4, 0))
            else:
                var = tk.StringVar(value=current)
                ttk.Entry(body, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
            q = tk.Label(body, text="?", fg="white", bg="#2980b9", font=("Segoe UI", 9, "bold"),
                         width=2, cursor="question_arrow")
            q.grid(row=row, column=2, sticky="w", padx=(10, 0))
            q.bind("<Enter>", lambda e, w=q, t=help_text: self.tip.show(w, t))
            q.bind("<Leave>", lambda e, w=q: self.tip.hide(w))
            q.bind("<Button-1>", lambda e, w=q, t=help_text: self.tip.toggle_pin(w, t))
            self.vars[key] = (kind, var)
            row += 1

        ttk.Label(body, text="Hover a ? for help; click it to keep the help open. Changes take effect when Voice Typing restarts.",
                  foreground="#666666").grid(row=row, column=0, columnspan=3, sticky="w", pady=(14, 6))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Open the settings file", command=lambda: open_path(settings_path)).pack(side="left", padx=(0, 16))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save and restart", command=self.save).pack(side="left", padx=4)

        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_reqwidth()) // 2
        y = (win.winfo_screenheight() - win.winfo_reqheight()) // 2
        win.geometry(f"+{x}+{y}")
        win.lift()
        win.attributes("-topmost", True)
        win.after(300, lambda: win.attributes("-topmost", False))
        win.focus_force()

    def browse(self, var):
        chosen = filedialog.askdirectory(parent=self.win, initialdir=os.path.expandvars(var.get()) or None,
                                         title="Choose a folder")
        if chosen:
            var.set(os.path.normpath(chosen))

    def save(self):
        values = {}
        for key, (kind, var) in self.vars.items():
            if kind == "bool":
                values[key] = "yes" if var.get() else "no"
            elif kind == "int":
                text = var.get().strip()
                if not text.lstrip("-").isdigit():
                    messagebox.showerror("Voice Typing", f"'{text}' is not a whole number.", parent=self.win)
                    return
                values[key] = text
            else:
                values[key] = var.get().strip()
        if values["hotkey"] and values["hotkey"] == values["meeting_hotkey"]:
            messagebox.showerror("Voice Typing", "The dictation key and the meeting key must be different.", parent=self.win)
            return
        if not values["hotkey"]:
            messagebox.showerror("Voice Typing", "The hold-to-talk key cannot be blank.", parent=self.win)
            return
        try:
            write_values(self.settings_path, self.template, values)
        except Exception as e:
            messagebox.showerror("Voice Typing", f"Could not save the settings file:\n{e}", parent=self.win)
            return
        self.win.destroy()
        self.on_restart()
