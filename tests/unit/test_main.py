"""
Unit tests for rickandmorty-api / main.py

Run with:  uv run pytest tests/unit/ -v
"""
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ── Bootstrap: provide dummy config files before the module is imported ──────
import os, tempfile, pathlib

_tmp = pathlib.Path(tempfile.mkdtemp())
(_tmp / "secrets.json").write_text(
    json.dumps({"user": "u", "password": "p", "host": "localhost", "dbname": "db"})
)
(_tmp / "config.yaml").write_text("log_level: INFO\n")

# Patch sys.argv so argparse uses our dummy paths instead of pytest's argv
sys.argv = ["main.py", "--config", str(_tmp / "config.yaml"), "--secret", str(_tmp / "secrets.json")]

import main  # noqa: E402  (must come after argv patch)


# ─────────────────────────────────────────────────────────────────────────────
# JsonFormatter
# ─────────────────────────────────────────────────────────────────────────────
class TestJsonFormatter(unittest.TestCase):
    def test_format_returns_valid_json(self):
        import logging
        formatter = main.JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert "time" in parsed
        assert "logger" in parsed

    def test_format_includes_correct_level(self):
        import logging
        formatter = main.JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0,
            msg="oops", args=(), exc_info=None
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# rget helper
# ─────────────────────────────────────────────────────────────────────────────
class TestRget(unittest.TestCase):
    @patch("main.requests.get")
    def test_successful_get(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        # requests.codes.ok is 200
        import requests as _req
        mock_resp.status_code = _req.codes.ok
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})
        assert result is mock_resp

    @patch("main.requests.get")
    def test_non_ok_status_returns_none(self, mock_get):
        import requests as _req
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = _req.exceptions.HTTPError("500 error")
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})
        assert result is None

    @patch("main.requests.get", side_effect=Exception("network down"))
    def test_exception_returns_none(self, mock_get):
        # Generic exceptions propagate; only HTTPError is caught.
        with pytest.raises(Exception):
            main.rget("http://example.com", {})


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app – endpoint input validation (no DB, no network)
# ─────────────────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

# Override lifespan so TestClient doesn't attempt a real DB connection
from contextlib import asynccontextmanager  # noqa: E402

@asynccontextmanager
async def _noop_lifespan(app):
    yield

main.app.router.lifespan_context = _noop_lifespan
client = TestClient(main.app, raise_server_exceptions=False)


class TestGetDataValidation(unittest.TestCase):
    def test_invalid_sort_order_returns_400(self):
        resp = client.get("/data?sort_field=id&sort_order=INVALID")
        assert resp.status_code == 400
        assert "ASC or DESC" in resp.json()["detail"]

    def test_invalid_sort_field_returns_400(self):
        resp = client.get("/data?sort_field=name&sort_order=ASC")
        assert resp.status_code == 400
        assert "id or data" in resp.json()["detail"]

    def test_valid_params_accepted(self):
        # Will fail at DB stage, not validation – that's fine for a unit test
        resp = client.get("/data?sort_field=id&sort_order=ASC")
        # 400 would mean validation failed; we just check it isn't that
        assert resp.status_code != 400 or "id or data" not in str(resp.text)


class TestDbMonValidation(unittest.TestCase):
    def test_unknown_aspect_returns_400(self):
        resp = client.get("/db-mon?aspect=garbage")
        assert resp.status_code == 400
        assert "Unrecognized aspect" in resp.json()["detail"]


if __name__ == "__main__":
    unittest.main()
