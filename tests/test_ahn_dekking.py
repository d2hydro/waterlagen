"""Test the published AHN sheets and the daily refresh."""

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from shapely.geometry import box

from waterlagen.ahn import dekking


def test_alkmaar_and_touching_neighbor(tmp_path):
    sheets = dekking.required(box(111250, 515750, 112250, 516750))
    current = dekking.publication(tmp_path)
    assert sheets.counts(6, current) == (4, 4)
    assert sheets.counts(4, current) == sheets.counts(5, current) == (1, 1)
    single = dekking.required(box(111000, 515000, 112000, 516000))
    assert single.counts(6, current) == (1, 1)
    rescheduled = replace(current, tiles=frozenset({"AHN6_2027_M_111000_515000"}))
    assert single.counts(6, rescheduled) == (1, 1)
    assert sheets.counts(6, replace(current, tiles=frozenset())) == (0, 4)


def test_refresh_304_reuses_list_and_needs_no_second_request(tmp_path, monkeypatch):
    initial = dekking.publication(tmp_path)
    now = initial.checked + 90000
    monkeypatch.setattr(dekking.time, "time", lambda: now)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs["headers"]))
        return nullcontext(SimpleNamespace(status_code=304, url=url))

    monkeypatch.setattr(dekking, "get", get)
    updated = dekking.refresh(tmp_path, lambda phase: pytest.fail(phase))
    assert updated.tiles == initial.tiles and updated.checked == now
    assert dekking.refresh(tmp_path, lambda _: None) == updated
    assert calls == [(initial.url, {"If-None-Match": initial.etag})]


def test_catalogue_failure_preserves_previous_list(tmp_path, monkeypatch):
    initial = dekking.publication(tmp_path)

    def failing(*args, **kwargs):
        raise requests.Timeout("Test")

    monkeypatch.setattr(dekking, "get", failing)
    with pytest.raises(requests.Timeout):
        dekking.refresh(tmp_path, lambda _: None, force=True)
    assert dekking.publication(tmp_path) == initial


def test_changed_catalogue_is_saved_after_download(tmp_path: Path, monkeypatch):
    previous = dekking.publication(tmp_path)
    filename = "AHN6_2027_M_111000_515000.TIF"
    response = SimpleNamespace(
        status_code=200,
        url=previous.url,
        headers={"ETag": "new"},
        raise_for_status=lambda: None,
        json=lambda: {
            "features": [{"properties": {"file": "https://example.org/" + filename}}]
        },
    )
    monkeypatch.setattr(dekking, "get", lambda *args, **kwargs: nullcontext(response))
    phases = []
    updated = dekking.refresh(tmp_path, phases.append, force=True)
    assert phases == ["download"]
    assert updated.tiles == {Path(filename).stem}
    assert dekking.publication(tmp_path) == updated
