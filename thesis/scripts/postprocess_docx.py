#!/usr/bin/env python3
"""Apply school thesis page templates without redrawing or moving frames."""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path
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
    CT_NS,
    LAYOUT,
    NS,
    add_header_footer_part,
    add_relationship,
    append_page_field_to_paragraph,
    blank_footer_xml,
    blank_header_xml,
    child,
    ensure_content_type,
    iter_section_properties,
    mm_to_twips,
    make_field_run,
    parse_xml,
    qn,
    read_docx,
    remove_page_number_restart,
    normalize_page_fields,
    serialize_xml,
    set_header_footer_references,
    set_section_break_type,
    text_of,
    write_docx,
)


ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = ROOT / "template"

# Calibrated at 150 dpi against the supplied title-page reference document.
# The reference file uses a taller legacy page, so only the upper frame
# clearance is mapped directly. The lower title-block area is kept below the
# Rules_diplom text area to avoid body text overlapping the school frame.
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

# The visible Page-number cell stays in template_1's header frame, but the
# actual PAGE field is a normal header text frame. Word refreshes this kind of
# field while the user creates new pages by typing, unlike a cached DrawingML
# text-box field.
LIVE_PAGE_FIELD_X_TWIPS = 11150 + FRAME_VISUAL_BALANCE_DX_TWIPS
LIVE_PAGE_FIELD_Y_TWIPS = 15880
LIVE_PAGE_FIELD_WIDTH_TWIPS = 540
LIVE_PAGE_FIELD_HEIGHT_TWIPS = 500
LIVE_PAGE_FIELD_RUN_POSITION_HALF_POINTS = 0
BODY_TITLE_BLOCK_CODE = "BSTU.YOUR_NUMBER- 12 81 00"


def _set_rules_text_margins(sect_pr: etree._Element) -> None:
    """Keep template anchors, but restore Rules_diplom Appendix L text margins."""

    pg_mar = child(sect_pr, "w:pgMar")
    if pg_mar is None:
        pg_mar = etree.SubElement(sect_pr, qn("w:pgMar"))
    pg_mar.set(qn("w:top"), str(mm_to_twips(LAYOUT.top_margin_mm)))
    pg_mar.set(qn("w:right"), str(mm_to_twips(LAYOUT.right_margin_mm)))
    pg_mar.set(qn("w:bottom"), str(mm_to_twips(LAYOUT.bottom_margin_mm)))
    pg_mar.set(qn("w:left"), str(mm_to_twips(LAYOUT.left_margin_mm)))
    pg_mar.set(qn("w:header"), str(mm_to_twips(LAYOUT.header_distance_mm)))
    pg_mar.set(qn("w:footer"), str(mm_to_twips(LAYOUT.footer_distance_mm)))
    pg_mar.set(qn("w:gutter"), "0")


def insert_page_field(paragraph) -> None:
    """Insert a real Word PAGE field into a python-docx or lxml paragraph."""

    paragraph_el = paragraph._p if hasattr(paragraph, "_p") else paragraph
    append_page_field_to_paragraph(paragraph_el)


def _template_document_root(template_docx: Path) -> etree._Element:
    with ZipFile(template_docx) as zf:
        return parse_xml(zf.read("word/document.xml"))


def _template_sect_pr(template_docx: Path) -> etree._Element:
    root = _template_document_root(template_docx)
    sects = root.xpath("//w:sectPr", namespaces=NS)
    if not sects:
        raise RuntimeError(f"No sectPr found in {template_docx}")
    return copy.deepcopy(sects[-1])


def _template_body_frame_elements(template_docx: Path, *, clear_text: bool = False) -> list[etree._Element]:
    root = _template_document_root(template_docx)
    body = root.find("w:body", namespaces=NS)
    if body is None:
        raise RuntimeError(f"No document body found in {template_docx}")
    elements = [copy.deepcopy(el) for el in body if el.tag != qn("w:sectPr")]
    if clear_text:
        for element in elements:
            for text in element.xpath(".//w:t", namespaces=NS):
                text.text = ""
            for instr in element.xpath(".//w:instrText", namespaces=NS):
                instr.text = ""
    return elements


def _section_break_paragraphs(document_root: etree._Element) -> list[etree._Element]:
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        return []
    return body.xpath("./w:p[w:pPr/w:sectPr]", namespaces=NS)


def _insert_elements_after(anchor: etree._Element, elements: list[etree._Element]) -> None:
    parent = anchor.getparent()
    if parent is None:
        raise RuntimeError("Cannot insert template elements after detached anchor")
    index = parent.index(anchor) + 1
    for offset, element in enumerate(elements):
        parent.insert(index + offset, element)


def _insert_elements_at_body_start(document_root: etree._Element, elements: list[etree._Element]) -> None:
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        raise RuntimeError("Cannot insert template elements: document body missing")
    for offset, element in enumerate(elements):
        body.insert(offset, element)


