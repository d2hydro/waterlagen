"""Start het Waterlagen-keuzevenster vanuit de broncode of het productiepakket."""

import gc
import os
import sys
from pathlib import Path


def choose_datastore(project: Path) -> bool:
    """Open de gekozen datastore voordat Waterlagen wordt geladen."""
    from tools.runscript_maken.datastore_window import choose_profile

    path = choose_profile(project)
    # Release cycles left by Tk callbacks on their owning thread before HTTP workers start.
    gc.collect()
    if path is None:
        return False
    os.environ["WATERLAGEN_DATASTORE"] = str(path.resolve())
    return True


def main() -> int:
    project = Path(__file__).resolve().parent
    if not (project / "tools/runscript_maken").is_dir():
        project = project.parent
    sys.path.insert(0, str(project))
    # Waterlagen opens its datastore on import. Ask before loading the package.
    if not sys.argv[1:]:
        if not choose_datastore(Path.cwd()):
            return 0
        print("Waterlagen laden...", flush=True)

    from tools.runscript_maken.waterlagen import main as open_runscript

    return open_runscript()


if __name__ == "__main__":
    raise SystemExit(main())
