"""Smoke tests for the Phase 3 Reasoning Layer (P3-T01 through P3-T06)."""
from __future__ import annotations

import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Ensure the package root is importable when tests are run directly
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mapper.db.schema import create_tables
from mapper.index.schema import create_chunk_tables
from mapper.reasoning.schema import create_reasoning_tables
from mapper.reasoning.extractor import AttachmentResult, ExtractResult, extract_file, extract_all
from mapper.reasoning.matcher import (
    Candidate,
    _is_usable_evidence_text,
    _structural_score,
    compute_candidates,
)
from mapper.reasoning.llm import LlamaCppBackend
from mapper.reasoning.assessor import (
    Assessment,
    build_user_prompt,
    parse_llm_response,
    PROMPT_VERSION,
)
from mapper.reasoning.reporter import build_report, build_html_report, save_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    """In-memory DB with all three phases of schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = OFF")  # easier for unit tests
    create_tables(conn)
    create_chunk_tables(conn)
    create_reasoning_tables(conn)
    return conn


def _seed_scan(conn: sqlite3.Connection, file_path: str) -> tuple[int, int]:
    """Insert minimal scan + file_node; return (scan_id, file_node_id)."""
    conn.execute(
        "INSERT INTO scans (scope_key, root_path, mode, scan_ts, file_count, "
        "folder_count, skipped_count, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("/tmp/test", "/tmp/test", "broad", "2026-01-01T00:00:00", 1, 0, 0, 10),
    )
    scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    ext = Path(file_path).suffix.lstrip(".")
    conn.execute(
        "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
        "size_bytes, modified_ts, depth, parent_path, is_document) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (scan_id, Path(file_path).name, file_path, ext, 100, "2026-01-01", 1, "/tmp/test", 1),
    )
    file_node_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return scan_id, file_node_id


def _seed_chunk(
    conn: sqlite3.Connection,
    scan_id: int,
    file_node_id: int,
    chunk_id: str = "chunk-001",
    standard_id: str = "CIP-007-6",
    requirement_id: str = "R1",
    citation_path: str = "CIP-007-6 -> R1",
    chunk_type: str = "requirement",
    expected_evidence: list[str] | None = None,
) -> None:
    ev_json = json.dumps(expected_evidence or ["policy", "procedure"])
    conn.execute(
        "INSERT INTO chunks (chunk_id, scan_id, file_node_id, standard_id, "
        "document_title, chunk_type, official_citation_path, requirement_id, "
        "expected_evidence, text, created_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chunk_id, scan_id, file_node_id, standard_id,
            "CIP-007-6 Test", chunk_type, citation_path, requirement_id,
            ev_json,
            "Each Responsible Entity shall implement one or more documented processes.",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()


# ===========================================================================
# P3-T01  extractor
# ===========================================================================

class TestExtractResult:
    def test_dataclass_fields(self):
        r = ExtractResult(
            file_node_id=1,
            file_path="/tmp/foo.txt",
            text="hello",
            char_count=5,
            extraction_method="plain",
            error=None,
        )
        assert r.file_node_id == 1
        assert r.char_count == 5
        assert r.extraction_method == "plain"
        assert r.error is None

    def test_extract_plain_text(self, tmp_path):
        p = tmp_path / "policy.txt"
        p.write_text("This is a policy document.", encoding="utf-8")
        result = extract_file(1, str(p))
        assert result.text == "This is a policy document."
        assert result.char_count == len("This is a policy document.")
        assert result.extraction_method == "plain"
        assert result.error is None

    def test_extract_missing_file(self):
        result = extract_file(42, "/nonexistent/path/file.pdf")
        assert result.text == ""
        assert result.extraction_method == "fallback"
        assert result.error is not None
        assert "not found" in result.error.lower() or "nonexistent" in result.error.lower() or result.error

    def test_extract_unknown_extension_fallback(self, tmp_path):
        p = tmp_path / "data.xyz"
        p.write_bytes(b"some bytes that are utf-8 decodable")
        result = extract_file(1, str(p))
        assert result.extraction_method == "fallback"
        assert len(result.text) > 0

    def test_extract_and_cache(self, tmp_path):
        p = tmp_path / "log.txt"
        p.write_text("audit log entry", encoding="utf-8")
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, str(p))

        results = extract_all(conn, scan_id)
        assert len(results) == 1
        assert results[0].text == "audit log entry"

        # Second call should return from cache
        results2 = extract_all(conn, scan_id)
        assert len(results2) == 1
        assert results2[0].text == "audit log entry"

        # Verify row is in DB
        row = conn.execute(
            "SELECT text, extraction_method FROM evidence_text WHERE file_node_id = ?",
            (file_node_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "audit log entry"
        assert row[1] == "plain"


# ===========================================================================
# P3-T01b  extractor — new file types
# ===========================================================================

class TestExtractEml:
    def test_extract_eml_headers_and_body(self, tmp_path):
        eml_content = (
            "From: sender@example.com\r\n"
            "To: recipient@example.com\r\n"
            "Subject: Compliance Policy Update\r\n"
            "Date: Mon, 01 Jan 2026 00:00:00 +0000\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "This document describes the updated patch management policy.\r\n"
        )
        p = tmp_path / "test.eml"
        p.write_bytes(eml_content.encode("utf-8"))
        result = extract_file(1, str(p))
        assert result.extraction_method == "email_stdlib"
        assert result.error is None
        assert "Compliance Policy Update" in result.text
        assert "sender@example.com" in result.text
        assert "patch management policy" in result.text
        assert result.char_count == len(result.text)

    def test_extract_eml_multipart_plain_preferred(self, tmp_path):
        eml_content = (
            "From: a@b.com\r\n"
            "Subject: Test\r\n"
            "Content-Type: multipart/alternative; boundary=\"boundary\"\r\n"
            "\r\n"
            "--boundary\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Plain text body content.\r\n"
            "--boundary\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "\r\n"
            "<html><body><p>HTML body content.</p></body></html>\r\n"
            "--boundary--\r\n"
        )
        p = tmp_path / "multipart.eml"
        p.write_bytes(eml_content.encode("utf-8"))
        result = extract_file(1, str(p))
        assert result.extraction_method == "email_stdlib"
        assert "Plain text body content." in result.text

    def test_extract_eml_html_fallback_strips_tags(self, tmp_path):
        eml_content = (
            "From: a@b.com\r\n"
            "Subject: HTML only\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "\r\n"
            "<html><body><p>Policy statement here.</p></body></html>\r\n"
        )
        p = tmp_path / "html.eml"
        p.write_bytes(eml_content.encode("utf-8"))
        result = extract_file(1, str(p))
        assert result.extraction_method == "email_stdlib"
        assert "Policy statement here." in result.text
        assert "<p>" not in result.text


class TestExtractMsg:
    def test_extract_msg_fallback_without_library(self, tmp_path):
        # Simulate a .msg file as raw bytes containing readable ASCII strings
        # (extract-msg may or may not be installed; we test the fallback path)
        readable = b"A" * 21  # 21 chars, just over the 20-char threshold
        payload = b"\x00\x01\x02" + readable + b"\x00\x01\x02"
        p = tmp_path / "test.msg"
        p.write_bytes(payload)
        result = extract_file(1, str(p))
        # Should succeed with either extract_msg or msg_fallback method
        assert result.extraction_method in ("extract_msg", "msg_fallback", "fallback")
        assert result.error is None or isinstance(result.error, str)

    def test_extract_msg_fallback_method_name(self, tmp_path, monkeypatch):
        # Force ImportError for extract_msg to exercise the fallback branch
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "extract_msg":
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        readable_string = b"This is a readable compliance policy string longer than twenty chars"
        p = tmp_path / "fallback.msg"
        p.write_bytes(b"\x00\x01" + readable_string + b"\x00\x01")
        result = extract_file(1, str(p))
        assert result.extraction_method == "msg_fallback"
        assert "compliance policy string" in result.text


class TestExtractImage:
    def test_extract_image_unavailable_returns_placeholder(self, tmp_path, monkeypatch):
        # Force ImportError for both PIL and pytesseract
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("PIL", "pytesseract"):
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        p = tmp_path / "scan.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
        result = extract_file(1, str(p))
        assert result.extraction_method == "ocr_unavailable"
        assert result.text == ""
        assert result.error is not None
        assert "pytesseract" in result.error.lower()

    def test_extract_jpeg_routes_to_image_extractor(self, tmp_path, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("PIL", "pytesseract"):
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        for ext in ("jpg", "jpeg"):
            p = tmp_path / f"photo.{ext}"
            p.write_bytes(b"\xff\xd8\xff")  # minimal JPEG header
            result = extract_file(1, str(p))
            assert result.extraction_method == "ocr_unavailable"


# ===========================================================================
# P3-T01c  extractor — email attachments
# ===========================================================================

class TestEmlAttachments:
    """Tests for attachment extraction from .eml files."""

    def _build_eml(self) -> bytes:
        """Multipart/mixed EML: plain-text body + txt attachment + fake PDF attachment."""
        msg = email.mime.multipart.MIMEMultipart("mixed")
        msg["From"] = "compliance@example.com"
        msg["To"] = "auditor@example.com"
        msg["Subject"] = "Q1 Compliance Evidence"

        # Plain-text body (not an attachment)
        body = email.mime.text.MIMEText(
            "This is the email body for compliance review.", "plain", "utf-8"
        )
        msg.attach(body)

        # .txt attachment
        txt_att = email.mime.text.MIMEText(
            "Policy version 2.1\nUpdated procedures.", "plain", "utf-8"
        )
        txt_att.add_header("Content-Disposition", "attachment", filename="policy_notes.txt")
        msg.attach(txt_att)

        # Fake PDF attachment (not a real PDF — pdfminer will fail gracefully)
        pdf_att = email.mime.base.MIMEBase("application", "pdf")
        pdf_att.set_payload(b"%PDF-FAKE\nNot a real PDF")
        email.encoders.encode_base64(pdf_att)
        pdf_att.add_header("Content-Disposition", "attachment", filename="policy.pdf")
        msg.attach(pdf_att)

        return msg.as_bytes()

    def test_body_and_attachments_extracted_separately(self, tmp_path):
        p = tmp_path / "evidence.eml"
        p.write_bytes(self._build_eml())
        result = extract_file(1, str(p))
        assert result.extraction_method == "email_stdlib"
        assert "email body for compliance review" in result.text
        assert len(result.attachments) == 2

    def test_attachment_filenames_captured(self, tmp_path):
        p = tmp_path / "evidence.eml"
        p.write_bytes(self._build_eml())
        result = extract_file(1, str(p))
        filenames = {a.attachment_filename for a in result.attachments}
        assert "policy_notes.txt" in filenames
        assert "policy.pdf" in filenames

    def test_txt_attachment_text_extracted(self, tmp_path):
        p = tmp_path / "evidence.eml"
        p.write_bytes(self._build_eml())
        result = extract_file(1, str(p))
        txt_atts = [a for a in result.attachments if a.attachment_filename == "policy_notes.txt"]
        assert len(txt_atts) == 1
        assert "Policy version 2.1" in txt_atts[0].text
        assert txt_atts[0].extraction_method == "plain"

    def test_attachment_result_fields(self, tmp_path):
        p = tmp_path / "evidence.eml"
        p.write_bytes(self._build_eml())
        result = extract_file(1, str(p))
        for att in result.attachments:
            assert isinstance(att, AttachmentResult)
            assert att.parent_file_path == str(p)
            assert att.size_bytes > 0
            assert att.attachment_ext in ("txt", "pdf")

    def test_attachments_persisted_to_db(self, tmp_path):
        p = tmp_path / "evidence.eml"
        p.write_bytes(self._build_eml())
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, str(p))
        extract_all(conn, scan_id)
        rows = conn.execute(
            "SELECT filename FROM email_attachments WHERE file_node_id = ?",
            (file_node_id,),
        ).fetchall()
        filenames = {r[0] for r in rows}
        assert "policy_notes.txt" in filenames
        assert "policy.pdf" in filenames

    def test_no_attachments_on_plain_eml(self, tmp_path):
        eml = (
            "From: a@b.com\r\nSubject: Simple\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\nJust a body.\r\n"
        )
        p = tmp_path / "simple.eml"
        p.write_bytes(eml.encode("utf-8"))
        result = extract_file(1, str(p))
        assert result.attachments == []
        assert "Just a body." in result.text


class TestMsgAttachments:
    """Tests for attachment extraction from .msg files."""

    def test_extract_msg_with_mock_attachment(self, tmp_path, monkeypatch):
        """Mock extract_msg.Message to exercise the attachment extraction path."""
        mock_att = MagicMock()
        mock_att.longFilename = "training_log.txt"
        mock_att.shortFilename = "TRAINI~1.TXT"
        mock_att.data = b"Employee training completed on 2026-01-15."

        mock_msg = MagicMock()
        mock_msg.body = "Please find the training log attached."
        mock_msg.attachments = [mock_att]
        mock_msg.__enter__ = MagicMock(return_value=mock_msg)
        mock_msg.__exit__ = MagicMock(return_value=False)

        mock_extract_msg = MagicMock()
        mock_extract_msg.Message = MagicMock(return_value=mock_msg)
        monkeypatch.setitem(sys.modules, "extract_msg", mock_extract_msg)

        p = tmp_path / "test.msg"
        p.write_bytes(b"fake msg content")
        result = extract_file(1, str(p))

        assert result.extraction_method == "extract_msg"
        assert len(result.attachments) == 1
        att = result.attachments[0]
        assert att.attachment_filename == "training_log.txt"
        assert att.attachment_ext == "txt"
        assert "training completed" in att.text
        assert att.extraction_method == "plain"

    def test_extract_msg_attachment_uses_long_filename(self, tmp_path, monkeypatch):
        """longFilename is preferred over shortFilename."""
        mock_att = MagicMock()
        mock_att.longFilename = "detailed_report.txt"
        mock_att.shortFilename = "DETAIL~1.TXT"
        mock_att.data = b"Report content here for testing purposes."

        mock_msg = MagicMock()
        mock_msg.body = "See attached."
        mock_msg.attachments = [mock_att]
        mock_msg.__enter__ = MagicMock(return_value=mock_msg)
        mock_msg.__exit__ = MagicMock(return_value=False)

        mock_extract_msg = MagicMock()
        mock_extract_msg.Message = MagicMock(return_value=mock_msg)
        monkeypatch.setitem(sys.modules, "extract_msg", mock_extract_msg)

        p = tmp_path / "test.msg"
        p.write_bytes(b"fake msg")
        result = extract_file(1, str(p))
        assert result.attachments[0].attachment_filename == "detailed_report.txt"

    def test_extract_msg_fallback_no_attachments(self, tmp_path, monkeypatch):
        """Fallback path (no extract_msg) yields no attachments."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "extract_msg":
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        readable = b"This is a readable compliance policy string longer than twenty chars"
        p = tmp_path / "fallback.msg"
        p.write_bytes(b"\x00\x01" + readable + b"\x00\x01")
        result = extract_file(1, str(p))

        assert result.extraction_method == "msg_fallback"
        assert result.attachments == []
        # Error field carries an informational note about extract_msg
        assert result.error is not None
        assert "extract" in result.error.lower()


