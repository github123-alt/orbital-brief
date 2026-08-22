"""
briefing.py

Generates a plain-language "Daily Space Operations Briefing" by combining
real-time NASA data (DONKI, NeoWs, EONET) with significance classification
grounded in real NOAA/NASA operational thresholds, topped with an
AI-generated narrative from IBM watsonx.ai (Granite), anomaly alerts,
mission window assessments, and spacecraft health forecasts.

Usage:
    python briefing.py
"""

from datetime import date

from nasa_api import (
    fetch_solar_flares,
    fetch_geomagnetic_storms,
    fetch_near_earth_objects,
    fetch_eonet_events,
    fetch_firms_fire_activity,
    fetch_satellites,
    fetch_satellites_with_status,
    fetch_decayed_satellites,
    classify_orbit_type,
    fetch_all_deep_space_objects,
)
from significance import (
    classify_flare,
    classify_geomagnetic_storm,
    classify_close_approach,
    summarize_earth_events,
    summarize_satellite_catalog,
    summarize_deep_space_objects,
    get_lunar_debris_summary,
    detect_alerts,
)
from mission_planner import assess_mission_windows, format_mission_windows
from spacecraft_health import score_spacecraft, format_spacecraft_health
from starlink import assess_starlink_fleet, format_starlink_fleet
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


# EONET's `days` filter matches an event's MOST RECENT observation, not its
# start, so a narrow window silently drops long-running events that nobody has
# re-reported lately — a fire logged three weeks ago disappears from a 7-day
# query while it is still burning. Measured on the live feed: 7 days returns 14
# events, 90 returns about 400 and is the narrowest window that surfaces
# volcanoes at all. 365 adds another ~1,100 that are mostly stale (one iceberg
# last observed years ago) for no new signal.
#
# "Reported in the last 7 days" is then derived locally by
# summarize_earth_events(), so the recent count is still available without
# making the window itself hide things.
EONET_WINDOW_DAYS = 90


def build_eonet_section():
    """
    EARTH EVENTS: what satellites actually detected, plus named events with a
    place and a duration.

    Two sources on purpose. EONET is a curated catalogue whose only wildfire
    source reports US incidents once each and never updates them; FIRMS is a
    raw global detection feed. Either alone is misleading — see the comment at
    the top of the EONET block in significance.py.

    Degrades to one source if the other is unavailable, and says which is
    missing rather than quietly dropping the number.
    """
    try:
        events = fetch_eonet_events(days_back=EONET_WINDOW_DAYS, status="open")
    except Exception as e:
        # A 90-day query asks more of EONET than the old 7-day one did, and
        # this section now has a second source that can carry it, so an EONET
        # outage costs the named-event list rather than the whole briefing.
        print(f"[briefing] EONET unavailable: {type(e).__name__}", flush=True)
        events = []

    return summarize_earth_events(events, firms=fetch_firms_fire_activity())


def fetch_catalog():
    """
    Fetch the satellite catalog once, for the sections that need it.

    Both SATELLITES and STARLINK are built from the same element sets, and
    each fetch is nine CelesTrak groups in parallel (or, in production, a
    read of the whole cached snapshot). Fetching per-section would double
    that for no new information. Returns (active, status, cached_at, decayed);
    decayed is empty when the catalog itself is unavailable, since there is
    nothing to compare it against.

    Not memoised on purpose — the API layer supports force_refresh, and a
    module-level cache in a long-running server process would pin the
    catalog until restart.
    """
    active, status, cached_at = fetch_satellites_with_status(group="active")
    decayed = [] if status == "unavailable" else fetch_decayed_satellites()
    return active, status, cached_at, decayed


def build_satellite_section(catalog=None):
    active, status, cached_at, decayed = catalog if catalog is not None else fetch_catalog()

    if status == "unavailable":
        return (
            "SATELLITES: Catalog temporarily unavailable — CelesTrak "
            "could not be reached from this server, and no cached "
            "snapshot is available yet. Other sections are unaffected."
        )

    result = summarize_satellite_catalog(active, decayed, classify_orbit_type)

    lines = [f"SATELLITES: {result['summary']}"]
    if status == "cached":
        lines.append(f"  (Live catalog unreachable — showing cached data "
                     f"from {cached_at})")

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


def build_starlink_section(catalog=None):
    """
    Summarise the Starlink constellation out of the catalog already fetched
    for the SATELLITES section. See starlink.py for why this deliberately
    makes no request of its own.
    """
    active, status, cached_at, decayed = catalog if catalog is not None else fetch_catalog()

    if status == "unavailable":
        return (
            "STARLINK CONSTELLATION: Unavailable — the satellite catalog "
            "this is derived from could not be reached. See the SATELLITES "
            "section."
        )

    assessment = assess_starlink_fleet(active, decayed)
    section = format_starlink_fleet(assessment)

    if status == "cached":
        # Appended rather than inserted after the title: the title line is
        # what the app splits sections on, so anything unindented below it
        # would start a new tile.
        section += f"\n  (Live catalog unreachable — showing cached data from {cached_at})"

    return section


