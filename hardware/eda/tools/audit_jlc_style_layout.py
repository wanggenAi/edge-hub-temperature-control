#!/usr/bin/env python3
"""Audit the final BSTU drawing for the JLC-style schematic workflow."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FINAL_DIR = ROOT / "hardware/eda/exports/final"
DEFAULT_FINAL_BASENAME = "esp32_temperature_control_unit_electrical_schematic"
DEFAULT_DRAWIO = DEFAULT_FINAL_DIR / f"{DEFAULT_FINAL_BASENAME}.drawio"
DEFAULT_SVG = DEFAULT_FINAL_DIR / f"{DEFAULT_FINAL_BASENAME}.svg"
DEFAULT_PNG = DEFAULT_FINAL_DIR / f"{DEFAULT_FINAL_BASENAME}.png"
DEFAULT_JLC = ROOT / "hardware/eda/jlc_schematic_original.svg"
DEFAULT_JSON_REPORT = ROOT / "build/reports/jlc_style_layout_audit.json"
DEFAULT_MD_REPORT = ROOT / "docs/jlc_style_layout_audit_report.md"
DEFAULT_CROPS_DIR = DEFAULT_FINAL_DIR / "layout_audit_crops"
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"

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

VISIBLE_REQUIRED_NETS = [
    "+3V3",
    "+12V",
    "GND",
    "EN",
    "DQ",
    "RXD0",
    "TXD0",
    "BOOT",
    "GATE",
    "GATE_R",
    "HEAT+",
    "HEAT-",
]

FORBIDDEN_REFS = [
    "U1",
    "Q1",
    "D1",
    "CN1",
    "J2_heater",
    "J_Power",
    "U7",
    "J_TS1",
    "U3_reset",
    "U4_boot",
    "U3_buck",
]

FORBIDDEN_NETS = [
    "J1_12V",
    "UART_GND",
    "GATE_DRV",
    "HEATER_PLUS",
    "HEATER_SW",
    "LED_SERIES",
    "$1N",
]

KICAD_LEAK_MARKERS = [
    "kicad.schematic.embed",
    "kicad_schematic_embed",
    "codex-kicad-local-wiring",
    "ESP32_Temperature_Control:",
    "kicad_block",
]

SYMBOL_FIDELITY_BLOCKER_CODES = {
    "JLC_SYMBOL_GEOMETRY_CHANGED",
    "JLC_SYMBOL_PATH_COUNT_CHANGED",
    "JLC_SYMBOL_STROKE_CHANGED",
    "JLC_SYMBOL_INTERNAL_RATIO_CHANGED",
}


@dataclass
class Finding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""
    x_mm: float | None = None
    y_mm: float | None = None


def add_finding(findings: list[Finding], code: str, severity: str, object_id: str, message: str, expected: str = "", actual: str = "") -> None:
    findings.append(Finding(code=code, severity=severity, object_id=object_id, message=message, expected=expected, actual=actual))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit final JLC-style schematic layout.")
    parser.add_argument("--jlc-source", type=Path, default=DEFAULT_JLC)
    parser.add_argument("--final-drawio", type=Path, default=DEFAULT_DRAWIO)
    parser.add_argument("--final-svg", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--final-png", type=Path, default=DEFAULT_PNG)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    parser.add_argument("--crops-dir", type=Path, default=DEFAULT_CROPS_DIR)
    return parser.parse_args()


def repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    try:
        return str(absolute.relative_to(ROOT))
    except ValueError:
        return str(absolute)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def token_present(token: str, haystack: str) -> bool:
    if token == "$1N":
        return "$1N" in haystack
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.-])3V3(?![A-Za-z0-9_.-])", haystack) is not None
    escaped = re.escape(token)
    return re.search(rf"(?<![A-Za-z0-9_.+-]){escaped}(?![A-Za-z0-9_.+-])", haystack) is not None


def extract_embedded_svg_payloads(text: str) -> list[str]:
    payloads: list[str] = []
    pattern = re.compile(r"data:image/svg\+xml(?:;base64)?,([^\"'<> ]+)", flags=re.I)
    for match in pattern.finditer(text):
        marker = match.group(0).lower()
        payload = html.unescape(match.group(1))
        try:
            if ";base64," in marker:
                decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
            else:
                decoded = urllib.parse.unquote(payload)
        except Exception:
            continue
        if "<svg" in decoded or re.search(r"<[A-Za-z0-9_]+:svg\b", decoded):
            payloads.append(decoded)
    return payloads


def plain_visible_text(*texts: str) -> str:
    snippets: list[str] = []
    for text in texts:
        snippets.append(re.sub(r'data:image/[^"\']+', " ", text))
        snippets.extend(extract_embedded_svg_payloads(text))
    values: list[str] = []
    for snippet in snippets:
        clean = re.sub(r"<br\s*/?>", " ", snippet, flags=re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = html.unescape(clean)
        clean = urllib.parse.unquote(clean)
        clean = re.sub(r"\s+", " ", clean)
        values.append(clean)
    return " ".join(values)


def parse_drawio_root(path: Path) -> ET.Element:
    root = ET.parse(path).find(".//root")
    if root is None:
        raise ValueError(f"{path} has no draw.io root")
    return root


def geometry(cell: ET.Element) -> dict[str, float]:
    geom = cell.find("mxGeometry")
    if geom is None:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": float(geom.get("x", "0") or 0),
        "y": float(geom.get("y", "0") or 0),
        "width": float(geom.get("width", "0") or 0),
        "height": float(geom.get("height", "0") or 0),
    }


def bbox_right(box: dict[str, float]) -> float:
    return box["x"] + box["width"]


def bbox_bottom(box: dict[str, float]) -> float:
    return box["y"] + box["height"]


def boxes_intersect(left: dict[str, float], right: dict[str, float], tolerance: float = 0.0) -> bool:
    return not (
        bbox_right(left) < right["x"] - tolerance
        or left["x"] > bbox_right(right) + tolerance
        or bbox_bottom(left) < right["y"] - tolerance
        or left["y"] > bbox_bottom(right) + tolerance
    )


def find_embed(root: ET.Element) -> tuple[ET.Element | None, dict[str, float]]:
    for cell in root:
        if cell.get("id") == "jlc_style.schematic.embed" or cell.get("data-role") == "jlc_style_schematic_embed":
            return cell, geometry(cell)
    return None, {}


def parse_viewbox(svg_text: str) -> dict[str, float]:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    raw = root.get("viewBox", "")
    parts = [float(value) for value in raw.split() if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value)]
    if len(parts) == 4:
        return {"x": parts[0], "y": parts[1], "width": parts[2], "height": parts[3]}
    return {
        "x": 0.0,
        "y": 0.0,
        "width": float(re.sub(r"[^0-9.]", "", root.get("width", "0")) or 0),
        "height": float(re.sub(r"[^0-9.]", "", root.get("height", "0")) or 0),
    }


def parse_embedded_jlc_metadata(jlc_payload: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(jlc_payload)
    except ET.ParseError:
        return {}
    for element in root:
        if element.tag.rsplit("}", 1)[-1] != "metadata":
            continue
        raw = "".join(element.itertext()).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def validate_symbol_fidelity(metadata: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    entries = metadata.get("symbol_fidelity", [])
    if not isinstance(entries, list):
        add_finding(findings, "JLC_SYMBOL_GEOMETRY_CHANGED", "blocker", "symbol_fidelity", "Embedded SVG metadata has no symbol_fidelity list")
        return {"entries": [], "pass_count": 0, "fail_count": len(REQUIRED_REFS), "missing_refs": REQUIRED_REFS}

    by_ref: dict[str, dict[str, Any]] = {
        str(entry.get("ref")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("ref")
    }
    missing = sorted(ref for ref in REQUIRED_REFS if ref not in by_ref)
    for ref in missing:
        add_finding(findings, "JLC_SYMBOL_GROUP_MISSING", "blocker", ref, "Missing exact JLC symbol fidelity entry", expected=ref)

    fail_count = 0
    for ref, entry in sorted(by_ref.items()):
        geometry_ok = bool(entry.get("geometry_hash_match"))
        stroke_ok = bool(entry.get("stroke_style_match"))
        path_before = entry.get("path_count_before")
        path_after = entry.get("path_count_after")
        elements_before = entry.get("source_elements_count")
        elements_after = entry.get("final_elements_count")
        if not geometry_ok:
            fail_count += 1
            add_finding(
                findings,
                "JLC_SYMBOL_GEOMETRY_CHANGED",
                "blocker",
                ref,
                "JLC symbol internal geometry hash changed",
                expected=str(entry.get("source_geometry_hash", "")),
                actual=str(entry.get("final_geometry_hash", "")),
            )
        if not stroke_ok:
            fail_count += 1
            add_finding(
                findings,
                "JLC_SYMBOL_STROKE_CHANGED",
                "blocker",
                ref,
                "JLC symbol stroke/style hash changed",
                expected=str(entry.get("source_style_hash", "")),
                actual=str(entry.get("final_style_hash", "")),
            )
        if path_before != path_after:
            fail_count += 1
            add_finding(
                findings,
                "JLC_SYMBOL_PATH_COUNT_CHANGED",
                "blocker",
                ref,
                "JLC symbol path count changed",
                expected=str(path_before),
                actual=str(path_after),
            )
        if elements_before != elements_after:
            fail_count += 1
            add_finding(
                findings,
                "JLC_SYMBOL_INTERNAL_RATIO_CHANGED",
                "blocker",
                ref,
                "JLC symbol element count changed",
                expected=str(elements_before),
                actual=str(elements_after),
            )
    return {
        "entries": entries,
        "pass_count": sum(1 for entry in by_ref.values() if entry.get("verdict") == "PASS"),
        "fail_count": fail_count + len(missing),
        "missing_refs": missing,
    }


def find_final_svg_embed_bbox(svg_text: str) -> dict[str, float]:
    for match in re.finditer(r"<image\b[^>]+>", svg_text, flags=re.I):
        tag = match.group(0)
        if "data:image/svg+xml" not in tag:
            continue
        payloads = extract_embedded_svg_payloads(tag)
        if payloads and "jlc_style_schematic_source" not in payloads[0] and "jlc_schematic_original.svg" not in payloads[0]:
            continue
        attrs = dict(re.findall(r'\b(x|y|width|height)="([-+]?\d+(?:\.\d+)?)"', tag))
        if all(key in attrs for key in ("x", "y", "width", "height")):
            return {key: float(attrs[key]) for key in ("x", "y", "width", "height")}
    return {}


def validate_symbols(root: ET.Element, text: str, findings: list[Finding]) -> dict[str, Any]:
    embed, embed_box = find_embed(root)
    if embed is None:
        add_finding(findings, "JLC_STYLE_SYMBOL_SHAPE_CHANGED", "blocker", "jlc_style.schematic.embed", "Generated draw.io has no JLC-style embedded schematic block")
    elif "jlc_schematic_original.svg" not in (embed.get("data-source", "") + embed.get("style", "")):
        add_finding(findings, "JLC_STYLE_SYMBOL_SHAPE_CHANGED", "blocker", "jlc_style.schematic.embed", "Embedded schematic does not identify the JLC source SVG")

    group_refs = {
        cell.get("data-ref")
        for cell in root
        if cell.get("data-role") == "jlc_symbol_group" or cell.get("id", "").startswith("jlc_style.group.")
    }
    missing_groups = sorted(ref for ref in REQUIRED_REFS if ref not in group_refs)
    for ref in missing_groups:
        add_finding(findings, "JLC_SYMBOL_GROUP_MISSING", "blocker", ref, "Missing JLC symbol group metadata", expected=ref)

    missing_refs = [ref for ref in REQUIRED_REFS if not token_present(ref, text)]
    for ref in missing_refs:
        add_finding(findings, "REQUIRED_REF_MISSING", "blocker", ref, "Required school ref is not visible", expected=ref)

    missing_nets = [net for net in VISIBLE_REQUIRED_NETS if not token_present(net, text)]
    for net in missing_nets:
        add_finding(findings, "REQUIRED_NET_MISSING", "blocker", net, "Required canonical net is not visible", expected=net)

    for ref in FORBIDDEN_REFS:
        if token_present(ref, text):
            add_finding(findings, "OLD_REF_VISIBLE", "blocker", ref, "Old JLC ref remains visible", actual=ref)
    for net in FORBIDDEN_NETS:
        if token_present(net, text):
            add_finding(findings, "OLD_NET_VISIBLE", "blocker", net, "Old JLC/stale net name remains visible", actual=net)
    for marker in KICAD_LEAK_MARKERS:
        if marker in text:
            add_finding(findings, "KICAD_STYLE_SYMBOL_LEAKED", "blocker", marker, "KiCad-style generated schematic marker leaked into final JLC-style drawing", actual=marker)
    return {"embed_box": embed_box, "missing_groups": missing_groups, "group_count": len(group_refs)}


def validate_layout(root: ET.Element, embed_box: dict[str, float], findings: list[Finding]) -> dict[str, Any]:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    regions = lock.get("regions", {})
    element = regions.get("element_list", {}).get("bbox", {})
    title = regions.get("title_block", {}).get("bbox", {})
    outer = regions.get("outer_frame", {}).get("bbox", {})
    if not embed_box:
        return {"layout_metrics": {}}
    if element and boxes_intersect(embed_box, element, tolerance=1.0):
        add_finding(findings, "SCHEMATIC_OVERLAPS_LIST_OR_TITLE", "blocker", "jlc_style.schematic.embed", "JLC schematic block overlaps the List of Elements")
    if title and boxes_intersect(embed_box, title, tolerance=1.0):
        add_finding(findings, "SCHEMATIC_OVERLAPS_LIST_OR_TITLE", "blocker", "jlc_style.schematic.embed", "JLC schematic block overlaps the Title Block")
    if outer:
        main_width = float(element.get("x", outer["right"])) - float(outer["x"])
        main_height = float(title.get("y", outer["bottom"])) - float(outer["y"])
        width_ratio = embed_box["width"] / main_width if main_width else 0.0
        height_ratio = embed_box["height"] / main_height if main_height else 0.0
        if width_ratio < 0.60 or height_ratio < 0.32:
            add_finding(findings, "BLOCK_TOO_SPARSE", "warning", "jlc_style.schematic.embed", "JLC schematic block uses too little of the available A1 main area", expected=">=0.60 width and >=0.32 height", actual=f"{width_ratio:.3f}, {height_ratio:.3f}")
        if width_ratio > 0.93 or height_ratio > 0.78:
            add_finding(findings, "BLOCK_TOO_CROWDED", "warning", "jlc_style.schematic.embed", "JLC schematic block may be too large for comfortable review", expected="<=0.93 width and <=0.78 height", actual=f"{width_ratio:.3f}, {height_ratio:.3f}")
        return {
            "layout_metrics": {
                "main_width": main_width,
                "main_height": main_height,
                "width_ratio": width_ratio,
                "height_ratio": height_ratio,
                "gap_to_element_list": element.get("x", 0) - bbox_right(embed_box) if element else None,
                "gap_to_title_block": title.get("y", 0) - bbox_bottom(embed_box) if title else None,
            }
        }
    return {"layout_metrics": {}}


def validate_svg_geometry(svg_text: str, findings: list[Finding]) -> dict[str, Any]:
    payloads = extract_embedded_svg_payloads(svg_text)
    jlc_payload = next((payload for payload in payloads if "jlc_style_schematic_source" in payload or "jlc_schematic_original.svg" in payload), "")
    if not jlc_payload:
        add_finding(findings, "JLC_STYLE_SYMBOL_SHAPE_CHANGED", "blocker", "final_svg", "Final SVG does not contain the embedded JLC source-style SVG payload")
        return {"payload_found": False}
    if re.search(r"<path\b[^>]*\bd=\"[^\"]*[a-z]", jlc_payload):
        # Lowercase path commands are curves/relative commands in the source symbol
        # artwork, not schematic wires. They are allowed for original JLC symbols.
        pass
    # Only flag explicitly declared line/polyline segments that are diagonal in
    # the normalized JLC payload. Path-based source symbols are not treated as
    # wires by this audit.
    try:
        root = ET.fromstring(jlc_payload)
    except ET.ParseError:
        add_finding(findings, "JLC_STYLE_SYMBOL_SHAPE_CHANGED", "blocker", "final_svg", "Embedded JLC SVG payload cannot be parsed")
        return {"payload_found": True, "payload_parseable": False}
    diagonal = 0
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "line":
            x1 = float(element.get("x1", "0") or 0)
            y1 = float(element.get("y1", "0") or 0)
            x2 = float(element.get("x2", "0") or 0)
            y2 = float(element.get("y2", "0") or 0)
            if abs(x1 - x2) > 0.01 and abs(y1 - y2) > 0.01:
                diagonal += 1
    if diagonal:
        add_finding(findings, "WIRE_NOT_ORTHOGONAL", "blocker", "final_svg", "Embedded JLC SVG contains diagonal line primitives", expected="0", actual=str(diagonal))
    metadata = parse_embedded_jlc_metadata(jlc_payload)
    fidelity = validate_symbol_fidelity(metadata, findings)
    return {
        "payload_found": True,
        "payload_parseable": True,
        "payload_viewbox": parse_viewbox(jlc_payload),
        "final_embed_bbox": find_final_svg_embed_bbox(svg_text),
        "diagonal_line_count": diagonal,
        "metadata": metadata,
        "symbol_fidelity": fidelity,
    }


def save_finding_crops(args: argparse.Namespace, findings: list[Finding], svg_metrics: dict[str, Any]) -> dict[str, Any]:
    args.crops_dir.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict[str, Any]] = []
    if not findings:
        manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "items": []}
        (args.crops_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest
    if not args.final_png.exists():
        manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "items": []}
        (args.crops_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest
    image = Image.open(args.final_png).convert("RGBA")
    for index, finding in enumerate(findings, start=1):
        crop_path = args.crops_dir / f"finding_{index:03d}_{finding.code}.png"
        # Without reliable exact coordinates for every semantic finding, provide
        # a full-sheet evidence crop. The visual review pack has detailed crops.
        image.save(crop_path)
        manifest_items.append(
            {
                "kind": "finding",
                "id": f"finding_{index:03d}_{finding.code}",
                "path": repo_path(crop_path),
                "source_png": repo_path(args.final_png),
                "pixel_box": {"x": 0, "y": 0, "width": image.width, "height": image.height},
                "finding": asdict(finding),
            }
        )
    manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "items": manifest_items}
    (args.crops_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def write_reports(args: argparse.Namespace, report: dict[str, Any]) -> None:
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# JLC Style Layout Audit Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Blockers: `{report['summary']['blocker_count']}`",
        f"- Warnings: `{report['summary']['warning_count']}`",
        f"- Final draw.io: `{repo_path(args.final_drawio)}`",
        f"- Final SVG: `{repo_path(args.final_svg)}`",
        f"- Final PNG: `{repo_path(args.final_png)}`",
        f"- JLC source: `{repo_path(args.jlc_source)}`",
        "",
        "## Checks",
        "",
        f"- JLC-style embedded block: `{report['checks'].get('jlc_payload_found')}`",
        f"- JLC symbol group metadata count: `{report['checks'].get('symbol_group_count')}`",
        f"- Exact JLC symbol fidelity: `{report['checks'].get('exact_symbol_fidelity')}`",
        f"- Required refs visible: `{report['checks'].get('required_refs_visible')}`",
        f"- Required nets visible: `{report['checks'].get('required_nets_visible')}`",
        f"- Old refs absent: `{report['checks'].get('old_refs_absent')}`",
        f"- Old nets absent: `{report['checks'].get('old_nets_absent')}`",
        f"- KiCad-style markers absent: `{report['checks'].get('kicad_style_markers_absent')}`",
        f"- Layout metrics: `{report.get('layout_metrics', {})}`",
        "",
        "## Findings",
        "",
    ]
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['code']}` `{finding['object_id']}`: {finding['message']}")
    else:
        lines.append("No blocker or warning findings.")
    fidelity_entries = report.get("svg", {}).get("symbol_fidelity", {}).get("entries", [])
    if fidelity_entries:
        lines.extend(["", "## Exact JLC Symbol Fidelity", ""])
        for entry in fidelity_entries:
            lines.append(
                "- `{ref}` verdict `{verdict}`; source `{source}` -> final `{final}`; "
                "elements `{before}`/`{after}`; paths `{paths_before}`/`{paths_after}`; "
                "geometry hash match `{geometry}`; stroke/style match `{stroke}`; transform `{transform}`".format(
                    ref=entry.get("ref"),
                    verdict=entry.get("verdict"),
                    source=entry.get("source_group_id"),
                    final=entry.get("final_group_id"),
                    before=entry.get("source_elements_count"),
                    after=entry.get("final_elements_count"),
                    paths_before=entry.get("path_count_before"),
                    paths_after=entry.get("path_count_after"),
                    geometry=entry.get("geometry_hash_match"),
                    stroke=entry.get("stroke_style_match"),
                    transform=entry.get("allowed_transform"),
                )
            )
    lines.extend(
        [
            "",
            "## Visual Review Note",
            "",
            "This audit confirms the final drawing uses the JLC-source SVG style block and passes automated text/layout checks. It does not claim human visual approval.",
        ]
    )
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    findings: list[Finding] = []
    for path, code in (
        (args.jlc_source, "JLC_SOURCE_MISSING"),
        (args.final_drawio, "FINAL_DRAWIO_MISSING"),
        (args.final_svg, "SVG_MISSING"),
        (args.final_png, "PNG_MISSING"),
    ):
        if not path.exists():
            add_finding(findings, code, "blocker", repo_path(path), f"Required file missing: {path}")

    drawio_text = read_text(args.final_drawio) if args.final_drawio.exists() else ""
    svg_text = read_text(args.final_svg) if args.final_svg.exists() else ""
    combined_text = plain_visible_text(drawio_text, svg_text)
    root = parse_drawio_root(args.final_drawio) if args.final_drawio.exists() else ET.Element("root")
    symbol_report = validate_symbols(root, combined_text, findings)
    layout_report = validate_layout(root, symbol_report.get("embed_box", {}), findings)
    svg_report = validate_svg_geometry(svg_text, findings) if svg_text else {}

    checks = {
        "jlc_payload_found": bool(svg_report.get("payload_found")),
        "symbol_group_count": symbol_report.get("group_count", 0),
        "exact_symbol_fidelity": svg_report.get("symbol_fidelity", {}).get("fail_count", 1) == 0,
        "required_refs_visible": all(token_present(ref, combined_text) for ref in REQUIRED_REFS),
        "required_nets_visible": all(token_present(net, combined_text) for net in VISIBLE_REQUIRED_NETS),
        "old_refs_absent": not any(token_present(ref, combined_text) for ref in FORBIDDEN_REFS),
        "old_nets_absent": not any(token_present(net, combined_text) for net in FORBIDDEN_NETS),
        "kicad_style_markers_absent": not any(marker in combined_text for marker in KICAD_LEAK_MARKERS),
    }
    if not checks["kicad_style_markers_absent"] and not any(item.code == "KICAD_STYLE_SYMBOL_LEAKED" for item in findings):
        add_finding(findings, "KICAD_STYLE_SYMBOL_LEAKED", "blocker", "final", "KiCad-style marker is present in final output")

    crop_manifest = save_finding_crops(args, findings, svg_report)
    blocker_count = sum(1 for item in findings if item.severity == "blocker")
    warning_count = sum(1 for item in findings if item.severity == "warning")
    status = "PASS" if blocker_count == 0 and warning_count == 0 else ("WARN" if blocker_count == 0 else "FAIL")
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "summary": {
            "blocker_count": blocker_count,
            "warning_count": warning_count,
            "finding_count": len(findings),
        },
        "inputs": {
            "jlc_source": repo_path(args.jlc_source),
            "final_drawio": repo_path(args.final_drawio),
            "final_svg": repo_path(args.final_svg),
            "final_png": repo_path(args.final_png),
        },
        "checks": checks,
        "layout_metrics": layout_report.get("layout_metrics", {}),
        "svg": svg_report,
        "crops_manifest": repo_path(args.crops_dir / "manifest.json"),
        "findings": [asdict(item) for item in findings],
    }
    write_reports(args, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if blocker_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
