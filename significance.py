"""
significance.py

Interprets raw space data (solar flare class, Kp index, asteroid close-approach
distance, EONET event counts) into plain-language significance assessments,
grounded in real NOAA/NASA operational thresholds.
"""

import re
from collections import Counter
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Solar Flares -> R-Scale (Radio Blackouts)
# ---------------------------------------------------------------------------

def classify_flare(flare_class_str):
    """
    Classify a solar flare string (e.g. 'X8.7', 'M2.1', 'C5.0') into
    NOAA R-scale radio blackout severity.

    Args:
        flare_class_str (str): flare classification as returned by DONKI,
            e.g. "X8.7", "M9.2", "C1.0"

    Returns:
        dict with keys: class_label, r_scale, severity, description
    """
    match = re.match(r"([ABCMX])(\d+\.?\d*)", flare_class_str.strip().upper())
    if not match:
        return {
            "class_label": flare_class_str,
            "r_scale": "Unknown",
            "severity": "Unknown",
            "description": "Could not parse flare classification."
        }

    letter, magnitude = match.group(1), float(match.group(2))

    if letter in ("A", "B", "C"):
        return {
            "class_label": flare_class_str,
            "r_scale": "R0",
            "severity": "None",
            "description": "No significant radio blackout impact expected."
        }
    elif letter == "M":
        if magnitude < 5:
            return {
                "class_label": flare_class_str,
                "r_scale": "R1",
                "severity": "Minor",
                "description": "Weak HF radio degradation possible on the sunlit side of Earth."
            }
        else:
            return {
                "class_label": flare_class_str,
                "r_scale": "R2",
                "severity": "Moderate",
                "description": "Limited HF radio blackout possible on the sunlit side."
            }
    elif letter == "X":
        if magnitude < 10:
            return {
                "class_label": flare_class_str,
                "r_scale": "R3",
                "severity": "Strong",
                "description": "Wide-area HF radio blackout likely for about an hour."
            }
        elif magnitude < 20:
            return {
                "class_label": flare_class_str,
                "r_scale": "R4",
                "severity": "Severe",
                "description": "HF radio blackout likely across most of the sunlit side of Earth."
            }
        else:
            return {
                "class_label": flare_class_str,
                "r_scale": "R5",
                "severity": "Extreme",
                "description": "Complete HF radio blackout expected across the sunlit side of Earth."
            }

    return {
        "class_label": flare_class_str,
        "r_scale": "Unknown",
        "severity": "Unknown",
        "description": "Unrecognized flare classification."
    }


# ---------------------------------------------------------------------------
# Geomagnetic Storms -> G-Scale (Kp Index)
# ---------------------------------------------------------------------------

def classify_geomagnetic_storm(kp_index):
    """
    Classify a Kp index value into NOAA G-scale geomagnetic storm severity.

    Args:
        kp_index (float): planetary K-index, typically 0-9

    Returns:
        dict with keys: kp_index, g_scale, severity, description
    """
    kp = float(kp_index)

    if kp < 5:
        return {
            "kp_index": kp,
            "g_scale": "G0",
            "severity": "None",
            "description": "No geomagnetic storm — quiet to unsettled conditions."
        }
    elif kp < 6:
        return {
            "kp_index": kp,
            "g_scale": "G1",
            "severity": "Minor",
            "description": "Minor geomagnetic storm. Weak power grid fluctuations possible; aurora visible at high latitudes."
        }
    elif kp < 7:
        return {
            "kp_index": kp,
            "g_scale": "G2",
            "severity": "Moderate",
            "description": "Moderate geomagnetic storm. High-latitude power systems may see voltage alarms."
        }
    elif kp < 8:
        return {
            "kp_index": kp,
            "g_scale": "G3",
            "severity": "Strong",
            "description": "Strong geomagnetic storm. Satellite orientation issues possible; aurora visible much farther from poles."
        }
    elif kp < 9:
        return {
            "kp_index": kp,
            "g_scale": "G4",
            "severity": "Severe",
            "description": "Severe geomagnetic storm. Widespread voltage control problems possible; spacecraft systems may experience surface charging."
        }
    else:
        return {
            "kp_index": kp,
            "g_scale": "G5",
            "severity": "Extreme",
            "description": "Extreme geomagnetic storm. Grid collapse possible in some systems; satellite navigation and communication significantly disrupted."
        }


# ---------------------------------------------------------------------------
# Near-Earth Objects (NeoWs)
# ---------------------------------------------------------------------------

LUNAR_DISTANCE_KM = 384_400

def classify_close_approach(miss_distance_km, diameter_m_estimate=None):
    """
    Classify an asteroid's close-approach distance into a plain-language tier,
    using lunar distances (LD) as the practical unit, and flag potential
    hazard status using NASA's PHA size/distance criteria.

    Args:
        miss_distance_km (float): closest approach distance in kilometers
        diameter_m_estimate (float, optional): estimated asteroid diameter in meters

    Returns:
        dict with keys: distance_km, distance_ld, tier, is_pha_range, description
    """
    distance_km = float(miss_distance_km)
    distance_ld = distance_km / LUNAR_DISTANCE_KM

    # PHA distance criterion: within 0.05 AU (~19.5 LD)
    is_pha_distance = distance_ld <= 19.5
    is_pha_size = (diameter_m_estimate is not None and diameter_m_estimate >= 140)
    is_pha_range = is_pha_distance and (diameter_m_estimate is None or is_pha_size)

    if distance_ld < 1:
        tier = "Extremely close"
        description = f"Passes closer than the Moon ({distance_ld:.2f} lunar distances) — a rare, notable approach."
    elif distance_ld < 5:
        tier = "Very close"
        description = f"Passes within {distance_ld:.1f} lunar distances — a close approach worth tracking."
    elif distance_ld < 19.5:
        tier = "Notable"
        description = f"Passes within {distance_ld:.1f} lunar distances — within NASA's potentially-hazardous monitoring range."
    else:
        tier = "Routine"
        description = f"Passes at {distance_ld:.1f} lunar distances — a routine, non-concerning distance."

    return {
        "distance_km": distance_km,
        "distance_ld": round(distance_ld, 2),
        "tier": tier,
        "is_pha_range": is_pha_range,
        "description": description
    }


