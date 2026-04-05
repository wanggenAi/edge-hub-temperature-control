"""CQ-editor entry point for the simplified wiring-first enclosure V1."""

from __future__ import annotations

import cadquery as cq

from pcb_reference import (
    DISPLAY_OPTIONS,
    DXF_REFERENCE,
    PCB_REFERENCE,
    PROJECT_ROOT,
    REFERENCE_ALIGNMENT,
    REFERENCE_FILES,
    SERVICE_CONSTRAINTS,
    STEP_REFERENCE,
    THERMAL_CONSTRAINTS,
    V1_GEOMETRY,
    VIEW_OPTIONS,
)


PCB_REFERENCE_DIR = PROJECT_ROOT / "references" / "pcb"


def normalize_board_xy(model: cq.Workplane) -> cq.Workplane:
    if not REFERENCE_ALIGNMENT["normalize_dxf_to_board_origin"]:
        return model
    return model.translate(
        (-DXF_REFERENCE["board_min_x"], -DXF_REFERENCE["board_min_y"], 0.0)
    )


def normalize_step_xy(model: cq.Workplane) -> cq.Workplane:
    if not REFERENCE_ALIGNMENT["normalize_step_xy_to_board_origin"]:
        return model
    return model.translate(
        (-STEP_REFERENCE["model_min_x"], -STEP_REFERENCE["model_min_y"], 0.0)
    )


WALL = V1_GEOMETRY["wall_thickness"]
BASE = V1_GEOMETRY["base_thickness"]
DIVIDER = V1_GEOMETRY["divider_thickness"]
LID = V1_GEOMETRY["lid_thickness"]
ELEC_COVER = V1_GEOMETRY["electronics_cover_thickness"]

CHAMBER_L = THERMAL_CONSTRAINTS["chamber_inner_length"]
CHAMBER_W = THERMAL_CONSTRAINTS["chamber_inner_width"]
CHAMBER_H = THERMAL_CONSTRAINTS["chamber_inner_height"]
ELEC_H = V1_GEOMETRY["electronics_inner_height"]

OUTER_L = CHAMBER_L + WALL * 2.0
OUTER_W = CHAMBER_W + WALL * 2.0
OUTER_H = BASE + ELEC_H + DIVIDER + CHAMBER_H

CHAMBER_FLOOR_Z = BASE + ELEC_H
CHAMBER_ORIGIN = (WALL, WALL, CHAMBER_FLOOR_Z + DIVIDER)

PCB_MODEL_OFFSET = (
    WALL + V1_GEOMETRY["pcb_offset_x"],
    WALL + V1_GEOMETRY["pcb_offset_y"],
    BASE + V1_GEOMETRY["pcb_floor_clearance"],
)

POWER_PAD_ORIGIN = (
    OUTER_L - WALL - V1_GEOMETRY["power_pad_length"] - 5.0,
    WALL + 10.0,
    BASE + 6.0,
)
TS1_SERVICE_PAD_ORIGIN = (
    OUTER_L - WALL - 24.0,
    SERVICE_CONSTRAINTS["ts1_opening_y_offset"] - 10.0,
    BASE + 6.0,
)

SAMPLE_AREA_ORIGIN = (
    WALL + 10.0,
    WALL + THERMAL_CONSTRAINTS["sample_area_front_gap"],
    CHAMBER_FLOOR_Z + DIVIDER + 0.2,
)

HEATER_PAD_ORIGIN = (
    WALL + CHAMBER_L - THERMAL_CONSTRAINTS["heater_pad_length"] - 10.0,
    WALL + CHAMBER_W - THERMAL_CONSTRAINTS["heater_pad_width"] - THERMAL_CONSTRAINTS["heater_zone_back_gap"],
    CHAMBER_FLOOR_Z + DIVIDER + 4.0,
)

