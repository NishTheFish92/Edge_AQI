"""
Air Quality Heatmap - Interactive Map using Folium
Pollutants: PM2.5 and CO2
Data source: Database / API

HOW TO USE:
  1. Fill in your DB/API credentials in the config section
  2. Adapt the `fetch_from_db()` or `fetch_from_api()` function to match your schema
  3. Run: python air_quality_heatmap.py
  4. Open the generated `air_quality_map.html` in a browser
"""

import folium
from folium.plugins import HeatMap, HeatMapWithTime
import pandas as pd
import numpy as np

# ─────────────────────────────────────────────
# CONFIG — edit these to match your setup
# ─────────────────────────────────────────────
MAP_CENTER = [12.9716, 77.5946]   # Default: Bangalore. Change to your city.
ZOOM_LEVEL = 13
OUTPUT_FILE = "air_quality_map.html"


# ─────────────────────────────────────────────
# DATA FETCHING — choose your source below
# ─────────────────────────────────────────────

def fetch_from_db():
    """
    Fetch readings from a SQL database (PostgreSQL / MySQL / SQLite).
    Expected table schema:
        readings(id, latitude FLOAT, longitude FLOAT,
                 pm25 FLOAT, co2 FLOAT, timestamp DATETIME)
    """
    #import sqlalchemy

    # ── Replace with your connection string ──
    # PostgreSQL: "postgresql://user:password@host:5432/dbname"
    # MySQL:      "mysql+pymysql://user:password@host:3306/dbname"
    # SQLite:     "sqlite:///air_quality.db"
    DB_URL = "postgresql://user:password@localhost:5432/air_quality_db"

    engine = sqlalchemy.create_engine(DB_URL)
    query = """
        SELECT latitude, longitude, pm25, co2, timestamp
        FROM readings
        ORDER BY timestamp DESC
    """
    df = pd.read_sql(query, engine)
    return df


def fetch_from_api():
    """
    Fetch readings from a REST API endpoint.
    Expected JSON response format:
        [
          {"latitude": 12.97, "longitude": 77.59, "pm25": 45.2, "co2": 412.0, "timestamp": "..."},
          ...
        ]
    """
    import requests

    # ── Replace with your API URL and auth ──
    API_URL = "https://your-api.example.com/readings"
    API_KEY = "your_api_key_here"

    headers = {"Authorization": f"Bearer {API_KEY}"}
    params  = {"pollutants": "pm25,co2", "limit": 1000}

    response = requests.get(API_URL, headers=headers, params=params)
    response.raise_for_status()

    df = pd.DataFrame(response.json())
    return df


def load_sample_data():
    """
    Synthetic sample data for testing — remove once your DB/API is connected.
    """
    np.random.seed(42)
    n = 120
    lat_center, lon_center = MAP_CENTER

    df = pd.DataFrame({
        "latitude":  lat_center  + np.random.uniform(-0.05, 0.05, n),
        "longitude": lon_center  + np.random.uniform(-0.05, 0.05, n),
        "pm25": np.random.uniform(10, 200, n),   # µg/m³
        "co2":  np.random.uniform(400, 1200, n), # ppm
    })
    return df


# ─────────────────────────────────────────────
# NORMALISATION
# ─────────────────────────────────────────────

def normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize a series to [0, 1]."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series))
    return (series - mn) / (mx - mn)


# ─────────────────────────────────────────────
# MAP BUILDING
# ─────────────────────────────────────────────

