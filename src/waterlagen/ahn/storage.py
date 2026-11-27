"""Gebruik gedeelde AHN-tegels en vraag toestemming voor lokale downloads."""

import os
import tempfile
from pathlib import Path

from waterlagen.datastore import DataStore


def reachable_source(path: Path, version: int) -> Path:
    """Controleer de bronmap voordat tegels worden opgezocht."""
    while not path.is_dir():
        if os.getenv("WATERLAGEN_INTERACTIVE_DOWNLOAD") != "1":
            raise FileNotFoundError(
                f"AHN{version}-bronmap ontbreekt of is onbereikbaar: {path}. Controleer de datastore."
            )
        from tkinter import filedialog, messagebox

        answer = messagebox.askyesnocancel(
            "AHN-bronmap onbereikbaar",
            f"AHN{version}: {path}\n\nJa: opnieuw proberen. Nee: andere bronmap kiezen.",
        )
        if answer is None:
            raise OSError("Run geannuleerd.")
        if not answer:
            choice = filedialog.askdirectory(title=f"AHN{version}-tegelmap kiezen")
            if not choice:
                raise OSError("Run geannuleerd.")
            path = Path(choice)
    return path


def writable(path: Path) -> bool:
    """Controleer of een tijdelijk bestand kan worden aangemaakt."""
    try:
        with tempfile.TemporaryFile(dir=path):
            return True
    except OSError:
        return False


def download_target(store: DataStore, source: Path, version: int, missing: int) -> Path:
    """Gebruik een lokale downloadmap na toestemming voor deze run."""
    if writable(source):
        return source
    if store.ahn_download_dir is None:
        if os.getenv("WATERLAGEN_INTERACTIVE_DOWNLOAD") != "1":
            raise PermissionError(
                f"{missing} AHN{version}-tegels ontbreken in de alleen-lezen map {source}. Geef --ahn-download-dir MAP op om lokaal downloaden toe te staan."
            )
        from tkinter import filedialog, messagebox

        default = store.source_data_dir / "ahn_downloads"
        allowed = messagebox.askyesnocancel(
            "AHN-tegels lokaal downloaden?",
            f"{missing} AHN{version}-tegels ontbreken in {source}.\nDownloadmap: {default}\n\nJa: toestaan voor deze run. Nee: andere map kiezen.",
        )
        if allowed is None:
            raise OSError("Download geannuleerd.")
        if allowed and writable(store.source_data_dir):
            chosen = default
        else:
            choice = filedialog.askdirectory(title="Schrijfbare downloadmap kiezen")
            if not choice:
                raise OSError("Download geannuleerd.")
            chosen = Path(choice)
        store.ahn_download_dir = chosen
    target = store.ahn_download_dir / f"AHN{version}"
    target.mkdir(parents=True, exist_ok=True)
    if not writable(target):
        raise PermissionError(f"Downloadmap is niet schrijfbaar: {target}")
    return target
