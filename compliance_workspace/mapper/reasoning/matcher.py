"""Two-stage evidence-to-requirement matching (P3-T02).

Stage 1 — Structural: file extension vs. expected evidence descriptors,
           plus folder-name keyword heuristics.
Stage 2 — Semantic: sentence-transformers cosine similarity (optional;
           gracefully skipped if the library is not installed).

Top-K candidates per chunk are written to the evidence_candidates table.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

# Folder / filename keywords that signal compliance evidence
_PATH_KEYWORDS = frozenset([
    "policy", "procedure", "log", "training", "audit", "evidence",
    "compliance", "security", "access", "configuration", "config",
    "report", "assessment", "review", "approval", "change", "incident",
    "backup", "monitor", "patch", "vulnerability", "system", "network",
    "firewall", "baseline",
])

# Evidence descriptor → file extensions that commonly fulfill it
_DESCRIPTOR_EXTENSIONS: dict[str, frozenset[str]] = {
    "procedure":              frozenset(["pdf", "docx", "doc"]),
    "screenshot":             frozenset(["png", "jpg", "jpeg", "pdf"]),
    "report":                 frozenset(["pdf", "docx", "xlsx", "csv"]),
    "log":                    frozenset(["txt", "csv", "log", "xlsx"]),
    "approval_record":        frozenset(["pdf", "docx", "doc"]),
    "email":                  frozenset(["pdf", "txt", "msg", "eml"]),
    "configuration_export":   frozenset(["txt", "csv", "xlsx", "xml", "json"]),
    "test_evidence":          frozenset(["pdf", "docx", "txt", "xlsx"]),
    "submission_record":      frozenset(["pdf", "docx"]),
    "signed_acknowledgement": frozenset(["pdf", "docx"]),
    "policy":                 frozenset(["pdf", "docx", "doc"]),
    "diagram":                frozenset(["pdf", "png", "jpg", "vsd", "vsdx"]),
    "training_record":        frozenset(["pdf", "xlsx", "csv", "docx"]),
}


@dataclass
class Candidate:
    candidate_id: Optional[int]
    run_id: str
    chunk_id: str
    file_node_id: int
    file_path: str          # in-memory only; not persisted
    structural_score: float
    semantic_score: float
    combined_score: float


# ---------------------------------------------------------------------------
# Stage 1 — structural scoring
# ---------------------------------------------------------------------------

def _structural_score(
    file_path: str,
    file_ext: str,
    expected_evidence: list[str],
) -> float:
    """Return a 0.0–1.0 score based on extension match and path keywords."""
    score = 0.0
    path_lower = file_path.lower()
    path_tokens = set(re.split(r"[/\\_ \-.]", path_lower))

    if expected_evidence:
        matched = sum(
            1
            for desc in expected_evidence
            if file_ext in _DESCRIPTOR_EXTENSIONS.get(desc, frozenset())
        )
        score += 0.5 * (matched / len(expected_evidence))
    else:
        if file_ext in ("pdf", "docx", "doc", "txt", "xlsx", "csv"):
            score += 0.25

    keyword_hits = len(path_tokens & _PATH_KEYWORDS)
    score += 0.5 * min(keyword_hits / 3.0, 1.0)

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Stage 2 — semantic scoring (optional)
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _chunk_text(text: str, max_chars: int = 2048) -> list[str]:
    """Split text into overlapping windows of at most *max_chars* characters."""
    if len(text) <= max_chars:
        return [text]
    step = max_chars - 256  # 256-char overlap
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + max_chars])
        start += step
    return chunks


def _semantic_score_for_pair(
    evidence_text: str,
    requirement_text: str,
    embedder,
) -> float:
    """Return the max cosine similarity between evidence windows and the requirement."""
    ev_chunks = _chunk_text(evidence_text)
    req_emb = embedder.encode([requirement_text])[0].tolist()
    best = 0.0
    for chunk in ev_chunks:
        ev_emb = embedder.encode([chunk])[0].tolist()
        sim = _cosine(req_emb, ev_emb)
        if sim > best:
            best = sim
    return best


def _is_usable_evidence_text(text: str) -> bool:
    """Return False for extraction output that is mostly PDF CID glyph noise."""
    if not text:
        return True

    cid_count = len(re.findall(r"\(cid:\d+\)", text))
    if cid_count < 20:
        return True

    cid_chars = sum(len(m.group(0)) for m in re.finditer(r"\(cid:\d+\)", text))
    return (cid_chars / max(len(text), 1)) < 0.05


def _load_embedder():
    """Return a sentence-transformers model, or None if not installed."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Chunk types that carry compliance obligations and should be assessed.
