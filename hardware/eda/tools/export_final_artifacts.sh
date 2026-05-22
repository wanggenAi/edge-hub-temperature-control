#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
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

if [[ ! -f "${SOURCE_DRAWIO}" ]]; then
  printf 'ERROR: generated draw.io source missing: %s\n' "${SOURCE_DRAWIO}" >&2
  exit 1
fi

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
