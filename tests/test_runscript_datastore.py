"""Controleer de datastorekeuze, gedeelde scripts en opslagpaden."""

import json
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from dotenv import dotenv_values
from waterlagen.datastore import DataStore

LAUNCHER = Path(__file__).resolve().parents[1] / "tools/runscript_maken.py"


def test_choose_named_profile_ignores_env(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(LAUNCHER.parents[1]))
    from tools.runscript_maken import datastore_window

    folder = tmp_path / "team"
    folder.mkdir()
    profile = folder / "HHNK.datastore"
    profile.write_text(
        "DATA_DIR=./data\nAHN_DATA_DIR=maps\nAHN4_DATA_DIR=archive\nTOP10NL_FILE=mine.gpkg\n",
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("SOURCE_DATA_DIR=wrong\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WATERLAGEN_DATASTORE", str(profile))
    monkeypatch.setattr(datastore_window, "choose_profile", lambda project: profile)
    assert runpy.run_path(str(LAUNCHER))["choose_datastore"](tmp_path)
    store = DataStore()
    assert store.source_data_dir == folder / "data/source_data"
    assert store.ahn_tiles(6) == folder / "maps/AHN6"
    assert store.ahn_tiles(4) == folder / "archive"
    assert store.top10nl_path == folder / "mine.gpkg"
    assert env.read_text() == "SOURCE_DATA_DIR=wrong\n"


def test_original_cache_and_cancel(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(LAUNCHER.parents[1]))
    from tools.runscript_maken import datastore_window

    monkeypatch.setattr(datastore_window, "choose_profile", lambda project: None)
    assert not runpy.run_path(str(LAUNCHER))["choose_datastore"](tmp_path)
    assert not (tmp_path / ".env").exists()
    store = DataStore(data_dir=tmp_path)
    assert store.ahn_tiles(4) == store.source_data_dir / "ahn/dtm_05"
    assert store.ahn_tiles(5) == store.source_data_dir / "ahn/ahn5/dtm_05"


def test_save_profile_preserves_comments_and_unrelated_settings(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(LAUNCHER.parents[1]))
    from tools.runscript_maken.datastore_window import write_profile

    profile = tmp_path / "nieuw.datastore"
    before = "# Team HHNK\nDATA_DIR=./data\nEXTRA=waarde\n"
    write_profile(
        profile,
        before,
        {"DATA_DIR": "./data", "AHN_DATA_DIR": "AHN"},
        {"DATA_DIR": "./data"},
    )
    assert "# Team HHNK" in profile.read_text()
    assert dotenv_values(profile) == {
        "DATA_DIR": "./data",
        "AHN_DATA_DIR": "AHN",
        "EXTRA": "waarde",
    }


def test_relative_datastore_in_batch(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(LAUNCHER.parents[1]))
    from tools.runscript_maken.script import build_batch_script
    from tools.runscript_maken.waterlagen import RunSettings, _commands
    from tools.runscript_maken.waterlagen_runfile import read_runfile

    root = tmp_path / "model"
    root.mkdir()
    profile = tmp_path / "Mijn HHNK.datastore"
    profile.write_text("DATA_DIR=./data")
    path = tmp_path / "run.bat"
    cmd = _commands(
        RunSettings(("dem",), ("--area", "nederland"), "kort", datastore_file=profile)
    )
    assert "--ahn-version latest" in cmd[0]
    path.write_text(build_batch_script(cmd, root, path), encoding="utf-8")
    assert "%~dp0Mijn HHNK.datastore" in path.read_text()
    assert read_runfile(path, root).datastore_file == profile


def test_shared_ahn_requires_explicit_consent(tmp_path,monkeypatch):
    import pytest
    from waterlagen.ahn import storage

    source=tmp_path/"team"
    source.mkdir()
    store=DataStore(data_dir=tmp_path)
    monkeypatch.delenv("WATERLAGEN_INTERACTIVE_DOWNLOAD",raising=False)
    monkeypatch.setattr(storage,"writable",lambda path: path != source)
    with pytest.raises(PermissionError, match="3 AHN6"):
        storage.download_target(store,source,6,3)
    with pytest.raises(FileNotFoundError):
        storage.reachable_source(tmp_path/"offline",6)
    downloads=tmp_path/"local"
    store.ahn_download_dir=downloads
    assert storage.download_target(store,source,6,3)==downloads/"AHN6"
    assert list(source.iterdir())==[]


@pytest.mark.parametrize("confirm", [True, False], ids=["open", "cancel"])
def test_datastore_window_releases_tk_before_background_collection(tmp_path, confirm):
    profile = tmp_path / ".datastore"
    profile.write_text("DATA_DIR=./data\n", encoding="utf-8")
    script = textwrap.dedent(
        """
        import gc
        import json
        import os
        import runpy
        import sys
        import threading
        import tkinter as tk
        import weakref
        from pathlib import Path
        from tkinter import ttk

        launcher = Path(sys.argv[1])
        project = Path(sys.argv[2])
        confirm = sys.argv[3] == "open"
        sys.path.insert(0, str(launcher.parents[1]))
        os.environ["LOCALAPPDATA"] = str(project / "preferences")
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetErrorMode(0x0002)

        from tools.runscript_maken import datastore_window

        roots = []
        errors = []
        sys.unraisablehook = lambda error: errors.append(str(error.exc_value))
        gc.disable()

        def hidden_window():
            try:
                root = tk.Tk()
            except tk.TclError as error:
                if "display" in str(error).lower():
                    print("TK_UNAVAILABLE: " + str(error), flush=True)
                    raise SystemExit(0)
                raise
            root.withdraw()
            roots.append(weakref.ref(root))

            def finish():
                if not confirm:
                    root.tk.call(root.protocol("WM_DELETE_WINDOW"))
                    return
                pending = list(root.winfo_children())
                while pending:
                    widget = pending.pop()
                    pending.extend(widget.winfo_children())
                    if isinstance(widget, ttk.Button) and widget.cget("text") == "Runmaker openen":
                        widget.invoke()
                        return
                raise AssertionError("Runmaker openen was not found")

            root.after(0, finish)
            root.after(5000, root.quit)
            return root

        datastore_window.create_run_window = hidden_window
        selected = runpy.run_path(str(launcher))["choose_datastore"](project)
        worker = threading.Thread(target=gc.collect)
        worker.start()
        worker.join(timeout=15)
        assert not worker.is_alive(), "Background collection did not finish"
        print(json.dumps({
            "selected": selected,
            "roots_released": all(reference() is None for reference in roots),
            "cleanup_errors": errors,
        }), flush=True)
        """
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(LAUNCHER),
            str(tmp_path),
            "open" if confirm else "cancel",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.stdout.startswith("TK_UNAVAILABLE:"):
        pytest.skip(result.stdout.strip())
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "selected": confirm,
        "roots_released": True,
        "cleanup_errors": [],
    }
    assert "Tcl_AsyncDelete" not in result.stderr
    assert "main thread is not in main loop" not in result.stderr
    assert profile.read_text(encoding="utf-8") == "DATA_DIR=./data\n"