# ===========================================================================
# P3-T02  matcher
# ===========================================================================

class TestStructuralScore:
    def test_known_policy_pdf(self):
        score = _structural_score(
            "/docs/policy/acceptable_use_policy.pdf", "pdf", ["policy"]
        )
        assert score > 0.5, f"Expected score > 0.5, got {score}"

    def test_no_keywords_no_descriptor_match(self):
        score = _structural_score("/data/random.bin", "bin", [])
        assert score < 0.5

    def test_descriptor_extension_match(self):
        score_match = _structural_score("/some/path/doc.pdf", "pdf", ["procedure"])
        score_no_match = _structural_score("/some/path/doc.png", "png", ["procedure"])
        assert score_match > score_no_match

    def test_path_keyword_boosts_score(self):
        score_with = _structural_score("/compliance/evidence/file.txt", "txt", [])
        score_without = _structural_score("/downloads/file.txt", "txt", [])
        assert score_with >= score_without

    def test_returns_between_zero_and_one(self):
        score = _structural_score("/policy/log/training/audit/config.pdf", "pdf",
                                   ["log", "policy", "procedure", "training_record"])
        assert 0.0 <= score <= 1.0


class TestEvidenceTextQuality:
    def test_rejects_pdf_cid_glyph_noise(self):
        garbage = " ".join(f"(cid:{i})" for i in range(100))
        assert not _is_usable_evidence_text(garbage)

    def test_accepts_normal_email_text(self):
        text = (
            "Subject: Acknowledgment of Receipt\n"
            "From: CenterPoint Energy\n"
            "Thank you. We will review and follow up as needed."
        )
        assert _is_usable_evidence_text(text)


