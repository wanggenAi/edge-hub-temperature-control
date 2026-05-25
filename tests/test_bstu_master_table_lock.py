from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
FINAL_DRAWIO = ROOT / "hardware/eda/exports/final/esp32_temperature_control_unit_electrical_schematic.drawio"
KICAD_SVG = ROOT / "hardware/kicad_schematic/exports/esp32_temperature_control_unit_schematic.svg"
EMBED_SCRIPT = ROOT / "hardware/eda/tools/embed_kicad_schematic_into_bstu_frame.py"
UPDATE_ELEMENT_LIST_SCRIPT = ROOT / "hardware/eda/tools/update_generated_element_list.py"
UPDATE_TITLE_BLOCK_SCRIPT = ROOT / "hardware/eda/tools/update_generated_title_block.py"
VALIDATOR = ROOT / "hardware/eda/tools/validate_generated_tables_match_master.py"
EXPORT_LINT = ROOT / "tools/export_artifact_lint.py"
ELEMENT_PREFIX = "Evo6jcjRQjkPnHUFUJlg-"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_generated_tables_match_master", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def element_cell_geometry(root: ET.Element, suffix: str) -> tuple[float, float, float, float]:
    cell = root.find(f".//mxCell[@id='{ELEMENT_PREFIX}{suffix}']/mxGeometry")
    assert cell is not None
    return (
        float(cell.get("x", "0") or 0),
        float(cell.get("y", "0") or 0),
        float(cell.get("width", "0") or 0),
        float(cell.get("height", "0") or 0),
    )


def element_line_x(root: ET.Element, suffix: str) -> float:
    geometry = root.find(f".//mxCell[@id='{ELEMENT_PREFIX}{suffix}']/mxGeometry")
    assert geometry is not None
    point = geometry.find("mxPoint[@as='sourcePoint']")
    assert point is not None
    return float(point.get("x", "0") or 0)


def build_text_replaced_generated(tmp_path: Path) -> Path:
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
    return generated


def test_text_replacement_keeps_master_table_geometry(tmp_path: Path) -> None:
    generated = build_text_replaced_generated(tmp_path)
    validator = load_validator()
    master = validator.master_signature(FRAME)
    findings, summary = validator.compare_candidate(master, generated)
    assert findings == []
    assert summary["cell_ids_match"] is True
    assert summary["geometry_matches_master"] is True
    assert summary["value_changed_cell_count"] > 0


def test_master_element_list_has_mpn_readability_geometry() -> None:
    root = ET.parse(FRAME).find(".//root")
    assert root is not None
    table_x, _table_y, table_width, _table_height = element_cell_geometry(root, "1")
    first_grid = element_line_x(root, "3")
    second_grid = element_line_x(root, "4")
    third_grid = element_line_x(root, "5")
    assert table_width >= 850.0
    assert abs((table_x + table_width) - 3173.01) < 0.01
    assert first_grid - table_x >= 125.0
    assert second_grid - first_grid >= 500.0
    assert third_grid - second_grid >= 48.0
    assert table_x + table_width - third_grid >= 165.0
    name_x, _name_y, name_width, _name_height = element_cell_geometry(root, "14")
    note_x, _note_y, note_width, _note_height = element_cell_geometry(root, "16")
    assert name_x >= first_grid
    assert name_width >= 500.0
    assert note_x >= third_grid
    assert note_width >= 160.0


def test_validator_rejects_generated_table_geometry_change(tmp_path: Path) -> None:
    generated = build_text_replaced_generated(tmp_path)
    tree = ET.parse(generated)
    cell = tree.find(".//mxCell[@id='Evo6jcjRQjkPnHUFUJlg-1']/mxGeometry")
    assert cell is not None
    cell.set("height", str(float(cell.get("height", "0")) - 10.0))
    drifted = tmp_path / "drifted.drawio"
    tree.write(drifted, encoding="utf-8", xml_declaration=True)

    validator = load_validator()
    master = validator.master_signature(FRAME)
    findings, _summary = validator.compare_candidate(master, drifted)
    assert any(finding.code == "MASTER_TABLE_GEOMETRY_CHANGED" for finding in findings)


def test_validator_rejects_generated_table_line_width_change(tmp_path: Path) -> None:
    generated = build_text_replaced_generated(tmp_path)
    tree = ET.parse(generated)
    cell = tree.find(".//mxCell[@id='Evo6jcjRQjkPnHUFUJlg-2']")
    assert cell is not None
    style = cell.get("style", "")
    cell.set("style", style.replace("strokeWidth=3.937", "strokeWidth=9.999"))
    drifted = tmp_path / "line_width_drifted.drawio"
    tree.write(drifted, encoding="utf-8", xml_declaration=True)

    validator = load_validator()
    master = validator.master_signature(FRAME)
    findings, _summary = validator.compare_candidate(master, drifted)
    assert any(finding.code == "MASTER_TABLE_GEOMETRY_CHANGED" for finding in findings)


def test_committed_generated_and_final_tables_match_master_when_present() -> None:
    validator = load_validator()
    master = validator.master_signature(FRAME)
    for candidate in (GENERATED, FINAL_DRAWIO):
        if not candidate.exists():
            continue
        findings, summary = validator.compare_candidate(master, candidate)
        assert findings == []
        assert summary["geometry_matches_master"] is True


def test_export_lint_label_checks_master_table_lock() -> None:
    spec = importlib.util.spec_from_file_location("export_artifact_lint", EXPORT_LINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.is_final_kicad_embed_label("final-bstu-table-geometry")
    assert module.requires_esp32_bom_check("final-bstu-table-geometry")
    assert module.requires_esp32_title_block_check("final-bstu-table-geometry")
    assert module.requires_bstu_table_geometry_check("final-bstu-table-geometry")
