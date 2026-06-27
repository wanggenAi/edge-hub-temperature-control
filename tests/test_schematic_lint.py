from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "tools/schematic_lint.py"
RULES = ROOT / "tools/schematic_rules.yaml"
FIXTURES = ROOT / "tests/fixtures"
GOOD = FIXTURES / "good_expected_layout.drawio"


def run_lint(path: Path, tmp_path: Path):
    reports = tmp_path / "reports"
    proc = subprocess.run(
        ["python3", str(LINT), str(path), "--config", str(RULES), "--reports-dir", str(reports), "--skip-exports"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    payload = {}
    report = reports / "schematic_lint.json"
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
    return proc, payload


def mutate_good(tmp_path: Path, mutator) -> Path:
    target = tmp_path / "mutated.drawio"
    target.write_text(GOOD.read_text(encoding="utf-8"), encoding="utf-8")
    tree = ET.ElementTree(ET.fromstring(target.read_text(encoding="utf-8")))
    mutator(tree)
    target.write_text(ET.tostring(tree.getroot(), encoding="unicode"), encoding="utf-8")
    return target


def cell(tree: ET.ElementTree, cell_id: str):
    found = tree.find(f".//mxCell[@id='{cell_id}']")
    assert found is not None, cell_id
    return found


def geom(mx_cell):
    found = mx_cell.find("mxGeometry")
    assert found is not None
    return found


def codes(payload: dict) -> set[str]:
    return {finding["code"] for finding in payload.get("findings", []) if finding["severity"] == "error"}


def assert_lint_fails(path: Path, tmp_path: Path, *expected_codes: str):
    proc, payload = run_lint(path, tmp_path)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    actual = codes(payload)
    for code in expected_codes:
        assert code in actual, f"{code} missing from {sorted(actual)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_bad_current_layout_fails(tmp_path):
    assert_lint_fails(
        FIXTURES / "bad_current_gost_layout.drawio",
        tmp_path,
        "WIRE_PIN_GAP",
        "FLOATING_WIRE_END",
        "PIN_LABEL_MISALIGNED",
        "PIN_LABEL_TOO_FAR_FROM_PIN",
        "TITLE_BLOCK_TEMPLATE_MISMATCH",
        "TITLE_BLOCK_CELL_SIZE_INVALID",
        "TITLE_BLOCK_LINE_WIDTH_INVALID",
        "ELEMENT_LIST_WIDTH_INVALID",
        "ELEMENT_LIST_COLUMN_WIDTH_INVALID",
        "ELEMENT_LIST_LINE_WIDTH_INCONSISTENT",
        "ELEMENT_LIST_WRONG_POSITION",
        "TABLE_TEXT_LINE_OVERLAP",
        "SCHEMATIC_TEXT_WIRE_OVERLAP",
        "COMPONENT_PIN_WIRE_NOT_ORTHOGONAL",
    )


def test_title_block_exact_template(tmp_path):
    assert_lint_fails(FIXTURES / "bad_title_block_wrong_cells.drawio", tmp_path, "TITLE_BLOCK_CELL_SIZE_INVALID")


def test_title_block_rejects_freehand_table(tmp_path):
    def remove_metadata(tree):
        c = cell(tree, "title_block.cell.document_code")
        c.attrib.pop("data-role", None)

    path = mutate_good(tmp_path, remove_metadata)
    assert_lint_fails(path, tmp_path, "TITLE_BLOCK_TEMPLATE_MISMATCH")


def test_element_list_exact_columns(tmp_path):
    def wrong_column(tree):
        g = geom(cell(tree, "element_list.cell.C1.description"))
        g.set("width", "100")

    path = mutate_good(tmp_path, wrong_column)
    assert_lint_fails(path, tmp_path, "ELEMENT_LIST_COLUMN_WIDTH_INVALID")


def test_element_list_line_widths(tmp_path):
    assert_lint_fails(FIXTURES / "bad_list_of_elements_line_width.drawio", tmp_path, "ELEMENT_LIST_LINE_WIDTH_INVALID")


def test_pin_label_alignment(tmp_path):
    def move_label(tree):
        g = geom(cell(tree, "component.DD1.pinlabel.DD1_3"))
        g.set("x", str(float(g.attrib["x"]) + 2.0))

    path = mutate_good(tmp_path, move_label)
    assert_lint_fails(path, tmp_path, "PIN_LABEL_MISALIGNED")


def test_wire_must_touch_pin(tmp_path):
    assert_lint_fails(FIXTURES / "bad_disconnected_wires.drawio", tmp_path, "WIRE_PIN_GAP")


def test_no_floating_wire_end(tmp_path):
    def float_wire(tree):
        wire = cell(tree, "wire.EN.EN.reset.001.001")
        g = geom(wire)
        g.find("mxPoint[@as='sourcePoint']").set("x", "128")

    path = mutate_good(tmp_path, float_wire)
    assert_lint_fails(path, tmp_path, "FLOATING_WIRE_END")


def test_junction_required(tmp_path):
    def remove_junction(tree):
        root = tree.getroot()
        parent = root.find(".//root")
        target = root.find(".//mxCell[@id='junction.GATE_R.002']")
        assert target is not None
        parent.remove(target)

    path = mutate_good(tmp_path, remove_junction)
    assert_lint_fails(path, tmp_path, "MISSING_JUNCTION_DOT")


def test_no_unknown_text(tmp_path):
    def add_unknown_text(tree):
        root = tree.find(".//root")
        root.append(ET.fromstring('<mxCell id="free.note" value="Extra note" style="text;html=1;strokeColor=none;fillColor=none;fontSize=3;rotation=0;" parent="1" vertex="1" data-kind="free_text" data-role="free_text"><mxGeometry x="50" y="50" width="30" height="8" as="geometry"/></mxCell>'))

    path = mutate_good(tmp_path, add_unknown_text)
    assert_lint_fails(path, tmp_path, "UNCLASSIFIED_OBJECT", "TEXT_OUTSIDE_ALLOWED_REGION")


def test_forbid_cyrillic_except_e3(tmp_path):
    def add_russian(tree):
        c = cell(tree, "element_list.text.header.description")
        c.set("value", "Перечень элементов")

    path = mutate_good(tmp_path, add_russian)
    assert_lint_fails(path, tmp_path, "CYRILLIC_FORBIDDEN")


def test_bom_quantity_match(tmp_path):
    def bad_qty(tree):
        c = cell(tree, "element_list.text.C2_C4.qty")
        c.set("value", "1")

    path = mutate_good(tmp_path, bad_qty)
    assert_lint_fails(path, tmp_path, "ELEMENT_LIST_QTY_MISMATCH")


def test_good_template_passes(tmp_path):
    proc, payload = run_lint(GOOD, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["error_count"] == 0
