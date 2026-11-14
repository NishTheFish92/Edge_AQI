import json
import logging
import os
import statistics
import subprocess
import time
from collections import deque
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

REQUIRED_FIELDS = {"temperature", "humidity", "co2_ppm"}
CLOUD_BACKEND_URL = os.environ["CLOUD_BACKEND_URL"]
FALLBACK_LAT = float(os.getenv("FALLBACK_LAT", "11.3410"))
FALLBACK_LON = float(os.getenv("FALLBACK_LON", "77.7172"))
GPS_REFRESH_INTERVAL = int(os.getenv("GPS_REFRESH_INTERVAL", "60"))


def _coordinator_interval():
    # SPINE coordinator config: sampling interval pushed to nodes; None lets nodes self-adapt
    try:
        ms = int(os.getenv("COORDINATOR_INTERVAL_MS", ""))
    except ValueError:
        return None
    return ms if ms > 0 else None


COORDINATOR_INTERVAL_MS = _coordinator_interval()

_lat = FALLBACK_LAT
_lon = FALLBACK_LON
_last_gps_update = 0.0

# Outlier rejection: drop a reading more than 4 std devs from the last 20 readings
_window = deque(maxlen=20)

# SPINE discovery: node_id -> announced sensors/functions
_nodes = {}


def is_outlier(reading):
    # Every reading enters the window, so a genuine level shift is absorbed after a few readings
    outlier = len(_window) >= 10 and any(
        abs(reading[f] - statistics.fmean(r[f] for r in _window))
        > 4 * max(statistics.pstdev([r[f] for r in _window]), 1.0)
        for f in REQUIRED_FIELDS
    )
    _window.append(reading)
    return outlier


def get_location():
    global _lat, _lon, _last_gps_update
    if time.time() - _last_gps_update < GPS_REFRESH_INTERVAL:
        return _lat, _lon
    try:
        result = subprocess.run(
            ["termux-location", "-p", "gps"],
            capture_output=True, text=True, timeout=20,
        )
        data = json.loads(result.stdout)
        _lat = float(data["latitude"])
        _lon = float(data["longitude"])
        _last_gps_update = time.time()
        logger.info("GPS updated: %.6f, %.6f", _lat, _lon)
    except Exception as e:
        logger.warning("GPS failed: %s", e)
    return _lat, _lon


def reply(body, status):
    # Every /sensor reply carries the coordinator config so the node never loses it on an error
    return jsonify({**body, "interval_ms": COORDINATOR_INTERVAL_MS}), status


def register_node(data):
    node_id = data.get("node_id")
    if node_id is not None and node_id not in _nodes:
        _nodes[node_id] = {"sensors": data.get("sensors"), "functions": data.get("functions")}
        logger.info("Discovered node %s: sensors=%s functions=%s",
                    node_id, _nodes[node_id]["sensors"], _nodes[node_id]["functions"])


@app.route("/sensor", methods=["POST"])
def receive_sensor():
    data = request.get_json(silent=True)
    if data is None:
        return reply({"error": "Invalid or missing JSON body"}, 400)

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return reply({"error": f"Missing fields: {', '.join(sorted(missing))}"}, 400)

    register_node(data)

    reading = {f: float(data[f]) for f in REQUIRED_FIELDS}
    if is_outlier(reading):
        logger.info("Outlier rejected: %s", reading)
        return reply({"status": "rejected", "reason": "outlier"}, 200)

    lat, lon = get_location()
    payload = {
        **reading,
        "latitude": lat,
        "longitude": lon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "phone_fognode",
    }

    try:
        resp = requests.post(CLOUD_BACKEND_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Forwarded: temp=%.1f hum=%.1f co2=%.1f",
                    payload["temperature"], payload["humidity"], payload["co2_ppm"])
        return reply({"status": "forwarded", "cloud_status": resp.status_code}, 200)
    except Exception as e:
        logger.warning("Forward failed: %s", e)
        return reply({"status": "error", "reason": str(e)}, 503)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