def build_map(df: pd.DataFrame) -> folium.Map:
    """
    Build and return a Folium map with two heatmap layers:
      - PM2.5 layer  (red gradient)
      - CO2 layer    (blue gradient)
    Plus individual marker popups showing raw values.
    """
    # Validate required columns
    required = {"latitude", "longitude", "pm25", "co2"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing columns: {missing}")

    df = df.dropna(subset=["latitude", "longitude", "pm25", "co2"]).copy()

    # Normalize intensities
    df["pm25_norm"] = normalize(df["pm25"])
    df["co2_norm"]  = normalize(df["co2"])

    # ── Base map ──
    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=ZOOM_LEVEL,
        tiles="CartoDB dark_matter",   # dark tile looks great for heatmaps
    )

    # ── PM2.5 Heatmap Layer ──
    pm25_data = df[["latitude", "longitude", "pm25_norm"]].values.tolist()
    HeatMap(
        pm25_data,
        name="PM2.5",
        radius=22,
        blur=14,
        min_opacity=0.35,
        gradient={
            0.0: "#00ff00",   # green  — clean
            0.4: "#ffff00",   # yellow — moderate
            0.7: "#ff7700",   # orange — unhealthy
            1.0: "#ff0000",   # red    — hazardous
        },
    ).add_to(m)

    # ── CO2 Heatmap Layer ──
    co2_data = df[["latitude", "longitude", "co2_norm"]].values.tolist()
    HeatMap(
        co2_data,
        name="CO₂",
        show=False,           # hidden by default; toggle in layer control
        radius=22,
        blur=14,
        min_opacity=0.35,
        gradient={
            0.0: "#00cfff",   # cyan   — low CO2
            0.4: "#0050ff",   # blue   — moderate
            0.7: "#6600cc",   # purple — elevated
            1.0: "#cc0066",   # pink   — high
        },
    ).add_to(m)

    # ── Sensor Markers with popups ──
    marker_group = folium.FeatureGroup(name="Sensor Readings", show=False)
    for _, row in df.iterrows():
        pm25_val = row["pm25"]
        co2_val  = row["co2"]

        # Colour-code marker by PM2.5 AQI level
        if pm25_val < 35:
            dot_color = "green"
        elif pm25_val < 75:
            dot_color = "orange"
        else:
            dot_color = "red"

        popup_html = f"""
        <div style="font-family: monospace; font-size: 13px; padding: 4px;">
            <b>📍 Sensor Reading</b><br>
            <hr style="margin:4px 0">
            🌫️ PM2.5 : <b>{pm25_val:.1f} µg/m³</b><br>
            🟢 CO₂   : <b>{co2_val:.0f} ppm</b><br>
            <small style="color:#888">
                ({row['latitude']:.5f}, {row['longitude']:.5f})
            </small>
        </div>
        """
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color=dot_color,
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=220),
        ).add_to(marker_group)

    marker_group.add_to(m)

    # ── Layer Control ──
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Legend ──
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px; z-index: 9999;
        background: rgba(20,20,20,0.88); color: #eee;
        padding: 14px 18px; border-radius: 10px;
        font-family: monospace; font-size: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        border: 1px solid rgba(255,255,255,0.12);
        ">
        <b style="font-size:13px">Air Quality Legend</b><br><br>
        <b>PM2.5 (µg/m³)</b><br>
        <span style="color:#00ff00">■</span> &lt; 35 — Good<br>
        <span style="color:#ffff00">■</span> 35–75 — Moderate<br>
        <span style="color:#ff7700">■</span> 75–150 — Unhealthy<br>
        <span style="color:#ff0000">■</span> &gt; 150 — Hazardous<br>
        <br>
        <b>CO₂ (ppm)</b><br>
        <span style="color:#00cfff">■</span> &lt; 600 — Normal<br>
        <span style="color:#0050ff">■</span> 600–900 — Elevated<br>
        <span style="color:#cc0066">■</span> &gt; 900 — High<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("📡 Loading air quality data...")

    # ── CHOOSE YOUR SOURCE ──────────────────────────────────────────────
    # Uncomment ONE of these:

    # df = fetch_from_db()         # ← PostgreSQL / MySQL / SQLite
    # df = fetch_from_api()        # ← REST API
    df = load_sample_data()        # ← sample data (for testing)
    # ────────────────────────────────────────────────────────────────────

    print(f"   Loaded {len(df)} readings.")
    print(f"   PM2.5 range : {df['pm25'].min():.1f} – {df['pm25'].max():.1f} µg/m³")
    print(f"   CO₂   range : {df['co2'].min():.0f}  – {df['co2'].max():.0f}  ppm")

    print("\n🗺️  Building interactive heatmap...")
    air_map = build_map(df)
    air_map.save(OUTPUT_FILE)

    print(f"\n✅ Map saved → {OUTPUT_FILE}")
    print("   Open it in any browser to explore.")