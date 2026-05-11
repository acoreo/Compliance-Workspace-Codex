"""ScanDialog — inline toolbar widgets for path entry and mode selection.

This module exposes ScanDialog as a lightweight QWidget that can be embedded
in a toolbar or used as a standalone dialog.  For the MVP it is used inline
inside MainWindow's toolbar.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class ScanDialog(QDialog):
    """Modal dialog for entering a scan path and choosing a mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Scan")
        self.setMinimumWidth(500)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Enter or browse to a directory…")

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_btn)

        self._broad_radio = QRadioButton("Broad")
        self._targeted_radio = QRadioButton("Targeted")
        self._broad_radio.setChecked(True)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._broad_radio)
        mode_row.addWidget(self._targeted_radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Path:", path_row)
        form.addRow("Mode:", mode_row)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Directory")
        if chosen:
            self._path_edit.setText(chosen)

    @property
    def selected_path(self) -> str:
        return self._path_edit.text().strip()

    @property
    def selected_mode(self) -> str:
        return "targeted" if self._targeted_radio.isChecked() else "broad"
