#!/usr/bin/env python3
"""
Sensor Data Server
Accepts temperature and humidity readings from sensors and stores them to a file.
Provides endpoints to list all readings and retrieve statistics.
"""
import json
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

DATA_FILE = os.environ.get("DATA_FILE", "data.json")


def load_readings():
    """Load all readings from the JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []


def save_readings(readings):
    """Persist readings to the JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(readings, f, indent=2)


@app.route("/health")
def health():
    readings = load_readings()
    return jsonify({"status": "healthy", "total_readings": len(readings)})


@app.route("/readings", methods=["GET"])
def get_readings():
    return jsonify(load_readings())


@app.route("/readings", methods=["POST"])
def add_reading():
    data = request.get_json()

    required_fields = ["sensor_id", "temperature", "humidity"]
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": f"Missing required fields: {required_fields}"}), 400

    readings = load_readings()
    reading = {
        "id": len(readings) + 1,
        "sensor_id": data["sensor_id"],
        "temperature": round(float(data["temperature"]), 2),
        "humidity": round(float(data["humidity"]), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    readings.append(reading)
    save_readings(readings)
    return jsonify(reading), 201


@app.route("/stats")
def get_stats():
    readings = load_readings()
    if not readings:
        return jsonify({"message": "No readings yet. Send some data first!"})

    temps = [r["temperature"] for r in readings]
    humidities = [r["humidity"] for r in readings]

    return jsonify(
        {
            "total_readings": len(readings),
            "temperature": {
                "min": round(min(temps), 2),
                "max": round(max(temps), 2),
                "avg": round(sum(temps) / len(temps), 2),
            },
            "humidity": {
                "min": round(min(humidities), 2),
                "max": round(max(humidities), 2),
                "avg": round(sum(humidities) / len(humidities), 2),
            },
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
