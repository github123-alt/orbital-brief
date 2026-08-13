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

Then test:
    curl http://localhost:8000/briefing
    curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Is it safe to do a spacewalk today?"}'
"""

import os
import time
from datetime import date, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from briefing import generate_briefing
from ask import ask as ask_flight_director

app = FastAPI(
    title="Orbital Brief API",
    description="AI-powered daily space operations briefing, served over HTTP.",
    version="1.0.0",
)

# Allow the Flutter app (and local dev/testing) to call this API.
# Tighten allow_origins once you know your app's actual origin / are ready to lock it down.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Simple in-memory cache for the daily briefing.
# generate_briefing() hits 5 external APIs + an LLM call — expensive to run
# on every request. Cache it for CACHE_TTL_SECONDS so multiple app opens in
# the same window don't re-fetch everything.
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes
_cache = {"date": None, "text": None, "timestamp": 0.0}


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
        "endpoints": ["/briefing", "/ask"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/briefing", response_model=BriefingResponse)
def get_briefing(force_refresh: bool = False):
    """
    Returns today's full space operations briefing.

    Cached for CACHE_TTL_SECONDS to avoid hammering NASA/watsonx APIs.
    Pass ?force_refresh=true to bypass the cache.
    """
    today = date.today().isoformat()
    now = time.time()
    cache_is_fresh = (
        _cache["date"] == today
        and _cache["text"] is not None
        and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS
    )

    if cache_is_fresh and not force_refresh:
        return BriefingResponse(date=today, briefing=_cache["text"], cached=True)

    try:
        text = generate_briefing()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to generate briefing: {e}")

    _cache["date"] = today
    _cache["text"] = text
    _cache["timestamp"] = now

    return BriefingResponse(date=today, briefing=text, cached=False)


@app.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest):
    """
    Ask a plain-English question about current space conditions.
    Always fetches fresh live data (not cached) since answers depend on
    the exact question asked.
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        answer = ask_flight_director(req.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to answer question: {e}")

    return AskResponse(question=req.question, answer=answer)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
