"""
archive_daily_briefing.py

Runs on GitHub Actions (not Render) once a day, generates the day's
briefing, and saves it to history/<date>.json in the repo. Committed by
the workflow, so Render picks it up on its next auto-deploy and can serve
past days' briefings from these static files — reliable in a way that
storing history directly on Render isn't, since Render's disk isn't
guaranteed to survive restarts.

If too many upstream sections are unavailable (e.g. a NASA outage), the
script exits WITHOUT writing a file, so a degraded briefing is never archived
as if it were a complete one. It exits with code 0 in that case so the
workflow doesn't fail; the next scheduled run simply tries again.

Run manually to test:
    python archive_daily_briefing.py
"""

import json
import os
import sys
from datetime import date

from briefing import generate_briefing, UNAVAILABLE_SUFFIX

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")

# Skip archiving when this many sections (or more) failed. Out of 10 sections,
# 3 means a real outage rather than one flaky endpoint.
MAX_UNAVAILABLE_SECTIONS = 3


def main():
    today = date.today().isoformat()

    print(f"Generating briefing for {today}...")
    text = generate_briefing()

    unavailable = text.count(UNAVAILABLE_SUFFIX)
    if unavailable >= MAX_UNAVAILABLE_SECTIONS:
        print(f"{unavailable} sections unavailable; skipping archive so an "
              "incomplete briefing isn't saved as a complete one.")
        sys.exit(0)

    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": today, "briefing": text}, f, ensure_ascii=False)

    print(f"Archived to {path} ({len(text)} chars).")


if __name__ == "__main__":
    main()
