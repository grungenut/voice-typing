"""
A minimal Windows notification-area (tray) icon using only ctypes - no third-party library,
so nothing with a copyleft license is pulled into the exe.

    tray = Tray("Voice Typing", "voice_typing.ico", [("Open settings", fn), None, ("Quit", fn2)])
    tray.start()      # runs its own message loop on a background thread
    tray.stop()       # removes the icon and ends that thread

Left-click opens the window (on_open); right-click shows the menu. Callbacks run on the tray thread, so they
should only do thread-safe things (open a file, put a message on a queue).
"""

import ctypes
import ctypes.wintypes as w
import logging
import threading

log = logging.getLogger("voice_typing.tray")

user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32

WM_USER, WM_COMMAND, WM_CLOSE, WM_DESTROY, WM_NULL = 0x0400, 0x0111, 0x0010, 0x0002, 0x0000
WM_TIMER = 0x0113
RETRY_TIMER_ID = 7
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
WM_TRAY = WM_USER + 1
NIM_ADD, NIM_DELETE = 0x0, 0x2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
IDI_APPLICATION = 32512

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.LoadImageW.restype = w.HANDLE
user32.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
user32.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
user32.RegisterWindowMessageW.restype = w.UINT
user32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [w.HWND, ctypes.c_size_t]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON)]


class Tray:
    def __init__(self, tooltip, icon_path, items, on_open=None):
        self.tooltip, self.icon_path, self.items = tooltip[:127], icon_path, items
        self.on_open = on_open                      # left click; the menu stays on right click
        self.hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._taskbar_created = None               # set in _run; messages can arrive before that
        self._added, self._attempts = False, 0
        self._wndproc = WNDPROC(self._on_message)   # keep a reference or it gets collected

    # ---- public ----------------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # ---- internals -------------------------------------------------------------------
    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "VoiceTypingTray"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            if kernel32.GetLastError() != 1410:          # ERROR_CLASS_ALREADY_EXISTS
                log.error("tray: RegisterClass failed %d", kernel32.GetLastError())
                self._ready.set()
                return
        self.hwnd = user32.CreateWindowExW(0, "VoiceTypingTray", "Voice Typing", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            log.error("tray: CreateWindow failed %d", kernel32.GetLastError())
            self._ready.set()
            return
        self._icon = user32.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE) \
            if self.icon_path else None
        if not self._icon:
            self._icon = user32.LoadIconW(None, w.LPCWSTR(IDI_APPLICATION))
        self._nid = NOTIFYICONDATAW()
        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._nid.hWnd = self.hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAY
        self._nid.hIcon = self._icon
        self._nid.szTip = self.tooltip
        # Explorer broadcasts this when the taskbar (re)starts; icons added before that are lost.
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._added = False
        self._attempts = 0
        self._add_icon()
        self._ready.set()
        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _add_icon(self):
        """Add the icon; if the taskbar is not there yet (typical when started at sign-in),
        keep retrying on a timer: every 2 s for two minutes, then every 15 s."""
        self._attempts += 1
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid)):
            self._added = True
            user32.KillTimer(self.hwnd, RETRY_TIMER_ID)
            if self._attempts > 1:
                log.info("tray icon added after %d attempts", self._attempts)
            return
        if self._attempts == 1:
            log.warning("tray: Shell_NotifyIcon failed (taskbar not ready?) - will keep trying")
        user32.SetTimer(self.hwnd, RETRY_TIMER_ID, 2000 if self._attempts < 60 else 15000, None)

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        for i, item in enumerate(self.items):
            if item is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                user32.AppendMenuW(menu, MF_STRING, i + 1, item[0])
        pt = w.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)             # so the menu closes when focus moves
        choice = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                       pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if choice:
            try:
                self.items[choice - 1][1]()
            except Exception:
                log.exception("tray menu action failed")

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and (lparam & 0xFFFF) in (WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU):
            if (lparam & 0xFFFF) == WM_LBUTTONUP and self.on_open:
                try:
                    self.on_open()
                except Exception:
                    log.exception("tray open action failed")
            else:
                self._show_menu()
            return 0
        if msg == WM_TIMER and wparam == RETRY_TIMER_ID:
            if not self._added:
                self._add_icon()
            else:
                user32.KillTimer(hwnd, RETRY_TIMER_ID)
            return 0
        if msg == self._taskbar_created:
            log.info("tray: taskbar restarted - re-adding the icon")
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._added, self._attempts = False, 0
            self._add_icon()
            return 0
        if msg == WM_CLOSE:
            user32.KillTimer(hwnd, RETRY_TIMER_ID)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
