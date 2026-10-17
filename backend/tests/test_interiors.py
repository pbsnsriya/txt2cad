"""Interiors: furniture and finishes, from the catalogue to the IFC, the plans, the quantities and what the model is told."""

import ifcopenshell
import ifcopenshell.geom
import pytest
from shapely.geometry import Polygon, box

from app.analysis.quantities import quantities
from app.domain import catalogue, checks
from app.domain.derive import DesignError, derive, prune_invalid_openings
from app.domain.describe import describe, describe_focus, describe_selection
from app.domain.design import Design
from app.domain.furnish import furniture_polygon, layout_room
from app.domain.steps import Step, StepError, apply_step
from app.export.dxf import build_dxf
from app.ifc.compile import compile_ifc


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


BASE = [
    {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3},
    {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [0, 0, 5, 5]},
    {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [5, 0, 4, 4]},
    {"step": "room", "level": "L1", "name": "Bedroom", "kind": "bedroom", "rect": [0, 5, 4, 4]},
    {"step": "door", "room": "Living", "to": "Kitchen"},
    {"step": "door", "room": "Living", "to": "Bedroom"},
    {"step": "door", "room": "Living", "to": "outside", "side": "S"},
    {"step": "window", "room": "Living", "side": "W"},
]


def house(*extra):
    return build(*BASE, *extra)


# --- the catalogue ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(catalogue.CATALOGUE))
def test_every_shape_stays_inside_its_footprint_and_height(kind):
    item = catalogue.CATALOGUE[kind]
    bxs = catalogue.parts(kind, item.w, item.d, item.h)
    assert bxs
    for x0, y0, x1, y1, z0, z1, key in bxs:
        assert -item.w / 2 - 1e-9 <= x0 < x1 <= item.w / 2 + 1e-9 and -item.d / 2 - 1e-9 <= y0 < y1 <= item.d / 2 + 1e-9
        assert 0 <= z0 < z1 <= item.h + 0.03 and (key == "main" or key in catalogue.PART_COLOURS)


def test_names_and_colours_resolve_or_say_what_is_allowed():
    assert catalogue.resolve("Oak", catalogue.FLOORS, "floor") == "#b89464" and catalogue.resolve("#AABBCC", catalogue.PAINTS, "paint") == "#aabbcc"
    assert catalogue.resolve(None, catalogue.PAINTS, "paint") is None
    with pytest.raises(catalogue.UnknownName, match="oak"):
        catalogue.resolve("sparkly", catalogue.FLOORS, "floor")
    assert catalogue.item_for("couch").kind == "sofa" and catalogue.item_for("Double Bed").kind == "bed_double"
    with pytest.raises(catalogue.UnknownName, match="bed_double"):
        catalogue.item_for("spaceship")


# --- the furniture step ---------------------------------------------------------------------------------------------------------
def test_a_piece_against_a_wall_has_its_back_to_it():
    d = house({"step": "furniture", "room": "Bedroom", "kind": "bed_double", "side": "N", "at": 0.5})
    [f] = d.furniture
    assert f.rot == 180 and f.y > 7.5 and f.x == pytest.approx(2.0, abs=0.01)           # the bedroom is x 0..4, y 5..9; the head is by the north wall
    d = house({"step": "furniture", "room": "Bedroom", "kind": "wardrobe", "side": "W", "at": 0.0})
    assert d.furniture[0].rot == 270 and d.furniture[0].x < 0.5


def test_a_piece_in_the_middle_and_its_options():
    d = house({"step": "furniture", "room": "Living", "kind": "coffee_table", "side": "center", "colour": "walnut", "rotation": 90})
    [f] = d.furniture
    assert (f.x, f.y, f.rot, f.colour) == (2.5, 2.5, 90, "walnut")
    d = house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "S", "width": 2.4, "id": "my.sofa"})
    assert d.furniture[0].id == "my.sofa" and d.furniture[0].w == 2.4


def test_bad_furniture_steps_say_what_to_do():
    with pytest.raises(StepError, match="does not fit inside"):
        house({"step": "furniture", "room": "Kitchen", "kind": "bed_double", "side": "center", "width": 6})
    with pytest.raises(StepError, match="unknown furniture"):
        house({"step": "furniture", "room": "Living", "kind": "spaceship", "side": "S"})
    with pytest.raises(StepError, match="overlaps"):
        house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "S", "at": 0.5},
              {"step": "furniture", "room": "Living", "kind": "armchair", "side": "S", "at": 0.5})
    with pytest.raises(StepError, match="unknown colour"):
        house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "S", "colour": "sparkly"})
    with pytest.raises(StepError, match="rotation"):
        house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "center", "rotation": 45})


