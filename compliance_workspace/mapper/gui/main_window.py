"""MainWindow — two-panel QMainWindow shell with toolbar and status bar."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

from mapper.gui.summary_panel import SummaryPanel
from mapper.gui.tree_panel import TreePanel
from mapper.models.scan import ScanResult


def _to_display_path(path: str) -> str:
    return path.replace("/", os.sep)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _ScanWorker(QThread):
    """Runs the directory scan on a background thread."""

    finished = Signal(object)  # emits ScanResult

    def __init__(self, root_path: str, mode: str) -> None:
        super().__init__()
        self._root_path = root_path
        self._mode = mode

    def run(self) -> None:
        from mapper.scanner.traversal import scan_directory
        result = scan_directory(self._root_path, self._mode)
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._current_mode = "broad"
        self._worker: _ScanWorker | None = None

        self.setWindowTitle("Compliance Discovery Workspace")
        self.resize(1200, 700)

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        path_label = QLabel("Path: ")
        toolbar.addWidget(path_label)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Enter directory path…")
        self._path_edit.setMinimumWidth(350)
        toolbar.addWidget(self._path_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        toolbar.addWidget(browse_btn)

        toolbar.addSeparator()

        self._broad_radio = QRadioButton("Broad")
        self._broad_radio.setChecked(True)
        self._broad_radio.toggled.connect(lambda checked: self._set_mode("broad", checked))
        toolbar.addWidget(self._broad_radio)

        self._targeted_radio = QRadioButton("Targeted")
        self._targeted_radio.toggled.connect(lambda checked: self._set_mode("targeted", checked))
        toolbar.addWidget(self._targeted_radio)

        toolbar.addSeparator()

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self._scan_btn)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        self._tree_panel = TreePanel()
        self._summary_panel = SummaryPanel()

        splitter.addWidget(self._tree_panel)
        splitter.addWidget(self._summary_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.setCentralWidget(splitter)

    def _build_statusbar(self) -> None:
        self._status_label = QLabel("Ready.")
        status_bar = QStatusBar(self)
        status_bar.addWidget(self._status_label)
        self.setStatusBar(status_bar)

    # ------------------------------------------------------------------
    # Slots / actions
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if chosen:
            self._path_edit.setText(_to_display_path(chosen))

    def _set_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self._current_mode = mode

    def _start_scan(self) -> None:
        raw_path = self._path_edit.text().strip()
        if not raw_path:
            self._status_label.setText("Please enter or browse to a directory.")
            return

        root = str(Path(raw_path).resolve())
        if not Path(root).is_dir():
            self._status_label.setText(f"Not a valid directory: {_to_display_path(root)}")
            return

        self._scan_btn.setEnabled(False)
        self._status_label.setText("Scanning… 0 files found")

        self._worker = _ScanWorker(root, self._current_mode)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._scan_btn.setEnabled(True)

        total_files = len(result.files)
        total_folders = len(result.tree)
        skipped = len(result.errors)
        self._status_label.setText(
            f"Scan complete — {total_folders:,} folders, "
            f"{total_files:,} files, {skipped:,} skipped "
            f"({result.duration_ms:,} ms)"
        )

        root_path = str(Path(self._path_edit.text().strip()).resolve())
        scan_ts = datetime.now(tz=timezone.utc).isoformat()
        mode = self._current_mode

        # Render GUI
        self._tree_panel.populate(result)
        self._summary_panel.populate(result, root_path, mode, scan_ts)

        # Persist to DB
        self._persist(result, root_path, mode, scan_ts)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(
        self,
        result: ScanResult,
        root_path: str,
        mode: str,
        scan_ts: str,
    ) -> None:
        import sqlite3
        from mapper.db.schema import create_tables
        from mapper.db.store import (
            write_scan,
            write_file_nodes,
            write_folder_nodes,
            write_errors,
        )
        from mapper.models.scan import ScanRecord
        from mapper.scanner.traversal import _normalise_scope_key

        conn = sqlite3.connect(self._db_path)
        try:
            create_tables(conn)
            record = ScanRecord(
                scan_id=None,
                scope_key=_normalise_scope_key(root_path),
                root_path=root_path,
                mode=mode,
                scan_ts=scan_ts,
                file_count=len(result.files),
                folder_count=len(result.tree),
                skipped_count=len(result.errors),
                duration_ms=result.duration_ms,
            )
            scan_id = write_scan(conn, record)
            write_file_nodes(conn, scan_id, result.files)
            write_folder_nodes(conn, scan_id, result.tree)
            write_errors(conn, scan_id, result.errors)
        finally:
            conn.close()
