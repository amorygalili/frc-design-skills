"""FRC 2026 ground intake -- parallelogram four-bar linkage mechanism.

A "4 bar intake" in FRC almost always means a parallelogram linkage: the
frame (side plate), a drive arm, a follower arm, and a floating carriage
that holds the intake roller. Because the drive arm and follower arm are
the SAME length and the frame/carriage pivot spacing is equal on both
links, the carriage keeps a constant orientation through the whole swing
(it translates along an arc but never rotates relative to the frame) --
that is what lets the roller bar stay parallel to the floor from stowed
to deployed. This generator implements that true parallelogram, not a
general (non-parallel) 4-bar.

Kinematic chain (built with build123d joints via AssemblyHelper, since
this is a closed loop that the joint tree cannot solve on its own):

    side_plate (root, fixed)
      -> drive_arm     [RevoluteJoint at pivot A, angle = deploy_angle_deg]
        -> carriage_plate [RevoluteJoint at drive_arm far pivot,
                            angle = -deploy_angle_deg -> cancels the drive
                            arm's rotation, so the carriage's net rotation
                            relative to the plate is always 0]
          -> follower_arm [RevoluteJoint at carriage pivot B',
                            angle = deploy_angle_deg -> lands back on the
                            plate's physical pivot B bore if arm_length /
                            pivot_spacing are consistent; validated with
                            `inspect measure` after generation]

Left and right sides are independent copies of this chain (mirrored
plate/carriage geometry, shared arm part), joined by one roller shaft
that carries the intake wheels.

Coordinate convention:
    Origin: intake centerline (X=0), at the frame drive-pivot (pivot A)
            height and fore/aft position (Y=0, Z=0 at pivot A).
    +X: left side plate -> right side plate (pivot/shaft axis direction).
    +Y: forward -- the direction the roller bar swings out from the frame.
    +Z: up.
    Units: mm. Angles: degrees.

Each plate/carriage/arm part is authored with the easy build123d default
(BuildSketch(Plane.XY), extrude +Z for thickness) using its own local
(x=in-plane asymmetry axis, y=up, z=thickness/bore axis) convention, then
placed. Root parts (the two side plates) get an explicit `.location`
that maps local x -> world Y, local y -> world Z, local z -> world X, so
the pivot bore axis (local Z) becomes the world pivot axis (world X).
Everything else is chained onto the plates with joints, which resolve
world orientation automatically.

COTS provenance (see parts/, exported with the $frc-design-lib skill from
FRC Design Lib's Onshape documents; dimensions below are measured from the
downloaded STEP files with `inspect refs --facts`, not guessed):

    flanged_radial_bearing.step
        "Flanged Radial Bearing", default ("Generic") configuration --
        0.375in ID round-bore radial bearing. Measured: bore assumed
        9.525 mm (3/8in, per the config's own dimension label -- bore is
        an internal feature and does not show in a bounding box), flange
        OD 24.6 mm, axial width 7.14 mm. Used at every pivot bore (frame,
        carriage, and roller-shaft support) -- 10 total per assembly.
    compliant_wheel_am_outer_diameter_3_bore_1_2_hex_durometer_40a.step
        "Compliant Wheel (AM)", Outer Diameter=3in, Bore=1/2in Hex,
        Durometer=40A. Measured: OD 76.2 mm, tread width 25.4 mm, axis
        along the part's local Y. 3 used on the roller shaft.
    neo_brushless_motor.step
        "NEO Brushless Motor", default configuration. Mounted on the
        LEFT (drive) side plate at pivot A as a mounting-datum reference
        only -- a production robot needs an external reduction stage
        (e.g. a small gearbox or worm stage) between the NEO and the
        pivot shaft, which is not modeled here.

Deliberate simplifications (first-pass mechanism, not a build-ready BOM):
    - Pivot shafts/pins and the roller shaft are modeled as simple local
      stock (round pin, stepped hex/round shaft), not sourced as COTS --
      they are cut-to-length raw stock rather than a distinct named part.
    - No wheel retaining clips/collars, hard stops, or belt/chain roller
      drive are modeled.
    - The frame rail itself is not modeled; the plates carry a 2-bolt
      mounting pattern sized for a generic FRC 2x1in rail face, but no
      rail geometry is included.
"""

