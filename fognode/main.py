import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone

import requests
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

REQUIRED_FIELDS = {"temperature", "humidity", "co2_ppm"}
CLOUD_BACKEND_URL = os.environ["CLOUD_BACKEND_URL"]
FALLBACK_LAT = float(os.getenv("FALLBACK_LAT", "11.3410"))
FALLBACK_LON = float(os.getenv("FALLBACK_LON", "77.7172"))
BUFFER_DB = os.getenv("BUFFER_DB", "buffer.db")
GPS_REFRESH_INTERVAL = int(os.getenv("GPS_REFRESH_INTERVAL", "60"))

# ── GPS cache ────────────────────────────────────────────────────────────────
_cached_lat: float = FALLBACK_LAT
_cached_lon: float = FALLBACK_LON
_location_lock = threading.Lock()


def _fetch_termux_location():
    result = subprocess.run(
        ["termux-location", "-p", "gps"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "termux-location failed")
    data = json.loads(result.stdout)
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        raise RuntimeError(f"Location missing from response: {data}")
    return float(lat), float(lon)


def _gps_refresh_loop():
    global _cached_lat, _cached_lon
    while True:
        try:
            lat, lon = _fetch_termux_location()
            with _location_lock:
                _cached_lat, _cached_lon = lat, lon
            logger.info("GPS updated: %.6f, %.6f", lat, lon)
        except Exception as e:
            logger.warning("GPS refresh failed: %s", e)
        time.sleep(GPS_REFRESH_INTERVAL)


def get_phone_location():
    with _location_lock:
        return _cached_lat, _cached_lon


# ── Local buffer ─────────────────────────────────────────────────────────────
def init_buffer():
    conn = sqlite3.connect(BUFFER_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def buffer_reading(payload: dict):
    conn = sqlite3.connect(BUFFER_DB)
    conn.execute(
        "INSERT INTO pending (payload, created_at) VALUES (?, ?)",
        (json.dumps(payload), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def drain_buffer():
    conn = sqlite3.connect(BUFFER_DB)
    rows = conn.execute(
        "SELECT id, payload FROM pending ORDER BY id ASC LIMIT 20"
    ).fetchall()
    conn.close()

    for row_id, payload_str in rows:
        try:
            resp = requests.post(CLOUD_BACKEND_URL, json=json.loads(payload_str), timeout=10)
            resp.raise_for_status()
            conn = sqlite3.connect(BUFFER_DB)
            conn.execute("DELETE FROM pending WHERE id = ?", (row_id,))
            conn.commit()
            conn.close()
            logger.info("Drained buffered reading id=%d", row_id)
        except Exception:
            break  # backend still down, stop trying


def _drain_loop():
    while True:
        time.sleep(30)
        try:
            drain_buffer()
        except Exception as e:
            logger.warning("Drain loop error: %s", e)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/sensor", methods=["POST"])
def receive_sensor():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(sorted(missing))}"}), 400

    lat, lon = get_phone_location()

    enriched = {
        "temperature": float(data["temperature"]),
        "humidity": float(data["humidity"]),
        "co2_ppm": float(data["co2_ppm"]),
        "latitude": lat,
        "longitude": lon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "phone_fognode",
    }

    try:
        resp = requests.post(CLOUD_BACKEND_URL, json=enriched, timeout=10)
        resp.raise_for_status()
        logger.info(
            "Forwarded: temp=%.1f hum=%.1f co2=%.1f",
            enriched["temperature"], enriched["humidity"], enriched["co2_ppm"],
        )
        return jsonify({"status": "forwarded", "cloud_status": resp.status_code}), 200
    except Exception as e:
        buffer_reading(enriched)
        logger.warning("Backend unreachable, buffered locally: %s", e)
        return jsonify({"status": "buffered", "reason": str(e)}), 200


if __name__ == "__main__":
    init_buffer()
    threading.Thread(target=_gps_refresh_loop, daemon=True).start()
    threading.Thread(target=_drain_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
