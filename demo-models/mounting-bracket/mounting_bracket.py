"""L-bracket demo part: block-and-feature modeling, holes, fillets, chamfers.

Coordinate convention:
    Origin: center of the base mounting hole pattern, on the back-bottom
            datum edge where the base plate meets the wall.
    XY:     base plate plane (Z = 0 at the underside of the base).
    +Z:     up, wall extrusion direction.
"""

from build123d import *

# --- Parameters -------------------------------------------------------
length = 80.0  # overall bracket length (X)
base_depth = 50.0  # base plate depth (Y)
wall_height = 60.0  # wall height above the base (Z)
thickness = 6.0  # plate/wall wall thickness

inner_fillet_radius = 5.0  # stress-relief fillet at the concave L corner
outer_chamfer = 1.0  # deburring chamfer on outer perimeter edges

base_hole_diameter = 5.5  # M5 clearance
base_hole_cbore_diameter = 9.0  # M5 socket-head cap screw head clearance
base_hole_cbore_depth = 3.0
base_hole_offset_x = 25.0
base_hole_offset_y = base_depth - 12.0

wall_hole_diameter = 4.5  # M4 clearance
wall_hole_offset_x = 25.0
wall_hole_offset_z = wall_height - 15.0

base_hole_positions = [
    (-base_hole_offset_x, base_hole_offset_y),
    (base_hole_offset_x, base_hole_offset_y),
]
wall_hole_positions = [
    (-wall_hole_offset_x, wall_hole_offset_z),
    (wall_hole_offset_x, wall_hole_offset_z),
]

base_top_plane = Plane.XY.offset(thickness)
back_plane = Plane.XZ  # outward normal -Y, origin on the back-bottom edge


def gen_step():
    with BuildPart() as bracket:
        # base plate
        with BuildSketch(Plane.XY):
            Rectangle(length, base_depth, align=(Align.CENTER, Align.MIN))
        extrude(amount=thickness)

        # wall
        with BuildSketch(Plane.XY):
            Rectangle(length, thickness, align=(Align.CENTER, Align.MIN))
        extrude(amount=wall_height)

        # base mounting holes: through clearance hole + top counterbore
        with Locations(base_top_plane):
            with Locations(*base_hole_positions):
                CounterBoreHole(
                    radius=base_hole_diameter / 2,
                    counter_bore_radius=base_hole_cbore_diameter / 2,
                    counter_bore_depth=base_hole_cbore_depth,
                    depth=thickness + 1.0,
                )

        # wall clearance holes, through the wall thickness
        with Locations(back_plane):
            with Locations(*wall_hole_positions):
                Hole(radius=wall_hole_diameter / 2, depth=thickness + 1.0)

        # inside corner stress-relief fillet, along the concave L edge
        inner_corner_edges = [
            e
            for e in bracket.edges()
            if abs(e.center().Y - thickness) < 1e-6
            and abs(e.center().Z - thickness) < 1e-6
        ]
        fillet(inner_corner_edges, radius=inner_fillet_radius)

        # outer perimeter deburring chamfers: base underside + wall top
        outer_edges = bracket.edges().group_by(Axis.Z)[0] + bracket.edges().group_by(
            Axis.Z
        )[-1]
        chamfer(outer_edges, length=outer_chamfer)

    part = bracket.part
    part.label = "mounting_bracket"
    return part
