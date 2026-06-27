#!/usr/bin/env python3
"""Assemble first-version A1 landscape draw.io poster files.

The generated files are intentionally poster layouts, not enlarged flowcharts.
Front: colorful showcase poster, no formal title block.
Back: blank A1 side, preserving the flowchart outer border and title block/table.
"""

from __future__ import annotations

import base64
import copy
from html import escape
from pathlib import Path
from urllib.parse import quote
from xml.dom import minidom
from xml.etree import ElementTree as ET


POSTER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = POSTER_ROOT.parent
ASSET_DIR = POSTER_ROOT / "assets"
FLOWCHART_DRAWIO = REPO_ROOT / "a1-engineering-flowchart" / "optimized_architecture_flowchart.drawio"
PAGE_W = 3300
PAGE_H = 2339
FONT = "Helvetica"
FRAME_X = 78.478
FRAME_Y = 19.689
FRAME_W = 3201.902
FRAME_H = 2299.623
FRONT_INSET_X = 90
FRONT_INSET_TOP = 55
FRONT_INSET_BOTTOM = 90
FRONT_X = FRAME_X + FRONT_INSET_X
FRONT_Y = FRAME_Y + FRONT_INSET_TOP
FRONT_R = FRAME_X + FRAME_W - FRONT_INSET_X
FRONT_B = FRAME_Y + FRAME_H - FRONT_INSET_BOTTOM
FRONT_W = FRONT_R - FRONT_X
FRONT_BOTTOM_Y = 1900
FRONT_MIRRORED_TABLE_CLEAR_R = 900