import math

from build123d import *
from cadpy.assembly import AssemblyHelper

# --- Linkage geometry (parallelogram: equal arm lengths, equal frame and
#     carriage pivot spacing keep the carriage orientation constant) -----
arm_length = 260.0  # frame pivot to carriage pivot, both arms equal
pivot_spacing = 63.5  # pivot A to pivot B, frame side AND carriage side
deploy_angle_deg = 40.0  # arm sweep from the local "hanging straight down"
# reference (0 deg), rotating toward +Y (forward/deployed)

# --- Track / plate geometry ----------------------------------------------
track_width = 460.0  # clear span between inner faces of the L/R plates
plate_thickness = 3.175  # 1/8in 6061 aluminum
plate_corner_fillet = 8.0
plate_x_left_outer = -(track_width / 2 + plate_thickness)
plate_x_right_outer = track_width / 2 + plate_thickness

# --- Bearing (COTS -- see module docstring for provenance/measurement) ---
bearing_bore = 9.525
bearing_flange_od = 24.6
bearing_width = 7.14
bearing_pocket_clearance = 0.2
bearing_pocket_diameter = bearing_flange_od + bearing_pocket_clearance
bearing_pocket_depth = bearing_width
plate_bore_through_diameter = bearing_bore + 1.0  # shaft clearance past the bearing

# --- Pivot shaft/pin (local stock, not COTS) ------------------------------
pivot_shaft_diameter = bearing_bore - 0.05  # light running clearance in the bearing bore
pivot_shaft_length = bearing_width + 14.0  # bearing width + arm boss + margin

# --- Arm (drive_arm and follower_arm share this part -- parallelogram
#     requires equal length) -------------------------------------------
arm_boss_diameter = 20.0
arm_bar_width = 15.0
arm_shaft_through_diameter = pivot_shaft_diameter + 0.3  # clearance/press-fit rep.

# --- Side (frame) plate ---------------------------------------------------
side_plate_x_min = -20.0
side_plate_x_max = 45.0
side_plate_y_min = -pivot_spacing - 20.0
side_plate_y_max = 60.0
rail_mount_local_x = 8.0
rail_mount_local_y = 45.0
rail_mount_spacing = 40.0
rail_mount_hole_diameter = 5.5  # M5 clearance
lightening_pocket_diameter = 26.0
lightening_pocket_depth = plate_thickness / 2

# --- Carriage (floating link) plate --------------------------------------
carriage_x_min = -18.0
carriage_x_max = 55.0
carriage_y_min = -pivot_spacing - 18.0
carriage_y_max = 18.0
roller_offset_x = 32.0  # forward of the carriage pivot line
roller_offset_y = -pivot_spacing / 2  # vertically centered between A' and B'

# --- Roller shaft + compliant wheels (COTS -- see module docstring) ------
wheel_od = 76.2
wheel_width = 25.4
wheel_hex_af = 12.7  # 1/2in hex across-flats
wheel_count = 3
roller_shaft_stub_diameter = pivot_shaft_diameter  # reuse the bearing bore fit
roller_shaft_stub_length = bearing_width + 6.0
roller_shaft_hex_half_span = track_width / 2 - 10.0  # hex portion inboard of the plates


def _plate_outline(x_min, x_max, y_min, y_max):
    """Build a rounded-rectangle plate outline centered on its extents."""

    width = x_max - x_min
    height = y_max - y_min
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    with BuildSketch() as sk:
        with Locations((cx, cy)):
            RectangleRounded(width, height, radius=plate_corner_fillet)
    return sk.sketch


