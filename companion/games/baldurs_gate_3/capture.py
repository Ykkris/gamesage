"""Screenshot saving for Baldur's Gate 3.

Only the file naming is game-specific; the capture itself is the generic
pipeline in ``companion.capture``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from companion.capture.window_capture import CaptureResult

#: Default directory for saved screenshots (relative to the working directory).
SCREENSHOTS_DIR = Path("screenshots")


def save_capture(
    result: CaptureResult, directory: Path | None = None
) -> Path:
    """Save a capture as ``bg3-<timestamp>.png`` under ``directory``."""
    target_dir = directory if directory is not None else SCREENSHOTS_DIR
    target_dir.mkdir(exist_ok=True)
    stem = f"bg3-{datetime.now():%Y%m%d-%H%M%S-%f}"
    path = target_dir / f"{stem}.png"
    suffix = 1
    while path.exists():
        path = target_dir / f"{stem}-{suffix}.png"
        suffix += 1
    return result.save(path)
