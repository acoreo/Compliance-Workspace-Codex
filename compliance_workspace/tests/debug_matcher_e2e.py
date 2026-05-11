"""End-to-end debug script for the CDW evidence matcher.

Reproduces the Dell '0 candidates' symptom by:
  1. Creating a temp SQLite DB with full Phase 1+2+3 schema.
  2. Inserting realistic MOD-025-2 chunks (incl. chunk_type='sub_sub_requirement').
  3. Inserting realistic file_nodes + evidence_text rows.
  4. Calling compute_candidates() and printing every step.

Also exercises a battery of variant scenarios to surface which production
condition is producing zero candidates.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mapper.db.schema import create_tables
from mapper.index.schema import create_chunk_tables
from mapper.reasoning.schema import create_reasoning_tables
from mapper.reasoning.matcher import (
    compute_candidates,
    _fetch_req_chunks,
    _REQUIREMENT_CHUNK_TYPES,
)


# ---------------------------------------------------------------------------
# Diagnostic: install a tracer on the connection so every SQL call is logged.
# ---------------------------------------------------------------------------

def _install_sql_tracer(conn: sqlite3.Connection) -> list[str]:
    """Capture every SQL statement issued on conn into a list."""
    captured: list[str] = []
    conn.set_trace_callback(captured.append)
    return captured


# ---------------------------------------------------------------------------
# Realistic MOD-025-2 fixture
# ---------------------------------------------------------------------------

_MOD025_CHUNKS = [
    # (chunk_id, chunk_type, citation, requirement_id, expected_evidence, text)
    ("MOD-025-2-R1", "requirement", "MOD-025-2 -> R1", "R1",
     ["procedure", "test_evidence"],
     "Each Generator Owner shall provide verified Real Power and Reactive Power "
     "capability data for each of its applicable Facilities to its Transmission "
     "Planner on a schedule specified by the Transmission Planner."),
    ("MOD-025-2-R1.1", "sub_requirement", "MOD-025-2 -> R1 -> R1.1", "R1",
     ["test_evidence", "report"],
     "The Generator Owner shall verify the Real and Reactive Power capability "
     "by performing a unit-specific test."),
    ("MOD-025-2-R1.1.1", "sub_sub_requirement",
     "MOD-025-2 -> R1 -> R1.1 -> R1.1.1", "R1",
     ["test_evidence"],
     "The test shall include the unit operating at maximum gross Real Power "
     "output as specified by the Generator Owner."),
    ("MOD-025-2-R1.1.2", "sub_sub_requirement",
     "MOD-025-2 -> R1 -> R1.1 -> R1.1.2", "R1",
     ["test_evidence"],
     "The Generator Owner shall provide the test results within 90 days of the test."),
    ("MOD-025-2-M1", "measure", "MOD-025-2 -> M1", "R1",
     ["report"],
     "Each Generator Owner shall have evidence such as test reports and dated "
     "verification records that demonstrate compliance with R1."),
]


_EVIDENCE_FILES = [
    # (name, ext, is_document, ev_text)
    ("MOD-025_Test_Procedure.pdf", "pdf", 1,
     "Test procedure for Real and Reactive Power verification of generators. "
     "Includes step-by-step methodology, instrumentation requirements, "
     "and acceptance criteria. Reference NERC MOD-025-2."),
    ("Generator_Capability_Test_Report_Unit3.pdf", "pdf", 1,
     "Unit 3 test report. Real Power output 412 MW, Reactive Power +/- 180 MVAR. "
     "Conducted 2025-08-14. Submitted to Transmission Planner 2025-09-02."),
    ("training_log.xlsx", "xlsx", 1,
     "Operator training records, irrelevant to MOD-025."),
    ("README.txt", "txt", 1, "readme text"),
]


def _build_db(db_path: Path) -> sqlite3.Connection:
    """Create the DB and populate it with a realistic MOD-025-2 fixture."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")
    create_tables(conn)
    create_chunk_tables(conn)
    create_reasoning_tables(conn)

    # 1) scan
    conn.execute(
        "INSERT INTO scans (scope_key, root_path, mode, scan_ts) "
        "VALUES (?, ?, ?, ?)",
        ("debug", "/tmp/debug", "broad", "2026-05-07T00:00:00"),
    )
    scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2) file_nodes + evidence_text
    file_node_ids: list[int] = []
    for name, ext, is_doc, ev_text in _EVIDENCE_FILES:
        full_path = f"/tmp/debug/Compliance/MOD-025/{name}"
        conn.execute(
            "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
            "size_bytes, modified_ts, depth, parent_path, is_document) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scan_id, name, full_path, ext, 1024, "2025-09-01", 3,
             "/tmp/debug/Compliance/MOD-025", is_doc),
        )
        fn_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        file_node_ids.append(fn_id)
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (fn_id, ev_text, "plain", len(ev_text), "2025-09-01"),
        )

    # 3) chunks
    src_fn_id = file_node_ids[0]  # arbitrary owning file
    for chunk_id, ctype, citation, req_id, ev_descs, text in _MOD025_CHUNKS:
        conn.execute(
            "INSERT INTO chunks (chunk_id, scan_id, file_node_id, standard_id, "
            "document_title, chunk_type, official_citation_path, requirement_id, "
            "expected_evidence, text, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, scan_id, src_fn_id, "MOD-025-2",
             "MOD-025-2 Verification of Generator Capability",
             ctype, citation, req_id,
             json.dumps(ev_descs), text, "2026-05-07"),
        )

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Diagnostic dump helpers
# ---------------------------------------------------------------------------

