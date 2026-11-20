"""Werk een Waterlagen-productiepakket bij zonder instellingen of data te vervangen."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Collection
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

REPOSITORY = "d2hydro/waterlagen"
METADATA = "productiepakket.json"
PENDING = ".bijwerken-herstel.json"
UPDATER_FILES = ("tools/code_bijwerken.py", "code_bijwerken.bat", "code_bijwerken.sh")
ROOT_UPDATER_FILES = ("code_bijwerken.py", "code_bijwerken.cmd", "code_bijwerken.sh")
LEGACY_UPDATER_FILES = ("bijwerken.py", "bijwerken.cmd", "bijwerken.sh")
BASE_FILES = (
    "pixi.toml",
    "pixi.lock",
    "README.md",
    "LICENSE",
    "scripts/afwateringseenheden.py",
    "scripts/autos.py",
    "scripts/dem.py",
    "scripts/functioneel_landgebruik.py",
    "scripts/inwoners.py",
)
# Vaste softwarepaden; nieuwe Run Maker-bestanden komen uit het releasemanifest.
MANAGED_FILES = (
    *BASE_FILES,
    *UPDATER_FILES,
    *LEGACY_UPDATER_FILES,
    *ROOT_UPDATER_FILES,
    "runscript_maken.py",
    "runscript-maken.cmd",
    "runscript-maken.bat",
    "tools/runscript_maken.py",
    "run-maken.bat",
    "docs/reference/voorbeelden/brandlagen.toml",
    METADATA,
)
MANAGED_DIRECTORIES = ("tools/runscript_maken", "docs/icons")
HISTORICAL_FILES = {*BASE_FILES, *LEGACY_UPDATER_FILES}
VERSION_PATTERN = (
    r"v?(?P<version>\d{4}\.\d{1,2}\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?)"
)
MAX_DOWNLOAD = 32 * 1024 * 1024


def _version(tag: str) -> str:
    match = re.fullmatch(VERSION_PATTERN, tag)
    if match is None:
        raise ValueError(f"Ongeldig versienummer: {tag}")
    return match.group("version")


def _get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "waterlagen-bijwerken"})
    with urlopen(request, timeout=60) as response:
        content = response.read(MAX_DOWNLOAD + 1)
    if len(content) > MAX_DOWNLOAD:
        raise ValueError("Het downloadbestand is onverwacht groot")
    return content


def _release_order(version: str) -> tuple[int, ...]:
    """Order the project's supported release, prerelease and development versions."""
    match = re.fullmatch(
        r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?(?:\.post(\d+))?(?:\.dev(\d+))?", version
    )
    year, month, patch, pre, number, post, dev = match.groups()
    stage = {"a": 0, "b": 1, "rc": 2, None: 3}[pre]
    if pre is None and post is None and dev is not None:
        stage = -1
    return (
        int(year),
        int(month),
        int(patch),
        stage,
        int(number or 0),
        int(post or 0),
        int(dev is None),
        int(dev or 0),
    )


def _release(tag: str | None) -> str:
    base = f"https://api.github.com/repos/{REPOSITORY}/releases"
    if tag is None:
        info = json.loads(_get(f"{base}/latest"))
    else:
        version = _version(tag)
        try:
            info = json.loads(_get(f"{base}/tags/{tag}"))
        except HTTPError as error:
            if error.code != 404:
                raise
            alternative = version if tag.startswith("v") else f"v{version}"
            info = json.loads(_get(f"{base}/tags/{alternative}"))
    result = info["tag_name"]
    _version(result)
    return result


def _manifest_version(content: bytes) -> str:
    manifest = tomllib.loads(content.decode("utf-8"))
    workspace = manifest["workspace"]
    if workspace["name"] != "waterlagen-productie":
        raise ValueError(
            "Start bijwerken vanuit een uitgepakt Waterlagen-productiepakket"
        )
    if "version" not in workspace:
        raise ValueError(
            "Dit oudere project is geen versiegebonden productiepakket; automatisch bijwerken is niet beschikbaar"
        )
    version = _version(workspace["version"])
    if manifest["pypi-dependencies"]["waterlagen"] != f"=={version}":
        raise ValueError("Het productiepakket heeft geen vaste Waterlagen-versie")
    return version


