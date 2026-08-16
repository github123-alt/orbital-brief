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
from translate import translate_text

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
#
# Translations are cached per-language too, since translating the full
# briefing means dozens of calls to the translation API — worth avoiding
# on every request for the same day's content.
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes
_cache = {"date": None, "text": None, "timestamp": 0.0, "translations": {}}


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
def get_briefing(force_refresh: bool = False, lang: str = "en"):
    """
    Returns today's full space operations briefing.

    Cached for CACHE_TTL_SECONDS to avoid hammering NASA/watsonx APIs.
    Pass ?force_refresh=true to bypass the cache.

    Pass ?lang=<code> (e.g. "ne", "hi", "es") to get a translated version,
    via a free translation API. Translations are cached per-language
    alongside the English source, so repeated requests in the same
    language are fast after the first one. If translation fails for any
    reason, falls back to English rather than erroring.
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
        _cache["translations"] = {}  # new English content invalidates old translations
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
