#!/usr/bin/env python3
"""Create PNG crops for final human schematic review.

The crop boxes are defined in draw.io page units and mapped to the exported
PNG coordinate space using the current final export dimensions.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = ROOT / "eda/exports/final"
PNG_PATH = EXPORT_DIR / "esp32_temperature_control_unit_electrical_schematic.png"
CROP_DIR = EXPORT_DIR / "review_crops"
MANIFEST_PATH = CROP_DIR / "manifest.json"

PAGE_WIDTH = 3293.0
PAGE_HEIGHT = 2333.0

CROPS = {
    "overview": (0, 0, PAGE_WIDTH, PAGE_HEIGHT),
    "dd1_area": (760, 560, 1480, 1470),
    "reset_led_decoupling_area": (120, 180, 820, 1580),
    "sensor_uart_area": (1500, 210, 2320, 820),
    "heater_area": (1450, 780, 2535, 1340),
    "power_area": (1320, 1450, 2570, 2050),
    "title_block_area": (2520, 2070, 3293, 2333),
    "element_list_area": (2520, 0, 3293, 1320),
}


def scale_box(box: tuple[float, float, float, float], image: Image.Image) -> tuple[int, int, int, int]:
    sx = image.width / PAGE_WIDTH
    sy = image.height / PAGE_HEIGHT
    left, top, right, bottom = box
    return (
        max(0, round(left * sx)),
        max(0, round(top * sy)),
        min(image.width, round(right * sx)),
        min(image.height, round(bottom * sy)),
    )


def main() -> None:
    if not PNG_PATH.exists():
        raise SystemExit(f"Missing final PNG: {PNG_PATH}")

    CROP_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(PNG_PATH).convert("RGBA")
    manifest: dict[str, object] = {
        "source_png": str(PNG_PATH.relative_to(ROOT.parent)),
        "source_width_px": image.width,
        "source_height_px": image.height,
        "page_width_units": PAGE_WIDTH,
        "page_height_units": PAGE_HEIGHT,
        "crops": [],
    }

    for name, drawio_box in CROPS.items():
        pixel_box = scale_box(drawio_box, image)
        output = CROP_DIR / f"{name}.png"
        image.crop(pixel_box).save(output)
        manifest["crops"].append({
            "name": name,
            "path": str(output.relative_to(ROOT.parent)),
            "drawio_box": {
                "x": drawio_box[0],
                "y": drawio_box[1],
                "width": drawio_box[2] - drawio_box[0],
                "height": drawio_box[3] - drawio_box[1],
            },
            "pixel_box": {
                "x": pixel_box[0],
                "y": pixel_box[1],
                "width": pixel_box[2] - pixel_box[0],
                "height": pixel_box[3] - pixel_box[1],
            },
        })

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
