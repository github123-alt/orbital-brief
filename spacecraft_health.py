"""
spacecraft_health.py

Predictive spacecraft risk scoring.

Given current space weather conditions, computes a risk score (0–100) and
health assessment for spacecraft in different orbit regimes (LEO, MEO, GEO, HEO).

Risk dimensions assessed:
  - Radiation dose rate     (solar flare + geomagnetic storm)
  - Surface charging        (geomagnetic storm severity)
  - Atmospheric drag        (geomagnetic storm — heats upper atmosphere)
  - Single-event upsets     (solar energetic particles from flares)
  - Communication integrity (radio blackout from flares)

Thresholds are derived from NASA/ESA spacecraft environmental specifications
and NOAA Space Weather Scales operational guidance.

No API key required.
"""

from significance import classify_flare, classify_geomagnetic_storm


# ---------------------------------------------------------------------------
# Risk weight matrices per orbit regime
# ---------------------------------------------------------------------------
# Each row is a risk dimension with weights (0-1) per orbit type.
# LEO is most affected by drag and radiation; GEO by charging; MEO by radiation belts.

RISK_WEIGHTS = {
    #                           LEO   MEO   GEO   HEO
    "radiation_dose":    dict(LEO=0.9, MEO=1.0, GEO=0.6, HEO=0.7),
    "surface_charging":  dict(LEO=0.3, MEO=0.7, GEO=1.0, HEO=0.8),
    "atmospheric_drag":  dict(LEO=1.0, MEO=0.1, GEO=0.0, HEO=0.2),
    "single_event_upset":dict(LEO=0.7, MEO=1.0, GEO=0.8, HEO=0.8),
    "comms_integrity":   dict(LEO=0.8, MEO=0.6, GEO=0.9, HEO=0.7),
}

# Base severity scores per NOAA scale (0–20 per dimension, max 100 total)
FLARE_BASE_SCORES = {
    "None":    0,
    "Minor":   3,
    "Moderate":8,
    "Strong":  14,
    "Severe":  18,
    "Extreme": 20,
    "Unknown": 0,
}

STORM_BASE_SCORES = {
    "None":    0,
    "Minor":   2,
    "Moderate":6,
    "Strong":  12,
    "Severe":  17,
    "Extreme": 20,
    "Unknown": 0,
}

RISK_LABELS = [
    (0,  19,  "NOMINAL",  "All systems nominal. No space weather concerns."),
    (20, 39,  "LOW",      "Minor space weather activity. Standard monitoring."),
    (40, 59,  "MODERATE", "Elevated conditions. Increase telemetry monitoring frequency."),
    (60, 79,  "HIGH",     "Significant risk. Consider protective mode for sensitive instruments."),
    (80, 94,  "SEVERE",   "High risk. Recommend safe mode for non-critical systems."),
    (95, 100, "CRITICAL", "Extreme conditions. Initiate emergency safe mode procedures."),
]


def score_spacecraft(flare_class_str: str, kp_index: float) -> dict:
    """
    Compute risk scores for spacecraft in each orbit regime.

    Args:
        flare_class_str (str): worst flare class in last 7 days, e.g. "X1.2"
        kp_index (float): peak Kp index in last 7 days

    Returns:
        dict mapping orbit type -> {
            "score": int (0-100),
            "label": str,
            "description": str,
            "dimension_scores": dict
        }
    """
    flare = classify_flare(flare_class_str)
    storm = classify_geomagnetic_storm(kp_index)

    flare_base = FLARE_BASE_SCORES.get(flare["severity"], 0)
    storm_base = STORM_BASE_SCORES.get(storm["severity"], 0)

    # Per-dimension raw scores (0-20 each)
    raw = {
        "radiation_dose":     max(flare_base, storm_base * 0.6),
        "surface_charging":   storm_base,
        "atmospheric_drag":   storm_base,
        "single_event_upset": flare_base,
        "comms_integrity":    flare_base,
    }

    results = {}
    for orbit in ["LEO", "MEO", "GEO", "HEO"]:
        weighted_sum = sum(
            raw[dim] * RISK_WEIGHTS[dim][orbit]
            for dim in raw
        )
        # Max possible weighted sum = 20 * sum(weights for this orbit)
        max_possible = sum(20 * RISK_WEIGHTS[dim][orbit] for dim in raw)
        score = round((weighted_sum / max_possible) * 100) if max_possible > 0 else 0
        score = min(100, score)

        label, description = "NOMINAL", "All systems nominal."
        for lo, hi, lbl, desc in RISK_LABELS:
            if lo <= score <= hi:
                label, description = lbl, desc
                break

        dim_scores = {
            dim: round(raw[dim] * RISK_WEIGHTS[dim][orbit])
            for dim in raw
        }

        results[orbit] = {
            "score":            score,
            "label":            label,
            "description":      description,
            "dimension_scores": dim_scores,
        }

    return results


def format_spacecraft_health(scores: dict) -> str:
    """
    Format spacecraft risk scores into a briefing section string.

    Args:
        scores (dict): output of score_spacecraft()

    Returns:
        str: multi-line formatted section
    """
    icons = {
        "NOMINAL":  "🟢",
        "LOW":      "🟡",
        "MODERATE": "🟠",
        "HIGH":     "🔴",
        "SEVERE":   "🔴",
        "CRITICAL": "⛔",
    }
    lines = ["SPACECRAFT HEALTH FORECAST (risk by orbit regime, 0–100):"]
    for orbit, data in scores.items():
        icon = icons.get(data["label"], "⚪")
        lines.append(
            f"  {icon} {orbit}: {data['score']:>3}/100 — {data['label']}  |  {data['description']}"
        )
        worst_dim = max(data["dimension_scores"], key=lambda d: data["dimension_scores"][d])
        if data["score"] >= 20:
            lines.append(
                f"       Primary risk: {worst_dim.replace('_', ' ').title()} "
                f"(score: {data['dimension_scores'][worst_dim]})"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== SPACECRAFT HEALTH DEMO — Moderate activity ===")
    scores = score_spacecraft("X1.2", 6.7)
    print(format_spacecraft_health(scores))

    print("\n=== QUIET DAY ===")
    scores = score_spacecraft("C2.0", 2.1)
    print(format_spacecraft_health(scores))

    print("\n=== EXTREME EVENT ===")
    scores = score_spacecraft("X22.0", 9.0)
    print(format_spacecraft_health(scores))
