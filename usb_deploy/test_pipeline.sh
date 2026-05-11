#!/bin/bash
# CDW Pre-sync pipeline validation
# No hardcoded standards or file names — discovers what's in NERC-DOCS at runtime.
#
# Note: set -u is intentionally NOT used here. Bash on macOS (3.2 and Homebrew 5)
# treats unset variables differently across heredoc subshell boundaries, causing
# false failures. Variables are validated explicitly below instead.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDW_ROOT="$SCRIPT_DIR/../compliance_workspace"
PYTHON="${PYTHON:-python3}"

# Use a project-local temp dir — avoids failures when /tmp is full on the host.
PIPE_TMP="$CDW_ROOT/data/.pipe_tmp"
mkdir -p "$PIPE_TMP"
export TMPDIR="$PIPE_TMP"   # bash heredocs write their temp files to TMPDIR

DB="$PIPE_TMP/cdw_presync_test_$$.db"
EV_FILE="$PIPE_TMP/cdw_test_ev_$$.txt"

cleanup() { rm -f "$DB" "$DB-wal" "$DB-shm" "$DB-journal" "$EV_FILE" "$PIPE_TMP/std_id.txt"; }
trap cleanup EXIT

echo "========================================"
echo "  CDW Pre-sync Pipeline Validation"
echo "  CDW root : $CDW_ROOT"
echo "  $(date)"
echo "========================================"

cd "$CDW_ROOT"

# Verify NERC-DOCS exists and has PDFs
NERC_DOCS="${NERC_DOCS_OVERRIDE:-$CDW_ROOT/NERC-DOCS}"
if [ ! -d "$NERC_DOCS" ]; then
  echo "  ✗ NERC-DOCS not found at $NERC_DOCS"
  exit 1
fi
PDF_COUNT=$(find "$NERC_DOCS" -maxdepth 1 -name "*.pdf" | wc -l | tr -d ' ')
if [ "$PDF_COUNT" -eq 0 ]; then
  echo "  ✗ No PDFs in NERC-DOCS"
  exit 1
fi
echo "  NERC-DOCS: $PDF_COUNT PDF(s) found"
if [ "$NERC_DOCS" != "$CDW_ROOT/NERC-DOCS" ]; then
  echo "  NERC-DOCS source: $NERC_DOCS"
fi

# ── 1. Chunk one PDF (first one discovered — no hardcoding) ─────────────────
echo ""
echo "[1/3] Chunking first available NERC PDF…"

RESULT=$($PYTHON - "$NERC_DOCS" "$DB" <<'PY'
import sys, sqlite3, pathlib, datetime, io

nerc_docs = pathlib.Path(sys.argv[1])
db_path   = sys.argv[2]

sys.path.insert(0, ".")
from mapper.db.schema import create_tables
from mapper.index.schema import create_chunk_tables
from mapper.reasoning.schema import create_reasoning_tables
from mapper.chunker.parser import parse_nerc_document
from mapper.chunker.chunker import build_chunks
from mapper.chunker.linker import build_relationships
from mapper.chunker.vsl import parse_vsl_table
from mapper.chunker.evidence import infer_evidence
from mapper.index.store import write_chunks, write_vsl_artifacts, write_relationships
from pdfminer.high_level import extract_text as pdf_text

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
create_tables(conn); create_chunk_tables(conn); create_reasoning_tables(conn)
conn.commit()

# System scan row
conn.execute("""INSERT INTO scans (scope_key,root_path,mode,scan_ts,
                   file_count,folder_count,skipped_count,duration_ms)
               VALUES ('nerc_standards',?,?,?,0,0,0,0)""",
             (str(nerc_docs), "system", datetime.datetime.utcnow().isoformat()))
conn.commit()
sid = conn.execute("SELECT scan_id FROM scans WHERE scope_key='nerc_standards'").fetchone()[0]

# Pick the first PDF that produces non-empty text
chosen_pdf = None
for pdf in sorted(nerc_docs.glob("*.pdf")):
    text = pdf_text(io.BytesIO(pdf.read_bytes()))
    if text.strip():
        chosen_pdf = pdf
        chosen_text = text
        break

assert chosen_pdf, "No readable PDF found in NERC-DOCS"

stat = chosen_pdf.stat()
conn.execute("""INSERT INTO file_nodes (scan_id,name,full_path,extension,size_bytes,
                   modified_ts,depth,parent_path,is_document)
               VALUES (?,?,?,'.pdf',?,?,0,?,1)""",
             (sid, chosen_pdf.name, str(chosen_pdf), stat.st_size,
              datetime.datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
              str(nerc_docs)))
conn.commit()
fn_id = conn.execute("SELECT id FROM file_nodes WHERE full_path=?",
                     (str(chosen_pdf),)).fetchone()[0]

units  = parse_nerc_document(chosen_text)
chunks = build_chunks(units, scan_id=sid, file_node_id=fn_id,
                      source_location=str(chosen_pdf),
                      document_title=chosen_pdf.stem)
assert chunks, f"build_chunks returned 0 chunks for {chosen_pdf.name}"

req_map = {c.metadata.requirement_id or "": c.text
           for c in chunks if c.metadata.chunk_type == "requirement"}
for c in chunks:
    if c.metadata.chunk_type in ("requirement","sub_requirement",
                                  "sub_sub_requirement","measure"):
        c.metadata.expected_evidence = infer_evidence(
            req_map.get(c.metadata.requirement_id or "", ""),
            c.text if c.metadata.chunk_type == "measure" else "")

std_id = chunks[0].metadata.standard_id
vsl_chunks, vsl_arts = parse_vsl_table(chosen_text, standard_id=std_id,
                                        scan_id=sid, file_node_id=fn_id,
                                        source_location=str(chosen_pdf))
all_chunks = chunks + vsl_chunks
write_chunks(conn, all_chunks)
if vsl_arts:  write_vsl_artifacts(conn, vsl_arts)
write_relationships(conn, build_relationships(all_chunks))
conn.commit()

n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
assert n_chunks > 0, f"0 chunks after processing {chosen_pdf.name}"
conn.close()
print(f"{chosen_pdf.name}|{std_id}|{n_chunks}")
PY
)

