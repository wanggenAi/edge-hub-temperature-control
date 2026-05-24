#!/usr/bin/env python3
"""Compare the JLC TEL netlist against the current KiCad schematic topology.

The checker is deliberately read-only. It normalizes JLC refs/nets through the
confirmed thesis mapping and then compares component-pin membership per net
against the connectivity graph extracted from the KiCad schematic.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


Point = tuple[float, float]
PointKey = tuple[float, float]


@dataclass(frozen=True)
class Connection:
    ref: str
    pin: str
    net: str
    raw_ref: str = ""
    raw_pin: str = ""
    raw_net: str = ""

    @property
    def node(self) -> str:
        return f"{self.ref}.{self.pin}"


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    expected: Any = ""
    actual: Any = ""
    object_id: str = ""


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[PointKey, PointKey] = {}

    def add(self, point: PointKey) -> None:
        self.parent.setdefault(point, point)

    def find(self, point: PointKey) -> PointKey:
        self.add(point)
        parent = self.parent[point]
        if parent != point:
            self.parent[point] = self.find(parent)
        return self.parent[point]

    def union(self, left: PointKey, right: PointKey) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def load_jsonish(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} must be JSON-compatible YAML in this environment: {exc}") from exc


def strip_net_name(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1]
    return raw


def parse_jlc_tel(path: Path, rules: dict[str, Any]) -> list[Connection]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"\$NETS\s*(.*?)\s*\$(?:SCHEDULE|END)", text, flags=re.S)
    if not match:
        raise ValueError(f"No $NETS section found in {path}")
    net_section = match.group(1)
    entries = list(
        re.finditer(
            r"(?P<net>'[^']+'|[^\s;]+)\s*;\s*(?P<body>.*?)(?=\n(?:'[^']+'|[A-Za-z0-9_$+.-]+)\s*;|\Z)",
            net_section,
            flags=re.S,
        )
    )
    ref_map = rules.get("ref_mappings", {})
    net_map = rules.get("net_mappings", {})
    pin_aliases = rules.get("pin_aliases", {})
    connections: list[Connection] = []
    for entry in entries:
        raw_net = strip_net_name(entry.group("net"))
        normalized_net = net_map.get(raw_net)
        body = entry.group("body").replace(",", " ")
        for token in re.findall(r"([A-Za-z0-9_]+(?:_[A-Za-z0-9]+)?|J_Power|J_TS1|J2_heater|U3_reset|U4_boot|U3_buck|CN1|U7|U1|Q1|D1|R\d+|C\d+)\.([A-Za-z0-9_+-]+)", body):
            raw_ref, raw_pin = token
            normalized_ref = ref_map.get(raw_ref)
            normalized_pin = pin_aliases.get(raw_ref, {}).get(raw_pin, raw_pin)
            connections.append(
                Connection(
                    ref=normalized_ref or raw_ref,
                    pin=normalized_pin,
                    net=normalized_net or raw_net,
                    raw_ref=raw_ref,
                    raw_pin=raw_pin,
                    raw_net=raw_net,
                )
            )
    return connections


def tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if char in "()":
            tokens.append(char)
            i += 1
            continue
        if char == '"':
            i += 1
            value: list[str] = []
            while i < len(text):
                if text[i] == "\\" and i + 1 < len(text):
                    value.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                value.append(text[i])
                i += 1
            tokens.append("".join(value))
            continue
        start = i
        while i < len(text) and not text[i].isspace() and text[i] not in "()":
            i += 1
        tokens.append(text[start:i])
    return tokens


def parse_sexpr(text: str) -> list[Any]:
    tokens = tokenize_sexpr(text)
    index = 0

    def parse_one() -> Any:
        nonlocal index
        if index >= len(tokens):
            raise ValueError("Unexpected end of S-expression")
        token = tokens[index]
        index += 1
        if token == "(":
            items: list[Any] = []
            while index < len(tokens) and tokens[index] != ")":
                items.append(parse_one())
            if index >= len(tokens):
                raise ValueError("Unclosed S-expression list")
            index += 1
            return items
        if token == ")":
            raise ValueError("Unexpected closing parenthesis")
        return token

    parsed = parse_one()
    if index != len(tokens):
        raise ValueError("Trailing tokens after S-expression")
    if not isinstance(parsed, list):
        raise ValueError("Expected root list")
    return parsed


def lists_named(tree: Any, name: str) -> Iterable[list[Any]]:
    if isinstance(tree, list):
        if tree and tree[0] == name:
            yield tree
        for child in tree:
            yield from lists_named(child, name)


def child_named(items: list[Any], name: str) -> list[Any] | None:
    for item in items:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def property_value(items: list[Any], name: str) -> str | None:
    for item in items:
        if isinstance(item, list) and len(item) >= 3 and item[0] == "property" and item[1] == name:
            return str(item[2])
    return None


def as_float(value: Any) -> float:
    return float(str(value))


def point_key(point: Point, digits: int = 3) -> PointKey:
    return (round(point[0], digits), round(point[1], digits))


def rotate_point(point: Point, degrees: float) -> Point:
    if abs(degrees) < 1e-9:
        return point
    radians = math.radians(degrees)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    return (point[0] * cos_v - point[1] * sin_v, point[0] * sin_v + point[1] * cos_v)


def parse_lib_symbol_pins(root: list[Any]) -> dict[str, dict[str, Point]]:
    lib_symbols = child_named(root, "lib_symbols")
    if not lib_symbols:
        raise ValueError("No lib_symbols block found in KiCad schematic")
    result: dict[str, dict[str, Point]] = {}
    for symbol in lib_symbols[1:]:
        if not isinstance(symbol, list) or len(symbol) < 2 or symbol[0] != "symbol":
            continue
        lib_id = str(symbol[1])
        pins: dict[str, Point] = {}
        for pin in lists_named(symbol, "pin"):
            at = child_named(pin, "at")
            number = child_named(pin, "number")
            if not at or len(at) < 3 or not number or len(number) < 2:
                continue
            pins[str(number[1])] = (as_float(at[1]), as_float(at[2]))
        result[lib_id] = pins
    return result


def parse_kicad_schematic(path: Path) -> tuple[list[Connection], dict[str, Any]]:
    xml_path = Path("build/reports/jlc_kicad_netlist_equivalence.kicad.xml")
    export_kicad_xml_netlist(path, xml_path)
    return parse_kicad_xml_netlist(xml_path)


def find_kicad_cli() -> str:
    candidates = [
        os.environ.get("KICAD_CLI", ""),
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        shutil.which("kicad-cli") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
        if candidate and shutil.which(candidate):
            return candidate
    raise RuntimeError("KICAD_CLI_UNAVAILABLE: kicad-cli was not found, so KiCad topology cannot be exported for equivalence checking")


def export_kicad_xml_netlist(schematic: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cli = find_kicad_cli()
    command = [
        cli,
        "sch",
        "export",
        "netlist",
        str(schematic),
        "--format",
        "kicadxml",
        "--output",
        str(output),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def parse_kicad_xml_netlist(path: Path) -> tuple[list[Connection], dict[str, Any]]:
    root = ET.parse(path).getroot()
    connections: list[Connection] = []
    net_count = 0
    for net in root.findall(".//nets/net"):
        net_name = net.get("name", "")
        if not net_name:
            continue
        net_count += 1
        for node in net.findall("node"):
            ref = node.get("ref", "")
            pin = node.get("pin", "")
            if ref and pin:
                connections.append(Connection(ref=ref, pin=pin, net=net_name))
    metadata = {
        "source": "kicad-cli sch export netlist --format kicadxml",
        "xml_netlist": str(path),
        "net_count": net_count,
        "connection_count": len(connections),
        "diagonal_wires": [],
        "unlabelled_pins": [],
        "net_conflicts": [],
    }
    return sorted(connections, key=lambda c: (c.net, c.ref, c.pin)), metadata


def parse_kicad_schematic_geometry_graph(path: Path) -> tuple[list[Connection], dict[str, Any]]:
    root = parse_sexpr(path.read_text(encoding="utf-8"))
    lib_pins = parse_lib_symbol_pins(root)
    symbols: dict[str, dict[str, Any]] = {}
    pin_points: dict[PointKey, list[tuple[str, str]]] = defaultdict(list)
    wires: list[tuple[Point, Point]] = []
    labels: dict[PointKey, set[str]] = defaultdict(set)
    diagonal_wires: list[tuple[Point, Point]] = []

    for item in root[1:]:
        if not isinstance(item, list) or not item:
            continue
        kind = item[0]
        if kind == "symbol" and child_named(item, "lib_id"):
            lib_id = str(child_named(item, "lib_id")[1])
            at = child_named(item, "at")
            ref = property_value(item, "Reference")
            if not at or len(at) < 3 or not ref:
                continue
            origin = (as_float(at[1]), as_float(at[2]))
            rotation = as_float(at[3]) if len(at) >= 4 else 0.0
            symbols[ref] = {"lib_id": lib_id, "origin": origin, "rotation": rotation}
            for pin_number, local_point in lib_pins.get(lib_id, {}).items():
                rotated = rotate_point(local_point, rotation)
                endpoint = (origin[0] + rotated[0], origin[1] + rotated[1])
                pin_points[point_key(endpoint)].append((ref, pin_number))
        elif kind == "wire":
            pts = child_named(item, "pts")
            if not pts:
                continue
            points = [(as_float(xy[1]), as_float(xy[2])) for xy in pts[1:] if isinstance(xy, list) and xy and xy[0] == "xy"]
            for left, right in zip(points, points[1:]):
                wires.append((left, right))
                if abs(left[0] - right[0]) > 1e-6 and abs(left[1] - right[1]) > 1e-6:
                    diagonal_wires.append((left, right))
        elif kind == "global_label" and len(item) >= 2:
            at = child_named(item, "at")
            if at and len(at) >= 3:
                labels[point_key((as_float(at[1]), as_float(at[2])))].add(str(item[1]))

    uf = UnionFind()
    important_points: set[PointKey] = set(labels) | set(pin_points)
    for left, right in wires:
        important_points.add(point_key(left))
        important_points.add(point_key(right))
    for key in important_points:
        uf.add(key)

    for left, right in wires:
        left_key = point_key(left)
        right_key = point_key(right)
        candidates = [left_key, right_key]
        if abs(left[0] - right[0]) <= 1e-6:
            x = left[0]
            low, high = sorted((left[1], right[1]))
            for point in important_points:
                if abs(point[0] - x) <= 0.001 and low - 0.001 <= point[1] <= high + 0.001:
                    candidates.append(point)
            candidates = sorted(set(candidates), key=lambda p: p[1])
        elif abs(left[1] - right[1]) <= 1e-6:
            y = left[1]
            low, high = sorted((left[0], right[0]))
            for point in important_points:
                if abs(point[1] - y) <= 0.001 and low - 0.001 <= point[0] <= high + 0.001:
                    candidates.append(point)
            candidates = sorted(set(candidates), key=lambda p: p[0])
        else:
            candidates = [left_key, right_key]
        for a, b in zip(candidates, candidates[1:]):
            uf.union(a, b)

    labels_by_root: dict[PointKey, set[str]] = defaultdict(set)
    for point, names in labels.items():
        labels_by_root[uf.find(point)].update(names)

    connections: list[Connection] = []
    unlabelled_pins: list[str] = []
    net_conflicts: list[dict[str, Any]] = []
    for root_key, names in labels_by_root.items():
        if len(names) > 1:
            net_conflicts.append({"point": list(root_key), "labels": sorted(names)})
    for point, pin_refs in pin_points.items():
        root_key = uf.find(point)
        names = sorted(labels_by_root.get(root_key, set()))
        net = names[0] if len(names) == 1 else ""
        for ref, pin in pin_refs:
            if net:
                connections.append(Connection(ref=ref, pin=pin, net=net))
            else:
                unlabelled_pins.append(f"{ref}.{pin}@{point[0]},{point[1]}")

    metadata = {
        "symbols": symbols,
        "wire_count": len(wires),
        "label_count": sum(len(v) for v in labels.values()),
        "pin_count": sum(len(v) for v in pin_points.values()),
        "diagonal_wires": diagonal_wires,
        "unlabelled_pins": sorted(unlabelled_pins),
        "net_conflicts": net_conflicts,
    }
    return sorted(connections, key=lambda c: (c.net, c.ref, c.pin)), metadata


def connections_by_net(connections: list[Connection]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for connection in connections:
        result[connection.net].add(connection.node)
    return result


def connections_by_component(connections: list[Connection]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = defaultdict(dict)
    for connection in connections:
        result[connection.ref][connection.pin] = connection.net
    return result


def compare_connections(jlc: list[Connection], kicad: list[Connection], rules: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    findings: list[Finding] = []
    ref_map = rules.get("ref_mappings", {})
    net_map = rules.get("net_mappings", {})
    known_refs = set(ref_map.values())
    known_nets = set(net_map.values())

    unmapped_refs = sorted({c.raw_ref for c in jlc if c.raw_ref and c.raw_ref not in ref_map})
    unmapped_nets = sorted({c.raw_net for c in jlc if c.raw_net and c.raw_net not in net_map})
    for raw_ref in unmapped_refs:
        findings.append(Finding("UNMAPPED_JLC_REF", "error", "JLC ref is not listed in equivalence rules", object_id=raw_ref))
    for raw_net in unmapped_nets:
        findings.append(Finding("UNMAPPED_JLC_NET", "error", "JLC net is not listed in equivalence rules", object_id=raw_net))

    jlc_by_net = connections_by_net(jlc)
    kicad_by_net = connections_by_net(kicad)
    per_net: list[dict[str, Any]] = []
    for net in sorted(set(jlc_by_net) | set(kicad_by_net)):
        expected = jlc_by_net.get(net, set())
        actual = kicad_by_net.get(net, set())
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        status = "PASS" if not missing and not extra else "FAIL"
        if missing:
            findings.append(Finding("MISSING_COMPONENT_PIN_ON_NET", "error", f"KiCad net {net} is missing expected JLC component pins", expected=missing, actual=sorted(actual), object_id=net))
        if extra:
            findings.append(Finding("EXTRA_COMPONENT_PIN_ON_NET", "error", f"KiCad net {net} has component pins absent from JLC", expected=sorted(expected), actual=extra, object_id=net))
        per_net.append({"net": net, "status": status, "jlc_pins": sorted(expected), "kicad_pins": sorted(actual), "missing": missing, "extra": extra})

    jlc_by_component = connections_by_component(jlc)
    kicad_by_component = connections_by_component(kicad)
    per_component: list[dict[str, Any]] = []
    for ref in sorted(set(jlc_by_component) | set(kicad_by_component)):
        expected = jlc_by_component.get(ref, {})
        actual = kicad_by_component.get(ref, {})
        missing = {pin: net for pin, net in expected.items() if actual.get(pin) != net}
        extra = {pin: net for pin, net in actual.items() if expected.get(pin) != net}
        status = "PASS" if not missing and not extra else "FAIL"
        per_component.append({"ref": ref, "status": status, "jlc_pin_nets": dict(sorted(expected.items())), "kicad_pin_nets": dict(sorted(actual.items())), "missing_or_changed": missing, "extra_or_changed": extra})

    for net, pins in kicad_by_net.items():
        if net not in known_nets:
            findings.append(Finding("UNEXPECTED_KICAD_NET", "error", "KiCad contains a net not listed in canonical equivalence rules", object_id=net, actual=sorted(pins)))
    for ref in kicad_by_component:
        if ref not in known_refs:
            findings.append(Finding("UNEXPECTED_KICAD_REF", "error", "KiCad contains a ref not listed in confirmed equivalence rules", object_id=ref))
    for segment in metadata.get("diagonal_wires", []):
        findings.append(Finding("KICAD_DIAGONAL_WIRE", "error", "KiCad wire segment is not horizontal or vertical", object_id=str(segment)))
    for pin in metadata.get("unlabelled_pins", []):
        findings.append(Finding("KICAD_PIN_WITHOUT_NET_LABEL", "error", "KiCad component pin is not connected to a labelled net", object_id=pin))
    for conflict in metadata.get("net_conflicts", []):
        findings.append(Finding("KICAD_NET_LABEL_CONFLICT", "error", "KiCad connected component has multiple different labels", object_id=str(conflict.get("point")), actual=conflict.get("labels")))

    blockers = [finding for finding in findings if finding.severity == "error"]
    status = "PASS" if not blockers else "FAIL"
    return {
        "status": status,
        "summary": {
            "total_jlc_nets_parsed": len({connection.raw_net for connection in jlc if connection.raw_net}),
            "total_jlc_raw_nets_parsed": len({connection.raw_net for connection in jlc if connection.raw_net}),
            "total_jlc_canonical_nets_parsed": len(jlc_by_net),
            "total_kicad_nets_parsed": len(kicad_by_net),
            "total_jlc_connections": len(jlc),
            "total_kicad_connections": len(kicad),
            "mapped_refs_count": len(ref_map),
            "mapped_nets_count": len(net_map),
            "unmapped_refs_count": len(unmapped_refs),
            "unmapped_nets_count": len(unmapped_nets),
            "blocker_count": len(blockers),
            "warning_count": 0,
        },
        "unmapped_refs": unmapped_refs,
        "unmapped_nets": unmapped_nets,
        "per_net": per_net,
        "per_component": per_component,
        "blockers": [finding.__dict__ for finding in blockers],
        "warnings": [],
        "kicad_metadata": metadata,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines: list[str] = [
        "# JLC / KiCad Netlist Equivalence Report",
        "",
        f"Final status: **{report['status']}**",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Per-Net Comparison", "", "| Net | Status | JLC Pins | KiCad Pins | Missing | Extra |", "| --- | --- | --- | --- | --- | --- |"])
    for row in report["per_net"]:
        lines.append(
            f"| {row['net']} | {row['status']} | {', '.join(row['jlc_pins'])} | {', '.join(row['kicad_pins'])} | {', '.join(row['missing'])} | {', '.join(row['extra'])} |"
        )
    lines.extend(["", "## Per-Component Comparison", "", "| Ref | Status | JLC Pin Nets | KiCad Pin Nets |", "| --- | --- | --- | --- |"])
    for row in report["per_component"]:
        jlc = ", ".join(f"{pin}:{net}" for pin, net in row["jlc_pin_nets"].items())
        kicad = ", ".join(f"{pin}:{net}" for pin, net in row["kicad_pin_nets"].items())
        lines.append(f"| {row['ref']} | {row['status']} | {jlc} | {kicad} |")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- `{blocker['code']}` `{blocker.get('object_id', '')}`: {blocker['message']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append(f"- `{warning['code']}` `{warning.get('object_id', '')}`: {warning['message']}")
    else:
        lines.append("- None")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rules = load_jsonish(Path(args.rules))
    jlc_connections = parse_jlc_tel(Path(args.jlc_netlist), rules)
    kicad_xml = Path(args.json_report).with_suffix(".kicad.xml")
    export_kicad_xml_netlist(Path(args.kicad_schematic), kicad_xml)
    kicad_connections, metadata = parse_kicad_xml_netlist(kicad_xml)
    report = compare_connections(jlc_connections, kicad_connections, rules, metadata)
    report["inputs"] = {
        "jlc_netlist": args.jlc_netlist,
        "kicad_schematic": args.kicad_schematic,
        "ref_mapping": args.ref_mapping,
        "model": args.model,
        "rules": args.rules,
    }
    report["jlc_connections"] = [connection.__dict__ for connection in jlc_connections]
    report["kicad_connections"] = [connection.__dict__ for connection in kicad_connections]
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jlc-netlist", required=True)
    parser.add_argument("--kicad-schematic", required=True)
    parser.add_argument("--ref-mapping", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--json-report", required=True)
    parser.add_argument("--md-report", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Validate these read-only inputs exist even though mappings are supplied by
    # the equivalence rules; this catches stale command lines and handoff drift.
    for input_path in (args.jlc_netlist, args.kicad_schematic, args.ref_mapping, args.model, args.rules):
        if not Path(input_path).exists():
            raise SystemExit(f"Missing input: {input_path}")
    report = build_report(args)
    json_path = Path(args.json_report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.md_report))
    print(f"JLC/KiCad equivalence: {report['status']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {args.md_report}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
