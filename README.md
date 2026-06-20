# Community Tool-Share Matcher — Prototype

A web app that recommends borrowing tools from neighbours instead of buying them.
The user picks a DIY project; the app shows which tools are needed, nearby lenders
who have each tool, and the estimated CO₂ saved by borrowing rather than buying new.

🔗 **Live demo:** [community-tool-share-matcher.streamlit.app](https://community-tool-share-matcher.streamlit.app)

> **All data is entirely mock and randomly invented. No real users, lenders, or
> locations are represented. This is a course prototype.**

---

## Tech stack

| Technology | Role |
|---|---|
| Python 3 | Language |
| [Streamlit](https://streamlit.io) | Web UI — runs in the browser, no HTML/CSS needed |
| pandas | Listed as a dependency for future data-handling work |
| `math` (standard library) | Haversine distance formula — **no scikit-learn used** |
| `json` + `pathlib` (standard library) | Loading the JSON data files |

The haversine formula converts two latitude/longitude pairs into a straight-line
distance in kilometres. It is implemented from scratch in `recommender.py` using
only Python's built-in `math` module.

---

## How to run

### Option A — manual (two commands)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Option B — one-command script

```bash
bash run_prototype.sh
```

Both options open the app at `http://localhost:8501` in your browser.

Alternatively, try the [live demo](https://community-tool-share-matcher.streamlit.app) — no setup needed.

---

## What you will see

1. **Screen 1 — Project input**: pick one of four DIY projects from a dropdown and
   click "Find lenders near me".
2. **Screen 2 — Recommendations**: for each tool the project needs, up to three
   lender cards appear (name, distance, rating, CO₂ saving, plain-English
   explanation). Tools are colour-coded by risk tier:
   - 🟢 **Low risk** — cards shown normally.
   - 🟡 **Medium risk** — cards shown with a safety caution note.
   - 🔴 **High risk** — no neighbour cards; a safety notice and a link to
     instructional material are shown instead, plus a suggestion to use a
     staffed tool library.
3. **Screen 3 — CO₂ impact**: a summary of total CO₂ saved by borrowing the
   low- and medium-risk tools from neighbours (high-risk tools are excluded from
   this total because the user goes to a staffed library, not a neighbour).

---

## File reference

| File | What it contains |
|---|---|
| `projects.json` | Maps each of the four project names to the list of tools it requires |
| `lenders.json` | 20 invented lenders scattered across Vienna with lat/lon, tools owned, loan count, rating, and availability |
| `emissions.json` | Maps each tool name to the estimated kg CO₂ saved by borrowing vs buying new |
| `risk_tiers.json` | Maps each tool name to its risk tier: `"low"`, `"medium"`, or `"high"` |
| `recommender.py` | Core logic: `haversine()`, `get_recommendations()`, and all data loading. Can be run standalone (`python recommender.py`) to print results without the UI |
| `app.py` | Streamlit UI — imports from `recommender.py` and renders all three screens |
| `requirements.txt` | Python package dependencies (`streamlit`, `pandas`) |
| `run_prototype.sh` | One-command convenience script: installs dependencies then starts the app |
| `CLAUDE.md` | Development notes for the AI assistant used to build this prototype |