def _hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {
        name: hashlib.sha256(content).hexdigest()
        for name, content in files.items()
        if name != METADATA
    }


def _validated_names(names: Collection[str]) -> set[str]:
    """Begrens manifestnamen tot pakketsoftware, ook op Windows."""
    seen = set()
    result = set()
    devices = {"con", "prn", "aux", "nul"}
    devices.update(
        f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
    )
    for name in names:
        if not isinstance(name, str):
            raise ValueError("Een softwarepad moet tekst zijn")
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or str(path) != name
            or ".." in path.parts
            or re.search(r'[\\<>:"|?*\x00-\x1f]', name)
            or any(
                part.rstrip(" .") != part or part.split(".")[0].casefold() in devices
                for part in path.parts
            )
        ):
            raise ValueError(f"Ongeldig softwarepad: {name}")
        if name not in MANAGED_FILES and not any(
            path.is_relative_to(directory) and str(path) != directory
            for directory in MANAGED_DIRECTORIES
        ):
            raise ValueError(f"Geen beheerd softwarebestand: {name}")
        folded = name.casefold()
        if folded in seen:
            raise ValueError(f"Dubbel softwarepad: {name}")
        seen.add(folded)
        result.add(name)
    for name in result:
        if any(
            str(parent).casefold() in seen for parent in PurePosixPath(name).parents
        ):
            raise ValueError(f"Softwarepad is ook een bovenliggende map: {name}")
    return result


def _metadata_files(content: bytes | str, version: str) -> dict[str, str]:
    """Lees de versie en gecontroleerde softwarebestanden uit pakketmetadata."""
    metadata = json.loads(content)
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        raise ValueError("De releasegegevens passen niet bij de pakketversie")
    files = metadata.get("files")
    if not isinstance(files, dict):
        raise ValueError("Ongeldige bestandslijst in de releasegegevens")
    names = _validated_names(files)
    if not set(BASE_FILES).issubset(names) or METADATA in names:
        raise ValueError("Onvolledige bestandslijst in de releasegegevens")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in files.values()
    ):
        raise ValueError("Ongeldige bestandscontrole in de releasegegevens")
    return files


def _has_updater(names: Collection[str]) -> bool:
    return any(
        set(required).issubset(names)
        for required in (UPDATER_FILES, ROOT_UPDATER_FILES, LEGACY_UPDATER_FILES)
    )


def _bundle(tag: str) -> dict[str, bytes]:
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/waterlagen-productie.zip"
    with ZipFile(BytesIO(_get(url))) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        _validated_names([name for name in names if name != ".datastore"])
        if len(names) != len(set(names)) or any(entry.is_dir() for entry in entries):
            raise ValueError("Dubbele bestanden of mappen in het productiepakket")
        if (
            not set(BASE_FILES).issubset(names)
            or sum(entry.file_size for entry in entries) > MAX_DOWNLOAD
        ):
            raise ValueError("Onvolledig of te groot productiepakket")
        files = {name: archive.read(name) for name in names if name != ".datastore"}
    version = _version(tag)
    if _manifest_version(files["pixi.toml"]) != version:
        raise ValueError("De pakketversie wijkt af van de release")
    if METADATA in files:
        expected = _metadata_files(files[METADATA], version)
        if expected != _hashes(files):
            raise ValueError("De bestandscontrole van de release klopt niet")
        if not _has_updater(files):
            raise ValueError("De release bevat geen volledige updater")
    elif set(files) - HISTORICAL_FILES:
        raise ValueError("Onbekende bestanden zonder releasegegevens")
    return files


