"""The standalone release updater migrates an actual 2026.11.0 updater safely."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_production_update import (
    REPOSITORY,
    builder,
    install,
    release_files,
    zip_bytes,
)

FIXTURE = Path(__file__).parent / "fixtures/production_2026_11_0"
OLD_RELEASE = "2026.11.0"
NEW_RELEASE = "2026.11.1"


def load_updater(path):
    spec = importlib.util.spec_from_file_location("standalone_updater", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "scenario",
    ["success", "cancel", "modified", "collision", "install", "controleer", "active"],
)
def test_one_time_entrypoint_migrates_old_installation(tmp_path, monkeypatch, scenario):
    root = tmp_path / "existing production with spaces"
    old_updater = load_updater(FIXTURE / "bijwerken.py")
    old_files = release_files(OLD_RELEASE, legacy=True)
    for name in old_updater.UPDATER_FILES:
        fixture_name = name + ".fixture" if name.endswith(".cmd") else name
        old_files[name] = (FIXTURE / fixture_name).read_bytes()
    old_files[old_updater.METADATA] = json.dumps(
        {"version": OLD_RELEASE, "files": old_updater._hashes(old_files)}
    ).encode()
    install(root, old_files)
    private = {
        ".datastore": b"DATA_DIR=./private-data\n",
        ".env": b"DEM_WORKERS=2\n",
        "scripts/eigen.py": b"my own script",
        "brandlagen.toml": b"my own configuration",
        "private-data/source_data/input.gpkg": b"existing source",
        "private-data/processed_data/dem/area/run/dem.tif": b"existing output",
    }
    install(root, private)

    # The downloaded updater is outside the installation; its old hashes stay valid.
    downloaded = tmp_path / "download with spaces/waterlagen-updater.py"
    downloaded.parent.mkdir()
    downloaded.write_bytes((REPOSITORY / "tools/code_bijwerken.py").read_bytes())
    updater = load_updater(downloaded)
    files = release_files(NEW_RELEASE)
    for name in builder.RUNSCRIPT_FILES:
        source = REPOSITORY / (
            name if name.startswith(("tools/", "docs/")) else f"envs/{name}"
        )
        files[name] = source.read_bytes()
    files[updater.METADATA] = json.dumps(
        {"version": NEW_RELEASE, "files": updater._hashes(files)}
    ).encode()
    archive = zip_bytes(files)
    requests = []

    def get(url):
        requests.append(url)
        if url.endswith("waterlagen-productie.zip"):
            return archive
        return json.dumps({"tag_name": NEW_RELEASE}).encode()

    def pixi(folder, *arguments, capture=False):
        assert folder == root.resolve()
        if capture:
            return subprocess.CompletedProcess(
                arguments, 0, json.dumps(str(root / "private-data/processed_data"))
            )
        version = updater._manifest_version((root / "pixi.toml").read_bytes())
        if version == NEW_RELEASE and scenario in arguments:
            raise subprocess.CalledProcessError(1, arguments)
        if arguments[0] == "install":
            install(root, {".pixi/installed-version": version.encode()})
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(updater, "_get", get)
    monkeypatch.setattr(updater, "_pixi", pixi)
    monkeypatch.chdir(downloaded.parent)
    monkeypatch.setattr(sys, "argv", [str(downloaded), "--project-dir", str(root)])
    monkeypatch.setattr(
        "builtins.input", lambda prompt: "n" if scenario == "cancel" else "j"
    )
    if scenario == "modified":
        old_files["scripts/dem.py"] += b"\n# local change"
        (root / "scripts/dem.py").write_bytes(old_files["scripts/dem.py"])
    if scenario == "collision":
        private["tools/runscript_maken/dem_preview.py"] = b"user-owned file"
        install(root, private)
    if scenario == "active":
        install(root, {"private-data/processed_data/dem/area/run/.run.lock": b"active"})

    result = updater.main()
    for name, content in private.items():
        assert (root / name).read_bytes() == content
    assert (
        downloaded.read_bytes() == (REPOSITORY / "tools/code_bijwerken.py").read_bytes()
    )
    if scenario == "success":
        assert result == 0
        assert (
            updater._manifest_version((root / "pixi.toml").read_bytes()) == NEW_RELEASE
        )
        assert (root / ".pixi/installed-version").read_text() == NEW_RELEASE
        assert (
            root / "tools/code_bijwerken.py"
        ).read_bytes() == downloaded.read_bytes()
        for name, content in files.items():
            assert (root / name).read_bytes() == content
        assert not any((root / name).exists() for name in old_updater.UPDATER_FILES)
    else:
        assert result == (0 if scenario == "cancel" else 1)
        for name, content in old_files.items():
            assert (root / name).read_bytes() == content
        assert not (root / "tools/code_bijwerken.py").exists()
        assert not (root / "code_bijwerken.bat").exists()
        if scenario in {"install", "controleer"}:
            assert (root / ".pixi/installed-version").read_text() == OLD_RELEASE
        else:
            assert not (root / ".updates").exists()
    assert not (root / updater.PENDING).exists()
    if scenario in {"cancel", "active"}:
        assert not any(url.endswith("waterlagen-productie.zip") for url in requests)


def test_unchanged_old_updater_still_rejects_new_layout(monkeypatch):
    legacy = load_updater(FIXTURE / "bijwerken.py")
    files = release_files(NEW_RELEASE)
    monkeypatch.setattr(legacy, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError, match="Onverwachte bestanden"):
        legacy._bundle(NEW_RELEASE)


@pytest.mark.parametrize("kind", ["missing", "checkout"])
def test_explicit_target_must_be_a_production_installation(tmp_path, monkeypatch, kind):
    updater = load_updater(REPOSITORY / "tools/code_bijwerken.py")
    target = tmp_path / "not a production installation"
    target.mkdir()
    if kind == "checkout":
        (target / "pixi.toml").write_text('[workspace]\nname="Waterlagen"\n')
    monkeypatch.setattr(
        sys, "argv", ["waterlagen-updater.py", "--project-dir", str(target), "--ja"]
    )
    monkeypatch.setattr(
        updater, "_get", lambda url: pytest.fail("Invalid target must not download")
    )
    assert updater.main() == 1
    assert not (target / ".bijwerken.lock").exists()
