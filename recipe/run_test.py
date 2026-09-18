"""Verify that the installed package works outside a source checkout."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    """Test an installed conda package, independently of repository pytest runs."""
    environment = os.environ.copy()
    for name in ("DATA_DIR", "SOURCE_DATA_DIR", "PROCESSED_DATA_DIR", "PYTHONPATH"):
        environment.pop(name, None)

    with TemporaryDirectory() as directory:
        workdir = Path(directory)
        subprocess.run(
            [sys.executable, "-m", "waterlagen", "--help"],
            cwd=workdir,
            env=environment,
            check=True,
        )
        assert not (workdir / "data").exists(), "Help must not create data directories"
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "from waterlagen.datastore import DataStore, repo_root; "
                    "assert repo_root is None; "
                    "store = DataStore(); "
                    "assert store.data_dir == Path.cwd() / 'data'; "
                    "assert store.source_data_dir.is_dir(); "
                    "assert store.processed_data_dir.is_dir()"
                ),
            ],
            cwd=workdir,
            env=environment,
            check=True,
        )


if __name__ == "__main__":
    main()
