#!/usr/bin/env python3
"""Replace the generated draw.io element-list text with the ESP32 BOM."""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
MODEL_FILE = ROOT / "hardware/eda/schematic_model.yaml"
KICAD_SCH = ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch"
ELEMENT_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"

HEADER_TEXT = {"Position number", "Name", "Number", "Qty", "Note"}
REQUIRED_REFS = {
    "C1",
    "C2",
    "C3",
    "C4",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
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
}


@dataclass(frozen=True)
class BomRow:
    kind: str
    refs: str = ""
    name: str = ""
    quantity: str = ""
    note: str = ""


ELEMENT_LIST_ROWS = [
    BomRow("group", name="Capacitors"),
    BomRow("item", "C1, C4", "Capacitor 0.1 uF, C0603", "2", "Generic"),
    BomRow("item", "C2", "Capacitor 10 uF, C0603", "1", "Generic"),
    BomRow("item", "C3", "Capacitor 100 uF, C0603", "1", "Generic"),
    BomRow("group", name="Resistors"),
    BomRow("item", "R1, R5, R6", "Resistor 10 kOhm, R0603", "3", "Generic"),
    BomRow("item", "R2", "Resistor 4.7 kOhm, R0603", "1", "Generic"),
    BomRow("item", "R3", "Resistor 330 Ohm, R0603", "1", "Generic"),
    BomRow("item", "R4", "Resistor 100 Ohm, R0603", "1", "Generic"),
    BomRow("group", name="Semiconductor Devices"),
    BomRow("item", "DD1", "ESP32-WROOM-32 Wi-Fi module", "1", "Espressif"),
    BomRow("item", "HL1", "Red LED, LED0603-RD_RED", "1", "LCSC"),
    BomRow("item", "VT1", "NMOS3400 N-channel MOSFET", "1", "LCSC"),
    BomRow("group", name="Switching Components"),
    BomRow("item", "SB1, SB2", "Tact switch SMT 6x6x7.5", "2", "LCSC"),
    BomRow("group", name="Connectors"),
    BomRow("item", "XS1", "XH-3PA 3-pin connector", "1", "ZHOURI/LCSC"),
    BomRow("item", "XS2, XS3", "KF2EDGV-3.81-2P connector", "2", "LCSC"),
    BomRow("item", "XS4", "Header45.08-4P service connector", "1", "LCSC"),
    BomRow("item", "XS5", "KF301-2P terminal connector", "1", "LCSC"),
    BomRow("group", name="Power Modules"),
    BomRow("item", "A1", "DC/DC converter 12 V to 3.3 V", "1", "LCSC"),
]

