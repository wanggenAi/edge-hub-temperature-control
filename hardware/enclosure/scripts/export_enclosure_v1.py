#!/usr/bin/env python3
"""Export, render, and inspect the CadQuery enclosure V1 model.

Run with the CadQuery conda environment, for example:

    /Users/seker./miniforge/envs/cadq/bin/python hardware/enclosure/scripts/export_enclosure_v1.py

The script intentionally does more than export files: it creates visual previews
and writes an inspection report so geometry regressions are easier to catch.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
ENCLOSURE_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
CQ_EDITOR_DIR = ENCLOSURE_ROOT / "cq_editor"
DEFAULT_EXPORT_DIR = ENCLOSURE_ROOT / "exports" / "v1"

PRINTABLE_PARTS = {
    "printable_body": "body with integrated enclosure features",
    "lid_print": "standalone removable lid",
    "electronics_cover_print": "standalone bottom electronics cover",
}

INSPECTED_HELPERS = [
    "enclosure_body",
    "pcb_support_shelf",
    "sensor_probe_clip",
    "heater_strain_relief",
    "thermal_barrier",
    "sensor_passage_ring",
    "heater_passage_ring",
    "debug_opening_frame",
    "power_opening_frame",
    "ts1_opening_frame",
    "board_proxy",
]

PART_COLORS = {
    "printable_body": "#2f6f9f",
    "lid_print": "#d08a32",
    "electronics_cover_print": "#707070",
}

PRINT_PREVIEW_OFFSETS = {
    "printable_body": (0.0, 0.0, 0.0),
    "lid_print": (122.0, 0.0, 0.0),
    "electronics_cover_print": (0.0, 0.0, 0.0),
}

PRESENTATION_OBJECTS = [
    {
        "name": "printable_body",
        "label": "transparent enclosure body",
        "color": "#66b7dd",
        "opacity": 0.24,
    },
    {
        "name": "lid_open",
        "label": "open lid context",
        "color": "#c8c8c8",
        "opacity": 0.26,
    },
    {
        "name": "step_reference",
        "label": "real PCB STEP reference",
        "color": "#f39c12",
        "opacity": 0.72,
        "optional": True,
    },
    {
        "name": "board_proxy",
        "label": "PCB outline reference",
        "color": "#2e8b57",
        "opacity": 0.38,
    },
    {
        "name": "sample_area_reference",
        "label": "heated sample area",
        "color": "#fff3a6",
        "opacity": 0.48,
    },
    {
        "name": "heater_placeholder",
        "label": "heater location",
        "color": "#b22222",
        "opacity": 0.76,
    },
    {
        "name": "thermal_barrier",
        "label": "thermal safety barrier",
        "color": "#ffd34d",
        "opacity": 0.88,
    },
    {
        "name": "heater_strain_relief",
        "label": "heater wire strain relief clamp",
        "color": "#f39c12",
        "opacity": 0.84,
    },
    {
        "name": "sensor_probe_clip",
        "label": "sensor support bracket",
        "color": "#00a6d6",
        "opacity": 0.86,
    },
    {
        "name": "sensor_probe_reference",
        "label": "temperature sensor probe",
        "color": "#ff6347",
        "opacity": 0.88,
    },
]


class GeometryIssue(dict[str, Any]):
    """JSON-friendly geometry issue record."""

    def __init__(self, severity: str, code: str, message: str, **data: Any) -> None:
        super().__init__(severity=severity, code=code, message=message, **data)


def load_model() -> Any:
    sys.path.insert(0, str(CQ_EDITOR_DIR))
    spec = importlib.util.spec_from_file_location("enclosure_v1", CQ_EDITOR_DIR / "enclosure_v1.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load enclosure_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def object_shape(model_obj: Any) -> Any:
    if hasattr(model_obj, "val"):
        return model_obj.val()
    return model_obj


def bbox_payload(model_obj: Any) -> dict[str, float]:
    bb = object_shape(model_obj).BoundingBox()
    return {
        "xmin": round(float(bb.xmin), 4),
        "ymin": round(float(bb.ymin), 4),
        "zmin": round(float(bb.zmin), 4),
        "xmax": round(float(bb.xmax), 4),
        "ymax": round(float(bb.ymax), 4),
        "zmax": round(float(bb.zmax), 4),
        "xlen": round(float(bb.xlen), 4),
        "ylen": round(float(bb.ylen), 4),
        "zlen": round(float(bb.zlen), 4),
    }


def collect_bboxes(module: Any, names: list[str]) -> dict[str, dict[str, float]]:
    bboxes: dict[str, dict[str, float]] = {}
    for name in names:
        obj = getattr(module, name, None)
        if obj is None:
            continue
        bboxes[name] = bbox_payload(obj)
    return bboxes


def export_parts(module: Any, export_dir: Path, *, export_step: bool, export_stl: bool) -> dict[str, dict[str, float]]:
    import cadquery as cq

    export_dir.mkdir(parents=True, exist_ok=True)
    bboxes: dict[str, dict[str, float]] = {}
    for name in PRINTABLE_PARTS:
        part = getattr(module, name)
        bboxes[name] = bbox_payload(part)
        if export_step:
            cq.exporters.export(part, str(export_dir / f"{name}.step"))
        if export_stl:
            cq.exporters.export(part, str(export_dir / f"{name}.stl"), tolerance=0.15, angularTolerance=0.2)
    return bboxes


def outer_bounds(module: Any) -> dict[str, float]:
    outer_l, outer_w, outer_h = module.layout_debug["outer_size"]
    return {
        "xmin": 0.0,
        "ymin": 0.0,
        "zmin": 0.0,
        "xmax": round(float(outer_l), 4),
        "ymax": round(float(outer_w), 4),
        "zmax": round(float(outer_h), 4),
    }


def bbox_overflow(bb: dict[str, float], bounds: dict[str, float], tolerance: float = 0.05) -> dict[str, float]:
    overflow: dict[str, float] = {}
    for axis in ("x", "y", "z"):
        low_key = f"{axis}min"
        high_key = f"{axis}max"
        low_delta = round(bounds[low_key] - bb[low_key], 4)
        high_delta = round(bb[high_key] - bounds[high_key], 4)
        if low_delta > tolerance:
            overflow[f"{axis}min"] = low_delta
        if high_delta > tolerance:
            overflow[f"{axis}max"] = high_delta
    return overflow


def clearance_to_bounds(bb: dict[str, float], bounds: dict[str, float]) -> dict[str, float]:
    return {
        "xmin": round(bb["xmin"] - bounds["xmin"], 4),
        "ymin": round(bb["ymin"] - bounds["ymin"], 4),
        "zmin": round(bb["zmin"] - bounds["zmin"], 4),
        "xmax": round(bounds["xmax"] - bb["xmax"], 4),
        "ymax": round(bounds["ymax"] - bb["ymax"], 4),
        "zmax": round(bounds["zmax"] - bb["zmax"], 4),
    }


def inspect_geometry(module: Any, part_bboxes: dict[str, dict[str, float]], helper_bboxes: dict[str, dict[str, float]]) -> dict[str, Any]:
    bounds = outer_bounds(module)
    issues: list[GeometryIssue] = []
    measurements: dict[str, Any] = {
        "outer_bounds": bounds,
        "printable_part_bounding_boxes": part_bboxes,
        "helper_bounding_boxes": helper_bboxes,
        "body_feature_clearances_mm": {},
    }

    printable_body_bb = part_bboxes.get("printable_body")
    if printable_body_bb:
        overflow = bbox_overflow(printable_body_bb, bounds)
        measurements["body_feature_clearances_mm"]["printable_body"] = clearance_to_bounds(printable_body_bb, bounds)
        if overflow:
            issues.append(
                GeometryIssue(
                    "error",
                    "printable_body_outside_outer_bounds",
                    "printable_body exceeds the nominal enclosure body envelope.",
                    overflow_mm=overflow,
                    printable_body_bbox=printable_body_bb,
                    outer_bounds=bounds,
                )
            )

    for helper_name in [
        "pcb_support_shelf",
        "sensor_probe_clip",
        "heater_strain_relief",
        "thermal_barrier",
        "sensor_passage_ring",
        "heater_passage_ring",
    ]:
        helper_bb = helper_bboxes.get(helper_name)
        if not helper_bb:
            continue
        overflow = bbox_overflow(helper_bb, bounds)
        measurements["body_feature_clearances_mm"][helper_name] = clearance_to_bounds(helper_bb, bounds)
        if overflow:
            issues.append(
                GeometryIssue(
                    "error",
                    f"{helper_name}_outside_outer_bounds",
                    f"{helper_name} protrudes outside the main body envelope.",
                    overflow_mm=overflow,
                    feature_bbox=helper_bb,
                    outer_bounds=bounds,
                )
            )

    for part_name, bb in part_bboxes.items():
        if bb["zmin"] < -0.05:
            issues.append(
                GeometryIssue(
                    "error",
                    f"{part_name}_below_build_plane",
                    f"{part_name} has geometry below the build plane.",
                    zmin_mm=bb["zmin"],
                )
            )
        if bb["zlen"] <= 0.0:
            issues.append(
                GeometryIssue(
                    "error",
                    f"{part_name}_empty_height",
                    f"{part_name} has an invalid zero or negative height.",
                    bbox=bb,
                )
            )

    lid_bb = part_bboxes.get("lid_print")
    if lid_bb:
        if lid_bb["ymin"] < -0.05:
            issues.append(
                GeometryIssue(
                    "info",
                    "lid_front_grip_tab",
                    "lid_print extends forward because the front grip tab is intentionally outside the rectangular lid envelope.",
                    y_extension_mm=round(abs(lid_bb["ymin"]), 4),
                )
            )
        expected_lid_height = round(float(module.V1_GEOMETRY["lid_thickness"] + module.V1_GEOMETRY["lid_insert_depth"]), 4)
        if abs(lid_bb["zlen"] - expected_lid_height) > 0.15:
            issues.append(
                GeometryIssue(
                    "warning",
                    "lid_height_unexpected",
                    "lid_print height differs from lid thickness plus insert depth.",
                    expected_mm=expected_lid_height,
                    actual_mm=lid_bb["zlen"],
                )
            )

    if getattr(module, "step_reference", None) is None:
        issues.append(
            GeometryIssue(
                "warning",
                "pcb_step_reference_not_loaded",
                "PCB STEP reference was not loaded, so component collision checks still require CQ-editor visual inspection.",
            )
        )

    blocking = [issue for issue in issues if issue["severity"] == "error"]
    return {
        "ok": not blocking,
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking),
        "issues": issues,
        "measurements": measurements,
        "notes": [
            "exports/ is generated output and is intentionally ignored by git.",
            "Use the cadq conda Python for repeatable CadQuery export and preview generation.",
        ],
    }


def write_debug_files(module: Any, export_dir: Path, part_bboxes: dict[str, dict[str, float]], helper_bboxes: dict[str, dict[str, float]], report: dict[str, Any]) -> None:
    (export_dir / "layout_debug.json").write_text(
        json.dumps(
            {
                "layout_debug": module.layout_debug,
                "printable_part_bounding_boxes": part_bboxes,
                "helper_bounding_boxes": helper_bboxes,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (export_dir / "inspection_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def project_iso(point: tuple[float, float, float], scale: float, offset: tuple[float, float]) -> tuple[float, float]:
    x, y, z = point
    # Lightweight isometric projection for a dependency-free inspection image.
    px = (x - y) * math.cos(math.radians(30.0))
    py = (x + y) * math.sin(math.radians(30.0)) - z
    return (px * scale + offset[0], py * scale + offset[1])


def bbox_corners(bb: dict[str, float]) -> list[tuple[float, float, float]]:
    xs = [bb["xmin"], bb["xmax"]]
    ys = [bb["ymin"], bb["ymax"]]
    zs = [bb["zmin"], bb["zmax"]]
    return [(x, y, z) for x in xs for y in ys for z in zs]


def draw_bbox_preview(export_dir: Path, bboxes: dict[str, dict[str, float]]) -> Path | None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # pragma: no cover - optional preview helper
        print(f"[preview] skipped bounding-box image: pillow unavailable: {exc}")
        return None

    image_size = (1200, 900)
    all_points = [p for bb in bboxes.values() for p in bbox_corners(bb)]
    raw_projected = [project_iso(p, 1.0, (0.0, 0.0)) for p in all_points]
    min_x = min(p[0] for p in raw_projected)
    max_x = max(p[0] for p in raw_projected)
    min_y = min(p[1] for p in raw_projected)
    max_y = max(p[1] for p in raw_projected)
    scale = min((image_size[0] - 180) / max(1.0, max_x - min_x), (image_size[1] - 160) / max(1.0, max_y - min_y))
    offset = (90 - min_x * scale, 120 - min_y * scale)

    img = Image.new("RGB", image_size, "white")
    draw = ImageDraw.Draw(img)
    edges = [
        (0, 1), (0, 2), (0, 4), (3, 1), (3, 2), (3, 7),
        (5, 1), (5, 4), (5, 7), (6, 2), (6, 4), (6, 7),
    ]
    for name, bb in bboxes.items():
        corners = bbox_corners(bb)
        pts = [project_iso(p, scale, offset) for p in corners]
        color = PART_COLORS.get(name, "black")
        for a, b in edges:
            draw.line((pts[a], pts[b]), fill=color, width=4)
        label_at = pts[7]
        draw.text((label_at[0] + 8, label_at[1] - 8), f"{name} {bb['xlen']}x{bb['ylen']}x{bb['zlen']}mm", fill=color)

    draw.text((40, 30), "EdgeHub enclosure V1 export bounding-box preview", fill="black")
    preview_path = export_dir / "preview_bounding_boxes.png"
    img.save(preview_path)
    print(f"[preview] wrote {preview_path.relative_to(REPO_ROOT)}")
    return preview_path


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def add_stl_actor(
    vtk: Any,
    renderer: Any,
    stl_path: Path,
    color: str,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    show_edges: bool = False,
) -> None:
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(stl_path))
    reader.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(reader.GetOutputPort())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*hex_to_rgb(color))
    prop.SetDiffuse(0.85)
    prop.SetSpecular(0.25)
    prop.SetSpecularPower(18.0)
    if show_edges:
        prop.EdgeVisibilityOn()
        prop.SetEdgeColor(0.08, 0.12, 0.14)
        prop.SetLineWidth(0.35)
    actor.SetPosition(*offset)
    renderer.AddActor(actor)


def add_cadquery_actor(
    vtk: Any,
    renderer: Any,
    model_obj: Any,
    color: str,
    opacity: float,
    show_edges: bool = False,
) -> None:
    import cadquery as cq

    shape = object_shape(model_obj)
    if hasattr(shape, "tessellate"):
        vertices, triangles = shape.tessellate(0.45)
    else:
        vertices, triangles = cq.Shape(shape).tessellate(0.45)

    points = vtk.vtkPoints()
    for vertex in vertices:
        points.InsertNextPoint(float(vertex.x), float(vertex.y), float(vertex.z))

    polys = vtk.vtkCellArray()
    for tri in triangles:
        polygon = vtk.vtkTriangle()
        polygon.GetPointIds().SetId(0, int(tri[0]))
        polygon.GetPointIds().SetId(1, int(tri[1]))
        polygon.GetPointIds().SetId(2, int(tri[2]))
        polys.InsertNextCell(polygon)

    poly_data = vtk.vtkPolyData()
    poly_data.SetPoints(points)
    poly_data.SetPolys(polys)

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(poly_data)
    normals.ConsistencyOn()
    normals.SplittingOff()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*hex_to_rgb(color))
    prop.SetOpacity(opacity)
    prop.SetDiffuse(0.82)
    prop.SetSpecular(0.28)
    prop.SetSpecularPower(20.0)
    if show_edges:
        prop.EdgeVisibilityOn()
        prop.SetEdgeColor(0.08, 0.12, 0.14)
        prop.SetLineWidth(0.25)
    renderer.AddActor(actor)


def configure_camera(renderer: Any, view: str) -> None:
    bounds = renderer.ComputeVisiblePropBounds()
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    cz = (zmin + zmax) / 2.0
    dx = max(1.0, xmax - xmin)
    dy = max(1.0, ymax - ymin)
    dz = max(1.0, zmax - zmin)
    span = max(dx, dy, dz)

    camera = renderer.GetActiveCamera()
    if view == "top":
        camera.SetPosition(cx, cy, cz + span * 2.8)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(max(dx, dy) * 0.62)
    elif view == "front":
        camera.SetPosition(cx, cy - span * 2.4, cz + span * 0.25)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(max(dx, dz) * 0.65)
    else:
        camera.SetPosition(cx + span * 1.25, cy - span * 1.65, cz + span * 1.05)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(span * 0.82)
    renderer.ResetCameraClippingRange()


def render_stl_preview(export_dir: Path, output_name: str, part_names: list[str], *, title: str, view: str = "iso") -> Path | None:
    try:
        import vtk
    except Exception as exc:  # pragma: no cover - optional preview helper
        print(f"[preview] skipped VTK render: vtk unavailable: {exc}")
        return None

    stl_paths = [(name, export_dir / f"{name}.stl") for name in part_names]
    missing = [path for _, path in stl_paths if not path.exists()]
    if missing:
        print(f"[preview] skipped {output_name}: missing STL files: {', '.join(str(p) for p in missing)}")
        return None

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1.0, 1.0, 1.0)
    renderer.SetUseDepthPeeling(True)

    use_print_layout = len(part_names) > 1
    for name, stl_path in stl_paths:
        offset = PRINT_PREVIEW_OFFSETS.get(name, (0.0, 0.0, 0.0)) if use_print_layout else (0.0, 0.0, 0.0)
        add_stl_actor(vtk, renderer, stl_path, PART_COLORS.get(name, "#2f6f9f"), offset, show_edges=True)

    light = vtk.vtkLight()
    light.SetLightTypeToSceneLight()
    light.SetPosition(80.0, -120.0, 180.0)
    light.SetFocalPoint(40.0, 35.0, 20.0)
    light.SetIntensity(0.8)
    renderer.AddLight(light)

    text = vtk.vtkTextActor()
    text.SetInput(title)
    text.SetPosition(24, 858)
    text.GetTextProperty().SetFontSize(22)
    text.GetTextProperty().SetColor(0.08, 0.08, 0.08)
    renderer.AddViewProp(text)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(1200, 900)
    window.AddRenderer(renderer)
    configure_camera(renderer, view)
    window.Render()

    image_filter = vtk.vtkWindowToImageFilter()
    image_filter.SetInput(window)
    image_filter.Update()

    output_path = export_dir / output_name
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output_path))
    writer.SetInputConnection(image_filter.GetOutputPort())
    writer.Write()
    print(f"[preview] wrote {output_path.relative_to(REPO_ROOT)}")
    return output_path


def render_presentation_preview(module: Any, export_dir: Path, output_name: str, *, title: str, view: str = "iso") -> Path | None:
    try:
        import vtk
    except Exception as exc:  # pragma: no cover - optional preview helper
        print(f"[preview] skipped presentation render: vtk unavailable: {exc}")
        return None

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1.0, 1.0, 1.0)
    renderer.SetUseDepthPeeling(True)
    renderer.SetMaximumNumberOfPeels(80)
    renderer.SetOcclusionRatio(0.08)

    labels: list[str] = []
    for item in PRESENTATION_OBJECTS:
        obj = getattr(module, item["name"], None)
        if obj is None:
            if not item.get("optional"):
                print(f"[preview] missing presentation object: {item['name']}")
            continue
        add_cadquery_actor(vtk, renderer, obj, str(item["color"]), float(item["opacity"]))
        labels.append(str(item["label"]))

    light = vtk.vtkLight()
    light.SetLightTypeToSceneLight()
    light.SetPosition(80.0, -120.0, 180.0)
    light.SetFocalPoint(40.0, 35.0, 25.0)
    light.SetIntensity(0.9)
    renderer.AddLight(light)

    title_actor = vtk.vtkTextActor()
    title_actor.SetInput(title)
    title_actor.SetPosition(24, 858)
    title_actor.GetTextProperty().SetFontSize(22)
    title_actor.GetTextProperty().SetColor(0.08, 0.08, 0.08)
    renderer.AddViewProp(title_actor)

    legend_actor = vtk.vtkTextActor()
    legend_actor.SetInput("Visible: " + " / ".join(labels[:5]) + (" / ..." if len(labels) > 5 else ""))
    legend_actor.SetPosition(24, 28)
    legend_actor.GetTextProperty().SetFontSize(16)
    legend_actor.GetTextProperty().SetColor(0.18, 0.18, 0.18)
    renderer.AddViewProp(legend_actor)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetAlphaBitPlanes(1)
    window.SetMultiSamples(0)
    window.SetSize(1200, 900)
    window.AddRenderer(renderer)
    configure_camera(renderer, view)
    window.Render()

    image_filter = vtk.vtkWindowToImageFilter()
    image_filter.SetInput(window)
    image_filter.Update()

    output_path = export_dir / output_name
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output_path))
    writer.SetInputConnection(image_filter.GetOutputPort())
    writer.Write()
    print(f"[preview] wrote {output_path.relative_to(REPO_ROOT)}")
    return output_path


def render_previews(module: Any, export_dir: Path) -> list[Path]:
    rendered: list[Path] = []
    requests = [
        ("preview_presentation_transparent_iso.png", None, "Presentation view - transparent enclosure with PCB", "iso"),
        ("preview_presentation_transparent_top.png", None, "Presentation view - system layout from top", "top"),
        ("preview_all_parts_iso.png", list(PRINTABLE_PARTS), "EdgeHub enclosure V1 printable parts - ISO", "iso"),
        ("preview_printable_body_iso.png", ["printable_body"], "Printable body - ISO", "iso"),
        ("preview_printable_body_top.png", ["printable_body"], "Printable body - top inspection", "top"),
        ("preview_printable_body_front.png", ["printable_body"], "Printable body - front/service inspection", "front"),
        ("preview_lid_iso.png", ["lid_print"], "Lid print with front grip tab - ISO", "iso"),
    ]
    for output_name, part_names, title, view in requests:
        if part_names is None:
            path = render_presentation_preview(module, export_dir, output_name, title=title, view=view)
        else:
            path = render_stl_preview(export_dir, output_name, part_names, title=title, view=view)
        if path:
            rendered.append(path)
    return rendered


def print_report_summary(report: dict[str, Any]) -> None:
    status = "OK" if report["ok"] else "FAILED"
    print(f"[inspect] {status}: {report['blocking_issue_count']} blocking issue(s), {report['issue_count']} total issue(s)")
    for issue in report["issues"]:
        severity = issue["severity"].upper()
        print(f"[inspect] {severity} {issue['code']}: {issue['message']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export, render, and inspect EdgeHub enclosure V1 printable parts.")
    parser.add_argument("--out", type=Path, default=DEFAULT_EXPORT_DIR, help="Output directory")
    parser.add_argument("--no-step", action="store_true", help="Skip STEP export")
    parser.add_argument("--no-stl", action="store_true", help="Skip STL export")
    parser.add_argument("--no-preview", action="store_true", help="Skip PNG preview generation")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when blocking geometry issues are found")
    args = parser.parse_args()

    module = load_model()
    part_bboxes = export_parts(module, args.out, export_step=not args.no_step, export_stl=not args.no_stl)
    helper_bboxes = collect_bboxes(module, INSPECTED_HELPERS)
    report = inspect_geometry(module, part_bboxes, helper_bboxes)
    write_debug_files(module, args.out, part_bboxes, helper_bboxes, report)

    if not args.no_preview:
        draw_bbox_preview(args.out, part_bboxes)
        if not args.no_stl:
            render_previews(module, args.out)
        else:
            print("[preview] skipped VTK render: --no-stl was used")

    print_report_summary(report)
    print(json.dumps(part_bboxes, indent=2, sort_keys=True))

    if args.strict and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
