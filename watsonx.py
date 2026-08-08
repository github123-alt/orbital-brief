"""
watsonx.py

Generates a plain-English AI narrative summary of the daily space briefing
using IBM watsonx.ai with the Granite language model.

Required environment variables:
    WATSONX_API_KEY   — IBM Cloud API key
    WATSONX_PROJECT_ID — watsonx.ai project ID
    WATSONX_URL       — watsonx.ai endpoint URL
                        e.g. https://us-south.ml.cloud.ibm.com

Get access at https://dataplatform.cloud.ibm.com/
"""

import os
import requests

WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID")
WATSONX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

# Granite model — granite-3-8b-instruct is faster and better at instruction-following
MODEL_ID = "ibm/granite-3-8b-instruct"


def _get_iam_token():
    """
    Exchange an IBM Cloud API key for a short-lived IAM bearer token.
    """
    resp = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": WATSONX_API_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def generate_narrative(briefing_sections: dict, active_alerts: list = None) -> str:
    """
    Send the assembled briefing data to IBM watsonx.ai Granite and receive
    an actionable mission-controller-style narrative with specific operational
    recommendations based on severity thresholds.

    Args:
        briefing_sections (dict): keys are section names, values are the
            plain-text content strings produced by briefing.py.
        active_alerts (list): optional list of alert strings from the anomaly
            detector — used to focus the AI on what actually needs attention.

    Returns:
        str: AI-generated narrative with recommendations, or a fallback message
             if watsonx credentials are not configured.
    """
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return (
            "AI SUMMARY: (Configure WATSONX_API_KEY and WATSONX_PROJECT_ID "
            "environment variables to enable AI narrative.)"
        )

    sections_text = "\n".join(briefing_sections.values())
    alerts_text = ""
    if active_alerts:
        alerts_text = (
            "\n\nACTIVE THRESHOLD ALERTS (conditions requiring immediate attention):\n"
            + "\n".join(f"  ⚠ {a}" for a in active_alerts)
        )

    prompt = (
        "You are a senior space operations flight director issuing a daily briefing "
        "to satellite operators, mission planners, and space weather engineers.\n\n"
        "Your briefing must:\n"
        "1. Open with a one-sentence overall threat level (LOW / MODERATE / ELEVATED / HIGH / CRITICAL)\n"
        "2. Call out any conditions that cross operational thresholds and state the specific risk "
        "(e.g. HF radio blackout, satellite charging, GPS degradation, aurora visibility)\n"
        "3. Highlight the most noteworthy space exploration milestone or object position today\n"
        "4. Close with 1-2 concrete recommended actions for operators\n\n"
        "Be precise, factual, and operator-focused. No speculation. 4-6 sentences total.\n\n"
        f"SENSOR DATA:\n{sections_text}"
        f"{alerts_text}\n\n"
        "FLIGHT DIRECTOR BRIEFING:"
    )

    token = _get_iam_token()

    url = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model_id": MODEL_ID,
        "input": prompt,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 300,
            "min_new_tokens": 80,
            "stop_sequences": ["\n\n\n"],
            "repetition_penalty": 1.1,
        },
        "project_id": WATSONX_PROJECT_ID,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    generated = result["results"][0]["generated_text"].strip()
    return f"AI FLIGHT DIRECTOR BRIEFING (IBM Granite):\n{generated}"


if __name__ == "__main__":
    # Quick smoke-test with dummy data (no real API call shape check)
    sample = {
        "solar_flares": "SOLAR FLARES: 3 flare(s) recorded. Most significant: X1.2 — R3 (Strong).",
        "geomagnetic": "GEOMAGNETIC ACTIVITY: 1 storm. Peak Kp=6.7 — G2 (Moderate).",
        "neo": "NEAR-EARTH OBJECTS: 18 objects. Closest: 3.4 lunar distances.",
        "earth_events": "EARTH EVENTS (from orbit): 14 wildfires, 3 severe storms, 1 volcano.",
    }
    print(generate_narrative(sample))
