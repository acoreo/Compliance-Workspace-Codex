"""Chunk boundary detection and chunk_type assignment.

Converts ParsedUnit objects from the parser into Chunk objects,
applying boundary rules and the long-content fallback.
"""
from __future__ import annotations

import re
import uuid
from typing import List, Optional

from mapper.models.chunk import Chunk, ChunkMetadata, ChunkType
from mapper.chunker.parser import ParsedUnit

# ---------------------------------------------------------------------------
# Long-content fallback constants
# ---------------------------------------------------------------------------

_MAX_TOKENS = 2000
_CHARS_PER_TOKEN = 4          # conservative approximation
_MAX_CHARS = _MAX_TOKENS * _CHARS_PER_TOKEN

# Subdivide only on numbered/lettered clause boundaries present in source
_CLAUSE_SPLIT_RE = re.compile(
    r'(?=(?:^|\n)\s*(?:\d+\.\s|[a-z]\.\s|[ivxlcdmIVXLCDM]+\.\s))',
    re.MULTILINE,
)

# Standard ID pattern for inference
_STANDARD_RE = re.compile(
    r'\b(CIP|FAC|MOD|PRC|TPL|COM|EOP|INT|IRO|PER|TOP|VAR|NUC|BAL|GOV|MNT|ORG|PBR|STA|UST)'
    r'-\d{3}-\d+\b'
)


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _subdivide(text: str) -> List[str]:
    """Split long text on clause boundaries; return non-empty parts."""
    parts = _CLAUSE_SPLIT_RE.split(text)
    result = [p.strip() for p in parts if p.strip()]
    return result if result else [text]


def _infer_standard_id(units: List[ParsedUnit]) -> str:
    for u in units:
        m = _STANDARD_RE.search(u.text)
        if m:
            return m.group(0)
    return "UNKNOWN"


def _build_citation_path(standard_id: str, unit: ParsedUnit) -> str:
    parts = [standard_id]
    if unit.detected_id and unit.detected_id != standard_id:
        parts.append(unit.detected_id)
    return " -> ".join(parts)


def build_chunks(
    units: List[ParsedUnit],
    scan_id: int,
    file_node_id: int,
    source_location: str,
    document_title: str = "",
    standard_id: str = "",
) -> List[Chunk]:
    """Convert ParsedUnit list into Chunk objects.

    Boundary rules (each produces a new chunk):
    - Change in requirement ID
    - Change in hierarchy level
    - Change in chunk_type
    - Attachment or VSL boundary

    Long-content fallback: units exceeding 2000 tokens are subdivided
    only along numbered/lettered clause boundaries in the source.
    """
    if not standard_id:
        standard_id = _infer_standard_id(units)

    chunks: List[Chunk] = []
    _last_req_id: Optional[str] = None  # most recently seen requirement ID

    for unit in units:
        # Apply long-content fallback
        if _estimate_tokens(unit.text) > _MAX_TOKENS:
            sub_texts = _subdivide(unit.text)
        else:
            sub_texts = [unit.text]

        for part_text in sub_texts:
            if not part_text.strip():
                continue

            citation_path = _build_citation_path(standard_id, unit)
            chunk_type = unit.detected_type
            det_id = unit.detected_id

            req_id: Optional[str] = None
            subreq_path: Optional[str] = None
            measure_id: Optional[str] = None
            attachment_id: Optional[str] = None

            if chunk_type == ChunkType.requirement.value:
                req_id = det_id
                _last_req_id = det_id
            elif chunk_type == ChunkType.sub_requirement.value:
                subreq_path = det_id
                if det_id and "." in det_id:
                    req_id = det_id.split(".")[0]
            elif chunk_type == ChunkType.sub_sub_requirement.value:
                subreq_path = det_id
                if det_id:
                    req_id = det_id.split(".")[0]
            elif chunk_type == ChunkType.measure.value:
                measure_id = det_id
                # Populate requirement_id from the most recently seen requirement
                # so the linker can build requirement_to_measure relationships.
                req_id = _last_req_id
                # Update citation path to reflect the parent requirement.
                if _last_req_id and det_id:
                    citation_path = f"{standard_id} -> {_last_req_id} -> {det_id}"
            elif chunk_type in (
                ChunkType.attachment_obligation.value,
                ChunkType.attachment_measure.value,
            ):
                attachment_id = det_id

            metadata = ChunkMetadata(
                standard_id=standard_id,
                document_title=document_title,
                chunk_type=chunk_type,
                official_citation_path=citation_path,
                parent_chunk_id=None,
                child_chunk_ids=[],
                requirement_id=req_id,
                subrequirement_path=subreq_path,
                measure_id=measure_id,
                attachment_id=attachment_id,
                source_location=source_location,
                effective_date=None,
                version=None,
                applicability_tags=[],
                governing_requirement_reference=None,
                vsl_row_id=None,
                vsl_level=None,
                expected_evidence=[],
            )

            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                scan_id=scan_id,
                file_node_id=file_node_id,
                text=part_text,
                metadata=metadata,
                embedding=None,
            ))

    return chunks
