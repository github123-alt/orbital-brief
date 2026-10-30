"""
briefing.py

Generates a plain-language "Daily Space Operations Briefing" by combining
real-time NASA data (DONKI, NeoWs, EONET) with significance classification
grounded in real NOAA/NASA operational thresholds, topped with an
AI-generated narrative from IBM watsonx.ai (Granite), anomaly alerts,
mission window assessments, and spacecraft health forecasts.

Resilience: every section is built inside safe_section(), so one failing
upstream API produces a one-line "Data temporarily unavailable" placeholder
for that section instead of crashing the whole briefing. DONKI and NeoWs data
is fetched ONCE per briefing and shared between sections, so an outage costs
one retry cycle, not three.

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


# ---------------------------------------------------------------------------
# Failure handling helpers
# ---------------------------------------------------------------------------

# fetch_solar_flares() returns a simulated placeholder flare when DONKI is
# down, so the app keeps running. It must never be presented (or archived) as
# a real observation, so it is detected by ID prefix and treated as "no data".
FALLBACK_FLARE_PREFIX = "FALLBACK-SIMULATED"

UNAVAILABLE_SUFFIX = "Data temporarily unavailable."


def safe_section(builder, title, *args):
    """
    Run a section builder; if it raises, return a one-line placeholder in the
    same 'TITLE: text' format so the rest of the briefing still renders.

    Only the exception TYPE is logged, never its message: `requests` puts the
    full request URL (including API keys) into its exception text.
    """
    try:
        return builder(*args)
    except Exception as e:
        print(f"[briefing] {title} section failed: {type(e).__name__}", flush=True)
        return f"{title}: {UNAVAILABLE_SUFFIX}"


def safe_fetch(fetcher, label, *args, **kwargs):
    """
    Run a data fetcher; return [] on any failure so downstream code can treat
    'no data' uniformly. Logs the exception type only (see safe_section).
    """
    try:
        result = fetcher(*args, **kwargs)
        return result if result is not None else []
    except Exception as e:
        print(f"[briefing] {label} fetch failed: {type(e).__name__}", flush=True)
        return []


def _split_fallback_flares(flares):
    """
    Separate real flares from the simulated outage placeholder.
    Returns (real_flares, used_fallback: bool).
    """
    real = [f for f in flares if not str(f.get("flrID", "")).startswith(FALLBACK_FLARE_PREFIX)]
    return real, len(real) != len(flares)


# ---------------------------------------------------------------------------
# Shared metric helpers (previously duplicated in two builders)
# ---------------------------------------------------------------------------

_FLARE_LETTER_RANK = {"A": 0, "B": 0, "C": 1, "M": 2, "X": 3}


def _flare_sort_key(class_type):
    """Sort key for a flare class string like 'M5.2'; tolerant of bad input."""
    class_type = (class_type or "C0").strip() or "C0"
    letter = _FLARE_LETTER_RANK.get(class_type[0].upper(), 0)
    try:
        magnitude = float(class_type[1:] or 0)
    except ValueError:
        magnitude = 0.0
    return (letter, magnitude)


def _worst_flare_class(flares):
    """Strongest flare class among real flares, or 'C0' (benign) if none."""
    if not flares:
        return "C0"
    return max(
        (f.get("classType") or "C0" for f in flares),
        key=_flare_sort_key,
    )


def _peak_kp(storms):
    """Highest Kp index across all storms; 0.0 if none or unparseable."""
    peak = 0.0
    for storm in storms or []:
        for entry in storm.get("allKpIndex", []):
            try:
                peak = max(peak, float(entry.get("kpIndex", 0)))
            except (TypeError, ValueError):
                continue
    return peak


# ---------------------------------------------------------------------------
# Section builders
# Each accepts optional pre-fetched data so generate_briefing() can fetch once
# and share. Called with no arguments (e.g. from other modules), they fetch
# for themselves exactly as before.
# ---------------------------------------------------------------------------

def build_flare_section(flares=None):
    if flares is None:
        flares = fetch_solar_flares(days_back=7)

    flares, used_fallback = _split_fallback_flares(flares)
    if used_fallback:
        return "SOLAR FLARES: " + UNAVAILABLE_SUFFIX + " NASA DONKI could not be reached."
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


def build_geomagnetic_section(storms=None):
    if storms is None:
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


def build_neo_section(neos=None):
    if neos is None:
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
        try:
            miss_km = float(approaches[0]["miss_distance"]["kilometers"])
        except (KeyError, TypeError, ValueError):
            continue
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


def build_mission_window_section(flares=None, storms=None, neos=None):
    """
    Extract the worst flare and peak Kp from the current data and assess
    mission windows. Worst-case flare defaults to 'C0' (benign) if none recorded.
    """
    if flares is None:
        flares = fetch_solar_flares(days_back=7)
    if storms is None:
        storms = fetch_geomagnetic_storms(days_back=7)
    if neos is None:
        neos = fetch_near_earth_objects(days_forward=7)

    flares, _ = _split_fallback_flares(flares)
    worst_flare = _worst_flare_class(flares)
    peak_kp = _peak_kp(storms)

    # Determine closest NEO tier
    neo_tier = "Routine"
    best_ld = float("inf")
    for neo in neos or []:
        approaches = neo.get("close_approach_data", [])
        if not approaches:
            continue
        try:
            km = float(approaches[0]["miss_distance"]["kilometers"])
        except (KeyError, TypeError, ValueError):
            continue
        r = classify_close_approach(km)
        if r["distance_ld"] < best_ld:
            best_ld = r["distance_ld"]
            neo_tier = r["tier"]

    windows = assess_mission_windows(worst_flare, peak_kp, neo_tier)
    return format_mission_windows(windows)


def build_spacecraft_health_section(flares=None, storms=None):
    """
    Compute spacecraft risk scores from current worst-case flare and peak Kp.
    """
    if flares is None:
        flares = fetch_solar_flares(days_back=7)
    if storms is None:
        storms = fetch_geomagnetic_storms(days_back=7)

    flares, _ = _split_fallback_flares(flares)
    scores = score_spacecraft(_worst_flare_class(flares), _peak_kp(storms))
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


def build_alert_banner(alerts: list) -> str:
    """
    Format active alerts into a prominent banner for the top of the briefing.
    Returns an all-clear line if there are no alerts.
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
    try:
        catalog = fetch_catalog()
    except Exception as e:
        print(f"[briefing] catalog fetch failed: {type(e).__name__}", flush=True)
        catalog = ([], "unavailable", None, [])

    # DONKI and NeoWs data feeds several sections (flares/storms/NEOs are each
    # used by 2-3 builders). Fetched once here so an outage costs one retry
    # cycle instead of one per section. A failed fetch yields [] ("no data").
    flares = safe_fetch(fetch_solar_flares, "solar flare", days_back=7)
    storms = safe_fetch(fetch_geomagnetic_storms, "geomagnetic", days_back=7)
    neos = safe_fetch(fetch_near_earth_objects, "NEO", days_forward=7)

    # Build each data section independently; one failure can't sink the rest.
    section_map = {
        "solar_flares":      safe_section(build_flare_section, "SOLAR FLARES", flares),
        "geomagnetic":       safe_section(build_geomagnetic_section, "GEOMAGNETIC ACTIVITY", storms),
        "neo":               safe_section(build_neo_section, "NEAR-EARTH OBJECTS", neos),
        "earth_events":      safe_section(build_eonet_section, "EARTH EVENTS"),
        "satellites":        safe_section(build_satellite_section, "SATELLITES", catalog),
        "starlink":          safe_section(build_starlink_section, "STARLINK CONSTELLATION", catalog),
        "deep_space":        safe_section(build_deep_space_section, "DEEP SPACE OBJECTS"),
        "lunar_debris":      safe_section(build_lunar_debris_section, "LUNAR DEBRIS INVENTORY"),
        "mission_windows":   safe_section(build_mission_window_section, "MISSION WINDOWS", flares, storms, neos),
        "spacecraft_health": safe_section(build_spacecraft_health_section, "SPACECRAFT HEALTH", flares, storms),
    }

    # Detect threshold-crossing conditions
    try:
        alerts = detect_alerts(section_map)
    except Exception as e:
        print(f"[briefing] alert detection failed: {type(e).__name__}", flush=True)
        alerts = []
    alert_banner = build_alert_banner(alerts)

    # Ask IBM Granite to narrate the day's conditions with alert context
    try:
        ai_narrative = generate_narrative(section_map, active_alerts=alerts)
    except Exception as e:
        print(f"[briefing] narrative failed: {type(e).__name__}", flush=True)
        ai_narrative = "AI NARRATIVE: Unavailable today. See detailed data below."

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


def main():
    print(generate_briefing())


if __name__ == "__main__":
    main()
