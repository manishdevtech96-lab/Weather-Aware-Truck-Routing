"""Weather and load-weight risk labels."""

RISK_ORDER = {
    "Low": 1,
    "Moderate": 2,
    "High": 3,
    "Severe": 4,
    "No Travel": 5,
}


def classify_weather(wind_mph, rain_in_per_hour, snow_in_per_hour, load_weight_lb):
    """Highest risk among wind, rain, and snow, then apply load rules.

    Boundary values belong to the more severe band. Load rules can raise wind
    risk, and they never lower a worse rain or snow condition.
    """
    if any(value is None for value in (wind_mph, rain_in_per_hour, snow_in_per_hour)):
        return "Unknown"

    risk = max(
        (_band_wind(wind_mph), _band_rain(rain_in_per_hour), _band_snow(snow_in_per_hour)),
        key=lambda level: RISK_ORDER[level],
    )
    if wind_mph >= 55:
        return "No Travel"
    if wind_mph >= 45 and load_weight_lb > 30000:
        return "No Travel"
    if 35 <= wind_mph < 45 and load_weight_lb > 40000:
        risk = max((risk, "Severe"), key=lambda level: RISK_ORDER[level])
    return risk


def _band_wind(speed_mph):
    if speed_mph >= 55:
        return "No Travel"
    if speed_mph >= 45:
        return "Severe"
    if speed_mph >= 35:
        return "High"
    if speed_mph >= 25:
        return "Moderate"
    return "Low"


def _band_rain(inches_per_hour):
    if inches_per_hour > 1:
        return "No Travel"
    if inches_per_hour >= 0.5:
        return "Severe"
    if inches_per_hour >= 0.25:
        return "High"
    if inches_per_hour >= 0.10:
        return "Moderate"
    return "Low"


def _band_snow(inches_per_hour):
    if inches_per_hour > 3:
        return "No Travel"
    if inches_per_hour >= 2:
        return "Severe"
    if inches_per_hour >= 1:
        return "High"
    if inches_per_hour >= 0.5:
        return "Moderate"
    return "Low"
