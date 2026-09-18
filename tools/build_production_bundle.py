"""Build a standalone Pixi production ZIP for an already published release."""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SCRIPTS = (
    "afwateringseenheden.py",
    "functioneel_landgebruik.py",
    "inwoners.py",
    "auto.py",
    "bag.py",
    "statistiek_inwoners_autos.py",
    "controleer_productie.py",
)


def release_version(tag: str, repository: Path) -> str:
    """Use the same tag pattern as hatch-vcs, rejecting paths and shell input."""
    project = tomllib.loads((repository / "pyproject.toml").read_text("utf-8"))
    pattern = project["tool"]["hatch"]["version"]["tag-pattern"]
    match = re.fullmatch(pattern, tag)
    if match is None:
        raise ValueError(
            f"Release tag does not match the package version scheme: {tag!r}"
        )
    return match.group("version")


def render_manifest(repository: Path, version: str) -> str:
    """Reuse runtime dependency requirements; omit development features and paths."""
    project = tomllib.loads((repository / "pixi.toml").read_text("utf-8"))
    dependencies = dict(project["dependencies"])
    dependencies.update(project["feature"]["afwateringseenheden"]["dependencies"])
    for name, requirement in dependencies.items():
        if not isinstance(requirement, str):
            raise TypeError(f"Production dependency must be a version string: {name}")
    dependency_lines = "\n".join(
        f"{json.dumps(name)} = {json.dumps(requirement)}"
        for name, requirement in dependencies.items()
    )
    template = (repository / "envs" / "pixi.toml.in").read_text("utf-8")
    return (
        template.replace("@VERSION@", version)
        .replace("@DEPENDENCIES@", dependency_lines)
        .replace("@PLATFORMS@", json.dumps(project["workspace"]["platforms"]))
    )


def validate_lock(lock_path: Path, version: str) -> None:
    """Reject local or private package references before distributing the lock."""
    lock_text = lock_path.read_text("utf-8")
    references = re.findall(r"^\s*- (?:conda|pypi): (.+)$", lock_text, re.MULTILINE)
    if not references:
        raise ValueError("Pixi lock contains no package references")
    waterlagen_urls = set()
    for reference in references:
        url = urlsplit(reference)
        if (
            url.scheme != "https"
            or url.hostname not in {"conda.anaconda.org", "files.pythonhosted.org"}
            or url.username is not None
            or url.password is not None
            or url.query
        ):
            raise ValueError(f"Non-public package reference in Pixi lock: {reference}")
        if url.hostname == "conda.anaconda.org" and not url.path.startswith(
            "/conda-forge/"
        ):
            raise ValueError("Only the public conda-forge channel is allowed")
        filename = url.path.rsplit("/", 1)[-1]
        if filename.startswith("waterlagen-"):
            waterlagen_urls.add(reference)
            if not filename.startswith(f"waterlagen-{version}-"):
                raise ValueError("Locked Waterlagen version differs from release tag")
    if not waterlagen_urls:
        raise ValueError("Pixi lock must contain the released Waterlagen wheel")


def build_bundle(tag: str, output_dir: Path, repository: Path = REPO_ROOT) -> Path:
    """Copy an explicit set of public files, lock dependencies, then create a ZIP."""
    repository = repository.resolve()
    version = release_version(tag, repository)
    bundle_name = f"waterlagen-productie-{tag}"
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{bundle_name}.zip"

    with tempfile.TemporaryDirectory(prefix="production-", dir=output_dir) as temporary:
        project_dir = Path(temporary) / bundle_name
        project_dir.mkdir()
        (project_dir / "scripts").mkdir()
        (project_dir / "pixi.toml").write_text(
            render_manifest(repository, version), encoding="utf-8", newline="\n"
        )
        readme = (repository / "envs" / "README.md").read_text("utf-8")
        (project_dir / "README.md").write_text(
            readme.replace("@VERSION@", version).replace("@TAG@", tag),
            encoding="utf-8",
            newline="\n",
        )
        # Explicit public default; never copy the developer's local .datastore.
        (project_dir / ".datastore").write_text(
            "DATA_DIR=./data\n", encoding="utf-8", newline="\n"
        )
        included = ["pixi.toml", "pixi.lock", ".datastore", "README.md", "LICENSE"]
        copied_files = ["LICENSE", *(f"scripts/{name}" for name in PRODUCTION_SCRIPTS)]
        for relative_path in copied_files:
            source = repository / relative_path
            if source.is_symlink() or not source.resolve().is_relative_to(repository):
                raise ValueError(f"Source must be a repository file: {relative_path}")
            shutil.copyfile(source, project_dir / relative_path)
        included.extend(f"scripts/{name}" for name in PRODUCTION_SCRIPTS)

        # This runs after PyPI publication: no local wheel or editable dependency.
        subprocess.run(
            [
                "pixi",
                "lock",
                "--manifest-path",
                str(project_dir / "pixi.toml"),
                "--no-config",
                "--quiet",
            ],
            cwd=project_dir,
            check=True,
        )
        validate_lock(project_dir / "pixi.lock", version)
        # Only allowlisted files enter the archive, including after Pixi has run.
        temporary_zip = Path(temporary) / "bundle.zip"
        with ZipFile(temporary_zip, "w", compression=ZIP_DEFLATED) as archive:
            for relative_path in sorted(included):
                info = ZipInfo(f"{bundle_name}/{relative_path}")
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (project_dir / relative_path).read_bytes())
        temporary_zip.replace(archive_path)
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Published Waterlagen release tag")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    print(build_bundle(args.tag, args.output_dir))


if __name__ == "__main__":
    main()
