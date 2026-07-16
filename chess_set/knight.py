"""Staunton-style chess knight: turned pedestal with an extruded horse-head
side-profile (throat, jaw, muzzle, forehead, and a jagged mane), plus two
ears. This is the one piece in the set that is not axisymmetric.

Coordinate convention:
    Origin: center of the piece's circular base, on the board surface.
    XY:     base plane (piece sits on Z=0).
    +Z:     up, toward the top of the head.
    +Y:     the direction the horse's head faces (forward, muzzle side).
    +X:     the head's thickness (side-to-side) direction.
"""

from build123d import *

# --- Piece parameters ----------------------------------------------------
H = 70.0  # overall piece height
R = 17.0  # base radius (base diameter 34 mm)

collar_top_frac = 0.32  # pedestal takes up this fraction of H; the rest is head/neck
head_half_thickness = 0.40 * R  # half-width of the head slab along X

# Head side-profile silhouette, as (y_fraction, z_fraction) pairs, where
# y_fraction scales by R (forward/back) and z_fraction scales by head_span
# (0 = collar top, 1 = top of poll). The smooth front curve (throat -> jaw ->
# muzzle -> forehead -> poll -> crest) is a spline; the mane is a small
# zigzag confined to the upper neck; the lower neck-back is a smooth spline
# back down to the collar.
front_curve_fractions = [
    (0.30, 0.00),  # throat, front-bottom at the collar
    (0.42, 0.09),
    (0.40, 0.18),  # throat concave curve
    (0.50, 0.28),
    (0.66, 0.37),  # jaw
    (0.80, 0.45),  # chin / mouth tip
    (0.78, 0.51),
    (0.88, 0.57),  # muzzle / nose tip, the most forward point
    (0.80, 0.61),  # nostril indent
    (0.72, 0.69),  # bridge of nose
    (0.62, 0.81),  # forehead
    (0.42, 0.91),
    (0.20, 0.97),
    (0.08, 1.00),  # poll peak
    (-0.02, 0.97),  # just behind the poll
    (-0.06, 0.90),  # crest, above the mane
]

mane_z_top = 0.82
mane_z_bottom = 0.58
mane_teeth = 8
mane_tip_y = -0.07
mane_notch_y = -0.02

back_curve_fractions = [
    (-0.10, 0.45),  # smooth neck-back curve down to the collar
    (-0.14, 0.30),
    (-0.12, 0.15),
    (-0.10, 0.00),  # back-bottom at the collar
]

ear_base_r = 2.6
ear_top_r = 0.4
ear_height = 8.5
ear_x_offset = 3.2
ear_y_frac = 0.28  # forward offset of the ears, as a fraction of R
ear_z_frac = 0.90  # base height of the ears, as a fraction of head_span
ear_embed = 1.2

eye_r = 1.5
eye_y_frac = 0.62
eye_z_frac = 0.68


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


def mane_profile_fractions():
    pts = []
    span = mane_z_top - mane_z_bottom
    steps = 2 * mane_teeth - 1
    for i in range(2 * mane_teeth):
        z = mane_z_top - span * i / steps
        y = mane_tip_y if i % 2 == 0 else mane_notch_y
        pts.append((y, z))
    return pts


def scaled(fractions, head_span):
    return [(yf * R, zf * head_span) for yf, zf in fractions]


def gen_step():
    collar_top_z = collar_top_frac * H
    head_span = H - collar_top_z

    body = revolve_profile(pedestal_profile(collar_top_z))

    front_pts = scaled(front_curve_fractions, head_span)
    mane_pts = scaled(mane_profile_fractions(), head_span)
    back_pts = scaled(back_curve_fractions, head_span)
    mane_pts = [front_pts[-1]] + mane_pts + [back_pts[0]]

    head_plane = Plane(origin=(0, 0, collar_top_z), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    with BuildPart() as head_part:
        with BuildSketch(head_plane):
            with BuildLine():
                Spline(*front_pts)
                Polyline(*mane_pts)
                Spline(*back_pts)
                Line(back_pts[-1], front_pts[0])
            make_face()
        extrude(amount=head_half_thickness, both=True)

    part = body.fuse(head_part.part)

    # Ears: two cones at the poll, spread apart in X.
    ear = Cone(
        bottom_radius=ear_base_r,
        top_radius=ear_top_r,
        height=ear_height,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    ear_z = collar_top_z + ear_z_frac * head_span - ear_embed
    ear_y = ear_y_frac * R
    left_ear = Pos(-ear_x_offset, ear_y, ear_z) * ear
    right_ear = Pos(ear_x_offset, ear_y, ear_z) * ear
    part = part.fuse(left_ear).fuse(right_ear)

    # Eyes: small shallow bumps on each side of the forehead.
    eye_y = eye_y_frac * R
    eye_z = collar_top_z + eye_z_frac * head_span
    left_eye = Pos(-head_half_thickness * 0.85, eye_y, eye_z) * Sphere(radius=eye_r)
    right_eye = Pos(head_half_thickness * 0.85, eye_y, eye_z) * Sphere(radius=eye_r)
    part = part.fuse(left_eye).fuse(right_eye)

    part.label = "knight"
    return part