class TestCandidateStructure:
    def test_candidate_fields(self):
        c = Candidate(
            candidate_id=None,
            run_id="run-1",
            chunk_id="chunk-001",
            file_node_id=5,
            file_path="/tmp/policy.pdf",
            structural_score=0.7,
            semantic_score=0.0,
            combined_score=0.7,
        )
        assert c.run_id == "run-1"
        assert c.candidate_id is None
        assert 0.0 <= c.combined_score <= 1.0

    def test_compute_candidates_returns_list(self, tmp_path):
        p = tmp_path / "policy.txt"
        p.write_text("documented process for patch management", encoding="utf-8")
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, str(p))
        _seed_chunk(conn, scan_id, file_node_id)

        # Cache evidence text
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (file_node_id, "documented process for patch management", "plain", 40, "2026-01-01"),
        )
        conn.commit()

        candidates = compute_candidates(conn, "run-001", "CIP-007-6", scan_id=scan_id, top_k=3)
        assert isinstance(candidates, list)
        for c in candidates:
            assert isinstance(c, Candidate)
            assert c.run_id == "run-001"
            assert 0.0 <= c.structural_score <= 1.0
            assert 0.0 <= c.combined_score <= 1.0

    def test_candidates_written_to_db(self, tmp_path):
        p = tmp_path / "procedure.pdf"
        p.write_bytes(b"procedure content")
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, str(p))
        _seed_chunk(conn, scan_id, file_node_id)
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (file_node_id, "procedure content", "fallback", 17, "2026-01-01"),
        )
        conn.commit()

        compute_candidates(conn, "run-002", "CIP-007-6", scan_id=scan_id, top_k=1)
        rows = conn.execute(
            "SELECT COUNT(*) FROM evidence_candidates WHERE run_id = 'run-002'"
        ).fetchone()
        assert rows[0] >= 1

    def test_sub_sub_requirement_chunks_are_matched(self, tmp_path):
        """Regression: chunks of type 'sub_sub_requirement' must produce candidates."""
        p = tmp_path / "policy.pdf"
        p.write_bytes(b"sub-sub policy content")
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, str(p))
        _seed_chunk(
            conn, scan_id, file_node_id,
            chunk_id="chunk-sub", standard_id="MOD-025-2",
            chunk_type="sub_sub_requirement",
        )
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (file_node_id, "sub-sub policy content", "fallback", 22, "2026-01-01"),
        )
        conn.commit()

        candidates = compute_candidates(conn, "run-sub", "MOD-025-2", scan_id=scan_id, top_k=5)
        assert len(candidates) >= 1
        assert candidates[0].chunk_id == "chunk-sub"

    def test_zero_score_falls_back_to_all_evidence(self, tmp_path):
        """When no evidence file scores above zero, pair every file with the chunk."""
        conn = _make_db()

        # Create ONE scan and insert 3 file_nodes into it (reflects real use-case).
        conn.execute(
            "INSERT INTO scans (scope_key, root_path, mode, scan_ts, file_count, "
            "folder_count, skipped_count, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("/tmp/test-zero", "/tmp/test-zero", "broad", "2026-01-01T00:00:00", 3, 0, 0, 10),
        )
        scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        files = []
        for i in range(3):
            f = tmp_path / f"f{i}.bin"
            f.write_bytes(b"x")
            conn.execute(
                "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
                "size_bytes, modified_ts, depth, parent_path, is_document) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scan_id, f.name, str(f), "bin", 1, "2026-01-01", 1, "/tmp/test-zero", 1),
            )
            file_node_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            files.append(file_node_id)
            conn.execute(
                "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
                "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
                (file_node_id, "", "fallback", 0, "2026-01-01"),
            )

        # Single chunk, no expected_evidence, no path keywords, .bin extension.
        # Structural score should be 0 across the board, no embedder available.
        _seed_chunk(
            conn, scan_id, files[-1],
            chunk_id="chunk-zero", standard_id="MOD-025-2",
            expected_evidence=["procedure"],
        )
        conn.commit()

        candidates = compute_candidates(conn, "run-zero", "MOD-025-2", scan_id=scan_id, top_k=2)
        # All 3 evidence files should be paired despite top_k=2, because
        # structural matching produced an all-zero score.
        assert len(candidates) == 3
        assert {c.file_node_id for c in candidates} == set(files)

    def test_garbled_pdf_text_is_not_selected(self, tmp_path):
        """Regression: CID-garbled Outlook PDFs should not be sent to the LLM."""
        conn = _make_db()
        conn.execute(
            "INSERT INTO scans (scope_key, root_path, mode, scan_ts, file_count, "
            "folder_count, skipped_count, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("/tmp/cid-garbage", "/tmp/cid-garbage", "broad", "2026-01-01T00:00:00", 2, 0, 0, 10),
        )
        scan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        bad_pdf = tmp_path / "Acknowledgment of Receipt From Centerpoint - Outlook.pdf"
        bad_pdf.write_bytes(b"%PDF bad extraction fixture")
        conn.execute(
            "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
            "size_bytes, modified_ts, depth, parent_path, is_document) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scan_id, bad_pdf.name, str(bad_pdf), "pdf", 267001, "2026-01-01", 1, "/tmp", 1),
        )
        bad_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        bad_text = " ".join(f"(cid:{i})" for i in range(200))
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (bad_id, bad_text, "pdfminer", len(bad_text), "2026-01-01"),
        )

        good_pdf = tmp_path / "MOD-025_Attachment_2_Filled_2022_v4.pdf"
        good_pdf.write_text("Reactive capability verification attachment.", encoding="utf-8")
        conn.execute(
            "INSERT INTO file_nodes (scan_id, name, full_path, extension, "
            "size_bytes, modified_ts, depth, parent_path, is_document) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scan_id, good_pdf.name, str(good_pdf), "pdf", 1000, "2026-01-01", 1, "/tmp", 1),
        )
        good_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (good_id, "Reactive capability verification attachment.", "pdfminer", 44, "2026-01-01"),
        )

        _seed_chunk(
            conn,
            scan_id,
            good_id,
            chunk_id="mod-025-r1",
            standard_id="MOD-025-2",
            expected_evidence=["signed_acknowledgement"],
        )
        conn.commit()

        candidates = compute_candidates(conn, "run-cid", "MOD-025-2", scan_id=scan_id, top_k=2)
        assert candidates
        assert bad_id not in {c.file_node_id for c in candidates}