def _checked_path(root: Path, path: Path) -> Path:
    """Sta geen symlink of junction toe tussen de projectmap en het doel."""
    if (
        not path.is_relative_to(root)
        or ".." in path.relative_to(root).parts
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError(f"Bestand verwijst buiten de projectmap: {path}")
    current = path
    while current != root:
        try:
            info = current.lstat()
        except FileNotFoundError:
            pass
        else:
            if current.is_symlink() or getattr(info, "st_reparse_tag", None) == getattr(
                stat, "IO_REPARSE_TAG_MOUNT_POINT", -1
            ):
                raise ValueError(f"Softwarepad bevat een symlink of junction: {path}")
        current = current.parent
    return path


def _target(root: Path, name: str, managed_names: Collection[str]) -> Path:
    if name not in managed_names:
        raise ValueError(f"Geen beheerd softwarebestand: {name}")
    return _checked_path(root, root / name)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
        if path.suffix == ".sh":
            temporary.chmod(0o755)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _update_lock(root: Path):
    """OS locks are released on exit, including after an interrupted updater."""
    with _checked_path(root, root / ".bijwerken.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Er is al een updater actief in deze map") from error
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _pixi(
    root: Path, *arguments: str, capture: bool = False
) -> subprocess.CompletedProcess:
    executable = shutil.which("pixi")
    if executable is None:
        raise RuntimeError("Pixi is niet gevonden. Installeer Pixi en probeer opnieuw.")
    return subprocess.run(
        [
            executable,
            arguments[0],
            "--manifest-path",
            str(root / "pixi.toml"),
            *arguments[1:],
        ],
        cwd=root,
        check=True,
        timeout=1800,
        capture_output=capture,
        text=True,
    )


def _check_idle(root: Path) -> None:
    # Ask the installed package to interpret .datastore and environment overrides.
    command = "import json; from waterlagen.datastore import DataStore; print(json.dumps(str(DataStore().processed_data_dir.resolve())))"
    result = _pixi(root, "run", "--locked", "python", "-c", command, capture=True)
    processed = Path(json.loads(result.stdout.strip()))
    locks = list(processed.glob("*/*/*/.run.lock"))
    if locks:
        raise RuntimeError(
            f"Stop eerst de actieve productie. Runvergrendeling: {locks[0]}"
        )


def _check_local_files(root: Path, current: str, new: dict[str, bytes]) -> set[str]:
    metadata_path = _checked_path(root, root / METADATA)
    if metadata_path.exists():
        expected = _metadata_files(metadata_path.read_bytes(), current)
    else:
        print("Oorspronkelijke softwarebestanden controleren...", flush=True)
        expected = _hashes(_bundle(_release(current)))
    changed = []
    managed_names = _validated_names(set(expected) | set(new))
    for name in sorted(managed_names):
        path = _target(root, name, managed_names)
        if name == METADATA:
            continue
        if name in expected:
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]
            ):
                changed.append(name)
        elif path.exists() and path.read_bytes() != new[name]:
            changed.append(name)
    if changed:
        raise ValueError(
            "Lokaal aangepaste of ontbrekende softwarebestanden; niets vervangen: "
            + ", ".join(sorted(changed))
        )
    return set(expected)


def _checks(root: Path) -> None:
    _pixi(root, "install", "--locked")
    _pixi(root, "run", "--locked", "controleer")


def _restore(root: Path) -> None:
    state = json.loads(_checked_path(root, root / PENDING).read_bytes())
    if (
        not isinstance(state, dict)
        or not isinstance(state.get("backup"), str)
        or not isinstance(state.get("files"), dict)
    ):
        raise ValueError("Ongeldige herstelgegevens")
    backup = _checked_path(root, root / state["backup"])
    if (
        not backup.resolve().is_relative_to(root / ".updates")
        or backup.resolve() == root / ".updates"
    ):
        raise ValueError("Ongeldig herstelpad")
    managed_names = _validated_names(state["files"])
    if any(not isinstance(value, bool) for value in state["files"].values()):
        raise ValueError("Ongeldige herstelgegevens")
    restoration = []
    for name, existed in state["files"].items():
        target = _target(root, name, managed_names)
        content = _target(backup, name, managed_names).read_bytes() if existed else None
        restoration.append((target, content))
    for target, content in restoration:
        if content is not None:
            _write(target, content)
        else:
            target.unlink(missing_ok=True)
    _checks(root)
    (root / PENDING).unlink()


