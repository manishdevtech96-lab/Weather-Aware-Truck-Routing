"""Sample checkpoints along a route polyline."""

from math import atan2, cos, radians, sin, sqrt


def haversine_miles(start, end):
    lon1, lat1 = start
    lon2, lat2 = end
    radius = 3958.7613
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    chord = sin(delta_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    return 2 * radius * atan2(sqrt(chord), sqrt(max(0.0, 1 - chord)))


def sample_route(coordinates, interval_miles, route_distance_miles):
    """Return origin, evenly spaced checkpoints, and the destination.

    `route_distance_miles` is the router's road distance. Positions are taken
    at the same fraction along the drawn polyline.
    """
    if not coordinates or len(coordinates) < 2:
        raise ValueError("Invalid route geometry")

    lengths = []
    cumulative = [0.0]
    for index in range(len(coordinates) - 1):
        lengths.append(haversine_miles(coordinates[index], coordinates[index + 1]))
        cumulative.append(cumulative[-1] + lengths[-1])

    geometry_total = cumulative[-1]
    if geometry_total <= 0 or route_distance_miles <= 0:
        raise ValueError("Route has zero length")

    targets = [0.0]
    cursor = float(interval_miles)
    while cursor < route_distance_miles:
        targets.append(cursor)
        cursor += interval_miles
    targets.append(float(route_distance_miles))

    checkpoints = []
    for sequence, target in enumerate(targets):
        along = min(target / route_distance_miles, 1) * geometry_total
        index = 0
        while index < len(lengths) - 1 and cumulative[index + 1] < along:
            index += 1
        segment = lengths[index]
        fraction = 0 if segment == 0 else (along - cumulative[index]) / segment
        fraction = max(0.0, min(1.0, fraction))
        point = _interpolate(coordinates[index], coordinates[index + 1], fraction)
        checkpoints.append(
            {
                "sequence": sequence,
                "distance_miles": round(target, 2),
                "longitude": round(point[0], 6),
                "latitude": round(point[1], 6),
            }
        )
    return checkpoints


def _interpolate(start, end, fraction):
    return [
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    ]
