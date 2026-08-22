"""
iss_passes.py

Fetches upcoming visible ISS passes for a given location, using N2YO's
free API (https://www.n2yo.com/api/ — free account required, no card).

Unlike the satellite cache, this can't be pre-archived via GitHub Actions
since it depends on the requester's real-time location — it's a live
call to N2YO on every request.
"""

import os
import requests

N2YO_API_KEY = os.environ.get("N2YO_API_KEY")
ISS_NORAD_ID = 25544  # NORAD catalog ID for the ISS (ZARYA)


def fetch_iss_passes(lat: float, lon: float, alt: float = 0,
                      days: int = 7, min_visibility: int = 300) -> dict:
    """
    Returns upcoming visually-observable ISS passes for a location.

    Args:
        lat, lon: observer location in decimal degrees
        alt: observer altitude in meters (0 is fine for most purposes)
        days: how many days ahead to search (N2YO free tier allows up to 10)
        min_visibility: minimum visible duration in seconds to include a pass

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
            "message": "ISS pass predictions require a free N2YO API key. "
                       "Get one at https://www.n2yo.com/api/ and set "
                       "N2YO_API_KEY.",
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
        # Deliberately does not put the exception text in the response.
        # requests includes the full request URL in most of its error
        # messages, and that URL carries apiKey as a query parameter — so
        # returning `e` to the caller would hand the N2YO key to anyone able
        # to trigger a failure. Log it with the key redacted, and return
        # something safe and actionable instead.
        detail = str(e)
        if N2YO_API_KEY:
            detail = detail.replace(N2YO_API_KEY, "<redacted>")
        print(f"[iss_passes] N2YO request failed: {detail}")
        return {
            "configured": True,
            "passes": [],
            "message": "Could not reach the ISS tracking service just now. "
                       "Try again in a moment.",
        }