SENSOR_PASSAGE_XY = (
    WALL + 20.0,
    WALL + THERMAL_CONSTRAINTS["sensor_probe_front_gap"],
)
HEATER_PASSAGE_XY = (
    HEATER_PAD_ORIGIN[0] + THERMAL_CONSTRAINTS["heater_pad_length"] - 8.0,
    HEATER_PAD_ORIGIN[1] + THERMAL_CONSTRAINTS["heater_pad_width"] / 2.0,
)

DEBUG_OPENING_CENTER = (
    WALL + 18.0,
    BASE + SERVICE_CONSTRAINTS["debug_opening_z_offset"],
)
POWER_OPENING_CENTER = (
    WALL + 18.0,
    BASE + SERVICE_CONSTRAINTS["power_opening_z_offset"],
)
TS1_OPENING_CENTER = (
    SERVICE_CONSTRAINTS["ts1_opening_y_offset"],
    BASE + SERVICE_CONSTRAINTS["ts1_opening_z_offset"],
)

ELECTRONICS_COVER_ORIGIN = (
    V1_GEOMETRY["electronics_cover_margin_x"],
    V1_GEOMETRY["electronics_cover_margin_y"],
    -ELEC_COVER - V1_GEOMETRY["electronics_cover_gap"],
)


def rounded_box(length: float, width: float, height: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, width, height, centered=(False, False, False))
        .edges("|Z")
        .fillet(V1_GEOMETRY["corner_radius"])
    )


def build_board_proxy() -> cq.Workplane:
    dxf_path = REFERENCE_FILES["pcb_dxf"]
    if dxf_path.exists():
        try:
            outline = cq.importers.importDXF(
                str(dxf_path),
                include=[DXF_REFERENCE["board_outline_layer"]],
            )
            outline = normalize_board_xy(outline)
            return outline.wires().toPending().extrude(PCB_REFERENCE["board_thickness"])
        except Exception:
            pass

    return (
        cq.Workplane("XY")
        .box(
            PCB_REFERENCE["board_length"],
            PCB_REFERENCE["board_width"],
            PCB_REFERENCE["board_thickness"],
            centered=(False, False, False),
        )
    )


