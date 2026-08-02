import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_calendar_artifact import PLACEHOLDER, build  # noqa: E402

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "calendar_prototype.html"


def test_template_has_placeholder():
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert PLACEHOLDER in text


def test_build_substitutes_snapshot_json(tmp_path):
    snapshot = {"generated_at": "2026-08-02T00:00:00", "location": {"city": "Austin", "state": "TX"}, "events": [], "categories": [], "sources": []}
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    out_path = tmp_path / "out.html"

    build(snapshot_path, TEMPLATE_PATH, out_path)

    output = out_path.read_text(encoding="utf-8")
    assert PLACEHOLDER not in output
    assert '"city": "Austin"' in output


def test_build_rejects_template_missing_placeholder(tmp_path):
    bad_template = tmp_path / "bad.html"
    bad_template.write_text("<html>no placeholder here</html>", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")

    try:
        build(snapshot_path, bad_template, tmp_path / "out.html")
        assert False, "expected ValueError"
    except ValueError:
        pass
