from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hardware/eda/tools/validate_bom_mpn_manufacturer.py"
CONFIRM_SCRIPT = ROOT / "hardware/eda/tools/create_bom_confirmation_package.py"
BOM = ROOT / "hardware/eda/jlc_schematic_bom.csv"
MODEL = ROOT / "hardware/eda/schematic_model.yaml"
FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_bom_mpn_manufacturer_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_utf16_jlc_bom_and_known_mpn_fields() -> None:
    module = load_module()
    rows = module.parse_bom(BOM)
    mapping = module.load_ref_mapping()
    items = module.expand_bom_items(rows, mapping)
    by_ref = {item.school_ref: item for item in items}
    assert by_ref["XS1"].manufacturer_part == "XH-3PA"
    assert "ZHOURI" in by_ref["XS1"].manufacturer
    assert by_ref["DD1"].manufacturer_part == "ESP32-WROOM-32"
    assert "ESPRESSIF" in by_ref["DD1"].manufacturer


def test_missing_mpn_or_manufacturer_requires_confirmation() -> None:
    module = load_module()
    rows = module.parse_bom(BOM)
    items = module.expand_bom_items(rows, module.load_ref_mapping())
    findings, summary = module.audit(items, module.parse_model_refs(MODEL), "")
    codes = {finding.code for finding in findings}
    assert "NEEDS_BOM_MPN_CONFIRMATION" in codes
    assert summary["unresolved_count"] > 0


def test_current_final_bom_audit_reports_confirmation_items(tmp_path: Path) -> None:
    if not FINAL_DRAWIO.exists():
        return
    json_report = tmp_path / "bom_audit.json"
    md_report = tmp_path / "bom_audit.md"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bom",
            str(BOM),
            "--model",
            str(MODEL),
            "--final-drawio",
            str(FINAL_DRAWIO),
            "--json-report",
            str(json_report),
            "--md-report",
            str(md_report),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["status"] in {"PASS", "WARN"}
    assert data["summary"]["error_count"] == 0
    assert data["bom_summary"]["unresolved_count"] > 0
    assert any(item["code"] == "NEEDS_BOM_MPN_CONFIRMATION" for item in data["findings"])


def test_bom_confirmation_package_lists_known_and_missing_fields(tmp_path: Path) -> None:
    json_output = tmp_path / "confirmation.json"
    md_output = tmp_path / "confirmation.md"
    result = subprocess.run(
        [
            sys.executable,
            str(CONFIRM_SCRIPT),
            "--bom",
            str(BOM),
            "--ref-mapping",
            str(ROOT / "hardware/eda/ref_mapping.yaml"),
            "--json-output",
            str(json_output),
            "--md-output",
            str(md_output),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(json_output.read_text(encoding="utf-8"))
    assert data["status"] == "NEEDS_BOM_MPN_CONFIRMATION"
    assert data["summary"]["confirmed_count"] == 2
    assert data["summary"]["needs_confirmation_count"] == 19
    by_ref = {item["school_ref"]: item for item in data["items"]}
    assert by_ref["DD1"]["confirmation_status"] == "confirmed_from_source_bom"
    assert by_ref["XS1"]["confirmation_status"] == "confirmed_from_source_bom"
    assert by_ref["R1"]["confirmation_status"] == "needs_human_confirmation"
    assert "User confirmed MPN" in md_output.read_text(encoding="utf-8")
