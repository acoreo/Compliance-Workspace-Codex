"""Read and write operations against the SQLite workspace database."""
from __future__ import annotations

import sqlite3
from typing import Sequence

from mapper.models.file_node import FileNode, FolderNode
from mapper.models.scan import ScanError, ScanRecord


def write_scan(conn: sqlite3.Connection, record: ScanRecord) -> int:
    """Insert a ScanRecord row and return the generated scan_id."""
    cur = conn.execute(
        """
        INSERT INTO scans
            (scope_key, root_path, mode, scan_ts,
             file_count, folder_count, skipped_count, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.scope_key,
            record.root_path,
            record.mode,
            record.scan_ts,
            record.file_count,
            record.folder_count,
            record.skipped_count,
            record.duration_ms,
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def write_file_nodes(
    conn: sqlite3.Connection,
    scan_id: int,
    file_nodes: Sequence[FileNode],
) -> None:
    """Bulk-insert FileNode rows for a given scan."""
    rows = [
        (
            scan_id,
            n.name,
            n.path,
            n.ext,
            n.size_bytes,
            n.modified_ts,
            n.depth,
            n.parent_path,
            int(n.is_document),
        )
        for n in file_nodes
    ]
    conn.executemany(
        """
        INSERT INTO file_nodes
            (scan_id, name, full_path, extension, size_bytes,
             modified_ts, depth, parent_path, is_document)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def write_folder_nodes(
    conn: sqlite3.Connection,
    scan_id: int,
    folder_nodes: Sequence[FolderNode],
) -> None:
    """Bulk-insert FolderNode rows for a given scan."""
    rows = [
        (
            scan_id,
            n.path,
            n.depth,
            n.direct_file_count,
            n.subtree_file_count,
            n.doc_count,
            None,   # is_hotspot — RESERVED
            None,   # hotspot_signals — RESERVED
        )
        for n in folder_nodes
    ]
    conn.executemany(
        """
        INSERT INTO folder_nodes
            (scan_id, full_path, depth, direct_file_count,
             subtree_file_count, doc_count, is_hotspot, hotspot_signals)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def write_errors(
    conn: sqlite3.Connection,
    scan_id: int,
    errors: Sequence[ScanError],
) -> None:
    """Bulk-insert ScanError rows for a given scan."""
    rows = [(scan_id, e.path, e.error_type, e.error_msg) for e in errors]
    conn.executemany(
        """
        INSERT INTO scan_errors (scan_id, path, error_type, error_msg)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def get_scans(conn: sqlite3.Connection) -> list[ScanRecord]:
    """Return all scan records ordered by scan_ts descending."""
    rows = conn.execute(
        """
        SELECT scan_id, scope_key, root_path, mode, scan_ts,
               file_count, folder_count, skipped_count, duration_ms
        FROM scans
        ORDER BY scan_ts DESC
        """
    ).fetchall()
    return [
        ScanRecord(
            scan_id=r[0],
            scope_key=r[1],
            root_path=r[2],
            mode=r[3],
            scan_ts=r[4],
            file_count=r[5],
            folder_count=r[6],
            skipped_count=r[7],
            duration_ms=r[8],
        )
        for r in rows
    ]
