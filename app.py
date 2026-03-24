import streamlit as st
import pandas as pd
import requests
import math

PEXELS_API_KEY = "q3INirINAMpMluGoKLpzZkQnZLZ4OtmLUwvc7rEPxmGxBe64cQ5rX1IP"

@st.cache_data
def load_data():
    cities_df = pd.read_csv("indian_cities_updated.csv")
    places_df = pd.read_csv("final_places_data.csv")
    return cities_df, places_df

cities_df, places_df = load_data()


def get_pexels_image(query, api_key):
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data["photos"]:
                return data["photos"][0]["src"]["medium"]
    except Exception:
        return None
    return None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * (2 * math.asin(math.sqrt(a)))


st.sidebar.header("🎯 Travel Filters")
duration = st.sidebar.selectbox("Travel Duration", ["Any"] + sorted(places_df["Duration"].unique()))
category = st.sidebar.selectbox("Category", ["Any", "Adventure", "Historical", "Nature", "Beaches"])
budget = st.sidebar.slider("Budget (₹)", 500, 50000, 10000, 500)
group = st.sidebar.selectbox("Who are you traveling with?", ["Any", "Single", "Friends", "Family", "Couple"])
season = st.sidebar.selectbox("Preferred Season", ["Any", "Monsoon", "Spring", "Summer", "Winter"])


state_choice = st.selectbox("Choose Your State", sorted(cities_df["State"].dropna().unique()))
filtered_cities = cities_df[cities_df["State"] == state_choice]["City"].dropna().unique()
city_choice = st.selectbox("Choose Your City", sorted(filtered_cities))


selected_city = cities_df[(cities_df["City"] == city_choice) & (cities_df["State"] == state_choice)].iloc[0]
city_lat = selected_city["Latitude"]
city_lon = selected_city["Longitude"]


places_df["Distance_km"] = places_df.apply(
    lambda row: haversine(city_lat, city_lon, row["Latitude"], row["Longitude"]), axis=1
)
filtered_df = places_df[places_df["Distance_km"] <= 100]

if duration != "Any":
    filtered_df = filtered_df[filtered_df["Duration"] == duration]
if category != "Any":
    filtered_df = filtered_df[filtered_df["Category"] == category]
if group != "Any":
    filtered_df = filtered_df[filtered_df["Ideal_For"].str.contains(group, case=False)]
if season != "Any":
    filtered_df = filtered_df[filtered_df["Recommended_Season"].str.contains(season, case=False)]

filtered_df = filtered_df[filtered_df["Budget"] <= budget].sort_values("Distance_km")


st.title("Smart Indian Travel Recommender")
st.subheader(f"📍 Places within 100 km of {city_choice}, {state_choice}")

if not filtered_df.empty:
    for _, row in filtered_df.iterrows():
        st.markdown(f"### 📍 {row['Place_Name']} ({row['City']}, {row['State']})")

        # 🔍 Fetch image
        image_url = get_pexels_image(f"{row['Place_Name']} {row['City']} India", PEXELS_API_KEY)
        if image_url:
            st.image(image_url, use_container_width=True)
        else:
            st.info("📷 No image available")

        st.markdown(f"- 🧭 **Duration**: {row['Duration']}")
        st.markdown(f"- 🏷️ **Category**: {row['Category']}")
        st.markdown(f"- 💰 **Budget**: ₹{row['Budget']}")
        st.markdown(f"- 👥 **Ideal For**: {row['Ideal_For']}")
        st.markdown(f"- 🌦️ **Season**: {row['Recommended_Season']}")
        st.markdown(f"- 📏 **Distance**: {row['Distance_km']:.1f} km")
        st.markdown("---")
else:
    st.warning("😕 No matching destinations found. Try different filters.")


if st.checkbox("🗺️ Show Map"):
    st.map(filtered_df.rename(columns={"Latitude": "lat", "Longitude": "lon"})[["lat", "lon"]])
