"""Geocoding and route options from the Mapbox Directions API."""

import math

import requests

from .checkpoints import haversine_miles

MILES_PER_METER = 0.000621371
TARGET_ROUTE_COUNT = 3
# Routes that stay within this distance for most of the trip are the same corridor.
SIMILAR_MILES = 6.0
SIMILAR_FRACTION = 0.75
SAMPLE_COUNT = 12

DISPLAY_NAMES = {
    "fastest": "Fastest",
    "alternate": "Alternate",
    "avoid_highways": "Avoid highways",
    "avoid_tolls": "Avoid tolls",
    "north_corridor": "North corridor",
    "south_corridor": "South corridor",
}


def get_routes(origin, destination, token, origin_point=None, destination_point=None):
    """Return up to three distinct driving routes.

    Mapbox `alternatives=true` returns at most two extra routes, and often only
    one. When that happens, ask for another real corridor (avoid highways, avoid
    tolls, or a waypoint off the direct line) instead of failing the trip.

    `origin_point` and `destination_point` are optional `[longitude, latitude]`
    pairs from a suggestion or a map click. Text is geocoded when a point is absent.
    """
    start = list(origin_point) if origin_point else _geocode(origin, token)
    end = list(destination_point) if destination_point else _geocode(destination, token)
    if haversine_miles(start, end) < 0.2:
        raise ValueError(
            "Origin and destination resolve to the same place. Choose two different locations."
        )

    collected = []
    primary = _directions(start, end, token, profile="driving-traffic", alternatives=True)
    if not primary:
        raise ValueError("No drivable route was found between those locations.")
    _append_distinct(collected, primary, "alternatives")

    if len(collected) < TARGET_ROUTE_COUNT:
        for strategy in _fallback_strategies(start, end):
            extra = _safe_directions(start, end, token, **strategy["request"])
            _append_distinct(collected, extra, strategy["label"])
            if len(collected) >= TARGET_ROUTE_COUNT:
                break

    chosen = collected[:TARGET_ROUTE_COUNT]
    chosen.sort(key=lambda route: (route["duration_seconds"], route["distance_miles"]))
    return _finalize(chosen)


def routes_are_similar(left, right):
    """True when two polylines follow essentially the same roads."""
    near = 0
    total = SAMPLE_COUNT + 1
    for index in range(total):
        fraction = index / SAMPLE_COUNT
        first = point_at_fraction(left["geometry"], fraction)
        second = point_at_fraction(right["geometry"], fraction)
        if haversine_miles(first, second) <= SIMILAR_MILES:
            near += 1
    return near / total >= SIMILAR_FRACTION


def point_at_fraction(coordinates, fraction):
    if not coordinates:
        raise ValueError("Route geometry is empty.")
    if fraction <= 0 or len(coordinates) == 1:
        return coordinates[0]
    if fraction >= 1:
        return coordinates[-1]

    lengths = [haversine_miles(a, b) for a, b in zip(coordinates, coordinates[1:])]
    total = sum(lengths)
    if total <= 0:
        return coordinates[0]

    target = total * fraction
    walked = 0.0
    for index, length in enumerate(lengths):
        if walked + length >= target and length > 0:
            share = (target - walked) / length
            start = coordinates[index]
            end = coordinates[index + 1]
            return [
                start[0] + (end[0] - start[0]) * share,
                start[1] + (end[1] - start[1]) * share,
            ]
        walked += length
    return coordinates[-1]


def offset_waypoint(start, end, side, fraction=0.5, offset_ratio=0.28):
    """A point to one side of the straight line, used to force another corridor."""
    delta_lon = end[0] - start[0]
    delta_lat = end[1] - start[1]
    length = math.hypot(delta_lon, delta_lat)
    if length == 0:
        raise ValueError("Origin and destination resolve to the same place.")
    side_lon = -delta_lat / length
    side_lat = delta_lon / length
    shift = length * offset_ratio * side
    return [
        start[0] + delta_lon * fraction + side_lon * shift,
        start[1] + delta_lat * fraction + side_lat * shift,
    ]


def _fallback_strategies(start, end):
    north = offset_waypoint(start, end, side=1, fraction=0.5, offset_ratio=0.28)
    south = offset_waypoint(start, end, side=-1, fraction=0.5, offset_ratio=0.28)
    north_wide = offset_waypoint(start, end, side=1, fraction=0.35, offset_ratio=0.42)
    south_wide = offset_waypoint(start, end, side=-1, fraction=0.65, offset_ratio=0.42)
    return [
        {"label": "avoid_highways", "request": {"exclude": "motorway"}},
        {"label": "alternatives", "request": {"profile": "driving", "alternatives": True}},
        {"label": "avoid_tolls", "request": {"exclude": "toll"}},
        {"label": "north_corridor", "request": {"via": north}},
        {"label": "south_corridor", "request": {"via": south}},
        {"label": "north_corridor", "request": {"via": north_wide}},
        {"label": "south_corridor", "request": {"via": south_wide}},
    ]


