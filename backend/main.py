from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__)

DB_PATH = Path("air_quality.db")

REQUIRED_FIELDS = {
    "temperature",
    "humidity",
    "co2_ppm",
    "latitude",
    "longitude",
}


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
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


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "message": "Air quality backend is running"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


@app.route("/data", methods=["POST"])
def receive_data():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return jsonify({
            "error": f"Missing fields: {', '.join(sorted(missing))}"
        }), 400

    try:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        co2_ppm = float(data["co2_ppm"])
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        timestamp = data.get("timestamp")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        source = str(data.get("source", "phone_fognode"))

    except (TypeError, ValueError) as e:
        return jsonify({
            "error": f"Invalid field type: {str(e)}"
        }), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO readings (
                temperature,
                humidity,
                co2_ppm,
                latitude,
                longitude,
                timestamp,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            temperature,
            humidity,
            co2_ppm,
            latitude,
            longitude,
            timestamp,
            source
        ))

        reading_id = cur.lastrowid
        conn.commit()
        conn.close()

        print({
            "id": reading_id,
            "temperature": temperature,
            "humidity": humidity,
            "co2_ppm": co2_ppm,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp,
            "source": source
        })

        return jsonify({
            "status": "ok",
            "message": "Reading stored successfully",
            "id": reading_id
        }), 200

    except Exception as e:
        return jsonify({
            "error": f"Database insert failed: {str(e)}"
        }), 500


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
    app.run(host="0.0.0.0", port=5000, debug=True)