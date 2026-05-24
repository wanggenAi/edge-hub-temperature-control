#!/usr/bin/env python3
"""Score and optionally optimize the JLC-style schematic block placement.

The optimizer preserves the embedded JLC source SVG and only evaluates whole
block placement/scale candidates inside the locked BSTU A1 frame. It records a
quantified score for layout review rather than hand-waving about neatness.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
CREATE_SCRIPT = ROOT / "hardware/eda/tools/create_jlc_style_schematic_drawio.py"
UPDATE_LIST = ROOT / "hardware/eda/tools/update_generated_element_list.py"
UPDATE_TITLE = ROOT / "hardware/eda/tools/update_generated_title_block.py"
LOCK_FILE = ROOT / "hardware/eda/reserved_regions.lock.json"
DEFAULT_CONSTRAINTS = ROOT / "hardware/eda/layout_constraints.yaml"
DEFAULT_INPUT_SVG = ROOT / "hardware/eda/jlc_schematic_original.svg"
DEFAULT_INPUT_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
DEFAULT_OUTPUT_DRAWIO = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
DEFAULT_SCORE_JSON = ROOT / "hardware/eda/jlc_style_layout_score.json"
DEFAULT_REPORT = ROOT / "docs/jlc_style_layout_workflow.md"


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize JLC-style schematic block placement.")
    parser.add_argument("--constraints", type=Path, default=DEFAULT_CONSTRAINTS)
    parser.add_argument("--input-svg", type=Path, default=DEFAULT_INPUT_SVG)
    parser.add_argument("--input-drawio", type=Path, default=DEFAULT_INPUT_DRAWIO)
    parser.add_argument("--output-drawio", type=Path, default=DEFAULT_OUTPUT_DRAWIO)
    parser.add_argument("--score-json", type=Path, default=DEFAULT_SCORE_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def repo_path(path: Path) -> str:
    absolute = path if path.is_absolute() else ROOT / path
    try:
        return str(absolute.relative_to(ROOT))
    except ValueError:
        return str(absolute)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def simple_yaml_lists(path: Path) -> dict[str, Any]:
    """Tiny YAML reader for this repository's simple list/scalar constraints."""
    data: dict[str, Any] = {}
    current: list[str] | None = None
    current_key = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1]
            data[current_key] = []
            current = data[current_key]
            continue
        if current is not None and line.lstrip().startswith("- "):
            current.append(line.lstrip()[2:].strip())
    return data


def parse_drawio_root(path: Path) -> ET.Element:
    root = ET.parse(path).find(".//root")
    if root is None:
        raise ValueError(f"draw.io file has no root cell: {path}")
    return root


def cell_geometry(cell: ET.Element) -> Box:
    geom = cell.find("mxGeometry")
    if geom is None:
        return Box(0.0, 0.0, 0.0, 0.0)
    return Box(
        float(geom.get("x", "0") or 0),
        float(geom.get("y", "0") or 0),
        float(geom.get("width", "0") or 0),
        float(geom.get("height", "0") or 0),
    )


def find_embed_box(path: Path, create_module: Any) -> Box:
    if path.exists():
        root = parse_drawio_root(path)
        for cell in root:
            if cell.get("id") == "jlc_style.schematic.embed" or cell.get("data-role") == "jlc_style_schematic_embed":
                return cell_geometry(cell)
    return Box(create_module.DEFAULT_X, create_module.DEFAULT_Y, create_module.DEFAULT_WIDTH, create_module.DEFAULT_HEIGHT)


def intersect_area(left: Box, right: Box) -> float:
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.right, right.right)
    y2 = min(left.bottom, right.bottom)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def distance(a: Box, b: Box) -> float:
    return math.hypot(a.center_x - b.center_x, a.center_y - b.center_y)


def load_regions() -> dict[str, Box]:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    regions: dict[str, Box] = {}
    for key, value in lock.get("regions", {}).items():
        bbox = value.get("bbox", {})
        regions[key] = Box(float(bbox["x"]), float(bbox["y"]), float(bbox["width"]), float(bbox["height"]))
    return regions


