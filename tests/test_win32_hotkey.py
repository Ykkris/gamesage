"""Integration tests for the Windows global hotkey listener.

No real keypresses are generated: WM_HOTKEY messages are posted directly to
the listener thread, and the hotkeys used (F13-F15) do not exist on physical
keyboards, so registration cannot collide with user shortcuts.
"""

import ctypes
import sys
import threading
import time

import pytest

from companion.input.hotkey import Hotkey, HotkeyRegistrationError
from companion.input.win32_hotkey import WM_HOTKEY, GlobalHotkeyListener

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only hotkey listener"
)


def post_hotkey_message(listener: GlobalHotkeyListener) -> None:
    ctypes.windll.user32.PostThreadMessageW(listener.thread_id, WM_HOTKEY, 1, 0)


def wait_until(condition, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestGlobalHotkeyListener:
    def test_dispatches_hotkey_message_to_callback(self):
        pressed = threading.Event()
        listener = GlobalHotkeyListener(Hotkey.parse("f13"), pressed.set)
        with listener:
            post_hotkey_message(listener)
            assert pressed.wait(2.0), "callback was not invoked"

    def test_registration_conflict_raises_clear_error(self):
        hotkey = Hotkey.parse("ctrl+f14")
        first = GlobalHotkeyListener(hotkey, lambda: None)
        first.start()
        try:
            second = GlobalHotkeyListener(hotkey, lambda: None)
            with pytest.raises(HotkeyRegistrationError) as excinfo:
                second.start()
            assert "already" in str(excinfo.value) or "1409" in str(excinfo.value)
        finally:
            first.stop()

    def test_handler_exception_keeps_listener_alive(self):
        state = {"calls": 0, "recovered": threading.Event()}

        def flaky_handler() -> None:
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("boom")
            state["recovered"].set()

        listener = GlobalHotkeyListener(Hotkey.parse("f15"), flaky_handler)
        with listener:
            post_hotkey_message(listener)
            assert wait_until(lambda: state["calls"] == 1)
            post_hotkey_message(listener)
            assert state["recovered"].wait(2.0), "listener died after handler error"

    def test_stop_is_idempotent(self):
        listener = GlobalHotkeyListener(Hotkey.parse("f13"), lambda: None)
        listener.start()
        listener.stop()
        listener.stop()
