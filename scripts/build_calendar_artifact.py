#!/usr/bin/env python3
"""Build the static month/agenda calendar prototype page from a snapshot.

Usage:
    events export-snapshot --out data/snapshot.json
    python3 scripts/build_calendar_artifact.py --snapshot data/snapshot.json --out calendar.html

The output is a single self-contained HTML file (data inlined, no external
requests) — open it directly in a browser, or re-run this after every
`events export-snapshot` to refresh the view. This is the Phase 1 prototype
UI; the planned Phase 2 replaces it with a live Flask app so events don't
need to be re-exported/rebuilt by hand.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = PROJECT_ROOT / "templates" / "calendar_prototype.html"
PLACEHOLDER = "/*__SNAPSHOT_JSON__*/"


def build(snapshot_path: Path, template_path: Path, out_path: Path) -> None:
    snapshot_json = snapshot_path.read_text(encoding="utf-8").strip()
    template = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise ValueError(f"template is missing the {PLACEHOLDER} placeholder")
    output = template.replace(PLACEHOLDER, snapshot_json)
    out_path.write_text(output, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Path to a JSON file from `events export-snapshot`.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    build(Path(args.snapshot), Path(args.template), Path(args.out))
    print(f"Built calendar prototype at {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
