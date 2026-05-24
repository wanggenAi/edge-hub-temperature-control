#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FRAME_DRAWIO="${ROOT_DIR}/hardware/eda/functiondiagramYUANLITU.drawio"
KICAD_SVG="${ROOT_DIR}/hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg"
SOURCE_DRAWIO="${ROOT_DIR}/hardware/eda/functiondiagramYUANLITU.generated.drawio"
EXPORT_DIR="${ROOT_DIR}/hardware/eda/exports/final"
DRAWIO_CLI="${DRAWIO_CLI:-/Applications/draw.io.app/Contents/MacOS/draw.io}"
BASENAME="esp32_temperature_control_unit_electrical_schematic"

DRAWIO_OUT="${EXPORT_DIR}/${BASENAME}.drawio"
SVG_OUT="${EXPORT_DIR}/${BASENAME}.svg"
PDF_OUT="${EXPORT_DIR}/${BASENAME}.pdf"
PNG_OUT="${EXPORT_DIR}/${BASENAME}.png"

if [[ ! -x "${DRAWIO_CLI}" ]]; then
  printf 'ERROR: draw.io CLI not found or not executable: %s\n' "${DRAWIO_CLI}" >&2
  exit 1
fi

if [[ ! -f "${FRAME_DRAWIO}" ]]; then
  printf 'ERROR: school frame draw.io source missing: %s\n' "${FRAME_DRAWIO}" >&2
  exit 1
fi

if [[ ! -f "${KICAD_SVG}" ]]; then
  printf 'ERROR: KiCad SVG source missing: %s\n' "${KICAD_SVG}" >&2
  exit 1
fi

python3 "${ROOT_DIR}/hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py" \
  --frame "${FRAME_DRAWIO}" \
  --kicad-svg "${KICAD_SVG}" \
  --output "${SOURCE_DRAWIO}"

python3 "${ROOT_DIR}/hardware/eda/tools/update_generated_element_list.py" \
  --input "${SOURCE_DRAWIO}" \
  --output "${SOURCE_DRAWIO}"

python3 "${ROOT_DIR}/hardware/eda/tools/update_generated_title_block.py" \
  --input "${SOURCE_DRAWIO}" \
  --output "${SOURCE_DRAWIO}"

python3 "${ROOT_DIR}/hardware/eda/tools/validate_generated_tables_match_master.py" \
  --master "${FRAME_DRAWIO}" \
  --candidate "${SOURCE_DRAWIO}" \
  --final-candidate "${SOURCE_DRAWIO}" \
  --report "${ROOT_DIR}/docs/bstu_master_table_lock_report.md" \
  --json-report "${ROOT_DIR}/build/reports/bstu_master_table_lock.json"

mkdir -p "${EXPORT_DIR}"
cp "${SOURCE_DRAWIO}" "${DRAWIO_OUT}"

"${DRAWIO_CLI}" \
  --export \
  --format svg \
  --output "${SVG_OUT}" \
  "${SOURCE_DRAWIO}"

"${DRAWIO_CLI}" \
  --export \
  --format pdf \
  --output "${PDF_OUT}" \
  "${SOURCE_DRAWIO}"

"${DRAWIO_CLI}" \
  --export \
  --format png \
  --scale 2 \
  --output "${PNG_OUT}" \
  "${SOURCE_DRAWIO}"

printf 'Final schematic artifacts generated:\n'
printf '%s\n' "- ${DRAWIO_OUT}"
printf '%s\n' "- ${SVG_OUT}"
printf '%s\n' "- ${PDF_OUT}"
printf '%s\n' "- ${PNG_OUT}"
