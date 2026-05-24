#!/usr/bin/env python3
"""Create a human confirmation package for real BOM MPN/manufacturer fields."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BOM = ROOT / "hardware/eda/jlc_schematic_bom.csv"
DEFAULT_MAPPING = ROOT / "hardware/eda/ref_mapping.yaml"
DEFAULT_AUDIT_JSON = ROOT / "build/reports/bom_mpn_manufacturer_audit.json"
DEFAULT_JSON = ROOT / "build/reports/bom_confirmation_package.json"
DEFAULT_MD = ROOT / "docs/bom_mpn_manufacturer_confirmation_package.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate BOM MPN/manufacturer confirmation package.")
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--ref-mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD)
    return parser.parse_args()


def repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    try:
        return str(absolute.relative_to(ROOT))
    except ValueError:
        return str(absolute)


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def load_mapping(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for item in data.get("mappings", []):
        source = clean(item.get("source_ref"))
        target = clean(item.get("confirmed_ref") or item.get("candidate_ref"))
        if source and target:
            mapping[source] = target
    return mapping


def read_bom(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-16")
    return [{clean(k): clean(v) for k, v in row.items()} for row in csv.DictReader(text.splitlines(), delimiter="\t")]


def read_audit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def expand_rows(rows: list[dict[str, str]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for row in rows:
        refs = [clean(ref) for ref in row.get("Designator", "").split(",") if clean(ref)]
        for source_ref in refs:
            school_ref = mapping.get(source_ref, source_ref)
            manufacturer_part = clean(row.get("Manufacturer Part"))
            manufacturer = clean(row.get("Manufacturer"))
            supplier_part = clean(row.get("Supplier Part"))
            supplier = clean(row.get("Supplier"))
            missing = []
            if not manufacturer_part:
                missing.append("Manufacturer Part")
            if not manufacturer:
                missing.append("Manufacturer")
            status = "confirmed_from_source_bom" if not missing else "needs_human_confirmation"
            expanded.append(
                {
                    "school_ref": school_ref,
                    "source_ref": source_ref,
                    "quantity": 1,
                    "source_quantity": clean(row.get("Quantity")),
                    "comment": clean(row.get("Comment")),
                    "footprint": clean(row.get("Footprint")),
                    "value": clean(row.get("Value")),
                    "manufacturer_part": manufacturer_part,
                    "manufacturer": manufacturer,
                    "supplier_part": supplier_part,
                    "supplier": supplier,
                    "missing_fields": missing,
                    "confirmation_status": status,
                    "user_confirmed_manufacturer_part": "",
                    "user_confirmed_manufacturer": "",
                    "user_notes": "",
                }
            )
    return expanded


def grouped_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        key = (item["comment"], item["footprint"], item["manufacturer_part"], item["manufacturer"])
        groups[key].append(item)
    rows = []
    for (comment, footprint, manufacturer_part, manufacturer), members in groups.items():
        rows.append(
            {
                "refs": ", ".join(item["school_ref"] for item in members),
                "source_refs": ", ".join(item["source_ref"] for item in members),
                "qty": len(members),
                "comment": comment,
                "footprint": footprint,
                "manufacturer_part": manufacturer_part,
                "manufacturer": manufacturer,
                "status": "confirmed_from_source_bom"
                if all(item["confirmation_status"] == "confirmed_from_source_bom" for item in members)
                else "needs_human_confirmation",
            }
        )
    return rows


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# BOM MPN / Manufacturer Confirmation Package",
        "",
        "This package is for human confirmation before changing the right-top List of Elements text.",
        "It is generated from the JLC BOM and does not invent missing MPN or Manufacturer values.",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report['created_at']}`",
        f"- Source BOM: `{report['inputs']['bom']}`",
        f"- Ref mapping: `{report['inputs']['ref_mapping']}`",
        f"- Audit report: `{report['inputs']['audit_json']}`",
        f"- Total school refs: `{report['summary']['item_count']}`",
        f"- Confirmed from source BOM: `{report['summary']['confirmed_count']}`",
        f"- Needs human confirmation: `{report['summary']['needs_confirmation_count']}`",
        "",
        "## Human Fill-In Instructions",
        "",
        "- Fill only `User confirmed MPN` and `User confirmed Manufacturer` for rows marked `needs_human_confirmation`.",
        "- Do not use `LCSC` as Manufacturer unless the actual manufacturer is confirmed to be LCSC.",
        "- Keep supplier PN separate from Manufacturer/MPN evidence.",
        "- After confirmation, update only List of Elements cell values; keep mother draw.io table geometry locked.",
        "",
        "## Grouped Confirmation Rows",
        "",
        "| Status | Refs | Source refs | Qty | Current source name/comment | Footprint | Source MPN | Source Manufacturer | Supplier PN | User confirmed MPN | User confirmed Manufacturer |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    supplier_by_group: dict[str, str] = {}
    for item in report["items"]:
        key = (item["comment"], item["footprint"], item["manufacturer_part"], item["manufacturer"])
        supplier_by_group.setdefault(str(key), item["supplier_part"])
    for row in report["grouped_items"]:
        key = str((row["comment"], row["footprint"], row["manufacturer_part"], row["manufacturer"]))
        lines.append(
            "| {status} | {refs} | {source_refs} | {qty} | {comment} | {footprint} | {mpn} | {manufacturer} | {supplier_part} |  |  |".format(
                status=row["status"],
                refs=row["refs"],
                source_refs=row["source_refs"],
                qty=row["qty"],
                comment=row["comment"] or "-",
                footprint=row["footprint"] or "-",
                mpn=row["manufacturer_part"] or "**MISSING**",
                manufacturer=row["manufacturer"] or "**MISSING**",
                supplier_part=supplier_by_group.get(key, "") or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Per-Ref Details",
            "",
            "| Status | Ref | Source ref | Comment | Footprint | Value | Source MPN | Source Manufacturer | Supplier PN | Supplier | Missing fields |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["items"]:
        lines.append(
            "| {status} | {school_ref} | {source_ref} | {comment} | {footprint} | {value} | {mpn} | {manufacturer} | {supplier_part} | {supplier} | {missing} |".format(
                status=item["confirmation_status"],
                school_ref=item["school_ref"],
                source_ref=item["source_ref"],
                comment=item["comment"] or "-",
                footprint=item["footprint"] or "-",
                value=item["value"] or "-",
                mpn=item["manufacturer_part"] or "**MISSING**",
                manufacturer=item["manufacturer"] or "**MISSING**",
                supplier_part=item["supplier_part"] or "-",
                supplier=item["supplier"] or "-",
                missing=", ".join(item["missing_fields"]) or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Source-Confirmed Items",
            "",
        ]
    )
    for item in report["items"]:
        if item["confirmation_status"] == "confirmed_from_source_bom":
            lines.append(f"- `{item['school_ref']}` from `{item['source_ref']}`: MPN `{item['manufacturer_part']}`, Manufacturer `{item['manufacturer']}`.")
    lines.extend(["", "## Items Requiring Confirmation", ""])
    for item in report["items"]:
        if item["confirmation_status"] == "needs_human_confirmation":
            missing = ", ".join(item["missing_fields"])
            source_hint = item["manufacturer_part"] or item["comment"] or item["value"] or item["footprint"]
            lines.append(
                f"- `{item['school_ref']}` from `{item['source_ref']}`: missing `{missing}`; source hint `{source_hint}`; supplier PN `{item['supplier_part'] or '-'}`."
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    mapping = load_mapping(args.ref_mapping)
    rows = read_bom(args.bom)
    items = expand_rows(rows, mapping)
    audit = read_audit(args.audit_json)
    confirmed_count = sum(1 for item in items if item["confirmation_status"] == "confirmed_from_source_bom")
    needs_count = len(items) - confirmed_count
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "NEEDS_BOM_MPN_CONFIRMATION" if needs_count else "CONFIRMED_FROM_SOURCE_BOM",
        "inputs": {
            "bom": repo_path(args.bom),
            "ref_mapping": repo_path(args.ref_mapping),
            "audit_json": repo_path(args.audit_json),
        },
        "summary": {
            "item_count": len(items),
            "confirmed_count": confirmed_count,
            "needs_confirmation_count": needs_count,
            "audit_status": audit.get("status", "UNKNOWN"),
            "audit_warning_count": audit.get("summary", {}).get("warning_count", "UNKNOWN"),
        },
        "grouped_items": grouped_summary(items),
        "items": items,
    }


def main() -> int:
    args = parse_args()
    for path in (args.bom, args.ref_mapping):
        if not path.exists():
            raise FileNotFoundError(path)
    report = build_report(args)
    write_json(args.json_output, report)
    write_markdown(args.md_output, report)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