def build_mission_window_section():
    """
    Extract the worst flare and peak Kp from the current data and assess
    mission windows. Worst-case flare defaults to 'C0' (benign) if none recorded.
    """
    flares = fetch_solar_flares(days_back=7)
    storms = fetch_geomagnetic_storms(days_back=7)
    neos   = fetch_near_earth_objects(days_forward=7)

    # Determine worst flare class
    worst_flare = "C0"
    if flares:
        rank = {"A": 0, "B": 0, "C": 1, "M": 2, "X": 3}
        worst_flare = max(
            (f.get("classType", "C0") for f in flares),
            key=lambda c: (rank.get(c[0].upper(), 0), float(c[1:] or 0))
        )

    # Determine peak Kp
    peak_kp = 0.0
    for storm in storms:
        for entry in storm.get("allKpIndex", []):
            peak_kp = max(peak_kp, float(entry.get("kpIndex", 0)))

    # Determine closest NEO tier
    neo_tier = "Routine"
    if neos:
        from significance import classify_close_approach
        best_ld = float("inf")
        for neo in neos:
            approaches = neo.get("close_approach_data", [])
            if approaches:
                km = float(approaches[0]["miss_distance"]["kilometers"])
                r  = classify_close_approach(km)
                if r["distance_ld"] < best_ld:
                    best_ld  = r["distance_ld"]
                    neo_tier = r["tier"]

    windows = assess_mission_windows(worst_flare, peak_kp, neo_tier)
    return format_mission_windows(windows)


def build_spacecraft_health_section():
    """
    Compute spacecraft risk scores from current worst-case flare and peak Kp.
    """
    flares = fetch_solar_flares(days_back=7)
    storms = fetch_geomagnetic_storms(days_back=7)

    worst_flare = "C0"
    if flares:
        rank = {"A": 0, "B": 0, "C": 1, "M": 2, "X": 3}
        worst_flare = max(
            (f.get("classType", "C0") for f in flares),
            key=lambda c: (rank.get(c[0].upper(), 0), float(c[1:] or 0))
        )

    peak_kp = 0.0
    for storm in storms:
        for entry in storm.get("allKpIndex", []):
            peak_kp = max(peak_kp, float(entry.get("kpIndex", 0)))

    scores = score_spacecraft(worst_flare, peak_kp)
    return format_spacecraft_health(scores)


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


def build_alert_banner(alerts: list) -> str:
    """
    Format active alerts into a prominent banner for the top of the briefing.
    Returns an empty string if there are no alerts (all-clear conditions).
    """
    if not alerts:
        return "OPERATIONAL STATUS: ✅ ALL CLEAR — No threshold-crossing conditions detected."
    lines = [f"⚠  OPERATIONAL ALERTS ({len(alerts)} active) ⚠"]
    for alert in alerts:
        lines.append(f"  • {alert}")
    return "\n".join(lines)


def generate_briefing():
    today = date.today().isoformat()

    # Shared by the SATELLITES and STARLINK sections, which are two views of
    # the same element sets. Fetched here so it happens once.
    catalog = fetch_catalog()

    # Build each data section independently
    section_map = {
        "solar_flares":     build_flare_section(),
        "geomagnetic":      build_geomagnetic_section(),
        "neo":              build_neo_section(),
        "earth_events":     build_eonet_section(),
        "satellites":       build_satellite_section(catalog),
        "starlink":         build_starlink_section(catalog),
        "deep_space":       build_deep_space_section(),
        "lunar_debris":     build_lunar_debris_section(),
        "mission_windows":  build_mission_window_section(),
        "spacecraft_health":build_spacecraft_health_section(),
    }

    # Detect threshold-crossing conditions
    alerts = detect_alerts(section_map)
    alert_banner = build_alert_banner(alerts)

    # Ask IBM Granite to narrate the day's conditions with alert context
    ai_narrative = generate_narrative(section_map, active_alerts=alerts)

    sections = [
        f"=== DAILY SPACE OPERATIONS BRIEFING — {today} ===\n",
        alert_banner,
        "",
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
        section_map["starlink"],
        "",
        section_map["spacecraft_health"],
        "",
        section_map["mission_windows"],
        "",
        section_map["deep_space"],
        "",
        section_map["lunar_debris"],
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    main()
