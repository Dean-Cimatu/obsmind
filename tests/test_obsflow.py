"""Tests for core/obsflow.py — subprocess calls are mocked."""

import subprocess
import pytest
from unittest.mock import MagicMock, patch


def make_result(stdout="", stderr="", returncode=0):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


# ── check_available ────────────────────────────────────────────────────────

def test_check_available_found(mocker):
    mocker.patch("shutil.which", return_value="/usr/local/bin/obs")
    from obsmind.core.obsflow import check_available
    assert check_available() == "/usr/local/bin/obs"


def test_check_available_missing(mocker):
    mocker.patch("shutil.which", return_value=None)
    from obsmind.core.obsflow import check_available, ObsFlowNotFoundError
    with pytest.raises(ObsFlowNotFoundError, match="obs CLI not found"):
        check_available()


def test_is_available_true(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/obs")
    from obsmind.core.obsflow import is_available
    assert is_available() is True


def test_is_available_false(mocker):
    mocker.patch("shutil.which", return_value=None)
    from obsmind.core.obsflow import is_available
    assert is_available() is False


# ── _run error handling ────────────────────────────────────────────────────

def test_run_raises_on_nonzero(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/obs")
    mocker.patch("subprocess.run", return_value=make_result(stderr="error", returncode=1))
    from obsmind.core.obsflow import ObsFlowError, _run
    with pytest.raises(ObsFlowError):
        _run(["index", "stats"])


def test_run_raises_not_found_on_missing_binary(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/obs")
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)
    from obsmind.core.obsflow import ObsFlowNotFoundError, _run
    with pytest.raises(ObsFlowNotFoundError):
        _run(["--version"])


# ── write operations ───────────────────────────────────────────────────────

def test_append_section(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/obs")
    mocker.patch("subprocess.run", return_value=make_result(stdout=""))
    from obsmind.core.obsflow import append_section
    append_section("Quick Capture", "test bullet")


def test_capture(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/obs")
    mocker.patch("subprocess.run", return_value=make_result(stdout=""))
    from obsmind.core.obsflow import capture
    capture("buy milk")
