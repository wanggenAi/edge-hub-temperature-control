#!/usr/bin/env python3
"""Lint SVG/PDF/PNG exports produced from the generated draw.io schematic."""

from __future__ import annotations

import argparse
import json
import re
import sys
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

    required = [
        "DD1",
        "ESP32-WROOM-32",
        "Capacitors",
        "Resistors",
        "ESP32-WROOM-32 module",
        "XH-3PA 3-pin sensor connector",
        "KF301-2P thermal switch terminal",
        "Qty.",
        "Department of Computer",
        "Microcontroller-based I/O Device",
        "Name",
        "Э3",
    ]
    missing = [value for value in required if value not in visible_text]
    if missing:
        error(findings, "SVG_REQUIRED_TEXT_MISSING", str(path), "SVG is missing required drawing text", ", ".join(required), ", ".join(missing))
    if REQUIRED_DOCUMENT_CODE not in visible_text:
        error(findings, "SVG_REQUIRED_TEXT_MISSING", str(path), "SVG is missing the required BSTU document code text", REQUIRED_DOCUMENT_CODE, "not found")
    validate_locked_region_boxes_in_svg(text, lock_file, findings, str(path))

    forbidden_refs = [
        "CN1",
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
    values: list[str] = []
    for snippet in snippets:
        clean = re.sub(r"<br\s*/?>", " ", snippet, flags=re.I)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = clean.replace("&nbsp;", " ")
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            values.append(clean)
    return " ".join(values)


def token_in_text(token: str, text: str) -> bool:
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
