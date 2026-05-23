from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "tools/visual_schematic_lint.py"
FIXTURES = ROOT / "tests/fixtures"
LOCK = FIXTURES / "visual_reserved_regions.lock.json"
CONFIG = ROOT / "hardware/eda/style_rules_from_drawio.yaml"
REAL_LOCK = ROOT / "hardware/eda/reserved_regions.lock.json"
REAL_SOURCE = ROOT / "hardware/eda/functiondiagramYUANLITU.drawio"
REAL_GENERATED = ROOT / "hardware/eda/functiondiagramYUANLITU.generated.drawio"
RENDERER = ROOT / "hardware/eda/render_esp32_drawio.js"
CONFIRMED_REFS = {
    "DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1", "XS4",
    "R6", "SB2", "R4", "R5", "VT1", "XS2", "XS5", "A1", "XS3", "C3", "C4",
}
DISCRETE_SYMBOL_REFS = {
    "R1", "R2", "R3", "R4", "R5", "R6", "C1", "C2", "C3", "C4", "SB1", "SB2", "HL1", "VT1",
}
RECTANGULAR_TABLE_REFS = {
    "DD1", "A1", "XS1", "XS2", "XS3", "XS4", "XS5",
}
FORBIDDEN_VISIBLE_REFS = {
    "CN1", "U1", "Q1", "U3_reset", "U4_boot", "U3_buck", "U7",
    "J2_heater", "J_TS1", "J_Power",
}
REQUIRED_CANONICAL_NETS = {
    "+3V3", "+12V", "GND", "EN", "LED", "LED_A", "DQ", "RXD0", "TXD0",
    "BOOT", "GATE", "GATE_R", "HEAT+", "HEAT-",
}
FORBIDDEN_NET_NAMES = {
    "3V3", "+12 B", "+12B", "UART_GND", "GATE_DRV", "HEATER_PLUS", "HEATER_SW", "LED_SERIES",
}


