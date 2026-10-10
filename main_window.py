"""
The Voice Typing window: one place for everything the tray menu used to hold.

Sidebar on the left (Recordings, Transcribe a file, Summaries, then the three settings
sections and About); one page on the right; a status line along the bottom. Closing the
window hides it - the app keeps running in the tray, and the tray icon (or the macOS pill)
brings the window back.

The app object it is built on (voice_typing.VoiceTyping) provides:
    version, settings_path, template, icon_path, log_path, notices_path, media_types
    transcript_folders()                      folders to list recordings from
    request_transcribe(paths)                 queue files for transcription
    request_summary(path)                     queue a transcript for a local summary
    summaries_enabled() / set_summaries(bool) the "summarize new recordings" switch
    hotkey, meeting_hotkey, dictation_mode    for the About page
    restart() / quit()
and calls window.event(kind, **data) from its worker threads ("file", "summary", "status").
"""

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import summarize
import sysglue
import transcripts
from settings_window import (ACCENT, BG, CARD, FONT, GREEN, HOVER, LINE, MUTED, SCHEMA, SECTION_NOTES, TEXT,
                             Switch, Tooltip, read_values, template_defaults, write_values)

PROJECT_URL = "https://github.com/grungenut/voice-typing"
SETTINGS_SECTIONS = [s for s in dict.fromkeys(sec for sec, *_ in SCHEMA)]   # Dictation, Meetings, Files


