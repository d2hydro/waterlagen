"""Start het Waterlagen-keuzevenster vanuit de broncode of het productiepakket."""

import sys
from pathlib import Path


def main() -> int:
    project = Path(__file__).resolve().parent
    if not (project / "tools/runscript_maken").is_dir():
        project = project.parent
    sys.path.insert(0, str(project))
    from tools.runscript_maken.waterlagen import main as open_runscript

    return open_runscript()


if __name__ == "__main__":
    raise SystemExit(main())
