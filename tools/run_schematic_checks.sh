#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMATIC_DIR="$ROOT_DIR/hardware/gost-schematic"
REPORT_DIR="$ROOT_DIR/build/reports"
DRAWIO_FILE="$SCHEMATIC_DIR/esp32_temperature_node_gost.drawio"
PNG_FILE="$SCHEMATIC_DIR/esp32_temperature_node_gost.png"
SVG_FILE="$SCHEMATIC_DIR/esp32_temperature_node_gost.svg"
PDF_FILE="$SCHEMATIC_DIR/esp32_temperature_node_gost.pdf"
MODEL_FILE="$SCHEMATIC_DIR/schematic_model.yaml"
TITLE_TEMPLATE="$ROOT_DIR/templates/gost_2_104_form1_title_block.yaml"
LINT="$ROOT_DIR/tools/schematic_lint.py"
RULES="$ROOT_DIR/tools/schematic_rules.yaml"
CONNECTIVITY="$ROOT_DIR/tools/validate_drawio_connectivity.py"
TITLE_VALIDATOR="$ROOT_DIR/tools/validate_title_block_geometry.py"

printf '== Tool checks ==\n'
command -v node >/dev/null
command -v python3 >/dev/null
python3 -m pytest --version >/dev/null

DRAWIO_CLI="${DRAWIO_CLI:-}"
if [[ -z "$DRAWIO_CLI" ]]; then
  for candidate in \
    "/Applications/draw.io.app/Contents/MacOS/draw.io" \
    "draw.io" \
    "drawio"; do
    if [[ -x "$candidate" ]]; then
      DRAWIO_CLI="$candidate"
      break
    fi
    if command -v "$candidate" >/dev/null 2>&1; then
      DRAWIO_CLI="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$DRAWIO_CLI" ]]; then
  printf 'ERROR: draw.io CLI not found. Set DRAWIO_CLI or install draw.io desktop CLI.\n' >&2
  exit 1
fi
printf 'draw.io CLI: %s\n' "$DRAWIO_CLI"

printf '\n== Pytest ==\n'
python3 -m pytest "$ROOT_DIR/tests/test_title_block_geometry.py" "$ROOT_DIR/tests/test_schematic_lint.py"

printf '\n== Generate draw.io ==\n'
node "$SCHEMATIC_DIR/render_esp32_gost_schematic.js"

printf '\n== Export SVG/PNG/PDF ==\n'
rm -f "$PNG_FILE" "$SVG_FILE" "$PDF_FILE"
"$DRAWIO_CLI" --export --format svg --output "$SVG_FILE" "$DRAWIO_FILE"
"$DRAWIO_CLI" --export --format png --scale 4 --output "$PNG_FILE" "$DRAWIO_FILE"
"$DRAWIO_CLI" --export --format pdf --output "$PDF_FILE" "$DRAWIO_FILE"

printf '\n== Schematic lint ==\n'
python3 "$LINT" "$DRAWIO_FILE" --config "$RULES" --reports-dir "$REPORT_DIR"

printf '\n== Title block geometry ==\n'
python3 "$TITLE_VALIDATOR" "$DRAWIO_FILE" --template "$TITLE_TEMPLATE" --report "$REPORT_DIR/title_block_geometry.json"

printf '\n== Draw.io connectivity ==\n'
python3 "$CONNECTIVITY" "$DRAWIO_FILE" --model "$MODEL_FILE" --report "$REPORT_DIR/drawio_connectivity.json"

printf '\n== ERC ==\n'
KICAD_SOURCE="$(find "$ROOT_DIR" -maxdepth 5 -type f -name '*.kicad_sch' | sort | head -n 1 || true)"
if [[ -n "$KICAD_SOURCE" ]] && command -v kicad-cli >/dev/null 2>&1; then
  kicad-cli sch erc --exit-code-violations "$KICAD_SOURCE"
  printf 'ERC_STATUS=PASSED\n' > "$REPORT_DIR/erc_status.txt"
else
  mkdir -p "$REPORT_DIR"
  printf 'ERC_UNAVAILABLE: no KiCad schematic source or kicad-cli unavailable. Electrical ERC is not fully verified.\n' | tee "$REPORT_DIR/erc_status.txt"
fi

printf '\n== Reports ==\n'
printf '%s\n' "$REPORT_DIR/schematic_lint.json"
printf '%s\n' "$REPORT_DIR/schematic_lint.md"
printf '%s\n' "$REPORT_DIR/title_block_geometry.json"
printf '%s\n' "$REPORT_DIR/drawio_connectivity.json"
printf '%s\n' "$REPORT_DIR/erc_status.txt"
