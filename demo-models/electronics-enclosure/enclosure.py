"""Electronics enclosure demo assembly: shell, bosses, patterned vents,
labeled AssemblyHelper occurrences, and a source-level face-to-face joint.

Coordinate convention (shared by both parts, local origins):
    base: origin at footprint center, Z = 0 at the exterior bottom face,
          local Z spans [0, base_height]; top wall rim is the lid-mating datum.
    lid:  origin at footprint center, Z = 0 at the lid mid-plane,
          local Z spans [-lid_thickness / 2, +lid_thickness / 2].
    XY:   footprint plane for both parts.
    +Z:   up.
"""

from build123d import *
from cadpy.assembly import AssemblyHelper

# --- Parameters ---------------------------------------------------------
width = 90.0  # footprint X
depth = 60.0  # footprint Y
base_height = 25.0  # base tray exterior height
wall_thickness = 2.5  # uniform shell thickness (walls + floor)
lid_thickness = 3.0
lid_edge_fillet = 1.5

corner_inset = 8.0  # corner boss offset from each outer edge
corner_boss_diameter = 7.0
corner_pilot_diameter = 2.5  # M3 self-tap pilot
lid_hole_clearance_diameter = 3.4  # M3 clearance, through the lid

standoff_inset_x = 22.0  # PCB standoff pattern (smaller footprint, interior)
standoff_inset_y = 15.0
standoff_diameter = 6.0
standoff_pilot_diameter = 2.5
standoff_clear_below_lid = 8.0  # PCB + component clearance under the lid

vent_slot_length = 14.0
vent_slot_width = 3.0
vent_count = 5
vent_pitch = 16.0

interior_floor_z = wall_thickness  # interior floor top surface, base-local


def corner_positions(inset):
    hx = width / 2 - inset
    hy = depth / 2 - inset
    return [(-hx, -hy), (hx, -hy), (-hx, hy), (hx, hy)]


def make_base():
    boss_positions = corner_positions(corner_inset)
    boss_height = base_height - wall_thickness  # bosses reach the rim
    standoff_height = base_height - wall_thickness - standoff_clear_below_lid
    standoff_positions = [
        (-standoff_inset_x, -standoff_inset_y),
        (standoff_inset_x, -standoff_inset_y),
        (-standoff_inset_x, standoff_inset_y),
        (standoff_inset_x, standoff_inset_y),
    ]

    with BuildPart() as base:
        with BuildSketch(Plane.XY):
            Rectangle(width, depth)
        extrude(amount=base_height)

        top_face = base.faces().group_by(Axis.Z)[-1]
        offset(amount=-wall_thickness, openings=top_face)

        # corner mounting bosses (also support the lid at the rim height)
        with Locations(Plane.XY.offset(interior_floor_z)):
            with Locations(*boss_positions):
                Cylinder(
                    radius=corner_boss_diameter / 2,
                    height=boss_height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )

        # PCB standoffs, shorter interior pattern
        with Locations(Plane.XY.offset(interior_floor_z)):
            with Locations(*standoff_positions):
                Cylinder(
                    radius=standoff_diameter / 2,
                    height=standoff_height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )

        # blind pilot holes down each boss/standoff, drilled from the top
        with Locations(Plane.XY.offset(base_height)):
            with Locations(*boss_positions):
                Hole(radius=corner_pilot_diameter / 2, depth=boss_height - 1.5)

        with Locations(Plane.XY.offset(interior_floor_z + standoff_height)):
            with Locations(*standoff_positions):
                Hole(radius=standoff_pilot_diameter / 2, depth=standoff_height - 1.5)

    part = base.part
    part.label = "base"
    return part, boss_positions


def make_lid(boss_positions):
    top_plane = Plane.XY.offset(lid_thickness / 2)
    vent_positions = [
        ((-(vent_count - 1) / 2 + i) * vent_pitch, 0.0) for i in range(vent_count)
    ]

    with BuildPart() as lid:
        with BuildSketch(Plane.XY):
            Rectangle(width, depth)
        extrude(amount=lid_thickness, both=True)

        with Locations(top_plane):
            with Locations(*boss_positions):
                Hole(
                    radius=lid_hole_clearance_diameter / 2,
                    depth=lid_thickness + 1.0,
                )

        with BuildSketch(top_plane):
            with Locations(*vent_positions):
                Rectangle(vent_slot_length, vent_slot_width)
        extrude(amount=-(lid_thickness + 1.0), mode=Mode.SUBTRACT)

        top_edges = lid.edges().group_by(Axis.Z)[-1]
        fillet(top_edges, radius=lid_edge_fillet)

    part = lid.part
    part.label = "lid"
    return part


def gen_step():
    base_part, boss_positions = make_base()
    lid_part = make_lid(boss_positions)

    asm = AssemblyHelper("electronics_enclosure")
    base = asm.add(base_part, "base")
    lid = asm.add(lid_part, "lid")

    base_seat = asm.rigid_frame(base, "lid_seat", Location((0, 0, base_height)))
    lid_underside = asm.rigid_frame(lid, "underside", Location((0, 0, -lid_thickness / 2)))
    asm.face_to_face(base_seat, lid_underside, offset=0.0)

    return asm.build()
