#!/usr/bin/env python3
"""
Sensor Data Client
Simulates sensor devices by sending random temperature and humidity readings
to the sensor server, then fetches and prints the collected statistics.
"""
import json
import os
import random
import time

import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5000")
NUM_READINGS = int(os.environ.get("NUM_READINGS", "5"))

SENSOR_IDS = ["sensor-A", "sensor-B", "sensor-C"]


def send_reading(sensor_id, temperature, humidity):
    payload = {
        "sensor_id": sensor_id,
        "temperature": temperature,
        "humidity": humidity,
    }
    response = requests.post(f"{SERVER_URL}/readings", json=payload, timeout=5)
    response.raise_for_status()
    return response.json()


def get_stats():
    response = requests.get(f"{SERVER_URL}/stats", timeout=5)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print(f"Connecting to server at: {SERVER_URL}")
    print(f"Sending {NUM_READINGS} readings...\n")

    for i in range(NUM_READINGS):
        sensor_id = random.choice(SENSOR_IDS)
        temperature = round(random.uniform(15.0, 35.0), 2)
        humidity = round(random.uniform(30.0, 90.0), 2)

        result = send_reading(sensor_id, temperature, humidity)
        print(
            f"  [{i + 1}/{NUM_READINGS}] {sensor_id}: "
            f"{temperature}°C | {humidity}% humidity  →  id={result['id']}"
        )
        time.sleep(0.3)

    print("\n--- Stats from server ---")
    stats = get_stats()
    print(json.dumps(stats, indent=2))