# Excludes pure-narrative types like standard_overview, definition,
# applicability, reference_guidance, and vsl_artifact.
_REQUIREMENT_CHUNK_TYPES = (
    "requirement",
    "sub_requirement",
    "sub_sub_requirement",
    "measure",
    "attachment_obligation",
    "attachment_measure",
)


def _fetch_req_chunks(
    conn: sqlite3.Connection, standard_id: str
) -> list[tuple[str, str, str]]:
    """Return requirement-like chunks for *standard_id*.

    Falls back to every chunk for the standard if the obligation-type filter
    yields nothing (e.g. an unusual standard whose parser produced only
    overview/definition chunks) — better to assess loosely than to silently
    return zero candidates.
    """
    placeholders = ",".join("?" * len(_REQUIREMENT_CHUNK_TYPES))
    rows = conn.execute(
        f"""SELECT chunk_id, text, expected_evidence
            FROM chunks
            WHERE standard_id LIKE ?
              AND chunk_type IN ({placeholders})
        """,
        (f"{standard_id}%", *_REQUIREMENT_CHUNK_TYPES),
    ).fetchall()
    if rows:
        return rows

    return conn.execute(
        """SELECT chunk_id, text, expected_evidence
           FROM chunks
           WHERE standard_id LIKE ?
        """,
        (f"{standard_id}%",),
    ).fetchall()


def compute_candidates(
    conn: sqlite3.Connection,
    run_id: str,
    standard_id: str,
    scan_id: int,
    top_k: int = 5,
) -> list[Candidate]:
    """Score every (requirement chunk, evidence file) pair; persist top-K per chunk.

    Returns the full list of persisted Candidate objects.
    """
    req_chunks = _fetch_req_chunks(conn, standard_id)

    evidence_rows = conn.execute(
        """SELECT fn.id, fn.full_path, fn.extension, et.text
           FROM file_nodes fn
           JOIN evidence_text et ON et.file_node_id = fn.id
           WHERE fn.scan_id = ?
        """,
        (scan_id,),
    ).fetchall()
    evidence_rows = [
        row for row in evidence_rows if _is_usable_evidence_text(row[3] or "")
    ]

    if not req_chunks or not evidence_rows:
        return []

    embedder = _load_embedder()

    all_candidates: list[Candidate] = []

    for chunk_id, req_text, expected_ev_json in req_chunks:
        try:
            expected_evidence: list[str] = json.loads(expected_ev_json or "[]")
        except Exception:
            expected_evidence = []

        # (structural_score, semantic_score, combined, file_node_id, file_path)
        scored: list[tuple[float, float, float, int, str]] = []

        for file_node_id, file_path, file_ext, ev_text in evidence_rows:
            ext = (file_ext or "").lower().lstrip(".")
            s_score = _structural_score(file_path, ext, expected_evidence)

            sem_score = 0.0
            if embedder is not None and ev_text:
                try:
                    sem_score = _semantic_score_for_pair(ev_text, req_text or "", embedder)
                except Exception:
                    sem_score = 0.0

            combined = (0.4 * s_score + 0.6 * sem_score) if embedder is not None else s_score
            scored.append((s_score, sem_score, combined, file_node_id, file_path))

        scored.sort(key=lambda x: x[2], reverse=True)

        # Take top-K when at least one evidence file scored above zero;
        # otherwise pair every evidence file with this requirement so the
        # downstream LLM assessor can make the call. Over-generating is
        # cheaper than silently dropping requirements.
        if scored and scored[0][2] > 0.0:
            selected = scored[:top_k]
        else:
            selected = scored

        for s_score, sem_score, combined, file_node_id, file_path in selected:
            all_candidates.append(
                Candidate(
                    candidate_id=None,
                    run_id=run_id,
                    chunk_id=chunk_id,
                    file_node_id=file_node_id,
                    file_path=file_path,
                    structural_score=s_score,
                    semantic_score=sem_score,
                    combined_score=combined,
                )
            )

    _write_candidates(conn, all_candidates)
    return all_candidates


def _write_candidates(conn: sqlite3.Connection, candidates: list[Candidate]) -> None:
    conn.executemany(
        """INSERT INTO evidence_candidates
               (run_id, chunk_id, file_node_id, structural_score, semantic_score, combined_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                c.run_id,
                c.chunk_id,
                c.file_node_id,
                c.structural_score,
                c.semantic_score,
                c.combined_score,
            )
            for c in candidates
        ],
    )
    conn.commit()
