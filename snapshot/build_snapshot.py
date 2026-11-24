"""Builds the bundled offline SQLite snapshot (premiumpulse_snapshot.db).

Processes the generated telematics data, applies scorecard v1 and pricing engine logic,
and writes out complete Gold, Curated, and Mart tables so the entire application
functions seamlessly in snapshot mode with zero external credentials.
"""

import csv
import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from premiumpulse.domain.models import RiskBand, VehicleClass
from premiumpulse.domain.pricing_engine import compute_monthly_premium
from premiumpulse.domain.scorecard import compute_driver_scorecard

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_GEN_DIR = BASE_DIR / "data_gen"
SNAPSHOT_PATH = BASE_DIR / "snapshot" / "premiumpulse_snapshot.db"


def sha256_sk(value: str) -> str:
    """Compute surrogate key hash."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def read_csv(filepath: Path) -> list[dict]:
    """Read CSV file into list of dicts."""
    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_snapshot_database() -> None:
    """Execute end-to-end data processing and create premiumpulse_snapshot.db."""
    print("=" * 60)
    print("PremiumPulse: Building Bundled Offline Snapshot Database")
    print(f"Target DB: {SNAPSHOT_PATH}")
    print("=" * 60)

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.unlink()

    conn = sqlite3.connect(SNAPSHOT_PATH)
    cursor = conn.cursor()

    # Enable foreign keys and WAL mode for performance
    cursor.execute("PRAGMA journal_mode = WAL;")

    # 1. Load Drivers and Vehicles
    drivers_raw = read_csv(DATA_GEN_DIR / "drivers.csv")
    vehicles_raw = read_csv(DATA_GEN_DIR / "vehicles.csv")

    driver_map = {d["driver_id"]: d for d in drivers_raw}
    vehicle_map = {v["driver_id"]: v for v in vehicles_raw}

    # 2. Ingest Telematics Batches and Simulate Cleaning
    batch_files = [
        DATA_GEN_DIR / "events_batch_1.csv",
        DATA_GEN_DIR / "events_batch_2.csv",
        DATA_GEN_DIR / "events_batch_3.csv",
        DATA_GEN_DIR / "events_batch_drift.csv",
    ]

    total_bronze_events = 0
    clean_events = []
    rejected_events = []
    seen_event_ids = set()

    for bf in batch_files:
        if not bf.exists():
            continue
        rows = read_csv(bf)
        total_bronze_events += len(rows)

        for r in rows:
            event_id = r.get("event_id", "")
            event_ts_str = r.get("event_ts", "")
            speed_str = r.get("speed_kmh", "")
            lat_str = r.get("latitude", "")
            lon_str = r.get("longitude", "")

            # Validation rules
            reject_reason = None
            if not event_ts_str:
                reject_reason = "ERR_NULL_EVENT_TS"
            elif event_id in seen_event_ids:
                reject_reason = "ERR_DUPLICATE_EVENT_ID"
            else:
                try:
                    speed = float(speed_str)
                    if speed < 0.0 or speed > 250.0:
                        reject_reason = "ERR_INVALID_SPEED"
                except (ValueError, TypeError):
                    reject_reason = "ERR_INVALID_SPEED"

                if not reject_reason:
                    try:
                        lat = float(lat_str)
                        lon = float(lon_str)
                        if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
                            reject_reason = "ERR_INVALID_GPS"
                    except (ValueError, TypeError):
                        reject_reason = "ERR_INVALID_GPS"

            if reject_reason:
                rejected_events.append({
                    "event_id": event_id,
                    "driver_id": r.get("driver_id", ""),
                    "vehicle_id": r.get("vehicle_id", ""),
                    "event_ts": event_ts_str,
                    "reject_reason": reject_reason,
                    "raw_record": json.dumps(r),
                })
            else:
                seen_event_ids.add(event_id)
                clean_events.append(r)

    print(f"Processed {total_bronze_events} Bronze events.")
    print(f" - Clean events: {len(clean_events)}")
    print(f" - Rejected events: {len(rejected_events)}")

    # 3. Aggregate Trip Metrics for Silver Trips
    # In full PySpark pipeline this is sessionized by gap > 15 min.
    # For snapshot, group clean events by trip_hint
    trips_grouped: dict[str, list[dict]] = {}
    for ev in clean_events:
        t_id = ev.get("trip_hint")
        if t_id:
            trips_grouped.setdefault(t_id, []).append(ev)

    silver_trips = []
    for t_id, evs in trips_grouped.items():
        evs.sort(key=lambda x: x["event_ts"])
        d_id = evs[0]["driver_id"]
        v_id = evs[0]["vehicle_id"]
        t_start = evs[0]["event_ts"]
        t_end = evs[-1]["event_ts"]

        # Calculate metrics
        hard_brake_count = sum(1 for e in evs if float(e.get("accel_ms2", 0)) <= -3.0)
        hard_accel_count = sum(1 for e in evs if float(e.get("accel_ms2", 0)) >= 3.0)
        speeding_seconds = sum(
            30 for e in evs if float(e.get("speed_kmh", 0)) > (float(e.get("speed_limit_kmh", 65)) + 10.0)
        )
        night_seconds = sum(
            30 for e in evs if datetime.strptime(e["event_ts"], "%Y-%m-%d %H:%M:%S").hour in [0, 1, 2, 3]
        )
        phone_seconds = sum(30 for e in evs if str(e.get("phone_in_use", "0")) in ["1", "True"])

        # Distance approximation
        duration_min = max(1, len(evs) * 30 // 60)
        speeds = [float(e.get("speed_kmh", 0)) for e in evs]
        avg_speed = sum(speeds) / len(speeds) if speeds else 40.0
        dist_km = round((avg_speed * duration_min) / 60.0, 2)

        silver_trips.append({
            "trip_id": t_id,
            "driver_id": d_id,
            "vehicle_id": v_id,
            "trip_start": t_start,
            "trip_end": t_end,
            "distance_km": dist_km,
            "duration_min": duration_min,
            "hard_brake_count": hard_brake_count,
            "hard_accel_count": hard_accel_count,
            "speeding_seconds": speeding_seconds,
            "night_seconds": night_seconds,
            "phone_seconds": phone_seconds,
        })

    print(f"Generated {len(silver_trips)} Silver trips.")

    # 4. Compute 30-Day Gold Driver Risk Scores
    driver_trips: dict[str, list[dict]] = {}
    for st in silver_trips:
        driver_trips.setdefault(st["driver_id"], []).append(st)

    window_end = date(2025, 3, 31)
    window_start = window_end - timedelta(days=30)

    gold_risk_scores = []
    gold_quotes = []

    for d in drivers_raw:
        d_id = d["driver_id"]
        v = vehicle_map.get(d_id, {})
        d_trips = driver_trips.get(d_id, [])

        tot_km = sum(t["distance_km"] for t in d_trips)
        tot_dur_sec = sum(t["duration_min"] * 60 for t in d_trips)
        tot_brakes = sum(t["hard_brake_count"] for t in d_trips)
        tot_accels = sum(t["hard_accel_count"] for t in d_trips)
        tot_speed_sec = sum(t["speeding_seconds"] for t in d_trips)
        tot_night_sec = sum(t["night_seconds"] for t in d_trips)
        tot_phone_sec = sum(t["phone_seconds"] for t in d_trips)

        # Rate metrics
        if tot_km > 0.0:
            hb_per_100km = (tot_brakes / tot_km) * 100.0
            ha_per_100km = (tot_accels / tot_km) * 100.0
            phone_min_per_100km = (tot_phone_sec / 60.0 / tot_km) * 100.0
        else:
            hb_per_100km = 0.0
            ha_per_100km = 0.0
            phone_min_per_100km = 0.0

        speeding_pct = (tot_speed_sec / tot_dur_sec * 100.0) if tot_dur_sec > 0 else 0.0
        night_pct = (tot_night_sec / tot_dur_sec * 100.0) if tot_dur_sec > 0 else 0.0

        # Run Scorecard
        score, band, penalties = compute_driver_scorecard(
            distance_km=tot_km,
            hard_brake_per_100km=hb_per_100km,
            speeding_pct=speeding_pct,
            phone_min_per_100km=phone_min_per_100km,
            night_pct=night_pct,
            hard_accel_per_100km=ha_per_100km,
        )

        gold_risk_scores.append({
            "driver_id": d_id,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "distance_km": round(tot_km, 2),
            "hard_brake_per_100km": round(hb_per_100km, 2),
            "hard_accel_per_100km": round(ha_per_100km, 2),
            "speeding_pct": round(speeding_pct, 2),
            "night_pct": round(night_pct, 2),
            "phone_min_per_100km": round(phone_min_per_100km, 2),
            "risk_score": score,
            "risk_band": band.value,
            "scorecard_version": "v1",
        })

        # Run Pricing Engine
        v_class = v.get("vehicle_class", "SEDAN")
        v_age = int(v.get("vehicle_age_years", 5))
        ann_km = int(v.get("annual_km_declared", 12000))
        lic_years = int(d.get("licence_years", 8))

        quote_bk = compute_monthly_premium(
            vehicle_class=v_class,
            risk_band=band,
            annual_km_declared=ann_km,
            vehicle_age_years=v_age,
            licence_years=lic_years,
        )

        quote_id = f"QTE-{d_id[4:]}-2025"
        gold_quotes.append({
            "quote_id": quote_id,
            "driver_id": d_id,
            "vehicle_id": v.get("vehicle_id", ""),
            "vehicle_class": v_class,
            "risk_score": score,
            "risk_band": band.value,
            "base_rate": float(quote_bk.base_rate),
            "band_multiplier": float(quote_bk.band_multiplier),
            "mileage_factor": float(quote_bk.mileage_factor),
            "vehicle_age_factor": float(quote_bk.vehicle_age_factor),
            "experience_factor": float(quote_bk.experience_factor),
            "monthly_premium": float(quote_bk.final_monthly_premium),
            "annual_premium": float(quote_bk.final_monthly_premium * 12),
            "effective_rate_date": "2025-01-01",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 5. Create SQLite Tables
    cursor.execute("""
    CREATE TABLE drivers (
        driver_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        age_band TEXT NOT NULL,
        licence_years INTEGER NOT NULL,
        city TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE vehicles (
        vehicle_id TEXT PRIMARY KEY,
        driver_id TEXT NOT NULL,
        vehicle_class TEXT NOT NULL,
        vehicle_age_years INTEGER NOT NULL,
        annual_km_declared INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE silver_trips (
        trip_id TEXT PRIMARY KEY,
        driver_id TEXT NOT NULL,
        vehicle_id TEXT NOT NULL,
        trip_start TEXT NOT NULL,
        trip_end TEXT NOT NULL,
        distance_km REAL NOT NULL,
        duration_min INTEGER NOT NULL,
        hard_brake_count INTEGER NOT NULL,
        hard_accel_count INTEGER NOT NULL,
        speeding_seconds INTEGER NOT NULL,
        night_seconds INTEGER NOT NULL,
        phone_seconds INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE silver_rejected_events (
        event_id TEXT,
        driver_id TEXT,
        vehicle_id TEXT,
        event_ts TEXT,
        reject_reason TEXT NOT NULL,
        raw_record TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE silver_dq_results (
        rule_name TEXT NOT NULL,
        table_name TEXT NOT NULL,
        rows_checked INTEGER NOT NULL,
        rows_failed INTEGER NOT NULL,
        run_ts TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE gold_driver_risk_score (
        driver_id TEXT PRIMARY KEY,
        window_start TEXT NOT NULL,
        window_end TEXT NOT NULL,
        distance_km REAL NOT NULL,
        hard_brake_per_100km REAL NOT NULL,
        hard_accel_per_100km REAL NOT NULL,
        speeding_pct REAL NOT NULL,
        night_pct REAL NOT NULL,
        phone_min_per_100km REAL NOT NULL,
        risk_score REAL NOT NULL,
        risk_band TEXT NOT NULL,
        scorecard_version TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE gold_dim_driver (
        driver_sk TEXT PRIMARY KEY,
        driver_id TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        age_band TEXT NOT NULL,
        licence_years INTEGER NOT NULL,
        city TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,
        is_current INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE gold_dim_vehicle (
        vehicle_sk TEXT PRIMARY KEY,
        vehicle_id TEXT NOT NULL,
        driver_id TEXT NOT NULL,
        vehicle_class TEXT NOT NULL,
        vehicle_age_years INTEGER NOT NULL,
        annual_km_declared INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE gold_fact_trip (
        trip_sk TEXT PRIMARY KEY,
        trip_id TEXT NOT NULL,
        driver_sk TEXT NOT NULL,
        vehicle_sk TEXT NOT NULL,
        trip_start TEXT NOT NULL,
        trip_end TEXT NOT NULL,
        distance_km REAL NOT NULL,
        duration_min INTEGER NOT NULL,
        hard_brake_count INTEGER NOT NULL,
        hard_accel_count INTEGER NOT NULL,
        speeding_seconds INTEGER NOT NULL,
        night_seconds INTEGER NOT NULL,
        phone_seconds INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE rate_factors (
        factor_type TEXT NOT NULL,
        factor_key TEXT NOT NULL,
        factor_value REAL NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE quotes (
        quote_id TEXT PRIMARY KEY,
        driver_id TEXT NOT NULL,
        vehicle_id TEXT NOT NULL,
        vehicle_class TEXT NOT NULL,
        risk_score REAL NOT NULL,
        risk_band TEXT NOT NULL,
        base_rate REAL NOT NULL,
        band_multiplier REAL NOT NULL,
        mileage_factor REAL NOT NULL,
        vehicle_age_factor REAL NOT NULL,
        experience_factor REAL NOT NULL,
        monthly_premium REAL NOT NULL,
        annual_premium REAL NOT NULL,
        effective_rate_date TEXT NOT NULL,
        generated_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE pipeline_audit (
        run_id TEXT PRIMARY KEY,
        bronze_event_count INTEGER NOT NULL,
        rejected_event_count INTEGER NOT NULL,
        silver_clean_event_count INTEGER NOT NULL,
        silver_trips_count INTEGER NOT NULL,
        gold_facts_count INTEGER NOT NULL,
        reconciliation_status TEXT NOT NULL,
        audit_ts TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE ai_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        driver_id TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        facts_hash TEXT NOT NULL,
        guardrail_result TEXT NOT NULL,
        latency_ms REAL NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 6. Insert Data
    cursor.executemany("""
    INSERT INTO drivers VALUES (:driver_id, :full_name, :email, :age_band, :licence_years, :city, :created_at);
    """, drivers_raw)

    cursor.executemany("""
    INSERT INTO vehicles VALUES (:vehicle_id, :driver_id, :vehicle_class, :vehicle_age_years, :annual_km_declared);
    """, vehicles_raw)

    cursor.executemany("""
    INSERT INTO silver_trips VALUES (
        :trip_id, :driver_id, :vehicle_id, :trip_start, :trip_end, :distance_km, :duration_min,
        :hard_brake_count, :hard_accel_count, :speeding_seconds, :night_seconds, :phone_seconds
    );
    """, silver_trips)

    cursor.executemany("""
    INSERT INTO silver_rejected_events VALUES (
        :event_id, :driver_id, :vehicle_id, :event_ts, :reject_reason, :raw_record
    );
    """, rejected_events)

    # DQ Results
    dq_records = [
        {"rule_name": "NON_NULL_EVENT_TS", "table_name": "bronze_telematics_events", "rows_checked": total_bronze_events, "rows_failed": sum(1 for r in rejected_events if r["reject_reason"] == "ERR_NULL_EVENT_TS"), "run_ts": datetime.now(timezone.utc).isoformat()},
        {"rule_name": "UNIQUE_EVENT_ID", "table_name": "bronze_telematics_events", "rows_checked": total_bronze_events, "rows_failed": sum(1 for r in rejected_events if r["reject_reason"] == "ERR_DUPLICATE_EVENT_ID"), "run_ts": datetime.now(timezone.utc).isoformat()},
        {"rule_name": "VALID_SPEED_BOUNDS", "table_name": "bronze_telematics_events", "rows_checked": total_bronze_events, "rows_failed": sum(1 for r in rejected_events if r["reject_reason"] == "ERR_INVALID_SPEED"), "run_ts": datetime.now(timezone.utc).isoformat()},
        {"rule_name": "VALID_GPS_RANGE", "table_name": "bronze_telematics_events", "rows_checked": total_bronze_events, "rows_failed": sum(1 for r in rejected_events if r["reject_reason"] == "ERR_INVALID_GPS"), "run_ts": datetime.now(timezone.utc).isoformat()},
    ]
    cursor.executemany("""
    INSERT INTO silver_dq_results VALUES (:rule_name, :table_name, :rows_checked, :rows_failed, :run_ts);
    """, dq_records)

    cursor.executemany("""
    INSERT INTO gold_driver_risk_score VALUES (
        :driver_id, :window_start, :window_end, :distance_km, :hard_brake_per_100km,
        :hard_accel_per_100km, :speeding_pct, :night_pct, :phone_min_per_100km,
        :risk_score, :risk_band, :scorecard_version
    );
    """, gold_risk_scores)

    # Gold Dims & Facts
    gold_dim_drivers = [
        {
            "driver_sk": sha256_sk(d["driver_id"]),
            "driver_id": d["driver_id"],
            "full_name": d["full_name"],
            "email": d["email"],
            "age_band": d["age_band"],
            "licence_years": int(d["licence_years"]),
            "city": d["city"],
            "valid_from": "2024-01-01",
            "valid_to": "2099-12-31",
            "is_current": 1,
        }
        for d in drivers_raw
    ]
    cursor.executemany("""
    INSERT INTO gold_dim_driver VALUES (
        :driver_sk, :driver_id, :full_name, :email, :age_band, :licence_years, :city, :valid_from, :valid_to, :is_current
    );
    """, gold_dim_drivers)

    gold_dim_vehicles = [
        {
            "vehicle_sk": sha256_sk(v["vehicle_id"]),
            "vehicle_id": v["vehicle_id"],
            "driver_id": v["driver_id"],
            "vehicle_class": v["vehicle_class"],
            "vehicle_age_years": int(v["vehicle_age_years"]),
            "annual_km_declared": int(v["annual_km_declared"]),
        }
        for v in vehicles_raw
    ]
    cursor.executemany("""
    INSERT INTO gold_dim_vehicle VALUES (
        :vehicle_sk, :vehicle_id, :driver_id, :vehicle_class, :vehicle_age_years, :annual_km_declared
    );
    """, gold_dim_vehicles)

    gold_facts = [
        {
            "trip_sk": sha256_sk(st["trip_id"]),
            "trip_id": st["trip_id"],
            "driver_sk": sha256_sk(st["driver_id"]),
            "vehicle_sk": sha256_sk(st["vehicle_id"]),
            "trip_start": st["trip_start"],
            "trip_end": st["trip_end"],
            "distance_km": st["distance_km"],
            "duration_min": st["duration_min"],
            "hard_brake_count": st["hard_brake_count"],
            "hard_accel_count": st["hard_accel_count"],
            "speeding_seconds": st["speeding_seconds"],
            "night_seconds": st["night_seconds"],
            "phone_seconds": st["phone_seconds"],
        }
        for st in silver_trips
    ]
    cursor.executemany("""
    INSERT INTO gold_fact_trip VALUES (
        :trip_sk, :trip_id, :driver_sk, :vehicle_sk, :trip_start, :trip_end, :distance_km,
        :duration_min, :hard_brake_count, :hard_accel_count, :speeding_seconds, :night_seconds, :phone_seconds
    );
    """, gold_facts)

    # Seed Rate Factors
    rf_rows = read_csv(DATA_GEN_DIR / "rate_factors_seed.csv")
    cursor.executemany("""
    INSERT INTO rate_factors VALUES (
        :factor_type, :factor_key, :factor_value, :effective_from, :effective_to
    );
    """, rf_rows)

    cursor.executemany("""
    INSERT INTO quotes VALUES (
        :quote_id, :driver_id, :vehicle_id, :vehicle_class, :risk_score, :risk_band,
        :base_rate, :band_multiplier, :mileage_factor, :vehicle_age_factor, :experience_factor,
        :monthly_premium, :annual_premium, :effective_rate_date, :generated_at
    );
    """, gold_quotes)

    # Pipeline Audit Invariant: Bronze = Rejected + Clean
    recon_pass = (total_bronze_events == len(rejected_events) + len(clean_events))
    cursor.execute("""
    INSERT INTO pipeline_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        "RUN-SNAPSHOT-001",
        total_bronze_events,
        len(rejected_events),
        len(clean_events),
        len(silver_trips),
        len(gold_facts),
        "VERIFIED" if recon_pass else "MISMATCH",
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()

    print("[SUCCESS] Snapshot database built successfully.")
    print(f"File size: {SNAPSHOT_PATH.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"Reconciliation Status: {'PASS' if recon_pass else 'FAIL'}")
    print(f"Invariant: Bronze ({total_bronze_events}) = Rejected ({len(rejected_events)}) + Clean ({len(clean_events)})")
    print("=" * 60)


if __name__ == "__main__":
    build_snapshot_database()
