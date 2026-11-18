"""Test de echte kaartbediening met een DOM en kleine synthetische gebieden."""

import importlib
import json
import shutil
import subprocess
from dataclasses import asdict

import pytest
from shapely.geometry import box, mapping
from shapely.ops import orient

from test_runscript_maken import REPOSITORY, generator


def test_browser_interactions(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js ontbreekt; installeer tests/browser/package.json voor de DOM-test"
        )
    folder = REPOSITORY / "tests/browser"
    available = subprocess.run(
        [node, "-e", "require('jsdom'); require('acorn')"],
        cwd=folder,
        capture_output=True,
    )
    if available.returncode:
        pytest.skip("Installeer de testafhankelijkheden in tests/browser")
    options = importlib.import_module("runscript_tool_tests.waterlagen_options")
    frame = {
        "type": "Feature",
        "properties": {},
        "geometry": mapping(orient(box(3.4, 50.7, 7.2, 53.6), sign=-1)),
    }
    features = []
    for code, name, bounds in [
        ("12", "HHNK", (4.5, 52.4, 5.1, 53)),
        ("13", "Rijnland", (4.4, 52, 4.9, 52.4)),
        ("38", "Aa en Maas", (5, 51.5, 5.9, 51.8)),
    ]:
        features.append(
            {
                "type": "Feature",
                "properties": {"code": code, "name": name},
                "geometry": mapping(orient(box(*bounds), sign=-1)),
            }
        )
    fixture = {
        "country": frame,
        "authorities": {"type": "FeatureCollection", "features": features},
        "options": {
            layer: [{**asdict(option), "url": option.help.url} for option in items]
            for layer, items in options.EXTRA_OPTIONS.items()
        },
        "layers": list(generator.LAYERS.items()),
        "layer_help": {
            layer: {"url": help.url} for layer, help in generator.LAYER_HELP.items()
        },
        "run_id": "kaartproef",
        "crs": "EPSG:28992",
    }
    path = tmp_path / "map.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    result = subprocess.run(
        [node, str(folder / "run_maken.cjs"), str(path)],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
