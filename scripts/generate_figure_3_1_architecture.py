#!/usr/bin/env python3
"""Generate Figure 3.1 as a fixed-coordinate system architecture diagram."""

from __future__ import annotations

from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "figures"
SVG_PATH = OUT_DIR / "figure_3_1_general_architecture.svg"
PNG_PATH = OUT_DIR / "figure_3_1_general_architecture.png"

WIDTH = 1900
HEIGHT = 900

FONT = "Times New Roman, DejaVu Serif, serif"
TEXT = "#222222"
MUTED = "#4B5563"
MAIN_FILL = "#F7F9FC"
STORAGE_FILL = "#FAFAFA"
WHITE = "#FFFFFF"
ARROW = "#333333"


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wrap(value: str, width: int) -> list[str]:
    return textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False)


class Svg:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, value: str) -> None:
        self.parts.append(value)

    def text(
        self,
        x: float,
        y: float,
        value: str | list[str],
        *,
        size: int,
        fill: str = TEXT,
        weight: str = "400",
        anchor: str = "middle",
    ) -> None:
        lines = [value] if isinstance(value, str) else value
        self.add(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
            f'font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}">'
        )
        for index, line in enumerate(lines):
            dy = "0" if index == 0 else "1.18em"
            self.add(f'<tspan x="{x}" dy="{dy}">{esc(line)}</tspan>')
        self.add("</text>")

    def render(self) -> str:
        return "\n".join(self.parts)


def draw_label(svg: Svg, x: int, y: int, label: str, *, anchor: str = "middle", width: int = 28) -> None:
    lines = wrap(label, width)
    longest = max((len(line) for line in lines), default=0)
    box_w = max(82, min(260, longest * 7 + 20))
    box_h = 22 + (len(lines) - 1) * 18
    if anchor == "middle":
        rect_x = x - box_w / 2
    elif anchor == "end":
        rect_x = x - box_w
    else:
        rect_x = x
    svg.add(
        f'<rect x="{rect_x}" y="{y - 17}" width="{box_w}" height="{box_h}" '
        f'rx="5" ry="5" fill="#FFFFFF" fill-opacity="0.92"/>'
    )
    svg.text(x, y, lines, size=16, fill=MUTED, anchor=anchor)


def draw_box(
    svg: Svg,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    subtitle: str,
    fill: str,
    stroke: str,
    *,
    dashed: bool = False,
) -> None:
    dash = ' stroke-dasharray="12 8"' if dashed else ""
    svg.add(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" ry="18" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
    )
    title_lines = wrap(title, 26 if w < 500 else 38)
    title_y = y + 42 if len(title_lines) == 1 else y + 34
    subtitle_y = y + 82 if len(title_lines) == 1 else y + 42 + 28 * len(title_lines)
    svg.text(x + w / 2, title_y, title_lines, size=25, fill=TEXT, weight="700")
    svg.text(x + w / 2, subtitle_y, wrap(subtitle, 44 if w < 500 else 58), size=18, fill=MUTED)


def draw_arrow(
    svg: Svg,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    label: str | None = None,
    label_x: int | None = None,
    label_y: int | None = None,
    label_anchor: str = "middle",
    label_width: int = 28,
    dashed: bool = False,
) -> None:
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    stroke = "#B07A20" if dashed else ARROW
    marker = "arrowheadAux" if dashed else "arrowhead"
    svg.add(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
        f'stroke-width="2" fill="none"{dash} marker-end="url(#{marker})"/>'
    )
    if label:
        draw_label(
            svg,
            label_x if label_x is not None else int((x1 + x2) / 2),
            label_y if label_y is not None else int((y1 + y2) / 2) - 10,
            label,
            anchor=label_anchor,
            width=label_width,
        )


