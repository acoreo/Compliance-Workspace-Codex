"""Gap report generation — JSON structure + self-contained HTML (P3-T06).

The HTML report is fully self-contained (inline CSS, no external resources,
no JavaScript).  It includes a summary section with an SVG donut chart and a
per-requirement detail table.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

_ASSESSED_CHUNK_TYPES = (
    "requirement",
    "sub_requirement",
    "sub_sub_requirement",
    "measure",
    "attachment_obligation",
    "attachment_measure",
)

def _collect_requirement_results(
    conn: sqlite3.Connection,
    run_id: str,
    standard_id: str,
) -> list[dict]:
    """Fetch the best assessment per obligation chunk for this run.

    Includes requirement, sub_requirement, measure, and attachment chunks —
    not just top-level requirements.
    """
    placeholders = ",".join("?" * len(_ASSESSED_CHUNK_TYPES))
    req_chunks = conn.execute(
        f"""SELECT chunk_id, official_citation_path
           FROM chunks
           WHERE standard_id LIKE ?
             AND chunk_type IN ({placeholders})
           ORDER BY official_citation_path
        """,
        (f"{standard_id}%", *_ASSESSED_CHUNK_TYPES),
    ).fetchall()

    results: list[dict] = []
    for chunk_id, citation_path in req_chunks:
        row = conn.execute(
            """SELECT ea.verdict, ea.confidence, ea.rationale,
                      ea.cited_text, ea.gaps_identified, fn.full_path
               FROM evidence_assessments ea
               JOIN file_nodes fn ON fn.id = ea.file_node_id
               WHERE ea.run_id = ? AND ea.chunk_id = ?
               ORDER BY ea.confidence DESC
               LIMIT 1
            """,
            (run_id, chunk_id),
        ).fetchone()

        if row:
            verdict, confidence, rationale, cited_text, gaps_json, file_path = row
            try:
                gaps: list[str] = json.loads(gaps_json or "[]")
            except Exception:
                gaps = []
        else:
            verdict = "gap"
            confidence = 0.0
            rationale = "No evidence was assessed for this requirement."
            cited_text = None
            gaps = ["No evidence found or assessed."]
            file_path = None

        results.append(
            {
                "citation_path": citation_path,
                "verdict": verdict,
                "confidence": round(float(confidence), 4),
                "rationale": rationale,
                "cited_text": cited_text,
                "evidence_file": file_path,
                "gaps_identified": gaps,
            }
        )

    return results


def build_report(
    conn: sqlite3.Connection,
    run_id: str,
    standard_id: str,
    report_id: Optional[str] = None,
) -> dict:
    """Build and return the full gap report as a plain Python dict."""
    if report_id is None:
        report_id = str(uuid.uuid4())

    ts = datetime.now(timezone.utc).isoformat()
    requirements = _collect_requirement_results(conn, run_id, standard_id)

    counts: dict[str, int] = {
        "satisfied": 0,
        "partial": 0,
        "gap": 0,
        "not_applicable": 0,
    }
    for r in requirements:
        v = r["verdict"]
        if v in counts:
            counts[v] += 1
        elif v == "parse_error":
            counts["gap"] += 1  # treat parse errors as gaps for summary

    return {
        "report_id": report_id,
        "run_id": run_id,
        "standard_id": standard_id,
        "generated_ts": ts,
        "summary": {
            "total_requirements": len(requirements),
            "satisfied": counts["satisfied"],
            "partial": counts["partial"],
            "gap": counts["gap"],
            "not_applicable": counts["not_applicable"],
        },
        "requirements": requirements,
    }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_VERDICT_BG: dict[str, str] = {
    "satisfied":     "#22c55e",
    "partial":       "#f59e0b",
    "gap":           "#ef4444",
    "not_applicable": "#6b7280",
    "parse_error":   "#a855f7",
}

_VERDICT_LABEL: dict[str, str] = {
    "satisfied":     "SATISFIED",
    "partial":       "PARTIAL",
    "gap":           "GAP",
    "not_applicable": "N/A",
    "parse_error":   "PARSE ERR",
}


def _html_escape(s: Optional[str]) -> str:
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _svg_donut(satisfied: int, partial: int, gap: int, na: int) -> str:
    """Return an inline SVG donut chart (no JS required)."""
    total = satisfied + partial + gap + na
    if total == 0:
        return (
            '<svg width="120" height="120" viewBox="0 0 120 120">'
            '<circle cx="60" cy="60" r="40" fill="none" stroke="#e5e7eb" stroke-width="20"/>'
            "</svg>"
        )

    def _arc_path(start_pct: float, end_pct: float, color: str) -> str:
        if end_pct <= start_pct:
            return ""
        r, ir, cx, cy = 50, 30, 60, 60
        start_a = 2 * math.pi * start_pct - math.pi / 2
        end_a   = 2 * math.pi * end_pct   - math.pi / 2
        x1o = cx + r  * math.cos(start_a)
        y1o = cy + r  * math.sin(start_a)
        x2o = cx + r  * math.cos(end_a)
        y2o = cy + r  * math.sin(end_a)
        x1i = cx + ir * math.cos(end_a)
        y1i = cy + ir * math.sin(end_a)
        x2i = cx + ir * math.cos(start_a)
        y2i = cy + ir * math.sin(start_a)
        large = 1 if (end_pct - start_pct) > 0.5 else 0
        return (
            f'<path d="M {x1o:.2f},{y1o:.2f} '
            f'A {r},{r} 0 {large},1 {x2o:.2f},{y2o:.2f} '
            f'L {x1i:.2f},{y1i:.2f} '
            f'A {ir},{ir} 0 {large},0 {x2i:.2f},{y2i:.2f} Z" '
            f'fill="{color}"/>'
        )

    slices = [
        (satisfied, "#22c55e"),
        (partial,   "#f59e0b"),
        (gap,       "#ef4444"),
        (na,        "#6b7280"),
    ]
    parts: list[str] = []
    offset = 0.0
    for count, color in slices:
        pct = count / total
        if pct > 0:
            parts.append(_arc_path(offset, offset + pct, color))
            offset += pct

    return (
        '<svg width="120" height="120" viewBox="0 0 120 120">'
        + "".join(parts)
        + "</svg>"
    )


_CSS = """
body{font-family:system-ui,sans-serif;margin:0;padding:24px;background:#f9fafb;color:#111827}
h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:24px 0 8px;color:#374151}
.meta{color:#6b7280;font-size:.85em;margin-bottom:24px}
.card{background:#fff;border-radius:8px;padding:16px 24px;display:inline-flex;
      gap:32px;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,.1);margin-bottom:24px}
.stat{text-align:center}
.stat .num{font-size:2rem;font-weight:700;line-height:1.1}
.stat .lbl{font-size:.75em;color:#6b7280;text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;background:#fff;
      box-shadow:0 1px 3px rgba(0,0,0,.1);border-radius:8px;overflow:hidden}
th{background:#f3f4f6;padding:10px 8px;border:1px solid #e5e7eb;
   text-align:left;font-size:.85em;color:#374151}
td{vertical-align:top}
tr:hover td{background:#f9fafb}
.badge{padding:2px 8px;border-radius:4px;font-size:.8em;font-weight:700;color:#fff}
blockquote{border-left:3px solid #d1d5db;margin:4px 0 0;padding:2px 8px;
           color:#374151;font-size:.85em}
ul.gaps{margin:4px 0 0 16px;padding:0;font-size:.85em;color:#dc2626}
"""


def build_html_report(report: dict) -> str:
    """Return a self-contained HTML string for the gap report."""
    summary = report["summary"]
    requirements = report["requirements"]

    donut = _svg_donut(
        summary["satisfied"],
        summary["partial"],
        summary["gap"],
        summary["not_applicable"],
    )

    rows: list[str] = []
    for r in requirements:
        verdict = r.get("verdict", "gap")
        bg = _VERDICT_BG.get(verdict, "#6b7280")
        label = _VERDICT_LABEL.get(verdict, verdict.upper())
        conf_pct = f"{r['confidence'] * 100:.0f}%"

        cited_html = ""
        if r.get("cited_text"):
            cited_html = (
                f'<blockquote>{_html_escape(r["cited_text"])}</blockquote>'
            )

        gaps_html = ""
        if r.get("gaps_identified"):
            items = "".join(
                f"<li>{_html_escape(g)}</li>" for g in r["gaps_identified"]
            )
            gaps_html = f'<ul class="gaps">{items}</ul>'

        ev_file = _html_escape(r.get("evidence_file")) or "—"

        rows.append(
            f"""<tr>
<td style="padding:8px;border:1px solid #e5e7eb;font-weight:600">{_html_escape(r["citation_path"])}</td>
<td style="padding:8px;border:1px solid #e5e7eb;text-align:center">
  <span class="badge" style="background:{bg}">{label}</span>
</td>
<td style="padding:8px;border:1px solid #e5e7eb;text-align:center">{conf_pct}</td>
<td style="padding:8px;border:1px solid #e5e7eb">
  <div>{_html_escape(r["rationale"])}</div>
  {cited_html}{gaps_html}
</td>
<td style="padding:8px;border:1px solid #e5e7eb;font-size:.8em;color:#6b7280">{ev_file}</td>
</tr>"""
        )

    rows_html = "\n".join(rows)
    total = summary["total_requirements"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compliance Gap Report — {_html_escape(report["standard_id"])}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Compliance Gap Report: {_html_escape(report["standard_id"])}</h1>
<p class="meta">
  Report ID: {_html_escape(report["report_id"])} &nbsp;|&nbsp;
  Run ID: {_html_escape(report["run_id"])} &nbsp;|&nbsp;
  Generated: {_html_escape(report["generated_ts"])}
</p>

<div class="card">
  {donut}
  <div class="stat"><div class="num">{total}</div><div class="lbl">Total</div></div>
  <div class="stat"><div class="num" style="color:#22c55e">{summary["satisfied"]}</div><div class="lbl">Satisfied</div></div>
  <div class="stat"><div class="num" style="color:#f59e0b">{summary["partial"]}</div><div class="lbl">Partial</div></div>
  <div class="stat"><div class="num" style="color:#ef4444">{summary["gap"]}</div><div class="lbl">Gap</div></div>
  <div class="stat"><div class="num" style="color:#6b7280">{summary["not_applicable"]}</div><div class="lbl">N/A</div></div>
</div>

<h2>Requirements Detail</h2>
<table>
<thead>
<tr>
  <th style="width:20%">Requirement</th>
  <th style="width:10%">Verdict</th>
  <th style="width:8%">Confidence</th>
  <th>Rationale / Gaps</th>
  <th style="width:20%">Evidence File</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_report(
    conn: sqlite3.Connection,
    report: dict,
    html: str,
) -> int:
    """Insert the report into gap_reports; return the new rowid."""
    summary = report["summary"]
    cursor = conn.execute(
        """INSERT INTO gap_reports
               (run_id, standard_id, generated_ts, total_requirements,
                satisfied_count, partial_count, gap_count, not_applicable_count,
                report_json, report_html)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report["run_id"],
            report["standard_id"],
            report["generated_ts"],
            summary["total_requirements"],
            summary["satisfied"],
            summary["partial"],
            summary["gap"],
            summary["not_applicable"],
            json.dumps(report),
            html,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]
