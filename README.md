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
| **Anomaly Alerts** | Derived from live data | ✅ Live | Threshold-crossing conditions flagged instantly (R3+, G3+, PHA approach, debris surge) |
| **AI Flight Director** | IBM watsonx.ai (Granite) | ✅ Live | Operator-focused narrative with threat level, specific risks, and recommended actions |
| **Solar Flares** | NASA DONKI | ✅ Live | Last 7 days of flares, classified by NOAA R-scale (radio blackout impact) |
| **Geomagnetic Storms** | NASA DONKI | ✅ Live | Last 7 days of storms, classified by NOAA G-scale (Kp index) |
| **Near-Earth Objects** | NASA NeoWs | ✅ Live | Next 7 days of asteroid close approaches, flagged by lunar distance & PHA criteria |
| **Earth Events (from orbit)** | NASA EONET | ✅ Live | Currently open natural events (wildfires, storms, volcanoes) tracked from orbit |
| **Satellites** | CelesTrak | ✅ Live | Active satellite count by orbit type (LEO/MEO/GEO/HEO) + recently re-entered objects |
| **Spacecraft Health Forecast** | Derived from live data | ✅ Live | Predictive risk score (0–100) per orbit regime: LEO, MEO, GEO, HEO |
| **Mission Window Assessment** | Derived from live data | ✅ Live | GO / CAUTION / HOLD for EVA, launch, orbital maneuver, deep-space uplink, calibration |
| **Deep-Space Objects & Telescopes** | JPL Horizons | ✅ Live | Real-time heliocentric distances for Voyager 1 & 2, New Horizons, Hubble, Webb, and more |
| **Lunar Debris Inventory** | NASA/ESA mission records | 📋 Static | All 38 confirmed human-made objects on or impacted into the Moon, with mass and fate |

All space-weather thresholds are grounded in **real NOAA/NASA operational standards** —
not arbitrary cutoffs.

---

## Sample output