def _shift_template_frame_elements(elements: list[etree._Element], delta_x_emu: int, delta_y_emu: int = 0) -> None:
    for element in elements:
        for anchor in element.xpath(".//wp:anchor", namespaces=NS):
            _add_to_int_text(anchor.find("./wp:positionH/wp:posOffset", namespaces=NS), delta_x_emu)
            _add_to_int_text(anchor.find("./wp:positionV/wp:posOffset", namespaces=NS), delta_y_emu)


def _scale_template_frame_elements_y(elements: list[etree._Element], scale_y: float) -> None:
    for element in elements:
        for anchor_extent in element.xpath(".//wp:anchor/wp:extent", namespaces=NS):
            _scale_int_attr(anchor_extent, "cy", scale_y)
        for group_ext in element.xpath(".//wpg:wgp/wpg:grpSpPr/a:xfrm/a:ext", namespaces=NS):
            _scale_int_attr(group_ext, "cy", scale_y)


def _rels_root(package: dict[str, bytes], rels_name: str) -> etree._Element:
    if rels_name in package:
        return parse_xml(package[rels_name])
    root = etree.Element(
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
    )
    package[rels_name] = serialize_xml(root)
    return root


def _copy_related_part(
    final_package: dict[str, bytes],
    final_rels_root: etree._Element,
    content_types_root: etree._Element,
    source_docx: Path,
    source_base_part: str,
    rid: str,
) -> str | None:
    source_rels_name = f"word/_rels/{Path(source_base_part).name}.rels"
    with ZipFile(source_docx) as zf:
        if source_rels_name not in zf.namelist():
            return None
        source_rels_root = parse_xml(zf.read(source_rels_name))
        rel = next((item for item in source_rels_root if item.get("Id") == rid), None)
        if rel is None:
            return None
        target = rel.get("Target")
        rel_type = rel.get("Type")
        if not target or not rel_type:
            return None
        if target.startswith("http"):
            return add_relationship(final_rels_root, rel_type.rsplit("/", 1)[-1], target)
        source_target = str((Path(source_base_part).parent / target).as_posix())
        if source_target not in zf.namelist():
            return None
        final_package[source_target] = zf.read(source_target)
        if source_target.startswith("word/media/"):
            ensure_content_type(
                content_types_root,
                source_target,
                "image/png" if source_target.lower().endswith(".png") else "image/jpeg",
            )
        new_rel = etree.SubElement(
            final_rels_root,
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        )
        new_rid = f"rIdTemplate{abs(hash((source_target, rid))) % 1000000}"
        used = {item.get("Id") for item in final_rels_root}
        while new_rid in used:
            new_rid += "x"
        new_rel.set("Id", new_rid)
        new_rel.set("Type", rel_type)
        new_rel.set("Target", target)
        return new_rid


def _remap_template_relationships(
    elements: list[etree._Element],
    final_package: dict[str, bytes],
    final_document_rels: etree._Element,
    content_types_root: etree._Element,
    source_docx: Path,
    source_part: str = "word/document.xml",
) -> None:
    ids = sorted({value for element in elements for value in element.xpath(".//@r:id", namespaces=NS)})
    for rid in ids:
        new_rid = _copy_related_part(
            final_package,
            final_document_rels,
            content_types_root,
            source_docx,
            source_part,
            rid,
        )
        if not new_rid:
            continue
        for element in elements:
            for attr_owner in element.xpath(f".//*[@r:id='{rid}']", namespaces=NS):
                attr_owner.set(qn("r:id"), new_rid)


def _paragraph_has_page_field(paragraph: etree._Element) -> bool:
    return any(
        instr.text and re.search(r"\bPAGE\b", instr.text)
        for instr in paragraph.xpath(".//w:instrText", namespaces=NS)
    )


def _strip_page_field_runs(paragraph: etree._Element) -> None:
    for child_el in list(paragraph):
        if child_el.tag == qn("w:pPr"):
            continue
        paragraph.remove(child_el)


def _replace_with_single_page_field(paragraph: etree._Element) -> None:
    _strip_page_field_runs(paragraph)
    append_page_field_to_paragraph(paragraph, display="1")


def _clear_paragraph_content_keep_ppr(paragraph: etree._Element) -> None:
    for child_el in list(paragraph):
        if child_el.tag != qn("w:pPr"):
            paragraph.remove(child_el)


def _append_field_to_paragraph(
    paragraph: etree._Element,
    instr: str,
    display: str,
    rpr: etree._Element | None = None,
) -> None:
    for run in make_field_run(instr, display):
        if rpr is not None:
            run.insert(0, copy.deepcopy(rpr))
        paragraph.append(run)