def draw_polyline_arrow(
    svg: Svg,
    points: list[tuple[int, int]],
    *,
    label: str | None = None,
    label_x: int | None = None,
    label_y: int | None = None,
    label_anchor: str = "middle",
    label_width: int = 28,
    dashed: bool = False,
) -> None:
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    stroke = "#B07A20" if dashed else ARROW
    marker = "arrowheadAux" if dashed else "arrowhead"
    point_data = " ".join(f"{x},{y}" for x, y in points)
    svg.add(
        f'<polyline points="{point_data}" stroke="{stroke}" stroke-width="2" '
        f'fill="none"{dash} marker-end="url(#{marker})"/>'
    )
    if label:
        lx, ly = points[len(points) // 2]
        draw_label(
            svg,
            label_x if label_x is not None else lx,
            label_y if label_y is not None else ly - 10,
            label,
            anchor=label_anchor,
            width=label_width,
        )


def build_svg() -> str:
    svg = Svg()
    svg.add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">')
    svg.add('<rect width="100%" height="100%" fill="#FFFFFF"/>')
    svg.add(
        """
<defs>
  <marker id="arrowhead" markerWidth="7" markerHeight="7" refX="6.2" refY="3.5" orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L7,3.5 L0,7 z" fill="#333333"/>
  </marker>
  <marker id="arrowheadAux" markerWidth="7" markerHeight="7" refX="6.2" refY="3.5" orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L7,3.5 L0,7 z" fill="#B07A20"/>
  </marker>
</defs>
"""
    )

    svg.text(950, 45, "Layered closed-loop temperature control and monitoring system", size=34, weight="700")
    svg.text(950, 76, "Three main layers and one auxiliary mechanism", size=18, fill=MUTED)

    hmi = (620, 100, 660, 110)
    data = (620, 290, 660, 120)
    edge = (620, 495, 660, 120)
    obj = (620, 700, 660, 105)
    storage = (1420, 290, 380, 120)
    aux = (110, 445, 410, 135)

    draw_box(svg, *hmi, "HMI Layer", "Monitoring · History · Configuration", MAIN_FILL, "#5A4B8B")
    draw_box(svg, *data, "Data Hub Layer", "MQTT ingestion · Processing · Status tracking", MAIN_FILL, "#3E6B35")
    draw_box(svg, *edge, "Edge Control Layer", "Acquisition · Local control · Actuator output · Acknowledgement", MAIN_FILL, "#2F5D8C")
    draw_box(svg, *obj, "Controlled Object / Sensor / Actuator", "Temperature process · Physical I/O", WHITE, "#222222")
    draw_box(svg, *storage, "Persistent Storage", "Telemetry · Commands · Acknowledgements · Status", STORAGE_FILL, "#777777")
    draw_box(
        svg,
        *aux,
        "Auxiliary Decision-Support Mechanism",
        "Behavior analysis · Reviewable recommendations",
        WHITE,
        "#B07A20",
        dashed=True,
    )

    # HMI Layer <-> Data Hub Layer.
    draw_arrow(svg, 830, 290, 830, 210, label="Current state / history", label_x=770, label_y=253, label_anchor="end")
    draw_arrow(svg, 1070, 210, 1070, 290, label="Configuration request", label_x=1130, label_y=253, label_anchor="start")

    # Data Hub Layer <-> Edge Control Layer.
    draw_arrow(svg, 830, 495, 830, 410, label="Telemetry / acknowledgements", label_x=770, label_y=453, label_anchor="end", label_width=40)
    draw_arrow(svg, 1070, 410, 1070, 495, label="Parameter commands", label_x=1130, label_y=458, label_anchor="start")

    # Edge Control Layer <-> controlled object.
    draw_arrow(svg, 830, 615, 830, 700, label="Actuator output", label_x=760, label_y=665, label_anchor="end")
    draw_arrow(svg, 1070, 700, 1070, 615, label="Temperature feedback", label_x=1130, label_y=665, label_anchor="start")

    # Data Hub Layer <-> Persistent Storage.
    draw_arrow(svg, 1280, 326, 1420, 326, label="Normalized records", label_x=1350, label_y=300, label_width=28)
    draw_arrow(svg, 1420, 374, 1280, 374, label="Historical data", label_x=1350, label_y=407, label_width=28)

    svg.add("</svg>")
    return svg.render()


def write_png(svg_text: str) -> bool:
    try:
        import cairosvg
    except ImportError:
        return False
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(PNG_PATH), output_width=1900)
    return True


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    svg_text = build_svg()
    SVG_PATH.write_text(svg_text, encoding="utf-8")
    print(SVG_PATH)
    if write_png(svg_text):
        print(PNG_PATH)
    else:
        print("PNG not generated: cairosvg is not installed")


if __name__ == "__main__":
    main()