def _dump(conn: sqlite3.Connection, label: str, sql: str, params: tuple = ()) -> None:
    rows = conn.execute(sql, params).fetchall()
    print(f"\n--- {label} (n={len(rows)}) ---")
    for r in rows:
        print(f"  {r}")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_happy_path() -> int:
    print("=" * 78)
    print("SCENARIO 1: Happy path — well-formed MOD-025-2 fixture")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "happy.db"
        conn = _build_db(db_path)

        _dump(conn, "all chunks (chunk_id, standard_id, chunk_type)",
              "SELECT chunk_id, standard_id, chunk_type FROM chunks")
        _dump(conn, "all file_nodes (id, name, ext, is_document)",
              "SELECT id, name, extension, is_document FROM file_nodes")
        _dump(conn, "all evidence_text (file_node_id, char_count)",
              "SELECT file_node_id, char_count FROM evidence_text")

        # Manually run the two queries the matcher uses, so we can see
        # what each one returns BEFORE going into compute_candidates.
        print("\n--- _fetch_req_chunks('MOD-025-2') ---")
        req = _fetch_req_chunks(conn, "MOD-025-2")
        print(f"  returned {len(req)} requirement chunk(s)")
        for r in req:
            print(f"    chunk_id={r[0]!r}  ev_json={r[2]!r}")

        ev = conn.execute(
            "SELECT fn.id, fn.full_path, fn.extension, et.text "
            "FROM file_nodes fn JOIN evidence_text et ON et.file_node_id = fn.id "
            "WHERE fn.is_document = 1"
        ).fetchall()
        print(f"\n--- evidence_rows query (the JOIN with is_document=1) ---")
        print(f"  returned {len(ev)} evidence row(s)")
        for fnid, fp, ex, txt in ev:
            print(f"    fn_id={fnid}  ext={ex!r}  path=...{fp[-50:]}")

        print("\n--- compute_candidates(conn, 'run-happy', 'MOD-025-2', top_k=5) ---")
        sql_log = _install_sql_tracer(conn)
        candidates = compute_candidates(conn, "run-happy", "MOD-025-2", top_k=5)
        print(f"  → returned {len(candidates)} candidate(s)")
        for c in candidates[:10]:
            print(f"    chunk_id={c.chunk_id!r:34s} fn_id={c.file_node_id} "
                  f"struct={c.structural_score:.3f} sem={c.semantic_score:.3f} "
                  f"combined={c.combined_score:.3f}")

        print(f"\n  SQL statements executed during compute_candidates:")
        for stmt in sql_log:
            normalized = " ".join(stmt.split())
            print(f"    {normalized[:160]}")

        conn.close()
        return len(candidates)


