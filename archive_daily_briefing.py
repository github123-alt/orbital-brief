"""
archive_daily_briefing.py

Runs on GitHub Actions (not Render) once a day, generates the day's
briefing, and saves it to history/<date>.json in the repo. Committed by
the workflow, so Render picks it up on its next auto-deploy and can serve
past days' briefings from these static files — reliable in a way that
storing history directly on Render isn't, since Render's disk isn't
guaranteed to survive restarts.

Run manually to test:
    python archive_daily_briefing.py
"""

import json
import os
from datetime import date

from briefing import generate_briefing

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")


def main():
    today = date.today().isoformat()
    os.makedirs(HISTORY_DIR, exist_ok=True)

    print(f"Generating briefing for {today}...")
    text = generate_briefing()

    path = os.path.join(HISTORY_DIR, f"{today}.json")
    with open(path, "w") as f:
        json.dump({"date": today, "briefing": text}, f)

    print(f"Archived to {path} ({len(text)} chars).")


if __name__ == "__main__":
    main()
