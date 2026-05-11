"""File metadata extraction and FolderNode aggregate construction."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from mapper.models.file_node import FileNode, FolderNode

# Extensions considered "documents" for is_document flagging
_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "docx", "doc", "xlsx", "xls", "txt", "csv", "pptx", "ppt",
     "eml", "msg", "png", "jpg", "jpeg"}
)


def _depth_relative(path: str, root: str) -> int:
    """Return folder depth of *path* relative to *root* (root itself = 0)."""
    try:
        rel = Path(path).relative_to(Path(root))
        return len(rel.parts)
    except ValueError:
        return 0


def extract_file_node(full_path: str, root: str) -> FileNode:
    """Extract metadata from a single file and return a :class:`FileNode`."""
    p = Path(full_path)
    st = p.stat()

    ext = p.suffix.lstrip(".").lower() if p.suffix else ""
    modified_ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()

    return FileNode(
        name=p.name,
        path=full_path,
        ext=ext,
        size_bytes=st.st_size,
        modified_ts=modified_ts,
        depth=_depth_relative(full_path, root),
        parent_path=str(p.parent),
        is_document=ext in _DOCUMENT_EXTENSIONS,
    )


def build_folder_nodes(
    root: str,
    folder_map: dict[str, list[FileNode]],
) -> list[FolderNode]:
    """Build :class:`FolderNode` list with subtree aggregates.

    Parameters
    ----------
    root:
        Absolute path to the scan root.
    folder_map:
        Mapping of ``dirpath -> list[FileNode]`` for direct children only,
        as produced by the traversal walk.
    """
    # First pass: create a FolderNode per directory
    nodes: dict[str, FolderNode] = {}
    for dirpath, direct_files in folder_map.items():
        direct_doc = sum(1 for f in direct_files if f.is_document)
        nodes[dirpath] = FolderNode(
            path=dirpath,
            depth=_depth_relative(dirpath, root),
            direct_file_count=len(direct_files),
            subtree_file_count=len(direct_files),  # will accumulate below
            doc_count=direct_doc,
        )

    # Second pass: propagate subtree counts up the directory tree (deepest first)
    sorted_paths = sorted(nodes.keys(), key=lambda p: p.count(os.sep), reverse=True)
    for dirpath in sorted_paths:
        node = nodes[dirpath]
        parent = str(Path(dirpath).parent)
        if parent != dirpath and parent in nodes:
            nodes[parent].subtree_file_count += node.subtree_file_count
            nodes[parent].doc_count += node.doc_count

    return list(nodes.values())
