#!/usr/bin/env python3
"""Render a transparent enclosure hero image for the A1 poster."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
POSTER_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[2]
CQ_EDITOR_DIR = REPO_ROOT / "hardware" / "enclosure" / "cq_editor"
DEFAULT_OUTPUT = POSTER_ROOT / "assets" / "enclosure-hero.png"


PRESENTATION_OBJECTS = [
    {"name": "printable_body", "color": "#70b7dc", "opacity": 0.24},
    {"name": "lid_open", "color": "#d2d7dd", "opacity": 0.28},
    {"name": "step_reference", "color": "#f6aa3c", "opacity": 0.72, "optional": True},
    {"name": "board_proxy", "color": "#3eb37a", "opacity": 0.40},
    {"name": "sample_area_reference", "color": "#fff2a8", "opacity": 0.52},
    {"name": "heater_placeholder", "color": "#d14b3d", "opacity": 0.74},
    {"name": "thermal_barrier", "color": "#ffd84d", "opacity": 0.88},
    {"name": "heater_strain_relief", "color": "#f3a33b", "opacity": 0.84},
    {"name": "sensor_probe_clip", "color": "#22c0ff", "opacity": 0.86},
    {"name": "sensor_probe_reference", "color": "#ff725e", "opacity": 0.90},
    {"name": "electronics_cover", "color": "#7b7f86", "opacity": 0.22},
]


def load_module() -> Any:
    sys.path.insert(0, str(CQ_EDITOR_DIR))
    spec = importlib.util.spec_from_file_location("enclosure_v1_presentation", CQ_EDITOR_DIR / "enclosure_v1_presentation.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load enclosure_v1_presentation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def object_shape(obj: Any) -> Any:
    if hasattr(obj, "val"):
        return obj.val()
    return obj


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def add_cadquery_actor(vtk: Any, renderer: Any, model_obj: Any, color: str, opacity: float) -> None:
    import cadquery as cq

    shape = object_shape(model_obj)
    if hasattr(shape, "tessellate"):
        vertices, triangles = shape.tessellate(0.42)
    else:
        vertices, triangles = cq.Shape(shape).tessellate(0.42)

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
    prop.SetDiffuse(0.84)
    prop.SetSpecular(0.28)
    prop.SetSpecularPower(20.0)
    renderer.AddActor(actor)


def configure_camera(renderer: Any, view: str) -> None:
    xmin, xmax, ymin, ymax, zmin, zmax = renderer.ComputeVisiblePropBounds()
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    cz = (zmin + zmax) / 2.0
    dx = max(1.0, xmax - xmin)
    dy = max(1.0, ymax - ymin)
    dz = max(1.0, zmax - zmin)
    span = max(dx, dy, dz)

    camera = renderer.GetActiveCamera()
    camera.ParallelProjectionOn()
    if view == "top":
        camera.SetPosition(cx, cy, cz + span * 2.75)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.SetParallelScale(max(dx, dy) * 0.66)
    elif view == "front":
        camera.SetPosition(cx, cy - span * 2.35, cz + span * 0.15)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.SetParallelScale(max(dx, dz) * 0.67)
    else:
        camera.SetPosition(cx + span * 1.22, cy - span * 1.58, cz + span * 1.06)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetViewUp(0.0, 0.0, 1.0)
        camera.SetParallelScale(span * 0.86)
    renderer.ResetCameraClippingRange()


def render(output_path: Path, *, view: str = "iso", width: int = 5200, height: int = 3900) -> Path:
    try:
        import vtk
    except Exception as exc:  # pragma: no cover - helpful for local troubleshooting
        raise RuntimeError(f"vtk is required for hero rendering: {exc}") from exc

    module = load_module()
    items = []
    for item in PRESENTATION_OBJECTS:
        obj = getattr(module, item["name"], None)
        if obj is None:
            if not item.get("optional"):
                print(f"[hero] missing object: {item['name']}")
            continue
        items.append(item)

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.0, 0.0, 0.0)
    if hasattr(renderer, "SetBackgroundAlpha"):
        renderer.SetBackgroundAlpha(0.0)
    renderer.SetUseDepthPeeling(True)
    renderer.SetMaximumNumberOfPeels(100)
    renderer.SetOcclusionRatio(0.05)

    for item in items:
        add_cadquery_actor(vtk, renderer, getattr(module, item["name"]), str(item["color"]), float(item["opacity"]))

    light1 = vtk.vtkLight()
    light1.SetLightTypeToSceneLight()
    light1.SetPosition(120.0, -180.0, 240.0)
    light1.SetFocalPoint(40.0, 50.0, 20.0)
    light1.SetIntensity(0.95)
    renderer.AddLight(light1)

    light2 = vtk.vtkLight()
    light2.SetLightTypeToSceneLight()
    light2.SetPosition(-180.0, 120.0, 180.0)
    light2.SetFocalPoint(20.0, 30.0, 16.0)
    light2.SetIntensity(0.60)
    renderer.AddLight(light2)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetAlphaBitPlanes(1)
    window.SetMultiSamples(0)
    window.SetSize(width, height)
    window.AddRenderer(renderer)
    configure_camera(renderer, view)
    window.Render()

    image_filter = vtk.vtkWindowToImageFilter()
    image_filter.SetInput(window)
    if hasattr(image_filter, "SetInputBufferTypeToRGBA"):
        image_filter.SetInputBufferTypeToRGBA()
    if hasattr(image_filter, "ReadFrontBufferOff"):
        image_filter.ReadFrontBufferOff()
    image_filter.Update()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output_path))
    writer.SetInputConnection(image_filter.GetOutputPort())
    writer.Write()

    try:
        from PIL import Image

        img = Image.open(output_path).convert("RGBA")
        alpha = img.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            pad = max(80, min(img.size) // 24)
            left = max(0, bbox[0] - pad)
            top = max(0, bbox[1] - pad)
            right = min(img.size[0], bbox[2] + pad)
            bottom = min(img.size[1], bbox[3] + pad)
            img = img.crop((left, top, right, bottom))
            img.save(output_path)
    except Exception as exc:  # pragma: no cover - crop is optional
        print(f"[hero] crop skipped: {exc}")

    try:
        display_path = output_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        display_path = output_path
    print(f"[hero] wrote {display_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the transparent enclosure hero PNG.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--view", choices=["iso", "top", "front"], default="iso")
    parser.add_argument("--width", type=int, default=5200)
    parser.add_argument("--height", type=int, default=3900)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    render(args.output, view=args.view, width=args.width, height=args.height)


if __name__ == "__main__":
    main()