class DiagramBuilder:
    def __init__(self, name: str, *, background: str) -> None:
        self.mxfile = ET.Element(
            "mxfile",
            {
                "host": "Electron",
                "agent": "Codex poster workflow",
                "version": "28.0.6",
            },
        )
        self.diagram = ET.SubElement(self.mxfile, "diagram", {"id": f"{name}-diagram", "name": name})
        self.model = ET.SubElement(
            self.diagram,
            "mxGraphModel",
            {
                "dx": "4016",
                "dy": "2700",
                "grid": "0",
                "gridSize": "3.937",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": str(PAGE_W),
                "pageHeight": str(PAGE_H),
                "background": background,
                "math": "0",
                "shadow": "0",
            },
        )
        self.root = ET.SubElement(self.model, "root")
        ET.SubElement(self.root, "mxCell", {"id": "0"})
        ET.SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        self._counter = 1

    def next_id(self, prefix: str = "p") -> str:
        value = f"{prefix}_{self._counter}"
        self._counter += 1
        return value

    def cell(
        self,
        *,
        value: str = "",
        style: str,
        x: float,
        y: float,
        w: float,
        h: float,
        parent: str = "1",
        cell_id: str | None = None,
    ) -> str:
        cid = cell_id or self.next_id()
        mx = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": cid,
                "value": value,
                "style": style,
                "parent": parent,
                "vertex": "1",
            },
        )
        ET.SubElement(mx, "mxGeometry", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}", "height": f"{h:.3f}", "as": "geometry"})
        return cid

    def edge(
        self,
        *,
        source: tuple[float, float],
        target: tuple[float, float],
        color: str = "#5ef2ff",
        width: float = 4,
        opacity: int = 45,
        dashed: bool = False,
        curved: bool = True,
        arrow: bool = True,
    ) -> str:
        style = (
            f"endArrow={'block' if arrow else 'none'};html=1;rounded=1;"
            f"strokeColor={color};strokeWidth={width};opacity={opacity};"
            f"curved={'1' if curved else '0'};"
        )
        if dashed:
            style += "dashed=1;dashPattern=8 8;"
        cid = self.next_id("edge")
        mx = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": cid,
                "value": "",
                "style": style,
                "parent": "1",
                "edge": "1",
            },
        )
        geo = ET.SubElement(mx, "mxGeometry", {"width": "50", "height": "50", "relative": "1", "as": "geometry"})
        ET.SubElement(geo, "mxPoint", {"x": f"{source[0]:.3f}", "y": f"{source[1]:.3f}", "as": "sourcePoint"})
        ET.SubElement(geo, "mxPoint", {"x": f"{target[0]:.3f}", "y": f"{target[1]:.3f}", "as": "targetPoint"})
        return cid

    def text(
        self,
        value: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        size: int = 34,
        color: str = "#ffffff",
        weight: str = "0",
        align: str = "left",
        valign: str = "middle",
        opacity: int | None = None,
        parent: str = "1",
    ) -> str:
        style = (
            "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;rounded=0;"
            f"fontFamily={FONT};fontSize={size};fontColor={color};fontStyle={weight};align={align};verticalAlign={valign};"
        )
        if opacity is not None:
            style += f"opacity={opacity};"
        return self.cell(value=value, style=style, x=x, y=y, w=w, h=h, parent=parent)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str,
        stroke: str = "none",
        radius: int = 1,
        width: float = 2,
        opacity: int | None = None,
        extra: str = "",
    ) -> str:
        style = (
            f"rounded={radius};whiteSpace=wrap;html=1;arcSize=8;fillColor={fill};"
            f"strokeColor={stroke};strokeWidth={width};"
        )
        if opacity is not None:
            style += f"opacity={opacity};"
        style += extra
        return self.cell(value="", style=style, x=x, y=y, w=w, h=h)

    def image(self, path: Path, x: float, y: float, w: float, h: float, *, label: str = "", rounded: bool = False) -> str:
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
        }.get(path.suffix.lower())
        if not mime:
            raise ValueError(f"Unsupported image type: {path}")
        if path.suffix.lower() == ".svg":
            image_uri = f"data:image/svg+xml,{quote(path.read_text(encoding='utf-8'), safe='')}"
        else:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            image_uri = f"data:{mime}%3Bbase64,{quote(data, safe='')}"
        style = (
            "shape=image;html=1;imageAspect=1;aspect=fixed;verticalAlign=middle;verticalLabelPosition=bottom;"
            f"image={image_uri};"
        )
        if rounded:
            style += "rounded=1;arcSize=8;"
        return self.cell(value=label, style=style, x=x, y=y, w=w, h=h)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = ET.tostring(self.mxfile, encoding="utf-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
        path.write_bytes(pretty)


def rich(lines: list[str]) -> str:
    return "<br>".join(escape(line) for line in lines)


def pill(builder: DiagramBuilder, x: float, y: float, w: float, text: str, color: str) -> None:
    builder.rect(x, y, w, 58, fill="#10283a", stroke=color, radius=1, width=2, opacity=96)
    builder.text(text, x, y + 5, w, 46, size=26, color="#f6fbff", weight="1", align="center")


def module_card(builder: DiagramBuilder, x: float, y: float, w: float, h: float, title: str, lines: list[str], color: str, *, fill: str = "#ffffff") -> None:
    builder.rect(x, y, w, h, fill=fill, stroke=color, radius=1, width=3)
    if h <= 160:
        builder.rect(x + 24, y + 24, 42, 42, fill=color, stroke=color, radius=1, width=2, opacity=16)
        builder.rect(x + 39, y + 39, 12, 12, fill=color, stroke=color, radius=1, width=1)
        builder.text(title, x + 86, y + 20, w - 110, 38, size=29, color="#132033", weight="1")
        builder.text(rich(lines), x + 36, y + 78, w - 72, h - 88, size=16, color="#435268", valign="top")
    else:
        builder.rect(x + 24, y + 24, 54, 54, fill=color, stroke=color, radius=1, width=2, opacity=18)
        builder.rect(x + 42, y + 42, 18, 18, fill=color, stroke=color, radius=1, width=1)
        builder.text(title, x + 96, y + 20, w - 120, 42, size=31, color="#132033", weight="1")
        builder.text(rich(lines), x + 34, y + 86, w - 68, h - 96, size=23, color="#435268", valign="top")


def contribution(builder: DiagramBuilder, x: float, y: float, w: float, number: str, title: str, subtitle: str, color: str) -> None:
    builder.rect(x, y, w, 138, fill="#071723", stroke=color, radius=1, width=3)
    builder.rect(x + 26, y + 36, 62, 62, fill=color, stroke=color, radius=1, width=2, opacity=16)
    builder.text(number, x + 26, y + 42, 62, 44, size=24, color="#ffffff", weight="1", align="center")
    builder.text(title, x + 112, y + 28, w - 132, 34, size=27, color="#f6fbff", weight="1")
    builder.text(subtitle, x + 112, y + 70, w - 132, 30, size=21, color="#bdd2df", weight="1")


def light_pill(builder: DiagramBuilder, x: float, y: float, w: float, text: str, color: str) -> None:
    builder.rect(x, y, w, 42, fill="#ffffff", stroke=color, radius=1, width=2)
    builder.text(text, x, y + 4, w, 31, size=20, color="#122333", weight="1", align="center")


def contribution_light(builder: DiagramBuilder, x: float, y: float, w: float, number: str, title: str, subtitle: str, color: str) -> None:
    builder.rect(x, y, w, 126, fill="#ffffff", stroke=color, radius=1, width=2.5)
    builder.rect(x + 22, y + 30, 54, 54, fill=color, stroke=color, radius=1, width=2, opacity=16)
    builder.text(number, x + 22, y + 36, 54, 34, size=22, color="#122333", weight="1", align="center")
    builder.text(title, x + 96, y + 26, w - 116, 32, size=24, color="#122333", weight="1")
    builder.text(subtitle, x + 96, y + 66, w - 116, 28, size=19, color="#425a6d", weight="1")


def draw_inner_frame(builder: DiagramBuilder) -> None:
    builder.cell(
        value="",
        style=(
            "rounded=0;whiteSpace=wrap;html=1;strokeWidth=3.937;strokeColor=#000000;"
            "fillColor=none;pointerEvents=0;movable=0;resizable=0;rotatable=0;"
            "deletable=0;editable=0;connectable=0"
        ),
        x=FRAME_X,
        y=FRAME_Y,
        w=FRAME_W,
        h=FRAME_H,
        cell_id="poster_inner_frame",
    )


def draw_front_title(builder: DiagramBuilder) -> None:
    builder.text(
        "EdgeHub-Based Closed-Loop Temperature Control System",
        FRONT_X + 120,
        FRONT_Y,
        FRONT_W - 240,
        86,
        size=66,
        color="#122333",
        weight="1",
        align="center",
    )
    builder.rect(FRONT_X + 360, FRONT_Y + 94, FRONT_W - 720, 4, fill="#122333", stroke="none", radius=0, width=0)
    tag_rows = [
        [
            ("ESP32", 108, "#5aa9e6"),
            ("MQTT", 105, "#2ad4a0"),
            ("Spring Boot + Reactor", 276, "#5aa9e6"),
            ("TDengine", 150, "#f0b84a"),
        ],
        [
            ("FastAPI", 130, "#ef8354"),
            ("React", 112, "#9f7aea"),
            ("PostgreSQL", 180, "#2ad4a0"),
            ("AI PID Recommendation", 282, "#5aa9e6"),
        ],
    ]
    for row_index, tag_specs in enumerate(tag_rows):
        total_tag_width = sum(width for _, width, _ in tag_specs) + (16 * (len(tag_specs) - 1))
        tag_x = FRONT_X + (FRONT_W - total_tag_width) / 2
        tag_y = FRONT_Y + 120 + (row_index * 50)
        for label, width, color in tag_specs:
            light_pill(builder, tag_x, tag_y, width, label, color)
            tag_x += width + 16


def flowchart_title_block_cells() -> list[ET.Element]:
    source_root = ET.parse(FLOWCHART_DRAWIO).getroot()
    model = source_root.find("./diagram/mxGraphModel")
    if model is None:
        raise RuntimeError(f"Cannot locate mxGraphModel in {FLOWCHART_DRAWIO}")
    root = model.find("root")
    if root is None:
        raise RuntimeError(f"Cannot locate root in {FLOWCHART_DRAWIO}")
    out: list[ET.Element] = []
    for cell in root.findall("mxCell"):
        cell_id = cell.attrib.get("id", "")
        if cell_id.startswith("content_page_titleblock_") or cell_id == "repo_template_outer_border":
            out.append(copy.deepcopy(cell))
    return out


def build_front() -> None:
    b = DiagramBuilder("Front A1 Poster", background="#ffffff")
    draw_front_title(b)

    # Large hero card: use the enclosure as the main visual impact.
    b.rect(170, 315, 1580, 1540, fill="#ffffff", stroke="#9bb4c2", radius=1, width=2)
    b.text("Edge Device / Thermal Enclosure", 210, 347, 920, 42, size=34, color="#122333", weight="1")
    b.text("3D thermal insulation enclosure and edge temperature-control prototype", 212, 393, 1120, 30, size=21, color="#425a6d")
    b.image(ASSET_DIR / "enclosure-hero.png", 230, 435, 1460, 1345)
    callouts = [
        (220, 580, "Insulated Chamber", "#5aa9e6", 740, 730),
        (1310, 615, "Safety Barrier", "#2ad4a0", 1235, 795),
        (212, 1225, "DS18B20 Probe", "#ef8354", 710, 1321),
        (1255, 1335, "Heater Zone", "#f0b84a", 1122, 1153),
        (1135, 1763, "Electronics Bay", "#9f7aea", 1050, 1610),
    ]
    for x, y, label, color, tx, ty in callouts:
        b.rect(x, y, 330, 64, fill="#ffffff", stroke=color, radius=1, width=3)
        b.text(label, x + 18, y + 14, 294, 32, size=23, color="#122333", weight="1")
        source = (x + 165, y) if label == "Heater Zone" else (x + (330 if x < tx else 0), y + 36)
        target = (tx, ty)
        b.edge(source=source, target=target, color="#ffffff", width=8, opacity=95, dashed=False, curved=False, arrow=False)
        b.edge(source=source, target=target, color=color, width=4.5, opacity=100, dashed=False, curved=False, arrow=False)

    # Data-Hub panel.
    b.rect(1810, 315, 1360, 375, fill="#ffffff", stroke="#9bb4c2", radius=1, width=2)
    b.text("Data-Hub Runtime Cluster", 1840, 347, 720, 38, size=31, color="#122333", weight="1")
    b.text("MQTT ingress, Java Reactor ingestion, buffering, persistence, and runtime observability", 1842, 389, 1080, 28, size=19, color="#425a6d")
    b.image(ASSET_DIR / "data-hub.svg", 1840, 433, 720, 240)
    b.text("Runtime Contract", 2600, 449, 430, 34, size=24, color="#122333", weight="1")
    for i, (topic, color) in enumerate(
        [
            ("telemetry -> broker -> Reactor", "#5ef2ff"),
            ("params/set -> edge controller", "#6df0c2"),
            ("params/ack -> status + audit", "#ffd166"),
        ]
    ):
        b.rect(2600, 500 + i * 62, 520, 42, fill="#f9fcff", stroke=color, radius=1, width=2)
        b.text(topic, 2617, 508 + i * 62, 485, 24, size=18, color="#23384a")

    # HMI screenshots.
    b.rect(1810, 730, 1360, 720, fill="#ffffff", stroke="#9bb4c2", radius=1, width=2)
    b.text("HMI Layer", 1840, 762, 480, 38, size=31, color="#122333", weight="1")
    b.text("Real FastAPI + React screenshots with seeded telemetry data", 1842, 804, 920, 28, size=19, color="#425a6d")
    b.rect(1840, 850, 610, 36, fill="#eaf5fb", stroke="#5aa9e6", radius=1, width=2)
    b.text("Device Detail + Parameter Apply", 1840, 855, 610, 24, size=21, color="#122333", weight="1", align="center")
    b.rect(1840, 895, 610, 486, fill="#030b12", stroke="#5aa9e6", radius=1, width=4)
    b.image(ASSET_DIR / "hmi-device-detail-crop.png", 1852, 907, 586, 462)
    b.rect(2525, 850, 610, 36, fill="#eafbf5", stroke="#2ad4a0", radius=1, width=2)
    b.text("AI Validation", 2525, 855, 610, 24, size=21, color="#122333", weight="1", align="center")
    b.rect(2525, 895, 610, 218, fill="#030b12", stroke="#2ad4a0", radius=1, width=4)
    b.image(ASSET_DIR / "hmi-ai-validation-crop.png", 2543, 906, 574, 196)
    b.rect(2525, 1150, 610, 36, fill="#fff7e6", stroke="#f0b84a", radius=1, width=2)
    b.text("Ops Console", 2525, 1155, 610, 24, size=21, color="#122333", weight="1", align="center")
    b.rect(2525, 1195, 610, 186, fill="#030b12", stroke="#f0b84a", radius=1, width=4)
    b.image(ASSET_DIR / "hmi-ops-console-crop.png", 2545, 1199, 570, 178)

    # AI-assisted decision panel.
    b.rect(1810, 1495, 1360, 360, fill="#ffffff", stroke="#9bb4c2", radius=1, width=2)
    b.text("AI-Assisted Decision", 1840, 1523, 650, 38, size=31, color="#122333", weight="1")
    b.text("features, recommendation, preview, operator apply, and ACK validation", 1842, 1564, 960, 28, size=19, color="#425a6d")
    b.image(ASSET_DIR / "ai-decision.svg", 1840, 1612, 470, 244)
    b.rect(2390, 1614, 720, 116, fill="#f9fcff", stroke="#9bb4c2", radius=1, width=2)
    b.text("Before / After Response", 2420, 1630, 520, 28, size=22, color="#122333", weight="1")
    for gx in [2440, 2585, 2730, 2875]:
        b.edge(source=(gx, 1679), target=(gx, 1717), color="#c6d8e2", width=1.2, opacity=55, curved=False, arrow=False)
    b.edge(source=(2435, 1714), target=(3075, 1714), color="#9bb4c2", width=2, opacity=70, curved=False, arrow=False)
    b.edge(source=(2445, 1710), target=(2600, 1657), color="#ef8354", width=6, opacity=85, curved=False, arrow=False)
    b.edge(source=(2600, 1657), target=(2785, 1710), color="#ef8354", width=6, opacity=85, curved=False, arrow=False)
    b.edge(source=(2785, 1710), target=(3050, 1681), color="#ef8354", width=6, opacity=85, curved=False, arrow=False)
    b.edge(source=(2445, 1708), target=(2640, 1693), color="#2ad4a0", width=6, opacity=85, curved=False, arrow=False)
    b.edge(source=(2640, 1693), target=(2860, 1702), color="#2ad4a0", width=6, opacity=85, curved=False, arrow=False)
    b.edge(source=(2860, 1702), target=(3052, 1697), color="#2ad4a0", width=6, opacity=85, curved=False, arrow=False)
    b.text("before", 2990, 1670, 90, 24, size=16, color="#ef8354", weight="1")
    b.text("after", 2990, 1701, 90, 24, size=16, color="#2ad4a0", weight="1")
    ai_cards = [
        ("Telemetry History", "#5ef2ff"),
        ("Feature Extraction", "#6df0c2"),
        ("Problem Classification", "#c8a4ff"),
        ("PID Recommendation", "#ffd166"),
        ("Preview Simulation", "#ff9c7a"),
        ("Operator Apply", "#7da7ff"),
        ("ACK Validation", "#6df0c2"),
    ]
    for i, (label, color) in enumerate(ai_cards):
        col = i % 3
        row = i // 3
        x = 2390 + col * 240
        y = 1745 + row * 35
        b.rect(x, y, 220, 26, fill="#ffffff", stroke=color, radius=1, width=1.8)
        b.text(label, x + 10, y + 3, 200, 18, size=12, color="#122333", weight="1")

    # Bottom key contributions.
    b.rect(920, FRONT_BOTTOM_Y, 2250, 315, fill="#ffffff", stroke="#9bb4c2", radius=1, width=2)
    b.text("Key Contributions", 960, 1928, 780, 42, size=34, color="#122333", weight="1")
    items = [
        ("01", "Edge closed-loop", "temperature control", "#5aa9e6"),
        ("02", "MQTT runtime", "telemetry + commands", "#2ad4a0"),
        ("03", "Data-Hub", "time-series persistence", "#5aa9e6"),
        ("04", "HMI workflow", "operate + apply params", "#f0b84a"),
        ("05", "AI PID assist", "recommend + validate", "#9f7aea"),
    ]
    x = 960
    for number, title, subtitle, color in items:
        contribution_light(b, x, 2022, 390, number, title, subtitle, color)
        x += 430

    b.write(POSTER_ROOT / "front-a1-poster.drawio")


def build_back() -> None:
    b = DiagramBuilder("Back A1 Technical Sheet", background="#ffffff")
    b.rect(0, 0, PAGE_W, PAGE_H, fill="#ffffff", stroke="none", radius=0)
    for cell in flowchart_title_block_cells():
        b.root.append(cell)
    b.write(POSTER_ROOT / "back-a1-technical-sheet.drawio")


def main() -> None:
    build_front()
    build_back()
    print(f"Wrote {POSTER_ROOT / 'front-a1-poster.drawio'}")
    print(f"Wrote {POSTER_ROOT / 'back-a1-technical-sheet.drawio'}")


if __name__ == "__main__":
    main()
