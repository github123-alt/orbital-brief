"""
ask.py

"Ask the Flight Director" — natural language Q&A interface.

Lets anyone ask plain-English questions about the current space environment
and get precise, data-grounded answers from IBM watsonx.ai Granite.

Examples:
    python ask.py "Is it safe to do a spacewalk today?"
    python ask.py "What's Voyager 1 doing right now?"
    python ask.py "Are there any dangerous asteroids this week?"
    python ask.py "Why is the aurora visible tonight?"
    python ask.py "How much human trash is on the Moon?"

The system builds a current briefing snapshot as context, then sends both
the snapshot and the user's question to Granite for a grounded answer.
This prevents hallucination — the AI can only answer from real data fetched
seconds ago.

Requires: NASA_API_KEY, WATSONX_API_KEY, WATSONX_PROJECT_ID
"""

import sys
import os
import requests

WATSONX_API_KEY    = os.environ.get("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID")
WATSONX_URL        = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
MODEL_ID           = "ibm/granite-3-8b-instruct"


def _get_iam_token() -> str:
    resp = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
              "apikey": WATSONX_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _build_context_snapshot() -> str:
    """
    Fetch a lightweight snapshot of current conditions from all data sources.
    Used as grounding context for the Q&A — Granite answers from this, not from
    its training data, which prevents outdated or fabricated responses.
    """
    lines = ["=== CURRENT SPACE CONDITIONS SNAPSHOT ==="]

    # NASA DONKI — solar flares
    try:
        from nasa_api import fetch_solar_flares, fetch_geomagnetic_storms, fetch_near_earth_objects
        from nasa_api import fetch_satellites, fetch_decayed_satellites, fetch_all_deep_space_objects
        from significance import (classify_flare, classify_geomagnetic_storm,
                                   classify_close_approach, get_lunar_debris_summary,
                                   summarize_satellite_catalog, classify_orbit_type)

        flares = fetch_solar_flares(days_back=7)
        if flares:
            worst = max(flares, key=lambda f: (
                {"A":0,"B":0,"C":0,"M":1,"X":2}.get(
                    f.get("classType","C")[0].upper(), 0),
                float(f.get("classType","C0")[1:] or 0)
            ))
            r = classify_flare(worst.get("classType","C0"))
            lines.append(f"Solar Flares: {len(flares)} in last 7 days. "
                         f"Worst: {worst.get('classType')} ({r['severity']}, {r['r_scale']}) "
                         f"on {worst.get('beginTime','unknown')}")
        else:
            lines.append("Solar Flares: None in last 7 days.")

        storms = fetch_geomagnetic_storms(days_back=7)
        if storms:
            max_kp = 0
            for s in storms:
                for e in s.get("allKpIndex", []):
                    max_kp = max(max_kp, e.get("kpIndex", 0))
            r = classify_geomagnetic_storm(max_kp)
            lines.append(f"Geomagnetic: {len(storms)} storm(s). Peak Kp={max_kp} "
                         f"({r['severity']}, {r['g_scale']})")
        else:
            lines.append("Geomagnetic: No storms in last 7 days.")

        neos = fetch_near_earth_objects(days_forward=7)
        lines.append(f"Near-Earth Objects: {len(neos)} tracked this week.")
        if neos:
            closest_km = min(
                float(n["close_approach_data"][0]["miss_distance"]["kilometers"])
                for n in neos if n.get("close_approach_data")
            )
            r = classify_close_approach(closest_km)
            lines.append(f"  Closest: {r['distance_ld']:.1f} lunar distances ({r['tier']})")

        active = fetch_satellites(group="active")
        decayed = fetch_decayed_satellites()
        cat = summarize_satellite_catalog(active, decayed, classify_orbit_type)
        lines.append(f"Satellites: {cat['total_active']:,} active in orbit. "
                     f"{cat['total_decayed']} re-entered recently.")

        deep = fetch_all_deep_space_objects()
        for obj in deep:
            if obj["name"] == "Voyager 1":
                lines.append(f"Voyager 1: {obj['range_au']:.1f} AU from Sun "
                             f"({obj['range_km']/1e9:.2f} billion km) — in interstellar space")
            if obj["name"] == "James Webb Space Telescope":
                lines.append(f"James Webb Telescope: {obj['range_au']:.4f} AU from Sun (at L2)")

        lunar = get_lunar_debris_summary()
        lines.append(f"Lunar Debris: {lunar['total_objects']} confirmed objects, "
                     f"~{lunar['total_mass_kg']:,.0f} kg total. "
                     f"Most recent: {lunar['most_recent']['name']} ({lunar['most_recent']['year']}).")

    except Exception as e:
        lines.append(f"[Some data unavailable: {e}]")

    return "\n".join(lines)


def ask(question: str) -> str:
    """
    Answer a plain-English question about current space conditions.

    Args:
        question (str): the user's question

    Returns:
        str: grounded answer from IBM Granite, or error message
    """
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return (
            "Cannot answer: WATSONX_API_KEY and WATSONX_PROJECT_ID must be set.\n"
            "Get free access at https://dataplatform.cloud.ibm.com/"
        )

    print("Fetching current space data...", flush=True)
    context = _build_context_snapshot()

    prompt = (
        "You are a space operations expert with access to real-time space data. "
        "Answer the user's question using ONLY the data snapshot below. "
        "If the data doesn't contain enough information to answer, say so clearly. "
        "Do not guess or use information from outside the snapshot. "
        "Keep your answer concise (2-4 sentences) and factual.\n\n"
        f"CURRENT DATA SNAPSHOT:\n{context}\n\n"
        f"USER QUESTION: {question}\n\n"
        "ANSWER:"
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
            "max_new_tokens": 200,
            "min_new_tokens": 20,
            "stop_sequences": ["\n\n"],
            "repetition_penalty": 1.05,
        },
        "project_id": WATSONX_PROJECT_ID,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    answer = resp.json()["results"][0]["generated_text"].strip()
    return f"Flight Director (IBM Granite): {answer}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ask.py \"your question here\"")
        print()
        print("Examples:")
        print('  python ask.py "Is it safe to do a spacewalk today?"')
        print('  python ask.py "What is Voyager 1 doing right now?"')
        print('  python ask.py "Are there any dangerous asteroids this week?"')
        print('  python ask.py "How much human trash is on the Moon?"')
        sys.exit(0)

    question = " ".join(sys.argv[1:])
    print(f"\nQuestion: {question}")
    print()
    print(ask(question))