def _apply(
    root: Path, files: dict[str, bytes], previous_files: Collection[str]
) -> None:
    # Verwijder alleen software die aantoonbaar bij de vorige levering hoorde.
    managed_names = _validated_names(set(previous_files) | set(files))
    obsolete = sorted(
        name
        for name in previous_files
        if name not in files and _target(root, name, managed_names).exists()
    )
    backup_root = _checked_path(root, root / ".updates")
    _checked_path(root, root / PENDING)
    backup_root.mkdir(exist_ok=True)
    backup = Path(
        tempfile.mkdtemp(
            prefix=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-"), dir=backup_root
        )
    )
    existed = {}
    for name in [*files, *obsolete]:
        target = _target(root, name, managed_names)
        existed[name] = target.exists()
        if existed[name]:
            _write(backup / name, target.read_bytes())
    state = {"backup": str(backup.relative_to(root)), "files": existed}
    _write(root / PENDING, json.dumps(state).encode())
    try:
        for name, content in files.items():
            _write(_target(root, name, managed_names), content)
        for name in obsolete:
            _target(root, name, managed_names).unlink()
        _checks(root)
    except BaseException as error:
        print("Bijwerken mislukt. Vorige versie herstellen...", flush=True)
        try:
            _restore(root)
        except BaseException as restore_error:
            raise RuntimeError(
                f"Herstel niet voltooid. Start bijwerken opnieuw om te herstellen. Reservekopie: {backup}"
            ) from restore_error
        raise RuntimeError(
            "Bijwerken mislukt; de vorige versie is hersteld en gecontroleerd"
        ) from error
    (root / PENDING).unlink()


def update(root: Path, *, version: str | None = None, yes: bool = False) -> None:
    """Install a tested release, preserving user files and recovering failed updates."""
    root = root.resolve()
    if Path(sys.prefix).resolve().is_relative_to(root / ".pixi"):
        raise RuntimeError(
            "Start de updater via code_bijwerken.bat of code_bijwerken.sh, buiten de productieomgeving"
        )
    _manifest_version(_checked_path(root, root / "pixi.toml").read_bytes())
    with _update_lock(root):
        if (root / PENDING).exists():
            print("Een eerdere update is onderbroken. De vorige versie wordt hersteld.")
            _restore(root)
            print(
                "Vorige versie hersteld. Start bijwerken opnieuw voor een nieuwe update."
            )
            return
        current = _manifest_version((root / "pixi.toml").read_bytes())
        print(f"Huidige versie: {current}. Release controleren...", flush=True)
        tag = _release(version)
        latest = _version(tag)
        if latest == current:
            print("Deze versie is al geïnstalleerd.")
            return
        if version is None and _release_order(latest) < _release_order(current):
            print("Er is geen nieuwere stabiele release beschikbaar.")
            return
        print(f"Beschikbare versie: {latest}. Instellingen en data blijven behouden.")
        if not yes and input("Bijwerken? [j/N] ").strip().lower() not in {"j", "ja"}:
            print("Niet bijgewerkt.")
            return
        _check_idle(root)
        print("Productiepakket downloaden...", flush=True)
        files = _bundle(tag)
        if not {*BASE_FILES, METADATA}.issubset(files) or not _has_updater(files):
            raise ValueError("Deze release ondersteunt automatisch bijwerken nog niet")
        previous_files = _check_local_files(root, current, files)
        _check_idle(root)
        _apply(root, files, previous_files)
        print(f"Bijwerken geslaagd: Waterlagen {latest}. Projectmap: {root}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versie", help="Gewenste release; standaard de nieuwste stabiele release"
    )
    parser.add_argument(
        "--ja", action="store_true", help="Bijwerken zonder bevestigingsvraag"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        help="Bestaande productiemap bij een los opgehaalde updater",
    )
    args = parser.parse_args()
    try:
        project = args.project_dir
        if project is None:
            project = Path(__file__).resolve().parent
            if project.name == "tools":
                project = project.parent
        update(project, version=args.versie, yes=args.ja)
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        BadZipFile,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as error:
        print(f"Bijwerken gestopt: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
