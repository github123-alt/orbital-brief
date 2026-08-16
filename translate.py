"""
translate.py

Translates the app's live briefing/Q&A text into other languages using
MyMemory's free translation API (https://mymemory.translated.net) — no
signup, no API key, no payment required.

Trade-offs, being upfront about them:
- Translation quality is not as good as paid services (Google/DeepL).
- MyMemory has a daily usage cap for anonymous requests (~5,000 words/day
  shared across all users of this server's IP). If it's exceeded, this
  falls back to returning the original English text rather than erroring.
- Translating a long briefing means many small API calls (one per line),
  done in parallel — this adds real latency (several seconds to ~20s)
  compared to the English-only response.
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MAX_CHUNK_CHARS = 450  # stay comfortably under MyMemory's per-request limit


def _translate_chunk(text: str, target_lang: str, timeout: int = 8) -> str:
    """Translate one small chunk of text. Falls back to the original text
    on any failure (rate limit, network error, unsupported language)."""
    if not text.strip():
        return text
    try:
        resp = requests.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": f"en|{target_lang}"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            print(f"[translate] MyMemory returned HTTP {resp.status_code}: "
                  f"{resp.text[:200]}", flush=True)
            return text
        data = resp.json()
        translated = data.get("responseData", {}).get("translatedText")
        status = data.get("responseStatus")
        if translated and status == 200:
            return translated
        print(f"[translate] MyMemory responseStatus={status}, "
              f"details={data.get('responseDetails')}", flush=True)
    except Exception as e:
        print(f"[translate] MyMemory request failed: "
              f"{type(e).__name__}: {e}", flush=True)
    return text


def translate_text(text: str, target_lang: str) -> str:
    """
    Translates a block of text line-by-line (preserving structure), with
    lines translated in parallel for speed. Any line that's too long for
    a single request gets chunked further.

    If target_lang is "en" or empty, returns the text unchanged — no
    network calls made.
    """
    if not target_lang or target_lang == "en":
        return text

    lines = text.split("\n")
    translated_lines = [None] * len(lines)

    def worker(i: int, line: str):
        if not line.strip():
            return i, line
        if len(line) <= MAX_CHUNK_CHARS:
            return i, _translate_chunk(line, target_lang)
        chunks = [line[j:j + MAX_CHUNK_CHARS] for j in range(0, len(line), MAX_CHUNK_CHARS)]
        return i, "".join(_translate_chunk(c, target_lang) for c in chunks)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i, line) for i, line in enumerate(lines)]
        for future in as_completed(futures):
            i, translated = future.result()
            translated_lines[i] = translated

    return "\n".join(translated_lines)
