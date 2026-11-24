"""Integration tests for local pipeline execution and reconciliation invariants."""

from datetime import datetime, timedelta
import pytest
from databricks.local_pipeline import run_local_pipeline


@pytest.fixture
def sample_pipeline_data():
    """Create a 5-driver fixture with known clean events, duplicates, dirty records, and trip gaps."""
    drivers = [
        {"driver_id": f"DRV-{i:05d}", "city": "Austin", "licence_years": 5}
        for i in range(1, 6)
    ]
    vehicles = [
        {"vehicle_id": f"VEH-{i:05d}", "driver_id": f"DRV-{i:05d}", "vehicle_class": "SEDAN"}
        for i in range(1, 6)
    ]

    base_ts = datetime(2025, 3, 10, 8, 0, 0)
    raw_events = []

    # Driver 1: Has 2 distinct trips separated by 30 minutes (> 15 min gap threshold)
    # Trip 1: 3 events, 30 sec apart
    for s in range(3):
        raw_events.append({
            "event_id": f"EVT-D1-T1-{s}",
            "driver_id": "DRV-00001",
            "vehicle_id": "VEH-00001",
            "event_ts": (base_ts + timedelta(seconds=s * 30)).strftime("%Y-%m-%d %H:%M:%S"),
            "speed_kmh": 60.0,
            "latitude": 30.2672 + (s * 0.001),
            "longitude": -97.7431 + (s * 0.001),
            "accel_ms2": 0.0,
            "speed_limit_kmh": 65.0,
            "phone_in_use": 0,
        })

    # Gap of 30 minutes -> should trigger a new trip!
    t2_start = base_ts + timedelta(minutes=30)
    for s in range(3):
        raw_events.append({
            "event_id": f"EVT-D1-T2-{s}",
            "driver_id": "DRV-00001",
            "vehicle_id": "VEH-00001",
            "event_ts": (t2_start + timedelta(seconds=s * 30)).strftime("%Y-%m-%d %H:%M:%S"),
            "speed_kmh": 50.0,
            "latitude": 30.2700 + (s * 0.001),
            "longitude": -97.7400 + (s * 0.001),
            "accel_ms2": -3.5,  # 1 hard brake per event
            "speed_limit_kmh": 65.0,
            "phone_in_use": 0,
        })

    # Add duplicate event_id for Driver 1
    raw_events.append({
        "event_id": "EVT-D1-T1-0",  # Duplicate!
        "driver_id": "DRV-00001",
        "vehicle_id": "VEH-00001",
        "event_ts": base_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "speed_kmh": 60.0,
        "latitude": 30.2672,
        "longitude": -97.7431,
        "accel_ms2": 0.0,
    })

    # Add dirty speed event (-50 kmh)
    raw_events.append({
        "event_id": "EVT-DIRTY-SPEED",
        "driver_id": "DRV-00002",
        "vehicle_id": "VEH-00002",
        "event_ts": base_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "speed_kmh": -50.0,
        "latitude": 30.2672,
        "longitude": -97.7431,
    })

    # Add dirty GPS event (lat > 90)
    raw_events.append({
        "event_id": "EVT-DIRTY-GPS",
        "driver_id": "DRV-00003",
        "vehicle_id": "VEH-00003",
        "event_ts": base_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "speed_kmh": 40.0,
        "latitude": 120.0,
        "longitude": -97.7431,
    })

    # Drivers 2 to 5 standard trips
    for d_idx in range(2, 6):
        d_id = f"DRV-{d_idx:05d}"
        v_id = f"VEH-{d_idx:05d}"
        for s in range(4):
            raw_events.append({
                "event_id": f"EVT-D{d_idx}-{s}",
                "driver_id": d_id,
                "vehicle_id": v_id,
                "event_ts": (base_ts + timedelta(seconds=s * 30)).strftime("%Y-%m-%d %H:%M:%S"),
                "speed_kmh": 45.0,
                "latitude": 30.2600 + (s * 0.001),
                "longitude": -97.7400 + (s * 0.001),
                "accel_ms2": 0.2,
                "speed_limit_kmh": 65.0,
                "phone_in_use": 1 if s == 0 else 0,
            })

    return raw_events, drivers, vehicles


def test_pipeline_deduplication_and_filtering(sample_pipeline_data):
    """Verify that duplicates, negative speed, and invalid GPS are quarantined to rejected."""
    raw_events, drivers, vehicles = sample_pipeline_data
    res = run_local_pipeline(raw_events, drivers, vehicles)

    assert res["reconciliation_holds"] is True
    # 3 defective events: duplicate, -50 kmh, lat 120
    assert res["rejected_count"] == 3
    assert res["bronze_count"] == res["clean_count"] + res["rejected_count"]


def test_pipeline_trip_sessionization_gap(sample_pipeline_data):
    """Verify that an inactivity gap > 15 minutes splits Driver 1 into 2 distinct trips."""
    raw_events, drivers, vehicles = sample_pipeline_data
    res = run_local_pipeline(raw_events, drivers, vehicles)

    d1_trips = [t for t in res["silver_trips"] if t["driver_id"] == "DRV-00001"]
    assert len(d1_trips) == 2
    assert d1_trips[0]["trip_id"] != d1_trips[1]["trip_id"]


def test_pipeline_zero_loss_distance_reconciliation(sample_pipeline_data):
    """Verify that sum of silver trip distances matches sum of gold fact distances."""
    raw_events, drivers, vehicles = sample_pipeline_data
    res = run_local_pipeline(raw_events, drivers, vehicles)

    assert res["distance_reconciliation"] is True
    assert len(res["gold_scores"]) == 5
