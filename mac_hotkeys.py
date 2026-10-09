"""
macOS global hotkeys for Voice Typing: a Quartz event tap (needs the Accessibility permission).

start(callback) runs the tap in its own thread. The callback gets a sysglue.KeyEvent
(name, down) for the keys listed below and returns True to let the key through or False to
swallow it (the app never sees it). All other keys pass untouched.

Modifier keys arrive as "flags changed" events; the device-specific flag bits tell left from
right. F-keys arrive as normal key down/up events with a key code.
"""

import logging
import threading

from sysglue import KeyEvent

log = logging.getLogger("voice_typing.mac")

# name -> (virtual key code, NX_DEVICE... flag bit that is set while the key is down)
MODIFIERS = {
    "left control": (59, 0x00000001), "left shift": (56, 0x00000002), "right shift": (60, 0x00000004),
    "left command": (55, 0x00000008), "right command": (54, 0x00000010), "left option": (58, 0x00000020),
    "right option": (61, 0x00000040), "right control": (62, 0x00002000), "fn": (63, 0x00800000),
}
KEYS = {"f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
        "f9": 101, "f10": 109, "f11": 103, "f12": 111}
_MOD_BY_CODE = {code: name for name, (code, _) in MODIFIERS.items()}
_KEY_BY_CODE = {code: name for name, code in KEYS.items()}

_state = {"tap": None, "loop": None, "thread": None, "callback": None, "held": set()}


def _handler(proxy, type_, event, refcon):
    import Quartz as Q
    try:
        if type_ in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(_state["tap"], True)
            return event
        keycode = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
        if type_ == Q.kCGEventFlagsChanged:
            name = _MOD_BY_CODE.get(keycode)
            if name is None:
                return event
            down = bool(Q.CGEventGetFlags(event) & MODIFIERS[name][1])
        else:
            name = _KEY_BY_CODE.get(keycode)
            if name is None:
                return event
            down = type_ == Q.kCGEventKeyDown
            if down and Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat):
                return None if name in _state["held"] else event
        if down:
            _state["held"].add(name)
        else:
            _state["held"].discard(name)
        keep = _state["callback"](KeyEvent(name, down))
        return event if keep else None
    except Exception:
        log.exception("hotkey handler failed")
        return event


def start(callback) -> bool:
    """Returns False if the tap could not be created (no Accessibility permission)."""
    import Quartz as Q
    _state["callback"] = callback
    result = {"ok": False}
    ready = threading.Event()

    def run():
        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
                | Q.CGEventMaskBit(Q.kCGEventFlagsChanged))
        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionDefault,
                                 mask, _handler, None)
        if tap is None:
            ready.set()
            return
        _state["tap"] = tap
        source = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = Q.CFRunLoopGetCurrent()
        _state["loop"] = loop
        Q.CFRunLoopAddSource(loop, source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(tap, True)
        result["ok"] = True
        ready.set()
        Q.CFRunLoopRun()

    t = threading.Thread(target=run, name="hotkeys", daemon=True)
    t.start()
    _state["thread"] = t
    ready.wait(5)
    return result["ok"]


def stop():
    import Quartz as Q
    if _state["tap"] is not None:
        Q.CGEventTapEnable(_state["tap"], False)
    if _state["loop"] is not None:
        Q.CFRunLoopStop(_state["loop"])
    _state["tap"] = _state["loop"] = None


def send_cmd_v():
    import Quartz as Q
    for down in (True, False):
        e = Q.CGEventCreateKeyboardEvent(None, 9, down)          # 9 = 'v'
        Q.CGEventSetFlags(e, Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap, e)