def make_side_plate():
    """Frame-side plate. Left and right plates are geometrically identical
    -- local x maps to world Y (forward) and local y to world Z (up) for
    both, unaffected by which side the plate is placed on; only the root
    placement's world-X offset differs between sides (see gen_step)."""

    with BuildPart() as part:
        add(_plate_outline(side_plate_x_min, side_plate_x_max, side_plate_y_min, side_plate_y_max))
        extrude(amount=plate_thickness)

        top_plane = Plane.XY.offset(plate_thickness)

        # pivot A / pivot B bearing pockets + shaft clearance through-bore
        with Locations(top_plane):
            with Locations((0, 0), (0, -pivot_spacing)):
                CounterBoreHole(
                    radius=plate_bore_through_diameter / 2,
                    counter_bore_radius=bearing_pocket_diameter / 2,
                    counter_bore_depth=bearing_pocket_depth,
                    depth=plate_thickness + 1.0,
                )

        # rail mounting holes (2x, clearance for bolting to a 2x1in rail face)
        rail_x = rail_mount_local_x
        rail_positions = [
            (rail_x - rail_mount_spacing / 2, rail_mount_local_y),
            (rail_x + rail_mount_spacing / 2, rail_mount_local_y),
        ]
        with Locations(top_plane):
            with Locations(*rail_positions):
                Hole(radius=rail_mount_hole_diameter / 2, depth=plate_thickness + 1.0)

        # lightening pocket between the pivots and the rail mount
        pocket_x = 10.0
        pocket_y = (0 + rail_mount_local_y) / 2 - 5.0
        with Locations(top_plane):
            with Locations((pocket_x, pocket_y)):
                Hole(radius=lightening_pocket_diameter / 2, depth=lightening_pocket_depth)

        # deburr top/bottom (thickness-direction) face perimeters
        z_edges = part.edges().group_by(Axis.Z)
        chamfer(z_edges[0] + z_edges[-1], length=0.5)

    p = part.part
    p.label = "side_plate"

    pivot_a_local = Axis((0, 0, plate_thickness / 2), (0, 0, 1))
    RevoluteJoint(label="pivot_a", to_part=p, axis=pivot_a_local, angular_range=(-180, 180))
    # bearing seats sit at the pocket mouth (top_plane, where the
    # CounterBoreHole pockets above were cut from).
    RigidJoint(
        label="bearing_seat_pivot_a",
        to_part=p,
        joint_location=Location((0, 0, plate_thickness)),
    )
    RigidJoint(
        label="bearing_seat_pivot_b",
        to_part=p,
        joint_location=Location((0, -pivot_spacing, plate_thickness)),
    )
    RigidJoint(
        label="motor_mount",
        to_part=p,
        joint_location=Location((0, 0, plate_thickness), (0, 90, 0)),
    )
    return p


