"""De kaartinterface gebruikt dezelfde bestanden en commando's als productie."""

import importlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import geopandas as gpd
import pytest
from shapely.geometry import box, shape
from test_runscript_maken import REPOSITORY, generator

app = importlib.import_module("runscript_tool_tests.browser_app")
server_module = importlib.import_module("runscript_tool_tests.browser_server")
maps = importlib.import_module("runscript_tool_tests.map_data")
tiles = importlib.import_module("runscript_tool_tests.map_tiles")


class Dialogs:
    def __init__(self, path):
        self.path = path

    def save(self, *args):
        return self.path

    def open(self, *args):
        return self.path


@pytest.fixture
def values():
    return {
        "mode": "authorities",
        "authorities": ["13", "12"],
        "layers": ["dem", "functioneel_landgebruik"],
        "run_id": "kaartproef",
        "workers": 8,
        "run_mode": "resume",
        "extra_options": [],
    }


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        generator,
        "DataStore",
        lambda: SimpleNamespace(processed_data_dir=tmp_path / "processed"),
    )
    return app.RunApplication(tmp_path, Dialogs(tmp_path / "run.bat"))


def test_main_opens_real_browser_layout(monkeypatch, tmp_path):
    (tmp_path / "pixi.toml").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(generator.sys, "argv", ["runscript_maken.py"])
    opened = []
    monkeypatch.setattr(server_module, "open_browser", opened.append)
    assert generator.main() == 0
    assert opened == [tmp_path]
    html = (server_module.ASSETS / "index.html").read_text("utf-8")
    assert 'src="app.js"' in html and 'id="rm-map"' in html
    assert "data-demo=" not in html
    assert 'id="rm-start"' in html
    assert (
        "tools\\runscript_maken.py" in (REPOSITORY / "envs/run-maken.bat").read_text()
    )


def test_failure_to_open_browser_closes_server(monkeypatch, tmp_path):
    import tkinter as tk

    def unexpected_mainloop():
        pytest.fail("A failed browser launch should not start the main loop")

    calls = []
    root = SimpleNamespace(
        withdraw=lambda: None,
        after=lambda *_: None,
        mainloop=unexpected_mainloop,
        destroy=lambda: calls.append("destroy"),
    )
    server = SimpleNamespace(
        url="http://127.0.0.1/",
        serve_forever=lambda: None,
        shutdown=lambda: calls.append("shutdown"),
        server_close=lambda: calls.append("close"),
    )
    monkeypatch.setattr(tk, "Tk", lambda: root)
    monkeypatch.setattr(server_module, "create_server", lambda *_: server)
    monkeypatch.setattr(server_module.webbrowser, "open", lambda *_, **__: False)
    with pytest.raises(RuntimeError, match="browser kon niet worden geopend"):
        server_module.open_browser(tmp_path)
    assert calls == ["shutdown", "close", "destroy"]


def test_bgt_file_extension_is_shown_in_field_and_picker(application, monkeypatch):
    selection = {"layer": "functioneel_landgebruik", "flag": "bgt-path"}
    application.boundaries = {}
    choices = application.bootstrap()["options"][selection["layer"]]
    option = next(item for item in choices if item["flag"] == selection["flag"])
    assert option["label"] == "Voorbereid BGT-bestand (.gpkg)"
    calls = []
    monkeypatch.setattr(application.dialogs, "open", lambda *args: calls.append(args))
    assert application.dispatch("browse", selection) == {"cancelled": True}
    assert calls == [("Voorbereid BGT-bestand (.gpkg)", "*.gpkg")]


def test_browse_checks_selected_file_and_invalid_path_stops_save(application, values):
    path = application.dialogs.path
    path.write_text("Verkeerd bestand")
    selection = {"layer": "afwateringseenheden", "flag": "eigen-hydamo"}
    chosen = application.dispatch("browse", selection)
    assert chosen == {
        "path": str(path),
        "error": "Kies een bestand van het type .gpkg.",
    }
    assert (
        application.dispatch("validate_path", {**selection, "path": str(path)})
        == chosen
    )
    assert application.dispatch("browse", {**selection, "flag": "brandlagen-config"})[
        "error"
    ]
    values["layers"] = ["afwateringseenheden"]
    values["extra_options"] = [{**selection, "value": str(path)}]
    with pytest.raises(ValueError, match="Eigen HyDAMO.*.gpkg"):
        application.dispatch("preview", values)
    with pytest.raises(ValueError, match="Eigen HyDAMO.*.gpkg"):
        application.dispatch("save", {**values, "start": True})
    assert path.read_text() == "Verkeerd bestand"


