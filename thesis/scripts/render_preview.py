#!/usr/bin/env python3
"""Render a docx preview PDF with LibreOffice when it is available."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "generated"


def render_preview(docx_path: Path, output_dir: Path = BUILD_DIR / "preview") -> int:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        print(
            "LibreOffice command line was not found. Install LibreOffice to render PDF previews, "
            "or open the docx in Word/LibreOffice and update fields manually."
        )
        return 0
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode == 0:
        print(f"Wrote preview PDF under {output_dir}")
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path, nargs="?", default=BUILD_DIR / "sample_final.docx")
    parser.add_argument("--output-dir", type=Path, default=BUILD_DIR / "preview")
    args = parser.parse_args(argv)
    if not args.docx.exists():
        raise SystemExit(f"Missing docx: {args.docx}")
    return render_preview(args.docx, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
