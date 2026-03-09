import json
import logging
import os
import subprocess
import time
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

_lat = FALLBACK_LAT
_lon = FALLBACK_LON
_last_gps_update = 0.0


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


@app.route("/sensor", methods=["POST"])
def receive_sensor():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(sorted(missing))}"}), 400

    lat, lon = get_location()
    payload = {
        "temperature": float(data["temperature"]),
        "humidity": float(data["humidity"]),
        "co2_ppm": float(data["co2_ppm"]),
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
        return jsonify({"status": "forwarded", "cloud_status": resp.status_code}), 200
    except Exception as e:
        logger.warning("Forward failed: %s", e)
        return jsonify({"status": "error", "reason": str(e)}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
