#!/usr/bin/env python3
"""Generate thesis evidence figures from real screenshots and source fragments."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FIGURES_DIR = ROOT / "docs" / "figures"
POSTER_ASSETS = ROOT / "a1-graduation-poster" / "assets"


CODE_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Menlo.ttc"),
    Path("/System/Library/Fonts/Supplemental/Courier New.ttf"),
    Path("/System/Library/Fonts/Courier.ttc"),
]


SOURCE_FIGURES = {
    "figure_4_5_pid_anti_windup_code.png": {
        "source": ROOT / "simulator/wokwi/src/controller/pi_controller.cpp",
        "start": 31,
        "end": 60,
    },
    "figure_4_6_edge_control_tick_code.png": {
        "source": ROOT / "simulator/wokwi/src/app/edge_app.cpp",
        "start": 220,
        "end": 267,
    },
    "figure_5_3_datahub_pipeline_code.png": {
        "source": ROOT / "data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java",
        "start": 169,
        "end": 187,
    },
    "figure_5_4_hmi_command_publisher_code.png": {
        "source": ROOT / "hmi/backend/app/services/mqtt_publisher.py",
        "start": 41,
        "end": 55,
    },
    "figure_6_2_feature_extraction_code.png": {
        "source": ROOT / "hmi/backend/app/services/ai/feature_extractor.py",
        "start": 37,
        "end": 78,
    },
    "figure_6_3_recommendation_rules_code.png": {
        "source": ROOT / "hmi/backend/app/services/ai/tuning_engine.py",
        "start": 18,
        "end": 78,
    },
    "figure_6_4_post_effect_evaluator_code.png": {
        "source": ROOT / "hmi/backend/app/services/ai/post_effect_evaluator.py",
        "start": 27,
        "end": 93,
    },
}


SCREENSHOT_FIGURES = {
    "figure_5_1_hmi_device_detail.png": POSTER_ASSETS / "hmi-device-detail.png",
    "figure_5_2_hmi_ops_console.png": POSTER_ASSETS / "hmi-ops-console.png",
    "figure_6_1_hmi_validation.png": POSTER_ASSETS / "hmi-ai-validation.png",
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in CODE_FONT_CANDIDATES:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _read_snippet(path: Path, start: int, end: int) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [(line_number, lines[line_number - 1]) for line_number in range(start, min(end, len(lines)) + 1)]


def render_code_figure(output: Path, *, source: Path, start: int, end: int) -> None:
    snippet = _read_snippet(source, start, end)
    display_lines: list[str] = []
    for line_number, line in snippet:
        if len(line) > 116:
            wrapped = textwrap.wrap(line, width=116, replace_whitespace=False, drop_whitespace=False)
        else:
            wrapped = [line]
        for index, part in enumerate(wrapped):
            prefix = f"{line_number:>4}  " if index == 0 else "      "
            display_lines.append(prefix + part.expandtabs(2))

    code_font = _font(24)
    meta_font = _font(20)

    padding_x = 44
    line_height = 34
    header_height = 58
    bottom_padding = 34
    width = 1800
    height = header_height + 24 + len(display_lines) * line_height + bottom_padding

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, height - 1], outline="#202020", width=2)
    draw.rectangle([0, 0, width - 1, header_height], fill="#f7f7f7", outline="#202020", width=2)
    source_label = f"Source fragment: {source.relative_to(ROOT)}, lines {start}-{end}"
    draw.text((padding_x, 18), source_label, font=meta_font, fill="#333333")

    y = header_height + 22
    for raw_line in display_lines:
        number_part = raw_line[:6]
        code_part = raw_line[6:]
        draw.text((padding_x, y), number_part, font=code_font, fill="#777777")
        draw.text((padding_x + 88, y), code_part, font=code_font, fill="#111111")
        y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def copy_screenshot(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for output_name, source_path in SCREENSHOT_FIGURES.items():
        copy_screenshot(source_path, FIGURES_DIR / output_name)
    for output_name, spec in SOURCE_FIGURES.items():
        render_code_figure(FIGURES_DIR / output_name, **spec)


if __name__ == "__main__":
    main()
