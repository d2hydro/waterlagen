"""Een keuzevenster met een voorbeeld, opslag en startknop voor runscripts."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .script import ScriptPlan, build_script, save_script

if TYPE_CHECKING:
    from tkinter import ttk


def open_window(
    project: Path,
    build_form: Callable[[ttk.Frame], Callable[[], ScriptPlan]],
    *,
    title: str = "Runscript maken",
    description: str = "Kies je opties. Sla het script op of start meteen.",
) -> None:
    """Toon de keuzes van een toepassing en bewaar of start de gekozen opdrachten.

    ``build_form`` vult het formulier en geeft een functie terug die de huidige
    keuzes leest. Die functie levert een ``ScriptPlan`` of meldt een ValueError.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(title)
    root.geometry("680x850")
    root.minsize(660, 850)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 11), background="#f5f7f8")
    style.configure("TButton", padding=(14, 9))
    style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
    style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("Hint.TLabel", foreground="#52616a", font=("Segoe UI", 10))
    style.configure("Save.TButton", background="#116b65", foreground="white")
    root.configure(background="#f5f7f8")
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Runscript maken", style="Title.TLabel").pack(anchor="w")
    ttk.Label(
        frame,
        text=description,
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(5, 22))

    read_plan = build_form(frame)

    def preview() -> None:
        try:
            script = "\n".join(read_plan().commands)
        except ValueError as error:
            messagebox.showerror("Controleer je keuzes", str(error), parent=root)
            return
        from tkinter.scrolledtext import ScrolledText

        window = tk.Toplevel(root)
        window.title("Voorbeeld runscript")
        text = ScrolledText(window, width=100, height=30, font=("Consolas", 10))
        text.pack(fill="both", expand=True)
        text.insert("1.0", script)
        text.configure(state="disabled")

    script_process: subprocess.Popen | None = None

    def check_process() -> None:
        if script_process is not None and script_process.poll() is None:
            root.after(1000, check_process)
            return
        start_button.state(["!disabled"])
        status.set("Scriptvenster gesloten. Bekijk de uitvoer voor het resultaat.")

    def save(*, start: bool = False) -> None:
        nonlocal script_process
        try:
            plan = read_plan()
            script = build_script(plan.commands, project)
            filename = filedialog.asksaveasfilename(
                parent=root,
                title="Runscript opslaan",
                initialdir=project,
                initialfile=f"{plan.name}.ps1",
                defaultextension=".ps1",
                filetypes=[("PowerShell-script", "*.ps1")],
            )
            if not filename:
                return
            process = save_script(script, Path(filename), project, start=start)
            if start:
                script_process = process
                start_button.state(["disabled"])
                status.set(
                    "Script opgeslagen. Volg de uitvoering in het PowerShell-venster."
                )
                root.after(1000, check_process)
            else:
                messagebox.showinfo(
                    "Runscript opgeslagen",
                    f"Opgeslagen: {filename}\n\nJe kunt het script later aanpassen en uitvoeren in PowerShell.\nHet script is nog niet gestart.",
                    parent=root,
                )
        except (ValueError, OSError) as error:
            messagebox.showerror(
                "Opslaan of starten niet gelukt", str(error), parent=root
            )

    buttons = ttk.Frame(frame)
    buttons.pack(side="bottom", fill="x", pady=(18, 0))
    ttk.Button(buttons, text="Script bekijken", command=preview).pack(side="left")
    ttk.Button(buttons, text="Alleen opslaan", command=save).pack(side="left", padx=8)
    start_button = ttk.Button(
        buttons,
        text="Opslaan en starten",
        command=lambda: save(start=True),
        style="Save.TButton",
    )
    start_button.pack(side="right")
    status = tk.StringVar(value="Bij starten wordt het script eerst opgeslagen.")
    ttk.Label(frame, textvariable=status, style="Hint.TLabel", wraplength=590).pack(
        side="bottom", anchor="w", pady=(12, 0)
    )
    root.mainloop()
