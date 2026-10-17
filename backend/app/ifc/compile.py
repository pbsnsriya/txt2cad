"""BuildingSpec -> IFC4 with IfcOpenShell. Own extrusions (no IfcOpenShell wall helpers) so geometry is exact and predictable.

GlobalIds are stable: pass the `guids` map from the previous version and every element that survives keeps its id.
Not thread-safe across threads: call from one worker only.
"""

from __future__ import annotations

import math

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.style
import ifcopenshell.api.unit
import ifcopenshell.guid

from ..domain.geom import box_on_wall as _box_on_wall, stair_profile, wall_outline as _wall_outline
from ..domain.roofs import roof_mesh
from shapely.geometry import MultiPolygon, Polygon, box as shp_box

from ..domain.spec import BoxSpec, BuildingSpec, CoveringSpec, Point, StairSpec

DOOR_LEAF_THICKNESS = 0.05
WINDOW_FRAME_THICKNESS = 0.08
OPENING_OVERCUT = 0.05          # opening is cut a little deeper than the wall so the boolean is clean

COLOURS: dict[str, tuple[float, float, float, float]] = {   # r, g, b, transparency
    "masonry": (0.78, 0.74, 0.68, 0.0), "concrete": (0.62, 0.63, 0.65, 0.0), "timber": (0.72, 0.55, 0.36, 0.0),
    "plaster": (0.90, 0.89, 0.86, 0.0), "slab": (0.55, 0.56, 0.58, 0.0), "roof": (0.36, 0.38, 0.42, 0.0),
    "door": (0.50, 0.33, 0.18, 0.0), "stair": (0.66, 0.60, 0.52, 0.0), "window": (0.55, 0.75, 0.90, 0.55), "space": (0.35, 0.65, 0.45, 0.92),
}