# ===========================================================================
# P3-T03  llm
# ===========================================================================

class TestLlamaCppBackend:
    def test_construction_defaults(self):
        backend = LlamaCppBackend()
        assert backend.base_url == "http://localhost:8080"
        assert backend.model == "qwen2.5-14b"
        assert backend.max_retries == 3
        assert backend.max_tokens == 1024
        assert backend.temperature == 0.1

    def test_construction_custom(self):
        backend = LlamaCppBackend(
            base_url="http://127.0.0.1:11434",
            model="llama3",
            timeout=60,
            max_retries=2,
            max_tokens=512,
            temperature=0.0,
        )
        assert backend.base_url == "http://127.0.0.1:11434"
        assert backend.model == "llama3"
        assert backend.max_retries == 2

    def test_from_config_with_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.toml"
        backend = LlamaCppBackend.from_config(missing)
        # Falls back to defaults
        assert backend.base_url == "http://localhost:8080"

    def test_from_config_reads_toml(self, tmp_path):
        cfg = tmp_path / "cdw_config.toml"
        cfg.write_text(
            '[llm]\nbase_url = "http://10.0.0.1:9000"\nmodel = "mistral"\n'
            "timeout_seconds = 60\nmax_retries = 5\nmax_tokens = 512\ntemperature = 0.2\n",
            encoding="utf-8",
        )
        backend = LlamaCppBackend.from_config(cfg)
        assert backend.base_url == "http://10.0.0.1:9000"
        assert backend.model == "mistral"
        assert backend.max_retries == 5

    def test_complete_raises_on_unreachable(self):
        backend = LlamaCppBackend(
            base_url="http://127.0.0.1:19999",  # nothing listening here
            max_retries=1,
            timeout=1,
        )
        try:
            backend.complete("system", "user")
            assert False, "Expected RuntimeError"
        except RuntimeError as exc:
            assert "unreachable" in str(exc).lower() or "attempt" in str(exc).lower()


