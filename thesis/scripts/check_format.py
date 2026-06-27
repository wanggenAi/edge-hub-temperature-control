#!/usr/bin/env python3
"""Check a generated thesis docx against the Rules_diplom.pdf requirements."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

try:
    from lxml import etree
except ImportError as exc:  # pragma: no cover - dependency guidance path
    raise SystemExit(
        "Missing dependency: lxml. Install with `python -m pip install lxml python-docx Pillow pypdf`."
    ) from exc

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from docx_utils import (
    LAYOUT,
    NS,
    child,
    has_page_field,
    has_toc_field,
    iter_section_properties,
    parse_xml,
    qn,
    relationship_targets,
    section_ref_targets,
    text_of,
    twips_to_mm,
    mm_to_twips,
)


ROOT = SCRIPT_DIR.parent
BUILD_DIR = ROOT / "generated"
REPORT_PATH = BUILD_DIR / "format_report.md"
TEMPLATE_DIR = ROOT / "template"


RULES = {
    "page_width_mm": LAYOUT.page_width_mm,
    "page_height_mm": LAYOUT.page_height_mm,
    "left_margin_mm": LAYOUT.left_margin_mm,
    "right_margin_mm": LAYOUT.right_margin_mm,
    "top_margin_mm": LAYOUT.top_margin_mm,
    "bottom_margin_mm": LAYOUT.bottom_margin_mm,
    "footer_distance_mm": LAYOUT.footer_distance_mm,
    "body_font": "Times New Roman",
    "body_size_pt": 13.0,
    "body_line_spacing_min": 1.25,
    "body_line_spacing_max": 1.30,
    "first_line_indent_mm": 12.5,
    "heading1_size_pt": 14.0,
    "heading2_size_pt": 13.0,
    "figure_caption_re": r"^Figure\s+\d+(?:\.\d+)?\s+\u2013\s+\S.+(?<!\.)$",
    "table_caption_re": r"^Table\s+\d+(?:\.\d+)?\s+\u2013\s+\S.+(?<!\.)$",
    "formula_number_re": r"\(\d+\.\d+\)",
}


FORMULA_REFERENCE_RE = r"\b(?:formula|equation|expression|equality|transfer function)\s+\(\d+\.\d+\)"


EMU_PER_MM = 36000
CONTENTS_FRAME_DX_EMU = -109728
CONTENTS_FRAME_DY_EMU = -79248
CONTENTS_FRAME_SCALE_X = 1.00137
CONTENTS_FRAME_SCALE_Y = 0.98959
FRAME_VISUAL_BALANCE_DX_EMU = -65000
FRAME_VISUAL_BALANCE_DX_TWIPS = int(round(FRAME_VISUAL_BALANCE_DX_EMU / 635))
FRAME_ALIGN_TO_BODY_DX_EMU = 182880
FRAME_ALIGN_TO_BODY_DY_EMU = 91440
CONTENTS_PAGE_FRAME_DY_EMU = -103632
CONTENTS_PAGE_FRAME_SCALE_Y = 0.98229
LIVE_PAGE_FIELD_X_TWIPS = 11150 + FRAME_VISUAL_BALANCE_DX_TWIPS
LIVE_PAGE_FIELD_Y_TWIPS = 15880
LIVE_PAGE_FIELD_WIDTH_TWIPS = 540
LIVE_PAGE_FIELD_HEIGHT_TWIPS = 500
LIVE_PAGE_FIELD_RUN_POSITION_HALF_POINTS = 0
BODY_TITLE_BLOCK_CODE = "БрГТУ.241297 - 05 81 00"
BODY_TITLE_BLOCK_PAGE_START = 5
BODY_TITLE_BLOCK_TOTAL_PAGES = 62
FORMULA_SYMBOL_TAB_MM = 16.0
FORMULA_SYMBOL_TAB_TWIPS = mm_to_twips(FORMULA_SYMBOL_TAB_MM)
FORMULA_SYMBOL_RE = r"[A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?"
CONTENTS_FIRST_PAGE_ENTRY_LIMIT = 27
FLOAT_SPACING_MIN_PT = 12.0
FLOAT_SPACING_MAX_PT = 15.0
NUMBERED_REFERENCE_WORDS_RE = r"(?:Figure|Table|formula|equation|expression|equality|transfer function)"


RULE_MARGIN_TWIPS = {
    "top": str(mm_to_twips(LAYOUT.top_margin_mm)),
    "right": str(mm_to_twips(LAYOUT.right_margin_mm)),
    "bottom": str(mm_to_twips(LAYOUT.bottom_margin_mm)),
    "left": str(mm_to_twips(LAYOUT.left_margin_mm)),
    "header": str(mm_to_twips(LAYOUT.header_distance_mm)),
    "footer": str(mm_to_twips(LAYOUT.footer_distance_mm)),
    "gutter": "0",
}


@dataclass
class Finding:
    severity: str
    code: str
    message: str


class Reporter:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def pass_(self, code: str, message: str) -> None:
        self.findings.append(Finding("PASS", code, message))

    def warn(self, code: str, message: str) -> None:
        self.findings.append(Finding("WARNING", code, message))

    def error(self, code: str, message: str) -> None:
        self.findings.append(Finding("ERROR", code, message))

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "ERROR" for f in self.findings)

    def counts(self) -> dict[str, int]:
        return {
            severity: sum(1 for f in self.findings if f.severity == severity)
            for severity in ["PASS", "WARNING", "ERROR"]
        }


def _approx(actual: float | None, expected: float, tolerance: float) -> bool:
    return actual is not None and abs(actual - expected) <= tolerance


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _visible_text(element: etree._Element) -> str:
    return "".join(text.text or "" for text in element.xpath(".//w:t", namespaces=NS))


def _style_map(styles_root: etree._Element | None) -> dict[str, etree._Element]:
    if styles_root is None:
        return {}
    styles = {}
    for style in styles_root.xpath("//w:style", namespaces=NS):
        style_id = style.get(qn("w:styleId"))
        if style_id:
            styles[style_id] = style
    return styles


def _style_name(style_el: etree._Element | None) -> str:
    if style_el is None:
        return ""
    name = style_el.find("w:name", namespaces=NS)
    return name.get(qn("w:val"), "") if name is not None else ""


def _paragraph_style_id(paragraph: etree._Element) -> str | None:
    style = paragraph.find("w:pPr/w:pStyle", namespaces=NS)
    return style.get(qn("w:val")) if style is not None else None


def _is_paragraph_style(paragraph: etree._Element, styles: dict[str, etree._Element], wanted: str) -> bool:
    sid = _paragraph_style_id(paragraph)
    if sid == wanted.replace(" ", "") or sid == wanted:
        return True
    return _style_name(styles.get(sid or "")).lower() == wanted.lower()


def _run_props(paragraph: etree._Element, styles: dict[str, etree._Element]) -> list[etree._Element]:
    props = []
    sid = _paragraph_style_id(paragraph)
    style = styles.get(sid or "")
    if style is not None:
        style_rpr = style.find("w:rPr", namespaces=NS)
        if style_rpr is not None:
            props.append(style_rpr)
    for rpr in paragraph.xpath("./w:r/w:rPr", namespaces=NS):
        props.append(rpr)
    return props


def _paragraph_props(paragraph: etree._Element, styles: dict[str, etree._Element]) -> list[etree._Element]:
    props = []
    sid = _paragraph_style_id(paragraph)
    style = styles.get(sid or "")
    if style is not None:
        style_ppr = style.find("w:pPr", namespaces=NS)
        if style_ppr is not None:
            props.append(style_ppr)
    ppr = paragraph.find("w:pPr", namespaces=NS)
    if ppr is not None:
        props.append(ppr)
    return props


def _effective_font(paragraph: etree._Element, styles: dict[str, etree._Element]) -> str | None:
    for rpr in reversed(_run_props(paragraph, styles)):
        fonts = rpr.find("w:rFonts", namespaces=NS)
        if fonts is not None:
            return (
                fonts.get(qn("w:ascii"))
                or fonts.get(qn("w:hAnsi"))
                or fonts.get(qn("w:cs"))
                or fonts.get(qn("w:eastAsia"))
            )
    return None


def _effective_size_pt(paragraph: etree._Element, styles: dict[str, etree._Element]) -> float | None:
    for rpr in reversed(_run_props(paragraph, styles)):
        size = rpr.find("w:sz", namespaces=NS)
        if size is not None and size.get(qn("w:val")):
            return int(size.get(qn("w:val"))) / 2
    return None


def _effective_bold(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    for rpr in reversed(_run_props(paragraph, styles)):
        bold = rpr.find("w:b", namespaces=NS)
        if bold is not None:
            return bold.get(qn("w:val"), "true") not in {"0", "false", "False"}
    return False


def _effective_underline(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    for rpr in reversed(_run_props(paragraph, styles)):
        underline = rpr.find("w:u", namespaces=NS)
        if underline is not None:
            return underline.get(qn("w:val"), "single") not in {"none", "0", "false"}
    return False


def _effective_all_caps(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    for rpr in reversed(_run_props(paragraph, styles)):
        caps = rpr.find("w:caps", namespaces=NS)
        if caps is not None:
            return caps.get(qn("w:val"), "true") not in {"0", "false", "False"}
    return False


def _effective_keep_next(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        keep_next = ppr.find("w:keepNext", namespaces=NS)
        if keep_next is not None:
            return keep_next.get(qn("w:val"), "true") not in {"0", "false", "False"}
    return False


def _effective_space_after_pt(paragraph: etree._Element, styles: dict[str, etree._Element]) -> float | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        spacing = ppr.find("w:spacing", namespaces=NS)
        if spacing is not None and spacing.get(qn("w:after")):
            return int(spacing.get(qn("w:after"))) / 20
    return None


def _effective_space_before_pt(paragraph: etree._Element, styles: dict[str, etree._Element]) -> float | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        spacing = ppr.find("w:spacing", namespaces=NS)
        if spacing is not None and spacing.get(qn("w:before")):
            return int(spacing.get(qn("w:before"))) / 20
    return None


def _effective_tab_stops(paragraph: etree._Element, styles: dict[str, etree._Element]) -> list[etree._Element]:
    tabs: list[etree._Element] = []
    for ppr in _paragraph_props(paragraph, styles):
        tabs.extend(ppr.xpath("./w:tabs/w:tab", namespaces=NS))
    return tabs


def _effective_alignment(paragraph: etree._Element, styles: dict[str, etree._Element]) -> str | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        jc = ppr.find("w:jc", namespaces=NS)
        if jc is not None:
            return jc.get(qn("w:val"))
    return None


def _effective_line_spacing(paragraph: etree._Element, styles: dict[str, etree._Element]) -> float | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        spacing = ppr.find("w:spacing", namespaces=NS)
        if spacing is not None and spacing.get(qn("w:line")):
            line_rule = spacing.get(qn("w:lineRule"))
            line = int(spacing.get(qn("w:line")))
            if line_rule in {None, "auto"}:
                return line / 240
    return None


def _effective_exact_line_spacing_pt(paragraph: etree._Element, styles: dict[str, etree._Element]) -> float | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        spacing = ppr.find("w:spacing", namespaces=NS)
        if spacing is not None and spacing.get(qn("w:line")):
            line_rule = spacing.get(qn("w:lineRule"))
            if line_rule not in {"exact", "atLeast"}:
                continue
            return int(spacing.get(qn("w:line"))) / 20
    return None


def _effective_first_line_indent_mm(
    paragraph: etree._Element, styles: dict[str, etree._Element]
) -> float | None:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        ind = ppr.find("w:ind", namespaces=NS)
        if ind is not None and ind.get(qn("w:firstLine")):
            return twips_to_mm(ind.get(qn("w:firstLine")))
    return None


def _paragraph_tab_positions_twips(paragraph: etree._Element) -> list[int]:
    positions: list[int] = []
    for tab in paragraph.xpath("./w:pPr/w:tabs/w:tab", namespaces=NS):
        value = tab.get(qn("w:pos"))
        if value is not None:
            positions.append(int(value))
    return positions


def _has_formula_symbol_tab(paragraph: etree._Element) -> bool:
    return any(abs(pos - FORMULA_SYMBOL_TAB_TWIPS) <= 20 for pos in _paragraph_tab_positions_twips(paragraph))


def _has_literal_tab_before_symbol(paragraph: etree._Element, *, first_where_line: bool) -> bool:
    seen_where = not first_where_line
    for child_el in paragraph.iterchildren():
        if child_el.tag != qn("w:r"):
            continue
        run_text = "".join(child_el.xpath("./w:t/text()", namespaces=NS))
        if first_where_line and run_text == "where ":
            seen_where = True
            continue
        if seen_where and child_el.find("w:tab", namespaces=NS) is not None:
            return True
        if run_text.strip():
            return False
    return False


def _is_empty_body_paragraph(element: etree._Element | None) -> bool:
    if element is None or element.tag != qn("w:p"):
        return False
    if _paragraph_has_page_break(element):
        return False
    if _clean(text_of(element)):
        return False
    return not element.xpath(".//a:blip|.//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS)


def _paragraph_has_page_break(element: etree._Element | None) -> bool:
    if element is None or element.tag != qn("w:p"):
        return False
    return bool(element.xpath(".//w:br[@w:type='page']", namespaces=NS))


def _is_empty_spacing_paragraph(element: etree._Element | None) -> bool:
    return _is_empty_body_paragraph(element) and not _paragraph_has_page_break(element)


def _is_float_spacing_paragraph(element: etree._Element | None, styles: dict[str, etree._Element]) -> bool:
    if not _is_empty_spacing_paragraph(element):
        return False
    spacing_pt = _effective_exact_line_spacing_pt(element, styles)
    return spacing_pt is not None and FLOAT_SPACING_MIN_PT <= spacing_pt <= FLOAT_SPACING_MAX_PT


def _has_formula_trailing_comma(paragraph: etree._Element) -> bool:
    seen_math = False
    for child_el in paragraph:
        if child_el.tag in {qn("m:oMath"), qn("m:oMathPara")}:
            seen_math = True
            continue
        if not seen_math or child_el.tag != qn("w:r"):
            continue
        if child_el.find("w:tab", namespaces=NS) is not None:
            return False
        if "".join(child_el.xpath("./w:t/text()", namespaces=NS)) == ",":
            return True
    return False


def _has_formula_comma_inside_math(paragraph: etree._Element) -> bool:
    return any("," in text for text in paragraph.xpath(".//m:oMath//m:t/text()|.//m:oMathPara//m:t/text()", namespaces=NS))


def _has_page_break_before(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    for ppr in reversed(_paragraph_props(paragraph, styles)):
        page_break = ppr.find("w:pageBreakBefore", namespaces=NS)
        if page_break is not None:
            return page_break.get(qn("w:val"), "true") not in {"0", "false", "False"}
    return False


def _is_template_paragraph(paragraph: etree._Element) -> bool:
    text = _clean(text_of(paragraph))
    if paragraph.xpath(".//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS) and not paragraph.xpath(
        ".//a:blip", namespaces=NS
    ):
        return True
    return any(
        key in text
        for key in [
            "BSTU.YOUR_NUMBER",
            "БрГТУ.241297",
            "Sign",
            "Supervisor",
            "Author",
            "Computer&Systems",
        ]
    )


def _is_body_candidate(paragraph: etree._Element, styles: dict[str, etree._Element]) -> bool:
    text = _clean(text_of(paragraph))
    if not text or _is_template_paragraph(paragraph):
        return False
    if text == "Contents" or "\t" in text:
        return False
    if re.match(r"^\[\d+\]\s+\S", text):
        return False
    if _is_paragraph_style(paragraph, styles, "Contents Entry") or _is_paragraph_style(paragraph, styles, "Contents Title"):
        return False
    if text.startswith(("Figure ", "Table ")):
        return False
    if paragraph.xpath(".//a:blip", namespaces=NS):
        return False
    if re.search(RULES["formula_number_re"], text):
        return False
    if (
        _is_paragraph_style(paragraph, styles, "Heading 1")
        or _is_paragraph_style(paragraph, styles, "Heading 2")
        or _is_paragraph_style(paragraph, styles, "Heading 3")
        or _is_paragraph_style(paragraph, styles, "Formula")
    ):
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _body_children(root: etree._Element) -> list[etree._Element]:
    body = root.find("w:body", namespaces=NS)
    return list(body) if body is not None else []


def _section_ranges(root: etree._Element) -> list[list[etree._Element]]:
    children = _body_children(root)
    ranges: list[list[etree._Element]] = []
    current: list[etree._Element] = []
    for child_el in children:
        if child_el.tag == qn("w:sectPr"):
            current.append(child_el)
            ranges.append(current)
            current = []
            continue
        current.append(child_el)
        if child_el.xpath("./w:pPr/w:sectPr", namespaces=NS):
            ranges.append(current)
            current = []
    if current:
        ranges.append(current)
    return ranges


def _section_paragraphs(root: etree._Element, section_index: int) -> list[etree._Element]:
    ranges = _section_ranges(root)
    if section_index >= len(ranges):
        return []
    return [el for el in ranges[section_index] if el.tag == qn("w:p") and not el.xpath("./w:pPr/w:sectPr", namespaces=NS)]


def _body_section_paragraphs(root: etree._Element) -> list[etree._Element]:
    ranges = _section_ranges(root)
    if len(ranges) < 3:
        return []
    return [el for el in ranges[2] if el.tag == qn("w:p")]


def _body_section_children(root: etree._Element) -> list[etree._Element]:
    ranges = _section_ranges(root)
    return ranges[2] if len(ranges) >= 3 else []


def _chapter_number_from_heading(text: str) -> int | None:
    match = re.match(r"^(\d+)\s+\S", text)
    return int(match.group(1)) if match else None


def _subsection_numbers_from_heading(text: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\s+\S", text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _body_item_kind(element: etree._Element, styles: dict[str, etree._Element]) -> str:
    if element.tag == qn("w:tbl"):
        return "table"
    if element.tag != qn("w:p"):
        return "other"
    if _is_paragraph_style(element, styles, "Heading 1"):
        return "heading1"
    if _is_paragraph_style(element, styles, "Heading 2"):
        return "heading2"
    if _is_paragraph_style(element, styles, "Heading 3"):
        return "heading3"
    if element.xpath(".//a:blip", namespaces=NS) and not _is_template_paragraph(element):
        return "figure"
    text = _clean(text_of(element))
    if text.startswith("Table "):
        return "table_caption"
    if text.startswith("Figure "):
        return "figure_caption"
    if re.search(RULES["formula_number_re"], text) and (
        _is_paragraph_style(element, styles, "Formula") or element.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS)
    ):
        return "formula"
    if text and not _is_template_paragraph(element):
        return "text"
    return "empty"


def _chapter_ranges(root: etree._Element, styles: dict[str, etree._Element]) -> list[tuple[int, str, list[etree._Element]]]:
    chapters: list[tuple[int, str, list[etree._Element]]] = []
    current_number: int | None = None
    current_title = ""
    current_items: list[etree._Element] = []
    for element in _body_section_children(root):
        if element.tag == qn("w:p") and _is_paragraph_style(element, styles, "Heading 1"):
            heading_text = _clean(text_of(element))
            if heading_text == "REFERENCES":
                if current_number is not None:
                    chapters.append((current_number, current_title, current_items))
                current_number = None
                current_title = ""
                current_items = []
                continue
            if current_number is not None:
                chapters.append((current_number, current_title, current_items))
            current_title = heading_text
            current_number = _chapter_number_from_heading(current_title)
            current_items = [element]
        elif current_number is not None:
            current_items.append(element)
    if current_number is not None:
        chapters.append((current_number, current_title, current_items))
    return chapters


def _load_package(docx_path: Path) -> tuple[dict[str, bytes], etree._Element, etree._Element | None]:
    with ZipFile(docx_path) as zf:
        package = {name: zf.read(name) for name in zf.namelist()}
    document_root = parse_xml(package["word/document.xml"])
    styles_root = parse_xml(package["word/styles.xml"]) if "word/styles.xml" in package else None
    return package, document_root, styles_root


def _section_signature(sect: etree._Element) -> dict[str, str | None]:
    pg_sz = sect.find("w:pgSz", namespaces=NS)
    pg_mar = sect.find("w:pgMar", namespaces=NS)
    return {
        "pgSz.w": pg_sz.get(qn("w:w")) if pg_sz is not None else None,
        "pgSz.h": pg_sz.get(qn("w:h")) if pg_sz is not None else None,
        "pgMar.top": pg_mar.get(qn("w:top")) if pg_mar is not None else None,
        "pgMar.right": pg_mar.get(qn("w:right")) if pg_mar is not None else None,
        "pgMar.bottom": pg_mar.get(qn("w:bottom")) if pg_mar is not None else None,
        "pgMar.left": pg_mar.get(qn("w:left")) if pg_mar is not None else None,
        "pgMar.header": pg_mar.get(qn("w:header")) if pg_mar is not None else None,
        "pgMar.footer": pg_mar.get(qn("w:footer")) if pg_mar is not None else None,
    }


def _template_section_signature(template_name: str) -> dict[str, str | None]:
    with ZipFile(TEMPLATE_DIR / template_name) as zf:
        root = parse_xml(zf.read("word/document.xml"))
    sects = root.xpath("//w:sectPr", namespaces=NS)
    if not sects:
        return {}
    return _section_signature(sects[-1])


def _margin_signature(sect: etree._Element) -> dict[str, str | None]:
    pg_mar = sect.find("w:pgMar", namespaces=NS)
    return {
        key: pg_mar.get(qn(f"w:{key}")) if pg_mar is not None else None
        for key in ["top", "right", "bottom", "left", "header", "footer", "gutter"]
    }


def _first_xpath(element: etree._Element, xpath: str) -> etree._Element | None:
    matches = element.xpath(xpath, namespaces=NS)
    return matches[0] if matches else None


def _attrs_or_none(element: etree._Element | None) -> dict[str, str] | None:
    return dict(element.attrib) if element is not None else None


def _text_or_none(element: etree._Element | None) -> str | None:
    return "".join(element.itertext()).strip() if element is not None else None


def _outer_frame_shapes(root: etree._Element) -> list[etree._Element]:
    return [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _shape_name(shape) == "Rectangle 65"
    ]


def _outer_frame_signature(shape: etree._Element) -> dict[str, object]:
    anchor = _first_xpath(shape, "ancestor::wp:anchor[1]")
    position_h = _first_xpath(shape, "ancestor::wp:anchor[1]/wp:positionH")
    position_v = _first_xpath(shape, "ancestor::wp:anchor[1]/wp:positionV")
    anchor_attrs = _attrs_or_none(anchor)
    if anchor_attrs:
        anchor_attrs = {
            etree.QName(key).localname: value
            for key, value in anchor_attrs.items()
            if etree.QName(key).localname not in {"anchorId", "editId"}
        }
    return {
        "shape.off": _attrs_or_none(_first_xpath(shape, "./wps:spPr/a:xfrm/a:off")),
        "shape.ext": _attrs_or_none(_first_xpath(shape, "./wps:spPr/a:xfrm/a:ext")),
        "shape.line": _attrs_or_none(_first_xpath(shape, "./wps:spPr/a:ln")),
        "shape.line.color": _attrs_or_none(_first_xpath(shape, "./wps:spPr/a:ln/a:solidFill/a:srgbClr")),
        "group.off": _attrs_or_none(_first_xpath(shape, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:off")),
        "group.ext": _attrs_or_none(_first_xpath(shape, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:ext")),
        "group.chOff": _attrs_or_none(_first_xpath(shape, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:chOff")),
        "group.chExt": _attrs_or_none(_first_xpath(shape, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:chExt")),
        "anchor": anchor_attrs,
        "anchor.positionH": _attrs_or_none(position_h),
        "anchor.positionH.offset": _text_or_none(_first_xpath(shape, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset")),
        "anchor.positionV": _attrs_or_none(position_v),
        "anchor.positionV.offset": _text_or_none(_first_xpath(shape, "ancestor::wp:anchor[1]/wp:positionV/wp:posOffset")),
        "anchor.extent": _attrs_or_none(_first_xpath(shape, "ancestor::wp:anchor[1]/wp:extent")),
        "anchor.effectExtent": _attrs_or_none(_first_xpath(shape, "ancestor::wp:anchor[1]/wp:effectExtent")),
    }


def _template1_outer_frame_signature() -> dict[str, object]:
    with ZipFile(TEMPLATE_DIR / "template_1.docx") as zf:
        root = parse_xml(zf.read("word/header2.xml"))
    frames = _outer_frame_shapes(root)
    if not frames:
        return {}
    return _outer_frame_signature(frames[0])


def _add_to_int_text(element: etree._Element | None, delta: int) -> None:
    if element is None or element.text is None:
        return
    element.text = str(int(element.text) + delta)


def _scale_int_attr(element: etree._Element | None, attr: str, scale: float) -> None:
    if element is None:
        return
    value = element.get(attr)
    if value is not None:
        element.set(attr, str(int(round(int(value) * scale))))


def _set_expected_outer_line_style(shape: etree._Element) -> None:
    line = shape.find("./wps:spPr/a:ln", namespaces=NS)
    if line is None:
        sp_pr = shape.find("./wps:spPr", namespaces=NS)
        if sp_pr is None:
            return
        line = etree.SubElement(sp_pr, qn("a:ln"))
    line.set("w", "25400")
    for no_fill in list(line.findall("a:noFill", namespaces=NS)):
        line.remove(no_fill)
    solid = line.find("a:solidFill", namespaces=NS)
    if solid is None:
        solid = etree.SubElement(line, qn("a:solidFill"))
    color = solid.find("a:srgbClr", namespaces=NS)
    if color is None:
        color = etree.SubElement(solid, qn("a:srgbClr"))
    color.set("val", "000000")


def _contents_aligned_template1_outer_frame_signature(*, align_to_body_pixels: bool = False) -> dict[str, object]:
    with ZipFile(TEMPLATE_DIR / "template_1.docx") as zf:
        root = parse_xml(zf.read("word/header2.xml"))
    frames = _outer_frame_shapes(root)
    if not frames:
        return {}
    frame = frames[0]
    _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), CONTENTS_FRAME_DX_EMU)
    _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), FRAME_VISUAL_BALANCE_DX_EMU)
    _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionV/wp:posOffset"), CONTENTS_FRAME_DY_EMU)
    if align_to_body_pixels:
        _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), FRAME_ALIGN_TO_BODY_DX_EMU)
        _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionV/wp:posOffset"), FRAME_ALIGN_TO_BODY_DY_EMU)
    anchor_extent = _first_xpath(frame, "ancestor::wp:anchor[1]/wp:extent")
    group_ext = _first_xpath(frame, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:ext")
    _scale_int_attr(anchor_extent, "cx", CONTENTS_FRAME_SCALE_X)
    _scale_int_attr(anchor_extent, "cy", CONTENTS_FRAME_SCALE_Y)
    _scale_int_attr(group_ext, "cx", CONTENTS_FRAME_SCALE_X)
    _scale_int_attr(group_ext, "cy", CONTENTS_FRAME_SCALE_Y)
    _set_expected_outer_line_style(frame)
    return _outer_frame_signature(frame)


def _contents_aligned_body_outer_frame_signature() -> dict[str, object]:
    signature = _contents_aligned_template1_outer_frame_signature()
    anchor = signature.get("anchor")
    if isinstance(anchor, dict):
        anchor = dict(anchor)
        anchor["behindDoc"] = "1"
        signature["anchor"] = anchor
    return signature


def _check_outer_frame_geometry(
    reporter: Reporter,
    code: str,
    label: str,
    frames: list[etree._Element],
    expected: dict[str, object],
) -> None:
    if not frames:
        reporter.error(code, f"{label} has no template_1 Rectangle 65 outer frame")
        return
    mismatches = []
    strict_keys = {
        "shape.off",
        "shape.ext",
        "shape.line",
        "shape.line.color",
        "anchor.positionH.offset",
        "anchor.positionV.offset",
    }
    tolerance_by_key = {
        "anchor.positionH.offset": 750,
        "anchor.positionV.offset": 7500,
    }
    for key, expected_value in expected.items():
        if key not in strict_keys:
            continue
        actual_value = _outer_frame_signature(frames[0]).get(key)
        if key in tolerance_by_key and actual_value is not None and expected_value is not None:
            try:
                if abs(int(str(actual_value)) - int(str(expected_value))) <= tolerance_by_key[key]:
                    continue
            except ValueError:
                pass
        if actual_value != expected_value:
            mismatches.append(f"{key}: actual={actual_value} expected={expected_value}")
    if mismatches:
        reporter.error(code, f"{label} Rectangle 65 geometry differs from Contents-aligned template_1: " + "; ".join(mismatches))
    else:
        reporter.pass_(code, f"{label} Rectangle 65 core geometry, line width, color, and calibrated offsets match the accepted frame")


def _bottom_right_score(element: etree._Element) -> tuple[int, int]:
    off = element.find("./wps:spPr/a:xfrm/a:off", namespaces=NS)
    if off is not None:
        try:
            return int(off.get("x", "0")), int(off.get("y", "0"))
        except ValueError:
            return 0, 0
    style = element.get("style", "")
    found: dict[str, int] = {}
    for key in ["left", "top"]:
        match = re.search(rf"{key}:(-?\d+)", style)
        if match:
            found[key] = int(match.group(1))
    return found.get("left", 0), found.get("top", 0)


def _shape_kind(element: etree._Element) -> str:
    if element.tag == qn("wps:wsp"):
        return "drawingml"
    if element.tag == qn("v:shape"):
        return "vml"
    return "other"


def _page_label_shapes(root: etree._Element) -> list[etree._Element]:
    return [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _clean(_visible_text(shape)) == "Page"
    ]


def _nearest_page_number_shape(root: etree._Element, kind: str = "drawingml") -> etree._Element | None:
    labels = [shape for shape in _page_label_shapes(root) if _shape_kind(shape) == kind]
    candidates = [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _shape_kind(shape) == kind
        and shape not in labels
        and (
            any(instr.text and re.search(r"\bPAGE\b", instr.text) for instr in shape.xpath(".//w:instrText", namespaces=NS))
            or re.fullmatch(r"\d+", _clean(_visible_text(shape))) is not None
        )
    ]
    if not labels or not candidates:
        return None
    label = max(labels, key=_bottom_right_score)
    lx, ly = _bottom_right_score(label)
    pool = [
        candidate
        for candidate in candidates
        if _bottom_right_score(candidate)[0] >= lx - 50 and _bottom_right_score(candidate)[1] >= ly
    ] or candidates
    return min(
        pool,
        key=lambda candidate: (
            abs(_bottom_right_score(candidate)[0] - lx),
            abs(_bottom_right_score(candidate)[1] - ly),
        ),
    )


def _shape_name(element: etree._Element) -> str:
    if element.tag == qn("wps:wsp"):
        props = element.find("./wps:cNvPr", namespaces=NS)
        return props.get("name", "") if props is not None else ""
    if element.tag == qn("v:shape"):
        return element.get("id", "") or element.get("name", "")
    return ""


def _textbox83_shapes(root: etree._Element) -> list[etree._Element]:
    return [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _shape_name(shape) == "Text Box 83"
    ]


def _textbox_shapes_by_name(root: etree._Element, wanted: str) -> list[etree._Element]:
    return [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _shape_name(shape) == wanted
    ]


def _has_highlight_or_shading(element: etree._Element) -> bool:
    return bool(element.xpath(".//w:highlight|.//w:shd", namespaces=NS))


def _shape_has_field(shape: etree._Element, instr: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(instr)}\b")
    return any(
        node.text and pattern.search(node.text)
        for node in shape.xpath(".//w:instrText", namespaces=NS)
    )


def _field_display_values(element: etree._Element, instr: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(instr)}\b")
    values: list[str] = []
    in_field = False
    after_separate = False
    for node in element.iter():
        if node.tag == qn("w:instrText") and node.text and pattern.search(node.text):
            in_field = True
            after_separate = False
        elif in_field and node.tag == qn("w:fldChar"):
            fld_type = node.get(qn("w:fldCharType"))
            if fld_type == "separate":
                after_separate = True
            elif fld_type == "end":
                in_field = False
                after_separate = False
        elif in_field and after_separate and node.tag == qn("w:t") and node.text:
            values.append(_clean(node.text))
    return values


def _text_outside_fields(element: etree._Element) -> list[str]:
    values: list[str] = []
    field_depth = 0
    for node in element.iter():
        if node.tag == qn("w:fldChar"):
            fld_type = node.get(qn("w:fldCharType"))
            if fld_type == "begin":
                field_depth += 1
            elif fld_type == "end" and field_depth:
                field_depth -= 1
        elif node.tag == qn("w:t") and node.text and field_depth == 0:
            text = _clean(node.text)
            if text:
                values.append(text)
    return values


def _has_standard_page_field(element: etree._Element) -> bool:
    paragraphs = []
    if element.tag == qn("w:p") and element.xpath(".//w:instrText[contains(., 'PAGE')]", namespaces=NS):
        paragraphs.append(element)
    paragraphs.extend(element.xpath(".//w:p[.//w:instrText[contains(., 'PAGE')]]", namespaces=NS))
    for paragraph in paragraphs:
        has_begin = bool(paragraph.xpath(".//w:fldChar[@w:fldCharType='begin']", namespaces=NS))
        has_instr = bool(paragraph.xpath(".//w:instrText[contains(., 'PAGE')]", namespaces=NS))
        has_separate = bool(paragraph.xpath(".//w:fldChar[@w:fldCharType='separate']", namespaces=NS))
        has_display = bool(paragraph.xpath(".//w:fldChar[@w:fldCharType='separate']/following::w:t[1]", namespaces=NS))
        has_end = bool(paragraph.xpath(".//w:fldChar[@w:fldCharType='end']", namespaces=NS))
        if has_begin and has_instr and has_separate and has_display and has_end:
            return True
    return False


def _standard_page_field_paragraphs(root: etree._Element) -> list[etree._Element]:
    return [paragraph for paragraph in root.xpath(".//w:p[.//w:instrText[contains(., 'PAGE')]]", namespaces=NS) if _has_standard_page_field(paragraph)]


def _live_page_field_paragraphs(root: etree._Element) -> list[etree._Element]:
    return [
        paragraph
        for paragraph in root.xpath("./w:p[.//w:instrText[contains(., 'PAGE')]]", namespaces=NS)
        if paragraph.find("./w:pPr/w:framePr", namespaces=NS) is not None
        and not paragraph.xpath(".//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS)
    ]


def _frame_pr_signature(paragraph: etree._Element) -> dict[str, str | None]:
    frame_pr = paragraph.find("./w:pPr/w:framePr", namespaces=NS)
    if frame_pr is None:
        return {}
    wanted = ["wrap", "hAnchor", "vAnchor", "x", "y", "w", "h"]
    return {name: frame_pr.get(qn(f"w:{name}")) for name in wanted}


def _page_field_run_position_values(paragraph: etree._Element) -> list[str | None]:
    values = []
    for run in paragraph.xpath("./w:r", namespaces=NS):
        if run.xpath("./w:fldChar|./w:instrText|./w:t", namespaces=NS):
            position = run.find("./w:rPr/w:position", namespaces=NS)
            values.append(position.get(qn("w:val")) if position is not None else None)
    return values


def _expected_live_page_frame_signature() -> dict[str, str]:
    return {
        "wrap": "none",
        "hAnchor": "page",
        "vAnchor": "page",
        "x": str(LIVE_PAGE_FIELD_X_TWIPS),
        "y": str(LIVE_PAGE_FIELD_Y_TWIPS),
        "w": str(LIVE_PAGE_FIELD_WIDTH_TWIPS),
        "h": str(LIVE_PAGE_FIELD_HEIGHT_TWIPS),
    }


def _color_value(paragraph: etree._Element, styles: dict[str, etree._Element]) -> tuple[str | None, dict[str, str]]:
    for rpr in reversed(_run_props(paragraph, styles)):
        color = rpr.find("w:color", namespaces=NS)
        if color is not None:
            return color.get(qn("w:val")), {etree.QName(k).localname: v for k, v in color.attrib.items()}
    return None, {}


def _style_color(style_el: etree._Element | None) -> tuple[str | None, dict[str, str]]:
    if style_el is None:
        return None, {}
    color = style_el.find("w:rPr/w:color", namespaces=NS)
    if color is None:
        return None, {}
    return color.get(qn("w:val")), {etree.QName(k).localname: v for k, v in color.attrib.items()}


def _is_black_or_default_black(color: str | None, attrs: dict[str, str]) -> bool:
    if any(k in attrs for k in ["themeColor", "themeShade", "themeTint"]):
        return False
    return color in {None, "000000", "auto"}


def _contents_entry_tab_segments(paragraph: etree._Element) -> list[str]:
    segments = [""]
    for run in paragraph.xpath("./w:r", namespaces=NS):
        for child_el in run:
            if child_el.tag == qn("w:t"):
                segments[-1] += child_el.text or ""
            elif child_el.tag == qn("w:tab"):
                segments.append("")
    return [_clean(segment) for segment in segments]


STALE_TEMPLATE_FALLBACK_MARKERS = [
    "BSTU.YOUR_NUMBER",
    "YOUR_NUMBER",
    "Your_name",
    "Designing a universal microcomputer",
    "Explanotary note",
    "Nikalayuk",
    "Rtsishchava",
    "Luo Zhenkun",
    "8051",
]


def _stale_template_fallback_texts(parts: list[etree._Element]) -> list[str]:
    stale = []
    for part in parts:
        for fallback in part.xpath(".//mc:Fallback", namespaces=NS):
            text = _clean(text_of(fallback))
            if any(marker in text for marker in STALE_TEMPLATE_FALLBACK_MARKERS):
                stale.append(text[:180] if text else "(empty fallback)")
    return stale


def check_page_setup(root: etree._Element, reporter: Reporter) -> None:
    sections = iter_section_properties(root)
    if len(sections) < 3:
        reporter.error("page.sections", f"Expected at least 3 sections, found {len(sections)}")
        return
    reporter.pass_("page.sections", f"Document has {len(sections)} sections")
    expected_signatures = [
        ("template_1.docx", _template_section_signature("template_1.docx")),
        ("template_0.docx", _template_section_signature("template_0.docx")),
        ("template_1.docx", _template_section_signature("template_1.docx")),
    ]
    for idx, sect in enumerate(sections[:3], start=1):
        if idx == 1 and sect.xpath("./w:pgBorders", namespaces=NS):
            reporter.error("page.section1.pgBorders", "Cover section uses w:pgBorders; cover border must come from template_1 Rectangle 65")
        elif idx == 1:
            reporter.pass_("page.section1.pgBorders", "Cover section does not use w:pgBorders")
        pg_sz = sect.find("w:pgSz", namespaces=NS)
        pg_mar = sect.find("w:pgMar", namespaces=NS)
        width = twips_to_mm(pg_sz.get(qn("w:w"))) if pg_sz is not None else None
        height = twips_to_mm(pg_sz.get(qn("w:h"))) if pg_sz is not None else None
        if _approx(width, RULES["page_width_mm"], 1.0) and _approx(height, RULES["page_height_mm"], 1.0):
            reporter.pass_(f"page.section{idx}.a4", f"Section {idx} is A4-ish: {width:.2f} x {height:.2f} mm")
        else:
            reporter.error(f"page.section{idx}.a4", f"Section {idx} page size is {width!r} x {height!r} mm")
        template_name, expected = expected_signatures[idx - 1]
        actual = _section_signature(sect)
        comparable_keys = list(expected)
        if idx == 3:
            comparable_keys = [key for key in comparable_keys if not key.startswith("pgMar.")]
        mismatches = [
            f"{key}: actual={actual.get(key)} expected={expected.get(key)}"
            for key in comparable_keys
            if actual.get(key) != expected.get(key)
        ]
        if mismatches:
            reporter.error(
                f"page.section{idx}.templateSectPr",
                f"Section {idx} must preserve {template_name} template page geometry; " + "; ".join(mismatches),
            )
        else:
            reporter.pass_(
                f"page.section{idx}.templateSectPr",
                f"Section {idx} preserves {template_name} page geometry for template anchors",
            )
        if idx == 3:
            actual_margins = _margin_signature(sect)
            margin_mismatches = [
                f"{key}: actual={actual_margins.get(key)} expected={value}"
                for key, value in RULE_MARGIN_TWIPS.items()
                if actual_margins.get(key) != value
            ]
            if margin_mismatches:
                reporter.error(
                    "page.body.rulesMargins",
                    "Body text margins must match Rules_diplom Appendix L "
                    "(left 30 mm, right 15 mm, top 20 mm, bottom 27 mm): "
                    + "; ".join(margin_mismatches),
                )
            else:
                reporter.pass_(
                    "page.body.rulesMargins",
                    "Body text margins match Rules_diplom Appendix L: left 30 mm, right 15 mm, top 20 mm, bottom 27 mm",
                )


def check_body_paragraphs(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    paragraphs = [p for p in _body_section_paragraphs(root) if _is_body_candidate(p, styles)]
    if not paragraphs:
        reporter.error("body.exists", "No body text paragraphs were found")
        return
    reporter.pass_("body.exists", f"Found {len(paragraphs)} body text paragraph(s)")
    for idx, paragraph in enumerate(paragraphs[:30], start=1):
        text = _clean(text_of(paragraph))[:80]
        font = _effective_font(paragraph, styles)
        size = _effective_size_pt(paragraph, styles)
        spacing = _effective_line_spacing(paragraph, styles)
        indent = _effective_first_line_indent_mm(paragraph, styles)
        alignment = _effective_alignment(paragraph, styles)
        if font == RULES["body_font"]:
            reporter.pass_(f"body.p{idx}.font", f"Body paragraph uses {font}: {text}")
        else:
            reporter.error(f"body.p{idx}.font", f"Body paragraph font is {font!r}, expected Times New Roman: {text}")
        if size == RULES["body_size_pt"]:
            reporter.pass_(f"body.p{idx}.size", f"Body paragraph is {size:.1f} pt")
        else:
            reporter.error(f"body.p{idx}.size", f"Body paragraph size is {size!r}, expected 13 pt: {text}")
        if spacing is not None and RULES["body_line_spacing_min"] <= spacing <= RULES["body_line_spacing_max"]:
            reporter.pass_(f"body.p{idx}.spacing", f"Body line spacing is {spacing:.2f}")
        else:
            reporter.error(f"body.p{idx}.spacing", f"Body line spacing is {spacing!r}, expected 1.25-1.3: {text}")
        if indent is not None and abs(indent - RULES["first_line_indent_mm"]) <= 1.0:
            reporter.pass_(f"body.p{idx}.indent", f"Body first-line indent is {indent:.2f} mm")
        else:
            reporter.error(f"body.p{idx}.indent", f"Body first-line indent is {indent!r}, expected 12.5 mm: {text}")
        if alignment in {"both", "distribute", "thaiDistribute"}:
            reporter.pass_(f"body.p{idx}.align", "Body paragraph is justified")
        else:
            reporter.error(f"body.p{idx}.align", f"Body paragraph alignment is {alignment!r}, expected justified: {text}")


def check_headings(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    body_paragraphs = _body_section_paragraphs(root)
    h1s = [p for p in body_paragraphs if _is_paragraph_style(p, styles, "Heading 1")]
    h2s = [p for p in body_paragraphs if _is_paragraph_style(p, styles, "Heading 2")]
    if not h1s:
        reporter.error("heading1.exists", "No Heading 1 paragraphs found")
    for idx, paragraph in enumerate(h1s, start=1):
        text = _clean(text_of(paragraph))
        if text == "REFERENCES":
            if _has_page_break_before(paragraph, styles):
                reporter.pass_(f"heading1.{idx}.referencesPageBreak", "REFERENCES starts on a new page")
            else:
                reporter.error(f"heading1.{idx}.referencesPageBreak", "REFERENCES must start on a new page")
            if _effective_size_pt(paragraph, styles) == RULES["heading1_size_pt"] and _effective_bold(paragraph, styles):
                reporter.pass_(f"heading1.{idx}.referencesStyle", "REFERENCES uses Heading 1 thesis style")
            else:
                reporter.error(
                    f"heading1.{idx}.referencesStyle",
                    f"REFERENCES must use Heading 1 style: size={_effective_size_pt(paragraph, styles)}, bold={_effective_bold(paragraph, styles)}",
                )
            if not _effective_underline(paragraph, styles):
                reporter.pass_(f"heading1.{idx}.referencesUnderline", "REFERENCES is not underlined")
            else:
                reporter.error(f"heading1.{idx}.referencesUnderline", "REFERENCES must not be underlined")
            continue
        numbered_title = re.sub(r"^\d+\s+", "", text)
        if text in {"INTRODUCTION", "CONCLUSION"}:
            reporter.pass_(f"heading1.{idx}.number", f"{text} is correctly unnumbered")
            numbered_title = text
        elif re.match(r"^\d+\s+\S", text):
            reporter.pass_(f"heading1.{idx}.number", f"Heading 1 number format is valid: {text}")
        else:
            reporter.error(f"heading1.{idx}.number", f"Heading 1 must start with Arabic section number: {text}")
        if numbered_title == numbered_title.upper():
            reporter.pass_(f"heading1.{idx}.uppercase", f"Heading 1 title is uppercase: {text}")
        else:
            reporter.error(f"heading1.{idx}.uppercase", f"Heading 1 title must be uppercase: {text}")
        if not text.endswith("."):
            reporter.pass_(f"heading1.{idx}.period", "Heading 1 has no final period")
        else:
            reporter.error(f"heading1.{idx}.period", f"Heading 1 must not end with a period: {text}")
        if _effective_size_pt(paragraph, styles) == RULES["heading1_size_pt"] and _effective_bold(paragraph, styles):
            reporter.pass_(f"heading1.{idx}.style", "Heading 1 is 14 pt bold")
        else:
            reporter.error(
                f"heading1.{idx}.style",
                f"Heading 1 style must be 14 pt bold: size={_effective_size_pt(paragraph, styles)}, bold={_effective_bold(paragraph, styles)}",
            )
        if _has_page_break_before(paragraph, styles):
            reporter.pass_(f"heading1.{idx}.pagebreak", "Heading 1 has page break before")
        else:
            reporter.error(f"heading1.{idx}.pagebreak", f"Heading 1 must start on a new page: {text}")
        if _effective_all_caps(paragraph, styles):
            reporter.pass_(f"heading1.{idx}.capsStyle", "Heading 1 style uses all caps")
        else:
            reporter.warn(
                f"heading1.{idx}.capsStyle",
                f"Rules require section headings in capital letters; text is uppercase, but Word all-caps style is not explicit: {text}",
            )
        after_pt = _effective_space_after_pt(paragraph, styles)
        if after_pt is not None and after_pt > 0:
            reporter.pass_(f"heading1.{idx}.afterSpace", f"Heading 1 leaves space after heading: {after_pt:.1f} pt")
        else:
            reporter.error(f"heading1.{idx}.afterSpace", f"Heading 1 must leave whitespace before following text: {text}")
        if _effective_keep_next(paragraph, styles):
            reporter.pass_(f"heading1.{idx}.keepNext", "Heading 1 is kept with following text")
        else:
            reporter.warn(f"heading1.{idx}.keepNext", f"Heading 1 should be kept with following text to avoid orphan heading: {text}")
        if not _effective_underline(paragraph, styles):
            reporter.pass_(f"heading1.{idx}.underline", "Heading 1 is not underlined")
        else:
            reporter.error(f"heading1.{idx}.underline", f"Heading 1 must not be underlined: {text}")
        color, attrs = _color_value(paragraph, styles)
        if _is_black_or_default_black(color, attrs):
            reporter.pass_(f"heading1.{idx}.color", "Heading 1 is black/default black")
        else:
            reporter.error(f"heading1.{idx}.color", f"Heading 1 must be black, not {attrs}: {text}")
    if not h2s:
        reporter.warn("heading2.exists", "No Heading 2 paragraphs found")
    for idx, paragraph in enumerate(h2s, start=1):
        text = _clean(text_of(paragraph))
        if re.match(r"^\d+\.\d+\s+\S", text):
            reporter.pass_(f"heading2.{idx}.number", f"Heading 2 number format is valid: {text}")
        else:
            reporter.error(f"heading2.{idx}.number", f"Heading 2 must start with number like 1.1: {text}")
        if not text.endswith("."):
            reporter.pass_(f"heading2.{idx}.period", "Heading 2 has no final period")
        else:
            reporter.error(f"heading2.{idx}.period", f"Heading 2 must not end with a period: {text}")
        if _effective_size_pt(paragraph, styles) == RULES["heading2_size_pt"] and _effective_bold(paragraph, styles):
            reporter.pass_(f"heading2.{idx}.style", "Heading 2 is 13 pt bold")
        else:
            reporter.error(
                f"heading2.{idx}.style",
                f"Heading 2 style must be 13 pt bold: size={_effective_size_pt(paragraph, styles)}, bold={_effective_bold(paragraph, styles)}",
            )
        title = re.sub(r"^\d+\.\d+\s+", "", text)
        if title and title[:1] == title[:1].upper() and title != title.upper():
            reporter.pass_(f"heading2.{idx}.case", f"Heading 2 starts with a capital and is not all caps: {text}")
        else:
            reporter.warn(
                f"heading2.{idx}.case",
                f"Rules require subsection headings in lowercase after the first capital letter; manually review: {text}",
            )
        after_pt = _effective_space_after_pt(paragraph, styles)
        if after_pt is not None and after_pt > 0:
            reporter.pass_(f"heading2.{idx}.afterSpace", f"Heading 2 leaves space after heading: {after_pt:.1f} pt")
        else:
            reporter.error(f"heading2.{idx}.afterSpace", f"Heading 2 must leave whitespace before following text: {text}")
        if _effective_keep_next(paragraph, styles):
            reporter.pass_(f"heading2.{idx}.keepNext", "Heading 2 is kept with following text")
        else:
            reporter.warn(f"heading2.{idx}.keepNext", f"Heading 2 should be kept with following text to avoid orphan heading: {text}")
        if not _effective_underline(paragraph, styles):
            reporter.pass_(f"heading2.{idx}.underline", "Heading 2 is not underlined")
        else:
            reporter.error(f"heading2.{idx}.underline", f"Heading 2 must not be underlined: {text}")
        color, attrs = _color_value(paragraph, styles)
        if _is_black_or_default_black(color, attrs):
            reporter.pass_(f"heading2.{idx}.color", "Heading 2 is black/default black")
        else:
            reporter.error(f"heading2.{idx}.color", f"Heading 2 must be black, not {attrs}: {text}")

    h3s = [p for p in body_paragraphs if _is_paragraph_style(p, styles, "Heading 3")]
    for idx, paragraph in enumerate(h3s, start=1):
        text = _clean(text_of(paragraph))
        color, attrs = _color_value(paragraph, styles)
        if _is_black_or_default_black(color, attrs):
            reporter.pass_(f"heading3.{idx}.color", "Heading 3 is black/default black")
        else:
            reporter.error(f"heading3.{idx}.color", f"Heading 3 must be black, not {attrs}: {text}")


def check_thesis_section_structure(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    body_paragraphs = _body_section_paragraphs(root)
    heading_events: list[tuple[str, str]] = []
    for paragraph in body_paragraphs:
        text = _clean(text_of(paragraph))
        if not text:
            continue
        if _is_paragraph_style(paragraph, styles, "Heading 1"):
            heading_events.append(("h1", text))
        elif _is_paragraph_style(paragraph, styles, "Heading 2"):
            heading_events.append(("h2", text))

    h1_texts = [text for kind, text in heading_events if kind == "h1"]
    if h1_texts and h1_texts[0] == "INTRODUCTION":
        reporter.pass_("section.introduction.position", "INTRODUCTION is the first body section and is unnumbered")
    else:
        reporter.error(
            "section.introduction.position",
            f"INTRODUCTION must be the first unnumbered body section; found {h1_texts[:3]}",
        )

    if "CONCLUSION" in h1_texts:
        reporter.pass_("section.conclusion.unnumbered", "CONCLUSION is present as an unnumbered Heading 1")
    else:
        numbered_conclusions = [text for text in h1_texts if re.search(r"\bCONCLUSION\b", text)]
        reporter.error(
            "section.conclusion.unnumbered",
            "CONCLUSION must be present without a leading number"
            + (f"; found {numbered_conclusions}" if numbered_conclusions else ""),
        )

    numbered_h1s = [
        (int(match.group(1)), text)
        for text in h1_texts
        if (match := re.match(r"^(\d+)\s+\S", text))
    ]
    numbers = [number for number, _ in numbered_h1s]
    expected = [1, 2, 3, 4, 5]
    if numbers == expected:
        reporter.pass_("section.numberedSequence", f"Numbered thesis sections are consecutive and start at 1: {numbers}")
    else:
        reporter.error("section.numberedSequence", f"Numbered thesis sections must be {expected}; found {numbers}")

    forbidden_numbered = [text for text in h1_texts if re.match(r"^\d+\s+(?:INTRODUCTION|CONCLUSION)\b", text)]
    if forbidden_numbered:
        reporter.error(
            "section.boundaryNumbering",
            "INTRODUCTION and CONCLUSION must not have section numbers: " + "; ".join(forbidden_numbered),
        )
    else:
        reporter.pass_("section.boundaryNumbering", "INTRODUCTION and CONCLUSION have no leading numbers")

    current_h1 = ""
    boundary_h2s: dict[str, list[str]] = {"INTRODUCTION": [], "CONCLUSION": []}
    for kind, text in heading_events:
        if kind == "h1":
            current_h1 = text
            continue
        if kind == "h2" and current_h1 in boundary_h2s:
            boundary_h2s[current_h1].append(text)
    for section, subsections in boundary_h2s.items():
        if subsections:
            reporter.error(
                f"section.{section.lower()}.subsections",
                f"{section} must be continuous text without subsection headings: " + "; ".join(subsections[:6]),
            )
        else:
            reporter.pass_(f"section.{section.lower()}.subsections", f"{section} has no subsection headings")


def check_style_colors(styles: dict[str, etree._Element], reporter: Reporter) -> None:
    for wanted in [
        "Heading 1",
        "Heading 2",
        "Heading 3",
        "Caption",
        "Figure Caption",
        "Table Caption",
        "Contents Entry",
        "Contents Title",
    ]:
        style_el = next(
            (
                style
                for style in styles.values()
                if _style_name(style).lower() == wanted.lower()
                or (style.get(qn("w:styleId")) or "").lower() == wanted.replace(" ", "").lower()
            ),
            None,
        )
        if style_el is None:
            reporter.error(f"stylecolor.{wanted}", f"{wanted} style is missing")
            continue
        color, attrs = _style_color(style_el)
        if _is_black_or_default_black(color, attrs):
            reporter.pass_(f"stylecolor.{wanted}", f"{wanted} style is black/default black")
        else:
            reporter.error(f"stylecolor.{wanted}", f"{wanted} style color must be black without theme color; found {attrs}")


def check_contents(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    paragraphs = _section_paragraphs(root, 1)
    body_leading_contents: list[etree._Element] = []
    for p in _body_section_paragraphs(root):
        text = _clean(text_of(p))
        if _is_paragraph_style(p, styles, "Contents Entry"):
            body_leading_contents.append(p)
            continue
        if text:
            break
    all_contents_paragraphs = paragraphs + body_leading_contents
    title_candidates = [p for p in paragraphs if _clean(text_of(p)) == "Contents"]
    if not title_candidates:
        reporter.error("contents.title.exists", "No Contents title found")
        return
    title = title_candidates[0]
    if _effective_alignment(title, styles) == "center":
        reporter.pass_("contents.title.align", "Contents title is centered")
    else:
        reporter.error("contents.title.align", "Contents title must be centered")
    if _effective_size_pt(title, styles) == 14 and _effective_bold(title, styles):
        reporter.pass_("contents.title.style", "Contents title is 14 pt bold")
    else:
        reporter.error(
            "contents.title.style",
            f"Contents title must be 14 pt bold: size={_effective_size_pt(title, styles)}, bold={_effective_bold(title, styles)}",
        )
    if has_toc_field(root):
        reporter.pass_("contents.structure", "Document contains a TOC field")
    else:
        contents_lines = [
            p
            for p in all_contents_paragraphs
            if _clean(text_of(p)) and p is not title and re.search(r"\d+$", _clean(text_of(p)))
        ]
        if contents_lines:
            reporter.pass_("contents.structure", f"Manual Contents structure found with {len(contents_lines)} entry/entries")
        else:
            reporter.error("contents.structure", "No TOC field or manual contents entries found")
    content_entries = [
        p
        for p in all_contents_paragraphs
        if (
            p is not title
            and _is_paragraph_style(p, styles, "Contents Entry")
            and _clean(text_of(p))
            and re.search(r"\d+$", _clean(text_of(p)))
        )
    ]
    malformed_entries = []
    for entry in content_entries:
        segments = _contents_entry_tab_segments(entry)
        before_tab = _clean(" ".join(segments[:-1]))
        page_segment = segments[-1] if segments else ""
        if len(segments) < 2 or not re.fullmatch(r"\d+", page_segment) or re.search(r"\d+$", before_tab):
            malformed_entries.append(_clean(text_of(entry)))
    if malformed_entries:
        reporter.error(
            "contents.entryPageTabOrder",
            "Contents entries must be title + dot-leader tab + page number; malformed entries: "
            + "; ".join(malformed_entries[:10]),
        )
    else:
        reporter.pass_("contents.entryPageTabOrder", "Contents page numbers are separated after the dot-leader tab")
    if len(content_entries) > CONTENTS_FIRST_PAGE_ENTRY_LIMIT:
        if body_leading_contents:
            reporter.pass_(
                "contents.bottomOverlapGuard",
                "Long Contents continues on a body-frame page before it can overlap the Contents title block",
            )
        else:
            reporter.error(
                "contents.bottomOverlapGuard",
                f"Long Contents has {len(content_entries)} entries but does not continue on a body-frame page after safe entry limit {CONTENTS_FIRST_PAGE_ENTRY_LIMIT}",
            )
    else:
        reporter.pass_("contents.bottomOverlapGuard", "Contents entry count fits on one page without reaching the title block")
    dot_leader = False
    for paragraph in all_contents_paragraphs:
        for tab in _effective_tab_stops(paragraph, styles):
            if tab.get(qn("w:leader")) == "dot":
                dot_leader = True
    if dot_leader:
        reporter.pass_("contents.dotleader", "Contents entries use a dot leader tab")
    else:
        reporter.error("contents.dotleader", "Contents entries must connect headings to page numbers with dot leaders")
    entries_text = "\n".join(_clean(text_of(p)) for p in all_contents_paragraphs if p is not title)
    body_headings = [
        _clean(text_of(p))
        for p in _body_section_paragraphs(root)
        if _is_paragraph_style(p, styles, "Heading 1") or _is_paragraph_style(p, styles, "Heading 2")
    ]
    missing = [heading for heading in body_headings if heading and heading not in entries_text]
    if missing:
        reporter.error(
            "contents.coverage",
            "Contents must include all section and subsection headings; missing: " + "; ".join(missing[:10]),
        )
    elif body_headings:
        reporter.pass_("contents.coverage", "Contents includes all Heading 1 and Heading 2 entries")
    else:
        reporter.warn("contents.coverage", "No body Heading 1/Heading 2 entries were found to compare with Contents")


def check_page_numbers(package: dict[str, bytes], root: etree._Element, reporter: Reporter) -> None:
    if "word/settings.xml" in package:
        settings_root = parse_xml(package["word/settings.xml"])
        if settings_root.xpath("./w:updateFields", namespaces=NS):
            reporter.error("pagenum.updatePrompt", "Document sets w:updateFields and will trigger Word's update-fields prompt")
        else:
            reporter.pass_("pagenum.updatePrompt", "Document does not request Word's update-fields prompt")
    sections = iter_section_properties(root)
    if len(sections) < 3:
        reporter.error("pagenum.sections", "Cannot check page numbers without 3 sections")
        return
    unexpected_restarts: list[str] = []
    for idx, sect in enumerate(sections[1:], start=2):
        pg_num = sect.find("w:pgNumType", namespaces=NS)
        start_value = pg_num.get(qn("w:start")) if pg_num is not None else None
        if idx == 3:
            if start_value != str(BODY_TITLE_BLOCK_PAGE_START):
                reporter.error(
                    "pagenum.bodyStart",
                    f"Body/title-block section must start visible page numbering at {BODY_TITLE_BLOCK_PAGE_START}, found {start_value or '<none>'}",
                )
                return
            continue
        if start_value:
            unexpected_restarts.append(f"section {idx}: {start_value}")
    if unexpected_restarts:
        reporter.error("pagenum.continuity", "Unexpected page-number restart(s): " + "; ".join(unexpected_restarts))
        return
    reporter.pass_("pagenum.bodyStart", f"Body/title-block section starts visible page numbering at {BODY_TITLE_BLOCK_PAGE_START}")
    reporter.pass_("pagenum.continuity", "No unexpected section page-number restarts")

    cover_targets = section_ref_targets(package, sections[0])
    cover_has_visible_page = False
    for target in cover_targets:
        if target in package:
            target_root = parse_xml(package[target])
            if has_page_field(target_root) or re.search(r"\bPage\b", text_of(target_root)):
                cover_has_visible_page = True
    if cover_has_visible_page:
        reporter.error("pagenum.cover.hidden", "Cover section header/footer contains visible page numbering")
    else:
        reporter.pass_("pagenum.cover.hidden", "Cover section has no visible page number in header/footer")

    body_targets = section_ref_targets(package, sections[-1])
    body_parts = [(target, parse_xml(package[target])) for target in body_targets if target in package]
    body_xml = [part for _, part in body_parts]
    header_parts = [(target, part) for target, part in body_parts if "/header" in target]
    footer_parts = [(target, part) for target, part in body_parts if "/footer" in target]
    headers_with_fields = [(target, part) for target, part in header_parts if has_page_field(part)]
    footers_with_fields = [(target, part) for target, part in footer_parts if has_page_field(part)]
    if headers_with_fields:
        reporter.pass_("pagenum.body.pagefield", "Body header contains a Word PAGE field")
    else:
        reporter.error("pagenum.body.pagefield", "Body header must contain a live PAGE field in the right-bottom Page cell")
    if footers_with_fields:
        reporter.error(
            "pagenum.body.footerField",
            "Body footer must be blank and must not contain PAGE fields: "
            + ", ".join(target for target, _ in footers_with_fields),
        )
    else:
        reporter.pass_("pagenum.body.footerField", "Body footer contains no PAGE field")
    total_fields = 0
    total_live_fields = 0
    artifact_re = re.compile(r"(?:\bX\b|\b3X\b|\b33X\b|\b66\b|PAGE\s+PAGE|\bPAGE\b)")
    for target, part in body_parts:
        txt = _clean(_visible_text(part))
        is_footer = "/footer" in target
        live_paragraphs = _live_page_field_paragraphs(part)
        floating_page_paragraphs = [
            paragraph
            for paragraph in part.xpath("./w:p[.//w:instrText[contains(., 'PAGE')]]", namespaces=NS)
            if paragraph not in live_paragraphs
            and not paragraph.xpath(".//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS)
        ]
        if floating_page_paragraphs:
            reporter.error(
                "pagenum.body.topPollution",
                f"`{target}` has unframed standalone PAGE paragraph(s) that can render at top: "
                + str([_clean(_visible_text(p)) for p in floating_page_paragraphs]),
            )
        else:
            reporter.pass_("pagenum.body.topPollution", f"`{target}` has no unframed top PAGE paragraph")
        field_count = len([instr for instr in part.xpath(".//w:instrText", namespaces=NS) if instr.text and re.search(r"\bPAGE\b", instr.text)])
        total_fields += field_count
        total_live_fields += len(live_paragraphs)
        if is_footer and has_page_field(part):
            reporter.error("pagenum.body.footer", f"`{target}` contains PAGE field; page number must not be in a footer")
        elif is_footer:
            reporter.pass_("pagenum.body.footer", f"`{target}` has no PAGE field")
        if "Page" in txt and not any(has_page_field(other_part) for _, other_part in body_parts):
            reporter.error("pagenum.body.plain", f"`{target}` has plain Page text but body section has no PAGE field")
        txt_without_allowed_shapes = txt
        for shape in _textbox83_shapes(part) + _page_label_shapes(part):
            txt_without_allowed_shapes = txt_without_allowed_shapes.replace(_clean(_visible_text(shape)), "")
        suspicious = artifact_re.findall(txt_without_allowed_shapes)
        if suspicious:
            reporter.error(
                "pagenum.body.artifactText",
                f"`{target}` contains visible page artifact text {suspicious}: {txt[:200]}",
            )
        else:
            reporter.pass_("pagenum.body.artifactText", f"`{target}` has no visible X/PAGE artifacts")

        if has_page_field(part) and not is_footer:
            textbox83 = _textbox83_shapes(part)
            if not textbox83:
                reporter.error("pagenum.body.location", f"`{target}` must contain template_1 Text Box 83")
            elif any(has_page_field(shape) for shape in textbox83):
                reporter.error(
                    "pagenum.body.location",
                    f"`{target}` has a PAGE field inside DrawingML Text Box 83; Word does not refresh that field live while editing",
                )
            else:
                plain_digits = [
                    _clean(_visible_text(paragraph))
                    for shape in textbox83
                    for paragraph in shape.xpath(".//w:txbxContent/w:p", namespaces=NS)
                    if re.fullmatch(r"\d+", _clean(_visible_text(paragraph))) and not has_page_field(paragraph)
                ]
                if plain_digits:
                    reporter.error("pagenum.body.location", f"`{target}` Text Box 83 still has plain page number text: {plain_digits}")
                else:
                    reporter.pass_("pagenum.body.textbox83", f"`{target}` Text Box 83 is present and contains no stale typed number")
                if len(live_paragraphs) == 1:
                    reporter.pass_("pagenum.body.location", f"`{target}` PAGE field is a live framed header paragraph over the Page cell")
                else:
                    reporter.error(
                        "pagenum.body.location",
                        f"`{target}` must contain exactly one live framed PAGE paragraph; found {len(live_paragraphs)}",
                    )
                if live_paragraphs and all(_has_standard_page_field(paragraph) for paragraph in live_paragraphs):
                    reporter.pass_("pagenum.body.standardField", f"`{target}` live PAGE field uses standard begin/instr/separate/display/end OOXML")
                else:
                    reporter.error("pagenum.body.standardField", f"`{target}` live PAGE field is not a standard Word field sequence")
                if live_paragraphs:
                    actual_frame = _frame_pr_signature(live_paragraphs[0])
                    expected_frame = _expected_live_page_frame_signature()
                    mismatches = [
                        f"{key}: actual={actual_frame.get(key)} expected={value}"
                        for key, value in expected_frame.items()
                        if actual_frame.get(key) != value
                    ]
                    if mismatches:
                        reporter.error("pagenum.body.framePr", f"`{target}` live PAGE framePr is not calibrated to Text Box 83: " + "; ".join(mismatches))
                    else:
                        reporter.pass_("pagenum.body.framePr", f"`{target}` live PAGE framePr is calibrated to the Text Box 83 Page cell")
                    positions = _page_field_run_position_values(live_paragraphs[0])
                    expected_position = str(LIVE_PAGE_FIELD_RUN_POSITION_HALF_POINTS)
                    if positions and all(value in {expected_position, None} for value in positions):
                        reporter.pass_("pagenum.body.runPosition", f"`{target}` live PAGE runs are vertically centered in the Page cell")
                    else:
                        reporter.error(
                            "pagenum.body.runPosition",
                            f"`{target}` live PAGE runs must use w:position={expected_position} for vertical centering; found {positions}",
                        )
                if any(_has_highlight_or_shading(shape) for shape in textbox83) or any(
                    _has_highlight_or_shading(paragraph) for paragraph in live_paragraphs
                ):
                    reporter.error("pagenum.body.highlight", f"`{target}` page number must not have highlight or shading")
                else:
                    reporter.pass_("pagenum.body.highlight", f"`{target}` page number has no highlight or shading")
        elif has_page_field(part):
            reporter.error("pagenum.body.location", f"`{target}` contains a PAGE field outside the body header")
        else:
            reporter.pass_("pagenum.body.location", f"`{target}` has no visible page-number frame to validate")
    if body_xml:
        reporter.pass_("pagenum.body.refs", f"Body section has {len(body_xml)} independent header/footer part(s)")
    if total_fields == 1:
        reporter.pass_("pagenum.body.fieldCount", "Body header/footer has exactly one PAGE field")
    else:
        reporter.error("pagenum.body.fieldCount", f"Body header/footer has {total_fields} PAGE fields; expected exactly one")
    if total_live_fields == 1:
        reporter.pass_("pagenum.body.liveFieldCount", "Body header has exactly one live framed PAGE field")
    else:
        reporter.error("pagenum.body.liveFieldCount", f"Body header/footer has {total_live_fields} live framed PAGE fields; expected exactly one")


def _caption_after(paragraphs: list[etree._Element], index: int, prefix: str, window: int = 3) -> etree._Element | None:
    for candidate in paragraphs[index + 1 : index + 1 + window]:
        if _clean(text_of(candidate)).startswith(prefix):
            return candidate
    return None


def _caption_before(paragraphs: list[etree._Element], index: int, prefix: str, window: int = 3) -> etree._Element | None:
    start = max(0, index - window)
    for candidate in reversed(paragraphs[start:index]):
        if _clean(text_of(candidate)).startswith(prefix):
            return candidate
    return None


def _check_numbered_caption_sequence(
    captions: list[etree._Element],
    prefix: str,
    reporter: Reporter,
    code_prefix: str,
) -> set[str]:
    previous_by_chapter: dict[int, int] = {}
    seen: set[str] = set()
    numbers: set[str] = set()
    checked = 0
    for caption in captions:
        caption_text = _clean(text_of(caption))
        match = re.match(rf"^{prefix}\s+(\d+)\.(\d+)\s+\u2013\s+", caption_text)
        if not match:
            continue
        checked += 1
        chapter = int(match.group(1))
        sequence = int(match.group(2))
        number = f"{chapter}.{sequence}"
        label = f"{prefix} {number}"
        if number in seen:
            reporter.error(f"{code_prefix}.{checked}.unique", f"{label} is duplicated")
        else:
            reporter.pass_(f"{code_prefix}.{checked}.unique", f"{label} is unique")
        expected = previous_by_chapter.get(chapter, 0) + 1
        if sequence == expected:
            reporter.pass_(
                f"{code_prefix}.{checked}.sequence",
                f"{prefix} numbering is consecutive in chapter {chapter}: {label}",
            )
        else:
            reporter.error(
                f"{code_prefix}.{checked}.sequence",
                f"{prefix} numbering must be consecutive within chapter {chapter}; "
                f"expected {prefix} {chapter}.{expected}, found {label}",
            )
        previous_by_chapter[chapter] = sequence
        seen.add(number)
        numbers.add(number)
    if checked:
        reporter.pass_(f"{code_prefix}.exists", f"Checked {checked} {prefix.lower()} caption number(s)")
    else:
        reporter.warn(f"{code_prefix}.exists", f"No {prefix.lower()} captions were available for sequence checking")
    return numbers


def _check_numbered_references_exist(
    prefix: str,
    known_numbers: set[str],
    document_text: str,
    reporter: Reporter,
    code: str,
) -> None:
    mentioned_numbers = sorted(set(re.findall(rf"\b{prefix}\s+(\d+\.\d+)\b", document_text)))
    unknown_numbers = [number for number in mentioned_numbers if number not in known_numbers]
    if unknown_numbers:
        reporter.error(
            code,
            f"{prefix} reference(s) point to missing caption number(s): " + ", ".join(unknown_numbers),
        )
    else:
        reporter.pass_(code, f"All {prefix.lower()} references point to existing caption numbers")


def check_figures(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    paragraphs = _body_section_paragraphs(root)
    image_paragraphs = [
        (idx, p)
        for idx, p in enumerate(paragraphs)
        if p.xpath(".//a:blip", namespaces=NS) and not _is_template_paragraph(p)
    ]
    if not image_paragraphs:
        reporter.warn("figure.exists", "No embedded figure image found")
    page_text_width_emu = (RULES["page_width_mm"] - RULES["left_margin_mm"] - RULES["right_margin_mm"]) * EMU_PER_MM
    captions = []
    code_figure_numbers = {"3.5", "3.6", "4.3", "4.4", "5.2", "5.3", "5.4"}
    for idx, paragraph in image_paragraphs:
        caption = _caption_after(paragraphs, idx, "Figure")
        if caption is None:
            reporter.error("figure.caption.nearby", "Embedded image has no nearby Figure caption")
            continue
        captions.append(caption)
        cap_text = _clean(text_of(caption))
        figure_number = re.search(r"Figure\s+(\d+(?:\.\d+)?)", cap_text)
        if re.match(RULES["figure_caption_re"], cap_text):
            reporter.pass_("figure.caption.format", f"Figure caption format is valid: {cap_text}")
        else:
            reporter.error("figure.caption.format", f"Invalid Figure caption format: {cap_text}")
        if _effective_alignment(caption, styles) == "center":
            reporter.pass_("figure.caption.align", "Figure caption is centered")
        else:
            reporter.error("figure.caption.align", f"Figure caption must be centered: {cap_text}")
        previous_paragraph = paragraphs[idx - 1] if idx > 0 else None
        second_previous = paragraphs[idx - 2] if idx > 1 else None
        if _is_float_spacing_paragraph(previous_paragraph, styles) and not _is_empty_body_paragraph(second_previous):
            reporter.pass_("figure.spacing.before", f"One blank line before {figure_number.group(0) if figure_number else 'figure'}")
        elif _is_empty_body_paragraph(previous_paragraph):
            reporter.error(
                "figure.spacing.before",
                f"Figure block must have one visible 13 pt blank line before it: {cap_text}",
            )
        else:
            reporter.error("figure.spacing.before", f"Figure block must have a blank line before it: {cap_text}")
        caption_index = paragraphs.index(caption)
        following_paragraph = paragraphs[caption_index + 1] if caption_index + 1 < len(paragraphs) else None
        second_following = paragraphs[caption_index + 2] if caption_index + 2 < len(paragraphs) else None
        if _is_float_spacing_paragraph(following_paragraph, styles) and not _is_empty_body_paragraph(second_following):
            reporter.pass_("figure.spacing.after", f"One blank line after {figure_number.group(0) if figure_number else 'figure'} caption")
        elif _is_empty_body_paragraph(following_paragraph):
            reporter.error(
                "figure.spacing.after",
                f"Figure caption must be followed by one visible 13 pt blank line before body text: {cap_text}",
            )
        else:
            reporter.error("figure.spacing.after", f"Figure caption must be followed by a blank line before body text: {cap_text}")
        for extent in paragraph.xpath(".//wp:extent", namespaces=NS):
            cx = int(extent.get("cx", "0"))
            if cx <= page_text_width_emu:
                reporter.pass_("figure.width", f"Figure width {cx / EMU_PER_MM:.1f} mm fits text area")
            else:
                reporter.error("figure.width", f"Figure width {cx / EMU_PER_MM:.1f} mm exceeds text area")
            if figure_number and figure_number.group(1) in code_figure_numbers:
                width_mm = cx / EMU_PER_MM
                expected_mm = page_text_width_emu / EMU_PER_MM
                if abs(width_mm - expected_mm) <= 0.2:
                    reporter.pass_(
                        "figure.code.widthExact",
                        f"Code fragment {figure_number.group(0)} width matches body text width: {width_mm:.1f} mm",
                    )
                else:
                    reporter.error(
                        "figure.code.widthExact",
                        f"Code fragment {figure_number.group(0)} width must match body text width "
                        f"{expected_mm:.1f} mm, found {width_mm:.1f} mm",
                    )
    document_text = _clean(text_of(root))
    figure_numbers = _check_numbered_caption_sequence(captions, "Figure", reporter, "figure.numbering")
    _check_numbered_references_exist("Figure", figure_numbers, document_text, reporter, "figure.referenceNumber")
    for caption in captions:
        cap_text = _clean(text_of(caption))
        number = re.search(r"Figure\s+(\d+(?:\.\d+)?)", cap_text)
        if not number:
            continue
        references = re.findall(rf"Figure\s+{re.escape(number.group(1))}\b", document_text)
        if len(references) >= 2:
            reporter.pass_("figure.reference", f"Figure {number.group(1)} is referenced in body text")
        else:
            reporter.error("figure.reference", f"Figure {number.group(1)} caption exists but no body reference was found")


def check_tables(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    children = _body_section_children(root)
    if not children:
        reporter.error("table.body", "Body section not found")
        return
    tables = [(idx, child_el) for idx, child_el in enumerate(children) if child_el.tag == qn("w:tbl")]
    if not tables:
        reporter.warn("table.exists", "No Word table found")
        return
    paragraphs = [child_el for child_el in children if child_el.tag == qn("w:p")]
    continuation_paragraphs = [
        _clean(text_of(paragraph))
        for paragraph in paragraphs
        if _clean(text_of(paragraph)).startswith("Continue of the Table")
    ]
    malformed_continuations = [
        text for text in continuation_paragraphs if not re.fullmatch(r"Continue of the Table \d+\.\d+", text)
    ]
    if malformed_continuations:
        reporter.error(
            "table.continuation.format",
            "Continuation labels must be written as `Continue of the Table xx.xx`: "
            + " | ".join(malformed_continuations[:3]),
        )
    elif continuation_paragraphs:
        reporter.pass_("table.continuation.format", "Table continuation labels use the required wording")
    else:
        reporter.pass_("table.continuation.format", "No manual table continuation labels are present")
    if continuation_paragraphs:
        reporter.pass_("table.continuation.required", "Manual continuation labels are present where the document generator split tables")
    else:
        reporter.pass_("table.continuation.required", "No manual table continuation labels are required by the document structure")
    table_caption_paragraphs = [
        paragraph for paragraph in paragraphs if re.match(RULES["table_caption_re"], _clean(text_of(paragraph)))
    ]
    document_text = _clean(text_of(root))
    table_numbers = _check_numbered_caption_sequence(table_caption_paragraphs, "Table", reporter, "table.numbering")
    _check_numbered_references_exist("Table", table_numbers, document_text, reporter, "table.referenceNumber")
    for table_index, table in tables:
        previous_paragraphs = [child_el for child_el in children[:table_index] if child_el.tag == qn("w:p")]
        caption = previous_paragraphs[-1] if previous_paragraphs else None
        cap_text = _clean(text_of(caption)) if caption is not None else ""
        continuation_text = ""
        if cap_text.startswith("Continue of the Table"):
            continuation_text = cap_text
            earlier_table_captions = [
                _clean(text_of(child_el))
                for child_el in previous_paragraphs[:-1]
                if _clean(text_of(child_el)).startswith("Table")
            ]
            cap_text = earlier_table_captions[-1] if earlier_table_captions else ""
            if cap_text:
                reporter.pass_("table.caption.position", f"Continued table follows {continuation_text}")
            else:
                reporter.error("table.caption.position", f"Continuation label has no preceding Table caption: {continuation_text}")
                continue
        elif cap_text.startswith("Table"):
            reporter.pass_("table.caption.position", f"Table caption is above table: {cap_text}")
        else:
            reporter.error("table.caption.position", "Each table must have a Table caption immediately above it")
            continue
        if re.match(RULES["table_caption_re"], cap_text):
            reporter.pass_("table.caption.format", f"Table caption format is valid: {cap_text}")
        else:
            reporter.error("table.caption.format", f"Invalid Table caption format: {cap_text}")
        if _effective_alignment(caption, styles) in {None, "left"}:
            reporter.pass_("table.caption.align", "Table caption starts at left/table boundary")
        else:
            reporter.error("table.caption.align", f"Table caption must be left aligned: {cap_text}")
        try:
            caption_index = children.index(caption)
        except ValueError:
            caption_index = -1
        if continuation_text:
            page_break_paragraph = children[table_index - 2] if table_index >= 2 else None
            if _paragraph_has_page_break(page_break_paragraph) or _has_page_break_before(caption, styles):
                reporter.pass_("table.continuation.pageBreak", f"{continuation_text} starts on a new page")
            else:
                reporter.error("table.continuation.pageBreak", f"{continuation_text} must start on a new page")
        before_caption = children[caption_index - 1] if caption_index > 0 else None
        second_before_caption = children[caption_index - 2] if caption_index > 1 else None
        if continuation_text:
            reporter.pass_("table.spacing.before", f"{continuation_text} is placed directly above the continued table")
        elif _paragraph_has_page_break(before_caption):
            reporter.pass_("table.spacing.before", f"{cap_text} starts at the top of a new page")
        elif _is_float_spacing_paragraph(before_caption, styles) and not _is_empty_body_paragraph(second_before_caption):
            reporter.pass_("table.spacing.before", f"One blank line before {cap_text}")
        elif _is_empty_body_paragraph(before_caption):
            reporter.error(
                "table.spacing.before",
                f"Table caption must have one visible 13 pt blank line before it: {cap_text}",
            )
        else:
            reporter.error("table.spacing.before", f"Table caption must have a blank line before it: {cap_text}")
        after_table = children[table_index + 1] if table_index + 1 < len(children) else None
        second_after_table = children[table_index + 2] if table_index + 2 < len(children) else None
        after_table_text = _clean(text_of(after_table)) if after_table is not None and after_table.tag == qn("w:p") else ""
        if after_table_text.startswith("Continue of the Table") and _has_page_break_before(after_table, styles):
            reporter.pass_("table.spacing.after", f"{cap_text} continues on the next page")
        elif _paragraph_has_page_break(after_table):
            reporter.pass_("table.spacing.after", f"{cap_text} continues on the next page")
        elif _is_float_spacing_paragraph(after_table, styles) and not _is_empty_body_paragraph(second_after_table):
            reporter.pass_("table.spacing.after", f"One blank line after {cap_text}")
        elif _is_empty_body_paragraph(after_table):
            reporter.error(
                "table.spacing.after",
                f"Table must be followed by one visible 13 pt blank line before body text: {cap_text}",
            )
        else:
            reporter.error("table.spacing.after", f"Table must be followed by a blank line before body text: {cap_text}")
        blank_cells = []
        for cell in table.xpath(".//w:tc", namespaces=NS):
            if not _clean(text_of(cell)):
                blank_cells.append(cell)
        if blank_cells:
            reporter.warn("table.blankcells", f"Table contains {len(blank_cells)} blank cell(s); use a dash for missing data")
        else:
            reporter.pass_("table.blankcells", "Table has no blank cells")
        split_rows = [
            row_index
            for row_index, row in enumerate(table.xpath("./w:tr", namespaces=NS), start=1)
            if row.find("./w:trPr/w:cantSplit", namespaces=NS) is None
        ]
        if split_rows:
            reporter.error(
                "table.rowSplit",
                "Table rows must not split across pages; missing w:cantSplit on row(s): "
                + ", ".join(str(row) for row in split_rows[:10]),
            )
        else:
            reporter.pass_("table.rowSplit", "Table rows are protected from splitting across pages")
        header_row = table.find("./w:tr", namespaces=NS)
        if header_row is not None and header_row.find("./w:trPr/w:tblHeader", namespaces=NS) is not None:
            reporter.pass_("table.headerRepeat", "Table header row is marked to repeat after a page break")
        else:
            reporter.warn("table.headerRepeat", "Table header row should be marked for repetition if the table continues on the next page")
        row_count = len(table.xpath("./w:tr", namespaces=NS))
        number = re.search(r"Table\s+(\d+(?:\.\d+)?)", cap_text)
        if row_count > 9 and number and f"Continue of the Table {number.group(1)}" not in continuation_paragraphs:
            reporter.warn(
                "table.continuation.marker",
                f"Table {number.group(1)} has {row_count} rows; if Word splits it across pages, "
                f"the continued page must start with `Continue of the Table {number.group(1)}`.",
            )
        elif row_count > 9 and number:
            reporter.pass_("table.continuation.marker", f"Continuation wording is present for long Table {number.group(1)}")
        tbl_w = table.find("w:tblPr/w:tblW", namespaces=NS)
        if tbl_w is not None and tbl_w.get(qn("w:type")) == "dxa" and tbl_w.get(qn("w:w")):
            width_mm = twips_to_mm(tbl_w.get(qn("w:w")))
            max_width = RULES["page_width_mm"] - RULES["left_margin_mm"] - RULES["right_margin_mm"]
            if _approx(width_mm, max_width, 1.0):
                reporter.pass_("table.width", f"Table width {width_mm:.1f} mm matches text area {max_width:.1f} mm")
            elif width_mm <= max_width + 1:
                reporter.warn("table.width", f"Table width {width_mm:.1f} mm fits but does not match text area {max_width:.1f} mm")
            else:
                reporter.error("table.width", f"Table width {width_mm:.1f} mm exceeds text area {max_width:.1f} mm")
        else:
            reporter.warn("table.width", "Table width is not explicit in OOXML; manually confirm it fits text width")
        if number:
            references = re.findall(rf"Table\s+{re.escape(number.group(1))}\b", document_text)
            if len(references) >= 2:
                reporter.pass_("table.reference", f"Table {number.group(1)} is referenced in body text")
            else:
                reporter.error("table.reference", f"Table {number.group(1)} caption exists but no body reference was found")


def check_formulas(
    root: etree._Element,
    styles: dict[str, etree._Element],
    reporter: Reporter,
    *,
    require_formula: bool = True,
) -> None:
    body_paragraphs = _body_section_paragraphs(root)
    formula_paragraphs = [
        p
        for p in body_paragraphs
        if re.search(RULES["formula_number_re"], _clean(text_of(p))) and _is_paragraph_style(p, styles, "Formula")
    ]
    omml_count = len(root.xpath("//m:oMath|//m:oMathPara", namespaces=NS))
    if not formula_paragraphs:
        if omml_count:
            reporter.error("formula.exists", "OMML math exists, but no numbered Formula paragraph like (1.1) was found")
        elif not require_formula:
            reporter.warn("formula.exists", "No formula found yet; acceptable for a partial chapter draft, but required for the complete thesis")
        else:
            reporter.error("formula.exists", "No formula number like (1.1) and no OMML formula was found")
        return
    if omml_count:
        reporter.pass_("formula.omml.exists", f"Document contains {omml_count} OMML math object(s)")
    else:
        reporter.error("formula.omml.exists", "Document contains no m:oMath or m:oMathPara objects")
    previous_formula_seq_by_chapter: dict[int, int] = {}
    formula_numbers: set[str] = set()
    for idx, paragraph in enumerate(formula_paragraphs, start=1):
        text = _clean(text_of(paragraph))
        formula_number = re.search(r"\((\d+)\.(\d+)\)", text)
        if paragraph.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS):
            reporter.pass_(f"formula.{idx}.omml", f"Formula paragraph contains a Word OMML math object: {text}")
        else:
            reporter.error(f"formula.{idx}.omml", f"Formula paragraph must contain m:oMath or m:oMathPara, not plain text: {text}")
        if "_" in text or "^" in text:
            reporter.error(
                f"formula.{idx}.mathNotation",
                f"Formula must use real math subscript/superscript structures, not code-style `_` or `^`: {text}",
            )
        else:
            reporter.pass_(f"formula.{idx}.mathNotation", "Formula uses rendered math notation without code-style `_` or `^`")
        has_right_tab = any(
            tab.get(qn("w:val")) == "right"
            for tab in paragraph.xpath(".//w:tabs/w:tab", namespaces=NS)
        )
        has_center_tab = any(
            tab.get(qn("w:val")) == "center"
            for tab in paragraph.xpath(".//w:tabs/w:tab", namespaces=NS)
        )
        if has_center_tab and has_right_tab:
            reporter.pass_(f"formula.{idx}.tabs", f"Formula has center and right tab stops: {text}")
        else:
            reporter.error(
                f"formula.{idx}.tabs",
                f"Formula must have center and right tab stops; center={has_center_tab}, right={has_right_tab}: {text}",
            )
        if has_right_tab and re.search(RULES["formula_number_re"], text):
            reporter.pass_(f"formula.{idx}.numberalign", f"Formula number appears aligned by a right tab: {text}")
        else:
            reporter.error(f"formula.{idx}.numberalign", f"Formula number must be aligned by a right tab: {text}")
        if _effective_alignment(paragraph, styles) in {None, "left"}:
            reporter.pass_(f"formula.{idx}.align", "Formula paragraph uses left paragraph alignment with center/right tab stops")
        else:
            reporter.error(f"formula.{idx}.align", f"Formula paragraph must use tab-stop alignment, not paragraph centering: {text}")
        before = _effective_space_before_pt(paragraph, styles)
        after = _effective_space_after_pt(paragraph, styles)
        if before is not None and before >= 12 and after is not None and after >= 12:
            reporter.pass_(f"formula.{idx}.spacing", f"Formula is separated from text by one-line spacing: before={before:g} pt, after={after:g} pt")
        else:
            reporter.error(
                f"formula.{idx}.spacing",
                f"Rules require formulas on separate lines separated from text by spaces; found before={before}, after={after}: {text}",
            )
        if formula_number:
            chapter = int(formula_number.group(1))
            seq = int(formula_number.group(2))
            formula_numbers.add(f"{chapter}.{seq}")
            expected = previous_formula_seq_by_chapter.get(chapter, 0) + 1
            if seq == expected:
                reporter.pass_(f"formula.{idx}.sequence", f"Formula numbering is consecutive in chapter {chapter}: ({chapter}.{seq})")
            else:
                reporter.error(
                    f"formula.{idx}.sequence",
                    f"Formula numbering must be consecutive within chapter {chapter}; expected ({chapter}.{expected}), found ({chapter}.{seq})",
                )
            previous_formula_seq_by_chapter[chapter] = seq
        try:
            paragraph_index = body_paragraphs.index(paragraph)
        except ValueError:
            paragraph_index = -1
        if paragraph_index >= 0 and paragraph_index + 1 < len(body_paragraphs):
            following = body_paragraphs[paragraph_index + 1]
            following_text = _clean(text_of(following))
            if following_text.startswith("where "):
                reporter.pass_(f"formula.{idx}.where", f"Formula is followed by a where explanation: {text}")
                if _has_formula_trailing_comma(paragraph):
                    reporter.pass_(f"formula.{idx}.commaBeforeWhere", "Formula line followed by `where` ends with a comma outside the OMML formula")
                else:
                    reporter.error(f"formula.{idx}.commaBeforeWhere", f"Formula followed by `where` must end with a comma outside the OMML formula: {text}")
                if _has_formula_comma_inside_math(paragraph):
                    reporter.error(f"formula.{idx}.commaOutsideOmml", f"Formula punctuation must not be inside the OMML math object: {text}")
                else:
                    reporter.pass_(f"formula.{idx}.commaOutsideOmml", "Formula comma is stored as ordinary text outside the OMML math object")
                first_indent = _effective_first_line_indent_mm(following, styles)
                if first_indent is None or abs(first_indent) < 0.2:
                    reporter.pass_(f"formula.{idx}.whereIndent", "`where` explanation has no paragraph indent")
                else:
                    reporter.error(f"formula.{idx}.whereIndent", f"`where` explanation must have no paragraph indent; found {first_indent:.1f} mm")
            else:
                reporter.error(f"formula.{idx}.where", f"Formula must be followed by `where` symbol explanations: {text}")
        else:
            reporter.error(f"formula.{idx}.where", f"Formula must be followed by `where` symbol explanations: {text}")

    formula_indices = {id(p): i for i, p in enumerate(body_paragraphs)}
    for idx, paragraph in enumerate(formula_paragraphs, start=1):
        paragraph_index = formula_indices.get(id(paragraph), -1)
        explanation_items: list[tuple[etree._Element, str]] = []
        if paragraph_index >= 0:
            for following in body_paragraphs[paragraph_index + 1 :]:
                following_text = _clean(text_of(following))
                if not following_text:
                    continue
                if following_text.startswith("where ") or re.match(rf"^{FORMULA_SYMBOL_RE}\s+\u2013\s+", following_text):
                    explanation_items.append((following, following_text))
                    continue
                break
        if explanation_items:
            explanation_lines = [line for _, line in explanation_items]
            bad_middle = [line for line in explanation_lines[:-1] if not line.endswith(";")]
            bad_last = explanation_lines[-1] if not explanation_lines[-1].endswith(".") else ""
            if bad_middle or bad_last:
                details = bad_middle[:2]
                if bad_last:
                    details.append(bad_last)
                reporter.error(
                    f"formula.{idx}.wherePunctuation",
                    "Formula symbol explanations must use semicolons for intermediate lines and an English full stop on the last line: "
                    + " | ".join(details),
                )
            else:
                reporter.pass_(f"formula.{idx}.wherePunctuation", "Formula symbol explanations use semicolons and final full stop")
            malformed = [
                line
                for line in explanation_lines
                if not re.match(rf"^(?:where\s+)?{FORMULA_SYMBOL_RE}\s+\u2013\s+.+[.;]$", line)
            ]
            if malformed:
                reporter.error(
                    f"formula.{idx}.whereDash",
                    "Formula explanations must use `symbol – explanation;` without a colon: " + " | ".join(malformed[:3]),
                )
            else:
                reporter.pass_(f"formula.{idx}.whereDash", "Formula explanations use dash form without a colon")
            if any(line.startswith("where:") or line.startswith("where :") for line in explanation_lines):
                reporter.error(f"formula.{idx}.whereColon", "`where` must not be followed by a colon")
            else:
                reporter.pass_(f"formula.{idx}.whereColon", "`where` has no colon")
            alignment_errors: list[str] = []
            for item_index, (expl_paragraph, line) in enumerate(explanation_items):
                first_where_line = item_index == 0
                if not _has_formula_symbol_tab(expl_paragraph):
                    alignment_errors.append(f"missing {FORMULA_SYMBOL_TAB_MM:g} mm symbol tab: {line}")
                if not _has_literal_tab_before_symbol(expl_paragraph, first_where_line=first_where_line):
                    alignment_errors.append(f"symbol is not placed after the alignment tab: {line}")
            if alignment_errors:
                reporter.error(
                    f"formula.{idx}.whereSymbolAlign",
                    "Formula symbol explanations must be aligned by symbols: " + " | ".join(alignment_errors[:3]),
                )
            else:
                reporter.pass_(f"formula.{idx}.whereSymbolAlign", "Formula explanations are aligned by symbol tab stops")
    document_text = _clean(text_of(root))
    referenced_formula_numbers = sorted(
        set(
            re.findall(
                r"\b(?:formula|equation|expression|equality|transfer function)\s+\((\d+\.\d+)\)",
                document_text,
                flags=re.I,
            )
        )
    )
    unknown_formula_numbers = [number for number in referenced_formula_numbers if number not in formula_numbers]
    if unknown_formula_numbers:
        reporter.error(
            "formula.referenceNumber",
            "Formula reference(s) point to missing formula number(s): " + ", ".join(unknown_formula_numbers),
        )
    else:
        reporter.pass_("formula.referenceNumber", "All formula references point to existing formula numbers")
    for number in sorted(set(re.findall(RULES["formula_number_re"], document_text))):
        refs = re.findall(rf"\b(?:formula|equation|expression|equality|transfer function)\s+{re.escape(number)}", document_text, flags=re.I)
        if refs:
            reporter.pass_("formula.reference", f"{number} is referenced with formula/equation/expression wording")
        else:
            reporter.warn("formula.reference", f"{number} appears without a clear formula/equation/expression reference")


def check_rules_text_presentation(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    body_paragraphs = [
        paragraph
        for paragraph in _body_section_paragraphs(root)
        if not _is_template_paragraph(paragraph) and _clean(text_of(paragraph))
        and not re.match(r"^\[\d+\]\s+\S", _clean(text_of(paragraph)))
    ]
    text = "\n".join(_clean(text_of(paragraph)) for paragraph in body_paragraphs)
    backtick_fragments = [value[:120] for value in (_clean(text_of(p)) for p in body_paragraphs) if "`" in value]
    if backtick_fragments:
        reporter.error(
            "rules.text.backticks",
            "Thesis body text must not contain Markdown/code backticks: " + " | ".join(backtick_fragments[:5]),
        )
    else:
        reporter.pass_("rules.text.backticks", "Body text contains no Markdown/code backticks")

    code_like_fragments = []
    code_line_re = re.compile(
        r"^\s*(?:"
        r"(?:const|auto|bool|float|double|int|String|return|if|else|for|while|class|def|async|await|public|private)\b"
        r"|#include\b|//|/\*|\*/|[{}]"
        r"|[A-Za-z_][A-Za-z0-9_]*\s*=\s*[^=]"
        r"|[A-Za-z_][A-Za-z0-9_]*\([^)]*\)\s*;?$"
        r")"
    )
    for paragraph in body_paragraphs:
        if paragraph.xpath(".//a:blip|.//m:oMath|.//m:oMathPara", namespaces=NS):
            continue
        if _is_paragraph_style(paragraph, styles, "Figure Caption") or _is_paragraph_style(paragraph, styles, "Table Caption"):
            continue
        value = _clean(text_of(paragraph))
        if code_line_re.search(value) and not re.search(r"\b(?:Figure|formula|Table|Chapter|Section)\b", value):
            code_like_fragments.append(value[:120])
    if code_like_fragments:
        reporter.error(
            "rules.text.inlineCodeBlocks",
            "Source code must be inserted as referenced Figure images, not as body text code blocks: "
            + " | ".join(code_like_fragments[:5]),
        )
    else:
        reporter.pass_("rules.text.inlineCodeBlocks", "No source-code blocks are present as thesis body text")

    formula_numbers = set(re.findall(RULES["formula_number_re"], text))
    unclear_formula_refs = []
    for number in formula_numbers:
        if not re.search(rf"\b(?:formula|equation|expression|equality|transfer function)\s+{re.escape(number)}", text, flags=re.I):
            unclear_formula_refs.append(number)
    if unclear_formula_refs:
        reporter.warn(
            "rules.text.formulaRefs",
            "Rules require wording such as formula/equation/expression before formula references; review: "
            + ", ".join(sorted(unclear_formula_refs)),
        )
    elif formula_numbers:
        reporter.pass_("rules.text.formulaRefs", "Formula references use explicit formula/equation/expression wording")
    else:
        reporter.warn("rules.text.formulaRefs", "No formula references were found")

    breakable_float_refs = []
    breakable_formula_refs = []
    for paragraph in body_paragraphs:
        if (
            _is_paragraph_style(paragraph, styles, "Heading 1")
            or _is_paragraph_style(paragraph, styles, "Heading 2")
            or _is_paragraph_style(paragraph, styles, "Contents Entry")
            or _is_paragraph_style(paragraph, styles, "Contents Title")
            or _is_paragraph_style(paragraph, styles, "Figure Caption")
            or _is_paragraph_style(paragraph, styles, "Table Caption")
        ):
            continue
        raw_value = text_of(paragraph)
        if re.search(r"\b(?:Figure|Table) \d+\.\d+\b", raw_value):
            breakable_float_refs.append(_clean(raw_value)[:120])
        if re.search(rf"\b(?:formula|equation|expression|equality|transfer function) \(\d+\.\d+\)", raw_value, flags=re.I):
            breakable_formula_refs.append(_clean(raw_value)[:120])
    if breakable_float_refs:
        reporter.error(
            "rules.text.floatReferenceNoBreak",
            "Figure/Table references must use a nonbreaking space so the number stays on the same line: "
            + " | ".join(breakable_float_refs[:5]),
        )
    else:
        reporter.pass_("rules.text.floatReferenceNoBreak", "Figure/Table references use nonbreaking spaces in running text")
    if breakable_formula_refs:
        reporter.error(
            "rules.text.formulaReferenceNoBreak",
            "Formula references must use a nonbreaking space so the number stays on the same line: "
            + " | ".join(breakable_formula_refs[:5]),
        )
    else:
        reporter.pass_("rules.text.formulaReferenceNoBreak", "Formula references use nonbreaking spaces in running text")

    comparison_signs = []
    for paragraph in body_paragraphs:
        if paragraph.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS):
            continue
        value = _clean(text_of(paragraph))
        if re.search(r"(?<!\d)\s[<>=]\s(?!\d)", value):
            comparison_signs.append(value[:120])
    if comparison_signs:
        reporter.warn(
            "rules.text.signs",
            "Rules restrict mathematical signs in running text without numerical values; manually review: "
            + " | ".join(comparison_signs[:5]),
        )
    else:
        reporter.pass_("rules.text.signs", "No obvious standalone mathematical signs were found in running text")

    suspicious_short_numbers = []
    for paragraph in body_paragraphs:
        value = _clean(text_of(paragraph))
        if (
            _is_paragraph_style(paragraph, styles, "Heading 1")
            or _is_paragraph_style(paragraph, styles, "Heading 2")
            or _is_paragraph_style(paragraph, styles, "Contents Entry")
            or _is_paragraph_style(paragraph, styles, "Contents Title")
            or _is_paragraph_style(paragraph, styles, "Formula")
            or paragraph.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS)
        ):
            continue
        if re.match(RULES["table_caption_re"], value) or re.search(r"\b(?:Table|Figure)\s+\d+\.\d+\b", value):
            continue
        for match in re.finditer(r"(?<![\w.(\[])\b[1-9]\b(?![\w.)\]]|\s*(?:mm|pt|s|ms|V|A|W|K|J|kg|°C|%))", value):
            if re.search(r"\b(?:Chapter|Section)\s+$", value[max(0, match.start() - 16) : match.start()]):
                continue
            suspicious_short_numbers.append(value[:120])
            break
    if suspicious_short_numbers:
        reporter.warn(
            "rules.text.shortNumbers",
            "Rules say numbers one to nine without units should be written in words; manually review: "
            + " | ".join(suspicious_short_numbers[:5]),
        )
    else:
        reporter.pass_("rules.text.shortNumbers", "No obvious one-digit unitless numerals were found in running text")


def check_chapter_rules(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    chapters = _chapter_ranges(root, styles)
    if not chapters:
        reporter.error("chapter.exists", "No numbered thesis chapters were found")
        return
    numbers = [number for number, _, _ in chapters]
    expected_numbers = list(range(1, len(numbers) + 1))
    if numbers == expected_numbers:
        reporter.pass_("chapter.sequence", f"Chapter numbers are consecutive: {numbers}")
    else:
        reporter.error("chapter.sequence", f"Chapter numbers must be consecutive from 1; found {numbers}")

    for number, title, items in chapters:
        h1 = items[0] if items and items[0].tag == qn("w:p") else None
        code_prefix = f"chapter.{number}"
        if h1 is not None and _has_page_break_before(h1, styles):
            reporter.pass_(f"{code_prefix}.pageBreak", f"{title} starts on a new page")
        else:
            reporter.error(f"{code_prefix}.pageBreak", f"{title} must start on a new page")

        content_items = [item for item in items[1:] if _body_item_kind(item, styles) not in {"empty", "other"}]
        first_content = content_items[0] if content_items else None
        if first_content is not None and _body_item_kind(first_content, styles) == "heading2":
            reporter.pass_(f"{code_prefix}.firstContent", f"{title} begins with a subsection heading")
        else:
            reporter.warn(f"{code_prefix}.firstContent", f"{title} should begin with a subsection heading")

        subsections = [
            (_subsection_numbers_from_heading(_clean(text_of(item))), _clean(text_of(item)))
            for item in items
            if item.tag == qn("w:p") and _is_paragraph_style(item, styles, "Heading 2")
        ]
        wrong_subsections = [text for pair, text in subsections if pair is None or pair[0] != number]
        if wrong_subsections:
            reporter.error(
                f"{code_prefix}.subsectionOwnership",
                f"Subsection number must belong to chapter {number}: " + "; ".join(wrong_subsections[:8]),
            )
        elif subsections:
            reporter.pass_(f"{code_prefix}.subsectionOwnership", f"All subsection numbers belong to chapter {number}")
        else:
            reporter.warn(f"{code_prefix}.subsectionOwnership", f"{title} has no subsection headings")

        subsection_ordinals = [pair[1] for pair, _ in subsections if pair is not None and pair[0] == number]
        if subsection_ordinals:
            expected_subsections = list(range(1, len(subsection_ordinals) + 1))
            if subsection_ordinals == expected_subsections:
                reporter.pass_(f"{code_prefix}.subsectionSequence", f"Subsections are consecutive: {subsection_ordinals}")
            else:
                reporter.error(
                    f"{code_prefix}.subsectionSequence",
                    f"Subsection numbers must be consecutive in chapter {number}; found {subsection_ordinals}",
                )

        chapter_text_so_far = ""
        chapter_text = _clean(" ".join(text_of(item) for item in items))
        for item in items:
            kind = _body_item_kind(item, styles)
            text = _clean(text_of(item))
            if kind == "table_caption":
                match = re.search(r"Table\s+(\d+)\.(\d+)", text)
                if not match:
                    reporter.error(f"{code_prefix}.tableNumber", f"Table caption must use section numbering: {text}")
                elif int(match.group(1)) != number:
                    reporter.error(f"{code_prefix}.tableNumber", f"Table number must match chapter {number}: {text}")
                elif re.search(rf"Table\s+{re.escape(match.group(0).split()[1])}\b", chapter_text_so_far):
                    reporter.pass_(f"{code_prefix}.tablePreReference", f"{match.group(0)} is referenced before its caption")
                else:
                    reporter.error(f"{code_prefix}.tablePreReference", f"{match.group(0)} must be referenced in text before the table")
            elif kind == "figure_caption":
                match = re.search(r"Figure\s+(\d+)\.(\d+)", text)
                if not match:
                    reporter.error(f"{code_prefix}.figureNumber", f"Figure caption must use section numbering: {text}")
                elif int(match.group(1)) != number:
                    reporter.error(f"{code_prefix}.figureNumber", f"Figure number must match chapter {number}: {text}")
                elif re.search(rf"Figure\s+{re.escape(match.group(0).split()[1])}\b", chapter_text_so_far):
                    reporter.pass_(f"{code_prefix}.figurePreReference", f"{match.group(0)} is referenced before its caption")
                else:
                    reporter.error(f"{code_prefix}.figurePreReference", f"{match.group(0)} must be referenced in text before the figure")
            elif kind == "formula":
                for formula_number in re.findall(r"\((\d+)\.(\d+)\)", text):
                    if int(formula_number[0]) != number:
                        reporter.error(
                            f"{code_prefix}.formulaNumber",
                            f"Formula number must match chapter {number}: ({formula_number[0]}.{formula_number[1]})",
                        )
                    elif re.search(
                        rf"\b(?:formula|equation|expression|equality|transfer function)\s+\({formula_number[0]}\.{formula_number[1]}\)",
                        chapter_text_so_far,
                        flags=re.I,
                    ) or re.search(
                        rf"\b(?:formula|equation|expression|equality|transfer function)\s+\({formula_number[0]}\.{formula_number[1]}\)",
                        chapter_text,
                        flags=re.I,
                    ):
                        reporter.pass_(f"{code_prefix}.formulaReference", f"Formula ({formula_number[0]}.{formula_number[1]}) has an explicit reference")
                    else:
                        reporter.warn(
                            f"{code_prefix}.formulaReference",
                            f"Formula ({formula_number[0]}.{formula_number[1]}) should be referenced with formula/equation wording",
                        )
            if text and kind not in {"table_caption", "figure_caption"}:
                chapter_text_so_far = _clean(f"{chapter_text_so_far} {text}")

        last_meaningful = next(
            (item for item in reversed(items) if _body_item_kind(item, styles) not in {"empty", "other"}),
            None,
        )
        if last_meaningful is not None and _body_item_kind(last_meaningful, styles) in {"heading1", "heading2", "heading3", "table_caption", "figure_caption"}:
            reporter.error(f"{code_prefix}.ending", f"{title} ends with an orphan heading/caption")
        else:
            reporter.pass_(f"{code_prefix}.ending", f"{title} does not end with an orphan heading or caption")


def check_references(root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    children = _body_section_children(root)
    references_heading_index: int | None = None
    for idx, element in enumerate(children):
        if element.tag == qn("w:p") and _is_paragraph_style(element, styles, "Heading 1"):
            if _clean(text_of(element)) == "REFERENCES":
                references_heading_index = idx
                break
    if references_heading_index is None:
        reporter.error("references.exists", "REFERENCES section was not found")
        return
    heading = children[references_heading_index]
    if _has_page_break_before(heading, styles):
        reporter.pass_("references.pageBreak", "REFERENCES starts on a new page")
    else:
        reporter.error("references.pageBreak", "REFERENCES must start on a new page")

    reference_items: list[tuple[int, str, etree._Element]] = []
    body_text_parts: list[str] = []
    for idx, element in enumerate(children):
        if element.tag != qn("w:p") or _is_template_paragraph(element):
            continue
        text = _clean(text_of(element))
        if not text:
            continue
        if idx > references_heading_index:
            match = re.match(r"^\[(\d+)\]\s+(.+)", text)
            if match:
                reference_items.append((int(match.group(1)), text, element))
            elif _body_item_kind(element, styles) != "empty":
                reporter.error("references.entry.format", f"Unexpected paragraph in REFERENCES section: {text}")
        elif text != "Contents":
            body_text_parts.append(text)

    if not reference_items:
        reporter.error("references.entries", "REFERENCES section contains no numbered entries")
        return

    numbers = [number for number, _, _ in reference_items]
    expected = list(range(1, len(reference_items) + 1))
    if numbers == expected:
        reporter.pass_("references.sequence", f"Reference numbering is consecutive: {numbers}")
    else:
        reporter.error("references.sequence", f"Reference numbering must be consecutive from 1; found {numbers}")

    body_text = "\n".join(body_text_parts)
    cited_numbers = sorted({int(value) for value in re.findall(r"\[(\d+)\]", body_text)})
    reference_number_set = set(numbers)
    missing_entries = [number for number in cited_numbers if number not in reference_number_set]
    unused_entries = [number for number in numbers if number not in set(cited_numbers)]
    if missing_entries:
        reporter.error(
            "references.citedMissingEntry",
            "In-text citation(s) have no reference entry: " + ", ".join(f"[{n}]" for n in missing_entries),
        )
    else:
        reporter.pass_("references.citedMissingEntry", "Every in-text citation has a matching reference entry")
    if unused_entries:
        reporter.error(
            "references.entryNotCited",
            "Reference entrie(s) not cited in body text: " + ", ".join(f"[{n}]" for n in unused_entries),
        )
    else:
        reporter.pass_("references.entryNotCited", "Every reference entry is cited in body text")
    if cited_numbers:
        reporter.pass_("references.inText.exists", f"Body contains {len(cited_numbers)} distinct numbered citation(s)")
    else:
        reporter.error("references.inText.exists", "Body text contains no numbered citations like [1]")

    for number, text, paragraph in reference_items:
        first_indent = _effective_first_line_indent_mm(paragraph, styles)
        if first_indent is None or abs(first_indent) <= 0.2:
            reporter.pass_(f"references.{number}.indent", f"Reference [{number}] has no first-line indent")
        else:
            reporter.error(f"references.{number}.indent", f"Reference [{number}] must not use body first-line indent")
        if text.endswith("."):
            reporter.pass_(f"references.{number}.punctuation", f"Reference [{number}] ends with a period")
        else:
            reporter.error(f"references.{number}.punctuation", f"Reference [{number}] must end with a period: {text}")
        if len(text) >= 35:
            reporter.pass_(f"references.{number}.content", f"Reference [{number}] contains bibliographic details")
        else:
            reporter.error(f"references.{number}.content", f"Reference [{number}] is too short: {text}")


def check_templates(package: dict[str, bytes], root: etree._Element, reporter: Reporter) -> None:
    ranges = _section_ranges(root)
    sections = iter_section_properties(root)
    expected_cover_outer_frame = _contents_aligned_template1_outer_frame_signature(align_to_body_pixels=True)
    expected_body_outer_frame = _contents_aligned_body_outer_frame_signature()
    if ranges:
        cover_range = ranges[0]
        cover_text = _clean(" ".join(_visible_text(element) for element in cover_range))
        required_cover_text = [
            "Министерство образования Республики Беларусь",
            "Учреждение образования",
            "«Брестский государственный технический университет»",
            "Кафедра «ЭВМ и систем»",
            "К защите допускаю",
            "EdgeHub-Based Closed-Loop Temperature Control System",
            "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА К ДИПЛОМНОМУ ПРОЕКТУ",
            "БрГТУ.241297 - 05 81 00",
            f"Листов {BODY_TITLE_BLOCK_TOTAL_PAGES}",
            "V.S. Razumeichik",
            "Wang Gen",
            "2026",
        ]
        missing_cover_text = [key for key in required_cover_text if key not in cover_text]
        forbidden_cover_text = [
            key
            for key in [
                "Sign",
                "Date",
                "Page",
                "Author",
                "Computer&Systems",
                "BSTU.YOUR_NUMBER",
                "YOUR TASK",
                "Your name",
                "Luo Zhenkun",
                "Design of EdgeHub",
                "Design of the EdgeHub",
            ]
            if key in cover_text
        ]
        cover_tables = sum(
            (1 if element.tag == qn("w:tbl") else 0) + len(element.xpath(".//w:tbl", namespaces=NS))
            for element in cover_range
        )
        cover_drawings = sum(
            len(element.xpath(".//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS))
            for element in cover_range
        )
        cover_borders = sum(len(element.xpath(".//w:pgBorders", namespaces=NS)) for element in cover_range)
        if missing_cover_text:
            reporter.error("template.cover.requiredText", "Cover is missing required text: " + "; ".join(missing_cover_text))
        else:
            reporter.pass_("template.cover.requiredText", "Cover contains all required school, project, author, sheet-count, and year text")
        if forbidden_cover_text:
            reporter.error("template.cover.clean", f"Cover contains forbidden template text: {forbidden_cover_text}")
        elif cover_drawings:
            reporter.error("template.cover.clean", f"Cover contains {cover_drawings} body frame/drawing element(s)")
        elif cover_borders:
            reporter.error("template.cover.clean", "Cover uses w:pgBorders instead of the real template_1 outer frame")
        else:
            reporter.pass_("template.cover.clean", "Cover body has no forbidden template text or body-drawn frame")
        if cover_tables >= 1:
            reporter.pass_("template.cover.peopleTable", "Cover includes the required people/signature table")
        else:
            reporter.error("template.cover.peopleTable", "Cover must include the required people/signature table")

    if sections:
        cover_targets = section_ref_targets(package, sections[0])
        cover_header_parts = [
            parse_xml(package[target])
            for target in cover_targets
            if target in package and "/header" in target
        ]
        cover_footer_parts = [
            parse_xml(package[target])
            for target in cover_targets
            if target in package and "/footer" in target
        ]
        cover_part_text = _clean(" ".join(text_of(part) for part in cover_header_parts + cover_footer_parts))
        forbidden = [
            key
            for key in [
                "Sign",
                "Date",
                "Page",
                "Author",
                "Supervisor",
                "Computer&Systems",
                "BSTU",
                "YOUR_NUMBER",
            ]
            if key in cover_part_text
        ]
        if forbidden:
            reporter.error("template.cover.headerClean", f"Cover header/footer contains forbidden template text: {forbidden}")
        else:
            reporter.pass_("template.cover.headerClean", "Cover header/footer has no title-block text")
        if any(has_page_field(part) for part in cover_header_parts + cover_footer_parts):
            reporter.error("template.cover.pageField", "Cover header/footer must not contain a PAGE field")
        else:
            reporter.pass_("template.cover.pageField", "Cover header/footer contains no PAGE field")
        outer_frames = [
            shape
            for part in cover_header_parts
            for shape in part.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
            if _shape_name(shape) == "Rectangle 65"
        ]
        all_shapes = [
            shape
            for part in cover_header_parts
            for shape in part.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        ]
        if len(outer_frames) == 1 and len(all_shapes) == 1:
            reporter.pass_("template.cover.frame", "Cover header contains only template_1 Rectangle 65 outer frame")
        else:
            reporter.error(
                "template.cover.frame",
                f"Cover header must contain only Rectangle 65; Rectangle65={len(outer_frames)}, total shapes={len(all_shapes)}",
            )
        _check_outer_frame_geometry(
            reporter,
            "template.cover.frameGeometry",
            "Cover header",
            outer_frames,
            expected_cover_outer_frame,
        )
        stale_cover_fallbacks = _stale_template_fallback_texts(cover_header_parts)
        if stale_cover_fallbacks:
            reporter.error("template.cover.fallback", "Cover header contains stale template fallback text: " + "; ".join(stale_cover_fallbacks))
        else:
            reporter.pass_("template.cover.fallback", "Cover header has no stale mc:Fallback template text")

    text = _clean(text_of(root))
    placeholder_text = [
        key
        for key in [
            "BSTU.YOUR_NUMBER",
            "YOUR_NUMBER",
            "YOUR TASK",
            "Your name",
            "Your_name",
            "Designing a universal microcomputer",
            "Design of EdgeHub",
            "Design of the EdgeHub",
            "Luo Zhenkun",
            "Nikalayuk",
            "Rtsishchava",
        ]
        if key in text
    ]
    if placeholder_text:
        reporter.error("template.placeholders", f"Document still contains template placeholder text: {placeholder_text}")
    else:
        reporter.pass_("template.placeholders", "Document contains no stale template placeholder text")
    if all(key in text for key in ["Sign", "Date", "Supervisor", "Author"]):
        reporter.pass_("template.contents.frame", "Contents page includes template_0 frame key text")
    else:
        reporter.error("template.contents.frame", "Contents page does not show expected template_0 frame text")
    stale_fallbacks = _stale_template_fallback_texts([root])
    if stale_fallbacks:
        reporter.error("template.contents.fallback", "Contents page still contains stale template fallback text: " + "; ".join(stale_fallbacks))
    else:
        reporter.pass_("template.contents.fallback", "Contents page has no stale fallback template text")
    contents_page_values = _textbox_shapes_by_name(root, "Rectangle 34")
    contents_pages_values = _textbox_shapes_by_name(root, "Rectangle 6")
    if any(_shape_has_field(shape, "PAGE") for shape in contents_page_values):
        reporter.error("template.contents.pageStatic", "Contents Page cell must be a stable static 4, not a live PAGE field")
    else:
        reporter.pass_("template.contents.pageStatic", "Contents Page cell is not a live PAGE field")
    page_static_values = [
        _clean(_visible_text(shape))
        for shape in contents_page_values
        if _clean(_visible_text(shape))
    ]
    if page_static_values and all(value == "4" for value in page_static_values):
        reporter.pass_("template.contents.pageStaticValue", "Contents Page cell visibly contains static value 4")
    else:
        reporter.error(
            "template.contents.pageStaticValue",
            f"Contents Page cell must visibly contain static value 4, found: {page_static_values or ['<empty>']}",
        )
    if any(_shape_has_field(shape, "NUMPAGES") for shape in contents_pages_values):
        reporter.error("template.contents.pagesStatic", "Contents Pages cell must be static visible page-total value, not a live NUMPAGES field")
    else:
        reporter.pass_("template.contents.pagesStatic", "Contents Pages cell is a static visible page-total value")
    pages_static_values = [
        _clean(_visible_text(shape))
        for shape in contents_pages_values
        if _clean(_visible_text(shape))
    ]
    if pages_static_values and all(value == str(BODY_TITLE_BLOCK_TOTAL_PAGES) for value in pages_static_values):
        reporter.pass_(
            "template.contents.pagesStaticValue",
            f"Contents Pages cell visibly contains static value {BODY_TITLE_BLOCK_TOTAL_PAGES}",
        )
    else:
        reporter.error(
            "template.contents.pagesStaticValue",
            f"Contents Pages cell must visibly contain static value {BODY_TITLE_BLOCK_TOTAL_PAGES}, found: {pages_static_values or ['<empty>']}",
        )
    if any(_clean(_visible_text(shape)) == "46" for shape in contents_pages_values):
        reporter.error("template.contents.staticPages", "Contents Pages cell still contains the template placeholder value 46")
    else:
        reporter.pass_("template.contents.staticPages", "Contents Pages cell does not contain the template placeholder value 46")
    if any(_has_highlight_or_shading(shape) for shape in contents_page_values + contents_pages_values):
        reporter.error("template.contents.pageHighlight", "Contents Page/Pages values must not have yellow highlight or shading")
    else:
        reporter.pass_("template.contents.pageHighlight", "Contents Page/Pages values have no highlight or shading")
    if len(sections) >= 3:
        body_targets = section_ref_targets(package, sections[-1])
        body_header_parts = [
            parse_xml(package[target])
            for target in body_targets
            if target in package and "/header" in target
        ]
        body_text = " ".join(
            _clean(text_of(parse_xml(package[target]))) for target in body_targets if target in package
        )
        if all(key in body_text for key in ["Page", "Sign", "Date"]):
            reporter.pass_("template.body.frame", "Body section header/footer includes template_1 key text")
        else:
            reporter.error("template.body.frame", "Body section header/footer lacks template_1 key text Page/Sign/Date")
        body_outer_frames = [
            shape
            for part in body_header_parts
            for shape in _outer_frame_shapes(part)
        ]
        _check_outer_frame_geometry(
            reporter,
            "template.body.frameGeometry",
            "Body header",
            body_outer_frames,
            expected_body_outer_frame,
        )
        if BODY_TITLE_BLOCK_CODE in body_text:
            reporter.pass_("template.body.code", "Body official document code is present")
        else:
            reporter.warn("template.body.code", f"Body official document code `{BODY_TITLE_BLOCK_CODE}` was not detected")
        code_boxes = [
            _clean(_visible_text(shape))
            for part in body_header_parts
            for shape in _textbox_shapes_by_name(part, "Text Box 81")
        ]
        code_box_shapes = [
            shape
            for part in body_header_parts
            for shape in _textbox_shapes_by_name(part, "Text Box 81")
        ]
        if code_boxes and all(value == BODY_TITLE_BLOCK_CODE for value in code_boxes):
            reporter.pass_("template.body.codeExact", f"Body title block code is restored to `{BODY_TITLE_BLOCK_CODE}`")
        else:
            reporter.error(
                "template.body.codeExact",
                f"Body Text Box 81 must be `{BODY_TITLE_BLOCK_CODE}`, found {code_boxes}",
            )
        if any(_has_highlight_or_shading(shape) for shape in code_box_shapes):
            reporter.error("template.body.codeHighlight", "Body title block code must not have yellow highlight or shading")
        else:
            reporter.pass_("template.body.codeHighlight", "Body title block code has no highlight or shading")
        body_title_entries = [
            _clean(text_of(paragraph))
            for paragraph in root.xpath("//w:p", namespaces=NS)
            if "EdgeHub-Based Closed-Loop Temperature Control System" in _clean(text_of(paragraph))
        ]
        if any("Explanatory note" in value for value in body_title_entries):
            reporter.pass_("template.body.explanatoryNote", "Body title block includes Explanatory note")
        else:
            reporter.error("template.body.explanatoryNote", "Body title block title must end with Explanatory note")


def _render_docx_to_pdf(docx_path: Path, out_dir: Path) -> Path | None:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return None
    return out_dir / f"{docx_path.stem}.pdf"


def _applescript_string(value: Path | str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _render_docx_to_pdf_with_word(docx_path: Path, out_dir: Path) -> Path | None:
    supplied_pdf = os.environ.get("THESIS_WORD_VISUAL_PDF")
    if supplied_pdf:
        supplied_path = Path(supplied_pdf)
        if supplied_path.exists():
            return supplied_path
    if not os.environ.get("THESIS_WORD_VISUAL_CHECK"):
        return None
    osascript = shutil.which("osascript")
    if not osascript or not Path("/Applications/Microsoft Word.app").exists():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{docx_path.stem}_word.pdf"
    if out_path.exists():
        out_path.unlink()
    script = f'''
set docPath to POSIX file "{_applescript_string(docx_path)}"
set outPath to "{_applescript_string(out_path)}"
tell application "Microsoft Word"
    set display alerts to none
    open docPath
    delay 1
    set docRef to active document
    save as docRef file name outPath file format format PDF
    close docRef saving no
end tell
'''
    result = subprocess.run(
        [osascript],
        input=script,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    if out_path.exists():
        return out_path
    if result.returncode != 0:
        return None
    return out_path if out_path.exists() else None


def _render_pdf_pages(pdf_path: Path, out_dir: Path) -> list[Path]:
    # macOS fallback via qlmanage creates a preview bundle, but page-accurate PNGs
    # need LibreOffice plus a PDF rasterizer. Keep this conservative.
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf_path.stem
    for stale in out_dir.glob(f"{pdf_path.stem}-*.png"):
        stale.unlink()
    result = subprocess.run(
        [pdftoppm, "-png", "-r", "150", str(pdf_path), str(prefix)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return []
    return sorted(out_dir.glob(f"{pdf_path.stem}-*.png"))


def _rendered_outer_frame_margins(png_path: Path) -> tuple[int, int, int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    image = Image.open(png_path).convert("L")
    width, height = image.size
    mask = image.point(lambda value: 1 if value < 120 else 0)
    row_counts = [
        sum(mask.crop((0, y, width, y + 1)).getdata())
        for y in range(height)
    ]
    col_counts = [
        sum(mask.crop((x, 0, x + 1, height)).getdata())
        for x in range(width)
    ]
    rows = [index for index, count in enumerate(row_counts) if count > width * 0.45]
    cols = [index for index, count in enumerate(col_counts) if count > height * 0.35]
    if not rows or not cols:
        return None

    def centers(items: list[int]) -> list[int]:
        groups: list[list[int]] = []
        for item in items:
            if not groups or item > groups[-1][-1] + 1:
                groups.append([item])
            else:
                groups[-1].append(item)
        return [sum(group) // len(group) for group in groups]

    row_centers = centers(rows)
    col_centers = centers(cols)
    if not row_centers or not col_centers:
        return None
    return row_centers[0], height - row_centers[-1], col_centers[0], width - col_centers[-1]


def _pdf_text(pdf_path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext or not pdf_path.exists():
        return ""
    result = subprocess.run(
        [pdftotext, "-layout", str(pdf_path), "-"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _pdf_pages_text(pdf_path: Path) -> list[str]:
    text = _pdf_text(pdf_path)
    if not text:
        return []
    return text.split("\f")


def _pdf_page_count(pdf_path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo and pdf_path.exists():
        result = subprocess.run(
            [pdfinfo, str(pdf_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, flags=re.M)
            if match:
                return int(match.group(1))
    pages_text = _pdf_pages_text(pdf_path)
    if not pages_text:
        return None
    return len(pages_text) - (1 if pages_text[-1] == "" else 0)


def _normalized_pdf_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip().lower()


def _rendered_page_heading_candidates(page_text: str) -> set[str]:
    lines = [_normalized_pdf_line(line) for line in page_text.splitlines() if line.strip()]
    candidates = set(lines)
    for start in range(len(lines)):
        combined = lines[start]
        for end in range(start + 1, min(start + 4, len(lines))):
            combined = f"{combined} {lines[end]}"
            candidates.add(combined)
    return candidates


def _rendered_body_start_index(pages_text: list[str]) -> int:
    for index, page in enumerate(pages_text):
        lines = [_normalized_pdf_line(line) for line in page.splitlines() if line.strip()]
        dot_leader_lines = sum(1 for line in page.splitlines() if re.search(r"\.{4,}\s*\d+\s*$", line))
        if any(line == "contents" for line in lines) or dot_leader_lines >= 3:
            continue
        if any(_normalized_pdf_line(line) == "introduction" for line in page.splitlines()):
            return index
    return 2


def _rendered_title_block_page_number(page_text: str, physical_page_index: int) -> str:
    lines = [line.rstrip() for line in page_text.splitlines()]
    for line_index, line in enumerate(lines):
        if not re.search(r"\bPage\b", line):
            continue
        for following in lines[line_index + 1 : line_index + 6]:
            matches = re.findall(r"\b(\d{1,3})\s*$", following)
            if not matches:
                continue
            value = int(matches[-1])
            if value >= 3:
                return str(value)
    return str(physical_page_index)


def _rendered_heading_pages(pages_text: list[str], headings: list[str]) -> dict[str, str]:
    body_start_index = _rendered_body_start_index(pages_text) if pages_text else 2
    page_heading_candidates = [_rendered_page_heading_candidates(page) for page in pages_text]
    heading_pages: dict[str, str] = {}
    for heading in headings:
        needle = _normalized_pdf_line(heading)
        if not needle:
            continue
        for page_index, heading_candidates in enumerate(page_heading_candidates[body_start_index:], start=body_start_index + 1):
            if needle in heading_candidates:
                heading_pages[heading] = _rendered_title_block_page_number(
                    pages_text[page_index - 1],
                    page_index,
                )
                break
    return heading_pages


def _table_header_text(table: etree._Element) -> str:
    header_row = table.find("./w:tr", namespaces=NS)
    if header_row is None:
        return ""
    return _normalized_pdf_line(" ".join(_clean(text_of(cell)) for cell in header_row.xpath("./w:tc", namespaces=NS)))


def _word_table_headers(root: etree._Element) -> dict[str, str]:
    children = _body_section_children(root)
    headers: dict[str, str] = {}
    for index, element in enumerate(children):
        if element.tag != qn("w:tbl"):
            continue
        previous_paragraphs = [child_el for child_el in children[:index] if child_el.tag == qn("w:p")]
        caption_text = _clean(text_of(previous_paragraphs[-1])) if previous_paragraphs else ""
        if caption_text.startswith("Continue of the Table"):
            continue
        match = re.match(r"^Table\s+(\d+\.\d+)\s+\u2013", caption_text)
        if not match:
            continue
        header_text = _table_header_text(element)
        if header_text:
            headers[match.group(1)] = header_text
    return headers


def _check_rendered_table_continuations(
    sample_pdf: Path,
    reporter: Reporter,
    *,
    table_headers: dict[str, str] | None = None,
) -> None:
    pages_text = _pdf_pages_text(sample_pdf)
    if not pages_text:
        reporter.warn("table.renderedContinuation", "Could not extract rendered PDF text to validate continued table labels")
        return
    table_headers = table_headers or {}
    if not table_headers:
        reporter.warn("table.renderedContinuation", "Could not validate continued table labels without Word table metadata")
        return
    missing: list[str] = []
    for page_index, page_text in enumerate(pages_text, start=1):
        lines = [_normalized_pdf_line(line) for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue
        top_text = " ".join(lines[:8])
        top_caption_zone = " ".join(lines[:14])
        for table_number, header_text in table_headers.items():
            continuation_text = f"continue of the table {table_number}"
            caption_text = f"table {table_number}"
            if (
                header_text in top_text
                and continuation_text not in top_text
                and caption_text not in top_caption_zone
            ):
                missing.append(f"page {page_index}: Table {table_number}")
    if missing:
        reporter.error(
            "table.renderedContinuation",
            "Rendered continued table page is missing the required upper-left label: " + "; ".join(missing),
        )
    else:
        reporter.pass_("table.renderedContinuation", "Rendered continued table pages include required upper-left labels")


def _contents_paragraphs_for_entries(root: etree._Element, styles: dict[str, etree._Element]) -> list[etree._Element]:
    paragraphs = _section_paragraphs(root, 1)
    body_leading_contents: list[etree._Element] = []
    for paragraph in _body_section_paragraphs(root):
        text = _clean(text_of(paragraph))
        if _is_paragraph_style(paragraph, styles, "Contents Entry"):
            body_leading_contents.append(paragraph)
            continue
        if text:
            break
    return paragraphs + body_leading_contents


def _manual_contents_entries(root: etree._Element, styles: dict[str, etree._Element]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for paragraph in _contents_paragraphs_for_entries(root, styles):
        if _clean(text_of(paragraph)) == "Contents":
            continue
        text = _clean(_visible_text(paragraph))
        match = re.match(r"^(.*?)(\d+)$", text)
        if not match:
            continue
        title = _clean(match.group(1))
        page = match.group(2)
        if title:
            entries[title] = page
    return entries


def _check_rendered_contents_page_numbers(
    root: etree._Element,
    styles: dict[str, etree._Element],
    sample_pdf: Path,
    reporter: Reporter,
) -> None:
    pages_text = _pdf_pages_text(sample_pdf)
    if not pages_text:
        reporter.warn("contents.pageNumbers.rendered", "Could not extract rendered PDF text to validate Contents page numbers")
        return
    body_headings = [
        _clean(text_of(paragraph))
        for paragraph in _body_section_paragraphs(root)
        if _is_paragraph_style(paragraph, styles, "Heading 1") or _is_paragraph_style(paragraph, styles, "Heading 2")
    ]
    entries = _manual_contents_entries(root, styles)
    rendered_pages = _rendered_heading_pages(pages_text, body_headings)
    mismatches: list[str] = []
    missing_rendered: list[str] = []
    for heading in body_headings:
        if heading not in entries:
            continue
        rendered_page = rendered_pages.get(heading)
        if rendered_page is None:
            missing_rendered.append(heading)
            continue
        if entries[heading] != rendered_page:
            mismatches.append(f"{heading}: Contents {entries[heading]}, rendered {rendered_page}")
    if mismatches:
        reporter.error(
            "contents.pageNumbers.rendered",
            "Contents page numbers must match rendered heading pages: " + "; ".join(mismatches[:12]),
        )
    elif missing_rendered:
        reporter.error(
            "contents.pageNumbers.rendered",
            "Rendered heading page could not be resolved for Contents validation: " + "; ".join(missing_rendered[:12]),
        )
    else:
        reporter.pass_("contents.pageNumbers.rendered", "Contents page numbers match rendered heading pages")


def _check_rendered_contents_total_pages(sample_pdf: Path, reporter: Reporter) -> None:
    pages_text = _pdf_pages_text(sample_pdf)
    page_count = _pdf_page_count(sample_pdf)
    if not pages_text or page_count is None:
        reporter.warn("contents.totalPages.rendered", "Could not extract rendered Contents total page count")
        return
    contents_text = "\n".join(pages_text[1:3])
    lines = contents_text.splitlines()
    rendered_total = None
    for index, line in enumerate(lines):
        if not re.search(r"\bPage\s+Pages\b", line):
            continue
        pages_col = line.find("Pages")
        for following in lines[index + 1 : index + 10]:
            for match in re.finditer(r"\b(\d{2,3})\b", following):
                value = int(match.group(1))
                if 40 <= value <= 200 and match.start() >= max(0, pages_col - 10):
                    rendered_total = value
                    break
            if rendered_total is not None:
                break
        if rendered_total is not None:
            break
    if rendered_total is None:
        match = re.search(r"\bPages\s*\n\s*(\d{2,3})\b", contents_text)
        if match:
            rendered_total = int(match.group(1))
    if rendered_total is None:
        reporter.warn("contents.totalPages.rendered", "Could not locate rendered Pages value in the Contents title block")
        return
    # The official title-block numbering starts on the third physical page:
    # cover = 1, first contents page = 2, second contents/body-title-block
    # section starts at visible page BODY_TITLE_BLOCK_PAGE_START.
    visible_last_page = page_count + BODY_TITLE_BLOCK_PAGE_START - 3
    if rendered_total != visible_last_page:
        reporter.error(
            "contents.totalPages.rendered",
            f"Rendered Contents Pages value must match the last visible title-block page number: Pages cell {rendered_total}, last visible page {visible_last_page}",
        )
    else:
        reporter.pass_(
            "contents.totalPages.rendered",
            f"Rendered Contents Pages value matches the last visible title-block page number: {visible_last_page}",
        )


def _check_rendered_numbered_reference_line_breaks(sample_pdf: Path, reporter: Reporter) -> None:
    pages_text = _pdf_pages_text(sample_pdf)
    if not pages_text:
        reporter.warn("visual.numberedReferenceNoBreak", "Could not extract rendered PDF text to validate numbered reference line breaks")
        return
    broken: list[str] = []
    ref_word_re = re.compile(rf"\b{NUMBERED_REFERENCE_WORDS_RE}\s*$", flags=re.I)
    ref_number_re = re.compile(r"^\s*\(\d+\.\d+\)\b")
    for page_index, page_text in enumerate(pages_text, start=1):
        lines = [line.rstrip() for line in page_text.splitlines()]
        for line_index, line in enumerate(lines[:-1]):
            if ref_word_re.search(line) and ref_number_re.search(lines[line_index + 1]):
                broken.append(
                    f"page {page_index}: `{_clean(line[-80:])}` / `{_clean(lines[line_index + 1][:40])}`"
                )
    if broken:
        reporter.error(
            "visual.numberedReferenceNoBreak",
            "Rendered numbered references must stay on one line: " + " | ".join(broken[:8]),
        )
    else:
        reporter.pass_("visual.numberedReferenceNoBreak", "Rendered Figure/Table/formula references are not split before their numbers")


def _pdf_words_by_page(pdf_path: Path) -> list[list[tuple[str, float, float, float, float]]]:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext or not pdf_path.exists():
        return []
    result = subprocess.run(
        [pdftotext, "-bbox-layout", str(pdf_path), "-"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    words_by_page: list[list[tuple[str, float, float, float, float]]] = []
    try:
        html = etree.fromstring(result.stdout.encode("utf-8"), etree.XMLParser(recover=True))
    except etree.XMLSyntaxError:
        return []
    for page in html.xpath("//*[local-name()='page']"):
        words = []
        for word in page.xpath(".//*[local-name()='word']"):
            text = "".join(word.itertext()).strip()
            try:
                coords = (
                    float(word.get("xMin")),
                    float(word.get("yMin")),
                    float(word.get("xMax")),
                    float(word.get("yMax")),
                )
            except (TypeError, ValueError):
                continue
            words.append((text, *coords))
        words_by_page.append(words)
    return words_by_page


def _non_template_words(words: list[tuple[str, float, float, float, float]]) -> list[tuple[str, float, float, float, float]]:
    return [
        item
        for item in words
        if item[0] not in {"Page", "Sign", "Date"}
        and not re.fullmatch(r"\d+", item[0])
        and "BSTU" not in item[0]
        and "YOUR_NUMBER" not in item[0]
        and "БрГТУ" not in item[0]
        and "241297" not in item[0]
    ]


def _page_fill_ratio(words: list[tuple[str, float, float, float, float]], *, usable_height: float = 650.0) -> float | None:
    content_words = _non_template_words(words)
    if not content_words:
        return None
    y_min = min(item[2] for item in content_words)
    y_max = max(item[4] for item in content_words)
    return (y_max - y_min) / usable_height


def _visual_page_fill_ratio(png_path: Path) -> float | None:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    image = Image.open(png_path).convert("RGB")
    width, height = image.size
    left, right = int(width * 0.12), int(width * 0.88)
    top, bottom = int(height * 0.10), int(height * 0.84)
    if right <= left or bottom <= top:
        return None
    cropped = image.crop((left, top, right, bottom))
    light_mask = cropped.point(lambda value: 255 if value >= 248 else 0)
    ink_mask = ImageChops.invert(light_mask.convert("L"))
    bbox = ink_mask.getbbox()
    if not bbox:
        return None
    return (bbox[3] - bbox[1]) / (bottom - top)


def _check_body_page_fill(
    sample_pdf: Path,
    reporter: Reporter,
    *,
    sample_pngs: list[Path] | None = None,
    min_body_ratio: float = 0.6,
    min_last_ratio: float = 0.5,
    hard_min_body_ratio: float = 0.5,
    code_prefix: str = "visual.pageFill",
) -> None:
    words_by_page = _pdf_words_by_page(sample_pdf)
    if len(words_by_page) < 3:
        reporter.warn(code_prefix, "Could not evaluate body-page fill because rendered body pages were not detected")
        return
    pages_text = _pdf_pages_text(sample_pdf)
    body_start_index = _rendered_body_start_index(pages_text) if pages_text else 2
    body_pages = words_by_page[body_start_index:]
    under_half_pages: list[str] = []
    short_middle_pages: list[str] = []
    for idx, words in enumerate(body_pages[:-1]):
        text_ratio = _page_fill_ratio(words)
        visual_ratio = None
        page_png_index = body_start_index + idx
        if sample_pngs and page_png_index < len(sample_pngs):
            visual_ratio = _visual_page_fill_ratio(sample_pngs[page_png_index])
        ratio_values = [ratio for ratio in [text_ratio, visual_ratio] if ratio is not None]
        ratio = max(ratio_values) if ratio_values else None
        if ratio is None:
            continue
        page_number = body_start_index + idx + 1
        if ratio < hard_min_body_ratio:
            under_half_pages.append(f"{page_number} ({ratio:.2f})")
        if ratio < min_body_ratio:
            short_middle_pages.append(f"{page_number} ({ratio:.2f})")
    if under_half_pages:
        reporter.error(
            f"{code_prefix}.halfPage",
            "Body pages must not be under 50% filled: " + ", ".join(under_half_pages),
        )
    else:
        reporter.pass_(f"{code_prefix}.halfPage", "All non-final body pages are at least half filled")
    if short_middle_pages:
        reporter.error(
            f"{code_prefix}.body",
            "Body pages must not contain large blank areas below the 60% fill threshold: "
            + ", ".join(short_middle_pages),
        )
    else:
        reporter.pass_(f"{code_prefix}.body", "All non-final body pages are filled above the 60% threshold")

    last_idx = None
    for idx in range(len(body_pages) - 1, -1, -1):
        words = _non_template_words(body_pages[idx])
        if words:
            last_idx = idx
            break
    if last_idx is None:
        reporter.warn(f"{code_prefix}.lastBody", "No body text words were found in rendered preview")
        return
    fill_ratio = _page_fill_ratio(body_pages[last_idx])
    if fill_ratio is None:
        reporter.warn(f"{code_prefix}.lastBody", "Could not evaluate final body-page fill")
        return
    page_number = body_start_index + last_idx + 1
    if fill_ratio >= min_last_ratio:
        reporter.pass_(
            f"{code_prefix}.lastBody",
            f"Last body page {page_number} is filled above half-page threshold: {fill_ratio:.2f}",
        )
    else:
        reporter.error(
            f"{code_prefix}.lastBody",
            f"Last body page {page_number} has large blank area; text fill is only {fill_ratio:.2f}. "
            "Add content or move material so the final page is at least about half full before the next section starts.",
        )


def check_visual_preview(docx_path: Path, root: etree._Element, styles: dict[str, etree._Element], reporter: Reporter) -> None:
    preview_dir = docx_path.parent / "preview"
    side_by_side_dir = preview_dir / "side_by_side_preview"
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        side_by_side_dir.mkdir(parents=True, exist_ok=True)
        note = side_by_side_dir / "VISUAL_QA_NOT_GENERATED.md"
        note.write_text(
            "# Visual QA Not Generated\n\n"
            "LibreOffice is not installed on this machine, so the checker could not render "
            "`sample_final.docx` and the source templates to PDF/PNG.\n\n"
            "Install LibreOffice and rerun:\n\n"
            "```bash\n"
            "python thesis/scripts/build_template.py\n"
            "```\n\n"
            "Expected side-by-side files after rendering:\n\n"
            "- `template_0_vs_contents.png`\n"
            "- `template_1_vs_body.png`\n",
            encoding="utf-8",
        )
        reporter.warn(
            "visual.renderer",
            "LibreOffice is not installed; visual QA PNGs were not generated. Manually inspect template alignment in Word/LibreOffice.",
        )
        reporter.warn(
            "visual.sideBySide",
            f"Side-by-side previews require LibreOffice and pdftoppm. Placeholder note: {note}",
        )
        return

    sample_pdf = _render_docx_to_pdf(docx_path, preview_dir)
    template0_pdf = _render_docx_to_pdf(TEMPLATE_DIR / "template_0.docx", preview_dir)
    template1_pdf = _render_docx_to_pdf(TEMPLATE_DIR / "template_1.docx", preview_dir)
    if not sample_pdf or not sample_pdf.exists():
        reporter.error("visual.render.sample", "LibreOffice failed to render sample_final.docx to PDF")
        return
    reporter.pass_("visual.render.sample", f"Rendered sample PDF: {sample_pdf}")

    word_pdf_dir = preview_dir / "word_preview"
    word_pdf = _render_docx_to_pdf_with_word(docx_path, word_pdf_dir)
    visual_pdf = word_pdf if word_pdf and word_pdf.exists() else sample_pdf
    if word_pdf and word_pdf.exists():
        reporter.pass_("visual.wordRender.sample", f"Using Microsoft Word PDF for page-sensitive checks: {word_pdf}")
    else:
        reporter.warn(
            "visual.wordRender.sample",
            "Microsoft Word PDF export was not available; LibreOffice PDF was used for page-sensitive preview checks",
        )
    _check_rendered_contents_page_numbers(root, styles, visual_pdf, reporter)
    _check_rendered_contents_total_pages(visual_pdf, reporter)
    _check_rendered_numbered_reference_line_breaks(visual_pdf, reporter)
    _check_rendered_table_continuations(visual_pdf, reporter, table_headers=_word_table_headers(root))

    sample_pngs = _render_pdf_pages(sample_pdf, preview_dir)
    template0_pngs = _render_pdf_pages(template0_pdf, preview_dir) if template0_pdf else []
    template1_pngs = _render_pdf_pages(template1_pdf, preview_dir) if template1_pdf else []
    if not sample_pngs:
        side_by_side_dir.mkdir(parents=True, exist_ok=True)
        note = side_by_side_dir / "PNG_QA_NOT_GENERATED.md"
        note.write_text(
            "# PNG QA Not Generated\n\n"
            "LibreOffice rendered the PDF, but `pdftoppm` was not found or failed, so page PNGs "
            "and side-by-side previews were not generated.\n",
            encoding="utf-8",
        )
        reporter.warn("visual.png", "PDF was rendered, but no PNG rasterizer was available; run visual inspection manually")
        return
    reporter.pass_("visual.png", f"Rendered {len(sample_pngs)} sample PNG page(s) under {preview_dir}")
    if len(sample_pngs) >= 3:
        contents_margins = _rendered_outer_frame_margins(sample_pngs[1])
        body_margins = _rendered_outer_frame_margins(sample_pngs[2])
        if contents_margins and body_margins:
            diffs = [abs(left - right) for left, right in zip(contents_margins, body_margins)]
            if max(diffs) <= 2:
                reporter.pass_(
                    "visual.frameMargins.contentsBody",
                    f"Contents and body rendered frame margins match: contents={contents_margins}, body={body_margins}",
                )
            else:
                reporter.error(
                    "visual.frameMargins.contentsBody",
                    f"Contents and body rendered frame margins differ: contents={contents_margins}, body={body_margins}",
                )
        else:
            reporter.warn("visual.frameMargins.contentsBody", "Could not measure rendered Contents/body frame margins")

    pages_text = _pdf_pages_text(visual_pdf)
    body_pages = [page for page in pages_text[2:] if page.strip()]
    visual_x_pages = [
        idx + 3
        for idx, page in enumerate(body_pages)
        if re.search(r"(?m)^\s*X\s*$", page)
    ]
    if visual_x_pages:
        reporter.error("visual.textArtifact.x", f"Rendered body page(s) contain standalone X: {visual_x_pages}")
    else:
        reporter.pass_("visual.textArtifact.x", "Rendered body pages contain no standalone X")
    visual_page_pages = [
        idx + 3
        for idx, page in enumerate(body_pages)
        if re.search(r"(?m)^\s*PAGE\s*$|PAGE\s+PAGE|3X|33X", page)
    ]
    if visual_page_pages:
        reporter.error("visual.textArtifact.page", f"Rendered body page(s) contain visible PAGE/field artifacts: {visual_page_pages}")
    else:
        reporter.pass_("visual.textArtifact.page", "Rendered body pages contain no visible PAGE artifacts")
    if word_pdf and word_pdf.exists():
        word_pngs = _render_pdf_pages(word_pdf, word_pdf_dir)
        if word_pngs:
            reporter.pass_("visual.wordPng", f"Rendered {len(word_pngs)} Microsoft Word PNG page(s) under {word_pdf_dir}")
            _check_body_page_fill(
                word_pdf,
                reporter,
                sample_pngs=word_pngs,
                code_prefix="visual.wordPageFill",
            )
        else:
            reporter.warn("visual.wordPng", "Microsoft Word PDF rendered, but PNG rasterization was not available")
    else:
        _check_body_page_fill(sample_pdf, reporter, sample_pngs=sample_pngs)
    if word_pdf and word_pdf.exists():
        reporter.pass_("visual.pagenum.rendered", "Microsoft Word PDF was used for rendered page-number verification")
    elif any(
        finding.severity == "PASS" and finding.code == "pagenum.body.liveFieldCount"
        for finding in reporter.findings
    ):
        reporter.warn(
            "visual.pagenum.rendered",
            "LibreOffice/PDF preview cannot reliably place Word w:framePr live header page fields; verify the right-bottom Page cell in Microsoft Word.",
        )
    else:
        live_field_xml_missing = True
        for finding in reporter.findings:
            if finding.severity == "PASS" and finding.code == "pagenum.body.framePr":
                live_field_xml_missing = False
                break
        if live_field_xml_missing:
            reporter.error("visual.pagenum.rendered", "Live PAGE field XML is missing, so rendered page numbers cannot be trusted")
        else:
            reporter.warn("visual.pagenum.rendered", "Rendered page-number position still needs Microsoft Word confirmation")

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        reporter.warn("visual.sideBySide", "Pillow is missing; cannot create side-by-side preview images")
        return

    side_by_side_dir.mkdir(parents=True, exist_ok=True)
    pairs = []
    if template0_pngs and len(sample_pngs) >= 2:
        pairs.append((template0_pngs[0], sample_pngs[1], side_by_side_dir / "template_0_vs_contents.png"))
    if template1_pngs and len(sample_pngs) >= 3:
        pairs.append((template1_pngs[0], sample_pngs[2], side_by_side_dir / "template_1_vs_body.png"))
    for left_path, right_path, out_path in pairs:
        left = Image.open(left_path).convert("RGB")
        right = Image.open(right_path).convert("RGB")
        height = max(left.height, right.height)
        width = left.width + right.width
        canvas = Image.new("RGB", (width, height), "white")
        canvas.paste(left, (0, 0))
        canvas.paste(right, (left.width, 0))
        draw = ImageDraw.Draw(canvas)
        draw.line((left.width, 0, left.width, height), fill=(255, 0, 0), width=3)
        canvas.save(out_path)
    if pairs:
        reporter.warn(
            "visual.manualReview",
            f"Generated side-by-side previews in {side_by_side_dir}; manually confirm border thickness, title-block alignment, and clipping.",
        )
    else:
        reporter.warn("visual.sideBySide", "Could not create side-by-side template previews; manually compare rendered files")


def render_report(docx_path: Path, reporter: Reporter) -> str:
    counts = reporter.counts()
    lines = [
        "# Thesis Format Report",
        "",
        f"- Document: `{docx_path}`",
        f"- PASS: {counts['PASS']}",
        f"- WARNING: {counts['WARNING']}",
        f"- ERROR: {counts['ERROR']}",
        "",
        "| Severity | Code | Message |",
        "| --- | --- | --- |",
    ]
    for finding in reporter.findings:
        msg = finding.message.replace("|", "\\|")
        lines.append(f"| {finding.severity} | `{finding.code}` | {msg} |")
    return "\n".join(lines) + "\n"


def check_docx(docx_path: Path, report_path: Path = REPORT_PATH, *, partial: bool = False) -> Reporter:
    package, document_root, styles_root = _load_package(docx_path)
    styles = _style_map(styles_root)
    reporter = Reporter()
    check_page_setup(document_root, reporter)
    check_body_paragraphs(document_root, styles, reporter)
    check_headings(document_root, styles, reporter)
    check_thesis_section_structure(document_root, styles, reporter)
    check_contents(document_root, styles, reporter)
    check_page_numbers(package, document_root, reporter)
    check_style_colors(styles, reporter)
    check_figures(document_root, styles, reporter)
    check_tables(document_root, styles, reporter)
    check_formulas(document_root, styles, reporter, require_formula=not partial)
    check_rules_text_presentation(document_root, styles, reporter)
    check_chapter_rules(document_root, styles, reporter)
    check_references(document_root, styles, reporter)
    check_templates(package, document_root, reporter)
    check_visual_preview(docx_path, document_root, styles, reporter)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(docx_path, reporter), encoding="utf-8")
    return reporter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when ERROR findings exist")
    parser.add_argument("--partial", action="store_true", help="Allow checks that are only required for the complete thesis to warn instead of error")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)
    if not args.docx.exists():
        raise SystemExit(f"Missing docx: {args.docx}")
    reporter = check_docx(args.docx, args.report, partial=args.partial)
    counts = reporter.counts()
    print(f"PASS: {counts['PASS']}")
    print(f"WARNING: {counts['WARNING']}")
    print(f"ERROR: {counts['ERROR']}")
    print(f"Wrote {args.report}")
    if args.strict and reporter.has_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
