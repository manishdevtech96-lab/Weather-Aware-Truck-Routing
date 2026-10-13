"""Route summaries and the safest-route ranking."""

from .risk_engine import RISK_ORDER


def summarize_route(route, checkpoints):
    totals = {level: 0.0 for level in ("Low", "Moderate", "High", "Severe", "No Travel", "Unknown")}
    for index, checkpoint in enumerate(checkpoints[:-1]):
        miles = max(0, checkpoints[index + 1]["distance_miles"] - checkpoint["distance_miles"])
        level = checkpoint["risk_level"]
        totals[level] = totals.get(level, 0) + miles

    known = [checkpoint["risk_level"] for checkpoint in checkpoints if checkpoint["risk_level"] in RISK_ORDER]
    average = sum(RISK_ORDER[level] for level in known) / len(known) if known else None
    covered = sum(1 for checkpoint in checkpoints if checkpoint.get("weather_available"))

    return {
        "low_miles": round(totals["Low"], 2),
        "moderate_miles": round(totals["Moderate"], 2),
        "high_miles": round(totals["High"], 2),
        "severe_miles": round(totals["Severe"], 2),
        "no_travel_miles": round(totals["No Travel"], 2),
        "unknown_miles": round(totals["Unknown"], 2),
        "average_risk_score": round(average, 2) if average is not None else None,
        "distance_miles": route["distance_miles"],
        "duration_seconds": route["duration_seconds"],
        "duration_minutes": round(route["duration_seconds"] / 60),
        "forecast_coverage_percent": round(100 * covered / max(1, len(checkpoints))),
    }


def recommend_routes(routes):
    """Rank by fewest severe miles, fewest high miles, lowest average risk, then time."""

    def sort_key(route):
        summary = route["summary"]
        average = summary["average_risk_score"]
        if average is None:
            average = 999
        return (
            summary["severe_miles"],
            summary["high_miles"],
            average,
            summary["duration_seconds"],
        )

    return sorted(routes, key=sort_key)
