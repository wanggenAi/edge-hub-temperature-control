"""CQ-editor presentation view for the EdgeHub enclosure V1.

Open this file for thesis-defense screenshots and walkthroughs.
It shows a transparent enclosure with the PCB and core thermal-control layout
visible inside. Nothing in this file should be exported for printing directly;
use `enclosure_v1_print.py` for fabrication review.
"""

from __future__ import annotations

from enclosure_v1 import (  # noqa: F401
    board_proxy,
    electronics_cover,
    heater_placeholder,
    heater_strain_relief,
    lid_open,
    printable_body,
    sample_area_reference,
    sensor_probe_clip,
    sensor_probe_reference,
    step_reference,
    thermal_barrier,
)


if "show_object" in globals():
    show_object(
        printable_body,
        name="01_transparent_enclosure_body",
        options={"color": "lightskyblue", "alpha": 0.24},
    )
    show_object(
        lid_open,
        name="02_open_lid_context",
        options={"color": "silver", "alpha": 0.26},
    )
    if step_reference is not None:
        show_object(
            step_reference,
            name="03_real_pcb_step_model",
            options={"color": "orange", "alpha": 0.72},
        )
    show_object(
        board_proxy,
        name="04_pcb_board_outline_reference",
        options={"color": "seagreen", "alpha": 0.38},
    )
    show_object(
        sample_area_reference,
        name="05_heated_sample_area",
        options={"color": "lightyellow", "alpha": 0.48},
    )
    show_object(
        heater_placeholder,
        name="06_heater_location",
        options={"color": "firebrick", "alpha": 0.76},
    )
    show_object(
        thermal_barrier,
        name="07_thermal_safety_barrier",
        options={"color": "gold", "alpha": 0.88},
    )
    show_object(
        heater_strain_relief,
        name="08_heater_wire_strain_relief_clamp",
        options={"color": "orange", "alpha": 0.84},
    )
    show_object(
        sensor_probe_clip,
        name="09_sensor_probe_support_bracket",
        options={"color": "deepskyblue", "alpha": 0.86},
    )
    show_object(
        sensor_probe_reference,
        name="10_temperature_sensor_probe",
        options={"color": "tomato", "alpha": 0.88},
    )
    show_object(
        electronics_cover,
        name="11_bottom_cover_context",
        options={"color": "gray", "alpha": 0.20},
    )
