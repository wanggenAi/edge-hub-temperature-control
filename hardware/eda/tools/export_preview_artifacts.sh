#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SOURCE_DRAWIO="${ROOT_DIR}/hardware/eda/functiondiagramYUANLITU.generated.drawio"
EXPORT_DIR="${ROOT_DIR}/hardware/eda/exports/preview"
DRAWIO_CLI="${DRAWIO_CLI:-/Applications/draw.io.app/Contents/MacOS/draw.io}"

SVG_OUT="${EXPORT_DIR}/functiondiagramYUANLITU.preview.svg"
PDF_OUT="${EXPORT_DIR}/functiondiagramYUANLITU.preview.pdf"
PNG_OUT="${EXPORT_DIR}/functiondiagramYUANLITU.preview.png"

if [[ ! -x "${DRAWIO_CLI}" ]]; then
  printf 'ERROR: draw.io CLI not found or not executable: %s\n' "${DRAWIO_CLI}" >&2
  exit 1
fi

if [[ ! -f "${SOURCE_DRAWIO}" ]]; then
  printf 'ERROR: generated draw.io source missing: %s\n' "${SOURCE_DRAWIO}" >&2
  exit 1
fi

mkdir -p "${EXPORT_DIR}"

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

printf 'Preview exports generated:\n'
printf '%s\n' "- ${SVG_OUT}"
printf '%s\n' "- ${PDF_OUT}"
printf '%s\n' "- ${PNG_OUT}"