def build_enclosure_body() -> cq.Workplane:
    body = rounded_box(OUTER_L, OUTER_W, OUTER_H)

    electronics_void = (
        cq.Workplane("XY")
        .box(
            OUTER_L - WALL * 2.0,
            OUTER_W - WALL * 2.0,
            ELEC_H,
            centered=(False, False, False),
        )
        .translate((WALL, WALL, BASE))
    )
    chamber_void = (
        cq.Workplane("XY")
        .box(CHAMBER_L, CHAMBER_W, CHAMBER_H, centered=(False, False, False))
        .translate(CHAMBER_ORIGIN)
    )
    body = body.cut(electronics_void).cut(chamber_void)

    electronics_access_opening = (
        cq.Workplane("XY")
        .box(
            OUTER_L - V1_GEOMETRY["electronics_cover_margin_x"] * 2.0,
            OUTER_W - V1_GEOMETRY["electronics_cover_margin_y"] * 2.0,
            BASE + 0.8,
            centered=(False, False, False),
        )
        .translate(
            (
                V1_GEOMETRY["electronics_cover_margin_x"],
                V1_GEOMETRY["electronics_cover_margin_y"],
                -0.4,
            )
        )
    )
    body = body.cut(electronics_access_opening)

    debug_opening = (
        cq.Workplane("YZ")
        .center(*DEBUG_OPENING_CENTER)
        .rect(
            SERVICE_CONSTRAINTS["debug_opening_width"],
            SERVICE_CONSTRAINTS["debug_opening_height"],
        )
        .extrude(WALL * 2.0)
    )
    body = body.cut(debug_opening)

    power_opening = (
        cq.Workplane("YZ")
        .center(*POWER_OPENING_CENTER)
        .rect(
            SERVICE_CONSTRAINTS["power_opening_width"],
            SERVICE_CONSTRAINTS["power_opening_height"],
        )
        .extrude(WALL * 2.0)
        .translate((OUTER_L - WALL * 2.0, 0.0, 0.0))
    )
    body = body.cut(power_opening)

    ts1_opening = (
        cq.Workplane("YZ")
        .center(*TS1_OPENING_CENTER)
        .rect(
            SERVICE_CONSTRAINTS["ts1_opening_width"],
            SERVICE_CONSTRAINTS["ts1_opening_height"],
        )
        .extrude(WALL * 2.0)
        .translate((OUTER_L - WALL * 2.0, 0.0, 0.0))
    )
    body = body.cut(ts1_opening)

    for center, diameter in (
        (SENSOR_PASSAGE_XY, SERVICE_CONSTRAINTS["sensor_passage_diameter"]),
        (HEATER_PASSAGE_XY, SERVICE_CONSTRAINTS["heater_passage_diameter"]),
    ):
        passage = (
            cq.Workplane("XY")
            .center(*center)
            .circle(diameter / 2.0)
            .extrude(DIVIDER + 0.8)
            .translate((0.0, 0.0, CHAMBER_FLOOR_Z - 0.4))
        )
        body = body.cut(passage)

    seat_outer = (
        cq.Workplane("XY")
        .box(
            OUTER_L - WALL * 2.0,
            OUTER_W - WALL * 2.0,
            V1_GEOMETRY["lid_insert_depth"],
            centered=(False, False, False),
        )
        .translate((WALL, WALL, OUTER_H - V1_GEOMETRY["lid_insert_depth"]))
    )
    seat_inner = (
        cq.Workplane("XY")
        .box(
            OUTER_L - WALL * 2.0 - V1_GEOMETRY["lid_seat_thickness"] * 2.0,
            OUTER_W - WALL * 2.0 - V1_GEOMETRY["lid_seat_thickness"] * 2.0,
            V1_GEOMETRY["lid_insert_depth"],
            centered=(False, False, False),
        )
        .translate(
            (
                WALL + V1_GEOMETRY["lid_seat_thickness"],
                WALL + V1_GEOMETRY["lid_seat_thickness"],
                OUTER_H - V1_GEOMETRY["lid_insert_depth"],
            )
        )
    )
    return body.cut(seat_outer.cut(seat_inner))


def build_lid(z_gap: float) -> cq.Workplane:
    lid_shell = rounded_box(OUTER_L, OUTER_W, LID)
    insert_rim = (
        cq.Workplane("XY")
        .box(
            OUTER_L - WALL * 2.0 - V1_GEOMETRY["lid_insert_clearance"] * 2.0,
            OUTER_W - WALL * 2.0 - V1_GEOMETRY["lid_insert_clearance"] * 2.0,
            V1_GEOMETRY["lid_insert_depth"],
            centered=(False, False, False),
        )
        .translate(
            (
                WALL + V1_GEOMETRY["lid_insert_clearance"],
                WALL + V1_GEOMETRY["lid_insert_clearance"],
                -V1_GEOMETRY["lid_insert_depth"],
            )
        )
    )
    insert_void = (
        cq.Workplane("XY")
        .box(
            OUTER_L
            - WALL * 2.0
            - V1_GEOMETRY["lid_seat_thickness"] * 2.0
            - V1_GEOMETRY["lid_insert_clearance"] * 2.0,
            OUTER_W
            - WALL * 2.0
            - V1_GEOMETRY["lid_seat_thickness"] * 2.0
            - V1_GEOMETRY["lid_insert_clearance"] * 2.0,
            V1_GEOMETRY["lid_insert_depth"],
            centered=(False, False, False),
        )
        .translate(
            (
                WALL
                + V1_GEOMETRY["lid_seat_thickness"]
                + V1_GEOMETRY["lid_insert_clearance"],
                WALL
                + V1_GEOMETRY["lid_seat_thickness"]
                + V1_GEOMETRY["lid_insert_clearance"],
                -V1_GEOMETRY["lid_insert_depth"],
            )
        )
    )
    return lid_shell.union(insert_rim.cut(insert_void)).translate((0.0, 0.0, OUTER_H + z_gap))


