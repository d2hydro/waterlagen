"""Release metadata permits new software files while protecting user paths."""

import json
import os
import subprocess

import pytest
import test_production_update as production_update
from test_production_update import NEW, OLD, install, release_files, updater, zip_bytes

project = production_update.project


def with_metadata(files, version=NEW):
    files[updater.METADATA] = json.dumps(
        {"version": version, "files": updater._hashes(files)}
    ).encode()
    return files


def test_same_updater_accepts_new_files_in_subsequent_releases(project, monkeypatch):
    root, private = project
    files = release_files(NEW)
    filename = "tools/runscript_maken/new_preview.py"
    files[filename] = b"first release\n"
    with_metadata(files)
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    monkeypatch.setattr(updater, "_bundle", _REAL_BUNDLE)
    updater.update(root, yes=True)
    assert (root / filename).read_bytes() == b"first release\n"

    following = "2026.11.1"
    files = release_files(following)
    files["tools/runscript_maken/web/new-panel.json"] = b'{"title": "New panel"}'
    with_metadata(files, following)
    monkeypatch.setattr(updater, "_release", lambda tag: following)
    updater.update(root, yes=True)
    assert not (root / filename).exists()
    assert (root / "tools/runscript_maken/web/new-panel.json").is_file()
    for name, content in private.items():
        assert (root / name).read_bytes() == content


_REAL_BUNDLE = updater._bundle


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/tmp/outside",
        "C:/outside",
        "//server/share/file",
        "tools\\runscript_maken\\file.py",
        "tools/runscript_maken/../outside.py",
        "tools/runscript_maken//file.py",
        "tools/runscript_maken/./file.py",
        "tools/runscript_maken/file.py.",
        "tools/runscript_maken/file.py ",
        "tools/runscript_maken/file.py:stream",
        "tools/runscript_maken/CON.py",
        "tools/runscript_maken/LPT1.py",
        "tools/runscript_maken/file\x00.py",
        ".env",
        ".datastore",
        "data/source_data/source.gpkg",
        "scripts/eigen.py",
        "tools/eigen.py",
        "docs/produceren/installatie.md",
        "tools/runscript_maken",
    ],
)
def test_manifest_cannot_grant_access_to_user_or_invalid_paths(monkeypatch, name):
    files = release_files(NEW)
    files[name] = b"not software at an allowed path"
    with_metadata(files)
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError):
        updater._bundle(NEW)


@pytest.mark.parametrize("collision", ["case", "parent", "duplicate"])
def test_archive_names_must_be_unique_and_not_conflict(monkeypatch, collision):
    from io import BytesIO
    from zipfile import ZipFile

    files = release_files(NEW)
    first = "tools/runscript_maken/example.py"
    second = {
        "case": "tools/runscript_maken/EXAMPLE.py",
        "parent": "tools/runscript_maken/example.py/child.py",
        "duplicate": first,
    }[collision]
    files[first] = b"one"
    if collision != "duplicate":
        files[second] = b"two"
    with_metadata(files)
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        if collision == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate"):
                archive.writestr(second, b"two")
    monkeypatch.setattr(updater, "_get", lambda url: buffer.getvalue())
    with pytest.raises(ValueError):
        updater._bundle(NEW)


@pytest.mark.parametrize(
    "damage",
    [
        "undeclared",
        "missing",
        "hash",
        "self",
        "type",
        "files_type",
        "digest_type",
        "empty",
    ],
)
def test_release_manifest_must_describe_exactly_the_software(monkeypatch, damage):
    files = release_files(NEW)
    metadata = json.loads(files[updater.METADATA])
    if damage == "undeclared":
        files["tools/runscript_maken/not-declared.py"] = b"extra"
    elif damage == "missing":
        del files["README.md"]
    elif damage == "hash":
        files["README.md"] = b"changed"
    elif damage == "self":
        metadata["files"][updater.METADATA] = "0" * 64
    elif damage == "type":
        metadata = []
    elif damage == "files_type":
        metadata["files"] = []
    elif damage == "digest_type":
        metadata["files"]["README.md"] = None
    else:
        metadata["files"] = {}
    files[updater.METADATA] = json.dumps(metadata).encode()
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError):
        updater._bundle(NEW)


def test_new_software_requires_metadata(monkeypatch):
    files = release_files(NEW)
    del files[updater.METADATA]
    files["tools/runscript_maken/new.py"] = b"new software"
    monkeypatch.setattr(updater, "_get", lambda url: zip_bytes(files))
    with pytest.raises(ValueError, match="zonder releasegegevens"):
        updater._bundle(NEW)


def test_new_software_cannot_replace_an_existing_user_file(project, monkeypatch):
    root, _ = project
    name = "tools/runscript_maken/new.py"
    install(root, {name: b"user's own file"})
    files = release_files(NEW)
    files[name] = b"new software"
    with_metadata(files)
    monkeypatch.setattr(updater, "_bundle", lambda tag: files)
    with pytest.raises(ValueError, match="Lokaal aangepaste"):
        updater.update(root, yes=True)
    assert (root / name).read_bytes() == b"user's own file"
    assert updater._manifest_version((root / "pixi.toml").read_bytes()) == OLD
    assert not (root / ".updates").exists()


@pytest.mark.parametrize("link_kind", ["symlink", "junction"])
def test_redirected_software_parent_is_rejected(project, monkeypatch, link_kind):
    root, _ = project
    destination = root / "my-data" / "custom-tools"
    destination.mkdir()
    link = root / "tools/runscript_maken"
    if link_kind == "junction":
        if os.name != "nt":
            pytest.skip("Junctions are Windows-specific")
        result = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        try:
            link.symlink_to(destination, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"Symlinks unavailable: {error}")
    files = release_files(NEW)
    files["tools/runscript_maken/new.py"] = b"new software"
    with_metadata(files)
    monkeypatch.setattr(updater, "_bundle", lambda tag: files)
    with pytest.raises(ValueError, match="symlink of junction"):
        updater.update(root, yes=True)
    assert not list(destination.iterdir())
    assert not (root / ".updates").exists()


def test_interrupted_restore_uses_recorded_new_file_names(project, monkeypatch):
    root, private = project
    new_name = "tools/runscript_maken/new.py"
    files = release_files(NEW)
    files[new_name] = b"new software"
    with_metadata(files)
    monkeypatch.setattr(updater, "_bundle", lambda tag: files)
    checks = updater._checks

    def fail_checks(root):
        raise RuntimeError("offline")

    monkeypatch.setattr(updater, "_checks", fail_checks)
    with pytest.raises(RuntimeError, match="Herstel niet voltooid"):
        updater.update(root, yes=True)
    assert (root / updater.PENDING).is_file()
    monkeypatch.setattr(updater, "_checks", checks)
    updater.update(root, yes=True)
    assert not (root / updater.PENDING).exists()
    assert not (root / new_name).exists()
    for name, content in private.items():
        assert (root / name).read_bytes() == content


@pytest.mark.parametrize(
    "name", [".env", "../outside", "tools/runscript_maken/../outside.py"]
)
def test_invalid_local_release_manifest_stops_before_writing(project, name):
    root, _ = project
    metadata = json.loads((root / updater.METADATA).read_bytes())
    metadata["files"][name] = "0" * 64
    (root / updater.METADATA).write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        updater.update(root, yes=True)
    assert not (root / ".updates").exists()
