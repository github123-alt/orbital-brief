"""
main.py

FastAPI wrapper around Orbital Brief's existing Python modules.

This file does NOT reimplement any logic — it imports your existing
briefing.py and ask.py functions directly and exposes them as HTTP
endpoints, so the Flutter Android app can call them over the network
instead of needing Python installed on the phone.

Drop this file into the root of your orbital-brief repo, alongside
briefing.py, ask.py, nasa_api.py, significance.py, mission_planner.py,
spacecraft_health.py, and watsonx.py.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import os
import json
import time
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from briefing import generate_briefing
from ask import ask as ask_flight_director
from translate import translate_text
from iss_passes import fetch_iss_passes, fetch_iss_position
from nasa_api import fetch_satellites_with_status, classify_orbit_type

app = FastAPI(
    title="Orbital Brief API",
    description="AI-powered daily space operations briefing, served over HTTP.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Added after CORS so CORS stays the outermost layer (Starlette wraps
# middleware in reverse order of registration).
#
# /satellites/elements is ~1.25 MB of JSON — the single largest thing this
# API serves, by two orders of magnitude. It compresses to roughly a quarter
# of that, which is the difference between a tolerable and an unreasonable
# download on mobile data. /briefing benefits too.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ---------------------------------------------------------------------------
# Simple in-memory cache for the daily briefing.
# generate_briefing() hits 5 external APIs + an LLM call — expensive to run
# on every request. Cache it for CACHE_TTL_SECONDS so multiple app opens in
# the same window don't re-fetch everything.
#
# Translations are cached per-language too, since translating the full
# briefing means dozens of calls to the translation API — worth avoiding
# on every request for the same day's content.
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes
_cache = {"date": None, "text": None, "timestamp": 0.0, "translations": {}}

# Where the daily-archive GitHub Action commits past briefings.
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")

# ---------------------------------------------------------------------------
# Orbital element cache for /satellites/elements.
#
# Separate from _cache above because it has nothing to do with the daily
# briefing and a very different refresh rhythm: the underlying data only
# changes when the GitHub Action commits a new satellite_cache.json, which is
# every 6 hours.
#
# The TTL is not a nicety. On Render the live CelesTrak fetch always fails,
# and fetch_satellites_with_status only falls back to the cached snapshot
# after nine parallel requests have each timed out — about 8 seconds. Without
# memoisation every single request would pay that, on top of re-trimming
# 12,000 records. With it, only the first request after a deploy does.
# ---------------------------------------------------------------------------
_ELEMENTS_TTL = 60 * 60  # 1 hour
_elements_cache = {"payload": None, "timestamp": 0.0}

# The elements a position actually requires. MEAN_MOTION fixes the orbit's
# size, ECCENTRICITY and ARG_OF_PERICENTER its shape and orientation within
# its plane, INCLINATION and RA_OF_ASC_NODE the plane itself, and MEAN_ANOMALY
# where along the orbit the object is at EPOCH. Drop any one and the position
# is unknowable rather than merely imprecise, so a record missing any of them
# is skipped and counted instead of being emitted with nulls for the app to
# trip over.
_REQUIRED_ELEMENTS = (
    "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
    "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
)


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str


class BriefingResponse(BaseModel):
    date: str
    briefing: str
    cached: bool


@app.get("/")
def root():
    return {
        "service": "Orbital Brief API",
        "status": "online",
        "endpoints": [
            "/briefing", "/ask", "/history/dates",
            "/history/{date}", "/iss-passes", "/iss-position",
            "/satellites/elements",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/briefing", response_model=BriefingResponse)
def get_briefing(force_refresh: bool = False, lang: str = "en"):
    """
    Returns today's full space operations briefing.

    Cached for CACHE_TTL_SECONDS to avoid hammering NASA/watsonx APIs.
    Pass ?force_refresh=true to bypass the cache.

    Pass ?lang=<code> (e.g. "ne", "hi", "es") to get a translated version,
    via a free translation API. Translations are cached per-language
    alongside the English source. If translation fails, falls back to
    English rather than erroring.
    """
    today = date.today().isoformat()
    now = time.time()
    cache_is_fresh = (
        _cache["date"] == today
        and _cache["text"] is not None
        and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS
    )

    if not cache_is_fresh or force_refresh:
        try:
            text = generate_briefing()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to generate briefing: {e}")

        _cache["date"] = today
        _cache["text"] = text
        _cache["timestamp"] = now
        _cache["translations"] = {}
        cached_flag = False
    else:
        text = _cache["text"]
        cached_flag = True

    if lang == "en":
        return BriefingResponse(date=today, briefing=text, cached=cached_flag)

    translated = _cache["translations"].get(lang)
    if translated is None:
        translated = translate_text(text, lang)
        _cache["translations"][lang] = translated

    return BriefingResponse(date=today, briefing=translated, cached=cached_flag)


@app.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest, lang: str = "en"):
    """
    Ask a plain-English question about current space conditions.
    Always fetches fresh live data (not cached) since answers depend on
    the exact question asked.

    Pass ?lang=<code> to get the answer translated. Not cached (each
    question is different), so translation happens fresh every time.
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        answer = ask_flight_director(req.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to answer question: {e}")

    if lang != "en":
        answer = translate_text(answer, lang)

    return AskResponse(question=req.question, answer=answer)


@app.get("/history/dates")
def get_history_dates():
    """
    Lists the dates for which an archived briefing exists (newest first).
    These are committed to the repo daily by a scheduled GitHub Action —
    see .github/workflows/archive-daily-briefing.yml.
    """
    if not os.path.isdir(HISTORY_DIR):
        return {"dates": []}

    dates = [
        f[:-5]  # strip ".json"
        for f in os.listdir(HISTORY_DIR)
        if f.endswith(".json")
    ]
    dates.sort(reverse=True)
    return {"dates": dates}


@app.get("/history/{date_str}", response_model=BriefingResponse)
def get_history_briefing(date_str: str):
    """
    Returns the archived briefing for a specific past date (YYYY-MM-DD).
    Read directly from the committed history/<date>.json file — no live
    API calls, since past conditions are exactly what was archived.
    """
    path = os.path.join(HISTORY_DIR, f"{date_str}.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"No archived briefing for {date_str}")

    with open(path, "r") as f:
        data = json.load(f)

    return BriefingResponse(date=data["date"], briefing=data["briefing"], cached=True)


@app.get("/iss-passes")
def get_iss_passes(lat: float, lon: float):
    """
    Returns upcoming visually-observable ISS passes for the given
    location. Live request to N2YO on every call (can't be pre-cached
    like the satellite catalog, since it depends on the requester's
    real-time position).
    """
    return fetch_iss_passes(lat, lon)


def _epoch_to_unix(epoch_str):
    """
    CelesTrak's EPOCH is an ISO timestamp with no zone suffix — e.g.
    "2026-08-22T04:22:11.123456" — and it is always UTC.

    fromisoformat() returns a *naive* datetime for that, and calling
    .timestamp() on a naive datetime makes Python interpret it in the
    server's local timezone. On Render that happens to be UTC so the bug
    would be invisible there, while a developer in UTC+5:45 would see every
    satellite displaced by nearly three degrees of arc. Hence the explicit
    replace(): converted once here so the app never has to parse 12,000
    timestamps or know about this.

    Returns None if the string is malformed, so the caller can skip the
    record rather than serving a broken one.
    """
    try:
        return (
            datetime.fromisoformat(epoch_str)
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except (TypeError, ValueError):
        return None


def _trim_element_set(sat):
    """
    Reduce one CelesTrak OMM record to just what a propagator needs.

    Short keys and 6-decimal rounding are purely about size: multiplied by
    12,000 records, full OMM field names alone cost more than the numbers
    they label. Returns None if any required element is absent or unparseable.
    """
    if any(sat.get(k) is None for k in _REQUIRED_ELEMENTS):
        return None

    epoch = _epoch_to_unix(sat.get("EPOCH"))
    if epoch is None:
        return None

    try:
        mean_motion = float(sat["MEAN_MOTION"])
        if mean_motion <= 0:
            return None
        return {
            "id": int(sat.get("NORAD_CAT_ID") or 0),
            "name": (sat.get("OBJECT_NAME") or "Unknown").strip(),
            "grp": sat.get("_group") or "",
            # Classified server-side with the same function the SATELLITES
            # and SPACECRAFT HEALTH sections use, so the app can colour by
            # orbit regime without a second, drifting set of thresholds.
            "cls": classify_orbit_type(mean_motion=mean_motion),
            "ep": round(epoch, 1),
            "mm": round(mean_motion, 8),
            "ecc": round(float(sat["ECCENTRICITY"]), 8),
            "inc": round(float(sat["INCLINATION"]), 6),
            "raan": round(float(sat["RA_OF_ASC_NODE"]), 6),
            "argp": round(float(sat["ARG_OF_PERICENTER"]), 6),
            "ma": round(float(sat["MEAN_ANOMALY"]), 6),
        }
    except (TypeError, ValueError):
        return None


@app.get("/satellites/elements")
def get_satellite_elements(group: str | None = None):
    """
    Orbital element sets for the tracked catalog, for the app's 3D globe.

    This serves data the repo has always had but never exposed. The 6-hourly
    GitHub Action fetches CelesTrak in OMM format and commits it whole, so
    satellite_cache.json already holds the complete element set for ~12,000
    objects; the briefing sections only ever read three of those fields.

    Positions are deliberately NOT computed here. The app propagates on
    device, which keeps the globe moving in real time without a request per
    frame, works with no network once the elements are cached, and means this
    endpoint stays a cheap static read instead of a per-viewer computation.

    Pass ?group=<celestrak group> (e.g. "starlink", "stations") to filter.
    That's a convenience for other callers — the app downloads everything
    once and filters on device so its chips respond instantly.

    Returns:
        cached_at: when the snapshot was taken, or null if served live
        source:    "live" | "cached"
        count:     element sets returned
        skipped:   records dropped for incomplete elements (expected: 0)
    """
    now = time.time()
    cached = _elements_cache["payload"]
    if cached is None or (now - _elements_cache["timestamp"]) >= _ELEMENTS_TTL:
        satellites, status, cached_at = fetch_satellites_with_status(group="active")

        if status == "unavailable":
            raise HTTPException(
                status_code=503,
                detail="Satellite catalog unavailable — CelesTrak could not be "
                       "reached and no cached snapshot exists yet.",
            )

        trimmed = []
        skipped = 0
        for sat in satellites:
            element_set = _trim_element_set(sat)
            if element_set is None:
                skipped += 1
            else:
                trimmed.append(element_set)

        if skipped:
            print(f"[main] /satellites/elements skipped {skipped} of "
                  f"{len(satellites)} records for incomplete elements",
                  flush=True)

        cached = {
            "cached_at": cached_at,
            "source": status,
            "count": len(trimmed),
            "skipped": skipped,
            "satellites": trimmed,
        }
        _elements_cache["payload"] = cached
        _elements_cache["timestamp"] = now

    if group:
        wanted = group.lower()
        subset = [s for s in cached["satellites"] if s["grp"] == wanted]
        return {**cached, "count": len(subset), "satellites": subset}

    return cached


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


@app.get("/iss-position")
def get_iss_position(lat: float, lon: float):
    """
    Where the ISS is right now, plus whether it's above the caller's
    horizon and in sunlight. Shown when there are no visible passes — the
    forecast only reaches 10 days ahead, so a quiet window would otherwise
    leave the screen with nothing on it.
    """
    return fetch_iss_position(lat, lon)
