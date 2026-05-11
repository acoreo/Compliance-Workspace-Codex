"""FileNode and FolderNode dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FileNode:
    """Represents a single file discovered during a scan."""
    name: str
    path: str
    ext: str                  # lowercase, no leading dot
    size_bytes: int
    modified_ts: str          # ISO 8601
    depth: int                # relative to scan root
    parent_path: str
    is_document: bool


@dataclass
class FolderNode:
    """Represents a directory with aggregated file statistics."""
    path: str
    depth: int                # relative to scan root
    direct_file_count: int = 0
    subtree_file_count: int = 0
    doc_count: int = 0
