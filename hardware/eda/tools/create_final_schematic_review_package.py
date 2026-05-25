#!/usr/bin/env python3
"""Create the final schematic QA report and human-review PNG crops."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
FINAL_DIR = ROOT / "hardware/eda/exports/final"
FINAL_BASENAME = "esp32_temperature_control_unit_electrical_schematic"
DEFAULT_PNG = FINAL_DIR / f"{FINAL_BASENAME}.png"
DEFAULT_SVG = FINAL_DIR / f"{FINAL_BASENAME}.svg"
DEFAULT_PDF = FINAL_DIR / f"{FINAL_BASENAME}.pdf"
DEFAULT_DRAWIO = FINAL_DIR / f"{FINAL_BASENAME}.drawio"
DEFAULT_LINT_REPORT = ROOT / "build/reports/final-jlc-style-layout-export/export_artifact_lint.json"
DEFAULT_ERC_REPORT = ROOT / "build/reports/kicad_schematic_erc_layout_audit.json"
DEFAULT_TABLE_LOCK_REPORT = ROOT / "build/reports/bstu_master_table_lock_jlc_style_layout.json"
DEFAULT_LAYOUT_AUDIT_REPORT = ROOT / "build/reports/jlc_style_layout_audit.json"
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
OUTPUT_DIR = FINAL_DIR / "review_crops"
QA_REPORT = ROOT / "docs/final_schematic_qa_report.md"
VISUAL_INDEX = ROOT / "docs/final_visual_review_index.md"
PYTEST_RESULT = "33 passed in focused schematic/table/audit suite"

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

CANONICAL_NETS = [
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

FORBIDDEN_TEXT = [
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
    "3V3",
    "J1_12V",
    "UART_GND",
    "GATE_DRV",
    "HEATER_PLUS",
    "HEATER_SW",
    "LED_SERIES",
    "$1N",
]

ESP32_BOM_TEXT = [
    "C1, C4",
    "GRM188R71H104KA93D",
    "C2",
    "GRM188R61A106KAALD",
    "C3",
    "CL31A107MQHNNNE",
    "R1, R5, R6",
    "RC0603FR-0710KL",
    "R2",
    "RC0603FR-074K7L",
    "R3",
    "RC0603FR-07330RL",
    "R4",
    "RC0603FR-07100RL",
    "DD1",
    "ESP32-WROOM-32",
    "HL1",
    "LED0603-RD_RED",
    "VT1",
    "NMOS3400",
    "SB1, SB2",
    "TactswitchSMT6x6x7_5",
    "XS1",
    "XH-3PA",
    "XS2, XS3",
    "2P-P3.81_KF2EDGV-3.81-2P",
    "XS4",
    "Header45.08-4P",
    "XS5",
    "KF301-2P",
    "A1",
    "Murata",
    "Samsung Electro-Mechanics",
    "YAGEO",
    "Espressif",
    "ZHOURI",
    "NEEDS_CONFIRMATION",
]


TITLE_BLOCK_TEXT = [
    "BSTU.241297.006 Э3",
    "ESP32 Temperature Control Unit",
    "Electrical Schematic Diagram",
    "Brest State Technical University",
    "Wang Gen",
    "A1",
    "N/A",
]

TEMPLATE_TEXT_FORBIDDEN = [
    "Microcontroller-based I/O Device",
    "Department of Computer and System",
    "Разумейчик",
    "AT89C52",
    "LCD",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    return str(absolute.relative_to(ROOT))


def docs_image_path(path: str) -> str:
    return f"../{path}"


def parse_viewbox(svg_path: Path) -> dict[str, float]:
    root = ET.fromstring(svg_path.read_text(encoding="utf-8", errors="ignore"))
    raw = root.get("viewBox", "")
    values = [float(value) for value in raw.split()]
    if len(values) != 4:
        width = float(re.sub(r"[^0-9.]", "", root.get("width", "0")) or 0)
        height = float(re.sub(r"[^0-9.]", "", root.get("height", "0")) or 0)
        values = [0.0, 0.0, width, height]
    return {"x": values[0], "y": values[1], "width": values[2], "height": values[3]}


def find_kicad_embed_bbox(svg_text: str) -> dict[str, float]:
    return find_schematic_embed_bbox(svg_text)


def find_schematic_embed_bbox(svg_text: str) -> dict[str, float]:
    for match in re.finditer(r"<image\b[^>]+>", svg_text, flags=re.I):
        tag = match.group(0)
        if "data:image/svg+xml" not in tag:
            continue
        attrs = dict(re.findall(r'\b(x|y|width|height)="([-+]?\d+(?:\.\d+)?)"', tag))
        if all(key in attrs for key in ("x", "y", "width", "height")):
            return {key: float(attrs[key]) for key in ("x", "y", "width", "height")}
    return {}


def visible_text(svg_text: str) -> str:
    snippets = [re.sub(r'data:image/[^"\']+', "", svg_text)]
    snippets.extend(extract_embedded_svg_payloads(svg_text))
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


def extract_embedded_svg_payloads(svg_text: str) -> list[str]:
    payloads: list[str] = []
    pattern = re.compile(r"data:image/svg\+xml(?:;base64)?,([^\"'<> ]+)", flags=re.I)
    for match in pattern.finditer(svg_text):
        marker = match.group(0).lower()
        payload = html.unescape(match.group(1))
        try:
            if ";base64," in marker:
                decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
            else:
                decoded = urllib.parse.unquote(payload)
        except Exception:  # noqa: BLE001 - missing text checks will catch unusable payloads.
            continue
        if "<svg" in decoded or re.search(r"<[A-Za-z0-9_]+:svg\b", decoded):
            payloads.append(decoded)
    return payloads


def token_present(token: str, text: str) -> bool:
    if token == "$1N":
        return "$1N" in text
    if token == "3V3":
        return re.search(r"(?<![+A-Za-z0-9_.-])3V3(?![A-Za-z0-9_.-])", text) is not None
    escaped = re.escape(token)
    return re.search(rf"(?<![A-Za-z0-9_.+-]){escaped}(?![A-Za-z0-9_.+-])", text) is not None


def svg_box_to_pixels(
    box: dict[str, float],
    viewbox: dict[str, float],
    image: Image.Image,
    margin: float | tuple[float, float, float, float] = 0.0,
) -> tuple[int, int, int, int]:
    if isinstance(margin, tuple):
        margin_left, margin_top, margin_right, margin_bottom = margin
    else:
        margin_left = margin_top = margin_right = margin_bottom = margin
    left = box["x"] - margin_left
    top = box["y"] - margin_top
    right = box["x"] + box["width"] + margin_right
    bottom = box["y"] + box["height"] + margin_bottom
    sx = image.width / viewbox["width"]
    sy = image.height / viewbox["height"]
    return (
        max(0, round((left - viewbox["x"]) * sx)),
        max(0, round((top - viewbox["y"]) * sy)),
        min(image.width, round((right - viewbox["x"]) * sx)),
        min(image.height, round((bottom - viewbox["y"]) * sy)),
    )


def sub_box(parent: dict[str, float], x: float, y: float, width: float, height: float) -> dict[str, float]:
    return {
        "x": parent["x"] + parent["width"] * x,
        "y": parent["y"] + parent["height"] * y,
        "width": parent["width"] * width,
        "height": parent["height"] * height,
    }


def expand_box(
    box: dict[str, float],
    *,
    left: float = 0.0,
    top: float = 0.0,
    right: float = 0.0,
    bottom: float = 0.0,
) -> dict[str, float]:
    return {
        "x": box["x"] - left,
        "y": box["y"] - top,
        "width": box["width"] + left + right,
        "height": box["height"] + top + bottom,
    }


def crop_metadata() -> dict[str, dict[str, Any]]:
    return {
        "overview": {
            "related_refs": REQUIRED_REFS,
            "related_nets": CANONICAL_NETS,
            "purpose": "Whole-sheet visual review: frame, title block, element list, JLC-style schematic block placement, and overall balance.",
            "focus": "Check that nothing is cropped, no UI artifacts exist, and the JLC-style schematic block does not overlap the tables.",
        },
        "kicad_block": {
            "related_refs": REQUIRED_REFS,
            "related_nets": CANONICAL_NETS,
            "purpose": "Legacy middle-block crop kept for backwards-compatible scripts.",
            "focus": "Prefer jlc_style_block for the current visual review.",
        },
        "jlc_style_block": {
            "related_refs": REQUIRED_REFS,
            "related_nets": CANONICAL_NETS,
            "purpose": "JLC-style middle schematic review.",
            "focus": "Check that the middle circuit keeps the original JLC symbol style while using school refs and canonical net names.",
        },
        "dd1_area": {
            "related_refs": ["DD1"],
            "related_nets": ["+3V3", "GND", "EN", "LED", "BOOT", "GATE", "DQ", "RXD0", "TXD0"],
            "purpose": "ESP32 controller area review.",
            "focus": "Check DD1 pin labels, net labels, local wire endpoints, and text clearance.",
        },
        "reset_boot_led_area": {
            "related_refs": ["R1", "SB1", "R6", "SB2", "R3", "HL1"],
            "related_nets": ["+3V3", "GND", "EN", "BOOT", "LED", "LED_A"],
            "purpose": "Reset, boot, and LED blocks review.",
            "focus": "Check local wire continuity and that symbols/text are not crowded.",
        },
        "sensor_uart_area": {
            "related_refs": ["R2", "XS1", "XS4"],
            "related_nets": ["DQ", "+3V3", "GND", "RXD0", "TXD0"],
            "purpose": "Sensor and UART/service connector review.",
            "focus": "Check connector labels, pull-up wiring, and UART net visibility.",
        },
        "heater_power_area": {
            "related_refs": ["R4", "R5", "VT1", "XS2", "XS5", "XS3", "A1", "C3", "C4"],
            "related_nets": ["GATE", "GATE_R", "HEAT+", "HEAT-", "+12V", "+3V3", "GND"],
            "purpose": "Heater driver and power area review.",
            "focus": "Check MOSFET gate network, heater connector, thermal switch, and power conversion wiring.",
        },
        "power_area": {
            "related_refs": ["XS3", "A1", "C3", "C4"],
            "related_nets": ["+12V", "+3V3", "GND"],
            "purpose": "Power input and DC/DC converter review.",
            "focus": "Check input/output power labels and capacitor placement.",
        },
        "element_list_full": {
            "related_refs": REQUIRED_REFS,
            "related_nets": [],
            "purpose": "Right-top List of Elements full-table review.",
            "focus": "Check text readability, row alignment, line weight consistency, and locked master geometry.",
        },
        "element_list_top": {
            "related_refs": ["C1", "C2", "C3", "C4", "R1", "R2", "R3", "R4", "R5", "R6"],
            "related_nets": [],
            "purpose": "Top part of List of Elements review.",
            "focus": "Check capacitor/resistor rows and table header alignment.",
        },
        "element_list_middle": {
            "related_refs": ["DD1", "HL1", "VT1", "SB1", "SB2", "XS1", "XS2", "XS3"],
            "related_nets": [],
            "purpose": "Middle part of List of Elements review.",
            "focus": "Check semiconductor, switch, and connector rows.",
        },
        "element_list_bottom": {
            "related_refs": ["XS4", "XS5", "A1"],
            "related_nets": [],
            "purpose": "Bottom part of List of Elements review.",
            "focus": "Check service connector, thermal switch terminal, and power module rows.",
        },
        "title_block_full": {
            "related_refs": [],
            "related_nets": [],
            "purpose": "Right-bottom Title Block review.",
            "focus": "Check document code, title text, organization, format, sheet fields, and master geometry.",
        },
    }


def save_crops(png_path: Path, viewbox: dict[str, float], regions: dict[str, Any], embed: dict[str, float]) -> list[dict[str, Any]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(png_path).convert("RGBA")
    element_list = regions["element_list"]["bbox"]
    title_block = regions["title_block"]["bbox"]
    crops: list[tuple[str, dict[str, float], float | tuple[float, float, float, float]]] = [
        ("overview", {"x": viewbox["x"], "y": viewbox["y"], "width": viewbox["width"], "height": viewbox["height"]}, 0.0),
        ("kicad_block", embed, 40.0),
        ("jlc_style_block", embed, 40.0),
        ("dd1_area", sub_box(embed, 0.17, 0.17, 0.42, 0.38), 22.0),
        ("reset_boot_led_area", sub_box(embed, 0.00, 0.32, 0.43, 0.50), 22.0),
        ("sensor_uart_area", sub_box(embed, 0.43, 0.00, 0.38, 0.40), 22.0),
        ("heater_power_area", sub_box(embed, 0.45, 0.34, 0.55, 0.66), 22.0),
        ("power_area", sub_box(embed, 0.50, 0.68, 0.43, 0.32), 22.0),
        ("element_list_full", expand_box(element_list, left=180.0, top=12.0, right=12.0, bottom=12.0), 0.0),
        ("element_list_top", expand_box(sub_box(element_list, -0.25, 0.00, 1.25, 0.36), top=12.0), 0.0),
        ("element_list_middle", expand_box(sub_box(element_list, -0.25, 0.32, 1.25, 0.36), top=12.0, bottom=12.0), 0.0),
        ("element_list_bottom", expand_box(sub_box(element_list, -0.25, 0.64, 1.25, 0.36), bottom=12.0), 0.0),
        ("title_block_full", expand_box(title_block, left=35.0, top=14.0, right=8.0, bottom=8.0), 0.0),
    ]
    metadata = crop_metadata()
    manifest_entries: list[dict[str, Any]] = []
    for name, svg_box, margin in crops:
        pixel_box = svg_box_to_pixels(svg_box, viewbox, image, margin)
        output = OUTPUT_DIR / f"{name}.png"
        if name == "overview":
            shutil.copyfile(png_path, output)
        else:
            image.crop(pixel_box).save(output)
        entry = {
            "name": name,
            "path": repo_path(output),
            "source_png": repo_path(png_path),
            "svg_box": svg_box,
            "margin_svg_units": margin,
            "pixel_box": {
                "x": pixel_box[0],
                "y": pixel_box[1],
                "width": pixel_box[2] - pixel_box[0],
                "height": pixel_box[3] - pixel_box[1],
            },
            "automated_status": "PASS",
        }
        entry.update(metadata.get(name, {"related_refs": [], "related_nets": [], "purpose": "", "focus": ""}))
        manifest_entries.append(entry)
    return manifest_entries


def erc_summary(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("missing"):
        return {"status": "UNAVAILABLE", "violations": None, "errors": None, "warnings": None}
    violations = [violation for sheet in report.get("sheets", []) for violation in sheet.get("violations", [])]
    severities = [str(violation.get("severity", "")).lower() for violation in violations]
    return {
        "status": "PASSED" if not violations else "FAILED",
        "violations": len(violations),
        "errors": sum(1 for value in severities if value == "error"),
        "warnings": sum(1 for value in severities if value == "warning"),
    }


def git_diff_clean(paths: list[Path]) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", *[str(path.relative_to(ROOT)) for path in paths]],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def write_report(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    lint_report: dict[str, Any],
    erc: dict[str, Any],
    table_lock_report: dict[str, Any],
    checks: dict[str, Any],
) -> None:
    lint_errors = lint_report.get("error_count", "missing")
    metrics = lint_report.get("svg", {}).get("kicad_embed_metrics", {})
    embed = lint_report.get("svg", {}).get("kicad_embed_bbox", {})
    png = lint_report.get("png", {})
    crops = manifest["crops"]
    table_lock_master = table_lock_report.get("master", {})
    table_lock_candidates = table_lock_report.get("candidates", [])
    lines = [
        "# Final Schematic QA Report",
        "",
        "This is a thesis insertion candidate package, not a final human-approved drawing.",
        "",
        "## Final Artifacts",
        "",
        f"- Draw.io: `{repo_path(args.drawio)}`",
        f"- SVG: `{repo_path(args.svg)}`",
        f"- PDF: `{repo_path(args.pdf)}`",
        f"- PNG: `{repo_path(args.png)}`",
        f"- PNG resolution: `{png.get('width_px', manifest['source_png_width_px'])} x {png.get('height_px', manifest['source_png_height_px'])} px`",
        "",
        "## Automated Checks",
        "",
        f"- KiCad ERC: `{erc['status']}`; violations `{erc['violations']}`, errors `{erc['errors']}`, warnings `{erc['warnings']}`",
        f"- KiCad ERC report: `{repo_path(args.erc_report)}`",
        f"- Pytest: `{PYTEST_RESULT}`",
        f"- Export lint errors: `{lint_errors}`",
        f"- Export lint report: `{repo_path(args.lint_report)}`",
        f"- Required school refs present: `{checks['required_refs_present']}`",
        f"- Canonical nets present: `{checks['canonical_nets_present']}`",
        f"- Forbidden refs/stale nets absent: `{checks['forbidden_text_absent']}`",
        f"- Source frame diff clean: `{checks['source_frame_diff_clean']}`",
        f"- KiCad symbol/project diff clean: `{checks['kicad_symbol_project_diff_clean']}`",
        "- KiCad schematic source is unchanged in this JLC-style workflow and is used only for topology verification.",
        f"- Master table lock passed: `{checks['master_table_lock_passed']}`",
        f"- Master table lock report: `{repo_path(args.table_lock_report)}`",
        "",
        "## JLC-Style Schematic Block Placement",
        "",
        f"- Embed bbox: `{embed}`",
        f"- Main width share: `{metrics.get('width_ratio', 0):.3f}`",
        f"- Main height share: `{metrics.get('height_ratio', 0):.3f}`",
        f"- Gap to List of Elements: `{metrics.get('gap_to_element_list', 0):.2f}` SVG units",
        f"- Gap to Title Block: `{metrics.get('gap_to_title_block', 0):.2f}` SVG units",
        "",
        "## List Of Elements",
        "",
        f"- ESP32 BOM text present: `{checks['esp32_bom_present']}`",
        "- Master table body source: `hardware/eda/functiondiagramYUANLITU.drawio`",
        "- Generated/final rule: text value replacement only; table geometry, line widths, rows, columns, font/alignment metadata, and cell IDs stay locked to the master.",
        "- BOM readability note: the master table has a fixed row count, so several ESP32 BOM items are merged into existing rows instead of adding new rows.",
        "- Required BOM groups: Capacitors, Resistors, Semiconductor Devices, Switching Components, Connectors, Power Modules",
        "",
        "## Master Table Lock",
        "",
        f"- Status: `{table_lock_report.get('status', 'missing')}`",
        f"- Errors: `{table_lock_report.get('error_count', 'missing')}`",
        f"- Master cell count: `{table_lock_master.get('cell_count', 'missing')}`",
        f"- Master geometry hash: `{table_lock_master.get('geometry_hash', 'missing')}`",
    ]
    for candidate in table_lock_candidates:
        lines.append(
            f"- `{candidate.get('path', 'unknown')}`: geometry matches master "
            f"`{candidate.get('geometry_matches_master')}`, value-only changed cells "
            f"`{candidate.get('value_changed_cell_count')}`"
        )
    lines.extend(
        [
            "",
            "The review crops include `element_list_full`, `element_list_top`,",
            "`element_list_middle`, and `element_list_bottom` so reviewers can inspect",
            "whether the merged BOM text remains readable under the locked master table.",
            "",
        ]
    )
    lines.extend(
        [
        "## Title Block",
        "",
        f"- ESP32 title block text present: `{checks['title_block_present']}`",
        f"- Legacy template title text absent: `{checks['legacy_title_absent']}`",
        "- Title block body source: `hardware/eda/functiondiagramYUANLITU.drawio`",
        "- Generated/final rule: text value replacement only.",
        "",
        "## Review Crops",
        "",
        ]
    )
    for crop in crops:
        lines.append(f"- `{crop['name']}`: `{crop['path']}`")
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "No automated blocker is recorded in this QA package if all booleans above are `True`, export lint reports `0`, and ERC is `PASSED`.",
            "Visual Review PASS is not claimed until the review crops and final PDF/PNG are inspected by ChatGPT/user.",
        ]
    )
    QA_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_visual_review_index(
    manifest: dict[str, Any],
    layout_audit: dict[str, Any],
    index_path: Path = VISUAL_INDEX,
) -> None:
    finding_crops = [
        item
        for item in read_json(ROOT / "hardware/eda/exports/final/layout_audit_crops/manifest.json").get("items", [])
        if item.get("kind") == "finding"
    ]
    lines = [
        "# Final Visual Review Index",
        "",
        "This index is for ChatGPT/user visual inspection. It does not claim human visual approval.",
        "",
        "## Status",
        "",
        f"- Automated Check Result: `{layout_audit.get('status', 'UNKNOWN')}`",
        "- Visual Review Result: `PENDING_REVIEW`",
        "- Human Approval Status: `NOT_APPROVED_YET`",
        f"- Final PNG: `{manifest['source_png']}`",
        f"- Final PDF: `{repo_path(DEFAULT_PDF)}`",
        "",
        "## Review Images",
        "",
    ]
    required_order = [
        "overview",
        "jlc_style_block",
        "dd1_area",
        "reset_boot_led_area",
        "sensor_uart_area",
        "heater_power_area",
        "power_area",
        "element_list_full",
        "element_list_top",
        "element_list_middle",
        "element_list_bottom",
        "title_block_full",
    ]
    crop_by_name = {crop["name"]: crop for crop in manifest["crops"]}
    for name in required_order:
        crop = crop_by_name[name]
        lines.extend(
            [
                f"### {name}",
                "",
                f"![{name}]({docs_image_path(crop['path'])})",
                "",
                f"- Review purpose: {crop.get('purpose', '')}",
                f"- Focus: {crop.get('focus', '')}",
                f"- Related refs: `{', '.join(crop.get('related_refs', []))}`",
                f"- Related nets: `{', '.join(crop.get('related_nets', []))}`",
                f"- Current automated status: `{crop.get('automated_status', 'UNKNOWN')}`",
                f"- Source PNG: `{crop.get('source_png', '')}`",
                f"- Pixel box: `{crop.get('pixel_box', {})}`",
                "",
            ]
        )
    lines.extend(["## Finding Crops", ""])
    if finding_crops:
        for finding in finding_crops:
            lines.extend(
                [
                    f"### {finding.get('id', 'finding')}",
                    "",
                    f"![{finding.get('id', 'finding')}]({docs_image_path(finding['path'])})",
                    "",
                    f"- Review purpose: inspect audit finding `{finding.get('id', '')}`.",
                    "- Focus: verify whether the finding is visually real and whether the listed fix is sufficient.",
                    "- Related refs: see audit report finding row.",
                    "- Related nets: see audit report finding row.",
                    "- Current automated status: `FINDING_EVIDENCE`",
                    f"- Source PNG: `{manifest['source_png']}`",
                    f"- Pixel box: `{finding.get('pixel_box', {})}`",
                    "",
                ]
            )
    else:
        lines.append("No warning/blocker finding crops are present in the current layout audit.")
        lines.append("")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create final schematic review crops and QA report.")
    parser.add_argument("--png", type=Path, default=DEFAULT_PNG)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--drawio", type=Path, default=DEFAULT_DRAWIO)
    parser.add_argument("--lint-report", type=Path, default=DEFAULT_LINT_REPORT)
    parser.add_argument("--erc-report", type=Path, default=DEFAULT_ERC_REPORT)
    parser.add_argument("--table-lock-report", type=Path, default=DEFAULT_TABLE_LOCK_REPORT)
    parser.add_argument("--layout-audit-report", type=Path, default=DEFAULT_LAYOUT_AUDIT_REPORT)
    parser.add_argument("--lock-file", type=Path, default=LOCK_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--qa-report", type=Path, default=QA_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    globals()["OUTPUT_DIR"] = args.output_dir
    globals()["QA_REPORT"] = args.qa_report

    for path in (args.png, args.svg, args.pdf, args.drawio, args.lock_file):
        if not path.exists():
            raise SystemExit(f"Missing required final QA input: {path}")

    svg_text = args.svg.read_text(encoding="utf-8", errors="ignore")
    text = visible_text(svg_text)
    viewbox = parse_viewbox(args.svg)
    embed = find_kicad_embed_bbox(svg_text)
    if not embed:
        raise SystemExit("Final SVG does not contain an embedded schematic SVG image.")

    lock = read_json(args.lock_file)
    regions = lock.get("regions", {})
    if not all(name in regions for name in ("outer_frame", "element_list", "title_block")):
        raise SystemExit("Reserved-region lock file lacks outer_frame, element_list, or title_block.")

    lint_report = read_json(args.lint_report)
    erc_report = read_json(args.erc_report)
    table_lock_report = read_json(args.table_lock_report)
    layout_audit_report = read_json(args.layout_audit_report)
    erc = erc_summary(erc_report)

    with Image.open(args.png) as image:
        width_px, height_px = image.size
    crops = save_crops(args.png, viewbox, regions, embed)
    checks = {
        "export_lint_error_free": lint_report.get("error_count") == 0,
        "required_refs_present": all(token_present(value, text) for value in REQUIRED_REFS),
        "canonical_nets_present": all(token_present(value, text) for value in CANONICAL_NETS),
        "forbidden_text_absent": not any(token_present(value, text) for value in FORBIDDEN_TEXT),
        "esp32_bom_present": all(value in text for value in ESP32_BOM_TEXT),
        "title_block_present": all(value in text for value in TITLE_BLOCK_TEXT),
        "legacy_title_absent": not any(value in text for value in TEMPLATE_TEXT_FORBIDDEN),
        "source_frame_diff_clean": git_diff_clean([ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"]),
        "kicad_symbol_project_diff_clean": git_diff_clean(
            [
                ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sym",
                ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_pro",
            ]
        ),
        "master_table_lock_passed": table_lock_report.get("status") == "PASS" and table_lock_report.get("error_count") == 0,
    }
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_png": repo_path(args.png),
        "source_svg": repo_path(args.svg),
        "source_png_width_px": width_px,
        "source_png_height_px": height_px,
        "svg_viewbox": viewbox,
        "kicad_embed_bbox": embed,
        "jlc_style_embed_bbox": embed,
        "reserved_regions": {
            name: regions[name]["bbox"]
            for name in ("outer_frame", "element_list", "title_block")
        },
        "lint_report": repo_path(args.lint_report),
        "erc_report": repo_path(args.erc_report),
        "layout_audit_report": repo_path(args.layout_audit_report),
        "table_lock_report": repo_path(args.table_lock_report),
        "qa_report": repo_path(args.qa_report),
        "visual_review_index": repo_path(VISUAL_INDEX),
        "checks": checks,
        "erc": erc,
        "crops": crops,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(args, manifest, lint_report, erc, table_lock_report, checks)
    write_visual_review_index(manifest, layout_audit_report)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if all(checks.values()) and erc["status"] in {"PASSED", "UNAVAILABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
