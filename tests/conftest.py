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