def test_the_same_id_replaces_a_piece():
    d = house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "S", "id": "s1"}, {"step": "furniture", "room": "Living", "kind": "sofa", "side": "N", "id": "s1"})
    assert len(d.furniture) == 1 and d.furniture[0].rot == 180


# --- furnish ------------------------------------------------------------------------------------------------------------------------
def test_furnish_fills_every_room_without_overlaps_or_blocked_doors():
    d = house({"step": "furnish", "room": "all"})
    spec = derive(d)                                   # derive validates fit, overlaps, door swings and stairs
    kinds = {f.kind for f in d.furniture}
    assert {"sofa", "tv_unit", "bed_double"} <= kinds or {"sofa", "tv_unit", "bed_single"} <= kinds
    assert {"sink_unit", "cooker", "fridge"} <= kinds
    assert len(spec.furniture) == len(d.furniture) > 8
    polys = [furniture_polygon(f) for f in d.furniture if f.room == "living" and f.kind != "ceiling_light"]
    assert all(a.intersection(b).area < 1e-4 for i, a in enumerate(polys) for b in polys[i + 1:])


def test_furnish_one_room_and_twice_adds_nothing_new():
    d = house({"step": "furnish", "room": "Bedroom"})
    assert {f.room for f in d.furniture} == {"bedroom"}
    again = apply_step(d, Step(step="furnish", room="Bedroom"))
    assert len(again.furniture) == len(d.furniture) and any("nothing more to add" in n for n in again.notes)


def test_furnish_keeps_pieces_off_the_door_swing():
    d = house({"step": "furnish", "room": "all"})
    spec = derive(d)
    from app.domain.furnish import keep_outs
    zones = keep_outs(spec)
    for f in spec.furniture:
        poly = Polygon(f.outline)
        assert f.kind == "ceiling_light" or all(poly.intersection(z).area < 1e-3 for z in zones.get(f.level, [])), f.id


def test_every_kind_of_room_gets_a_plausible_set_and_never_overlaps():
    for kind, rect in [("bedroom", (0, 0, 4, 4)), ("bedroom", (0, 0, 3, 3)), ("living", (0, 0, 6, 5)), ("kitchen", (0, 0, 5, 4)), ("dining", (0, 0, 4, 3.5)),
                       ("bathroom", (0, 0, 2.5, 2.5)), ("office", (0, 0, 3, 3)), ("utility", (0, 0, 2.5, 2.5)), ("hall", (0, 0, 3, 3)), ("garage", (0, 0, 3, 6))]:
        room = __import__("app.domain.design", fromlist=["Room"]).Room(id=kind, name=kind.title(), level="L1", kind=kind, rect=rect)
        counter: dict[str, int] = {}

        def nid(k, counter=counter, kind=kind):
            counter[k] = counter.get(k, 0) + 1
            return f"furn.{kind}.{k}.{counter[k]}"
        out = layout_room(room, [], [], nid)
        polys = [furniture_polygon(f) for f in out if f.kind != "ceiling_light"]
        assert all(a.intersection(b).area < 1e-4 for i, a in enumerate(polys) for b in polys[i + 1:]), kind
        if kind in ("garage",):
            assert out == []
        elif kind == "hall":
            assert [f.kind for f in out] == ["ceiling_light"]
        else:
            assert out, kind


# --- finishes ------------------------------------------------------------------------------------------------------------------------
def test_finish_sets_floor_and_walls_for_one_room_or_all():
    d = house({"step": "finish", "room": "Living", "floor": "oak", "walls": "cream"})
    assert (d.room("living").floor, d.room("living").walls, d.room("kitchen").floor) == ("oak", "cream", None)
    d = apply_step(d, Step(step="finish", room="all", walls="#aabbcc"))
    assert {r.walls for r in d.rooms} == {"#aabbcc"} and d.room("living").floor == "oak"
    d = apply_step(d, Step(step="finish", room="Living", floor="none"))
    assert d.room("living").floor is None


def test_a_bad_finish_says_what_is_allowed():
    with pytest.raises(StepError, match="floor finish.*oak"):
        house({"step": "finish", "room": "Living", "floor": "sparkly"})
    with pytest.raises(StepError, match="floor' and/or 'walls"):
        house({"step": "finish", "room": "Living"})


