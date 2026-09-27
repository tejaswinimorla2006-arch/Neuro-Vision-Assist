"""Small Mapbox Search and walking Directions client for external destinations."""

import json
import math
import os
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class MapboxError(Exception):
    """A user-facing Mapbox request error."""


@dataclass(frozen=True)
class MapboxDestination:
    name: str
    address: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class MapboxStep:
    instruction: str
    distance_m: float
    maneuver_latitude: float
    maneuver_longitude: float


@dataclass(frozen=True)
class MapboxRoute:
    destination: MapboxDestination
    distance_m: float
    duration_s: float
    geometry: tuple
    steps: tuple


def _request_json(url: str) -> dict:
    try:
        with urlopen(Request(url, headers={"User-Agent": "neuro-vision-assist/1.0"}), timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise MapboxError("Internet connection unavailable.") from error


def _token() -> str:
    token = os.environ.get("MAPBOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise MapboxError("MAPBOX_ACCESS_TOKEN is not configured.")
    return token


def search_destination(query: str, latitude: float, longitude: float) -> MapboxDestination | None:
    token = _token()
    params = urlencode({
        "q": query,
        "access_token": token,
        "proximity": f"{longitude},{latitude}",
        "limit": 5,
    })
    try:
        payload = _request_json(f"https://api.mapbox.com/search/searchbox/v1/forward?{params}")
    except MapboxError:
        raise
    features = payload.get("features", [])
    if not features:
        return None

    def rank(feature):
        center = feature.get("geometry", {}).get("coordinates", [None, None])
        if len(center) < 2 or center[0] is None:
            return float("inf")
        return _haversine(latitude, longitude, float(center[1]), float(center[0]))

    feature = min(features, key=rank)
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    if len(coordinates) < 2:
        return None
    properties = feature.get("properties", {})
    name = properties.get("name") or feature.get("text") or query
    address = (properties.get("full_address") or properties.get("place_formatted")
               or feature.get("place_name") or "Address unavailable")
    return MapboxDestination(name, address, float(coordinates[1]), float(coordinates[0]))


def reverse_geocode(latitude: float, longitude: float) -> str | None:
    token = _token()
    params = urlencode({
        "longitude": longitude,
        "latitude": latitude,
        "access_token": token,
        "types": "poi,address,street",
        "language": "en",
        "limit": 1,
    })
    payload = _request_json(
        f"https://api.mapbox.com/search/searchbox/v1/reverse?{params}"
    )
    features = payload.get("features", [])
    if not features:
        return None
    properties = features[0].get("properties", {})
    name = properties.get("name")
    address = (properties.get("place_formatted") or properties.get("full_address")
               or features[0].get("place_name"))
    if name and address:
        return f"{name}, {address}"
    return name or address


def walking_route(origin_latitude: float, origin_longitude: float,
                  destination: MapboxDestination) -> MapboxRoute:
    token = _token()
    coordinates = (f"{origin_longitude},{origin_latitude};"
                   f"{destination.longitude},{destination.latitude}")
    params = urlencode({
        "access_token": token,
        "steps": "true",
        "overview": "full",
        "geometries": "geojson",
        "language": "en",
    })
    try:
        payload = _request_json(
            f"https://api.mapbox.com/directions/v5/mapbox/walking/{coordinates}?{params}"
        )
    except MapboxError:
        raise
    routes = payload.get("routes", [])
    if not routes:
        raise MapboxError("Route calculation failed.")
    route = routes[0]
    geometry = tuple(tuple(point) for point in route.get("geometry", {}).get("coordinates", []))
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            location = maneuver.get("location", [None, None])
            if len(location) >= 2 and location[0] is not None:
                steps.append(MapboxStep(
                    step.get("name") and step.get("maneuver", {}).get("instruction")
                    or step.get("instruction") or "Continue",
                    float(step.get("distance", 0.0)),
                    float(location[1]), float(location[0]),
                ))
    return MapboxRoute(destination, float(route.get("distance", 0.0)),
                       float(route.get("duration", 0.0)), geometry, tuple(steps))


def _haversine(lat1, lon1, lat2, lon2):
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = (math.sin(dphi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
