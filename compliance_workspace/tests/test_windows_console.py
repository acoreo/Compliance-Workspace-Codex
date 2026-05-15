"""Guards for Windows console-safe verbose output."""
from __future__ import annotations

from pathlib import Path


def test_reasoning_verbose_output_is_ascii_safe():
    """Reason runs are redirected to logs on Windows cp1252 consoles."""
    root = Path(__file__).resolve().parents[1]
    checked = [
        root / "mapper" / "reasoning" / "assessor.py",
        root / "mapper" / "reasoning" / "runner.py",
    ]
    for path in checked:
        text = path.read_text(encoding="utf-8")
        try:
            text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AssertionError(f"{path} contains non-ASCII console text: {exc}") from exc
