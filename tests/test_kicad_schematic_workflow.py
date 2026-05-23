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
UPDATE_ELEMENT_LIST_SCRIPT = ROOT / "hardware/eda/tools/update_generated_element_list.py"
UPDATE_TITLE_BLOCK_SCRIPT = ROOT / "hardware/eda/tools/update_generated_title_block.py"
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
FINAL_SVG = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg"

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

ESP32_BOM_TEXT = [
    "C1, C4",
    "Capacitor 0.1 uF",
    "C2",
    "Capacitor 10 uF",
    "C3",
    "Capacitor 100 uF",
    "R1, R5, R6",
    "Resistor 10 kOhm",
    "R2",
    "Resistor 4.7 kOhm",
    "R3",
    "Resistor 330 Ohm",
    "R4",
    "Resistor 100 Ohm",
    "DD1",
    "ESP32-WROOM-32 Wi-Fi module",
    "HL1",
    "Red LED",
    "VT1",
    "NMOS3400 N-channel MOSFET",
    "SB1, SB2",
    "Tact switch SMT 6x6x7.5",
    "XS1",
    "XH-3PA 3-pin connector",
    "XS2, XS3",
    "KF2EDGV-3.81-2P connector",
    "XS4",
    "Header45.08-4P service connector",
    "XS5",
    "KF301-2P terminal connector",
    "A1",
    "DC/DC converter 12 V to 3.3 V",
]

LEGACY_BOM_TEXT = [
    "Microcontroller AT89C52",
    "LCD1602-A",
    "Crystal Oscillator",
    "BUTTON SPST",
    "Micro-USB to DIP adapter",
    "RV1",
    "ZQ1",
    "DD2",
    "DD3",
]

ESP32_TITLE_TEXT = [
    "BSTU.241297.006 Э3",
    "ESP32 Temperature Control Unit",
    "Electrical Schematic Diagram",
    "Brest State Technical University",
    "Wang Gen",
    "A1",
    "N/A",
]

LEGACY_TITLE_TEXT = [
    "Microcontroller-based I/O Device",
    "Department of Computer and System",
    "Разумейчик",
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


def drawio_geometry(path: Path, cell_id: str) -> tuple[float, float, float, float]:
    root = ET.parse(path).find(".//root")
    assert root is not None
    cell = root.find(f".//mxCell[@id='{cell_id}']")
    assert cell is not None
    geometry = cell.find("mxGeometry")
    assert geometry is not None
    return tuple(float(geometry.get(key, "0")) for key in ("x", "y", "width", "height"))


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


def visible_drawio_xml_text(path: Path) -> str:
    values: list[str] = []
    for cell in ET.parse(path).findall(".//mxCell"):
        value = cell.get("value", "")
        if not value:
            continue
        value = value.replace("&nbsp;", " ")
        value = value.replace("&amp;", "&")
        value = value.replace("&lt;", "<")
        value = value.replace("&gt;", ">")
        value = re.sub(r"<br\s*/?>", " ", value)
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            values.append(value)
    return " ".join(values)


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


def test_update_generated_element_list_replaces_legacy_bom_without_touching_source_frame(tmp_path: Path) -> None:
    generated = tmp_path / "generated.drawio"
    updated = tmp_path / "updated.drawio"
    subprocess.run(
        [
            sys.executable,
            str(EMBED_SCRIPT),
            "--frame",
            str(FRAME),
            "--kicad-svg",
            str(KICAD_SVG),
            "--output",
            str(generated),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(UPDATE_ELEMENT_LIST_SCRIPT),
            "--input",
            str(generated),
            "--output",
            str(updated),
        ],
        check=True,
    )
    frame_text = visible_drawio_xml_text(FRAME)
    assert "Microcontroller AT89C52" in frame_text
    updated_text = visible_drawio_xml_text(updated)
    for value in ESP32_BOM_TEXT:
        assert value in updated_text
    for value in LEGACY_BOM_TEXT:
        assert value not in updated_text


def test_update_generated_title_block_replaces_template_text_without_touching_source_frame(tmp_path: Path) -> None:
    generated = tmp_path / "generated.drawio"
    updated = tmp_path / "updated.drawio"
    subprocess.run(
        [
            sys.executable,
            str(EMBED_SCRIPT),
            "--frame",
            str(FRAME),
            "--kicad-svg",
            str(KICAD_SVG),
            "--output",
            str(generated),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(UPDATE_TITLE_BLOCK_SCRIPT),
            "--input",
            str(generated),
            "--output",
            str(updated),
        ],
        check=True,
    )
    frame_text = visible_drawio_xml_text(FRAME)
    assert "Microcontroller-based I/O Device" in frame_text
    assert "Department of Computer and System" in frame_text
    updated_text = visible_drawio_xml_text(updated)
    for value in ESP32_TITLE_TEXT:
        assert value in updated_text
    for value in LEGACY_TITLE_TEXT:
        assert value not in updated_text


def test_embed_script_places_kicad_block_in_main_schematic_area(tmp_path: Path) -> None:
    output = tmp_path / "generated.drawio"
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
    x, y, width, height = drawio_geometry(output, "kicad.schematic.embed")
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    outer = lock["regions"]["outer_frame"]["bbox"]
    element_list = lock["regions"]["element_list"]["bbox"]
    title_block = lock["regions"]["title_block"]["bbox"]
    main_width = element_list["x"] - outer["x"]
    main_height = title_block["y"] - outer["y"]

    assert outer["x"] <= x
    assert outer["y"] <= y
    assert x + width <= element_list["x"] - 30
    assert y + height <= title_block["y"] - 40
    assert 0.70 <= width / main_width <= 0.85
    assert 0.45 <= height / main_height <= 0.70


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


def test_generated_drawio_has_esp32_bom_when_present() -> None:
    if not GENERATED.exists():
        return
    payload = visible_drawio_xml_text(GENERATED)
    for value in ESP32_BOM_TEXT:
        assert value in payload
    for value in LEGACY_BOM_TEXT:
        assert value not in payload


def test_generated_drawio_has_esp32_title_block_when_present() -> None:
    if not GENERATED.exists():
        return
    payload = visible_drawio_xml_text(GENERATED)
    for value in ESP32_TITLE_TEXT:
        assert value in payload
    for value in LEGACY_TITLE_TEXT:
        assert value not in payload


def test_final_svg_kicad_embed_geometry_when_present() -> None:
    if not FINAL_SVG.exists():
        return
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("export_artifact_lint", ROOT / "tools/export_artifact_lint.py")
    assert spec and spec.loader
    lint = module_from_spec(spec)
    sys.modules[spec.name] = lint
    spec.loader.exec_module(lint)

    findings = []
    payload: dict[str, object] = {}
    lint.validate_kicad_embed_geometry(FINAL_SVG.read_text(encoding="utf-8"), LOCK_FILE, findings, str(FINAL_SVG), payload)
    assert findings == []