def build_electronics_cover() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            OUTER_L - V1_GEOMETRY["electronics_cover_margin_x"] * 2.0,
            OUTER_W - V1_GEOMETRY["electronics_cover_margin_y"] * 2.0,
            ELEC_COVER,
            centered=(False, False, False),
        )
        .translate(ELECTRONICS_COVER_ORIGIN)
    )


def build_pcb_support_shelf() -> cq.Workplane:
    shelf = (
        cq.Workplane("XY")
        .box(
            PCB_REFERENCE["board_length"] + 6.0,
            PCB_REFERENCE["board_width"] + 6.0,
            V1_GEOMETRY["pcb_shelf_thickness"],
            centered=(False, False, False),
        )
        .translate(
            (
                PCB_MODEL_OFFSET[0] - 3.0,
                PCB_MODEL_OFFSET[1] - 3.0,
                BASE + 0.8,
            )
        )
    )
    stop_left = (
        cq.Workplane("XY")
        .box(
            2.0,
            PCB_REFERENCE["board_width"] + 2.0,
            V1_GEOMETRY["pcb_stop_height"],
            centered=(False, False, False),
        )
        .translate(
            (
                PCB_MODEL_OFFSET[0] - 1.0,
                PCB_MODEL_OFFSET[1] - 1.0,
                BASE + 0.8,
            )
        )
    )
    stop_right = (
        cq.Workplane("XY")
        .box(
            2.0,
            PCB_REFERENCE["board_width"] + 2.0,
            V1_GEOMETRY["pcb_stop_height"],
            centered=(False, False, False),
        )
        .translate(
            (
                PCB_MODEL_OFFSET[0] + PCB_REFERENCE["board_length"] - 1.0,
                PCB_MODEL_OFFSET[1] - 1.0,
                BASE + 0.8,
            )
        )
    )
    return shelf.union(stop_left).union(stop_right)


def build_power_service_pad() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            V1_GEOMETRY["power_pad_length"],
            V1_GEOMETRY["power_pad_width"],
            V1_GEOMETRY["power_pad_thickness"],
            centered=(False, False, False),
        )
        .translate(POWER_PAD_ORIGIN)
    )


def build_ts1_service_pad() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            18.0,
            16.0,
            2.0,
            centered=(False, False, False),
        )
        .translate(TS1_SERVICE_PAD_ORIGIN)
    )


def build_sample_area_reference() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            THERMAL_CONSTRAINTS["sample_area_length"],
            THERMAL_CONSTRAINTS["sample_area_width"],
            0.8,
            centered=(False, False, False),
        )
        .translate(SAMPLE_AREA_ORIGIN)
    )


def build_heater_pad() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            THERMAL_CONSTRAINTS["heater_pad_length"],
            THERMAL_CONSTRAINTS["heater_pad_width"],
            THERMAL_CONSTRAINTS["heater_pad_thickness"],
            centered=(False, False, False),
        )
        .translate(HEATER_PAD_ORIGIN)
    )


def build_heater_placeholder() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(
            THERMAL_CONSTRAINTS["heater_body_length"],
            THERMAL_CONSTRAINTS["heater_body_width"],
            THERMAL_CONSTRAINTS["heater_body_thickness"],
            centered=(False, False, False),
        )
        .translate(
            (
                HEATER_PAD_ORIGIN[0] + 2.0,
                HEATER_PAD_ORIGIN[1] + 1.0,
                HEATER_PAD_ORIGIN[2] + 2.0,
            )
        )
    )


def build_sensor_probe_reference() -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .circle(1.6)
        .extrude(12.0)
        .translate(
            (
                SENSOR_PASSAGE_XY[0],
                WALL + THERMAL_CONSTRAINTS["sensor_probe_front_gap"],
                CHAMBER_FLOOR_Z + DIVIDER + THERMAL_CONSTRAINTS["sensor_probe_height"],
            )
        )
    )


