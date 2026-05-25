#!/usr/bin/env python3
"""Audit whether the List of Elements uses real MPN/model and Manufacturer fields."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOM = ROOT / "hardware/eda/jlc_schematic_bom.csv"
DEFAULT_MODEL = ROOT / "hardware/eda/schematic_model.yaml"
DEFAULT_MAPPING = ROOT / "hardware/eda/ref_mapping.yaml"
DEFAULT_CONFIRMED = ROOT / "hardware/eda/bom_mpn_manufacturer_confirmed.json"
DEFAULT_FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"
DEFAULT_JSON_REPORT = ROOT / "build/reports/bom_mpn_manufacturer_audit.json"
DEFAULT_MD_REPORT = ROOT / "docs/bom_mpn_manufacturer_audit_report.md"
ELEMENT_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"

SOURCE_TO_SCHOOL_FALLBACK = {
    "U1": "DD1",
    "Q1": "VT1",
    "D1": "HL1",
    "U3_reset": "SB1",
    "U4_boot": "SB2",
    "U3_buck": "A1",
    "CN1": "XS1",
    "J2_heater": "XS2",
    "J_Power": "XS3",
    "U7": "XS4",
    "J_TS1": "XS5",
}


@dataclass
class BomItem:
    school_ref: str
    source_ref: str
    quantity: int
    comment: str
    footprint: str
    value: str
    manufacturer_part: str
    manufacturer: str
    supplier_part: str
    supplier: str


@dataclass
class Finding:
    code: str
    severity: str
    object_id: str
    message: str
    expected: str = ""
    actual: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate BOM MPN and Manufacturer semantics in the final List of Elements.")
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--confirmed-bom", type=Path, default=DEFAULT_CONFIRMED)
    parser.add_argument("--final-drawio", type=Path, default=DEFAULT_FINAL_DRAWIO)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    return parser.parse_args()


def repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    try:
        return str(absolute.relative_to(ROOT))
    except ValueError:
        return str(absolute)


def clean(value: str) -> str:
    return " ".join((value or "").replace("\ufeff", "").split())


def normalized_manufacturer(value: str) -> str:
    value = clean(value)
    value = re.sub(r"\([^)]*\)", "", value)
    return clean(value)


def manufacturer_requires_confirmation(value: str) -> bool:
    return normalized_manufacturer(value).upper() in {"NEEDS_CONFIRMATION", "NEEDS_PURCHASE_CONFIRMATION"}


def normalized_mpn_tokens(value: str) -> list[str]:
    value = clean(value)
    tokens = [value] if value else []
    ascii_core = re.sub(r"[^\x00-\x7F].*$", "", value).strip()
    if ascii_core and ascii_core not in tokens:
        tokens.append(ascii_core)
    return tokens


def load_ref_mapping() -> dict[str, str]:
    if not DEFAULT_MAPPING.exists():
        return dict(SOURCE_TO_SCHOOL_FALLBACK)
    try:
        data = json.loads(DEFAULT_MAPPING.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(SOURCE_TO_SCHOOL_FALLBACK)
    mapping = dict(SOURCE_TO_SCHOOL_FALLBACK)
    for item in data.get("mappings", []):
        source = item.get("source_ref")
        target = item.get("confirmed_ref") or item.get("candidate_ref")
        if source and target:
            mapping[source] = target
    return mapping


def parse_bom(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-16")
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    return [{clean(key): clean(value) for key, value in row.items()} for row in rows]


def expand_bom_items(rows: list[dict[str, str]], mapping: dict[str, str]) -> list[BomItem]:
    items: list[BomItem] = []
    for row in rows:
        refs = [clean(ref) for ref in row.get("Designator", "").split(",") if clean(ref)]
        quantity = int(row.get("Quantity", "0") or 0)
        for source_ref in refs:
            school_ref = mapping.get(source_ref, source_ref)
            items.append(
                BomItem(
                    school_ref=school_ref,
                    source_ref=source_ref,
                    quantity=1 if len(refs) > 1 else quantity,
                    comment=row.get("Comment", ""),
                    footprint=row.get("Footprint", ""),
                    value=row.get("Value", ""),
                    manufacturer_part=row.get("Manufacturer Part", ""),
                    manufacturer=row.get("Manufacturer", ""),
                    supplier_part=row.get("Supplier Part", ""),
                    supplier=row.get("Supplier", ""),
                )
            )
    return items


def load_confirmed_items(path: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return {}, [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    by_ref: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        for ref in item.get("refs", []):
            by_ref[str(ref)] = item
    return by_ref, data.get("items", []), data.get("sources", [])


def apply_confirmed_items(items: list[BomItem], confirmed_by_ref: dict[str, dict[str, Any]]) -> None:
    for item in items:
        confirmed = confirmed_by_ref.get(item.school_ref)
        if not confirmed:
            continue
        if not item.manufacturer_part:
            item.manufacturer_part = clean(confirmed.get("manufacturer_part", ""))
        if not item.manufacturer:
            item.manufacturer = clean(confirmed.get("manufacturer", ""))


def parse_model_refs(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(component.get("ref")) for component in data.get("components", []) if component.get("ref")}


def plain_text(value: str) -> str:
    value = html.unescape(value or "").replace("\xa0", " ")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def list_of_elements_text(path: Path) -> str:
    root = ET.parse(path).find(".//root")
    if root is None:
        return ""
    values = []
    for cell in root:
        cell_id = cell.get("id", "")
        if cell_id.startswith(ELEMENT_PREFIX) or cell_id.startswith("element_list.generated."):
            values.append(plain_text(cell.get("value", "")))
    return "\n".join(values)


def token_present(token: str, text: str) -> bool:
    if not token:
        return False
    return re.search(rf"(?<![A-Za-z0-9_.+-]){re.escape(token)}(?![A-Za-z0-9_.+-])", text, flags=re.I) is not None


def add(finding_list: list[Finding], code: str, severity: str, object_id: str, message: str, expected: str = "", actual: str = "") -> None:
    finding_list.append(Finding(code, severity, object_id, message, expected, actual))


def audit(
    items: list[BomItem],
    model_refs: set[str],
    table_text: str,
    confirmed_by_ref: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    confirmed_by_ref = confirmed_by_ref or {}
    findings: list[Finding] = []
    unresolved: list[dict[str, Any]] = []
    package_review_items: list[dict[str, str]] = []
    for item in items:
        if model_refs and item.school_ref not in model_refs:
            add(findings, "BOM_REF_NOT_IN_MODEL", "error", item.school_ref, "BOM ref is not present in schematic_model.yaml", expected=item.school_ref)
        confirmed = confirmed_by_ref.get(item.school_ref, {})
        if confirmed.get("warning"):
            package_review_items.append(
                {
                    "ref": item.school_ref,
                    "manufacturer_part": clean(confirmed.get("manufacturer_part", "")),
                    "manufacturer": clean(confirmed.get("manufacturer", "")),
                    "warning": clean(confirmed.get("warning", "")),
                }
            )
            add(
                findings,
                "BOM_PACKAGE_OR_ORDERING_REVIEW_REQUIRED",
                "warning",
                item.school_ref,
                "External BOM source is usable for the table, but package/ordering details need review before purchasing",
                expected="Human order review",
                actual=clean(confirmed.get("warning", "")),
            )
        if not item.manufacturer_part or not item.manufacturer:
            missing = []
            if not item.manufacturer_part:
                missing.append("Manufacturer Part")
            if not item.manufacturer:
                missing.append("Manufacturer")
            unresolved.append({"ref": item.school_ref, "source_ref": item.source_ref, "missing": missing, "supplier_part": item.supplier_part, "supplier": item.supplier})
            add(
                findings,
                "NEEDS_BOM_MPN_CONFIRMATION",
                "warning",
                item.school_ref,
                "Source BOM and external confirmation data lack true MPN and/or Manufacturer; do not invent values for List of Elements",
                expected=", ".join(missing),
                actual=f"MPN={item.manufacturer_part or '<missing>'}, Manufacturer={item.manufacturer or '<missing>'}",
            )
        if item.manufacturer_part and not any(token_present(token, table_text) for token in normalized_mpn_tokens(item.manufacturer_part)):
            add(findings, "BOM_MPN_NOT_VISIBLE_IN_LIST", "warning", item.school_ref, "Known Manufacturer Part is not visible in List of Elements", expected=item.manufacturer_part)
        maker = normalized_manufacturer(item.manufacturer)
        if maker and not token_present(maker, table_text):
            if manufacturer_requires_confirmation(maker):
                add(findings, "BOM_MANUFACTURER_CONFIRMATION_MARKER_NOT_VISIBLE", "warning", item.school_ref, "Manufacturer is unknown and must be visibly marked NEEDS_CONFIRMATION in List of Elements", expected=maker)
            else:
                add(findings, "BOM_MANUFACTURER_NOT_VISIBLE_IN_NOTE", "warning", item.school_ref, "Known Manufacturer is not visible in List of Elements Note text", expected=maker)
    if re.search(r"(?<![A-Za-z0-9])JLCPCB Assembly(?![A-Za-z0-9])", table_text, flags=re.I):
        add(
            findings,
            "NOTE_USES_SUPPLIER_NOT_MANUFACTURER",
            "error",
            "element_list",
            "List of Elements Note text contains JLCPCB Assembly, which is a supplier/assembly source rather than verified Manufacturer",
            expected="Manufacturer or NEEDS_CONFIRMATION",
            actual="JLCPCB Assembly",
        )
    if re.search(r"(?<![A-Za-z0-9])\+5V(?![A-Za-z0-9])", table_text):
        add(
            findings,
            "BOM_POSITION_CONTAINS_NON_COMPONENT_NET",
            "error",
            "element_list",
            "+5V appears in List of Elements text; net labels must not appear as component position rows",
            expected="Only component refs in Position number column",
            actual="+5V",
        )
    if re.search(r"(?<![A-Za-z0-9])LCSC(?![A-Za-z0-9])", table_text):
        add(
            findings,
            "NOTE_USES_SUPPLIER_NOT_MANUFACTURER",
            "warning",
            "element_list",
            "List of Elements Note text contains LCSC, which is a supplier field unless explicitly confirmed as Manufacturer",
            expected="Manufacturer name",
            actual="LCSC",
        )
    summary = {
        "bom_item_count": len(items),
        "model_ref_count": len(model_refs),
        "unresolved_count": len(unresolved),
        "unresolved_items": unresolved,
        "known_mpn_count": sum(1 for item in items if item.manufacturer_part),
        "known_manufacturer_count": sum(1 for item in items if item.manufacturer),
        "externally_confirmed_count": sum(1 for item in items if item.school_ref in confirmed_by_ref),
        "package_review_count": len(package_review_items),
        "package_review_items": package_review_items,
    }
    return findings, summary


def write_reports(args: argparse.Namespace, report: dict[str, Any]) -> None:
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# BOM MPN / Manufacturer Audit Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Warnings: `{report['summary']['warning_count']}`",
        f"- Errors: `{report['summary']['error_count']}`",
        f"- Source BOM: `{repo_path(args.bom)}`",
        f"- External confirmation file: `{repo_path(args.confirmed_bom)}`",
        f"- Final draw.io: `{repo_path(args.final_drawio)}`",
        f"- Unresolved MPN/Manufacturer items: `{report['bom_summary']['unresolved_count']}`",
        f"- External confirmations used: `{report['bom_summary']['externally_confirmed_count']}`",
        f"- Package/order review warnings: `{report['bom_summary']['package_review_count']}`",
        "",
        "## Policy",
        "",
        "- Name column should use real purchasable model/MPN plus specs.",
        "- Note column should use Manufacturer, not supplier.",
        "- Missing source MPN/Manufacturer is reported as `NEEDS_BOM_MPN_CONFIRMATION`; no AI-invented values are created.",
        "",
        "## Unresolved Items",
        "",
    ]
    for item in report["bom_summary"]["unresolved_items"]:
        lines.append(f"- `{item['ref']}` from `{item['source_ref']}`: missing `{', '.join(item['missing'])}`; supplier PN `{item.get('supplier_part', '')}` supplier `{item.get('supplier', '')}`")
    if not report["bom_summary"]["unresolved_items"]:
        lines.append("No unresolved MPN/Manufacturer items.")
    lines.extend(["", "## Package / Ordering Review Items", ""])
    if report["bom_summary"]["package_review_items"]:
        for item in report["bom_summary"]["package_review_items"]:
            lines.append(f"- `{item['ref']}` `{item['manufacturer_part']}` `{item['manufacturer']}`: {item['warning']}")
    else:
        lines.append("No package/order review warnings.")
    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['code']}` `{finding['object_id']}`: {finding['message']}")
    else:
        lines.append("No findings.")
    args.md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    for path in (args.bom, args.model, args.final_drawio):
        if not path.exists():
            raise FileNotFoundError(path)
    mapping = load_ref_mapping()
    rows = parse_bom(args.bom)
    items = expand_bom_items(rows, mapping)
    confirmed_by_ref, confirmed_items, confirmed_sources = load_confirmed_items(args.confirmed_bom)
    apply_confirmed_items(items, confirmed_by_ref)
    model_refs = parse_model_refs(args.model)
    table_text = list_of_elements_text(args.final_drawio)
    findings, bom_summary = audit(items, model_refs, table_text, confirmed_by_ref)
    error_count = sum(1 for item in findings if item.severity == "error")
    warning_count = sum(1 for item in findings if item.severity == "warning")
    status = "PASS" if not findings else ("WARN" if error_count == 0 else "FAIL")
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "inputs": {
            "bom": repo_path(args.bom),
            "confirmed_bom": repo_path(args.confirmed_bom),
            "model": repo_path(args.model),
            "final_drawio": repo_path(args.final_drawio),
        },
        "summary": {
            "error_count": error_count,
            "warning_count": warning_count,
            "finding_count": len(findings),
        },
        "bom_summary": bom_summary,
        "external_confirmed_items": confirmed_items,
        "external_sources": confirmed_sources,
        "items": [asdict(item) for item in items],
        "findings": [asdict(item) for item in findings],
    }
    write_reports(args, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
