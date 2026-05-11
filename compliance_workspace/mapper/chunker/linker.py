"""Parent-child relationship builder for chunks.

Builds relationships based on citation path hierarchy and semantic
linkages (measure→requirement, VSL→requirement, attachment→standard,
definition→term-containing chunks).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List

from mapper.models.chunk import Chunk, ChunkType


@dataclass
class ChunkRelationship:
    parent_chunk_id: str
    child_chunk_id: str
    relationship_type: str  # "parent_child" | "requirement_to_measure" |
                            # "requirement_to_vsl" | "requirement_to_attachment" |
                            # "term_dependency"


def build_relationships(chunks: List[Chunk]) -> List[ChunkRelationship]:
    """Derive all inter-chunk relationships and update chunk metadata in place.

    Mutates parent_chunk_id and child_chunk_ids on each Chunk.
    Returns a flat list of ChunkRelationship records for DB insertion.
    """
    relationships: List[ChunkRelationship] = []

    # Build lookup indexes
    path_to_chunk: dict[str, Chunk] = {}
    req_by_req_id: dict[str, Chunk] = {}
    standard_chunks: dict[str, Chunk] = {}

    for c in chunks:
        path_to_chunk[c.metadata.official_citation_path] = c
        if (
            c.metadata.chunk_type == ChunkType.requirement.value
            and c.metadata.requirement_id
        ):
            req_by_req_id[c.metadata.requirement_id] = c
        if c.metadata.chunk_type == ChunkType.standard_overview.value:
            standard_chunks[c.metadata.standard_id] = c

    # --- 1. Hierarchy: parent_child via citation path prefix ---
    for c in chunks:
        path = c.metadata.official_citation_path
        parts = path.split(" -> ")
        if len(parts) <= 1:
            continue
        parent_path = " -> ".join(parts[:-1])
        parent = path_to_chunk.get(parent_path)
        if parent and parent.chunk_id != c.chunk_id:
            relationships.append(ChunkRelationship(
                parent_chunk_id=parent.chunk_id,
                child_chunk_id=c.chunk_id,
                relationship_type="parent_child",
            ))
            c.metadata.parent_chunk_id = parent.chunk_id
            if c.chunk_id not in parent.metadata.child_chunk_ids:
                parent.metadata.child_chunk_ids.append(c.chunk_id)

    # --- 2. Measures → parent requirement ---
    for c in chunks:
        if (
            c.metadata.chunk_type == ChunkType.measure.value
            and c.metadata.requirement_id
        ):
            parent_req = req_by_req_id.get(c.metadata.requirement_id)
            if parent_req:
                relationships.append(ChunkRelationship(
                    parent_chunk_id=parent_req.chunk_id,
                    child_chunk_id=c.chunk_id,
                    relationship_type="requirement_to_measure",
                ))

    # --- 3. VSL artifacts → governing requirement ---
    for c in chunks:
        if c.metadata.chunk_type == ChunkType.vsl_artifact.value:
            gov_ref = c.metadata.governing_requirement_reference
            if gov_ref:
                parent_req = req_by_req_id.get(gov_ref)
                if parent_req:
                    relationships.append(ChunkRelationship(
                        parent_chunk_id=parent_req.chunk_id,
                        child_chunk_id=c.chunk_id,
                        relationship_type="requirement_to_vsl",
                    ))

    # --- 4. Attachment chunks → standard overview ---
    for c in chunks:
        if c.metadata.chunk_type in (
            ChunkType.attachment_obligation.value,
            ChunkType.attachment_measure.value,
        ):
            parent_std = standard_chunks.get(c.metadata.standard_id)
            if parent_std and parent_std.chunk_id != c.metadata.parent_chunk_id:
                relationships.append(ChunkRelationship(
                    parent_chunk_id=parent_std.chunk_id,
                    child_chunk_id=c.chunk_id,
                    relationship_type="requirement_to_attachment",
                ))

    # --- 5. Definition chunks → chunks containing the defined term ---
    definition_chunks = [
        c for c in chunks if c.metadata.chunk_type == ChunkType.definition.value
    ]
    non_definition_chunks = [
        c for c in chunks if c.metadata.chunk_type != ChunkType.definition.value
    ]
    for defn in definition_chunks:
        # Extract the first word of the definition text as the term
        words = defn.text.split()
        if not words:
            continue
        term = words[0].strip(".,;:()")
        if len(term) < 3:
            continue
        term_lower = term.lower()
        for target in non_definition_chunks:
            if term_lower in target.text.lower():
                relationships.append(ChunkRelationship(
                    parent_chunk_id=defn.chunk_id,
                    child_chunk_id=target.chunk_id,
                    relationship_type="term_dependency",
                ))

    return relationships


def write_relationships_to_db(
    conn: sqlite3.Connection,
    relationships: List[ChunkRelationship],
) -> None:
    """Batch-insert chunk relationships into the chunk_relationships table."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO chunk_relationships
            (parent_chunk_id, child_chunk_id, relationship_type)
        VALUES (?, ?, ?)
        """,
        [
            (r.parent_chunk_id, r.child_chunk_id, r.relationship_type)
            for r in relationships
        ],
    )
    conn.commit()
