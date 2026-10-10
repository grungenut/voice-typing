"""
Settings window for Voice Typing (tkinter). Opened from the tray icon (Windows) or the
Voice Typing pill menu (macOS).

Styled after macOS System Settings: a sidebar of sections on the left, one white card of
settings on the right, switches for yes/no settings. One "?" button in the corner turns help
mode on; while it is on, resting the pointer on any setting shows what it does. Save rewrites
settings.ini from SETTINGS_TEMPLATE with the new values (comments stay) and restarts the app.
"""

import configparser
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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


class SettingsWindow:
    def __init__(self, root, settings_path, template, on_restart, icon_path=None, version=""):
        self.settings_path, self.template, self.on_restart = settings_path, template, on_restart
        self.vars = {}
        self.rows = []                        # (row frame, help text)
        self.help_on = False
        self.current = None
        values = template_defaults(template)
        values.update(read_values(settings_path))   # a setting missing from the file shows its default

        win = self.win = tk.Toplevel(root, bg=BG)
        win.title("Voice Typing Settings")
        if icon_path:
            try:
                win.iconbitmap(icon_path)
            except Exception:
                pass
        win.resizable(False, False)
        self.tip = Tooltip(win)
        win.bind("<Destroy>", lambda e: self.tip.destroy() if e.widget is win else None)
        self.style()

        # ---- header: icon, title, the one help button ---------------------------------
        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=22, pady=(18, 10))
        self.icon_img = None
        png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "voice_typing.png")
        if os.path.exists(png):
            try:
                self.icon_img = tk.PhotoImage(file=png).subsample(2, 2)   # 64 px -> 32 px
                tk.Label(header, image=self.icon_img, bg=BG).pack(side="left", padx=(0, 12))
            except Exception:
                self.icon_img = None
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="Voice Typing", font=(FONT, 15, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(titles, text=f"Settings  ·  version {version}" if version else "Settings",
                 font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w")
        self.help_btn = tk.Label(header, text="?", font=(FONT, 11, "bold"), fg=ACCENT, bg=CARD, width=3,
                                 cursor="hand2", highlightbackground=LINE, highlightthickness=1, pady=2)
        self.help_btn.pack(side="right")
        self.help_btn.bind("<Button-1>", lambda e: self.toggle_help())
        self.help_hint = tk.Label(header, text="", font=(FONT, 9), fg=MUTED, bg=BG)
        self.help_hint.pack(side="right", padx=(0, 10))

        # ---- body: sidebar + one card per section ------------------------------------
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=22)
        sidebar = tk.Frame(body, bg=BG)
        sidebar.pack(side="left", fill="y", padx=(0, 16), anchor="n")
        self.pane = tk.Frame(body, bg=BG)
        self.pane.pack(side="left", fill="both", expand=True, anchor="n")

        sections = []
        for sec, *_ in SCHEMA:
            if sec not in sections:
                sections.append(sec)
        self.side_items, self.cards = {}, {}
        for sec in sections:
            item = tk.Label(sidebar, text=sec, font=(FONT, 10), fg=TEXT, bg=BG, anchor="w",
                            padx=12, pady=6, width=14, cursor="hand2")
            item.pack(fill="x", pady=1)
            item.bind("<Button-1>", lambda e, s=sec: self.select(s))
            item.bind("<Enter>", lambda e, s=sec: self.side_items[s].config(bg=HOVER) if s != self.current else None)
            item.bind("<Leave>", lambda e, s=sec: self.side_items[s].config(bg=BG) if s != self.current else None)
            self.side_items[sec] = item
            self.cards[sec] = self.build_card(sec, values)
            self.cards[sec].grid(row=0, column=0, sticky="new")
        self.select(sections[0])

        # ---- footer ------------------------------------------------------------------
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill="x", padx=22, pady=(14, 18))
        tk.Label(footer, text="Changes take effect when Voice Typing restarts.", font=(FONT, 9), fg=MUTED, bg=BG).pack(side="left")
        self.button(footer, "Save and restart", self.save, primary=True).pack(side="right")
        self.button(footer, "Cancel", win.destroy).pack(side="right", padx=8)
        link = tk.Label(footer, text="Open settings file", font=(FONT, 9, "underline"), fg=ACCENT, bg=BG, cursor="hand2")
        link.pack(side="right", padx=(0, 14))
        link.bind("<Button-1>", lambda e: open_path(settings_path))

        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_reqwidth()) // 2
        y = (win.winfo_screenheight() - win.winfo_reqheight()) // 2
        win.geometry(f"+{x}+{max(y, 20)}")
        win.lift()
        win.attributes("-topmost", True)
        win.after(300, lambda: win.attributes("-topmost", False))
        win.focus_force()

    # ---- look ----------------------------------------------------------------------------
    def style(self):
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Set.TCombobox", fieldbackground=CARD, background=CARD, bordercolor=LINE,
                     lightcolor=CARD, darkcolor=CARD, arrowcolor=MUTED, foreground=TEXT, padding=3)
        st.map("Set.TCombobox", fieldbackground=[("readonly", CARD)], selectbackground=[("readonly", CARD)],
               selectforeground=[("readonly", TEXT)], bordercolor=[("focus", ACCENT)])
        st.configure("Set.TEntry", fieldbackground=CARD, bordercolor=LINE, lightcolor=CARD, darkcolor=CARD,
                     foreground=TEXT, padding=3)
        st.map("Set.TEntry", bordercolor=[("focus", ACCENT)])
        self.win.option_add("*TCombobox*Listbox.font", (FONT, 10))
        self.win.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def button(self, parent, text, command, primary=False):
        b = tk.Label(parent, text=text, font=(FONT, 10, "bold" if primary else "normal"),
                     fg="white" if primary else TEXT, bg=ACCENT if primary else CARD, padx=14, pady=5,
                     cursor="hand2", highlightbackground=ACCENT if primary else "#c7c7cc", highlightthickness=1)
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg="#0071e3" if primary else "#f5f5f7"))
        b.bind("<Leave>", lambda e: b.config(bg=ACCENT if primary else CARD))
        return b

    def build_card(self, section, values):
        outer = tk.Frame(self.pane, bg=BG)
        tk.Label(outer, text=section.upper(), font=(FONT, 9, "bold"), fg=MUTED, bg=BG).pack(anchor="w", padx=4)
        tk.Label(outer, text=SECTION_NOTES.get(section, ""), font=(FONT, 9), fg=MUTED, bg=BG,
                 wraplength=520, justify="left").pack(anchor="w", padx=4, pady=(0, 6))
        card = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x")
        first = True
        for sec, key, label, kind, options, help_text in SCHEMA:
            if sec != section:
                continue
            if not first:
                tk.Frame(card, bg=LINE, height=1).pack(fill="x", padx=14)
            first = False
            row = tk.Frame(card, bg=CARD, padx=14, pady=8)
            row.pack(fill="x")
            tk.Label(row, text=label, font=(FONT, 10), fg=TEXT, bg=CARD, anchor="w").pack(side="left", padx=(0, 24))
            current = values.get(key, "")
            if kind == "bool":
                var = tk.BooleanVar(value=current.strip().lower() in ("1", "yes", "true", "on"))
                Switch(row, var).pack(side="right")
            elif kind in ("key", "choice"):
                var = tk.StringVar(value=current)
                ttk.Combobox(row, textvariable=var, values=options, width=18, style="Set.TCombobox",
                             font=(FONT, 10), state="normal" if kind == "key" else "readonly").pack(side="right")
            elif kind == "folder":
                var = tk.StringVar(value=current)
                self.button(row, "Choose...", lambda v=var: self.browse(v)).pack(side="right", padx=(6, 0))
                ttk.Entry(row, textvariable=var, width=34, style="Set.TEntry", font=(FONT, 10)).pack(side="right")
            else:
                var = tk.StringVar(value=current)
                ttk.Entry(row, textvariable=var, width=6, justify="right", style="Set.TEntry",
                          font=(FONT, 10)).pack(side="right")
            self.vars[key] = (kind, var)
            self.rows.append((row, help_text))
            for widget in [row] + row.winfo_children():
                widget.bind("<Enter>", lambda e, r=row, t=help_text: self.tip.show(r, t) if self.help_on else None, add="+")
                widget.bind("<Leave>", lambda e: self.tip.hide_soon() if self.help_on else None, add="+")
        return outer

    def select(self, section):
        self.current = section
        for sec, item in self.side_items.items():
            item.config(bg=ACCENT if sec == section else BG, fg="white" if sec == section else TEXT)
        self.cards[section].lift()
        self.tip.hide()

    def toggle_help(self):
        self.help_on = not self.help_on
        self.help_btn.config(bg=ACCENT if self.help_on else CARD, fg="white" if self.help_on else ACCENT)
        self.help_hint.config(text="Rest the pointer on a setting to see what it does" if self.help_on else "")
        for row, _ in self.rows:
            row.config(cursor="question_arrow" if self.help_on else "")
        if not self.help_on:
            self.tip.hide()

    # ---- actions -------------------------------------------------------------------------
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
            messagebox.showerror("Voice Typing", "The dictation key cannot be blank.", parent=self.win)
            return
        try:
            write_values(self.settings_path, self.template, values)
        except Exception as e:
            messagebox.showerror("Voice Typing", f"Could not save the settings file:\n{e}", parent=self.win)
            return
        self.win.destroy()
        self.on_restart()