def scenario_is_document_zero() -> int:
    print("\n" + "=" * 78)
    print("SCENARIO 2: file_nodes.is_document = 0 (extraction never flagged docs)")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_doc_flag.db"
        conn = _build_db(db_path)
        # Wipe the is_document flag — simulate the bug where it's never set.
        conn.execute("UPDATE file_nodes SET is_document = 0")
        conn.commit()

        _dump(conn, "file_nodes after is_document=0 wipe",
              "SELECT id, name, is_document FROM file_nodes")

        ev_rows = conn.execute(
            "SELECT COUNT(*) FROM file_nodes fn "
            "JOIN evidence_text et ON et.file_node_id = fn.id "
            "WHERE fn.is_document = 1"
        ).fetchone()[0]
        print(f"\n  evidence_rows query returns {ev_rows} row(s)")

        candidates = compute_candidates(conn, "run-isdoc0", "MOD-025-2", top_k=5)
        print(f"  → compute_candidates returned {len(candidates)} candidate(s)")
        conn.close()
        return len(candidates)


def scenario_wrong_standard_prefix() -> int:
    print("\n" + "=" * 78)
    print("SCENARIO 3: chunks have full standard name, caller passes short ID")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "wrong_prefix.db"
        conn = _build_db(db_path)
        # Simulate a parser that wrote 'Standard MOD-025-2' instead of 'MOD-025-2'
        conn.execute("UPDATE chunks SET standard_id = 'Standard MOD-025-2'")
        conn.commit()

        _dump(conn, "chunks after standard_id rewrite",
              "SELECT chunk_id, standard_id FROM chunks")

        # User calls with the canonical short ID.
        req = _fetch_req_chunks(conn, "MOD-025-2")
        print(f"\n  _fetch_req_chunks('MOD-025-2') returned {len(req)} chunk(s)")
        candidates = compute_candidates(conn, "run-wrongpre", "MOD-025-2", top_k=5)
        print(f"  → compute_candidates returned {len(candidates)} candidate(s)")
        conn.close()
        return len(candidates)


def scenario_no_evidence_text_rows() -> int:
    print("\n" + "=" * 78)
    print("SCENARIO 4: file_nodes flagged is_document=1 but evidence_text is empty")
    print("=" * 78)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "no_ev_text.db"
        conn = _build_db(db_path)
        conn.execute("DELETE FROM evidence_text")
        conn.commit()

        ev_rows = conn.execute(
            "SELECT COUNT(*) FROM file_nodes fn "
            "JOIN evidence_text et ON et.file_node_id = fn.id "
            "WHERE fn.is_document = 1"
        ).fetchone()[0]
        print(f"  evidence_rows query returns {ev_rows} row(s)")
        candidates = compute_candidates(conn, "run-noet", "MOD-025-2", top_k=5)
        print(f"  → compute_candidates returned {len(candidates)} candidate(s)")
        conn.close()
        return len(candidates)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    n1 = scenario_happy_path()
    n2 = scenario_is_document_zero()
    n3 = scenario_wrong_standard_prefix()
    n4 = scenario_no_evidence_text_rows()

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  Scenario 1 happy path:               {n1} candidate(s)")
    print(f"  Scenario 2 is_document=0:            {n2} candidate(s)")
    print(f"  Scenario 3 std_id prefix mismatch:   {n3} candidate(s)")
    print(f"  Scenario 4 no evidence_text rows:    {n4} candidate(s)")

    assert n1 > 0, (
        "Happy path returned 0 — matcher is broken in isolation, not just on Dell data"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
