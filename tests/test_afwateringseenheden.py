from waterlagen.afwateringseenheden import require_pcraster


def test_afwateringseenheden_package_imports_without_pcraster():
    assert callable(require_pcraster)


def test_require_pcraster_returns_module_or_actionable_error():
    try:
        module = require_pcraster()
    except RuntimeError as exc:
        assert "afwateringseenheden" in str(exc)
        assert "pixi" in str(exc)
    else:
        assert module.__name__ == "pcraster"