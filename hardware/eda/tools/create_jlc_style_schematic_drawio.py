#!/usr/bin/env python3
"""Create a BSTU-framed draw.io schematic using the original JLC SVG style.

The middle schematic is not redrawn with KiCad symbols here.  The script crops
the reusable JLC schematic body, normalizes visible refs/nets, and embeds that
source-faithful vector block into the locked school frame.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import math
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
FRAME_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
JLC_SVG = ROOT / "hardware/eda/jlc_schematic_original.svg"
OUTPUT_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"

DEFAULT_X = 250.0
DEFAULT_Y = 455.0
DEFAULT_WIDTH = 2100.0
DEFAULT_HEIGHT = 1180.0

# Source SVG coordinate crop.  It removes the JLC page frame/title block while
# keeping the complete schematic body and the source symbol geometry.
JLC_CROP = {
    "x": 200.0,
    "y": -735.0,
    "width": 780.0,
    "height": 420.0,
}

GENERATED_PREFIXES = (
    "jlc_style.",
    "kicad.",
    "generated.schematic.",
)
ELEMENT_LIST_CELL_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"
SVG_NS = "http://www.w3.org/2000/svg"

REF_REPLACEMENTS = {
    "U3_reset": "SB1",
    "U4_boot": "SB2",
    "U3_buck": "A1",
    "J2_heater": "XS2",
    "J_Power": "XS3",
    "J_TS1": "XS5",
    "CN1": "XS1",
    "U7": "XS4",
    "U1": "DD1",
    "Q1": "VT1",
    "D1": "HL1",
}

NET_REPLACEMENTS = {
    "J1_12V": "+12V",
    "3V3": "+3V3",
    "$1N14": "DQ",
    "$1N8": "EN",
    "$1N55": "BOOT",
    "$1N42": "RXD0",
    "$1N43": "TXD0",
    "$1N39": "GND",
    "$1N21": "LED",
    "$1N18": "LED_A",
    "$1N23": "GATE",
    "$1N24": "GATE_R",
    "$1N29": "HEAT-",
    "$1N65": "HEAT+",
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

REQUIRED_NETS = [
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

# Normalized source coordinates for invisible component-management metadata in
# the generated draw.io file.  The visible source symbol is the embedded JLC SVG.
COMPONENT_BBOXES = {
    "C1": (225, -720, 70, 38),
    "C2": (225, -690, 70, 38),
    "C3": (795, -430, 90, 50),
    "C4": (795, -380, 90, 50),
    "R1": (255, -607, 65, 35),
    "R2": (570, -695, 80, 55),
    "R3": (600, -445, 95, 55),
    "R4": (515, -540, 95, 35),
    "R5": (575, -590, 95, 45),
    "R6": (515, -640, 95, 45),
    "DD1": (350, -625, 160, 230),
    "HL1": (500, -420, 90, 55),
    "VT1": (595, -560, 70, 95),
    "SB1": (215, -570, 115, 75),
    "SB2": (505, -670, 135, 80),
    "XS1": (720, -675, 85, 90),
    "XS2": (870, -545, 95, 80),
    "XS3": (900, -455, 95, 80),
    "XS4": (510, -495, 100, 75),
    "XS5": (725, -545, 95, 75),
    "A1": (755, -650, 170, 120),
}

# Missing canonical net labels are added as ordinary schematic labels, not as a
# separate note, so export checks can confirm the school net names are visible.
ADDED_NET_LABELS = {
    "DQ": (680, -650),
    "BOOT": (620, -625),
    "LED": (565, -395),
    "LED_A": (670, -420),
    "GATE": (558, -545),
    "GATE_R": (625, -555),
    "HEAT+": (880, -520),
    "HEAT-": (870, -445),
}

ADDED_REF_LABELS = {
    "DD1": (420, -525),
    "C1": (270, -705),
    "C2": (270, -670),
    "C3": (830, -415),
    "C4": (830, -365),
    "R4": (520, -557),
    "R5": (595, -595),
    "SB1": (225, -565),
    "SB2": (560, -670),
    "HL1": (535, -385),
    "VT1": (618, -570),
    "XS2": (895, -550),
    "XS3": (930, -460),
    "XS4": (545, -500),
    "XS5": (742, -545),
    "A1": (810, -635),
}

DD1_PIN_LABELS = [
    {"name": "GND", "number": "1", "x": 368.7, "y": -614.1, "side": "left"},
    {"name": "+3V3", "number": "2", "x": 368.7, "y": -604.1, "side": "left"},
    {"name": "EN", "number": "3", "x": 368.7, "y": -594.1, "side": "left"},
    {"name": "SENSOR_VP", "number": "4", "x": 368.7, "y": -584.1, "side": "left"},
    {"name": "SENSOR_VN", "number": "5", "x": 368.7, "y": -574.1, "side": "left"},
    {"name": "IO34", "number": "6", "x": 368.7, "y": -564.1, "side": "left"},
    {"name": "IO35", "number": "7", "x": 368.7, "y": -554.1, "side": "left"},
    {"name": "IO32", "number": "8", "x": 368.7, "y": -544.1, "side": "left"},
    {"name": "IO33", "number": "9", "x": 368.7, "y": -534.1, "side": "left"},
    {"name": "IO25", "number": "10", "x": 368.7, "y": -524.1, "side": "left"},
    {"name": "IO26", "number": "11", "x": 368.7, "y": -514.1, "side": "left"},
    {"name": "IO27", "number": "12", "x": 368.7, "y": -504.1, "side": "left"},
    {"name": "IO14", "number": "13", "x": 368.7, "y": -494.1, "side": "left"},
    {"name": "IO12", "number": "14", "x": 368.7, "y": -484.1, "side": "left"},
    {"name": "IO0", "number": "25", "x": 481.3, "y": -484.1, "side": "right"},
    {"name": "IO4", "number": "26", "x": 481.3, "y": -494.1, "side": "right"},
    {"name": "IO16", "number": "27", "x": 481.3, "y": -504.1, "side": "right"},
    {"name": "IO17", "number": "28", "x": 481.3, "y": -514.1, "side": "right"},
    {"name": "IO5", "number": "29", "x": 481.3, "y": -524.1, "side": "right"},
    {"name": "IO18", "number": "30", "x": 481.3, "y": -534.1, "side": "right"},
    {"name": "IO19", "number": "31", "x": 481.3, "y": -544.1, "side": "right"},
    {"name": "NC", "number": "32", "x": 481.3, "y": -554.1, "side": "right"},
    {"name": "IO21", "number": "33", "x": 481.3, "y": -564.1, "side": "right"},
    {"name": "RXD0", "number": "34", "x": 481.3, "y": -574.1, "side": "right"},
    {"name": "TXD0", "number": "35", "x": 481.3, "y": -584.1, "side": "right"},
    {"name": "IO22", "number": "36", "x": 481.3, "y": -594.1, "side": "right"},
    {"name": "IO23", "number": "37", "x": 481.3, "y": -604.1, "side": "right"},
    {"name": "GND", "number": "38", "x": 481.3, "y": -614.1, "side": "right"},
]


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects(self, other: "BBox", tolerance: float = 0.0) -> bool:
        return not (
            self.right < other.x - tolerance
            or self.x > other.right + tolerance
            or self.bottom < other.y - tolerance
            or self.y > other.bottom + tolerance
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed a JLC-style schematic body into the BSTU draw.io frame.")
    parser.add_argument("--frame", type=Path, default=FRAME_DRAWIO)
    parser.add_argument("--jlc-svg", type=Path, default=JLC_SVG)
    parser.add_argument("--output", type=Path, default=OUTPUT_DRAWIO)
    parser.add_argument("--x", type=float, default=DEFAULT_X)
    parser.add_argument("--y", type=float, default=DEFAULT_Y)
    parser.add_argument("--width", type=float, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=float, default=DEFAULT_HEIGHT)
    return parser.parse_args()


def qname(local_name: str) -> str:
    return f"{{{SVG_NS}}}{local_name}"


def tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def token_replace(text: str) -> str:
    for source, target in sorted({**REF_REPLACEMENTS, **NET_REPLACEMENTS}.items(), key=lambda item: len(item[0]), reverse=True):
        if source == "3V3":
            text = re.sub(r"(?<![+A-Za-z0-9_.$-])3V3(?![A-Za-z0-9_.$-])", target, text)
            continue
        text = re.sub(rf"(?<![A-Za-z0-9_.$-]){re.escape(source)}(?![A-Za-z0-9_.$-])", target, text)
    return text


def token_present(token: str, text: str) -> bool:
    if token == "$1N":
        return "$1N" in text
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.$-])3V3(?![A-Za-z0-9_.$-])", text) is not None
    return re.search(rf"(?<![A-Za-z0-9_.$-]){re.escape(token)}(?![A-Za-z0-9_.$-])", text) is not None


def parse_svg(path: Path) -> ET.ElementTree:
    if not path.exists():
        raise FileNotFoundError(f"JLC SVG source missing: {path}")
    text = path.read_text(encoding="utf-8", errors="strict")
    if "<svg" not in text:
        raise ValueError(f"Input is not an SVG file: {path}")
    return ET.ElementTree(ET.fromstring(token_replace(text)))


def numbers_from_text(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", value or "")]


def numeric_attr(element: ET.Element, name: str, default: float = 0.0) -> float:
    raw = element.get(name)
    if raw is None:
        return default
    match = re.match(r"\s*([-+]?\d+(?:\.\d+)?)\s*(?:px|pt|mm)?\s*$", raw)
    if not match:
        raise ValueError(f"non-numeric SVG attribute {name}={raw!r}")
    return float(match.group(1))


def bbox_from_element(element: ET.Element) -> BBox | None:
    tag = tag_name(element)
    if tag == "text":
        try:
            x = numeric_attr(element, "x", math.nan)
            y = numeric_attr(element, "y", math.nan)
        except ValueError:
            return None
        if math.isnan(x) or math.isnan(y):
            return None
        text = "".join(element.itertext())
        return BBox(x - 6.0, y - 16.0, max(20.0, len(text) * 7.0), 22.0)
    if tag == "line":
        try:
            values = [numeric_attr(element, name) for name in ("x1", "y1", "x2", "y2")]
        except ValueError:
            return None
        x1, y1, x2, y2 = values
        return BBox(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    if tag in {"rect", "image", "use"}:
        try:
            x = numeric_attr(element, "x")
            y = numeric_attr(element, "y")
            width = numeric_attr(element, "width")
            height = numeric_attr(element, "height")
        except ValueError:
            return None
        return BBox(x, y, width, height)
    if tag in {"circle", "ellipse"}:
        try:
            cx = numeric_attr(element, "cx")
            cy = numeric_attr(element, "cy")
            rx = numeric_attr(element, "r", numeric_attr(element, "rx", 0.0))
            ry = numeric_attr(element, "r", numeric_attr(element, "ry", 0.0))
        except ValueError:
            return None
        return BBox(cx - rx, cy - ry, rx * 2, ry * 2)
    if tag in {"path", "polygon", "polyline"}:
        source = element.get("d", "") if tag == "path" else element.get("points", "")
        numbers = numbers_from_text(source)
        if len(numbers) < 2:
            return None
        points = list(zip(numbers[0::2], numbers[1::2], strict=False))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return BBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return None


def element_intersects_crop(element: ET.Element, crop: BBox) -> bool:
    bbox = bbox_from_element(element)
    if bbox is not None:
        return bbox.intersects(crop, tolerance=3.0)
    if tag_name(element) in {"defs", "style", "metadata"}:
        return True
    child_boxes = [bbox_from_element(child) for child in element.iter() if child is not element]
    child_boxes = [box for box in child_boxes if box is not None]
    return any(box.intersects(crop, tolerance=3.0) for box in child_boxes)


def prune_to_crop(parent: ET.Element, crop: BBox) -> None:
    for child in list(parent):
        if tag_name(child) in {"defs", "style", "metadata"}:
            continue
        prune_to_crop(child, crop)
        if len(child) == 0 and not element_intersects_crop(child, crop):
            parent.remove(child)
        elif len(child) > 0 and not element_intersects_crop(child, crop):
            parent.remove(child)


def normalize_svg_style(root: ET.Element) -> None:
    for element in root.iter():
        tag = tag_name(element)
        if tag == "text":
            element.set("fill", "#000000")
            element.set("font-family", "Arial")
            element.set("font-size", element.get("font-size", "12"))
        stroke = element.get("stroke")
        if stroke and stroke.lower() not in {"none", "#fff", "#ffffff", "white"}:
            element.set("stroke", "#000000")
        fill = element.get("fill")
        if tag != "text" and fill and fill.lower() not in {"none", "#fff", "#ffffff", "white"}:
            if fill.lower() in {"#ff8d00", "#008cff", "#0000ff", "orange", "blue"}:
                element.set("fill", "#000000")
        style = element.get("style")
        if style:
            style = re.sub(r"stroke:\s*(?!none|#fff(?:fff)?|white)[^;]+", "stroke:#000000", style, flags=re.I)
            if tag == "text":
                style = re.sub(r"fill:\s*[^;]+", "fill:#000000", style, flags=re.I)
            element.set("style", style)


def bring_text_to_front(root: ET.Element) -> None:
    text_nodes: list[ET.Element] = []

    def walk(parent: ET.Element) -> None:
        for child in list(parent):
            if tag_name(child) == "text":
                parent.remove(child)
                text_nodes.append(child)
            else:
                walk(child)

    walk(root)
    if not text_nodes:
        return
    group = ET.SubElement(root, qname("g"), {"id": "codex-source-text-layer-front"})
    for node in text_nodes:
        group.append(node)


def add_missing_net_labels(root: ET.Element) -> None:
    existing = " ".join("".join(element.itertext()) for element in root.iter() if tag_name(element) == "text")
    group = ET.SubElement(root, qname("g"), {"id": "codex-added-canonical-net-labels"})
    for net, (x, y) in ADDED_NET_LABELS.items():
        if re.search(rf"(?<![A-Za-z0-9_+.-]){re.escape(net)}(?![A-Za-z0-9_+.-])", existing):
            continue
        text = ET.SubElement(
            group,
            qname("text"),
            {
                "x": f"{x:.1f}",
                "y": f"{y:.1f}",
                "fill": "#000000",
                "font-size": "11",
                "font-family": "Arial",
                "transform": f"rotate(0, {x:.1f}, {y:.1f})",
                "data-role": "net_label",
                "data-net": net,
            },
        )
        text.text = net


def add_missing_ref_labels(root: ET.Element) -> None:
    existing = " ".join("".join(element.itertext()) for element in root.iter() if tag_name(element) == "text")
    group = ET.SubElement(root, qname("g"), {"id": "codex-added-school-ref-labels"})
    for ref, (x, y) in ADDED_REF_LABELS.items():
        if re.search(rf"(?<![A-Za-z0-9_+.-]){re.escape(ref)}(?![A-Za-z0-9_+.-])", existing):
            continue
        text = ET.SubElement(
            group,
            qname("text"),
            {
                "x": f"{x:.1f}",
                "y": f"{y:.1f}",
                "fill": "#000000",
                "font-size": "10",
                "font-family": "Arial",
                "transform": f"rotate(0, {x:.1f}, {y:.1f})",
                "data-role": "component_ref",
                "data-ref": ref,
            },
        )
        text.text = ref


def add_text(
    parent: ET.Element,
    *,
    value: str,
    x: float,
    y: float,
    font_size: float,
    anchor: str = "start",
    role: str = "restored_text",
    extra: dict[str, str] | None = None,
) -> ET.Element:
    attrs = {
        "x": f"{x:.1f}",
        "y": f"{y:.1f}",
        "fill": "#000000",
        "font-size": f"{font_size:g}",
        "font-family": "Arial",
        "text-anchor": anchor,
        "transform": f"rotate(0, {x:.1f}, {y:.1f})",
        "data-role": role,
    }
    if extra:
        attrs.update(extra)
    text = ET.SubElement(parent, qname("text"), attrs)
    text.text = value
    return text


def add_dd1_pin_labels(root: ET.Element) -> None:
    """Restore DD1 pin text that is blank in the exported JLC SVG payload.

    The original symbol geometry stays untouched.  Only text labels are added
    at the JLC symbol's pin-row coordinates so the A1 review crop remains
    readable after embedding in the BSTU frame.
    """

    existing = " ".join("".join(element.itertext()) for element in root.iter() if tag_name(element) == "text")
    group = ET.SubElement(root, qname("g"), {"id": "codex-restored-dd1-pin-labels", "data-role": "restored_jlc_pin_text"})
    if "ESP32-WROOM-32" not in existing:
        add_text(
            group,
            value="ESP32-WROOM-32",
            x=424.0,
            y=-405.0,
            font_size=8.5,
            anchor="middle",
            role="component_value",
            extra={"data-ref": "DD1"},
        )
    for pin in DD1_PIN_LABELS:
        side = pin["side"]
        name_x = float(pin["x"])
        number_x = 363.9 if side == "left" else 486.1
        anchor = "start" if side == "left" else "end"
        number_anchor = "end" if side == "left" else "start"
        y = float(pin["y"])
        name = str(pin["name"])
        number = str(pin["number"])
        if not re.search(rf"(?<![A-Za-z0-9_+.-]){re.escape(name)}(?![A-Za-z0-9_+.-])", existing):
            add_text(
                group,
                value=name,
                x=name_x,
                y=y,
                font_size=6.4,
                anchor=anchor,
                role="pin_label",
                extra={"data-ref": "DD1", "data-pin": name, "data-pin-number": number},
            )
        add_text(
            group,
            value=number,
            x=number_x,
            y=y,
            font_size=5.8,
            anchor=number_anchor,
            role="pin_number",
            extra={"data-ref": "DD1", "data-pin": name, "data-pin-number": number},
        )


def cleaned_jlc_svg(path: Path) -> str:
    tree = parse_svg(path)
    root = tree.getroot()
    crop = BBox(**JLC_CROP)
    prune_to_crop(root, crop)
    root.set("width", f"{crop.width:.3f}mm")
    root.set("height", f"{crop.height:.3f}mm")
    root.set("viewBox", f"{crop.x:.3f} {crop.y:.3f} {crop.width:.3f} {crop.height:.3f}")
    root.set("data-role", "jlc_style_schematic_source")
    normalize_svg_style(root)
    add_missing_ref_labels(root)
    add_missing_net_labels(root)
    add_dd1_pin_labels(root)
    bring_text_to_front(root)
    metadata = root.find(qname("metadata"))
    if metadata is None:
        metadata = ET.Element(qname("metadata"))
        root.insert(0, metadata)
    metadata.text = json.dumps(
        {
            "source": "hardware/eda/jlc_schematic_original.svg",
            "workflow": "JLC-style faithful layout beautification",
            "crop": JLC_CROP,
            "required_refs": REQUIRED_REFS,
            "required_nets": REQUIRED_NETS,
            "symbol_shape_policy": "source JLC vector geometry is cropped/reused; refs/nets normalized",
        },
        ensure_ascii=False,
    )
    xml = ET.tostring(root, encoding="unicode")
    xml = token_replace(xml)
    forbidden = [token for token in list(REF_REPLACEMENTS) + ["J1_12V"] if token_present(token, html.unescape(xml))]
    if forbidden:
        raise ValueError(f"Cleaned JLC SVG still contains forbidden source tokens: {', '.join(sorted(set(forbidden)))}")
    return xml


def parse_drawio(path: Path) -> ET.ElementTree:
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


def overlaps_region(rect: tuple[float, float, float, float], region: dict[str, float], tolerance: float = 1.0) -> bool:
    x, y, width, height = rect
    if width <= 0 or height <= 0:
        return False
    return not (
        x + width < float(region["x"]) - tolerance
        or x > float(region["right"]) + tolerance
        or y + height < float(region["y"]) - tolerance
        or y > float(region["bottom"]) + tolerance
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


def remove_previous_generated_cells(root_cell: ET.Element) -> None:
    for cell in list(root_cell):
        cell_id = cell.get("id", "")
        role = cell.get("data-role", "")
        if any(cell_id.startswith(prefix) for prefix in GENERATED_PREFIXES) or role in {
            "jlc_style_schematic_embed",
            "jlc_style_schematic_background",
            "jlc_symbol_group",
            "kicad_schematic_embed",
            "kicad_schematic_background",
        }:
            root_cell.remove(cell)


def add_rect_cell(root_cell: ET.Element, *, cell_id: str, role: str, x: float, y: float, width: float, height: float, visible: bool) -> None:
    style = "rounded=0;whiteSpace=wrap;html=1;"
    if visible:
        style += "fillColor=#ffffff;strokeColor=none;"
    else:
        style += "fillColor=none;strokeColor=none;opacity=0;"
    cell = ET.SubElement(
        root_cell,
        "mxCell",
        {
            "id": cell_id,
            "value": "",
            "style": style,
            "vertex": "1",
            "parent": "1",
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
            "id": "jlc_style.schematic.embed",
            "value": "",
            "style": style,
            "vertex": "1",
            "parent": "1",
            "data-role": "jlc_style_schematic_embed",
            "data-source": "hardware/eda/jlc_schematic_original.svg",
            "data-policy": "preserve_jlc_symbol_shapes",
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


def map_jlc_bbox_to_drawio(raw: tuple[float, float, float, float], x: float, y: float, width: float, height: float) -> tuple[float, float, float, float]:
    source_x, source_y, source_w, source_h = raw
    scale = min(width / JLC_CROP["width"], height / JLC_CROP["height"])
    image_w = JLC_CROP["width"] * scale
    image_h = JLC_CROP["height"] * scale
    offset_x = x + (width - image_w) / 2
    offset_y = y + (height - image_h) / 2
    mapped_x = offset_x + (source_x - JLC_CROP["x"]) * scale
    mapped_y = offset_y + (source_y - JLC_CROP["y"]) * scale
    return (mapped_x, mapped_y, source_w * scale, source_h * scale)


def add_component_group_metadata(root_cell: ET.Element, x: float, y: float, width: float, height: float) -> None:
    for ref, source_bbox in COMPONENT_BBOXES.items():
        gx, gy, gw, gh = map_jlc_bbox_to_drawio(source_bbox, x, y, width, height)
        cell = ET.SubElement(
            root_cell,
            "mxCell",
            {
                "id": f"jlc_style.group.{ref}",
                "value": "",
                "style": "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;opacity=0;",
                "vertex": "1",
                "parent": "1",
                "data-role": "jlc_symbol_group",
                "data-ref": ref,
                "data-source": "hardware/eda/jlc_schematic_original.svg",
                "data-shape-policy": "shape_reused_from_jlc_svg",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": f"{gx:.3f}".rstrip("0").rstrip("."),
                "y": f"{gy:.3f}".rstrip("0").rstrip("."),
                "width": f"{gw:.3f}".rstrip("0").rstrip("."),
                "height": f"{gh:.3f}".rstrip("0").rstrip("."),
                "as": "geometry",
            },
        )


def assert_locked_template_text_unchanged(tree: ET.ElementTree) -> None:
    text = html.unescape(ET.tostring(tree.getroot(), encoding="unicode"))
    required = ["Position number", "Name", "BSTU.241297.006"]
    missing = [value for value in required if value not in text]
    if "Qty" not in text and "Number" not in text:
        missing.append("Qty or Number")
    if missing:
        raise ValueError(f"Frame/list/title template text missing after JLC embed: {', '.join(missing)}")


def create_drawio(frame: Path, jlc_svg: Path, output: Path, x: float, y: float, width: float, height: float) -> None:
    svg = cleaned_jlc_svg(jlc_svg)
    tree = parse_drawio(frame)
    root_cell = root_with_locked_regions_only(tree)
    remove_previous_generated_cells(root_cell)
    add_rect_cell(root_cell, cell_id="jlc_style.schematic.background", role="jlc_style_schematic_background", x=x, y=y, width=width, height=height, visible=True)
    add_svg_image(root_cell, svg, x, y, width, height)
    add_component_group_metadata(root_cell, x, y, width, height)
    assert_locked_template_text_unchanged(tree)
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    create_drawio(args.frame, args.jlc_svg, args.output, args.x, args.y, args.width, args.height)
    print(f"Embedded JLC-style schematic body into {args.output}")
    print(f"Source: {args.jlc_svg}")
    print(f"Placement: x={args.x:.2f}, y={args.y:.2f}, width={args.width:.2f}, height={args.height:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
