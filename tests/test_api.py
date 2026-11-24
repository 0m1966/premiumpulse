"""API integration and security tests using FastAPI TestClient."""

from fastapi.testclient import TestClient
import pytest
from api.main import app

client = TestClient(app)
VALID_API_KEY = "pp-dev-secret-key-98765"


def test_health_endpoint_no_auth_required():
    """Health check must be publicly accessible without credentials."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mode"] in ["LIVE", "SNAPSHOT"]
    assert "scorecard_version" in data


def test_auth_rejection_missing_or_invalid_key():
    """Protected endpoints must reject requests with missing or invalid X-API-Key."""
    # Missing key
    res_missing = client.get("/drivers")
    assert res_missing.status_code == 401

    # Invalid key
    res_invalid = client.get("/drivers", headers={"X-API-Key": "wrong-key"})
    assert res_invalid.status_code == 401


def test_list_drivers_success():
    """List drivers returns valid paginated list with valid API key."""
    response = client.get(
        "/drivers?limit=10&offset=0",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    drivers = response.json()
    assert isinstance(drivers, list)
    assert len(drivers) <= 10
    if drivers:
        assert "driver_id" in drivers[0]
        assert "monthly_premium" in drivers[0]


def test_get_driver_score_and_quote_success():
    """Fetch specific driver score and quote."""
    # Score
    res_score = client.get(
        "/drivers/DRV-00001/score",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res_score.status_code == 200
    score_data = res_score.json()
    assert score_data["driver_id"] == "DRV-00001"
    assert "risk_score" in score_data

    # Quote
    res_quote = client.get(
        "/drivers/DRV-00001/quote",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res_quote.status_code == 200
    quote_data = res_quote.json()
    assert quote_data["driver_id"] == "DRV-00001"
    assert "monthly_premium" in quote_data
    assert "breakdown" in quote_data


def test_quote_simulation_endpoint():
    """Simulate quote what-if returns projected score and savings."""
    payload = {
        "driver_id": "DRV-00001",
        "hard_brake_per_100km": 1.0,
        "hard_accel_per_100km": 0.5,
        "speeding_pct": 2.0,
        "night_pct": 1.0,
        "phone_min_per_100km": 0.0,
        "annual_km_declared": 10000,
    }
    response = client.post(
        "/quote/simulate",
        json=payload,
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    sim_data = response.json()
    assert sim_data["driver_id"] == "DRV-00001"
    assert "projected_risk_score" in sim_data
    assert "monthly_savings" in sim_data


def test_guidelines_ask_endpoint():
    """Test guideline Q&A endpoint."""
    response = client.post(
        "/guidelines/ask",
        json={"question": "What is the minimum driving distance required for telematics rating?"},
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "cited_clause_ids" in data


def test_no_secret_leakage_in_error_responses():
    """Verify error responses never leak tokens, database queries, or server internals."""
    res_bad = client.get(
        "/drivers/DRV-99999/score",
        headers={"X-API-Key": VALID_API_KEY},
    )
    assert res_bad.status_code == 404
    err_text = res_bad.text.lower()
    assert "password" not in err_text
    assert "token" not in err_text
    assert "select " not in err_text
    assert "traceback" not in err_text
