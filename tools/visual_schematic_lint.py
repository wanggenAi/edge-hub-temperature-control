#!/usr/bin/env python3
"""Visual geometry lint for the draw.io ESP32 schematic workflow.

This checker is intentionally scoped to the draw.io visual-engineering path in
`hardware/eda/`. It validates editable mxCell geometry and metadata before the
project starts generating the final middle schematic.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "hardware/eda/reserved_regions.lock.json"
DEFAULT_CONFIG = ROOT / "hardware/eda/style_rules_from_drawio.yaml"
DEFAULT_MODEL = ROOT / "hardware/eda/schematic_model.yaml"
RESERVED_CONTAINER_ROLE = "reserved_container"


@dataclass
class Finding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""
    x: float | None = None
    y: float | None = None


@dataclass
class Vertex:
    id: str
    value: str
    style: str
    parent: str
    x: float
    y: float
    width: float
    height: float
    attrs: dict[str, str]

    @property
    def role(self) -> str:
        return role_of(self.attrs)

    @property
    def kind(self) -> str:
        return self.attrs.get("data-kind", self.role)

    @property
    def text(self) -> str:
        return normalize_text(self.value)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)


@dataclass
class Edge:
    id: str
    value: str
    style: str
    parent: str
    x1: float
    y1: float
    x2: float
    y2: float
    attrs: dict[str, str]

    @property
    def role(self) -> str:
        return role_of(self.attrs)

    @property
    def kind(self) -> str:
        return self.attrs.get("data-kind", self.role)

    @property
    def net(self) -> str:
        return self.attrs.get("data-net", self.attrs.get("net", ""))

    @property
    def endpoints(self) -> list[tuple[float, float]]:
        return [(self.x1, self.y1), (self.x2, self.y2)]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (min(self.x1, self.x2), min(self.y1, self.y2), max(self.x1, self.x2), max(self.y1, self.y2))

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


class DrawioModel:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tree = ET.ElementTree(ET.fromstring(path.read_text(encoding="utf-8")))
        self.root = self.tree.getroot()
        self.cells = {cell.get("id", ""): cell for cell in self.root.findall(".//mxCell") if cell.get("id")}
        graph = self.root.find(".//mxGraphModel")
        self.page_width = fnum(graph.get("pageWidth")) if graph is not None else 0.0
        self.page_height = fnum(graph.get("pageHeight")) if graph is not None else 0.0
        self._abs_cache: dict[str, tuple[float, float]] = {}
        self.vertices: list[Vertex] = []
        self.edges: list[Edge] = []
        self._parse_cells()

    def _parse_cells(self) -> None:
        for cell_id, cell in self.cells.items():
            if cell_id in {"0", "1"}:
                continue
            geom = cell.find("mxGeometry")
            attrs = dict(cell.attrib)
            if cell.get("vertex") == "1" and geom is not None:
                ox, oy = self.absolute_origin(cell_id)
                self.vertices.append(
                    Vertex(
                        id=cell_id,
                        value=cell.get("value", ""),
                        style=cell.get("style", ""),
                        parent=cell.get("parent", ""),
                        x=ox,
                        y=oy,
                        width=fnum(geom.get("width")),
                        height=fnum(geom.get("height")),
                        attrs=attrs,
                    )
                )
            elif cell.get("edge") == "1":
                p1, p2 = self.edge_points(cell_id)
                self.edges.append(
                    Edge(
                        id=cell_id,
                        value=cell.get("value", ""),
                        style=cell.get("style", ""),
                        parent=cell.get("parent", ""),
                        x1=p1[0],
                        y1=p1[1],
                        x2=p2[0],
                        y2=p2[1],
                        attrs=attrs,
                    )
                )

    def geometry(self, cell_id: str) -> ET.Element | None:
        cell = self.cells.get(cell_id)
        return cell.find("mxGeometry") if cell is not None else None

    def absolute_origin(self, cell_id: str) -> tuple[float, float]:
        if cell_id in self._abs_cache:
            return self._abs_cache[cell_id]
        cell = self.cells[cell_id]
        geom = self.geometry(cell_id)
        x = fnum(geom.get("x")) if geom is not None else 0.0
        y = fnum(geom.get("y")) if geom is not None else 0.0
        parent = cell.get("parent", "")
        if parent and parent in self.cells and parent not in {"0", "1"}:
            px, py = self.absolute_origin(parent)
            x += px
            y += py
        self._abs_cache[cell_id] = (x, y)
        return (x, y)

    def edge_points(self, cell_id: str) -> tuple[tuple[float, float], tuple[float, float]]:
        cell = self.cells[cell_id]
        geom = self.geometry(cell_id)
        parent_offset = (0.0, 0.0)
        parent = cell.get("parent", "")
        if parent and parent in self.cells and parent not in {"0", "1"}:
            parent_offset = self.absolute_origin(parent)
        points: dict[str, tuple[float, float]] = {}
        if geom is not None:
            for point in geom.findall("mxPoint"):
                role = point.get("as", "")
                points[role] = (fnum(point.get("x")) + parent_offset[0], fnum(point.get("y")) + parent_offset[1])
        if "sourcePoint" in points and "targetPoint" in points:
            return points["sourcePoint"], points["targetPoint"]
        if geom is not None:
            x = fnum(geom.get("x")) + parent_offset[0]
            y = fnum(geom.get("y")) + parent_offset[1]
            w = fnum(geom.get("width"))
            h = fnum(geom.get("height"))
            return (x, y), (x + w, y + h)
        return (0.0, 0.0), (0.0, 0.0)


def fnum(value: str | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def normalize_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def role_of(attrs: dict[str, str]) -> str:
    return attrs.get("data-role") or attrs.get("role") or ""


def read_jsonish(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def style_value(style: str, key: str, default: str = "") -> str:
    for part in style.split(";"):
        if part.startswith(key + "="):
            return part.split("=", 1)[1]
    return default


def hash_payload(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def orthogonal(edge: Edge, tol: float = 1e-6) -> bool:
    return math.isclose(edge.x1, edge.x2, abs_tol=tol) or math.isclose(edge.y1, edge.y2, abs_tol=tol)


def intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float], margin: float = 0.0) -> bool:
    return a[2] > b[0] - margin and b[2] > a[0] - margin and a[3] > b[1] - margin and b[3] > a[1] - margin


def segment_intersects_box(edge: Edge, box: tuple[float, float, float, float], clearance: float = 0.0) -> bool:
    bx1, by1, bx2, by2 = box
    bx1 -= clearance
    by1 -= clearance
    bx2 += clearance
    by2 += clearance
    if math.isclose(edge.x1, edge.x2):
        x = edge.x1
        return bx1 <= x <= bx2 and max(min(edge.y1, edge.y2), by1) <= min(max(edge.y1, edge.y2), by2)
    if math.isclose(edge.y1, edge.y2):
        y = edge.y1
        return by1 <= y <= by2 and max(min(edge.x1, edge.x2), bx1) <= min(max(edge.x1, edge.x2), bx2)
    return intersects(edge.bbox, box, clearance)


def bbox_of_vertices(vertices: list[Vertex]) -> tuple[float, float, float, float]:
    return (
        min(v.bbox[0] for v in vertices),
        min(v.bbox[1] for v in vertices),
        max(v.bbox[2] for v in vertices),
        max(v.bbox[3] for v in vertices),
    )


def round_box(box: tuple[float, float, float, float]) -> dict[str, float]:
    x1, y1, x2, y2 = box
    return {
        "x": round(x1, 3),
        "y": round(y1, 3),
        "width": round(x2 - x1, 3),
        "height": round(y2 - y1, 3),
        "right": round(x2, 3),
        "bottom": round(y2, 3),
    }


class VisualSchematicLint:
    def __init__(self, model: DrawioModel, lock: dict[str, Any], config: dict[str, Any], schematic_model: dict[str, Any] | None = None, mode: str = "strict") -> None:
        self.model = model
        self.lock = lock
        self.schematic_model = schematic_model or {}
        self.mode = mode
        rules = config.get("quantified_visual_rules", config)
        self.connection_tol = float(rules.get("connection_tolerance_mm", 0.2))
        self.pin_label_center_tol = float(rules.get("pin_label_center_tolerance_mm", 0.5))
        self.pin_label_offset_min = float(rules.get("pin_label_vertical_offset_min_mm", 1.0))
        self.pin_label_offset_max = float(rules.get("pin_label_vertical_offset_max_mm", 3.5))
        self.text_wire_clearance = float(rules.get("min_text_to_wire_clearance_mm", 0.5))
        self.text_symbol_clearance = float(rules.get("min_text_to_symbol_clearance_mm", 0.5))
        self.component_zone_tol = float(rules.get("component_zone_tolerance_mm", 0.5))
        self.component_spacing = float(rules.get("min_component_spacing_mm", 3.0))
        self.min_local_wire_length = float(rules.get("min_local_wire_visible_length_units", 25.0))
        self.net_label_anchor_max = float(rules.get("max_net_label_anchor_distance_units", 90.0))
        reference_style = config.get("reference_component_table", {})
        style_lock = config.get("renderer_component_style_lock", {})
        self.component_common_width = float(style_lock.get("common_body_width", {}).get("value", reference_style.get("common_width", {}).get("value", 210.0)))
        self.component_width_tolerance = float(style_lock.get("common_body_width", {}).get("tolerance", 0.5))
        self.component_table_style_required = bool(style_lock.get("require_table_body_style", {}).get("value", False))
        self.component_table_line_width = float(style_lock.get("component_table_line_width", {}).get("value", self.component_common_width))
        self.component_table_line_width_tolerance = float(style_lock.get("component_table_line_width", {}).get("tolerance", 0.03))
        discrete_policy = config.get("standard_schematic_symbols", {})
        self.discrete_symbol_types: dict[str, str] = discrete_policy.get(
            "required_by_ref_prefix",
            {"R": "resistor", "C": "capacitor", "SB": "switch", "HL": "led", "VT": "nmos"},
        )
        self.rectangular_component_prefixes = tuple(discrete_policy.get("rectangular_component_prefixes", ["DD", "A", "XS"]))
        self.forbidden_visible_refs = set(config.get("forbidden_visible_refs", []))
        self.forbidden_net_names = set(config.get("forbidden_net_names", []))
        self.findings: list[Finding] = []
        self.region_boxes: dict[str, tuple[float, float, float, float]] = {}
        self.locked_cell_ids = self.collect_locked_cell_ids()
        self.locked_ancestor_ids = self.collect_locked_ancestor_ids()

    def run(self) -> list[Finding]:
        self.validate_locked_regions()
        if self.mode == "template":
            return self.findings
        self.validate_role_metadata()
        if self.mode == "generated":
            self.validate_element_list_content()
        self.validate_geometry()
        self.validate_local_wire_visibility()
        self.validate_connectivity()
        self.validate_pin_line_connectivity()
        self.validate_pin_labels()
        self.validate_text_policy()
        self.validate_text_clearance()
        self.validate_text_text_clearance()
        self.validate_component_spacing()
        self.validate_component_zones()
        self.validate_reserved_region_overlap()
        return self.findings

    def collect_locked_cell_ids(self) -> set[str]:
        locked: set[str] = set()
        for region in self.lock.get("regions", {}).values():
            locked.update(region.get("cell_ids", []))
        return locked

    def collect_locked_ancestor_ids(self) -> set[str]:
        ancestors: set[str] = set()
        for cell_id in self.locked_cell_ids:
            cell = self.model.cells.get(cell_id)
            while cell is not None:
                parent = cell.get("parent", "")
                if not parent or parent in {"0", "1"} or parent in self.locked_cell_ids:
                    break
                ancestors.add(parent)
                cell = self.model.cells.get(parent)
        return ancestors

    def error(self, code: str, object_id: str, message: str, expected: str = "", actual: str = "", x: float | None = None, y: float | None = None) -> None:
        self.findings.append(Finding(code=code, severity="error", object_id=object_id, message=message, expected=expected, actual=actual, x=x, y=y))

    def validate_locked_regions(self) -> None:
        regions = self.lock.get("regions", {})
        for name, expected in regions.items():
            ids = expected.get("cell_ids", [])
            cells = [self.model.cells.get(cell_id) for cell_id in ids]
            if any(cell is None for cell in cells):
                missing = [cell_id for cell_id, cell in zip(ids, cells) if cell is None]
                self.error(self.region_code(name), name, f"Locked region cells are missing: {missing}", "all locked cell ids present", ",".join(missing))
                continue
            vertices = [v for v in self.model.vertices if v.id in ids]
            if len(ids) != int(expected.get("cell_count", len(ids))):
                self.error(self.region_code(name), name, "Locked region cell_count in lock file is inconsistent", str(expected.get("cell_count")), str(len(ids)))
            if vertices:
                actual_box = round_box(bbox_of_vertices(vertices))
                expected_box = expected.get("bbox", {})
                self.region_boxes[name] = (
                    float(expected_box.get("x", actual_box["x"])),
                    float(expected_box.get("y", actual_box["y"])),
                    float(expected_box.get("right", actual_box["right"])),
                    float(expected_box.get("bottom", actual_box["bottom"])),
                )
                for key in ("x", "y", "width", "height", "right", "bottom"):
                    if key in expected_box and abs(float(expected_box[key]) - actual_box[key]) > 0.01:
                        self.error(self.region_code(name), name, f"Locked region bbox {key} changed", str(expected_box[key]), str(actual_box[key]))
                        break
            if self.lock.get("hash_schema") == "visual_schematic_lint_v1":
                actual_hashes = self.compute_region_hashes(ids)
                for key in ("style_hash", "geometry_hash", "value_hash", "combined_hash"):
                    if expected.get(key) and expected[key] != actual_hashes[key]:
                        self.error(self.region_code(name), name, f"Locked region {key} changed", expected[key], actual_hashes[key])

    def region_code(self, name: str) -> str:
        return "FRAME_CHANGED" if name == "outer_frame" else "TABLE_CHANGED"

    def compute_region_hashes(self, ids: list[str]) -> dict[str, str]:
        style_items = []
        geometry_items = []
        value_items = []
        for cell_id in sorted(ids):
            cell = self.model.cells[cell_id]
            style_items.append({"id": cell_id, "style": cell.get("style", "")})
            value_items.append({"id": cell_id, "value": cell.get("value", "")})
            vertex = next((v for v in self.model.vertices if v.id == cell_id), None)
            if vertex:
                geometry_items.append({"id": cell_id, **round_box(vertex.bbox)})
            else:
                geometry_items.append({"id": cell_id})
        style_hash = hash_payload(style_items)
        geometry_hash = hash_payload(geometry_items)
        value_hash = hash_payload(value_items)
        combined_hash = hash_payload({"style_hash": style_hash, "geometry_hash": geometry_hash, "value_hash": value_hash})
        return {
            "style_hash": style_hash,
            "geometry_hash": geometry_hash,
            "value_hash": value_hash,
            "combined_hash": combined_hash,
        }

    def validate_role_metadata(self) -> None:
        allowed = {
            RESERVED_CONTAINER_ROLE,
            "outer_frame",
            "element_list",
            "element_list_line",
            "element_list_text",
            "title_block",
            "drawing_frame",
            "component_body",
            "component_ref",
            "component_value",
            "component_table_line",
            "symbol_primitive",
            "pin",
            "pin_label",
            "wire",
            "net_label",
            "junction",
            "schematic_root",
        }
        for item in [*self.model.vertices, *self.model.edges]:
            if item.id in self.locked_cell_ids:
                continue
            if item.id in self.locked_ancestor_ids:
                if item.role != RESERVED_CONTAINER_ROLE:
                    self.error("UNCLASSIFIED_OBJECT", item.id, "Locked-region ancestor container must be marked as reserved_container", RESERVED_CONTAINER_ROLE, item.role)
                continue
            if not item.role:
                self.error("UNCLASSIFIED_OBJECT", item.id, "mxCell is missing data-role metadata")
            elif item.role not in allowed:
                self.error("UNCLASSIFIED_OBJECT", item.id, f"mxCell has unsupported data-role {item.role}", "known role", item.role)
            elif self.mode == "generated":
                self.validate_generated_metadata(item)

    def validate_generated_metadata(self, item: Vertex | Edge) -> None:
        required_by_role = {
            "schematic_root": ["data-generated", "data-owner", "data-zone"],
            "component_body": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-zone"],
            "component_ref": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-zone"],
            "component_value": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-zone"],
            "component_table_line": ["data-generated", "data-owner", "data-ref", "data-line-type", "data-style-source"],
            "symbol_primitive": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-zone", "data-symbol-type", "data-kind"],
            "pin": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-pin", "data-pin-number", "data-net", "data-source-net", "data-zone"],
            "pin_label": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-pin", "data-pin-number", "data-net", "data-source-net", "data-zone"],
            "wire": ["data-generated", "data-owner", "data-ref", "data-source-ref", "data-pin", "data-pin-number", "data-net", "data-source-net", "data-zone"],
            "net_label": ["data-generated", "data-owner", "data-net", "data-source-net", "data-zone", "data-anchor-x", "data-anchor-y"],
            "junction": ["data-generated", "data-owner", "data-net", "data-source-net", "data-zone"],
            "element_list_line": ["data-generated", "data-owner", "data-region", "data-line-type"],
            "element_list_text": ["data-generated", "data-owner", "data-region", "data-row-type", "data-column"],
        }
        missing = [key for key in required_by_role.get(item.role, []) if not item.attrs.get(key)]
        if item.attrs.get("data-generated") not in {"true", "false", None}:
            missing.append("valid data-generated")
        if missing:
            self.error("MISSING_ROLE_METADATA", item.id, "Generated object is missing required role metadata", ",".join(required_by_role.get(item.role, [])), ",".join(missing), *item.center)

    def validate_element_list_content(self) -> None:
        texts = [v for v in self.model.vertices if v.role == "element_list_text"]
        lines = [e for e in self.model.edges if e.role == "element_list_line"]
        visible = " ".join(text.text for text in texts)
        required_text = [
            "Position number",
            "Name",
            "Qty.",
            "Note",
            "Capacitors",
            "Resistors",
            "Semiconductor Devices",
            "Switching Components",
            "Connectors",
            "Power Modules",
            "ESP32-WROOM-32 module",
            "XH-3PA 3-pin sensor connector",
            "KF301-2P thermal switch terminal",
            "XS5",
            "A1",
        ]
        if not texts:
            self.error("ELEMENT_LIST_CONTENT_MISSING", "element_list", "Generated List of Elements has no text cells", "element_list_text cells", "0")
        if len(lines) < 4:
            self.error("ELEMENT_LIST_LINES_MISSING", "element_list", "Generated List of Elements has too few line cells", ">= 4 element_list_line cells", str(len(lines)))
        for value in required_text:
            if value not in visible:
                self.error("ELEMENT_LIST_REQUIRED_TEXT_MISSING", "element_list", "Generated List of Elements is missing required visible text", value, "not found")

    def validate_geometry(self) -> None:
        for edge in self.wires():
            if not orthogonal(edge):
                self.error("DIAGONAL_WIRE", edge.id, "Wire is not horizontal or vertical", "angle 0 or 90 degrees", f"({edge.x1},{edge.y1}) -> ({edge.x2},{edge.y2})", *edge.center)

    def validate_local_wire_visibility(self) -> None:
        if self.mode != "generated":
            return
        local_wires = [
            edge for edge in self.wires()
            if edge.id.startswith("wire.local.")
            and edge.attrs.get("data-zone") in {"mosfet_heater_driver", "dcdc_power_module"}
        ]
        for wire in local_wires:
            if wire.length <= 1e-6:
                self.error(
                    "ZERO_LENGTH_WIRE",
                    wire.id,
                    "Local wire has identical source and target points and can disappear in exports",
                    "> 0",
                    f"{wire.length:.3f}",
                    *wire.center,
                )
                continue
            if wire.length < self.min_local_wire_length:
                self.error(
                    "LOCAL_WIRE_TOO_SHORT",
                    wire.id,
                    "Local heater/power wire is shorter than the configured visible length",
                    f">= {self.min_local_wire_length}",
                    f"{wire.length:.3f}",
                    *wire.center,
                )
        for required_net in {"GATE_R", "HEAT-"}:
            total = sum(wire.length for wire in local_wires if wire.net == required_net)
            if total and total < self.min_local_wire_length:
                self.error(
                    "LOCAL_NET_VISIBILITY_WEAK",
                    f"local-net.{required_net}",
                    "Local net is represented only by very short linework",
                    f">= {self.min_local_wire_length}",
                    f"{total:.3f}",
                )
        for label in [v for v in self.model.vertices if v.role == "net_label"]:
            anchor = (fnum(label.attrs.get("data-anchor-x"), label.center[0]), fnum(label.attrs.get("data-anchor-y"), label.center[1]))
            anchor_distance = dist(label.center, anchor)
            if anchor_distance > self.net_label_anchor_max:
                self.error(
                    "NET_LABEL_TOO_FAR_FROM_ANCHOR",
                    label.id,
                    "Net label center is too far from its declared wire/pin anchor",
                    f"<= {self.net_label_anchor_max}",
                    f"{anchor_distance:.3f}",
                    *label.center,
                )

    def validate_connectivity(self) -> None:
        connection_points = self.connection_points()
        for wire in self.wires():
            if not wire.net:
                self.error("WIRE_MISSING_NET_METADATA", wire.id, "Wire is missing data-net metadata")
            other_wire_points = [p for other in self.wires() if other.id != wire.id for p in other.endpoints]
            for point in wire.endpoints:
                candidates = connection_points + other_wire_points
                nearest = min((dist(point, p) for p in candidates), default=math.inf)
                if nearest <= self.connection_tol:
                    continue
                pin_nearest = min((dist(point, p) for p in self.pin_points()), default=math.inf)
                if pin_nearest <= 5.0:
                    self.error("WIRE_ENDPOINT_NOT_CONNECTED", wire.id, "Wire endpoint is close to a pin but not connected within tolerance", f"<= {self.connection_tol}", f"{pin_nearest:.3f}", point[0], point[1])
                else:
                    self.error("FLOATING_WIRE_END", wire.id, "Wire endpoint is not connected to a pin, junction, net label, or another wire", f"<= {self.connection_tol}", f"{nearest:.3f}", point[0], point[1])

    def validate_pin_line_connectivity(self) -> None:
        if self.mode != "generated":
            return
        wire_points = [p for wire in self.wires() for p in wire.endpoints]
        label_points = [
            (fnum(label.attrs.get("data-anchor-x"), label.center[0]), fnum(label.attrs.get("data-anchor-y"), label.center[1]))
            for label in self.model.vertices
            if label.role == "net_label"
        ]
        junction_points = [v.center for v in self.model.vertices if v.role == "junction"]
        external_points = wire_points + label_points + junction_points
        for pin in self.pin_edges():
            if not pin.attrs.get("data-pin-number"):
                self.error("PIN_NUMBER_MISSING", pin.id, "Rendered pin line is missing a pin number", "data-pin-number", "", *pin.center)
            nearest = min((dist(point, candidate) for point in pin.endpoints for candidate in external_points), default=math.inf)
            if nearest > self.connection_tol:
                self.error(
                    "PIN_LINE_NOT_CONNECTED",
                    pin.id,
                    "Pin line has no endpoint connected to a wire, junction, or net label anchor",
                    f"<= {self.connection_tol}",
                    f"{nearest:.3f}",
                    *pin.center,
                )

    def connection_points(self) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        points.extend(self.pin_points())
        for vertex in self.model.vertices:
            if vertex.role == "junction":
                points.append(vertex.center)
            elif vertex.role == "net_label":
                points.append((fnum(vertex.attrs.get("data-anchor-x"), vertex.center[0]), fnum(vertex.attrs.get("data-anchor-y"), vertex.center[1])))
        return points

    def pin_points(self) -> list[tuple[float, float]]:
        return [p for pin in self.pin_edges() for p in pin.endpoints]

    def validate_pin_labels(self) -> None:
        pins = {pin_binding_key(pin): pin for pin in self.pin_edges()}
        for label in [v for v in self.model.vertices if v.role == "pin_label"]:
            key = pin_binding_key(label)
            pin = pins.get(key)
            if pin is None:
                self.error("PIN_LABEL_NOT_BOUND_TO_PIN", label.id, "Pin label is not bound to a rendered pin", "matching data-ref/data-pin pin", str(key), *label.center)
                continue
            if not math.isclose(pin.y1, pin.y2, abs_tol=1e-6):
                continue
            if label.attrs.get("data-label-policy") == "inside_table_row":
                row_error = abs(label.center[1] - pin.y1)
                if row_error > 0.5:
                    self.error("PIN_LABEL_MISALIGNED", label.id, "Pin label is not vertically centered in the referenced table row", "<= 0.5", f"{row_error:.3f}", *label.center)
                body = next((candidate for candidate in self.model.vertices if candidate.role == "component_body" and candidate.attrs.get("data-ref") == label.attrs.get("data-ref")), None)
                if body is None or not bbox_inside(label.bbox, body.bbox):
                    self.error("PIN_LABEL_MISALIGNED", label.id, "Pin label is not inside its reference table component body", "label bbox inside component body", str(round_box(label.bbox)), *label.center)
                continue
            center_error = abs(label.center[0] - pin.center[0])
            vertical_offset = pin.y1 - label.bbox[3]
            if center_error > self.pin_label_center_tol:
                self.error("PIN_LABEL_MISALIGNED", label.id, "Pin label center_x is not aligned with pin line center_x", f"<= {self.pin_label_center_tol}", f"{center_error:.3f}", *label.center)
            if vertical_offset < self.pin_label_offset_min or vertical_offset > self.pin_label_offset_max:
                self.error("PIN_LABEL_MISALIGNED", label.id, "Pin label vertical offset is outside the allowed band above the pin line", f"{self.pin_label_offset_min}..{self.pin_label_offset_max}", f"{vertical_offset:.3f}", *label.center)

    def validate_text_clearance(self) -> None:
        text_roles = {"component_ref", "component_value", "pin_label", "net_label"}
        text_vertices = [v for v in self.model.vertices if v.role in text_roles]
        for text in text_vertices:
            for wire in self.wires():
                if segment_intersects_box(wire, text.bbox, self.text_wire_clearance):
                    self.error("TEXT_OVERLAPS_WIRE", text.id, "Text bbox touches or overlaps a wire clearance zone", f"> {self.text_wire_clearance} clearance", wire.id, *text.center)
                    break
            for body in [v for v in self.model.vertices if v.role == "component_body" and v.attrs.get("data-ref") != text.attrs.get("data-ref")]:
                if intersects(text.bbox, body.bbox, self.text_symbol_clearance):
                    self.error("TEXT_OVERLAPS_SYMBOL", text.id, "Text bbox touches or overlaps another component symbol clearance zone", f"> {self.text_symbol_clearance} clearance", body.id, *text.center)
                    break

    def validate_text_text_clearance(self) -> None:
        if self.mode != "generated":
            return
        text_roles = {"component_ref", "component_value", "pin_label", "net_label"}
        text_vertices = [v for v in self.model.vertices if v.role in text_roles]
        for index, first in enumerate(text_vertices):
            for second in text_vertices[index + 1:]:
                if intersects(first.bbox, second.bbox, self.text_symbol_clearance):
                    self.error(
                        "TEXT_OVERLAPS_TEXT",
                        f"{first.id},{second.id}",
                        "Generated text labels overlap or touch each other",
                        f"> {self.text_symbol_clearance} clearance",
                        str(round_box(second.bbox)),
                        *first.center,
                    )
                    break

    def validate_text_policy(self) -> None:
        for vertex in self.model.vertices:
            if vertex.role not in {"component_ref", "component_value", "pin_label", "net_label"}:
                continue
            text = vertex.text
            if text in self.forbidden_visible_refs:
                self.error("STALE_VISIBLE_REF", vertex.id, "Visible text uses a source ref instead of a confirmed thesis ref", "confirmed thesis ref", text, *vertex.center)
            if text in self.forbidden_net_names:
                self.error("STALE_NET_NAME", vertex.id, "Visible text uses a stale net name instead of a canonical net name", "canonical net name", text, *vertex.center)
        for edge in self.model.edges:
            net = edge.net
            if net in self.forbidden_net_names:
                self.error("STALE_NET_NAME", edge.id, "Generated edge uses a stale net name instead of a canonical net name", "canonical net name", net, *edge.center)

    def validate_component_spacing(self) -> None:
        bodies = [v for v in self.model.vertices if v.role == "component_body"]
        self.validate_reference_component_style(bodies)
        for index, first in enumerate(bodies):
            for second in bodies[index + 1:]:
                spacing = bbox_gap(first.bbox, second.bbox)
                if spacing < self.component_spacing:
                    self.error(
                        "COMPONENT_SPACING_TOO_SMALL",
                        f"{first.id},{second.id}",
                        "Generated component bodies are closer than configured minimum spacing",
                        f">= {self.component_spacing}",
                        f"{spacing:.3f}",
                        *first.center,
                    )

    def validate_reference_component_style(self, bodies: list[Vertex]) -> None:
        if self.mode != "generated":
            return
        primitives_by_ref: dict[str, list[Vertex | Edge]] = {}
        for primitive in [*self.model.vertices, *self.model.edges]:
            if primitive.role == "symbol_primitive":
                primitives_by_ref.setdefault(primitive.attrs.get("data-ref", ""), []).append(primitive)
        for body in bodies:
            ref = body.attrs.get("data-ref", "")
            required_symbol_type = self.required_symbol_type(ref)
            if required_symbol_type:
                if "shape=table" in body.style:
                    self.error(
                        "FORBIDDEN_TABLE_STYLE_FOR_DISCRETE_SYMBOL",
                        body.id,
                        "Discrete schematic components must be rendered as electrical symbols, not table rectangles",
                        f"{required_symbol_type} symbol primitives",
                        body.style,
                        *body.center,
                    )
                if body.attrs.get("data-style-lock") != "standard_symbol_component":
                    self.error(
                        "FORBIDDEN_RANDOM_SYMBOL_GEOMETRY",
                        body.id,
                        "Discrete component body is missing the standard symbol style lock",
                        "data-style-lock=standard_symbol_component",
                        body.attrs.get("data-style-lock", ""),
                        *body.center,
                    )
                primitives = primitives_by_ref.get(ref, [])
                matching = [primitive for primitive in primitives if primitive.attrs.get("data-symbol-type") == required_symbol_type]
                if not matching:
                    self.error(
                        "REQUIRED_SYMBOL_SHAPE_MISSING",
                        body.id,
                        "Discrete component is missing required schematic symbol primitives",
                        required_symbol_type,
                        ",".join(sorted({primitive.attrs.get("data-symbol-type", "") for primitive in primitives})),
                        *body.center,
                    )
                for primitive in primitives:
                    if primitive.attrs.get("data-symbol-type") != required_symbol_type:
                        self.error(
                            "FORBIDDEN_RANDOM_SYMBOL_GEOMETRY",
                            primitive.id,
                            "Symbol primitive has an unexpected symbol type for its reference designator",
                            required_symbol_type,
                            primitive.attrs.get("data-symbol-type", ""),
                            *primitive.center,
                        )
                continue
            if abs(body.width - self.component_common_width) > self.component_width_tolerance:
                self.error(
                    "COMPONENT_BODY_WIDTH_NOT_LOCKED",
                    body.id,
                    "Generated component body width does not match the reference draw.io component width lock",
                    f"{self.component_common_width} +/- {self.component_width_tolerance}",
                    f"{body.width:.3f}",
                    *body.center,
                )
            if body.attrs.get("data-style-lock") != "reference_table_component":
                self.error(
                    "COMPONENT_STYLE_LOCK_MISSING",
                    body.id,
                    "Generated component body is missing the reference table style lock metadata",
                    "data-style-lock=reference_table_component",
                    body.attrs.get("data-style-lock", ""),
                    *body.center,
                )
            if self.component_table_style_required and "shape=table" not in body.style:
                self.error(
                    "COMPONENT_BODY_STYLE_NOT_REFERENCE_TABLE",
                    body.id,
                    "Generated component body is not rendered with the reference draw.io table style",
                    "shape=table",
                    body.style,
                    *body.center,
                )
        for line in [edge for edge in self.model.edges if edge.role == "component_table_line"]:
            if not orthogonal(line):
                self.error("COMPONENT_TABLE_LINE_NOT_ORTHOGONAL", line.id, "Component table divider is not horizontal or vertical", "orthogonal", f"({line.x1},{line.y1})->({line.x2},{line.y2})", *line.center)
            stroke = fnum(style_value(line.style, "strokeWidth"), 0.0)
            if abs(stroke - self.component_table_line_width) > self.component_table_line_width_tolerance:
                self.error(
                    "COMPONENT_TABLE_LINE_WIDTH_INVALID",
                    line.id,
                    "Component table line width does not match the reference style lock",
                    f"{self.component_table_line_width} +/- {self.component_table_line_width_tolerance}",
                    f"{stroke:.4f}",
                    *line.center,
                )

    def required_symbol_type(self, ref: str) -> str:
        if ref.startswith("SB"):
            return self.discrete_symbol_types.get("SB", "")
        if ref.startswith("HL"):
            return self.discrete_symbol_types.get("HL", "")
        if ref.startswith("VT"):
            return self.discrete_symbol_types.get("VT", "")
        prefix = ref[:1]
        return self.discrete_symbol_types.get(prefix, "")

    def validate_reserved_region_overlap(self) -> None:
        if not self.region_boxes:
            return
        schematic_vertices = [v for v in self.model.vertices if v.role in {"component_body", "component_ref", "component_value", "pin_label", "net_label", "junction", "symbol_primitive"}]
        schematic_edges = [e for e in self.model.edges if e.role in {"wire", "pin", "symbol_primitive"}]
        for region_name in ("element_list", "title_block"):
            box = self.region_boxes.get(region_name)
            if not box:
                continue
            code = "SCHEMATIC_OVERLAPS_ELEMENT_LIST" if region_name == "element_list" else "SCHEMATIC_OVERLAPS_TITLE_BLOCK"
            for vertex in schematic_vertices:
                if intersects(vertex.bbox, box):
                    self.error(code, vertex.id, f"Schematic object overlaps reserved {region_name} region", "no overlap", str(round_box(vertex.bbox)), *vertex.center)
            for edge in schematic_edges:
                if segment_intersects_box(edge, box):
                    self.error(code, edge.id, f"Schematic line overlaps reserved {region_name} region", "no overlap", str(edge.bbox), *edge.center)

    def validate_component_zones(self) -> None:
        if self.mode != "generated":
            return
        zones = self.schematic_model.get("layout_zones", {})
        if not isinstance(zones, dict) or not zones:
            return
        ref_to_zone: dict[str, tuple[str, dict[str, Any]]] = {}
        for zone_name, zone in zones.items():
            for ref in zone.get("refs", []):
                ref_to_zone[ref] = (zone_name, zone)
        for vertex in self.model.vertices:
            if vertex.role != "component_body":
                continue
            ref = vertex.attrs.get("data-ref", "")
            if not ref:
                continue
            zone_info = ref_to_zone.get(ref)
            if not zone_info:
                self.error("COMPONENT_ZONE_UNKNOWN", vertex.id, "Component ref is not assigned to a known layout zone", "ref in layout_zones", ref, *vertex.center)
                continue
            zone_name, zone = zone_info
            expected = (
                float(zone.get("x_min", -math.inf)) - self.component_zone_tol,
                float(zone.get("y_min", -math.inf)) - self.component_zone_tol,
                float(zone.get("x_max", math.inf)) + self.component_zone_tol,
                float(zone.get("y_max", math.inf)) + self.component_zone_tol,
            )
            if not bbox_inside(vertex.bbox, expected):
                self.error(
                    "COMPONENT_ZONE_VIOLATION",
                    vertex.id,
                    f"Component body is outside its assigned {zone_name} layout zone",
                    str(round_box(expected)),
                    str(round_box(vertex.bbox)),
                    *vertex.center,
                )

    def wires(self) -> list[Edge]:
        return [edge for edge in self.model.edges if edge.role == "wire"]

    def pin_edges(self) -> list[Edge]:
        return [edge for edge in self.model.edges if edge.role == "pin"]


def pin_binding_key(item: Vertex | Edge) -> tuple[str, str, str]:
    return (
        item.attrs.get("data-ref", ""),
        item.attrs.get("data-pin", ""),
        item.attrs.get("data-pin-number", ""),
    )


def bbox_inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def bbox_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    if intersects(a, b):
        return 0.0
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def write_reports(findings: list[Finding], reports_dir: Path, source: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": str(source),
        "error_count": sum(1 for f in findings if f.severity == "error"),
        "findings": [asdict(f) for f in findings],
    }
    (reports_dir / "visual_schematic_lint.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Visual Schematic Lint Report",
        "",
        f"- Source: `{source}`",
        f"- Errors: {payload['error_count']}",
        "",
    ]
    if findings:
        lines.append("## Findings")
        for finding in findings:
            loc = "" if finding.x is None else f" at ({finding.x:.3f}, {finding.y:.3f})"
            lines.append(f"- **{finding.code}** `{finding.object_id}`{loc}: {finding.message}")
    else:
        lines.append("No visual schematic lint errors.")
    (reports_dir / "visual_schematic_lint.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint draw.io visual schematic geometry and metadata.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--schematic-model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "build/reports")
    parser.add_argument("--mode", choices=("strict", "generated", "template"), default="strict", help="template mode checks locked regions only; strict/generated mode requires metadata for generated schematic objects.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source.exists():
        print(f"source missing: {args.source}", file=sys.stderr)
        return 2
    if not args.lock_file.exists():
        print(f"lock file missing: {args.lock_file}", file=sys.stderr)
        return 2
    config = read_jsonish(args.config) if args.config.exists() else {}
    schematic_model = read_jsonish(args.schematic_model) if args.schematic_model.exists() else {}
    lock = read_jsonish(args.lock_file)
    model = DrawioModel(args.source)
    findings = VisualSchematicLint(model, lock, config, schematic_model=schematic_model, mode=args.mode).run()
    write_reports(findings, args.reports_dir, args.source)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
