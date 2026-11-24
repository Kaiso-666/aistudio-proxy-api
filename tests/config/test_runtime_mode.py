import sys

import pytest

from config.runtime_mode import (
    browser_endpoint,
    browser_kind,
    is_termux,
    runtime_mode,
    runtime_snapshot,
    runtime_temp_dir,
)

TERMUX_PREFIX = "/data/data/com.termux/files/usr"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every case starts from a non-Termux, unconfigured host."""
    for name in (
        "RUNTIME_MODE",
        "TERMUX_VERSION",
        "BROWSER_CDP_ENDPOINT",
        "BROWSER_WS_ENDPOINT",
        "CAMOUFOX_WS_ENDPOINT",
        "BROWSER_KIND",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PREFIX", "/usr")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    return monkeypatch


def test_default_is_standard(clean_env):
    assert is_termux() is False
    assert runtime_mode() == "standard"


@pytest.mark.parametrize("value", ["termux", "attach", "android", "TERMUX"])
def test_explicit_termux(clean_env, value):
    clean_env.setenv("RUNTIME_MODE", value)
    assert runtime_mode() == "termux"


@pytest.mark.parametrize("value", ["standard", "normal", "local", "camoufox"])
def test_explicit_standard_wins_over_detection(clean_env, value):
    clean_env.setenv("RUNTIME_MODE", value)
    clean_env.setenv("TERMUX_VERSION", "0.118")
    assert is_termux() is True
    assert runtime_mode() == "standard"


def test_auto_detects_each_termux_marker(clean_env):
    clean_env.setenv("RUNTIME_MODE", "auto")
    assert runtime_mode() == "standard"

    clean_env.setenv("TERMUX_VERSION", "0.118")
    assert runtime_mode() == "termux"

    clean_env.delenv("TERMUX_VERSION")
    clean_env.setenv("PREFIX", TERMUX_PREFIX)
    assert runtime_mode() == "termux"

    clean_env.setenv("PREFIX", "/usr")
    clean_env.setattr(sys, "executable", TERMUX_PREFIX + "/bin/python")
    assert runtime_mode() == "termux"


def test_auto_is_not_the_default(clean_env):
    """Auto-detection has to be asked for, so a test host cannot flip the mode."""
    clean_env.setenv("TERMUX_VERSION", "0.118")
    assert is_termux() is True
    assert runtime_mode() == "standard"


def test_unknown_mode_is_standard(clean_env):
    clean_env.setenv("RUNTIME_MODE", "banana")
    assert runtime_mode() == "standard"


def test_endpoint_precedence(clean_env):
    assert browser_endpoint() == ""

    clean_env.setenv("CAMOUFOX_WS_ENDPOINT", "ws://launcher/one")
    assert browser_endpoint() == "ws://launcher/one"

    clean_env.setenv("BROWSER_WS_ENDPOINT", "ws://operator/two")
    assert browser_endpoint() == "ws://operator/two"

    clean_env.setenv("BROWSER_CDP_ENDPOINT", "http://127.0.0.1:9222")
    assert browser_endpoint() == "http://127.0.0.1:9222"

    clean_env.setenv("BROWSER_CDP_ENDPOINT", "   ")
    assert browser_endpoint() == "ws://operator/two"


def test_browser_kind_follows_scheme(clean_env):
    assert browser_kind() == "none"
    assert browser_kind("http://127.0.0.1:9222") == "chromium"
    assert browser_kind("https://host:9222") == "chromium"
    assert browser_kind("ws://host:9222/devtools/browser/x") == "firefox"


def test_browser_kind_override(clean_env):
    clean_env.setenv("BROWSER_KIND", "chromium")
    assert browser_kind("ws://host:9222/devtools/browser/x") == "chromium"

    clean_env.setenv("BROWSER_KIND", "camoufox")
    assert browser_kind("http://127.0.0.1:9222") == "firefox"

    clean_env.setenv("BROWSER_KIND", "nonsense")
    assert browser_kind("http://127.0.0.1:9222") == "chromium"


def test_temp_dir_falls_back_when_prefix_tmp_is_missing(clean_env):
    clean_env.setenv("PREFIX", "/nonexistent/prefix")
    assert runtime_temp_dir()


def test_snapshot_shape(clean_env):
    clean_env.setenv("RUNTIME_MODE", "termux")
    clean_env.setenv("BROWSER_CDP_ENDPOINT", "http://127.0.0.1:9222")
    snapshot = runtime_snapshot()

    assert snapshot["mode"] == "termux"
    assert snapshot["browser"]["kind"] == "chromium"
    assert snapshot["browser"]["configured"] is True
    assert snapshot["browser"]["external"] is True
    assert snapshot["tempDir"]