def _insert_single_page_field_in_paragraph(paragraph: etree._Element) -> None:
    _clear_paragraph_content_keep_ppr(paragraph)
    append_page_field_to_paragraph(paragraph, display="1")


def _remove_highlight_and_shading(element: etree._Element) -> None:
    for rpr in element.xpath(".//w:rPr|.//w:pPr/w:rPr", namespaces=NS):
        for tag in (qn("w:highlight"), qn("w:shd")):
            for child_el in list(rpr.findall(tag)):
                rpr.remove(child_el)


def _field_run_properties_from_shape(shape: etree._Element) -> etree._Element | None:
    rpr = _first_xpath(shape, ".//w:txbxContent/w:p/w:r/w:rPr")
    if rpr is None:
        rpr = _first_xpath(shape, ".//w:txbxContent/w:p/w:pPr/w:rPr")
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for tag in (qn("w:highlight"), qn("w:shd")):
        for child_el in list(rpr.findall(tag)):
            rpr.remove(child_el)
    return rpr


def _shape_matches_name(shape: etree._Element, wanted: str) -> bool:
    return _shape_name(shape) == wanted


def _shapes_by_name_in_elements(elements: list[etree._Element], wanted: str) -> list[etree._Element]:
    matches: list[etree._Element] = []
    for element in elements:
        matches.extend(
            shape
            for shape in element.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
            if _shape_matches_name(shape, wanted)
        )
    return matches


def _replace_shape_text_with_field(shape: etree._Element, instr: str, display: str) -> None:
    paragraphs = _paragraphs_inside(shape)
    if not paragraphs:
        return
    rpr = _field_run_properties_from_shape(shape)
    _remove_highlight_and_shading(shape)
    _clear_paragraph_content_keep_ppr(paragraphs[0])
    _append_field_to_paragraph(paragraphs[0], instr, display, rpr)
    for paragraph in paragraphs[1:]:
        _clear_paragraph_content_keep_ppr(paragraph)


def _normalize_contents_page_number_cells(elements: list[etree._Element]) -> None:
    # template_0 contains static sample values ("2" and highlighted "46").
    # Keep the original title-block geometry, but make both cells real Word fields.
    for shape in _shapes_by_name_in_elements(elements, "Rectangle 34"):
        _replace_shape_text_with_field(shape, "PAGE", "2")
    for shape in _shapes_by_name_in_elements(elements, "Rectangle 6"):
        _replace_shape_text_with_field(shape, "NUMPAGES", "1")


def _remove_standalone_page_paragraphs(root: etree._Element) -> None:
    # These paragraphs are outside the visible title block and caused top-of-page PAGE/3X artifacts.
    for paragraph in list(root.xpath("./w:p", namespaces=NS)):
        if _paragraph_has_page_field(paragraph) and not paragraph.xpath(
            ".//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS
        ):
            root.remove(paragraph)


def _remove_floating_page_runs(root: etree._Element) -> None:
    for paragraph in root.xpath("./w:p", namespaces=NS):
        for run in list(paragraph.xpath("./w:r", namespaces=NS)):
            # Preserve the actual school frame stored in AlternateContent/drawing/pict.
            if run.xpath(".//mc:AlternateContent|.//w:drawing|.//w:pict|.//v:shape|.//wps:wsp", namespaces=NS):
                continue
            if (
                _paragraph_has_page_field(run)
                or text_of(run).strip().isdigit()
                or run.xpath(".//w:fldChar", namespaces=NS)
            ):
                paragraph.remove(run)


def _element_bottom_right_score(element: etree._Element) -> tuple[int, int]:
    off = element.find("./wps:spPr/a:xfrm/a:off", namespaces=NS)
    if off is not None:
        try:
            return int(off.get("x", "0")), int(off.get("y", "0"))
        except ValueError:
            return 0, 0
    style = element.get("style", "")
    coords: dict[str, int] = {}
    for key in ["left", "top"]:
        match = re.search(rf"{key}:(-?\d+)", style)
        if match:
            coords[key] = int(match.group(1))
    return coords.get("left", 0), coords.get("top", 0)


def _page_label_shapes(root: etree._Element) -> list[etree._Element]:
    return [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _clean_text(text_of(shape)) == "Page"
    ]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _shape_textbox_kind(element: etree._Element) -> str:
    if element.tag == qn("wps:wsp"):
        return "drawingml"
    if element.tag == qn("v:shape"):
        return "vml"
    return "other"


