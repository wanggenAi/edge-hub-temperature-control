#!/usr/bin/env python3
"""Embed the KiCad schematic SVG into the locked BSTU draw.io frame."""

from __future__ import annotations

import argparse
import html
import copy
import json
import re
import sys
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET


# Placement is in draw.io page units. These defaults keep the KiCad SVG in the
# left/middle schematic area while leaving measured clearance from the preserved
# element list and title block regions.
DEFAULT_X = 270.0
DEFAULT_Y = 185.0
DEFAULT_WIDTH = 2070.0
DEFAULT_HEIGHT = 1440.0
LOCK_FILE = Path(__file__).resolve().parents[1] / "reserved_regions.lock.json"
GENERATED_IDS = (
    "kicad.schematic.embed",
    "kicad.schematic.background",
    "generated.schematic.root",
)
ELEMENT_LIST_CELL_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed KiCad SVG into the school draw.io frame.")
    parser.add_argument("--frame", type=Path, required=True, help="Original school frame .drawio file")
    parser.add_argument("--kicad-svg", type=Path, required=True, help="KiCad schematic SVG export")
    parser.add_argument("--output", type=Path, required=True, help="Generated output .drawio file")
    parser.add_argument("--x", type=float, default=DEFAULT_X)
    parser.add_argument("--y", type=float, default=DEFAULT_Y)
    parser.add_argument("--width", type=float, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=float, default=DEFAULT_HEIGHT)
    return parser.parse_args()


def read_svg_for_drawio(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"KiCad SVG not found: {path}")
    svg = path.read_text(encoding="utf-8", errors="strict")
    if "<svg" not in svg:
        raise ValueError(f"Input does not look like SVG: {path}")
    if re.search(r"#(?:0000ff|00ff00|008000|ff0000)\b", svg, flags=re.I):
        raise ValueError("KiCad SVG contains forbidden editor-like colors")
    return crop_svg_to_content(svg)


def crop_svg_to_content(svg: str, margin_mm: float = 6.0) -> str:
    """Trim the KiCad page-sized SVG viewBox to the actual schematic content."""
    points: list[tuple[float, float]] = []
    for match in re.finditer(r"<path\b[^>]*\bd=\"([^\"]+)\"", svg, flags=re.I):
        numbers = [float(value) for value in re.findall(r"[-+]?\d+(?:\.\d+)?", match.group(1))]
        points.extend((numbers[i], numbers[i + 1]) for i in range(0, len(numbers) - 1, 2))
    for match in re.finditer(r"<text\b([^>]*)>", svg, flags=re.I):
        attrs = match.group(1)
        x = re.search(r'\bx="([-+]?\d+(?:\.\d+)?)"', attrs)
        y = re.search(r'\by="([-+]?\d+(?:\.\d+)?)"', attrs)
        if x and y:
            points.append((float(x.group(1)), float(y.group(1))))
    if not points:
        return svg
    min_x = max(0.0, min(x for x, _ in points) - margin_mm)
    min_y = max(0.0, min(y for _, y in points) - margin_mm)
    max_x = max(x for x, _ in points) + margin_mm
    max_y = max(y for _, y in points) + margin_mm
    width = max_x - min_x
    height = max_y - min_y
    svg = re.sub(
        r'width="[^"]+"\s+height="[^"]+"\s+viewBox="[^"]+"',
        f'width="{width:.4f}mm" height="{height:.4f}mm" viewBox="{min_x:.4f} {min_y:.4f} {width:.4f} {height:.4f}"',
        svg,
        count=1,
    )
    return svg


def parse_drawio(path: Path) -> ET.ElementTree:
    if not path.exists():
        raise FileNotFoundError(f"draw.io frame not found: {path}")
    return ET.parse(path)


def find_root_cell(tree: ET.ElementTree) -> ET.Element:
    root_cell = tree.find(".//root")
    if root_cell is None:
        raise ValueError("draw.io XML has no <root> cell container")
    return root_cell


def remove_previous_generated_cells(root_cell: ET.Element) -> None:
    for cell in list(root_cell):
        cell_id = cell.get("id", "")
        role = cell.get("data-role", "")
        if role in {"kicad_schematic_embed", "kicad_schematic_background", "schematic_root"}:
            root_cell.remove(cell)
            continue
        if any(cell_id == prefix or cell_id.startswith(f"{prefix}.") for prefix in GENERATED_IDS):
            root_cell.remove(cell)


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


