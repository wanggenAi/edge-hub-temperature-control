from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
JLC_SVG = ROOT / "hardware/eda/jlc_schematic_original.svg"
GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"
FINAL_SVG = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg"
FINAL_PNG = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png"
CREATE_SCRIPT = ROOT / "hardware/eda/tools/create_jlc_style_schematic_drawio.py"
AUDIT_SCRIPT = ROOT / "hardware/eda/tools/audit_jlc_style_layout.py"
VALIDATE_TABLES = ROOT / "hardware/eda/tools/validate_generated_tables_match_master.py"

REQUIRED_REFS = {
    "DD1",
    "VT1",
    "HL1",
    "SB1",
    "SB2",
    "A1",
    "XS1",
    "XS2",
    "XS3",
    "XS4",
    "XS5",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
    "C1",
    "C2",
    "C3",
    "C4",
}

REQUIRED_NETS = {
    "+3V3",
    "+12V",
    "GND",
    "EN",
    "LED",
    "LED_A",
    "DQ",
    "RXD0",
    "TXD0",
    "BOOT",
    "GATE",
    "GATE_R",
    "HEAT+",
    "HEAT-",
}

FORBIDDEN = {
    "U1",
    "Q1",
    "D1",
    "CN1",
    "J2_heater",
    "J_Power",
    "U7",
    "J_TS1",
    "U3_reset",
    "U4_boot",
    "U3_buck",
    "J1_12V",
    "UART_GND",
    "GATE_DRV",
    "HEATER_PLUS",
    "HEATER_SW",
    "LED_SERIES",
    "$1N",
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def decoded_payloads(payload: str) -> str:
    pieces = [payload]
    for match in re.finditer(r"data:image/svg\+xml,([^\"'&<> ]+)", payload):
        pieces.append(urllib.parse.unquote(match.group(1)))
    return " ".join(pieces)


def token_present(token: str, haystack: str) -> bool:
    if token == "$1N":
        return "$1N" in haystack
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.-])3V3(?![A-Za-z0-9_.-])", haystack) is not None
    return re.search(rf"(?<![A-Za-z0-9_.+-]){re.escape(token)}(?![A-Za-z0-9_.+-])", haystack) is not None


def test_jlc_source_svg_is_available_and_contains_original_symbols() -> None:
    payload = text(JLC_SVG)
    assert "<svg" in payload
    assert "U1" in payload
    assert "ESP32-WROOM-32" in payload
    assert "嘉立创EDA" in payload


def test_generator_embeds_jlc_source_style_not_kicad(tmp_path: Path) -> None:
    output = tmp_path / "jlc_style.drawio"
    subprocess.run(
        [
            sys.executable,
            str(CREATE_SCRIPT),
            "--frame",
            str(FRAME),
            "--jlc-svg",
            str(JLC_SVG),
            "--output",
            str(output),
        ],
        check=True,
    )
    payload = decoded_payloads(text(output))
    assert 'data-role="jlc_style_schematic_embed"' in payload
    assert "jlc_schematic_original.svg" in payload
    assert "kicad.schematic.embed" not in payload
    for ref in REQUIRED_REFS:
        assert token_present(ref, payload), ref
    for net in REQUIRED_NETS:
        assert token_present(net, payload), net
    for old in FORBIDDEN:
        assert not token_present(old, payload), old

    root = ET.parse(output).find(".//root")
    assert root is not None
    groups = {cell.get("data-ref") for cell in root if cell.get("data-role") == "jlc_symbol_group"}
    assert REQUIRED_REFS <= groups


def test_generated_tables_still_match_master_after_jlc_style_generation(tmp_path: Path) -> None:
    output = tmp_path / "jlc_style.drawio"
    subprocess.run(
        [
            sys.executable,
            str(CREATE_SCRIPT),
            "--frame",
            str(FRAME),
            "--jlc-svg",
            str(JLC_SVG),
            "--output",
            str(output),
        ],
        check=True,
    )
    validator = load_module(VALIDATE_TABLES, "validate_generated_tables_match_master_for_jlc_style")
    master = validator.master_signature(FRAME)
    findings, summary = validator.compare_candidate(master, output)
    assert findings == []
    assert summary["geometry_matches_master"] is True


def test_current_final_jlc_style_outputs_pass_audit_when_present(tmp_path: Path) -> None:
    if not (FINAL_DRAWIO.exists() and FINAL_SVG.exists() and FINAL_PNG.exists()):
        return
    report = tmp_path / "audit.json"
    md = tmp_path / "audit.md"
    crops = tmp_path / "crops"
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--jlc-source",
            str(JLC_SVG),
            "--final-drawio",
            str(FINAL_DRAWIO),
            "--final-svg",
            str(FINAL_SVG),
            "--final-png",
            str(FINAL_PNG),
            "--json-report",
            str(report),
            "--md-report",
            str(md),
            "--crops-dir",
            str(crops),
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] in {"PASS", "WARN"}
    assert data["summary"]["blocker_count"] == 0
    assert data["checks"]["old_refs_absent"] is True
    assert data["checks"]["old_nets_absent"] is True
    assert data["checks"]["kicad_style_markers_absent"] is True