# ---------------------------------------------------------------------------
# Satellites (CelesTrak)
# ---------------------------------------------------------------------------

def summarize_satellite_catalog(active_sats, decayed_sats, orbit_classifier):
    """
    Summarize the active and recently decayed satellite catalogs into a
    plain-language report broken down by orbit type.

    Args:
        active_sats (list): list of satellite dicts from fetch_satellites()
        decayed_sats (list): list of satellite dicts from fetch_decayed_satellites()
        orbit_classifier (callable): function(period_minutes) -> orbit type string
            (pass nasa_api.classify_orbit_type)

    Returns:
        dict with keys:
            total_active (int)
            total_decayed (int)
            by_orbit (dict): {"LEO": int, "MEO": int, "GEO": int, "HEO": int, "Unknown": int}
            notable_decayed (list of str): names of up to 5 recently decayed objects
            summary (str): one-line plain-English description
    """
    orbit_counts = {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0, "Unknown": 0}

    for sat in active_sats:
        period      = sat.get("PERIOD")
        mean_motion = sat.get("MEAN_MOTION")
        orbit = orbit_classifier(period_minutes=period, mean_motion=mean_motion)
        orbit_counts[orbit] = orbit_counts.get(orbit, 0) + 1

    notable_decayed = [
        sat.get("OBJECT_NAME", "Unknown")
        for sat in decayed_sats[:5]
        if sat.get("OBJECT_NAME")
    ]

    orbit_parts = [
        f"{count} in {orbit}"
        for orbit, count in orbit_counts.items()
        if count > 0
    ]

    summary = (
        f"{len(active_sats):,} active satellites in orbit "
        f"({', '.join(orbit_parts)}). "
        f"{len(decayed_sats)} object(s) recently re-entered the atmosphere."
    )

    return {
        "total_active": len(active_sats),
        "total_decayed": len(decayed_sats),
        "by_orbit": orbit_counts,
        "notable_decayed": notable_decayed,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# EONET (Earth Observatory Natural Event Tracker) + FIRMS fire detections
# ---------------------------------------------------------------------------
#
# What this section is careful about, and why.
#
# EONET is a *curated catalogue of named events*, not a detection feed, and
# its shape is lopsided in ways that made the old one-line summary actively
# misleading. Measured against 1,571 open events:
#
#   - 1,532 of them come from IRWIN, the US interagency fire reporting
#     system. There is no international wildfire source in EONET at all, so
#     an EONET wildfire count is a US incident count and nothing more.
#   - IRWIN files each fire once and never updates it (one geometry point).
#     Since EONET's `days` filter matches an event's MOST RECENT observation,
#     a fire reported three weeks ago drops out of a 7-day query while it is
#     still burning.
#   - The same feed carries deliberate prescribed burns alongside genuine
#     wildfires, so counting the category wholesale overstates how much is
#     burning out of control.
#   - "Open" is not "active": one tracked iceberg started drifting 5,471 days
#     ago. Anything honest has to report *started* and *last observed*
#     separately rather than collapsing them into "active".
#
# So the real "what can be seen from space" number comes from FIRMS, which is
# an actual satellite detection feed, and EONET is used for what it is good
# at: named events with a place and a history.

RECENT_DAYS = 7            # what "reported recently" means in the rollup
MAX_CYCLONES_LISTED = 3
MAX_WILDFIRES_LISTED = 3
MAX_VOLCANOES_LISTED = 2

# EONET source ids we need to reason about by name.
IRWIN_SOURCE = "IRWIN"                      # US-only, one report per fire
CYCLONE_SOURCES = {"JTWC", "NOAA_NHC"}      # properly tracked, many fixes

# Singular / plural labels per event kind. "wildfire incident" rather than
# "wildfire" is deliberate: IRWIN files incidents, and the distinction is the
# whole point of this section.
KIND_LABELS = {
    "wildfire":         ("wildfire incident", "wildfire incidents"),
    "prescribed burn":  ("prescribed burn", "prescribed burns"),
    "tropical cyclone": ("tropical cyclone", "tropical cyclones"),
    "severe storm":     ("severe storm", "severe storms"),
    "volcano":          ("volcano", "volcanoes"),
    "iceberg":          ("iceberg", "icebergs"),
}

# Ordered lon/lat boxes as (name, west, south, east, north). First match wins,
# so more specific regions precede broader ones and all land precedes the
# ocean fallbacks. Same idea as SHELL_BANDS in starlink.py.
#
# These serve two callers at once, which is why no reverse-geocoding service
# is needed: they name the FIRMS regional breakdown, and they supply a place
# for the EONET events whose titles carry none (storms and icebergs).
#
# The Pacific is split into two boxes either side of the dateline rather than
# adding longitude-wrapping logic to the lookup.
REGION_BOXES = [
    ("Greenland",                          -73,  59,  -12,  84),
    ("Central America & the Caribbean",   -118,   7,  -58,  25),
    ("western North America",             -170,  25, -100,  72),
    ("eastern North America",             -100,  25,  -50,  72),
    ("the Amazon basin",                   -78, -15,  -44,   5),
    ("northern South America",             -82,   0,  -34,  13),
    ("southern South America",             -78, -56,  -34,   0),
    ("Europe",                             -12,  36,   40,  72),
    ("the Middle East",                     34,  12,   63,  42),
    ("north Africa & the Sahel",           -18,  10,   52,  37),
    ("central Africa",                     -18,  -6,   52,  10),
    ("southern Africa",                      8, -36,   52,  -6),
    ("Siberia & the Russian Far East",      60,  50,  180,  78),
    ("central Asia",                        45,  36,   90,  56),
    ("south Asia",                          60,   5,   92,  37),
    ("Southeast Asia",                      92, -11,  142,  29),
    ("east Asia",                          100,  20,  146,  54),
    ("Australia",                          112, -44,  154, -10),
    ("New Zealand & the southwest Pacific", 154, -50, 180, -10),
    ("the Arctic",                        -180,  66,  180,  90),
    ("the Antarctic",                     -180, -90,  180, -60),
    ("the Southern Ocean",                -180, -60,  180, -45),
    ("the North Atlantic",                 -80,   5,    0,  66),
    ("the South Atlantic",                 -70, -60,   20,   5),
    ("the Indian Ocean",                    20, -60,  100,  30),
    ("the North Pacific",                  120,   5,  180,  66),
    ("the North Pacific",                 -180,   5,  -80,  66),
    ("the South Pacific",                  120, -60,  180,   5),
    ("the South Pacific",                 -180, -60,  -70,   5),
]


def region_for_coordinates(lon, lat):
    """
    Name the region a lon/lat falls in, or None if the pair is unusable.

    Public because nasa_api.fetch_firms_fire_activity() buckets fire detections
    with it — the same boxes that place the storms and icebergs here.
    """
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    for name, west, south, east, north in REGION_BOXES:
        if west <= lon <= east and south <= lat <= north:
            return name
    return "open ocean"


def _coordinates_of(point):
    """
    Pull a (lon, lat) pair out of one EONET geometry entry.

    Point geometries are a flat [lon, lat]; Polygon and MultiPolygon nest that
    one or two levels deeper. Walking down to the first vertex is precise
    enough to name a region, and avoids a centroid calculation that would add
    nothing at this resolution. Returns None on anything unrecognised.
    """
    node = (point or {}).get("coordinates")
    for _ in range(4):
        if not isinstance(node, (list, tuple)) or not node:
            return None
        if not isinstance(node[0], (list, tuple)):
            break
        node = node[0]
    if not isinstance(node, (list, tuple)) or len(node) < 2:
        return None
    try:
        return float(node[0]), float(node[1])
    except (TypeError, ValueError):
        return None


def _age_days(iso, now):
    """Whole days between an EONET date string and `now`, or None."""
    if not iso:
        return None
    try:
        stamp = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, (now - stamp).days)


