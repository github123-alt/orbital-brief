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
