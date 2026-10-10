"""
The few things Voice Typing does differently on Windows and macOS, in one place:
where data lives, opening files, beeps, pasting, and the global hotkey hook.

Windows: the `keyboard` library (hook + Ctrl+V), winsound, os.startfile, explorer.exe.
macOS:   a Quartz event tap (mac_hotkeys.py) + Cmd+V, a tone through sounddevice, `open`.
"""

import os
import subprocess
import sys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# subprocess flag so helper programs (ffmpeg) do not flash a console window on Windows
NO_WINDOW = {"creationflags": 0x08000000} if IS_WIN else {}

if IS_MAC:
    DEFAULT_HOTKEY, DEFAULT_MEETING_HOTKEY = "right option", "right command"
    KEY_NAME_HELP = ("right option, right command, right control, right shift, left option, left command,\n"
                     "; left control, fn, or f1 ... f12 (on a laptop, F-keys may need the Fn key)")
    KEY_NAMES = ["right option", "right command", "right control", "right shift", "left option",
                 "left command", "left control", "fn", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8",
                 "f9", "f10", "f11", "f12"]
    PASTE_KEYS = "Cmd+V"
    TEXT_EDITOR = "TextEdit"
else:
    DEFAULT_HOTKEY, DEFAULT_MEETING_HOTKEY = "right alt", "right ctrl"
    KEY_NAME_HELP = ("right alt, right ctrl, right shift, right windows, left alt, left ctrl,\n"
                     "; caps lock, scroll lock, pause, insert, menu, f1 ... f12, or a plain letter or number")
    KEY_NAMES = ["right alt", "right ctrl", "right shift", "right windows", "left alt", "left ctrl",
                 "caps lock", "scroll lock", "pause", "insert", "menu",
                 "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"]
    PASTE_KEYS = "Ctrl+V"
    TEXT_EDITOR = "Notepad"


class KeyEvent:
    __slots__ = ("name", "down")

    def __init__(self, name, down):
        self.name, self.down = name, down


def data_dir() -> str:
    if IS_WIN:
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VoiceTyping")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support/VoiceTyping")
    else:
        base = os.path.expanduser("~/.voicetyping")
    os.makedirs(base, exist_ok=True)
    return base


def total_ram_gb() -> float:
    """Physical memory in GB (0 if unknown)."""
    try:
        if IS_WIN:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            total = m.ullTotalPhys
        elif IS_MAC:
            import subprocess
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        else:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        import math
        return float(math.ceil(total / 2 ** 30))        # "32 GB", the way the PC is sold
    except Exception:
        return 0.0


def open_path(path: str):
    """Open a file with its default program, or a folder in Explorer / Finder."""
    if IS_WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["open", path])


def reveal_path(path: str):
    """Open the folder holding `path` with that file selected."""
    if IS_WIN:
        subprocess.Popen(["explorer.exe", "/select,", path])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def beep(freq: int, ms: int):
    if IS_WIN:
        import winsound
        winsound.Beep(freq, ms)
        return
    import numpy as np
    import sounddevice as sd
    rate = 44100
    t = np.arange(int(rate * ms / 1000)) / rate
    tone = (0.25 * np.sin(2 * np.pi * freq * t)).astype("float32")
    fade = min(len(tone) // 8, 400)
    if fade:
        tone[:fade] *= np.linspace(0, 1, fade)
        tone[-fade:] *= np.linspace(1, 0, fade)
    try:
        sd.play(tone, rate, blocking=True)
    except Exception:
        pass


def send_paste():
    if IS_WIN:
        import keyboard
        keyboard.send("ctrl+v")
    elif IS_MAC:
        import mac_hotkeys
        mac_hotkeys.send_cmd_v()


_MAC_ALIASES = {"right alt": "right option", "left alt": "left option", "alt": "left option",
                "right ctrl": "right control", "left ctrl": "left control", "ctrl": "left control",
                "right windows": "right command", "left windows": "left command", "windows": "left command",
                "right cmd": "right command", "left cmd": "left command", "cmd": "left command",
                "option": "left option", "command": "left command", "control": "left control",
                "shift": "left shift"}


def normalize_key_name(name: str) -> str:
    name = " ".join(name.strip().lower().split())
    if IS_WIN:
        import keyboard
        return keyboard.normalize_name(name)
    return _MAC_ALIASES.get(name, name)


def key_name_variants(name: str) -> set:
    """All event names that mean this key. Windows reports the left modifiers as plain
    alt / ctrl / shift, so 'left alt' must match 'alt' too."""
    name = normalize_key_name(name)
    names = {name}
    if IS_WIN and name.startswith("left ") and name != "left windows":
        names.add(name[5:])
    return names


def install_hook(callback) -> bool:
    """Start the global key hook. `callback(KeyEvent) -> keep` (False swallows the key).
    Returns False when the OS refused (macOS without Accessibility permission)."""
    if IS_WIN:
        import keyboard

        def wrap(event):
            return callback(KeyEvent(event.name, event.event_type == keyboard.KEY_DOWN))

        keyboard.hook(wrap, suppress=True)
        return True
    if IS_MAC:
        import mac_hotkeys
        return mac_hotkeys.start(callback)
    return False


def remove_hooks():
    if IS_WIN:
        import keyboard
        keyboard.unhook_all()
    elif IS_MAC:
        import mac_hotkeys
        mac_hotkeys.stop()


def accessibility_prompt():
    """macOS: ask the system to show the Accessibility permission prompt. Returns trusted?"""
    if not IS_MAC:
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
    except Exception:
        return False
