"""Staunton-style chess knight: turned pedestal with a lofted, forward-leaning
horse head, ears, and a snout. This is the one piece in the set that is not
axisymmetric.

Coordinate convention:
    Origin: center of the piece's circular base, on the board surface.
    XY:     base plane (piece sits on Z=0).
    +Z:     up, toward the top of the head.
    +Y:     the direction the horse's head faces (forward lean / snout side).
"""

from build123d import *

# --- Piece parameters ----------------------------------------------------
H = 70.0  # overall piece height
R = 17.0  # base radius (base diameter 34 mm)

collar_top_frac = 0.32  # pedestal takes up this fraction of H; the rest is head/neck

ear_base_r = 2.8
ear_top_r = 0.4
ear_height = 10.0
ear_x_offset = 4.0
ear_embed = 1.0

muzzle_base_r = 3.4
muzzle_tip_r = 1.3
muzzle_length = 8.5
muzzle_embed = 1.5


def pedestal_profile(top_z):
    return [
        (R * 1.00, 0.00 * top_z),
        (R * 1.00, 0.05 * top_z),
        (R * 0.70, 0.16 * top_z),
        (R * 0.80, 0.20 * top_z),
        (R * 0.48, 0.30 * top_z),
        (R * 0.30, 0.55 * top_z),
        (R * 0.30, 0.85 * top_z),
        (R * 0.42, 0.93 * top_z),
        (R * 0.50, 1.00 * top_z),
    ]


def revolve_profile(points):
    pts = list(points)
    if pts[0][0] > 1e-9:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] > 1e-9:
        pts.append((0.0, pts[-1][1]))
    with BuildPart() as p:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts, close=True)
            make_face()
        revolve(axis=Axis.Z)
    return p.part


def gen_step():
    collar_top_z = collar_top_frac * H
    head_span = H - collar_top_z

    body = revolve_profile(pedestal_profile(collar_top_z))

    # Loft sections: circular collar -> narrow neck (leaning forward in +Y)
    # -> wide jaw/head base -> narrower skull top.
    z1 = collar_top_z
    z2 = collar_top_z + 0.35 * head_span
    z3 = collar_top_z + 0.68 * head_span
    z4 = collar_top_z + 0.85 * head_span

    with BuildPart() as head_part:
        with BuildSketch(Plane.XY.offset(z1)):
            Circle(0.50 * R)
        with BuildSketch(Plane.XY.offset(z2)):
            with Locations((0, 0.15 * R)):
                Ellipse(x_radius=0.42 * R, y_radius=0.55 * R)
        with BuildSketch(Plane.XY.offset(z3)):
            with Locations((0, 0.45 * R)):
                Ellipse(x_radius=0.50 * R, y_radius=0.62 * R)
        with BuildSketch(Plane.XY.offset(z4)):
            with Locations((0, 0.55 * R)):
                Ellipse(x_radius=0.40 * R, y_radius=0.45 * R)
        loft()

    part = body.fuse(head_part.part)

    # Ears: two cones on top of the skull, spread apart in X.
    ear = Cone(
        bottom_radius=ear_base_r,
        top_radius=ear_top_r,
        height=ear_height,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    ear_z = z4 - ear_embed
    ear_y = 0.55 * R
    left_ear = Pos(-ear_x_offset, ear_y, ear_z) * ear
    right_ear = Pos(ear_x_offset, ear_y, ear_z) * ear
    part = part.fuse(left_ear).fuse(right_ear)

    # Muzzle: a forward-pointing tapered cone at the front of the jaw,
    # projecting clearly past the head silhouette (+Y is "forward").
    jaw_y_max = 0.45 * R + 0.62 * R
    muzzle = Rot(-90, 0, 0) * Cone(
        bottom_radius=muzzle_base_r,
        top_radius=muzzle_tip_r,
        height=muzzle_length,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    muzzle_z = collar_top_z + 0.62 * head_span
    muzzle = Pos(0, jaw_y_max - muzzle_embed, muzzle_z) * muzzle
    part = part.fuse(muzzle)

    part.label = "knight"
    return part
