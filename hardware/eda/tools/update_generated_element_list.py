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
CONFIRMED_BOM_FILE = ROOT / "hardware/eda/bom_mpn_manufacturer_confirmed.json"
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

DEFAULT_ELEMENT_LIST_TEXT_BY_ID = {
    "Evo6jcjRQjkPnHUFUJlg-6": "Position number",
    "Evo6jcjRQjkPnHUFUJlg-7": "Name",
    "Evo6jcjRQjkPnHUFUJlg-8": "Qty",
    "Evo6jcjRQjkPnHUFUJlg-9": "Note",
    "Evo6jcjRQjkPnHUFUJlg-12": "Capacitors",
    "Evo6jcjRQjkPnHUFUJlg-13": "C1, C4",
    "Evo6jcjRQjkPnHUFUJlg-14": "Capacitor 0.1 uF, C0603",
    "Evo6jcjRQjkPnHUFUJlg-15": "2",
    "Evo6jcjRQjkPnHUFUJlg-16": "Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-18": "C2, C3",
    "Evo6jcjRQjkPnHUFUJlg-19": "Capacitor 10 uF / Capacitor 100 uF, C0603",
    "Evo6jcjRQjkPnHUFUJlg-20": "2",
    "Evo6jcjRQjkPnHUFUJlg-21": "Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-27": "Resistors",
    "Evo6jcjRQjkPnHUFUJlg-26": "R1, R5, R6",
    "Evo6jcjRQjkPnHUFUJlg-25": "Resistor 10 kOhm, R0603",
    "Evo6jcjRQjkPnHUFUJlg-28": "3",
    "Evo6jcjRQjkPnHUFUJlg-30": "R2, R3, R4",
    "Evo6jcjRQjkPnHUFUJlg-31": "Resistor 4.7 kOhm;\nResistor 330 Ohm;\nResistor 100 Ohm, R0603",
    "Evo6jcjRQjkPnHUFUJlg-32": "3",
    "Evo6jcjRQjkPnHUFUJlg-35": "Semiconductor Devices",
    "Evo6jcjRQjkPnHUFUJlg-37": "DD1, HL1, VT1",
    "Evo6jcjRQjkPnHUFUJlg-38": "ESP32-WROOM-32 Wi-Fi module;\nLED0603-RD red LED; NMOS3400 MOSFET",
    "Evo6jcjRQjkPnHUFUJlg-39": "3",
    "Evo6jcjRQjkPnHUFUJlg-40": "Espressif / Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-42": "SB1, SB2",
    "Evo6jcjRQjkPnHUFUJlg-43": "TactswitchSMT6x6x7_5 tactile switch",
    "Evo6jcjRQjkPnHUFUJlg-44": "2",
    "Evo6jcjRQjkPnHUFUJlg-45": "Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-50": "XS1; XS2, XS3",
    "Evo6jcjRQjkPnHUFUJlg-51": "XH-3PA 3-pin connector;\n2P-P3.81_KF2EDGV-3.81-2P terminal",
    "Evo6jcjRQjkPnHUFUJlg-52": "3",
    "Evo6jcjRQjkPnHUFUJlg-53": "ZHOURI / Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-54": "XS4, XS5",
    "Evo6jcjRQjkPnHUFUJlg-55": "Header45.08-4P service connector;\nKF301-2P terminal",
    "Evo6jcjRQjkPnHUFUJlg-56": "2",
    "Evo6jcjRQjkPnHUFUJlg-57": "Mfr TBD",
    "Evo6jcjRQjkPnHUFUJlg-60": "A1",
    "Evo6jcjRQjkPnHUFUJlg-61": "Header45.08-4P DC/DC module interface",
    "Evo6jcjRQjkPnHUFUJlg-62": "1",
}


