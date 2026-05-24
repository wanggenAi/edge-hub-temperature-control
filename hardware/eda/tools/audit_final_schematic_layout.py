#!/usr/bin/env python3
"""Automated final schematic layout/aesthetic audit.

This script is deliberately read-only for drawing artifacts. It parses the
KiCad schematic geometry, consumes existing ERC/topology/export/table-lock
reports, and cuts evidence crops from the already exported final PNG.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KICAD = ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch"
DEFAULT_KICAD_SVG = ROOT / "hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg"
DEFAULT_FINAL_SVG = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.svg"
DEFAULT_FINAL_PNG = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.png"
DEFAULT_FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"
DEFAULT_REVIEW_MANIFEST = ROOT / "hardware/eda/exports/final/review_crops/manifest.json"
DEFAULT_ERC_REPORT = ROOT / "build/reports/kicad_schematic_erc_master_table_lock.json"
DEFAULT_EQUIVALENCE_REPORT = ROOT / "build/reports/jlc_kicad_netlist_equivalence.json"
DEFAULT_TABLE_LOCK_REPORT = ROOT / "build/reports/bstu_master_table_lock.json"
DEFAULT_EXPORT_LINT_REPORT = ROOT / "build/reports/final-master-table-lock-export/export_artifact_lint.json"
DEFAULT_JSON_REPORT = ROOT / "build/reports/final_schematic_layout_audit.json"
DEFAULT_MD_REPORT = ROOT / "docs/final_schematic_layout_audit_report.md"
DEFAULT_CROPS_DIR = ROOT / "hardware/eda/exports/final/layout_audit_crops"

CANONICAL_BLOCKS: dict[str, dict[str, Any]] = {
    "DD1 ESP32 core block": {"refs": ["DD1"], "nets": ["+3V3", "GND", "EN", "LED", "BOOT", "GATE", "DQ", "RXD0", "TXD0"]},
    "RESET/EN block": {"refs": ["R1", "SB1"], "nets": ["+3V3", "EN", "GND"]},
    "BOOT block": {"refs": ["R6", "SB2"], "nets": ["+3V3", "BOOT", "GND"]},
    "LED block": {"refs": ["R3", "HL1"], "nets": ["+3V3", "LED_A", "LED"]},
    "DS18B20 sensor block": {"refs": ["R2", "XS1"], "nets": ["DQ", "+3V3", "GND"]},
    "UART/service block": {"refs": ["XS4"], "nets": ["RXD0", "TXD0", "+3V3", "GND"]},
    "heater driver block": {"refs": ["R4", "R5", "VT1", "XS2", "XS5"], "nets": ["GATE", "GATE_R", "HEAT+", "HEAT-", "+12V", "GND"]},
    "power block": {"refs": ["XS3", "A1", "C3", "C4"], "nets": ["+12V", "+3V3", "GND"]},
}

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

CANONICAL_NETS = ["+3V3", "+12V", "GND", "EN", "LED", "LED_A", "DQ", "RXD0", "TXD0", "BOOT", "GATE", "GATE_R", "HEAT+", "HEAT-"]
PROPERTY_TEXT_REVIEW_REFS = ["A1", "DD1", "HL1", "VT1", "XS1", "XS4"]
PROPERTY_TEXT_BODY_CLEARANCE_MM = 0.4
PROPERTY_TEXT_WIRE_CLEARANCE_MM = 0.5


Point = tuple[float, float]
BBox = tuple[float, float, float, float]


@dataclass
class Finding:
    id: str
    severity: str
    rule: str
    message: str
    refs: list[str]
    nets: list[str]
    source_file: str
    coordinates: dict[str, float]
    measured_value: Any
    threshold: Any
    explanation: str
    evidence_crop: str = ""


@dataclass
class PropertyText:
    name: str
    value: str
    at: Point
    angle: float
    font_size: Point
    hidden: bool


@dataclass
class SymbolInstance:
    ref: str
    lib_id: str
    at: Point
    angle: float
    properties: dict[str, PropertyText]
    pins: dict[str, Point]
    bbox: BBox


@dataclass
class Wire:
    uuid: str
    points: list[Point]

    @property
    def start(self) -> Point:
        return self.points[0]

    @property
    def end(self) -> Point:
        return self.points[-1]

    @property
    def length(self) -> float:
        return sum(distance(a, b) for a, b in zip(self.points, self.points[1:]))


@dataclass
class Label:
    value: str
    at: Point
    angle: float
    font_size: Point


@dataclass
class RenderedText:
    value: str
    anchor: Point
    bbox: BBox
    font_size: float
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit final schematic layout without modifying drawing artifacts.")
    parser.add_argument("--kicad-schematic", type=Path, default=DEFAULT_KICAD)
    parser.add_argument("--kicad-svg", type=Path, default=DEFAULT_KICAD_SVG)
    parser.add_argument("--final-svg", type=Path, default=DEFAULT_FINAL_SVG)
    parser.add_argument("--final-png", type=Path, default=DEFAULT_FINAL_PNG)
    parser.add_argument("--final-drawio", type=Path, default=DEFAULT_FINAL_DRAWIO)
    parser.add_argument("--review-manifest", type=Path, default=DEFAULT_REVIEW_MANIFEST)
    parser.add_argument("--erc-report", type=Path, default=DEFAULT_ERC_REPORT)
    parser.add_argument("--equivalence-report", type=Path, default=DEFAULT_EQUIVALENCE_REPORT)
    parser.add_argument("--table-lock-report", type=Path, default=DEFAULT_TABLE_LOCK_REPORT)
    parser.add_argument("--export-lint-report", type=Path, default=DEFAULT_EXPORT_LINT_REPORT)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    parser.add_argument("--crops-dir", type=Path, default=DEFAULT_CROPS_DIR)
    return parser.parse_args()


def tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                value.append(text[index])
                index += 1
            tokens.append("".join(value))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "()":
            index += 1
        tokens.append(text[start:index])
    return tokens


def parse_sexpr(text: str) -> list[Any]:
    tokens = tokenize_sexpr(text)
    index = 0

    def parse_one() -> Any:
        nonlocal index
        if tokens[index] == "(":
            index += 1
            items: list[Any] = []
            while tokens[index] != ")":
                items.append(parse_one())
            index += 1
            return items
        token = tokens[index]
        index += 1
        return token

    parsed = parse_one()
    if index != len(tokens):
        raise ValueError("Trailing tokens while parsing KiCad schematic")
    if not isinstance(parsed, list):
        raise ValueError("KiCad schematic root must be a list")
    return parsed


def lists_named(tree: Any, name: str) -> Iterable[list[Any]]:
    if isinstance(tree, list):
        if tree and tree[0] == name:
            yield tree
        for child in tree:
            yield from lists_named(child, name)


def child_named(items: list[Any], name: str) -> list[Any] | None:
    for item in items:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def as_float(value: Any) -> float:
    return float(str(value))


def parse_at(items: list[Any]) -> tuple[Point, float]:
    at = child_named(items, "at")
    if not at or len(at) < 3:
        return (0.0, 0.0), 0.0
    angle = as_float(at[3]) if len(at) > 3 else 0.0
    return (as_float(at[1]), as_float(at[2])), angle


def parse_font_size(items: list[Any]) -> Point:
    effects = child_named(items, "effects")
    font = child_named(effects or [], "font") if effects else None
    size = child_named(font or [], "size") if font else None
    if size and len(size) >= 3:
        return as_float(size[1]), as_float(size[2])
    return (0.0, 0.0)


def is_hidden_property(items: list[Any]) -> bool:
    effects = child_named(items, "effects")
    return bool(effects and any(isinstance(item, list) and item and item[0] == "hide" for item in effects))


def rotate(point: Point, degrees: float) -> Point:
    if abs(degrees) < 1e-9:
        return point
    radians = math.radians(degrees)
    return (point[0] * math.cos(radians) - point[1] * math.sin(radians), point[0] * math.sin(radians) + point[1] * math.cos(radians))


def translate(point: Point, origin: Point, degrees: float) -> Point:
    rx, ry = rotate(point, degrees)
    # KiCad library symbol coordinates use positive Y upward relative to the
    # symbol origin, while schematic sheet coordinates increase downward.
    return (origin[0] + rx, origin[1] - ry)


def parse_lib_symbol_pins(root: list[Any]) -> dict[str, dict[str, Point]]:
    lib_symbols = child_named(root, "lib_symbols")
    if not lib_symbols:
        return {}
    result: dict[str, dict[str, Point]] = {}
    for symbol in lib_symbols[1:]:
        if not isinstance(symbol, list) or len(symbol) < 2 or symbol[0] != "symbol":
            continue
        lib_id = str(symbol[1])
        pins: dict[str, Point] = {}
        for pin in lists_named(symbol, "pin"):
            at = child_named(pin, "at")
            number = child_named(pin, "number")
            if not at or len(at) < 3 or not number or len(number) < 2:
                continue
            pins[str(number[1])] = (as_float(at[1]), as_float(at[2]))
        result[lib_id] = pins
    return result


def parse_kicad(path: Path) -> tuple[list[SymbolInstance], list[Wire], list[Label], dict[str, Any]]:
    root = parse_sexpr(path.read_text(encoding="utf-8", errors="ignore"))
    lib_pins = parse_lib_symbol_pins(root)
    symbols: list[SymbolInstance] = []
    wires: list[Wire] = []
    labels: list[Label] = []
    paper = ""
    for item in root:
        if isinstance(item, list) and item and item[0] == "paper" and len(item) > 1:
            paper = str(item[1])
        if not isinstance(item, list) or not item:
            continue
        if item[0] == "symbol" and child_named(item, "lib_id"):
            lib_id = str(child_named(item, "lib_id")[1])
            origin, angle = parse_at(item)
            properties: dict[str, PropertyText] = {}
            for prop in item:
                if isinstance(prop, list) and len(prop) >= 3 and prop[0] == "property":
                    at, prop_angle = parse_at(prop)
                    properties[str(prop[1])] = PropertyText(
                        name=str(prop[1]),
                        value=str(prop[2]),
                        at=at,
                        angle=prop_angle,
                        font_size=parse_font_size(prop),
                        hidden=is_hidden_property(prop),
                    )
            ref = properties.get("Reference", PropertyText("", "", (0, 0), 0, (0, 0), False)).value
            pins = {number: translate(local, origin, angle) for number, local in lib_pins.get(lib_id, {}).items()}
            bbox = symbol_bbox(lib_id, origin)
            symbols.append(SymbolInstance(ref=ref, lib_id=lib_id, at=origin, angle=angle, properties=properties, pins=pins, bbox=bbox))
        elif item[0] == "wire":
            pts_block = child_named(item, "pts")
            points: list[Point] = []
            if pts_block:
                for xy in pts_block[1:]:
                    if isinstance(xy, list) and xy and xy[0] == "xy" and len(xy) >= 3:
                        points.append((as_float(xy[1]), as_float(xy[2])))
            uuid_block = child_named(item, "uuid")
            wires.append(Wire(uuid=str(uuid_block[1]) if uuid_block and len(uuid_block) > 1 else "", points=points))
        elif item[0] == "global_label":
            at, angle = parse_at(item)
            labels.append(Label(value=str(item[1]), at=at, angle=angle, font_size=parse_font_size(item)))
    return symbols, wires, labels, {"paper": paper}


def symbol_bbox(lib_id: str, origin: Point) -> BBox:
    # Conservative body extents in KiCad mm, matching the project-local symbol definitions.
    widths = {
        "ESP32_Temperature_Control:ESP32-WROOM-32": (-15.24, -16.51, 15.24, 16.51),
        "ESP32_Temperature_Control:DCDC_12V_3V3": (-12.70, -7.62, 12.70, 8.89),
        "ESP32_Temperature_Control:CONN_2": (-2.54, -2.54, 2.54, 2.54),
        "ESP32_Temperature_Control:CONN_3": (-2.54, -3.81, 2.54, 3.81),
        "ESP32_Temperature_Control:CONN_4": (-2.54, -5.08, 2.54, 5.08),
        "ESP32_Temperature_Control:R_H": (-2.54, -1.27, 2.54, 1.27),
        "ESP32_Temperature_Control:C_H": (-2.54, -2.54, 2.54, 2.54),
        "ESP32_Temperature_Control:SW_NO_H": (-2.54, -1.78, 2.54, 1.78),
        "ESP32_Temperature_Control:LED_H": (-2.54, -2.54, 5.08, 5.08),
        "ESP32_Temperature_Control:NMOS_GDS": (-2.54, -3.81, 2.54, 3.81),
    }
    left, top, right, bottom = widths.get(lib_id, (-3.0, -3.0, 3.0, 3.0))
    return (origin[0] + left, origin[1] - bottom, origin[0] + right, origin[1] - top)


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_key(point: Point, digits: int = 3) -> tuple[float, float]:
    return (round(point[0], digits), round(point[1], digits))


def bbox_union(boxes: Iterable[BBox]) -> BBox:
    boxes = list(boxes)
    return (min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes))


def bbox_intersects(a: BBox, b: BBox, margin: float = 0.0) -> bool:
    return a[2] > b[0] - margin and b[2] > a[0] - margin and a[3] > b[1] - margin and b[3] > a[1] - margin


def line_crosses_box(wire: Wire, box: BBox, clearance: float = 0.0) -> bool:
    bx1, by1, bx2, by2 = (box[0] - clearance, box[1] - clearance, box[2] + clearance, box[3] + clearance)
    for p1, p2 in zip(wire.points, wire.points[1:]):
        if math.isclose(p1[0], p2[0], abs_tol=1e-6):
            x = p1[0]
            if bx1 <= x <= bx2 and max(min(p1[1], p2[1]), by1) <= min(max(p1[1], p2[1]), by2):
                return True
        elif math.isclose(p1[1], p2[1], abs_tol=1e-6):
            y = p1[1]
            if by1 <= y <= by2 and max(min(p1[0], p2[0]), bx1) <= min(max(p1[0], p2[0]), bx2):
                return True
    return False


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def as_repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    return str(absolute.relative_to(ROOT))


def erc_status(report: dict[str, Any]) -> dict[str, Any]:
    violations = [violation for sheet in report.get("sheets", []) for violation in sheet.get("violations", [])]
    return {"status": "PASS" if not violations and not report.get("missing") else "FAIL", "violations": len(violations)}


def image_crop_box_from_kicad_bbox(kicad_box: BBox, kicad_overall: BBox, embed: dict[str, float], svg_viewbox: dict[str, float], image: Image.Image, margin_mm: float = 8.0) -> tuple[int, int, int, int]:
    kx1, ky1, kx2, ky2 = kicad_overall
    scale_x = embed["width"] / (kx2 - kx1)
    scale_y = embed["height"] / (ky2 - ky1)
    svg_box = {
        "x": embed["x"] + (kicad_box[0] - margin_mm - kx1) * scale_x,
        "y": embed["y"] + (kicad_box[1] - margin_mm - ky1) * scale_y,
        "width": (kicad_box[2] - kicad_box[0] + 2 * margin_mm) * scale_x,
        "height": (kicad_box[3] - kicad_box[1] + 2 * margin_mm) * scale_y,
    }
    px_per_svg_x = image.width / svg_viewbox["width"]
    px_per_svg_y = image.height / svg_viewbox["height"]
    left = round((svg_box["x"] - svg_viewbox["x"]) * px_per_svg_x)
    top = round((svg_box["y"] - svg_viewbox["y"]) * px_per_svg_y)
    right = round((svg_box["x"] + svg_box["width"] - svg_viewbox["x"]) * px_per_svg_x)
    bottom = round((svg_box["y"] + svg_box["height"] - svg_viewbox["y"]) * px_per_svg_y)
    return (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))


def image_crop_box_from_embedded_kicad_bbox(
    kicad_box: BBox,
    embedded_viewbox: dict[str, float],
    embed: dict[str, float],
    svg_viewbox: dict[str, float],
    image: Image.Image,
    margin_mm: float = 4.0,
) -> tuple[int, int, int, int]:
    view_x = embedded_viewbox["x"]
    view_y = embedded_viewbox["y"]
    view_w = embedded_viewbox["width"]
    view_h = embedded_viewbox["height"]
    svg_box = {
        "x": embed["x"] + (kicad_box[0] - margin_mm - view_x) * embed["width"] / view_w,
        "y": embed["y"] + (kicad_box[1] - margin_mm - view_y) * embed["height"] / view_h,
        "width": (kicad_box[2] - kicad_box[0] + 2 * margin_mm) * embed["width"] / view_w,
        "height": (kicad_box[3] - kicad_box[1] + 2 * margin_mm) * embed["height"] / view_h,
    }
    px_per_svg_x = image.width / svg_viewbox["width"]
    px_per_svg_y = image.height / svg_viewbox["height"]
    left = round((svg_box["x"] - svg_viewbox["x"]) * px_per_svg_x)
    top = round((svg_box["y"] - svg_viewbox["y"]) * px_per_svg_y)
    right = round((svg_box["x"] + svg_box["width"] - svg_viewbox["x"]) * px_per_svg_x)
    bottom = round((svg_box["y"] + svg_box["height"] - svg_viewbox["y"]) * px_per_svg_y)
    return (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))


def parse_svg_viewbox(svg_path: Path) -> dict[str, float]:
    root = ET.fromstring(svg_path.read_text(encoding="utf-8", errors="ignore"))
    values = [float(value) for value in root.get("viewBox", "0 0 0 0").split()]
    return {"x": values[0], "y": values[1], "width": values[2], "height": values[3]}


def parse_svg_viewbox_from_text(svg_text: str) -> dict[str, float] | None:
    match = re.search(r'\bviewBox="([^"]+)"', svg_text)
    if not match:
        return None
    values = [float(value) for value in match.group(1).split()]
    if len(values) != 4:
        return None
    return {"x": values[0], "y": values[1], "width": values[2], "height": values[3]}


def extract_embedded_svg_payloads(svg_text: str) -> list[str]:
    payloads: list[str] = []
    pattern = re.compile(r"data:image/svg\+xml(?:;base64)?,([^\"'&<> ]+)", flags=re.I)
    for match in pattern.finditer(svg_text):
        marker = match.group(0).lower()
        payload = match.group(1)
        try:
            if ";base64," in marker:
                decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
            else:
                decoded = urllib.parse.unquote(payload)
        except Exception:  # noqa: BLE001 - unusable payloads are simply ignored.
            continue
        if "<svg" in decoded:
            payloads.append(decoded)
    return payloads


def parse_rendered_texts(svg_text: str, source: str) -> list[RenderedText]:
    """Return rendered text bboxes from KiCad SVG stroked text groups.

    KiCad emits an invisible <text> node followed by a stroked path group with
    a <desc> containing the same text. The path coordinates are the best
    machine-readable approximation of the actual rendered glyph extents.
    """

    rendered: list[RenderedText] = []
    pattern = re.compile(r"<text\s+([^>]*)>(.*?)</text>\s*<g class=\"stroked-text\"><desc>(.*?)</desc>(.*?)</g>", re.S)
    for match in pattern.finditer(svg_text):
        attrs = match.group(1)
        text_value = re.sub(r"\s+", " ", match.group(2)).strip()
        desc_value = re.sub(r"\s+", " ", match.group(3)).strip()
        group = match.group(4)
        value = text_value or desc_value
        attr_map = dict(re.findall(r'\b([A-Za-z_:][-A-Za-z0-9_:.]*)="([^"]*)"', attrs))
        try:
            x = float(attr_map.get("x", "0"))
            y = float(attr_map.get("y", "0"))
            font_size = float(attr_map.get("font-size", "0"))
        except ValueError:
            continue
        points: list[Point] = []
        for path_data in re.findall(r'<path\s+d="([^"]+)"', group, re.S):
            values = [float(value) for value in re.findall(r"[-+]?\d+(?:\.\d+)?", path_data)]
            points.extend((values[index], values[index + 1]) for index in range(0, len(values) - 1, 2))
        if points:
            bbox = (min(point[0] for point in points), min(point[1] for point in points), max(point[0] for point in points), max(point[1] for point in points))
        else:
            text_length = float(attr_map.get("textLength", "0") or 0)
            anchor = attr_map.get("text-anchor", "start")
            if anchor == "middle":
                bbox = (x - text_length / 2, y - font_size, x + text_length / 2, y + 0.2 * font_size)
            elif anchor == "end":
                bbox = (x - text_length, y - font_size, x, y + 0.2 * font_size)
            else:
                bbox = (x, y - font_size, x + text_length, y + 0.2 * font_size)
        rendered.append(RenderedText(value=value, anchor=(x, y), bbox=bbox, font_size=font_size, source=source))
    return rendered


def parse_kicad_rendered_texts(kicad_svg: Path, final_svg: Path) -> list[RenderedText]:
    texts: list[RenderedText] = []
    if kicad_svg.exists():
        texts.extend(parse_rendered_texts(kicad_svg.read_text(encoding="utf-8", errors="ignore"), as_repo_path(kicad_svg)))
    if final_svg.exists():
        final_text = final_svg.read_text(encoding="utf-8", errors="ignore")
        for index, payload in enumerate(extract_embedded_svg_payloads(final_text), start=1):
            texts.extend(parse_rendered_texts(payload, f"{as_repo_path(final_svg)}#embedded-svg-{index}"))
    return texts


def parse_embedded_kicad_viewbox(final_svg: Path) -> dict[str, float] | None:
    if not final_svg.exists():
        return None
    payloads = extract_embedded_svg_payloads(final_svg.read_text(encoding="utf-8", errors="ignore"))
    for payload in payloads:
        viewbox = parse_svg_viewbox_from_text(payload)
        if viewbox:
            return viewbox
    return None


def box_clearance_to_box(text_box: BBox, symbol_box: BBox) -> tuple[float, str]:
    tx1, ty1, tx2, ty2 = text_box
    sx1, sy1, sx2, sy2 = symbol_box
    if sx1 <= tx1 and tx2 <= sx2 and sy1 <= ty1 and ty2 <= sy2:
        return min(tx1 - sx1, sx2 - tx2, ty1 - sy1, sy2 - ty2), "inside_body"
    dx = max(sx1 - tx2, tx1 - sx2, 0.0)
    dy = max(sy1 - ty2, ty1 - sy2, 0.0)
    if dx == 0.0 and dy == 0.0:
        overlap_x = min(tx2, sx2) - max(tx1, sx1)
        overlap_y = min(ty2, sy2) - max(ty1, sy1)
        return -min(overlap_x, overlap_y), "boundary_overlap"
    return math.hypot(dx, dy), "outside_body"


def segment_distance_to_box(box: BBox, start: Point, end: Point) -> float:
    x1, y1, x2, y2 = box
    sx, sy = start
    ex, ey = end
    if math.isclose(sx, ex, abs_tol=1e-9):
        x = sx
        seg_y1, seg_y2 = sorted((sy, ey))
        if x1 <= x <= x2 and max(y1, seg_y1) <= min(y2, seg_y2):
            return 0.0
        dx = 0.0 if x1 <= x <= x2 else min(abs(x - x1), abs(x - x2))
        dy = 0.0 if max(y1, seg_y1) <= min(y2, seg_y2) else min(abs(y1 - seg_y2), abs(seg_y1 - y2))
        return math.hypot(dx, dy)
    if math.isclose(sy, ey, abs_tol=1e-9):
        y = sy
        seg_x1, seg_x2 = sorted((sx, ex))
        if y1 <= y <= y2 and max(x1, seg_x1) <= min(x2, seg_x2):
            return 0.0
        dx = 0.0 if max(x1, seg_x1) <= min(x2, seg_x2) else min(abs(x1 - seg_x2), abs(seg_x1 - x2))
        dy = 0.0 if y1 <= y <= y2 else min(abs(y - y1), abs(y - y2))
        return math.hypot(dx, dy)
    # The diagonal-wire check reports these elsewhere; keep this conservative.
    return min(distance((x1, y1), start), distance((x2, y2), end))


def nearest_wire_clearance(box: BBox, wires: list[Wire]) -> float:
    distances = [segment_distance_to_box(box, start, end) for wire in wires for start, end in zip(wire.points, wire.points[1:])]
    return min(distances) if distances else math.inf


def estimate_text_bbox(prop: PropertyText) -> BBox:
    font_width = prop.font_size[0] if prop.font_size[0] else 1.27
    font_height = prop.font_size[1] if prop.font_size[1] else 1.27
    width = max(font_width, len(prop.value) * font_width * 0.55)
    return (prop.at[0] - width / 2, prop.at[1] - font_height * 0.78, prop.at[0] + width / 2, prop.at[1] + font_height * 0.22)


def find_rendered_property_text(prop: PropertyText, rendered_texts: list[RenderedText]) -> RenderedText | None:
    candidates = [text for text in rendered_texts if text.value == prop.value]
    if not candidates:
        return None
    return min(candidates, key=lambda text: distance(((text.bbox[0] + text.bbox[2]) / 2, (text.bbox[1] + text.bbox[3]) / 2), prop.at))


def assess_property_text_spacing(symbols: list[SymbolInstance], wires: list[Wire], rendered_texts: list[RenderedText]) -> dict[str, Any]:
    symbol_by_ref = {symbol.ref: symbol for symbol in symbols}
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for ref in PROPERTY_TEXT_REVIEW_REFS:
        symbol = symbol_by_ref.get(ref)
        if not symbol:
            unresolved.append({"ref": ref, "reason": "symbol_not_found"})
            continue
        for property_name in ("Reference", "Value"):
            prop = symbol.properties.get(property_name)
            if prop is None or prop.hidden:
                continue
            rendered = find_rendered_property_text(prop, rendered_texts)
            if rendered is not None:
                text_bbox = rendered.bbox
                source = rendered.source
                method = "kicad_svg_stroked_text_bbox"
            else:
                text_bbox = estimate_text_bbox(prop)
                source = "kicad_schematic_property_anchor"
                method = "estimated_from_property_font"
            body_clearance, relation = box_clearance_to_box(text_bbox, symbol.bbox)
            wire_clearance = nearest_wire_clearance(text_bbox, wires)
            body_ok = body_clearance >= PROPERTY_TEXT_BODY_CLEARANCE_MM
            wire_ok = wire_clearance >= PROPERTY_TEXT_WIRE_CLEARANCE_MM
            status = "PASS" if body_ok and wire_ok and method != "estimated_from_property_font" else "FAIL"
            if method == "estimated_from_property_font":
                status = "UNRESOLVED"
                unresolved.append({"ref": ref, "property": property_name, "reason": "rendered_svg_text_bbox_unavailable"})
            row = {
                "ref": ref,
                "property": property_name,
                "text": prop.value,
                "method": method,
                "source": source,
                "property_anchor_mm": {"x": round(prop.at[0], 4), "y": round(prop.at[1], 4)},
                "text_bbox_mm": {"x1": round(text_bbox[0], 4), "y1": round(text_bbox[1], 4), "x2": round(text_bbox[2], 4), "y2": round(text_bbox[3], 4)},
                "symbol_body_bbox_mm": {"x1": round(symbol.bbox[0], 4), "y1": round(symbol.bbox[1], 4), "x2": round(symbol.bbox[2], 4), "y2": round(symbol.bbox[3], 4)},
                "relation_to_symbol_body": relation,
                "body_clearance_mm": round(body_clearance, 4),
                "body_clearance_threshold_mm": PROPERTY_TEXT_BODY_CLEARANCE_MM,
                "nearest_wire_clearance_mm": round(wire_clearance, 4) if not math.isinf(wire_clearance) else None,
                "wire_clearance_threshold_mm": PROPERTY_TEXT_WIRE_CLEARANCE_MM,
                "status": status,
            }
            rows.append(row)
            if status == "FAIL":
                failures.append(row)
    overall = "FAIL" if failures or unresolved else "PASS"
    resolution = "FIXED_BY_TEXT_PROPERTY_MOVE" if overall == "PASS" else "FAIL_WITH_BLOCKERS"
    return {"status": overall, "resolution": resolution, "rows": rows, "failures": failures, "unresolved": unresolved}


def make_finding(
    finding_id: str,
    severity: str,
    rule: str,
    message: str,
    *,
    refs: list[str] | None = None,
    nets: list[str] | None = None,
    source_file: Path | str = "",
    coordinates: dict[str, float] | None = None,
    measured_value: Any = "",
    threshold: Any = "",
    explanation: str = "",
    evidence_crop: str = "",
) -> Finding:
    return Finding(
        id=finding_id,
        severity=severity,
        rule=rule,
        message=message,
        refs=refs or [],
        nets=nets or [],
        source_file=str(source_file),
        coordinates=coordinates or {},
        measured_value=measured_value,
        threshold=threshold,
        explanation=explanation,
        evidence_crop=evidence_crop,
    )


def count_colored_pixels(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGBA")
    non_transparent = 0
    colored = 0
    selection_like = 0
    for r, g, b, a in image.getdata():
        if a == 0:
            continue
        non_transparent += 1
        if max(r, g, b) - min(r, g, b) > 12:
            colored += 1
        if (b > 150 and r < 100 and g < 170) or (g > 140 and r < 120 and b < 120):
            selection_like += 1
    return {
        "width_px": image.width,
        "height_px": image.height,
        "non_transparent_pixels": non_transparent,
        "colored_ratio": colored / non_transparent if non_transparent else 0,
        "selection_like_pixels": selection_like,
    }


def nearest_distance(point: Point, points: list[Point]) -> float:
    if not points:
        return math.inf
    return min(distance(point, candidate) for candidate in points)


def is_endpoint_connected(endpoint: Point, connect_points: list[Point], tolerance: float = 0.001) -> bool:
    return nearest_distance(endpoint, connect_points) <= tolerance


def audit_kicad_geometry(
    symbols: list[SymbolInstance],
    wires: list[Wire],
    labels: list[Label],
    kicad_path: Path,
    property_text_spacing: dict[str, Any],
) -> tuple[list[Finding], dict[str, Any], dict[str, Any]]:
    findings: list[Finding] = []
    symbol_by_ref = {symbol.ref: symbol for symbol in symbols}
    symbol_boxes = {symbol.ref: symbol.bbox for symbol in symbols}
    pin_points = [point for symbol in symbols for point in symbol.pins.values()]
    label_points = [label.at for label in labels]
    wire_endpoints = [point for wire in wires for point in (wire.start, wire.end)]
    connect_points = pin_points + label_points + wire_endpoints
    wire_count_by_endpoint: dict[tuple[float, float], int] = {}
    for endpoint in wire_endpoints:
        wire_count_by_endpoint[point_key(endpoint)] = wire_count_by_endpoint.get(point_key(endpoint), 0) + 1

    diagonal_count = 0
    zero_length_count = 0
    short_wire_count = 0
    dangling_count = 0
    body_cross_count = 0
    floating_labels: list[str] = []
    for wire in wires:
        if len(wire.points) < 2:
            continue
        for start, end in zip(wire.points, wire.points[1:]):
            if not (math.isclose(start[0], end[0], abs_tol=1e-6) or math.isclose(start[1], end[1], abs_tol=1e-6)):
                diagonal_count += 1
                findings.append(
                    make_finding(
                        "KICAD_DIAGONAL_WIRE",
                        "BLOCKER",
                        "wire_orientation",
                        "KiCad wire segment is not horizontal or vertical.",
                        source_file=kicad_path,
                        coordinates={"x1": start[0], "y1": start[1], "x2": end[0], "y2": end[1]},
                        measured_value=start + end,
                        threshold="horizontal or vertical",
                        explanation="Formal schematic wires must be orthogonal.",
                    )
                )
            if distance(start, end) < 0.001:
                zero_length_count += 1
        if wire.length < 2.5:
            short_wire_count += 1
        for endpoint in (wire.start, wire.end):
            others = [point for point in connect_points if point is not endpoint]
            if not is_endpoint_connected(endpoint, others, 0.001):
                dangling_count += 1
        for ref, box in symbol_boxes.items():
            if ref and line_crosses_box(wire, box, clearance=-0.05):
                if all(distance(endpoint, pin) > 0.001 for endpoint in (wire.start, wire.end) for pin in symbol_by_ref[ref].pins.values()):
                    body_cross_count += 1
                    break

    if dangling_count:
        findings.append(
            make_finding(
                "KICAD_DANGLING_WIRE_ENDPOINT",
                "BLOCKER",
                "wire_endpoint_connectivity",
                "One or more wire endpoints do not coincide with a pin, label anchor, or another wire endpoint.",
                source_file=kicad_path,
                measured_value=dangling_count,
                threshold=0,
                explanation="This is a machine geometry check for visually close but electrically unclear endpoints.",
            )
        )
    if short_wire_count:
        findings.append(
            make_finding(
                "KICAD_SHORT_WIRE_SEGMENT",
                "WARNING",
                "wire_length",
                "Short wire segments exist and should be visually reviewed.",
                source_file=kicad_path,
                measured_value=short_wire_count,
                threshold="review if many or visually confusing",
                explanation="Short segments are sometimes needed to connect labels and pins, but many short stubs can make a drawing look fragmented.",
            )
        )
    if body_cross_count:
        findings.append(
            make_finding(
                "KICAD_WIRE_THROUGH_SYMBOL_BODY",
                "BLOCKER",
                "wire_symbol_overlap",
                "Wire appears to pass through a symbol body.",
                source_file=kicad_path,
                measured_value=body_cross_count,
                threshold=0,
                explanation="Wires crossing component bodies reduce schematic readability and can imply wrong topology.",
            )
        )

    for label in labels:
        if nearest_distance(label.at, pin_points + wire_endpoints) > 0.001:
            floating_labels.append(label.value)
    if floating_labels:
        findings.append(
            make_finding(
                "KICAD_FLOATING_NET_LABEL",
                "BLOCKER",
                "label_anchor",
                "One or more global labels are not anchored on a wire endpoint or pin.",
                nets=sorted(set(floating_labels)),
                source_file=kicad_path,
                measured_value=sorted(set(floating_labels)),
                threshold="all label anchors connected",
                explanation="A label that is only visually near a wire is not acceptable for final schematic review.",
            )
        )

    min_symbol_spacing = math.inf
    spacing_pairs: list[dict[str, Any]] = []
    refs = sorted(symbol_by_ref)
    for index, left_ref in enumerate(refs):
        for right_ref in refs[index + 1 :]:
            a = symbol_by_ref[left_ref].bbox
            b = symbol_by_ref[right_ref].bbox
            gap_x = max(0.0, max(b[0] - a[2], a[0] - b[2]))
            gap_y = max(0.0, max(b[1] - a[3], a[1] - b[3]))
            gap = math.hypot(gap_x, gap_y)
            min_symbol_spacing = min(min_symbol_spacing, gap)
            if gap < 2.0 and not bbox_intersects(a, b):
                spacing_pairs.append({"refs": [left_ref, right_ref], "gap_mm": round(gap, 3)})
            if bbox_intersects(a, b):
                findings.append(
                    make_finding(
                        "KICAD_SYMBOL_BODY_OVERLAP",
                        "BLOCKER",
                        "symbol_overlap",
                        "Two symbol bodies overlap.",
                        refs=[left_ref, right_ref],
                        source_file=kicad_path,
                        measured_value="overlap",
                        threshold="no body overlap",
                        explanation="Overlapped component bodies are not acceptable in an engineering schematic.",
                    )
                )

    for symbol in symbols:
        for prop in symbol.properties.values():
            if prop.hidden or prop.name in {"Footprint", "Datasheet"}:
                continue
            if prop.angle % 360 != 0:
                findings.append(
                    make_finding(
                        "KICAD_TEXT_ROTATED",
                        "BLOCKER",
                        "text_orientation",
                        "Visible symbol property text is rotated.",
                        refs=[symbol.ref],
                        source_file=kicad_path,
                        coordinates={"x": prop.at[0], "y": prop.at[1]},
                        measured_value=prop.angle,
                        threshold=0,
                        explanation="The requested drawing style allows horizontal text only.",
                    )
                )
    if property_text_spacing.get("unresolved"):
        findings.append(
            make_finding(
                "KICAD_PROPERTY_TEXT_SPACING_UNRESOLVED",
                "BLOCKER",
                "text_symbol_spacing",
                "Rendered SVG text bbox could not be resolved for one or more reviewed property texts.",
                refs=sorted({item.get("ref", "") for item in property_text_spacing.get("unresolved", []) if item.get("ref")}),
                source_file=kicad_path,
                measured_value=property_text_spacing.get("unresolved"),
                threshold="all reviewed property text bboxes from final/KiCad SVG",
                explanation="The review prompt forbids PASS based on fallback estimates for this text-spacing warning.",
            )
        )
    if property_text_spacing.get("failures"):
        findings.append(
            make_finding(
                "KICAD_PROPERTY_TEXT_CLEARANCE_FAIL",
                "BLOCKER",
                "text_symbol_spacing",
                "One or more reviewed Reference/Value texts violate symbol-body or wire clearance thresholds.",
                refs=sorted({item.get("ref", "") for item in property_text_spacing.get("failures", []) if item.get("ref")}),
                source_file=kicad_path,
                measured_value=property_text_spacing.get("failures"),
                threshold={
                    "body_clearance_mm": PROPERTY_TEXT_BODY_CLEARANCE_MM,
                    "wire_clearance_mm": PROPERTY_TEXT_WIRE_CLEARANCE_MM,
                },
                explanation="Measured from KiCad SVG stroked glyph extents against KiCad symbol body bboxes and wire segments.",
            )
        )

    block_results: dict[str, Any] = {}
    for block_name, config in CANONICAL_BLOCKS.items():
        missing_refs = [ref for ref in config["refs"] if ref not in symbol_by_ref]
        boxes = [symbol_by_ref[ref].bbox for ref in config["refs"] if ref in symbol_by_ref]
        block_bbox = bbox_union(boxes) if boxes else (0, 0, 0, 0)
        block_wires = [
            wire
            for wire in wires
            if bbox_intersects((min(wire.start[0], wire.end[0]), min(wire.start[1], wire.end[1]), max(wire.start[0], wire.end[0]), max(wire.start[1], wire.end[1])), block_bbox, margin=8.0)
        ]
        block_labels = [label.value for label in labels if bbox_intersects((label.at[0], label.at[1], label.at[0], label.at[1]), block_bbox, margin=12.0)]
        status = "PASS" if not missing_refs and block_wires else "WARN"
        if missing_refs:
            status = "FAIL"
        block_results[block_name] = {
            "status": status,
            "refs": config["refs"],
            "nets": config["nets"],
            "bbox_mm": {"x1": block_bbox[0], "y1": block_bbox[1], "x2": block_bbox[2], "y2": block_bbox[3]},
            "symbol_count": len(boxes),
            "wire_count": len(block_wires),
            "label_count": len(block_labels),
            "labels": sorted(set(block_labels)),
            "min_spacing_mm": None if math.isinf(min_symbol_spacing) else round(min_symbol_spacing, 3),
            "local_wire_continuity": "present" if block_wires else "not_detected",
        }

    metrics = {
        "symbol_count": len(symbols),
        "wire_count": len(wires),
        "global_label_count": len(labels),
        "junction_count": 0,
        "diagonal_wire_count": diagonal_count,
        "zero_length_wire_count": zero_length_count,
        "short_wire_count": short_wire_count,
        "dangling_endpoint_count": dangling_count,
        "floating_label_count": len(floating_labels),
        "wire_through_symbol_body_count": body_cross_count,
        "property_text_spacing_status": property_text_spacing.get("status"),
        "property_text_spacing_resolution": property_text_spacing.get("resolution"),
        "property_text_spacing_fail_count": len(property_text_spacing.get("failures", [])),
        "property_text_spacing_unresolved_count": len(property_text_spacing.get("unresolved", [])),
        "property_text_spacing": property_text_spacing,
        "min_symbol_spacing_mm": None if math.isinf(min_symbol_spacing) else round(min_symbol_spacing, 3),
        "close_symbol_pairs_under_2mm": spacing_pairs[:20],
        "symbols": {
            ref: {
                "lib_id": symbol.lib_id,
                "at_mm": {"x": symbol.at[0], "y": symbol.at[1]},
                "bbox_mm": {"x1": symbol.bbox[0], "y1": symbol.bbox[1], "x2": symbol.bbox[2], "y2": symbol.bbox[3]},
            }
            for ref, symbol in symbol_by_ref.items()
        },
    }
    return findings, metrics, block_results


def add_external_report_findings(
    findings: list[Finding],
    erc: dict[str, Any],
    equivalence: dict[str, Any],
    table_lock: dict[str, Any],
    export_lint: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    erc_summary = erc_status(erc)
    equivalence_status = equivalence.get("status", "MISSING" if equivalence.get("missing") else "UNKNOWN")
    table_status = table_lock.get("status", "MISSING" if table_lock.get("missing") else "UNKNOWN")
    export_error_count = export_lint.get("error_count", None)
    if erc_summary["status"] != "PASS":
        findings.append(make_finding("ERC_NOT_CLEAN", "BLOCKER", "electrical_baseline", "KiCad ERC is not clean.", source_file=args.erc_report, measured_value=erc_summary, threshold="0 violations"))
    if equivalence_status != "PASS":
        findings.append(make_finding("JLC_KICAD_EQUIVALENCE_NOT_PASS", "BLOCKER", "topology_equivalence", "JLC/KiCad topology equivalence did not pass.", source_file=args.equivalence_report, measured_value=equivalence_status, threshold="PASS"))
    if table_status != "PASS" or table_lock.get("error_count", 1) != 0:
        findings.append(make_finding("MASTER_TABLE_LOCK_NOT_PASS", "BLOCKER", "table_lock", "Master table lock did not pass.", source_file=args.table_lock_report, measured_value=table_lock.get("status"), threshold="PASS/0 errors"))
    if export_error_count != 0:
        findings.append(make_finding("EXPORT_LINT_NOT_CLEAN", "BLOCKER", "final_export", "Final export lint has errors.", source_file=args.export_lint_report, measured_value=export_error_count, threshold=0))
    return {
        "erc": erc_summary,
        "jlc_kicad_equivalence": {"status": equivalence_status, "summary": equivalence.get("summary", {})},
        "master_table_lock": {
            "status": table_status,
            "error_count": table_lock.get("error_count"),
            "value_only_changed_cell_count": table_lock.get("candidates", [{}])[-1].get("value_changed_cell_count") if table_lock.get("candidates") else None,
        },
        "export_lint": {"error_count": export_error_count, "png": export_lint.get("png", {}), "svg": export_lint.get("svg", {})},
    }


def create_evidence_crops(
    findings: list[Finding],
    block_results: dict[str, Any],
    metrics: dict[str, Any],
    property_text_spacing: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    crops_dir = args.crops_dir if args.crops_dir.is_absolute() else ROOT / args.crops_dir
    crops_dir.mkdir(parents=True, exist_ok=True)
    for stale in crops_dir.glob("*.png"):
        stale.unlink()
    manifest_path = crops_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
    image = Image.open(args.final_png).convert("RGBA")
    svg_viewbox = parse_svg_viewbox(args.final_svg)
    embedded_kicad_viewbox = parse_embedded_kicad_viewbox(args.final_svg)
    review_manifest = read_json(args.review_manifest)
    embed = review_manifest.get("kicad_embed_bbox", {})
    symbol_boxes = [tuple(value["bbox_mm"].values()) for value in metrics.get("symbols", {}).values()]
    if symbol_boxes:
        kicad_overall = bbox_union(symbol_boxes)  # type: ignore[arg-type]
    else:
        kicad_overall = (0, 0, 210, 190)
    evidence: dict[str, Any] = {"source_png": as_repo_path(args.final_png), "items": []}
    for block_name, result in block_results.items():
        bbox_dict = result["bbox_mm"]
        box = (bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"])
        crop_box = image_crop_box_from_kicad_bbox(box, kicad_overall, embed, svg_viewbox, image, margin_mm=12)
        crop = image.crop(crop_box)
        draw = ImageDraw.Draw(crop)
        draw.rectangle((2, 2, max(2, crop.width - 3), max(2, crop.height - 3)), outline=(0, 0, 0, 255), width=3)
        safe_name = re.sub(r"[^a-z0-9]+", "_", block_name.lower()).strip("_")
        output = crops_dir / f"block_{safe_name}.png"
        crop.save(output)
        result["evidence_crop"] = as_repo_path(output)
        evidence["items"].append({"kind": "block", "name": block_name, "path": as_repo_path(output), "pixel_box": crop_box})

    for row in property_text_spacing.get("rows", []):
        ref = row.get("ref", "")
        if any(item.get("kind") == "text_spacing" and item.get("ref") == ref for item in evidence["items"]):
            existing = next(item for item in evidence["items"] if item.get("kind") == "text_spacing" and item.get("ref") == ref)
            row["evidence_crop"] = existing["path"]
            continue
        symbol_info = metrics.get("symbols", {}).get(ref)
        if not symbol_info or not embedded_kicad_viewbox or not embed:
            continue
        bbox_dict = symbol_info["bbox_mm"]
        symbol_box = (bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"])
        text_bbox_dict = row["text_bbox_mm"]
        text_box = (text_bbox_dict["x1"], text_bbox_dict["y1"], text_bbox_dict["x2"], text_bbox_dict["y2"])
        crop_box = image_crop_box_from_embedded_kicad_bbox(bbox_union([symbol_box, text_box]), embedded_kicad_viewbox, embed, svg_viewbox, image, margin_mm=5)
        crop = image.crop(crop_box)
        draw = ImageDraw.Draw(crop)
        draw.rectangle((2, 2, max(2, crop.width - 3), max(2, crop.height - 3)), outline=(0, 0, 0, 255), width=3)
        output = crops_dir / f"text_spacing_{ref}.png"
        crop.save(output)
        row["evidence_crop"] = as_repo_path(output)
        evidence["items"].append({"kind": "text_spacing", "ref": ref, "path": as_repo_path(output), "pixel_box": crop_box})

    for idx, finding in enumerate([f for f in findings if f.severity in {"BLOCKER", "WARNING"}], start=1):
        if finding.evidence_crop:
            continue
        crop_box: tuple[int, int, int, int] | None = None
        if finding.refs and embed:
            symbol_boxes_for_refs: list[BBox] = []
            for ref in finding.refs:
                symbol_info = metrics.get("symbols", {}).get(ref)
                if symbol_info:
                    bbox_dict = symbol_info["bbox_mm"]
                    symbol_boxes_for_refs.append((bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"]))
            if symbol_boxes_for_refs:
                crop_box = image_crop_box_from_kicad_bbox(bbox_union(symbol_boxes_for_refs), kicad_overall, embed, svg_viewbox, image, margin_mm=14)
        if crop_box is None:
            # Fallback for global findings such as PNG color or report-level
            # errors: use the full KiCad block as the evidence region.
            crop_box = image_crop_box_from_kicad_bbox(kicad_overall, kicad_overall, embed, svg_viewbox, image, margin_mm=10)
        crop = image.crop(crop_box)
        draw = ImageDraw.Draw(crop)
        draw.rectangle((2, 2, max(2, crop.width - 3), max(2, crop.height - 3)), outline=(255, 0, 0, 255), width=3)
        output = crops_dir / f"finding_{idx:03d}_{finding.id.lower()}.png"
        crop.save(output)
        finding.evidence_crop = as_repo_path(output)
        evidence["items"].append({"kind": "finding", "id": finding.id, "path": as_repo_path(output), "pixel_box": crop_box})
    manifest_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return evidence


def final_status(findings: list[Finding]) -> str:
    if any(f.severity == "BLOCKER" for f in findings):
        return "FAIL"
    if any(f.severity == "WARNING" for f in findings):
        return "WARN"
    return "PASS"


def write_reports(
    args: argparse.Namespace,
    status: str,
    findings: list[Finding],
    metrics: dict[str, Any],
    blocks: dict[str, Any],
    external: dict[str, Any],
    visual: dict[str, Any],
) -> None:
    blocker_count = sum(1 for finding in findings if finding.severity == "BLOCKER")
    warning_count = sum(1 for finding in findings if finding.severity == "WARNING")
    payload = {
        "status": status,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "per_rule_results": {
            "electrical_baseline": external["erc"],
            "topology_equivalence": external["jlc_kicad_equivalence"],
            "master_table_lock": external["master_table_lock"],
            "export_lint": external["export_lint"],
            "kicad_geometry": {key: value for key, value in metrics.items() if key != "symbols"},
            "png_visual": visual,
        },
        "per_block_results": blocks,
        "findings": [asdict(finding) for finding in findings],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "kicad_schematic": as_repo_path(args.kicad_schematic),
            "final_svg": as_repo_path(args.final_svg),
            "final_png": as_repo_path(args.final_png),
            "final_drawio": as_repo_path(args.final_drawio),
        },
        "statement": "This is an automated engineering-layout audit, not final human approval.",
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Final Schematic Layout/Aesthetic Audit",
        "",
        "**This is an automated engineering-layout audit, not final human approval.**",
        "",
        f"- Status: **{status}**",
        f"- Blockers: `{blocker_count}`",
        f"- Warnings: `{warning_count}`",
        f"- JSON report: `{as_repo_path(args.json_report)}`",
        f"- Evidence crop directory: `{as_repo_path(args.crops_dir)}`",
        "",
        "## Electrical Baseline",
        "",
        f"- KiCad ERC: `{external['erc']['status']}`; violations `{external['erc']['violations']}`",
        f"- JLC/KiCad topology equivalence: `{external['jlc_kicad_equivalence']['status']}`",
        f"- Master table lock: `{external['master_table_lock']['status']}`; value-only changed cells `{external['master_table_lock']['value_only_changed_cell_count']}`",
        f"- Export lint errors: `{external['export_lint']['error_count']}`",
        "",
        "## KiCad Geometry Metrics",
        "",
        f"- Symbols: `{metrics['symbol_count']}`",
        f"- Wires: `{metrics['wire_count']}`",
        f"- Global labels: `{metrics['global_label_count']}`",
        f"- Junctions: `{metrics['junction_count']}`",
        f"- Diagonal wires: `{metrics['diagonal_wire_count']}`",
        f"- Zero-length wires: `{metrics['zero_length_wire_count']}`",
        f"- Short wires: `{metrics['short_wire_count']}`",
        f"- Dangling endpoints: `{metrics['dangling_endpoint_count']}`",
        f"- Floating labels: `{metrics['floating_label_count']}`",
        f"- Wire-through-symbol-body count: `{metrics['wire_through_symbol_body_count']}`",
        f"- Property text spacing status: `{metrics['property_text_spacing_status']}`",
        f"- Property text spacing resolution: `{metrics['property_text_spacing_resolution']}`",
        f"- Property text spacing failures: `{metrics['property_text_spacing_fail_count']}`",
        f"- Property text spacing unresolved: `{metrics['property_text_spacing_unresolved_count']}`",
        f"- Minimum symbol spacing: `{metrics['min_symbol_spacing_mm']}` mm",
        "",
        "## Property Text Clearance",
        "",
        f"- Body clearance threshold: `{PROPERTY_TEXT_BODY_CLEARANCE_MM}` mm",
        f"- Wire clearance threshold: `{PROPERTY_TEXT_WIRE_CLEARANCE_MM}` mm",
        "",
        "| Ref | Property | Text | Relation | Body clearance mm | Wire clearance mm | Status | Evidence crop |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in metrics.get("property_text_spacing", {}).get("rows", []):
        lines.append(
            "| {ref} | {property} | `{text}` | {relation} | {body:.4f} | {wire} | {status} | `{crop}` |".format(
                ref=row["ref"],
                property=row["property"],
                text=row["text"].replace("|", "\\|"),
                relation=row["relation_to_symbol_body"],
                body=row["body_clearance_mm"],
                wire="" if row["nearest_wire_clearance_mm"] is None else f"{row['nearest_wire_clearance_mm']:.4f}",
                status=row["status"],
                crop=row.get("evidence_crop", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Block Review",
            "",
        ]
    )
    for name, result in blocks.items():
        lines.extend(
            [
                f"### {name}",
                f"- Status: `{result['status']}`",
                f"- Refs: `{', '.join(result['refs'])}`",
                f"- Nets: `{', '.join(result['nets'])}`",
                f"- Symbol count: `{result['symbol_count']}`",
                f"- Wire count near block: `{result['wire_count']}`",
                f"- Label count near block: `{result['label_count']}`",
                f"- Local-wire continuity: `{result['local_wire_continuity']}`",
                f"- Evidence crop: `{result.get('evidence_crop', '')}`",
                "",
            ]
        )
    lines.extend(["## Findings", ""])
    if findings:
        for finding in findings:
            lines.extend(
                [
                    f"### {finding.id}",
                    f"- Severity: `{finding.severity}`",
                    f"- Rule: `{finding.rule}`",
                    f"- Refs: `{', '.join(finding.refs)}`",
                    f"- Nets: `{', '.join(finding.nets)}`",
                    f"- Measured: `{finding.measured_value}`",
                    f"- Threshold: `{finding.threshold}`",
                    f"- Evidence crop: `{finding.evidence_crop}`",
                    f"- Explanation: {finding.explanation}",
                    "",
                ]
            )
    else:
        lines.append("No blocker or warning findings were generated.")
    lines.extend(
        [
            "## Conclusion",
            "",
            "- PASS/WARN means the package can proceed to brief human visual approval.",
            "- FAIL means only the listed blockers should be fixed in the next round.",
            "- This checkpoint did not modify drawing, schematic, table, BOM, ref, net, or topology artifacts.",
        ]
    )
    args.md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    for path in (args.kicad_schematic, args.kicad_svg, args.final_svg, args.final_png, args.final_drawio, args.review_manifest):
        if not path.exists():
            raise SystemExit(f"Missing audit input: {path}")
    symbols, wires, labels, metadata = parse_kicad(args.kicad_schematic)
    rendered_texts = parse_kicad_rendered_texts(args.kicad_svg, args.final_svg)
    property_text_spacing = assess_property_text_spacing(symbols, wires, rendered_texts)
    findings, metrics, block_results = audit_kicad_geometry(symbols, wires, labels, args.kicad_schematic, property_text_spacing)
    erc = read_json(args.erc_report)
    equivalence = read_json(args.equivalence_report)
    table_lock = read_json(args.table_lock_report)
    export_lint = read_json(args.export_lint_report)
    external = add_external_report_findings(findings, erc, equivalence, table_lock, export_lint, args)
    png_visual = count_colored_pixels(args.final_png)
    if png_visual["width_px"] < 3000:
        findings.append(make_finding("PNG_TOO_SMALL", "BLOCKER", "final_png", "Final PNG is below required width.", source_file=args.final_png, measured_value=png_visual["width_px"], threshold=">= 3000 px"))
    if png_visual["selection_like_pixels"] != 0:
        findings.append(make_finding("PNG_SELECTION_ARTIFACT", "BLOCKER", "final_png", "Selection-like blue/green pixels detected.", source_file=args.final_png, measured_value=png_visual["selection_like_pixels"], threshold=0))
    if png_visual["colored_ratio"] > 0.005:
        findings.append(make_finding("PNG_COLORED_PIXEL_RATIO_HIGH", "WARNING", "final_png", "Colored pixel ratio is above monochrome-review threshold.", source_file=args.final_png, measured_value=png_visual["colored_ratio"], threshold="<= 0.005"))
    evidence = create_evidence_crops(findings, block_results, metrics, property_text_spacing, args)
    status = final_status(findings)
    write_reports(args, status, findings, metrics, block_results, external, png_visual)
    print(json.dumps({"status": status, "blocker_count": sum(f.severity == "BLOCKER" for f in findings), "warning_count": sum(f.severity == "WARNING" for f in findings), "json_report": str(args.json_report), "md_report": str(args.md_report), "crops_dir": str(args.crops_dir)}, ensure_ascii=False, indent=2))
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