```
=== DAILY SPACE OPERATIONS BRIEFING — 2025-08-08 ===

⚠  OPERATIONAL ALERTS (2 active) ⚠
  • STRONG solar flare (R3) — wide-area HF radio blackout likely; GPS accuracy may be degraded
  • Very close PHA-range asteroid approach — within 5 LD and meets size criteria; elevated monitoring recommended

AI FLIGHT DIRECTOR BRIEFING (IBM Granite):
THREAT LEVEL: ELEVATED. An X1.2-class solar flare (R3/Strong) produced a wide-area HF
radio blackout and GPS degradation; switch ground stations to backup channels. A G2
geomagnetic storm (Kp=6.7) is ongoing — monitor high-latitude power systems and satellite
attitude control. Asteroid 2025 NA3 passes at 3.4 LD; no impact risk but trajectory
confirmation advised. RECOMMENDED ACTIONS: (1) Delay EVA until flare activity subsides.
(2) Verify collision avoidance buffers for LEO assets.

--- DETAILED DATA ---

SOLAR FLARES: 5 flare(s) recorded in the past 7 days.
  Most significant: X1.2 class flare on 2025-08-06T08:14Z — R3 (Strong).

GEOMAGNETIC ACTIVITY: 2 storm(s) recorded in the past 7 days.
  Storm starting 2025-08-07T02:00Z: peak Kp=6.7 — G2 (Moderate).

NEAR-EARTH OBJECTS: 18 object(s) tracked with close approaches in the coming week.
  Closest approach: (2025 NA3) — Very close (within PHA monitoring range). 3.4 lunar distances.

EARTH EVENTS (from orbit): Currently tracking: 14 active wildfires, 3 active severe storms.

SATELLITES: 1,656 active satellites (1,609 LEO, 14 MEO, 24 GEO, 9 HEO). 275 re-entered recently.
  Recently re-entered: STARLINK-37886, STARLINK-37937, STARLINK-37903

SPACECRAFT HEALTH FORECAST (risk by orbit regime, 0–100):
  🟠 LEO:  56/100 — MODERATE  |  Increase telemetry monitoring frequency.
       Primary risk: Radiation Dose
  🔴 MEO:  61/100 — HIGH      |  Consider protective mode for sensitive instruments.
       Primary risk: Radiation Dose
  🟠 GEO:  58/100 — MODERATE  |  Increase telemetry monitoring frequency.
       Primary risk: Comms Integrity
  🟠 HEO:  57/100 — MODERATE  |  Increase telemetry monitoring frequency.
       Primary risk: Single Event Upset

MISSION WINDOW ASSESSMENT (today's operational recommendations):
  🛑 EVA (Spacewalk): HOLD
       → X-class flare — elevated radiation dose risk for crew outside ISS
  ⚠️  Satellite Launch: CAUTION
       → R3/R4 flare — HF comms degraded; use backup telemetry
  ✅ Orbital Maneuver: GO
  🛑 Deep-Space Uplink: HOLD
       → R3+ flare — HF/S-band blackout on sunlit hemisphere; DSN window lost
  🛑 Instrument Calibration: HOLD
       → X-class flare — elevated particle flux contaminates calibration baseline

DEEP-SPACE OBJECTS & TELESCOPES: 11 tracked object(s) beyond Earth orbit.
  ★ INTERSTELLAR:
    Voyager 1  — 171.4 AU (25.64 billion km) — farthest human-made object; still transmitting
    Voyager 2  — 143.6 AU (21.48 billion km) — in interstellar space since Nov 2018
    Pioneer 10 — 141.6 AU (21.18 billion km) — last contact Jan 2003
  Deep-space probes: Pioneer 11 (117.6 AU), New Horizons (65.3 AU), Ulysses (1.45 AU)
  Space telescopes: Hubble (1.014 AU, operational), Webb (1.023 AU, L2), Spitzer, Kepler

LUNAR DEBRIS: 38 objects, ~105 metric tonnes on/impacted into the Moon.
  Most recent: SLIM lander (JAXA, Jan 2024) | Heaviest: Apollo S-IVB ~13,930 kg each
  NOTE: Mar 2022 lunar impact = Chang'e 5-T1 booster (CNSA), not SpaceX Falcon 9.

--- ON A QUIET DAY ---

OPERATIONAL STATUS: ✅ ALL CLEAR — No threshold-crossing conditions detected.

SPACECRAFT HEALTH FORECAST:
  🟢 LEO: 5/100 — NOMINAL | 🟢 MEO: 4/100 — NOMINAL
  🟢 GEO: 4/100 — NOMINAL | 🟢 HEO: 4/100 — NOMINAL

MISSION WINDOW ASSESSMENT:
  ✅ EVA (Spacewalk): GO  ✅ Satellite Launch: GO  ✅ Orbital Maneuver: GO
  ✅ Deep-Space Uplink: GO  ✅ Instrument Calibration: GO
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
> still run and all live data sections will work normally — only the AI narrative section
> will show a configuration reminder. `ask.py` also works without credentials by returning
> the raw live data matched to your question. CelesTrak and JPL Horizons need no keys at all.

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
├── briefing.py           # Entry point — full daily briefing
├── nasa_api.py           # All API clients: DONKI, NeoWs, EONET, CelesTrak, JPL Horizons
├── significance.py       # Classifiers + alert detection + static inventories
├── mission_planner.py    # Mission window advisor: GO/CAUTION/HOLD per operation type
├── spacecraft_health.py  # Predictive spacecraft risk scoring per orbit regime (0–100)
├── watsonx.py            # IBM watsonx.ai Granite — flight director AI narrative
├── ask.py                # "Ask the Flight Director" — natural language Q&A interface
├── sample_output.txt     # Example briefing output (no API key needed to view)
└── pyproject.toml        # Package metadata and dependencies
```

### ask.py — Natural Language Interface

Ask any space question in plain English:

```bash
python ask.py "Is it safe to do a spacewalk today?"
python ask.py "What is Voyager 1 doing right now?"
python ask.py "Are there any dangerous asteroids this week?"
python ask.py "How much human trash is on the Moon?"
python ask.py "How many satellites are in orbit right now?"
```

**Works with or without watsonx credentials:**

| Credentials set? | What you get |
|---|---|
| ✅ Yes | IBM Granite answers in natural language, grounded in live data fetched seconds ago |
| ❌ No | Live data is still fetched and the most relevant lines are shown directly — real data, no AI wrapper |

Granite answers **only from data fetched on that run** — it cannot hallucinate outdated
facts because the context snapshot is rebuilt live every invocation.

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
