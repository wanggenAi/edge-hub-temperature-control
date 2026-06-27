from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.validate_title_block_geometry import validate


ROOT = Path(__file__).resolve().parents[1]
DRAWIO = ROOT / "hardware/gost-schematic/esp32_temperature_node_gost.drawio"
GENERATOR = ROOT / "hardware/gost-schematic/render_esp32_gost_schematic.js"
TEMPLATE = ROOT / "templates/gost_2_104_form1_title_block.yaml"


def generate_exact(tmp_path: Path) -> Path:
    subprocess.run(["node", str(GENERATOR)], cwd=ROOT, check=True)
    target = tmp_path / "exact.drawio"
    target.write_text(DRAWIO.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def mutate(path: Path, mutator) -> Path:
    tree = ET.ElementTree(ET.fromstring(path.read_text(encoding="utf-8")))
    mutator(tree)
    path.write_text(ET.tostring(tree.getroot(), encoding="unicode"), encoding="utf-8")
    return path


def cell(tree: ET.ElementTree, cell_id: str):
    found = tree.find(f".//mxCell[@id='{cell_id}']")
    assert found is not None
    return found


def geom(mx_cell):
    found = mx_cell.find("mxGeometry")
    assert found is not None
    return found


def assert_fails(path: Path, code: str):
    findings, _ = validate(path, TEMPLATE)
    codes = {finding.code for finding in findings if finding.level == "error"}
    assert code in codes


def test_title_block_rejects_scaled_table(tmp_path):
    path = generate_exact(tmp_path)

    def scale(tree):
        g = geom(cell(tree, "title_block.outer"))
        g.set("width", "180")
        g.set("height", "35")

    mutate(path, scale)
    assert_fails(path, "TITLE_BLOCK_CELL_SIZE_INVALID")


def test_title_block_rejects_wrong_cell_size(tmp_path):
    path = generate_exact(tmp_path)

    def resize_cell(tree):
        g = geom(cell(tree, "title_block.cell.document_code"))
        g.set("width", "69")

    mutate(path, resize_cell)
    assert_fails(path, "TITLE_BLOCK_CELL_SIZE_INVALID")


def test_title_block_rejects_wrong_position(tmp_path):
    path = generate_exact(tmp_path)

    def move(tree):
        g = geom(cell(tree, "title_block.outer"))
        g.set("x", "650")

    mutate(path, move)
    assert_fails(path, "TITLE_BLOCK_TEMPLATE_MISMATCH")


def test_title_block_rejects_small_font(tmp_path):
    path = generate_exact(tmp_path)

    def small_font(tree):
        text = cell(tree, "title_block.text.document_code")
        text.set("data-font_height_mm", "2.0")

    mutate(path, small_font)
    assert_fails(path, "TITLE_BLOCK_FONT_TOO_SMALL")


def test_title_block_rejects_freehand_table(tmp_path):
    path = generate_exact(tmp_path)

    def remove_metadata(tree):
        c = cell(tree, "title_block.cell.document_code")
        c.attrib.pop("data-role", None)

    mutate(path, remove_metadata)
    assert_fails(path, "TITLE_BLOCK_TEMPLATE_MISMATCH")


def test_title_block_passes_exact_template(tmp_path):
    path = generate_exact(tmp_path)
    findings, payload = validate(path, TEMPLATE)
    assert [finding for finding in findings if finding.level == "error"] == []
    assert payload["measured_title_block"] == {
        "x": 648.996,
        "y": 532.876,
        "width": 187.004,
        "height": 56.124,
        "right": 836.0,
        "bottom": 589.0,
    }