class _Builder:
    def __init__(self, guids: dict[str, str] | None) -> None:
        self.model = ifcopenshell.api.project.create_file("IFC4")
        self.guids = dict(guids or {})
        self.used: dict[str, str] = {}
        self.styles: dict[str, ifcopenshell.entity_instance] = {}

    def reg(self, entity: ifcopenshell.entity_instance, key: str) -> ifcopenshell.entity_instance:
        guid = self.guids.get(key) or ifcopenshell.guid.new()
        entity.GlobalId = guid
        self.used[key] = guid
        return entity

    def style(self, name: str) -> ifcopenshell.entity_instance:
        if name not in self.styles:
            r, g, b, t = COLOURS[name]
            st = ifcopenshell.api.style.add_style(self.model, name=name)
            ifcopenshell.api.style.add_surface_style(
                self.model, style=st, ifc_class="IfcSurfaceStyleRendering",
                attributes={"SurfaceColour": {"Name": None, "Red": r, "Green": g, "Blue": b}, "Transparency": t, "ReflectanceMethod": "NOTDEFINED"})
            self.styles[name] = st
        return self.styles[name]

    def rgb_style(self, hex_colour: str) -> ifcopenshell.entity_instance:
        """A surface style for any #rrggbb, made once per colour."""
        key = f"rgb{hex_colour}"
        if key not in self.styles:
            r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
            st = ifcopenshell.api.style.add_style(self.model, name=hex_colour)
            ifcopenshell.api.style.add_surface_style(
                self.model, style=st, ifc_class="IfcSurfaceStyleRendering",
                attributes={"SurfaceColour": {"Name": None, "Red": r, "Green": g, "Blue": b}, "Transparency": 0.0, "ReflectanceMethod": "NOTDEFINED"})
            self.styles[key] = st
        return self.styles[key]

    def _solid(self, outline: list[Point], z0: float, depth: float, holes: list[list[Point]] | None = None):
        m = self.model
        outer = self._ring(outline)
        profile = (m.createIfcArbitraryProfileDefWithVoids("AREA", None, outer, [self._ring(h) for h in holes]) if holes
                   else m.createIfcArbitraryClosedProfileDef("AREA", None, outer))
        place = m.createIfcAxis2Placement3D(m.createIfcCartesianPoint((0.0, 0.0, float(z0))), None, None)
        return m.createIfcExtrudedAreaSolid(profile, place, m.createIfcDirection((0.0, 0.0, 1.0)), float(depth))

    def boxes_shape(self, body, boxes: list[BoxSpec]):
        """A piece of furniture: several blocks in one shape, each with its own colour."""
        m = self.model
        items = []
        for bx in boxes:
            solid = self._solid(bx.outline, bx.z0, bx.depth)
            ifcopenshell.api.style.assign_item_style(m, item=solid, style=self.rgb_style(bx.colour))
            items.append(solid)
        rep = m.createIfcShapeRepresentation(body, "Body", "SweptSolid", items)
        return m.createIfcProductDefinitionShape(None, None, [rep])

    def covering_shape(self, body, c: CoveringSpec):
        """A floor finish is a thin slab; a wall finish is the wall's inside face with holes where the openings are, extruded into the room."""
        m = self.model
        if c.kind == "floor":
            solid = self._solid(c.outline, c.z0, c.thickness)
            ifcopenshell.api.style.assign_item_style(m, item=solid, style=self.rgb_style(c.colour))
            return m.createIfcProductDefinitionShape(None, None, [m.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])])
        assert c.start and c.end and c.normal
        ux, uy = (c.end[0] - c.start[0]) / c.length, (c.end[1] - c.start[1]) / c.length
        nx, ny = c.normal
        flip = (nx * uy + ny * -ux) < 0                       # the extrusion axis must be (uy, -ux) for local y to point up; otherwise run the wall backwards
        base = c.end if flip else c.start
        xdir = (-ux, -uy, 0.0) if flip else (ux, uy, 0.0)
        face = (base[0] + nx * c.wall_thickness / 2, base[1] + ny * c.wall_thickness / 2, float(c.z0))
        place = m.createIfcAxis2Placement3D(m.createIfcCartesianPoint(face), m.createIfcDirection((nx, ny, 0.0)), m.createIfcDirection(xdir))
        holes = [(c.length - a1, b0, c.length - a0, b1) for a0, b0, a1, b1 in c.holes] if flip else list(c.holes)
        skin = shp_box(0.0, 0.0, c.length, c.height)
        if holes:
            from shapely.ops import unary_union
            skin = skin.difference(unary_union([shp_box(a0, b0, a1, b1) for a0, b0, a1, b1 in holes]))
        polys = list(skin.geoms) if isinstance(skin, MultiPolygon) else [skin]
        items = []
        for poly in polys:
            if poly.is_empty or poly.area < 1e-6:
                continue
            outer = self._ring(list(poly.exterior.coords)[:-1])
            inner = [self._ring(list(r.coords)[:-1]) for r in poly.interiors]
            profile = m.createIfcArbitraryProfileDefWithVoids("AREA", None, outer, inner) if inner else m.createIfcArbitraryClosedProfileDef("AREA", None, outer)
            solid = m.createIfcExtrudedAreaSolid(profile, place, m.createIfcDirection((0.0, 0.0, 1.0)), float(c.thickness))
            ifcopenshell.api.style.assign_item_style(m, item=solid, style=self.rgb_style(c.colour))
            items.append(solid)
        return m.createIfcProductDefinitionShape(None, None, [m.createIfcShapeRepresentation(body, "Body", "SweptSolid", items)])

    def _ring(self, pts: list[Point]):
        m = self.model
        return m.createIfcPolyline([m.createIfcCartesianPoint(list(p)) for p in [*pts, pts[0]]])

    def extrude(self, body, outline: list[Point], z0: float, depth: float, style: str, holes: list[list[Point]] | None = None):
        m = self.model
        outer = self._ring(outline)
        profile = (m.createIfcArbitraryProfileDefWithVoids("AREA", None, outer, [self._ring(h) for h in holes]) if holes
                   else m.createIfcArbitraryClosedProfileDef("AREA", None, outer))
        place = m.createIfcAxis2Placement3D(m.createIfcCartesianPoint((0.0, 0.0, float(z0))), None, None)
        solid = m.createIfcExtrudedAreaSolid(profile, place, m.createIfcDirection((0.0, 0.0, 1.0)), float(depth))
        ifcopenshell.api.style.assign_item_style(m, item=solid, style=self.style(style))
        rep = m.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        return m.createIfcProductDefinitionShape(None, None, [rep])

    def mesh_shape(self, body, vertices, triangles, style: str):
        """A closed tessellated body (pitched roofs)."""
        m = self.model
        rep = ifcopenshell.api.geometry.add_mesh_representation(m, context=body, vertices=[[list(v) for v in vertices]], faces=[[list(t) for t in triangles]])
        for item in rep.Items:
            ifcopenshell.api.style.assign_item_style(m, item=item, style=self.style(style))
        return m.createIfcProductDefinitionShape(None, None, [rep])

    def stair_shape(self, body, st: StairSpec):
        """A solid flight: the stepped profile in the vertical plane of the run, extruded across the width."""
        m = self.model
        pts = stair_profile(st.risers, st.riser_height, st.going)
        poly = m.createIfcPolyline([m.createIfcCartesianPoint([float(a), float(b)]) for a, b in [*pts, pts[0]]])
        profile = m.createIfcArbitraryClosedProfileDef("AREA", None, poly)
        ux, uy = st.direction
        nx, ny = -uy, ux                                    # lateral axis; the flight is extruded towards -n so local Y is up
        loc = m.createIfcCartesianPoint((st.start[0] + nx * st.width / 2, st.start[1] + ny * st.width / 2, float(st.z0)))
        place = m.createIfcAxis2Placement3D(loc, m.createIfcDirection((-nx, -ny, 0.0)), m.createIfcDirection((ux, uy, 0.0)))
        solid = m.createIfcExtrudedAreaSolid(profile, place, m.createIfcDirection((0.0, 0.0, 1.0)), float(st.width))
        ifcopenshell.api.style.assign_item_style(m, item=solid, style=self.style("stair"))
        rep = m.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        return m.createIfcProductDefinitionShape(None, None, [rep])

    def create(self, cls: str, name: str, key: str, shape, predefined: str | None = None):
        e = ifcopenshell.api.root.create_entity(self.model, ifc_class=cls, predefined_type=predefined, name=name)
        self.reg(e, key)
        if hasattr(e, "Tag"):
            e.Tag = key.split(":", 1)[1]                    # the stable element id; Name is the human label
        e.Representation = shape
        ifcopenshell.api.geometry.edit_object_placement(self.model, product=e)
        return e


