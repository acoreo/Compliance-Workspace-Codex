"""LLM-based compliance assessment per (requirement chunk, evidence file) pair (P3-T04).

Exact prompt template as specified.  Responses are stored verbatim in the DB
for full auditability.  Already-assessed pairs are skipped (resumable runs).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .llm import LlamaCppBackend

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a NERC compliance auditor. Assess whether the provided evidence "
    "satisfies the stated requirement. Respond only with valid JSON matching "
    "the schema provided."
)

PROMPT_VERSION = "v1"

_RESPONSE_SCHEMA = """{
  "verdict": "satisfied" | "partial" | "gap" | "not_applicable",
  "confidence": 0.0-1.0,
  "rationale": "one paragraph explanation",
  "cited_text": "exact quote from evidence that supports verdict, or null",
  "gaps_identified": ["list of specific gaps if verdict is partial or gap"]
}"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class Assessment:
    run_id: str
    chunk_id: str
    file_node_id: int
    verdict: str
    confidence: float
    rationale: str
    cited_text: Optional[str]
    gaps_identified: list[str] = field(default_factory=list)
    raw_llm_response: str = ""
    prompt_version: str = PROMPT_VERSION
    assessed_ts: str = ""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_user_prompt(
    citation_path: str,
    requirement_text: str,
    measure_text: str,
    file_path: str,
    evidence_excerpt: str,
) -> str:
    """Construct the user turn of the assessment prompt (exact template from spec)."""
    return (
        f"REQUIREMENT:\n"
        f"Citation: {citation_path}\n"
        f"Text: {requirement_text}\n\n"
        f"MEASURE (what evidence is required):\n{measure_text}\n\n"
        f"EVIDENCE FILE: {file_path}\n"
        f"EVIDENCE CONTENT:\n{evidence_excerpt}\n\n"
        f"TASK: Does this evidence satisfy the requirement?\n"
        f"Respond with this exact JSON:\n{_RESPONSE_SCHEMA}"
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

_VALID_VERDICTS = {"satisfied", "partial", "gap", "not_applicable", "parse_error"}


def _normalise_parsed(d: dict) -> dict:
    """Enforce schema on a parsed dict - clamp types, fill missing fields."""
    verdict = str(d.get("verdict", "parse_error")).lower().strip()
    if verdict not in _VALID_VERDICTS:
        verdict = "parse_error"

    try:
        confidence = float(d.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    rationale = str(d.get("rationale", "")) if d.get("rationale") is not None else ""
    cited_text = str(d["cited_text"]) if d.get("cited_text") else None

    gaps = d.get("gaps_identified") or []
    if not isinstance(gaps, list):
        gaps = [str(gaps)]
    gaps = [str(g) for g in gaps]

    return {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "cited_text": cited_text,
        "gaps_identified": gaps,
    }


def _extract_json_block(raw: str) -> dict | None:
    """Try to find and parse a balanced JSON object anywhere in raw."""
    # Find every '{' and try to parse a balanced block from that position
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        depth = 0
        for j, c in enumerate(raw[i:], i):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[i : j + 1])
                except (json.JSONDecodeError, ValueError):
                    break
    return None


def _keyword_verdict(raw: str) -> dict | None:
    """Extract verdict from plain-text response using regex word-boundary matching."""
    t = raw.lower()

    na_patterns      = [r"\bnot applicable\b", r"\bn/a\b", r"\bnot apply\b", r"\bexempt\b"]
    gap_patterns     = [r"\bdoes not satisfy\b", r"\bnot satisfied\b", r"\bnon-compliant\b",
                        r"\bno evidence\b", r"\binsufficient\b", r"\bfails to\b",
                        r"\bdoes not demonstrate\b", r"\bnot met\b", r"\bcannot confirm\b",
                        r"\bmissing\b"]
    partial_patterns = [r"\bpartially\b", r"\bpartial\b", r"\bsome evidence\b",
                        r"\bincomplete\b", r"\bnot fully\b", r"\blimited evidence\b"]
    sat_patterns     = [r"\bsatisfies\b", r"\bsatisfied\b", r"\bcompliant\b",
                        r"\bmeets\b", r"\bmet\b", r"\bdemonstrates compliance\b",
                        r"\bevidence supports\b", r"\badequate\b", r"\bsufficient\b",
                        r"\bdoes satisfy\b"]

    def matches(patterns: list[str]) -> bool:
        return any(re.search(p, t) for p in patterns)

    if matches(na_patterns):
        verdict, confidence = "not_applicable", 0.5
    elif matches(gap_patterns):
        verdict, confidence = "gap", 0.4
    elif matches(partial_patterns):
        verdict, confidence = "partial", 0.4
    elif matches(sat_patterns):
        verdict, confidence = "satisfied", 0.4
    else:
        return None

    return {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": f"[Extracted from plain-text response] {raw.strip()[:800]}",
        "cited_text": None,
        "gaps_identified": [],
    }


def parse_llm_response(raw: str) -> dict:
    """Parse LLM response with multiple fallback strategies.

    1. Direct json.loads() + schema normalisation
    2. JSON inside a markdown fenced block
    3. Brace-balanced JSON block found anywhere in the response
    4. Regex keyword extraction from plain text
    5. Parse-error sentinel
    """
    if not raw or raw.startswith("ERROR:"):
        return {
            "verdict": "parse_error",
            "confidence": 0.0,
            "rationale": raw or "Empty LLM response.",
            "cited_text": None,
            "gaps_identified": [],
        }

    # Attempt 1: direct JSON
    try:
        return _normalise_parsed(json.loads(raw))
    except (json.JSONDecodeError, ValueError):
        pass

    # Attempt 2: markdown fenced block
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        try:
            return _normalise_parsed(json.loads(match.group(1).strip()))
        except (json.JSONDecodeError, ValueError):
            pass

    # Attempt 3: brace-balanced JSON block
    extracted = _extract_json_block(raw)
    if extracted is not None:
        return _normalise_parsed(extracted)

    # Attempt 4: keyword extraction
    kw = _keyword_verdict(raw)
    if kw is not None:
        return kw

    # Attempt 5: give up
    return {
        "verdict": "parse_error",
        "confidence": 0.0,
        "rationale": f"LLM response could not be parsed. Raw: {raw[:300]}",
        "cited_text": None,
        "gaps_identified": [],
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assess_candidates(
    conn: sqlite3.Connection,
    backend: LlamaCppBackend,
    run_id: str,
    standard_id: str,
    *,
    verbose: bool = True,
) -> list[Assessment]:
    """Run LLM assessment for every candidate pair belonging to *run_id*.

    Skips pairs that already have a row in evidence_assessments for this
    run_id (resumable).  Returns all newly created Assessment objects.
    """
    candidates = conn.execute(
        """SELECT ec.chunk_id,
                  ec.file_node_id,
                  fn.full_path,
                  et.text,
                  c.official_citation_path,
                  c.text AS req_text,
                  c.requirement_id,
                  c.standard_id AS std_id
           FROM evidence_candidates ec
           JOIN file_nodes fn   ON fn.id          = ec.file_node_id
           JOIN evidence_text et ON et.file_node_id = ec.file_node_id
           JOIN chunks c        ON c.chunk_id      = ec.chunk_id
           WHERE ec.run_id = ?
           ORDER BY ec.chunk_id, ec.combined_score DESC
        """,
        (run_id,),
    ).fetchall()

    total_candidates = len(candidates)
    already_assessed = {
        (chunk_id, file_node_id)
        for chunk_id, file_node_id in conn.execute(
            """SELECT chunk_id, file_node_id
               FROM evidence_assessments
               WHERE run_id = ?""",
            (run_id,),
        ).fetchall()
    }
    total_to_assess = sum(
        1
        for row in candidates
        if (row[0], row[1]) not in already_assessed
    )

    assessments: list[Assessment] = []
    processed = 0
    skipped = 0
    started = time.time()

    for (chunk_id, file_node_id, file_path, ev_text,
         citation_path, req_text, requirement_id, std_id) in candidates:

        # Resumability: skip if already assessed this pair
        if (chunk_id, file_node_id) in already_assessed:
            skipped += 1
            continue

        # Fetch best measure text for this requirement
        measure_row = conn.execute(
            """SELECT text FROM chunks
               WHERE chunk_type = 'measure'
                 AND requirement_id = ?
                 AND standard_id = ?
               LIMIT 1""",
            (requirement_id or "", std_id or ""),
        ).fetchone()
        measure_text = measure_row[0] if measure_row else ""

        # Keep excerpt short - large prompts spike memory on CPU-only inference
        evidence_excerpt = (ev_text or "")[:1500]
        user_prompt = build_user_prompt(
            citation_path=citation_path or "",
            requirement_text=req_text or "",
            measure_text=measure_text,
            file_path=file_path,
            evidence_excerpt=evidence_excerpt,
        )

        if verbose:
            short_path = file_path[-60:] if len(file_path) > 60 else file_path
            current = processed + 1
            percent = (current - 1) / total_to_assess if total_to_assess else 1.0
            bar_width = 24
            filled = int(percent * bar_width)
            bar = "#" * filled + "-" * (bar_width - filled)
            elapsed = time.time() - started
            eta = ""
            if processed > 0:
                avg = elapsed / processed
                remaining = max(total_to_assess - processed, 0) * avg
                eta = f" | ETA {timedelta(seconds=int(remaining))}"
            print(
                f"  [{bar}] {current}/{total_to_assess} "
                f"({percent * 100:5.1f}%) | elapsed {timedelta(seconds=int(elapsed))}{eta}"
            )
            print(f"    Assessing: {citation_path or chunk_id} <- ...{short_path}")

        # First-pass runs should keep moving. Backend failures are stored as
        # parse_error assessments so the report shows exactly which pairs failed.
        call_started = time.time()
        try:
            raw_response = backend.complete(_SYSTEM_PROMPT, user_prompt)
        except RuntimeError as exc:
            raw_response = f"ERROR: {exc}"
        call_seconds = time.time() - call_started

        # Brief pause between calls - lets CPU-only Ollama free memory before next inference
        delay = getattr(backend, "inter_call_delay", 3)
        if delay > 0:
            time.sleep(delay)

        parsed = parse_llm_response(raw_response)
        ts = datetime.now(timezone.utc).isoformat()

        a = Assessment(
            run_id=run_id,
            chunk_id=chunk_id,
            file_node_id=file_node_id,
            verdict=str(parsed.get("verdict", "parse_error")),
            confidence=float(parsed.get("confidence", 0.0)),
            rationale=str(parsed.get("rationale", "")),
            cited_text=parsed.get("cited_text"),
            gaps_identified=parsed.get("gaps_identified") or [],
            raw_llm_response=raw_response,
            prompt_version=PROMPT_VERSION,
            assessed_ts=ts,
        )
        assessments.append(a)
        _write_assessment(conn, a)
        processed += 1
        if verbose:
            done_percent = processed / total_to_assess if total_to_assess else 1.0
            filled = int(done_percent * 24)
            bar = "#" * filled + "-" * (24 - filled)
            elapsed = time.time() - started
            avg = elapsed / processed if processed else 0
            remaining = max(total_to_assess - processed, 0) * avg
            print(
                f"    Done in {call_seconds:.1f}s | verdict={a.verdict} | "
                f"progress [{bar}] {processed}/{total_to_assess} "
                f"({done_percent * 100:5.1f}%) | ETA {timedelta(seconds=int(remaining))}"
            )

    if verbose:
        print(
            f"  Assessed {processed} new pair(s); skipped {skipped} existing "
            f"out of {total_candidates} candidate pair(s)."
        )

    return assessments


def _write_assessment(conn: sqlite3.Connection, a: Assessment) -> None:
    conn.execute(
        """INSERT INTO evidence_assessments
               (run_id, chunk_id, file_node_id, verdict, confidence, rationale,
                cited_text, gaps_identified, raw_llm_response, prompt_version, assessed_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            a.run_id,
            a.chunk_id,
            a.file_node_id,
            a.verdict,
            a.confidence,
            a.rationale,
            a.cited_text,
            json.dumps(a.gaps_identified),
            a.raw_llm_response,
            a.prompt_version,
            a.assessed_ts,
        ),
    )
    conn.commit()
