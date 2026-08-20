"""Thin ctypes wrappers over the Windows APIs used for window/process enumeration.

Windows-only module, implemented with the standard library only (no external
dependency). Import it from platform-independent code lazily or behind a
``sys.platform`` check; importing on another OS raises ``ImportError``.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from .window_detection import ProcessInfo, Rect, WindowInfo

if sys.platform != "win32":
    raise ImportError("companion.capture.win32_api is only available on Windows.")

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_DWMWA_EXTENDED_FRAME_BOUNDS = 9

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

_psapi.EnumProcesses.argtypes = [
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_psapi.EnumProcesses.restype = wintypes.BOOL

_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL

_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT


def _enable_dpi_awareness() -> None:
    """Best-effort DPI awareness so window bounds are physical pixels.

    Without this, Windows virtualizes coordinates of DPI-aware game windows
    when this Python process is not DPI-aware, yielding scaled bounds. The
    call fails harmlessly if the host process already set an awareness level.
    """
    try:
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
        if result != 0:  # E_ACCESSDENIED when already set: fall back silently.
            _user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        _user32.SetProcessDPIAware()


_enable_dpi_awareness()


def _win_error(action: str) -> OSError:
    """Build an OSError from the last Win32 error, with context."""
    error = ctypes.WinError(ctypes.get_last_error())
    error.strerror = f"{action} failed: {error.strerror}"
    return error


def list_processes() -> list[ProcessInfo]:
    """List running processes with their lowercase executable base name.

    Processes that cannot be opened (e.g. protected system processes) are
    skipped rather than raising.
    """
    max_pids = 4096
    pid_array = (wintypes.DWORD * max_pids)()
    bytes_returned = wintypes.DWORD()
    if not _psapi.EnumProcesses(
        pid_array, ctypes.sizeof(pid_array), ctypes.byref(bytes_returned)
    ):
        raise _win_error("EnumProcesses")

    count = bytes_returned.value // ctypes.sizeof(wintypes.DWORD)
    processes: list[ProcessInfo] = []
    for pid in pid_array[:count]:
        if pid == 0:
            continue
        exe_name = _process_image_name(pid)
        if exe_name is not None:
            processes.append(ProcessInfo(pid=pid, exe_name=exe_name))
    return processes


def _process_image_name(pid: int) -> str | None:
    """Return the lowercase executable base name of ``pid``, or None."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return os.path.basename(buffer.value).lower()
    finally:
        _kernel32.CloseHandle(handle)


def list_visible_windows() -> list[WindowInfo]:
    """List visible top-level windows that have a non-empty title."""
    windows: list[WindowInfo] = []

    def collect(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        title_length = _user32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return True

        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        _user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)

        windows.append(
            WindowInfo(
                hwnd=int(hwnd),
                pid=pid.value,
                title=title_buffer.value,
                rect=_window_rect(hwnd),
                minimized=bool(_user32.IsIconic(hwnd)),
            )
        )
        return True

    callback = _WNDENUMPROC(collect)
    if not _user32.EnumWindows(callback, 0):
        raise _win_error("EnumWindows")
    return windows


def _window_rect(hwnd: int) -> Rect:
    """Window bounds in physical pixels, preferring the DWM frame bounds.

    ``GetWindowRect`` includes invisible DWM resize borders on Windows 10/11,
    so ``DWMWA_EXTENDED_FRAME_BOUNDS`` is used when available. For minimized
    windows both report placeholder coordinates; the ``minimized`` flag on
    :class:`WindowInfo` is the reliable signal.
    """
    if not _user32.IsIconic(hwnd):
        frame = wintypes.RECT()
        result = _dwmapi.DwmGetWindowAttribute(
            hwnd,
            _DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(frame),
            ctypes.sizeof(frame),
        )
        if result == 0 and frame.right > frame.left and frame.bottom > frame.top:
            return Rect(
                left=frame.left, top=frame.top, right=frame.right, bottom=frame.bottom
            )

    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise _win_error("GetWindowRect")
    return Rect(left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom)
