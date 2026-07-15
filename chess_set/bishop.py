"""Staunton-style chess bishop: turned pedestal, spherical head, small
finial ball, and a diagonal mitre notch cut into the head.

Coordinate convention:
    Origin: center of the piece's circular base, on the board surface.
    XY:     base plane (piece sits on Z=0).
    +Z:     up, toward the head of the piece.
"""

import math

from build123d import *

# --- Piece parameters ----------------------------------------------------
H = 75.0  # overall piece height
R = 17.0  # base radius (base diameter 34 mm)

head_r_frac = 0.60  # main head sphere radius as a fraction of R
head_embed_frac = 0.25  # overlap between pedestal collar and head sphere
finial_r_frac = 0.18  # finial ball radius as a fraction of R
finial_embed_frac = 0.20  # overlap between head sphere and finial ball

mitre_angle_deg = 22.0  # tilt of the mitre notch off vertical


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
    head_r = head_r_frac * R
    finial_r = finial_r_frac * R

    # Solve collar_top_z so the finial apex lands exactly at H.
    collar_top_z = H - (1 + head_embed_frac) * head_r - (1 - finial_embed_frac) * finial_r

    body = revolve_profile(pedestal_profile(collar_top_z))

    head_center_z = collar_top_z + head_embed_frac * head_r
    head_top_z = head_center_z + head_r
    finial_center_z = head_top_z - finial_embed_frac * finial_r

    head = Pos(0, 0, head_center_z) * Sphere(radius=head_r)
    finial = Pos(0, 0, finial_center_z) * Sphere(radius=finial_r)

    part = body.fuse(head).fuse(finial)

    # Mitre notch: a thin overshooting box sliced through the top of the
    # head sphere, tilted off vertical, characteristic of a bishop's mitre.
    notch = Box(
        head_r * 2.6,
        head_r * 0.24,
        head_r * 1.6,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    )
    notch = Rot(mitre_angle_deg, 0, 0) * notch
    notch = Pos(0, 0, head_top_z - head_r * 0.35) * notch

    part = part.cut(notch)
    part.label = "bishop"
    return part
