"""step-parts skill demo: a bearing-mount plate assembled around catalog
hardware fetched from step.parts (no placeholder geometry for the
purchased parts).

Provenance (see parts/ and the `$step-parts` skill):
    bearing_608zz.step                        -- step.parts id "bearing_608zz"
    iso4762_socket_head_cap_screw_m3x12.step   -- step.parts id "iso4762_socket_head_cap_screw_m3x12"
Both were resolved with exact-match searches (no alias/facet disambiguation
needed) and downloaded with `scripts/download_step_part.py --download`,
which verifies each file's SHA-256 against the catalog record before
returning it.

Mating dimensions below are not guessed: the bearing OD/width and the screw
head diameter/height were taken from `scripts/inspect refs <part>.step
--facts` against the downloaded STEP files, per the imported-components
guidance in the CAD skill's positioning reference. The bearing bore (8 mm)
comes from the 608 bearing's standard bore designation, not from geometry.

Coordinate convention:
    Origin: plate footprint center, Z = 0 at the underside of the plate.
    XY:     plate face plane.
    +Z:     up, toward the bearing/screw seating face.
"""

from build123d import *
from cadpy.assembly import AssemblyHelper

# --- Plate parameters ---------------------------------------------------
plate_length = 70.0  # X
plate_width = 50.0  # Y
plate_thickness = 10.0
outer_chamfer = 0.5  # deburring chamfer, top + bottom perimeter and hole edges

# --- Bearing pocket (measured from parts/bearing_608zz.step) -------------
bearing_od = 22.0  # measured bounding-box diameter
bearing_width = 7.0  # measured bounding-box thickness
bearing_bore = 8.0  # 608 standard bore designation (not measured)
bearing_pocket_clearance = 0.2
bearing_pocket_diameter = bearing_od + bearing_pocket_clearance
bearing_pocket_depth = bearing_width + bearing_pocket_clearance
shaft_bore_diameter = bearing_bore + 0.4  # through-clearance for the shaft

# --- Corner screws (measured from parts/iso4762_socket_head_cap_screw_m3x12.step) --
screw_head_diameter = 5.5  # measured
screw_head_height = 3.0  # measured
screw_counterbore_diameter = screw_head_diameter + 0.5
screw_counterbore_depth = screw_head_height  # head sits flush with the top face
screw_clearance_diameter = 3.4  # M3 clearance

corner_inset = 10.0
corner_offset_x = plate_length / 2 - corner_inset
corner_offset_y = plate_width / 2 - corner_inset
screw_positions = [
    ("front_left", -corner_offset_x, corner_offset_y),
    ("front_right", corner_offset_x, corner_offset_y),
    ("rear_left", -corner_offset_x, -corner_offset_y),
    ("rear_right", corner_offset_x, -corner_offset_y),
]

top_plane = Plane.XY.offset(plate_thickness)


def make_plate():
    with BuildPart() as plate:
        with BuildSketch(Plane.XY):
            Rectangle(plate_length, plate_width)
        extrude(amount=plate_thickness)

        # bearing pocket + through shaft clearance bore, centered
        with Locations(top_plane):
            CounterBoreHole(
                radius=shaft_bore_diameter / 2,
                counter_bore_radius=bearing_pocket_diameter / 2,
                counter_bore_depth=bearing_pocket_depth,
                depth=plate_thickness + 1.0,
            )

        # corner screw holes: flush socket-head counterbore + M3 clearance through
        with Locations(top_plane):
            with Locations(*[(x, y) for _, x, y in screw_positions]):
                CounterBoreHole(
                    radius=screw_clearance_diameter / 2,
                    counter_bore_radius=screw_counterbore_diameter / 2,
                    counter_bore_depth=screw_counterbore_depth,
                    depth=plate_thickness + 1.0,
                )

        # deburr outer perimeter + hole edges, top and bottom faces
        outer_edges = plate.edges().group_by(Axis.Z)[0] + plate.edges().group_by(
            Axis.Z
        )[-1]
        chamfer(outer_edges, length=outer_chamfer)

    part = plate.part
    part.label = "bearing_mount_plate"
    return part


def gen_step():
    asm = AssemblyHelper("bearing_mount_plate_demo")
    plate = asm.add(make_plate(), "plate")
    bearing = asm.add(import_step("parts/bearing_608zz.step"), "bearing_608zz")

    plate_bearing_seat = asm.rigid_frame(
        plate, "bearing_seat", Location((0, 0, plate_thickness - bearing_width / 2))
    )
    bearing_center = asm.rigid_frame(bearing, "center", Location((0, 0, 0)))
    asm.coaxial(plate_bearing_seat, bearing_center, offset=0.0)

    for role, x, y in screw_positions:
        screw = asm.add(
            import_step("parts/iso4762_socket_head_cap_screw_m3x12.step"),
            f"m3x12_screw_{role}",
        )
        plate_screw_seat = asm.rigid_frame(
            plate,
            f"screw_seat_{role}",
            Location((x, y, plate_thickness - screw_counterbore_depth)),
        )
        screw_bearing_face = asm.rigid_frame(screw, "bearing_face", Location((0, 0, 0)))
        asm.face_to_face(plate_screw_seat, screw_bearing_face, offset=0.0)

    return asm.build()