def _nearest_page_number_shape(root: etree._Element, kind: str) -> etree._Element | None:
    labels = [shape for shape in _page_label_shapes(root) if _shape_textbox_kind(shape) == kind]
    candidates = [
        shape
        for shape in root.xpath(".//wps:wsp|.//v:shape", namespaces=NS)
        if _shape_textbox_kind(shape) == kind
        and shape not in labels
        and (_paragraph_has_page_field(shape) or re.fullmatch(r"\d+", _clean_text(text_of(shape))) is not None)
    ]
    if not labels or not candidates:
        return None
    label = max(labels, key=_element_bottom_right_score)
    lx, ly = _element_bottom_right_score(label)
    below_or_same = []
    for candidate in candidates:
        cx, cy = _element_bottom_right_score(candidate)
        if cx >= lx - 50 and cy >= ly:
            below_or_same.append(candidate)
    pool = below_or_same or candidates
    return min(
        pool,
        key=lambda candidate: (
            abs(_element_bottom_right_score(candidate)[0] - lx),
            abs(_element_bottom_right_score(candidate)[1] - ly),
        ),
    )


def _paragraphs_inside(element: etree._Element) -> list[etree._Element]:
    return element.xpath(".//w:txbxContent/w:p", namespaces=NS)


def _clear_page_fields_and_digits(element: etree._Element) -> None:
    for paragraph in _paragraphs_inside(element):
        _clear_paragraph_content_keep_ppr(paragraph)


def _remove_visible_field_instruction_runs(root: etree._Element) -> None:
    # Field instructions inside text boxes are XML machinery, but LibreOffice can expose
    # stale cached instruction text when duplicate compatibility branches disagree.
    for text in root.xpath(".//w:t", namespaces=NS):
        if text.text and re.fullmatch(r"\s*PAGE\s*", text.text):
            parent = text.getparent()
            run = parent.getparent() if parent is not None and parent.tag == qn("w:rPr") else parent
            if run is not None and run.tag == qn("w:r"):
                run.getparent().remove(run)


def _shape_name(element: etree._Element) -> str:
    if element.tag == qn("wps:wsp"):
        props = element.find("./wps:cNvPr", namespaces=NS)
        return props.get("name", "") if props is not None else ""
    if element.tag == qn("v:shape"):
        return element.get("id", "") or element.get("name", "")
    return ""


def _first_xpath(element: etree._Element, xpath: str) -> etree._Element | None:
    matches = element.xpath(xpath, namespaces=NS)
    return matches[0] if matches else None


def _add_to_int_text(element: etree._Element | None, delta: int) -> None:
    if element is None or element.text is None:
        return
    element.text = str(int(element.text) + delta)


def _shift_anchor_horizontally(element: etree._Element, delta_emu: int) -> None:
    _add_to_int_text(_first_xpath(element, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), delta_emu)


def _shift_anchor(element: etree._Element, delta_x_emu: int, delta_y_emu: int) -> None:
    _add_to_int_text(_first_xpath(element, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), delta_x_emu)
    _add_to_int_text(_first_xpath(element, "ancestor::wp:anchor[1]/wp:positionV/wp:posOffset"), delta_y_emu)


def _scale_int_attr(element: etree._Element | None, attr: str, scale: float) -> None:
    if element is None:
        return
    value = element.get(attr)
    if value is not None:
        element.set(attr, str(int(round(int(value) * scale))))


def _set_template1_outer_line_style(shape: etree._Element) -> None:
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


def _align_template1_frame_to_contents_outer_border(root: etree._Element) -> None:
    frames = root.xpath(".//wps:cNvPr[@name='Rectangle 65']/..", namespaces=NS)
    if len(frames) != 1:
        raise RuntimeError(f"Expected exactly one template_1 Rectangle 65 frame, found {len(frames)}")
    frame = frames[0]
    anchor = _first_xpath(frame, "ancestor::wp:anchor[1]")
    group_ext = _first_xpath(frame, "ancestor::wpg:wgp[1]/wpg:grpSpPr/a:xfrm/a:ext")
    _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionH/wp:posOffset"), CONTENTS_FRAME_DX_EMU)
    _shift_anchor_horizontally(frame, FRAME_VISUAL_BALANCE_DX_EMU)
    _add_to_int_text(_first_xpath(frame, "ancestor::wp:anchor[1]/wp:positionV/wp:posOffset"), CONTENTS_FRAME_DY_EMU)
    if anchor is not None:
        anchor_extent = anchor.find("wp:extent", namespaces=NS)
        _scale_int_attr(anchor_extent, "cx", CONTENTS_FRAME_SCALE_X)
        _scale_int_attr(anchor_extent, "cy", CONTENTS_FRAME_SCALE_Y)
    _scale_int_attr(group_ext, "cx", CONTENTS_FRAME_SCALE_X)
    _scale_int_attr(group_ext, "cy", CONTENTS_FRAME_SCALE_Y)
    _set_template1_outer_line_style(frame)


def _send_template_frame_behind_text(root: etree._Element) -> None:
    for anchor in root.xpath(".//wp:anchor", namespaces=NS):
        anchor.set("behindDoc", "1")
        anchor.set("relativeHeight", "0")


