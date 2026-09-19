"""Win32 SendInput wrappers tuned for GLFW/Minecraft.

Two details here are the difference between "works" and "silently does
nothing", and both come from Minecraft reading input through GLFW rather than
through the normal Windows message path:

* Keys must be sent as **scan codes** (KEYEVENTF_SCANCODE). Virtual-key-only
  events are dropped by a lot of games, Minecraft among them.
* Mouse aim must be sent as **relative** motion (MOUSEEVENTF_MOVE). While the
  cursor is grabbed, SetCursorPos does nothing useful -- the game never reads
  the cursor position, only the deltas.

Windows "Enhance pointer precision" must be OFF, otherwise the OS applies a
non-linear acceleration curve to these deltas and the mouse calibration in
`mcbuilder.calibrate` stops being a single scalar.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover - import guard for dev on Linux
    raise RuntimeError("mcbuilder.input.sendinput requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(*events: INPUT) -> None:
    n = len(events)
    arr = (INPUT * n)(*events)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())


# Scan codes (set 1) for every key the builder touches.
SCAN: dict[str, int] = {
    "escape": 0x01,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A,
    "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21,
    "enter": 0x1C,
    "lshift": 0x2A,
    "lcontrol": 0x1D,
    "space": 0x39,
    "f3": 0x3D,
    "slash": 0x35,
}


def key_down(name: str) -> None:
    scan = SCAN[name]
    ev = INPUT(type=INPUT_KEYBOARD)
    ev.ki = KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, None)
    _send(ev)


def key_up(name: str) -> None:
    scan = SCAN[name]
    ev = INPUT(type=INPUT_KEYBOARD)
    ev.ki = KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None)
    _send(ev)


def mouse_move(dx: int, dy: int) -> None:
    """Relative mouse motion, in raw counts (not pixels)."""
    ev = INPUT(type=INPUT_MOUSE)
    ev.mi = MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, None)
    _send(ev)


def mouse_button(button: str, down: bool) -> None:
    flags = {
        ("left", True): MOUSEEVENTF_LEFTDOWN,
        ("left", False): MOUSEEVENTF_LEFTUP,
        ("right", True): MOUSEEVENTF_RIGHTDOWN,
        ("right", False): MOUSEEVENTF_RIGHTUP,
    }[(button, down)]
    ev = INPUT(type=INPUT_MOUSE)
    ev.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
    _send(ev)


def type_text(text: str) -> None:
    """Type a literal string via unicode key events.

    Used only for chat commands (the `/item replace` hotbar loader), where the
    text is arbitrary and scan codes would mean a full layout mapping. Chat is
    a text field, so the unicode path works fine there even though it would not
    for gameplay keys.
    """
    KEYEVENTF_UNICODE = 0x0004
    for ch in text:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            ev = INPUT(type=INPUT_KEYBOARD)
            ev.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
            _send(ev)