def test_commands_order_union_and_workers(application, values):
    commands = application.dispatch("preview", values)["commands"]
    assert commands[0].startswith("pixi run --locked functioneel_landgebruik")
    assert commands[1].startswith("pixi run --locked dem")
    assert all("--waterbeheercode '12,13'" in command for command in commands)
    assert all("--workers 8" in command for command in commands)
    assert not any("--resume" in command for command in commands)


@pytest.mark.parametrize(
    "mode,flag", [("resume", "--resume"), ("overwrite", "--overwrite")]
)
def test_existing_run_policy_is_per_layer(application, values, mode, flag):
    target = (
        application.project
        / "processed/functioneel_landgebruik/waterschappen_12_13/kaartproef"
    )
    target.mkdir(parents=True)
    (target / "run.json").write_text("{}")
    values["run_mode"] = mode
    commands = application.commands(values)
    assert flag in commands[0]
    assert flag not in commands[1]


def test_existing_refresh_is_rejected(application, values):
    target = application.project / "processed/dem/waterschappen_12_13/kaartproef"
    target.mkdir(parents=True)
    (target / "run.json").write_text("{}")
    values["refresh_sources"] = True
    with pytest.raises(ValueError, match="nieuwe run"):
        application.commands(values)


def test_save_and_reload_preserves_options(application, values):
    values.update(
        workers=32,
        debug=True,
        extra_options=[{"layer": "dem", "flag": "building-workers", "value": "3"}],
    )
    result = application.dispatch("save", values)
    assert not result["started"]
    path = Path(result["path"])
    assert path.suffix == ".bat"
    assert "pixi run --locked dem" in path.read_text("utf-8")
    loaded = application.dispatch("run_load", {})
    assert loaded["authorities"] == ["12", "13"]
    assert loaded["workers"] == 32 and loaded["debug"]
    assert loaded["extra_options"] == values["extra_options"]


def test_save_start_uses_saved_batch(application, values, monkeypatch):
    scripts = importlib.import_module("runscript_tool_tests.script")
    started = []
    monkeypatch.setattr(
        scripts,
        "start_batch",
        lambda path, project: started.append((path, project)) or SimpleNamespace(pid=1),
    )
    result = application.dispatch("save", {**values, "start": True})
    assert result["started"]
    assert started == [(application.dialogs.path, application.project)]
    assert started[0][0].is_file()


def test_cancel_does_not_start_or_write(application, values, monkeypatch):
    application.dialogs.path = None
    monkeypatch.setattr(
        app, "save_script", lambda *args, **kwargs: pytest.fail("Opslaan na annuleren")
    )
    assert application.dispatch("save", {**values, "start": True}) == {
        "cancelled": True
    }


def test_polygon_roundtrip_crs_and_other_layers(tmp_path):
    target = tmp_path / "gebied.gpkg"
    other = gpd.GeoDataFrame(
        {"naam": ["behouden"]},
        geometry=[box(100000, 500000, 100010, 500010)],
        crs=28992,
    )
    other.to_file(target, layer="ander", driver="GPKG")
    coordinates = [[4.7, 52.6], [4.71, 52.6], [4.71, 52.61], [4.7, 52.61]]
    result = maps.save_polygon(coordinates, target)
    loaded = app.area_from_file(target, layer="gebied")
    assert str(loaded.crs).upper() == "EPSG:28992"
    assert gpd.read_file(target, layer="ander").naam.tolist() == ["behouden"]
    assert (
        shape(result["geometry"])
        .symmetric_difference(
            shape({"type": "Polygon", "coordinates": [coordinates + [coordinates[0]]]})
        )
        .area
        < 1e-9
    )


def test_invalid_polygon_never_replaces_file(tmp_path):
    target = tmp_path / "bestaand.gpkg"
    target.write_bytes(b"niet vervangen")
    with pytest.raises(ValueError):
        maps.save_polygon([[4, 52], [5, 53], [4, 53], [5, 52]], target)
    assert target.read_bytes() == b"niet vervangen"