def _remove_fallback_branches(root: etree._Element) -> None:
    for fallback in list(root.xpath(".//mc:Fallback", namespaces=NS)):
        parent = fallback.getparent()
        if parent is not None:
            parent.remove(fallback)


def _remove_empty_groups(root: etree._Element) -> None:
    changed = True
    while changed:
        changed = False
        for group in list(root.xpath(".//wpg:grpSp", namespaces=NS)):
            if group.xpath(".//wps:wsp|.//v:shape", namespaces=NS):
                continue
            parent = group.getparent()
            if parent is not None:
                parent.remove(group)
                changed = True


def _template1_outer_frame_header(header_xml: bytes) -> bytes:
    root = parse_xml(header_xml)
    _remove_standalone_page_paragraphs(root)
    _remove_floating_page_runs(root)
    _remove_fallback_branches(root)
    alternate = root.find(".//mc:AlternateContent", namespaces=NS)
    if alternate is None:
        raise RuntimeError("template_1 header2.xml does not contain an AlternateContent frame")

    for shape in list(root.xpath(".//wps:wsp", namespaces=NS)):
        if _shape_name(shape) != "Rectangle 65":
            parent = shape.getparent()
            if parent is not None:
                parent.remove(shape)
    for shape in list(root.xpath(".//v:shape", namespaces=NS)):
        parent = shape.getparent()
        if parent is not None:
            parent.remove(shape)
    _remove_empty_groups(root)
    if not root.xpath(".//wps:cNvPr[@name='Rectangle 65']", namespaces=NS):
        raise RuntimeError("Could not isolate template_1 Rectangle 65 outer frame")
    _align_template1_frame_to_contents_outer_border(root)
    _shift_anchor(root.xpath(".//wps:cNvPr[@name='Rectangle 65']/..", namespaces=NS)[0], FRAME_ALIGN_TO_BODY_DX_EMU, FRAME_ALIGN_TO_BODY_DY_EMU)
    return serialize_xml(root)


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


def _title_block_run_properties(*, size: str = "28", highlight: bool = False) -> etree._Element:
    rpr = etree.Element(qn("w:rPr"))
    fonts = etree.SubElement(rpr, qn("w:rFonts"))
    fonts.set(qn("w:ascii"), "ISOCPEUR")
    fonts.set(qn("w:hAnsi"), "ISOCPEUR")
    fonts.set(qn("w:eastAsia"), "ISOCPEUR")
    etree.SubElement(rpr, qn("w:i"))
    sz = etree.SubElement(rpr, qn("w:sz"))
    sz.set(qn("w:val"), size)
    sz_cs = etree.SubElement(rpr, qn("w:szCs"))
    sz_cs.set(qn("w:val"), size)
    if highlight:
        marker = etree.SubElement(rpr, qn("w:highlight"))
        marker.set(qn("w:val"), "yellow")
    return rpr


def _append_text_run(paragraph: etree._Element, text: str, rpr: etree._Element) -> None:
    run = etree.SubElement(paragraph, qn("w:r"))
    run.append(copy.deepcopy(rpr))
    text_el = etree.SubElement(run, qn("w:t"))
    if text.startswith(" ") or text.endswith(" "):
        text_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_el.text = text


def _restore_template1_title_block_text(root: etree._Element) -> None:
    boxes = _textbox_shapes_by_name(root, "Text Box 81")
    if len(boxes) != 1:
        raise RuntimeError(f"Expected exactly one template_1 Text Box 81, found {len(boxes)}")
    paragraphs = _paragraphs_inside(boxes[0])
    if not paragraphs:
        raise RuntimeError("Text Box 81 has no paragraph for the document code")
    paragraph = paragraphs[0]
    _clear_paragraph_content_keep_ppr(paragraph)
    _append_text_run(paragraph, "BSTU", _title_block_run_properties(size="28"))
    _append_text_run(paragraph, ".", _title_block_run_properties(size="28"))
    _append_text_run(paragraph, "YOUR_NUMBER", _title_block_run_properties(size="28"))
    _append_text_run(paragraph, "- 12 81 00", _title_block_run_properties(size="28"))
    for extra in paragraphs[1:]:
        _clear_paragraph_content_keep_ppr(extra)


def _fit_sign_date_labels(root: etree._Element) -> None:
    # Word can clip italic descenders in these tiny title-block cells after the
    # frame is calibrated to the Contents-page border. Keep the cell geometry and
    # text box position intact; only trim the label typography so Sign/Date fit.
    for box_name in ("Text Box 79", "Text Box 80"):
        for shape in _textbox_shapes_by_name(root, box_name):
            for body_pr in shape.xpath(".//wps:bodyPr", namespaces=NS):
                body_pr.set("tIns", "9000")
                body_pr.set("bIns", "0")
            for spacing in shape.xpath(".//w:pPr/w:spacing", namespaces=NS):
                spacing.set(qn("w:line"), "180")
                spacing.set(qn("w:lineRule"), "exact")
            for size in shape.xpath(".//w:sz|.//w:szCs", namespaces=NS):
                size.set(qn("w:val"), "18")


