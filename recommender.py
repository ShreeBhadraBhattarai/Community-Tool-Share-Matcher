import json
import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Load data files once when the module is imported.
# Path(__file__).parent makes sure this works regardless of which directory
# you run the script from.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
PROJECTS   = json.loads((_HERE / "projects.json").read_text(encoding="utf-8"))
LENDERS    = json.loads((_HERE / "lenders.json").read_text(encoding="utf-8"))
EMISSIONS  = json.loads((_HERE / "emissions.json").read_text(encoding="utf-8"))
RISK_TIERS = json.loads((_HERE / "risk_tiers.json").read_text(encoding="utf-8"))

# Default user location: Vienna city centre (Stephansplatz)
DEFAULT_LAT = 48.2082
DEFAULT_LON = 16.3738


def haversine(lat1, lon1, lat2, lon2):
    """Return the great-circle distance in kilometres between two points."""
    R = 6371  # Earth's mean radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def get_recommendations(project_name, user_lat=None, user_lon=None):
    """
    Return the top lenders for every tool required by project_name.

    Parameters
    ----------
    project_name : str
        Must match a key in projects.json exactly.
    user_lat, user_lon : float, optional
        The user's location. Defaults to Vienna city centre.

    Returns
    -------
    dict with keys:
        "project" : str
        "tools"   : dict mapping each tool name to a list of up to 3 lender dicts.
    Each lender dict has: id, name, distance_km, rating, completed_loans,
    co2_saving_kg, is_new_lender.
    """
    if user_lat is None:
        user_lat = DEFAULT_LAT
    if user_lon is None:
        user_lon = DEFAULT_LON

    if project_name not in PROJECTS:
        known = ", ".join(PROJECTS.keys())
        raise KeyError(f"Unknown project '{project_name}'. Known projects: {known}")

    tools_needed = PROJECTS[project_name]
    results = {}

    for tool in tools_needed:
        # Step 1: keep only lenders who own this tool and are available
        candidates = [
            lender for lender in LENDERS
            if tool in lender["tools"] and lender["availability"]
        ]

        # Step 2: compute distance for each candidate
        for lender in candidates:
            lender["_dist"] = haversine(
                user_lat, user_lon,
                lender["latitude"], lender["longitude"]
            )

        # Step 3: sort by distance (closest first), rating as tiebreaker (highest first)
        candidates.sort(key=lambda l: (l["_dist"], -l["rating"]))

        # Step 4: find the closest "new" lender (completed_loans < 5)
        new_pick = next(
            (l for l in candidates if l["completed_loans"] < 5),
            None
        )

        natural_top3_ids = {l["id"] for l in candidates[:3]}

        if new_pick is None:
            # No new lender exists for this tool — just take the top 3
            selected = candidates[:3]
        elif new_pick["id"] in natural_top3_ids:
            # New lender is already in the top 3 by distance — keep as-is
            selected = candidates[:3]
        else:
            # New lender wouldn't appear naturally — reserve slot 3 for them.
            # Fill slots 1-2 from the remaining (non-new) candidates.
            others = [l for l in candidates if l["id"] != new_pick["id"]]
            selected = others[:2] + [new_pick]

        # Step 5: build clean result dicts (drop the temporary _dist key)
        co2 = EMISSIONS.get(tool, 0.0)
        tool_results = []
        for lender in selected:
            tool_results.append({
                "id":              lender["id"],
                "name":            lender["name"],
                "distance_km":     round(lender["_dist"], 2),
                "rating":          lender["rating"],
                "completed_loans": lender["completed_loans"],
                "co2_saving_kg":   co2,
                "is_new_lender":   lender["completed_loans"] < 5,
            })

        results[tool] = tool_results

    return {"project": project_name, "tools": results}


# ---------------------------------------------------------------------------
# Quick test — run with:  python recommender.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    project = "Build a planter box"
    data = get_recommendations(project)

    print(f"\n=== {data['project']} ===")
    for tool, lenders in data["tools"].items():
        co2 = EMISSIONS.get(tool, 0)
        print(f"\n  Tool: {tool}  (saves {co2} kg CO2 vs buying new)")
        if not lenders:
            print("    (no available lenders found)")
            continue
        for rank, l in enumerate(lenders, start=1):
            new_tag = "  << New to the network" if l["is_new_lender"] else ""
            prefix  = "[NEW] " if l["is_new_lender"] else "      "
            print(
                f"    {rank}. {prefix}{l['name']:<20}"
                f"- {l['distance_km']:>5.2f} km, "
                f"rating {l['rating']}, "
                f"{l['completed_loans']} loans"
                f"{new_tag}"
            )
    print()
