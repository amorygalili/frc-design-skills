"""URDF skill feature demo: a small 3-DOF arm on a fixed base.

Design ledger
=============

Robot metadata
    name: urdf_arm_demo
    target consumers: RViz / robot_state_publisher (illustrative demo, not a
        real product) -- geometry uses primitives so no mesh assets are needed.
    units: meters, kilograms, seconds, radians (URDF default convention).
    frame convention: REP-103-style, right-handed, +Z up at the root frame.
    mesh units: n/a (primitive-only geometry).
    source of dimensions: none -- every dimension, mass, and inertia in this
        file is an ASSUMED_* placeholder chosen only to keep the model
        physically valid and visually legible. Do not treat any of it as a
        real robot's specification.

Link ledger (name / role / frame / parent joint)
    base_footprint   frame-only, ground projection of the robot         : none (root)
    base_link        physical, pedestal box                            : base_footprint_to_base
    shoulder_link    physical, pan cylinder on top of the base          : shoulder_pan_joint
    upper_arm_link   physical, lift link driven from the shoulder       : shoulder_lift_joint
    forearm_link     physical, telescoping link                        : forearm_extend_joint
    wrist_link       physical, roll sphere at the end of the forearm    : wrist_roll_joint
    tool0            frame-only, tool control point                    : wrist_to_tool0

Joint ledger (name / type / axis / positive motion)
    base_footprint_to_base  fixed       n/a          rigidly places base_link above the ground frame
    shoulder_pan_joint      revolute    +Z (joint)   CCW pan of the arm viewed from +Z looking down
    shoulder_lift_joint     revolute    +Y (joint)   rotates the upper arm from horizontal (0) toward +Z (up)
    forearm_extend_joint    prismatic   +X (joint)   extends the forearm away from the upper arm
    wrist_roll_joint        continuous  +X (joint)   rolls the wrist/tool about the forearm's long axis
    wrist_to_tool0          fixed       n/a          places the tool control point at the wrist surface

Geometry ledger
    Visual and collision geometry are primitives (box/cylinder/sphere) so the
    file is self-contained. upper_arm_link intentionally uses a simplified
    collision cylinder instead of repeating its visual box, to demonstrate
    that visual and collision geometry may differ (see frame-semantics.md).

Inertial ledger
    Every physical link's inertia tensor is computed from its mass and
    primitive dimensions with the standard solid-primitive formulas below
    (see _box_inertia / _cylinder_inertia_about_z / _sphere_inertia), so the
    ASSUMED_* mass/dimension constants stay the single source of truth.
    confidence: placeholder (chosen for validity/legibility, not measured).

Assumption ledger
    All masses, dimensions, joint limits, and effort/velocity limits are
    ASSUMED_* placeholders for demo purposes; none are sourced from CAD,
    drawings, or vendor data.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

ROBOT_NAME = "urdf_arm_demo"

# --- base -------------------------------------------------------------
# base_footprint is a frame-only ground reference; base_link is the
# physical pedestal sitting on top of it.
ASSUMED_BASE_SIZE_XYZ_M = (0.30, 0.30, 0.08)
ASSUMED_BASE_MASS_KG = 4.0
# base_link center sits half its own height above base_footprint.
BASE_FOOTPRINT_TO_BASE_Z_M = ASSUMED_BASE_SIZE_XYZ_M[2] / 2.0

# --- shoulder (revolute pan) -------------------------------------------
ASSUMED_SHOULDER_RADIUS_M = 0.06
ASSUMED_SHOULDER_LENGTH_M = 0.12
ASSUMED_SHOULDER_MASS_KG = 1.5
SHOULDER_PAN_AXIS = (0.0, 0.0, 1.0)
# shoulder_link center sits on top of base_link, offset by half its own length.
SHOULDER_PAN_JOINT_Z_M = ASSUMED_BASE_SIZE_XYZ_M[2] / 2.0 + ASSUMED_SHOULDER_LENGTH_M / 2.0
ASSUMED_SHOULDER_PAN_LOWER_DEG = -170.0
ASSUMED_SHOULDER_PAN_UPPER_DEG = 170.0

# --- upper arm (revolute lift) -----------------------------------------
ASSUMED_UPPER_ARM_SIZE_XYZ_M = (0.28, 0.06, 0.06)
ASSUMED_UPPER_ARM_MASS_KG = 1.2
SHOULDER_LIFT_AXIS = (0.0, 1.0, 0.0)
# upper_arm_link's joint frame is at the top of the shoulder cylinder.
SHOULDER_LIFT_JOINT_Z_M = ASSUMED_SHOULDER_LENGTH_M / 2.0
# the box extends from the joint frame along +X, so its own visual/collision
# origin is offset by half its length.
UPPER_ARM_GEOMETRY_X_M = ASSUMED_UPPER_ARM_SIZE_XYZ_M[0] / 2.0
# simplified collision cylinder: radius must fit inside the box's y/z cross
# section (0.06 m square), so use a conservative radius under half that.
ASSUMED_UPPER_ARM_COLLISION_RADIUS_M = 0.025
ASSUMED_SHOULDER_LIFT_LOWER_DEG = -45.0
ASSUMED_SHOULDER_LIFT_UPPER_DEG = 90.0

# --- forearm (prismatic extend) -----------------------------------------
ASSUMED_FOREARM_SIZE_XYZ_M = (0.20, 0.05, 0.05)
ASSUMED_FOREARM_MASS_KG = 0.8
FOREARM_EXTEND_AXIS = (1.0, 0.0, 0.0)
# forearm_link's joint frame is at the distal (far) end of the upper arm box.
FOREARM_EXTEND_JOINT_X_M = ASSUMED_UPPER_ARM_SIZE_XYZ_M[0]
FOREARM_GEOMETRY_X_M = ASSUMED_FOREARM_SIZE_XYZ_M[0] / 2.0
ASSUMED_FOREARM_EXTEND_LOWER_M = 0.0
ASSUMED_FOREARM_EXTEND_UPPER_M = 0.15

# --- wrist (continuous roll) --------------------------------------------
ASSUMED_WRIST_RADIUS_M = 0.04
ASSUMED_WRIST_MASS_KG = 0.3
WRIST_ROLL_AXIS = (1.0, 0.0, 0.0)
# wrist_link's joint frame is at the distal end of the (retracted) forearm.
WRIST_ROLL_JOINT_X_M = ASSUMED_FOREARM_SIZE_XYZ_M[0]

# --- tool0 (fixed tool control point) ------------------------------------
# tool0 sits at the wrist sphere's surface along the wrist roll axis.
WRIST_TO_TOOL0_X_M = ASSUMED_WRIST_RADIUS_M

# --- placeholder actuator limits (illustrative only, not sourced) --------
ASSUMED_REVOLUTE_EFFORT_NM = 40.0
ASSUMED_REVOLUTE_VELOCITY_RAD_S = 2.0
ASSUMED_PRISMATIC_EFFORT_N = 100.0
ASSUMED_PRISMATIC_VELOCITY_M_S = 0.1
ASSUMED_CONTINUOUS_EFFORT_NM = 10.0
ASSUMED_CONTINUOUS_VELOCITY_RAD_S = 3.0


def _box_inertia(mass_kg: float, size_xyz_m: tuple[float, float, float]) -> tuple[float, float, float]:
    """Solid box inertia about its own center, axis-aligned with its sides."""
    x, y, z = size_xyz_m
    ixx = mass_kg / 12.0 * (y**2 + z**2)
    iyy = mass_kg / 12.0 * (x**2 + z**2)
    izz = mass_kg / 12.0 * (x**2 + y**2)
    return ixx, iyy, izz


def _cylinder_inertia_about_z(mass_kg: float, radius_m: float, length_m: float) -> tuple[float, float, float]:
    """Solid cylinder inertia about its own center, long axis along local Z."""
    ixx = iyy = mass_kg / 12.0 * (3.0 * radius_m**2 + length_m**2)
    izz = mass_kg / 2.0 * radius_m**2
    return ixx, iyy, izz


def _sphere_inertia(mass_kg: float, radius_m: float) -> float:
    """Solid sphere inertia about its own center (same about every axis)."""
    return 2.0 / 5.0 * mass_kg * radius_m**2


def _add_origin(parent: ET.Element, *, xyz: tuple[float, float, float], rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
    ET.SubElement(parent, "origin", {"xyz": f"{xyz[0]:.6g} {xyz[1]:.6g} {xyz[2]:.6g}", "rpy": f"{rpy[0]:.6g} {rpy[1]:.6g} {rpy[2]:.6g}"})


def _add_inertial(
    link: ET.Element,
    *,
    mass_kg: float,
    com_xyz_m: tuple[float, float, float],
    ixx: float,
    iyy: float,
    izz: float,
) -> None:
    inertial = ET.SubElement(link, "inertial")
    _add_origin(inertial, xyz=com_xyz_m)
    ET.SubElement(inertial, "mass", {"value": f"{mass_kg:.6g}"})
    ET.SubElement(
        inertial,
        "inertia",
        {
            "ixx": f"{ixx:.6g}",
            "ixy": "0",
            "ixz": "0",
            "iyy": f"{iyy:.6g}",
            "iyz": "0",
            "izz": f"{izz:.6g}",
        },
    )


def _add_box_geometry(owner: ET.Element, *, size_xyz_m: tuple[float, float, float], origin_xyz: tuple[float, float, float], origin_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
    _add_origin(owner, xyz=origin_xyz, rpy=origin_rpy)
    geometry = ET.SubElement(owner, "geometry")
    ET.SubElement(geometry, "box", {"size": f"{size_xyz_m[0]:.6g} {size_xyz_m[1]:.6g} {size_xyz_m[2]:.6g}"})


def _add_cylinder_geometry(owner: ET.Element, *, radius_m: float, length_m: float, origin_xyz: tuple[float, float, float], origin_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
    _add_origin(owner, xyz=origin_xyz, rpy=origin_rpy)
    geometry = ET.SubElement(owner, "geometry")
    ET.SubElement(geometry, "cylinder", {"radius": f"{radius_m:.6g}", "length": f"{length_m:.6g}"})


def _add_sphere_geometry(owner: ET.Element, *, radius_m: float, origin_xyz: tuple[float, float, float]) -> None:
    _add_origin(owner, xyz=origin_xyz)
    geometry = ET.SubElement(owner, "geometry")
    ET.SubElement(geometry, "sphere", {"radius": f"{radius_m:.6g}"})


def _add_joint(
    robot: ET.Element,
    *,
    name: str,
    joint_type: str,
    parent: str,
    child: str,
    origin_xyz: tuple[float, float, float],
    axis: tuple[float, float, float] | None = None,
    limit: dict[str, float] | None = None,
) -> None:
    joint = ET.SubElement(robot, "joint", {"name": name, "type": joint_type})
    ET.SubElement(joint, "parent", {"link": parent})
    ET.SubElement(joint, "child", {"link": child})
    _add_origin(joint, xyz=origin_xyz)
    if axis is not None:
        ET.SubElement(joint, "axis", {"xyz": f"{axis[0]:.6g} {axis[1]:.6g} {axis[2]:.6g}"})
    if limit is not None:
        ET.SubElement(joint, "limit", {key: f"{value:.6g}" for key, value in limit.items()})


def gen_urdf() -> ET.Element:
    robot = ET.Element("robot", {"name": ROBOT_NAME})

    # base_footprint: frame-only root link, no inertial/visual/collision.
    ET.SubElement(robot, "link", {"name": "base_footprint"})

    # base_link: physical pedestal box.
    base_link = ET.SubElement(robot, "link", {"name": "base_link"})
    _add_box_geometry(
        ET.SubElement(base_link, "visual"),
        size_xyz_m=ASSUMED_BASE_SIZE_XYZ_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    _add_box_geometry(
        ET.SubElement(base_link, "collision"),
        size_xyz_m=ASSUMED_BASE_SIZE_XYZ_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    base_ixx, base_iyy, base_izz = _box_inertia(ASSUMED_BASE_MASS_KG, ASSUMED_BASE_SIZE_XYZ_M)
    _add_inertial(
        base_link,
        mass_kg=ASSUMED_BASE_MASS_KG,
        com_xyz_m=(0.0, 0.0, 0.0),
        ixx=base_ixx,
        iyy=base_iyy,
        izz=base_izz,
    )

    _add_joint(
        robot,
        name="base_footprint_to_base",
        joint_type="fixed",
        parent="base_footprint",
        child="base_link",
        origin_xyz=(0.0, 0.0, BASE_FOOTPRINT_TO_BASE_Z_M),
    )

    # shoulder_link: physical pan cylinder, long axis along the link's local Z.
    shoulder_link = ET.SubElement(robot, "link", {"name": "shoulder_link"})
    _add_cylinder_geometry(
        ET.SubElement(shoulder_link, "visual"),
        radius_m=ASSUMED_SHOULDER_RADIUS_M,
        length_m=ASSUMED_SHOULDER_LENGTH_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    _add_cylinder_geometry(
        ET.SubElement(shoulder_link, "collision"),
        radius_m=ASSUMED_SHOULDER_RADIUS_M,
        length_m=ASSUMED_SHOULDER_LENGTH_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    shoulder_ixx, shoulder_iyy, shoulder_izz = _cylinder_inertia_about_z(
        ASSUMED_SHOULDER_MASS_KG, ASSUMED_SHOULDER_RADIUS_M, ASSUMED_SHOULDER_LENGTH_M
    )
    _add_inertial(
        shoulder_link,
        mass_kg=ASSUMED_SHOULDER_MASS_KG,
        com_xyz_m=(0.0, 0.0, 0.0),
        ixx=shoulder_ixx,
        iyy=shoulder_iyy,
        izz=shoulder_izz,
    )

    _add_joint(
        robot,
        name="shoulder_pan_joint",
        joint_type="revolute",
        parent="base_link",
        child="shoulder_link",
        origin_xyz=(0.0, 0.0, SHOULDER_PAN_JOINT_Z_M),
        axis=SHOULDER_PAN_AXIS,
        limit={
            "lower": math.radians(ASSUMED_SHOULDER_PAN_LOWER_DEG),
            "upper": math.radians(ASSUMED_SHOULDER_PAN_UPPER_DEG),
            "effort": ASSUMED_REVOLUTE_EFFORT_NM,
            "velocity": ASSUMED_REVOLUTE_VELOCITY_RAD_S,
        },
    )

    # upper_arm_link: physical lift link. Visual is a box; collision is a
    # simplified cylinder rotated 90 deg about Y so its own axis (normally Z)
    # aligns with the box's long X axis -- demonstrates visual/collision
    # geometry intentionally differing (see frame-semantics.md).
    upper_arm_link = ET.SubElement(robot, "link", {"name": "upper_arm_link"})
    _add_box_geometry(
        ET.SubElement(upper_arm_link, "visual"),
        size_xyz_m=ASSUMED_UPPER_ARM_SIZE_XYZ_M,
        origin_xyz=(UPPER_ARM_GEOMETRY_X_M, 0.0, 0.0),
    )
    _add_cylinder_geometry(
        ET.SubElement(upper_arm_link, "collision"),
        radius_m=ASSUMED_UPPER_ARM_COLLISION_RADIUS_M,
        length_m=ASSUMED_UPPER_ARM_SIZE_XYZ_M[0],
        origin_xyz=(UPPER_ARM_GEOMETRY_X_M, 0.0, 0.0),
        origin_rpy=(0.0, math.pi / 2.0, 0.0),
    )
    upper_arm_ixx, upper_arm_iyy, upper_arm_izz = _box_inertia(ASSUMED_UPPER_ARM_MASS_KG, ASSUMED_UPPER_ARM_SIZE_XYZ_M)
    _add_inertial(
        upper_arm_link,
        mass_kg=ASSUMED_UPPER_ARM_MASS_KG,
        com_xyz_m=(UPPER_ARM_GEOMETRY_X_M, 0.0, 0.0),
        ixx=upper_arm_ixx,
        iyy=upper_arm_iyy,
        izz=upper_arm_izz,
    )

    _add_joint(
        robot,
        name="shoulder_lift_joint",
        joint_type="revolute",
        parent="shoulder_link",
        child="upper_arm_link",
        origin_xyz=(0.0, 0.0, SHOULDER_LIFT_JOINT_Z_M),
        axis=SHOULDER_LIFT_AXIS,
        limit={
            "lower": math.radians(ASSUMED_SHOULDER_LIFT_LOWER_DEG),
            "upper": math.radians(ASSUMED_SHOULDER_LIFT_UPPER_DEG),
            "effort": ASSUMED_REVOLUTE_EFFORT_NM,
            "velocity": ASSUMED_REVOLUTE_VELOCITY_RAD_S,
        },
    )

    # forearm_link: physical telescoping link, driven by a prismatic joint.
    forearm_link = ET.SubElement(robot, "link", {"name": "forearm_link"})
    _add_box_geometry(
        ET.SubElement(forearm_link, "visual"),
        size_xyz_m=ASSUMED_FOREARM_SIZE_XYZ_M,
        origin_xyz=(FOREARM_GEOMETRY_X_M, 0.0, 0.0),
    )
    _add_box_geometry(
        ET.SubElement(forearm_link, "collision"),
        size_xyz_m=ASSUMED_FOREARM_SIZE_XYZ_M,
        origin_xyz=(FOREARM_GEOMETRY_X_M, 0.0, 0.0),
    )
    forearm_ixx, forearm_iyy, forearm_izz = _box_inertia(ASSUMED_FOREARM_MASS_KG, ASSUMED_FOREARM_SIZE_XYZ_M)
    _add_inertial(
        forearm_link,
        mass_kg=ASSUMED_FOREARM_MASS_KG,
        com_xyz_m=(FOREARM_GEOMETRY_X_M, 0.0, 0.0),
        ixx=forearm_ixx,
        iyy=forearm_iyy,
        izz=forearm_izz,
    )

    _add_joint(
        robot,
        name="forearm_extend_joint",
        joint_type="prismatic",
        parent="upper_arm_link",
        child="forearm_link",
        origin_xyz=(FOREARM_EXTEND_JOINT_X_M, 0.0, 0.0),
        axis=FOREARM_EXTEND_AXIS,
        limit={
            "lower": ASSUMED_FOREARM_EXTEND_LOWER_M,
            "upper": ASSUMED_FOREARM_EXTEND_UPPER_M,
            "effort": ASSUMED_PRISMATIC_EFFORT_N,
            "velocity": ASSUMED_PRISMATIC_VELOCITY_M_S,
        },
    )

    # wrist_link: physical roll sphere at the end of the forearm.
    wrist_link = ET.SubElement(robot, "link", {"name": "wrist_link"})
    _add_sphere_geometry(
        ET.SubElement(wrist_link, "visual"),
        radius_m=ASSUMED_WRIST_RADIUS_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    _add_sphere_geometry(
        ET.SubElement(wrist_link, "collision"),
        radius_m=ASSUMED_WRIST_RADIUS_M,
        origin_xyz=(0.0, 0.0, 0.0),
    )
    wrist_inertia = _sphere_inertia(ASSUMED_WRIST_MASS_KG, ASSUMED_WRIST_RADIUS_M)
    _add_inertial(
        wrist_link,
        mass_kg=ASSUMED_WRIST_MASS_KG,
        com_xyz_m=(0.0, 0.0, 0.0),
        ixx=wrist_inertia,
        iyy=wrist_inertia,
        izz=wrist_inertia,
    )

    _add_joint(
        robot,
        name="wrist_roll_joint",
        joint_type="continuous",
        parent="forearm_link",
        child="wrist_link",
        origin_xyz=(WRIST_ROLL_JOINT_X_M, 0.0, 0.0),
        axis=WRIST_ROLL_AXIS,
        limit={
            "effort": ASSUMED_CONTINUOUS_EFFORT_NM,
            "velocity": ASSUMED_CONTINUOUS_VELOCITY_RAD_S,
        },
    )

    # tool0: frame-only tool control point, no inertial/visual/collision.
    ET.SubElement(robot, "link", {"name": "tool0"})

    _add_joint(
        robot,
        name="wrist_to_tool0",
        joint_type="fixed",
        parent="wrist_link",
        child="tool0",
        origin_xyz=(WRIST_TO_TOOL0_X_M, 0.0, 0.0),
    )

    return robot
