"""The standalone updater preserves user data and restores failed installations."""

import importlib.util
import json
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_production_bundle import builder, public_lock

REPOSITORY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "production_update", REPOSITORY / "envs/code_bijwerken.py"
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
OLD = "2026.9.0"
NEW = "2026.11.0"


def release_files(version, *, legacy=False):
    files = {
        name: f"release {version}: {name}\n".encode() for name in updater.BASE_FILES
    }
    files["pixi.toml"] = builder.render_manifest(REPOSITORY, version).encode()
    files["pixi.lock"] = public_lock(version).encode()
    if not legacy:
        files.update(
            {
                name: (REPOSITORY / "envs" / name).read_bytes()
                for name in updater.UPDATER_FILES
            }
        )
        files[updater.METADATA] = json.dumps(
            {"version": version, "files": updater._hashes(files)}
        ).encode()
    return files


def install(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "production with spaces"
    install(root, release_files(OLD))
    private = {
        ".datastore": b"DATA_DIR=./my-data\n",
        ".env": b"AFWATERINGSEENHEDEN_WORKERS=2\n",
        "brandlagen.toml": b"private configuration",
        "scripts/eigen.py": b"private script",
        "my-data/source_data/original.gpkg": b"source data",
        "my-data/processed_data/afwateringseenheden/38/old/run.json": b"existing run",
    }
    install(root, private)
    monkeypatch.setattr(updater, "_release", lambda tag: tag or NEW)
    monkeypatch.setattr(
        updater, "_bundle", lambda tag: release_files(updater._version(tag))
    )

    def pixi(folder, *arguments, capture=False):
        assert folder == root.resolve()
        if capture:
            return subprocess.CompletedProcess(
                arguments, 0, json.dumps(str(root / "my-data/processed_data"))
            )
        if arguments[0] == "install":
            environment = root / ".pixi"
            environment.mkdir(exist_ok=True)
            (environment / "installed-version").write_text(
                updater._manifest_version((root / "pixi.toml").read_bytes())
            )
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(updater, "_pixi", pixi)
    return root, private


def assert_private_unchanged(root, private):
    for name, content in private.items():
        assert (root / name).read_bytes() == content


def test_update_adds_runscript_window_without_touching_user_scripts(
    project, monkeypatch
):
    root, private = project
    files = release_files(NEW)
    for name in updater.RUNSCRIPT_FILES:
        source = REPOSITORY / (name if name.startswith("tools/") else f"envs/{name}")
        files[name] = source.read_bytes()
    files[updater.METADATA] = json.dumps(
        {"version": NEW, "files": updater._hashes(files)}
    ).encode()
    monkeypatch.setattr(updater, "_bundle", lambda tag: files)
    updater.update(root, yes=True)
    for name in updater.RUNSCRIPT_FILES:
        assert (root / name).read_bytes() == files[name]
    assert_private_unchanged(root, private)


def test_update_keeps_data_settings_and_existing_runs(project):
    root, private = project
    updater.update(root, yes=True)
    for name, content in release_files(NEW).items():
        assert (root / name).read_bytes() == content
    assert_private_unchanged(root, private)
    assert not (root / updater.PENDING).exists()
    assert (root / ".pixi/installed-version").read_text() == NEW
    backups = list((root / ".updates").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "pixi.lock").read_bytes() == release_files(OLD)["pixi.lock"]


def old_named_release_files(version):
    files = release_files(version)
    for current, old in zip(updater.UPDATER_FILES, updater.LEGACY_UPDATER_FILES):
        files[old] = files.pop(current).replace(b"code_bijwerken", b"bijwerken")
    files[updater.METADATA] = json.dumps(
        {"version": version, "files": updater._hashes(files)}
    ).encode()
    return files


@pytest.mark.parametrize("failure", [False, True])
def test_old_names_are_migrated_and_restored_on_failure(project, monkeypatch, failure):
    root, private = project
    for name in updater.UPDATER_FILES:
        (root / name).unlink()
    old_files = old_named_release_files(OLD)
    install(root, old_files)
    checks = updater._checks

    def check(folder):
        if (
            failure
            and updater._manifest_version((folder / "pixi.toml").read_bytes()) == NEW
        ):
            raise RuntimeError("test failure")
        checks(folder)

    monkeypatch.setattr(updater, "_checks", check)
    if failure:
        with pytest.raises(RuntimeError, match="vorige versie is hersteld"):
            updater.update(root, yes=True)
        for name, content in old_files.items():
            assert (root / name).read_bytes() == content
        assert all(not (root / name).exists() for name in updater.UPDATER_FILES)
    else:
        updater.update(root, yes=True)
        assert all(not (root / name).exists() for name in updater.LEGACY_UPDATER_FILES)
        for name, content in release_files(NEW).items():
            assert (root / name).read_bytes() == content
    assert_private_unchanged(root, private)


def test_release_with_old_updater_names_remains_usable(project, monkeypatch):
    root, private = project
    files = old_named_release_files(NEW)
    monkeypatch.setattr(updater, "_bundle", lambda tag: files)
    updater.update(root, yes=True)
    assert (root / "bijwerken.cmd").exists()
    assert_private_unchanged(root, private)


def test_download_accepts_old_updater_names(monkeypatch):
    files = old_named_release_files(NEW)
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    assert updater._bundle(NEW) == files


@pytest.mark.parametrize(
    "name", ["pixi.toml", "pixi.lock", "scripts/afwateringseenheden.py", "README.md"]
)
def test_local_changes_are_not_overwritten(project, name):
    root, private = project
    original = (root / name).read_bytes()
    (root / name).write_bytes(original + b"\n# local change\n")
    with pytest.raises(ValueError, match="Lokaal aangepaste"):
        updater.update(root, yes=True)
    assert (root / name).read_bytes() == original + b"\n# local change\n"
    assert_private_unchanged(root, private)
    assert not (root / ".updates").exists()


def test_active_run_blocks_update(project):
    root, private = project
    lock = root / "my-data/processed_data/afwateringseenheden/38/old/.run.lock"
    lock.touch()
    with pytest.raises(RuntimeError, match="Stop eerst"):
        updater.update(root, yes=True)
    assert not (root / ".updates").exists()
    assert_private_unchanged(root, private)


@pytest.mark.parametrize("failure", ["install", "controleer", "interrupt"])
def test_failed_update_restores_files_and_environment(project, monkeypatch, failure):
    root, private = project
    actual = updater._pixi

    def pixi(folder, *arguments, capture=False):
        version = updater._manifest_version((root / "pixi.toml").read_bytes())
        if version == NEW and not capture:
            if failure == "interrupt":
                raise KeyboardInterrupt
            if failure in arguments:
                raise subprocess.CalledProcessError(1, arguments)
        return actual(folder, *arguments, capture=capture)

    monkeypatch.setattr(updater, "_pixi", pixi)
    with pytest.raises(
        RuntimeError, match="vorige versie is hersteld en gecontroleerd"
    ):
        updater.update(root, yes=True)
    for name, content in release_files(OLD).items():
        assert (root / name).read_bytes() == content
    assert (root / ".pixi/installed-version").read_text() == OLD
    assert not (root / updater.PENDING).exists()
    assert_private_unchanged(root, private)


def test_failed_restore_can_be_retried(project, monkeypatch):
    root, private = project
    actual = updater._pixi

    def unavailable(folder, *arguments, capture=False):
        if not capture:
            raise subprocess.CalledProcessError(1, arguments)
        return actual(folder, *arguments, capture=True)

    monkeypatch.setattr(updater, "_pixi", unavailable)
    with pytest.raises(RuntimeError, match="Herstel niet voltooid"):
        updater.update(root, yes=True)
    assert (root / updater.PENDING).is_file()
    monkeypatch.setattr(updater, "_pixi", actual)
    updater.update(root, yes=True)
    assert not (root / updater.PENDING).exists()
    assert (root / ".pixi/installed-version").read_text() == OLD
    assert_private_unchanged(root, private)


def test_older_zip_without_metadata_uses_original_release_to_check_local_files(
    project, monkeypatch
):
    root, private = project
    (root / updater.METADATA).unlink()
    # The three launcher files were copied once into the old installation.
    monkeypatch.setattr(
        updater, "_bundle", lambda tag: release_files(tag, legacy=tag == OLD)
    )
    updater.update(root, yes=True)
    assert (root / updater.METADATA).exists()
    assert_private_unchanged(root, private)


def test_cancel_and_current_version_do_not_change_installation(project, monkeypatch):
    root, private = project
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    updater.update(root)
    monkeypatch.setattr(updater, "_release", lambda tag: OLD)
    updater.update(root, yes=True)
    assert not (root / ".updates").exists()
    assert_private_unchanged(root, private)


def test_latest_does_not_implicitly_downgrade(project, monkeypatch):
    root, _ = project
    monkeypatch.setattr(updater, "_release", lambda tag: "2026.2.1")
    updater.update(root, yes=True)
    assert not (root / ".updates").exists()


def test_second_updater_is_blocked(project):
    root, _ = project
    with (
        updater._update_lock(root),
        pytest.raises(RuntimeError, match="al een updater"),
    ):
        updater.update(root, yes=True)


def zip_bytes(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_downloaded_bundle_never_includes_datastore_in_update(monkeypatch):
    files = release_files(NEW)
    files[".datastore"] = b"DATA_DIR=wrong-location"
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    assert updater._bundle(NEW) == release_files(NEW)


@pytest.mark.parametrize("damage", ["path", "hash", "version", "missing"])
def test_invalid_download_is_rejected(monkeypatch, damage):
    files = release_files(NEW)
    if damage == "path":
        files["../outside"] = b"not allowed"
    elif damage == "hash":
        files["pixi.lock"] = b"damaged download"
    elif damage == "version":
        files["pixi.toml"] = release_files(OLD)["pixi.toml"]
    else:
        del files["pixi.lock"]
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError):
        updater._bundle(NEW)


def test_does_not_update_from_inside_production_environment(project, monkeypatch):
    root, _ = project
    monkeypatch.setattr(updater.sys, "prefix", str(root / ".pixi/envs/default"))
    with pytest.raises(RuntimeError, match="buiten de productieomgeving"):
        updater.update(root, yes=True)


def test_old_unversioned_project_is_rejected_without_changing_files(project):
    root, private = project
    manifest = (root / "pixi.toml").read_text().replace(f'version = "{OLD}"\n', "")
    (root / "pixi.toml").write_text(manifest)
    with pytest.raises(ValueError, match="geen versiegebonden productiepakket"):
        updater.update(root, yes=True)
    assert (root / "pixi.toml").read_text() == manifest
    assert_private_unchanged(root, private)
