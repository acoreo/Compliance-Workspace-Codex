"""List CDW scan IDs for the next workflow step."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List CDW scans in workspace.db.")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to workspace.db. Defaults to compliance_workspace/data/workspace.db.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include system scans such as nerc_standards.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    db_path = Path(args.db) if args.db else root / "data" / "workspace.db"

    if not db_path.exists():
        print(f"No workspace database found at: {db_path}")
        print("Launch CDW and scan an evidence folder first.")
        return 1

    where = "" if args.all else "WHERE scope_key != 'nerc_standards'"
    sql = f"""
        SELECT scan_id, scope_key, mode, scan_ts, file_count, folder_count, skipped_count, root_path
          FROM scans
          {where}
         ORDER BY scan_id DESC
         LIMIT 20
    """

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No evidence scans found.")
        print("Launch CDW and scan an evidence folder first.")
        return 1

    print("| scan_id | scope_key | mode | files | folders | skipped | scan_ts | root_path |")
    print("|---:|---|---|---:|---:|---:|---|---|")
    for scan_id, scope_key, mode, scan_ts, files, folders, skipped, root_path in rows:
        print(
            f"| {scan_id} | {scope_key} | {mode} | {files} | {folders} | "
            f"{skipped} | {scan_ts} | {root_path} |"
        )

    print(f"\nLatest evidence scan_id: {rows[0][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
