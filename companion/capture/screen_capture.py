"""Windows screen-region capture implemented with mss.

mss performs GDI screen capture (BitBlt) of a physical-pixel region and
provides a proven PNG encoder, with no transitive dependencies. Kept behind
a single function so the capture backend can be swapped without touching
the game-agnostic logic in :mod:`companion.capture.window_capture`.
"""

from __future__ import annotations

import mss
import mss.tools

from .window_capture import CaptureResult, ScreenCaptureError
from .window_detection import Rect


def capture_screen_region(rect: Rect) -> CaptureResult:
    """Capture the screen region described by physical-pixel ``rect``.

    Raises:
        ScreenCaptureError: the screen region could not be captured.
    """
    region = {
        "left": rect.left,
        "top": rect.top,
        "width": rect.width,
        "height": rect.height,
    }
    try:
        with mss.MSS() as sct:
            shot = sct.grab(region)
            png = mss.tools.to_png(shot.rgb, shot.size)
    except Exception as error:  # mss raises assorted low-level errors.
        raise ScreenCaptureError(
            f"Capturing screen region {rect} failed: {error}"
        ) from error
    return CaptureResult(png=png, width=shot.size[0], height=shot.size[1])
