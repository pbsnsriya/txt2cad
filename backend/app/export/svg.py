"""The DXF plans as an SVG, for the Drawings tab. Rendered from the same DXF document so the preview never differs from the download."""

from __future__ import annotations

from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

from ..domain.spec import BuildingSpec
from .dxf import build_dxf

PAGE_MARGIN_MM = 8
SCALE_MM_PER_M = 10            # 1:100 on paper: one metre of building is 10 mm


def svg_text(spec: BuildingSpec) -> str:
    doc = build_dxf(spec)
    backend = svg.SVGBackend()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(doc.modelspace())
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(PAGE_MARGIN_MM))      # 0 x 0: size the page to the drawing
    return backend.get_string(page, settings=layout.Settings(scale=SCALE_MM_PER_M))
