import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from map import generate_map
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "air_quality.db")))
PORT = int(os.getenv("PORT", 5001))

REQUIRED_FIELDS = {"temperature", "humidity", "co2_ppm", "latitude", "longitude"}

_reading_buffer = []


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    try:
        conn = get_db_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                co2_ppm REAL NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT DEFAULT 'phone_fognode'
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Database initialized at %s", DB_PATH)
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Air quality backend is running"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/stats", methods=["GET"])
def stats():
    conn = get_db_connection()
    row = conn.execute(
        "SELECT COUNT(*) as total, MAX(timestamp) as last_reading FROM readings"
    ).fetchone()
    conn.close()
    return jsonify(dict(row)), 200


@app.route("/data", methods=["POST"])
def receive_data():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(sorted(missing))}"}), 400

    try:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        co2_ppm = float(data["co2_ppm"])
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        if not (-90 <= latitude <= 90):
            return jsonify({"error": "latitude must be between -90 and 90"}), 400
        if not (-180 <= longitude <= 180):
            return jsonify({"error": "longitude must be between -180 and 180"}), 400

        timestamp = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
        source = str(data.get("source", "phone_fognode"))
        
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid field type: {str(e)}"}), 400

    _reading_buffer.append((temperature, humidity, co2_ppm, latitude, longitude))

    if len(_reading_buffer) < 10:
        return jsonify({"status": "ok", "message": "Reading buffered", "buffered": len(_reading_buffer)}), 200

    # Average the 10 readings
    avg = [sum(col) / 10 for col in zip(*_reading_buffer)]
    avg_temp, avg_hum, avg_co2, avg_lat, avg_lon = avg
    _reading_buffer.clear()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO readings (temperature, humidity, co2_ppm, latitude, longitude, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (avg_temp, avg_hum, avg_co2, avg_lat, avg_lon, timestamp, source))
        reading_id = cur.lastrowid
        conn.commit()
        conn.close()

        logger.info("Stored averaged id=%d temp=%.1f hum=%.1f co2=%.1f", reading_id, avg_temp, avg_hum, avg_co2)
        generate_map()
        return jsonify({"status": "ok", "message": "Averaged reading stored", "id": reading_id}), 201

    except Exception as e:
        return jsonify({"error": f"Database insert failed: {str(e)}"}), 500


@app.route("/readings", methods=["GET"])
def list_readings():
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 500))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, temperature, humidity, co2_ppm, latitude, longitude, timestamp, source
        FROM readings
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify(rows), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT, debug=False)
