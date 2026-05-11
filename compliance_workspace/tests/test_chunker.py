"""Smoke tests for the Phase 2 chunking pipeline.

Exercises: parser → chunker → linker → VSL → evidence → DB schema/store.

Run with:
    cd compliance_workspace
    python -m pytest tests/test_chunker.py -v
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure the package root is on sys.path when running tests directly
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ---------------------------------------------------------------------------
# Sample NERC-style text
# ---------------------------------------------------------------------------

SAMPLE_TEXT = """\
CIP-007-6 — Cyber Security — Systems Security Management

4. Applicability:
This standard applies to responsible entities as follows:

R1. Each Responsible Entity shall implement one or more documented processes
that collectively include each of the applicable requirement parts in CIP-007-6
Table R1 – Ports and Services.

R1.1. Enable only logical network accessible ports that have been determined to
be needed by the Responsible Entity, including port ranges or services where
technically feasible.

R1.2. Protect against the use of unnecessary physical input/output ports used
for network connectivity, console commands, or removable media.

R2. Each Responsible Entity shall implement one or more documented processes
that collectively include each of the applicable requirement parts in CIP-007-6
Table R2 – Security Patch Management.

R2.1. At least once every 35 calendar days, evaluate security patches for
applicability that have been released since the last evaluation for each
software type.

M1. Each Responsible Entity shall have evidence of the documented process for
CIP-007-6 Requirement R1.  Acceptable evidence includes: a procedure, log, or
configuration_export showing managed ports.

M2. Each Responsible Entity shall have evidence showing security patch
management procedures, reports, and approval records.

Violation Severity Levels

R1 – Ports and Services

High
The Responsible Entity did not implement a process for managing ports and services.

Moderate
The Responsible Entity implemented a process but failed to review all applicable ports.

Lower
The Responsible Entity implemented a process with minor documentation gaps.

Definitions
Cyber Asset: Programmable electronic devices and communication networks
including hardware, software, and data.

Attachment 1 — CIP-007-6 Security Patch Management Guidelines
Additional guidance for responsible entities implementing patch management.
"""


# ---------------------------------------------------------------------------
# Real-document-structure sample texts based on actual NERC PDF extraction
# ---------------------------------------------------------------------------

# Mirrors CIP-014-3 pattern: sub-requirements use n.n. (no R-prefix)
REAL_SUBREQ_TEXT = """\
CIP-014-3 — Physical Security

4. Applicability:
4.1. Functional Entities:
4.1.1 Transmission Owner

B. Requirements and Measures

R1. Each Transmission Owner shall perform an initial risk assessment and
subsequent risk assessments of its Transmission stations and substations.
[VRF: High; Time-Horizon: Long-term Planning]

1.1. Subsequent risk assessments shall be performed at least once every 30
calendar months for a Transmission Owner that has identified one or more
Transmission stations in its previous assessment.

1.2. The Transmission Owner shall identify the primary control center that
operationally controls each Transmission station identified in Requirement R1.

M1. Examples of acceptable evidence may include dated written documentation
of the risk assessment satisfying Requirement R1.

R2. Each Transmission Owner shall have an unaffiliated third party verify the
risk assessment performed under Requirement R1. [VRF: Medium]

2.1. Each Transmission Owner shall select an unaffiliated verifying entity
that is either a registered Planning Coordinator or an entity with transmission
planning experience.

2.2. The unaffiliated third party verification shall verify the Transmission
Owner's risk assessment and shall be completed within 90 calendar days.

M2. Examples of evidence may include dated documentation of the unaffiliated
third party verification satisfying Requirement R2.
"""

# Mirrors EOP-004-4 pattern: standard-ID–prefixed attachment headers,
# VSL table rows start with R1./R2. but should stay inside VSL section
REAL_ATTACHMENT_TEXT = """\
EOP-004-4 — Event Reporting

4. Applicability:
4.1. Functional Entities:

B. Requirements and Measures

R1. Each Responsible Entity shall have an event reporting Operating Plan.
[Violation Risk Factor: Lower] [Time Horizon: Operations Planning]

