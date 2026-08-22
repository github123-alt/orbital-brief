"""
significance.py

Interprets raw space data (solar flare class, Kp index, asteroid close-approach
distance, EONET event counts) into plain-language significance assessments,
grounded in real NOAA/NASA operational thresholds.
"""

import re


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
# EONET (Earth Observatory Natural Event Tracker)
# ---------------------------------------------------------------------------

def summarize_eonet_events(events_by_category):
    """
    Summarize EONET open events by category into a plain-language line.

    Args:
        events_by_category (dict): e.g. {"Wildfires": 12, "Severe Storms": 3, "Volcanoes": 2}

    Returns:
        str: plain-language summary sentence
    """
    if not events_by_category:
        return "No significant Earth events currently being tracked."

    parts = [f"{count} active {category.lower()}" for category, count in events_by_category.items() if count > 0]
    if not parts:
        return "No significant Earth events currently being tracked."

    return "Currently tracking: " + ", ".join(parts) + "."


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
    Scan all briefing sections for conditions that cross operational thresholds
    and return a list of plain-English alert strings.

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
    text = " ".join(section_map.values()).upper()

    # ── Solar flare severity ───────────────────────────────────────────────
    # R3 = "Strong" or worse = X-class flare
    if "R5" in text or "(EXTREME)" in text:
        alerts.append("EXTREME solar flare detected (R5) — complete HF blackout on sunlit hemisphere; emergency comms may be affected")
    elif "R4" in text or "(SEVERE)" in text:
        alerts.append("SEVERE solar flare (R4) — widespread HF radio blackout; satellite operators should check radiation dose monitors")
    elif "R3" in text or "(STRONG)" in text:
        alerts.append("STRONG solar flare (R3) — wide-area HF radio blackout likely; GPS accuracy may be degraded")

    # ── Geomagnetic storm severity ─────────────────────────────────────────
    if "G5" in text:
        alerts.append("EXTREME geomagnetic storm (G5) — grid collapse risk; all satellites in LEO should enter safe mode")
    elif "G4" in text:
        alerts.append("SEVERE geomagnetic storm (G4) — widespread voltage control issues; surface charging on spacecraft likely")
    elif "G3" in text:
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

    print("\n--- EONET Summary Test ---")
    print(summarize_eonet_events({"Wildfires": 14, "Severe Storms": 2, "Volcanoes": 0}))
