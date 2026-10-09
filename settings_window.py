"""
Settings window for Voice Typing (tkinter). Opened from the tray icon.

It reads settings.ini, shows every setting as a labeled control with its explanation, and on
Save rewrites settings.ini from SETTINGS_TEMPLATE with the new values (so the comments stay).
Settings only take effect when the app restarts; the window offers to do that.
"""

import configparser
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

KEY_NAMES = ["right alt", "right ctrl", "right shift", "right windows", "left alt", "left ctrl",
             "caps lock", "scroll lock", "pause", "insert", "menu",
             "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"]
LANGUAGES = ["en", "auto", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "ja", "zh", "ko", "ar", "hi"]

# (section, key, label, kind, options, help)   kind: key | text | int | bool | choice | folder
SCHEMA = [
    ("Dictation", "hotkey", "Hold-to-talk key", "key", KEY_NAMES,
     "Hold it, speak, let go. The key stops working for everything else while Voice Typing runs."),
    ("Dictation", "language", "Language", "choice", LANGUAGES,
     "Language spoken, or auto (auto needs an NVIDIA card; the CPU model is English-only)."),
    ("Dictation", "gpu_model", "Speech model with an NVIDIA card", "choice", ["turbo", "small.en", "base.en", "medium", "large-v3"],
     "turbo is the best choice on a graphics card."),
    ("Dictation", "cpu_model", "Speech model without one", "choice", ["base.en", "small.en", "tiny.en"],
     "base.en is quick; small.en is more accurate but slower."),
    ("Dictation", "beeps", "Beeps", "bool", None, "Short tone when recording starts and stops."),
    ("Dictation", "show_overlay", "On-screen status pill", "bool", None, "The little colored pill near the bottom of the screen."),
    ("Dictation", "trailing_space", "Add a space after dictated text", "bool", None, "So the next dictation does not run into it."),

    ("Meetings", "meeting_hotkey", "Record-a-meeting key", "key", KEY_NAMES, "Tap to start, tap to stop."),
    ("Meetings", "meeting_hold_seconds", "Hold the key this many seconds", "int", None,
     "0 = a quick tap starts and stops. 3 or 5 = hold it that long (a countdown shows), so a stray tap does nothing."),
    ("Meetings", "meeting_dir", "Transcripts folder", "folder", None, "Where meeting transcripts go."),
    ("Meetings", "meeting_audio_dir", "Audio folder (optional)", "folder", None,
     "Put the WAV files somewhere else. Blank keeps them next to the transcripts."),
    ("Meetings", "meeting_subfolders", "One folder per meeting", "bool", None,
     "Each meeting gets its own folder holding its transcript and audio."),
    ("Meetings", "meeting_speakers", "Number of speakers", "int", None, "0 = work it out automatically, or force 2, 3, ..."),
    ("Meetings", "meeting_paste_path", "Type the recording's location", "choice", ["stop", "start", "both", "no"],
     "Types the file location where your cursor is when a recording stops (or starts)."),
    ("Meetings", "meeting_open", "When the transcript is ready, open", "choice", ["transcript", "folder", "both", "no"],
     "The transcript in Notepad, the folder with the audio selected, both, or nothing."),
    ("Meetings", "meeting_chunk_seconds", "Live transcript update (seconds)", "int", None,
     "How often the .live.txt file grows during a meeting."),
    ("Meetings", "meeting_threads", "CPU threads for speaker labeling", "int", None, "8 is a good default."),

    ("Transcribing files", "file_transcript_dir", "Transcripts of existing files go to", "folder", None,
     "Blank = next to the file. Right-click the tray icon > Transcribe a file."),
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
        body = ttk.Frame(win, padding=14)
        body.grid(sticky="nsew")

        row, section = 0, None
        for sec, key, label, kind, options, help_text in SCHEMA:
            if sec != section:
                section = sec
                ttk.Label(body, text=sec, font=("Segoe UI", 11, "bold")).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(12 if row else 0, 4))
                row += 1
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
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
                ttk.Entry(frame, textvariable=var, width=44).pack(side="left")
                ttk.Button(frame, text="Browse...", command=lambda v=var: self.browse(v)).pack(side="left", padx=(4, 0))
            else:
                var = tk.StringVar(value=current)
                ttk.Entry(body, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
            ttk.Label(body, text=help_text, foreground="#666666", wraplength=330, justify="left").grid(
                row=row, column=2, sticky="w", padx=(12, 0))
            self.vars[key] = (kind, var)
            row += 1

        ttk.Label(body, text="Changes take effect when Voice Typing restarts.", foreground="#666666").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(14, 6))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Open the settings file", command=lambda: os.startfile(settings_path)).pack(side="left", padx=(0, 16))
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