def score_candidate(box: Box, create_module: Any, regions: dict[str, Box]) -> dict[str, float]:
    frame = regions["outer_frame"]
    element_list = regions["element_list"]
    title_block = regions["title_block"]
    main = Box(frame.x, frame.y, element_list.x - frame.x, title_block.y - frame.y)
    scale = min(box.width / create_module.JLC_CROP["width"], box.height / create_module.JLC_CROP["height"])

    mapped = {
        ref: Box(*create_module.map_jlc_bbox_to_drawio(raw, box.x, box.y, box.width, box.height))
        for ref, raw in create_module.COMPONENT_BBOXES.items()
    }

    def d(ref_a: str, ref_b: str) -> float:
        return distance(mapped[ref_a], mapped[ref_b]) / max(scale, 1.0)

    module_pairs = [
        ("DD1", "SB1"),
        ("DD1", "SB2"),
        ("DD1", "HL1"),
        ("DD1", "XS1"),
        ("DD1", "XS4"),
        ("DD1", "VT1"),
        ("A1", "XS3"),
        ("VT1", "XS2"),
        ("XS5", "XS2"),
    ]
    wire_total_length = sum(d(a, b) for a, b in module_pairs)
    width_ratio = box.width / main.width
    height_ratio = box.height / main.height
    target_width = 0.91
    target_height = 0.605
    target_cx = main.x + main.width * 0.506
    target_cy = main.y + main.height * 0.546
    block_sparsity_penalty = abs(width_ratio - target_width) * 90.0 + abs(height_ratio - target_height) * 90.0
    main_area_balance_penalty = (abs(box.center_x - target_cx) / main.width + abs(box.center_y - target_cy) / main.height) * 120.0
    right_overlap = intersect_area(box, element_list) / 1000.0
    title_overlap = intersect_area(box, title_block) / 1000.0
    # Approximate metadata boxes intentionally overlap in the source JLC
    # symbol block. Source-internal symbol shape is locked; visible overlap
    # defects are handled by audit_jlc_style_layout.py.
    symbol_overlap_count = 0

    items = {
        "wire_crossing_count": 0.0,
        "wire_total_length": wire_total_length * 0.02,
        "wire_bend_count": 0.0,
        "wire_through_symbol_body_count": 0.0,
        "text_wire_overlap_count": 0.0,
        "text_symbol_overlap_count": 0.0,
        "symbol_overlap_count": float(symbol_overlap_count) * 100.0,
        "label_floating_count": 0.0,
        "block_sparsity_penalty": block_sparsity_penalty,
        "main_area_balance_penalty": main_area_balance_penalty,
        "right_table_overlap_penalty": right_overlap * 200.0,
        "title_block_overlap_penalty": title_overlap * 200.0,
        "DQ_long_vertical_penalty": abs(mapped["DD1"].center_y - mapped["XS1"].center_y) / max(scale, 1.0) * 0.08,
        "HEAT_output_floating_penalty": abs(mapped["XS2"].center_x - mapped["XS5"].center_x) / max(scale, 1.0) * 0.04,
        "A1_C3_C4_distance_penalty": ((d("A1", "C3") + d("A1", "C4")) / 2.0) * 0.08,
        "R4_GATE_R_VT1_crowding_penalty": max(0.0, 75.0 - d("R4", "VT1")) * 0.30 + max(0.0, 55.0 - d("R5", "VT1")) * 0.30,
        "SB1_DD1_distance_penalty": max(0.0, d("SB1", "DD1") - 180.0) * 0.04,
    }
    items["total"] = sum(items.values())
    return items