def test_derive_makes_a_floor_skin_and_wall_skins_with_holes_for_openings():
    d = house({"step": "finish", "room": "Living", "floor": "oak", "walls": "cream"})
    spec = derive(d)
    floors = [c for c in spec.coverings if c.kind == "floor"]
    walls = [c for c in spec.coverings if c.kind == "wall"]
    assert len(floors) == 1 and 21 < floors[0].area < 24 and floors[0].colour == "#b89464"
    assert len(walls) >= 4 and all(c.colour == "#efe3c8" and c.normal for c in walls)
    assert any(c.holes for c in walls)                                                      # the door and the window
    south = next(c for c in walls if c.id.endswith(".living") and "S" in c.id.split(".")[-2:] or "living.S" in c.id)
    assert south.area < south.length * south.height


def test_deleting_a_room_removes_its_furniture_and_resizing_prunes_what_no_longer_fits():
    d = house({"step": "furnish", "room": "all"})
    d2 = apply_step(d, Step(step="delete", id="bedroom"))
    assert not any(f.room == "bedroom" for f in d2.furniture)
    one = house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "E", "id": "far"})
    shrunk = apply_step(one, Step(step="room", level="L1", name="Living", kind="living", rect=[0, 0, 2, 5]))
    with pytest.raises(DesignError):
        derive(shrunk)
    kept, removed = prune_invalid_openings(shrunk)
    assert not kept.furniture and any("furniture far removed" in r for r in removed)


def test_furniture_in_front_of_a_door_is_refused_by_derive():
    d = house({"step": "furniture", "room": "Living", "kind": "wardrobe", "side": "S", "at": 0.5, "id": "blocker"})
    spec_ok = None
    try:
        spec_ok = derive(d)
    except DesignError as exc:
        assert exc.opening_id == "blocker" and "door swings" in str(exc)
    assert spec_ok is None or all(f.id != "blocker" for f in spec_ok.furniture)


# --- IFC ------------------------------------------------------------------------------------------------------------------------------
def furnished_model():
    d = house({"step": "furnish", "room": "all"}, {"step": "finish", "room": "all", "floor": "oak", "walls": "white"})
    spec = derive(d)
    model, _ = compile_ifc(spec)
    return d, spec, model


def test_ifc_has_furniture_and_coverings_with_real_geometry():
    d, spec, model = furnished_model()
    pieces = model.by_type("IfcFurniture")
    lamps = model.by_type("IfcLightFixture")
    assert len(pieces) + len(lamps) == len(d.furniture) and all(p.Name for p in [*pieces, *lamps]) and all(p.Tag.startswith("furn.") for p in pieces)
    kinds = {c.PredefinedType for c in model.by_type("IfcCovering")}
    assert kinds == {"FLOORING", "CLADDING"}
    settings = ifcopenshell.geom.settings()
    for el in [*pieces[:6], *model.by_type("IfcCovering")[:10]]:
        shape = ifcopenshell.geom.create_shape(settings, el)
        assert len(shape.geometry.verts) >= 24
    sofa = next(p for p in pieces if "sofa" in p.Tag)
    zs = ifcopenshell.geom.create_shape(settings, sofa).geometry.verts[2::3]
    assert min(zs) == pytest.approx(0.0, abs=0.01) and 0.8 < max(zs) < 0.9
    assert len(model.by_type("IfcStyledItem")) > 20


def test_a_wall_covering_sits_just_inside_its_room():
    d = house({"step": "finish", "room": "Living", "walls": "cream"})
    model, _ = compile_ifc(derive(d))
    settings = ifcopenshell.geom.settings()
    inside = 0
    for cov in (c for c in model.by_type("IfcCovering") if c.PredefinedType == "CLADDING"):
        v = ifcopenshell.geom.create_shape(settings, cov).geometry.verts
        xs, ys, zs = v[0::3], v[1::3], v[2::3]
        assert -0.01 <= min(zs) and max(zs) <= 3.01
        assert -0.2 <= min(xs) and max(xs) <= 5.2 and -0.2 <= min(ys) and max(ys) <= 5.2           # the living room is 5 x 5 m at the origin
        inside += 1
    assert inside >= 4


def test_an_archway_is_a_hole_with_no_door_in_it():
    d = house({"step": "door", "room": "Living", "to": "Kitchen", "kind": "opening", "width": 2.0, "id": "door.living.kitchen"})       # replaces the door in that wall
    spec = derive(d)
    arch = next(o for o in spec.openings if o.id == "door.living.kitchen")
    assert arch.style == "opening" and arch.width == 2.0
    model, _ = compile_ifc(spec)
    tags = {e.Tag for e in model.by_type("IfcDoor")}
    assert "door.living.kitchen" not in tags and len(model.by_type("IfcOpeningElement")) == len(spec.openings)
    doc = build_dxf(spec)
    assert len(doc.modelspace().query('ARC[layer=="A-DOOR"]')) == len([o for o in spec.openings if o.kind == "door" and o.style != "opening"])