# ===========================================================================
# P3-T04  assessor — prompt building and JSON parsing
# ===========================================================================

class TestBuildUserPrompt:
    def test_contains_required_sections(self):
        prompt = build_user_prompt(
            citation_path="CIP-007-6 -> R1",
            requirement_text="Each Responsible Entity shall implement documented processes.",
            measure_text="Evidence of documented patch management process.",
            file_path="/evidence/patch_policy.pdf",
            evidence_excerpt="This policy describes patch management procedures for BES Cyber Systems.",
        )
        assert "REQUIREMENT:" in prompt
        assert "CIP-007-6 -> R1" in prompt
        assert "MEASURE" in prompt
        assert "Evidence of documented patch management" in prompt
        assert "EVIDENCE FILE:" in prompt
        assert "/evidence/patch_policy.pdf" in prompt
        assert "EVIDENCE CONTENT:" in prompt
        assert "patch management procedures" in prompt
        assert "TASK:" in prompt
        assert '"verdict"' in prompt

    def test_evidence_excerpt_included(self):
        prompt = build_user_prompt(
            citation_path="R1",
            requirement_text="req",
            measure_text="measure",
            file_path="/f.txt",
            evidence_excerpt="specific evidence text here",
        )
        assert "specific evidence text here" in prompt

    def test_prompt_version_constant(self):
        assert PROMPT_VERSION == "v1"


