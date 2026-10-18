import io

import ezdxf

from app.domain.derive import derive
from app.export.dxf import build_dxf, dxf_text
from tests.test_ifc import sample


def test_dxf_roundtrips_with_no_audit_errors_and_expected_entities():
    spec = derive(sample())
    text = dxf_text(spec)
    doc = ezdxf.read(io.StringIO(text))
    auditor = doc.audit()
    assert not auditor.errors, auditor.errors
    assert doc.units == ezdxf.units.M
    msp = doc.modelspace()
    count = lambda t, layer=None: len([e for e in msp.query(t) if layer is None or e.dxf.layer == layer])  # noqa: E731
    assert count("HATCH", "A-WALL-PATT") >= 2                      # one hatch per connected wall piece; doors can split a level
    assert count("ARC", "A-DOOR") == 2 and count("LINE", "A-DOOR") == 2
    assert count("LINE", "A-GLAZ") == 2 * 3                         # three lines per window
    assert len([e for e in msp.query("TEXT") if e.dxf.layer == "A-AREA-IDEN"]) == len(spec.spaces)
    assert count("DIMENSION") == 4                                   # two per level
    assert {"A-WALL", "A-DOOR", "A-GLAZ", "A-AREA-IDEN"} <= {la.dxf.name for la in doc.layers}


def test_walls_are_closed_outlines_with_openings_cut_out():
    doc = build_dxf(derive(sample()))
    outlines = [e for e in doc.modelspace().query("LWPOLYLINE") if e.dxf.layer == "A-WALL"]
    assert outlines and all(e.closed for e in outlines)


def test_levels_do_not_overlap_in_model_space():
    doc = build_dxf(derive(sample()))
    texts = sorted((e.dxf.insert.x, e.dxf.text) for e in doc.modelspace().query("TEXT") if e.dxf.layer == "A-ANNO-TTLB")
    assert len(texts) == 2 and texts[1][0] - texts[0][0] > 8
