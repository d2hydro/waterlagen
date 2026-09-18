import importlib.util
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from zipfile import ZipFile

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_production_bundle", REPOSITORY / "tools/build_production_bundle.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def public_lock(version):
    return (
        "version: 7\npackages:\n"
        "- conda: https://conda.anaconda.org/conda-forge/noarch/example-1.conda\n"
        f"- pypi: https://files.pythonhosted.org/packages/waterlagen-{version}-py3-none-any.whl\n"
    )


@pytest.mark.parametrize("tag", ["2026.9.0rc1", "v2026.9.0", "2026.7.0.dev0"])
def test_bundle_is_standalone_and_contains_only_public_inputs(
    tmp_path, monkeypatch, tag
):
    repository = tmp_path / "private-checkout"
    for path in [
        "pyproject.toml",
        "pixi.toml",
        "LICENSE",
        "envs/pixi.toml.in",
        "envs/README.md",
        *(f"scripts/{name}" for name in builder.PRODUCTION_SCRIPTS),
    ]:
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / path, target)
    (repository / ".env").write_text("PRIVATE_KEY=never-copy-me")
    (repository / ".datastore").write_text("DATA_DIR=D:/private-production")
    (repository / "scripts/private.py").write_text("secret = 'never-copy-me'")
    calls = []

    def fake_lock(command, *, cwd, check):
        calls.append(command)
        assert check
        manifest = tomllib.loads((cwd / "pixi.toml").read_text("utf-8"))
        version = tag.removeprefix("v")
        assert manifest["pypi-dependencies"] == {"waterlagen": f"=={version}"}
        assert "pcraster" in manifest["dependencies"]
        assert (
            not {"pytest", "ruff", "ipykernel", "mkdocs"}
            & manifest["dependencies"].keys()
        )
        assert manifest["tasks"]["inwoners"]["depends-on"] == ["bag"]
        assert manifest["tasks"]["auto"]["depends-on"] == ["bag"]
        (cwd / "pixi.lock").write_text(public_lock(version))
        (cwd / "unexpected.log").write_text("never-copy-me")

    monkeypatch.setattr(builder.subprocess, "run", fake_lock)
    archive_path = builder.build_bundle(tag, tmp_path / "output", repository)
    assert len(calls) == 1
    assert "--no-config" in calls[0]
    assert archive_path.name == f"waterlagen-productie-{tag}.zip"
    with ZipFile(archive_path) as archive:
        prefix = f"waterlagen-productie-{tag}/"
        members = {name.removeprefix(prefix) for name in archive.namelist()}
        assert members == {
            "pixi.toml",
            "pixi.lock",
            "README.md",
            "LICENSE",
            ".datastore",
            *(f"scripts/{name}" for name in builder.PRODUCTION_SCRIPTS),
        }
        assert archive.read(prefix + ".datastore") == b"DATA_DIR=./data\n"
        for name in builder.PRODUCTION_SCRIPTS:
            assert (
                archive.read(prefix + f"scripts/{name}")
                == (repository / "scripts" / name).read_bytes()
            )
        readme = archive.read(prefix + "README.md").decode()
        assert "@VERSION@" not in readme
        assert tag.removeprefix("v") in readme
        manifest = tomllib.loads(archive.read(prefix + "pixi.toml").decode())
        for task in manifest["tasks"].values():
            command = task if isinstance(task, str) else task.get("cmd", "")
            for script in re.findall(r"\./(scripts/\S+\.py)", command):
                assert script in members
        for name in archive.namelist():
            content = archive.read(name)
            assert b"never-copy-me" not in content
            assert str(repository).encode() not in content


@pytest.mark.parametrize("tag", ["../2026.9.0", "2026.9.0/secret", "$(secret)", "main"])
def test_rejects_invalid_release_tag(tmp_path, tag):
    with pytest.raises(ValueError, match="version scheme"):
        builder.build_bundle(tag, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "reference",
    [
        "file:///private/waterlagen.whl",
        "../waterlagen",
        "https://token@files.pythonhosted.org/waterlagen.whl",
        "https://private.example.org/waterlagen.whl",
        "https://conda.anaconda.org/private/package.conda",
    ],
)
def test_rejects_non_public_lock_references(tmp_path, reference):
    lock_path = tmp_path / "pixi.lock"
    lock_path.write_text(f"- pypi: {reference}\n")
    with pytest.raises(ValueError):
        builder.validate_lock(lock_path, "2026.9.0rc1")


def test_rejects_wrong_locked_waterlagen_version(tmp_path):
    lock_path = tmp_path / "pixi.lock"
    lock_path.write_text(public_lock("2026.2.1"))
    with pytest.raises(ValueError, match="differs"):
        builder.validate_lock(lock_path, "2026.9.0rc1")


def test_failed_lock_does_not_replace_existing_asset(tmp_path, monkeypatch):
    target = tmp_path / "waterlagen-productie-2026.9.0rc1.zip"
    target.write_bytes(b"previous valid asset")

    def fail_lock(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["pixi", "lock"])

    monkeypatch.setattr(builder.subprocess, "run", fail_lock)
    with pytest.raises(subprocess.CalledProcessError):
        builder.build_bundle("2026.9.0rc1", tmp_path)
    assert target.read_bytes() == b"previous valid asset"
