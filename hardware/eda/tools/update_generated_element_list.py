#!/usr/bin/env python3
"""Replace the generated draw.io element-list text with the ESP32 BOM."""

from __future__ import annotations

import argparse
import copy
import html
import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
MODEL_FILE = ROOT / "hardware/eda/schematic_model.yaml"
KICAD_SCH = ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch"

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


def find_element_list_frame(root_cell: ET.Element, region: dict[str, float]) -> ET.Element:
    bboxes = absolute_bbox_by_id(root_cell)
    candidates = []
    for cell in root_cell:
        cell_id = cell.get("id", "")
        if not cell_id:
            continue
        rect = bboxes.get(cell_id)
        if not rect or not overlaps_region(rect, region):
            continue
        x, y, width, height = rect
        area_delta = abs(width - float(region["width"])) + abs(height - float(region["height"]))
        if width > 600 and height > 1000:
            candidates.append((area_delta, cell))
    if not candidates:
        raise ValueError("Could not locate the element-list frame cell")
    return sorted(candidates, key=lambda item: item[0])[0][1]


def clear_generated_element_list_text(root_cell: ET.Element, region: dict[str, float]) -> None:
    bboxes = absolute_bbox_by_id(root_cell)
    for cell in root_cell:
        value = cell.get("value", "")
        if not value:
            continue
        rect = bboxes.get(cell.get("id", ""))
        if not rect or not overlaps_region(rect, region):
            continue
        if plain_text(value) in HEADER_TEXT:
            continue
        if "text;" not in cell.get("style", ""):
            continue
        cell.set("value", "")
        cell.set("data-role", "legacy_element_list_text_cleared")


def html_value(text: str, font_size: int, bold: bool = False) -> str:
    escaped = html.escape(text).replace("\n", "<br>")
    if bold:
        escaped = f"<b>{escaped}</b>"
    return f'<font style="font-size: {font_size}px;">{escaped}</font>'


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


def add_esp32_bom_text(root_cell: ET.Element, frame_cell: ET.Element) -> None:
    frame_geom = frame_cell.find("mxGeometry")
    if frame_geom is None:
        raise ValueError("Element-list frame has no geometry")
    parent = frame_cell.get("parent", "1")
    table_x = float(frame_geom.get("x", "0") or 0)
    table_y = float(frame_geom.get("y", "0") or 0)
    table_height = float(frame_geom.get("height", "0") or 0)

    columns = {
        "refs": (table_x + 2, 148.0),
        "name": (table_x + 151.0, 340.0),
        "qty": (table_x + 491.0, 68.0),
        "note": (table_x + 559.0, 169.0),
    }
    row_height = 52.0
    y = table_y + 68.0
    bottom_limit = table_y + table_height - 8.0
    for index, row in enumerate(ELEMENT_LIST_ROWS, start=1):
        if y + row_height > bottom_limit:
            raise ValueError("ESP32 BOM rows do not fit inside the locked element-list frame")
        if row.kind == "group":
            x, width = columns["name"]
            add_text_cell(
                root_cell,
                cell_id=f"element_list.generated.group.{index:02d}",
                parent=parent,
                value=row.name,
                x=x,
                y=y,
                width=width,
                height=row_height,
                font_size=13,
                role="generated_element_list_group",
                bold=True,
            )
        else:
            for column, value in (
                ("refs", row.refs),
                ("name", row.name),
                ("qty", row.quantity),
                ("note", row.note),
            ):
                x, width = columns[column]
                add_text_cell(
                    root_cell,
                    cell_id=f"element_list.generated.row.{index:02d}.{column}",
                    parent=parent,
                    value=value,
                    x=x,
                    y=y,
                    width=width,
                    height=row_height,
                    font_size=12,
                    role="generated_element_list_text",
                )
        y += row_height


def update_element_list(tree: ET.ElementTree) -> None:
    validate_bom_refs()
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    region = lock["regions"]["element_list"]["bbox"]
    root_cell = find_root_cell(tree)
    frame_cell = find_element_list_frame(root_cell, region)
    clear_generated_element_list_text(root_cell, region)
    remove_previous_generated_bom_cells(root_cell)
    add_esp32_bom_text(root_cell, frame_cell)


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
