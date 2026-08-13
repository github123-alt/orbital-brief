"""
nasa_api.py

Fetches real-time data from NASA open APIs, CelesTrak, and JPL Horizons:
- DONKI (space weather: solar flares, geomagnetic storms)
- NeoWs (near-Earth object tracking)
- EONET (Earth natural event tracker)
- CelesTrak (satellite catalog: active and decayed satellites)
- JPL Horizons (deep-space / escaped-Earth-orbit objects)

Requires the NASA_API_KEY environment variable to be set.
Get a free key at https://api.nasa.gov/
CelesTrak and JPL Horizons require no API key.
"""

import os
import requests
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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


# CelesTrak blocks HTTPS from server/cloud IPs; use HTTP which works universally.
CELESTRAK_URL = "http://celestrak.org/NORAD/elements/gp.php"

CELESTRAK_HEADERS = {
    "User-Agent": "orbital-brief/1.0 (https://github.com/your-username/orbital-brief)"
}


# Named groups that CelesTrak serves reliably — used to build a representative
# picture of the active fleet without hitting the blocked "active" mega-group.
CELESTRAK_GROUPS = [
    "stations",   # ISS, Tiangong, etc.
    "visual",     # brightest/most-tracked objects
    "weather",    # weather satellites
    "goes",       # NOAA GOES series
    "starlink",   # SpaceX Starlink constellation
    "oneweb",     # OneWeb constellation
    "planet",     # Planet Labs imaging sats
    "spire",      # Spire Global
    "analyst",    # analyst / miscellaneous tracked objects
]


