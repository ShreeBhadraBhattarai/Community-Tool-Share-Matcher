# Community Tool-Share Matcher — Prototype

## What this is
A web app that recommends borrowing tools from neighbours instead of buying them.
The user picks a DIY project; the app shows the tools needed and nearby lenders
who have them, with an explanation and a CO2 saving for each.
This is a course prototype. ALL DATA IS MOCK/RANDOM. No real users.

## Audience note
I am a beginner. Write simple, well-commented code. After each step, explain in
plain language what you did and what I should check.

## Tech stack
- Python + Streamlit (the web UI)
- pandas (handling the mock data)
- Distance via the haversine formula (lat/long to kilometres)
- Run locally with: streamlit run app.py

## Data (three JSON files, all invented)
1. projects.json — maps each project to the tools it needs. Projects:
   "Hang a picture", "Build a planter box", "Fix a leaky pipe", "Build a bookshelf".
2. lenders.json — about 20 lenders scattered around Vienna, Austria. Each has:
   id, name, latitude, longitude, list of tools they own, completed_loans (a count),
   rating (placeholder ~4.5–5.0), and availability (true/false).
3. emissions.json — maps each tool to estimated kg CO2 saved by borrowing vs buying new.

## Ranking logic
For each required tool, find lenders who own it AND are available, then:
- Rank by distance (closest first); use rating as a tiebreaker.
- Reserve ONE slot for a "new lender" (completed_loans < 5) within range, labelled
  "New to the network" — this counteracts popularity bias on purpose.
- Show the top 3 lenders per tool.

## Risk tiers (safety gating)
- Low risk (tape measure, screwdriver, hand saw): show normally.
- Medium risk (power drill, sander): add a line asking the user to confirm familiarity.
- High risk (chainsaw, circular saw, angle grinder): DO NOT just list neighbours.
  Show a safety notice + a link to instructional material, and suggest a staffed
  tool library instead.

## Every recommendation must include an explanation
Example: "Anna is 0.3 km away, completed 14 loans with a 100% return rate, and
borrowing her drill saves ~2.5 kg CO2 versus buying new."

## Three screens
1. Project input: a dropdown to pick the project, optional postcode box.
2. Recommendations: one card per lender — tool, name, distance, trust summary,
   one-sentence explanation, CO2 saving.
3. Impact: total CO2 saved across the chosen tools vs buying everything new.