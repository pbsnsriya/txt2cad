# What txt2cad builds

Generated from `backend/app/domain/envelope.py`; the Home screen and `GET /api/capabilities` say the same thing. Anything in the last section is
named in the result as "not built" instead of being left out quietly.

## Builds today

| What | Note |
| --- | --- |
| Houses, flats, small offices and shops of 1 to 5 storeys | Rooms are rectangles on a grid, packed edge to edge. Many more storeys are accepted but only up to 5 are tested. |
| Doors, windows, archways and one straight stair per storey | A door wider than 2 m is read as an archway, which is how a wall is opened up. |
| Sizes you state: room sizes, the overall footprint, total areas | Checked after the build and shown as asked against built; metres or feet. |
| Flat, gable, hip and shed roofs | On plain rectangular roof areas. An L-shaped area stays flat and the version says so. |
| Furniture, floor finishes and wall paint | 30 pieces drawn as simple blocks, including ceiling and floor lights and a plant, in colours. No textures. |
| IFC4, DXF and SVG floor plans, and JSON | Plans have dimensions, door swings, stairs and furniture footprints. |

## Partly: read the note

| What | Note |
| --- | --- |
| L-shaped and U-shaped houses, and courtyards | Built from rectangles that touch, with the notch left empty. Whether the model gets it right is checked and reported. |
| Design check and quantities | A few dwelling rules in the style of the US IRC, labelled indicative. Quantities have no prices. |
| Offices, classrooms, shops and workshops | As room kinds with the same walls, doors and windows. No occupancy, egress or accessibility rules. |

## Not built yet

| What | Note |
| --- | --- |
| Basements and cellars | Reported as not built; the rest is built without it. |
| Balconies, porches, verandas, pools, gardens and the plot | Reported as not built. |
| Curved or angled walls, domes, round rooms | Walls are straight and square. |
| Structure and services | No columns, beams, ducts, pipes, wiring or lifts. |
| Textures, computed lighting and rendered images | Colours only. "Save picture" saves the 3D view as it is. |
| Importing an existing IFC or DWG to edit | Projects start from a description. |

## Words that are flagged before you send

balcony, basement, cellar, circular, curved wall, curved walls, dome, elevator, escalator, garden, landscaping, lift, pool, porch, round room, swimming pool, terrace, veranda, verandah