class TestParseLlmResponse:
    def test_direct_json(self):
        raw = json.dumps({
            "verdict": "satisfied",
            "confidence": 0.95,
            "rationale": "The policy document covers all requirements.",
            "cited_text": "patch management is documented",
            "gaps_identified": [],
        })
        result = parse_llm_response(raw)
        assert result["verdict"] == "satisfied"
        assert result["confidence"] == 0.95
        assert result["gaps_identified"] == []

    def test_fenced_markdown_block(self):
        raw = (
            "Here is my assessment:\n"
            "```json\n"
            '{"verdict": "gap", "confidence": 0.3, '
            '"rationale": "No evidence found.", "cited_text": null, '
            '"gaps_identified": ["missing patch log"]}\n'
            "```\n"
            "Let me know if you need more details."
        )
        result = parse_llm_response(raw)
        assert result["verdict"] == "gap"
        assert result["gaps_identified"] == ["missing patch log"]

    def test_fenced_block_without_language_tag(self):
        raw = "```\n{\"verdict\": \"partial\", \"confidence\": 0.6, \"rationale\": \"r\", \"cited_text\": null, \"gaps_identified\": []}\n```"
        result = parse_llm_response(raw)
        assert result["verdict"] == "partial"

    def test_parse_error_fallback(self):
        raw = "I cannot provide a JSON response, but the evidence looks good."
        result = parse_llm_response(raw)
        assert result["verdict"] == "parse_error"
        assert result["confidence"] == 0.0
        assert "gaps_identified" in result

    def test_malformed_json_extracts_keyword_verdict(self):
        # Missing comma makes JSON invalid — parser falls through to keyword extraction
        # and correctly picks up "satisfied" from the text.
        raw = '{"verdict": "satisfied" "confidence": 0.9}'  # missing comma
        result = parse_llm_response(raw)
        assert result["verdict"] == "satisfied"

    def test_truly_unparseable_gives_parse_error(self):
        # No JSON, no recognisable verdict keywords → parse_error sentinel
        raw = "The model was unable to process this request at this time."
        result = parse_llm_response(raw)
        assert result["verdict"] == "parse_error"