ELEMENT_LIST_TEXT_BY_ID = {
    "Evo6jcjRQjkPnHUFUJlg-6": "Position number",
    "Evo6jcjRQjkPnHUFUJlg-7": "Name",
    "Evo6jcjRQjkPnHUFUJlg-8": "Qty",
    "Evo6jcjRQjkPnHUFUJlg-9": "Note",
    "Evo6jcjRQjkPnHUFUJlg-12": "Capacitors",
    "Evo6jcjRQjkPnHUFUJlg-13": "C1, C4",
    "Evo6jcjRQjkPnHUFUJlg-14": "Capacitor 0.1 uF, C0603",
    "Evo6jcjRQjkPnHUFUJlg-15": "2",
    "Evo6jcjRQjkPnHUFUJlg-16": "Generic",
    "Evo6jcjRQjkPnHUFUJlg-18": "C2, C3",
    "Evo6jcjRQjkPnHUFUJlg-19": "Capacitor 10 uF / Capacitor 100 uF, C0603",
    "Evo6jcjRQjkPnHUFUJlg-20": "2",
    "Evo6jcjRQjkPnHUFUJlg-21": "Generic",
    "Evo6jcjRQjkPnHUFUJlg-27": "Resistors",
    "Evo6jcjRQjkPnHUFUJlg-26": "R1, R5, R6",
    "Evo6jcjRQjkPnHUFUJlg-25": "Resistor 10 kOhm, R0603",
    "Evo6jcjRQjkPnHUFUJlg-28": "3",
    "Evo6jcjRQjkPnHUFUJlg-30": "R2, R3, R4",
    "Evo6jcjRQjkPnHUFUJlg-31": "Resistor 4.7 kOhm;\nResistor 330 Ohm;\nResistor 100 Ohm, R0603",
    "Evo6jcjRQjkPnHUFUJlg-32": "3",
    "Evo6jcjRQjkPnHUFUJlg-35": "Semiconductor Devices",
    "Evo6jcjRQjkPnHUFUJlg-37": "DD1, HL1, VT1",
    "Evo6jcjRQjkPnHUFUJlg-38": "ESP32-WROOM-32 Wi-Fi module;\nRed LED; NMOS3400 N-channel MOSFET",
    "Evo6jcjRQjkPnHUFUJlg-39": "3",
    "Evo6jcjRQjkPnHUFUJlg-40": "Espressif / LCSC",
    "Evo6jcjRQjkPnHUFUJlg-42": "SB1, SB2",
    "Evo6jcjRQjkPnHUFUJlg-43": "Tact switch SMT 6x6x7.5",
    "Evo6jcjRQjkPnHUFUJlg-44": "2",
    "Evo6jcjRQjkPnHUFUJlg-45": "LCSC",
    "Evo6jcjRQjkPnHUFUJlg-50": "XS1; XS2, XS3",
    "Evo6jcjRQjkPnHUFUJlg-51": "XH-3PA 3-pin connector;\nKF2EDGV-3.81-2P connector",
    "Evo6jcjRQjkPnHUFUJlg-52": "3",
    "Evo6jcjRQjkPnHUFUJlg-53": "ZHOURI/LCSC",
    "Evo6jcjRQjkPnHUFUJlg-54": "XS4, XS5",
    "Evo6jcjRQjkPnHUFUJlg-55": "Header45.08-4P service connector;\nKF301-2P terminal connector",
    "Evo6jcjRQjkPnHUFUJlg-56": "2",
    "Evo6jcjRQjkPnHUFUJlg-57": "LCSC",
    "Evo6jcjRQjkPnHUFUJlg-60": "A1",
    "Evo6jcjRQjkPnHUFUJlg-61": "Power Modules: DC/DC converter 12 V to 3.3 V",
    "Evo6jcjRQjkPnHUFUJlg-62": "1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update generated draw.io List of Elements text to the ESP32 BOM.")
    parser.add_argument("--input", type=Path, required=True, help="Generated draw.io file to update")
    parser.add_argument("--output", type=Path, required=True, help="Updated draw.io output path")
    return parser.parse_args()


def read_tree(path: Path) -> ET.ElementTree:
    if not path.exists():
        raise FileNotFoundError(path)
    return ET.parse(path)


def find_root_cell(tree: ET.ElementTree) -> ET.Element:
    root_cell = tree.find(".//root")
    if root_cell is None:
        raise ValueError("draw.io XML has no <root> cell container")
    return root_cell


