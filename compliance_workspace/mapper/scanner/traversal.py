"""Recursive directory traversal with robust Windows error handling."""
from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from mapper.models.file_node import FileNode, FolderNode
from mapper.models.scan import ScanError, ScanResult
from mapper.scanner.metadata import extract_file_node, build_folder_nodes


def _is_reparse_point(path: str) -> bool:
    """Return True if *path* is an NTFS junction or reparse point (Windows only)."""
    try:
        st = os.lstat(path)
        # st_file_attributes and FILE_ATTRIBUTE_REPARSE_POINT are both Windows-only.
        # Check both guards so this is safe on macOS/Linux.
        if hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT") and hasattr(st, "st_file_attributes"):
            return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return False
    except OSError:
        return False


def _normalise_scope_key(root: str) -> str:
    """Convert an absolute path to the canonical scope_key format.

    Windows:  C:\\EHS\\Policies  ->  C:/EHS/Policies
    POSIX:    /home/user/docs   ->  /home/user/docs
    """
    p = Path(root).resolve()
    parts = p.parts
    if len(parts) == 0:
        return str(p)

    # On Windows parts[0] is like 'C:\\'
    drive = p.drive  # 'C:' on Windows, '' on POSIX
    if drive:
        # Uppercase drive letter, strip trailing backslash from drive part
        key = drive.upper().rstrip("\\") + "/" + "/".join(parts[1:])
    else:
        key = "/".join(parts).lstrip("/")
        key = "/" + key if str(p).startswith("/") else key

    # Remove trailing slash
    return key.rstrip("/") or "/"


def scan_directory(root_path: str, mode: str = "broad") -> ScanResult:
    """Walk *root_path* recursively and return a :class:`ScanResult`.

    Parameters
    ----------
    root_path:
        Absolute path to the directory to scan.
    mode:
        ``'broad'`` — scan everything under root.
        ``'targeted'`` — same walk, reserved for future filtering extensions.

    Error handling
    --------------
    All filesystem errors are caught, logged as :class:`ScanError` entries, and
    the walk continues.  No exception propagates to the caller.
    """
    start = time.perf_counter()
    errors: list[ScanError] = []
    raw_files: list[FileNode] = []
    folder_map: dict[str, list[FileNode]] = {}  # dirpath -> direct files

    root = Path(root_path).resolve()
    root_str = str(root)

    def _log(path: str, exc: Exception) -> None:
        errors.append(
            ScanError(
                path=path,
                error_type=type(exc).__name__,
                error_msg=str(exc),
            )
        )

    for dirpath, dirnames, filenames in os.walk(root_str, followlinks=False, onerror=None):
        # --- reparse / junction check ---
        if dirpath != root_str and _is_reparse_point(dirpath):
            errors.append(
                ScanError(
                    path=dirpath,
                    error_type="ReparsePoint",
                    error_msg="Skipped NTFS junction or reparse point.",
                )
            )
            dirnames.clear()
            continue

        # --- symlink directories (belt-and-suspenders) ---
        try:
            if dirpath != root_str and Path(dirpath).is_symlink():
                errors.append(
                    ScanError(
                        path=dirpath,
                        error_type="Symlink",
                        error_msg="Skipped symbolic link (informational).",
                    )
                )
                dirnames.clear()
                continue
        except OSError as exc:
            _log(dirpath, exc)
            dirnames.clear()
            continue

        # Filter dirnames in-place to skip inaccessible sub-directories early
        accessible_dirs: list[str] = []
        for d in dirnames:
            full_d = os.path.join(dirpath, d)
            if _is_reparse_point(full_d):
                errors.append(
                    ScanError(
                        path=full_d,
                        error_type="ReparsePoint",
                        error_msg="Skipped NTFS junction or reparse point.",
                    )
                )
                continue
            try:
                if Path(full_d).is_symlink():
                    errors.append(
                        ScanError(
                            path=full_d,
                            error_type="Symlink",
                            error_msg="Skipped symbolic link (informational).",
                        )
                    )
                    continue
            except OSError as exc:
                _log(full_d, exc)
                continue
            accessible_dirs.append(d)
        dirnames[:] = accessible_dirs

        direct_files: list[FileNode] = []

        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                node = extract_file_node(fpath, root_str)
                direct_files.append(node)
                raw_files.append(node)
            except PermissionError as exc:
                _log(fpath, exc)
            except OSError as exc:
                # Covers broken network paths, MAX_PATH violations, etc.
                _log(fpath, exc)
            except Exception as exc:  # noqa: BLE001
                _log(fpath, exc)

        folder_map[dirpath] = direct_files

    # Build FolderNode aggregates
    tree = build_folder_nodes(root_str, folder_map)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return ScanResult(
        tree=tree,
        files=raw_files,
        errors=errors,
        duration_ms=elapsed_ms,
    )