def make_carriage_plate():
    """Floating-link plate carrying the roller. Left and right carriages are
    geometrically identical, same rationale as make_side_plate()."""

    with BuildPart() as part:
        add(_plate_outline(carriage_x_min, carriage_x_max, carriage_y_min, carriage_y_max))
        extrude(amount=plate_thickness)

        top_plane = Plane.XY.offset(plate_thickness)

        # pivot A' / pivot B' bearing pockets (mate the drive/follower arms)
        with Locations(top_plane):
            with Locations((0, 0), (0, -pivot_spacing)):
                CounterBoreHole(
                    radius=plate_bore_through_diameter / 2,
                    counter_bore_radius=bearing_pocket_diameter / 2,
                    counter_bore_depth=bearing_pocket_depth,
                    depth=plate_thickness + 1.0,
                )

        # roller-shaft bearing pocket
        roller_x = roller_offset_x
        with Locations(top_plane):
            with Locations((roller_x, roller_offset_y)):
                CounterBoreHole(
                    radius=plate_bore_through_diameter / 2,
                    counter_bore_radius=bearing_pocket_diameter / 2,
                    counter_bore_depth=bearing_pocket_depth,
                    depth=plate_thickness + 1.0,
                )

        z_edges = part.edges().group_by(Axis.Z)
        chamfer(z_edges[0] + z_edges[-1], length=0.5)

    p = part.part
    p.label = "carriage_plate"

    pivot_b_local = Axis((0, -pivot_spacing, plate_thickness / 2), (0, 0, 1))
    RigidJoint(label="pivot_a", to_part=p, joint_location=Location((0, 0, plate_thickness / 2)))
    RevoluteJoint(label="pivot_b", to_part=p, axis=pivot_b_local, angular_range=(-180, 180))
    # bearing seats sit at the pocket mouth (top_plane).
    RigidJoint(label="bearing_seat_pivot_a", to_part=p, joint_location=Location((0, 0, plate_thickness)))
    RigidJoint(
        label="bearing_seat_pivot_b",
        to_part=p,
        joint_location=Location((0, -pivot_spacing, plate_thickness)),
    )
    RigidJoint(
        label="roller_bearing_seat",
        to_part=p,
        joint_location=Location((roller_offset_x, roller_offset_y, plate_thickness)),
    )
    return p


def make_arm():
    """Drive/follower link -- shared part, boss-to-boss = arm_length."""

    boss_r = arm_boss_diameter / 2
    with BuildPart() as part:
        with BuildSketch():
            with Locations((0, 0), (0, -arm_length)):
                Circle(boss_r)
            with Locations((0, -arm_length / 2)):
                Rectangle(arm_bar_width, arm_length)
        extrude(amount=plate_thickness)

        top_plane = Plane.XY.offset(plate_thickness)
        with Locations(top_plane):
            with Locations((0, 0), (0, -arm_length)):
                Hole(radius=arm_shaft_through_diameter / 2, depth=plate_thickness + 1.0)

        z_edges = part.edges().group_by(Axis.Z)
        chamfer(z_edges[0] + z_edges[-1], length=0.5)

    p = part.part
    p.label = "arm"

    far_local = Axis((0, -arm_length, plate_thickness / 2), (0, 0, 1))
    # near_pivot: rigid attachment into the plate's pivot_a hinge.
    RigidJoint(label="near_pivot", to_part=p, joint_location=Location((0, 0, plate_thickness / 2)))
    # far_pivot_hinge: this arm acts as the drive link, providing the hinge
    # the carriage's pivot_a rigidly attaches into.
    RevoluteJoint(label="far_pivot_hinge", to_part=p, axis=far_local, angular_range=(-180, 180))
    # far_pivot_rigid: this arm acts as the follower link, attaching
    # rigidly into the carriage's pivot_b hinge.
    RigidJoint(label="far_pivot_rigid", to_part=p, joint_location=Location((0, -arm_length, plate_thickness / 2)))
    return p


def make_pivot_pin():
    """Simple pivot pin/shaft (local stock, press-fit into an arm boss,
    running clear in a plate/carriage bearing bore)."""

    with BuildPart() as part:
        Cylinder(radius=pivot_shaft_diameter / 2, height=pivot_shaft_length)
        chamfer(part.edges().group_by(Axis.Z)[0] + part.edges().group_by(Axis.Z)[-1], length=0.6)
    p = part.part
    p.label = "pivot_pin"
    RigidJoint(label="center", to_part=p, joint_location=Location((0, 0, -pivot_shaft_length / 2)))
    return p


