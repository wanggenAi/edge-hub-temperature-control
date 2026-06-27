#!/usr/bin/env python3
"""Validate the draw.io title block against the Form 1 template."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schematic_lint import DrawioParser, Finding, TitleBlockValidator, read_jsonish


def validate(drawio: Path, template_path: Path, report_path: Path | None = None) -> tuple[list[Finding], dict[str, Any]]:
    rules_path = Path(__file__).resolve().parent / "schematic_rules.yaml"
    rules = read_jsonish(rules_path)
    schematic = DrawioParser().parse(drawio)
    findings, payload = TitleBlockValidator(rules, template_path).validate(schematic)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload["findings"] = [asdict(f) for f in findings]
        payload["error_count"] = len([f for f in findings if f.severity == "error"])
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return findings, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("drawio", type=Path)
    parser.add_argument("--template", type=Path, default=Path("templates/gost_2_104_form1_title_block.yaml"))
    parser.add_argument("--report", type=Path, default=Path("build/reports/title_block_geometry.json"))
    args = parser.parse_args()
    findings, _ = validate(args.drawio, args.template, args.report)
    errors = [f for f in findings if f.severity == "error"]
    print(f"title_block_geometry: {len(errors)} error(s)")
    print(f"Report: {args.report}")
    if errors:
        for finding in errors:
            print(f"ERROR {finding.code}: {finding.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
