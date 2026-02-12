import os
from pathlib import Path

import pytest


@pytest.fixture
def ahn_dir(tmp_path_factory):
    """Temporary directory for AHN-data."""
    d = tmp_path_factory.mktemp("ahn")
    return d


@pytest.fixture
def bgt_dir(tmp_path_factory):
    """Temporary directory for BGT-data."""
    d = tmp_path_factory.mktemp("bgt")
    return d


@pytest.fixture
def bag_dir(tmp_path_factory):
    """Temporary directory for BAG-data."""
    d = tmp_path_factory.mktemp("bag")
    return d


def _select_temp_root() -> Path:
    candidates = []
    for env_name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    candidates.append(Path.cwd() / ".tmp_pytest_fallback")

    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / "pytest-probe"
            probe.mkdir(exist_ok=True)
            probe.rmdir()
            return root
        except Exception:
            continue

    fallback = Path.cwd() / ".tmp_pytest_fallback"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def pytest_configure(config):
    """Force pytest basetemp to a usable temp root (system temp when possible)."""
    root = _select_temp_root()
    os.environ["PYTEST_TEMP_ROOT"] = str(root)
    base = root / f"pytest-session-{os.getpid()}"
    config.option.basetemp = str(base)


@pytest.fixture(autouse=True)
def _set_temp_env(monkeypatch):
    """Redirect temp dirs to a workspace location to avoid system temp permissions."""
    temp_root = Path(os.environ.get("PYTEST_TEMP_ROOT", _select_temp_root()))
    monkeypatch.setenv("TMPDIR", str(temp_root))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMP", str(temp_root))


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """Skip tmpdir cleanup when basetemp is not readable (sandbox restrictions)."""
    tmp_path_factory = getattr(session.config, "_tmp_path_factory", None)
    if tmp_path_factory is None:
        return
    basetemp = tmp_path_factory._basetemp
    if basetemp is None:
        return
    try:
        next(basetemp.iterdir(), None)
    except PermissionError:
        tmp_path_factory._basetemp = None