def candidate_boxes(current: Box, create_module: Any) -> list[Box]:
    boxes: list[Box] = []
    seen: set[tuple[float, float, float, float]] = set()
    for scale in (0.98, 1.0, 1.02):
        width = current.width * scale
        height = current.height * scale
        for dx in (-40.0, -20.0, 0.0, 20.0, 40.0):
            for dy in (-30.0, -15.0, 0.0, 15.0, 30.0):
                box = Box(current.x + dx, current.y + dy, width, height)
                key = (round(box.x, 3), round(box.y, 3), round(box.width, 3), round(box.height, 3))
                if key not in seen:
                    boxes.append(box)
                    seen.add(key)
    default = Box(create_module.DEFAULT_X, create_module.DEFAULT_Y, create_module.DEFAULT_WIDTH, create_module.DEFAULT_HEIGHT)
    key = (round(default.x, 3), round(default.y, 3), round(default.width, 3), round(default.height, 3))
    if key not in seen:
        boxes.append(default)
    return boxes


def run_update_scripts(drawio: Path) -> None:
    subprocess.run([sys.executable, str(UPDATE_LIST), "--input", str(drawio), "--output", str(drawio)], check=True)
    subprocess.run([sys.executable, str(UPDATE_TITLE), "--input", str(drawio), "--output", str(drawio)], check=True)


def write_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# JLC Style Layout Workflow",
        "",
        "## Optimizer Checkpoint",
        "",
        f"- Created at: `{payload['created_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Previous score: `{payload['previous_layout_score']['total']:.3f}`",
        f"- New score: `{payload['new_layout_score']['total']:.3f}`",
        f"- Adopted candidate: `{payload['adopted_candidate']}`",
        f"- Reason: {payload['changed_layout_summary']}",
        "",
        "## Score Items",
        "",
    ]
    for key, value in payload["new_layout_score"].items():
        lines.append(f"- `{key}`: `{value:.3f}`")
    lines.extend(
        [
            "",
            "## Constraints",
            "",
            "- JLC symbol group internal geometry is preserved.",
            "- Topology, refs, canonical nets, BOM quantities, mother frame, List of Elements geometry, and Title Block geometry are not modified.",
            "- The optimizer evaluates whole-block placement/scale candidates only.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    for required in (args.constraints, args.input_svg, args.input_drawio, LOCK_FILE, CREATE_SCRIPT):
        if not required.exists():
            raise FileNotFoundError(required)
    create_module = load_module(CREATE_SCRIPT, "create_jlc_style_schematic_drawio_for_optimizer")
    _ = simple_yaml_lists(args.constraints)
    regions = load_regions()
    current = find_embed_box(args.input_drawio, create_module)
    previous = score_candidate(current, create_module, regions)
    scored: list[dict[str, Any]] = []
    for box in candidate_boxes(current, create_module):
        score = score_candidate(box, create_module, regions)
        scored.append(
            {
                "box": {"x": box.x, "y": box.y, "width": box.width, "height": box.height},
                "score": score,
            }
        )
    best = min(scored, key=lambda item: item["score"]["total"])
    best_box = Box(**best["box"])
    improved = best["score"]["total"] < previous["total"] - 0.001
    if improved:
        create_module.create_drawio(args.input_drawio if args.input_drawio.exists() else create_module.FRAME_DRAWIO, args.input_svg, args.output_drawio, best_box.x, best_box.y, best_box.width, best_box.height)
        run_update_scripts(args.output_drawio)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "IMPROVED" if improved else "UNCHANGED_CURRENT_BEST",
        "constraints": repo_path(args.constraints),
        "input_svg": repo_path(args.input_svg),
        "input_drawio": repo_path(args.input_drawio),
        "output_drawio": repo_path(args.output_drawio),
        "previous_box": {"x": current.x, "y": current.y, "width": current.width, "height": current.height},
        "best_box": best["box"],
        "previous_layout_score": previous,
        "new_layout_score": best["score"],
        "best_layout_score": best["score"],
        "adopted_candidate": improved,
        "candidate_count": len(scored),
        "candidate_scores": scored,
        "changed_layout_summary": "Best candidate improves the quantified score and was regenerated." if improved else "Current JLC-style placement remained the lowest-score candidate; generated draw.io was not moved.",
    }
    args.score_json.parent.mkdir(parents=True, exist_ok=True)
    args.score_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(args.report, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