def _format_age(days):
    """A duration phrase for an age in days: '3 days', '2 months', '4.2 years'."""
    if days is None:
        return None
    if days <= 0:
        return "less than a day"
    if days == 1:
        return "1 day"
    if days < 31:
        return f"{days} days"
    if days < 365:
        months = max(1, round(days / 30.44))
        return f"{months} month{'s' if months != 1 else ''}"
    years = days / 365.25
    return f"{years:.1f} years" if years < 10 else f"{round(years)} years"


def _format_when(days):
    """A point in the past: 'today' / '3 days ago' / '2 months ago'."""
    if days is None:
        return None
    return "today" if days <= 0 else f"{_format_age(days)} ago"


def _format_utc_date(iso):
    """'2026-08-21' -> '21 Aug'. Returns None if it isn't a date we recognise."""
    try:
        return datetime.strptime(str(iso), "%Y-%m-%d").strftime("%d %b").lstrip("0")
    except (TypeError, ValueError):
        return None


def _kind_for(category, title, sources):
    """
    Map an EONET category onto the kind of thing we actually want to report.

    Keyed on EONET's own category taxonomy rather than on source ids, so a new
    source feeding an existing category needs no change here.
    """
    cat = (category or "").strip()
    if cat == "Wildfires":
        # A prescribed burn is a deliberate, planned fire. IRWIN files them in
        # the same feed as wildfires, so without this split the section would
        # report controlled forestry work as uncontrolled burning.
        return "prescribed burn" if "prescribed" in title.lower() else "wildfire"
    if cat == "Severe Storms":
        return "tropical cyclone" if sources & CYCLONE_SOURCES else "severe storm"
    if cat == "Volcanoes":
        return "volcano"
    if cat in ("Sea and Lake Ice", "Icebergs"):
        return "iceberg"
    if not cat:
        return "other"
    return cat[:-1].lower() if cat.endswith("s") else cat.lower()


def _place_for(title, sources, lon, lat):
    """
    Where the event is, in words.

    One rule with two branches, so an unfamiliar source still produces
    something sensible. Every EONET title that carries a location puts it
    after the first comma — 'Wildfire Windmill, Stillwater, Montana' or
    'Nevados del Chillan Volcano, Chile' — which covers 1,547 of 1,571 open
    events. The rest (storms, icebergs) carry no place in the title at all
    and are named from their coordinates instead.
    """
    if "," in title:
        place = title.split(",", 1)[1].strip()
        if place:
            # IRWIN reports US incidents only, so its titles stop at the
            # state and the country is safe to add.
            if IRWIN_SOURCE in sources and not place.upper().endswith("USA"):
                place += ", USA"
            return place
    return region_for_coordinates(lon, lat)


def _short_name(title):
    """
    Trim an EONET title down to the distinguishing part.

    The category is already stated by the group heading, so 'Wildfire
    Windmill, Stillwater, Montana' only needs to contribute 'Windmill'.
    """
    name = title.split(",", 1)[0].strip()
    # 'Incident Complex ' first: it is longer than 'Wildfire ' and EONET uses it
    # for merged fires, which otherwise read as 'Incident Complex ROWE CREEK
    # COMPLEX'.
    for prefix in ("Incident Complex ", "Wildfire ", "Iceberg "):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
            break
    if name.endswith(" Volcano"):
        name = name[:-len(" Volcano")].strip()
    return name or title


def _magnitude_of(point):
    """
    Format one geometry point's magnitude, or None if it has none.

    Returns the numeric value too, since wildfires and icebergs are ranked by
    it. Units come straight from EONET: acres for fires, kts for cyclones,
    NM^2 for icebergs.
    """
    value = (point or {}).get("magnitudeValue")
    if value is None:
        return None, None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None, None
    unit = ((point or {}).get("magnitudeUnit") or "").strip()
    pretty = {"kts": "kt winds", "NM^2": "NM²"}.get(unit, unit)
    shown = f"{value:,.0f}" if value >= 100 else f"{value:g}"
    return f"{shown} {pretty}".strip(), value


