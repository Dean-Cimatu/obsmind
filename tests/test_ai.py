"""Tests for core/ai.py — all Anthropic SDK calls are mocked."""

import pytest
from unittest.mock import MagicMock, patch


def make_message(input_tokens=10, output_tokens=5, text="ok"):
    msg = MagicMock()
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    msg.content = [MagicMock(text=text)]
    return msg


# ── model_for ──────────────────────────────────────────────────────────────

def test_model_for_known_task():
    from obsmind.core.ai import model_for, HAIKU
    assert model_for("ping") == HAIKU


def test_model_for_unknown_task():
    from obsmind.core.ai import model_for
    with pytest.raises(ValueError, match="Unknown task"):
        model_for("nonexistent_task")


# ── call ───────────────────────────────────────────────────────────────────

def test_call_returns_ai_response(mocker):
    mocker.patch("obsmind.core.usage.log_usage")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_message(10, 5, "ok")
    mocker.patch("obsmind.core.ai._client", return_value=mock_client)

    from obsmind.core.ai import call
    resp = call("ping", "Reply: ok", max_tokens=5, command="test")

    assert resp.content == "ok"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5
    assert resp.cost_usd >= 0
    assert resp.elapsed_ms >= 0


def test_call_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from obsmind.core.ai import call
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        call("ping", "hi")


def test_call_logs_usage(mocker):
    log_mock = mocker.patch("obsmind.core.ai.log_usage")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_message(3, 2, "x")
    mocker.patch("obsmind.core.ai._client", return_value=mock_client)

    from obsmind.core.ai import call
    call("ping", "hi", command="doctor")
    log_mock.assert_called_once()


def test_meta_line_format(mocker):
    mocker.patch("obsmind.core.usage.log_usage")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_message(10, 5, "ok")
    mocker.patch("obsmind.core.ai._client", return_value=mock_client)

    from obsmind.core.ai import call
    resp = call("ping", "hi")
    line = resp.meta_line()
    assert "haiku" in line
    assert "→" in line
    assert "$" in line


# ── tier_name ──────────────────────────────────────────────────────────────

def test_tier_name():
    from obsmind.core.ai import tier_name, HAIKU, SONNET, OPUS
    assert tier_name(HAIKU)  == "haiku"
    assert tier_name(SONNET) == "sonnet"
    assert tier_name(OPUS)   == "opus"
    assert tier_name("unknown-model") == "unknown-model"
