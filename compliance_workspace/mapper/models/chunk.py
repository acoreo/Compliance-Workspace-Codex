"""Chunk, ChunkMetadata, and VSLArtifact dataclasses for Phase 2."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ChunkType(str, Enum):
    standard_overview = "standard_overview"
    requirement = "requirement"
    sub_requirement = "sub_requirement"
    sub_sub_requirement = "sub_sub_requirement"
    measure = "measure"
    attachment_obligation = "attachment_obligation"
    attachment_measure = "attachment_measure"
    definition = "definition"
    applicability = "applicability"
    reference_guidance = "reference_guidance"
    vsl_artifact = "vsl_artifact"


@dataclass
class ChunkMetadata:
    standard_id: str
    document_title: str
    chunk_type: str                     # ChunkType enum value
    official_citation_path: str        # e.g. "CIP-007-6 -> R2 -> R2.1 -> M1"
    parent_chunk_id: Optional[str]
    child_chunk_ids: List[str]
    requirement_id: Optional[str]      # e.g. "R2"
    subrequirement_path: Optional[str] # e.g. "R2.1"
    measure_id: Optional[str]
    attachment_id: Optional[str]
    source_location: str               # file path
    effective_date: Optional[str]
    version: Optional[str]
    applicability_tags: List[str]
    # VSL-specific (only for vsl_artifact chunks)
    governing_requirement_reference: Optional[str]
    vsl_row_id: Optional[str]
    vsl_level: Optional[str]
    # Evidence descriptors
    expected_evidence: List[str]       # e.g. ["procedure", "log", "screenshot"]


@dataclass
class Chunk:
    chunk_id: str                      # UUID
    scan_id: int                       # FK to Phase 1 scans table
    file_node_id: int                  # FK to Phase 1 file_nodes table
    text: str                          # raw extracted text for this chunk
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None  # populated by semantic.py


@dataclass
class VSLArtifact:
    vsl_id: str
    chunk_id: str                      # FK to the vsl_artifact chunk
    standard_id: str
    requirement_ref: str
    vsl_level: str                     # "High", "Medium", "Lower", "Severe"
    vsl_text: str
    row_id: str