TABLE_ROW_BY_REFS = {
    ("C1", "C4"): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-13",
        "name": "Evo6jcjRQjkPnHUFUJlg-14",
        "qty": "Evo6jcjRQjkPnHUFUJlg-15",
        "note": "Evo6jcjRQjkPnHUFUJlg-16",
    },
    ("C2",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-18",
        "name": "Evo6jcjRQjkPnHUFUJlg-19",
        "qty": "Evo6jcjRQjkPnHUFUJlg-20",
        "note": "Evo6jcjRQjkPnHUFUJlg-21",
    },
    ("C3",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-26",
        "name": "Evo6jcjRQjkPnHUFUJlg-25",
        "qty": "Evo6jcjRQjkPnHUFUJlg-28",
    },
    ("R1", "R5", "R6"): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-30",
        "name": "Evo6jcjRQjkPnHUFUJlg-31",
        "qty": "Evo6jcjRQjkPnHUFUJlg-32",
    },
    ("R2",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-37",
        "name": "Evo6jcjRQjkPnHUFUJlg-38",
        "qty": "Evo6jcjRQjkPnHUFUJlg-39",
        "note": "Evo6jcjRQjkPnHUFUJlg-40",
    },
    ("R3",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-42",
        "name": "Evo6jcjRQjkPnHUFUJlg-43",
        "qty": "Evo6jcjRQjkPnHUFUJlg-44",
        "note": "Evo6jcjRQjkPnHUFUJlg-45",
    },
    ("R4",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-50",
        "name": "Evo6jcjRQjkPnHUFUJlg-51",
        "qty": "Evo6jcjRQjkPnHUFUJlg-52",
        "note": "Evo6jcjRQjkPnHUFUJlg-53",
    },
    ("DD1",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-54",
        "name": "Evo6jcjRQjkPnHUFUJlg-55",
        "qty": "Evo6jcjRQjkPnHUFUJlg-56",
        "note": "Evo6jcjRQjkPnHUFUJlg-57",
    },
    ("HL1",): {
        "refs": "Evo6jcjRQjkPnHUFUJlg-60",
        "name": "Evo6jcjRQjkPnHUFUJlg-61",
        "qty": "Evo6jcjRQjkPnHUFUJlg-62",
    },
}

OVERLAY_ELEMENT_LIST_ROWS = [
    ("VT1", "NMOS3400 N-channel MOSFET", "1", "NEEDS_CONFIRMATION"),
    ("SB1, SB2", "TactswitchSMT6x6x7_5 tactile switch", "2", "NEEDS_CONFIRMATION"),
    ("XS1", "XH-3PA 3-pin XH connector", "1", "ZHOURI"),
    ("XS2, XS3", "2P-P3.81_KF2EDGV-3.81-2P terminal", "2", "NEEDS_CONFIRMATION"),
    ("XS4", "Header45.08-4P service connector", "1", "NEEDS_CONFIRMATION"),
    ("XS5", "KF301-2P terminal connector", "1", "NEEDS_CONFIRMATION"),
    ("A1", "Header45.08-4P DC/DC interface", "1", "NEEDS_CONFIRMATION"),
]

OVERLAY_NOTE_CELLS = [
    ("C3", 336.01, "Samsung E-M"),
    ("R1_R5_R6", 403.01, "YAGEO"),
    ("HL1", 1070.01, "NEEDS_CONFIRMATION"),
]


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


