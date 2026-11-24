"""Synthetic telematics and driver profile data generator for PremiumPulse.

Generates deterministic, realistic telematics streams across 5 driver personas,
deliberately injecting dirty events and schema drift to exercise Auto Loader
and PySpark cleaning/sessionization rules.
"""

import csv
import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Deterministic seed for exact reproducibility
RANDOM_SEED = 42

OUTPUT_DIR = Path(__file__).resolve().parent

CITIES = ["Austin", "Dallas", "Houston", "San Antonio", "Fort Worth", "El Paso"]
AGE_BANDS = ["18-24", "25-34", "35-49", "50-64", "65+"]
VEHICLE_CLASSES = ["HATCHBACK", "SEDAN", "SUV", "EV", "PICKUP"]
PERSONAS = [
    "safe_commuter",
    "night_owl",
    "speeder",
    "distracted_phone_user",
    "high_mileage_rideshare",
]

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
]


def generate_drivers_and_vehicles(num_drivers: int = 100) -> tuple[list[dict], list[dict]]:
    """Generate master driver and vehicle records."""
    random.seed(RANDOM_SEED)
    drivers = []
    vehicles = []

    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for i in range(1, num_drivers + 1):
        driver_id = f"DRV-{i:05d}"
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"
        email = f"{first_name.lower()}.{last_name.lower()}{i}@example.com"
        age_band = random.choice(AGE_BANDS)
        city = random.choice(CITIES)

        # Drivers aged 18-24 have fewer licence years
        if age_band == "18-24":
            licence_years = random.randint(1, 4)
        elif age_band == "25-34":
            licence_years = random.randint(3, 14)
        else:
            licence_years = random.randint(8, 40)

        created_at = base_date + timedelta(days=random.randint(0, 180))

        drivers.append({
            "driver_id": driver_id,
            "full_name": full_name,
            "email": email,
            "age_band": age_band,
            "licence_years": licence_years,
            "city": city,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

        # Matching vehicle
        vehicle_id = f"VEH-{i:05d}"
        v_class = VEHICLE_CLASSES[(i - 1) % len(VEHICLE_CLASSES)]
        v_age = random.randint(1, 15)

        # Low mileage for first 2 drivers to test UNRATED (<50 km)
        if i in [1, 2]:
            annual_km = 4000
        else:
            annual_km = random.choice([6000, 10000, 14000, 18000, 24000, 32000])

        vehicles.append({
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "vehicle_class": v_class,
            "vehicle_age_years": v_age,
            "annual_km_declared": annual_km,
        })

    return drivers, vehicles


def generate_telematics_stream(
    drivers: list[dict],
    vehicles: list[dict],
    days: int = 90,
) -> tuple[list[dict], list[dict]]:
    """Generate realistic telematics trip events across driver personas."""
    random.seed(RANDOM_SEED + 1)
    end_date = datetime(2025, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=days)

    clean_events = []
    trips_summary = []

    # Assign personas deterministically
    driver_personas = {}
    for idx, d in enumerate(drivers):
        d_id = d["driver_id"]
        if idx in [0, 1]:
            driver_personas[d_id] = "unrated_low_mileage"
        else:
            driver_personas[d_id] = PERSONAS[(idx - 2) % len(PERSONAS)]

    event_counter = 100000
    trip_counter = 50000

    # City coordinate anchors (lat, lon)
    city_anchors = {
        "Austin": (30.2672, -97.7431),
        "Dallas": (32.7767, -96.7970),
        "Houston": (29.7604, -95.3698),
        "San Antonio": (29.4241, -98.4936),
        "Fort Worth": (32.7555, -97.3308),
        "El Paso": (31.7619, -106.4850),
    }

    for idx, d in enumerate(drivers):
        d_id = d["driver_id"]
        v_id = vehicles[idx]["vehicle_id"]
        persona = driver_personas[d_id]
        city = d["city"]
        base_lat, base_lon = city_anchors.get(city, (30.2672, -97.7431))

        # Determine trip frequency and distance based on persona
        if persona == "unrated_low_mileage":
            num_trips = 3
        elif persona == "high_mileage_rideshare":
            num_trips = random.randint(80, 110)
        else:
            num_trips = random.randint(35, 60)

        for _ in range(num_trips):
            trip_counter += 1
            trip_id = f"TRP-{trip_counter:06d}"

            # Trip start time based on persona
            day_offset = random.randint(0, days - 1)
            trip_day = start_date + timedelta(days=day_offset)

            if persona == "night_owl":
                # Midnight to 4 AM
                trip_hour = random.choice([0, 1, 2, 3])
            elif persona == "safe_commuter":
                # Morning or evening rush hour
                trip_hour = random.choice([8, 9, 17, 18])
            else:
                trip_hour = random.randint(6, 22)

            trip_start = trip_day.replace(
                hour=trip_hour,
                minute=random.randint(0, 50),
                second=random.randint(0, 50),
            )

            # Persona driving parameters
            if persona == "unrated_low_mileage":
                trip_dur_min = random.randint(5, 10)
                speed_mean = 35.0
                hard_brake_prob = 0.0
                speeding_prob = 0.0
                phone_prob = 0.0
            elif persona == "safe_commuter":
                trip_dur_min = random.randint(15, 35)
                speed_mean = 45.0
                hard_brake_prob = 0.01
                speeding_prob = 0.01
                phone_prob = 0.00
            elif persona == "night_owl":
                trip_dur_min = random.randint(20, 45)
                speed_mean = 55.0
                hard_brake_prob = 0.03
                speeding_prob = 0.05
                phone_prob = 0.02
            elif persona == "speeder":
                trip_dur_min = random.randint(15, 40)
                speed_mean = 85.0
                hard_brake_prob = 0.08
                speeding_prob = 0.35
                phone_prob = 0.04
            elif persona == "distracted_phone_user":
                trip_dur_min = random.randint(15, 35)
                speed_mean = 48.0
                hard_brake_prob = 0.07
                speeding_prob = 0.05
                phone_prob = 0.30
            else:  # rideshare
                trip_dur_min = random.randint(25, 60)
                speed_mean = 50.0
                hard_brake_prob = 0.04
                speeding_prob = 0.08
                phone_prob = 0.05

            num_waypoints = max(2, trip_dur_min * 2)  # 30-sec steps for generator efficiency
            step_sec = (trip_dur_min * 60) // num_waypoints

            cur_lat = base_lat + random.uniform(-0.05, 0.05)
            cur_lon = base_lon + random.uniform(-0.05, 0.05)
            trip_km = 0.0

            for wp in range(num_waypoints):
                event_counter += 1
                event_id = f"EVT-{event_counter:07d}"
                event_ts = trip_start + timedelta(seconds=wp * step_sec)

                speed_limit = 65.0
                if persona == "speeder" and random.random() < speeding_prob:
                    speed = speed_limit + random.uniform(12.0, 35.0)
                else:
                    speed = max(0.0, random.gauss(speed_mean, 8.0))

                # Accelerometer
                if random.random() < hard_brake_prob:
                    accel = random.uniform(-4.5, -3.1)
                elif random.random() < 0.03:
                    accel = random.uniform(3.1, 4.5)
                else:
                    accel = random.gauss(0.1, 0.5)

                phone_in_use = random.random() < phone_prob

                # Update coordinates
                d_lat = (speed * 0.277778 * step_sec) / 111139.0 * math.cos(math.radians(cur_lat))
                d_lon = (speed * 0.277778 * step_sec) / 111139.0 * math.sin(math.radians(cur_lon))
                cur_lat += d_lat
                cur_lon += d_lon
                dist_step = (speed * step_sec) / 3600.0
                trip_km += dist_step

                clean_events.append({
                    "event_id": event_id,
                    "driver_id": d_id,
                    "vehicle_id": v_id,
                    "trip_hint": trip_id,
                    "event_ts": event_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "latitude": round(cur_lat, 6),
                    "longitude": round(cur_lon, 6),
                    "speed_kmh": round(speed, 1),
                    "speed_limit_kmh": speed_limit,
                    "accel_ms2": round(accel, 2),
                    "phone_in_use": 1 if phone_in_use else 0,
                    "event_type": "TELEMATICS_HEARTBEAT",
                })

            trips_summary.append({
                "trip_id": trip_id,
                "driver_id": d_id,
                "vehicle_id": v_id,
                "trip_start": trip_start.strftime("%Y-%m-%d %H:%M:%S"),
                "trip_end": (trip_start + timedelta(minutes=trip_dur_min)).strftime("%Y-%m-%d %H:%M:%S"),
                "distance_km": round(trip_km, 2),
                "duration_min": trip_dur_min,
            })

    return clean_events, trips_summary


def inject_dirty_events_and_schema_drift(
    clean_events: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Partition events into batches, injecting 3% data errors and schema drift."""
    random.seed(RANDOM_SEED + 2)
    total = len(clean_events)

    batch_1 = clean_events[: int(total * 0.35)]
    batch_2 = clean_events[int(total * 0.35) : int(total * 0.70)]
    batch_3 = clean_events[int(total * 0.70) : int(total * 0.90)]
    batch_drift = clean_events[int(total * 0.90) :]

    # Inject dirty events into batch_2 and batch_3 (~3% total)
    dirty_count = int(total * 0.03)
    target_batches = [batch_2, batch_3]

    for _ in range(dirty_count):
        target_batch = random.choice(target_batches)
        error_type = random.choice([
            "null_ts",
            "duplicate_id",
            "invalid_speed_neg",
            "invalid_speed_high",
            "invalid_gps_lat",
            "invalid_gps_lon",
        ])

        corrupted = dict(random.choice(target_batch))
        corrupted["event_id"] = f"DIRTY-{random.randint(1000, 9999)}"

        if error_type == "null_ts":
            corrupted["event_ts"] = ""
        elif error_type == "duplicate_id":
            # Duplicate an existing event_id
            existing = random.choice(target_batch)
            corrupted["event_id"] = existing["event_id"]
        elif error_type == "invalid_speed_neg":
            corrupted["speed_kmh"] = -25.0
        elif error_type == "invalid_speed_high":
            corrupted["speed_kmh"] = 320.0
        elif error_type == "invalid_gps_lat":
            corrupted["latitude"] = 95.500000
        elif error_type == "invalid_gps_lon":
            corrupted["longitude"] = -195.000000

        target_batch.append(corrupted)

    # Add schema drift column 'ambient_temp_c' to batch_drift
    drifted_records = []
    for evt in batch_drift:
        record = dict(evt)
        record["ambient_temp_c"] = round(random.uniform(15.0, 38.0), 1)
        drifted_records.append(record)

    return batch_1, batch_2, batch_3, drifted_records


def write_csv(filepath: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """Helper to write CSV file with header."""
    if not rows:
        return
    if not fieldnames:
        fieldnames = list(rows[0].keys())
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_generation() -> None:
    """Execute complete deterministic data generation process."""
    print("=" * 60)
    print("PremiumPulse: Telematics Synthetic Data Generation")
    print("=" * 60)

    print("1. Generating 100 drivers and 100 matched vehicles...")
    drivers, vehicles = generate_drivers_and_vehicles(num_drivers=100)

    print("2. Generating telematics trip event stream across 5 personas...")
    events, trips = generate_telematics_stream(drivers, vehicles, days=90)
    print(f"   Generated {len(events)} telematics events across {len(trips)} trips.")

    print("3. Partitioning batches, injecting ~3% dirty events and schema drift...")
    b1, b2, b3, b_drift = inject_dirty_events_and_schema_drift(events)

    print("4. Writing files to data_gen/ ...")
    write_csv(OUTPUT_DIR / "drivers.csv", drivers)
    write_csv(OUTPUT_DIR / "vehicles.csv", vehicles)
    write_csv(OUTPUT_DIR / "events_batch_1.csv", b1)
    write_csv(OUTPUT_DIR / "events_batch_2.csv", b2)
    write_csv(OUTPUT_DIR / "events_batch_3.csv", b3)

    # Drift batch has extra column
    drift_fields = list(b1[0].keys()) + ["ambient_temp_c"]
    write_csv(OUTPUT_DIR / "events_batch_drift.csv", b_drift, fieldnames=drift_fields)

    print("[SUCCESS] Data generation complete:")
    print(f" - drivers.csv: {len(drivers)} records")
    print(f" - vehicles.csv: {len(vehicles)} records")
    print(f" - events_batch_1.csv: {len(b1)} records")
    print(f" - events_batch_2.csv: {len(b2)} records")
    print(f" - events_batch_3.csv: {len(b3)} records")
    print(f" - events_batch_drift.csv: {len(b_drift)} records (schema drift demonstrated)")
    print("=" * 60)


if __name__ == "__main__":
    run_generation()