def _fetch_group(group: str, timeout: int = 8) -> list:
    """Fetch one CelesTrak group; return empty list on any error.

    timeout is intentionally short (8s, down from 20s) — if CelesTrak is
    slow or blocked from the current network, we want to fail fast rather
    than stall the whole request. This function is also called in parallel
    across groups (see fetch_satellites), so a single slow group no longer
    blocks the others.
    """
    try:
        response = requests.get(
            CELESTRAK_URL,
            params={"GROUP": group, "FORMAT": "json"},
            headers=CELESTRAK_HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        # Tag each entry with its source group
        for sat in data:
            sat["_group"] = group
        return data
    except Exception:
        return []


def fetch_satellites(group="active"):
    """
    Fetch satellite data from CelesTrak.

    If group is "active" (the default), aggregates across all known reliable
    named groups because CelesTrak blocks the full "active" dataset.
    Otherwise fetches the specific group requested.

    Groups are fetched IN PARALLEL (not sequentially) so a single slow or
    blocked group only costs its own timeout, not 9x that time.

    Args:
        group (str): CelesTrak GROUP name, or "active" for the aggregated set.

    Returns:
        list of satellite dicts with keys like:
            OBJECT_NAME, NORAD_CAT_ID, OBJECT_TYPE,
            PERIOD, INCLINATION, APOGEE, PERIGEE, _group
    """
    if group == "active":
        seen = set()
        satellites = []
        with ThreadPoolExecutor(max_workers=len(CELESTRAK_GROUPS)) as executor:
            futures = {executor.submit(_fetch_group, g): g for g in CELESTRAK_GROUPS}
            for future in as_completed(futures):
                for sat in future.result():
                    norad_id = sat.get("NORAD_CAT_ID")
                    if norad_id and norad_id not in seen:
                        seen.add(norad_id)
                        satellites.append(sat)
        return satellites

    return _fetch_group(group)


def fetch_decayed_satellites():
    """
    Fetch recently re-entered satellites from CelesTrak (last-30-days group).

    Returns:
        list of satellite dicts
    """
    return _fetch_group("last-30-days")


def classify_orbit_type(period_minutes=None, mean_motion=None):
    """
    Classify a satellite's orbit type.

    Accepts either orbital period (minutes) or mean motion (revolutions/day),
    since CelesTrak JSON returns MEAN_MOTION rather than PERIOD.

    Args:
        period_minutes (float, optional): orbital period in minutes
        mean_motion (float, optional): mean motion in rev/day

    Returns:
        str: "LEO", "MEO", "GEO", or "HEO"
    """
    # Derive period from mean_motion if period not given
    if period_minutes is None and mean_motion is not None:
        try:
            period_minutes = 1440.0 / float(mean_motion)  # 1440 min/day
        except (ZeroDivisionError, TypeError, ValueError):
            return "Unknown"

    if period_minutes is None:
        return "Unknown"

    p = float(period_minutes)
    if p < 128:              # roughly below ~2,000 km altitude
        return "LEO"
    elif p < 600:            # up to ~20,000 km
        return "MEO"
    elif 1400 <= p <= 1500:  # ~24h period
        return "GEO"
    else:
        return "HEO"


# ---------------------------------------------------------------------------
# JPL Horizons — deep-space / escaped-Earth-orbit objects & space telescopes
# ---------------------------------------------------------------------------

# Correct JPL Horizons API endpoint
JPL_HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# Human-made objects beyond Earth orbit tracked by JPL Horizons.
# "type" values:
#   spacecraft   — operational or former science/exploration probes
#   telescope    — space observatories (Earth-orbiting or L2/heliocentric)
#   rocket_body  — escaped upper stages / debris
#
# Note on interstellar objects:
#   Voyager 1 crossed the heliopause (~123 AU) in Aug 2012 — now in interstellar space.
#   Voyager 2 crossed the heliopause (~119 AU) in Nov 2018 — now in interstellar space.
#   All others remain within the heliosphere.

DEEP_SPACE_OBJECTS = [
    # ── Interstellar spacecraft (beyond the heliopause) ────────────────────
    {"name": "Voyager 1",              "id": "-31",   "type": "spacecraft",
     "note": "Farthest human-made object; crossed into interstellar space Aug 2012; still transmitting"},
    {"name": "Voyager 2",              "id": "-32",   "type": "spacecraft",
     "note": "Second farthest; crossed into interstellar space Nov 2018; still transmitting"},
    # ── Deep-space probes (within heliosphere) ─────────────────────────────
    {"name": "New Horizons",           "id": "-98",   "type": "spacecraft",
     "note": "Flew past Pluto Jul 2015 & Arrokoth Jan 2019; now in Kuiper Belt"},
    {"name": "Pioneer 10",             "id": "-23",   "type": "spacecraft",
     "note": "First spacecraft through asteroid belt & past Jupiter; last contact Jan 2003"},
    {"name": "Pioneer 11",             "id": "-24",   "type": "spacecraft",
     "note": "First to flyby Saturn; last contact Nov 1995; heading toward constellation Aquila"},
    {"name": "Ulysses",                "id": "-55",   "type": "spacecraft",
     "note": "ESA/NASA solar polar orbiter; mission ended Jun 2009; in solar orbit"},
    # ── Space telescopes (operational) ────────────────────────────────────
    {"name": "Hubble Space Telescope", "id": "-48",   "type": "telescope",
     "note": "NASA; LEO at ~547 km; launched 1990; repaired 5 times; still operational as of 2025"},
    {"name": "James Webb Space Telescope", "id": "-170", "type": "telescope",
     "note": "NASA/ESA/CSA; at L2 (~1.5M km from Earth); launched Dec 2021; deepest infrared images ever"},
    {"name": "Spitzer Space Telescope","id": "-79",   "type": "telescope",
     "note": "NASA infrared; heliocentric Earth-trailing orbit; retired Jan 2020"},
    {"name": "Kepler / K2",            "id": "-227",  "type": "telescope",
     "note": "NASA; discovered 2,600+ confirmed exoplanets; retired Oct 2018; heliocentric orbit"},
    # ── Escaped rocket bodies / debris ────────────────────────────────────
    {"name": "Chang'e 5-T1 booster",   "id": "-164",  "type": "rocket_body",
     "note": "CNSA upper stage; impacted Moon Mar 2022 — no longer in space"},
]


def fetch_deep_space_object(horizons_id: str, name: str) -> dict | None:
    """
    Query JPL Horizons for the current heliocentric distance of a single object.
    Returns a lightweight summary dict, or None on failure.

    Args:
        horizons_id (str): Horizons COMMAND id (e.g. "-31" for Voyager 1)
        name (str): human-readable name for display

    Returns:
        dict with keys: name, horizons_id, range_au, range_km
        or None if the query fails or object is no longer in space
    """
    from datetime import date as _date, timedelta as _td
    today = _date.today().isoformat()
    tomorrow = (_date.today() + _td(days=1)).isoformat()

    params = {
        "format": "json",
        "COMMAND": horizons_id,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "500@10",        # heliocentric (Sun-centred)
        "START_TIME": today,
        "STOP_TIME": tomorrow,
        "STEP_SIZE": "1d",
        "QUANTITIES": "19",        # range & range-rate
    }
    try:
        resp = requests.get(JPL_HORIZONS_URL, params=params, timeout=8)
        resp.raise_for_status()
        result_text = resp.json().get("result", "")

        # Data sits between $$SOE and $$EOE markers
        range_au = None
        in_data = False
        for line in result_text.splitlines():
            if "$$SOE" in line:
                in_data = True
                continue
            if "$$EOE" in line:
                break
            if in_data:
                parts = line.split()
                # Format: "date time  range_AU  range_rate"
                # date part contains "-", e.g. "2025-Aug-01"
                if len(parts) >= 3:
                    try:
                        range_au = float(parts[2])
                        break
                    except ValueError:
                        continue

        if range_au is None:
            return None

        return {
            "name": name,
            "horizons_id": horizons_id,
            "range_au": round(range_au, 4),
            "range_km": round(range_au * 149_597_870.7, 0),  # exact AU in km
        }
    except Exception:
        return None


def fetch_all_deep_space_objects() -> list[dict]:
    """
    Fetch heliocentric range data for all objects in DEEP_SPACE_OBJECTS.
    Objects that fail to return data are silently skipped (e.g. objects
    that have already impacted the Moon or are no longer tracked).

    Objects are queried IN PARALLEL (not sequentially) — with 11 objects
    and an 8s timeout each, sequential fetching could cost up to ~90s if
    JPL Horizons is slow; in parallel it costs roughly one timeout's worth.

    Returns:
        list of dicts with keys: name, horizons_id, range_au, range_km, type, note
    """
    results = []
    with ThreadPoolExecutor(max_workers=len(DEEP_SPACE_OBJECTS)) as executor:
        futures = {
            executor.submit(fetch_deep_space_object, obj["id"], obj["name"]): obj
            for obj in DEEP_SPACE_OBJECTS
        }
        for future in as_completed(futures):
            obj = futures[future]
            result = future.result()
            if result:
                result["type"] = obj["type"]
                result["note"] = obj.get("note", "")
                results.append(result)
    return results


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

    print("\n--- Active Satellites (CelesTrak) ---")
    active = fetch_satellites(group="active")
    print(f"Found {len(active)} active satellite(s)")
    for s in active[:3]:
        print(f"  {s.get('OBJECT_NAME')} | NORAD {s.get('NORAD_CAT_ID')} | Period: {s.get('PERIOD')} min")

    print("\n--- Recently Decayed Satellites (CelesTrak) ---")
    decayed = fetch_decayed_satellites()
    print(f"Found {len(decayed)} recently decayed satellite(s)")
    for s in decayed[:3]:
        print(f"  {s.get('OBJECT_NAME')} | NORAD {s.get('NORAD_CAT_ID')} | Decayed: {s.get('DECAY_DATE')}")
