# Final Thesis Check Report

- Final DOCX: `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/thesis_draft_final_checked.docx`
- Final PDF preview: `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/preview/thesis_draft_final_checked.pdf`
- Machine check report: `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/thesis_final_check_report_machine.md`
- Date: 14 May 2026

## Automated Check Result

`check_format.py --strict` result for `thesis_draft_final_checked.docx`:

- PASS: 952
- WARNING: 2
- ERROR: 0

The two remaining warnings are visual/manual-review warnings only:

- LibreOffice/PDF preview cannot reliably render the Word live PAGE field placed in the right-bottom template page cell. The page-number cell must still be checked in Microsoft Word.
- Side-by-side preview files were generated for manual confirmation of border thickness, title-block alignment, and clipping.

## Fixed Issues

- Created a separate final checked file instead of overwriting the working draft.
- Rebuilt the full Word document from the thesis source and school template pipeline.
- Corrected Table 2.1 terminology:
  - `Auxiliary decision support` changed to `Auxiliary decision-support mechanism`.
  - `Explainability and assisted decision making` changed to `Explainability and assisted decision-making`.
- Reordered Chapter 5 figure numbering according to first appearance:
  - Figure 5.1 is now the Data Hub bounded MQTT ingestion fragment.
  - Figure 5.2 is now the HMI device detail screen.
  - Figure 5.3 is now the HMI operations console.
  - Figure 5.4 remains the HMI backend parameter command publishing fragment.
- Reordered Chapter 6 figure numbering according to first appearance:
  - Figure 6.1 is now the feature extraction fragment.
  - Figure 6.2 is now the rule-based parameter recommendation fragment.
  - Figure 6.3 is now the HMI post-apply validation view.
  - Figure 6.4 remains the post-apply effect evaluation fragment.
- Updated the corresponding in-text references and figure captions through the build definitions.
- Added access dates to online REFERENCES entries without adding unsupported references.
- Moved Table 6.1 to start on a new page so it no longer begins at the bottom of the previous page and no longer creates a weak split-table visual impression.
- Preserved the existing thesis technical boundary: hardware is described as designed but not yet physically/electrically/thermally validated.
- Preserved the core architecture wording: three main layers and one auxiliary decision-support mechanism.

## Format Checks

- Body text: checked as Times New Roman, 13 pt, line spacing 1.25-1.3.
- Heading 1: checked as 14 pt bold, uppercase, no final period, starts on new page.
- Heading 2: checked as 13 pt bold, no final period, subsection numbering belongs to the chapter.
- Body paragraphs: checked for 12.5 mm first-line indent where applicable.
- Formulas: all formula paragraphs contain OMML math objects and use center/right tab stops with right-aligned numbering.
- Formula explanations: checked for `where` without colon, dash-based symbol explanations, semicolon punctuation, and aligned symbol tab.
- Page fill: all non-final body pages are above the 60% threshold; final body page is above the half-page threshold.

## Contents Check

- Contents spans two pages naturally.
- Contents includes section and subsection headings only.
- Dot leaders and right-side page numbers are present.
- REFERENCES is listed with the correct rendered final page: page 58.
- Chapter 5 is listed on page 34, which matches the rendered preview.
- No abnormal large blank gap was detected in the Contents pages by the automated check.

## Figure Check

- All figure captions follow the format `Figure x.x – Title` without a final period.
- All figures are referenced in body text.
- Figure numbering now follows first appearance order in Chapters 5 and 6.
- Figure 3.1 remains generated from the approved architecture diagram and is kept within the text frame.
- Code-evidence figures remain inserted as images, not body-text code blocks.
- Code-evidence figure width is checked against the body text width where applicable.

## Table Check

- All table captions follow the format `Table x.x – Title` without a final period.
- All tables are referenced before their caption.
- Table width is checked at 165 mm, matching the body text width.
- Table rows are protected from splitting internally.
- Header rows are marked to repeat if a table continues.
- Table 6.1 now starts on a new page to improve visual quality.
- No table title is separated from its table body in the automated check.

## Formula Check

- Formula (4.1) through formula (4.7) are present as Word OMML math objects.
- Formula numbering is consecutive within Chapter 4.
- Formula references use wording such as `formula (4.x)`.
- Formula (4.6) remains the standard continuous PID form with an integral term over `e(τ)dτ` and a derivative term in fraction form.
- Variable explanations follow the Rules style: `where` without colon, dash separator, semicolon ending.

## References Check

- REFERENCES starts on a new page.
- Reference numbering is consecutive from [1] to [12].
- Every in-text citation has a matching reference entry.
- Every reference entry is cited in the thesis body.
- URLs are complete in the generated text.
- Access dates were added to online sources.
- No new unsupported references were added.

## Remaining Placeholders

- The template title block still contains `BSTU.YOUR_NUMBER- 12 81 00`. This appears to be the template/project code placeholder and should be manually replaced with the official diploma code if the university requires a real code.
- No `TODO`, `TBD`, `Author`, `Supervisor`, or `Computer&Systems` body placeholders were found in the thesis source scan.

## Manual Confirmation Needed

- Open `thesis_draft_final_checked.docx` in Microsoft Word and update fields if prompted; confirm the right-bottom Page cell displays live incrementing page numbers.
- Confirm the template frame/title-block alignment visually in Word, because LibreOffice rendering is not fully reliable for the custom header frame and live page-number field.
- Confirm whether the university requires a specific national/GOST bibliographic style beyond the Rules text available in `Rules_diplom.pdf`. The current REFERENCES format is consistent and numbered, but the rules text does not provide a detailed bibliographic template.
- Confirm the official value replacing `BSTU.YOUR_NUMBER- 12 81 00` before final submission.

## Output Files

- `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/thesis_draft_final_checked.docx`
- `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/thesis_final_check_report.md`
- `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/preview/thesis_draft_final_checked.pdf`
- `/Users/seker./edge-hub-temperature-control/thesis/generated/drafts/preview/thesis_draft_final_checked-58.png`