def run_lint(path: Path, tmp_path: Path, *, lock: Path = LOCK, mode: str = "strict"):
    reports = tmp_path / "reports"
    proc = subprocess.run(
        [
            "python3",
            str(LINT),
            str(path),
            "--lock-file",
            str(lock),
            "--config",
            str(CONFIG),
            "--reports-dir",
            str(reports),
            "--mode",
            mode,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    payload_path = reports / "visual_schematic_lint.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {}
    return proc, payload


def codes(payload: dict) -> set[str]:
    return {finding["code"] for finding in payload.get("findings", []) if finding["severity"] == "error"}


def visible_values(drawio_text: str) -> set[str]:
    return set(re.findall(r'<mxCell\b[^>]*\bvalue="([^"]*)"', drawio_text))


def component_body_refs(drawio_text: str) -> set[str]:
    return set(re.findall(r'data-role="component_body"[^>]*data-ref="([^"]+)"', drawio_text))


def component_body_widths(drawio_text: str) -> list[str]:
    root = ET.fromstring(drawio_text)
    widths = []
    for cell in root.findall(".//mxCell"):
        if cell.get("data-role") != "component_body":
            continue
        geom = cell.find("mxGeometry")
        if geom is not None:
            widths.append(geom.get("width", ""))
    return widths


def component_body_info(drawio_text: str) -> dict[str, dict[str, str]]:
    root = ET.fromstring(drawio_text)
    info = {}
    for cell in root.findall(".//mxCell"):
        if cell.get("data-role") != "component_body":
            continue
        ref = cell.get("data-ref", "")
        geom = cell.find("mxGeometry")
        info[ref] = {
            "width": geom.get("width", "") if geom is not None else "",
            "style": cell.get("style", ""),
            "style_lock": cell.get("data-style-lock", ""),
            "symbol_type": cell.get("data-symbol-type", ""),
        }
    return info


def symbol_primitive_refs(drawio_text: str) -> set[str]:
    return set(re.findall(r'data-role="symbol_primitive"[^>]*data-ref="([^"]+)"', drawio_text))


def assert_fails(path_name: str, tmp_path: Path, *expected_codes: str):
    proc, payload = run_lint(FIXTURES / path_name, tmp_path)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    actual = codes(payload)
    for expected in expected_codes:
        assert expected in actual, f"{expected} missing from {sorted(actual)}"


def test_good_visual_fixture_passes(tmp_path):
    proc, payload = run_lint(FIXTURES / "good_visual_schematic.drawio", tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["error_count"] == 0


def test_real_template_mode_passes_locked_region_check(tmp_path):
    proc, payload = run_lint(REAL_SOURCE, tmp_path, lock=REAL_LOCK, mode="template")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["error_count"] == 0


def test_no_circuit_generated_copy_passes_strict_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--no-circuit",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["finalCircuitRendered"] is False
    assert output.exists()

    source_text = REAL_SOURCE.read_text(encoding="utf-8")
    generated_text = output.read_text(encoding="utf-8")
    assert 'data-role="reserved_container"' in generated_text
    assert 'id="OTuqVLYWGNuakiADof2M-2"' in source_text
    assert 'id="OTuqVLYWGNuakiADof2M-2"' not in generated_text
    for required in (
        "Capacitors",
        "Resistors",
        "ESP32-WROOM-32 module",
        "XH-3PA 3-pin sensor connector",
        "KF301-2P thermal switch terminal",
        "Qty.",
    ):
        assert required in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_dd1_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--dd1-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["finalCircuitRendered"] is False
    assert output.exists()

    generated_text = output.read_text(encoding="utf-8")
    assert 'id="generated.schematic.root"' in generated_text
    assert 'data-role="schematic_root"' in generated_text
    assert 'id="component.DD1.body"' in generated_text
    assert generated_text.count('data-role="pin"') == 10
    assert generated_text.count('data-role="pin_label"') == 10
    assert generated_text.count('data-role="wire"') == 10
    assert generated_text.count('data-role="net_label"') == 10
    for forbidden_ref in ("R1", "C1", "XS1", "VT1", "HL1", "SB1", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_pin_label_binding_uses_pin_number_for_duplicate_pin_names(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--dd1-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert "PIN_LABEL_MISALIGNED" not in codes(payload)
    generated_text = output.read_text(encoding="utf-8")
    assert 'data-pin="GND" data-pin-number="1"' in generated_text
    assert 'data-pin="GND" data-pin-number="38"' in generated_text


def test_reset_led_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--reset-led-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in ("DD1", "R1", "SB1", "R3", "HL1"):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("R2", "R4", "R5", "R6", "C1", "C2", "C3", "C4", "XS1", "XS2", "XS3", "XS4", "XS5", "VT1", "SB2", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    for required_net in ("EN", "LED", "LED_A", "+3V3"):
        assert f'data-net="{required_net}"' in generated_text
    assert 'id="pin.SB1.GND.4"' in generated_text
    assert 'id="wire.local.LED_A.R3_HL1"' in generated_text
    assert "netlabel.R3.LED_A" not in generated_text
    assert "netlabel.HL1.LED_A" not in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_decoupling_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--decoupling-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in ("DD1", "R1", "SB1", "R3", "HL1", "C1", "C2"):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("R2", "R4", "R5", "R6", "C3", "C4", "XS1", "XS2", "XS3", "XS4", "XS5", "VT1", "SB2", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    assert generated_text.count('data-ref="C1"') > 0
    assert generated_text.count('data-ref="C2"') > 0

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_sensor_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--sensor-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["sensorBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in ("DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1"):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("R4", "R5", "R6", "C3", "C4", "XS2", "XS3", "XS4", "XS5", "VT1", "SB2", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    assert 'id="wire.local.DQ.R2_XS1"' in generated_text
    assert "netlabel.R2.DQ" not in generated_text
    assert "netlabel.XS1.DQ" not in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_uart_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--uart-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["sensorBlockRendered"] is True
    assert summary["uartBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in ("DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1", "XS4"):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("R4", "R5", "R6", "C3", "C4", "XS2", "XS3", "XS5", "VT1", "SB2", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    for required_net in ("+3V3", "GND", "RXD0", "TXD0"):
        assert f'data-net="{required_net}"' in generated_text
    assert 'id="component.XS4.body"' in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_boot_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--boot-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["sensorBlockRendered"] is True
    assert summary["uartBlockRendered"] is True
    assert summary["bootBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in ("DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1", "XS4", "R6", "SB2"):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("R4", "R5", "C3", "C4", "XS2", "XS3", "XS5", "VT1", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    assert 'data-net="BOOT"' in generated_text
    assert 'id="component.R6.body"' in generated_text
    assert 'id="component.SB2.body"' in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_heater_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--heater-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["sensorBlockRendered"] is True
    assert summary["uartBlockRendered"] is True
    assert summary["bootBlockRendered"] is True
    assert summary["heaterBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in (
        "DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1", "XS4",
        "R6", "SB2", "R4", "R5", "VT1", "XS2", "XS5",
    ):
        assert f'data-ref="{required_ref}"' in generated_text
    for forbidden_ref in ("C3", "C4", "XS3", "A1"):
        assert f'data-ref="{forbidden_ref}"' not in generated_text
    for required_net in ("GATE", "GATE_R", "HEAT+", "HEAT-", "+12V", "GND"):
        assert f'data-net="{required_net}"' in generated_text
    assert 'id="component.VT1.body"' in generated_text
    assert 'id="component.XS5.body"' in generated_text
    assert 'id="wire.local.GATE_R.R4_VT1_R5"' in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_power_block_generated_copy_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--power-block",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["dd1BlockRendered"] is True
    assert summary["resetLedBlockRendered"] is True
    assert summary["decouplingBlockRendered"] is True
    assert summary["sensorBlockRendered"] is True
    assert summary["uartBlockRendered"] is True
    assert summary["bootBlockRendered"] is True
    assert summary["heaterBlockRendered"] is True
    assert summary["powerBlockRendered"] is True
    assert summary["finalCircuitRendered"] is False

    generated_text = output.read_text(encoding="utf-8")
    for required_ref in (
        "DD1", "R1", "SB1", "R3", "HL1", "C1", "C2", "R2", "XS1", "XS4",
        "R6", "SB2", "R4", "R5", "VT1", "XS2", "XS5", "A1", "XS3", "C3", "C4",
    ):
        assert f'data-ref="{required_ref}"' in generated_text
    for required_net in ("+12V", "+3V3", "GND"):
        assert f'data-net="{required_net}"' in generated_text
    assert 'id="component.A1.body"' in generated_text
    assert 'id="component.XS3.body"' in generated_text
    assert 'id="component.C3.body"' in generated_text
    assert 'id="component.C4.body"' in generated_text
    assert 'data-pin-number="3"' in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_layout_refinement_contains_exact_confirmed_components(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        [
            "node",
            str(RENDERER),
            "--write-output",
            "--layout-refinement",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["renderedStage"] == "middle_schematic_layout_refinement"
    assert summary["layoutRefinementRendered"] is True
    assert summary["finalCircuitRendered"] is False
    assert summary["changedLayoutOnly"] is True
    assert summary["generatedComponentsCount"] == 21
    assert summary["exportedArtifacts"] is False

    generated_text = output.read_text(encoding="utf-8")
    assert component_body_refs(generated_text) == CONFIRMED_REFS
    assert len(component_body_refs(generated_text)) == 21
    assert "shape=table;startSize=0;container=1" in generated_text
    assert 'data-style-lock="three_column_module_symbol"' in generated_text
    assert 'data-style-lock="standard_symbol_component"' in generated_text
    assert DISCRETE_SYMBOL_REFS.issubset(symbol_primitive_refs(generated_text))


def test_layout_refinement_component_widths_locked_to_reference(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated_text = output.read_text(encoding="utf-8")
    info = component_body_info(generated_text)
    assert set(info) == CONFIRMED_REFS
    assert {ref for ref, body in info.items() if body["width"] == "210"} == CONFIRMED_REFS
    for ref in RECTANGULAR_TABLE_REFS:
        assert "shape=table" in info[ref]["style"]
        assert info[ref]["style_lock"] == "three_column_module_symbol"
    for ref in DISCRETE_SYMBOL_REFS:
        assert "shape=table" not in info[ref]["style"]
        assert info[ref]["style_lock"] == "standard_symbol_component"


def test_heater_power_readability_polish_passes_generated_lint(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--heater-power-readability-polish", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["renderedStage"] == "heater_power_readability_polish"
    assert summary["heaterPowerReadabilityPolishRendered"] is True
    assert summary["generatedComponentsCount"] == 21

    generated_text = output.read_text(encoding="utf-8")
    assert component_body_refs(generated_text) == CONFIRMED_REFS
    info = component_body_info(generated_text)
    for ref in DISCRETE_SYMBOL_REFS:
        assert "shape=table" not in info[ref]["style"]
        assert ref in symbol_primitive_refs(generated_text)
    for ref in RECTANGULAR_TABLE_REFS:
        assert "shape=table" in info[ref]["style"]
        assert info[ref]["style_lock"] == "three_column_module_symbol"
    assert 'id="component.R4.body"' in generated_text
    assert 'id="component.A1.body"' in generated_text
    assert 'id="wire.local.HEAT-.VT1_XS2"' in generated_text

    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_local_zero_length_wire_fails(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--heater-power-readability-polish", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text(encoding="utf-8")
    text = re.sub(
        r'(<mxCell id="wire\.local\.GATE_R\.R5_bus"[\s\S]*?<mxPoint x=")1920(" y="1199" as="targetPoint"/>)',
        r'\g<1>1880\2',
        text,
        count=1,
    )
    output.write_text(text, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    assert "ZERO_LENGTH_WIRE" in codes(payload)


def test_local_wire_too_short_fails(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--heater-power-readability-polish", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text(encoding="utf-8")
    text = text.replace(
        '<mxPoint x="2225" y="1000" as="targetPoint"/>',
        '<mxPoint x="2185" y="1000" as="targetPoint"/>',
        1,
    )
    output.write_text(text, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    assert "LOCAL_WIRE_TOO_SHORT" in codes(payload)


def test_rectangular_component_freehand_style_fails(tmp_path):
    fixture = tmp_path / "bad_freehand_component.drawio"
    fixture.write_text(
        """<mxfile host="app.diagrams.net">
  <diagram id="bad-style" name="bad-style">
    <mxGraphModel page="1" pageWidth="3300" pageHeight="2339">
      <root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="frame.outer" value="" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="outer_frame"><mxGeometry x="79.74" y="7.74" width="3211.2" height="2322.83" as="geometry"/></mxCell>
        <mxCell id="element_list.lock" value="List of Elements" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="element_list"><mxGeometry x="2558.18" y="10.43" width="730" height="1260" as="geometry"/></mxCell>
        <mxCell id="title_block.lock" value="Title Block" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="title_block"><mxGeometry x="2555.18" y="2107.42" width="733.786" height="221" as="geometry"/></mxCell>
        <mxCell id="component.DD1.body" value="" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="component_body" data-generated="true" data-owner="test" data-ref="DD1" data-source-ref="U1" data-zone="esp32_controller"><mxGeometry x="940" y="640" width="150" height="90" as="geometry"/></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
""",
        encoding="utf-8",
    )
    proc, payload = run_lint(fixture, tmp_path, mode="generated")
    actual = codes(payload)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "COMPONENT_BODY_WIDTH_NOT_LOCKED" in actual
    assert "COMPONENT_STYLE_LOCK_MISSING" in actual
    assert "COMPONENT_BODY_STYLE_NOT_REFERENCE_TABLE" in actual


def test_discrete_component_table_style_fails(tmp_path):
    output = tmp_path / "bad_discrete_table_component.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text(encoding="utf-8")
    text = re.sub(
        r'(<mxCell id="component\.R1\.body" value="" style=")[^"]+(")',
        r'\1shape=table;startSize=0;container=1;fillColor=none;strokeColor=#000000;strokeWidth=1.9685;\2',
        text,
        count=1,
    )
    output.write_text(text, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    actual = codes(payload)
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    assert "FORBIDDEN_TABLE_STYLE_FOR_DISCRETE_SYMBOL" in actual


def test_discrete_component_missing_symbol_primitives_fails(tmp_path):
    output = tmp_path / "bad_missing_discrete_symbol.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text(encoding="utf-8")
    text = re.sub(r'\n\s*<mxCell id="symbol\.R1\.[^"]+"[\s\S]*?</mxCell>', "", text)
    output.write_text(text, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    actual = codes(payload)
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    assert "REQUIRED_SYMBOL_SHAPE_MISSING" in actual


def test_three_column_module_missing_divider_fails(tmp_path):
    output = tmp_path / "bad_missing_module_column.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text(encoding="utf-8")
    text = re.sub(r'\n\s*<mxCell id="component\.XS4\.table\.v\.left_pin_column"[\s\S]*?</mxCell>', "", text, count=1)
    output.write_text(text, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    actual = codes(payload)
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    assert "MODULE_LEFT_PIN_COLUMN_MISSING" in actual


def test_layout_refinement_contains_no_source_ref_as_displayed_ref(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    values = visible_values(output.read_text(encoding="utf-8"))
    assert values.isdisjoint(FORBIDDEN_VISIBLE_REFS)


def test_layout_refinement_contains_required_canonical_nets(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated_text = output.read_text(encoding="utf-8")
    for net in REQUIRED_CANONICAL_NETS:
        assert f'data-net="{net}"' in generated_text


def test_layout_refinement_rejects_stale_net_names(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated_text = output.read_text(encoding="utf-8")
    values = visible_values(generated_text)
    assert values.isdisjoint(FORBIDDEN_NET_NAMES)
    for net in FORBIDDEN_NET_NAMES:
        assert f'data-net="{net}"' not in generated_text


def test_layout_refinement_generated_objects_outside_reserved_regions(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert not (codes(payload) & {"SCHEMATIC_OVERLAPS_ELEMENT_LIST", "SCHEMATIC_OVERLAPS_TITLE_BLOCK"})


def test_layout_refinement_no_text_overlaps_wire(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert "TEXT_OVERLAPS_WIRE" not in codes(payload)


def test_layout_refinement_no_diagonal_wires(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert "DIAGONAL_WIRE" not in codes(payload)


def test_layout_refinement_source_template_unchanged(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    before = REAL_SOURCE.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = REAL_SOURCE.read_text(encoding="utf-8")
    assert before == after


def test_layout_refinement_does_not_export_svg_pdf_png(tmp_path):
    before = set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.svg"))
    before |= set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.pdf"))
    before |= set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.png"))
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.svg"))
    after |= set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.pdf"))
    after |= set(ROOT.joinpath("hardware/eda").glob("functiondiagramYUANLITU*.png"))
    assert after == before


def test_layout_refinement_generated_lint_passes(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode == 0, lint_proc.stdout + lint_proc.stderr
    assert payload["error_count"] == 0


def test_component_zone_violation_fails(tmp_path):
    fixture = tmp_path / "bad_component_zone.drawio"
    fixture.write_text(
        """<mxfile host="app.diagrams.net">
  <diagram id="bad-zone" name="bad-zone">
    <mxGraphModel page="1" pageWidth="3300" pageHeight="2339">
      <root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="frame.outer" value="" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="outer_frame"><mxGeometry x="79.74" y="7.74" width="3211.2" height="2322.83" as="geometry"/></mxCell>
        <mxCell id="element_list.lock" value="List of Elements" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="element_list"><mxGeometry x="2558.18" y="10.43" width="730" height="1260" as="geometry"/></mxCell>
        <mxCell id="title_block.lock" value="Title Block" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="title_block"><mxGeometry x="2555.18" y="2107.42" width="733.786" height="221" as="geometry"/></mxCell>
        <mxCell id="component.R1.body" value="" style="rounded=0;strokeColor=#000000;strokeWidth=1.9685;" parent="1" vertex="1" data-role="component_body" data-generated="true" data-owner="test" data-ref="R1" data-source-ref="R1" data-zone="reset_en"><mxGeometry x="1200" y="720" width="210" height="90" as="geometry"/></mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
""",
        encoding="utf-8",
    )
    proc, payload = run_lint(fixture, tmp_path, mode="generated")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "COMPONENT_ZONE_VIOLATION" in codes(payload)


def test_bad_locked_region_changed_fails(tmp_path):
    assert_fails("bad_locked_region_changed.drawio", tmp_path, "FRAME_CHANGED")


def test_bad_unclassified_object_fails(tmp_path):
    assert_fails("bad_unclassified_object.drawio", tmp_path, "UNCLASSIFIED_OBJECT")


def test_bad_wire_endpoint_gap_fails(tmp_path):
    assert_fails("bad_wire_endpoint_gap.drawio", tmp_path, "WIRE_ENDPOINT_NOT_CONNECTED")


def test_bad_floating_wire_fails(tmp_path):
    assert_fails("bad_floating_wire.drawio", tmp_path, "FLOATING_WIRE_END")


def test_bad_diagonal_wire_fails(tmp_path):
    assert_fails("bad_diagonal_wire.drawio", tmp_path, "DIAGONAL_WIRE")


def test_bad_pin_label_misaligned_fails(tmp_path):
    assert_fails("bad_pin_label_misaligned.drawio", tmp_path, "PIN_LABEL_MISALIGNED")


def test_bad_text_overlaps_wire_fails(tmp_path):
    assert_fails("bad_text_overlaps_wire.drawio", tmp_path, "TEXT_OVERLAPS_WIRE")


def test_bad_schematic_overlaps_reserved_region_fails(tmp_path):
    assert_fails(
        "bad_schematic_overlaps_reserved_region.drawio",
        tmp_path,
        "SCHEMATIC_OVERLAPS_ELEMENT_LIST",
    )


def test_generated_lint_rejects_missing_element_list_text(tmp_path):
    output = tmp_path / "functiondiagramYUANLITU.generated.drawio"
    proc = subprocess.run(
        ["node", str(RENDERER), "--write-output", "--layout-refinement", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    broken = output.read_text(encoding="utf-8")
    broken = re.sub(r'\n\s*<mxCell id="element_list\.[^"]+"[\s\S]*?</mxCell>', "", broken)
    output.write_text(broken, encoding="utf-8")
    lint_proc, payload = run_lint(output, tmp_path, lock=REAL_LOCK, mode="generated")
    assert lint_proc.returncode != 0, lint_proc.stdout + lint_proc.stderr
    actual = codes(payload)
    assert "ELEMENT_LIST_CONTENT_MISSING" in actual
    assert "ELEMENT_LIST_LINES_MISSING" in actual
