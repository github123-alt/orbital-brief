"""
starlink.py

Summarises the SpaceX Starlink constellation.

Deliberately performs NO network I/O. Starlink is already one of the groups
in nasa_api.CELESTRAK_GROUPS, so its satellites are present in whatever
catalog the SATELLITES section already fetched — tagged with
_group == "starlink" by nasa_api._fetch_group. Reusing that list matters for
a reason beyond tidiness: Render cannot open a TCP connection to
celestrak.org at all (see fetch_satellites_with_status), so production runs
entirely off the snapshot committed by the update-satellite-cache Action. A
new CelesTrak endpoint added here would work locally and silently return
nothing once deployed.

On "active" vs "inactive":
    Neither CelesTrak's element sets nor any other free public feed reports
    whether an individual Starlink is operationally healthy — only SpaceX
    knows that, and they do not publish it per-satellite. What orbital
    elements *do* reveal is where each satellite is, which is a genuinely
    useful proxy: satellites on station sit in the published shells,
    newly-launched ones climb from a much lower insertion orbit, and
    satellites being retired are deliberately lowered until drag finishes
    the job. This module reports that altitude split and says plainly that
    it is inferred. It does not claim to know operational status.
"""

import math

EARTH_RADIUS_KM = 6378.137
MU_KM3_S2 = 398600.4418  # Earth's standard gravitational parameter

# Starlink's published operational shells sit between roughly 525 and 570 km.
# Satellites at or above this floor are on station.
OPERATIONAL_FLOOR_KM = 500.0

# Below the operational floor a satellite is either climbing to its shell
# after launch or being walked down for disposal. Between these two values
# it is plausibly either, so they are reported as one honest bucket rather
# than guessed apart.
TRANSIT_FLOOR_KM = 400.0

# Altitude bands used for the shell breakdown, as (label, low, high).
SHELL_BANDS = [
    ("~340 km (very low orbit)", 300.0, 400.0),
    ("~440 km", 400.0, 500.0),
    ("~530 km", 500.0, 545.0),
    ("~560 km", 545.0, 600.0),
    ("above 600 km", 600.0, 100000.0),
]


def _mean_altitude_km(sat: dict) -> float | None:
    """
    Derive mean altitude from mean motion via Kepler's third law.

    CelesTrak's JSON element sets carry MEAN_MOTION (revolutions per day)
    but not APOGEE/PERIGEE — those only appear in the SATCAT format. Since
    a = (mu / n^2)^(1/3), mean motion is enough, and for Starlink's
    near-circular orbits mean altitude is within a couple of km of both
    apogee and perigee anyway.

    Returns None rather than raising if the field is missing or unusable, so
    one malformed catalog entry cannot take down the whole section.
    """
    try:
        n_rev_per_day = float(sat.get("MEAN_MOTION"))
    except (TypeError, ValueError):
        return None
    if n_rev_per_day <= 0:
        return None

    n_rad_per_sec = n_rev_per_day * 2.0 * math.pi / 86400.0
    semi_major_km = (MU_KM3_S2 / (n_rad_per_sec ** 2)) ** (1.0 / 3.0)
    return semi_major_km - EARTH_RADIUS_KM


def _inclination(sat: dict) -> float | None:
    try:
        return float(sat.get("INCLINATION"))
    except (TypeError, ValueError):
        return None


def is_starlink(sat: dict) -> bool:
    """
    True if this catalog entry is a Starlink satellite.

    Prefers the _group tag that nasa_api attaches, and falls back to the
    object name so this also works on the decayed list, which comes from the
    "last-30-days" group and is therefore tagged with that instead.
    """
    if sat.get("_group") == "starlink":
        return True
    name = sat.get("OBJECT_NAME") or ""
    return name.upper().startswith("STARLINK")