def _clear_page_fields_outside_textbox83(root: etree._Element) -> None:
    textbox83 = set(_textbox83_shapes(root))
    for paragraph in root.xpath(".//w:txbxContent/w:p[.//w:instrText]", namespaces=NS):
        owner = next(
            (
                shape
                for shape in paragraph.xpath("ancestor::wps:wsp|ancestor::v:shape", namespaces=NS)
                if shape in textbox83
            ),
            None,
        )
        if owner is None:
            _clear_paragraph_content_keep_ppr(paragraph)


def _page_number_run_properties() -> etree._Element:
    rpr = etree.Element(qn("w:rPr"))
    fonts = etree.SubElement(rpr, qn("w:rFonts"))
    fonts.set(qn("w:ascii"), "ISOCPEUR")
    fonts.set(qn("w:hAnsi"), "ISOCPEUR")
    fonts.set(qn("w:eastAsia"), "ISOCPEUR")
    etree.SubElement(rpr, qn("w:i"))
    size = etree.SubElement(rpr, qn("w:sz"))
    size.set(qn("w:val"), "28")
    size_cs = etree.SubElement(rpr, qn("w:szCs"))
    size_cs.set(qn("w:val"), "28")
    position = etree.SubElement(rpr, qn("w:position"))
    position.set(qn("w:val"), str(LIVE_PAGE_FIELD_RUN_POSITION_HALF_POINTS))
    return rpr


def _style_page_field_runs(paragraph: etree._Element) -> None:
    for run in paragraph.xpath("./w:r", namespaces=NS):
        existing = run.find("w:rPr", namespaces=NS)
        if existing is not None:
            run.remove(existing)
        run.insert(0, copy.deepcopy(_page_number_run_properties()))


def _append_live_page_field_frame(root: etree._Element) -> None:
    paragraph = etree.SubElement(root, qn("w:p"))
    ppr = etree.SubElement(paragraph, qn("w:pPr"))
    frame_pr = etree.SubElement(ppr, qn("w:framePr"))
    frame_pr.set(qn("w:wrap"), "none")
    frame_pr.set(qn("w:hAnchor"), "page")
    frame_pr.set(qn("w:vAnchor"), "page")
    frame_pr.set(qn("w:x"), str(LIVE_PAGE_FIELD_X_TWIPS))
    frame_pr.set(qn("w:y"), str(LIVE_PAGE_FIELD_Y_TWIPS))
    frame_pr.set(qn("w:w"), str(LIVE_PAGE_FIELD_WIDTH_TWIPS))
    frame_pr.set(qn("w:h"), str(LIVE_PAGE_FIELD_HEIGHT_TWIPS))
    jc = etree.SubElement(ppr, qn("w:jc"))
    jc.set(qn("w:val"), "center")
    append_page_field_to_paragraph(paragraph, display="1")
    _style_page_field_runs(paragraph)


def _body_header_with_live_page_field(header_xml: bytes) -> bytes:
    root = parse_xml(header_xml)
    _remove_fallback_branches(root)
    _remove_standalone_page_paragraphs(root)
    _remove_floating_page_runs(root)
    _align_template1_frame_to_contents_outer_border(root)
    _send_template_frame_behind_text(root)
    _restore_template1_title_block_text(root)
    _fit_sign_date_labels(root)

    _clear_page_fields_outside_textbox83(root)
    text_boxes = _textbox83_shapes(root)
    if len(text_boxes) != 1:
        raise RuntimeError(f"Expected exactly one template_1 Text Box 83, found {len(text_boxes)}")
    for text_box in text_boxes:
        paragraphs = _paragraphs_inside(text_box)
        if not paragraphs:
            raise RuntimeError("Text Box 83 has no paragraph to clear")
        _clear_paragraph_content_keep_ppr(paragraphs[0])
        _remove_highlight_and_shading(text_box)
        for extra in paragraphs[1:]:
            _clear_paragraph_content_keep_ppr(extra)
    _remove_visible_field_instruction_runs(root)
    _remove_floating_page_runs(root)
    _append_live_page_field_frame(root)
    return serialize_xml(root)


def _copy_template_header_part(template_docx: Path, part_name: str) -> bytes:
    with ZipFile(template_docx) as zf:
        return zf.read(part_name)


