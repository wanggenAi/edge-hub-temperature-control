#!/usr/bin/env python3
"""Validate generated/final draw.io tables keep the master table geometry unchanged."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
MASTER_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
GENERATED_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"
REPORT_MD = ROOT / "docs/bstu_master_table_lock_report.md"
REPORT_JSON = ROOT / "build/reports/bstu_master_table_lock.json"
ELEMENT_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"
TITLE_PREFIX = "pFFQBGnBG81xobuCz_b_-"
ALLOWED_VALUE_ONLY_IDS = {
    # Element list text cells.
    *(f"{ELEMENT_PREFIX}{index}" for index in (6, 7, 8, 9, 12, 13, 14, 15, 16, 18, 19, 20, 21, 25, 26, 27, 28, 30, 31, 32, 35, 37, 38, 39, 40, 42, 43, 44, 45, 50, 51, 52, 53, 54, 55, 56, 57, 60, 61, 62)),
    # Title block text cells.
    *(f"{TITLE_PREFIX}{index}" for index in (18, 19, 20, 21, 22, 23, 24, 25, 36, 37, 38, 39)),
}


@dataclass
class Finding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated/final BSTU tables match the master draw.io table geometry.")
    parser.add_argument("--master", type=Path, default=MASTER_DRAWIO)
    parser.add_argument("--candidate", type=Path, default=GENERATED_DRAWIO)
    parser.add_argument("--final-candidate", type=Path, default=FINAL_DRAWIO)
    parser.add_argument("--report", type=Path, default=REPORT_MD)
    parser.add_argument("--json-report", type=Path, default=REPORT_JSON)
    return parser.parse_args()


def parse_drawio(path: Path) -> ET.Element:
    if not path.exists():
        raise FileNotFoundError(path)
    root = ET.parse(path).find(".//root")
    if root is None:
        raise ValueError(f"draw.io file has no mxGraphModel/root: {path}")
    return root


def plain_text(value: str) -> str:
    value = html.unescape(value or "").replace("\xa0", " ")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def geometry_signature(cell: ET.Element) -> dict[str, Any]:
    geom = cell.find("mxGeometry")
    children: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    geom_attrs: tuple[tuple[str, str], ...] = ()
    if geom is not None:
        geom_attrs = tuple(sorted(geom.attrib.items()))
        for child in geom:
            children.append((child.tag, tuple(sorted(child.attrib.items()))))
    return {
        # The generated/final drawings may replace only cell text. Every other
        # mxCell attribute belongs to the locked master table body.
        "attributes": tuple(sorted((key, value) for key, value in cell.attrib.items() if key != "value")),
        "geometry": geom_attrs,
        "geometry_children": children,
    }


def value_signature(cell: ET.Element) -> str:
    return plain_text(cell.get("value", ""))


def table_cells(root: ET.Element) -> dict[str, ET.Element]:
    cells: dict[str, ET.Element] = {}
    for cell in root:
        cell_id = cell.get("id", "")
        if cell_id.startswith(ELEMENT_PREFIX) or cell_id.startswith(TITLE_PREFIX):
            cells[cell_id] = cell
    return cells


def digest_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def master_signature(path: Path) -> dict[str, Any]:
    root = parse_drawio(path)
    cells = table_cells(root)
    geometry = {cell_id: geometry_signature(cell) for cell_id, cell in sorted(cells.items())}
    values = {cell_id: value_signature(cell) for cell_id, cell in sorted(cells.items())}
    return {
        "path": str(path),
        "cell_count": len(cells),
        "cell_ids": sorted(cells),
        "geometry_hash": digest_payload(geometry),
        "value_hash": digest_payload(values),
        "geometry": geometry,
        "values": values,
    }


def compare_candidate(master: dict[str, Any], candidate_path: Path) -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    root = parse_drawio(candidate_path)
    candidate_cells = table_cells(root)
    candidate_geometry = {cell_id: geometry_signature(cell) for cell_id, cell in sorted(candidate_cells.items())}
    candidate_values = {cell_id: value_signature(cell) for cell_id, cell in sorted(candidate_cells.items())}
    master_ids = set(master["cell_ids"])
    candidate_ids = set(candidate_cells)
    missing = sorted(master_ids - candidate_ids)
    extra = sorted(candidate_ids - master_ids)
    for cell_id in missing:
        findings.append(Finding("MASTER_TABLE_CELL_MISSING", "error", cell_id, "Candidate is missing a master table cell"))
    for cell_id in extra:
        findings.append(Finding("MASTER_TABLE_EXTRA_CELL", "error", cell_id, "Candidate contains an extra generated table cell"))
    for cell_id in sorted(master_ids & candidate_ids):
        expected_geometry = master["geometry"][cell_id]
        actual_geometry = candidate_geometry[cell_id]
        if expected_geometry != actual_geometry:
            findings.append(
                Finding(
                    "MASTER_TABLE_GEOMETRY_CHANGED",
                    "error",
                    cell_id,
                    "Candidate changed master table geometry/style/line/font/alignment metadata",
                    json.dumps(expected_geometry, ensure_ascii=False, sort_keys=True),
                    json.dumps(actual_geometry, ensure_ascii=False, sort_keys=True),
                )
            )
    summary = {
        "path": str(candidate_path),
        "cell_count": len(candidate_cells),
        "cell_ids_match": not missing and not extra,
        "geometry_hash": digest_payload(candidate_geometry),
        "geometry_matches_master": digest_payload(candidate_geometry) == master["geometry_hash"],
        "value_hash": digest_payload(candidate_values),
        "value_changed_cell_count": sum(1 for cell_id in master_ids & candidate_ids if master["values"][cell_id] != candidate_values[cell_id]),
        "value_only_changed_ids": sorted(cell_id for cell_id in master_ids & candidate_ids if master["values"][cell_id] != candidate_values[cell_id]),
    }
    disallowed_value_changes = sorted(set(summary["value_only_changed_ids"]) - ALLOWED_VALUE_ONLY_IDS)
    for cell_id in disallowed_value_changes:
        findings.append(
            Finding(
                "MASTER_TABLE_VALUE_CHANGED_IN_NON_TEXT_CELL",
                "error",
                cell_id,
                "Candidate changed value on a table cell that is not in the approved text-cell allowlist",
                master["values"].get(cell_id, ""),
                candidate_values.get(cell_id, ""),
            )
        )
    return findings, summary


def write_reports(master: dict[str, Any], candidates: list[dict[str, Any]], findings: list[Finding], md_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "PASS" if not findings else "FAILED",
        "error_count": len(findings),
        "master": {
            "path": master["path"],
            "cell_count": master["cell_count"],
            "geometry_hash": master["geometry_hash"],
            "value_hash": master["value_hash"],
        },
        "candidates": candidates,
        "findings": [asdict(finding) for finding in findings],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# BSTU Master Table Lock Report",
        "",
        f"- Status: **{payload['status']}**",
        f"- Errors: `{payload['error_count']}`",
        f"- Master: `{master['path']}`",
        f"- Master table cell count: `{master['cell_count']}`",
        f"- Master geometry hash: `{master['geometry_hash']}`",
        "",
        "## Candidate Results",
    ]
    for candidate in candidates:
        lines.extend(
            [
                f"- Candidate: `{candidate['path']}`",
                f"  - Cell count: `{candidate['cell_count']}`",
                f"  - Cell IDs match: `{candidate['cell_ids_match']}`",
                f"  - Geometry matches master: `{candidate['geometry_matches_master']}`",
                f"  - Geometry hash: `{candidate['geometry_hash']}`",
                f"  - Value-only changed cell count: `{candidate['value_changed_cell_count']}`",
            ]
        )
    if findings:
        lines.extend(["", "## Findings"])
        for finding in findings:
            lines.append(f"- **{finding.code}** `{finding.object_id}`: {finding.message}")
    else:
        lines.extend(
            [
                "",
                "No table geometry/style/font/alignment/line-width differences from the master draw.io tables were detected.",
                "Only approved table text-cell values differ.",
            ]
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    master = master_signature(args.master)
    all_findings: list[Finding] = []
    summaries: list[dict[str, Any]] = []
    candidate_paths = list(dict.fromkeys((args.candidate, args.final_candidate)))
    for candidate in candidate_paths:
        findings, summary = compare_candidate(master, candidate)
        all_findings.extend(findings)
        summaries.append(summary)
    write_reports(master, summaries, all_findings, args.report, args.json_report)
    print(f"BSTU master table lock: {'PASS' if not all_findings else 'FAILED'}")
    print(f"JSON report: {args.json_report}")
    print(f"Markdown report: {args.report}")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
