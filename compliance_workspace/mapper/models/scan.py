"""Scan-level dataclasses: ScanRecord, ScanScope, ScanError, ScanResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mapper.models.file_node import FileNode, FolderNode


@dataclass
class ScanScope:
    """Describes the scope of a scan request."""
    root_path: str
    mode: str          # 'broad' | 'targeted'
    scope_key: str     # normalised key, e.g. C:/EHS/Policies


@dataclass
class ScanError:
    """Records a path that could not be accessed during a scan."""
    path: str
    error_type: str    # e.g. 'PermissionError', 'OSError'
    error_msg: str


@dataclass
class ScanRecord:
    """Persisted record of a completed scan stored in the DB."""
    scan_id: Optional[int]   # None before insert
    scope_key: str
    root_path: str
    mode: str
    scan_ts: str             # ISO 8601 datetime
    file_count: int
    folder_count: int
    skipped_count: int
    duration_ms: int


@dataclass
class ScanResult:
    """Full in-memory result returned by the scanner."""
    tree: list[FolderNode] = field(default_factory=list)
    files: list[FileNode] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)
    duration_ms: int = 0
