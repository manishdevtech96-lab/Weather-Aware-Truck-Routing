from django.urls import path

from .views import analyze_trip, health, reverse_place_view, suggest_places_view

urlpatterns = [
    path("health/", health, name="health"),
    path("places/suggest/", suggest_places_view, name="suggest-places"),
    path("places/reverse/", reverse_place_view, name="reverse-place"),
    path("trips/analyze/", analyze_trip, name="analyze-trip"),
]
