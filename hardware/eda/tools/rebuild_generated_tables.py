#!/usr/bin/env python3
"""Rebuild and validate generated BSTU table geometry in draw.io output."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES = ROOT / "hardware/eda/table_geometry_rules.yaml"
DEFAULT_REPORT = ROOT / "docs/bstu_table_geometry_report.md"
DEFAULT_JSON_REPORT = ROOT / "build/reports/bstu_table_geometry.json"
LEGACY_ELEMENT_LIST_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"


@dataclass
class TableFinding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild generated List of Elements and Title Block geometry.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def load_rules(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_drawio(path: Path) -> ET.ElementTree:
    if not path.exists():
        raise FileNotFoundError(path)
    return ET.parse(path)


def find_root_cell(tree: ET.ElementTree) -> ET.Element:
    root_cell = tree.find(".//root")
    if root_cell is None:
        raise ValueError("draw.io XML has no <root> cell container")
    return root_cell


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def normalize_style_width(width: float) -> str:
    return fmt(width)


def text_value(value: str, font_size: int, *, bold: bool = False) -> str:
    escaped = html.escape(value).replace("\n", "<br>")
    if bold:
        escaped = f"<b>{escaped}</b>"
    return f'<font style="font-size: {font_size}px;">{escaped}</font>'


def plain_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def bbox_by_id(root_cell: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    cells = {cell.get("id", ""): cell for cell in root_cell if cell.get("id")}
    memo: dict[str, tuple[float, float, float, float]] = {}

    def bbox(cell_id: str) -> tuple[float, float, float, float]:
        if cell_id in memo:
            return memo[cell_id]
        cell = cells.get(cell_id)
        if cell is None:
            memo[cell_id] = (0.0, 0.0, 0.0, 0.0)
            return memo[cell_id]
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


def local_origin(root_cell: ET.Element, parent_id: str) -> tuple[float, float]:
    bboxes = bbox_by_id(root_cell)
    x, y, _, _ = bboxes.get(parent_id, (0.0, 0.0, 0.0, 0.0))
    return x, y


def overlaps(rect: tuple[float, float, float, float], region: dict[str, float], tolerance: float = 1.0) -> bool:
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return False
    return not (
        x + width < float(region["x"]) - tolerance
        or x > float(region["right"]) + tolerance
        or y + height < float(region["y"]) - tolerance
        or y > float(region["bottom"]) + tolerance
    )


def remove_generated_table_cells(root_cell: ET.Element, rules: dict[str, Any]) -> None:
    bboxes = bbox_by_id(root_cell)
    element_region = rules["element_list"]["locked_region_bbox"]
    title_group = rules["title_block"]["group_id"]
    for cell in list(root_cell):
        cell_id = cell.get("id", "")
        role = cell.get("data-role", "")
        rect = bboxes.get(cell_id, (0.0, 0.0, 0.0, 0.0))
        if cell_id.startswith(("bstu.element_list.", "bstu.title_block.")):
            root_cell.remove(cell)
            continue
        if cell_id.startswith(LEGACY_ELEMENT_LIST_PREFIX) and overlaps(rect, element_region):
            root_cell.remove(cell)
            continue
        if cell.get("parent") == title_group:
            root_cell.remove(cell)
            continue
        if role.startswith(("generated_element_list_", "generated_title_block")):
            root_cell.remove(cell)


def add_rect(
    root_cell: ET.Element,
    *,
    cell_id: str,
    parent: str,
    x: float,
    y: float,
    width: float,
    height: float,
    stroke_width: float,
    role: str,
) -> ET.Element:
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": cell_id,
            "value": "",
            "style": (
                "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;"
                f"strokeWidth={normalize_style_width(stroke_width)};"
            ),
            "vertex": "1",
            "parent": parent,
            "data-role": role,
            "data-stroke-width": normalize_style_width(stroke_width),
        },
    )
    ET.SubElement(cell, "mxGeometry", {"x": fmt(x), "y": fmt(y), "width": fmt(width), "height": fmt(height), "as": "geometry"})
    return cell


def add_line(
    root_cell: ET.Element,
    *,
    cell_id: str,
    parent: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke_width: float,
    role: str,
) -> ET.Element:
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": cell_id,
            "value": "",
            "style": f"endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth={normalize_style_width(stroke_width)};",
            "edge": "1",
            "parent": parent,
            "data-role": role,
            "data-stroke-width": normalize_style_width(stroke_width),
        },
    )
    geom = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    ET.SubElement(geom, "mxPoint", {"x": fmt(x1), "y": fmt(y1), "as": "sourcePoint"})
    ET.SubElement(geom, "mxPoint", {"x": fmt(x2), "y": fmt(y2), "as": "targetPoint"})
    return cell


def add_text(
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
) -> ET.Element:
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": cell_id,
            "value": text_value(value, font_size, bold=bold),
            "style": (
                "text;html=1;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;"
                f"fontFamily=Helvetica;fontSize={font_size};fontColor=#000000;labelBackgroundColor=none;spacing=2;"
            ),
            "vertex": "1",
            "parent": parent,
            "data-role": role,
            "data-font-size": str(font_size),
        },
    )
    ET.SubElement(cell, "mxGeometry", {"x": fmt(x), "y": fmt(y), "width": fmt(width), "height": fmt(height), "as": "geometry"})
    return cell


def column_edges(columns: list[dict[str, Any]]) -> list[float]:
    edges = [0.0]
    total = 0.0
    for column in columns:
        total += float(column["width"])
        edges.append(total)
    return edges


def rebuild_element_list(root_cell: ET.Element, rules: dict[str, Any]) -> None:
    cfg = rules["element_list"]
    parent = cfg["parent_id"]
    parent_x, parent_y = local_origin(root_cell, parent)
    bbox = cfg["table_bbox"]
    x = float(bbox["x"]) - parent_x
    y = float(bbox["y"]) - parent_y
    width = float(bbox["width"])
    height = float(bbox["height"])
    columns = cfg["columns"]
    edges = column_edges(columns)
    line_widths = cfg["line_widths"]

    add_rect(
        root_cell,
        cell_id="bstu.element_list.outer",
        parent=parent,
        x=x,
        y=y,
        width=width,
        height=height,
        stroke_width=float(line_widths["outer"]),
        role="element_list.outer_border",
    )
    for index, edge_x in enumerate(edges[1:-1], start=1):
        add_line(
            root_cell,
            cell_id=f"bstu.element_list.line.v.{index:03d}",
            parent=parent,
            x1=x + edge_x,
            y1=y,
            x2=x + edge_x,
            y2=y + height,
            stroke_width=float(line_widths["vertical"]),
            role="element_list.vertical_line",
        )
    header_h = float(cfg["header_height"])
    add_line(
        root_cell,
        cell_id="bstu.element_list.line.h.header",
        parent=parent,
        x1=x,
        y1=y + header_h,
        x2=x + width,
        y2=y + header_h,
        stroke_width=float(line_widths["header"]),
        role="element_list.header_line",
    )
    row_h = float(cfg["row_height"])
    for row_index in range(1, len(cfg["rows"])):
        line_y = y + header_h + row_h * row_index
        add_line(
            root_cell,
            cell_id=f"bstu.element_list.line.h.{row_index:03d}",
            parent=parent,
            x1=x,
            y1=line_y,
            x2=x + width,
            y2=line_y,
            stroke_width=float(line_widths["horizontal"]),
            role="element_list.horizontal_line",
        )

    font_sizes = cfg["font_sizes"]
    for col_index, column in enumerate(columns):
        add_text(
            root_cell,
            cell_id=f"bstu.element_list.text.header.{column['id']}",
            parent=parent,
            value=column["title"],
            x=x + edges[col_index],
            y=y,
            width=float(column["width"]),
            height=header_h,
            font_size=int(font_sizes["header"]),
            role="element_list.header_text",
            bold=True,
        )

    for row_index, row in enumerate(cfg["rows"], start=1):
        row_y = y + header_h + (row_index - 1) * row_h
        if row["kind"] == "group":
            add_text(
                root_cell,
                cell_id=f"bstu.element_list.text.group.{row_index:02d}",
                parent=parent,
                value=row["name"],
                x=x,
                y=row_y,
                width=width,
                height=row_h,
                font_size=int(font_sizes["group"]),
                role="element_list.group_text",
                bold=True,
            )
            continue
        values = {"ref": row["ref"], "name": row["name"], "qty": row["qty"], "note": row["note"]}
        for col_index, column in enumerate(columns):
            col_id = column["id"]
            add_text(
                root_cell,
                cell_id=f"bstu.element_list.text.row.{row_index:02d}.{col_id}",
                parent=parent,
                value=values[col_id],
                x=x + edges[col_index],
                y=row_y,
                width=float(column["width"]),
                height=row_h,
                font_size=int(font_sizes["body"]),
                role="element_list.body_text",
            )


def mm_to_page(title_cfg: dict[str, Any], x_mm: float, y_mm: float, width_mm: float, height_mm: float) -> tuple[float, float, float, float]:
    bbox = title_cfg["bbox"]
    overall = title_cfg["overall_mm"]
    sx = float(bbox["width"]) / float(overall["width"])
    sy = float(bbox["height"]) / float(overall["height"])
    return x_mm * sx, y_mm * sy, width_mm * sx, height_mm * sy


def rebuild_title_block(root_cell: ET.Element, rules: dict[str, Any]) -> None:
    cfg = rules["title_block"]
    parent = cfg["group_id"]
    bbox = cfg["bbox"]
    width = float(bbox["width"])
    height = float(bbox["height"])
    overall = cfg["overall_mm"]
    sx = width / float(overall["width"])
    sy = height / float(overall["height"])
    line_widths = cfg["line_widths"]

    add_rect(
        root_cell,
        cell_id="bstu.title_block.outer",
        parent=parent,
        x=0.0,
        y=0.0,
        width=width,
        height=height,
        stroke_width=float(line_widths["outer"]),
        role="title_block.outer_border",
    )
    for index, grid_x in enumerate(cfg["vertical_grid_mm"][1:-1], start=1):
        line_x = float(grid_x) * sx
        role = "title_block.major_line" if grid_x in (65.0, 135.0) else "title_block.minor_line"
        stroke = line_widths["major"] if role.endswith("major_line") else line_widths["minor"]
        add_line(
            root_cell,
            cell_id=f"bstu.title_block.line.v.{index:03d}",
            parent=parent,
            x1=line_x,
            y1=0.0,
            x2=line_x,
            y2=height,
            stroke_width=float(stroke),
            role=role,
        )
    for index, grid_y in enumerate(cfg["horizontal_grid_mm"][1:-1], start=1):
        line_y = float(grid_y) * sy
        role = "title_block.major_line" if grid_y in (15.0, 40.0) else "title_block.minor_line"
        stroke = line_widths["major"] if role.endswith("major_line") else line_widths["minor"]
        if grid_y == 15.0:
            x1_mm, x2_mm = 0.0, 185.0
        elif grid_y == 40.0:
            x1_mm, x2_mm = 0.0, 135.0
        else:
            # Signature rows are 5 mm high only in the left block. The center
            # document-code/name cells and right information block have their
            # own larger cells, so these row lines must not cut through text.
            x1_mm, x2_mm = 0.0, 65.0
        add_line(
            root_cell,
            cell_id=f"bstu.title_block.line.h.{index:03d}",
            parent=parent,
            x1=x1_mm * sx,
            y1=line_y,
            x2=x2_mm * sx,
            y2=line_y,
            stroke_width=float(stroke),
            role=role,
        )

    # Right-block sub-grid lines not represented by the main 7/10/23/15/10/70/50 chain.
    for index, x_mm in enumerate((151.67, 168.34), start=1):
        line_x = float(x_mm) * sx
        add_line(
            root_cell,
            cell_id=f"bstu.title_block.line.v.right.{index:03d}",
            parent=parent,
            x1=line_x,
            y1=0.0,
            x2=line_x,
            y2=15.0 * sy,
            stroke_width=float(line_widths["minor"]),
            role="title_block.minor_line",
        )
    line_x = 160.0 * sx
    add_line(
        root_cell,
        cell_id="bstu.title_block.line.v.sheet",
        parent=parent,
        x1=line_x,
        y1=15.0 * sy,
        x2=line_x,
        y2=25.0 * sy,
        stroke_width=float(line_widths["minor"]),
        role="title_block.minor_line",
    )
    for y_mm in (25.0, 45.0):
        add_line(
            root_cell,
            cell_id=f"bstu.title_block.line.h.right.{int(y_mm):03d}",
            parent=parent,
            x1=135.0 * sx,
            y1=y_mm * sy,
            x2=185.0 * sx,
            y2=y_mm * sy,
            stroke_width=float(line_widths["minor"]),
            role="title_block.minor_line",
        )

    font_sizes = cfg["font_sizes"]
    for cell_cfg in cfg["cells"]:
        x, y, cell_w, cell_h = mm_to_page(
            cfg,
            float(cell_cfg["x_mm"]),
            float(cell_cfg["y_mm"]),
            float(cell_cfg["width_mm"]),
            float(cell_cfg["height_mm"]),
        )
        add_text(
            root_cell,
            cell_id=f"bstu.title_block.text.{cell_cfg['id']}",
            parent=parent,
            value=cell_cfg["text"],
            x=x,
            y=y,
            width=cell_w,
            height=cell_h,
            font_size=int(font_sizes[cell_cfg["font_key"]]),
            role="title_block.text",
            bold=bool(cell_cfg.get("bold", False)),
        )


def rebuild_tables(tree: ET.ElementTree, rules: dict[str, Any]) -> None:
    root_cell = find_root_cell(tree)
    remove_generated_table_cells(root_cell, rules)
    rebuild_element_list(root_cell, rules)
    rebuild_title_block(root_cell, rules)


def edge_points(cell: ET.Element) -> tuple[float, float, float, float] | None:
    geom = cell.find("mxGeometry")
    if geom is None:
        return None
    source = geom.find("mxPoint[@as='sourcePoint']")
    target = geom.find("mxPoint[@as='targetPoint']")
    if source is None or target is None:
        return None
    return (
        float(source.get("x", "0") or 0),
        float(source.get("y", "0") or 0),
        float(target.get("x", "0") or 0),
        float(target.get("y", "0") or 0),
    )


def geometry(cell: ET.Element) -> tuple[float, float, float, float]:
    geom = cell.find("mxGeometry")
    if geom is None:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(float(geom.get(key, "0") or 0) for key in ("x", "y", "width", "height"))


def stroke_width(cell: ET.Element) -> float:
    if cell.get("data-stroke-width"):
        return float(cell.get("data-stroke-width", "0"))
    match = re.search(r"strokeWidth=([0-9.]+)", cell.get("style", ""))
    return float(match.group(1)) if match else 0.0


def add_finding(findings: list[TableFinding], code: str, object_id: str, message: str, expected: str = "", actual: str = "") -> None:
    findings.append(TableFinding(code=code, severity="error", object_id=object_id, message=message, expected=expected, actual=actual))


def approx(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance


def cell_by_id(root_cell: ET.Element) -> dict[str, ET.Element]:
    return {cell.get("id", ""): cell for cell in root_cell if cell.get("id")}


def validate_element_list(root_cell: ET.Element, rules: dict[str, Any], findings: list[TableFinding], summary: dict[str, Any]) -> None:
    cfg = rules["element_list"]
    cells = cell_by_id(root_cell)
    parent_x, parent_y = local_origin(root_cell, cfg["parent_id"])
    tolerance = float(rules["geometry_tolerance"])
    bbox = cfg["table_bbox"]
    outer = cells.get("bstu.element_list.outer")
    if outer is None:
        add_finding(findings, "ELEMENT_LIST_MISSING", "bstu.element_list.outer", "Generated List of Elements outer border is missing")
        return
    x, y, width, height = geometry(outer)
    actual_abs = {"x": x + parent_x, "y": y + parent_y, "width": width, "height": height, "right": x + parent_x + width, "bottom": y + parent_y + height}
    summary["element_list"] = {"actual_bbox": actual_abs, "expected_bbox": bbox}
    for key in ("x", "y", "width", "height", "right", "bottom"):
        if not approx(float(actual_abs[key]), float(bbox[key]), tolerance):
            add_finding(findings, "ELEMENT_LIST_WIDTH_INVALID", "bstu.element_list.outer", f"Element List {key} does not match rules", str(bbox[key]), fmt(actual_abs[key]))
    if not approx(stroke_width(outer), float(cfg["line_widths"]["outer"]), float(rules["line_width_tolerance"])):
        add_finding(findings, "ELEMENT_LIST_LINE_WIDTH_INVALID", "bstu.element_list.outer", "Element List outer border line width is invalid", str(cfg["line_widths"]["outer"]), fmt(stroke_width(outer)))
    expected_edges = column_edges(cfg["columns"])
    measured_columns = [float(col["width"]) for col in cfg["columns"]]
    summary["element_list"]["column_widths"] = measured_columns
    if measured_columns != [150.0, 340.0, 68.0, 172.0]:
        add_finding(findings, "ELEMENT_LIST_COLUMN_WIDTH_INVALID", "hardware/eda/table_geometry_rules.yaml", "Element List column width chain changed", "150/340/68/172", "/".join(fmt(v) for v in measured_columns))
    for index, edge_x in enumerate(expected_edges[1:-1], start=1):
        line = cells.get(f"bstu.element_list.line.v.{index:03d}")
        if line is None:
            add_finding(findings, "ELEMENT_LIST_LINE_MISSING", f"bstu.element_list.line.v.{index:03d}", "Element List vertical line is missing")
            continue
        points = edge_points(line)
        if points is None:
            add_finding(findings, "ELEMENT_LIST_LINE_INVALID", line.get("id", ""), "Element List vertical line has no source/target points")
            continue
        x1, y1, x2, y2 = points
        if not (approx(x1, x2, tolerance) and approx(x1, x + edge_x, tolerance)):
            add_finding(findings, "ELEMENT_LIST_COLUMN_WIDTH_INVALID", line.get("id", ""), "Element List vertical grid position is invalid", fmt(x + edge_x), f"{fmt(x1)}->{fmt(x2)}")
        if not approx(stroke_width(line), float(cfg["line_widths"]["vertical"]), float(rules["line_width_tolerance"])):
            add_finding(findings, "ELEMENT_LIST_LINE_WIDTH_INCONSISTENT", line.get("id", ""), "Element List vertical line width is invalid", str(cfg["line_widths"]["vertical"]), fmt(stroke_width(line)))
        if not (approx(y1, y, tolerance) and approx(y2, y + height, tolerance)):
            add_finding(findings, "ELEMENT_LIST_LINE_NOT_ORTHOGONAL", line.get("id", ""), "Element List vertical line does not span table height cleanly")
    expected_line_count = 1 + len(cfg["rows"]) - 1
    actual_h_lines = [cell for cell in cells.values() if cell.get("data-role") in {"element_list.header_line", "element_list.horizontal_line"}]
    summary["element_list"]["horizontal_line_count"] = len(actual_h_lines)
    if len(actual_h_lines) != expected_line_count:
        add_finding(findings, "ELEMENT_LIST_ROW_HEIGHT_INVALID", "bstu.element_list", "Element List horizontal line count is invalid", str(expected_line_count), str(len(actual_h_lines)))
    min_font = min((int(cell.get("data-font-size", "999")) for cell in cells.values() if cell.get("data-role", "").startswith("element_list.")), default=0)
    summary["element_list"]["min_font_size"] = min_font
    if min_font < 14:
        add_finding(findings, "ELEMENT_LIST_FONT_TOO_SMALL", "bstu.element_list", "Element List text font size is too small", ">= 14", str(min_font))
    visible = " ".join(plain_text(cell.get("value", "")) for cell in cells.values() if cell.get("data-role", "").startswith("element_list."))
    for required in [*cfg["headers"], *(row.get("name", "") for row in cfg["rows"]), *(row.get("ref", "") for row in cfg["rows"] if row["kind"] == "item")]:
        if required and required not in visible:
            add_finding(findings, "ELEMENT_LIST_REQUIRED_TEXT_MISSING", "bstu.element_list", "Element List required text is missing", required, "not found")
    if "Number" in visible:
        add_finding(findings, "ELEMENT_LIST_STALE_HEADER", "bstu.element_list", "Element List still contains stale Number header", "Qty", "Number")


def validate_title_block(root_cell: ET.Element, rules: dict[str, Any], findings: list[TableFinding], summary: dict[str, Any]) -> None:
    cfg = rules["title_block"]
    cells = cell_by_id(root_cell)
    tolerance = float(rules["geometry_tolerance"])
    outer = cells.get("bstu.title_block.outer")
    if outer is None:
        add_finding(findings, "TITLE_BLOCK_MISSING", "bstu.title_block.outer", "Generated Title Block outer border is missing")
        return
    x, y, width, height = geometry(outer)
    bbox = cfg["bbox"]
    actual_abs = {"x": float(bbox["x"]) + x, "y": float(bbox["y"]) + y, "width": width, "height": height, "right": float(bbox["x"]) + x + width, "bottom": float(bbox["y"]) + y + height}
    summary["title_block"] = {"actual_bbox": actual_abs, "expected_bbox": bbox, "cells": []}
    for key in ("width", "height"):
        if not approx(float(actual_abs[key]), float(bbox[key]), tolerance):
            add_finding(findings, "TITLE_BLOCK_TEMPLATE_MISMATCH", "bstu.title_block.outer", f"Title Block {key} does not match rules", str(bbox[key]), fmt(actual_abs[key]))
    if not approx(stroke_width(outer), float(cfg["line_widths"]["outer"]), float(rules["line_width_tolerance"])):
        add_finding(findings, "TITLE_BLOCK_LINE_WIDTH_INVALID", "bstu.title_block.outer", "Title Block outer line width is invalid", str(cfg["line_widths"]["outer"]), fmt(stroke_width(outer)))
    overall = cfg["overall_mm"]
    sx = float(bbox["width"]) / float(overall["width"])
    sy = float(bbox["height"]) / float(overall["height"])
    for index, grid_x in enumerate(cfg["vertical_grid_mm"][1:-1], start=1):
        line = cells.get(f"bstu.title_block.line.v.{index:03d}")
        if line is None:
            add_finding(findings, "TITLE_BLOCK_GRID_X_MISMATCH", f"bstu.title_block.line.v.{index:03d}", "Title Block vertical grid line is missing")
            continue
        points = edge_points(line)
        if points is None:
            add_finding(findings, "TITLE_BLOCK_GRID_X_MISMATCH", line.get("id", ""), "Title Block vertical grid line has no source/target points")
            continue
        expected = float(grid_x) * sx
        if not (approx(points[0], points[2], tolerance) and approx(points[0], expected, tolerance)):
            add_finding(findings, "TITLE_BLOCK_GRID_X_MISMATCH", line.get("id", ""), "Title Block vertical grid x coordinate is invalid", fmt(expected), f"{fmt(points[0])}->{fmt(points[2])}")
    for index, grid_y in enumerate(cfg["horizontal_grid_mm"][1:-1], start=1):
        line = cells.get(f"bstu.title_block.line.h.{index:03d}")
        if line is None:
            add_finding(findings, "TITLE_BLOCK_GRID_Y_MISMATCH", f"bstu.title_block.line.h.{index:03d}", "Title Block horizontal grid line is missing")
            continue
        points = edge_points(line)
        if points is None:
            add_finding(findings, "TITLE_BLOCK_GRID_Y_MISMATCH", line.get("id", ""), "Title Block horizontal grid line has no source/target points")
            continue
        expected = float(grid_y) * sy
        if not (approx(points[1], points[3], tolerance) and approx(points[1], expected, tolerance)):
            add_finding(findings, "TITLE_BLOCK_GRID_Y_MISMATCH", line.get("id", ""), "Title Block horizontal grid y coordinate is invalid", fmt(expected), f"{fmt(points[1])}->{fmt(points[3])}")
    visible = " ".join(plain_text(cell.get("value", "")) for cell in cells.values() if cell.get("data-role", "").startswith("title_block."))
    for required in cfg["required_text"]:
        if required not in visible:
            add_finding(findings, "TITLE_BLOCK_REQUIRED_TEXT_MISSING", "bstu.title_block", "Title Block required text is missing", required, "not found")
    cyrillic = re.sub(r"Э3", "", visible)
    if re.search(r"[\u0400-\u04FF]", cyrillic):
        add_finding(findings, "TITLE_BLOCK_CYRILLIC_FORBIDDEN", "bstu.title_block", "Title Block contains Cyrillic outside allowed Э3 code")
    min_font = min((int(cell.get("data-font-size", "999")) for cell in cells.values() if cell.get("data-role") == "title_block.text"), default=0)
    summary["title_block"]["min_font_size"] = min_font
    if min_font < 8:
        add_finding(findings, "TITLE_BLOCK_FONT_TOO_SMALL", "bstu.title_block", "Title Block text font size is too small", ">= 8 px", str(min_font))
    for cell_cfg in cfg["cells"]:
        expected_x = float(cell_cfg["x_mm"]) * sx
        expected_y = float(cell_cfg["y_mm"]) * sy
        expected_w = float(cell_cfg["width_mm"]) * sx
        expected_h = float(cell_cfg["height_mm"]) * sy
        text_cell = cells.get(f"bstu.title_block.text.{cell_cfg['id']}")
        if text_cell is None:
            add_finding(findings, "TITLE_BLOCK_REQUIRED_TEXT_MISSING", f"bstu.title_block.text.{cell_cfg['id']}", "Title Block cell text object is missing")
            continue
        actual_x, actual_y, actual_w, actual_h = geometry(text_cell)
        summary["title_block"]["cells"].append(
            {
                "id": cell_cfg["id"],
                "expected": {"x": expected_x, "y": expected_y, "width": expected_w, "height": expected_h},
                "actual": {"x": actual_x, "y": actual_y, "width": actual_w, "height": actual_h},
                "delta": {
                    "x": actual_x - expected_x,
                    "y": actual_y - expected_y,
                    "width": actual_w - expected_w,
                    "height": actual_h - expected_h,
                },
            }
        )
        if not (approx(actual_x, expected_x, tolerance) and approx(actual_y, expected_y, tolerance) and approx(actual_w, expected_w, tolerance) and approx(actual_h, expected_h, tolerance)):
            add_finding(findings, "TITLE_BLOCK_CELL_SIZE_INVALID", text_cell.get("id", ""), "Title Block text cell geometry differs from template", f"x={fmt(expected_x)} y={fmt(expected_y)} w={fmt(expected_w)} h={fmt(expected_h)}", f"x={fmt(actual_x)} y={fmt(actual_y)} w={fmt(actual_w)} h={fmt(actual_h)}")


def validate_tables(tree: ET.ElementTree, rules: dict[str, Any]) -> tuple[list[TableFinding], dict[str, Any]]:
    root_cell = find_root_cell(tree)
    findings: list[TableFinding] = []
    summary: dict[str, Any] = {"status": "PASS"}
    validate_element_list(root_cell, rules, findings, summary)
    validate_title_block(root_cell, rules, findings, summary)
    if findings:
        summary["status"] = "FAILED"
    summary["error_count"] = len(findings)
    return findings, summary


def write_tree(tree: ET.ElementTree, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    tmp.replace(output)


def write_reports(findings: list[TableFinding], summary: dict[str, Any], md_report: Path, json_report: Path) -> None:
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(json.dumps({"summary": summary, "findings": [asdict(f) for f in findings]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BSTU Table Geometry Report",
        "",
        f"- Status: **{summary['status']}**",
        f"- Errors: {len(findings)}",
        "- Scope: generated/final draw.io table geometry only; KiCad electrical topology is unchanged.",
        "",
        "## Element List",
    ]
    element = summary.get("element_list", {})
    if element:
        lines.extend(
            [
                f"- Expected bbox: `{element.get('expected_bbox')}`",
                f"- Actual bbox: `{element.get('actual_bbox')}`",
                f"- Column widths: `{element.get('column_widths')}`",
                f"- Horizontal line count: `{element.get('horizontal_line_count')}`",
                f"- Minimum font size: `{element.get('min_font_size')}` px",
                "",
            ]
        )
    lines.append("## Title Block")
    title = summary.get("title_block", {})
    if title:
        lines.extend(
            [
                f"- Expected bbox: `{title.get('expected_bbox')}`",
                f"- Actual bbox: `{title.get('actual_bbox')}`",
                f"- Minimum font size: `{title.get('min_font_size')}` px",
                "",
                "### Cell Geometry",
            ]
        )
        for cell in title.get("cells", []):
            delta = cell["delta"]
            lines.append(
                f"- `{cell['id']}` delta x={delta['x']:.3f}, y={delta['y']:.3f}, "
                f"w={delta['width']:.3f}, h={delta['height']:.3f}"
            )
    if findings:
        lines.extend(["", "## Findings"])
        for finding in findings:
            lines.append(f"- **{finding.code}** `{finding.object_id}`: {finding.message}")
    else:
        lines.extend(["", "No table geometry lint errors."])
    md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    rules = load_rules(args.rules)
    tree = parse_drawio(args.input)
    if not args.validate_only:
        rebuild_tables(tree, rules)
        write_tree(tree, args.output)
        tree = parse_drawio(args.output)
    findings, summary = validate_tables(tree, rules)
    write_reports(findings, summary, args.report, args.json_report)
    if findings:
        for finding in findings:
            print(f"{finding.code}: {finding.object_id}: {finding.message}")
        return 1
    print(f"BSTU table geometry PASS for {args.output if not args.validate_only else args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
