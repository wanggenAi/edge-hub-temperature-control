from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "tools/visual_schematic_lint.py"
FIXTURES = ROOT / "tests/fixtures"
LOCK = FIXTURES / "visual_reserved_regions.lock.json"
CONFIG = ROOT / "hardware/eda/style_rules_from_drawio.yaml"


def run_lint(path: Path, tmp_path: Path):
    reports = tmp_path / "reports"
    proc = subprocess.run(
        [
            "python3",
            str(LINT),
            str(path),
            "--lock-file",
            str(LOCK),
            "--config",
            str(CONFIG),
            "--reports-dir",
            str(reports),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    payload_path = reports / "visual_schematic_lint.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {}
    return proc, payload


def codes(payload: dict) -> set[str]:
    return {finding["code"] for finding in payload.get("findings", []) if finding["severity"] == "error"}


def assert_fails(path_name: str, tmp_path: Path, *expected_codes: str):
    proc, payload = run_lint(FIXTURES / path_name, tmp_path)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    actual = codes(payload)
    for expected in expected_codes:
        assert expected in actual, f"{expected} missing from {sorted(actual)}"


def test_good_visual_fixture_passes(tmp_path):
    proc, payload = run_lint(FIXTURES / "good_visual_schematic.drawio", tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["error_count"] == 0


def test_bad_locked_region_changed_fails(tmp_path):
    assert_fails("bad_locked_region_changed.drawio", tmp_path, "FRAME_CHANGED")


def test_bad_unclassified_object_fails(tmp_path):
    assert_fails("bad_unclassified_object.drawio", tmp_path, "UNCLASSIFIED_OBJECT")


def test_bad_wire_endpoint_gap_fails(tmp_path):
    assert_fails("bad_wire_endpoint_gap.drawio", tmp_path, "WIRE_ENDPOINT_NOT_CONNECTED")


def test_bad_floating_wire_fails(tmp_path):
    assert_fails("bad_floating_wire.drawio", tmp_path, "FLOATING_WIRE_END")


def test_bad_diagonal_wire_fails(tmp_path):
    assert_fails("bad_diagonal_wire.drawio", tmp_path, "DIAGONAL_WIRE")


def test_bad_pin_label_misaligned_fails(tmp_path):
    assert_fails("bad_pin_label_misaligned.drawio", tmp_path, "PIN_LABEL_MISALIGNED")


def test_bad_text_overlaps_wire_fails(tmp_path):
    assert_fails("bad_text_overlaps_wire.drawio", tmp_path, "TEXT_OVERLAPS_WIRE")


def test_bad_schematic_overlaps_reserved_region_fails(tmp_path):
    assert_fails(
        "bad_schematic_overlaps_reserved_region.drawio",
        tmp_path,
        "SCHEMATIC_OVERLAPS_ELEMENT_LIST",
    )