def absolute_bbox_by_id(root_cell: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    cells = {cell.get("id", ""): cell for cell in root_cell if cell.get("id")}
    memo: dict[str, tuple[float, float, float, float]] = {}

    def bbox(cell_id: str) -> tuple[float, float, float, float]:
        if cell_id in memo:
            return memo[cell_id]
        cell = cells.get(cell_id)
        if cell is None:
            return (0.0, 0.0, 0.0, 0.0)
        geom = cell.find("mxGeometry")
        x = y = width = height = 0.0
        if geom is not None:
            x = float(geom.get("x", "0") or 0)
            y = float(geom.get("y", "0") or 0)
            width = float(geom.get("width", "0") or 0)
            height = float(geom.get("height", "0") or 0)
        parent = cell.get("parent")
        if parent and parent not in {"0", "1"}:
            px, py, _, _ = bbox(parent)
            x += px
            y += py
        memo[cell_id] = (x, y, width, height)
        return memo[cell_id]

    return {cell_id: bbox(cell_id) for cell_id in cells}


def overlaps_region(rect: tuple[float, float, float, float], region: dict[str, float]) -> bool:
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return False
    return not (
        x + width < float(region["x"]) - 1
        or x > float(region["right"]) + 1
        or y + height < float(region["y"]) - 1
        or y > float(region["bottom"]) + 1
    )


def plain_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    for tag in ("<br>", "<br/>", "<br />"):
        value = value.replace(tag, " ")
    out = []
    inside = False
    for char in value:
        if char == "<":
            inside = True
            continue
        if char == ">":
            inside = False
            continue
        if not inside:
            out.append(char)
    return " ".join("".join(out).split())


def load_component_refs() -> set[str]:
    model = json.loads(MODEL_FILE.read_text(encoding="utf-8"))
    return {component["ref"] for component in model.get("components", [])}


def validate_bom_refs() -> None:
    model_refs = load_component_refs()
    missing = sorted(REQUIRED_REFS - model_refs)
    if missing:
        raise ValueError(f"schematic_model.yaml is missing refs required by generated element list: {', '.join(missing)}")
    schematic_text = KICAD_SCH.read_text(encoding="utf-8", errors="ignore")
    missing_from_kicad = [ref for ref in sorted(REQUIRED_REFS) if f'"Reference" "{ref}"' not in schematic_text]
    if missing_from_kicad:
        raise ValueError(f"KiCad schematic is missing refs required by generated element list: {', '.join(missing_from_kicad)}")


def html_value(text: str, font_size: int, bold: bool = False) -> str:
    escaped = html.escape(text).replace("\n", "<br>")
    if bold:
        escaped = f"<b>{escaped}</b>"
    return f'<font style="font-size: {font_size}px;">{escaped}</font>'


def replacement_value_preserving_master_markup(original_value: str, text: str) -> str:
    """Replace visible text while preserving the master cell's basic text wrapper."""
    if not text:
        return ""
    escaped = html.escape(text).replace("\n", "<br>")
    font_size_match = re.search(r"font-size:\s*([0-9.]+)px", original_value or "", flags=re.I)
    if not font_size_match:
        return escaped
    if re.search(r"<b\b", original_value or "", flags=re.I):
        escaped = f"<b>{escaped}</b>"
    tag = "span" if re.search(r"<span\b", original_value or "", flags=re.I) else "font"
    return f'<{tag} style="font-size: {font_size_match.group(1)}px;">{escaped}</{tag}>'


def add_text_cell(
    root_cell: ET.Element,
    *,
    cell_id: str,
    parent: str,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: int,
    role: str,
    bold: bool = False,
) -> None:
    style = (
        "text;html=1;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;"
        f"fontFamily=Helvetica;fontSize={font_size};fontColor=#000000;labelBackgroundColor=none;spacing=2;"
    )
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": cell_id,
            "value": html_value(value, font_size, bold=bold),
            "style": style,
            "vertex": "1",
            "parent": parent,
            "data-role": role,
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": f"{x:.3f}".rstrip("0").rstrip("."),
            "y": f"{y:.3f}".rstrip("0").rstrip("."),
            "width": f"{width:.3f}".rstrip("0").rstrip("."),
            "height": f"{height:.3f}".rstrip("0").rstrip("."),
            "as": "geometry",
        },
    )


def remove_previous_generated_bom_cells(root_cell: ET.Element) -> None:
    for cell in list(root_cell):
        if cell.get("data-role", "").startswith("generated_element_list_"):
            root_cell.remove(cell)
            continue
        if cell.get("id", "").startswith("element_list.generated."):
            root_cell.remove(cell)


def replace_master_element_list_text(root_cell: ET.Element) -> None:
    cells = {cell.get("id", ""): cell for cell in root_cell if cell.get("id")}
    missing = sorted(set(ELEMENT_LIST_TEXT_BY_ID) - set(cells))
    if missing:
        raise ValueError(f"Could not locate master element-list text cells: {', '.join(missing)}")
    for cell_id, value in ELEMENT_LIST_TEXT_BY_ID.items():
        cell = cells[cell_id]
        cell.set("value", replacement_value_preserving_master_markup(cell.get("value", ""), value))


def update_element_list(tree: ET.ElementTree) -> None:
    validate_bom_refs()
    root_cell = find_root_cell(tree)
    remove_previous_generated_bom_cells(root_cell)
    replace_master_element_list_text(root_cell)


def write_tree(tree: ET.ElementTree, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        tmp = output.with_suffix(output.suffix + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        tmp.replace(output)
    else:
        tree.write(output, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    tree = read_tree(args.input)
    update_element_list(tree)
    write_tree(tree, args.output)
    print(f"Updated generated List of Elements in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
