"""Phase 3 pipeline orchestrator (P3-T07).

Runs extraction → matching → LLM assessment → gap report in order,
printing progress when verbose=True.  Each step is idempotent / resumable:
already-cached extractions and already-assessed pairs are skipped.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from .assessor import assess_candidates
from .extractor import extract_all
from .llm import LlamaCppBackend
from .matcher import compute_candidates
from .reporter import build_html_report, build_report, save_report
from .schema import create_reasoning_tables


def run_phase3(
    conn: sqlite3.Connection,
    scan_id: int,
    standard_id: str,
    run_id: Optional[str] = None,
    top_k: int = 5,
    verbose: bool = True,
    *,
    config_path: Optional[Path] = None,
    backend: Optional[LlamaCppBackend] = None,
) -> str:
    """Run the full Phase 3 reasoning pipeline.

    Parameters
    ----------
    conn:        Open SQLite connection to workspace.db.
    scan_id:     The Phase 1 scan whose evidence files to process.
    standard_id: NERC standard to assess (e.g. "CIP-007-6").
    run_id:      Unique identifier for this assessment run; auto-generated if None.
    top_k:       Number of top evidence candidates per requirement chunk.
    verbose:     Print step-by-step progress to stdout.
    config_path: Path to cdw_config.toml; used to build *backend* if not supplied.
    backend:     Pre-constructed LlamaCppBackend; overrides config_path if provided.

    Returns
    -------
    The string rowid of the saved gap_reports row.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    if verbose:
        print("\n=== Phase 3: Reasoning Layer ===")
        print(f"  Run ID:   {run_id}")
        print(f"  Standard: {standard_id}")
        print(f"  Scan ID:  {scan_id}")

    # Ensure Phase 3 schema exists
    create_reasoning_tables(conn)

    # ------------------------------------------------------------------
    # Step 1 — Extract text from all document file_nodes
    # ------------------------------------------------------------------
    if verbose:
        print("\n[1/4] Extracting evidence text…")
    results = extract_all(conn, scan_id)
    if verbose:
        cached = sum(1 for r in results if r.extraction_method != "fallback" or r.error is None)
        print(f"  {len(results)} file(s) processed ({cached} usable).")

    # ------------------------------------------------------------------
    # Step 2 — Match evidence to requirement chunks
    # ------------------------------------------------------------------
    if verbose:
        print(f"\n[2/4] Matching evidence to {standard_id} requirements (top-{top_k})…")
    candidates = compute_candidates(conn, run_id, standard_id, scan_id=scan_id, top_k=top_k)
    if verbose:
        print(f"  {len(candidates)} candidate pair(s) generated.")

    # ------------------------------------------------------------------
    # Step 3 — LLM assessment
    # ------------------------------------------------------------------
    if verbose:
        print("\n[3/4] Running LLM assessment…")

    if backend is None:
        if config_path is None:
            # Default: look for config relative to this file's package root
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "cdw_config.toml"
        backend = LlamaCppBackend.from_config(config_path)

    # Verify Ollama is reachable before burning through retries on every pair
    if hasattr(backend, "assert_healthy"):
        backend.assert_healthy()

    try:
        assess_candidates(conn, backend, run_id, standard_id, verbose=verbose)
    except RuntimeError as exc:
        # Backend went down mid-run — surface a clear message and abort.
        # Do NOT generate a partial gap report; the caller sees the exception.
        if verbose:
            print(f"\n  [FATAL] LLM backend error: {exc}")
            print("  Assessment aborted — start Ollama and re-run with the same run_id to resume.")
        raise

    # ------------------------------------------------------------------
    # Step 4 — Generate gap report
    # ------------------------------------------------------------------
    if verbose:
        print("\n[4/4] Generating gap report…")

    report = build_report(conn, run_id, standard_id)
    html = build_html_report(report)
    rowid = save_report(conn, report, html)

    if verbose:
        s = report["summary"]
        print(f"\n  Report saved (gap_reports rowid={rowid})")
        print(
            f"  Total: {s['total_requirements']} | "
            f"Satisfied: {s['satisfied']} | "
            f"Partial: {s['partial']} | "
            f"Gap: {s['gap']} | "
            f"N/A: {s['not_applicable']}"
        )

    return str(rowid)
