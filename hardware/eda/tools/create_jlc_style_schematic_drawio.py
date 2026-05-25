#!/usr/bin/env python3
"""Create a BSTU-framed draw.io schematic using the original JLC SVG style.

The middle schematic is not redrawn with KiCad symbols here.  The script reuses
the source JLC symbol artwork for every component, normalizes visible refs/nets,
and lays those symbols out as a cleaner A1 engineering schematic inside the
locked school frame.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
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

DEFAULT_X = 160.0
DEFAULT_Y = 400.0
DEFAULT_WIDTH = 2180.0
DEFAULT_HEIGHT = 1368.0

# Source SVG coordinate crop.  It removes the JLC page frame/title block while
# keeping the complete schematic body and the source symbol geometry.
JLC_CROP = {
    "x": 200.0,
    "y": -735.0,
    "width": 780.0,
    "height": 420.0,
}

# Internal coordinate system for the rebuilt middle schematic SVG.  The
# component artwork is still cropped from the JLC source; only its placement and
# the connecting wires are rebuilt.
COMPOSITE_VIEWBOX = {
    "x": 0.0,
    "y": 0.0,
    "width": 900.0,
    "height": 545.0,
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

# Source coordinates for the JLC component artwork crops.
SOURCE_COMPONENT_BBOXES = {
    "C1": (225, -733, 40, 34),
    "C2": (225, -698, 40, 34),
    "C3": (805, -443, 40, 34),
    "C4": (805, -393, 40, 34),
    "R1": (265, -611, 40, 42),
    "R2": (580, -696, 40, 42),
    "R3": (600, -446, 40, 42),
    "R4": (520, -544, 40, 25),
    "R5": (585, -594, 40, 25),
    "R6": (510, -521, 40, 42),
    "DD1": (354, -644.1, 149.3, 240.1),
    "HL1": (515, -401, 40, 33),
    "VT1": (595, -561.1, 37, 41.1),
    "SB1": (209, -560.1, 61, 42),
    "SB2": (515, -645.1, 44.5, 37),
    "XS1": (720, -681, 30, 57.9),
    "XS2": (655, -525.1, 30, 37),
    "XS3": (765, -515.1, 30, 37),
    "XS4": (530, -495.1, 61, 42),
    "XS5": (725, -556, 39, 47.9),
    "A1": (795, -600.1, 44.5, 37),
}

COMPOSITE_COMPONENT_POSITIONS = {
    "C1": (72.0, 50.0),
    "C2": (72.0, 105.0),
    "C3": (770.0, 462.0),
    "C4": (770.0, 512.0),
    "R1": (120.0, 245.0),
    "R2": (585.0, 66.0),
    "R3": (255.0, 420.0),
    "R4": (560.0, 300.0),
    "R5": (620.0, 390.0),
    "R6": (455.0, 320.0),
    "DD1": (300.0, 165.0),
    "HL1": (390.0, 448.0),
    "VT1": (690.0, 310.0),
    "SB1": (95.0, 315.0),
    "SB2": (455.0, 360.0),
    "XS1": (745.0, 115.0),
    "XS2": (815.0, 390.0),
    "XS3": (530.0, 486.0),
    "XS4": (560.0, 205.0),
    "XS5": (790.0, 292.0),
    "A1": (650.0, 486.0),
}

COMPONENT_BBOXES = {
    ref: (
        COMPOSITE_COMPONENT_POSITIONS[ref][0],
        COMPOSITE_COMPONENT_POSITIONS[ref][1],
        SOURCE_COMPONENT_BBOXES[ref][2],
        SOURCE_COMPONENT_BBOXES[ref][3],
    )
    for ref in SOURCE_COMPONENT_BBOXES
}

ADDED_NET_LABELS = {
    "EN": (248.0, 260.0),
    "DQ": (695.0, 150.0),
    "BOOT": (505.0, 362.0),
    "RXD0": (690.0, 222.0),
    "TXD0": (690.0, 240.0),
    "LED": (465.0, 484.0),
    "LED_A": (325.0, 446.0),
    "GATE": (532.0, 318.0),
    "GATE_R": (746.0, 336.0),
    "HEAT+": (835.0, 318.0),
    "HEAT-": (852.0, 443.0),
    "+3V3": (812.0, 482.0),
}

ADDED_REF_LABELS = {
    "C1": (112.0, 44.0),
    "C2": (112.0, 99.0),
    "C3": (808.0, 456.0),
    "C4": (808.0, 506.0),
    "R4": (570.0, 294.0),
    "SB1": (104.0, 308.0),
    "R5": (635.0, 384.0),
    "SB2": (490.0, 397.0),
    "VT1": (703.0, 303.0),
    "XS2": (828.0, 384.0),
    "XS3": (545.0, 480.0),
    "XS4": (610.0, 199.0),
    "A1": (690.0, 480.0),
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
        element.attrib.pop("filter", None)
        if tag == "text":
            element.set("fill", "#000000")
            element.set("font-family", "Arial")
            if element.get("font-size") is None:
                element.set("font-size", "10")
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
            style = re.sub(r"opacity:\s*0(?:\.0+)?;?", "", style, flags=re.I)
            style = re.sub(r"fill-opacity:\s*0(?:\.0+)?;?", "", style, flags=re.I)
            style = re.sub(r"stroke-opacity:\s*0(?:\.0+)?;?", "", style, flags=re.I)
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


def group_bbox(group: ET.Element) -> BBox | None:
    boxes = [bbox_from_element(child) for child in group.iter() if child is not group]
    boxes = [box for box in boxes if box is not None]
    if not boxes:
        return None
    left = min(box.x for box in boxes)
    top = min(box.y for box in boxes)
    right = max(box.right for box in boxes)
    bottom = max(box.bottom for box in boxes)
    return BBox(left, top, right - left, bottom - top)


def canonical_symbol_ref(texts: list[str]) -> str | None:
    joined = " ".join(texts)
    exact_map = {
        "U1": "DD1",
        "DD1": "DD1",
        "D1": "HL1",
        "HL1": "HL1",
        "CN1": "XS1",
        "XS1": "XS1",
        "J_TS1": "XS5",
        "XS5": "XS5",
    }
    for source, target in exact_map.items():
        if source in texts:
            return target
    if "R6" in texts and "10K" in texts:
        return "R6"
    if "R1" in texts and "10K" in texts:
        return "R1"
    if "R2" in texts:
        return "R2"
    if "R3" in texts:
        return "R3"
    if "100R" in texts:
        return "R4"
    if "10K" in texts and "R6" not in texts and "R1" not in texts:
        return "R5"
    if {"S", "G", "D"}.issubset(set(texts)):
        return "VT1"
    if texts.count("1") >= 2 and texts.count("2") >= 2 and len(texts) == 4:
        return None
    if "0.1uF" in texts:
        return None
    if "10uF" in texts:
        return "C1"
    if "100uF" in texts:
        return "C3"
    if "1" in texts and "2" in texts and "3" in texts and "4" in texts:
        if "12V to 3V3 Buck Module" in joined:
            return "A1"
        return None
    return None


def source_symbol_groups(root: ET.Element) -> dict[str, ET.Element]:
    groups: dict[str, ET.Element] = {}
    anonymous_groups: list[tuple[BBox, ET.Element]] = []
    for group in root.iter():
        if tag_name(group) != "g" or group.get("c_partid") != "part":
            continue
        texts = ["".join(element.itertext()).strip() for element in group.iter() if tag_name(element) == "text" and "".join(element.itertext()).strip()]
        ref = canonical_symbol_ref(texts)
        if ref:
            groups[ref] = copy.deepcopy(group)
            continue
        bbox = group_bbox(group)
        if bbox is None:
            continue
        anonymous_groups.append((bbox, copy.deepcopy(group)))

    # Source JLC symbols without visible refs are assigned by exact source bbox.
    # This avoids accidentally swapping visually similar switches/connectors.
    for ref, expected in SOURCE_COMPONENT_BBOXES.items():
        if ref in groups:
            continue
        ex, ey, ew, eh = expected
        for bbox, node in anonymous_groups:
            if (
                abs(bbox.x - ex) <= 0.2
                and abs(bbox.y - ey) <= 0.2
                and abs(bbox.width - ew) <= 0.2
                and abs(bbox.height - eh) <= 0.2
            ):
                groups[ref] = node
                break

    missing = sorted(set(REQUIRED_REFS) - set(groups))
    if missing:
        raise ValueError(f"Unable to map JLC source symbol groups: {', '.join(missing)}")
    return groups


def symbol_internal_items(symbol: ET.Element) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for element in symbol.iter():
        if element is symbol:
            continue
        attrs = {key: value for key, value in sorted(element.attrib.items())}
        if tag_name(element) == "text":
            attrs.pop("id", None)
        items.append(
            {
                "tag": tag_name(element),
                "attrs": attrs,
                "text": "" if tag_name(element) == "text" else "".join(element.itertext()).strip(),
            }
        )
    return items


def hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def symbol_style_items(symbol: ET.Element) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for element in symbol.iter():
        if element is symbol:
            continue
        if tag_name(element) == "text":
            continue
        items.append(
            {
                "tag": tag_name(element),
                "style": element.get("style", ""),
                "stroke": element.get("stroke", ""),
                "stroke-width": element.get("stroke-width", ""),
                "fill": element.get("fill", ""),
                "class": element.get("class", ""),
            }
        )
    return items


def symbol_fidelity_entry(ref: str, source_symbol: ET.Element, final_symbol: ET.Element) -> dict[str, Any]:
    source_items = symbol_internal_items(source_symbol)
    final_items = symbol_internal_items(final_symbol)
    source_styles = symbol_style_items(source_symbol)
    final_styles = symbol_style_items(final_symbol)
    source_tag_counts: dict[str, int] = {}
    final_tag_counts: dict[str, int] = {}
    for item in source_items:
        source_tag_counts[item["tag"]] = source_tag_counts.get(item["tag"], 0) + 1
    for item in final_items:
        final_tag_counts[item["tag"]] = final_tag_counts.get(item["tag"], 0) + 1
    source_geometry_hash = hash_json(source_items)
    final_geometry_hash = hash_json(final_items)
    source_style_hash = hash_json(source_styles)
    final_style_hash = hash_json(final_styles)
    geometry_match = source_geometry_hash == final_geometry_hash
    style_match = source_style_hash == final_style_hash
    tag_match = source_tag_counts == final_tag_counts
    return {
        "ref": ref,
        "source_group_id": source_symbol.get("id", ""),
        "final_group_id": final_symbol.get("id", ""),
        "source_elements_count": len(source_items),
        "final_elements_count": len(final_items),
        "source_tag_counts": source_tag_counts,
        "final_tag_counts": final_tag_counts,
        "source_geometry_hash": source_geometry_hash,
        "final_geometry_hash": final_geometry_hash,
        "geometry_hash_match": geometry_match,
        "source_style_hash": source_style_hash,
        "final_style_hash": final_style_hash,
        "stroke_style_match": style_match,
        "path_count_before": source_tag_counts.get("path", 0),
        "path_count_after": final_tag_counts.get("path", 0),
        "allowed_transform": final_symbol.get("transform", ""),
        "verdict": "PASS" if geometry_match and style_match and tag_match else "FAIL",
    }


def transform_symbol_to_position(symbol: ET.Element, source_bbox: tuple[float, float, float, float], target: tuple[float, float]) -> ET.Element:
    node = copy.deepcopy(symbol)
    source_x, source_y, _, _ = source_bbox
    dx = target[0] - source_x
    dy = target[1] - source_y
    existing = node.get("transform", "")
    transform = f"translate({dx:.3f},{dy:.3f})"
    node.set("transform", f"{existing} {transform}".strip())
    node.set("data-role", "jlc_symbol_source_group")
    return node


def make_line(parent: ET.Element, points: list[tuple[float, float]], *, net: str, role: str = "wire") -> None:
    formatted = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    ET.SubElement(
        parent,
        qname("polyline"),
        {
            "points": formatted,
            "fill": "none",
            "stroke": "#000000",
            "stroke-width": "1",
            "stroke-linecap": "square",
            "stroke-linejoin": "miter",
            "vector-effect": "unset",
            "data-role": role,
            "data-net": net,
        },
    )


def make_dot(parent: ET.Element, x: float, y: float, *, net: str) -> None:
    ET.SubElement(
        parent,
        qname("circle"),
        {
            "cx": f"{x:.1f}",
            "cy": f"{y:.1f}",
            "r": "2.3",
            "fill": "#000000",
            "stroke": "#000000",
            "stroke-width": "1.0",
            "data-role": "junction",
            "data-net": net,
        },
    )


def make_power(parent: ET.Element, x: float, y: float, label: str, *, net: str) -> None:
    make_line(parent, [(x, y), (x, y - 20)], net=net, role="power_symbol")
    add_text(parent, value=label, x=x, y=y - 24, font_size=11.0, anchor="middle", role="net_label", extra={"data-net": net})


def make_ground(parent: ET.Element, x: float, y: float, *, net: str = "GND") -> None:
    make_line(parent, [(x, y - 18), (x, y - 8)], net=net, role="gnd_symbol")
    make_line(parent, [(x - 12, y - 8), (x + 12, y - 8)], net=net, role="gnd_symbol")
    make_line(parent, [(x - 8, y - 3), (x + 8, y - 3)], net=net, role="gnd_symbol")
    make_line(parent, [(x - 4, y + 2), (x + 4, y + 2)], net=net, role="gnd_symbol")
    add_text(parent, value="GND", x=x + 18, y=y - 3, font_size=9.0, anchor="start", role="net_label", extra={"data-net": net})


def make_pullup(parent: ET.Element, x: float, y: float, *, net: str = "+3V3") -> None:
    make_line(parent, [(x - 8, y), (x + 8, y)], net=net, role="power_symbol")
    make_line(parent, [(x, y), (x, y + 16)], net=net, role="power_symbol")
    add_text(parent, value=net, x=x, y=y - 6, font_size=10.5, anchor="middle", role="net_label", extra={"data-net": net})


def add_composite_wires(root: ET.Element) -> None:
    group = ET.SubElement(root, qname("g"), {"id": "codex-jlc-style-rebuilt-wires", "data-role": "rebuilt_jlc_style_wiring"})

    # Decoupling power rail near DD1.
    make_pullup(group, 70, 40)
    make_line(group, [(70, 56), (72, 56), (72, 154), (300, 154)], net="+3V3")
    make_line(group, [(72, 69), (72, 124), (142, 124)], net="+3V3")
    make_ground(group, 185, 165)
    make_line(group, [(142, 88), (185, 88), (185, 147)], net="GND")
    make_line(group, [(142, 143), (185, 143)], net="GND")
    make_dot(group, 72, 124, net="+3V3")

    # Reset / EN block.
    make_pullup(group, 112, 220)
    make_line(group, [(112, 236), (120, 266), (188, 266), (300, 266)], net="EN")
    make_line(group, [(95, 336), (188, 336), (188, 266)], net="EN")
    make_ground(group, 125, 390)
    make_line(group, [(95, 357), (125, 357), (125, 372)], net="GND")
    make_dot(group, 188, 266, net="EN")

    # Sensor and UART form a compact upper-right interface module.
    make_pullup(group, 585, 46)
    make_line(group, [(585, 66), (585, 87), (745, 87)], net="+3V3")
    make_line(group, [(625, 87), (625, 154), (745, 154)], net="DQ")
    make_line(group, [(449, 231), (535, 231), (535, 154), (625, 154)], net="DQ")
    make_ground(group, 735, 200)
    make_line(group, [(745, 174), (735, 174), (735, 182)], net="GND")
    make_line(group, [(449, 260), (560, 260), (560, 225)], net="RXD0")
    make_line(group, [(449, 247), (560, 247), (560, 240)], net="TXD0")
    make_line(group, [(621, 225), (685, 225)], net="RXD0")
    make_line(group, [(621, 240), (685, 240)], net="TXD0")
    make_pullup(group, 670, 192)
    make_ground(group, 680, 278)
    make_line(group, [(685, 245), (680, 245), (680, 260)], net="GND")
    make_dot(group, 625, 154, net="DQ")

    # Boot circuit.
    make_pullup(group, 465, 295)
    make_line(group, [(465, 320), (486, 320), (486, 350), (468, 350)], net="BOOT")
    make_line(group, [(449, 273), (486, 273), (486, 350)], net="BOOT")
    make_ground(group, 522, 422)
    make_line(group, [(516, 385), (522, 385), (522, 404)], net="GND")
    make_dot(group, 486, 350, net="BOOT")

    # Heater driver is a distinct right-middle output block.
    make_line(group, [(449, 333), (560, 333), (560, 327)], net="GATE")
    make_line(group, [(600, 327), (690, 327)], net="GATE_R")
    make_line(group, [(660, 394), (742, 394), (742, 352)], net="GATE_R")
    make_ground(group, 712, 442)
    make_line(group, [(620, 394), (620, 412), (712, 412), (712, 424)], net="GND")
    make_ground(group, 724, 405)
    make_line(group, [(720, 352), (724, 352), (724, 387)], net="GND")
    make_pullup(group, 790, 268, net="+12V")
    make_line(group, [(790, 292), (832, 292)], net="HEAT+")
    make_line(group, [(845, 410), (815, 410)], net="HEAT+")
    make_line(group, [(845, 429), (760, 429), (760, 352), (727, 352)], net="HEAT-")
    make_dot(group, 690, 327, net="GATE_R")

    # Power input and DC/DC block are kept separate from heater output.
    make_pullup(group, 530, 462, net="+12V")
    make_line(group, [(530, 486), (650, 486)], net="+12V")
    make_line(group, [(700, 496), (770, 496)], net="+3V3")
    make_line(group, [(700, 515), (770, 515), (770, 522)], net="+3V3")
    make_ground(group, 700, 543)
    make_line(group, [(700, 523), (700, 525)], net="GND")
    make_line(group, [(810, 486), (845, 486)], net="+3V3")
    make_line(group, [(810, 541), (845, 541)], net="GND")

    # LED status.
    make_pullup(group, 255, 395)
    make_line(group, [(255, 441), (390, 441)], net="LED_A")
    make_line(group, [(430, 464), (470, 464), (470, 492), (449, 492)], net="LED")


def add_composite_labels(root: ET.Element) -> None:
    label_group = ET.SubElement(root, qname("g"), {"id": "codex-jlc-style-rebuilt-labels", "data-role": "rebuilt_jlc_style_labels"})
    for ref, (x, y) in ADDED_REF_LABELS.items():
        add_text(label_group, value=ref, x=x, y=y, font_size=11.0 if ref != "DD1" else 14.0, anchor="middle", role="component_ref", extra={"data-ref": ref})
    for net, (x, y) in ADDED_NET_LABELS.items():
        add_text(label_group, value=net, x=x, y=y, font_size=10.5, anchor="start", role="net_label", extra={"data-net": net})


def composite_jlc_svg(path: Path) -> str:
    tree = parse_svg(path)
    source_root = tree.getroot()
    symbols = source_symbol_groups(source_root)
    root = ET.Element(
        qname("svg"),
        {
            "xmlns": SVG_NS,
            "width": f"{COMPOSITE_VIEWBOX['width']:.3f}mm",
            "height": f"{COMPOSITE_VIEWBOX['height']:.3f}mm",
            "viewBox": f"{COMPOSITE_VIEWBOX['x']:.3f} {COMPOSITE_VIEWBOX['y']:.3f} {COMPOSITE_VIEWBOX['width']:.3f} {COMPOSITE_VIEWBOX['height']:.3f}",
            "data-role": "jlc_style_schematic_source",
            "data-layout": "module_rebuilt_from_jlc_symbols",
        },
    )
    metadata = ET.SubElement(root, qname("metadata"))
    symbol_fidelity: list[dict[str, Any]] = []
    metadata.text = json.dumps(
        {
            "source": "hardware/eda/jlc_schematic_original.svg",
            "workflow": "JLC-style faithful layout beautification",
            "layout": "JLC symbols reused per component; wires redrawn orthogonally in A1 functional zones",
            "symbol_shape_policy": "source JLC symbol group is deep-cloned unchanged, then translated only",
            "required_refs": REQUIRED_REFS,
            "required_nets": REQUIRED_NETS,
        },
        ensure_ascii=False,
    )
    background = ET.SubElement(root, qname("rect"), {"x": "0", "y": "0", "width": f"{COMPOSITE_VIEWBOX['width']:.1f}", "height": f"{COMPOSITE_VIEWBOX['height']:.1f}", "fill": "#ffffff", "stroke": "none"})
    background.set("data-role", "schematic_background")
    symbol_layer = ET.SubElement(root, qname("g"), {"id": "codex-reused-jlc-symbols", "data-role": "reused_jlc_symbol_layer"})
    for ref in REQUIRED_REFS:
        symbol = transform_symbol_to_position(symbols[ref], SOURCE_COMPONENT_BBOXES[ref], COMPOSITE_COMPONENT_POSITIONS[ref])
        symbol.set("id", f"jlc-symbol-{ref}")
        symbol.set("data-ref", ref)
        symbol.set("data-role", "jlc_symbol_exact_clone")
        symbol.set("data-source-bbox", ",".join(f"{value:g}" for value in SOURCE_COMPONENT_BBOXES[ref]))
        symbol_fidelity.append(symbol_fidelity_entry(ref, symbols[ref], symbol))
        symbol_layer.append(symbol)
    metadata.text = json.dumps(
        {
            "source": "hardware/eda/jlc_schematic_original.svg",
            "workflow": "JLC exact-symbol faithful layout refinement",
            "layout": "JLC symbols cloned per component; wires redrawn orthogonally in A1 functional zones",
            "symbol_shape_policy": "source JLC symbol group is deep-cloned unchanged, then translated only",
            "required_refs": REQUIRED_REFS,
            "required_nets": REQUIRED_NETS,
            "symbol_fidelity": symbol_fidelity,
        },
        ensure_ascii=False,
    )
    add_composite_wires(root)
    add_composite_labels(root)
    xml = ET.tostring(root, encoding="unicode")
    xml = token_replace(xml)
    forbidden = [token for token in list(REF_REPLACEMENTS) + ["J1_12V", "3V3"] if token_present(token, html.unescape(xml))]
    if forbidden:
        raise ValueError(f"Composite JLC SVG still contains forbidden source tokens: {', '.join(sorted(set(forbidden)))}")
    return xml


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
                font_size=5.7,
                anchor=anchor,
                role="pin_label",
                extra={"data-ref": "DD1", "data-pin": name, "data-pin-number": number},
            )
        add_text(
            group,
            value=number,
            x=number_x,
            y=y,
            font_size=5.0,
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
    scale = min(width / COMPOSITE_VIEWBOX["width"], height / COMPOSITE_VIEWBOX["height"])
    image_w = COMPOSITE_VIEWBOX["width"] * scale
    image_h = COMPOSITE_VIEWBOX["height"] * scale
    offset_x = x + (width - image_w) / 2
    offset_y = y + (height - image_h) / 2
    mapped_x = offset_x + (source_x - COMPOSITE_VIEWBOX["x"]) * scale
    mapped_y = offset_y + (source_y - COMPOSITE_VIEWBOX["y"]) * scale
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
    svg = composite_jlc_svg(jlc_svg)
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