def _copy_part_rels(
    final_package: dict[str, bytes],
    final_part_name: str,
    source_docx: Path,
    source_part_name: str,
) -> None:
    source_rels_name = f"word/_rels/{Path(source_part_name).name}.rels"
    final_rels_name = f"word/_rels/{Path(final_part_name).name}.rels"
    with ZipFile(source_docx) as zf:
        if source_rels_name not in zf.namelist():
            return
        final_package[final_rels_name] = zf.read(source_rels_name)
        rels_root = parse_xml(zf.read(source_rels_name))
        for rel in rels_root:
            target = rel.get("Target")
            if not target or target.startswith("http"):
                continue
            target_name = str((Path(source_part_name).parent / target).as_posix())
            if target_name in zf.namelist():
                final_package[target_name] = zf.read(target_name)


def _add_clean_body_header_footer(
    package: dict[str, bytes],
    document_rels_root: etree._Element,
    content_types_root: etree._Element,
    template_1: Path,
) -> tuple[str, str]:
    header_xml = _body_header_with_live_page_field(_copy_template_header_part(template_1, "word/header2.xml"))
    default_header_rid = add_header_footer_part(
        package, document_rels_root, content_types_root, "header", header_xml
    )
    default_footer_rid = add_header_footer_part(
        package, document_rels_root, content_types_root, "footer", blank_footer_xml()
    )
    return default_header_rid, default_footer_rid


def _set_section_from_template(
    target_sect_pr: etree._Element,
    template_sect_pr: etree._Element,
    *,
    section_type: str | None,
) -> None:
    parent = target_sect_pr.getparent()
    if parent is None:
        raise RuntimeError("Cannot replace detached section properties")
    replacement = copy.deepcopy(template_sect_pr)
    for ref in list(replacement):
        if ref.tag in {qn("w:headerReference"), qn("w:footerReference")}:
            replacement.remove(ref)
    remove_page_number_restart(replacement)
    set_section_break_type(replacement, section_type)
    parent.replace(target_sect_pr, replacement)


def _enforce_black_styles(package: dict[str, bytes]) -> None:
    styles_name = "word/styles.xml"
    if styles_name not in package:
        return
    root = parse_xml(package[styles_name])
    target_names = {
        "heading 1",
        "heading 2",
        "heading 3",
        "caption",
        "figure caption",
        "table caption",
        "contents title",
        "contents entry",
        "formula",
        "body text",
        "normal",
    }
    for style in root.xpath("//w:style", namespaces=NS):
        name_el = style.find("w:name", namespaces=NS)
        style_name = (name_el.get(qn("w:val"), "") if name_el is not None else "").lower()
        style_id = (style.get(qn("w:styleId")) or "").lower()
        if style_name not in target_names and style_id not in {name.replace(" ", "") for name in target_names}:
            continue
        rpr = style.find("w:rPr", namespaces=NS)
        if rpr is None:
            rpr = etree.SubElement(style, qn("w:rPr"))
        color = rpr.find("w:color", namespaces=NS)
        if color is None:
            color = etree.SubElement(rpr, qn("w:color"))
        color.attrib.clear()
        color.set(qn("w:val"), "000000")
    package[styles_name] = serialize_xml(root)


def _merge_template_styles(package: dict[str, bytes], template_docx_paths: list[Path]) -> None:
    styles_name = "word/styles.xml"
    if styles_name not in package:
        return
    target_root = parse_xml(package[styles_name])
    existing = {
        style.get(qn("w:styleId"))
        for style in target_root.xpath("//w:style", namespaces=NS)
        if style.get(qn("w:styleId"))
    }
    used = {
        item.get(qn("w:val"))
        for name, data in package.items()
        if name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer")
        for item in parse_xml(data).xpath(".//w:pStyle|.//w:rStyle", namespaces=NS)
        if item.get(qn("w:val"))
    }
    wanted = set(used)
    for template_docx in template_docx_paths:
        with ZipFile(template_docx) as zf:
            if styles_name not in zf.namelist():
                continue
            source_root = parse_xml(zf.read(styles_name))
        source_styles = {
            style.get(qn("w:styleId")): style
            for style in source_root.xpath("//w:style", namespaces=NS)
            if style.get(qn("w:styleId"))
        }
        queue = list(wanted)
        while queue:
            style_id = queue.pop()
            style = source_styles.get(style_id)
            if style is None:
                continue
            for ref in style.xpath("./w:basedOn|./w:link|./w:next", namespaces=NS):
                ref_id = ref.get(qn("w:val"))
                if ref_id and ref_id not in wanted:
                    wanted.add(ref_id)
                    queue.append(ref_id)
        for style_id in sorted(wanted):
            if style_id in existing:
                continue
            style = source_styles.get(style_id)
            if style is None:
                continue
            target_root.append(copy.deepcopy(style))
            existing.add(style_id)
    package[styles_name] = serialize_xml(target_root)


