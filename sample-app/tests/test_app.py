"""Tests for the sample Flask application."""

import json

import pytest

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_html(client):
    """GET / returns HTML with app name and version."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sample App" in resp.data
    assert b"1.0.0" in resp.data


def test_health_returns_json(client):
    """GET /health returns JSON with status, version, timestamp."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data


def test_health_content_type(client):
    """GET /health has application/json content type."""
    resp = client.get("/health")
    assert resp.content_type == "application/json"


def test_not_found(client):
    """Undefined routes return 404 JSON."""
    resp = client.get("/nonexistent")
    assert resp.status_code == 404
    data = json.loads(resp.data)
    assert data["error"] == "Not Found"


def test_trace_id_generated(client):
    """Requests without traceparent generate a trace_id."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_trace_id_from_header(client):
    """Requests with traceparent header propagate trace_id."""
    resp = client.get(
        "/health",
        headers={"traceparent": "00-abcdef1234567890abcdef1234567890-0123456789abcdef-01"},
    )
    assert resp.status_code == 200