def build_divider_passage_ring(center_xy: tuple[float, float], outer_diameter: float, inner_diameter: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .center(*center_xy)
        .circle(outer_diameter / 2.0)
        .circle(inner_diameter / 2.0)
        .extrude(2.0)
        .translate((0.0, 0.0, CHAMBER_FLOOR_Z + DIVIDER))
    )


def build_opening_frame(
    opening_width: float,
    opening_height: float,
    side: str,
    center_y: float,
    center_z: float,
) -> cq.Workplane:
    frame = (
        cq.Workplane("YZ")
        .center(
            center_y,
            center_z,
        )
        .rect(opening_width + 6.0, opening_height + 6.0)
        .rect(opening_width, opening_height)
        .extrude(1.2)
    )
    if side == "right":
        frame = frame.translate((OUTER_L - 1.2, 0.0, 0.0))
    return frame


def load_step_reference() -> cq.Workplane | None:
    step_path = REFERENCE_FILES["pcb_step"]
    if not step_path.exists() or not REFERENCE_ALIGNMENT["show_step_reference"]:
        return None
    try:
        model = cq.importers.importStep(str(step_path))
        model = normalize_step_xy(model)
        return model.translate(PCB_MODEL_OFFSET)
    except Exception:
        return None


enclosure_body = build_enclosure_body()
lid_closed = build_lid(0.0)
lid_open = build_lid(V1_GEOMETRY["lid_display_gap"])
electronics_cover = build_electronics_cover()
board_proxy = build_board_proxy().translate(PCB_MODEL_OFFSET)
pcb_support_shelf = build_pcb_support_shelf()
power_service_pad = build_power_service_pad()
ts1_service_pad = build_ts1_service_pad()
sample_area_reference = build_sample_area_reference()
heater_pad = build_heater_pad()
heater_placeholder = build_heater_placeholder()
sensor_probe_reference = build_sensor_probe_reference()
sensor_passage_ring = build_divider_passage_ring(
    SENSOR_PASSAGE_XY,
    SERVICE_CONSTRAINTS["sensor_passage_ring_diameter"],
    SERVICE_CONSTRAINTS["sensor_passage_diameter"],
)
heater_passage_ring = build_divider_passage_ring(
    HEATER_PASSAGE_XY,
    SERVICE_CONSTRAINTS["heater_passage_ring_diameter"],
    SERVICE_CONSTRAINTS["heater_passage_diameter"],
)
debug_opening_frame = build_opening_frame(
    SERVICE_CONSTRAINTS["debug_opening_width"],
    SERVICE_CONSTRAINTS["debug_opening_height"],
    side="left",
    center_y=DEBUG_OPENING_CENTER[0],
    center_z=DEBUG_OPENING_CENTER[1],
)
power_opening_frame = build_opening_frame(
    SERVICE_CONSTRAINTS["power_opening_width"],
    SERVICE_CONSTRAINTS["power_opening_height"],
    side="right",
    center_y=POWER_OPENING_CENTER[0],
    center_z=POWER_OPENING_CENTER[1],
)
ts1_opening_frame = build_opening_frame(
    SERVICE_CONSTRAINTS["ts1_opening_width"],
    SERVICE_CONSTRAINTS["ts1_opening_height"],
    side="right",
    center_y=TS1_OPENING_CENTER[0],
    center_z=TS1_OPENING_CENTER[1],
)
step_reference = load_step_reference()

layout_debug = {
    "outer_size": (OUTER_L, OUTER_W, OUTER_H),
    "chamber_inner_size": (CHAMBER_L, CHAMBER_W, CHAMBER_H),
    "electronics_inner_size": (OUTER_L - WALL * 2.0, OUTER_W - WALL * 2.0, ELEC_H),
    "pcb_offset": PCB_MODEL_OFFSET,
    "sensor_passage_xy": SENSOR_PASSAGE_XY,
    "heater_passage_xy": HEATER_PASSAGE_XY,
    "ts1_opening_center": TS1_OPENING_CENTER,
    "ts1_service_pad_origin": TS1_SERVICE_PAD_ORIGIN,
}