def make_roller_shaft():
    """1/2in hex roller shaft with round stub ends for the carriage bearings."""

    hex_apothem = wheel_hex_af / 2
    total_length = 2 * roller_shaft_stub_length + 2 * roller_shaft_hex_half_span
    with BuildPart() as part:
        Cylinder(
            radius=roller_shaft_stub_diameter / 2,
            height=roller_shaft_stub_length,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        with Locations((0, 0, roller_shaft_stub_length)):
            with BuildSketch():
                RegularPolygon(radius=hex_apothem, side_count=6, major_radius=False)
            extrude(amount=2 * roller_shaft_hex_half_span)
        with Locations((0, 0, roller_shaft_stub_length + 2 * roller_shaft_hex_half_span)):
            Cylinder(
                radius=roller_shaft_stub_diameter / 2,
                height=roller_shaft_stub_length,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
    p = part.part
    p.label = "roller_shaft"
    # local Z is the shaft axis, local origin at the "left stub" outer end;
    # increasing local Z runs toward the right-side carriage.
    RigidJoint(label="left_end", to_part=p, joint_location=Location((0, 0, 0)))
    for i in range(wheel_count):
        t = (i + 0.5) / wheel_count
        z = roller_shaft_stub_length + t * (2 * roller_shaft_hex_half_span)
        RigidJoint(label=f"wheel_seat_{i}", to_part=p, joint_location=Location((0, 0, z - wheel_width / 2)))
    return p


def _mount_bearing(asm, host, seat_label, role, *details):
    bearing = asm.add(import_step("parts/flanged_radial_bearing.step"), "flanged_radial_bearing", *details)
    bearing_center = asm.rigid_frame(bearing, "center", Location((0, 0, 0)))
    asm.coaxial((host, seat_label), bearing_center, offset=0.0, label=f"bearing_{role}")
    return bearing


def _mount_pin(asm, host, seat_label, role, *details):
    pin = asm.add(make_pivot_pin(), "pivot_pin", *details)
    pin_center = asm.rigid_frame(pin, "center", Location((0, 0, 0)))
    asm.coaxial((host, seat_label), pin_center, offset=0.0, label=f"pin_{role}")
    return pin


def gen_step():
    asm = AssemblyHelper("four_bar_intake_2026")

    # -- Right side chain (root) -------------------------------------------------
    plate_r = make_side_plate()
    plate_r.location = Location(
        Plane(origin=(plate_x_right_outer - plate_thickness, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    )
    asm.add(plate_r, "side_plate", "right")
    _mount_bearing(asm, plate_r, "bearing_seat_pivot_a", "frame_a_right", "right", "pivot_a")
    _mount_bearing(asm, plate_r, "bearing_seat_pivot_b", "frame_b_right", "right", "pivot_b")

    drive_arm_r = make_arm()
    asm.add(drive_arm_r, "arm", "drive", "right")
    asm.revolute((plate_r, "pivot_a"), (drive_arm_r, "near_pivot"), angle=deploy_angle_deg, label="drive_pivot_right")
    _mount_pin(asm, drive_arm_r, "near_pivot", "drive_near_right", "right", "drive", "near")

    carriage_r = make_carriage_plate()
    asm.add(carriage_r, "carriage_plate", "right")
    asm.revolute(
        (drive_arm_r, "far_pivot_hinge"), (carriage_r, "pivot_a"), angle=-deploy_angle_deg, label="carriage_mount_right"
    )
    _mount_pin(asm, drive_arm_r, "far_pivot_rigid", "drive_far_right", "right", "drive", "far")
    _mount_bearing(asm, carriage_r, "bearing_seat_pivot_a", "carriage_a_right", "right", "carriage_a")
    _mount_bearing(asm, carriage_r, "bearing_seat_pivot_b", "carriage_b_right", "right", "carriage_b")

    follower_arm_r = make_arm()
    asm.add(follower_arm_r, "arm", "follower", "right")
    asm.revolute(
        (carriage_r, "pivot_b"), (follower_arm_r, "far_pivot_rigid"), angle=deploy_angle_deg, label="follower_pivot_right"
    )
    _mount_pin(asm, follower_arm_r, "far_pivot_rigid", "follower_far_right", "right", "follower", "far")
    _mount_pin(asm, follower_arm_r, "near_pivot", "follower_near_right", "right", "follower", "near")

    # -- Left side chain -----------------------------------------------------
    plate_l = make_side_plate()
    plate_l.location = Location(Plane(origin=(plate_x_left_outer, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
    asm.add(plate_l, "side_plate", "left")
    _mount_bearing(asm, plate_l, "bearing_seat_pivot_a", "frame_a_left", "left", "pivot_a")
    _mount_bearing(asm, plate_l, "bearing_seat_pivot_b", "frame_b_left", "left", "pivot_b")

    drive_arm_l = make_arm()
    asm.add(drive_arm_l, "arm", "drive", "left")
    asm.revolute((plate_l, "pivot_a"), (drive_arm_l, "near_pivot"), angle=deploy_angle_deg, label="drive_pivot_left")
    _mount_pin(asm, drive_arm_l, "near_pivot", "drive_near_left", "left", "drive", "near")

    carriage_l = make_carriage_plate()
    asm.add(carriage_l, "carriage_plate", "left")
    asm.revolute(
        (drive_arm_l, "far_pivot_hinge"), (carriage_l, "pivot_a"), angle=-deploy_angle_deg, label="carriage_mount_left"
    )
    _mount_pin(asm, drive_arm_l, "far_pivot_rigid", "drive_far_left", "left", "drive", "far")
    _mount_bearing(asm, carriage_l, "bearing_seat_pivot_a", "carriage_a_left", "left", "carriage_a")
    _mount_bearing(asm, carriage_l, "bearing_seat_pivot_b", "carriage_b_left", "left", "carriage_b")

    follower_arm_l = make_arm()
    asm.add(follower_arm_l, "arm", "follower", "left")
    asm.revolute(
        (carriage_l, "pivot_b"), (follower_arm_l, "far_pivot_rigid"), angle=deploy_angle_deg, label="follower_pivot_left"
    )
    _mount_pin(asm, follower_arm_l, "far_pivot_rigid", "follower_far_left", "left", "follower", "far")
    _mount_pin(asm, follower_arm_l, "near_pivot", "follower_near_left", "left", "follower", "near")

    # -- Roller shaft + compliant wheels (spans the two carriage plates) -----
    roller_shaft = make_roller_shaft()
    asm.add(roller_shaft, "roller_shaft")
    _mount_bearing(asm, carriage_l, "roller_bearing_seat", "roller_left", "left", "roller")
    _mount_bearing(asm, carriage_r, "roller_bearing_seat", "roller_right", "right", "roller")
    asm.coaxial((carriage_l, "roller_bearing_seat"), (roller_shaft, "left_end"), offset=0.0, label="roller_shaft_mount")

    for i in range(wheel_count):
        wheel = asm.add(
            import_step("parts/compliant_wheel_am_outer_diameter_3_bore_1_2_hex_durometer_40a.step"),
            "compliant_wheel_3in",
            i,
        )
        # Compliant Wheel (AM) is authored with its rolling axis along local
        # Y (measured: width along Y, OD in X/Z); rotate +90deg about X so
        # this mount frame's local Z (matched to the shaft axis) becomes
        # the wheel's actual rolling axis.
        wheel_center = asm.rigid_frame(wheel, "center", Location((0, 0, 0), (90, 0, 0)))
        asm.coaxial((roller_shaft, f"wheel_seat_{i}"), wheel_center, offset=0.0, label=f"wheel_mount_{i}")

    # -- Deploy drive motor (mounting datum only; see module docstring) ------
    motor = asm.add(import_step("parts/neo_brushless_motor.step"), "neo_brushless_motor", "deploy_drive")
    motor_mount_local = asm.rigid_frame(motor, "mount", Location((0, 0, 0)))
    asm.coaxial((plate_l, "motor_mount"), motor_mount_local, offset=0.0, label="deploy_motor_mount")

    return asm.build()
