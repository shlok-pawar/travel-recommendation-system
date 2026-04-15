import streamlit as st
import pandas as pd
import requests
import math
import io
import datetime

try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
PEXELS_API_KEY = "q3INirINAMpMluGoKLpzZkQnZLZ4OtmLUwvc7rEPxmGxBe64cQ5rX1IP"

st.set_page_config(
    page_title="TravelSmart India",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1 {
        font-family: 'Playfair Display', serif !important;
        color: #1a1a2e !important;
    }
    .match-score-high   { color: #16a34a; font-weight: 700; font-size: 1.3rem; }
    .match-score-medium { color: #d97706; font-weight: 700; font-size: 1.3rem; }
    .match-score-low    { color: #dc2626; font-weight: 700; font-size: 1.3rem; }

    .card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-blue   { background:#dbeafe; color:#1d4ed8; }
    .badge-green  { background:#dcfce7; color:#16a34a; }
    .badge-orange { background:#ffedd5; color:#ea580c; }
    .badge-purple { background:#ede9fe; color:#7c3aed; }

    .budget-row {
        display: flex; justify-content: space-between;
        padding: 6px 0; border-bottom: 1px solid #f3f4f6;
        font-size: 0.9rem;
    }
    .budget-total {
        display: flex; justify-content: space-between;
        padding: 8px 0; font-weight: 700; font-size: 1rem;
        color: #1a1a2e;
    }
    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    div[data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────
@st.cache_data
def load_data():
    cities_df = pd.read_csv("indian_cities_updated.csv")
    places_df = pd.read_csv("final_places_data.csv")
    return cities_df, places_df

cities_df, places_df = load_data()

# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * (2 * math.asin(math.sqrt(a)))


def get_pexels_image(query, api_key):
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data["photos"]:
                return data["photos"][0]["src"]["medium"]
    except Exception:
        return None
    return None


def compute_match_score(row, budget, season, group, category, distance_km, max_distance):
    """
    Returns a score 0-100 based on how well this destination matches user preferences.
    """
    score = 0

    # Distance score (closer = better) — 30 pts
    dist_score = max(0, 1 - (distance_km / max_distance))
    score += dist_score * 30

    # Budget score — 25 pts (if dest budget <= user budget, full marks; else drops off)
    if row["Budget"] <= budget:
        score += 25
    else:
        overshoot = (row["Budget"] - budget) / budget
        score += max(0, 25 - overshoot * 25)

    # Season match — 20 pts
    if season == "Any" or season.lower() in str(row["Recommended_Season"]).lower():
        score += 20

    # Group match — 15 pts
    if group == "Any" or group.lower() in str(row["Ideal_For"]).lower():
        score += 15

    # Category match — 10 pts
    if category == "Any" or category.lower() == str(row["Category"]).lower():
        score += 10

    return round(score)


def budget_breakdown(total_budget, distance_km, duration):
    """
    Splits total budget into transport, stay, food, misc per person.
    """
    # Transport estimate: ₹4 per km (round trip bus/train approx)
    transport = min(round(distance_km * 2 * 4 / 10) * 10, int(total_budget * 0.30))

    remaining = total_budget - transport
    nights = {"1-day trip": 0, "Weekend trip": 1, ">1 week": 7, "1 week+": 6}.get(duration, 1)

    stay_per_night = 800
    stay = min(nights * stay_per_night, int(remaining * 0.45))
    food_days = max(nights + 1, 1)
    food = min(food_days * 350, int(remaining * 0.30))
    misc = max(remaining - stay - food, 0)

    return {
        "🚌 Transport (round trip)": transport,
        "🏨 Stay": stay,
        "🍽️ Food": food,
        "🎟️ Entry / Activities": misc,
    }


def generate_pdf(results_df, city_choice, state_choice, filters):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(26, 26, 46)
    pdf.cell(0, 12, "TravelSmart India - Itinerary Report", ln=True, align="C")

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Generated on {datetime.date.today().strftime('%d %B %Y')}", ln=True, align="C")
    pdf.ln(4)

    # Trip summary box
    pdf.set_fill_color(240, 248, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(26, 26, 46)
    pdf.cell(0, 8, f"Origin: {city_choice}, {state_choice}", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Budget: Rs.{filters['budget']}  |  Season: {filters['season']}  |  Group: {filters['group']}  |  Duration: {filters['duration']}", ln=True)
    pdf.ln(6)

    for i, (_, row) in enumerate(results_df.iterrows(), 1):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(26, 26, 46)
        pdf.cell(0, 9, f"{i}. {row['Place_Name']} - {row['City']}, {row['State']}", ln=True)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 6, f"   Match Score: {row['Match_Score']}%  |  Distance: {row['Distance_km']:.1f} km  |  Category: {row['Category']}", ln=True)
        pdf.cell(0, 6, f"   Budget: Rs.{row['Budget']}  |  Season: {row['Recommended_Season']}  |  Ideal For: {row['Ideal_For']}", ln=True)

        bd = budget_breakdown(row["Budget"], row["Distance_km"], row["Duration"])
        pdf.cell(0, 6, "   Budget Breakdown:", ln=True)
        for k, v in bd.items():
            pdf.cell(0, 6, f"      {k}: Rs.{v}", ln=True)

        pdf.set_draw_color(220, 220, 220)
        pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
        pdf.ln(6)

    return pdf.output(dest="S").encode("latin-1")


# ─────────────────────────────────────────────
# SIDEBAR FILTERS
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎯 Travel Filters")
    st.markdown("---")

    max_distance = st.slider("📏 Max Distance (km)", 50, 2000, 500, 50)
    budget = st.slider("💰 Budget per person (₹)", 500, 50000, 15000, 500)
    duration = st.selectbox("⏱️ Trip Duration", ["Any"] + sorted(places_df["Duration"].dropna().unique()))
    category = st.selectbox("🏷️ Category", ["Any", "Adventure", "Historical", "Nature", "Beaches"])
    group = st.selectbox("👥 Traveling With", ["Any", "Single", "Friends", "Family", "Couple"])
    season = st.selectbox("🌦️ Preferred Season", ["Any", "Monsoon", "Spring", "Summer", "Winter"])

    st.markdown("---")
    sort_by = st.radio("📊 Sort Results By", ["Match Score", "Distance", "Budget (Low→High)"])
    top_n = st.slider("🔢 Max Results to Show", 3, 20, 8)

# ─────────────────────────────────────────────
# CITY SELECTION
# ─────────────────────────────────────────────
st.markdown("# 🗺️ TravelSmart India")
st.markdown("*Structured travel recommendations built for Indian travelers — not a chatbot, a decision engine.*")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    state_choice = st.selectbox("📍 Your State", sorted(cities_df["State"].dropna().unique()))
with col2:
    filtered_cities = cities_df[cities_df["State"] == state_choice]["City"].dropna().unique()
    city_choice = st.selectbox("🏙️ Your City", sorted(filtered_cities))

selected_city = cities_df[
    (cities_df["City"] == city_choice) & (cities_df["State"] == state_choice)
].iloc[0]
city_lat = selected_city["Latitude"]
city_lon = selected_city["Longitude"]

# ─────────────────────────────────────────────
# COMPUTE DISTANCES + SCORES
# ─────────────────────────────────────────────
places_df["Distance_km"] = places_df.apply(
    lambda row: haversine(city_lat, city_lon, row["Latitude"], row["Longitude"]), axis=1
)

filtered_df = places_df[places_df["Distance_km"] <= max_distance].copy()

# Apply filters
if duration != "Any":
    filtered_df = filtered_df[filtered_df["Duration"] == duration]
if category != "Any":
    filtered_df = filtered_df[filtered_df["Category"] == category]
if group != "Any":
    filtered_df = filtered_df[filtered_df["Ideal_For"].str.contains(group, case=False, na=False)]
if season != "Any":
    filtered_df = filtered_df[filtered_df["Recommended_Season"].str.contains(season, case=False, na=False)]

filtered_df = filtered_df[filtered_df["Budget"] <= budget]

# Compute match score
filtered_df["Match_Score"] = filtered_df.apply(
    lambda row: compute_match_score(row, budget, season, group, category, row["Distance_km"], max_distance),
    axis=1
)

# Sort
if sort_by == "Match Score":
    filtered_df = filtered_df.sort_values("Match_Score", ascending=False)
elif sort_by == "Distance":
    filtered_df = filtered_df.sort_values("Distance_km")
else:
    filtered_df = filtered_df.sort_values("Budget")

top_results = filtered_df.head(top_n)

# ─────────────────────────────────────────────
# SUMMARY METRICS
# ─────────────────────────────────────────────
st.markdown(f"### 📍 Destinations within {max_distance} km of **{city_choice}, {state_choice}**")

m1, m2, m3, m4 = st.columns(4)
m1.metric("🏆 Destinations Found", len(filtered_df))
m2.metric("⭐ Best Match Score", f"{filtered_df['Match_Score'].max() if not filtered_df.empty else 0}%")
m3.metric("💰 Lowest Budget", f"₹{filtered_df['Budget'].min():,}" if not filtered_df.empty else "—")
m4.metric("📏 Nearest Place", f"{filtered_df['Distance_km'].min():.0f} km" if not filtered_df.empty else "—")

st.markdown("---")

# ─────────────────────────────────────────────
# MAIN RESULTS
# ─────────────────────────────────────────────
if top_results.empty:
    st.warning("😕 No destinations found. Try increasing the distance or budget, or loosen your filters.")
else:
    # Download buttons
    filters_meta = {"budget": budget, "season": season, "group": group, "duration": duration}
    dl_col1, dl_col2 = st.columns(2)

    # CSV download (always available)
    with dl_col1:
        csv_df = top_results[["Place_Name", "City", "State", "Category", "Distance_km",
                               "Budget", "Recommended_Season", "Ideal_For", "Duration", "Match_Score"]].copy()
        csv_df.columns = ["Place", "City", "State", "Category", "Distance_km",
                          "Budget", "Season", "Ideal_For", "Duration", "Match_%"]
        csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download as CSV",
            data=csv_bytes,
            file_name=f"TravelSmart_{city_choice}_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # PDF download (if fpdf installed)
    with dl_col2:
        if PDF_AVAILABLE:
            try:
                pdf_bytes = generate_pdf(top_results, city_choice, state_choice, filters_meta)
                st.download_button(
                    label="📄 Download Itinerary PDF",
                    data=pdf_bytes,
                    file_name=f"TravelSmart_{city_choice}_{datetime.date.today()}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception:
                st.info("PDF export: install `fpdf2` via pip")
        else:
            st.info("📄 PDF export: run `pip install fpdf2` to enable")

    st.markdown(f"**Showing top {len(top_results)} recommendations:**")
    st.markdown("")

    for rank, (_, row) in enumerate(top_results.iterrows(), 1):
        score = row["Match_Score"]
        score_class = "match-score-high" if score >= 70 else ("match-score-medium" if score >= 45 else "match-score-low")
        score_emoji = "🟢" if score >= 70 else ("🟡" if score >= 45 else "🔴")

        with st.container():
            st.markdown(f'<div class="card">', unsafe_allow_html=True)

            img_col, info_col = st.columns([1, 1.8])

            with img_col:
                image_url = get_pexels_image(f"{row['City']} India tourism", PEXELS_API_KEY)
                if image_url:
                    st.image(image_url, use_container_width=True)
                else:
                    st.info("📷 Image unavailable")

            with info_col:
                # Header row
                hcol1, hcol2 = st.columns([2, 1])
                with hcol1:
                    st.markdown(f"#### #{rank} — {row['Place_Name']}")
                    st.markdown(f"📍 *{row['City']}, {row['State']}*")
                with hcol2:
                    st.markdown(f'<div class="{score_class}">{score_emoji} {score}% Match</div>', unsafe_allow_html=True)

                # Badges
                st.markdown(
                    f'<span class="badge badge-blue">{row["Category"]}</span>'
                    f'<span class="badge badge-green">{row["Recommended_Season"]}</span>'
                    f'<span class="badge badge-orange">{row["Ideal_For"]}</span>'
                    f'<span class="badge badge-purple">{row["Duration"]}</span>',
                    unsafe_allow_html=True
                )
                st.markdown("")

                # Stats row
                sc1, sc2 = st.columns(2)
                sc1.markdown(f"📏 **Distance:** {row['Distance_km']:.1f} km")
                sc2.markdown(f"💰 **Total Budget:** ₹{row['Budget']:,}")

                # Budget breakdown (expandable)
                with st.expander("💳 Budget Breakdown (per person)"):
                    bd = budget_breakdown(row["Budget"], row["Distance_km"], row["Duration"])
                    total = 0
                    for label, amt in bd.items():
                        total += amt
                        st.markdown(
                            f'<div class="budget-row"><span>{label}</span><span>₹{amt:,}</span></div>',
                            unsafe_allow_html=True
                        )
                    st.markdown(
                        f'<div class="budget-total"><span>💼 Estimated Total</span><span>₹{total:,}</span></div>',
                        unsafe_allow_html=True
                    )

            st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MAP VIEW
# ─────────────────────────────────────────────
st.markdown("---")
if st.checkbox("🗺️ Show Destinations on Map"):
    if not filtered_df.empty:
        map_df = filtered_df.rename(columns={"Latitude": "lat", "Longitude": "lon"})[["lat", "lon"]].copy()
        # Add origin city
        origin_row = pd.DataFrame([{"lat": city_lat, "lon": city_lon}])
        st.map(pd.concat([origin_row, map_df], ignore_index=True))
        st.caption(f"📍 Your city ({city_choice}) shown with all matching destinations")
    else:
        st.info("No destinations to show on map.")

# ─────────────────────────────────────────────
# COMPARISON TABLE
# ─────────────────────────────────────────────
st.markdown("---")
if st.checkbox("📊 Show Comparison Table") and not filtered_df.empty:
    st.markdown("#### Side-by-Side Comparison")
    table_df = top_results[["Place_Name", "City", "State", "Category", "Distance_km", "Budget", "Recommended_Season", "Ideal_For", "Duration", "Match_Score"]].copy()
    table_df.columns = ["Place", "City", "State", "Category", "Distance (km)", "Budget (₹)", "Season", "Ideal For", "Duration", "Match %"]
    table_df["Distance (km)"] = table_df["Distance (km)"].round(1)
    st.dataframe(table_df.reset_index(drop=True), use_container_width=True)

# ─────────────────────────────────────────────
# WHY NOT JUST CHATGPT — INFO SECTION
# ─────────────────────────────────────────────
st.markdown("---")
with st.expander("ℹ️ Why TravelSmart instead of ChatGPT?"):
    st.markdown("""
    | Feature | **TravelSmart India** | ChatGPT |
    |---|---|---|
    | Real distance from YOUR city | ✅ Haversine formula | ❌ Vague guesses |
    | Verified Indian dataset | ✅ 6,600+ destinations | ❌ Can hallucinate |
    | Consistent results (same input → same output) | ✅ Deterministic | ❌ Non-deterministic |
    | Budget breakdown per person | ✅ Auto-calculated | ❌ Not provided |
    | Match Score % | ✅ Built-in scoring | ❌ Not available |
    | Downloadable PDF itinerary | ✅ One-click export | ❌ Copy-paste from chat |
    | Can be white-labeled for travel agencies | ✅ Embeddable product | ❌ Cannot be embedded |
    | Cost per query after setup | ✅ ₹0 | ❌ Paid API per call |
    """)
