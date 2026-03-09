from flask import Flask, request, jsonify
import subprocess
import json
import requests
from datetime import datetime, timezone

app = Flask(__name__)

REQUIRED_FIELDS = {"temperature", "humidity", "co2_ppm"}
CLOUD_BACKEND_URL = "https://your-cloud-server.example.com/data"


def get_phone_location():
    import platform

    if platform.system() == "Windows":
        # Temporary fake location for laptop testing
        return 11.3410, 77.7172

    result = subprocess.run(
        ["termux-location", "-p", "gps"],
        capture_output=True,
        text=True,
        timeout=20
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "termux-location failed")

    data = json.loads(result.stdout)
    lat = data.get("latitude")
    lon = data.get("longitude")

    if lat is None or lon is None:
        raise RuntimeError(f"Location missing: {data}")

    return float(lat), float(lon)

@app.route("/sensor", methods=["POST"])
def receive_sensor():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(sorted(missing))}"}), 400

    try:
        lat, lon = get_phone_location()

        enriched = {
            "temperature": float(data["temperature"]),
            "humidity": float(data["humidity"]),
            "co2_ppm": float(data["co2_ppm"]),
            "latitude": lat,
            "longitude": lon,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # resp = requests.post(CLOUD_BACKEND_URL, json=enriched, timeout=10)

        return jsonify({
            "status": "forwarded",
            # "cloud_status": resp.status_code,
            "payload": enriched
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)