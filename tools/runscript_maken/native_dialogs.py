"""Windows-bestandskeuzes blijven op de hoofdthread van Tk."""

import sys
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from tkinter import filedialog


class NativeDialogs:
    """Laat HTTP-verzoeken veilig een lokaal bestandsvenster openen."""

    def __init__(self, root: tk.Tk, project: Path) -> None:
        self.root = root
        self.project = project
        self.pending: Queue[tuple[Callable[[], str], Future[str]]] = Queue()
        self._dialog_lock = Lock()
        root.after(50, self._poll)

    def _poll(self) -> None:
        try:
            action, result = self.pending.get_nowait()
        except Empty:
            pass
        else:
            try:
                result.set_result(action())
            except Exception as error:  # noqa: BLE001 - forward failures to the HTTP caller
                result.set_exception(error)
        self.root.after(50, self._poll)

    def _call(self, action: Callable[[], str]) -> str:
        if not self._dialog_lock.acquire(blocking=False):
            raise ValueError("Sluit eerst het geopende Waterlagen-venster.")
        try:
            result: Future[str] = Future()
            self.pending.put((action, result))
            return result.result()
        finally:
            self._dialog_lock.release()

    def _file_dialog(self, action: Callable[[tk.Toplevel], str]) -> str:
        """Geef de dialoog focus via een onzichtbaar, gemapt venster."""
        owner = tk.Toplevel(self.root)
        try:
            if sys.platform == "win32":
                owner.attributes("-toolwindow", True)
            owner.geometry("1x1+0+0")
            owner.attributes("-alpha", 0)
            owner.attributes("-topmost", True)
            owner.update_idletasks()
            owner.lift()
            owner.focus_force()
            return action(owner)
        finally:
            owner.destroy()

    def open(self, title: str, pattern: str) -> Path | None:
        value = self._call(
            lambda: self._file_dialog(
                lambda owner: filedialog.askopenfilename(
                    parent=owner,
                    title=title,
                    initialdir=self.project,
                    filetypes=[(title, pattern), ("Alle bestanden", "*")],
                ),
            )
        )
        return Path(value).resolve() if value else None

    def save(self, title: str, suffix: str, name: str) -> Path | None:
        value = self._call(
            lambda: self._file_dialog(
                lambda owner: filedialog.asksaveasfilename(
                    parent=owner,
                    title=title,
                    initialdir=self.project,
                    initialfile=name,
                    defaultextension=suffix,
                    filetypes=[(title, "*" + suffix)],
                    confirmoverwrite=True,
                ),
            )
        )
        return Path(value).resolve() if value else None

    def directory(self, title: str) -> Path | None:
        value = self._call(
            lambda: self._file_dialog(
                lambda owner: filedialog.askdirectory(
                    parent=owner, title=title, initialdir=self.project
                ),
            )
        )
        return Path(value).resolve() if value else None

    def brandlagen(self, path: str) -> str:
        from .brandlagen import open_options

        def edit(owner: tk.Toplevel) -> str:
            variable = tk.StringVar(master=owner, value=path)
            open_options(owner, variable)
            window = next(
                child
                for child in owner.winfo_children()
                if isinstance(child, tk.Toplevel)
            )
            window.attributes("-topmost", True)
            window.update_idletasks()
            window.lift()
            window.focus_force()
            owner.wait_window(window)
            return variable.get()

        return self._call(lambda: self._file_dialog(edit))
