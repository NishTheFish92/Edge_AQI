from flask import Flask, request, jsonify

app = Flask(__name__)

REQUIRED_FIELDS = {"temperature", "humidity", "co2_ppm"}


@app.route("/data", methods=["POST"])
def receive_data():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(sorted(missing))}"}), 400

    print(data)
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
