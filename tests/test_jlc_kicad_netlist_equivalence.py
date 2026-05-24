from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "hardware/eda/tools/check_jlc_kicad_netlist_equivalence.py"
JLC_NETLIST = ROOT / "hardware/eda/jlc_netlist_altium.tel"
KICAD_SCH = ROOT / "hardware/kicad_schematic/esp32_temperature_control_unit.kicad_sch"
RULES = ROOT / "hardware/eda/net_equivalence_rules.yaml"


spec = importlib.util.spec_from_file_location("jlc_kicad_equivalence", CHECKER_PATH)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


def test_parse_jlc_tel_counts_and_canonical_nets() -> None:
    rules = checker.load_jsonish(RULES)
    connections = checker.parse_jlc_tel(JLC_NETLIST, rules)
    by_net = checker.connections_by_net(connections)
    assert len({connection.raw_net for connection in connections}) == 15
    assert len(by_net) == 14
    assert len(connections) == 57
    assert by_net["+3V3"] == {"A1.4", "C1.1", "C2.1", "DD1.2", "R1.1", "R2.1", "R3.1", "R6.1", "XS1.1", "XS4.4"}
    assert by_net["HEAT+"] == {"XS2.2", "XS5.1"}
    assert by_net["GND"] >= {"DD1.1", "DD1.38", "DD1.39", "XS3.2", "VT1.3"}


def test_parse_kicad_schematic_extracts_component_pin_nets() -> None:
    connections, metadata = checker.parse_kicad_schematic(KICAD_SCH)
    by_net = checker.connections_by_net(connections)
    assert not metadata["diagonal_wires"]
    assert not metadata["unlabelled_pins"]
    assert metadata["source"] == "kicad-cli sch export netlist --format kicadxml"
    assert by_net["+3V3"] == {"A1.4", "C1.1", "C2.1", "DD1.2", "R1.1", "R2.1", "R3.1", "R6.1", "XS1.1", "XS4.4"}
    assert by_net["GATE_R"] == {"R4.2", "R5.1", "VT1.1"}
    assert by_net["HEAT-"] == {"VT1.2", "XS2.1"}


def test_current_jlc_and_kicad_topology_are_equivalent() -> None:
    rules = checker.load_jsonish(RULES)
    jlc = checker.parse_jlc_tel(JLC_NETLIST, rules)
    kicad, metadata = checker.parse_kicad_schematic(KICAD_SCH)
    report = checker.compare_connections(jlc, kicad, rules, metadata)
    assert report["status"] == "PASS"
    assert report["summary"]["blocker_count"] == 0
    assert report["summary"]["unmapped_refs_count"] == 0
    assert report["summary"]["unmapped_nets_count"] == 0


def test_mismatched_net_fails() -> None:
    rules = checker.load_jsonish(RULES)
    jlc = checker.parse_jlc_tel(JLC_NETLIST, rules)
    kicad, metadata = checker.parse_kicad_schematic(KICAD_SCH)
    broken = []
    for connection in copy.deepcopy(kicad):
        if connection.ref == "R4" and connection.pin == "1":
            broken.append(checker.Connection(ref=connection.ref, pin=connection.pin, net="GND", raw_ref=connection.raw_ref, raw_pin=connection.raw_pin, raw_net=connection.raw_net))
        else:
            broken.append(connection)
    report = checker.compare_connections(jlc, broken, rules, metadata)
    codes = {blocker["code"] for blocker in report["blockers"]}
    assert report["status"] == "FAIL"
    assert "MISSING_COMPONENT_PIN_ON_NET" in codes
    assert "EXTRA_COMPONENT_PIN_ON_NET" in codes


def test_unmapped_jlc_net_fails(tmp_path: Path) -> None:
    rules = checker.load_jsonish(RULES)
    modified = tmp_path / "bad.tel"
    modified.write_text(JLC_NETLIST.read_text(encoding="utf-8").replace("'$1N14'", "'$UNKNOWN_NET'", 1), encoding="utf-8")
    jlc = checker.parse_jlc_tel(modified, rules)
    kicad, metadata = checker.parse_kicad_schematic(KICAD_SCH)
    report = checker.compare_connections(jlc, kicad, rules, metadata)
    assert report["status"] == "FAIL"
    assert "UNMAPPED_JLC_NET" in {blocker["code"] for blocker in report["blockers"]}


def test_pin_aliases_document_orientation_changes() -> None:
    rules = checker.load_jsonish(RULES)
    assert rules["pin_aliases"]["D1"] == {"1": "2", "2": "1"}
    assert rules["pin_aliases"]["U3_reset"] == {"2": "2", "4": "1"}
    assert rules["pin_aliases"]["U4_boot"] == {"1": "2", "3": "1"}
