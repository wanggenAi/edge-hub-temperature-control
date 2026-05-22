from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "tools/visual_schematic_lint.py"
FIXTURES = ROOT / "tests/fixtures"
LOCK = FIXTURES / "visual_reserved_regions.lock.json"
CONFIG = ROOT / "hardware/eda/style_rules_from_drawio.yaml"
REAL_LOCK = ROOT / "hardware/eda/reserved_regions.lock.json"
REAL_SOURCE = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
REAL_GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
RENDERER = ROOT / "hardware/eda/render_esp32_drawio.js"


def run_lint(path: Path, tmp_path: Path, *, lock: Path = LOCK, mode: str = "strict"):
    reports = tmp_path / "reports"
    proc = subprocess.run(
        [
            "python3",
            str(LINT),
            str(path),
            "--lock-file",
            str(lock),
            "--config",
            str(CONFIG),
            "--reports-dir",
            str(reports),
            "--mode",
            mode,
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


def test_real_template_mode_passes_locked_region_check(tmp_path):
    proc, payload = run_lint(REAL_SOURCE, tmp_path, lock=REAL_LOCK, mode="template")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["error_count"] == 0


def test_no_circuit_generated_copy_passes_strict_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--no-circuit",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["finalCircuitRendered"] is False
    assert output.exists()

    source_text = REAL_SOURCE.read_text(encoding="utf-8")
    generated_text = output.read_text(encoding="utf-8")
    assert 'data-role="reserved_container"' in generated_text
    assert 'id="OTuqVLYWGNuakiADof2M-2"' in source_text
    assert 'id="OTuqVLYWGNuakiADof2M-2"' not in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_dd1_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--dd1-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["finalCircuitRendered"] is False
    assert output.exists()

    generated_text = output.read_text(encoding="utf-8")
    assert 'id="generated.schematic.root"' in generated_text
    assert 'data-role="schematic_root"' in generated_text
    assert 'id="component.DD1.body"' in generated_text
    assert generated_text.count('data-role="pin"') == 10
    assert generated_text.count('data-role="pin_label"') == 10
    assert generated_text.count('data-role="wire"') == 10
    assert generated_text.count('data-role="net_label"') == 10
    for forbidden_ref in ("R1", "C1", "XS1", "VT1", "HL1", "SB1", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_pin_label_binding_uses_pin_number_for_duplicate_pin_names(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--dd1-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert "PIN_LABEL_MISALIGNED" not in codes(payload)
    generated_text = output.read_text(encoding="utf-8")
    assert 'data-pin="GND" data-pin-number="1"' in generated_text
    assert 'data-pin="GND" data-pin-number="38"' in generated_text


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
