"""Hourly forecast lookups from Open-Meteo."""

from datetime import datetime, timedelta, timezone

import requests

FORECAST_HOURS = 49
MAX_LOCATIONS_PER_REQUEST = 80
MATCH_WINDOW_SECONDS = 3 * 60 * 60
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_forecasts(locations):
    """Fetch hourly forecasts for each (latitude, longitude) pair, in order."""
    if not locations:
        return []
    forecasts = []
    for start in range(0, len(locations), MAX_LOCATIONS_PER_REQUEST):
        chunk = locations[start : start + MAX_LOCATIONS_PER_REQUEST]
        forecasts.extend(_fetch_chunk(chunk))
    if len(forecasts) != len(locations):
        raise RuntimeError("Weather provider returned an unexpected number of forecasts.")
    return forecasts


def conditions_at(forecast, eta_iso):
    """Weather nearest to a checkpoint ETA. Rates are inches per hour."""
    if not forecast or not forecast.get("index_by_hour"):
        return _unavailable()
    eta = datetime.fromisoformat(eta_iso).astimezone(timezone.utc)
    eta = eta.replace(minute=0, second=0, microsecond=0)
    index = forecast["index_by_hour"].get(eta)
    if index is None:
        index = _nearest_index(forecast, eta)
    reading = _reading(forecast, index)
    if reading is None:
        return _unavailable()
    reading["weather_available"] = _complete(reading)
    return reading


def timeline_from_departure(forecast, departure, hours=FORECAST_HOURS):
    """One reading per hour from departure through `hours` (inclusive of hour 0)."""
    if not forecast:
        return [None] * hours
    start = departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    rows = []
    for hour in range(hours):
        stamp = start + timedelta(hours=hour)
        reading = _reading(forecast, forecast["index_by_hour"].get(stamp))
        if reading is None or not _complete(reading):
            rows.append(None)
        else:
            rows.append(reading)
    return rows


def _fetch_chunk(locations):
    params = {
        "latitude": ",".join(f"{lat:.5f}" for lat, _lon in locations),
        "longitude": ",".join(f"{lon:.5f}" for _lat, lon in locations),
        "hourly": "wind_speed_10m,precipitation,rain,snowfall",
        "wind_speed_unit": "mph",
        "timezone": "UTC",
        "forecast_days": 16,
    }
    response = requests.get(FORECAST_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else [payload]
    return [_normalize(row) for row in rows]


def _normalize(row):
    hourly = row.get("hourly") or {}
    times = hourly.get("time") or []
    return {
        "times": times,
        "wind": hourly.get("wind_speed_10m") or [],
        "rain": hourly.get("rain") or [],
        "precipitation": hourly.get("precipitation") or [],
        "snow": hourly.get("snowfall") or [],
        "index_by_hour": _index_times(times),
    }


def _index_times(times):
    indexed = {}
    for index, raw in enumerate(times):
        stamp = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        indexed[stamp] = index
    return indexed


def _nearest_index(forecast, target):
    if not forecast["index_by_hour"]:
        return None
    nearest = min(
        forecast["index_by_hour"],
        key=lambda stamp: abs((stamp - target).total_seconds()),
    )
    if abs((nearest - target).total_seconds()) > MATCH_WINDOW_SECONDS:
        return None
    return forecast["index_by_hour"][nearest]


def _reading(forecast, index):
    if index is None:
        return None
    wind = _at(forecast["wind"], index)
    rain = _at(forecast["rain"], index)
    if rain is None:
        rain = _at(forecast["precipitation"], index)
    snow = _at(forecast["snow"], index)
    forecast_time = forecast["times"][index] if index < len(forecast["times"]) else None
    return {
        "wind_mph": round(float(wind), 2) if wind is not None else None,
        "rain_in_per_hour": round(float(rain) / 25.4, 4) if rain is not None else None,
        "snow_in_per_hour": round(float(snow) / 2.54, 4) if snow is not None else None,
        "forecast_time": forecast_time,
    }


def _at(values, index):
    if index < 0 or index >= len(values):
        return None
    value = values[index]
    return None if value is None else value


def _complete(reading):
    return all(
        reading[key] is not None
        for key in ("wind_mph", "rain_in_per_hour", "snow_in_per_hour")
    )


def _unavailable():
    return {
        "wind_mph": None,
        "rain_in_per_hour": None,
        "snow_in_per_hour": None,
        "weather_available": False,
        "forecast_time": None,
    }