def _append_distinct(collected, routes, label):
    has_fastest = any(route["label"] == "fastest" for route in collected)
    for index, route in enumerate(routes):
        if label == "alternatives":
            route_label = "fastest" if index == 0 and not has_fastest else "alternate"
        else:
            route_label = label
        candidate = {**route, "label": route_label}
        if any(routes_are_similar(candidate, existing) for existing in collected):
            continue
        collected.append(candidate)
        if route_label == "fastest":
            has_fastest = True


def _finalize(routes):
    alternate_number = 0
    alternate_total = sum(1 for route in routes if route["label"] == "alternate")
    named = []
    for index, route in enumerate(routes, start=1):
        label = route["label"]
        name = DISPLAY_NAMES[label]
        if label == "alternate" and alternate_total > 1:
            alternate_number += 1
            name = f"Alternate {alternate_number}"
        named.append(
            {
                "id": f"route-{index}",
                "name": name,
                "geometry": route["geometry"],
                "distance_miles": route["distance_miles"],
                "duration_seconds": route["duration_seconds"],
            }
        )
    return named


def suggest_places(query, token, limit=5):
    """Autocomplete labels for an origin or destination field."""
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.quote(query)}.json"
    payload = _request_json(
        url,
        {
            "access_token": token,
            "autocomplete": "true",
            "limit": limit,
            "types": "address,place,locality,neighborhood,postcode,poi,district,region",
        },
        timeout=15,
    )
    return [place for feature in payload.get("features") or [] if (place := _place_from_feature(feature))]


def reverse_geocode(longitude, latitude, token):
    """Nearest place name for a point chosen on the map."""
    url = (
        "https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{float(longitude):.6f},{float(latitude):.6f}.json"
    )
    payload = _request_json(url, {"access_token": token, "limit": 1}, timeout=15)
    features = payload.get("features") or []
    if not features:
        raise ValueError("No place was found at that map point.")
    place = _place_from_feature(features[0])
    if place is None:
        raise ValueError("No place was found at that map point.")
    # Keep the exact click, and use the geocoder only for the label.
    place["longitude"] = round(float(longitude), 6)
    place["latitude"] = round(float(latitude), 6)
    return place


def _geocode(query, token):
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.quote(query)}.json"
    payload = _request_json(url, {"access_token": token, "limit": 1}, timeout=20)
    features = payload.get("features") or []
    if not features:
        raise ValueError(f"Could not geocode location: {query}")
    center = features[0].get("center")
    if not center or len(center) < 2:
        raise ValueError(f"Could not geocode location: {query}")
    return [float(center[0]), float(center[1])]


def _place_from_feature(feature):
    center = feature.get("center") or []
    label = feature.get("place_name") or feature.get("text")
    if not label or len(center) < 2:
        return None
    return {
        "label": label,
        "longitude": float(center[0]),
        "latitude": float(center[1]),
    }


def _directions(start, end, token, profile="driving-traffic", alternatives=False, exclude=None, via=None):
    points = [start]
    if via is not None:
        points.append(via)
    points.append(end)
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    url = f"https://api.mapbox.com/directions/v5/mapbox/{profile}/{path}"
    params = {
        "access_token": token,
        "alternatives": "true" if alternatives and via is None else "false",
        "geometries": "geojson",
        "overview": "full",
        "steps": "false",
    }
    if exclude:
        params["exclude"] = exclude
    payload = _request_json(url, params, timeout=30)
    if payload.get("code") != "Ok":
        message = payload.get("message") or "Routing API failed"
        raise ValueError(message)
    routes = []
    for raw in payload.get("routes") or []:
        geometry = (raw.get("geometry") or {}).get("coordinates") or []
        if len(geometry) < 2:
            continue
        routes.append(
            {
                "geometry": geometry,
                "distance_miles": round(raw["distance"] * MILES_PER_METER, 2),
                "duration_seconds": round(raw["duration"]),
            }
        )
    return routes


def _safe_directions(start, end, token, **kwargs):
    try:
        return _directions(start, end, token, **kwargs)
    except (requests.RequestException, ValueError, KeyError):
        return []


def _request_json(url, params, timeout):
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()