def test_polygon_layers_and_geometry(application, tmp_path, values):
    target = tmp_path / "selectie.gpkg"
    for layer, x in [("west", 100000), ("oost", 110000)]:
        gpd.GeoDataFrame(geometry=[box(x, 500000, x + 100, 500100)], crs=28992).to_file(
            target, layer=layer, driver="GPKG"
        )
    application.dialogs.path = target
    assert set(application.dispatch("polygon_file", {})["layers"]) == {"west", "oost"}
    result = application.dispatch(
        "polygon_layer", {"path": str(target), "layer": "oost"}
    )
    assert result["feature"]["geometry"]["type"] == "Polygon"
    values.update(mode="file", area_file=str(target), area_layer="oost")
    assert "--area-layer oost" in application.commands(values)[0]


@pytest.mark.parametrize(
    "change",
    [
        {"workers": "1.5"},
        {"workers": 0},
        {"layers": []},
        {"authorities": []},
        {"authorities": ["999"]},
        {"mode": "draw", "drawing_saved": False},
    ],
)
def test_invalid_form_is_rejected(application, values, change):
    with pytest.raises(ValueError):
        application.commands({**values, **change})


@pytest.fixture
def http_server(application, tmp_path):
    server = server_module.create_server(application.dispatch, tmp_path / "tiles")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def test_http_preview_and_actual_layout(http_server, values):
    with urlopen(http_server.url) as response:
        text = response.read().decode()
        assert response.headers.get_content_type() == "text/html"
        for control in ("rm-choose-authorities", "rm-map", "rm-preview"):
            assert f'id="{control}"' in text
    request = Request(
        http_server.url + "api/preview",
        json.dumps(values).encode(),
        {"Content-Type": "application/json"},
    )
    with urlopen(request) as response:
        assert len(json.load(response)["commands"]) == 2


def test_http_rejects_foreign_origin_and_unknown_session(http_server, values):
    for address, headers in [
        (http_server.url + "api/save", {"Origin": "https://example.com"}),
        (
            http_server.url.split(http_server.url.split("/")[-2])[0] + "wrong/api/save",
            {},
        ),
    ]:
        request = Request(
            address,
            json.dumps(values).encode(),
            {"Content-Type": "application/json", **headers},
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 403


def test_pdok_tiles_support_detail_and_reuse_cache(tmp_path, monkeypatch):
    requested = []

    class Response:
        headers = {"Content-Type": "image/jpeg"}
        content = b"\xff\xd8test"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        tiles.requests, "get", lambda url, **kwargs: requested.append(url) or Response()
    )
    first = tiles.tile(tmp_path, "aerial", 21, 1076114, 687430)
    assert tiles.tile(tmp_path, "aerial", 21, 1076114, 687430) == first
    assert len(requested) == 1
    assert "Actueel_orthoHR/EPSG:3857/21/" in requested[0]
    with pytest.raises(ValueError):
        tiles.tile(tmp_path, "streets", 21, 1, 1)


@pytest.mark.parametrize("mixed", [False, True])
def test_another_file_after_unsuitable_area(http_server, application, tmp_path, mixed):
    from shapely.geometry import Point

    unsuitable = tmp_path / "ongeschikt.gpkg"
    geometries = [Point(100000, 500000)]
    if mixed:
        geometries.append(box(100000, 500000, 100100, 500100))
    gpd.GeoDataFrame(geometry=geometries, crs=28992).to_file(
        unsuitable, layer="gemengd", driver="GPKG"
    )
    valid = tmp_path / "gebied.gpkg"
    gpd.GeoDataFrame(geometry=[box(110000, 500000, 110100, 500100)], crs=28992).to_file(
        valid, layer="gebied", driver="GPKG"
    )

    def request(action, values):
        with urlopen(
            Request(
                http_server.url + "api/" + action,
                json.dumps(values).encode(),
                {"Content-Type": "application/json"},
            )
        ) as response:
            return json.load(response)

    application.dialogs.path = unsuitable
    with pytest.raises(HTTPError) as error:
        if mixed:
            request("polygon_layer", {"path": str(unsuitable), "layer": "gemengd"})
        else:
            request("polygon_file", {})
    assert error.value.code == 400
    application.dialogs.path = valid
    assert request("polygon_file", {}) == {"path": str(valid), "layers": ["gebied"]}
    result = request("polygon_layer", {"path": str(valid), "layer": "gebied"})
    assert shape(result["feature"]["geometry"]).is_valid


