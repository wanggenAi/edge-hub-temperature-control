from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
KICAD_DIR = ROOT / "hardware/kicad_schematic"
KICAD_SCH = KICAD_DIR / "esp32_temperature_control_unit.kicad_sch"
KICAD_SYM = KICAD_DIR / "esp32_temperature_control_unit.kicad_sym"
KICAD_SVG = KICAD_DIR / "exports/esp32_temperature_control_unit_schematic.svg"
EMBED_SCRIPT = ROOT / "hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py"

REQUIRED_REFS = [
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
]

CANONICAL_NETS = [
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
]

FORBIDDEN_SOURCE_REFS = [
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
]

FORBIDDEN_NETS = [
    "J1_12V",
    "UART_GND",
    "GATE_DRV",
    "HEATER_PLUS",
    "HEATER_SW",
    "LED_SERIES",
    "$1N",
]

PROFESSIONAL_PROJECT_SYMBOLS = [
    "ESP32_Temperature_Control:R_H",
    "ESP32_Temperature_Control:C_H",
    "ESP32_Temperature_Control:SW_NO_H",
    "ESP32_Temperature_Control:LED_H",
    "ESP32_Temperature_Control:NMOS_GDS",
    "ESP32_Temperature_Control:CONN_2",
    "ESP32_Temperature_Control:CONN_3",
    "ESP32_Temperature_Control:CONN_4",
    "ESP32_Temperature_Control:ESP32-WROOM-32",
    "ESP32_Temperature_Control:DCDC_12V_3V3",
]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def token_present(token: str, haystack: str) -> bool:
    if token == "$1N":
        return "$1N" in haystack
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.-])3V3(?![A-Za-z0-9_.-])", haystack) is not None
    if re.fullmatch(r"[A-Z]+[0-9]+", token):
        escaped = re.escape(token)
        return re.search(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", haystack) is not None
    escaped = re.escape(token)
    return re.search(rf"(?<![A-Za-z0-9_.+-]){escaped}(?![A-Za-z0-9_.+-])", haystack) is not None


def drawio_visible_payload(path: Path) -> str:
    payload = text(path)
    decoded = [payload]
    for match in re.finditer(r"data:image/svg\+xml,([^\"'&<> ]+)", payload, flags=re.I):
        decoded.append(urllib.parse.unquote(match.group(1)))
    return "\n".join(decoded)


def locked_template_fingerprint(path: Path) -> str:
    tree = ET.parse(path)
    values: list[str] = []
    for cell in tree.findall(".//mxCell"):
        value = cell.get("value", "")
        style = cell.get("style", "")
        geometry = cell.find("mxGeometry")
        geom_attrs = "" if geometry is None else repr(sorted(geometry.attrib.items()))
        if any(
            marker in value
            for marker in (
                "Position number",
                "Capacitors",
                "BSTU.241297.006",
                "Microcontroller-based I/O Device",
                "Department of Computer",
            )
        ):
            values.append(f"{cell.get('id')}|{value}|{style}|{geom_attrs}")
    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def test_kicad_sources_exist_and_use_professional_symbols() -> None:
    assert KICAD_SCH.exists()
    assert KICAD_SYM.exists()
    schematic = text(KICAD_SCH)
    for symbol in PROFESSIONAL_PROJECT_SYMBOLS:
        assert symbol in schematic
    assert "(generator \"codex-kicad-local-wiring\")" in schematic
    assert "(label " not in schematic
    assert "(global_label " in schematic


def test_kicad_source_visible_refs_and_nets_are_canonical() -> None:
    schematic = text(KICAD_SCH)
    for ref in REQUIRED_REFS:
        assert f'"Reference" "{ref}"' in schematic
    for net in CANONICAL_NETS:
        assert f'(global_label "{net}"' in schematic
    for forbidden in FORBIDDEN_SOURCE_REFS:
        assert not token_present(forbidden, schematic)
    for forbidden in FORBIDDEN_NETS:
        assert forbidden not in schematic
    assert not token_present("3V3", schematic)


def test_kicad_erc_has_no_violations_when_cli_available(tmp_path: Path) -> None:
    kicad_cli = shutil.which("kicad-cli")
    macos_cli = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if not kicad_cli and macos_cli.exists():
        kicad_cli = str(macos_cli)
    if not kicad_cli:
        return

    report = tmp_path / "erc.json"
    subprocess.run(
        [
            kicad_cli,
            "sch",
            "erc",
            "--format",
            "json",
            "--output",
            str(report),
            str(KICAD_SCH),
        ],
        check=True,
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    violations = [violation for sheet in data.get("sheets", []) for violation in sheet.get("violations", [])]
    assert violations == []


def test_embed_script_generates_drawio_without_touching_template(tmp_path: Path) -> None:
    output = tmp_path / "generated.drawio"
    before = locked_template_fingerprint(FRAME)
    subprocess.run(
        [
            sys.executable,
            str(EMBED_SCRIPT),
            "--frame",
            str(FRAME),
            "--kicad-svg",
            str(KICAD_SVG),
            "--output",
            str(output),
        ],
        check=True,
    )
    after = locked_template_fingerprint(output)
    assert before == after
    payload = drawio_visible_payload(output)
    assert 'data-role="kicad_schematic_embed"' in payload
    for ref in REQUIRED_REFS:
        assert ref in payload
    for net in CANONICAL_NETS:
        assert net in payload
    for forbidden in FORBIDDEN_SOURCE_REFS:
        assert not token_present(forbidden, payload)
    for forbidden in FORBIDDEN_NETS:
        assert not token_present(forbidden, payload)


def test_generated_drawio_is_kicad_embedded_when_present() -> None:
    if not GENERATED.exists():
        return
    payload = drawio_visible_payload(GENERATED)
    assert 'data-role="kicad_schematic_embed"' in payload
    assert "generated.schematic.root" not in payload
    for ref in REQUIRED_REFS:
        assert ref in payload
    for net in CANONICAL_NETS:
        assert net in payload