# --- drawings and numbers ----------------------------------------------------------------------------------------------------------
def test_dxf_draws_each_piece_with_a_front_line_on_its_own_layer():
    d, spec, _ = furnished_model()
    msp = build_dxf(spec).modelspace()
    outlines = msp.query('LWPOLYLINE[layer=="A-FURN"]')
    lines = msp.query('LINE[layer=="A-FURN"]')
    assert len(outlines) == len(spec.furniture) == len(lines)


def test_quantities_count_furniture_and_measure_finishes():
    d, spec, _ = furnished_model()
    rows = {(r["group"], r["item"]): r for r in quantities(spec)["rows"]}
    assert rows[("Furniture", "Sofa")]["qty"] == 1
    floor, wall = rows[("Finishes", "Floor finish: oak")], rows[("Finishes", "Wall finish: white")]
    assert 50 < floor["qty"] < 60 and wall["qty"] > 100 and floor["unit"] == wall["unit"] == "m2"


# --- what the model is told -------------------------------------------------------------------------------------------------------------
def test_the_design_text_lists_furniture_and_finishes_and_focus_can_name_them():
    d = house({"step": "furnish", "room": "Living"}, {"step": "finish", "room": "Living", "floor": "oak"})
    text = describe(d)
    assert "floor=oak" in text and "FURNITURE furn.living.sofa: sofa" in text and "back to the south" in text or "back to the north" in text
    assert "the sofa furn.living.sofa in Living" in describe_focus(d, "furn.living.sofa")
    assert "floor finish (oak)" in describe_focus(d, "covering.floor.L1.living")
    sel = describe_selection(d, ["furn.living.sofa", "covering.floor.L1.living"])
    assert "2 elements" in sel and "ROOMS INVOLVED: living 'Living'" in sel


# --- the requirement ------------------------------------------------------------------------------------------------------------------------
def test_a_furnished_requirement_is_measured():
    want = checks.normalise({"kind": "feature", "keyword": "furnished", "text": "The rooms are furnished", "supported": False})
    assert want["supported"] is True
    assert checks.check(house(), [want])[0]["status"] == "unmet"
    assert "furnish step" in checks.check(house(), [want])[0]["detail"]
    assert checks.check(house({"step": "furnish", "room": "all"}), [want])[0]["status"] == "met"


def test_a_piece_is_changed_by_its_id_and_keeps_what_was_not_mentioned():
    d = house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "S", "id": "s1"})
    before = d.furniture[0]
    d = apply_step(d, Step(step="furniture", id="s1", colour="blue", width=2.4))
    after = d.furniture[0]
    assert (after.kind, after.rot, after.x, after.y, after.colour, after.w) == (before.kind, before.rot, before.x, before.y, "blue", 2.4)
    deeper = apply_step(d, Step(step="furniture", id="s1", depth=1.1))
    assert deeper.furniture[0].d == 1.1 and deeper.furniture[0].y - 1.1 / 2 == pytest.approx(before.y - before.d / 2, abs=0.01)     # the back stays against the wall
    moved = apply_step(d, Step(step="furniture", id="s1", side="N"))
    assert moved.furniture[0].rot == 180 and moved.furniture[0].colour == "blue" and len(moved.furniture) == 1
    with pytest.raises(StepError, match="'kind' is required"):
        apply_step(d, Step(step="furniture", room="Living", side="N"))


def test_an_archway_can_take_almost_the_whole_wall():
    d = house({"step": "door", "room": "Living", "to": "Kitchen", "kind": "opening", "width": 3.9, "id": "door.living.kitchen"})       # the shared wall is 4 m
    spec = derive(d)
    arch = next(o for o in spec.openings if o.id == "door.living.kitchen")
    assert arch.width == 3.9 and abs(arch.offset - 2.0) < 0.06
    with pytest.raises(DesignError, match="no free space"):
        derive(house({"step": "door", "room": "Living", "to": "Kitchen", "kind": "garage", "width": 3.9, "id": "door.living.kitchen"}))     # a real door keeps its margins


def test_a_new_door_moves_furniture_out_of_the_way_instead_of_being_refused():
    import asyncio
    from app.pipeline.stream import StepStream

    async def _noop(*a, **k):
        return None

    d = build(*BASE[:4], {"step": "furniture", "room": "Kitchen", "kind": "fridge", "side": "N", "at": 0.0, "id": "f1"}, {"step": "window", "room": "Living", "side": "W"})
    stream = StepStream(d, _noop, lambda x: None)
    asyncio.run(stream.feed_steps([{"step": "door", "room": "Kitchen", "to": "outside", "side": "N", "at": 0.0, "id": "d9"}]))
    assert stream.rejections == [] and any(x.id == "d9" for x in stream.design.doors)
    assert not any(f.id == "f1" for f in stream.design.furniture) and any("furniture f1 removed" in n for n in stream.design.notes)