def describe_earth_event(event, now=None):
    """
    Reduce one raw EONET event to the fields the briefing needs.

    Returns None rather than raising, so one malformed record cannot take the
    whole section down with it.

    Returns:
        dict with keys: name, kind, place, magnitude, magnitude_value,
        started_days, last_seen_days, points
    """
    if not isinstance(event, dict):
        return None
    title = (event.get("title") or "").strip()
    if not title:
        return None

    now = now or datetime.now(timezone.utc)
    geometry = [g for g in (event.get("geometry") or []) if isinstance(g, dict)]
    first = geometry[0] if geometry else {}
    last = geometry[-1] if geometry else {}

    sources = {(s.get("id") or "").upper()
               for s in (event.get("sources") or []) if isinstance(s, dict)}
    categories = [c.get("title") or ""
                  for c in (event.get("categories") or []) if isinstance(c, dict)]

    coords = _coordinates_of(last) or _coordinates_of(first)
    lon, lat = coords if coords else (None, None)
    magnitude, magnitude_value = _magnitude_of(last)

    return {
        "name":            _short_name(title),
        "kind":            _kind_for(categories[0] if categories else "", title, sources),
        "place":           _place_for(title, sources, lon, lat),
        "magnitude":       magnitude,
        "magnitude_value": magnitude_value,
        "started_days":    _age_days(first.get("date"), now),
        "last_seen_days":  _age_days(last.get("date"), now),
        "points":          len(geometry),
    }


def _describe_timing(event):
    """
    How long it has been going, reporting *started* and *last observed*
    separately.

    A single-observation event cannot distinguish "burning for three weeks"
    from "filed once and never updated", so it says 'reported' rather than
    implying anyone has looked since.
    """
    started = _format_when(event["started_days"])
    seen = _format_when(event["last_seen_days"])
    if event["points"] <= 1:
        return f"reported {started}" if started else None
    if not started:
        return f"last seen {seen}" if seen else None
    if event["started_days"] == event["last_seen_days"]:
        return f"started {started}"
    return f"started {started}, last seen {seen}"


def _event_line(event):
    """One indented detail line: name — place · magnitude · timing."""
    text = event["name"]
    if event["place"]:
        text += f" — {event['place']}"
    trailing = [bit for bit in (event["magnitude"], _describe_timing(event)) if bit]
    return text + (" · " + " · ".join(trailing) if trailing else "")


def _plural(kind, count):
    singular, plural = KIND_LABELS.get(kind, (kind, f"{kind}s"))
    return singular if count == 1 else plural


def _listing(events, heading, limit, sort_key, lines):
    """Append a bounded group of detail lines, saying so when it truncates."""
    if not events:
        return
    ordered = sorted(events, key=sort_key)
    hidden = len(ordered) - limit
    if hidden > 0:
        heading += f" — {limit} of {len(ordered)}"
    lines.append(f"  {heading}:")
    for event in ordered[:limit]:
        lines.append(f"    {_event_line(event)}")


