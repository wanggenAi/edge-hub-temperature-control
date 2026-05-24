from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "hardware/eda/tools/audit_final_schematic_layout.py"
JSON_REPORT = ROOT / "build/reports/final_schematic_layout_audit.json"
MD_REPORT = ROOT / "docs/final_schematic_layout_audit_report.md"
CROPS_DIR = ROOT / "hardware/eda/exports/final/layout_audit_crops"


def run_audit() -> dict:
    proc = subprocess.run([sys.executable, str(AUDIT)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert JSON_REPORT.exists()
    assert MD_REPORT.exists()
    return json.loads(JSON_REPORT.read_text(encoding="utf-8"))


def test_final_schematic_layout_audit_generates_warn_or_pass_report() -> None:
    payload = run_audit()
    assert payload["status"] in {"PASS", "WARN"}
    assert payload["blocker_count"] == 0
    assert payload["per_rule_results"]["electrical_baseline"]["status"] == "PASS"
    assert payload["per_rule_results"]["topology_equivalence"]["status"] == "PASS"
    assert payload["per_rule_results"]["master_table_lock"]["status"] == "PASS"
    assert payload["per_rule_results"]["export_lint"]["error_count"] == 0
    assert payload["per_rule_results"]["kicad_geometry"]["diagonal_wire_count"] == 0
    assert payload["per_rule_results"]["kicad_geometry"]["dangling_endpoint_count"] == 0
    assert payload["per_rule_results"]["kicad_geometry"]["floating_label_count"] == 0
    assert payload["per_rule_results"]["png_visual"]["width_px"] >= 3000
    assert payload["per_rule_results"]["png_visual"]["selection_like_pixels"] == 0
    assert "This is an automated engineering-layout audit, not final human approval." in payload["statement"]


def test_final_schematic_layout_audit_reports_each_functional_block() -> None:
    payload = run_audit()
    expected = {
        "DD1 ESP32 core block",
        "RESET/EN block",
        "BOOT block",
        "LED block",
        "DS18B20 sensor block",
        "UART/service block",
        "heater driver block",
        "power block",
    }
    assert set(payload["per_block_results"]) == expected
    for block in payload["per_block_results"].values():
        assert block["status"] in {"PASS", "WARN"}
        assert block["wire_count"] > 0
        assert block["label_count"] > 0
        crop = ROOT / block["evidence_crop"]
        assert crop.exists()
        assert crop.stat().st_size > 0


def test_final_schematic_layout_audit_has_evidence_for_all_warnings() -> None:
    payload = run_audit()
    for finding in payload["findings"]:
        if finding["severity"] in {"BLOCKER", "WARNING"}:
            assert finding["evidence_crop"]
            crop = ROOT / finding["evidence_crop"]
            assert crop.exists()
            assert crop.stat().st_size > 0
            assert finding["source_file"]
            assert finding["threshold"] != ""


def test_final_schematic_layout_audit_markdown_contains_required_sections() -> None:
    run_audit()
    text = MD_REPORT.read_text(encoding="utf-8")
    for heading in (
        "## Electrical Baseline",
        "## KiCad Geometry Metrics",
        "## Block Review",
        "## Findings",
        "## Conclusion",
    ):
        assert heading in text
    assert "not final human approval" in text
    assert "KiCad ERC" in text
    assert "JLC/KiCad topology equivalence" in text
    assert "Master table lock" in text


def test_final_schematic_layout_audit_does_not_modify_drawing_artifacts() -> None:
    tracked_guard_paths = [
        "hardware/eda/functiondiagramYUANLITU.drawio",
        "hardware/eda/functiondiagramYUANLITU.generated.drawio",
        "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio",
        "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg",
        "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.pdf",
        "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png",
        "hardware/eda/exports/final/review_crops",
        "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch",
        "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym",
        "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro",
        "hardware/kicad_schematic/exports",
    ]
    run_audit()
    for path in tracked_guard_paths:
        result = subprocess.run(["git", "diff", "--quiet", "--", path], cwd=ROOT, check=False)
        assert result.returncode == 0, path