def test_a_door_too_wide_for_its_wall_is_told_about_archways():
    with pytest.raises(DesignError, match='use kind "opening"'):
        derive(house({"step": "door", "room": "Living", "to": "Kitchen", "kind": "garage", "width": 3.9, "id": "door.living.kitchen"}))


def test_an_archway_replaces_the_door_already_in_that_wall_without_being_told_to():
    d = house({"step": "door", "room": "Living", "to": "Kitchen", "kind": "opening", "width": 3.8})
    assert [x.kind for x in d.doors if {x.room, x.to} == {"living", "kitchen"}] == ["opening"]
    derive(d)


def test_a_door_wider_than_any_door_is_taken_to_mean_an_archway():
    d = house({"step": "door", "room": "Living", "to": "Kitchen", "width": 3.8})                    # no kind given, and far too wide for a door
    assert [x.kind for x in d.doors if {x.room, x.to} == {"living", "kitchen"}] == ["opening"]
    d = house({"step": "door", "room": "Living", "to": "Kitchen", "width": 1.6, "kind": "double", "id": "door.living.kitchen"})
    assert [x.kind for x in d.doors if {x.room, x.to} == {"living", "kitchen"}] == ["double"]


# --- lights, corners, gaps ---------------------------------------------------------------------------------------------------------------------
def test_furnish_hangs_lights_from_the_ceiling_over_the_furniture():
    d = house({"step": "furnish", "room": "all"})
    lights = [f for f in d.furniture if f.kind == "ceiling_light"]
    assert {f.room for f in lights} == {"living", "kitchen", "bedroom"} and len(lights) >= 3
    spec = derive(d)                                                    # lights over a sofa are fine: derive does not count them as in the way
    fixture = next(f for f in spec.furniture if f.kind == "ceiling_light")
    assert fixture.z0 == pytest.approx(3.0 - 0.12, abs=0.01) and all(b.z0 >= 2.8 for b in fixture.boxes)
    model, _ = compile_ifc(spec)
    assert len(model.by_type("IfcLightFixture")) >= len(lights) and not any("light" in p.Tag for p in model.by_type("IfcFurniture"))


def test_a_big_room_gets_more_than_one_light_and_they_keep_apart():
    room = __import__("app.domain.design", fromlist=["Room"]).Room(id="hall", name="Hall", level="L1", kind="living", rect=(0, 0, 8, 6))
    counter: dict[str, int] = {}

    def nid(k, counter=counter):
        counter[k] = counter.get(k, 0) + 1
        return f"furn.hall.{k}.{counter[k]}"
    out = [f for f in layout_room(room, [], [], nid) if f.kind == "ceiling_light"]
    assert len(out) >= 3
    assert all(furniture_polygon(a).intersection(furniture_polygon(b)).area < 1e-4 for i, a in enumerate(out) for b in out[i + 1:])


def test_a_piece_can_go_in_a_corner_stand_off_the_wall_or_be_turned():
    d = house({"step": "furniture", "room": "Living", "kind": "armchair", "side": "NE", "id": "chair"})
    c = d.furniture[0]
    assert c.rot == 180 and c.x > 4.0 and c.y > 4.0                    # north wall, pushed to the east
    d = house({"step": "furniture", "room": "Living", "kind": "bed_double", "side": "N", "gap": 0.3, "id": "bed"})
    edge = house({"step": "furniture", "room": "Living", "kind": "bed_double", "side": "N", "id": "bed"}).furniture[0]
    assert d.furniture[0].y == pytest.approx(edge.y - 0.3, abs=0.001)
    d = house({"step": "furniture", "room": "Living", "kind": "sofa", "side": "W", "rotation": 180, "id": "turned"})
    assert d.furniture[0].rot == 180 and derive(d)                         # turned, and slid back inside the room


def test_a_plant_and_a_lamp_are_in_the_catalogue_and_the_quantities():
    d = house({"step": "furniture", "room": "Living", "kind": "plant", "side": "NW"}, {"step": "furniture", "room": "Living", "kind": "lamp", "side": "SE"})
    assert {f.kind for f in d.furniture} == {"plant", "floor_lamp"}
    rows = {(r["group"], r["item"]) for r in quantities(derive(d))["rows"]}
    assert ("Furniture", "Plant") in rows and ("Furniture", "Floor lamp") in rows
