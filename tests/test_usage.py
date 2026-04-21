"""Tests for core/usage.py."""

import json
import pytest
from pathlib import Path
from datetime import datetime


@pytest.fixture(autouse=True)
def tmp_usage(tmp_path, mocker):
    """Redirect USAGE_FILE and USAGE_DIR to a temp location."""
    mocker.patch("obsmind.core.usage.USAGE_DIR",  tmp_path)
    mocker.patch("obsmind.core.usage.USAGE_FILE", tmp_path / "usage.jsonl")


def test_log_usage_creates_file(tmp_path, mocker):
    mocker.patch("obsmind.core.usage.USAGE_DIR",  tmp_path)
    mocker.patch("obsmind.core.usage.USAGE_FILE", tmp_path / "usage.jsonl")
    from obsmind.core.usage import log_usage
    log_usage("doctor", "ping", "claude-haiku-4-5-20251001", 10, 5, 0.00001)
    assert (tmp_path / "usage.jsonl").exists()


def test_log_usage_appends(tmp_path, mocker):
    uf = tmp_path / "usage.jsonl"
    mocker.patch("obsmind.core.usage.USAGE_DIR",  tmp_path)
    mocker.patch("obsmind.core.usage.USAGE_FILE", uf)
    from obsmind.core.usage import log_usage
    log_usage("a", "ping", "haiku", 1, 1, 0.0)
    log_usage("b", "ping", "haiku", 2, 2, 0.0)
    lines = uf.read_text().strip().split("\n")
    assert len(lines) == 2


def test_read_usage_empty(tmp_path, mocker):
    mocker.patch("obsmind.core.usage.USAGE_FILE", tmp_path / "nonexistent.jsonl")
    from obsmind.core.usage import read_usage
    assert read_usage() == []


def test_read_usage_month_filter(tmp_path, mocker):
    uf = tmp_path / "usage.jsonl"
    mocker.patch("obsmind.core.usage.USAGE_DIR",  tmp_path)
    mocker.patch("obsmind.core.usage.USAGE_FILE", uf)
    uf.write_text(
        json.dumps({"ts": "2026-04-01T00:00:00+00:00", "command": "a", "task": "ping",
                    "model": "haiku", "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0}) + "\n" +
        json.dumps({"ts": "2026-05-01T00:00:00+00:00", "command": "b", "task": "ping",
                    "model": "haiku", "input_tokens": 2, "output_tokens": 2, "cost_usd": 0.0}) + "\n"
    )
    from obsmind.core.usage import read_usage
    april = read_usage(month="2026-04")
    assert len(april) == 1
    assert april[0]["command"] == "a"


def test_summarise_usage():
    from obsmind.core.usage import summarise_usage
    records = [
        {"model": "haiku", "input_tokens": 10, "output_tokens": 5,  "cost_usd": 0.001},
        {"model": "haiku", "input_tokens": 20, "output_tokens": 10, "cost_usd": 0.002},
        {"model": "sonnet","input_tokens": 50, "output_tokens": 25, "cost_usd": 0.01},
    ]
    s = summarise_usage(records)
    assert s["total_calls"] == 3
    assert s["total_input"] == 80
    assert s["total_cost_usd"] == pytest.approx(0.013)
    assert "haiku" in s["by_model"]
    assert s["by_model"]["haiku"]["calls"] == 2