def summarize_earth_events(events, firms=None, now=None):
    """
    Build the EARTH EVENTS briefing section from EONET events plus, when
    available, a FIRMS satellite fire-detection count.

    Replaces the old summarize_eonet_events(), which reported raw EONET
    category counts as "12 active wildfires" — a number that actually meant
    "12 US fire incidents filed in the last week" and read as though only
    twelve fires were burning on Earth.

    The title line is unindented ALL-CAPS with a colon and every other line is
    indented, which is what the app's parser uses to split sections apart (see
    ParsedBriefing.parse). An unindented body line would be read as the start
    of a new section and would silently produce a spurious tile.

    Args:
        events (list): raw EONET event dicts, from fetch_eonet_events()
        firms (dict|None): fetch_firms_fire_activity() output, or None if the
            fire-detection feed was unavailable
        now (datetime|None): reference time, for testing

    Returns:
        str: multi-line briefing section
    """
    now = now or datetime.now(timezone.utc)
    described = [d for d in (describe_earth_event(e, now) for e in events or []) if d]

    hotspots = (firms or {}).get("total")
    fire_date = _format_utc_date((firms or {}).get("date"))
    fire_partial = bool((firms or {}).get("partial"))

    # A complete UTC day is comparable between briefings; a partial one is not,
    # so the wording changes rather than presenting them as the same thing.
    if fire_partial:
        span = f"so far on {fire_date} (UTC)" if fire_date else "so far today"
    else:
        span = f"on {fire_date} (UTC)" if fire_date else "in the last full day"

    if hotspots:
        headline = (f"{hotspots:,} active fire pixels detected worldwide {span}, "
                    f"plus {len(described)} named events tracked.")
    elif described:
        headline = f"{len(described)} named events currently being tracked."
    else:
        headline = "No named events currently being tracked, and no fire detections available."

    lines = [f"EARTH EVENTS (from orbit): {headline}"]

    # ── What satellites actually detected ─────────────────────────────────
    if hotspots:
        label = firms.get("label", "VIIRS")
        if fire_partial and fire_date:
            coverage = (f"{hotspots:,} hotspots so far on {fire_date} — a partial "
                        f"UTC day, still filling up.")
        elif fire_date:
            coverage = (f"{hotspots:,} hotspots on {fire_date}, the last complete "
                        f"UTC day.")
        else:
            coverage = f"{hotspots:,} hotspots."
        lines.append(f"  Satellite fire detection ({label}): {coverage}")
        busiest = sorted((firms.get("by_region") or {}).items(),
                         key=lambda item: -item[1])[:3]
        if busiest:
            lines.append("    Most active: "
                         + " · ".join(f"{name} {count:,}" for name, count in busiest)
                         + ".")
    else:
        lines.append("  Satellite fire detection: unavailable right now "
                     "(NASA FIRMS could not be reached).")

    if not described:
        return "\n".join(lines)

    # ── The named-event catalogue ─────────────────────────────────────────
    counts = Counter(d["kind"] for d in described)
    recent = sum(1 for d in described
                 if d["last_seen_days"] is not None
                 and d["last_seen_days"] <= RECENT_DAYS)
    rollup = ", ".join(f"{count} {_plural(kind, count)}"
                       for kind, count in counts.most_common())
    lines.append(f"  Named events open in NASA's catalogue: {rollup} "
                 f"({recent} reported in the last {RECENT_DAYS} days).")

    # Sort keys: cyclones and volcanoes by most recently observed, fires and
    # icebergs by size. None sorts last in both cases.
    by_recency = lambda d: (d["last_seen_days"] is None, d["last_seen_days"] or 0)
    by_size = lambda d: -(d["magnitude_value"] or 0)

    _listing([d for d in described if d["kind"] in ("tropical cyclone", "severe storm")],
             "Tropical cyclones (JTWC / NOAA hurricane centres — continuously tracked)",
             MAX_CYCLONES_LISTED, by_recency, lines)

    _listing([d for d in described if d["kind"] == "wildfire"],
             "Largest fire incidents (US interagency reports — this catalogue is US-only)",
             MAX_WILDFIRES_LISTED, by_size, lines)

    _listing([d for d in described if d["kind"] == "volcano"],
             "Volcanic activity", MAX_VOLCANOES_LISTED, by_recency, lines)

    bergs = [d for d in described if d["kind"] == "iceberg"]
    if bergs:
        biggest = max(bergs, key=lambda d: d["magnitude_value"] or 0)
        detail = ", ".join(bit for bit in (biggest["place"], biggest["magnitude"],
                                           _describe_timing(biggest)) if bit)
        lines.append(f"  Drifting icebergs: {len(bergs)} tracked, largest "
                     f"{biggest['name']} ({detail}).")

    # Prescribed burns stay counted in the rollup above so the categories still
    # sum to the headline total; the gloss explaining what they are rides along
    # on the closing paragraph rather than costing a line of its own.
    hint = ("  How to read this: the hotspot count is what satellites actually saw — one "
            "pixel is a 375 m patch that was burning, so a single large fire can produce "
            "hundreds of them.")
    if counts.get("prescribed burn"):
        hint += (" Prescribed burns are deliberate, planned fires — not fires burning out "
                 "of control, though EONET files both together.")
    lines.append(hint)

    lines.append("  The named-event list is NASA's hand-curated catalogue, which is a different "
                 "thing: its only wildfire source files US incidents once and never updates "
                 "them, so fires elsewhere never appear there. That is why it lists a handful "
                 "while the satellites see thousands, and why each entry says when it was last "
                 "observed rather than claiming it is still burning.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deep-Space Objects (JPL Horizons)
# ---------------------------------------------------------------------------

# Heliopause distance — boundary of interstellar space (~120 AU)
HELIOPAUSE_AU = 120.0

def summarize_deep_space_objects(objects: list) -> str:
    """
    Turn a list of deep-space object dicts (from fetch_all_deep_space_objects)
    into a plain-language summary, grouped by type and flagging interstellar objects.

    Args:
        objects (list): list of dicts with keys: name, type, range_au, range_km, note

    Returns:
        str: multi-line plain-language summary
    """
    if not objects:
        return (
            "DEEP-SPACE OBJECTS & TELESCOPES: Live position data unavailable "
            "(JPL Horizons unreachable). See static catalog in nasa_api.DEEP_SPACE_OBJECTS."
        )

    interstellar = [o for o in objects if o.get("range_au", 0) >= HELIOPAUSE_AU]
    probes       = [o for o in objects if o.get("type") == "spacecraft"
                    and o.get("range_au", 0) < HELIOPAUSE_AU]
    telescopes   = [o for o in objects if o.get("type") == "telescope"]
    debris       = [o for o in objects if o.get("type") == "rocket_body"]

    lines = [
        f"DEEP-SPACE OBJECTS & TELESCOPES: {len(objects)} tracked object(s) beyond Earth orbit."
    ]

    if interstellar:
        lines.append("  ★ INTERSTELLAR (beyond heliopause ~120 AU):")
        for o in sorted(interstellar, key=lambda x: -x["range_au"]):
            lines.append(
                f"    {o['name']} — {o['range_au']:.1f} AU from Sun "
                f"({o['range_km']/1e9:.2f} billion km)  {o.get('note','')}"
            )

    if probes:
        lines.append("  Deep-space probes (within heliosphere):")
        for o in sorted(probes, key=lambda x: -x["range_au"]):
            lines.append(
                f"    {o['name']} — {o['range_au']:.2f} AU  |  {o.get('note','')}"
            )

    if telescopes:
        lines.append("  Space telescopes:")
        for o in telescopes:
            dist = (f"{o['range_au']:.4f} AU from Sun" if o.get("range_au") else "distance N/A")
            lines.append(
                f"    {o['name']} — {dist}  |  {o.get('note','')}"
            )

    if debris:
        lines.append("  Escaped rocket bodies:")
        for o in debris:
            lines.append(
                f"    {o['name']}  |  {o.get('note','')}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lunar Debris — static inventory (no live API exists for this data)
# ---------------------------------------------------------------------------
#
# Sources: NASA mission records, ESA Space Debris Office, published research.
# Mass values are approximate; some are estimates from mission documentation.
# "Lunar debris" = human-made objects that have impacted or been left on the Moon.

# Sources: NASA NSSDCA, ESA Space Debris Office, ISRO, CNSA, JAXA mission records.
# Mass values are confirmed from mission documentation; ~estimates where noted.
# NOTE: A 2022 rocket booster impact was initially misattributed to SpaceX in media —
#       subsequent trajectory analysis identified it as China's Chang'e 5-T1 booster.
#       No SpaceX rocket has been confirmed to have impacted the Moon.

LUNAR_DEBRIS_INVENTORY = [
    # ── Intentional impactors / mission hardware ──────────────────────────
    {"name": "Luna 2 (USSR)",               "year": 1959, "mass_kg": 390,   "fate": "impact",  "note": "First human-made object to reach the Moon"},
    {"name": "Ranger 4 (NASA)",             "year": 1962, "mass_kg": 331,   "fate": "impact",  "note": "Crashed after systems failure"},
    {"name": "Ranger 6 (NASA)",             "year": 1964, "mass_kg": 364,   "fate": "impact",  "note": "Camera failed; intentional impact site"},
    {"name": "Ranger 7 (NASA)",             "year": 1964, "mass_kg": 365,   "fate": "impact",  "note": "Intentional impact after photo mission"},
    {"name": "Ranger 8 (NASA)",             "year": 1965, "mass_kg": 366,   "fate": "impact",  "note": "Intentional impact after photo mission"},
    {"name": "Ranger 9 (NASA)",             "year": 1965, "mass_kg": 367,   "fate": "impact",  "note": "Intentional impact after photo mission"},
    {"name": "Luna 5 (USSR)",               "year": 1965, "mass_kg": 1476,  "fate": "impact",  "note": "Soft-landing attempt failed"},
    {"name": "Luna 7 (USSR)",               "year": 1965, "mass_kg": 1506,  "fate": "impact",  "note": "Retrorocket failure on approach"},
    {"name": "Luna 8 (USSR)",               "year": 1965, "mass_kg": 1550,  "fate": "impact",  "note": "Airbag failure on approach"},
    {"name": "Surveyor 2 (NASA)",           "year": 1966, "mass_kg": 995,   "fate": "impact",  "note": "Thruster failure during descent"},
    {"name": "Luna 15 (USSR)",              "year": 1969, "mass_kg": 2718,  "fate": "impact",  "note": "Sample-return attempt crashed during Apollo 11"},
    {"name": "Apollo 12 S-IVB stage",       "year": 1969, "mass_kg": 13930, "fate": "impact",  "note": "Intentionally impacted for seismic data; ~13.9 t"},
    {"name": "Apollo 13 S-IVB stage",       "year": 1970, "mass_kg": 13930, "fate": "impact",  "note": "Intentionally impacted for seismic data; ~13.9 t"},
    {"name": "Apollo 14 S-IVB stage",       "year": 1971, "mass_kg": 13930, "fate": "impact",  "note": "Intentionally impacted for seismic data; ~13.9 t"},
    {"name": "Apollo 15 S-IVB stage",       "year": 1971, "mass_kg": 13930, "fate": "impact",  "note": "Intentionally impacted for seismic data; ~13.9 t"},
    {"name": "Apollo 16 S-IVB stage",       "year": 1972, "mass_kg": 13930, "fate": "impact",  "note": "Intentionally impacted for seismic data; ~13.9 t"},
    {"name": "LCROSS impactor (NASA)",      "year": 2009, "mass_kg": 2300,  "fate": "impact",  "note": "Intentional Centaur stage impact to detect water ice"},
    {"name": "GRAIL-A Ebb (NASA)",          "year": 2012, "mass_kg": 202,   "fate": "impact",  "note": "Intentional end-of-mission impact, Altai Scarp"},
    {"name": "GRAIL-B Flow (NASA)",         "year": 2012, "mass_kg": 202,   "fate": "impact",  "note": "Intentional end-of-mission impact, Altai Scarp"},
    {"name": "Chang'e 5-T1 booster (CNSA)", "year": 2022, "mass_kg": 900,   "fate": "impact",  "note": "Uncontrolled lunar impact Mar 4 2022; initially misidentified as SpaceX Falcon 9 upper stage — trajectory analysis confirmed CNSA origin"},
    {"name": "Beresheet (SpaceIL)",         "year": 2019, "mass_kg": 585,   "fate": "impact",  "note": "Engine failure on descent; crash-landed Mare Tranquillitatis"},
    {"name": "Vikram lander Chandrayaan-2", "year": 2019, "mass_kg": 1471,  "fate": "impact",  "note": "ISRO Chandrayaan-2; lost contact 2.1 km above surface; crash-landed"},
    {"name": "Luna 25 (Roscosmos)",         "year": 2023, "mass_kg": 800,   "fate": "impact",  "note": "Russia's first lunar mission since 1976; engine malfunction caused crash Aug 19 2023"},
    # ── Landers / rovers confirmed on surface ─────────────────────────────
    {"name": "Luna 9 lander (USSR)",        "year": 1966, "mass_kg": 99,    "fate": "surface", "note": "First soft landing; Oceanus Procellarum"},
    {"name": "Surveyor 1 (NASA)",           "year": 1966, "mass_kg": 270,   "fate": "surface", "note": "Still on surface, Oceanus Procellarum"},
    {"name": "Apollo 11 LM descent stage",  "year": 1969, "mass_kg": 2034,  "fate": "surface", "note": "Eagle, Sea of Tranquility; EVA equipment, flags, experiments left"},
    {"name": "Apollo 12 LM descent stage",  "year": 1969, "mass_kg": 2034,  "fate": "surface", "note": "Intrepid, Oceanus Procellarum"},
    {"name": "Apollo 14 LM descent stage",  "year": 1971, "mass_kg": 2034,  "fate": "surface", "note": "Antares, Fra Mauro"},
    {"name": "Apollo 15 LM descent stage",  "year": 1971, "mass_kg": 2034,  "fate": "surface", "note": "Falcon, Hadley Rille"},
    {"name": "Apollo 16 LM descent stage",  "year": 1972, "mass_kg": 2034,  "fate": "surface", "note": "Orion, Descartes Highlands"},
    {"name": "Apollo 17 LM descent stage",  "year": 1972, "mass_kg": 2034,  "fate": "surface", "note": "Challenger, Taurus-Littrow"},
    {"name": "Lunokhod 1 rover (USSR)",     "year": 1970, "mass_kg": 756,   "fate": "surface", "note": "First roving vehicle on another world; Sea of Rains"},
    {"name": "Lunokhod 2 rover (USSR)",     "year": 1973, "mass_kg": 836,   "fate": "surface", "note": "Mare Serenitatis; still visible via NASA LRO imagery"},
    {"name": "Chang'e 3 lander (CNSA)",     "year": 2013, "mass_kg": 1200,  "fate": "surface", "note": "Mare Imbrium; Yutu rover also on surface"},
    {"name": "Chang'e 4 lander (CNSA)",     "year": 2019, "mass_kg": 1200,  "fate": "surface", "note": "Von Kármán crater, far side; Yutu-2 rover still active as of 2024"},
    {"name": "Chang'e 5 ascent stage (CNSA)","year": 2020, "mass_kg": 300,  "fate": "impact",  "note": "Intentionally de-orbited after sample return; impacted lunar surface Dec 2020"},
    {"name": "Vikram lander Chandrayaan-3", "year": 2023, "mass_kg": 1752,  "fate": "surface", "note": "ISRO; first successful soft landing at lunar south pole, Aug 23 2023; Pragyan rover deployed"},
    {"name": "SLIM lander (JAXA)",          "year": 2024, "mass_kg": 200,   "fate": "surface", "note": "Japan's Smart Lander; precision landing Jan 19 2024; landed on its nose but solar panels generated power"},
]


def get_lunar_debris_summary() -> dict:
    """
    Summarize the known lunar debris inventory into counts, total mass,
    and a plain-language description.

    Returns:
        dict with keys:
            total_objects (int)
            total_mass_kg (float)
            impacts (int)          — objects that crashed/impacted
            on_surface (int)       — landers/rovers left on surface
            mass_impacted_kg (float)
            mass_on_surface_kg (float)
            heaviest (dict)        — single heaviest item
            most_recent (dict)     — most recent addition
            summary (str)          — one-line plain-English overview
            items (list)           — full inventory list
    """
    impacts    = [o for o in LUNAR_DEBRIS_INVENTORY if o["fate"] == "impact"]
    on_surface = [o for o in LUNAR_DEBRIS_INVENTORY if o["fate"] == "surface"]

    total_mass       = sum(o["mass_kg"] for o in LUNAR_DEBRIS_INVENTORY)
    mass_impacted    = sum(o["mass_kg"] for o in impacts)
    mass_on_surface  = sum(o["mass_kg"] for o in on_surface)

    heaviest     = max(LUNAR_DEBRIS_INVENTORY, key=lambda o: o["mass_kg"])
    most_recent  = max(LUNAR_DEBRIS_INVENTORY, key=lambda o: o["year"])

    summary = (
        f"{len(LUNAR_DEBRIS_INVENTORY)} known human-made objects on or impacted into the Moon, "
        f"totalling ~{total_mass:,.0f} kg. "
        f"{len(impacts)} impact(s) (~{mass_impacted:,.0f} kg) and "
        f"{len(on_surface)} object(s) still on the surface (~{mass_on_surface:,.0f} kg). "
        f"Most recent: {most_recent['name']} ({most_recent['year']})."
    )

    return {
        "total_objects":      len(LUNAR_DEBRIS_INVENTORY),
        "total_mass_kg":      total_mass,
        "impacts":            len(impacts),
        "on_surface":         len(on_surface),
        "mass_impacted_kg":   mass_impacted,
        "mass_on_surface_kg": mass_on_surface,
        "heaviest":           heaviest,
        "most_recent":        most_recent,
        "summary":            summary,
        "items":              LUNAR_DEBRIS_INVENTORY,
    }


# ---------------------------------------------------------------------------
# Anomaly & Alert Detection
# ---------------------------------------------------------------------------

# Re-entries in the last 30 days above which debris activity is called out.
# Kept at the value the code has always used; the docstring below previously
# said 50, which was never what ran.
REENTRY_ALERT_THRESHOLD = 100


def detect_alerts(section_map: dict) -> list:
    """
    Scan the briefing sections for conditions that cross operational thresholds
    and return a list of plain-English alert strings.

    Every check reads only the one section that owns its reading, never the
    sections joined together — see the comment in the body for the false
    alerts that scanning everything produced.

    These alerts are passed to the AI narrative so Granite focuses on what
    actually needs attention, not just routine conditions.

    Alert thresholds used:
      - Solar flare  >= X class  (R3+ / Strong or worse)
      - Geomagnetic  >= G3       (Kp >= 7 — satellite charging risk)
      - NEO          <= 5 LD     (very close approach)
      - NEO          is PHA range AND very close
      - Satellites   >= REENTRY_ALERT_THRESHOLD re-entries in last 30 days

    Args:
        section_map (dict): the same dict passed to generate_briefing() —
            keys are section names, values are pre-built text strings.

    Returns:
        list of str — one alert per triggered threshold, empty if all clear.
    """
    alerts = []

    # Each check below reads ONLY the section that owns the reading it looks
    # for. This used to scan " ".join(section_map.values()), which
    # mis-escalated on ordinary days, because mission_planner.py writes
    # multi-scale tokens into its recommendations:
    #
    #   - An R3 flare produced the text "R3/R4 flare — HF comms degraded"
    #     (mission_planner.py:44). R4 is tested before R3, so the briefing
    #     reported a SEVERE R4 flare that had not happened.
    #   - "G4/G5 storm" (:46) made every G4 read as a G5 grid-collapse alert.
    #   - A G4 storm's own "(SEVERE)" label raised a phantom solar flare
    #     alert with no flare present at all.
    #
    # Scoping is also what keeps EARTH EVENTS out of the scan. That section
    # carries third-party incident names — US counties and fire names — and
    # any one of them containing "G3" as a substring would raise a false
    # geomagnetic alert. Same class of bug as the re-entry scan below.
    flare_text = section_map.get("solar_flares", "").upper()
    storm_text = section_map.get("geomagnetic", "").upper()

    # ── Solar flare severity ───────────────────────────────────────────────
    # R3 = "Strong" or worse = X-class flare. classify_flare() emits exactly
    # one clean R0–R5 token, so scoped to its own section these are exact.
    if "R5" in flare_text or "(EXTREME)" in flare_text:
        alerts.append("EXTREME solar flare detected (R5) — complete HF blackout on sunlit hemisphere; emergency comms may be affected")
    elif "R4" in flare_text or "(SEVERE)" in flare_text:
        alerts.append("SEVERE solar flare (R4) — widespread HF radio blackout; satellite operators should check radiation dose monitors")
    elif "R3" in flare_text or "(STRONG)" in flare_text:
        alerts.append("STRONG solar flare (R3) — wide-area HF radio blackout likely; GPS accuracy may be degraded")

    # ── Geomagnetic storm severity ─────────────────────────────────────────
    if "G5" in storm_text:
        alerts.append("EXTREME geomagnetic storm (G5) — grid collapse risk; all satellites in LEO should enter safe mode")
    elif "G4" in storm_text:
        alerts.append("SEVERE geomagnetic storm (G4) — widespread voltage control issues; surface charging on spacecraft likely")
    elif "G3" in storm_text:
        alerts.append("STRONG geomagnetic storm (G3) — satellite drag increase in LEO; attitude control anomalies possible")

    # ── Near-Earth Object proximity ────────────────────────────────────────
    neo_text = section_map.get("neo", "")
    if "EXTREMELY CLOSE" in neo_text.upper():
        alerts.append("EXTREMELY CLOSE asteroid approach (< 1 lunar distance) — rare event; confirm with NASA JPL close-approach table")
    elif "VERY CLOSE" in neo_text.upper() and "POTENTIALLY-HAZARDOUS" in neo_text.upper():
        alerts.append("Very close PHA-range asteroid approach — within 5 LD and meets size criteria; elevated monitoring recommended")
    elif "VERY CLOSE" in neo_text.upper():
        alerts.append("Very close asteroid approach (1–5 lunar distances) — within enhanced monitoring range")

    # ── Satellite re-entry rate ────────────────────────────────────────────
    # Anchored to the phrasing summarize_satellite_catalog() produces, rather
    # than scanning for the first large number in the section. That scan
    # matched the *active satellite count* — the first number in the same
    # sentence — so every briefing carried a false alert claiming that all
    # ~12,000 tracked satellites had re-entered in the last 30 days. It never
    # cleared, which meant the status banner never showed ALL CLEAR, the home
    # screen widget's dot was permanently amber, and the AI narrative was
    # briefed on a debris emergency that was not happening.
    sat_text = section_map.get("satellites", "")
    reentry = re.search(
        r"([\d,]+)\s+object\(s\)\s+recently\s+re-entered", sat_text
    )
    if reentry:
        count = int(reentry.group(1).replace(",", ""))
        if count >= REENTRY_ALERT_THRESHOLD:
            alerts.append(
                f"{count} objects re-entered atmosphere in last 30 days — "
                "elevated debris activity; check collision avoidance for LEO assets"
            )

    return alerts


# ---------------------------------------------------------------------------
# Manual test block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("--- Solar Flare Tests ---")
    for flare in ["C5.0", "M2.1", "M7.4", "X1.2", "X8.7", "X22.0"]:
        result = classify_flare(flare)
        print(f"{flare}: {result['r_scale']} ({result['severity']}) — {result['description']}")

    print("\n--- Geomagnetic Storm Tests ---")
    for kp in [3, 5, 6, 7, 8, 9]:
        result = classify_geomagnetic_storm(kp)
        print(f"Kp={kp}: {result['g_scale']} ({result['severity']}) — {result['description']}")

    print("\n--- Close Approach Tests ---")
    for dist_km, size in [(300_000, 50), (1_500_000, 400), (5_000_000, 150), (50_000_000, 300)]:
        result = classify_close_approach(dist_km, size)
        print(f"{dist_km:,} km, {size}m: {result['tier']} — {result['description']}")

    print("\n--- Earth Events Test ---")
    # Shapes taken from the live EONET feed: an IRWIN fire (place in the title,
    # one report only), a JTWC cyclone (no place, many track fixes), and a
    # prescribed burn that must not be counted as a wildfire.
    sample_events = [
        {
            "title": "Wildfire Windmill, Stillwater, Montana",
            "categories": [{"title": "Wildfires"}],
            "sources": [{"id": "IRWIN"}],
            "geometry": [{"date": "2026-08-19T00:00:00Z", "type": "Point",
                          "coordinates": [-109.5, 45.4],
                          "magnitudeValue": 14200, "magnitudeUnit": "acres"}],
        },
        {
            "title": "Prescribed Fire RX Tom Green 7105, Tom Green, Texas",
            "categories": [{"title": "Wildfires"}],
            "sources": [{"id": "IRWIN"}],
            "geometry": [{"date": "2026-08-20T00:00:00Z", "type": "Point",
                          "coordinates": [-100.4, 31.4],
                          "magnitudeValue": 560, "magnitudeUnit": "acres"}],
        },
        {
            "title": "Typhoon Saudel",
            "categories": [{"title": "Severe Storms"}],
            "sources": [{"id": "JTWC"}],
            "geometry": [
                {"date": "2026-08-16T00:00:00Z", "type": "Point",
                 "coordinates": [130.0, 15.0], "magnitudeValue": 45, "magnitudeUnit": "kts"},
                {"date": "2026-08-22T00:00:00Z", "type": "Point",
                 "coordinates": [125.0, 20.0], "magnitudeValue": 105, "magnitudeUnit": "kts"},
            ],
        },
    ]
    # Pinned so the ages below stay stable as this file gets older — otherwise
    # "started 6 days ago" silently becomes "3 months ago" and the demo stops
    # demonstrating anything.
    demo_now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    print(summarize_earth_events(
        sample_events,
        firms={"total": 106921, "date": "2026-08-21", "partial": False,
               "label": "VIIRS/NOAA-20, 375 m pixels",
               "by_region": {"southern Africa": 47924,
                             "Siberia & the Russian Far East": 14595,
                             "the Amazon basin": 7900}},
        now=demo_now,
    ))

    print("\n--- Earth Events with a partial FIRMS day ---")
    # What we fall back to when only one acq_date came back, so the count is
    # the UTC day still in progress and must not be presented as a full day.
    print(summarize_earth_events(
        sample_events,
        firms={"total": 90941, "date": "2026-08-22", "partial": True,
               "label": "VIIRS/NOAA-20, 375 m pixels", "by_region": {}},
        now=demo_now,
    ).splitlines()[1])

    print("\n--- Earth Events with FIRMS unavailable ---")
    print(summarize_earth_events(sample_events, firms=None, now=demo_now))

    print("\n--- Region lookup ---")
    for lon, lat in [(-109.5, 45.4), (130.0, 20.0), (25.0, -5.0), (-45.0, 70.0), (-150.0, -30.0)]:
        print(f"  ({lon}, {lat}) -> {region_for_coordinates(lon, lat)}")

    print("\n--- Alert scoping regression ---")
    # mission_planner.py writes "R3/R4" and "G4/G5" into its section. Scanning
    # every section joined together reported R4 and G5 here; scoped, this must
    # report exactly the R3 flare and nothing else.
    print(detect_alerts({
        "solar_flares":    "  Most significant: X2.1 class flare — R3 (Strong).",
        "geomagnetic":     "  Storm starting today: peak Kp=5.0 — G1 (Minor).",
        "mission_windows": "  R3/R4 flare — HF comms degraded. G4/G5 storm — drag uncertainty.",
    }))

