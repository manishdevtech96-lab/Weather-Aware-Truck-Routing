from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from .views import optional_point
from .services.recommendation import recommend_routes
from .services.risk_engine import classify_weather
from .services.routing import get_routes, routes_are_similar
from .services.weather import conditions_at, timeline_from_departure


class RiskEngineTests(SimpleTestCase):
    def test_wind_thresholds(self):
        self.assertEqual(classify_weather(24.9, 0, 0, 10000), "Low")
        self.assertEqual(classify_weather(25, 0, 0, 10000), "Moderate")
        self.assertEqual(classify_weather(35, 0, 0, 10000), "High")
        self.assertEqual(classify_weather(45, 0, 0, 10000), "Severe")
        self.assertEqual(classify_weather(55, 0, 0, 10000), "No Travel")

    def test_load_rules(self):
        self.assertEqual(classify_weather(50, 0, 0, 30000), "Severe")
        self.assertEqual(classify_weather(50, 0, 0, 30001), "No Travel")
        self.assertEqual(classify_weather(40, 0, 0, 40000), "High")
        self.assertEqual(classify_weather(40, 0, 0, 40001), "Severe")

    def test_precipitation_and_missing_values(self):
        self.assertEqual(classify_weather(0, 0.09, 0, 10000), "Low")
        self.assertEqual(classify_weather(0, 0.10, 0, 10000), "Moderate")
        self.assertEqual(classify_weather(0, 1.01, 0, 10000), "No Travel")
        self.assertEqual(classify_weather(0, 0, 3.1, 10000), "No Travel")
        self.assertEqual(classify_weather(None, 0, 0, 10000), "Unknown")

    def test_load_rule_does_not_downgrade_worse_weather(self):
        self.assertEqual(classify_weather(40, 1.2, 0, 10000), "No Travel")


class PointParsingTests(SimpleTestCase):
    def test_reads_longitude_latitude_pair(self):
        point = optional_point(
            {"origin_latitude": "41.88", "origin_longitude": "-87.63"},
            "origin_latitude",
            "origin_longitude",
        )
        self.assertEqual(point, [-87.63, 41.88])

    def test_missing_coordinates_stay_empty(self):
        self.assertIsNone(optional_point({}, "origin_latitude", "origin_longitude"))


class RecommendationTests(SimpleTestCase):
    def test_prefers_fewer_severe_miles_then_high_then_risk_then_time(self):
        routes = [
            _route("slow-safe", severe=0, high=5, average=2, duration=9000),
            _route("fast-severe", severe=10, high=0, average=1, duration=3000),
            _route("best", severe=0, high=1, average=1.5, duration=8000),
            _route("tied-shorter", severe=0, high=1, average=1.5, duration=5000),
        ]
        ranked = recommend_routes(routes)
        self.assertEqual(
            [route["id"] for route in ranked],
            ["tied-shorter", "best", "slow-safe", "fast-severe"],
        )


class RoutingTests(SimpleTestCase):
    def test_similar_corridors_are_collapsed(self):
        base = _line(lat_shift=0)
        almost_same = _line(lat_shift=0.02)
        other = _line(lat_shift=0.45)
        self.assertTrue(routes_are_similar({"geometry": base}, {"geometry": almost_same}))
        self.assertFalse(routes_are_similar({"geometry": base}, {"geometry": other}))

    @patch("trips.services.routing.requests.get")
    def test_third_route_is_requested_when_provider_returns_two(self, get):
        direction_calls = []

        def side_effect(url, params=None, timeout=None):
            if "geocoding" in url:
                center = [-87.63, 41.88] if "Chicago" in url else [-86.16, 39.77]
                return _response({"features": [{"center": center}]})
            direction_calls.append(params or {})
            if params and params.get("exclude") == "motorway":
                return _response({"code": "Ok", "routes": [_mapbox_route(198000, 12000, 0.45)]})
            return _response(
                {
                    "code": "Ok",
                    "routes": [
                        _mapbox_route(183000, 10000, 0.0),
                        _mapbox_route(191000, 11000, 0.2),
                    ],
                }
            )

        get.side_effect = side_effect
        routes = get_routes("Chicago, IL", "Indianapolis, IN", "test-token")

        self.assertEqual(len(routes), 3)
        self.assertEqual([route["name"] for route in routes], ["Fastest", "Alternate", "Avoid highways"])
        self.assertEqual(len(direction_calls), 2)
        self.assertTrue(direction_calls[0]["alternatives"])
        self.assertEqual(direction_calls[1]["exclude"], "motorway")

    @patch("trips.services.routing.requests.get")
    def test_stops_after_three_distinct_alternatives(self, get):
        direction_calls = []

        def side_effect(url, params=None, timeout=None):
            if "geocoding" in url:
                center = [-87.63, 41.88] if "Chicago" in url else [-86.16, 39.77]
                return _response({"features": [{"center": center}]})
            direction_calls.append(params or {})
            return _response(
                {
                    "code": "Ok",
                    "routes": [
                        _mapbox_route(180000, 9000, 0.0),
                        _mapbox_route(190000, 10000, 0.25),
                        _mapbox_route(210000, 12000, 0.5),
                    ],
                }
            )

        get.side_effect = side_effect
        routes = get_routes("Chicago, IL", "Indianapolis, IN", "test-token")
        self.assertEqual(len(routes), 3)
        self.assertEqual(len(direction_calls), 1)


class WeatherTests(SimpleTestCase):
    def test_unit_conversion_and_hourly_timeline(self):
        hour = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
        forecast = {
            "times": ["2026-10-13T15:00", "2026-10-13T16:00"],
            "wind": [30, None],
            "rain": [25.4, 0],
            "precipitation": [25.4, 0],
            "snow": [2.54, 0],
            "index_by_hour": {hour: 0, hour.replace(hour=16): 1},
        }
        reading = conditions_at(forecast, "2026-10-13T15:10:00+00:00")
        self.assertEqual(reading["wind_mph"], 30)
        self.assertEqual(reading["rain_in_per_hour"], 1)
        self.assertEqual(reading["snow_in_per_hour"], 1)
        self.assertTrue(reading["weather_available"])

        timeline = timeline_from_departure(forecast, hour, hours=3)
        self.assertEqual(timeline[0]["rain_in_per_hour"], 1)
        self.assertIsNone(timeline[1])
        self.assertIsNone(timeline[2])


def _route(route_id, severe, high, average, duration):
    return {
        "id": route_id,
        "summary": {
            "severe_miles": severe,
            "high_miles": high,
            "average_risk_score": average,
            "duration_seconds": duration,
        },
    }


def _line(lat_shift):
    return [[-87.6, 41.8 + lat_shift], [-86.9, 41.2 + lat_shift], [-86.2, 39.8 + lat_shift]]


def _mapbox_route(distance_meters, duration_seconds, lat_shift):
    return {
        "distance": distance_meters,
        "duration": duration_seconds,
        "geometry": {"coordinates": _line(lat_shift)},
    }


class _response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload
