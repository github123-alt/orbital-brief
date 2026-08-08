# 🛰️ Orbital Brief

**A daily space operations briefing — powered by live NASA, JPL, and CelesTrak data.**

Orbital Brief pulls real-time data from five official space-agency APIs and translates
it into a plain-language, operationally meaningful daily report — topped with an
AI-generated narrative from IBM watsonx.ai (Granite). Think of it as a mission-control
morning brief that is always current, no matter when you run it.

> **Run this today, run it in 50 years — it will always show the data for that day.**
> Voyager 1 will show its actual distance in 2075. The asteroid list will be that
> week's real approaches. The satellite count will reflect whatever is in orbit then.
> See [What updates automatically](#what-updates-automatically-forever) for the full breakdown.

---

## What it covers

| Section | Data Source | Live? | What it tells you |
|---|---|---|---|
| **AI Narrative** | IBM watsonx.ai (Granite) | ✅ Live | Plain-English summary of the day's space conditions, generated fresh each run |
| **Solar Flares** | NASA DONKI | ✅ Live | Last 7 days of flares, classified by NOAA R-scale (radio blackout impact) |
| **Geomagnetic Storms** | NASA DONKI | ✅ Live | Last 7 days of storms, classified by NOAA G-scale (Kp index) |
| **Near-Earth Objects** | NASA NeoWs | ✅ Live | Next 7 days of asteroid close approaches, flagged by lunar distance & PHA criteria |
| **Earth Events (from orbit)** | NASA EONET | ✅ Live | Currently open natural events (wildfires, storms, volcanoes) tracked from orbit |
| **Satellites** | CelesTrak | ✅ Live | Active satellite count by orbit type (LEO/MEO/GEO/HEO) + recently re-entered objects |
| **Deep-Space Objects & Telescopes** | JPL Horizons | ✅ Live | Real-time heliocentric distances for Voyager 1 & 2, New Horizons, Hubble, Webb, and more |
| **Lunar Debris Inventory** | NASA/ESA mission records | 📋 Static | All 38 confirmed human-made objects on or impacted into the Moon, with mass and fate |

All space-weather thresholds are grounded in **real NOAA/NASA operational standards** —
not arbitrary cutoffs.

---

## Sample output

```
=== DAILY SPACE OPERATIONS BRIEFING — 2025-08-08 ===

AI SUMMARY (IBM Granite): Today's space environment is moderately active. A strong
X1.2-class solar flare caused wide-area HF radio blackouts on the sunlit side of Earth,
and a follow-on G2 geomagnetic storm may affect high-latitude power systems and satellite
attitude control. Eighteen near-Earth objects are tracked this week; asteroid 2025 NA3
passes at 3.4 lunar distances with no impact risk. Voyager 1 continues its journey
through interstellar space at 171.4 AU — over 25 billion kilometres from our Sun.

--- DETAILED DATA ---

SOLAR FLARES: 5 flare(s) recorded in the past 7 days.
  Most significant: X1.2 class flare on 2025-08-06T08:14Z — R3 (Strong).

GEOMAGNETIC ACTIVITY: 2 storm(s) recorded in the past 7 days.
  Storm starting 2025-08-07T02:00Z: peak Kp=6.7 — G2 (Moderate).

NEAR-EARTH OBJECTS: 18 object(s) tracked with close approaches in the coming week.
  Closest approach: (2025 NA3) — Very close. Passes within 3.4 lunar distances.

EARTH EVENTS (from orbit): Currently tracking: 14 active wildfires, 3 active severe storms.

SATELLITES: 1,656 active satellites in orbit (1,609 in LEO, 14 in MEO, 24 in GEO, 9 in HEO).
  275 object(s) recently re-entered the atmosphere.
  Recently re-entered: STARLINK-37886, STARLINK-37937, STARLINK-37903

DEEP-SPACE OBJECTS & TELESCOPES: 11 tracked object(s) beyond Earth orbit.
  ★ INTERSTELLAR (beyond heliopause ~120 AU):
    Voyager 1  — 171.4 AU from Sun (25.64 billion km)  Farthest human-made object ever; still transmitting
    Voyager 2  — 143.6 AU from Sun (21.48 billion km)  In interstellar space since Nov 2018; still transmitting
    Pioneer 10 — 141.6 AU from Sun (21.18 billion km)  Last contact Jan 2003
  Deep-space probes (within heliosphere):
    Pioneer 11   — 117.60 AU  |  Heading toward constellation Aquila; last contact Nov 1995
    New Horizons —  65.29 AU  |  In the Kuiper Belt; flew past Pluto 2015 & Arrokoth 2019
    Ulysses      —   1.45 AU  |  ESA/NASA solar orbiter; retired Jun 2009
  Space telescopes:
    Hubble Space Telescope      — 1.0141 AU  |  LEO ~547 km; launched 1990; still operational
    James Webb Space Telescope  — 1.0229 AU  |  At L2 ~1.5M km from Earth; launched Dec 2021
    Spitzer Space Telescope     — 1.0028 AU  |  Retired Jan 2020; Earth-trailing heliocentric orbit
    Kepler / K2                 — 1.0249 AU  |  Retired Oct 2018; discovered 2,600+ exoplanets
  Escaped rocket bodies:
    Chang'e 5-T1 booster  |  Impacted Moon Mar 2022 — no longer in space

LUNAR DEBRIS INVENTORY: 38 known human-made objects on or impacted into the Moon,
  totalling ~105,355 kg (~105 metric tonnes).
  24 impact(s) (~86,838 kg) | 14 objects still on surface (~18,517 kg)
  Heaviest: Apollo S-IVB stages (~13,930 kg each — 5 intentionally impacted for seismic data)
  Most recent: SLIM lander (JAXA, Jan 2024)
  NOTE: The Mar 2022 lunar impact was initially misreported as SpaceX Falcon 9 —
        confirmed as China's Chang'e 5-T1 booster. No SpaceX rocket has hit the Moon.
```

See [`sample_output.txt`](sample_output.txt) for the complete untruncated example.

---

## What updates automatically (forever)

Every time you run `python briefing.py`, these sections fetch **fresh data for that exact day**
from live APIs. Run it today, run it in 10 or 50 years — the output will always reflect
current reality:

| Section | What will be different in 50 years |
|---|---|
| Solar Flares | That week's actual flares |
| Geomagnetic Storms | That week's actual Kp readings |
| Near-Earth Objects | Asteroids approaching Earth that week |
| Earth Events | Currently burning wildfires, active storms |
| Satellites | However many satellites are in orbit in 2075 |
| Voyager 1 distance | ~240 AU by 2075 — the actual position that day |
| Webb / Hubble / future telescopes | Live positions from JPL Horizons |
| AI Narrative | IBM Granite will summarise that day's actual conditions |

## What requires occasional manual updates

| Section | Why it's static | How to update |
|---|---|---|
| **Lunar Debris Inventory** | No live API exists anywhere for lunar surface objects | Add new missions to `LUNAR_DEBRIS_INVENTORY` in [`significance.py`](significance.py) when they land or crash |
| **Deep-space object list** | JPL Horizons gives live positions, but you must tell it *which* objects to track | Add new spacecraft IDs to `DEEP_SPACE_OBJECTS` in [`nasa_api.py`](nasa_api.py) as new probes launch |
| **Telescope status notes** | Descriptive text is written at code time | Update when missions end or new observatories launch |

---

## Requirements

- Python 3.9+
- A free NASA API key — get one at **https://api.nasa.gov/**
- An IBM watsonx.ai account — get free access at **https://dataplatform.cloud.ibm.com/**
- CelesTrak and JPL Horizons require **no API key**

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/orbital-brief.git
cd orbital-brief
```

### 2. Install dependencies

```bash
pip install -e .
```

Or without packaging:

```bash
pip install requests ibm-watsonx-ai
```

### 3. Set your environment variables

```bash
# Required: NASA data
export NASA_API_KEY="your_nasa_key_here"

# Required for AI narrative: IBM watsonx.ai
export WATSONX_API_KEY="your_ibm_cloud_api_key"
export WATSONX_PROJECT_ID="your_watsonx_project_id"
export WATSONX_URL="https://us-south.ml.cloud.ibm.com"   # adjust region if needed
```

To make these permanent, add the lines above to your `~/.bashrc` or `~/.zshrc`.

> **Note:** If `WATSONX_API_KEY` or `WATSONX_PROJECT_ID` are not set, the briefing will
> still run — the AI summary line will display a configuration reminder instead.
> CelesTrak and JPL Horizons work with no credentials at all.

---

## Usage

```bash
python briefing.py
```

That's it. The briefing prints to stdout, so you can pipe it anywhere:

```bash
# Save today's briefing
python briefing.py > briefing_$(date +%F).txt

# Email it (with mailutils installed)
python briefing.py | mail -s "Daily Space Brief" you@example.com

# Schedule it daily at 7 AM with cron
0 7 * * * cd /path/to/orbital-brief && python briefing.py >> ~/space_log.txt
```

---

## Project structure

```
orbital-brief/
├── briefing.py        # Entry point — assembles and prints the full daily briefing
├── nasa_api.py        # All API clients: DONKI, NeoWs, EONET, CelesTrak, JPL Horizons
├── significance.py    # Classifiers + static inventories (R/G-scale, PHA, lunar debris)
├── watsonx.py         # IBM watsonx.ai Granite integration (AI narrative summary)
├── sample_output.txt  # Example briefing output (no API key needed to view)
└── pyproject.toml     # Package metadata and dependencies
```

---

## How the classification works

### Solar Flares → NOAA R-Scale

| Flare class | R-Scale | Severity |
|---|---|---|
| A, B, C | R0 | None |
| M1–M4 | R1 | Minor |
| M5–M9 | R2 | Moderate |
| X1–X9 | R3 | Strong |
| X10–X19 | R4 | Severe |
| X20+ | R5 | Extreme |

### Geomagnetic Storms → NOAA G-Scale

| Kp Index | G-Scale | Severity |
|---|---|---|
| < 5 | G0 | None |
| 5–5.9 | G1 | Minor |
| 6–6.9 | G2 | Moderate |
| 7–7.9 | G3 | Strong |
| 8–8.9 | G4 | Severe |
| 9+ | G5 | Extreme |

### Near-Earth Objects → Lunar Distance Tiers

| Distance | Tier |
|---|---|
| < 1 LD | Extremely close |
| 1–5 LD | Very close |
| 5–19.5 LD | Notable (PHA monitoring range) |
| > 19.5 LD | Routine |

> **PHA flag**: objects within 19.5 lunar distances (0.05 AU) AND ≥ 140 m diameter
> meet NASA's Potentially Hazardous Asteroid criteria.

### Deep-Space Objects → Interstellar threshold

Objects at or beyond **120 AU** from the Sun have crossed the heliopause — the boundary
where the Sun's solar wind gives way to interstellar space. As of 2025, three human-made
objects have crossed it: Voyager 1 (2012), Voyager 2 (2018), and Pioneer 10.

---

## Data sources

| Source | Used for | API key needed |
|---|---|---|
| [NASA DONKI](https://kauai.ccmc.gsfc.nasa.gov/DONKI/) | Solar flares, geomagnetic storms | Yes (free) |
| [NASA NeoWs](https://api.nasa.gov/) | Near-Earth object tracking | Yes (free) |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Earth natural events from orbit | No |
| [CelesTrak](https://celestrak.org/) | Active satellite catalog + re-entries | No |
| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | Deep-space & telescope positions | No |
| [IBM watsonx.ai](https://dataplatform.cloud.ibm.com/) | AI narrative (Granite model) | Yes (free tier) |
| NASA/ESA mission records | Lunar debris inventory (static) | N/A |

---

## Lunar debris — key facts

- **38** confirmed human-made objects on or having impacted the Moon
- **~105 metric tonnes** total mass
- **~87 tonnes** from impacts (dominated by 5 Apollo S-IVB rocket stages at ~14 t each)
- **~18.5 tonnes** still sitting on the surface (Apollo landers, Soviet rovers, recent landers)
- **Most recent:** SLIM lander (JAXA), January 19, 2024
- **Most distant past:** Luna 2 (USSR), September 14, 1959 — first human object to reach the Moon
- The widely-cited "SpaceX Falcon 9 Moon crash" was a **misidentification** — the Mar 2022
  impactor was China's Chang'e 5-T1 booster, confirmed by trajectory analysis.

---

## License

MIT
