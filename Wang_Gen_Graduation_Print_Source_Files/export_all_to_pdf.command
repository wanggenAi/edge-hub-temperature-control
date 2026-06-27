#!/bin/zsh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/PDF_exports"
mkdir -p "$OUT"

SOFFICE="/opt/homebrew/bin/soffice"
DRAWIO="/Applications/draw.io.app/Contents/MacOS/draw.io"

if [[ ! -x "$SOFFICE" ]]; then
  echo "LibreOffice command not found: $SOFFICE"
  exit 1
fi

if [[ ! -x "$DRAWIO" ]]; then
  echo "draw.io command not found: $DRAWIO"
  exit 1
fi

echo "Exporting draw.io files to PDF..."
"$DRAWIO" --export --format pdf --embed-diagram --all-pages --output "$OUT/01_architecture_diagram.pdf" "$DIR/01_architecture_diagram.drawio"
"$DRAWIO" --export --format pdf --embed-diagram --all-pages --output "$OUT/02_engineering_flowchart.pdf" "$DIR/02_engineering_flowchart.drawio"
"$DRAWIO" --export --format pdf --embed-diagram --all-pages --output "$OUT/03_poster_front.pdf" "$DIR/03_poster_front.drawio"
"$DRAWIO" --export --format pdf --embed-diagram --all-pages --output "$OUT/04_poster_back.pdf" "$DIR/04_poster_back.drawio"

echo "Exporting Word files to PDF..."
"$SOFFICE" --headless --convert-to pdf --outdir "$OUT" \
  "$DIR/05_thesis.docx" \
  "$DIR/06_text_of_program_CD_appendix.docx" \
  "$DIR/07_list_of_documents.docx" \
  "$DIR/08_annotation.docx"

echo
echo "Done. PDF files are in: $OUT"
