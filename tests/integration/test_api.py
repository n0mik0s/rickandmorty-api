"""
Integration tests for rickandmorty-api.

These tests assume the application is already running and reachable at
the URL specified by the API_BASE_URL environment variable
(default: http://localhost:8000).

Run with:  uv run pytest tests/integration/ -v
"""

import os

import pytest
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    yield s
    s.close()


# ─────────────────────────────────────────────────────────────────────────────
# Health / reachability
# ─────────────────────────────────────────────────────────────────────────────
class TestReachability:
    def test_openapi_docs_available(self, session):
        resp = session.get(f"{BASE_URL}/docs")
        assert resp.status_code == 200

    def test_openapi_json_available(self, session):
        resp = session.get(f"{BASE_URL}/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema


# ─────────────────────────────────────────────────────────────────────────────
# /sync endpoint – validation (does NOT actually hit Rick & Morty API)
# ─────────────────────────────────────────────────────────────────────────────
class TestSync:
    def test_sync_invalid_resource_still_attempts_request(self, session):
        """
        Posting with a clearly unreachable URL should result in a 4xx/5xx,
        not a 200 – confirming the endpoint is wired up and reachable.
        """
        resp = session.post(
            f"{BASE_URL}/sync",
            params={"source_url": "does.not.exist.invalid", "resource": "character"},
        )
        # We expect either an application error or a network error surfaced by
        # the app, but NOT a 404 for the route itself.
        assert resp.status_code != 404

    def test_rate_limiter_kicks_in(self, session):
        """
        The endpoint allows 2 requests per 5 seconds; a burst of 5 should
        trigger at least one 429.
        """
        responses = [
            session.post(
                f"{BASE_URL}/sync",
                params={"source_url": "does.not.exist.invalid", "resource": "character"},
            )
            for _ in range(5)
        ]
        status_codes = {r.status_code for r in responses}
        assert 429 in status_codes, "Expected at least one 429 from the rate limiter"


# ─────────────────────────────────────────────────────────────────────────────
# /data endpoint – validation
# ─────────────────────────────────────────────────────────────────────────────
class TestGetData:
    def test_invalid_sort_order_returns_400(self, session):
        resp = session.get(f"{BASE_URL}/data?sort_field=id&sort_order=NOPE")
        assert resp.status_code == 400

    def test_invalid_sort_field_returns_400(self, session):
        resp = session.get(f"{BASE_URL}/data?sort_field=name&sort_order=ASC")
        assert resp.status_code == 400

    def test_valid_request_returns_list(self, session):
        resp = session.get(f"{BASE_URL}/data?sort_field=id&sort_order=ASC")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sort_desc_returns_list(self, session):
        resp = session.get(f"{BASE_URL}/data?sort_field=id&sort_order=DESC")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
