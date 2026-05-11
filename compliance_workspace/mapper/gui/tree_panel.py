"""TreePanel — QTreeWidget displaying the scanned folder/file hierarchy."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget
from PySide6.QtCore import Qt

from mapper.models.file_node import FileNode, FolderNode
from mapper.models.scan import ScanResult


def _to_display_path(path: str) -> str:
    """Convert a path to Windows-native backslash format for display."""
    return path.replace("/", os.sep)


class TreePanel(QTreeWidget):
    """Left panel: hierarchical folder tree with file children."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Files (subtree)"])
        self.setColumnWidth(0, 380)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)

    def populate(self, result: ScanResult) -> None:
        """Rebuild the tree from a :class:`ScanResult`."""
        self.clear()

        if not result.tree:
            return

        # Sort folder nodes by path length so parents come first
        sorted_folders = sorted(result.tree, key=lambda n: len(n.path))

        # Map path -> QTreeWidgetItem for folders
        folder_items: dict[str, QTreeWidgetItem] = {}

        for folder in sorted_folders:
            display = _to_display_path(folder.path)
            label = os.path.basename(folder.path) or display
            item = QTreeWidgetItem([label, str(folder.subtree_file_count)])
            item.setData(0, Qt.ItemDataRole.UserRole, folder.path)

            parent_path = str(os.path.dirname(folder.path))
            if parent_path in folder_items:
                folder_items[parent_path].addChild(item)
            else:
                self.addTopLevelItem(item)

            folder_items[folder.path] = item

        # Build a lookup: parent_path -> [FileNode]
        files_by_parent: dict[str, list[FileNode]] = {}
        for f in result.files:
            files_by_parent.setdefault(f.parent_path, []).append(f)

        # Attach file children to their parent folder items
        for folder_path, f_item in folder_items.items():
            for file_node in files_by_parent.get(folder_path, []):
                child = QTreeWidgetItem([_to_display_path(file_node.name), ""])
                child.setData(0, Qt.ItemDataRole.UserRole, file_node.path)
                f_item.addChild(child)

        # Expand top-level items by default
        self.expandToDepth(0)