def _merge_template_fonts(package: dict[str, bytes], template_docx_paths: list[Path]) -> None:
    font_table_name = "word/fontTable.xml"
    if font_table_name not in package:
        return
    target_root = parse_xml(package[font_table_name])
    existing = {
        font.get(qn("w:name"))
        for font in target_root.xpath("//w:font", namespaces=NS)
        if font.get(qn("w:name"))
    }
    for template_docx in template_docx_paths:
        with ZipFile(template_docx) as zf:
            if font_table_name not in zf.namelist():
                continue
            source_root = parse_xml(zf.read(font_table_name))
        for font in source_root.xpath("//w:font", namespaces=NS):
            name = font.get(qn("w:name"))
            if name and name not in existing:
                target_root.append(copy.deepcopy(font))
                existing.add(name)
    package[font_table_name] = serialize_xml(target_root)


def postprocess_docx(
    raw_docx: Path,
    final_docx: Path,
    template_dir: Path = TEMPLATE_DIR,
) -> None:
    raw_docx = raw_docx.resolve()
    final_docx = final_docx.resolve()
    template_0 = template_dir / "template_0.docx"
    template_1 = template_dir / "template_1.docx"

    for path in [raw_docx, template_0, template_1]:
        if not path.exists():
            raise FileNotFoundError(path)

    package = read_docx(raw_docx)
    document_root = parse_xml(package["word/document.xml"])
    document_rels_root = parse_xml(package["word/_rels/document.xml.rels"])
    content_types_root = parse_xml(package["[Content_Types].xml"])

    sections = iter_section_properties(document_root)
    if len(sections) < 3:
        raise RuntimeError("Raw docx must contain cover, contents, and body sections.")

    contents_frame = _template_body_frame_elements(template_0)
    _normalize_contents_page_number_cells(contents_frame)
    _shift_template_frame_elements(
        contents_frame,
        FRAME_VISUAL_BALANCE_DX_EMU + FRAME_ALIGN_TO_BODY_DX_EMU,
        FRAME_ALIGN_TO_BODY_DY_EMU + CONTENTS_PAGE_FRAME_DY_EMU,
    )
    _scale_template_frame_elements_y(contents_frame, CONTENTS_PAGE_FRAME_SCALE_Y)
    _remap_template_relationships(contents_frame, package, document_rels_root, content_types_root, template_0)

    breaks = _section_break_paragraphs(document_root)
    if not breaks:
        raise RuntimeError("Cannot locate cover-to-contents section break")
    _insert_elements_after(breaks[0], contents_frame)

    cover_header_rid = add_header_footer_part(
        package,
        document_rels_root,
        content_types_root,
        "header",
        _template1_outer_frame_header(_copy_template_header_part(template_1, "word/header2.xml")),
    )
    cover_footer_rid = add_header_footer_part(
        package, document_rels_root, content_types_root, "footer", blank_footer_xml()
    )
    contents_header_rid = add_header_footer_part(
        package, document_rels_root, content_types_root, "header", blank_header_xml()
    )
    contents_footer_rid = add_header_footer_part(
        package, document_rels_root, content_types_root, "footer", blank_footer_xml()
    )
    body_header_rid, body_footer_rid = _add_clean_body_header_footer(
        package, document_rels_root, content_types_root, template_1
    )

    # Re-read section references after frame insertion. Frame elements can contain nested sectPr-like
    # data in text boxes, but direct section properties remain the section boundaries.
    sections = iter_section_properties(document_root)
    template_0_sect_pr = _template_sect_pr(template_0)
    template_1_sect_pr = _template_sect_pr(template_1)
    _set_section_from_template(sections[0], template_1_sect_pr, section_type="nextPage")
    _set_section_from_template(sections[1], template_0_sect_pr, section_type="nextPage")
    _set_section_from_template(sections[2], template_1_sect_pr, section_type=None)

    sections = iter_section_properties(document_root)
    _set_rules_text_margins(sections[2])
    set_header_footer_references(sections[0], cover_header_rid, cover_footer_rid)
    set_header_footer_references(sections[1], contents_header_rid, contents_footer_rid)
    set_header_footer_references(sections[2], body_header_rid, body_footer_rid)

    package["word/document.xml"] = serialize_xml(document_root)
    package["word/_rels/document.xml.rels"] = serialize_xml(document_rels_root)
    package["[Content_Types].xml"] = serialize_xml(content_types_root)
    _merge_template_styles(package, [template_0, template_1])
    _merge_template_fonts(package, [template_0, template_1])
    _enforce_black_styles(package)
    final_docx.parent.mkdir(parents=True, exist_ok=True)
    write_docx(final_docx, package)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_docx", type=Path)
    parser.add_argument("final_docx", type=Path)
    parser.add_argument("--template-dir", type=Path, default=TEMPLATE_DIR)
    args = parser.parse_args(argv)
    postprocess_docx(args.raw_docx, args.final_docx, args.template_dir)
    print(f"Wrote {args.final_docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
