import pytest


@pytest.fixture
def ahn_dir(tmp_path_factory):
    """Maakt een tijdelijke directory voor AHN-data."""
    d = tmp_path_factory.mktemp("ahn")
    return d