def overlaps_region(
    rect: tuple[float, float, float, float],
    region: dict[str, float],
    tolerance: float = 1.0,
) -> bool:
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return False
    left, top, right, bottom = x, y, x + width, y + height
    return not (
        right < float(region["x"]) - tolerance
        or left > float(region["right"]) + tolerance
        or bottom < float(region["y"]) - tolerance
        or top > float(region["bottom"]) + tolerance
    )


def root_with_locked_regions_only(tree: ET.ElementTree) -> ET.Element:
    old_root = find_root_cell(tree)
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    regions = lock.get("regions", {})
    keep_ids: set[str] = {"0", "1"}
    keep_ids.update(regions.get("outer_frame", {}).get("cell_ids", []))
    keep_ids.update(regions.get("title_block", {}).get("cell_ids", []))

    bboxes = absolute_bbox_by_id(old_root)
    element_bbox = regions.get("element_list", {}).get("bbox", {})
    if element_bbox:
        for cell_id, rect in bboxes.items():
            if overlaps_region(rect, element_bbox) or cell_id.startswith(ELEMENT_LIST_CELL_PREFIX):
                keep_ids.add(cell_id)

    old_cells = {cell.get("id", ""): cell for cell in old_root if cell.get("id")}
    parent_by_id = {cell_id: cell.get("parent") for cell_id, cell in old_cells.items()}
    for cell_id in list(keep_ids):
        parent = parent_by_id.get(cell_id)
        while parent:
            keep_ids.add(parent)
            parent = parent_by_id.get(parent)

    new_root = ET.Element("root")
    for cell in old_root:
        cell_id = cell.get("id", "")
        if cell_id in keep_ids:
            new_root.append(copy.deepcopy(cell))

    graph_model = tree.find(".//mxGraphModel")
    if graph_model is None:
        raise ValueError("draw.io XML has no <mxGraphModel> container")
    graph_model.remove(old_root)
    graph_model.append(new_root)
    return new_root


def add_background(root_cell: ET.Element, x: float, y: float, width: float, height: float) -> None:
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": "kicad.schematic.background",
            "value": "",
            "style": "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=none;",
            "vertex": "1",
            "parent": "1",
            "data-role": "kicad_schematic_background",
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


def add_svg_image(root_cell: ET.Element, svg: str, x: float, y: float, width: float, height: float) -> None:
    encoded = urllib.parse.quote(svg, safe="")
    style = (
        "shape=image;verticalLabelPosition=bottom;verticalAlign=top;imageAspect=1;"
        "aspect=fixed;image=data:image/svg+xml,"
        f"{encoded};"
    )
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": "kicad.schematic.embed",
            "value": "",
            "style": style,
            "vertex": "1",
            "parent": "1",
            "data-role": "kicad_schematic_embed",
            "data-source": "hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg",
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


def assert_locked_template_text_unchanged(tree: ET.ElementTree) -> None:
    xml_text = ET.tostring(tree.getroot(), encoding="unicode")
    required = [
        "Position number",
        "Name",
        "Note",
        "BSTU.241297.006",
        "Microcontroller-based I/O Device",
    ]
    missing = [value for value in required if value not in html.unescape(xml_text)]
    if "Qty" not in html.unescape(xml_text) and "Number" not in html.unescape(xml_text):
        missing.append("Qty or Number")
    if missing:
        raise ValueError(f"Frame/list/title template text missing after embed: {', '.join(missing)}")


def main() -> int:
    args = parse_args()
    svg = read_svg_for_drawio(args.kicad_svg)
    tree = parse_drawio(args.frame)
    root_cell = root_with_locked_regions_only(tree)
    remove_previous_generated_cells(root_cell)
    add_background(root_cell, args.x, args.y, args.width, args.height)
    add_svg_image(root_cell, svg, args.x, args.y, args.width, args.height)
    assert_locked_template_text_unchanged(tree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Embedded KiCad schematic SVG into {args.output}")
    print(f"Placement: x={args.x:.2f}, y={args.y:.2f}, width={args.width:.2f}, height={args.height:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
