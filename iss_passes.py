"""
iss_passes.py

Fetches upcoming visible ISS passes for a given location — and, when there
are none, the station's live position — using N2YO's free API
(https://www.n2yo.com/api/ — free account required, no card).

Unlike the satellite cache, none of this can be pre-archived via GitHub
Actions since it depends on the requester's real-time location — it's a
live call to N2YO on every request.
"""

import math
import os
import requests

N2YO_API_KEY = os.environ.get("N2YO_API_KEY")
ISS_NORAD_ID = 25544  # NORAD catalog ID for the ISS (ZARYA)
EARTH_RADIUS_KM = 6371.0

_MISSING_KEY_MESSAGE = (
    "ISS tracking requires a free N2YO API key. Get one at "
    "https://www.n2yo.com/api/ and set N2YO_API_KEY."
)
_UPSTREAM_FAIL_MESSAGE = (
    "Could not reach the ISS tracking service just now. Try again in a moment."
)

_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _log_redacted(context: str, exc: Exception) -> None:
    """
    Logs an upstream failure with the API key stripped out.

    NEVER put exception text in an HTTP response. `requests` includes the
    full request URL in most of its error messages, and that URL carries
    apiKey as a query parameter — so returning the exception to the caller
    would hand the N2YO key to anyone able to trigger a failure. Every
    N2YO call in this module routes its errors through here, so there is
    exactly one place this can go wrong.
    """
    detail = str(exc)
    if N2YO_API_KEY:
        detail = detail.replace(N2YO_API_KEY, "<redacted>")
    print(f"[iss_passes] {context} failed: {detail}")


def _compass(azimuth: float) -> str:
    """Converts a compass bearing in degrees to a 16-point label."""
    return _COMPASS[int((azimuth % 360) / 22.5 + 0.5) % 16]


def fetch_iss_passes(lat: float, lon: float, alt: float = 0,
                     days: int = 10, min_visibility: int = 60) -> dict:
    """
    Returns upcoming visually-observable ISS passes for a location.

    Args:
        lat, lon: observer location in decimal degrees
        alt: observer altitude in meters (0 is fine for most purposes)
        days: how many days ahead to search (10 is N2YO's maximum)
        min_visibility: minimum visible duration in seconds to include a pass

    On min_visibility: the ISS is only visible for about six minutes even
    in a near-overhead pass, so the previous 300s threshold sat almost at
    the physical ceiling and discarded most watchable passes — measured at
    London, it dropped 9 of 24. 60s admits anything genuinely worth
    stepping outside for.

    Returns:
        {"configured": bool, "passes": list, "message": str | None}
        configured=False means no N2YO_API_KEY is set at all.
        A non-null message on configured=True means the request failed
        (network issue, invalid key, etc.) — passes will be empty in
        that case, never a crash.
    """
    if not N2YO_API_KEY:
        return {
            "configured": False,
            "passes": [],
            "message": _MISSING_KEY_MESSAGE,
        }

    url = (f"https://api.n2yo.com/rest/v1/satellite/visualpasses/"
           f"{ISS_NORAD_ID}/{lat}/{lon}/{alt}/{days}/{min_visibility}/")

    try:
        resp = requests.get(url, params={"apiKey": N2YO_API_KEY}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        passes = data.get("passes") or []
        return {"configured": True, "passes": passes, "message": None}
    except Exception as e:
        _log_redacted("N2YO visualpasses request", e)
        return {
            "configured": True,
            "passes": [],
            "message": _UPSTREAM_FAIL_MESSAGE,
        }


def _speed_kmh(first: dict, second: dict):
    """
    Orbital speed measured from two consecutive position samples.

    N2YO has no velocity field, so this derives it from the arc actually
    travelled between the samples at orbital radius. Measuring beats
    hardcoding ~27,600 km/h: it stays correct through reboosts and any
    future altitude change.

    Returns None rather than guessing if the samples are unusable.
    """
    try:
        dt = second["timestamp"] - first["timestamp"]
        if dt <= 0:
            return None

        lat1 = math.radians(first["satlatitude"])
        lat2 = math.radians(second["satlatitude"])
        dlat = lat2 - lat1
        dlon = math.radians(second["satlongitude"] - first["satlongitude"])

        # Haversine. Handles an antimeridian crossing between samples for
        # free — sin(dlon/2)**2 is identical for a +0.06° step and the
        # -359.94° the raw subtraction produces.
        a = (math.sin(dlat / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        central_angle = 2 * math.asin(min(1.0, math.sqrt(a)))

        mean_alt = (first["sataltitude"] + second["sataltitude"]) / 2
        distance_km = central_angle * (EARTH_RADIUS_KM + mean_alt)
        return distance_km / dt * 3600
    except Exception:
        # Malformed sample — the caller shows everything else and omits
        # speed rather than failing the whole response over one number.
        return None


def fetch_iss_position(lat: float, lon: float, alt: float = 0) -> dict:
    """
    Where the ISS is right now, relative to an observer.

    Used when the pass forecast comes back empty. That happens routinely —
    visible passes cluster with multi-week gaps between them, especially
    at lower latitudes — and the forecast only reaches 10 days ahead, so
    a quiet window can't be explained by predictions alone.

    `elevation` is degrees above the observer's horizon (negative means
    below it), and `eclipsed` is whether the station is in Earth's shadow.
    Between them they explain *why* nothing is visible, which is more use
    than an empty list.

    Returns:
        {"configured": bool, "position": dict | None, "message": str | None}
        Same never-throws contract as fetch_iss_passes.
    """
    if not N2YO_API_KEY:
        return {
            "configured": False,
            "position": None,
            "message": _MISSING_KEY_MESSAGE,
        }

    # Two samples, one second apart — the second exists only to measure
    # speed, since N2YO doesn't report it.
    url = (f"https://api.n2yo.com/rest/v1/satellite/positions/"
           f"{ISS_NORAD_ID}/{lat}/{lon}/{alt}/2/")

    try:
        resp = requests.get(url, params={"apiKey": N2YO_API_KEY}, timeout=15)
        resp.raise_for_status()
        positions = resp.json().get("positions") or []
        if not positions:
            return {
                "configured": True,
                "position": None,
                "message": _UPSTREAM_FAIL_MESSAGE,
            }

        now = positions[0]
        speed = _speed_kmh(now, positions[1]) if len(positions) > 1 else None
        azimuth = now.get("azimuth")

        return {
            "configured": True,
            "position": {
                "latitude": now.get("satlatitude"),
                "longitude": now.get("satlongitude"),
                "altitudeKm": now.get("sataltitude"),
                "speedKmh": round(speed) if speed is not None else None,
                "elevation": now.get("elevation"),
                "azimuth": azimuth,
                "azimuthCompass": _compass(azimuth) if azimuth is not None
                                  else None,
                "eclipsed": now.get("eclipsed"),
                "timestamp": now.get("timestamp"),
            },
            "message": None,
        }
    except Exception as e:
        _log_redacted("N2YO positions request", e)
        return {
            "configured": True,
            "position": None,
            "message": _UPSTREAM_FAIL_MESSAGE,
        }
