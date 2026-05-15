#!/usr/bin/env python3
"""Shared OOXML helpers for the thesis Word template system."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

NS = {
    "w": W_NS,
    "r": R_NS,
    "rel": REL_NS,
    "ct": CT_NS,
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "v": "urn:schemas-microsoft-com:vml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}


def qn(name: str) -> str:
    prefix, local = name.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def mm_to_twips(mm: float) -> int:
    return int(round(mm * 1440 / 25.4))


def pt_to_half_points(pt: float) -> int:
    return int(round(pt * 2))


def twips_to_mm(value: int | str | None) -> float | None:
    if value is None:
        return None
    return int(value) * 25.4 / 1440


@dataclass(frozen=True)
class LayoutRules:
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    left_margin_mm: float = 30.0
    right_margin_mm: float = 15.0
    top_margin_mm: float = 20.0
    bottom_margin_mm: float = 27.0
    header_distance_mm: float = 12.5
    footer_distance_mm: float = 17.0


LAYOUT = LayoutRules()


def parse_xml(data: bytes) -> etree._Element:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    return etree.fromstring(data, parser=parser)


def serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=False,
    )


def read_docx(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def write_docx(path: Path, package: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        for name, data in package.items():
            zf.writestr(name, data)


def iter_section_properties(document_root: etree._Element) -> list[etree._Element]:
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        return []
    sect_prs = body.xpath("./w:p/w:pPr/w:sectPr", namespaces=NS)
    final = body.find("w:sectPr", namespaces=NS)
    if final is not None:
        sect_prs.append(final)
    return sect_prs


def section_break_paragraphs(document_root: etree._Element) -> list[etree._Element]:
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        return []
    return body.xpath("./w:p[w:pPr/w:sectPr]", namespaces=NS)


def text_of(element: etree._Element) -> str:
    return "".join(element.itertext())


def child(parent: etree._Element, tag: str) -> etree._Element | None:
    return parent.find(tag, namespaces=NS)


def ensure_child(parent: etree._Element, tag: str) -> etree._Element:
    existing = child(parent, tag)
    if existing is not None:
        return existing
    new = etree.Element(qn(tag))
    parent.append(new)
    return new


def set_section_layout(sect_pr: etree._Element, rules: LayoutRules = LAYOUT) -> None:
    pg_sz = ensure_child(sect_pr, "w:pgSz")
    pg_sz.set(qn("w:w"), str(mm_to_twips(rules.page_width_mm)))
    pg_sz.set(qn("w:h"), str(mm_to_twips(rules.page_height_mm)))

    pg_mar = ensure_child(sect_pr, "w:pgMar")
    pg_mar.set(qn("w:top"), str(mm_to_twips(rules.top_margin_mm)))
    pg_mar.set(qn("w:right"), str(mm_to_twips(rules.right_margin_mm)))
    pg_mar.set(qn("w:bottom"), str(mm_to_twips(rules.bottom_margin_mm)))
    pg_mar.set(qn("w:left"), str(mm_to_twips(rules.left_margin_mm)))
    pg_mar.set(qn("w:header"), str(mm_to_twips(rules.header_distance_mm)))
    pg_mar.set(qn("w:footer"), str(mm_to_twips(rules.footer_distance_mm)))
    pg_mar.set(qn("w:gutter"), "0")


def remove_page_number_restart(sect_pr: etree._Element) -> None:
    pg_num = child(sect_pr, "w:pgNumType")
    if pg_num is not None:
        pg_num.attrib.pop(qn("w:start"), None)
        if not pg_num.attrib:
            sect_pr.remove(pg_num)


def set_section_break_type(sect_pr: etree._Element, value: str | None) -> None:
    typ = child(sect_pr, "w:type")
    if value is None:
        if typ is not None:
            sect_pr.remove(typ)
        return
    if typ is None:
        typ = etree.Element(qn("w:type"))
        sect_pr.insert(0, typ)
    typ.set(qn("w:val"), value)


def blank_header_xml() -> bytes:
    root = etree.Element(qn("w:hdr"), nsmap={"w": W_NS, "r": R_NS})
    etree.SubElement(root, qn("w:p"))
    return serialize_xml(root)


def blank_footer_xml() -> bytes:
    root = etree.Element(qn("w:ftr"), nsmap={"w": W_NS, "r": R_NS})
    etree.SubElement(root, qn("w:p"))
    return serialize_xml(root)


def next_numbered_part(package: dict[str, bytes], prefix: str, suffix: str = ".xml") -> str:
    pat = re.compile(rf"^word/{re.escape(prefix)}(\d+){re.escape(suffix)}$")
    used = [int(m.group(1)) for name in package for m in [pat.match(name)] if m]
    return f"word/{prefix}{(max(used) + 1) if used else 1}{suffix}"


def next_relationship_id(rels_root: etree._Element) -> str:
    used = []
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        rid = rel.get("Id", "")
        if rid.startswith("rId") and rid[3:].isdigit():
            used.append(int(rid[3:]))
    return f"rId{(max(used) + 1) if used else 1}"


def add_relationship(rels_root: etree._Element, rel_type_tail: str, target: str) -> str:
    rid = next_relationship_id(rels_root)
    rel = etree.SubElement(rels_root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", rid)
    rel.set(
        "Type",
        f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{rel_type_tail}",
    )
    rel.set("Target", target)
    return rid


def ensure_content_type(content_types_root: etree._Element, part_name: str, content_type: str) -> None:
    wanted = "/" + part_name if not part_name.startswith("/") else part_name
    for override in content_types_root.findall(f"{{{CT_NS}}}Override"):
        if override.get("PartName") == wanted:
            override.set("ContentType", content_type)
            return
    override = etree.SubElement(content_types_root, f"{{{CT_NS}}}Override")
    override.set("PartName", wanted)
    override.set("ContentType", content_type)


def add_header_footer_part(
    package: dict[str, bytes],
    rels_root: etree._Element,
    content_types_root: etree._Element,
    kind: str,
    xml_bytes: bytes,
) -> str:
    if kind not in {"header", "footer"}:
        raise ValueError(f"Unsupported part kind: {kind}")
    part_name = next_numbered_part(package, kind)
    package[part_name] = xml_bytes
    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
        if kind == "header"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
    )
    ensure_content_type(content_types_root, part_name, content_type)
    return add_relationship(rels_root, kind, Path(part_name).name)


def clear_header_footer_references(sect_pr: etree._Element) -> None:
    for ref in list(sect_pr):
        if ref.tag in {qn("w:headerReference"), qn("w:footerReference")}:
            sect_pr.remove(ref)


def set_header_footer_references(
    sect_pr: etree._Element,
    default_header_rid: str,
    default_footer_rid: str,
    even_header_rid: str | None = None,
    even_footer_rid: str | None = None,
) -> None:
    clear_header_footer_references(sect_pr)
    insert_at = 0
    refs: list[tuple[str, str, str]] = []
    if even_header_rid:
        refs.append(("headerReference", "even", even_header_rid))
    refs.append(("headerReference", "default", default_header_rid))
    if even_footer_rid:
        refs.append(("footerReference", "even", even_footer_rid))
    refs.append(("footerReference", "default", default_footer_rid))
    for tag, ref_type, rid in refs:
        ref = etree.Element(qn(f"w:{tag}"))
        ref.set(qn("w:type"), ref_type)
        ref.set(qn("r:id"), rid)
        sect_pr.insert(insert_at, ref)
        insert_at += 1


def remove_title_page_header_flag(sect_pr: etree._Element) -> None:
    title_pg = child(sect_pr, "w:titlePg")
    if title_pg is not None:
        sect_pr.remove(title_pg)


def make_field_run(instr: str, display: str = "1") -> list[etree._Element]:
    def run_with(child_el: etree._Element) -> etree._Element:
        run = etree.Element(qn("w:r"))
        run.append(child_el)
        return run

    begin = etree.Element(qn("w:fldChar"))
    begin.set(qn("w:fldCharType"), "begin")

    instr_text = etree.Element(qn("w:instrText"))
    instr_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr_text.text = f" {instr} "

    separate = etree.Element(qn("w:fldChar"))
    separate.set(qn("w:fldCharType"), "separate")

    display_text = etree.Element(qn("w:t"))
    display_text.text = display

    end = etree.Element(qn("w:fldChar"))
    end.set(qn("w:fldCharType"), "end")

    return [
        run_with(begin),
        run_with(instr_text),
        run_with(separate),
        run_with(display_text),
        run_with(end),
    ]


def append_page_field_to_paragraph(paragraph_el: etree._Element, display: str = "1") -> None:
    for run in make_field_run("PAGE", display):
        paragraph_el.append(run)


def replace_paragraph_with_page_field(paragraph_el: etree._Element, label: str = "") -> None:
    for child_el in list(paragraph_el):
        if child_el.tag != qn("w:pPr"):
            paragraph_el.remove(child_el)
    if label:
        run = etree.SubElement(paragraph_el, qn("w:r"))
        text = etree.SubElement(run, qn("w:t"))
        text.text = label
    append_page_field_to_paragraph(paragraph_el)


def has_page_field(root: etree._Element) -> bool:
    for instr in root.xpath(".//w:instrText", namespaces=NS):
        if instr.text and re.search(r"\bPAGE\b", instr.text):
            return True
    return False


def has_toc_field(root: etree._Element) -> bool:
    for instr in root.xpath(".//w:instrText", namespaces=NS):
        if instr.text and re.search(r"\bTOC\b", instr.text):
            return True
    return False


def normalize_page_fields(root: etree._Element, display: str = "1") -> None:
    """Ensure cached PAGE field display values are harmless placeholders."""
    in_page_field = False
    after_separate = False
    for el in root.iter():
        if el.tag == qn("w:instrText") and el.text and re.search(r"\bPAGE\b", el.text):
            in_page_field = True
            after_separate = False
        elif in_page_field and el.tag == qn("w:fldChar"):
            fld_type = el.get(qn("w:fldCharType"))
            if fld_type == "separate":
                after_separate = True
            elif fld_type == "end":
                in_page_field = False
                after_separate = False
        elif in_page_field and after_separate and el.tag == qn("w:t"):
            if el.text and el.text.strip().isdigit():
                el.text = display


def add_update_fields_setting(package: dict[str, bytes]) -> None:
    settings_name = "word/settings.xml"
    if settings_name not in package:
        root = etree.Element(qn("w:settings"), nsmap={"w": W_NS})
    else:
        root = parse_xml(package[settings_name])
    existing = child(root, "w:updateFields")
    if existing is None:
        existing = etree.Element(qn("w:updateFields"))
        root.insert(0, existing)
    existing.set(qn("w:val"), "true")
    package[settings_name] = serialize_xml(root)


def relationship_targets(package: dict[str, bytes]) -> dict[str, str]:
    rels_name = "word/_rels/document.xml.rels"
    if rels_name not in package:
        return {}
    root = parse_xml(package[rels_name])
    return {
        rel.get("Id"): rel.get("Target")
        for rel in root.findall(f"{{{REL_NS}}}Relationship")
        if rel.get("Id") and rel.get("Target")
    }


def section_ref_targets(package: dict[str, bytes], sect_pr: etree._Element) -> list[str]:
    targets = relationship_targets(package)
    found = []
    for ref in sect_pr.xpath("./w:headerReference|./w:footerReference", namespaces=NS):
        rid = ref.get(qn("r:id"))
        target = targets.get(rid)
        if target:
            found.append("word/" + target if not target.startswith("word/") else target)
    return found


def iter_document_paragraphs_xml(document_root: etree._Element) -> Iterable[etree._Element]:
    return document_root.xpath("//w:body//w:p", namespaces=NS)