class MainWindow:
    def __init__(self, root, app):
        self.root, self.app = root, app
        self.vars = {}                    # settings key -> (kind, tk var)
        self.rows = []                    # (row frame, help text) for help mode
        self.help_on = False
        self.current = None
        self.recordings = []              # parsed transcript headers, newest first
        self.jobs = {}                    # transcribe page: path -> tree item id
        self.download_cancel = None

        win = self.win = tk.Toplevel(root, bg=BG)
        win.title("Voice Typing")
        win.withdraw()
        if app.icon_path:
            try:
                win.iconbitmap(app.icon_path)
            except Exception:
                pass
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Escape>", lambda e: self.hide())
        win.minsize(900, 600)
        self.tip = Tooltip(win)
        self.style()

        # ---- header -----------------------------------------------------------------
        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=22, pady=(16, 8))
        self.icon_img = None
        png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "voice_typing.png")
        if os.path.exists(png):
            try:
                self.icon_img = tk.PhotoImage(file=png).subsample(2, 2)
                tk.Label(header, image=self.icon_img, bg=BG).pack(side="left", padx=(0, 12))
            except Exception:
                self.icon_img = None
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="Voice Typing", font=(FONT, 15, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        self.page_title = tk.Label(titles, text="", font=(FONT, 9), fg=MUTED, bg=BG)
        self.page_title.pack(anchor="w")
        self.help_btn = tk.Label(header, text="?", font=(FONT, 11, "bold"), fg=ACCENT, bg=CARD, width=3,
                                 cursor="hand2", highlightbackground=LINE, highlightthickness=1, pady=2)
        self.help_btn.pack(side="right")
        self.help_btn.bind("<Button-1>", lambda e: self.toggle_help())
        self.help_hint = tk.Label(header, text="", font=(FONT, 9), fg=MUTED, bg=BG)
        self.help_hint.pack(side="right", padx=(0, 10))

        # ---- body: sidebar + pages ----------------------------------------------------
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=22)
        sidebar = tk.Frame(body, bg=BG)
        sidebar.pack(side="left", fill="y", padx=(0, 18), anchor="n")
        self.pane = tk.Frame(body, bg=BG)
        self.pane.pack(side="left", fill="both", expand=True)
        self.pane.grid_rowconfigure(0, weight=1)
        self.pane.grid_columnconfigure(0, weight=1)

        self.side_items, self.pages = {}, {}
        entries = [("recordings", "Recordings"), ("transcribe", "Transcribe a file"), ("summaries", "Summaries"),
                   ("_", "SETTINGS")] + [("set:" + s, s) for s in SETTINGS_SECTIONS] + [("_", ""), ("about", "About")]
        for key, label in entries:
            if key == "_":
                tk.Label(sidebar, text=label, font=(FONT, 8, "bold"), fg=MUTED, bg=BG, anchor="w", padx=12,
                         pady=(10 if label else 4)).pack(fill="x")
                continue
            item = tk.Label(sidebar, text=label, font=(FONT, 10), fg=TEXT, bg=BG, anchor="w",
                            padx=12, pady=6, width=16, cursor="hand2")
            item.pack(fill="x", pady=1)
            item.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            item.bind("<Enter>", lambda e, k=key: self.side_items[k].config(bg=HOVER) if k != self.current else None)
            item.bind("<Leave>", lambda e, k=key: self.side_items[k].config(bg=BG) if k != self.current else None)
            self.side_items[key] = item

        self.pages["recordings"] = self.build_recordings()
        self.pages["transcribe"] = self.build_transcribe()
        self.pages["summaries"] = self.build_summaries()
        values = template_defaults(app.template)
        values.update(read_values(app.settings_path))
        for sec in SETTINGS_SECTIONS:
            self.pages["set:" + sec] = self.build_settings(sec, values)
        self.pages["about"] = self.build_about()
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        # ---- footer: status line, and the settings buttons when a settings page shows ----
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill="x", padx=22, pady=(10, 14))
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(footer, textvariable=self.status_var, font=(FONT, 9), fg=MUTED, bg=BG, anchor="w").pack(side="left", fill="x", expand=True)
        self.settings_buttons = tk.Frame(footer, bg=BG)
        self.button(self.settings_buttons, "Save and restart", self.save_settings, primary=True).pack(side="right")
        self.button(self.settings_buttons, "Revert", self.revert_settings).pack(side="right", padx=8)
        tk.Label(self.settings_buttons, text="Changes take effect when Voice Typing restarts.", font=(FONT, 9),
                 fg=MUTED, bg=BG).pack(side="right", padx=(0, 14))

        self.show_page("recordings")

    # ---- window ----------------------------------------------------------------------------
    def show(self, page=None):
        if page:
            self.show_page(page)
        elif self.current == "recordings":
            self.refresh_recordings()
        if self.win.state() == "withdrawn":
            self.win.update_idletasks()
            w, h = max(self.win.winfo_reqwidth(), 900), max(self.win.winfo_reqheight(), 600)
            x = (self.win.winfo_screenwidth() - w) // 2
            y = max((self.win.winfo_screenheight() - h) // 2 - 30, 20)
            self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.after(300, lambda: self.win.attributes("-topmost", False))
        self.win.focus_force()

    def hide(self):
        self.tip.hide()
        self.win.withdraw()

    def show_page(self, key):
        self.current = key
        for k, item in self.side_items.items():
            item.config(bg=ACCENT if k == key else BG, fg="white" if k == key else TEXT)
        self.pages[key].lift()
        self.tip.hide()
        titles = {"recordings": "Your meeting recordings and transcripts", "transcribe": "Transcribe an existing recording or video",
                  "summaries": "A title and summary for each recording, made on this computer", "about": f"Version {self.app.version}"}
        self.page_title.config(text=titles.get(key, SECTION_NOTES.get(key[4:], "")))
        if key.startswith("set:"):
            self.settings_buttons.pack(side="right")
        else:
            self.settings_buttons.pack_forget()
        if key == "recordings":
            self.refresh_recordings()
        elif key == "summaries":
            self.refresh_summaries()

    def post(self, fn, *args):
        """Run fn on the Tk thread (safe to call from any thread)."""
        self.root.after(0, lambda: fn(*args))

    def event(self, kind, **data):
        """Called by the app from its worker threads."""
        self.post(self._event, kind, data)

    def _event(self, kind, data):
        if kind == "status":
            self.status_var.set(data.get("text") or "Ready")
        elif kind == "file":
            self.job_update(data["path"], data["status"], data.get("transcript"))
        elif kind == "summary":
            self.status_var.set(data.get("text") or "Ready")
            if data.get("done") and self.current == "recordings":
                self.refresh_recordings(keep=data.get("path"))
            if data.get("error"):
                messagebox.showerror("Voice Typing", data["error"], parent=self.win)

    # ---- look ------------------------------------------------------------------------------
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
        st.configure("App.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=28,
                     borderwidth=0, relief="flat", font=(FONT, 10))
        st.configure("App.Treeview.Heading", background=BG, foreground=MUTED, font=(FONT, 9, "bold"),
                     relief="flat", borderwidth=0, padding=(6, 4))
        st.map("App.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        st.map("App.Treeview.Heading", background=[("active", BG)])
        st.configure("App.Vertical.TScrollbar", background=BG, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                     lightcolor=BG, darkcolor=BG)
        st.configure("App.Horizontal.TProgressbar", background=ACCENT, troughcolor=LINE, bordercolor=LINE,
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        self.win.option_add("*TCombobox*Listbox.font", (FONT, 10))
        self.win.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def button(self, parent, text, command, primary=False):
        b = tk.Label(parent, text=text, font=(FONT, 10, "bold" if primary else "normal"),
                     fg="white" if primary else TEXT, bg=ACCENT if primary else CARD, padx=14, pady=5,
                     cursor="hand2", highlightbackground=ACCENT if primary else "#c7c7cc", highlightthickness=1)
        b.enabled = True
        b.primary = primary

        def click(e):
            if b.enabled:
                command()
        b.bind("<Button-1>", click)
        b.bind("<Enter>", lambda e: b.enabled and b.config(bg="#0071e3" if primary else "#f5f5f7"))
        b.bind("<Leave>", lambda e: b.enabled and b.config(bg=ACCENT if primary else CARD))
        return b

    @staticmethod
    def enable(b, on=True):
        b.enabled = on
        if on:
            b.config(fg="white" if b.primary else TEXT, bg=ACCENT if b.primary else CARD, cursor="hand2")
        else:
            b.config(fg=MUTED, bg=BG, cursor="")

    def card(self, parent, title=None, note=None):
        outer = tk.Frame(parent, bg=BG)
        if title:
            tk.Label(outer, text=title.upper(), font=(FONT, 9, "bold"), fg=MUTED, bg=BG).pack(anchor="w", padx=4)
        if note:
            tk.Label(outer, text=note, font=(FONT, 9), fg=MUTED, bg=BG, wraplength=600, justify="left").pack(
                anchor="w", padx=4, pady=(0, 6))
        card = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="both", expand=True)
        return outer, card

    def link(self, parent, text, command):
        lbl = tk.Label(parent, text=text, font=(FONT, 9, "underline"), fg=ACCENT, bg=parent.cget("bg"), cursor="hand2")
        lbl.bind("<Button-1>", lambda e: command())
        return lbl

    # ---- Recordings page -------------------------------------------------------------------
    def build_recordings(self):
        page = tk.Frame(self.pane, bg=BG)
        top = tk.Frame(page, bg=BG)
        top.pack(fill="x", pady=(0, 8))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_recordings())
        search = ttk.Entry(top, textvariable=self.search_var, width=34, style="Set.TEntry", font=(FONT, 10))
        search.pack(side="left")
        tk.Label(top, text="Search titles, summaries and words spoken", font=(FONT, 9), fg=MUTED, bg=BG).pack(side="left", padx=10)
        self.button(top, "Open folder", lambda: self.open_folder(self.app.transcript_folders()[0])).pack(side="right")
        self.button(top, "Refresh", self.refresh_recordings).pack(side="right", padx=8)

        outer, card = self.card(page)
        outer.pack(fill="both", expand=True)
        cols = ("title", "date", "length", "speakers", "summary")
        self.tree = ttk.Treeview(card, columns=cols, show="headings", style="App.Treeview", selectmode="browse", height=9)
        for col, text, width, anchor in (("title", "Title", 380, "w"), ("date", "Date", 150, "w"), ("length", "Length", 70, "e"),
                                         ("speakers", "Speakers", 70, "e"), ("summary", "Summary", 70, "center")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, minwidth=50, anchor=anchor, stretch=(col == "title"))
        sb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview, style="App.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.tree.bind("<Return>", lambda e: self.open_selected())

        douter, detail = self.card(page)
        douter.pack(fill="x", pady=(10, 0))
        inner = tk.Frame(detail, bg=CARD, padx=14, pady=10)
        inner.pack(fill="x")
        self.detail_title = tk.Label(inner, text="Select a recording", font=(FONT, 11, "bold"), fg=TEXT, bg=CARD,
                                     anchor="w", wraplength=640, justify="left")
        self.detail_title.pack(anchor="w")
        self.detail_meta = tk.Label(inner, text="", font=(FONT, 9), fg=MUTED, bg=CARD, anchor="w", wraplength=640, justify="left")
        self.detail_meta.pack(anchor="w", pady=(2, 6))
        self.detail_text = tk.Text(inner, height=7, wrap="word", font=(FONT, 10), fg=TEXT, bg=CARD, relief="flat",
                                   highlightthickness=0, state="disabled", cursor="arrow")
        self.detail_text.pack(fill="x")
        buttons = tk.Frame(inner, bg=CARD)
        buttons.pack(fill="x", pady=(8, 0))
        self.b_open = self.button(buttons, "Open transcript", self.open_selected, primary=True)
        self.b_open.pack(side="left")
        self.b_play = self.button(buttons, "Play recording", lambda: self.open_recording())
        self.b_play.pack(side="left", padx=8)
        self.b_folder = self.button(buttons, "Show in folder", lambda: self.reveal_selected())
        self.b_folder.pack(side="left")
        self.b_sum = self.button(buttons, "Summarize", self.summarize_selected)
        self.b_sum.pack(side="right")
        self.sum_hint = tk.Label(buttons, text="", font=(FONT, 9), fg=MUTED, bg=CARD)
        self.sum_hint.pack(side="right", padx=(0, 10))
        for b in (self.b_open, self.b_play, self.b_folder, self.b_sum):
            self.enable(b, False)
        return page

    def refresh_recordings(self, keep=None):
        selected = keep or self.selected_path()
        self.recordings = transcripts.find_transcripts(self.app.transcript_folders())
        query = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for info in self.recordings:
            if query:
                hay = (info["title"] + "\n" + info["summary"]).lower()
                if query not in hay:
                    try:
                        with open(info["path"], encoding="utf-8-sig", errors="replace") as f:
                            if query not in f.read().lower():
                                continue
                    except OSError:
                        continue
            when = info["recorded"].strftime("%b %d, %Y  %I:%M %p").replace("  0", "  ") if info["recorded"] else ""
            self.tree.insert("", "end", iid=info["path"], values=(
                info["title"], when, info["length"], info["speakers"], "✓" if info["summary"] else ""))
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.see(selected)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        else:
            self.show_detail()

    def selected_path(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def selected_info(self):
        path = self.selected_path()
        return next((i for i in self.recordings if i["path"] == path), None)

    def show_detail(self):
        info = self.selected_info()
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        if info is None:
            self.detail_title.config(text="No recordings yet" if not self.recordings
                                     else "No matches" if self.search_var.get().strip() else "Select a recording")
            self.detail_meta.config(text=f"Tap {self.app.meeting_hotkey} to record a meeting; its transcript appears here."
                                    if not self.recordings else "")
            for b in (self.b_open, self.b_play, self.b_folder, self.b_sum):
                self.enable(b, False)
            self.sum_hint.config(text="")
        else:
            self.detail_title.config(text=info["title"])
            meta = []
            if info["recorded"]:
                meta.append(info["recorded"].strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " "))
            if info["length"]:
                meta.append(info["length"] + (f", {info['speakers']} speakers" if info["speakers"] else ""))
            meta.append(info["path"])
            self.detail_meta.config(text="  ·  ".join(meta[:2]) + "\n" + meta[-1])
            self.detail_text.insert("1.0", info["summary"] or "No summary yet.")
            self.enable(self.b_open)
            self.enable(self.b_play, bool(info["recording"]) and os.path.exists(info["recording"]))
            self.enable(self.b_folder)
            ready = summarize.status()["ready"]
            self.enable(self.b_sum, ready)
            self.b_sum.config(text="Summarize again" if info["summary"] else "Summarize")
            self.sum_hint.config(text="" if ready else "Download the summary model on the Summaries page")
        self.detail_text.config(state="disabled")

    def open_selected(self):
        info = self.selected_info()
        if info:
            sysglue.open_path(info["path"])

    def open_recording(self):
        info = self.selected_info()
        if info and info["recording"] and os.path.exists(info["recording"]):
            sysglue.open_path(info["recording"])

    def reveal_selected(self):
        info = self.selected_info()
        if info:
            sysglue.reveal_path(info["path"])

    def open_folder(self, folder):
        os.makedirs(folder, exist_ok=True)
        sysglue.open_path(folder)

    def summarize_selected(self):
        info = self.selected_info()
        if info:
            self.status_var.set("Summarizing... (a few minutes on a computer without a graphics card)")
            self.app.request_summary(info["path"])

    # ---- Transcribe page -------------------------------------------------------------------
    def build_transcribe(self):
        page = tk.Frame(self.pane, bg=BG)
        outer, card = self.card(page, "Transcribe a file",
                                "A recording or video becomes a transcript with speaker labels, saved next to the "
                                "file (or in the folder set under Files). MP3, M4A, WAV, MP4, MOV and most other formats.")
        outer.pack(fill="x")
        row = tk.Frame(card, bg=CARD, padx=14, pady=12)
        row.pack(fill="x")
        self.button(row, "Choose a file...", self.pick_files, primary=True).pack(side="left")
        tk.Label(row, text="You can pick several at once; they are done one after another.", font=(FONT, 9),
                 fg=MUTED, bg=CARD).pack(side="left", padx=12)

        jouter, jcard = self.card(page, "This session")
        jouter.pack(fill="both", expand=True, pady=(14, 0))
        self.jobs_tree = ttk.Treeview(jcard, columns=("file", "status"), show="headings", style="App.Treeview", height=8)
        self.jobs_tree.heading("file", text="File", anchor="w")
        self.jobs_tree.heading("status", text="Status", anchor="w")
        self.jobs_tree.column("file", width=360, anchor="w")
        self.jobs_tree.column("status", width=300, anchor="w")
        self.jobs_tree.pack(fill="both", expand=True, padx=1, pady=1)
        self.jobs_tree.bind("<Double-1>", lambda e: self.open_job())
        jb = tk.Frame(page, bg=BG)
        jb.pack(fill="x", pady=(8, 0))
        self.button(jb, "Open transcript", self.open_job).pack(side="left")
        self.button(jb, "Show in folder", lambda: self.open_job(reveal=True)).pack(side="left", padx=8)
        self.job_results = {}
        return page

    def pick_files(self):
        paths = filedialog.askopenfilenames(parent=self.win, title="Transcribe a recording or video",
                                            filetypes=self.app.media_types)
        if paths:
            for p in paths:
                self.job_update(p, "Waiting...")
            self.app.request_transcribe(list(paths))

    def job_update(self, path, status, transcript=None):
        iid = self.jobs.get(path)
        if iid is None:
            iid = self.jobs_tree.insert("", "end", values=(os.path.basename(path), status))
            self.jobs[path] = iid
        else:
            self.jobs_tree.item(iid, values=(os.path.basename(path), status))
        if transcript:
            self.job_results[iid] = transcript

    def open_job(self, reveal=False):
        sel = self.jobs_tree.selection()
        if sel and sel[0] in self.job_results:
            (sysglue.reveal_path if reveal else sysglue.open_path)(self.job_results[sel[0]])

    # ---- Summaries page --------------------------------------------------------------------
    def build_summaries(self):
        page = tk.Frame(self.pane, bg=BG)
        outer, card = self.card(page, "Summaries",
                                "A small language model on this computer reads each transcript and writes a title and "
                                "a summary into it: what it was about, the key points, and any action items. "
                                "Nothing is sent anywhere. The model is a separate download, so you choose whether to have it.")
        outer.pack(fill="x")
        inner = tk.Frame(card, bg=CARD, padx=14, pady=10)
        inner.pack(fill="x")
        self.sum_status = tk.Label(inner, text="", font=(FONT, 10), fg=TEXT, bg=CARD, anchor="w", justify="left")
        self.sum_status.pack(anchor="w")
        tk.Label(inner, text=f"Model: {summarize.MODEL_LABEL}  ·  runs with llama.cpp (MIT)  ·  {summarize.total_download_bytes() / 1e9:.1f} GB on disk",
                 font=(FONT, 9), fg=MUTED, bg=CARD).pack(anchor="w", pady=(2, 8))
        self.progress = ttk.Progressbar(inner, style="App.Horizontal.TProgressbar", length=560, mode="determinate", maximum=1000)
        self.progress_label = tk.Label(inner, text="", font=(FONT, 9), fg=MUTED, bg=CARD, anchor="w")
        brow = tk.Frame(inner, bg=CARD)
        brow.pack(fill="x", pady=(4, 0))
        self.b_download = self.button(brow, "Download the summary model", self.start_download, primary=True)
        self.b_download.pack(side="left")
        self.b_cancel = self.button(brow, "Cancel", self.cancel_download)
        self.b_remove = self.link(brow, "Remove the model from this computer", self.remove_model)

        souter, scard = self.card(page)
        souter.pack(fill="x", pady=(14, 0))
        row = tk.Frame(scard, bg=CARD, padx=14, pady=8)
        row.pack(fill="x")
        tk.Label(row, text="Summarize every new recording automatically", font=(FONT, 10), fg=TEXT, bg=CARD).pack(side="left")
        self.auto_var = tk.BooleanVar(value=self.app.summaries_enabled())
        self.auto_switch = Switch(row, self.auto_var)
        self.auto_switch.pack(side="right")
        self.auto_var.trace_add("write", lambda *a: self.app.set_summaries(bool(self.auto_var.get())))
        tk.Frame(scard, bg=LINE, height=1).pack(fill="x", padx=14)
        tk.Label(scard, text="When on, a meeting's transcript opens once its summary is written (a minute or a few, "
                             "depending on the computer and the length). Older recordings can be summarized from the "
                             "Recordings page.", font=(FONT, 9), fg=MUTED, bg=CARD, wraplength=600, justify="left",
                 padx=14, pady=8).pack(anchor="w")
        return page

    def refresh_summaries(self):
        st = summarize.status()
        if st["ready"]:
            self.sum_status.config(text="Installed and ready.", fg=GREEN)
            self.b_download.pack_forget()
            self.b_remove.pack(side="left")
        else:
            part = st["partial_bytes"] or st["model_bytes"]
            self.sum_status.config(text="Not installed." + (f"  A partial download ({part / 1e9:.2f} GB) will be resumed." if part else ""), fg=TEXT)
            self.b_remove.pack_forget()
            if self.download_cancel is None:
                self.b_download.pack(side="left")

    def start_download(self):
        if self.download_cancel is not None:
            return
        self.download_cancel = threading.Event()
        self.b_download.pack_forget()
        self.b_cancel.pack(side="left")
        self.progress.pack(fill="x", pady=(6, 2), before=self.b_download.master)
        self.progress_label.pack(anchor="w", before=self.b_download.master)
        self.progress["value"] = 0
        self.progress_label.config(text="Starting...")

        def progress(label, fraction):
            self.post(self._download_progress, label, fraction)

        def work():
            try:
                summarize.download(progress, self.download_cancel)
                self.post(self._download_done, None)
            except summarize.Canceled:
                self.post(self._download_done, "canceled")
            except Exception as e:
                self.post(self._download_done, f"The download failed: {e}")

        threading.Thread(target=work, daemon=True, name="summary-download").start()

    def _download_progress(self, label, fraction):
        self.progress["value"] = int(fraction * 1000)
        self.progress_label.config(text=label)

    def _download_done(self, error):
        self.download_cancel = None
        self.b_cancel.pack_forget()
        self.progress.pack_forget()
        self.progress_label.pack_forget()
        self.refresh_summaries()
        if error and error != "canceled":
            messagebox.showerror("Voice Typing", error, parent=self.win)
        if self.current == "recordings":
            self.show_detail()

    def cancel_download(self):
        if self.download_cancel is not None:
            self.download_cancel.set()

    def remove_model(self):
        if messagebox.askyesno("Voice Typing", "Remove the summary model and its runtime from this computer?", parent=self.win):
            summarize.remove()
            self.refresh_summaries()

    # ---- Settings pages --------------------------------------------------------------------
    def build_settings(self, section, values):
        page = tk.Frame(self.pane, bg=BG)
        outer, card = self.card(page, section, SECTION_NOTES.get(section, ""))
        outer.pack(fill="x")
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
                ttk.Entry(row, textvariable=var, width=6, justify="right", style="Set.TEntry", font=(FONT, 10)).pack(side="right")
            self.vars[key] = (kind, var)
            self.rows.append((row, help_text))
            for widget in [row] + row.winfo_children():
                widget.bind("<Enter>", lambda e, r=row, t=help_text: self.tip.show(r, t) if self.help_on else None, add="+")
                widget.bind("<Leave>", lambda e: self.tip.hide_soon() if self.help_on else None, add="+")
        return page

    def toggle_help(self):
        self.help_on = not self.help_on
        self.help_btn.config(bg=ACCENT if self.help_on else CARD, fg="white" if self.help_on else ACCENT)
        self.help_hint.config(text="Rest the pointer on a setting to see what it does" if self.help_on else "")
        for row, _ in self.rows:
            row.config(cursor="question_arrow" if self.help_on else "")
        if self.help_on and not (self.current or "").startswith("set:"):
            self.show_page("set:" + SETTINGS_SECTIONS[0])
        if not self.help_on:
            self.tip.hide()

    def browse(self, var):
        chosen = filedialog.askdirectory(parent=self.win, initialdir=os.path.expandvars(var.get()) or None,
                                         title="Choose a folder")
        if chosen:
            var.set(os.path.normpath(chosen))

    def revert_settings(self):
        values = template_defaults(self.app.template)
        values.update(read_values(self.app.settings_path))
        for key, (kind, var) in self.vars.items():
            current = values.get(key, "")
            if kind == "bool":
                var.set(current.strip().lower() in ("1", "yes", "true", "on"))
            else:
                var.set(current)

    def save_settings(self):
        values = read_values(self.app.settings_path)        # keeps keys no page shows (summaries)
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
            write_values(self.app.settings_path, self.app.template, values)
        except Exception as e:
            messagebox.showerror("Voice Typing", f"Could not save the settings file:\n{e}", parent=self.win)
            return
        self.hide()
        self.app.restart()

    # ---- About page ------------------------------------------------------------------------
    def build_about(self):
        page = tk.Frame(self.pane, bg=BG)
        outer, card = self.card(page, "About")
        outer.pack(fill="x")
        inner = tk.Frame(card, bg=CARD, padx=14, pady=12)
        inner.pack(fill="x")
        tk.Label(inner, text=f"Voice Typing {self.app.version}", font=(FONT, 12, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        verb = "Tap" if self.app.dictation_mode == "toggle" else "Hold"
        tk.Label(inner, text=f"{verb} {self.app.hotkey} to dictate where the cursor is.  Tap {self.app.meeting_hotkey} to "
                             f"record a meeting.\nEverything runs on this computer; nothing is sent anywhere.",
                 font=(FONT, 10), fg=TEXT, bg=CARD, justify="left").pack(anchor="w", pady=(4, 10))
        row = tk.Frame(inner, bg=CARD)
        row.pack(anchor="w")
        self.button(row, "View log", lambda: sysglue.open_path(self.app.log_path)).pack(side="left")
        self.button(row, "Open settings file", lambda: sysglue.open_path(self.app.settings_path)).pack(side="left", padx=8)
        self.button(row, "Open transcripts folder", lambda: self.open_folder(self.app.transcript_folders()[0])).pack(side="left")
        links = tk.Frame(inner, bg=CARD)
        links.pack(anchor="w", pady=(12, 0))
        self.link(links, "Project page and new versions", lambda: webbrowser.open(PROJECT_URL + "/releases")).pack(side="left")
        if self.app.notices_path and os.path.exists(self.app.notices_path):
            self.link(links, "Third-party notices", lambda: sysglue.open_path(self.app.notices_path)).pack(side="left", padx=16)

        qouter, qcard = self.card(page)
        qouter.pack(fill="x", pady=(14, 0))
        qrow = tk.Frame(qcard, bg=CARD, padx=14, pady=10)
        qrow.pack(fill="x")
        tk.Label(qrow, text="Stop Voice Typing. The hotkeys stop working until it is started again.",
                 font=(FONT, 9), fg=MUTED, bg=CARD).pack(side="left")
        self.button(qrow, "Quit Voice Typing", self.app.quit).pack(side="right")
        return page
