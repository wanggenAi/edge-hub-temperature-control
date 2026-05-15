#!/usr/bin/env python3
"""Generate Chapter 4 thesis figures from real project hardware artifacts."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FIGURES_DIR = ROOT / "docs" / "figures"
WOKWI_DIAGRAM = ROOT / "simulator" / "wokwi" / "diagram.json"
PCB_DXF = ROOT / "hardware" / "enclosure" / "references" / "pcb" / "DXF_PCB1_2026-04-05_AutoCAD2007.dxf"
SCHEMATIC_PDF = Path("/Users/seker./Downloads/SCH_Schematic1_2026-05-14.pdf")
PCB_SCREENSHOT = Path("/Users/seker./Downloads/PCB_PCB1_2026-05-14.png")
ENCLOSURE_PRESENTATION = ROOT / "hardware" / "enclosure" / "exports" / "v1" / "preview_presentation_transparent_iso.png"
ENCLOSURE_PARTS = ROOT / "hardware" / "enclosure" / "exports" / "v1" / "preview_all_parts_iso.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/Library/Fonts/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


TITLE_FONT = font(34, True)
SUBTITLE_FONT = font(24)
LABEL_FONT = font(22)
SMALL_FONT = font(18)


def draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill="#111111") -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    x, y = xy
    draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2), text, font=fnt, fill=fill)


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    *,
    fill: str,
    width: int = 5,
    label: str | None = None,
    label_xy: tuple[float, float] | None = None,
) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")
    if len(points) < 2:
        return
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    head = 18
    spread = math.radians(28)
    p1 = (x2 - head * math.cos(angle - spread), y2 - head * math.sin(angle - spread))
    p2 = (x2 - head * math.cos(angle + spread), y2 - head * math.sin(angle + spread))
    draw.polygon([(x2, y2), p1, p2], fill=fill)
    if label and label_xy:
        draw_label(draw, label_xy, label, fill="#222222")


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, *, fill: str = "#222222") -> None:
    box = draw.textbbox((0, 0), text, font=SMALL_FONT)
    x, y = xy
    pad_x, pad_y = 10, 5
    rect = [x - (box[2] - box[0]) / 2 - pad_x, y - (box[3] - box[1]) / 2 - pad_y, x + (box[2] - box[0]) / 2 + pad_x, y + (box[3] - box[1]) / 2 + pad_y]
    draw.rounded_rectangle(rect, radius=8, fill="#FFFFFF", outline="#D8D8D8", width=1)
    draw.text((x - (box[2] - box[0]) / 2, y - (box[3] - box[1]) / 2), text, font=SMALL_FONT, fill=fill)


def draw_resistor(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], label: str) -> None:
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, fill="#F4E3B0", outline="#8A6B22", width=4)
    draw_centered(draw, (x + w / 2, y + h / 2), label, SMALL_FONT)


def draw_wokwi_figure() -> None:
    data = json.loads(WOKWI_DIAGRAM.read_text(encoding="utf-8"))
    parts = {part["id"]: part for part in data["parts"]}

    out_w, out_h = 1800, 1100
    img = Image.new("RGB", (out_w, out_h), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((60, 60, out_w - 60, out_h - 60), outline="#E5E5E5", width=2)

    def pos(part_id: str, dx: float = 0, dy: float = 0) -> tuple[float, float]:
        part = parts[part_id]
        x = (part["left"] + 360) * 2.0 + 270 + dx
        y = (part["top"] + 150) * 2.0 + 215 + dy
        return x, y

    esp_x, esp_y = pos("esp", dy=-70)
    esp = (esp_x, esp_y, 330, 500)
    draw.rounded_rectangle((esp[0], esp[1], esp[0] + esp[2], esp[1] + esp[3]), radius=26, fill="#ECF3FF", outline="#244B7C", width=5)
    draw.rectangle((esp[0] + 72, esp[1] + 30, esp[0] + 258, esp[1] + 115), fill="#D8E6F6", outline="#244B7C", width=3)
    draw_centered(draw, (esp[0] + esp[2] / 2, esp[1] + 65), "ESP32 DevKit C", LABEL_FONT)
    for i in range(12):
        y = esp[1] + 145 + i * 25
        draw.rounded_rectangle((esp[0] + 18, y, esp[0] + 52, y + 14), radius=3, fill="#888888", outline="#555555")
        draw.rounded_rectangle((esp[0] + esp[2] - 52, y, esp[0] + esp[2] - 18, y + 14), radius=3, fill="#888888", outline="#555555")
    draw_centered(draw, (esp[0] + esp[2] / 2, esp[1] + 240), "local control", LABEL_FONT)
    draw_centered(draw, (esp[0] + esp[2] / 2, esp[1] + 280), "MQTT telemetry", LABEL_FONT)
    draw_centered(draw, (esp[0] + esp[2] / 2, esp[1] + 320), "PWM output", LABEL_FONT)

    sensor_x, sensor_y = pos("tempSensor", dy=-70)
    sensor = (sensor_x, sensor_y, 230, 120)
    draw.rounded_rectangle((sensor[0], sensor[1], sensor[0] + sensor[2], sensor[1] + sensor[3]), radius=18, fill="#FFF5E8", outline="#9A621C", width=5)
    draw_centered(draw, (sensor[0] + sensor[2] / 2, sensor[1] + 44), "DS18B20", LABEL_FONT)
    draw_centered(draw, (sensor[0] + sensor[2] / 2, sensor[1] + 82), "temperature sensor", SMALL_FONT)

    pull_x, pull_y = pos("pullupResistor", dy=-70)
    draw_resistor(draw, (pull_x, pull_y, 170, 55), "4.7 kΩ")

    led_x, led_y = pos("statusLed", dy=-70)
    draw.ellipse((led_x, led_y, led_x + 95, led_y + 95), fill="#BFE7C6", outline="#246B33", width=5)
    draw_centered(draw, (led_x + 47, led_y + 120), "status LED", SMALL_FONT)
    res_x, res_y = pos("ledResistor", dy=-70)
    draw_resistor(draw, (res_x, res_y, 145, 50), "220 Ω")

    logic_x, logic_y = pos("logic", dy=-70)
    logic = (logic_x, logic_y, 270, 210)
    draw.rounded_rectangle((logic[0], logic[1], logic[0] + logic[2], logic[1] + logic[3]), radius=18, fill="#F4F4F4", outline="#565656", width=5)
    draw_centered(draw, (logic[0] + logic[2] / 2, logic[1] + 55), "Logic analyzer", LABEL_FONT)
    draw_centered(draw, (logic[0] + logic[2] / 2, logic[1] + 98), "PWM waveform", SMALL_FONT)
    for i in range(4):
        y = logic[1] + 132 + i * 16
        draw.line((logic[0] + 55, y, logic[0] + 215, y), fill="#777777", width=3)

    colors = {"red": "#C83A32", "black": "#222222", "green": "#28824A", "blue": "#2D5EAA", "orange": "#D07A1F"}
    connection_labels = {
        ("esp:21", "tempSensor:DQ"): "GPIO21 / OneWire",
        ("esp:18", "logic:D0"): "GPIO18 / PWM",
        ("esp:2", "ledResistor:1"): "GPIO2 / status",
        ("esp:3V3", "tempSensor:VDD"): "3.3 V",
        ("esp:GND.1", "tempSensor:GND"): "GND",
    }
    anchors = {
        "esp:21": (esp[0] + esp[2], esp[1] + 195),
        "esp:18": (esp[0], esp[1] + 255),
        "esp:2": (esp[0] + esp[2], esp[1] + 375),
        "esp:3V3": (esp[0] + esp[2], esp[1] + 145),
        "esp:GND.1": (esp[0] + esp[2], esp[1] + 170),
        "esp:GND.2": (esp[0] + esp[2], esp[1] + 430),
        "esp:GND.3": (esp[0], esp[1] + 315),
        "tempSensor:DQ": (sensor[0], sensor[1] + 62),
        "tempSensor:VDD": (sensor[0], sensor[1] + 32),
        "tempSensor:GND": (sensor[0], sensor[1] + 92),
        "pullupResistor:1": (pull_x + 85, pull_y + 55),
        "pullupResistor:2": (pull_x + 85, pull_y),
        "ledResistor:1": (res_x, res_y + 25),
        "ledResistor:2": (res_x + 145, res_y + 25),
        "statusLed:A": (led_x, led_y + 48),
        "statusLed:C": (led_x + 95, led_y + 48),
        "logic:D0": (logic[0] + logic[2], logic[1] + 80),
        "logic:GND": (logic[0] + logic[2], logic[1] + 150),
    }
    label_positions = {
        ("esp:21", "tempSensor:DQ"): (980, 368),
        ("esp:18", "logic:D0"): (570, 455),
        ("esp:2", "ledResistor:1"): (1058, 825),
        ("esp:3V3", "tempSensor:VDD"): (1018, 310),
        ("esp:GND.1", "tempSensor:GND"): (1032, 475),
    }
    for src, dst, color_name, _path in data["connections"]:
        if src.startswith("$") or dst.startswith("$"):
            continue
        if src not in anchors or dst not in anchors:
            continue
        x1, y1 = anchors[src]
        x2, y2 = anchors[dst]
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        pts = [(x1, y1), (mid[0], y1), (mid[0], y2), (x2, y2)]
        label = connection_labels.get((src, dst))
        draw_arrow(draw, pts, fill=colors.get(color_name, "#555555"), width=5, label=label, label_xy=label_positions.get((src, dst)))

    draw.text((86, out_h - 102), f"Source file: {WOKWI_DIAGRAM.relative_to(ROOT)}", font=SMALL_FONT, fill="#555555")
    out = FIGURES_DIR / "figure_4_1_wokwi_connection.png"
    img.save(out)


def draw_pcb_figure() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(PCB_DXF)
    out = FIGURES_DIR / "figure_4_2_pcb_design_reference.png"
    fig = plt.figure(figsize=(12, 8.0), dpi=220)
    ax = fig.add_axes([0.035, 0.075, 0.93, 0.89])
    ax.set_facecolor("white")
    ctx = RenderContext(doc)
    Frontend(ctx, MatplotlibBackend(ax)).draw_layout(doc.modelspace(), finalize=True)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    fig.text(
        0.5,
        0.032,
        f"Source file: {PCB_DXF.relative_to(ROOT)}",
        ha="center",
        va="center",
        fontsize=10,
        fontname="Times New Roman",
        color="#555555",
    )
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def convert_schematic_pdf() -> None:
    if not SCHEMATIC_PDF.exists():
        raise FileNotFoundError(SCHEMATIC_PDF)
    tmp_prefix = FIGURES_DIR / "_figure_4_1_schematic_tmp"
    subprocess.run(
        ["pdftoppm", "-png", "-singlefile", "-r", "240", str(SCHEMATIC_PDF), str(tmp_prefix)],
        check=True,
    )
    rendered = tmp_prefix.with_suffix(".png")
    out = FIGURES_DIR / "figure_4_1_schematic.png"
    image = Image.open(rendered).convert("RGB")
    image = crop_schematic_main_area(image)
    image.save(out, quality=95)
    rendered.unlink(missing_ok=True)


def crop_schematic_main_area(image: Image.Image) -> Image.Image:
    """Keep the circuit area and remove the EasyEDA title block."""
    width, height = image.size
    search = image.crop((60, 60, width - 60, int(height * 0.62)))
    xs: list[int] = []
    ys: list[int] = []
    pixels = search.load()
    for y in range(search.height):
        for x in range(search.width):
            r, g, b = pixels[x, y]
            if min(r, g, b) < 245 and 20 < x < search.width - 20 and 20 < y < search.height - 20:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return image
    left = max(0, 60 + min(xs) - 95)
    top = max(0, 60 + min(ys) - 90)
    right = min(width, 60 + max(xs) + 95)
    bottom = min(int(height * 0.62), 60 + max(ys) + 95)
    return image.crop((left, top, right, bottom))


def copy_pcb_screenshot() -> None:
    if not PCB_SCREENSHOT.exists():
        raise FileNotFoundError(PCB_SCREENSHOT)
    out = FIGURES_DIR / "figure_4_2_pcb_design.png"
    image = Image.open(PCB_SCREENSHOT).convert("RGB")
    image = crop_pcb_main_area(image)
    image.save(out, quality=95)


def crop_pcb_main_area(image: Image.Image) -> Image.Image:
    """Crop the component-placement screenshot to the visible board area."""
    width, height = image.size
    pixels = image.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            # The EasyEDA/JLCPCB screenshot has a nearly black canvas around
            # the board. Keep colored, grey, and white board/component pixels.
            is_canvas = r < 18 and g < 18 and b < 18
            if not is_canvas:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return image

    left = max(0, min(xs) - 24)
    top = max(0, min(ys) - 24)
    right = min(width, max(xs) + 24)
    bottom = min(height, max(ys) + 24)
    return image.crop((left, top, right, bottom))


def copy_enclosure_figures() -> None:
    targets = [
        (ENCLOSURE_PRESENTATION, FIGURES_DIR / "figure_4_3_enclosure_layout.png"),
        (ENCLOSURE_PARTS, FIGURES_DIR / "figure_4_4_enclosure_parts.png"),
    ]
    for src, dst in targets:
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy2(src, dst)


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    convert_schematic_pdf()
    copy_pcb_screenshot()
    copy_enclosure_figures()
    for path in [
        FIGURES_DIR / "figure_4_1_schematic.png",
        FIGURES_DIR / "figure_4_2_pcb_design.png",
        FIGURES_DIR / "figure_4_3_enclosure_layout.png",
        FIGURES_DIR / "figure_4_4_enclosure_parts.png",
    ]:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
