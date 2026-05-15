# References GOST/BrSTU Format Report

## Source Files

- Input DOCX: `thesis/generated/drafts/thesis_draft_final_format_fixed.docx`
- Output DOCX: `thesis/generated/drafts/thesis_draft_final_format_fixed_gost_refs.docx`
- Word-rendered PDF preview: `thesis/generated/drafts/preview_gost_refs_word/thesis_draft_final_format_fixed_gost_refs_word.pdf`
- Machine check report: `thesis/generated/drafts/format_fix_machine_report_gost_refs.md`

## External Format Basis

The bibliography was adjusted according to BrSTU/Brest State Technical University-oriented formatting practice found in online methodological materials for diploma project preparation. The relevant rule is that the list of used sources is arranged in the order of first citation in the text and bibliographic descriptions follow `GOST 7.1`.

The local `Rules_diplom.pdf` was also checked. It contains detailed formatting rules for figures, tables, formulas, and general thesis layout, while the bibliography details are less explicit. Therefore, the reference list was converted to a conservative GOST-like style suitable for an English technical thesis:

- numbered references in the same order as first citation;
- dash-separated bibliographic elements;
- `[Electronic resource]` marker for web documentation;
- `Mode of access:` for URLs;
- `Date of access: 15.05.2026`;
- no fabricated sources and no unsupported bibliographic data.

## Changes Made

- Converted all 30 references from `Available:` / `Accessed:` style to GOST-like bibliography style.
- Preserved reference numbering `[1]` to `[30]`.
- Preserved citation order and existing in-text citation mapping.
- Kept books and standards as bibliographic records without artificial URLs.
- Kept web documentation as electronic resources with access mode and access date.
- Did not add unsupported publication places, publishers, or page counts where they could not be safely confirmed.

## Validation Results

- Strict format check: `PASS: 1006`, `WARNING: 2`, `ERROR: 0`.
- Word-rendered PDF page count: 60 pages.
- Contents page check: `REFERENCES` is shown with page `60`.
- References section starts on page 59 and continues on page 60.
- Page 60 contains references `[15]` to `[30]`, so the final page is not sparsely filled.

## Remaining Manual Confirmation

- The university may prefer Russian labels such as `Режим доступа` and `Дата доступа` even in an English thesis. The current version uses English labels because the thesis body and references are in English.
- If the department provides a specific BrSTU bibliography template for English theses, the labels can be switched globally while preserving the same source order.
- Word field updates should be checked once more on the final machine before printing, because table of contents fields are Word-rendered objects.