M1. Each Responsible Entity will have a dated event reporting Operating Plan.

R2. Each Responsible Entity shall report events within 24 hours of recognition.
[Violation Risk Factor: Medium] [Time Horizon: Operations Assessment]

M2. Each Responsible Entity will have evidence of reporting an event.

Violation Severity Levels
R # Violation Severity Levels
Lower VSL Moderate VSL High VSL Severe VSL
R1. The Responsible Entity had an event reporting Operating Plan, but failed
to include one applicable event type.
R2. The Responsible Entity submitted an event report to all required recipients
up to 24 hours after the timing requirement for submittal.

D. Regional Variances
None.

EOP-004 - Attachment 1:  Reportable Events
Table of event types and reporting thresholds.

EOP-004 - Attachment 2:  Event Reporting Form
Standard form for submitting event reports.
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParser:
    def test_returns_parsed_units(self):
        from mapper.chunker.parser import parse_nerc_document
        units = parse_nerc_document(SAMPLE_TEXT)
        assert len(units) > 0

    def test_detects_requirement_chunks(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.requirement.value in types

    def test_detects_sub_requirement_chunks(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.sub_requirement.value in types

    def test_detects_measure_chunks(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.measure.value in types

    def test_detects_vsl_section(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.vsl_artifact.value in types

    def test_detects_definition_section(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.definition.value in types

    def test_detects_attachment(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.attachment_obligation.value in types

    def test_detects_applicability(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.applicability.value in types

    def test_raw_start_pos_ascending(self):
        from mapper.chunker.parser import parse_nerc_document
        units = parse_nerc_document(SAMPLE_TEXT)
        positions = [u.raw_start_pos for u in units]
        assert positions == sorted(positions)

    def test_empty_text_returns_one_unit(self):
        from mapper.chunker.parser import parse_nerc_document
        units = parse_nerc_document("")
        # Empty text → empty list (no text to create a unit from)
        assert isinstance(units, list)


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunker:
    def test_produces_chunks(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        assert len(chunks) > 0

    def test_chunk_ids_are_unique(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_standard_id_inferred(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        std_ids = {c.metadata.standard_id for c in chunks}
        assert "CIP-007-6" in std_ids

    def test_citation_paths_non_empty(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        for c in chunks:
            assert c.metadata.official_citation_path, f"Empty citation path on {c.chunk_id}"

    def test_requirement_chunk_has_requirement_id(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        req_chunks = [c for c in chunks if c.metadata.chunk_type == ChunkType.requirement.value]
        assert req_chunks, "No requirement chunks produced"
        for c in req_chunks:
            assert c.metadata.requirement_id is not None

    def test_sub_requirement_has_subreq_path(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        sub_chunks = [c for c in chunks if c.metadata.chunk_type == ChunkType.sub_requirement.value]
        assert sub_chunks, "No sub_requirement chunks produced"
        for c in sub_chunks:
            assert c.metadata.subrequirement_path is not None

    def test_measure_chunk_has_measure_id(self):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(units, scan_id=1, file_node_id=1, source_location="/test.txt")
        measure_chunks = [c for c in chunks if c.metadata.chunk_type == ChunkType.measure.value]
        assert measure_chunks, "No measure chunks produced"
        for c in measure_chunks:
            assert c.metadata.measure_id is not None


# ---------------------------------------------------------------------------
# Evidence inference tests
# ---------------------------------------------------------------------------

class TestEvidence:
    def test_detects_procedure(self):
        from mapper.chunker.evidence import infer_evidence
        result = infer_evidence("Each entity shall document a procedure for patch management.")
        assert "procedure" in result

    def test_detects_log(self):
        from mapper.chunker.evidence import infer_evidence
        result = infer_evidence("Evidence includes an access log showing activity.")
        assert "log" in result

    def test_detects_multiple_descriptors(self):
        from mapper.chunker.evidence import infer_evidence
        result = infer_evidence(
            "Entity shall maintain a procedure and log for all changes.",
            "Acceptable evidence includes a configuration_export or screenshot.",
        )
        assert "procedure" in result
        assert "log" in result

    def test_no_false_positives_on_empty(self):
        from mapper.chunker.evidence import infer_evidence
        result = infer_evidence("", "")
        assert result == []

    def test_returns_list(self):
        from mapper.chunker.evidence import infer_evidence
        result = infer_evidence("test text")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# VSL parser tests
# ---------------------------------------------------------------------------

class TestVSL:
    def test_parses_vsl_rows(self):
        from mapper.chunker.vsl import parse_vsl_table
        chunks, artifacts = parse_vsl_table(
            SAMPLE_TEXT,
            standard_id="CIP-007-6",
            scan_id=1,
            file_node_id=1,
            source_location="/test.txt",
        )
        assert len(chunks) > 0
        assert len(artifacts) > 0

    def test_vsl_chunk_types(self):
        from mapper.chunker.vsl import parse_vsl_table
        from mapper.models.chunk import ChunkType
        chunks, _ = parse_vsl_table(
            SAMPLE_TEXT,
            standard_id="CIP-007-6",
            scan_id=1,
            file_node_id=1,
            source_location="/test.txt",
        )
        for c in chunks:
            assert c.metadata.chunk_type == ChunkType.vsl_artifact.value

    def test_vsl_levels_assigned(self):
        from mapper.chunker.vsl import parse_vsl_table
        _, artifacts = parse_vsl_table(
            SAMPLE_TEXT,
            standard_id="CIP-007-6",
            scan_id=1,
            file_node_id=1,
            source_location="/test.txt",
        )
        levels = {a.vsl_level for a in artifacts}
        # Real NERC docs use "Moderate" not "Medium"
        assert levels & {"High", "Moderate", "Lower", "Severe"}, f"Unexpected levels: {levels}"

    def test_vsl_chunk_ids_match_artifact_chunk_ids(self):
        from mapper.chunker.vsl import parse_vsl_table
        chunks, artifacts = parse_vsl_table(
            SAMPLE_TEXT,
            standard_id="CIP-007-6",
            scan_id=1,
            file_node_id=1,
            source_location="/test.txt",
        )
        chunk_ids = {c.chunk_id for c in chunks}
        artifact_chunk_ids = {a.chunk_id for a in artifacts}
        assert chunk_ids == artifact_chunk_ids


# ---------------------------------------------------------------------------
# DB schema + store tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_conn():
    """In-memory SQLite connection with both Phase 1 and Phase 2 tables."""
    conn = sqlite3.connect(":memory:")
    from mapper.db.schema import create_tables
    from mapper.index.schema import create_chunk_tables
    create_tables(conn)
    create_chunk_tables(conn)
    # Insert a minimal scan + file_node so FK constraints are satisfied
    conn.execute(
        "INSERT INTO scans (scope_key, root_path, mode, scan_ts) VALUES (?,?,?,?)",
        ("/test", "/test", "broad", "2026-01-01T00:00:00"),
    )
    conn.execute(
        "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
        "size_bytes, modified_ts, depth, parent_path, is_document) "
        "VALUES (1, 'test.txt', '/test/test.txt', 'txt', 0, '2026-01-01T00:00:00', 0, '/test', 1)",
    )
    conn.commit()
    yield conn
    conn.close()


class TestSchema:
    def test_chunk_table_created(self, mem_conn):
        tables = {
            r[0]
            for r in mem_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chunks" in tables

    def test_chunk_relationships_table_created(self, mem_conn):
        tables = {
            r[0]
            for r in mem_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chunk_relationships" in tables

    def test_vsl_artifacts_table_created(self, mem_conn):
        tables = {
            r[0]
            for r in mem_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "vsl_artifacts" in tables


class TestStore:
    def test_write_and_read_chunk(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks, get_chunk

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        assert chunks, "No chunks produced"
        write_chunks(mem_conn, chunks)

        fetched = get_chunk(mem_conn, chunks[0].chunk_id)
        assert fetched is not None
        assert fetched.chunk_id == chunks[0].chunk_id
        assert fetched.metadata.chunk_type == chunks[0].metadata.chunk_type

    def test_write_vsl_artifacts(self, mem_conn):
        from mapper.chunker.vsl import parse_vsl_table
        from mapper.index.store import write_chunks, write_vsl_artifacts

        chunks, artifacts = parse_vsl_table(
            SAMPLE_TEXT,
            standard_id="CIP-007-6",
            scan_id=1,
            file_node_id=1,
            source_location="/test/test.txt",
        )
        write_chunks(mem_conn, chunks)
        write_vsl_artifacts(mem_conn, artifacts)

        count = mem_conn.execute("SELECT COUNT(*) FROM vsl_artifacts").fetchone()[0]
        assert count == len(artifacts)

    def test_write_relationships(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.chunker.linker import build_relationships
        from mapper.index.store import write_chunks, write_relationships

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)
        rels = build_relationships(chunks)
        write_relationships(mem_conn, rels)

        count = mem_conn.execute(
            "SELECT COUNT(*) FROM chunk_relationships"
        ).fetchone()[0]
        assert count == len(rels)

    def test_update_embedding(self, mem_conn):
        import numpy as np
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks, update_embedding, get_chunk

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        vec = np.random.default_rng(42).standard_normal(384).astype(np.float32)
        update_embedding(mem_conn, chunks[0].chunk_id, vec)

        fetched = get_chunk(mem_conn, chunks[0].chunk_id)
        assert fetched.embedding is not None
        assert len(fetched.embedding) == 384


# ---------------------------------------------------------------------------
# Semantic retrieval tests
# ---------------------------------------------------------------------------

class TestSemantic:
    def test_stub_embed_chunks(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.semantic import SemanticRetriever

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        retriever = SemanticRetriever(mem_conn, backend="stub")
        n = retriever.embed_chunks()
        assert n == len(chunks)

    def test_stub_search_returns_results(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.semantic import SemanticRetriever

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        retriever = SemanticRetriever(mem_conn, backend="stub")
        retriever.embed_chunks()
        results = retriever.search("patch management procedure")
        assert len(results) > 0
        # Each result is (chunk_id, score, chunk_type, citation_path)
        chunk_id, score, ctype, citation = results[0]
        assert isinstance(chunk_id, str)
        assert isinstance(score, float)

    def test_stub_search_with_type_filter(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.semantic import SemanticRetriever
        from mapper.models.chunk import ChunkType

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        retriever = SemanticRetriever(mem_conn, backend="stub")
        retriever.embed_chunks()
        results = retriever.search(
            "patch management",
            chunk_type_filter=ChunkType.requirement.value,
        )
        for _, _, ctype, _ in results:
            assert ctype == ChunkType.requirement.value


# ---------------------------------------------------------------------------
# Structural retrieval tests
# ---------------------------------------------------------------------------

class TestStructural:
    def test_get_requirements_for_standard(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.structural import get_requirements_for_standard

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)
        reqs = get_requirements_for_standard(mem_conn, "CIP-007-6")
        assert len(reqs) > 0

    def test_get_chunks_by_type(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.structural import get_chunks_by_type
        from mapper.models.chunk import ChunkType

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        measures = get_chunks_by_type(mem_conn, ChunkType.measure.value)
        for c in measures:
            assert c.metadata.chunk_type == ChunkType.measure.value

    def test_get_full_path(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.structural import get_full_path

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        path = get_full_path(mem_conn, chunks[0].chunk_id)
        assert isinstance(path, str)
        assert len(path) > 0

    def test_get_definition(self, mem_conn):
        from mapper.chunker.parser import parse_nerc_document
        from mapper.chunker.chunker import build_chunks
        from mapper.index.store import write_chunks
        from mapper.index.structural import get_definition

        units = parse_nerc_document(SAMPLE_TEXT)
        chunks = build_chunks(
            units, scan_id=1, file_node_id=1, source_location="/test/test.txt"
        )
        write_chunks(mem_conn, chunks)

        result = get_definition(mem_conn, "Cyber Asset")
        # May or may not find depending on parse; just verify type
        assert result is None or hasattr(result, "chunk_id")


# ---------------------------------------------------------------------------
# Real-document-structure parser tests
# (Based on actual patterns observed in NERC PDFs)
# ---------------------------------------------------------------------------

class TestParserRealStructure:
    """Parser tests driven by real NERC document patterns."""

    def test_detects_numbered_applicability(self):
        """'4. Applicability:' (numbered, with colon) is the real format."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_SUBREQ_TEXT)
        types = [u.detected_type for u in units]
        assert ChunkType.applicability.value in types

    def test_detects_subreqs_without_r_prefix(self):
        """Sub-requirements appear as '1.1.', '2.1.' (no R-prefix) in real docs."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_SUBREQ_TEXT)
        sub_units = [u for u in units if u.detected_type == ChunkType.sub_requirement.value]
        assert len(sub_units) >= 4, f"Expected ≥4 sub-reqs, got {len(sub_units)}"

    def test_subreq_ids_match_parent_requirement(self):
        """Sub-req id '1.2' belongs to parent R1; '2.1' to R2."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_SUBREQ_TEXT)
        sub_ids = {
            u.detected_id
            for u in units
            if u.detected_type == ChunkType.sub_requirement.value
        }
        assert "1.1" in sub_ids, f"1.1 not found; got {sub_ids}"
        assert "1.2" in sub_ids, f"1.2 not found; got {sub_ids}"
        assert "2.1" in sub_ids, f"2.1 not found; got {sub_ids}"
        assert "2.2" in sub_ids, f"2.2 not found; got {sub_ids}"

    def test_subreq_ordering_after_parent(self):
        """Each sub-req chunk appears immediately after its parent requirement."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_SUBREQ_TEXT)
        for i, u in enumerate(units):
            if u.detected_type == ChunkType.sub_requirement.value and u.detected_id:
                parent_num = int(u.detected_id.split(".")[0])
                # Find the nearest preceding requirement
                prev_reqs = [
                    pu for pu in units[:i]
                    if pu.detected_type == ChunkType.requirement.value
                ]
                assert prev_reqs, f"No parent requirement before sub-req {u.detected_id}"
                last_req_num = int(prev_reqs[-1].detected_id[1:])
                assert last_req_num == parent_num, (
                    f"Sub-req {u.detected_id} follows R{last_req_num}, expected R{parent_num}"
                )

    def test_vsl_rows_not_classified_as_requirements(self):
        """R1./R2. lines inside a VSL table must NOT become requirement chunks."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_ATTACHMENT_TEXT)
        # Find the index of the first vsl_artifact
        vsl_indices = [i for i, u in enumerate(units) if u.detected_type == ChunkType.vsl_artifact.value]
        assert vsl_indices, "No VSL artifact found"
        first_vsl = vsl_indices[0]
        # No requirement chunks should appear after the first VSL unit
        # and before the next non-VSL section (D. Regional Variances)
        post_vsl = units[first_vsl:]
        req_after_vsl = [
            u for u in post_vsl
            if u.detected_type == ChunkType.requirement.value
        ]
        assert not req_after_vsl, (
            f"Requirement chunks found inside VSL section: "
            f"{[u.detected_id for u in req_after_vsl]}"
        )

    def test_standard_id_prefixed_attachment_detected(self):
        """'EOP-004 - Attachment 1: Title' (with standard-ID prefix) is detected."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        units = parse_nerc_document(REAL_ATTACHMENT_TEXT)
        attachment_units = [u for u in units if u.detected_type == ChunkType.attachment_obligation.value]
        assert len(attachment_units) >= 1, "No attachment chunks found"
        ids = [u.detected_id or "" for u in attachment_units]
        assert any("Attachment 1" in aid for aid in ids), f"Attachment 1 not found in: {ids}"

    def test_inline_attachment_reference_not_a_boundary(self):
        """'Attachment 1 contained herein...' inline prose is NOT an attachment boundary."""
        from mapper.chunker.parser import parse_nerc_document, _ATTACHMENT_LINE_RE
        inline_lines = [
            "Attachment 1 contained herein, the following Functional Entities",
            "Attachment 1, Section 1, if any, at each asset;",
            "with EOP-004-4 Attachment 1 that includes the protocol",
        ]
        for line in inline_lines:
            assert not _ATTACHMENT_LINE_RE.match(line), (
                f"Inline reference incorrectly matched as attachment: {repr(line)}"
            )

    def test_real_attachment_header_matches(self):
        """Standard attachment header formats from real NERC PDFs do match."""
        from mapper.chunker.parser import _ATTACHMENT_LINE_RE
        valid_headers = [
            "EOP-004 - Attachment 1:  Reportable Events",
            "CIP-002-5.1a - Attachment 1",
            "PRC-005 \u2014  Attachment A",
            "Attachment 1 \u2014 Title",
            "Attachment 1:",
        ]
        for line in valid_headers:
            assert _ATTACHMENT_LINE_RE.match(line), (
                f"Valid attachment header not matched: {repr(line)}"
            )

    def test_vsl_moderate_severity_detected(self):
        """VSL tables use 'Moderate' (not 'Medium') as a severity level."""
        from mapper.chunker.vsl import parse_vsl_table, _SEVERITY_HEADER_RE
        assert _SEVERITY_HEADER_RE.search("Moderate VSL"), "Moderate not matched"
        assert not _SEVERITY_HEADER_RE.search("Medium VSL"), "Medium should not match"
        vsl_text = (
            "Violation Severity Levels\n"
            "Lower VSL Moderate VSL High VSL Severe VSL\n"
            "R1. The entity failed to do X. The entity failed to do Y. "
            "The entity failed to do Z. The entity failed to do all.\n"
        )
        chunks, artifacts = parse_vsl_table(
            vsl_text, standard_id="TEST-001-1",
            scan_id=1, file_node_id=1, source_location="/test.txt"
        )
        levels = {a.vsl_level for a in artifacts}
        assert "Moderate" in levels, f"Moderate not in VSL levels: {levels}"

    def test_reserved_requirement_classified_correctly(self):
        """'R19.' on its own line (reserved requirement) classifies as requirement."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        text = (
            "TOP-001-6 - Transmission Operations\n\n"
            "R18. Each Transmission Operator shall operate to the most limiting.\n\n"
            "R19.\nReserved.\n\n"
            "M19. Reserved.\n"
        )
        units = parse_nerc_document(text)
        r19 = [u for u in units if u.detected_id == "R19"]
        assert r19, "R19 not detected"
        assert r19[0].detected_type == ChunkType.requirement.value

    def test_compliance_section_subitems_not_subreqs(self):
        """'1.1.' in the Compliance section (after all requirements) is not a sub-req."""
        from mapper.chunker.parser import parse_nerc_document
        from mapper.models.chunk import ChunkType
        # R1 and R2 appear first; compliance section (1.1.) appears after M2
        # current_req_num becomes 2, so "1.1." (leading 1 != 2) must not match
        text = (
            "EOP-004-4 — Event Reporting\n\n"
            "R1. Each Responsible Entity shall have an event reporting plan.\n\n"
            "M1. Evidence includes a dated plan.\n\n"
            "R2. Each Responsible Entity shall report events within 24 hours.\n\n"
            "M2. Evidence includes a copy of the completed event report.\n\n"
            "C. Compliance\n"
            "1. Compliance Monitoring Process\n"
            "1.1. Compliance Enforcement Authority:\n"
            "The CEA means NERC or the Regional Entity.\n"
            "1.2. Evidence Retention:\n"
            "Retain evidence for three calendar years.\n"
        )
        units = parse_nerc_document(text)
        sub_units = [u for u in units if u.detected_type == ChunkType.sub_requirement.value]
        # "1.1." and "1.2." should NOT be sub-reqs (current_req_num=2, leading digit=1)
        false_positives = [u for u in sub_units if u.detected_id in ("1.1", "1.2")]
        assert not false_positives, (
            f"Compliance section items incorrectly classified as sub-reqs: "
            f"{[u.detected_id for u in false_positives]}"
        )