PDF_NAME=$(echo "$RESULT" | cut -d'|' -f1)
STD_ID=$(echo "$RESULT"   | cut -d'|' -f2)
N_CHUNKS=$(echo "$RESULT" | cut -d'|' -f3)

# Persist STD_ID to disk — bash on macOS can lose variables across heredoc
# subshell boundaries under set -euo pipefail. Reading from file is reliable.
echo "$STD_ID" > "$PIPE_TMP/std_id.txt"

if [ -z "$PDF_NAME" ] || [ -z "$STD_ID" ] || [ -z "$N_CHUNKS" ]; then
  echo "  ✗ Chunker output malformed: RESULT='$RESULT'"
  exit 1
fi
echo "  pdf=$PDF_NAME  standard=$STD_ID  chunks=$N_CHUNKS"
echo "  ✓ Chunker OK"

# ── 2. Synthetic evidence scan ───────────────────────────────────────────────
echo ""
echo "[2/3] Inserting synthetic evidence file (standard: $STD_ID)…"
echo "$STD_ID compliance evidence. This document demonstrates adherence to all requirements." > "$EV_FILE"

$PYTHON - "$DB" "$EV_FILE" <<'PY'
import sys, sqlite3, datetime, pathlib
db_path = sys.argv[1]
ev_path = pathlib.Path(sys.argv[2])
conn = sqlite3.connect(db_path)
conn.execute("""INSERT INTO scans (scope_key,root_path,mode,scan_ts,
                   file_count,folder_count,skipped_count,duration_ms)
               VALUES ('evidence',?,?,?,1,0,0,0)""",
             (str(ev_path.parent), "manual", datetime.datetime.utcnow().isoformat()))
conn.commit()
sid = conn.execute("SELECT scan_id FROM scans WHERE scope_key='evidence'").fetchone()[0]
conn.execute("""INSERT INTO file_nodes (scan_id,name,full_path,extension,size_bytes,
                   modified_ts,depth,parent_path,is_document)
               VALUES (?,?,?,'.txt',?,?,0,?,1)""",
             (sid, ev_path.name, str(ev_path), ev_path.stat().st_size,
              datetime.datetime.utcnow().isoformat(), str(ev_path.parent)))
conn.commit()
conn.close()
print(f"  evidence scan_id={sid}")
PY
echo "  ✓ Evidence scan OK"

# ── 3. Phase 3 reasoning (mock LLM, standard discovered from chunks) ─────────
# Re-read STD_ID from disk — guards against macOS bash variable scope loss
STD_ID=$(cat "$PIPE_TMP/std_id.txt" 2>/dev/null || echo "")
if [ -z "$STD_ID" ]; then
  echo "  ✗ STD_ID lost between steps — chunker may have failed silently"
  exit 1
fi
echo ""
echo "[3/3] Running --reason for $STD_ID…"

$PYTHON - "$DB" "$STD_ID" <<'PY'
import sys, sqlite3
sys.path.insert(0, ".")
from mapper.reasoning import matcher
from mapper.reasoning.runner import run_phase3

db_path   = sys.argv[1]
std_id    = sys.argv[2]

matcher._load_embedder = lambda: None

class MockLLM:
    inter_call_delay = 0

    def complete(self, system, user, **kw):
        return "verdict: Met\nrationale: Synthetic evidence satisfies the requirement."

conn = sqlite3.connect(db_path)
sid = conn.execute("SELECT scan_id FROM scans WHERE scope_key='evidence'").fetchone()[0]
run_phase3(conn, scan_id=sid, standard_id=std_id, backend=MockLLM(), verbose=False)
candidates  = conn.execute("SELECT COUNT(*) FROM evidence_candidates").fetchone()[0]
assessments = conn.execute("SELECT COUNT(*) FROM evidence_assessments").fetchone()[0]
gap_reports = conn.execute("SELECT COUNT(*) FROM gap_reports").fetchone()[0]
conn.close()
print(f"  candidates={candidates}  assessments={assessments}  gap_reports={gap_reports}")
assert candidates  > 0, f"FAIL: 0 candidates — matcher broken"
assert assessments > 0, f"FAIL: 0 assessments"
assert gap_reports > 0, f"FAIL: 0 gap_reports"
PY
echo "  ✓ Reasoning OK"

echo ""
echo "========================================"
echo "  ✅ ALL CHECKS PASSED — safe to sync"
echo "========================================"