def compile_ifc(spec: BuildingSpec, design_json: str = "", guids: dict[str, str] | None = None) -> tuple[ifcopenshell.file, dict[str, str]]:
    b = _Builder(guids)
    m = b.model
    project = ifcopenshell.api.root.create_entity(m, ifc_class="IfcProject", name=spec.name)
    b.reg(project, "project")
    # The API default is millimetres; this app works in metres, so say so or every size is off by 1000.
    ifcopenshell.api.unit.assign_unit(m, length={"is_metric": True, "raw": "METRE"}, area={"is_metric": True, "raw": "SQUARE_METRE"},
                                      volume={"is_metric": True, "raw": "CUBIC_METRE"})
    ctx = ifcopenshell.api.context.add_context(m, context_type="Model")
    body = ifcopenshell.api.context.add_context(m, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = b.reg(ifcopenshell.api.root.create_entity(m, ifc_class="IfcSite", name="Site"), "site")
    building = b.reg(ifcopenshell.api.root.create_entity(m, ifc_class="IfcBuilding", name=spec.name), "building")
    ifcopenshell.api.aggregate.assign_object(m, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(m, products=[building], relating_object=site)
    storeys = {}
    for lv in spec.levels:
        st = b.reg(ifcopenshell.api.root.create_entity(m, ifc_class="IfcBuildingStorey", name=lv.name), f"level:{lv.id}")
        st.Elevation = lv.elevation
        ifcopenshell.api.aggregate.assign_object(m, products=[st], relating_object=building)
        storeys[lv.id] = st

    walls = {}
    for w in spec.walls:
        pts, _, _ = _wall_outline(w.start, w.end, w.thickness)
        z0 = spec.level_elevation(w.level)
        wall = b.create("IfcWall", w.label or w.id, f"element:{w.id}", b.extrude(body, pts, z0, w.height, w.material if w.external else "plaster"), "STANDARD")
        ifcopenshell.api.spatial.assign_container(m, products=[wall], relating_structure=storeys[w.level])
        walls[w.id] = wall

    for s in spec.slabs:
        slab = b.create("IfcSlab", s.label or s.id, f"element:{s.id}", b.extrude(body, s.outline, s.z_top - s.thickness, s.thickness, "slab", s.holes), "FLOOR")
        ifcopenshell.api.spatial.assign_container(m, products=[slab], relating_structure=storeys[s.level])
    for st in spec.stairs:
        stair = b.create("IfcStair", st.label or st.id, f"element:{st.id}", b.stair_shape(body, st), "STRAIGHT_RUN_STAIR")
        ifcopenshell.api.spatial.assign_container(m, products=[stair], relating_structure=storeys[st.level])
    for r in spec.roofs:
        if r.kind == "flat":
            roof = b.create("IfcRoof", r.label or r.id, f"element:{r.id}", b.extrude(body, r.outline, r.z_bottom, r.thickness, "roof"), "FLAT_ROOF")
        else:
            verts, tris = roof_mesh(r.outline, r.z_bottom, r.kind, r.pitch, r.high_side)
            roof = b.create("IfcRoof", r.label or r.id, f"element:{r.id}", b.mesh_shape(body, verts, tris, "roof"), f"{r.kind.upper()}_ROOF")
        ifcopenshell.api.spatial.assign_container(m, products=[roof], relating_structure=storeys[r.level])

    for o in spec.openings:
        wall_spec = spec.wall(o.host)
        _, u, n = _wall_outline(wall_spec.start, wall_spec.end, wall_spec.thickness)
        centre = (wall_spec.start[0] + u[0] * o.offset, wall_spec.start[1] + u[1] * o.offset)
        z0 = spec.level_elevation(o.level) + o.sill
        cut = b.create("IfcOpeningElement", f"{o.label or o.id} (opening)", f"opening:{o.id}",
                       b.extrude(body, _box_on_wall(centre, u, n, o.width, wall_spec.thickness + 2 * OPENING_OVERCUT), z0, o.height, "plaster"))
        ifcopenshell.api.feature.add_feature(m, feature=cut, element=walls[o.host])
        if o.kind == "door" and o.style == "opening":          # an archway: the wall is open, there is nothing to fill it with
            continue
        thickness = DOOR_LEAF_THICKNESS if o.kind == "door" else WINDOW_FRAME_THICKNESS
        cls = "IfcDoor" if o.kind == "door" else "IfcWindow"
        fill = b.create(cls, o.label or o.id, f"element:{o.id}", b.extrude(body, _box_on_wall(centre, u, n, o.width, thickness), z0, o.height, o.kind))
        fill.OverallWidth, fill.OverallHeight = o.width, o.height
        ifcopenshell.api.spatial.assign_container(m, products=[fill], relating_structure=storeys[o.level])
        ifcopenshell.api.feature.add_filling(m, opening=cut, element=fill)

    for fu in spec.furniture:
        piece = b.create("IfcLightFixture" if fu.kind in ("ceiling_light", "floor_lamp") else "IfcFurniture", fu.label or fu.id, f"element:{fu.id}", b.boxes_shape(body, fu.boxes))
        ifcopenshell.api.spatial.assign_container(m, products=[piece], relating_structure=storeys[fu.level])
        ifcopenshell.api.pset.edit_pset(m, pset=ifcopenshell.api.pset.add_pset(m, product=piece, name="Txt2Cad_Furniture"),
                                        properties={"Kind": fu.kind, "Room": fu.room, "HeightM": fu.height})
    for cv in spec.coverings:
        covering = b.create("IfcCovering", cv.label or cv.id, f"element:{cv.id}", b.covering_shape(body, cv), "FLOORING" if cv.kind == "floor" else "CLADDING")
        ifcopenshell.api.spatial.assign_container(m, products=[covering], relating_structure=storeys[cv.level])
        ifcopenshell.api.pset.edit_pset(m, pset=ifcopenshell.api.pset.add_pset(m, product=covering, name="Txt2Cad_Finish"),
                                        properties={"Finish": cv.finish, "Colour": cv.colour, "AreaM2": cv.area})

    for sp in spec.spaces:
        space = b.create("IfcSpace", sp.name, f"element:{sp.id}", b.extrude(body, sp.outline, spec.level_elevation(sp.level), 2.4, "space"))
        ifcopenshell.api.aggregate.assign_object(m, products=[space], relating_object=storeys[sp.level])
        ifcopenshell.api.pset.edit_pset(m, pset=ifcopenshell.api.pset.add_pset(m, product=space, name="Txt2Cad_Space"), properties={"SpecId": sp.id, "Kind": sp.kind, "AreaM2": sp.area})

    if design_json:  # lets the app read back its own export (lossless re-import)
        ps = ifcopenshell.api.pset.add_pset(m, product=building, name="Txt2Cad_Design")
        ifcopenshell.api.pset.edit_pset(m, pset=ps, properties={"DesignJson": design_json})
    return m, b.used
