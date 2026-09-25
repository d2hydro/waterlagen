"""Worker configuration for production workflows."""

import pytest
from pydantic import ValidationError

from waterlagen.settings import Settings


@pytest.mark.parametrize(
    "field,default",
    [("functioneel_landgebruik_workers", 16), ("afwateringseenheden_workers", 4)],
)
def test_workers_default(monkeypatch, field, default):
    monkeypatch.delenv(field.upper(), raising=False)
    assert getattr(Settings(_env_file=None), field) == default


def test_landuse_workers_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNCTIONEEL_LANDGEBRUIK_WORKERS", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "FUNCTIONEEL_LANDGEBRUIK_WORKERS=8\n", encoding="utf-8"
    )
    assert Settings().functioneel_landgebruik_workers == 8
    monkeypatch.setenv("FUNCTIONEEL_LANDGEBRUIK_WORKERS", "12")
    assert Settings().functioneel_landgebruik_workers == 12


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid"])
@pytest.mark.parametrize(
    "field", ["functioneel_landgebruik_workers", "afwateringseenheden_workers"]
)
def test_workers_reject_invalid_values(monkeypatch, value, field):
    monkeypatch.setenv(field.upper(), value)
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None)
