# Thesis Word Template System

This directory contains generated and copied Word templates used by the thesis build scripts.

- `template_0.docx` is a preserved copy of the Contents/content page frame.
- `template_1.docx` is a preserved copy of the body page frame.
- `cover_template.docx` is generated from the template frame and contains only a page border.
- `reference.docx` is generated for Pandoc/Quarto-compatible Word styles.
- `rules.yaml` centralizes the measurable rules extracted from `Rules_diplom.pdf`.

Do not edit or overwrite the original files in `thesis/`: `Rules_diplom.pdf`, `template_0.docx`, and `template_1.docx`.

Regenerate derived templates with:

```bash
python thesis/scripts/build_template.py
```

The body page number in the final document must remain a Word `PAGE` field. A typed page number is not acceptable because it will not update when sections, figures, tables, or pages change.