def assess_starlink_fleet(satellites: list, decayed: list | None = None) -> dict:
    """
    Build a summary of the Starlink constellation.

    Args:
        satellites: the full catalog already fetched for the SATELLITES
            section. Starlink entries are selected from it; the total is
            kept so the constellation's share of the catalog can be shown.
        decayed: optional list of recently re-entered objects.

    Returns:
        dict with keys: tracked, on_station, in_transit, low_orbit,
        unknown_altitude, by_shell, by_inclination, share_of_catalog,
        catalog_total, reentered_recently, reentered_names
    """
    fleet = [s for s in satellites if is_starlink(s)]

    on_station = 0
    in_transit = 0
    low_orbit = 0
    unknown_altitude = 0
    by_shell = {label: 0 for label, _, _ in SHELL_BANDS}
    inclination_counts: dict[float, int] = {}

    for sat in fleet:
        altitude = _mean_altitude_km(sat)
        if altitude is None:
            unknown_altitude += 1
            continue

        if altitude >= OPERATIONAL_FLOOR_KM:
            on_station += 1
        elif altitude >= TRANSIT_FLOOR_KM:
            in_transit += 1
        else:
            low_orbit += 1

        for label, low, high in SHELL_BANDS:
            if low <= altitude < high:
                by_shell[label] += 1
                break

        inclination = _inclination(sat)
        if inclination is not None:
            # Starlink flies a handful of discrete inclinations (53.0, 53.2,
            # 70.0, 97.6 and so on). Rounding to one decimal collapses
            # per-satellite variation without merging distinct shells.
            key = round(inclination, 1)
            inclination_counts[key] = inclination_counts.get(key, 0) + 1

    reentered = [s for s in (decayed or []) if is_starlink(s)]

    return {
        "tracked": len(fleet),
        "on_station": on_station,
        "in_transit": in_transit,
        "low_orbit": low_orbit,
        "unknown_altitude": unknown_altitude,
        "by_shell": {k: v for k, v in by_shell.items() if v > 0},
        "by_inclination": dict(
            sorted(inclination_counts.items(), key=lambda kv: kv[1], reverse=True)
        ),
        "catalog_total": len(satellites),
        "share_of_catalog": (
            round(100.0 * len(fleet) / len(satellites)) if satellites else 0
        ),
        "reentered_recently": len(reentered),
        "reentered_names": [
            (s.get("OBJECT_NAME") or "unnamed") for s in reentered[:4]
        ],
    }


def format_starlink_fleet(assessment: dict) -> str:
    """
    Render the assessment as a briefing section.

    The title line is unindented ALL-CAPS with a colon and every other line
    is indented, which is what the app's parser uses to split sections apart
    (see ParsedBriefing.parse). An unindented body line would be read as the
    start of a new section and would silently produce a spurious tile.
    """
    if assessment["tracked"] == 0:
        return (
            "STARLINK CONSTELLATION: No Starlink satellites found in the "
            "current catalog snapshot — the SATELLITES section will say "
            "whether the catalog itself is unavailable."
        )

    tracked = assessment["tracked"]
    lines = [
        f"STARLINK CONSTELLATION: {tracked:,} SpaceX satellites currently "
        f"tracked in orbit — {assessment['on_station']:,} on station at "
        f"operational altitude, {assessment['in_transit']:,} in transit, "
        f"{assessment['low_orbit']:,} in low orbit."
    ]

    if assessment["by_shell"]:
        shells = ", ".join(
            f"{count:,} at {label}"
            for label, count in assessment["by_shell"].items()
        )
        lines.append(f"  Altitude distribution: {shells}")

    if assessment["by_inclination"]:
        # Four covers Starlink's real shells with room to spare; more than
        # that is noise from odd single satellites.
        top = list(assessment["by_inclination"].items())[:4]
        incs = ", ".join(f"{count:,} at {inc}°" for inc, count in top)
        lines.append(f"  Orbital planes by inclination: {incs}")

    lines.append(
        f"  Share of all satellites tracked in this briefing: "
        f"{assessment['share_of_catalog']}% "
        f"({tracked:,} of {assessment['catalog_total']:,})"
    )

    if assessment["reentered_recently"]:
        names = ", ".join(assessment["reentered_names"])
        more = (
            f", and {assessment['reentered_recently'] - len(assessment['reentered_names'])} more"
            if assessment["reentered_recently"] > len(assessment["reentered_names"])
            else ""
        )
        lines.append(
            f"  Re-entered in the last 30 days: "
            f"{assessment['reentered_recently']} ({names}{more})"
        )
    else:
        lines.append("  Re-entered in the last 30 days: none recorded")

    if assessment["unknown_altitude"]:
        lines.append(
            f"  Altitude could not be derived for "
            f"{assessment['unknown_altitude']} object(s)"
        )

    lines.append(
        "  How to read this: SpaceX does not publish the health of individual "
        "satellites, so this is orbital position, not reported status. On "
        "station means sitting in one of the published operational shells "
        "above 500 km. In transit means between 400 and 500 km — either "
        "climbing to a shell after launch or being lowered for disposal, "
        "which look alike from orbital elements alone. Low orbit means below "
        "400 km, where atmospheric drag brings a satellite down within "
        "months."
    )

    return "\n".join(lines)
