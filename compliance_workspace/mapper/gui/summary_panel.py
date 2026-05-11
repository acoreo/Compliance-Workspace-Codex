"""SummaryPanel — right panel showing scan statistics and skipped paths."""
from __future__ import annotations

import os
from collections import Counter

from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from mapper.models.scan import ScanResult


def _to_display_path(path: str) -> str:
    return path.replace("/", os.sep)


class SummaryPanel(QScrollArea):
    """Right panel: scope info, counts, type breakdown, skipped paths."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scope_label = QLabel("No scan performed yet.")
        self._scope_label.setWordWrap(True)
        self._scope_label.setTextFormat(Qt.TextFormat.RichText)

        self._counts_label = QLabel("")
        self._counts_label.setWordWrap(True)
        self._counts_label.setTextFormat(Qt.TextFormat.RichText)

        self._types_label = QLabel("File types:")
        self._types_label.setTextFormat(Qt.TextFormat.RichText)

        self._skipped_label = QLabel("Skipped paths:")
        self._skipped_list = QListWidget()
        self._skipped_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        for widget in (
            self._scope_label,
            self._counts_label,
            self._types_label,
            self._skipped_label,
            self._skipped_list,
        ):
            self._layout.addWidget(widget)

        self.setWidget(inner)

    def populate(
        self,
        result: ScanResult,
        root_path: str,
        mode: str,
        scan_ts: str,
    ) -> None:
        """Refresh all summary widgets from a completed scan."""
        display_root = _to_display_path(root_path)

        self._scope_label.setText(
            f"<b>Scan scope</b><br>"
            f"Root: {display_root}<br>"
            f"Mode: {mode.capitalize()}<br>"
            f"Timestamp: {scan_ts}"
        )

        total_files = len(result.files)
        total_folders = len(result.tree)
        total_skipped = len(result.errors)
        duration_s = result.duration_ms / 1000

        self._counts_label.setText(
            f"<b>Results</b><br>"
            f"Folders: {total_folders:,}<br>"
            f"Files: {total_files:,}<br>"
            f"Skipped: {total_skipped:,}<br>"
            f"Duration: {duration_s:.2f}s"
        )

        # File type breakdown
        ext_counter: Counter[str] = Counter(
            f.ext if f.ext else "(no ext)" for f in result.files
        )
        type_lines = "<b>File types</b><br>" + "<br>".join(
            f"{ext}: {count:,}"
            for ext, count in ext_counter.most_common()
        )
        self._types_label.setText(type_lines or "<b>File types</b><br>(none)")

        # Skipped paths
        self._skipped_list.clear()
        for err in result.errors:
            self._skipped_list.addItem(
                f"[{err.error_type}] {_to_display_path(err.path)}"
            )
        self._skipped_label.setText(
            f"<b>Skipped paths</b> ({total_skipped:,}):"
        )
        # Resize list widget to content height (cap at 300 px)
        row_h = self._skipped_list.sizeHintForRow(0)
        if row_h > 0:
            self._skipped_list.setFixedHeight(
                min(300, row_h * max(1, total_skipped) + 4)
            )