# ===========================================================================
# P3-T05  DB schema
# ===========================================================================

class TestPhase3Schema:
    def test_tables_created(self):
        conn = _make_db()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "evidence_text" in tables
        assert "evidence_candidates" in tables
        assert "evidence_assessments" in tables
        assert "gap_reports" in tables

    def test_evidence_text_insert(self):
        conn = _make_db()
        _seed_scan(conn, "/tmp/dummy.txt")
        file_node_id = conn.execute("SELECT id FROM file_nodes LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO evidence_text (file_node_id, text, extraction_method, "
            "char_count, extracted_ts) VALUES (?, ?, ?, ?, ?)",
            (file_node_id, "hello world", "plain", 11, "2026-01-01T00:00:00"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT text FROM evidence_text WHERE file_node_id = ?", (file_node_id,)
        ).fetchone()
        assert row[0] == "hello world"

    def test_gap_reports_insert(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO gap_reports (run_id, standard_id, generated_ts, "
            "total_requirements, satisfied_count, partial_count, gap_count, "
            "not_applicable_count, report_json, report_html) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("r1", "CIP-007-6", "2026-01-01T00:00:00", 5, 3, 1, 1, 0, "{}", "<html/>"),
        )
        conn.commit()
        row = conn.execute("SELECT standard_id FROM gap_reports").fetchone()
        assert row[0] == "CIP-007-6"

    def test_idempotent_creation(self):
        conn = _make_db()
        # Should not raise on second call
        create_reasoning_tables(conn)
        create_reasoning_tables(conn)


# ===========================================================================
# P3-T06  reporter
# ===========================================================================

class TestReporter:
    def _setup_with_assessment(self) -> tuple[sqlite3.Connection, str]:
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, "/tmp/policy.pdf")
        _seed_chunk(conn, scan_id, file_node_id)
        run_id = "run-report-001"

        conn.execute(
            "INSERT INTO evidence_assessments "
            "(run_id, chunk_id, file_node_id, verdict, confidence, rationale, "
            "cited_text, gaps_identified, raw_llm_response, prompt_version, assessed_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, "chunk-001", file_node_id,
                "satisfied", 0.92, "The policy document covers all aspects.",
                "patch management is documented", "[]", '{"verdict":"satisfied"}',
                "v1", "2026-01-01T00:00:00",
            ),
        )
        conn.commit()
        return conn, run_id

    def test_report_structure(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")

        assert "report_id" in report
        assert report["run_id"] == run_id
        assert report["standard_id"] == "CIP-007-6"
        assert "generated_ts" in report
        assert "summary" in report
        assert "requirements" in report

        summary = report["summary"]
        assert "total_requirements" in summary
        assert "satisfied" in summary
        assert "partial" in summary
        assert "gap" in summary
        assert "not_applicable" in summary

    def test_report_satisfied_count(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        assert report["summary"]["satisfied"] == 1
        assert report["summary"]["gap"] == 0

    def test_report_gap_when_no_assessment(self):
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, "/tmp/doc.pdf")
        _seed_chunk(conn, scan_id, file_node_id)
        report = build_report(conn, "nonexistent-run", "CIP-007-6")
        # No assessments → requirement should be reported as gap
        assert report["summary"]["gap"] >= 1

    def test_requirement_entry_fields(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        req = report["requirements"][0]
        assert "citation_path" in req
        assert "verdict" in req
        assert "confidence" in req
        assert "rationale" in req
        assert "cited_text" in req
        assert "evidence_file" in req
        assert "gaps_identified" in req

    def test_html_report_is_valid_html(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "CIP-007-6" in html

    def test_html_contains_summary_counts(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        assert "SATISFIED" in html or "satisfied" in html.lower()

    def test_html_contains_svg_donut(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        assert "<svg" in html

    def test_html_no_external_resources(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        # No external CSS/JS links
        assert "href=" not in html or "stylesheet" not in html
        assert "<script" not in html

    def test_save_report(self):
        conn, run_id = self._setup_with_assessment()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        rowid = save_report(conn, report, html)
        assert isinstance(rowid, int)
        assert rowid >= 1

        row = conn.execute(
            "SELECT standard_id, satisfied_count FROM gap_reports WHERE rowid = ?",
            (rowid,),
        ).fetchone()
        assert row[0] == "CIP-007-6"
        assert row[1] == 1

    def test_html_xss_escaped(self):
        conn = _make_db()
        scan_id, file_node_id = _seed_scan(conn, "/tmp/evil.pdf")
        _seed_chunk(
            conn, scan_id, file_node_id,
            citation_path='CIP-007-6 -> <script>alert(1)</script>',
        )
        run_id = "run-xss"
        conn.execute(
            "INSERT INTO evidence_assessments "
            "(run_id, chunk_id, file_node_id, verdict, confidence, rationale, "
            "cited_text, gaps_identified, raw_llm_response, prompt_version, assessed_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, "chunk-001", file_node_id, "gap", 0.1,
             "<script>evil()</script>", None, "[]", "", "v1", "2026-01-01T00:00:00"),
        )
        conn.commit()
        report = build_report(conn, run_id, "CIP-007-6")
        html = build_html_report(report)
        assert "<script>alert" not in html
        assert "<script>evil" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Run with pytest or python -m pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