def test_native_dialog_recovers_after_cancel_and_error(tmp_path, monkeypatch):
    native = importlib.import_module("runscript_tool_tests.native_dialogs")
    try:
        root = native.tk.Tk()
    except native.tk.TclError as error:
        if "display" not in str(error).lower():
            raise
        pytest.skip("Voor de venstercontrole is een grafisch scherm nodig")
    root.withdraw()
    dialogs = native.NativeDialogs(root, tmp_path)
    monkeypatch.setattr(dialogs, "_call", lambda action: action())
    results = iter(
        ["", OSError("Bestand niet bereikbaar"), str(tmp_path / "ander.gpkg")]
    )
    owners = []

    def choose(**options):
        owner = options["parent"]
        owners.append(owner)
        assert owner.winfo_viewable()
        assert not owner.overrideredirect()
        assert owner.attributes("-alpha") == 0
        if sys.platform == "win32":
            assert owner.attributes("-toolwindow")
        assert owner.attributes("-topmost")
        value = next(results)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(native.filedialog, "askopenfilename", choose)
    try:
        assert dialogs.open("Gebied", "*.gpkg") is None
        with pytest.raises(OSError, match="bereikbaar"):
            dialogs.open("Gebied", "*.gpkg")
        assert dialogs.open("Gebied", "*.gpkg") == tmp_path / "ander.gpkg"
        assert all(not owner.winfo_exists() for owner in owners)
    finally:
        root.destroy()


def test_file_dialog_disposes_owner_after_cancel_and_error(tmp_path, monkeypatch):
    native = importlib.import_module("runscript_tool_tests.native_dialogs")
    dialogs = native.NativeDialogs(Mock(), tmp_path)
    owners = [Mock(), Mock(), Mock()]
    monkeypatch.setattr(native.tk, "Toplevel", Mock(side_effect=owners))
    monkeypatch.setattr(dialogs, "_call", lambda action: action())
    selected = tmp_path / "gebied.gpkg"
    choose = Mock(side_effect=["", OSError("Geen toegang"), str(selected)])
    monkeypatch.setattr(native.filedialog, "askopenfilename", choose)

    assert dialogs.open("Eigen DTM-VRT", "*.vrt") is None
    assert choose.call_args.kwargs["title"] == "Eigen DTM-VRT"
    assert choose.call_args.kwargs["filetypes"][0] == ("*.vrt", "*.vrt")
    with pytest.raises(OSError, match="Geen toegang"):
        dialogs.open("Gebied", "*.gpkg")
    assert dialogs.open("Gebied", "*.gpkg *.geojson *.json") == selected
    assert choose.call_args.kwargs["filetypes"][0] == (
        "*.gpkg; *.geojson; *.json",
        "*.gpkg *.geojson *.json",
    )
    assert [call.kwargs["parent"] for call in choose.call_args_list] == owners
    for owner in owners:
        owner.destroy.assert_called_once_with()


def test_native_dialog_rejects_second_request_and_accepts_retry(monkeypatch):
    native = importlib.import_module("runscript_tool_tests.native_dialogs")
    root = SimpleNamespace(after=lambda *_: None)
    dialogs = native.NativeDialogs(root, Path.cwd())
    queued = threading.Event()
    put = dialogs.pending.put

    def enqueue(request):
        put(request)
        queued.set()

    monkeypatch.setattr(dialogs.pending, "put", enqueue)
    monkeypatch.setattr(dialogs, "_file_dialog", lambda *_: "")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dialogs.open, "Openen", "*.toml")
        try:
            assert queued.wait(timeout=2)
            second = pool.submit(dialogs.directory, "Map kiezen")
            with pytest.raises(ValueError, match="Sluit eerst"):
                second.result(timeout=2)
        finally:
            dialogs._poll()
            if not dialogs.pending.empty():
                dialogs._poll()
        assert first.result(timeout=2) is None
        queued.clear()
        retry = pool.submit(dialogs.open, "Openen", "*.toml")
        assert queued.wait(timeout=2)
        dialogs._poll()
        assert retry.result(timeout=2) is None
