"""
briefing.py

Generates a plain-language "Daily Space Operations Briefing" by combining
real-time NASA data (DONKI, NeoWs, EONET) with significance classification
grounded in real NOAA/NASA operational thresholds.

Usage:
    python briefing.py
"""

from datetime import date

from nasa_api import (
    fetch_solar_flares,
    fetch_geomagnetic_storms,
    fetch_near_earth_objects,
    fetch_eonet_events,
    count_eonet_by_category,
)
from significance import (
    classify_flare,
    classify_geomagnetic_storm,
    classify_close_approach,
    summarize_eonet_events,
)


def build_flare_section():
    flares = fetch_solar_flares(days_back=7)
    if not flares:
        return "SOLAR FLARES: No significant solar flares recorded in the past 7 days. Conditions quiet."

    lines = [f"SOLAR FLARES: {len(flares)} flare(s) recorded in the past 7 days."]
    # Highlight the most significant flare
    most_significant = None
    highest_rank = -1
    rank_order = {"None": 0, "Minor": 1, "Moderate": 2, "Strong": 3, "Severe": 4, "Extreme": 5}

    for flare in flares:
        class_type = flare.get("classType", "")
        result = classify_flare(class_type)
        rank = rank_order.get(result["severity"], -1)
        if rank > highest_rank:
            highest_rank = rank
            most_significant = (flare, result)

    if most_significant:
        flare, result = most_significant
        lines.append(
            f"  Most significant: {flare.get('classType')} class flare on {flare.get('beginTime', 'unknown date')} "
            f"— {result['r_scale']} ({result['severity']}). {result['description']}"
        )
    return "\n".join(lines)


def build_geomagnetic_section():
    storms = fetch_geomagnetic_storms(days_back=7)
    if not storms:
        return "GEOMAGNETIC ACTIVITY: No geomagnetic storms recorded in the past 7 days. Conditions quiet."

    lines = [f"GEOMAGNETIC ACTIVITY: {len(storms)} storm(s) recorded in the past 7 days."]
    for storm in storms[:3]:
        kp_entries = storm.get("allKpIndex", [])
        if kp_entries:
            max_kp = max(entry.get("kpIndex", 0) for entry in kp_entries)
            result = classify_geomagnetic_storm(max_kp)
            lines.append(
                f"  Storm starting {storm.get('startTime', 'unknown date')}: "
                f"peak Kp={max_kp} — {result['g_scale']} ({result['severity']}). {result['description']}"
            )
    return "\n".join(lines)


def build_neo_section():
    neos = fetch_near_earth_objects(days_forward=7)
    if not neos:
        return "NEAR-EARTH OBJECTS: No close approaches recorded for the coming week."

    lines = [f"NEAR-EARTH OBJECTS: {len(neos)} object(s) tracked with close approaches in the coming week."]

    # Find the closest approach among all tracked objects
    closest = None
    closest_ld = float("inf")

    for neo in neos:
        approaches = neo.get("close_approach_data", [])
        if not approaches:
            continue
        miss_km = float(approaches[0]["miss_distance"]["kilometers"])
        diameter_est = neo.get("estimated_diameter", {}).get("meters", {})
        diameter_avg = None
        if diameter_est:
            diameter_avg = (diameter_est.get("estimated_diameter_min", 0) +
                             diameter_est.get("estimated_diameter_max", 0)) / 2

        result = classify_close_approach(miss_km, diameter_avg)
        if result["distance_ld"] < closest_ld:
            closest_ld = result["distance_ld"]
            closest = (neo, result)

    if closest:
        neo, result = closest
        pha_flag = " (within potentially-hazardous monitoring range)" if result["is_pha_range"] else ""
        lines.append(
            f"  Closest approach: {neo.get('name', 'Unknown')} — {result['tier']}{pha_flag}. {result['description']}"
        )
    return "\n".join(lines)


def build_eonet_section():
    events = fetch_eonet_events(days_back=7, status="open")
    counts = count_eonet_by_category(events)
    summary = summarize_eonet_events(counts)
    return f"EARTH EVENTS (from orbit): {summary}"


def generate_briefing():
    today = date.today().isoformat()
    sections = [
        f"=== DAILY SPACE OPERATIONS BRIEFING — {today} ===\n",
        build_flare_section(),
        "",
        build_geomagnetic_section(),
        "",
        build_neo_section(),
        "",
        build_eonet_section(),
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    print(generate_briefing())
