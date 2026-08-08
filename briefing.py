"""
briefing.py

Generates a plain-language "Daily Space Operations Briefing" by combining
real-time NASA data (DONKI, NeoWs, EONET) with significance classification
grounded in real NOAA/NASA operational thresholds, topped with an
AI-generated narrative summary from IBM watsonx.ai (Granite).

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
    fetch_satellites,
    fetch_decayed_satellites,
    classify_orbit_type,
    fetch_all_deep_space_objects,
)
from significance import (
    classify_flare,
    classify_geomagnetic_storm,
    classify_close_approach,
    summarize_eonet_events,
    summarize_satellite_catalog,
    summarize_deep_space_objects,
    get_lunar_debris_summary,
)
from watsonx import generate_narrative


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


def build_satellite_section():
    active = fetch_satellites(group="active")
    decayed = fetch_decayed_satellites()
    result = summarize_satellite_catalog(active, decayed, classify_orbit_type)

    lines = [f"SATELLITES: {result['summary']}"]

    # Orbit breakdown
    orbit_detail = ", ".join(
        f"{count} {orbit}"
        for orbit, count in result["by_orbit"].items()
        if count > 0
    )
    if orbit_detail:
        lines.append(f"  Orbit breakdown: {orbit_detail}")

    # Recently decayed objects
    if result["notable_decayed"]:
        names = ", ".join(result["notable_decayed"])
        lines.append(f"  Recently re-entered: {names}")

    return "\n".join(lines)


def build_deep_space_section():
    objects = fetch_all_deep_space_objects()
    return summarize_deep_space_objects(objects)


def build_lunar_debris_section():
    data = get_lunar_debris_summary()
    lines = [
        f"LUNAR DEBRIS INVENTORY: {data['summary']}",
        f"  Heaviest single object: {data['heaviest']['name']} "
        f"(~{data['heaviest']['mass_kg']:,} kg, {data['heaviest']['year']}) "
        f"— {data['heaviest']['note']}",
        f"  Total mass on surface: ~{data['mass_on_surface_kg']:,.0f} kg  |  "
        f"Total mass impacted: ~{data['mass_impacted_kg']:,.0f} kg",
    ]
    # Show the 5 most recent items chronologically
    recent = sorted(data["items"], key=lambda o: o["year"], reverse=True)[:5]
    lines.append("  Most recent additions:")
    for item in recent:
        fate_label = "surface" if item["fate"] == "surface" else "impact"
        lines.append(
            f"    {item['year']}  {item['name']} ({item['mass_kg']:,} kg, {fate_label}) — {item['note']}"
        )
    return "\n".join(lines)


def main():
    print(generate_briefing())


def generate_briefing():
    today = date.today().isoformat()

    # Build each data section independently
    section_map = {
        "solar_flares":  build_flare_section(),
        "geomagnetic":   build_geomagnetic_section(),
        "neo":           build_neo_section(),
        "earth_events":  build_eonet_section(),
        "satellites":    build_satellite_section(),
        "deep_space":    build_deep_space_section(),
        "lunar_debris":  build_lunar_debris_section(),
    }

    # Ask IBM Granite to narrate the day's conditions
    ai_narrative = generate_narrative(section_map)

    sections = [
        f"=== DAILY SPACE OPERATIONS BRIEFING — {today} ===\n",
        ai_narrative,
        "",
        "--- DETAILED DATA ---",
        "",
        section_map["solar_flares"],
        "",
        section_map["geomagnetic"],
        "",
        section_map["neo"],
        "",
        section_map["earth_events"],
        "",
        section_map["satellites"],
        "",
        section_map["deep_space"],
        "",
        section_map["lunar_debris"],
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    main()
