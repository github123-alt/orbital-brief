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
MU_EARTH_KM3_S2 = 398600.4418  # Earth's standard gravitational parameter

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


def _orbital_speed_kmh(altitude_km):
    """
    Orbital speed from altitude, via the circular-orbit case of vis-viva:
    v = sqrt(mu / r).

    An earlier version derived this by differencing two consecutive
    position samples, which was subtly wrong. N2YO reports sub-satellite
    latitude and longitude in an Earth-fixed frame, so differencing them
    gives ground-track speed — Earth's own rotation already subtracted —
    which came out ~4% under the figure every reference quotes (26,550 vs
    27,590 km/h).

    Altitude is live telemetry as well, so this still tracks reboosts, and
    the ISS's eccentricity of ~0.0005 makes the circular assumption good
    to well under 0.1%.
    """
    try:
        radius_km = EARTH_RADIUS_KM + float(altitude_km)
        if radius_km <= 0:
            return None
        return math.sqrt(MU_EARTH_KM3_S2 / radius_km) * 3600
    except (TypeError, ValueError):
        return None


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

    url = (f"https://api.n2yo.com/rest/v1/satellite/positions/"
           f"{ISS_NORAD_ID}/{lat}/{lon}/{alt}/1/")

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
        speed = _orbital_speed_kmh(now.get("sataltitude"))
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
