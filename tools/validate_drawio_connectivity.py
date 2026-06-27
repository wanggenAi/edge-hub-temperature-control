#!/usr/bin/env python3
"""Validate draw.io wire topology against the pin-level schematic model."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schematic_lint import ConnectivityValidator, DrawioParser, Finding, read_jsonish


def validate(drawio: Path, model_path: Path, report_path: Path | None = None, tolerance: float | None = None) -> tuple[list[Finding], dict[str, Any]]:
    rules_path = Path(__file__).resolve().parent / "schematic_rules.yaml"
    rules = read_jsonish(rules_path)
    if tolerance is not None:
        rules["connectivity"]["connection_tolerance_mm"] = tolerance
    rules["connectivity"]["model"] = str(model_path)
    schematic = DrawioParser().parse(drawio)
    findings, payload = ConnectivityValidator(rules, model_path).validate(schematic)
    payload["source"] = str(drawio)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload["findings"] = [asdict(f) for f in findings]
        payload["error_count"] = len([f for f in findings if f.severity == "error"])
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return findings, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("drawio", type=Path)
    parser.add_argument("--model", type=Path, default=Path("hardware/gost-schematic/schematic_model.yaml"))
    parser.add_argument("--report", type=Path, default=Path("build/reports/drawio_connectivity.json"))
    parser.add_argument("--tolerance", type=float, default=None)
    args = parser.parse_args()
    findings, _ = validate(args.drawio, args.model, args.report, args.tolerance)
    errors = [finding for finding in findings if finding.severity == "error"]
    print(f"drawio_connectivity: {len(errors)} error(s)")
    print(f"Report: {args.report}")
    if errors:
        for finding in errors:
            print(f"ERROR {finding.code}: {finding.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
