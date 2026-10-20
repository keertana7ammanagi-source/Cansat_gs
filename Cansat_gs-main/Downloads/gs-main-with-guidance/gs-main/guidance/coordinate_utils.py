"""
guidance/coordinate_utils.py

Converts GPS lat/lon into a local flat-earth (east, north) metre frame
centred on a reference point, and provides distance / bearing / cross-track
error helpers used by the LandingController.

This uses an equirectangular approximation, which is accurate to well
under 1% error over the distances involved in a CanSat recovery area
(hundreds of metres, not kilometres).
"""

import math

EARTH_RADIUS_M = 6371000.0
METERS_PER_DEG_LAT = 111320.0  # approx, good enough for small areas


def gps_to_local(lat, lon, ref_lat, ref_lon):
    """
    Convert a GPS (lat, lon) into local (east, north) metres relative to
    a reference point (ref_lat, ref_lon).

    Returns:
        (east_m, north_m)
    """
    d_lat = lat - ref_lat
    d_lon = lon - ref_lon

    north = d_lat * METERS_PER_DEG_LAT
    east = d_lon * METERS_PER_DEG_LAT * math.cos(math.radians(ref_lat))

    return east, north


def distance_m(point_a, point_b):
    """
    Straight-line distance between two (east, north) points in metres.
    """
    dx = point_b[0] - point_a[0]
    dy = point_b[1] - point_a[1]
    return math.hypot(dx, dy)


def bearing_deg(point_a, point_b):
    """
    Compass bearing (0 = North, 90 = East) from point_a to point_b,
    in local (east, north) coordinates.
    """
    dx = point_b[0] - point_a[0]
    dy = point_b[1] - point_a[1]
    angle = math.degrees(math.atan2(dx, dy))  # atan2(east, north)
    return angle % 360.0


def cross_track_error(origin, target, current):
    """
    Perpendicular distance and signed side of `current` relative to the
    straight line from `origin` (e.g. launch point / last waypoint) to
    `target` (landing target), all given as (east, north) tuples.

    Returns:
        (error_m, sign)
        sign > 0  -> current position is to the RIGHT of the origin->target
                     line (looking from origin towards target)
        sign < 0  -> current position is to the LEFT of that line
        sign == 0 -> exactly on the line

    This is the standard 2D cross-track formula: it projects the
    origin->current vector onto the normal of the origin->target vector.
    It does NOT use wind for the geometry -- wind is a separate input
    used later to decide how to correct, not to define the track itself.
    """
    ox, oy = origin
    tx, ty = target
    cx, cy = current

    path_dx = tx - ox
    path_dy = ty - oy
    path_len = math.hypot(path_dx, path_dy)

    if path_len < 1e-6:
        # Degenerate: origin and target are the same point.
        return distance_m(origin, current), 0.0

    # Vector from origin to current position
    rel_dx = cx - ox
    rel_dy = cy - oy

    # Cross product (z-component) of path x rel. In (east, north) axes,
    # a plain 2D cross product is positive for a point on the LEFT of
    # the path direction (counter-clockwise), so it's negated below to
    # get the more intuitive convention: positive = point is to the
    # RIGHT of the origin->target direction.
    cross = path_dx * rel_dy - path_dy * rel_dx
    error = -cross / path_len

    # sign > 0 means current is to the RIGHT of the path direction
    # (looking from origin towards target); sign < 0 means LEFT.
    sign = 1.0 if error > 0 else (-1.0 if error < 0 else 0.0)
    return abs(error), sign


def along_track_distance(origin, target, current):
    """
    Distance travelled along the origin->target line (projection of
    origin->current onto origin->target). Useful for knowing how far
    through the descent corridor the CanSat is.
    """
    ox, oy = origin
    tx, ty = target
    cx, cy = current

    path_dx = tx - ox
    path_dy = ty - oy
    path_len = math.hypot(path_dx, path_dy)
    if path_len < 1e-6:
        return 0.0

    rel_dx = cx - ox
    rel_dy = cy - oy
    return (rel_dx * path_dx + rel_dy * path_dy) / path_len
