#!/usr/bin/env python3
"""Generate draw.io title block cells from the GOST 2.104 Form 1 template."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def style(stroke: float, font_size: float = 2.5) -> str:
    return (
        "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#000000;"
        f"strokeWidth={stroke};fontFamily=Arial;fontSize={font_size};"
        "align=center;verticalAlign=middle;spacing=0;"
    )


def text_style(font_size: float) -> str:
    return (
        "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;"
        f"whiteSpace=wrap;rounded=0;fontFamily=Arial;fontSize={font_size};rotation=0;spacing=0;"
    )


def generate(template: dict, x_offset: float | None = None, y_offset: float | None = None) -> str:
    title = template["title_block"]
    line_widths = template["line_widths"]
    ox = title["x"] if x_offset is None else x_offset
    oy = title["y"] if y_offset is None else y_offset
    cells: list[str] = []
    cells.append(
        f'<mxCell id="title_block_outer" value="" style="{style(line_widths["major"], 1)}" parent="1" '
        f'vertex="1" data-kind="title_block" data-role="title-block-outer" '
        f'data-template_id="gost_2_104_form1" data-unit="mm">'
        f'<mxGeometry x="{ox}" y="{oy}" width="{title["width"]}" height="{title["height"]}" as="geometry"/></mxCell>'
    )
    for cell in template["cells"]:
        stroke = line_widths["major"] if cell["line_type"] == "major" else line_widths["minor"]
        cid = cell["id"]
        cells.append(
            f'<mxCell id="tb_cell_{esc(cid)}" value="" style="{style(stroke, 1)}" parent="1" '
            f'vertex="1" data-kind="title_block_cell" data-role="title-block-cell" '
            f'data-template_id="{esc(cid)}" data-field_name="{esc(cell.get("field_name", ""))}" data-unit="mm">'
            f'<mxGeometry x="{ox + cell["x"]}" y="{oy + cell["y"]}" width="{cell["width"]}" height="{cell["height"]}" as="geometry"/></mxCell>'
        )
        expected = cell.get("expected_text") or ""
        if expected:
            font = template["text"]["small_font_height_mm"] if cell["height"] <= 5 else template["text"]["value_font_height_mm"]
            cells.append(
                f'<mxCell id="tb_text_{esc(cid)}" value="{esc(expected)}" style="{text_style(font)}" parent="1" '
                f'vertex="1" data-kind="title_block" data-role="title-block-text" '
                f'data-template_id="{esc(cid)}" data-field_name="{esc(cell.get("field_name", ""))}" '
                f'data-font_height_mm="{font}" data-unit="mm">'
                f'<mxGeometry x="{ox + cell["x"] + 0.8}" y="{oy + cell["y"] + 0.3}" '
                f'width="{max(cell["width"] - 1.6, 1)}" height="{max(cell["height"] - 0.6, 1)}" as="geometry"/></mxCell>'
            )
    return "\n".join(cells)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=Path("templates/gost_2_104_form1_title_block.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    template = json.loads(args.template.read_text(encoding="utf-8"))
    args.output.write_text(generate(template), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
