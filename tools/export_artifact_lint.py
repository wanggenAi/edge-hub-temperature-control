#!/usr/bin/env python3
"""Lint SVG/PDF/PNG exports produced from the generated draw.io schematic."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIR = ROOT / "hardware/eda/exports/preview"
DEFAULT_REPORTS_DIR = ROOT / "build/reports/export-preview"
DEFAULT_LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
DEFAULT_BASENAME = "functiondiagramYUANLITU.preview"
REQUIRED_DOCUMENT_CODE = "BSTU.241297.006"
KICAD_EMBED_MIN_WIDTH_RATIO = 0.70
KICAD_EMBED_MAX_WIDTH_RATIO = 0.85
KICAD_EMBED_MIN_HEIGHT_RATIO = 0.45
KICAD_EMBED_MAX_HEIGHT_RATIO = 0.70
KICAD_EMBED_MIN_GAP_TO_ELEMENT_LIST = 30.0
KICAD_EMBED_MIN_GAP_TO_TITLE_BLOCK = 40.0
ESP32_BOM_REQUIRED_TEXT = [
    "C1, C4",
    "Capacitor 0.1 uF",
    "C2",
    "Capacitor 10 uF",
    "C3",
    "Capacitor 100 uF",
    "R1, R5, R6",
    "Resistor 10 kOhm",
    "R2",
    "Resistor 4.7 kOhm",
    "R3",
    "Resistor 330 Ohm",
    "R4",
    "Resistor 100 Ohm",
    "DD1",
    "ESP32-WROOM-32 Wi-Fi module",
    "HL1",
    "Red LED",
    "VT1",
    "NMOS3400 N-channel MOSFET",
    "SB1, SB2",
    "Tact switch SMT 6x6x7.5",
    "XS1",
    "XH-3PA 3-pin connector",
    "XS2, XS3",
    "KF2EDGV-3.81-2P connector",
    "XS4",
    "Header45.08-4P service connector",
    "XS5",
    "KF301-2P terminal connector",
    "A1",
    "DC/DC converter 12 V to 3.3 V",
]
LEGACY_BOM_FORBIDDEN_TEXT = [
    "Microcontroller AT89C52",
    "LCD1602-A",
    "Crystal Oscillator",
    "BUTTON SPST",
    "Micro-USB to DIP adapter",
    "RV1",
    "ZQ1",
    "DD2",
    "DD3",
]
ESP32_TITLE_BLOCK_REQUIRED_TEXT = [
    "BSTU.241297.006 Э3",
    "ESP32 Temperature Control Unit",
    "Electrical Schematic Diagram",
    "Brest State Technical University",
    "Wang Gen",
    "A1",
    "N/A",
]
LEGACY_TITLE_BLOCK_FORBIDDEN_TEXT = [
    "Microcontroller-based I/O Device",
    "Department of Computer and System",
    "Разумейчик",
    "AT89C52",
    "LCD",
]


def is_final_kicad_embed_label(label: str) -> bool:
    label_lower = label.lower()
    return any(
        marker in label_lower
        for marker in (
            "kicad",
            "element-list-esp32-bom",
            "title-block-esp32",
            "thesis-candidate",
            "jlc-faithful-kicad-redraw",
        )
    )


def requires_esp32_bom_check(label: str) -> bool:
    label_lower = label.lower()
    return any(marker in label_lower for marker in ("element-list-esp32-bom", "title-block-esp32", "thesis-candidate", "jlc-faithful-kicad-redraw"))


def requires_esp32_title_block_check(label: str) -> bool:
    label_lower = label.lower()
    return any(marker in label_lower for marker in ("title-block-esp32", "thesis-candidate", "jlc-faithful-kicad-redraw"))


@dataclass
class Finding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""


def error(findings: list[Finding], code: str, object_id: str, message: str, expected: str = "", actual: str = "") -> None:
    findings.append(Finding(code=code, severity="error", object_id=object_id, message=message, expected=expected, actual=actual))


def validate_exists(path: Path, kind: str, findings: list[Finding], label: str) -> bool:
    if not path.exists():
        error(findings, f"{kind.upper()}_MISSING", str(path), f"Missing {label} {kind.upper()} export")
        return False
    if path.stat().st_size <= 0:
        error(findings, f"{kind.upper()}_EMPTY", str(path), f"{label.title()} {kind.upper()} export is empty", "> 0 bytes", "0 bytes")
        return False
    return True


def validate_svg(path: Path, findings: list[Finding], lock_file: Path, label: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not validate_exists(path, "svg", findings, label):
        return payload
    text = path.read_text(encoding="utf-8", errors="ignore")
    payload["size_bytes"] = path.stat().st_size
    try:
        root = ET.fromstring(text)
        payload["root_tag"] = root.tag
        payload["width"] = root.get("width", "")
        payload["height"] = root.get("height", "")
        payload["viewBox"] = root.get("viewBox", "")
    except ET.ParseError as exc:
        error(findings, "SVG_PARSE_ERROR", str(path), "SVG is not parseable XML", "parseable XML", str(exc))
        return payload

    visible_text = visible_svg_text(text)
    payload["visible_text_sample"] = visible_text[:500]
    lower = remove_data_urls(text).lower()
    forbidden_text = [
        "draw.io editor",
        "geSidebar",
        "selection",
        "cursor",
        "resize handle",
    ]
    for marker in forbidden_text:
        if marker.lower() in lower:
            error(findings, "SVG_EDITOR_ARTIFACT", str(path), "SVG contains editor UI or selection artifact text", "no editor artifacts", marker)

    forbidden_colors = {
        "#0000ff": "blue selection color",
        "#00ff00": "green handle color",
        "#008000": "green handle color",
        "#ff0000": "red editor color",
        "rgb(0,0,255)": "blue selection color",
        "rgb(0,255,0)": "green handle color",
    }
    for color, reason in forbidden_colors.items():
        if color in lower.replace(" ", ""):
            error(findings, "SVG_FORBIDDEN_COLOR", str(path), f"SVG contains {reason}", "black/white engineering style", color)

    if "grid" in lower and "stroke" in lower:
        # This intentionally stays conservative: draw.io exports should not contain
        # obvious editor grid objects. Text containing the word grid alone is allowed.
        grid_patterns = [r'id="[^"]*grid[^"]*"', r'class="[^"]*grid[^"]*"']
        if any(re.search(pattern, lower) for pattern in grid_patterns):
            error(findings, "SVG_GRID_ARTIFACT", str(path), "SVG contains obvious grid artifact", "no grid", "grid marker")

    required = required_visible_text(label)
    missing = [value for value in required if value not in visible_text]
    if missing:
        error(findings, "SVG_REQUIRED_TEXT_MISSING", str(path), "SVG is missing required drawing text", ", ".join(required), ", ".join(missing))
    if REQUIRED_DOCUMENT_CODE not in visible_text:
        error(findings, "SVG_REQUIRED_TEXT_MISSING", str(path), "SVG is missing the required BSTU document code text", REQUIRED_DOCUMENT_CODE, "not found")
    is_final_kicad_embed = is_final_kicad_embed_label(label)
    if not is_final_kicad_embed:
        validate_locked_region_boxes_in_svg(text, lock_file, findings, str(path))
    else:
        if "Qty" not in visible_text and "Number" not in visible_text:
            error(findings, "SVG_REQUIRED_TEXT_MISSING", str(path), "SVG is missing the element-list quantity column header", "Qty or Number", "not found")
        validate_kicad_embed_geometry(text, lock_file, findings, str(path), payload)
        if requires_esp32_bom_check(label):
            validate_esp32_bom_visible_text(visible_text, findings, str(path))
        if requires_esp32_title_block_check(label):
            validate_esp32_title_block_visible_text(visible_text, findings, str(path))

    forbidden_refs = [
        "CN1",
        "D1",
        "U1",
        "Q1",
        "U3_reset",
        "U4_boot",
        "U3_buck",
        "U7",
        "J2_heater",
        "J_TS1",
        "J_Power",
    ]
    forbidden_nets = [
        "UART_GND",
        "GATE_DRV",
        "HEATER_PLUS",
        "HEATER_SW",
        "LED_SERIES",
        "J1_12V",
        "$1N",
        "+12 B",
        "+12B",
        "3V3",
    ]
    for marker in forbidden_refs:
        if token_in_text(marker, visible_text):
            error(findings, "SVG_FORBIDDEN_VISIBLE_REF", str(path), "SVG contains a forbidden source ref as visible text", "confirmed thesis refs only", marker)
    for marker in forbidden_nets:
        if token_in_text(marker, visible_text):
            error(findings, "SVG_FORBIDDEN_NET_NAME", str(path), "SVG contains a stale net name as visible text", "canonical net names only", marker)
    return payload


def validate_esp32_bom_visible_text(visible_text: str, findings: list[Finding], object_id: str) -> None:
    missing = [value for value in ESP32_BOM_REQUIRED_TEXT if value not in visible_text]
    if missing:
        error(
            findings,
            "SVG_ESP32_BOM_REQUIRED_TEXT_MISSING",
            object_id,
            "Final SVG is missing required ESP32 List of Elements text",
            ", ".join(ESP32_BOM_REQUIRED_TEXT),
            ", ".join(missing),
        )
    stale = [value for value in LEGACY_BOM_FORBIDDEN_TEXT if token_in_text(value, visible_text)]
    if stale:
        error(
            findings,
            "SVG_LEGACY_BOM_TEXT_VISIBLE",
            object_id,
            "Final SVG still contains legacy/template List of Elements text",
            "ESP32 BOM only",
            ", ".join(stale),
        )


def validate_esp32_title_block_visible_text(visible_text: str, findings: list[Finding], object_id: str) -> None:
    missing = [value for value in ESP32_TITLE_BLOCK_REQUIRED_TEXT if value not in visible_text]
    if missing:
        error(
            findings,
            "SVG_ESP32_TITLE_BLOCK_REQUIRED_TEXT_MISSING",
            object_id,
            "Final SVG is missing required ESP32 Title Block text",
            ", ".join(ESP32_TITLE_BLOCK_REQUIRED_TEXT),
            ", ".join(missing),
        )
    stale = [value for value in LEGACY_TITLE_BLOCK_FORBIDDEN_TEXT if value in visible_text]
    if stale:
        error(
            findings,
            "SVG_LEGACY_TITLE_BLOCK_TEXT_VISIBLE",
            object_id,
            "Final SVG still contains legacy/template Title Block text",
            "ESP32 schematic title block only",
            ", ".join(stale),
        )
    cyrillic_outside_code = visible_text.replace("Э3", "")
    if re.search(r"[\u0400-\u04FF]", cyrillic_outside_code):
        error(
            findings,
            "SVG_TITLE_BLOCK_CYRILLIC_FORBIDDEN",
            object_id,
            "Final SVG contains Cyrillic text outside the allowed Э3 document-type code",
            "English title block text except Э3",
            "Cyrillic text found",
        )


def validate_kicad_embed_geometry(
    text: str,
    lock_file: Path,
    findings: list[Finding],
    object_id: str,
    payload: dict[str, Any],
) -> None:
    if not lock_file.exists():
        error(findings, "LOCK_FILE_MISSING", str(lock_file), "Reserved-region lock file is missing")
        return
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    regions = lock.get("regions", {})
    outer = regions.get("outer_frame", {}).get("bbox", {})
    element_list = regions.get("element_list", {}).get("bbox", {})
    title_block = regions.get("title_block", {}).get("bbox", {})
    embed = find_kicad_svg_image_bbox(text)
    payload["kicad_embed_bbox"] = embed
    if not embed:
        error(findings, "KICAD_EMBED_MISSING", object_id, "Final SVG has no embedded KiCad SVG image")
        return
    if not (outer and element_list and title_block):
        error(findings, "LOCKED_REGION_MISSING", object_id, "Lock file lacks outer frame, element list, or title block bbox data")
        return

    left = float(embed["x"])
    top = float(embed["y"])
    right = left + float(embed["width"])
    bottom = top + float(embed["height"])
    outer_left = float(outer["x"])
    outer_top = float(outer["y"])
    outer_right = float(outer["right"])
    outer_bottom = float(outer["bottom"])
    element_left = float(element_list["x"])
    title_top = float(title_block["y"])
    main_width = element_left - outer_left
    main_height = title_top - outer_top
    width_ratio = float(embed["width"]) / main_width if main_width > 0 else 0.0
    height_ratio = float(embed["height"]) / main_height if main_height > 0 else 0.0
    gap_to_element_list = element_left - right
    gap_to_title_block = title_top - bottom
    payload["kicad_embed_metrics"] = {
        "main_width": main_width,
        "main_height": main_height,
        "width_ratio": width_ratio,
        "height_ratio": height_ratio,
        "gap_to_element_list": gap_to_element_list,
        "gap_to_title_block": gap_to_title_block,
    }

    if left < outer_left or top < outer_top or right > outer_right or bottom > outer_bottom:
        error(
            findings,
            "KICAD_EMBED_OUTSIDE_OUTER_FRAME",
            object_id,
            "Embedded KiCad block extends outside the locked outer frame",
            f"inside x={outer_left}..{outer_right}, y={outer_top}..{outer_bottom}",
            f"x={left}..{right}, y={top}..{bottom}",
        )
    if gap_to_element_list < KICAD_EMBED_MIN_GAP_TO_ELEMENT_LIST:
        error(
            findings,
            "KICAD_EMBED_OVERLAPS_ELEMENT_LIST",
            object_id,
            "Embedded KiCad block is too close to or overlaps the right-top List of Elements",
            f">= {KICAD_EMBED_MIN_GAP_TO_ELEMENT_LIST} units",
            f"{gap_to_element_list:.2f} units",
        )
    if gap_to_title_block < KICAD_EMBED_MIN_GAP_TO_TITLE_BLOCK:
        error(
            findings,
            "KICAD_EMBED_OVERLAPS_TITLE_BLOCK",
            object_id,
            "Embedded KiCad block is too close to or overlaps the right-bottom Title Block",
            f">= {KICAD_EMBED_MIN_GAP_TO_TITLE_BLOCK} units",
            f"{gap_to_title_block:.2f} units",
        )
    if not (KICAD_EMBED_MIN_WIDTH_RATIO <= width_ratio <= KICAD_EMBED_MAX_WIDTH_RATIO):
        error(
            findings,
            "KICAD_EMBED_WIDTH_RATIO_INVALID",
            object_id,
            "Embedded KiCad block does not use the required share of the main schematic width",
            f"{KICAD_EMBED_MIN_WIDTH_RATIO:.2f}..{KICAD_EMBED_MAX_WIDTH_RATIO:.2f}",
            f"{width_ratio:.3f}",
        )
    if not (KICAD_EMBED_MIN_HEIGHT_RATIO <= height_ratio <= KICAD_EMBED_MAX_HEIGHT_RATIO):
        error(
            findings,
            "KICAD_EMBED_HEIGHT_RATIO_INVALID",
            object_id,
            "Embedded KiCad block does not use the required share of the main schematic height",
            f"{KICAD_EMBED_MIN_HEIGHT_RATIO:.2f}..{KICAD_EMBED_MAX_HEIGHT_RATIO:.2f}",
            f"{height_ratio:.3f}",
        )


def find_kicad_svg_image_bbox(text: str) -> dict[str, float]:
    for match in re.finditer(r"<image\b[^>]+>", text, flags=re.I):
        tag = match.group(0)
        if "data:image/svg+xml" not in tag:
            continue
        attrs = dict(re.findall(r'\b(x|y|width|height)="([-+]?\d+(?:\.\d+)?)"', tag))
        if all(key in attrs for key in ("x", "y", "width", "height")):
            return {key: float(attrs[key]) for key in ("x", "y", "width", "height")}
    return {}


def validate_locked_region_boxes_in_svg(text: str, lock_file: Path, findings: list[Finding], object_id: str) -> None:
    if not lock_file.exists():
        error(findings, "LOCK_FILE_MISSING", str(lock_file), "Reserved-region lock file is missing")
        return
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    geometry_text = remove_data_urls(text)
    geometry_numbers = [float(match) for match in re.findall(r"[-+]?\d+(?:\.\d+)?", geometry_text)]
    regions = lock.get("regions", {})
    for region_name in ("outer_frame", "element_list", "title_block"):
        region = regions.get(region_name, {})
        bbox = region.get("bbox", {})
        if not bbox:
            error(findings, "LOCKED_REGION_MISSING", object_id, f"Lock file has no bbox for {region_name}")
            continue
        x = format_svg_number(float(bbox["x"]))
        y = format_svg_number(float(bbox["y"]))
        width = format_svg_number(float(bbox["width"]))
        height = format_svg_number(float(bbox["height"]))
        exact_rect_found = f'x="{x}"' in text and f'y="{y}"' in text and f'width="{width}"' in text and f'height="{height}"' in text
        boundary_found = all(
            number_within(geometry_numbers, float(bbox[key]), 2.0)
            for key in ("x", "y", "right", "bottom")
        )
        if not (exact_rect_found or boundary_found):
            error(
                findings,
                "SVG_LOCKED_REGION_NOT_VISIBLE",
                object_id,
                f"SVG does not contain the locked {region_name} rectangle geometry",
                f'x={x} y={y} width={width} height={height} or matching boundary coordinates',
                "not found",
            )


def format_svg_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def number_within(values: list[float], expected: float, tolerance: float) -> bool:
    return any(abs(value - expected) <= tolerance for value in values)


def remove_data_urls(text: str) -> str:
    return re.sub(r'data:image/[^"\']+', "", text)


def visible_svg_text(text: str) -> str:
    without_data = remove_data_urls(text)
    snippets = re.findall(r"<foreignObject\b.*?</foreignObject>", without_data, flags=re.S | re.I)
    if not snippets:
        snippets = [without_data]
    snippets.extend(extract_embedded_svg_payloads(text))
    values: list[str] = []
    for snippet in snippets:
        clean = re.sub(r"<br\s*/?>", " ", snippet, flags=re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = html.unescape(clean)
        clean = clean.replace("&nbsp;", " ")
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            values.append(clean)
    return " ".join(values)


def extract_embedded_svg_payloads(text: str) -> list[str]:
    payloads: list[str] = []
    pattern = re.compile(r"data:image/svg\+xml(?:;base64)?,([^\"'&<> ]+)", flags=re.I)
    for match in pattern.finditer(text):
        marker = match.group(0).lower()
        payload = match.group(1)
        try:
            if ";base64," in marker:
                decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
            else:
                decoded = urllib.parse.unquote(payload)
        except Exception:  # noqa: BLE001 - malformed payload is handled by required text failures.
            continue
        if "<svg" in decoded:
            payloads.append(decoded)
    return payloads


def required_visible_text(label: str) -> list[str]:
    label_lower = label.lower()
    base = [
        "Capacitors",
        "Resistors",
        "Position number",
        "Name",
        "Note",
        "Э3",
    ]
    if requires_esp32_title_block_check(label):
        base.extend(ESP32_TITLE_BLOCK_REQUIRED_TEXT)
    else:
        base.extend(["Department of Computer", "Microcontroller-based I/O Device"])
    if not is_final_kicad_embed_label(label):
        return ["DD1", "ESP32-WROOM-32", *base]
    school_refs = [
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
    canonical_nets = [
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
    return [*school_refs, *canonical_nets, "ESP32-WROOM-32", *base]


def token_in_text(token: str, text: str) -> bool:
    if token == "$1N":
        return "$1N" in text
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.-])3V3(?![A-Za-z0-9_.-])", text) is not None
    escaped = re.escape(token)
    return re.search(rf"(?<![A-Za-z0-9_.+-]){escaped}(?![A-Za-z0-9_.+-])", text) is not None


def validate_png(path: Path, findings: list[Finding], min_width: int, label: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not validate_exists(path, "png", findings, label):
        return payload
    payload["size_bytes"] = path.stat().st_size
    with Image.open(path) as image:
        image = image.convert("RGBA")
        width, height = image.size
        payload["width_px"] = width
        payload["height_px"] = height
        if width < min_width:
            error(findings, "PNG_TOO_SMALL", str(path), f"{label.title()} PNG width is below minimum", f">= {min_width}px", f"{width}px")
        if height < 2000:
            error(findings, "PNG_HEIGHT_TOO_SMALL", str(path), f"{label.title()} PNG height is below minimum for page export", ">= 2000px", f"{height}px")

        sample_pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        total = 0
        colored = 0
        selection_pixels = 0
        non_transparent = 0
        for r, g, b, a in sample_pixels:
            if a < 16:
                continue
            non_transparent += 1
            total += 1
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            if max_c - min_c > 18:
                colored += 1
            if (b > 150 and r < 120 and g < 180) or (g > 150 and r < 140 and b < 140):
                selection_pixels += 1
        payload["non_transparent_pixels"] = non_transparent
        payload["colored_ratio"] = 0 if total == 0 else colored / total
        payload["selection_like_pixels"] = selection_pixels
        if total == 0:
            error(findings, "PNG_EMPTY_CANVAS", str(path), "Preview PNG has no visible pixels")
        if payload["colored_ratio"] > 0.005:
            error(findings, "PNG_NOT_MONOCHROME", str(path), "Preview PNG has too many non-monochrome pixels", "<= 0.5%", f"{payload['colored_ratio']:.5f}")
        if selection_pixels > max(20, total * 0.0001):
            error(findings, "PNG_SELECTION_ARTIFACT", str(path), "Preview PNG contains blue/green selection-like pixels", "no selection artifacts", str(selection_pixels))
    return payload


def validate_pdf(path: Path, findings: list[Finding], label: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not validate_exists(path, "pdf", findings, label):
        return payload
    payload["size_bytes"] = path.stat().st_size
    try:
        reader = PdfReader(str(path))
        payload["page_count"] = len(reader.pages)
        if len(reader.pages) < 1:
            error(findings, "PDF_NO_PAGES", str(path), "Preview PDF has no pages", ">= 1", "0")
    except Exception as exc:  # noqa: BLE001 - report parser failure as lint error.
        error(findings, "PDF_PARSE_ERROR", str(path), "Preview PDF could not be parsed", "parseable PDF", str(exc))
    return payload


def write_reports(findings: list[Finding], payload: dict[str, Any], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = {
        **payload,
        "error_count": sum(1 for finding in findings if finding.severity == "error"),
        "findings": [asdict(finding) for finding in findings],
    }
    (reports_dir / "export_artifact_lint.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Export Artifact Lint Report",
        "",
        f"- Export directory: `{payload['export_dir']}`",
        f"- Errors: {report['error_count']}",
        "",
    ]
    if findings:
        lines.append("## Findings")
        for finding in findings:
            lines.append(f"- **{finding.code}** `{finding.object_id}`: {finding.message}")
    else:
        lines.append("No export artifact lint errors.")
    (reports_dir / "export_artifact_lint.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint SVG/PDF/PNG exports for the draw.io schematic.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--min-png-width", type=int, default=3000)
    parser.add_argument("--label", default="preview")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    svg = args.export_dir / f"{args.basename}.svg"
    pdf = args.export_dir / f"{args.basename}.pdf"
    png = args.export_dir / f"{args.basename}.png"
    findings: list[Finding] = []
    payload = {
        "export_dir": str(args.export_dir),
        "basename": args.basename,
        "label": args.label,
        "svg": validate_svg(svg, findings, args.lock_file, args.label),
        "png": validate_png(png, findings, args.min_png_width, args.label),
        "pdf": validate_pdf(pdf, findings, args.label),
    }
    write_reports(findings, payload, args.reports_dir)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
