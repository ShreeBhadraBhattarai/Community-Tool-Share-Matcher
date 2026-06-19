import pandas as pd
import streamlit as st
from recommender import (
    get_recommendations,
    PROJECTS, EMISSIONS, RISK_TIERS, LENDERS,
    DEFAULT_LAT, DEFAULT_LON,
)

# Build fast lookups from the full lender list (used in several places below).
LENDER_COORDS = {l["id"]: (l["latitude"], l["longitude"]) for l in LENDERS}
# id → display name, used by the fairness panel to label every lender in the catalogue.
LENDER_NAMES  = {l["id"]: l["name"] for l in LENDERS}
# IDs of "new to the network" lenders (fewer than 5 completed loans).
# The recommender gives these a reserved slot to counteract popularity bias.
NEW_LENDER_IDS = {l["id"] for l in LENDERS if l["completed_loans"] < 5}

# ---------------------------------------------------------------------------
# st.set_page_config() must be the very first Streamlit call in the file.
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Tool-Share Matcher",
    page_icon="🌱",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Global CSS — only the overrides that config.toml cannot handle:
#   • import the "Sora" Google Font and apply it app-wide (incl. headings)
#   • h2/h3 headings need to be moss green, not the white textColor
#   • caption text gets a muted sage tone
# !important is required to beat Streamlit's own stylesheet.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&display=swap');
html, body, [class*="css"]      { font-family: 'Sora', sans-serif; }
h1, h2, h3, h4, h5, h6          { font-family: 'Sora', sans-serif; }
h2, h3        { color: #97BC62 !important; }
.stCaption p  { color: #5A7A6A !important; }

/* -------------------------------------------------------------------------
   Equal-height recommendation cards (applies to EVERY tool row).
   Each row is wrapped in st.container(key="rec_row_<tool>") -> the prefix
   selector below scopes these rules to those rows only, so the chat/form
   column layouts are left untouched.

   - the row is a flex row that stretches its columns to equal height
   - each column becomes a flex column filling that height
   - the card (st.markdown) grows to fill, pinning the button (the next
     widget) to the bottom so the "Request to borrow" buttons line up
   ------------------------------------------------------------------------- */
[class*="st-key-rec_row_"] [data-testid="stHorizontalBlock"] {
    align-items: stretch;
}
[class*="st-key-rec_row_"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
    height: 100%;
    display: flex;
    flex-direction: column;
}
[class*="st-key-rec_row_"] [data-testid="stColumn"] [data-testid="stMarkdown"] {
    flex: 1 1 auto;
    display: flex;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Risk-tier visual styles: maps each tier name to (badge label, bg colour, text colour)
# ---------------------------------------------------------------------------
TIER_STYLE = {
    "low":    ("Low risk",    "#1A3D24", "#97BC62"),   # dark green bg, moss text
    "medium": ("Medium risk", "#3D2B00", "#FFB347"),   # dark amber bg, amber text
    "high":   ("High risk",   "#3D0000", "#FF6B6B"),   # dark red bg,   soft red text
}

# ---------------------------------------------------------------------------
# Safety links for high-risk tools.
# Each value is a (link label, URL) tuple pointing to a YouTube safety-guide search.
# Update these to point to specific videos or official resources if you prefer.
# ---------------------------------------------------------------------------
SAFETY_LINKS = {
    "circular saw":  (
        "Circular Saw Safety Guide",
        "https://www.youtube.com/results?search_query=circular+saw+safety+guide",
    ),
    "chainsaw":      (
        "Chainsaw Safety Guide",
        "https://www.youtube.com/results?search_query=chainsaw+safety+guide",
    ),
    "angle grinder": (
        "Angle Grinder Safety Guide",
        "https://www.youtube.com/results?search_query=angle+grinder+safety+guide",
    ),
}


# ---------------------------------------------------------------------------
# Simulated lender replies, grouped by conversation stage.
# Stage 0 = reply to the user's first message, 1 = second, 2+ = all later ones.
# {tool} and {name} are filled in at reply time.
# ---------------------------------------------------------------------------
REPLY_TEMPLATES = [
    [   # Stage 0 — first reply
        "Hi! Yes, the {tool} is free this weekend. When were you thinking of stopping by?",
        "Of course, happy to help out! What day works best for you?",
        "Great timing — I'm not using it this week. How long do you need it for?",
    ],
    [   # Stage 1 — second reply
        "That works for me! Pop by any time after 10 am — I'm at Mariahilfer Str. 45.",
        "Saturday morning sounds perfect. I'll leave it by the front door.",
        "Sunday afternoon is great. Just ring the bell when you arrive!",
    ],
    [   # Stage 2+ — later replies
        "Wonderful — all confirmed! Let me know if you have any questions about how it works.",
        "Perfect, looking forward to it. Good luck with the project! 🙂",
        "Great stuff! Feel free to keep it for the full weekend if you need.",
    ],
]


# ---------------------------------------------------------------------------
# Helper: Gini coefficient for a list of non-negative counts.
# Formula: G = Σ(2i - n - 1) * x_i  /  (n * total),  with x sorted ascending.
# Returns 0 for a perfectly equal distribution, up to (n-1)/n for full concentration.
# ---------------------------------------------------------------------------
def gini_index(values):
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    arr   = sorted(values)
    total = sum(arr)
    num   = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(arr))
    return round(num / (n * total), 3)


# ---------------------------------------------------------------------------
# Helper: fairness & equity panel — rendered in the SIDEBAR so it stays
# available without interrupting the recommendation flow.
# Reads st.session_state["impressions"] — a dict of lender_id → int count
# accumulated across all searches in this browser session.
# ---------------------------------------------------------------------------
def show_fairness_panel():
    impressions      = st.session_state.get("impressions", {})
    total_impr       = sum(impressions.values())
    n_catalogue      = len(LENDER_NAMES)            # always 20 in this dataset

    with st.sidebar:
        st.header("⚖️ Fairness & equity")
        st.caption("Behind the scenes")

        # Reset button — clears counts and removes cached results so Screen 2
        # disappears, giving a clean slate for a fresh demo run.
        if st.button("Reset stats", key="reset_fairness"):
            for key in ("impressions", "results", "active_chat", "conversations"):
                st.session_state.pop(key, None)
            st.rerun()

        if total_impr == 0:
            st.info("Run at least one search to see fairness metrics.")
            return

        st.caption(
            f"Stats accumulated over this session ({total_impr} total impressions "
            f"across all searches). One impression = one lender card shown."
        )

        # --- 1. Gini index of lender exposure ---
        # We include all 20 catalogue lenders (even those with 0 impressions) so
        # the score reflects under-exposure, not just within-surfaced distribution.
        all_counts  = [impressions.get(lid, 0) for lid in LENDER_NAMES]
        gini        = gini_index(all_counts)

        if gini < 0.2:
            interpretation = "Exposure looks well-balanced — lenders are sharing impressions fairly evenly."
        elif gini < 0.4:
            interpretation = "Moderate concentration — a handful of lenders attract more exposure than others."
        else:
            interpretation = "Concentrated exposure — a small number of lenders dominate; others are rarely surfaced."

        st.subheader("1 · Gini index of lender exposure")
        st.metric("Gini index  (0 = equal, 1 = fully concentrated)", f"{gini:.3f}")
        st.caption(interpretation)

        # --- 2. Catalogue coverage ---
        surfaced   = sum(1 for lid in LENDER_NAMES if impressions.get(lid, 0) > 0)
        coverage   = round(100 * surfaced / n_catalogue, 1)

        st.subheader("2 · Catalogue coverage")
        st.metric(
            f"Lenders surfaced at least once  (out of {n_catalogue})",
            f"{surfaced} / {n_catalogue}  ({coverage} %)",
        )

        # --- 3. Bar chart of impressions per lender ---
        # Shows all 20 lenders so unsurfaced ones appear with a 0 bar.
        # We use first-name only so the x-axis labels don't overlap.
        st.subheader("3 · Impressions per lender")
        chart_df = pd.DataFrame({
            "Impressions": [impressions.get(lid, 0) for lid in LENDER_NAMES]
        }, index=[name.split()[0] for name in LENDER_NAMES.values()])
        st.bar_chart(chart_df)

        # --- 4. Cold-start boost visibility ---
        new_impr       = sum(impressions.get(lid, 0) for lid in NEW_LENDER_IDS)
        new_names_str  = ", ".join(LENDER_NAMES[lid] for lid in sorted(NEW_LENDER_IDS))
        new_pct        = round(100 * new_impr / total_impr, 1) if total_impr else 0

        st.subheader("4 · Cold-start boost")
        st.markdown(
            f"**{new_impr}** of {total_impr} impressions ({new_pct} %) went to "
            f"\"New to the network\" lenders ({new_names_str}) — "
            f"those with fewer than 5 completed loans. "
            f"A non-zero share here shows the reserved newcomer slot is translating "
            f"into real visibility for cold-start lenders."
        )


# ---------------------------------------------------------------------------
# Helper: simulated borrow-request / messaging panel.
# Reads st.session_state["active_chat"] (set when a card button is clicked) and
# renders the whole conversation inside ONE bordered container, so it reads as a
# self-contained panel rather than a chat bar pinned to the bottom of the page.
# It is called from show_recommendations() directly under the active lender's card.
# Each lender keeps its own thread under its id, so switching lenders preserves it.
# ---------------------------------------------------------------------------
def render_conversation():
    active = st.session_state.get("active_chat")
    if active is None:
        return

    lender_id   = active["lender_id"]
    lender_name = active["lender_name"]
    tool        = active["tool"]
    first_name  = lender_name.split()[0]

    # Retrieve (or create) this lender's thread.
    convos = st.session_state.setdefault("conversations", {})
    thread = convos.setdefault(lender_id, [])

    # Everything below lives inside one bordered container = one visual unit.
    with st.container(border=True):

        # Header row: panel title on the left, close button on the right
        col_title, col_close = st.columns([5, 1])
        with col_title:
            st.markdown(f"**💬 Message {lender_name}  ·  {tool.title()}**")
        with col_close:
            if st.button("✕ Close", key="close_chat"):
                st.session_state.pop("active_chat", None)
                st.rerun()

        # Simulated-conversation notice — kept visible so it's clearly a demo.
        st.caption(
            "ℹ️ Simulated conversation for the prototype — messages don't reach a "
            "real person; the lender's replies are generated locally."
        )

        # Seed the thread with a short opening note so there is something to reply to.
        if not thread:
            thread.append({"role": "lender", "content": (
                f"Hi! I saw you're interested in borrowing my {tool}. "
                f"Feel free to ask any questions or let me know when you need it."
            )})

        # Render the full thread with st.chat_message for a clean look.
        for msg in thread:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant", avatar="🔧"):
                    st.markdown(f"**{first_name}:** {msg['content']}")

        # Input row: a text box + small "Send" button, wrapped in a form so the
        # box clears automatically on submit (clear_on_submit) and both Enter and
        # the button trigger one send.
        with st.form(key=f"msg_form_{lender_id}", clear_on_submit=True):
            in_col, btn_col = st.columns([5, 1])
            with in_col:
                user_text = st.text_input(
                    "Your message",
                    placeholder=f"Message {first_name} about the {tool}…",
                    label_visibility="collapsed",
                )
            with btn_col:
                sent = st.form_submit_button("Send", use_container_width=True)

        if sent and user_text.strip():
            thread.append({"role": "user", "content": user_text.strip()})

            # Pick a reply based on how far into the conversation we are.
            # Stage advances per user message; we cycle within each bucket so the
            # replies are deterministic (no flicker across reruns).
            user_count = sum(1 for m in thread if m["role"] == "user")
            stage      = min(user_count - 1, len(REPLY_TEMPLATES) - 1)
            bucket     = REPLY_TEMPLATES[stage]
            reply      = bucket[(user_count - 1) % len(bucket)].format(
                tool=tool, name=first_name
            )
            thread.append({"role": "lender", "content": reply})
            st.rerun()   # redraw so the new messages appear above the input

        # Let the user clear just this conversation thread.
        if len(thread) > 1:
            if st.button("Clear this conversation", key=f"clear_conv_{lender_id}"):
                convos[lender_id] = []
                st.rerun()


# ---------------------------------------------------------------------------
# Helper: one-sentence plain-English explanation for a lender card.
# ---------------------------------------------------------------------------
def make_explanation(lender, tool):
    """Return a one-sentence summary of why this lender is a good match."""
    first  = lender["name"].split()[0]   # "Anna Hofer" -> "Anna"
    dist   = lender["distance_km"]
    loans  = lender["completed_loans"]
    rating = lender["rating"]
    co2    = lender["co2_saving_kg"]

    if lender["is_new_lender"]:
        loan_word = "loan" if loans == 1 else "loans"
        return (
            f"{first} is new to the network ({loans} {loan_word} completed so far) "
            f"and lives {dist:.1f} km away -- borrowing their {tool} saves "
            f"~{co2} kg CO2 versus buying new."
        )

    return (
        f"{first} is {dist:.1f} km away, has completed {loans} loans "
        f"with a {rating}/5 rating, and borrowing their {tool} saves "
        f"~{co2} kg CO2 versus buying new."
    )


# ---------------------------------------------------------------------------
# Helper: render one lender as a bordered card.
# ---------------------------------------------------------------------------
def render_card(lender, tool):
    """Display a single lender as a bordered card with info chips."""

    # "New to the network" pill — distinct mint colour so it stands out from
    # the green chips below. Dark text keeps it readable on the light mint fill.
    if lender["is_new_lender"]:
        new_pill = (
            '<span style="background:#D5E8D0; color:#1A3D24; '
            'padding:2px 9px; border-radius:12px; font-size:0.72em; '
            'font-weight:600; margin-left:6px;">New to the network</span>'
        )
    else:
        new_pill = ""

    # Shared chip style: deep-green card background, thin moss border, small sage text.
    chip = (
        "display:inline-block; background:#1E2D28; border:1px solid #97BC62; "
        "color:#8FAF8A; padding:2px 9px; border-radius:12px; font-size:0.78em; "
        "margin:0 5px 4px 0;"
    )

    explanation = make_explanation(lender, tool)

    # The card is a flex column that fills the full (equal) height of its
    # column; the description block gets flex:1 so it absorbs any extra space,
    # keeping every card's bottom edge — and the button below it — aligned.
    html = f"""
    <div style="border:1px solid #97BC62; border-radius:8px; padding:14px;
                margin-bottom:10px; background:#1E2D28;
                display:flex; flex-direction:column; flex:1 1 auto; width:100%;">
      <p style="margin:0 0 8px 0;">
        <span style="color:#FFFFFF; font-weight:700;">{lender['name']}</span>{new_pill}
      </p>
      <div style="margin:0 0 8px 0;">
        <span style="{chip}">📍 {lender['distance_km']:.1f} km</span>
        <span style="{chip}">✅ {lender['completed_loans']} loans · {lender['rating']}</span>
        <span style="{chip}">🌱 saves ~{lender['co2_saving_kg']} kg</span>
      </div>
      <p style="margin:0; flex:1 1 auto; font-style:italic; font-size:0.88em; color:#5A7A6A;">
        {explanation}
      </p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

    # Button to open the messaging panel for this specific lender + tool combo.
    # The key must be unique across all rendered buttons on the page.
    btn_key = f"request_{lender['id']}_{tool.replace(' ', '_')}"
    if st.button("📩 Request to borrow", key=btn_key, use_container_width=True):
        st.session_state["active_chat"] = {
            "lender_id":   lender["id"],
            "lender_name": lender["name"],
            "tool":        tool,
        }
        st.rerun()


# ---------------------------------------------------------------------------
# Helper: caution note for medium-risk tools (shown above the lender cards).
# ---------------------------------------------------------------------------
def render_medium_risk_notice(tool):
    """Display a yellow warning box for medium-risk tools."""
    st.warning(
        f"**Before borrowing a {tool}:** Make sure you are comfortable using "
        f"this tool safely. Do not hesitate to ask the lender to show you "
        f"how it works before you take it home."
    )


# ---------------------------------------------------------------------------
# Helper: full safety block for high-risk tools.
# No lender cards are shown — the caller uses `continue` after this.
# ---------------------------------------------------------------------------
def render_high_risk_notice(tool):
    """Display a red safety block for high-risk tools (replaces lender cards)."""
    # Look up the tool-specific link; fall back to a generic search if not listed
    link_label, link_url = SAFETY_LINKS.get(
        tool,
        ("Power Tool Safety Guide", "https://www.youtube.com/results?search_query=power+tool+safety+guide"),
    )

    st.error(
        f"**{tool.title()} — High-Risk Tool**\n\n"
        f"For your safety, we do not list neighbour lenders for the {tool}. "
        f"This tool requires proper training to use without risk of serious injury."
    )
    st.markdown(f"📺 [{link_label}]({link_url})")
    st.info(
        "**Use a staffed tool library instead.** Trained staff can "
        "demonstrate safe technique and supervise your first use. "
        "Search *'Werkzeugverleih Wien'* to find one near you in Vienna."
    )


# ---------------------------------------------------------------------------
# Helper: render all of Screen 2.
# ---------------------------------------------------------------------------
def show_recommendations(results):
    """Display one section per tool with appropriate safety gating."""
    st.markdown("---")
    st.header(f"Tools for: {results['project']}")

    for tool, lenders in results["tools"].items():
        co2  = EMISSIONS.get(tool, 0)
        tier = RISK_TIERS.get(tool, "low")   # default to low if a tool isn't in the file
        label, bg, fg = TIER_STYLE[tier]

        # Compact tool header (moss green, smaller than a full subheader),
        # with the risk badge (amber/red as before) + CO2 note on the next line.
        st.markdown(
            f'<div style="margin:12px 0 2px 0;">'
            f'<span style="color:#97BC62; font-size:1.05rem; font-weight:700;">'
            f'{tool.title()}</span></div>'
            f'<div style="margin-bottom:8px;">'
            f'<span style="background:{bg}; color:{fg}; padding:2px 9px; '
            f'border-radius:4px; font-size:0.85em; font-weight:600;">{label}</span>'
            f'&nbsp;&nbsp;<span style="color:#5A7A6A; font-size:0.85em;">'
            f'Saves ~{co2} kg CO2 vs buying new</span></div>',
            unsafe_allow_html=True,
        )

        # HIGH RISK: show safety block only — skip lender cards entirely
        if tier == "high":
            render_high_risk_notice(tool)
            continue

        # MEDIUM RISK: show caution note, then fall through to lender cards
        if tier == "medium":
            render_medium_risk_notice(tool)

        # LOW + MEDIUM: show up to 3 lender cards side by side
        if not lenders:
            st.info("No available lenders found for this tool.")
            continue

        # st.columns(n) creates n equal-width columns; zip stops at the shorter list.
        # Wrap the row in a keyed container so the equal-height CSS above (scoped
        # to .st-key-rec_row_*) targets these cards without touching other layouts.
        with st.container(key=f"rec_row_{tool.replace(' ', '_')}"):
            cols = st.columns(len(lenders))
            for col, lender in zip(cols, lenders):
                with col:
                    render_card(lender, tool)

        # If the user opened a chat for a lender in THIS tool's row, show the
        # conversation full-width directly beneath the row of cards.
        active = st.session_state.get("active_chat")
        if active and active["tool"] == tool and any(
            l["id"] == active["lender_id"] for l in lenders
        ):
            render_conversation()


# ---------------------------------------------------------------------------
# Helper: render Screen 3 — CO2 impact summary.
# ---------------------------------------------------------------------------
def show_impact(results):
    """Display total CO2 saved by borrowing neighbour-lent tools."""

    # Only count tools that are low/medium-risk AND have at least one lender.
    # High-risk tools are excluded — the user goes to a staffed library for those,
    # not a neighbour, so they don't count as a "borrow-from-neighbour" saving.
    borrowable = [
        tool for tool, lenders in results["tools"].items()
        if RISK_TIERS.get(tool, "low") != "high" and len(lenders) > 0
    ]

    # Also note which tools were gated, so we can explain the exclusion.
    gated = [
        tool for tool in results["tools"]
        if RISK_TIERS.get(tool, "low") == "high"
    ]

    # Sum the CO2 saving for every borrowable tool.
    # EMISSIONS[tool] is the kg CO2 emitted when buying that tool new.
    # Borrowing emits ~0 kg, so the saving equals the purchase cost.
    total = round(sum(EMISSIONS.get(t, 0) for t in borrowable), 2)

    st.markdown("---")
    st.header("Your CO2 Impact")

    if not borrowable:
        st.info("No tools available to borrow from neighbours for this project.")
        return

    # Small note explaining what is and isn't counted
    if gated:
        gated_list = ", ".join(t.title() for t in gated)
        st.caption(
            f"Counting {len(borrowable)} neighbour-borrowed tool(s). "
            f"Excluded (high-risk, use a staffed library): {gated_list}."
        )
    else:
        st.caption(f"Counting all {len(borrowable)} tools you can borrow from neighbours.")

    # --- Headline metric ---
    # One big number for the total CO2 saved. The delta is used as a context
    # label ("vs buying new"); delta_color="off" keeps it neutral grey rather
    # than red/green, since it's a caption, not an increase/decrease.
    st.metric(
        label="Total CO₂ saved by borrowing",
        value=f"~{total} kg CO₂",
        delta="vs buying everything new",
        delta_color="off",
    )

    # --- Per-tool breakdown ---
    st.markdown("**Breakdown by tool:**")
    for tool in borrowable:
        co2       = EMISSIONS.get(tool, 0)
        tier      = RISK_TIERS.get(tool, "low")
        tier_label = TIER_STYLE[tier][0]   # e.g. "Low risk" or "Medium risk"
        st.markdown(f"- **{tool.title()}** ({tier_label}): ~{co2} kg CO2 saved")


# ---------------------------------------------------------------------------
# Helper: render the lender map section.
# ---------------------------------------------------------------------------
def show_map(results):
    """Plot all recommended lenders (deduplicated) on a map with st.map."""

    # Collect unique lenders across every tool.
    # We skip high-risk tools because no neighbour cards are shown for them.
    seen_ids = set()
    rows = []
    for tool, lenders in results["tools"].items():
        if RISK_TIERS.get(tool, "low") == "high":
            continue
        for lender in lenders:
            if lender["id"] not in seen_ids:
                seen_ids.add(lender["id"])
                lat, lon = LENDER_COORDS[lender["id"]]
                rows.append({
                    "lat":   lat,
                    "lon":   lon,
                    "color": "#97BC62",          # moss green for lenders
                    "size":  80,
                })

    if not rows:
        return   # nothing borrowable to map

    # Add the user's default location (Vienna city centre) as a distinct pin.
    rows.append({
        "lat":   DEFAULT_LAT,
        "lon":   DEFAULT_LON,
        "color": "#F7F9F5",                      # near-white so it stands out
        "size":  120,                            # slightly larger to be easy to spot
    })

    df = pd.DataFrame(rows)

    st.markdown("---")
    st.header("Where these lenders are")
    st.caption(
        "Green dots = recommended lenders for this project. "
        "White dot = your location (Vienna centre). "
        "A lender who appears for several tools is shown only once."
    )

    # st.map() reads "lat"/"lon" columns by default.
    # The "color" column sets a per-row CSS colour (requires Streamlit 1.30+).
    # zoom=12 gives a city-district view appropriate for Vienna distances.
    st.map(df, color="color", size="size", zoom=12)


# ===========================================================================
# SCREEN 1 — Project Input
# ===========================================================================

# --- Hero header -----------------------------------------------------------
# App name (white), a one-line tagline (muted sage), and a thin moss divider.
# Built as a single HTML block so the spacing stays tight and consistent.
st.markdown(
    """
    <div style="margin-bottom:6px;">
      <span style="font-size:2rem; font-weight:700; color:#FFFFFF;">
        🌱 Community Tool-Share Matcher
      </span>
    </div>
    <div style="color:#5A7A6A; font-size:1.05rem; margin-bottom:14px;">
      Borrow tools from neighbours instead of buying — pick a project and find who can lend.
    </div>
    <hr style="border:none; border-top:2px solid #97BC62; margin:0 0 24px 0;">
    """,
    unsafe_allow_html=True,
)

# --- Project-input card ----------------------------------------------------
# Everything the user fills in lives inside one bordered container so it reads
# as a single "form card". The button spans the full card width.
with st.container(border=True):
    st.markdown(
        '<h3 style="margin-top:0;">What are you building?</h3>',
        unsafe_allow_html=True,
    )

    project = st.selectbox(
        "Project",
        options=list(PROJECTS.keys()),
        label_visibility="collapsed",   # heading above already labels this
    )

    st.text_input(
        "Your Vienna postcode (optional)",
        placeholder="e.g. 1070",
        help=(
            "Postcode lookup is not implemented yet. "
            "The app uses Vienna city centre as your location."
        ),
    )

    clicked = st.button(
        "Find lenders near me",
        type="primary",
        use_container_width=True,
    )

# Breathing room before the results sections begin.
st.write("")

# ===========================================================================
# SESSION STATE — keep results visible across Streamlit reruns
# "impressions" accumulates lender exposure counts across all searches.
# ===========================================================================
if "impressions" not in st.session_state:
    st.session_state["impressions"] = {}    # lender_id → int impression count
if "conversations" not in st.session_state:
    st.session_state["conversations"] = {}  # lender_id → list of message dicts

if clicked:
    with st.spinner("Finding lenders near you…"):
        results = get_recommendations(project)
    st.session_state["results"] = results

    # Count one impression for every lender card that is about to be shown.
    # High-risk tools are excluded because no lender cards are rendered for them.
    for tool, lenders in results["tools"].items():
        if RISK_TIERS.get(tool, "low") != "high":
            for lender in lenders:
                lid = lender["id"]
                st.session_state["impressions"][lid] = (
                    st.session_state["impressions"].get(lid, 0) + 1
                )

# ===========================================================================
# SCREEN 2 — Recommendations → Map → CO2 Impact
# All three sections are driven by the same results dict in session state.
# ===========================================================================
# The fairness panel renders into the sidebar, so it is always available and
# does not interrupt the main recommendation flow. Called unconditionally.
show_fairness_panel()

if "results" in st.session_state:
    # A blank st.write("") between each section adds a consistent vertical gap
    # on top of the horizontal divider every section already draws.
    # (The borrow-request conversation now appears inline, directly under the
    # active lender's card inside show_recommendations.)
    show_recommendations(st.session_state["results"])
    st.write("")
    show_map(st.session_state["results"])
    st.write("")
    show_impact(st.session_state["results"])
