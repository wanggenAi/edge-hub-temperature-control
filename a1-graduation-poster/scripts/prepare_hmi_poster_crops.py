#!/usr/bin/env python3
"""Create readable HMI crop assets for the A1 poster.

The full-page screenshots are useful proof that the real HMI runs, but they
become too small when placed inside a poster module. These crops keep the real
UI pixels while focusing on the chart and metric regions that remain legible at
A1 scale.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


POSTER_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = POSTER_ROOT / "assets"


def crop_asset(source: str, target: str, box: tuple[int, int, int, int], *, pad: int = 18) -> None:
    image = Image.open(ASSET_DIR / source).convert("RGB")
    cropped = image.crop(box)
    cropped = ImageOps.expand(cropped, border=pad, fill=(4, 14, 20))
    cropped.save(ASSET_DIR / target, optimize=True)
    print(f"Wrote {target}: {cropped.size}")


def main() -> None:
    crop_asset(
        "hmi-device-detail.png",
        "hmi-device-detail-crop.png",
        (35, 500, 1485, 1560),
    )
    crop_asset(
        "hmi-ai-validation.png",
        "hmi-ai-validation-crop.png",
        (35, 20, 2620, 820),
    )
    crop_asset(
        "hmi-ops-console.png",
        "hmi-ops-console-crop.png",
        (20, 420, 2640, 1160),
    )


if __name__ == "__main__":
    main()
