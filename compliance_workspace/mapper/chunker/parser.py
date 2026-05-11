"""NERC document structural parser.

Accepts raw text extracted from a NERC document and splits it into
ParsedUnit objects at structural boundaries (requirements, measures,
VSL sections, attachments, definitions, applicability tables).

Key structural facts observed in real NERC PDFs
------------------------------------------------
* Main requirements: ``R1.``, ``R2.`` … (period immediately after number)
* Measures:          ``M1.``, ``M2.`` … (same)
* Sub-requirements:  ``1.1.``, ``2.3.`` … (no ``R`` prefix; leading digit
  matches the parent requirement number)
* Sub-sub-reqs:      ``1.1.1.``, ``2.3.4.`` … (same convention)
* VSL table header:  "Violation Severity Levels" — repeats on every page
  of the multi-page table; rows inside are ``R1.`` … that must NOT be
  re-classified as requirements.
* VSL severity columns: Lower / Moderate / High / Severe  (NOT "Medium")
* Attachments:       ``EOP-004 - Attachment 1: Title`` or
                     ``CIP-002-5.1a - Attachment 1`` or
                     ``PRC-005 — Attachment A`` (standard-ID prefix common)
* Applicability:     ``4. Applicability:`` (numbered, not standalone word)
* Definitions:       no standalone "Definitions" header observed in tested
                     standards; kept for synthetic / older documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from mapper.models.chunk import ChunkType


@dataclass
class ParsedUnit:
    text: str
    detected_type: str            # ChunkType value
    detected_id: Optional[str]   # e.g. "R1", "1.2", "M3", "CIP-007-6"
    depth: int                    # 0=standard, 1=req/attachment/vsl, 2=subreq/measure, 3=sub-sub-req
    raw_start_pos: int            # character offset in source text


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_STANDARD_ID_RE = re.compile(
    r'\b(CIP|FAC|MOD|PRC|TPL|COM|EOP|INT|IRO|PER|TOP|VAR|NUC|BAL|GOV|MNT|ORG|PBR|STA|UST)'
    r'-\d{3}-\d+\b'
)

# Real NERC format: "R1." (period after number is required).
# The trailing whitespace/end-of-string is optional to handle lines like
# "R19." that appear alone (reserved requirements).
_SUBSUBREQ_LINE_RE = re.compile(r'^\s*(R\d+\.\d+\.\d+)\s*[.:](?:\s|$)')
_SUBREQ_LINE_RE    = re.compile(r'^\s*(R\d+\.\d+)\s*[.:](?:\s|$)')
_MAINREQ_LINE_RE   = re.compile(r'^\s*(R\d+)\s*[.:](?:\s|$)')
_MEASURE_LINE_RE   = re.compile(r'^\s*(M\d+)\s*[.:](?:\s|$)')

# Attachment: optionally prefixed by a standard ID; must end or be followed
# by colon / dash / em-dash (not ordinary prose words).
_ATTACHMENT_LINE_RE = re.compile(
    r'^\s*(?:(?:CIP|FAC|MOD|PRC|TPL|COM|EOP|INT|IRO|PER|TOP|VAR|NUC|BAL|GOV|MNT|ORG|PBR|STA|UST)'
    r'-\d+[\w.-]*\s*[-\u2014\u2013]\s*)?'   # optional "STANDARD - " prefix
    r'Attachment\s+(\d+|[A-Z])'             # "Attachment 1" or "Attachment A"
    r'(?:\s*[:\-\u2014\u2013]|\s*$)',       # must end or be followed by : or dash
    re.IGNORECASE,
)

_VSL_LINE_RE        = re.compile(r'Violation\s+Severity\s+Levels?|^\s*VSL\s*$', re.IGNORECASE)
_DEFINITION_LINE_RE = re.compile(r'^\s*Definitions?\s*$', re.IGNORECASE)
_TERMS_LINE_RE      = re.compile(r'^\s*Terms?\s*$', re.IGNORECASE)

# Match both standalone "Applicability" and numbered "4. Applicability:"
_APPLICABILITY_LINE_RE = re.compile(r'^\s*(?:\d+\.\s*)?Applicability\s*:?\s*$', re.IGNORECASE)

# End-of-VSL-section markers: lettered major sections D onwards, or well-known
# post-body sections.  These reset _in_vsl when encountered.
_END_OF_VSL_RE = re.compile(
    r'^[D-Z]\.\s'
    r'|^Guidelines\s+and\s+Technical\s+Basis'
    r'|^Appendix\s+\d'
    r'|^Version\s+History',
    re.IGNORECASE,
)

# Detects "B. Requirements" / "B. Requirements and Measures" (and equivalent
# lettered headers A–B that introduce the requirements body).
_REQUIREMENTS_SECTION_RE = re.compile(
    r'^\s*[A-B]\.\s+Requirements?(?:\s+and\s+Measures?)?\s*$',
    re.IGNORECASE,
)

# Detects the start of any section that follows the requirements body.
# Includes lettered post-body headers (C. Compliance, D. Regional …) and
# well-known appendix titles.
_POST_REQUIREMENTS_RE = re.compile(
    r'^\s*[C-Z]\.\s'
    r'|^\s*Guidelines\s+and\s+Technical\s+Basis'
    r'|^\s*Appendix\s+\d'
    r'|^\s*Version\s+History',
    re.IGNORECASE,
)

# Combined boundary detector used when NOT inside a VSL section.
# A line matching this triggers a new unit.
_BOUNDARY_RE = re.compile(
    r'^\s*(?:'
    r'R\d+\.\d+\.\d+\s*[.:](?:\s|$)'   # sub-sub-req  (R-prefix style)
    r'|R\d+\.\d+\s*[.:](?:\s|$)'       # sub-req      (R-prefix style)
    r'|R\d+\s*[.:](?:\s|$)'            # main req  (period/colon required)
    r'|M\d+\s*[.:](?:\s|$)'            # measure
    r'|(?:(?:CIP|FAC|MOD|PRC|TPL|COM|EOP|INT|IRO|PER|TOP|VAR|NUC|BAL|GOV|MNT|ORG|PBR|STA|UST)'
    r'-\d+[\w.-]*\s*[-\u2014\u2013]\s*)?'
    r'Attachment\s+(?:\d+|[A-Z])(?:\s*[:\-\u2014\u2013]|\s*$)'
    r'|Violation\s+Severity\s+Levels?'
    r'|VSL\s*$'
    r'|Definitions?\s*$'
    r'|Terms?\s*$'
    r'|(?:\d+\.\s*)?Applicability\s*:?\s*$'
    r')',
    re.IGNORECASE,
)


def _classify_line(line: str) -> tuple[str, Optional[str], int]:
    """Return (chunk_type, detected_id, depth) for a boundary line."""
    stripped = line.strip()

    m = _SUBSUBREQ_LINE_RE.match(stripped)
    if m:
        return ChunkType.sub_sub_requirement.value, m.group(1), 3

    m = _SUBREQ_LINE_RE.match(stripped)
    if m:
        return ChunkType.sub_requirement.value, m.group(1), 2

    m = _MAINREQ_LINE_RE.match(stripped)
    if m:
        return ChunkType.requirement.value, m.group(1), 1

    m = _MEASURE_LINE_RE.match(stripped)
    if m:
        return ChunkType.measure.value, m.group(1), 2

    m = _ATTACHMENT_LINE_RE.match(stripped)
    if m:
        return ChunkType.attachment_obligation.value, m.group(0).strip(), 1

    if _VSL_LINE_RE.search(stripped):
        return ChunkType.vsl_artifact.value, None, 1

    if _DEFINITION_LINE_RE.match(stripped) or _TERMS_LINE_RE.match(stripped):
        return ChunkType.definition.value, None, 1

    if _APPLICABILITY_LINE_RE.match(stripped):
        return ChunkType.applicability.value, None, 1

    # Default: infer standard ID if present
    m = _STANDARD_ID_RE.search(stripped)
    if m:
        return ChunkType.standard_overview.value, m.group(0), 0

    return ChunkType.reference_guidance.value, None, 99


# Pre-compiled pattern for extracting the R-number from a requirement ID
_REQ_NUM_RE = re.compile(r'^R(\d+)$')


def parse_nerc_document(text: str) -> List[ParsedUnit]:
    """Parse raw NERC document text into a list of ParsedUnit objects.

    Splits at structural boundary lines and classifies each segment.
    Uses state tracking to handle:

    * VSL table sections — the "Violation Severity Levels" header repeats on
      every page of the PDF table; rows starting with ``R1.`` inside the VSL
      block are *not* classified as requirements.
    * Sub-requirements — ``n.m.`` lines (no R-prefix) are detected only when
      ``n`` matches the most recently seen main-requirement number, preventing
      false positives inside the Applicability and Compliance sections.

    If no boundaries are detected, the whole document is a single unit.
    """
    units: List[ParsedUnit] = []
    lines = text.splitlines(keepends=True)

    current_lines: List[str] = []
    current_start = 0
    current_type = ChunkType.standard_overview.value
    current_id: Optional[str] = None
    current_depth = 0
    pos = 0

    # --- state ---
    _current_req_num: int = 0   # number of the last seen R{n} requirement
    _in_vsl: bool = False       # True while inside a VSL table section
    _in_requirements_section: bool = False  # True only inside the requirements body

    def flush() -> None:
        txt = "".join(current_lines).strip()
        if txt:
            units.append(ParsedUnit(
                text=txt,
                detected_type=current_type,
                detected_id=current_id,
                depth=current_depth,
                raw_start_pos=current_start,
            ))

    def _subreq_boundary(line: str) -> tuple[bool, Optional[str], int]:
        """Check for un-prefixed sub-req (``n.m.``) given current req num.

        Only fires when inside the requirements section to prevent numbered
        clauses in applicability / compliance / background sections from being
        mis-classified as sub-requirements.
        """
        if _current_req_num <= 0 or not _in_requirements_section:
            return False, None, 0
        stripped = line.strip()
        n = _current_req_num
        # sub-sub-req: n.m.p.  — trailing period required to avoid matching
        # mid-sentence references like "see 4.1.2 for details".
        m = re.match(rf'^\s*({n}\.\d+\.\d+)\.\s', stripped)
        if m:
            return True, m.group(1), 3
        # sub-req: n.m.  — same: period required.
        m = re.match(rf'^\s*({n}\.\d+)\.\s', stripped)
        if m:
            return True, m.group(1), 2
        return False, None, 0

    for line in lines:
        stripped = line.strip()

        # ----------------------------------------------------------------
        # VSL header — always starts a new vsl_artifact unit regardless of
        # current state (the table header repeats on every PDF page).
        # ----------------------------------------------------------------
        if _VSL_LINE_RE.search(stripped):
            flush()
            current_lines = [line]
            current_start = pos
            current_type = ChunkType.vsl_artifact.value
            current_id = None
            current_depth = 1
            _in_vsl = True

        # ----------------------------------------------------------------
        # Inside VSL section — swallow all lines; exit on major post-body
        # section headers, standalone Definitions/Terms, or Attachment
        # section headers.
        # ----------------------------------------------------------------
        elif _in_vsl:
            exits_vsl = (
                _END_OF_VSL_RE.match(stripped)
                or _ATTACHMENT_LINE_RE.match(stripped)
                or _DEFINITION_LINE_RE.match(stripped)
                or _TERMS_LINE_RE.match(stripped)
            )
            if exits_vsl:
                flush()
                current_lines = [line]
                current_start = pos
                current_type, current_id, current_depth = _classify_line(line)
                _in_vsl = False
                # Exiting to a post-requirements section header means we are
                # no longer in the requirements body.
                if _END_OF_VSL_RE.match(stripped) or _POST_REQUIREMENTS_RE.match(stripped):
                    _in_requirements_section = False
            else:
                current_lines.append(line)

        # ----------------------------------------------------------------
        # Normal boundary detection
        # ----------------------------------------------------------------
        elif _BOUNDARY_RE.match(line):
            flush()
            current_lines = [line]
            current_start = pos
            current_type, current_id, current_depth = _classify_line(line)
            # Track requirement number for sub-req detection.
            # Also treat first requirement as implicit entry into the
            # requirements section (fallback for docs without "B. Requirements"
            # header).
            if current_type == ChunkType.requirement.value and current_id:
                m = _REQ_NUM_RE.match(current_id)
                if m:
                    _current_req_num = int(m.group(1))
                    _in_requirements_section = True

        # ----------------------------------------------------------------
        # Sub-requirement detection (n.m. / n.m.p. without R prefix)
        # ----------------------------------------------------------------
        else:
            is_sub, sub_id, sub_depth = _subreq_boundary(line)
            if is_sub:
                flush()
                current_lines = [line]
                current_start = pos
                current_type = (
                    ChunkType.sub_sub_requirement.value
                    if sub_depth == 3
                    else ChunkType.sub_requirement.value
                )
                current_id = sub_id
                current_depth = sub_depth
            else:
                # Update requirements-section context based on section headers.
                if _REQUIREMENTS_SECTION_RE.match(stripped):
                    _in_requirements_section = True
                elif _POST_REQUIREMENTS_RE.match(stripped):
                    _in_requirements_section = False
                # Opportunistically grab a standard ID for the overview chunk
                if current_type == ChunkType.standard_overview.value and current_id is None:
                    m = _STANDARD_ID_RE.search(line)
                    if m:
                        current_id = m.group(0)
                current_lines.append(line)

        pos += len(line)

    flush()

    # Fallback: whole document as one unit
    if not units:
        units.append(ParsedUnit(
            text=text.strip(),
            detected_type=ChunkType.standard_overview.value,
            detected_id=None,
            depth=0,
            raw_start_pos=0,
        ))

    return units
