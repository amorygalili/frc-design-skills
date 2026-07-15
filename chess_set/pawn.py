"""Staunton-style chess pawn: turned pedestal body with a spherical head.

Coordinate convention:
    Origin: center of the piece's circular base, on the board surface.
    XY:     base plane (piece sits on Z=0).
    +Z:     up, toward the head of the piece.
"""

from build123d import *

# --- Piece parameters ----------------------------------------------------
H = 45.0  # overall piece height
R = 15.0  # base radius (base diameter 30 mm)

head_r_frac = 0.55  # head sphere radius as a fraction of R
head_embed_frac = 0.30  # how far the sphere center sits below its own top, as a
# fraction of its radius, relative to the collar it rests on (controls overlap)


def pedestal_profile(top_z):
    """Base -> collar -> waist -> stem -> collar profile, scaled to top_z."""
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
    # Solve collar_top_z so the sphere apex lands exactly at H.
    collar_top_z = H - (1 + head_embed_frac) * head_r

    body = revolve_profile(pedestal_profile(collar_top_z))

    head_center_z = collar_top_z + head_embed_frac * head_r
    head = Pos(0, 0, head_center_z) * Sphere(radius=head_r)

    part = body.fuse(head)
    part.label = "pawn"
    return part
