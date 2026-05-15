# Thesis Template System

This folder builds a reproducible Word thesis template sample. It does not contain the real thesis body yet.

## Dependencies

Use Python 3.11 or newer.

```bash
python -m pip install -r thesis/requirements.txt
```

Optional tools:

- Pandoc or Quarto, for future Markdown/QMD to docx generation.
- LibreOffice, for command-line PDF previews and field refresh checks.

## Generate The Sample Template

```bash
python thesis/scripts/build_template.py
```

The command creates:

- `thesis/template/reference.docx`
- `thesis/template/cover_template.docx`
- `thesis/generated/sample_raw.docx`
- `thesis/generated/sample_final.docx`
- `thesis/generated/format_report.md`

It also runs the strict format checker.

## Inspect Source Templates

```bash
python thesis/scripts/inspect_templates.py
```

This writes `thesis/generated/template_inspection_report.md`, including sections, margins, header/footer parts, PAGE fields, plain numeric placeholders, and key template text.

## Run The Format Checker

```bash
python thesis/scripts/check_format.py thesis/generated/sample_final.docx --strict
```

Strict mode exits with a non-zero code if any `ERROR` is found.

## Render A Preview

```bash
python thesis/scripts/render_preview.py thesis/generated/sample_final.docx
```

This requires LibreOffice. When LibreOffice and a PDF rasterizer such as `pdftoppm` are available, the format checker also writes side-by-side visual QA previews under `thesis/generated/preview/side_by_side_preview/`.

If LibreOffice is not installed, the checker writes a warning and a placeholder note in that directory. In that case, open the docx in Microsoft Word or LibreOffice manually and compare:

- `thesis/template/template_0.docx` vs the Contents page.
- `thesis/template/template_1.docx` vs the body pages.

## Update Word Fields

Open `thesis/generated/sample_final.docx` in Word, select all (`Ctrl+A` or `Cmd+A`), then update fields (`F9`, or right-click and choose update field). Word may ask to update the table of contents or fields when opening the file.

The body page number must be a real Word `PAGE` field, not typed text. A typed number will not follow pagination when sections, figures, tables, or paragraphs are added.

## Future Thesis Writing

Put future source Markdown or QMD files under `thesis/source/`. The current files are placeholders used only to validate the template system:

- `00_cover.md`
- `01_contents.md`
- `02_sample_body.md`
- `metadata.yaml`

Do not directly edit `thesis/generated/sample_final.docx` except during the final manual inspection stage. Regenerate it from source and scripts whenever possible.

Do not overwrite the original files in `thesis/`:

- `Rules_diplom.pdf`
- `template_0.docx`
- `template_1.docx`
