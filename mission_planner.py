"""
mission_planner.py

AI-powered mission window advisor.

Given the current space weather and NEO conditions, determines whether today
is a SAFE / CAUTION / HOLD window for common space operations, with specific
reasoning grounded in NOAA/NASA operational thresholds.

Operations assessed:
  - EVA (spacewalk)
  - Satellite launch
  - Orbital maneuver (thruster firing, orbit raise/lower)
  - Deep-space communication uplink
  - Sensitive instrument calibration

No API key required — uses the section data already fetched by briefing.py.
"""

from significance import classify_flare, classify_geomagnetic_storm


# ---------------------------------------------------------------------------
# Threshold rules per operation type
# ---------------------------------------------------------------------------

# Maps operation name -> list of (condition_key, bad_values, window, reason)
# window: "HOLD" = do not proceed | "CAUTION" = proceed with care
OPERATION_RULES = {
    "EVA (Spacewalk)": [
        ("flare_severity",   {"Strong", "Severe", "Extreme"}, "HOLD",
         "X-class flare — elevated radiation dose risk for crew outside ISS/station"),
        ("flare_severity",   {"Moderate"},                    "CAUTION",
         "M5+ flare — increased particle flux; limit EVA duration"),
        ("storm_severity",   {"Severe", "Extreme"},           "HOLD",
         "G4/G5 storm — severe charged-particle environment; EVA abort criteria met"),
        ("storm_severity",   {"Strong"},                      "CAUTION",
         "G3 storm — elevated energetic particle flux; monitor dosimeter closely"),
    ],
    "Satellite Launch": [
        ("flare_severity",   {"Extreme"},                     "HOLD",
         "R5 flare — GPS/navigation blackout on sunlit side; launch guidance at risk"),
        ("flare_severity",   {"Strong", "Severe"},            "CAUTION",
         "R3/R4 flare — HF comms degraded; backup telemetry recommended"),
        ("storm_severity",   {"Severe", "Extreme"},           "HOLD",
         "G4/G5 storm — upper atmosphere expansion increases drag uncertainty"),
        ("storm_severity",   {"Strong"},                      "CAUTION",
         "G3 storm — LEO drag models less reliable; monitor TLE updates"),
        ("neo_tier",         {"Extremely close"},              "CAUTION",
         "Sub-lunar asteroid approach — confirm trajectory does not intersect launch corridor"),
    ],
    "Orbital Maneuver": [
        ("storm_severity",   {"Severe", "Extreme"},           "HOLD",
         "G4/G5 storm — atmospheric density in LEO significantly elevated; Δv budget unreliable"),
        ("storm_severity",   {"Strong"},                      "CAUTION",
         "G3 storm — drag uncertainty elevated; add margin to maneuver planning"),
        ("flare_severity",   {"Extreme"},                     "CAUTION",
         "R5 flare — ionospheric disturbance may affect GPS-based navigation"),
    ],
    "Deep-Space Uplink": [
        ("flare_severity",   {"Strong", "Severe", "Extreme"}, "HOLD",
         "R3+ flare — HF/S-band radio blackout on sunlit hemisphere; DSN contact window lost"),
        ("flare_severity",   {"Moderate"},                    "CAUTION",
         "R2 flare — possible signal degradation on sunlit-side ground stations"),
        ("storm_severity",   {"Severe", "Extreme"},           "CAUTION",
         "G4/G5 storm — ionospheric scintillation may affect uplink signal quality"),
    ],
    "Instrument Calibration": [
        ("flare_severity",   {"Strong", "Severe", "Extreme"}, "HOLD",
         "X-class flare — elevated particle flux contaminates calibration baseline"),
        ("storm_severity",   {"Strong", "Severe", "Extreme"}, "CAUTION",
         "G3+ storm — magnetospheric disturbance affects sensor reference fields"),
    ],
}


def assess_mission_windows(flare_class_str: str, kp_index: float,
                            neo_tier: str = "Routine") -> dict:
    """
    Assess mission windows for all operation types given current conditions.

    Args:
        flare_class_str (str): worst flare class in last 7 days, e.g. "X1.2"
        kp_index (float): peak Kp index in last 7 days
        neo_tier (str): closest NEO tier string from classify_close_approach()

    Returns:
        dict mapping operation name -> {"window": "GO"|"CAUTION"|"HOLD", "reasons": [str]}
    """
    flare = classify_flare(flare_class_str)
    storm = classify_geomagnetic_storm(kp_index)
    flare_sev = flare["severity"]
    storm_sev = storm["severity"]

    conditions = {
        "flare_severity": flare_sev,
        "storm_severity": storm_sev,
        "neo_tier": neo_tier,
    }

    results = {}
    for operation, rules in OPERATION_RULES.items():
        window = "GO"
        reasons = []
        for condition_key, bad_values, rule_window, reason in rules:
            if conditions.get(condition_key) in bad_values:
                reasons.append(reason)
                # HOLD overrides CAUTION
                if rule_window == "HOLD" or window == "GO":
                    window = rule_window
                elif rule_window == "CAUTION" and window != "HOLD":
                    window = "CAUTION"
        results[operation] = {"window": window, "reasons": reasons}

    return results


def format_mission_windows(windows: dict) -> str:
    """
    Format mission window assessments into a briefing section string.

    Args:
        windows (dict): output of assess_mission_windows()

    Returns:
        str: multi-line formatted section
    """
    icons = {"GO": "✅", "CAUTION": "⚠️ ", "HOLD": "🛑"}
    lines = ["MISSION WINDOW ASSESSMENT (today's operational recommendations):"]
    for operation, result in windows.items():
        icon = icons[result["window"]]
        lines.append(f"  {icon} {operation}: {result['window']}")
        for reason in result["reasons"]:
            lines.append(f"       → {reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo with a moderately active space weather day
    print("=== MISSION WINDOW DEMO ===")
    windows = assess_mission_windows(
        flare_class_str="X1.2",
        kp_index=6.7,
        neo_tier="Very close",
    )
    print(format_mission_windows(windows))

    print("\n=== QUIET DAY ===")
    windows = assess_mission_windows(
        flare_class_str="C2.0",
        kp_index=2.1,
        neo_tier="Routine",
    )
    print(format_mission_windows(windows))

    print("\n=== EXTREME EVENT ===")
    windows = assess_mission_windows(
        flare_class_str="X22.0",
        kp_index=9.0,
        neo_tier="Extremely close",
    )
    print(format_mission_windows(windows))
