"""Local execution engine replicating the Databricks Medallion pipeline.

Enables full testing, validation, and offline development in CI and local environments
without requiring an active Databricks cluster.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from premiumpulse.domain.scorecard import compute_driver_scorecard


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two GPS points."""
    r = 6371.0  # Earth radius km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def run_local_pipeline(
    raw_events: list[dict],
    drivers: list[dict],
    vehicles: list[dict],
    trip_gap_seconds: int = 900,  # 15 minutes
) -> dict:
    """Execute Bronze -> Silver -> Gold transformation locally.

    Returns:
        dict containing bronze_count, rejected_events, clean_events, silver_trips,
        gold_risk_scores, and reconciliation_status.
    """
    total_bronze = len(raw_events)

    # --- 1. Silver Cleaning & Deduplication ---
    seen_ids = set()
    rejected_events = []
    clean_events = []

    for r in raw_events:
        event_id = r.get("event_id")
        ts_str = r.get("event_ts")
        speed_val = r.get("speed_kmh")
        lat_val = r.get("latitude")
        lon_val = r.get("longitude")

        # Duplicate check
        if event_id in seen_ids:
            rejected_events.append({**r, "reject_reason": "ERR_DUPLICATE_EVENT_ID"})
            continue

        # Null timestamp
        if not ts_str:
            rejected_events.append({**r, "reject_reason": "ERR_NULL_EVENT_TS"})
            continue

        # Valid speed (0..250)
        try:
            speed = float(speed_val)
            if speed < 0.0 or speed > 250.0:
                rejected_events.append({**r, "reject_reason": "ERR_INVALID_SPEED"})
                continue
        except (ValueError, TypeError):
            rejected_events.append({**r, "reject_reason": "ERR_INVALID_SPEED"})
            continue

        # Valid GPS
        try:
            lat = float(lat_val)
            lon = float(lon_val)
            if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
                rejected_events.append({**r, "reject_reason": "ERR_INVALID_GPS"})
                continue
        except (ValueError, TypeError):
            rejected_events.append({**r, "reject_reason": "ERR_INVALID_GPS"})
            continue

        seen_ids.add(event_id)
        clean_events.append({
            **r,
            "speed_kmh": speed,
            "latitude": lat,
            "longitude": lon,
            "accel_ms2": float(r.get("accel_ms2", 0.0)),
            "speed_limit_kmh": float(r.get("speed_limit_kmh", 65.0)),
            "phone_in_use": 1 if str(r.get("phone_in_use", "0")) in ["1", "true", "True"] else 0,
            "parsed_ts": datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S"),
        })

    # --- 2. Silver Sessionization (15 min gap threshold) ---
    clean_events.sort(key=lambda x: (x["driver_id"], x["vehicle_id"], x["parsed_ts"]))

    current_session = []
    trips = []
    trip_id_seq = 1

    for i, ev in enumerate(clean_events):
        if not current_session:
            current_session.append(ev)
            continue

        prev_ev = current_session[-1]
        same_driver = (ev["driver_id"] == prev_ev["driver_id"] and ev["vehicle_id"] == prev_ev["vehicle_id"])
        gap_sec = (ev["parsed_ts"] - prev_ev["parsed_ts"]).total_seconds()

        if same_driver and gap_sec <= trip_gap_seconds:
            current_session.append(ev)
        else:
            # Finalize previous trip
            trips.append(_summarize_trip(current_session, f"LOCAL-TRP-{trip_id_seq:05d}"))
            trip_id_seq += 1
            current_session = [ev]

    if current_session:
        trips.append(_summarize_trip(current_session, f"LOCAL-TRP-{trip_id_seq:05d}"))

    # --- 3. Gold Risk Scores (Scorecard v1) ---
    driver_trips: dict[str, list[dict]] = {}
    for t in trips:
        driver_trips.setdefault(t["driver_id"], []).append(t)

    gold_scores = []
    for d in drivers:
        d_id = d["driver_id"]
        d_t = driver_trips.get(d_id, [])

        tot_dist = sum(t["distance_km"] for t in d_t)
        tot_dur_sec = sum(t["duration_min"] * 60 for t in d_t)
        tot_brakes = sum(t["hard_brake_count"] for t in d_t)
        tot_accels = sum(t["hard_accel_count"] for t in d_t)
        tot_speed_sec = sum(t["speeding_seconds"] for t in d_t)
        tot_night_sec = sum(t["night_seconds"] for t in d_t)
        tot_phone_sec = sum(t["phone_seconds"] for t in d_t)

        hb_rate = (tot_brakes / tot_dist * 100.0) if tot_dist > 0 else 0.0
        ha_rate = (tot_accels / tot_dist * 100.0) if tot_dist > 0 else 0.0
        phone_rate = (tot_phone_sec / 60.0 / tot_dist * 100.0) if tot_dist > 0 else 0.0
        speed_pct = (tot_speed_sec / tot_dur_sec * 100.0) if tot_dur_sec > 0 else 0.0
        night_pct = (tot_night_sec / tot_dur_sec * 100.0) if tot_dur_sec > 0 else 0.0

        score, band, penalties = compute_driver_scorecard(
            distance_km=tot_dist,
            hard_brake_per_100km=hb_rate,
            speeding_pct=speed_pct,
            phone_min_per_100km=phone_rate,
            night_pct=night_pct,
            hard_accel_per_100km=ha_rate,
        )

        gold_scores.append({
            "driver_id": d_id,
            "distance_km": round(tot_dist, 2),
            "risk_score": score,
            "risk_band": band.value,
        })

    # Invariant Checks
    reconciliation_holds = (total_bronze == len(rejected_events) + len(clean_events))
    sum_silver_km = sum(t["distance_km"] for t in trips)
    sum_gold_km = sum(s["distance_km"] for s in gold_scores)
    distance_reconciliation = (round(sum_silver_km, 2) == round(sum_gold_km, 2))

    return {
        "bronze_count": total_bronze,
        "rejected_count": len(rejected_events),
        "clean_count": len(clean_events),
        "silver_trips": trips,
        "gold_scores": gold_scores,
        "reconciliation_holds": reconciliation_holds,
        "distance_reconciliation": distance_reconciliation,
    }


