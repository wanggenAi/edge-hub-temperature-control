"""Minimal V1 reference and parameter model for the enclosure workflow.

The goal of this module is to keep the wiring-first prototype simple:
- trust the PCB exports for board size and 3D envelope
- keep only the mechanical constraints needed for a first useful print
- postpone product-like helper details until later revisions
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PCB_REFERENCE_DIR = PROJECT_ROOT / "references" / "pcb"


REFERENCE_FILES = {
    "pcb_step": PCB_REFERENCE_DIR / "3D_PCB1_2026-04-05.step",
    "pcb_dxf": PCB_REFERENCE_DIR / "DXF_PCB1_2026-04-05_AutoCAD2007.dxf",
}


DXF_REFERENCE = {
    "board_outline_layer": "Board-Outline-Layer",
    "board_min_x": -49.784099568199146,
    "board_min_y": -44.47408940817883,
    "board_max_x": 35.21607061214123,
    "board_max_y": 17.526035052070107,
}


STEP_REFERENCE = {
    "model_min_x": -49.77139954279001,
    "model_min_y": -44.46138938277,
    "model_max_x": 35.20337058674101,
    "model_max_y": 17.51333502667,
    "model_min_z": -1.8999492777484623,
    "model_max_z": 11.700050822250999,
    "board_bottom_z": 0.0,
    "board_top_z": 1.6,
}


PCB_REFERENCE = {
    "board_thickness": 1.6,
    "board_length": DXF_REFERENCE["board_max_x"] - DXF_REFERENCE["board_min_x"],
    "board_width": DXF_REFERENCE["board_max_y"] - DXF_REFERENCE["board_min_y"],
    "max_component_height_top": 18.0,
    "max_component_height_bottom": 3.0,
}


REFERENCE_ALIGNMENT = {
    "normalize_dxf_to_board_origin": True,
    "normalize_step_xy_to_board_origin": True,
    "step_translation": (0.0, 0.0, 0.0),
    "show_step_reference": True,
}


# Group 1: thermal-experiment hard constraints.
THERMAL_CONSTRAINTS = {
    # Small chamber volume is easier to heat, control, and validate in V1.
    "chamber_inner_length": 102.0,
    "chamber_inner_width": 74.0,
    "chamber_inner_height": 40.0,
    # Simple heater zone at the back of the chamber.
    "heater_pad_length": 56.0,
    "heater_pad_width": 18.0,
    "heater_pad_thickness": 2.0,
    "heater_body_length": 52.0,
    "heater_body_width": 16.0,
    "heater_body_thickness": 1.6,
    "heater_zone_back_gap": 6.0,
    # V1 uses the chamber floor directly as the sample area.
    "sample_area_length": 62.0,
    "sample_area_width": 42.0,
    "sample_area_front_gap": 10.0,
    # Sensor should live near the sample region, away from the heater face.
    "sensor_probe_height": 22.0,
    "sensor_probe_front_gap": 18.0,
}


# Group 2: wiring/service hard constraints.
SERVICE_CONSTRAINTS = {
    # Debug access needs finger room, not just pin-hole room.
    "debug_opening_width": 32.0,
    "debug_opening_height": 18.0,
    "debug_opening_z_offset": 13.0,
    # Power side gets its own larger access window.
    "power_opening_width": 32.0,
    "power_opening_height": 18.0,
    "power_opening_z_offset": 13.0,
    # Dedicated side opening for J_TS1 external thermal protection switch wiring.
    "ts1_opening_width": 22.0,
    "ts1_opening_height": 14.0,
    "ts1_opening_z_offset": 20.0,
    "ts1_opening_y_offset": 52.0,
    # Divider pass-throughs let heater and sensor wiring go straight up.
    "sensor_passage_diameter": 5.0,
    "heater_passage_diameter": 7.0,
    "sensor_passage_ring_diameter": 10.0,
    "heater_passage_ring_diameter": 13.0,
}


# Group 3: V1-adjustable geometry parameters.
V1_GEOMETRY = {
    "wall_thickness": 2.4,
    "base_thickness": 2.8,
    "divider_thickness": 2.4,
    "lid_thickness": 2.4,
    "corner_radius": 4.0,
    "electronics_inner_height": 24.0,
    "electronics_cover_thickness": 2.4,
    "electronics_cover_gap": 6.0,
    "electronics_cover_margin_x": 8.0,
    "electronics_cover_margin_y": 6.0,
    # Show both lid states for CQ-editor, but do not over-complicate the lid.
    "lid_display_gap": 10.0,
    "lid_insert_depth": 6.0,
    "lid_insert_clearance": 0.35,
    "lid_seat_thickness": 2.0,
    # PCB retention is intentionally simple for V1.
    "pcb_floor_clearance": 3.0,
    "pcb_shelf_thickness": 2.4,
    "pcb_stop_height": 6.0,
    # Board placement is wiring-first: debug side to the left, power side right.
    "pcb_offset_x": 10.0,
    "pcb_offset_y": 6.0,
    # Simple service landings inside the electronics bay.
    "power_pad_length": 22.0,
    "power_pad_width": 18.0,
    "power_pad_thickness": 2.0,
}


VIEW_OPTIONS = {
    "enclosure_alpha": 0.22,
    "lid_alpha": 0.35,
    "board_alpha": 0.80,
    "step_alpha": 0.42,
    "helper_alpha": 0.82,
}


DISPLAY_OPTIONS = {
    "show_lid": True,
    "show_board_proxy": True,
    "show_step_reference": True,
    "show_thermal_helpers": True,
    "show_service_helpers": True,
}