def load_confirmed_bom_text() -> dict[str, str]:
    if not CONFIRMED_BOM_FILE.exists():
        return dict(DEFAULT_ELEMENT_LIST_TEXT_BY_ID)
    data = json.loads(CONFIRMED_BOM_FILE.read_text(encoding="utf-8"))
    by_ref: dict[str, dict[str, str]] = {}
    for item in data.get("items", []):
        for ref in item.get("refs", []):
            by_ref[str(ref)] = {
                "manufacturer_part": str(item.get("manufacturer_part", "")).strip(),
                "manufacturer": str(item.get("manufacturer", "")).strip(),
                "list_note": str(item.get("list_note", "")).strip(),
                "description": str(item.get("description", "")).strip(),
            }

    values = dict(DEFAULT_ELEMENT_LIST_TEXT_BY_ID)
    # Clear legacy mother-table cells that are not part of the ESP32 List of Elements.
    for legacy_id in (
        "cfE38QplHeOGj-dFLcIy-40",
        "Evo6jcjRQjkPnHUFUJlg-40",
        "Evo6jcjRQjkPnHUFUJlg-45",
        "Evo6jcjRQjkPnHUFUJlg-53",
        "Evo6jcjRQjkPnHUFUJlg-57",
    ):
        values[legacy_id] = ""
    values["Evo6jcjRQjkPnHUFUJlg-27"] = "Resistors"
    values["Evo6jcjRQjkPnHUFUJlg-35"] = "Semiconductor Devices"
    for refs, ids in TABLE_ROW_BY_REFS.items():
        entries = [by_ref[ref] for ref in refs if ref in by_ref]
        if len(entries) != len(refs):
            missing = [ref for ref in refs if ref not in by_ref]
            raise ValueError(f"{CONFIRMED_BOM_FILE} is missing confirmed BOM refs: {', '.join(missing)}")
        values[ids["refs"]] = "; ".join(refs) if refs in {("XS1", "XS2", "XS3")} else ", ".join(refs)
        values[ids["qty"]] = str(len(refs))
        names = []
        manufacturers = []
        for entry in entries:
            name = f"{entry['manufacturer_part']} {entry['description']}".strip()
            maker = entry.get("list_note") or entry["manufacturer"]
            if name and name not in names:
                names.append(name)
            if maker and maker not in manufacturers:
                manufacturers.append(maker)
        values[ids["name"]] = "\n".join(names)
        if note_id := ids.get("note"):
            values[note_id] = "\n".join(manufacturers)
    return values


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
    text_by_id = load_confirmed_bom_text()
    missing = sorted(set(text_by_id) - set(cells))
    if missing:
        raise ValueError(f"Could not locate master element-list text cells: {', '.join(missing)}")
    for cell_id, value in text_by_id.items():
        cell = cells[cell_id]
        cell.set("value", replacement_value_preserving_master_markup(cell.get("value", ""), value))


def add_overlay_element_list_rows(root_cell: ET.Element) -> None:
    """Add extra semantic BOM rows without changing the locked master table geometry."""
    parent = "OTuqVLYWGNuakiADof2M-1"
    x_ref, x_name, x_qty, x_note = 2315.01, 2445.01, 2954.01, 3005.01
    w_ref, w_name, w_qty, w_note = 126.0, 506.0, 48.0, 166.0
    row_h = 42.0
    y0 = 1132.0
    font_size = 13
    for index, (refs, name, qty, note) in enumerate(OVERLAY_ELEMENT_LIST_ROWS):
        y = y0 + index * row_h
        add_text_cell(
            root_cell,
            cell_id=f"element_list.generated.semantic.{index}.refs",
            parent=parent,
            value=refs,
            x=x_ref,
            y=y,
            width=w_ref,
            height=row_h,
            font_size=font_size,
            role="generated_element_list_semantic_text",
        )
        add_text_cell(
            root_cell,
            cell_id=f"element_list.generated.semantic.{index}.name",
            parent=parent,
            value=name,
            x=x_name,
            y=y,
            width=w_name,
            height=row_h,
            font_size=font_size,
            role="generated_element_list_semantic_text",
        )
        add_text_cell(
            root_cell,
            cell_id=f"element_list.generated.semantic.{index}.qty",
            parent=parent,
            value=qty,
            x=x_qty,
            y=y,
            width=w_qty,
            height=row_h,
            font_size=font_size,
            role="generated_element_list_semantic_text",
        )
        add_text_cell(
            root_cell,
            cell_id=f"element_list.generated.semantic.{index}.note",
            parent=parent,
            value=note,
            x=x_note,
            y=y,
            width=w_note,
            height=row_h,
            font_size=font_size,
            role="generated_element_list_semantic_text",
        )


def add_overlay_note_cells(root_cell: ET.Element) -> None:
    """Add Note-column text for locked master rows that have no original text cell."""
    parent = "OTuqVLYWGNuakiADof2M-1"
    for cell_key, y, note in OVERLAY_NOTE_CELLS:
        add_text_cell(
            root_cell,
            cell_id=f"element_list.generated.note.{cell_key}",
            parent=parent,
            value=note,
            x=3005.01,
            y=y,
            width=166.0,
            height=60.0,
            font_size=12,
            role="generated_element_list_note_text",
        )


def update_element_list(tree: ET.ElementTree) -> None:
    validate_bom_refs()
    root_cell = find_root_cell(tree)
    remove_previous_generated_bom_cells(root_cell)
    replace_master_element_list_text(root_cell)
    add_overlay_note_cells(root_cell)
    add_overlay_element_list_rows(root_cell)


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