def _summarize_trip(events: list[dict], trip_id: str) -> dict:
    """Compute summary trip facts from list of events."""
    d_id = events[0]["driver_id"]
    v_id = events[0]["vehicle_id"]
    start_ts = events[0]["parsed_ts"]
    end_ts = events[-1]["parsed_ts"]

    duration_min = max(1, int((end_ts - start_ts).total_seconds() / 60))

    # Haversine step sum
    total_km = 0.0
    for idx in range(1, len(events)):
        p1 = events[idx - 1]
        p2 = events[idx]
        total_km += haversine_distance(p1["latitude"], p1["longitude"], p2["latitude"], p2["longitude"])

    hard_brakes = sum(1 for e in events if e["accel_ms2"] <= -3.0)
    hard_accels = sum(1 for e in events if e["accel_ms2"] >= 3.0)
    speeding_sec = sum(30 for e in events if e["speed_kmh"] > (e["speed_limit_kmh"] + 10.0))
    night_sec = sum(30 for e in events if e["parsed_ts"].hour in [0, 1, 2, 3])
    phone_sec = sum(30 for e in events if e["phone_in_use"] == 1)

    return {
        "trip_id": trip_id,
        "driver_id": d_id,
        "vehicle_id": v_id,
        "trip_start": start_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "trip_end": end_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "distance_km": round(total_km, 2),
        "duration_min": duration_min,
        "hard_brake_count": hard_brakes,
        "hard_accel_count": hard_accels,
        "speeding_seconds": speeding_sec,
        "night_seconds": night_sec,
        "phone_seconds": phone_sec,
    }
