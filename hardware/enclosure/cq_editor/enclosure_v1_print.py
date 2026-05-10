"""CQ-editor print/fabrication view for the EdgeHub enclosure V1.

Open this file when checking the final printable parts. It only shows the
objects that should be exported to STL/STEP for fabrication.
"""

from __future__ import annotations

from enclosure_v1 import (  # noqa: F401
    OUTER_L,
    electronics_cover_print,
    lid_print,
    printable_body,
)


PRINT_LAYOUT_GAP = 14.0
lid_print_preview = lid_print.translate((OUTER_L + PRINT_LAYOUT_GAP, 0.0, 0.0))


if "show_object" in globals():
    show_object(
        printable_body,
        name="PRINT_01_main_body",
        options={"color": "steelblue", "alpha": 0.82},
    )
    show_object(
        lid_print_preview,
        name="PRINT_02_top_lid",
        options={"color": "darkorange", "alpha": 0.86},
    )
    show_object(
        electronics_cover_print,
        name="PRINT_03_bottom_electronics_cover",
        options={"color": "dimgray", "alpha": 0.86},
    )
