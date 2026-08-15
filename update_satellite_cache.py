"""
update_satellite_cache.py

Fetches the current CelesTrak satellite catalog and writes it to
satellite_cache.json. Meant to run on GitHub Actions' own servers — NOT on
Render — since CelesTrak blocks Render's network at the connection level
but does not block GitHub's runners.

The GitHub Action (.github/workflows/update-satellite-cache.yml) runs this
on a schedule and commits the updated file back to the repo. Render then
picks up the new file automatically on its next auto-deploy (triggered by
that commit), and nasa_api.py reads it as a fallback whenever a live
CelesTrak request fails.

Run manually to test:
    python update_satellite_cache.py
"""

import json
import sys
from datetime import datetime, timezone

from nasa_api import fetch_satellites, fetch_decayed_satellites, SATELLITE_CACHE_PATH


def main():
    print("Fetching active satellites from CelesTrak...")
    active = fetch_satellites(group="active")
    print(f"  Got {len(active)} active satellites.")

    print("Fetching recently decayed satellites...")
    decayed = fetch_decayed_satellites()
    print(f"  Got {len(decayed)} decayed satellites.")

    if not active:
        print("ERROR: Got 0 active satellites — CelesTrak likely blocked "
              "this runner too, or the API changed. Not overwriting the "
              "existing cache with empty data.")
        sys.exit(1)

    cache = {
        "active": active,
        "decayed": decayed,
        "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    with open(SATELLITE_CACHE_PATH, "w") as f:
        json.dump(cache, f)

    print(f"Wrote cache to {SATELLITE_CACHE_PATH} "
          f"({len(active)} active, {len(decayed)} decayed).")


if __name__ == "__main__":
    main()
