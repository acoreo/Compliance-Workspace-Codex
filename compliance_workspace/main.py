"""Entry point for the Compliance Discovery Workspace application."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root and set up sys.path so the package is importable
# whether the user runs `python main.py` from the project root or installs
# the package via pip.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mapper.db.schema import create_tables
from mapper.index.schema import create_chunk_tables
from mapper.reasoning.schema import create_reasoning_tables


def _init_db(db_path: Path) -> str:
    """Ensure the database file and schema exist; return the absolute path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        create_tables(conn)
        create_chunk_tables(conn)
        create_reasoning_tables(conn)
    finally:
        conn.close()
    return str(db_path)


# ---------------------------------------------------------------------------
# Text extraction helpers (all optional dependencies degrade gracefully)
# ---------------------------------------------------------------------------

def _extract_text_pdf(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text as _pdf_extract  # type: ignore
        return _pdf_extract(str(path)) or ""
    except Exception:
        return path.read_bytes().decode("utf-8", errors="replace")


def _extract_text_docx(path: Path) -> str:
    try:
        import docx  # type: ignore
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return path.read_bytes().decode("utf-8", errors="replace")


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _extract_text_pdf(path)
    if ext in ("docx", "doc"):
        return _extract_text_docx(path)
    # txt, csv, and everything else
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Chunk pipeline
# ---------------------------------------------------------------------------

def _ensure_nerc_system_scan(conn: sqlite3.Connection) -> int:
    """Get or create a dedicated system scan for NERC standard PDFs.

    Returns the scan_id of the 'nerc_standards' system scan.
    The NERC-DOCS directory is always chunked from disk regardless of what
    the user has scanned — this keeps standard PDFs separate from evidence.
    """
    import datetime

    row = conn.execute(
        "SELECT scan_id FROM scans WHERE scope_key = 'nerc_standards' LIMIT 1"
    ).fetchone()
    if row:
        return row[0]

    nerc_docs = _PROJECT_ROOT / "NERC-DOCS"
    conn.execute(
        """INSERT INTO scans (scope_key, root_path, mode, scan_ts,
               file_count, folder_count, skipped_count, duration_ms)
           VALUES (?, ?, ?, ?, 0, 0, 0, 0)""",
        ("nerc_standards", str(nerc_docs), "system", datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT scan_id FROM scans WHERE scope_key = 'nerc_standards' LIMIT 1"
    ).fetchone()
    return row[0]


def _upsert_nerc_file_nodes(conn: sqlite3.Connection, scan_id: int) -> list[tuple]:
    """Insert NERC-DOCS PDFs into file_nodes (skip if already present).

    Returns list of (file_node_id, full_path, name) for all NERC PDFs.
    """
    import datetime

    nerc_docs = _PROJECT_ROOT / "NERC-DOCS"
    if not nerc_docs.is_dir():
        return []

    results = []
    for pdf in sorted(nerc_docs.glob("*.pdf")):
        full_path = str(pdf)
        existing = conn.execute(
            "SELECT id FROM file_nodes WHERE full_path = ?", (full_path,)
        ).fetchone()
        if existing:
            results.append((existing[0], full_path, pdf.name))
            continue

        stat = pdf.stat()
        conn.execute(
            """INSERT INTO file_nodes
               (scan_id, name, full_path, extension, size_bytes, modified_ts,
                depth, parent_path, is_document)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                scan_id,
                pdf.name,
                full_path,
                ".pdf",
                stat.st_size,
                datetime.datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                0,
                str(nerc_docs),
            ),
        )
        file_node_id = conn.execute(
            "SELECT id FROM file_nodes WHERE full_path = ?", (full_path,)
        ).fetchone()[0]
        results.append((file_node_id, full_path, pdf.name))

    conn.commit()
    return results


def _run_chunking(db_str: str) -> None:
    """Chunk all NERC standard PDFs from the embedded NERC-DOCS directory.

    Reads directly from compliance_workspace/NERC-DOCS/ on disk — independent
    of whatever evidence folder the user has scanned.  Creates a dedicated
    'nerc_standards' system scan row so FK constraints are satisfied.
    """
    from mapper.chunker.parser import parse_nerc_document
    from mapper.chunker.chunker import build_chunks
    from mapper.chunker.linker import build_relationships
    from mapper.chunker.vsl import parse_vsl_table
    from mapper.chunker.evidence import infer_evidence
    from mapper.index.store import write_chunks, write_vsl_artifacts, write_relationships

    conn = sqlite3.connect(db_str)
    try:
        scan_id = _ensure_nerc_system_scan(conn)
        rows = _upsert_nerc_file_nodes(conn, scan_id)

        if not rows:
            print("No NERC PDFs found in NERC-DOCS/ — check that the directory exists.")
            return

        print(f"Chunking {len(rows)} NERC standard PDF(s) from NERC-DOCS/…")

        for file_node_id, full_path, name in rows:
            path = Path(full_path)
            if not path.exists():
                print(f"  SKIP (not found): {full_path}")
                continue

            print(f"  {name}")
            text = _extract_text(path)
            if not text.strip():
                print(f"    (empty text, skipped)")
                continue

            # Determine document title from filename
            doc_title = path.stem

            # Parse → chunk
            units = parse_nerc_document(text)
            chunks = build_chunks(
                units,
                scan_id=scan_id,
                file_node_id=file_node_id,
                source_location=full_path,
                document_title=doc_title,
            )

            if not chunks:
                continue

            # Infer evidence descriptors for requirement + measure chunks
            req_text_map: dict[str, str] = {}
            for c in chunks:
                if c.metadata.chunk_type == "requirement":
                    req_id = c.metadata.requirement_id or ""
                    req_text_map[req_id] = c.text

            for c in chunks:
                if c.metadata.chunk_type in ("requirement", "sub_requirement",
                                              "sub_sub_requirement", "measure"):
                    req_text = req_text_map.get(c.metadata.requirement_id or "", "")
                    measure_text = c.text if c.metadata.chunk_type == "measure" else ""
                    c.metadata.expected_evidence = infer_evidence(req_text, measure_text)

            # VSL parsing
            std_id = chunks[0].metadata.standard_id
            vsl_chunks, vsl_artifacts = parse_vsl_table(
                text,
                standard_id=std_id,
                scan_id=scan_id,
                file_node_id=file_node_id,
                source_location=full_path,
            )
            all_chunks = chunks + vsl_chunks

            # Build relationships (mutates chunk metadata in place)
            relationships = build_relationships(all_chunks)

            # Persist
            write_chunks(conn, all_chunks)
            if vsl_artifacts:
                write_vsl_artifacts(conn, vsl_artifacts)
            if relationships:
                write_relationships(conn, relationships)

            print(f"    → {len(all_chunks)} chunk(s), {len(vsl_artifacts)} VSL artifact(s)")

    finally:
        conn.close()

    print("Chunking complete.")


# ---------------------------------------------------------------------------
# Phase 3 reasoning entry point
# ---------------------------------------------------------------------------

def _run_reasoning(db_str: str, args) -> None:
    """Run the Phase 3 gap-analysis pipeline (headless)."""
    import datetime

    from mapper.reasoning.llm import LlamaCppBackend
    from mapper.reasoning.runner import run_phase3

    if args.scan_id is None:
        print("Error: --scan-id is required with --reason.")
        sys.exit(1)
    if not args.standard:
        print("Error: --standard is required with --reason.")
        sys.exit(1)

    config_path = _PROJECT_ROOT / "config" / "cdw_config.toml"
    backend = LlamaCppBackend.from_config(config_path)

    conn = sqlite3.connect(db_str)
    try:
        report_id = run_phase3(
            conn,
            scan_id=args.scan_id,
            standard_id=args.standard,
            run_id=args.run_id or None,
            backend=backend,
            verbose=True,
        )

        # Retrieve HTML from DB and save to data/reports/
        row = conn.execute(
            "SELECT report_html, run_id FROM gap_reports WHERE rowid = ?",
            (int(report_id),),
        ).fetchone()
        if row:
            html, run_id = row
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir = _PROJECT_ROOT / "data" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            out_path = report_dir / f"{args.standard}_{ts}.html"
            out_path.write_text(html, encoding="utf-8")
            print(f"\nHTML report saved to: {out_path}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI + GUI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compliance Discovery Workspace"
    )
    parser.add_argument(
        "--chunk",
        action="store_true",
        help=(
            "Run the NERC chunking pipeline on all documents from the last scan "
            "and exit (headless — no GUI)."
        ),
    )
    parser.add_argument(
        "--reason",
        action="store_true",
        help=(
            "Run the Phase 3 reasoning / gap-analysis pipeline and exit "
            "(requires --scan-id and --standard)."
        ),
    )
    parser.add_argument(
        "--scan-id",
        type=int,
        default=None,
        metavar="ID",
        help="scan_id to use as the evidence source for --reason.",
    )
    parser.add_argument(
        "--standard",
        type=str,
        default=None,
        metavar="STANDARD_ID",
        help='NERC standard to assess, e.g. "CIP-007-6".',
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        metavar="UUID",
        help=(
            "Resume a previous --reason run using its run_id (UUID printed at run start). "
            "Already-assessed candidate pairs are skipped; matching is re-run but idempotent."
        ),
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        metavar="PATH",
        help="Override the default workspace.db path (useful for testing).",
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else _PROJECT_ROOT / "data" / "workspace.db"
    db_str = _init_db(db_path)

    if args.chunk:
        _run_chunking(db_str)
        return

    if args.reason:
        _run_reasoning(db_str, args)
        return

    # PySide6 import deferred so the DB can be initialised even in headless
    # environments (import verification, CI, etc.).
    from PySide6.QtWidgets import QApplication
    from mapper.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Compliance Discovery Workspace")
    app.setOrganizationName("ComplianceWS")

    window = MainWindow(db_str)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
