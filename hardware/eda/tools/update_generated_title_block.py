#!/usr/bin/env python3
"""Replace generated draw.io title-block text with the ESP32 schematic title data."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"

TITLE_BLOCK_TEXT_BY_ID = {
    "pFFQBGnBG81xobuCz_b_-18": "Name",
    "pFFQBGnBG81xobuCz_b_-19": "Sign",
    "pFFQBGnBG81xobuCz_b_-20": "Date",
    "pFFQBGnBG81xobuCz_b_-21": "Executed",
    "pFFQBGnBG81xobuCz_b_-22": "Checked",
    "pFFQBGnBG81xobuCz_b_-23": "",
    "pFFQBGnBG81xobuCz_b_-24": "Wang Gen",
    "pFFQBGnBG81xobuCz_b_-25": "BSTU.241297.006 Э3",
    "pFFQBGnBG81xobuCz_b_-36": "ESP32 Temperature\nControl Unit",
    "pFFQBGnBG81xobuCz_b_-37": "Sheet 1\nA1",
    "pFFQBGnBG81xobuCz_b_-38": "Sheets 1\nN/A",
    "pFFQBGnBG81xobuCz_b_-39": "Electrical Schematic Diagram\nBrest State Technical University",
}

REQUIRED_EXISTING_TITLE_CELLS = set(TITLE_BLOCK_TEXT_BY_ID)
LEGACY_TITLE_TEXT = {
    "Microcontroller-based I/O Device",
    "Department of Computer and System",
    "Разумейчик",
}
REQUIRED_TITLE_TEXT = {
    "BSTU.241297.006 Э3",
    "ESP32 Temperature Control Unit",
    "Electrical Schematic Diagram",
    "Brest State Technical University",
    "Wang Gen",
    "A1",
    "N/A",
    "Sheet",
    "Sheets",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update generated draw.io Title Block text for the ESP32 schematic.")
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
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def find_title_block_group(root_cell: ET.Element, region: dict[str, float]) -> ET.Element:
    bboxes = absolute_bbox_by_id(root_cell)
    candidates = []
    for cell in root_cell:
        cell_id = cell.get("id", "")
        rect = bboxes.get(cell_id)
        if not cell_id or not rect or not overlaps_region(rect, region):
            continue
        x, y, width, height = rect
        if width > 650 and height > 180 and "group" in cell.get("style", ""):
            candidates.append((abs(x - float(region["x"])) + abs(y - float(region["y"])), cell))
    if not candidates:
        raise ValueError("Could not locate the title-block group cell")
    return sorted(candidates, key=lambda item: item[0])[0][1]


def remove_previous_generated_title_cells(root_cell: ET.Element) -> None:
    for cell in list(root_cell):
        if cell.get("id", "").startswith("title_block.generated."):
            root_cell.remove(cell)


def update_existing_title_cells(root_cell: ET.Element) -> None:
    cells = {cell.get("id", ""): cell for cell in root_cell if cell.get("id")}
    missing = sorted(REQUIRED_EXISTING_TITLE_CELLS - set(cells))
    if missing:
        raise ValueError(f"Could not uniquely locate required title-block text cells: {', '.join(missing)}")
    for cell_id, value in TITLE_BLOCK_TEXT_BY_ID.items():
        cell = cells[cell_id]
        escaped = html.escape(value).replace("\n", "<br>")
        original_value = cell.get("value", "")
        font_size_match = re.search(r"font-size:\s*([0-9.]+)px", original_value, flags=re.I)
        if not value:
            cell.set("value", "")
        elif font_size_match:
            tag = "span" if re.search(r"<span\b", original_value, flags=re.I) else "font"
            cell.set("value", f'<{tag} style="font-size: {font_size_match.group(1)}px;">{escaped}</{tag}>')
        else:
            cell.set("value", escaped)


def visible_title_text(root_cell: ET.Element, region: dict[str, float]) -> str:
    bboxes = absolute_bbox_by_id(root_cell)
    values: list[str] = []
    for cell in root_cell:
        rect = bboxes.get(cell.get("id", ""))
        if not rect or not overlaps_region(rect, region):
            continue
        value = plain_text(cell.get("value", ""))
        if value:
            values.append(value)
    return " ".join(values)


def validate_title_text(root_cell: ET.Element, region: dict[str, float]) -> None:
    text = visible_title_text(root_cell, region)
    missing = sorted(value for value in REQUIRED_TITLE_TEXT if value not in text)
    if missing:
        raise ValueError(f"Updated title block is missing required text: {', '.join(missing)}")
    stale = sorted(value for value in LEGACY_TITLE_TEXT if value in text)
    if stale:
        raise ValueError(f"Updated title block still contains legacy text: {', '.join(stale)}")
    cyrillic_outside_code = text.replace("Э3", "")
    if re.search(r"[\u0400-\u04FF]", cyrillic_outside_code):
        raise ValueError("Updated title block contains Cyrillic text outside the allowed Э3 document-type code")


def update_title_block(tree: ET.ElementTree) -> None:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    region = lock["regions"]["title_block"]["bbox"]
    root_cell = find_root_cell(tree)
    find_title_block_group(root_cell, region)
    remove_previous_generated_title_cells(root_cell)
    update_existing_title_cells(root_cell)
    validate_title_text(root_cell, region)


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
    update_title_block(tree)
    write_tree(tree, args.output)
    print(f"Updated generated Title Block in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
