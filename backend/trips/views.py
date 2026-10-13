"""Trip analysis API."""

from datetime import datetime

import requests
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services.checkpoints import sample_route
from .services.recommendation import recommend_routes, summarize_route
from .services.risk_engine import classify_weather
from .services.routing import TARGET_ROUTE_COUNT, get_routes, reverse_geocode, suggest_places
from .services.weather import conditions_at, get_forecasts, timeline_from_departure

TRIP_ERROR = (
    "Provide a valid timezone-aware departure_time, a non-negative load weight, "
    "and a checkpoint interval of 10, 25, or 50."
)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def suggest_places_view(request):
    query = str(request.GET.get("q", "")).strip()
    if len(query) < 2:
        return Response({"places": []})
    if not settings.MAPBOX_ACCESS_TOKEN:
        return Response(
            {"error": "MAPBOX_ACCESS_TOKEN is missing. Add it to backend/.env."},
            status=503,
        )
    try:
        places = suggest_places(query, settings.MAPBOX_ACCESS_TOKEN)
    except (requests.RequestException, RuntimeError):
        return Response({"error": "Place search is unavailable. Try again shortly."}, status=502)
    return Response({"places": places})


@api_view(["GET"])
def reverse_place_view(request):
    if not settings.MAPBOX_ACCESS_TOKEN:
        return Response(
            {"error": "MAPBOX_ACCESS_TOKEN is missing. Add it to backend/.env."},
            status=503,
        )
    try:
        latitude = float(request.GET["latitude"])
        longitude = float(request.GET["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        place = reverse_geocode(longitude, latitude, settings.MAPBOX_ACCESS_TOKEN)
    except (KeyError, TypeError, ValueError):
        return Response({"error": "Choose a point on the map with a valid location."}, status=400)
    except (requests.RequestException, RuntimeError):
        return Response({"error": "That map point could not be identified. Try again shortly."}, status=502)
    return Response(place)


@api_view(["POST"])
def analyze_trip(request):
    trip, error = _parse_trip(request.data)
    if error is not None:
        return error
    if not settings.MAPBOX_ACCESS_TOKEN:
        return Response(
            {"error": "MAPBOX_ACCESS_TOKEN is missing. Add it to backend/.env."},
            status=503,
        )

    try:
        routes = get_routes(
            trip["origin"],
            trip["destination"],
            settings.MAPBOX_ACCESS_TOKEN,
            origin_point=trip["origin_point"],
            destination_point=trip["destination_point"],
        )
        analyzed = _score_routes(routes, trip)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=422)
    except (requests.RequestException, RuntimeError):
        return Response(
            {"error": "A mapping or weather provider could not be reached. Try again shortly."},
            status=502,
        )

    ranked = recommend_routes(analyzed)
    best_id = ranked[0]["id"]
    for route in analyzed:
        route["is_recommended"] = route["id"] == best_id

    warnings = [
        "Checkpoint risk uses the forecast closest to the truck's estimated arrival.",
        "The map heatmap shows that same corridor at each hour from departure through 48 hours.",
        "Open-Meteo precipitation and snowfall are hourly amounts, treated here as hourly rates.",
        "Checkpoint ETAs are proportional to distance along the route's total duration.",
        "This prototype is not a guarantee of real-world truck safety.",
    ]
    if len(analyzed) < TARGET_ROUTE_COUNT:
        warnings.insert(
            0,
            f"Only {len(analyzed)} distinct driving route(s) were available for this trip.",
        )

    return Response(
        {
            "trip": {
                "origin": trip["origin"],
                "destination": trip["destination"],
                "departure_time": trip["departure"].isoformat(),
                "load_weight_lb": trip["weight"],
                "checkpoint_interval_miles": trip["interval"],
            },
            "recommended_route_id": best_id,
            "routes": analyzed,
            "forecast_slider": {"min_hours": 0, "max_hours": 48},
            "warnings": warnings,
        }
    )


def _parse_trip(data):
    origin = str(data.get("origin", "")).strip()
    destination = str(data.get("destination", "")).strip()
    if not origin or not destination:
        return None, Response({"error": "Origin and destination are required."}, status=400)
    try:
        weight = float(data["load_weight_lb"])
        interval = int(data.get("checkpoint_interval_miles", 25))
        departure = datetime.fromisoformat(str(data["departure_time"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None, Response({"error": TRIP_ERROR}, status=400)
    if weight < 0 or interval not in (10, 25, 50) or departure.tzinfo is None:
        return None, Response({"error": TRIP_ERROR}, status=400)
    try:
        origin_point = optional_point(data, "origin_latitude", "origin_longitude")
        destination_point = optional_point(data, "destination_latitude", "destination_longitude")
    except (TypeError, ValueError):
        return None, Response(
            {"error": "Origin and destination coordinates must be valid latitude and longitude."},
            status=400,
        )
    return {
        "origin": origin,
        "destination": destination,
        "origin_point": origin_point,
        "destination_point": destination_point,
        "weight": weight,
        "interval": interval,
        "departure": departure,
    }, None


def optional_point(data, latitude_key, longitude_key):
    """Return `[longitude, latitude]` when both values are present."""
    latitude_raw = data.get(latitude_key)
    longitude_raw = data.get(longitude_key)
    if latitude_raw in (None, "") and longitude_raw in (None, ""):
        return None
    latitude = float(latitude_raw)
    longitude = float(longitude_raw)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates are out of range.")
    return [longitude, latitude]


def _score_routes(routes, trip):
    prepared = []
    locations = []
    for route in routes:
        checkpoints = sample_route(route["geometry"], trip["interval"], route["distance_miles"])
        for checkpoint in checkpoints:
            progress = checkpoint["distance_miles"] / max(route["distance_miles"], 0.001)
            eta_timestamp = trip["departure"].timestamp() + route["duration_seconds"] * progress
            checkpoint["eta"] = datetime.fromtimestamp(eta_timestamp, tz=trip["departure"].tzinfo).isoformat()
            locations.append((checkpoint["latitude"], checkpoint["longitude"]))
        prepared.append((route, checkpoints))

    forecasts = get_forecasts(locations)
    cursor = 0
    analyzed = []
    for route, checkpoints in prepared:
        for checkpoint in checkpoints:
            forecast = forecasts[cursor]
            cursor += 1
            checkpoint.update(conditions_at(forecast, checkpoint["eta"]))
            checkpoint["risk_level"] = classify_weather(
                checkpoint.get("wind_mph"),
                checkpoint.get("rain_in_per_hour"),
                checkpoint.get("snow_in_per_hour"),
                trip["weight"],
            )
            checkpoint["risk_timeline"] = [
                "Unknown"
                if reading is None
                else classify_weather(
                    reading["wind_mph"],
                    reading["rain_in_per_hour"],
                    reading["snow_in_per_hour"],
                    trip["weight"],
                )
                for reading in timeline_from_departure(forecast, trip["departure"])
            ]
        analyzed.append(
            {
                **route,
                "checkpoints": checkpoints,
                "summary": summarize_route(route, checkpoints),
            }
        )
    return analyzed