if "show_object" in globals():
    show_object(
        enclosure_body,
        name="enclosure_body",
        options={"color": "lightgray", "alpha": VIEW_OPTIONS["enclosure_alpha"]},
    )
    if DISPLAY_OPTIONS["show_lid"]:
        show_object(
            lid_closed,
            name="lid_closed",
            options={"color": "silver", "alpha": 0.18},
        )
        show_object(
            lid_open,
            name="lid_open",
            options={"color": "silver", "alpha": VIEW_OPTIONS["lid_alpha"]},
        )
        show_object(
            electronics_cover,
            name="electronics_cover",
            options={"color": "gray", "alpha": 0.22},
        )
    if DISPLAY_OPTIONS["show_board_proxy"]:
        show_object(
            board_proxy,
            name="board_proxy",
            options={"color": "seagreen", "alpha": VIEW_OPTIONS["board_alpha"]},
        )
        show_object(
            pcb_support_shelf,
            name="pcb_support_shelf",
            options={"color": "slategray", "alpha": 0.85},
        )
    if DISPLAY_OPTIONS["show_step_reference"] and step_reference is not None:
        show_object(
            step_reference,
            name="step_reference",
            options={"color": "orange", "alpha": VIEW_OPTIONS["step_alpha"]},
        )
    if DISPLAY_OPTIONS["show_thermal_helpers"]:
        show_object(
            sample_area_reference,
            name="sample_area_reference",
            options={"color": "lightyellow", "alpha": 0.35},
        )
        show_object(
            heater_pad,
            name="heater_pad",
            options={"color": "goldenrod", "alpha": VIEW_OPTIONS["helper_alpha"]},
        )
        show_object(
            heater_placeholder,
            name="heater_placeholder",
            options={"color": "firebrick", "alpha": 0.88},
        )
        show_object(
            sensor_probe_reference,
            name="sensor_probe_reference",
            options={"color": "tomato", "alpha": 0.88},
        )
        show_object(
            sensor_passage_ring,
            name="sensor_passage_ring",
            options={"color": "salmon", "alpha": VIEW_OPTIONS["helper_alpha"]},
        )
        show_object(
            heater_passage_ring,
            name="heater_passage_ring",
            options={"color": "peru", "alpha": VIEW_OPTIONS["helper_alpha"]},
        )
    if DISPLAY_OPTIONS["show_service_helpers"]:
        show_object(
            debug_opening_frame,
            name="debug_opening_frame",
            options={"color": "steelblue", "alpha": 0.9},
        )
        show_object(
            power_opening_frame,
            name="power_opening_frame",
            options={"color": "tan", "alpha": 0.9},
        )
        show_object(
            ts1_opening_frame,
            name="ts1_opening_frame",
            options={"color": "orchid", "alpha": 0.92},
        )
        show_object(
            power_service_pad,
            name="power_service_pad",
            options={"color": "sienna", "alpha": VIEW_OPTIONS["helper_alpha"]},
        )
        show_object(
            ts1_service_pad,
            name="ts1_service_pad",
            options={"color": "purple", "alpha": VIEW_OPTIONS["helper_alpha"]},
        )


__all__ = [
    "PCB_REFERENCE_DIR",
    "board_proxy",
    "debug_opening_frame",
    "electronics_cover",
    "enclosure_body",
    "heater_pad",
    "heater_passage_ring",
    "heater_placeholder",
    "layout_debug",
    "lid_closed",
    "lid_open",
    "pcb_support_shelf",
    "power_opening_frame",
    "power_service_pad",
    "sample_area_reference",
    "sensor_passage_ring",
    "sensor_probe_reference",
    "step_reference",
    "ts1_opening_frame",
    "ts1_service_pad",
]
