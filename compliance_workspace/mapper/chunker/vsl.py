"""VSL (Violation Severity Levels) table parser.

Detects VSL table boundaries in NERC document text, parses individual
severity rows, and produces vsl_artifact Chunk objects plus VSLArtifact
records for DB storage.
"""
from __future__ import annotations

import re
import uuid
from typing import List, Optional, Tuple

from mapper.models.chunk import Chunk, ChunkMetadata, ChunkType, VSLArtifact


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Marks the start of a VSL section
_VSL_SECTION_START_RE = re.compile(
    r'Violation\s+Severity\s+Levels?',
    re.IGNORECASE,
)

# Severity level keywords used as column headers in VSL tables.
# Real NERC documents use "Moderate" (not "Medium").
_SEVERITY_LEVELS = ("Severe", "High", "Moderate", "Lower")
_SEVERITY_HEADER_RE = re.compile(
    r'\b(Severe|High|Moderate|Lower)\b',
    re.IGNORECASE,
)

# Requirement reference for back-linking
_REQ_REF_RE = re.compile(r'\b(R\d+(?:\.\d+)*)\b')

# Matches lines that start a VSL table row for a specific requirement.
# E.g. "R1. The entity..." or "R3 – Ports and Services"
_REQ_ROW_RE = re.compile(r'(?m)^\s*(R\d+)[.\s]')

# Section-end heuristic: three+ blank lines or a new top-level header
_SECTION_END_RE = re.compile(r'\n{3,}', re.MULTILINE)


def _extract_governing_req(text: str) -> Optional[str]:
    """Return the first Rn / Rn.m reference in text."""
    m = _REQ_REF_RE.search(text)
    return m.group(1) if m else None


def _find_req_before_pos(section_text: str, pos: int) -> Optional[str]:
    """Return the most recent R\\d+ line-starter before character position *pos*.

    Scans *section_text* for lines that begin with ``R<n>.`` or ``R<n> ``
    (the row-header pattern used in NERC VSL tables) and returns the
    requirement ID of the last such line that starts before *pos*.
    """
    last_req: Optional[str] = None
    for m in _REQ_ROW_RE.finditer(section_text):
        if m.start() >= pos:
            break
        last_req = m.group(1)
    return last_req


def _find_vsl_sections(text: str) -> List[Tuple[int, int]]:
    """Return (start, end) character spans for each VSL section."""
    spans: List[Tuple[int, int]] = []
    for m in _VSL_SECTION_START_RE.finditer(text):
        start = m.start()
        # End: next triple-newline gap or end of string
        end_m = _SECTION_END_RE.search(text, m.end())
        end = end_m.start() if end_m else len(text)
        spans.append((start, end))
    return spans


def parse_vsl_table(
    text: str,
    standard_id: str,
    scan_id: int,
    file_node_id: int,
    source_location: str,
) -> Tuple[List[Chunk], List[VSLArtifact]]:
    """Find all VSL tables in *text* and produce chunks + artifacts.

    Each severity-level row in each VSL table becomes:
    - one ``vsl_artifact`` Chunk
    - one VSLArtifact dataclass record

    Returns ``(chunks, artifacts)``.
    """
    chunks: List[Chunk] = []
    artifacts: List[VSLArtifact] = []

    for section_start, section_end in _find_vsl_sections(text):
        section_text = text[section_start:section_end]

        # Section-wide fallback: first R\d+ reference anywhere in the section
        gov_req = _extract_governing_req(section_text) or _extract_governing_req(text)

        # Locate all severity-level positions within the section
        level_hits: List[Tuple[str, int]] = [
            (m.group(1), m.start())
            for m in _SEVERITY_HEADER_RE.finditer(section_text)
        ]

        if not level_hits:
            continue

        for i, (level, rel_start) in enumerate(level_hits):
            rel_end = level_hits[i + 1][1] if i + 1 < len(level_hits) else len(section_text)
            row_text = section_text[rel_start:rel_end].strip()
            if not row_text:
                continue

            # Per-row governing requirement: nearest R\d+. line-starter before
            # this severity hit, falling back to the section-wide gov_req.
            row_gov_req = _find_req_before_pos(section_text, rel_start) or gov_req

            # Fallback: scan VSL section for "R<n>." pattern (covers tables where
            # R1./R2. appears inline rather than as a line-start row header).
            if not row_gov_req:
                matches = re.findall(r'\bR(\d+)\.', section_text)
                if matches:
                    row_gov_req = f"R{matches[0]}"

            # Citation path includes the requirement when known.
            if row_gov_req:
                citation_path = f"{standard_id} -> {row_gov_req} -> VSL"
            else:
                citation_path = f"{standard_id} -> VSL -> {level.capitalize()}"

            row_id = f"row_{i}"
            chunk_id = str(uuid.uuid4())
            vsl_id = str(uuid.uuid4())

            metadata = ChunkMetadata(
                standard_id=standard_id,
                document_title="",
                chunk_type=ChunkType.vsl_artifact.value,
                official_citation_path=citation_path,
                parent_chunk_id=None,
                child_chunk_ids=[],
                requirement_id=row_gov_req,
                subrequirement_path=None,
                measure_id=None,
                attachment_id=None,
                source_location=source_location,
                effective_date=None,
                version=None,
                applicability_tags=[],
                governing_requirement_reference=row_gov_req,
                vsl_row_id=row_id,
                vsl_level=level.capitalize(),
                expected_evidence=[],
            )

            chunks.append(Chunk(
                chunk_id=chunk_id,
                scan_id=scan_id,
                file_node_id=file_node_id,
                text=row_text,
                metadata=metadata,
                embedding=None,
            ))

            artifacts.append(VSLArtifact(
                vsl_id=vsl_id,
                chunk_id=chunk_id,
                standard_id=standard_id,
                requirement_ref=row_gov_req or "",
                vsl_level=level.capitalize(),
                vsl_text=row_text,
                row_id=row_id,
            ))

    return chunks, artifacts
