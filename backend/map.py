"""
Air Quality Heatmap - Interactive Map using Folium
Sensors: Temperature, Humidity, CO2
Data source: SQLite database (air_quality.db)

HOW TO USE:
  Run: python map.py
  Open the generated `air_quality_map.html` in a browser
"""

import os
import sqlite3
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
MAP_CENTER = [12.9716, 77.5946]   # Default: Bangalore. Change to your city.
ZOOM_LEVEL = 13
OUTPUT_FILE = "air_quality_map.html"
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "air_quality.db")))


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_from_db(db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Fetch readings from the SQLite database.
    Schema: readings(id, temperature, humidity, co2_ppm, latitude, longitude, timestamp, source)
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT latitude, longitude, temperature, humidity, co2_ppm, timestamp FROM readings ORDER BY timestamp DESC",
        conn,
    )
    conn.close()
    return df


# ─────────────────────────────────────────────
# NORMALISATION
# ─────────────────────────────────────────────

def normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize a series to [0, 1]."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - mn) / (mx - mn)


# ─────────────────────────────────────────────
# MAP BUILDING
# ─────────────────────────────────────────────

def build_map(df: pd.DataFrame) -> folium.Map:
    """
    Build and return a Folium map with heatmap layers for CO2 and Temperature,
    plus individual marker popups showing raw sensor values.
    """
    required = {"latitude", "longitude", "temperature", "humidity", "co2_ppm"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing columns: {missing}")

    df = df.dropna(subset=list(required)).copy()

    if df.empty:
        raise ValueError("No valid readings to plot.")

    # Compute map center from data
    center = [df["latitude"].mean(), df["longitude"].mean()]

    df["co2_norm"]  = normalize(df["co2_ppm"])
    df["temp_norm"] = normalize(df["temperature"])

    # ── Base map ──
    m = folium.Map(
        location=center,
        zoom_start=ZOOM_LEVEL,
        tiles="CartoDB dark_matter",
    )

    # ── CO2 Heatmap Layer ──
    co2_data = df[["latitude", "longitude", "co2_norm"]].values.tolist()
    HeatMap(
        co2_data,
        name="CO₂ (ppm)",
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

    # ── Temperature Heatmap Layer ──
    temp_data = df[["latitude", "longitude", "temp_norm"]].values.tolist()
    HeatMap(
        temp_data,
        name="Temperature (°C)",
        show=False,
        radius=22,
        blur=14,
        min_opacity=0.35,
        gradient={
            0.0: "#00ff00",   # green  — cool
            0.4: "#ffff00",   # yellow — warm
            0.7: "#ff7700",   # orange — hot
            1.0: "#ff0000",   # red    — very hot
        },
    ).add_to(m)

    # ── Sensor Markers with popups ──
    marker_group = folium.FeatureGroup(name="Sensor Readings", show=False)
    for _, row in df.iterrows():
        co2_val  = row["co2_ppm"]
        temp_val = row["temperature"]
        hum_val  = row["humidity"]

        if temp_val < 25:
            dot_color = "green"
        elif temp_val <= 35:
            dot_color = "orange"
        else:
            dot_color = "red"

        ts = row.get("timestamp", "")
        popup_html = f"""
        <div style="font-family: monospace; font-size: 13px; padding: 4px;">
            <b>Sensor Reading</b><br>
            <hr style="margin:4px 0">
            CO₂         : <b>{co2_val:.0f} ppm</b><br>
            Temperature : <b>{temp_val:.1f} °C</b><br>
            Humidity    : <b>{hum_val:.1f} %</b><br>
            <small style="color:#888">
                ({row['latitude']:.5f}, {row['longitude']:.5f})<br>
                {ts}
            </small>
        </div>
        """
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color=dot_color,
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=240),
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
        <b>CO₂ (ppm)</b><br>
        <span style="color:#00cfff">&#9632;</span> Normal<br>
        <span style="color:#0050ff">&#9632;</span>  Elevated<br>
        <span style="color:#cc0066">&#9632;</span> High<br>
        <br>
        <b>Temperature (°C)</b><br>
        <span style="color:#00ff00">&#9632;</span> Cool<br>
        <span style="color:#ffff00">&#9632;</span> Warm<br>
        <span style="color:#ff0000">&#9632;</span> Hot<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


# ─────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────

def generate_map(output_file: str = OUTPUT_FILE, db_path: Path = DB_PATH) -> str:
    """
    Fetch sensor data from the SQLite database and save an interactive
    heatmap HTML file.

    Returns the path to the saved file.
    """
    print("Loading air quality data from database...")
    df = fetch_from_db(db_path)

    if df.empty:
        print("No readings found in the database.")
        return output_file

    print(f"   Loaded {len(df)} readings.")
    print(f"   CO₂   range : {df['co2_ppm'].min():.0f} – {df['co2_ppm'].max():.0f} ppm")
    print(f"   Temp  range : {df['temperature'].min():.1f} – {df['temperature'].max():.1f} °C")
    print(f"   Humidity    : {df['humidity'].min():.1f} – {df['humidity'].max():.1f} %")

    print("\nBuilding interactive heatmap...")
    air_map = build_map(df)
    air_map.save(output_file)

    print(f"\nMap saved -> {output_file}")
    print("   Open it in any browser to explore.")
    return output_file


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    generate_map()
