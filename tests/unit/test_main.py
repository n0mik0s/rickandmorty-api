"""
Unit tests for rickandmorty-api / main.py  (matches updated main.py)

Run with:  uv run pytest tests/unit/ -v
"""

import json
import logging
import sys
import tempfile
import pathlib
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

# ── Provide dummy config files before the module is imported ─────────────────
_tmp = pathlib.Path(tempfile.mkdtemp())
(_tmp / "secrets.json").write_text(
    json.dumps({"user": "u", "password": "p", "host": "localhost", "dbname": "db"})
)
(_tmp / "config.yaml").write_text("log_level: INFO\n")

# Patch sys.argv so argparse uses our dummy paths instead of pytest's argv
sys.argv = [
    "main.py",
    "--config",
    str(_tmp / "config.yaml"),
    "--secret",
    str(_tmp / "secrets.json"),
]

import main  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Replace lifespan so TestClient never attempts a real DB connection
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _noop_lifespan(app):
    yield


main.app.router.lifespan_context = _noop_lifespan

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# JsonFormatter
# ─────────────────────────────────────────────────────────────────────────────


class TestJsonFormatter:
    def _make_record(self, level, msg, name="test"):
        r = logging.LogRecord(
            name=name,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return r

    def test_output_is_valid_json(self):
        parsed = json.loads(main.JsonFormatter().format(self._make_record(logging.INFO, "hi")))
        assert isinstance(parsed, dict)

    def test_message_field(self):
        parsed = json.loads(
            main.JsonFormatter().format(self._make_record(logging.INFO, "test msg"))
        )
        assert parsed["message"] == "test msg"

    def test_level_info(self):
        parsed = json.loads(main.JsonFormatter().format(self._make_record(logging.INFO, "")))
        assert parsed["level"] == "INFO"

    def test_level_error(self):
        parsed = json.loads(main.JsonFormatter().format(self._make_record(logging.ERROR, "")))
        assert parsed["level"] == "ERROR"

    def test_time_field_present(self):
        parsed = json.loads(main.JsonFormatter().format(self._make_record(logging.DEBUG, "")))
        assert "time" in parsed

    def test_logger_name_field(self):
        parsed = json.loads(
            main.JsonFormatter().format(self._make_record(logging.WARNING, "", name="mylogger"))
        )
        assert parsed["logger"] == "mylogger"


# ─────────────────────────────────────────────────────────────────────────────
# rget  — now always returns {"status": bool, "content": ...}, never raises
# ─────────────────────────────────────────────────────────────────────────────


class TestRget:
    @patch("main.requests.get")
    def test_success_status_true(self, mock_get):
        import requests as _req

        mock_resp = MagicMock()
        mock_resp.status_code = _req.codes.ok
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})

        assert result["status"] is True
        assert result["content"] is mock_resp

    @patch("main.requests.get")
    def test_non_ok_status_returns_false(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})

        assert result["status"] is False
        assert result["content"] == "Request status not OK"

    @patch("main.requests.get")
    def test_http_error_exception_caught(self, mock_get):
        import requests as _req

        mock_get.side_effect = _req.exceptions.HTTPError("http error")

        result = main.rget("http://example.com", {})

        assert result["status"] is False
        assert result["content"] is not None

    @patch("main.requests.get")
    def test_connection_error_caught(self, mock_get):
        import requests as _req

        mock_get.side_effect = _req.exceptions.ConnectionError("conn refused")

        result = main.rget("http://example.com", {})

        assert result["status"] is False

    @patch("main.requests.get")
    def test_generic_exception_caught(self, mock_get):
        mock_get.side_effect = RuntimeError("something exploded")

        result = main.rget("http://example.com", {})

        assert result["status"] is False

    @patch("main.requests.get")
    def test_timeout_is_passed(self, mock_get):
        import requests as _req

        mock_resp = MagicMock()
        mock_resp.status_code = _req.codes.ok
        mock_get.return_value = mock_resp

        main.rget("http://example.com", {"k": "v"})

        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") == (5, 30)

    @patch("main.requests.get")
    def test_returns_dict_shape_on_success(self, mock_get):
        import requests as _req

        mock_resp = MagicMock()
        mock_resp.status_code = _req.codes.ok
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})

        assert set(result.keys()) == {"status", "content"}

    @patch("main.requests.get")
    def test_returns_dict_shape_on_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = main.rget("http://example.com", {})

        assert set(result.keys()) == {"status", "content"}


# ─────────────────────────────────────────────────────────────────────────────
# /data — input validation (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetDataValidation:
    def test_invalid_sort_order_returns_400(self):
        resp = client.get("/data?sort_field=id&sort_order=INVALID")
        assert resp.status_code == 400
        assert "ASC or DESC" in resp.json()["detail"]

    def test_invalid_sort_field_returns_400(self):
        resp = client.get("/data?sort_field=name&sort_order=ASC")
        assert resp.status_code == 400
        assert "id or data" in resp.json()["detail"]

    def test_missing_params_returns_422(self):
        resp = client.get("/data")
        assert resp.status_code == 422

    def test_sort_order_case_insensitive_asc(self):
        # Validation passes for lowercase — any failure must not be a validation 400
        resp = client.get("/data?sort_field=id&sort_order=asc")
        if resp.status_code == 400:
            assert "ASC or DESC" not in resp.json().get("detail", "")

    def test_sort_order_case_insensitive_desc(self):
        resp = client.get("/data?sort_field=id&sort_order=desc")
        if resp.status_code == 400:
            assert "ASC or DESC" not in resp.json().get("detail", "")

    def test_valid_sort_field_data(self):
        # Validation passes — only assert it is NOT a validation 400
        resp = client.get("/data?sort_field=data&sort_order=ASC")
        if resp.status_code == 400:
            assert "id or data" not in resp.json().get("detail", "")


# ─────────────────────────────────────────────────────────────────────────────
# /db-mon — input validation (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────


class TestDbMonValidation:
    def test_unknown_aspect_returns_400(self):
        resp = client.get("/db-mon?aspect=garbage")
        assert resp.status_code == 400
        assert "Unrecognized aspect" in resp.json()["detail"]

    def test_missing_aspect_returns_422(self):
        resp = client.get("/db-mon")
        assert resp.status_code == 422

    def test_injection_attempt_rejected(self):
        resp = client.get("/db-mon?aspect=conn; DROP TABLE character;--")
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# /sync — route wiring & rget failure handling (no network, no DB)
# ─────────────────────────────────────────────────────────────────────────────


class TestSyncRoute:
    def test_missing_params_returns_422(self):
        resp = client.post("/sync")
        assert resp.status_code == 422

    @patch("main.rget", return_value={"status": False, "content": "connection error"})
    def test_failed_rget_handled_gracefully(self, _):
        """When rget returns status=False the while loop exits; endpoint should not 500."""
        resp = client.post("/sync?source_url=unreachable.invalid&resource=character")
        assert resp.status_code < 500
