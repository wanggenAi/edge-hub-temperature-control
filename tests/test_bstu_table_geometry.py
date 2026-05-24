from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
KICAD_SVG = ROOT / "hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg"
EMBED_SCRIPT = ROOT / "hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py"
UPDATE_ELEMENT_LIST_SCRIPT = ROOT / "hardware/eda/tools/update_generated_element_list.py"
UPDATE_TITLE_BLOCK_SCRIPT = ROOT / "hardware/eda/tools/update_generated_title_block.py"
REBUILD_TABLES_SCRIPT = ROOT / "hardware/eda/tools/rebuild_generated_tables.py"
RULES = ROOT / "hardware/eda/table_geometry_rules.yaml"
EXPORT_LINT = ROOT / "tools/export_artifact_lint.py"


def load_rebuilder():
    spec = importlib.util.spec_from_file_location("rebuild_generated_tables", REBUILD_TABLES_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def visible_text(path: Path) -> str:
    values: list[str] = []
    for cell in ET.parse(path).findall(".//mxCell"):
        value = cell.get("value", "")
        if value:
            values.append(value)
    return " ".join(values)


def build_generated_with_rebuilt_tables(tmp_path: Path) -> Path:
    generated = tmp_path / "generated.drawio"
    subprocess.run(
        [
            sys.executable,
            str(EMBED_SCRIPT),
            "--frame",
            str(FRAME),
            "--kicad-svg",
            str(KICAD_SVG),
            "--output",
            str(generated),
        ],
        check=True,
    )
    subprocess.run([sys.executable, str(UPDATE_ELEMENT_LIST_SCRIPT), "--input", str(generated), "--output", str(generated)], check=True)
    subprocess.run([sys.executable, str(UPDATE_TITLE_BLOCK_SCRIPT), "--input", str(generated), "--output", str(generated)], check=True)
    subprocess.run(
        [
            sys.executable,
            str(REBUILD_TABLES_SCRIPT),
            "--input",
            str(generated),
            "--output",
            str(generated),
            "--report",
            str(tmp_path / "table_report.md"),
            "--json-report",
            str(tmp_path / "table_report.json"),
        ],
        check=True,
    )
    return generated


def test_table_geometry_rules_are_strict_and_json_compatible() -> None:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    assert rules["element_list"]["columns"] == [
        {"id": "ref", "title": "Position number", "width": 150.0},
        {"id": "name", "title": "Name", "width": 340.0},
        {"id": "qty", "title": "Qty", "width": 68.0},
        {"id": "note", "title": "Note", "width": 172.0},
    ]
    assert rules["element_list"]["table_bbox"]["height"] == 1208.0
    assert rules["title_block"]["overall_mm"] == {"width": 185.0, "height": 55.0}
    assert rules["title_block"]["vertical_grid_mm"] == [0.0, 7.0, 17.0, 40.0, 55.0, 65.0, 135.0, 185.0]


def test_rebuild_tables_removes_legacy_table_objects_and_validates(tmp_path: Path) -> None:
    generated = build_generated_with_rebuilt_tables(tmp_path)
    root = ET.parse(generated).find(".//root")
    assert root is not None
    assert sum(1 for cell in root if cell.get("id", "").startswith("Evo6jcjRQjkPnHUFUJlg-")) == 0
    assert sum(1 for cell in root if cell.get("id", "").startswith("bstu.element_list.")) == 100
    assert sum(1 for cell in root if cell.get("id", "").startswith("bstu.title_block.")) == 39

    rebuilder = load_rebuilder()
    findings, summary = rebuilder.validate_tables(ET.parse(generated), rebuilder.load_rules(RULES))
    assert findings == []
    assert summary["status"] == "PASS"
    assert summary["element_list"]["actual_bbox"]["height"] == 1208.0
    assert summary["element_list"]["column_widths"] == [150.0, 340.0, 68.0, 172.0]


def test_rebuild_tables_rejects_column_width_drift(tmp_path: Path) -> None:
    generated = build_generated_with_rebuilt_tables(tmp_path)
    tree = ET.parse(generated)
    cell = tree.find(".//mxCell[@id='bstu.element_list.line.v.002']/mxGeometry/mxPoint[@as='sourcePoint']")
    assert cell is not None
    cell.set("x", str(float(cell.get("x", "0")) + 12.0))
    target = tree.find(".//mxCell[@id='bstu.element_list.line.v.002']/mxGeometry/mxPoint[@as='targetPoint']")
    assert target is not None
    target.set("x", cell.get("x", "0"))
    drifted = tmp_path / "drifted.drawio"
    tree.write(drifted, encoding="utf-8", xml_declaration=True)

    rebuilder = load_rebuilder()
    findings, _summary = rebuilder.validate_tables(ET.parse(drifted), rebuilder.load_rules(RULES))
    assert any(finding.code == "ELEMENT_LIST_COLUMN_WIDTH_INVALID" for finding in findings)


def test_rebuild_tables_rejects_title_block_cell_drift(tmp_path: Path) -> None:
    generated = build_generated_with_rebuilt_tables(tmp_path)
    tree = ET.parse(generated)
    geom = tree.find(".//mxCell[@id='bstu.title_block.text.document_code']/mxGeometry")
    assert geom is not None
    geom.set("width", str(float(geom.get("width", "0")) - 20.0))
    drifted = tmp_path / "title_drifted.drawio"
    tree.write(drifted, encoding="utf-8", xml_declaration=True)

    rebuilder = load_rebuilder()
    findings, _summary = rebuilder.validate_tables(ET.parse(drifted), rebuilder.load_rules(RULES))
    assert any(finding.code == "TITLE_BLOCK_CELL_SIZE_INVALID" for finding in findings)


def test_generated_drawio_has_rebuilt_table_geometry_when_present() -> None:
    if not GENERATED.exists():
        return
    rebuilder = load_rebuilder()
    findings, summary = rebuilder.validate_tables(ET.parse(GENERATED), rebuilder.load_rules(RULES))
    assert findings == []
    assert summary["status"] == "PASS"
    payload = visible_text(GENERATED)
    assert "Qty" in payload
    assert "Number" not in payload
    assert "BSTU.241297.006 Э3" in payload


def test_export_lint_label_enables_bstu_table_geometry_check() -> None:
    spec = importlib.util.spec_from_file_location("export_artifact_lint", EXPORT_LINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.is_final_kicad_embed_label("final-bstu-table-geometry")
    assert module.requires_esp32_bom_check("final-bstu-table-geometry")
    assert module.requires_esp32_title_block_check("final-bstu-table-geometry")
    assert module.requires_bstu_table_geometry_check("final-bstu-table-geometry")
