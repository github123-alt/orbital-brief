"""
nasa_api.py

Fetches real-time data from three NASA open APIs:
- DONKI (space weather: solar flares, geomagnetic storms)
- NeoWs (near-Earth object tracking)
- EONET (Earth natural event tracker)

Requires the NASA_API_KEY environment variable to be set.
Get a free key at https://api.nasa.gov/
"""

import os
import requests
from datetime import date, timedelta

NASA_API_KEY = os.environ.get("NASA_API_KEY")
BASE_URL = "https://api.nasa.gov"
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3"

if not NASA_API_KEY:
    raise EnvironmentError(
        "NASA_API_KEY environment variable not set. "
        "Get a free key at https://api.nasa.gov/ and set it with:\n"
        "  export NASA_API_KEY=\"your_key_here\""
    )


def fetch_solar_flares(days_back=7):
    """
    Fetch recent solar flare events from DONKI.

    Args:
        days_back (int): how many days back to look

    Returns:
        list of dicts, each with 'flrID', 'classType', 'beginTime', etc.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    url = f"{BASE_URL}/DONKI/FLR"
    params = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "api_key": NASA_API_KEY
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_geomagnetic_storms(days_back=7):
    """
    Fetch recent geomagnetic storm events from DONKI.

    Args:
        days_back (int): how many days back to look

    Returns:
        list of dicts, each with 'gstID', 'startTime', 'allKpIndex', etc.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    url = f"{BASE_URL}/DONKI/GST"
    params = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "api_key": NASA_API_KEY
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_near_earth_objects(days_forward=7):
    """
    Fetch near-Earth object close-approach data from NeoWs.

    Args:
        days_forward (int): how many days ahead to look (max 7 per NASA API limits)

    Returns:
        list of dicts, each representing one asteroid with close-approach info
    """
    start_date = date.today()
    end_date = start_date + timedelta(days=min(days_forward, 7))

    url = f"{BASE_URL}/neo/rest/v1/feed"
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "api_key": NASA_API_KEY
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    # Flatten the date-keyed structure into a simple list
    objects = []
    for date_key, neos in data.get("near_earth_objects", {}).items():
        for neo in neos:
            objects.append(neo)
    return objects


def fetch_eonet_events(days_back=7, status="open"):
    """
    Fetch recent Earth natural events from EONET (no API key required for this one,
    but we keep the interface consistent with the other fetchers).

    Args:
        days_back (int): how many days back to look
        status (str): "open", "closed", or "all"

    Returns:
        list of event dicts, each with 'title', 'categories', 'geometry', etc.
    """
    url = f"{EONET_URL}/events"
    params = {
        "status": status,
        "days": days_back
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    return data.get("events", [])


def count_eonet_by_category(events):
    """
    Helper: turn a raw EONET events list into a {category: count} dict,
    ready for significance.summarize_eonet_events().
    """
    counts = {}
    for event in events:
        for category in event.get("categories", []):
            name = category.get("title", "Unknown")
            counts[name] = counts.get(name, 0) + 1
    return counts


if __name__ == "__main__":
    # Quick manual test of each fetcher
    print("--- Solar Flares (last 7 days) ---")
    flares = fetch_solar_flares()
    print(f"Found {len(flares)} flare(s)")
    for f in flares[:3]:
        print(f"  {f.get('flrID')}: class {f.get('classType')}, begin {f.get('beginTime')}")

    print("\n--- Geomagnetic Storms (last 7 days) ---")
    storms = fetch_geomagnetic_storms()
    print(f"Found {len(storms)} storm(s)")
    for s in storms[:3]:
        print(f"  {s.get('gstID')}: start {s.get('startTime')}")

    print("\n--- Near-Earth Objects (next 7 days) ---")
    neos = fetch_near_earth_objects()
    print(f"Found {len(neos)} object(s)")
    for n in neos[:3]:
        print(f"  {n.get('name')}")

    print("\n--- EONET Events (last 7 days, open) ---")
    events = fetch_eonet_events()
    print(f"Found {len(events)} event(s)")
    counts = count_eonet_by_category(events)
    print(counts)
