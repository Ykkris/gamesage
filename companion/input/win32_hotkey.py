"""Windows global hotkey listener built on RegisterHotKey (ctypes only).

RegisterHotKey associates the hotkey with the calling thread, so the
listener runs a dedicated thread that registers the hotkey and pumps
thread messages, dispatching ``WM_HOTKEY`` to the callback. Presses are
handled serially in that thread: a slow callback delays the next press
instead of overlapping it, and MOD_NOREPEAT suppresses key auto-repeat.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from collections.abc import Callable

from .hotkey import Hotkey, HotkeyRegistrationError, virtual_key_code

if sys.platform != "win32":
    raise ImportError("companion.input.win32_hotkey is only available on Windows.")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.GetMessageW.restype = ctypes.c_int
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class GlobalHotkeyListener:
    """Call ``on_press`` whenever the global ``hotkey`` is pressed.

    Works regardless of which application has focus. Use as a context
    manager, or call :meth:`start` / :meth:`stop` explicitly.
    """

    def __init__(self, hotkey: Hotkey, on_press: Callable[[], None]) -> None:
        self._hotkey = hotkey
        self._on_press = on_press
        self._hotkey_id = 1  # Arbitrary; scoped to the listener thread.
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._registration_error: HotkeyRegistrationError | None = None

    @property
    def hotkey(self) -> Hotkey:
        return self._hotkey

    @property
    def thread_id(self) -> int:
        """Windows thread id of the listener (0 until started)."""
        return self._thread_id

    def start(self) -> None:
        """Register the hotkey and begin listening.

        Raises:
            HotkeyRegistrationError: the OS refused the hotkey (unknown key,
                or the combination is already taken by another application).
        """
        if self._thread is not None:
            raise RuntimeError("Listener already started.")
        self._thread = threading.Thread(
            target=self._run, name="gamesage-hotkey-listener", daemon=True
        )
        self._thread.start()
        self._ready.wait()
        if self._registration_error is not None:
            self._thread.join()
            raise self._registration_error

    def stop(self) -> None:
        """Unregister the hotkey and end the listener thread. Idempotent."""
        if self._thread is None or not self._thread.is_alive():
            return
        _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(5.0)
        if self._thread.is_alive():
            print(
                "Warning: hotkey listener did not stop within 5 seconds.",
                file=sys.stderr,
            )

    def __enter__(self) -> "GlobalHotkeyListener":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def _run(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        try:
            self._registration_error = self._register()
        finally:
            self._ready.set()
        if self._registration_error is not None:
            return
        try:
            self._pump_messages()
        finally:
            _user32.UnregisterHotKey(None, self._hotkey_id)

    def _register(self) -> HotkeyRegistrationError | None:
        vk = virtual_key_code(self._hotkey.key)
        if vk is None:
            return HotkeyRegistrationError(
                f"Could not register global hotkey {self._hotkey}: "
                f"key {self._hotkey.key!r} has no known virtual-key code."
            )
        modifiers = MOD_NOREPEAT
        for name in self._hotkey.modifiers:
            modifiers |= _MODIFIERS[name]
        if not _user32.RegisterHotKey(None, self._hotkey_id, modifiers, vk):
            error = ctypes.WinError(ctypes.get_last_error())
            return HotkeyRegistrationError(
                f"Could not register global hotkey {self._hotkey}: {error}. "
                "Another application may already be using it."
            )
        return None

    def _pump_messages(self) -> None:
        message = wintypes.MSG()
        while True:
            result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0:  # WM_QUIT: clean shutdown.
                return
            if result == -1:
                error = ctypes.WinError(ctypes.get_last_error())
                print(f"Hotkey listener failed: {error}", file=sys.stderr)
                return
            if message.message == WM_HOTKEY:
                try:
                    self._on_press()
                except Exception as error:  # Keep listening on handler failures.
                    print(f"Hotkey handler failed: {error}", file=sys.stderr)
