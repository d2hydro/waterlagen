"""Een keuzevenster met een voorbeeld, opslag en startknop voor runscripts."""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .script import ScriptPlan, build_batch_script, build_script, save_script

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import ttk

    from PIL import ImageTk


def _scaled_image(path: Path, size: int, master: tk.Misc) -> ImageTk.PhotoImage:
    """Verklein met vloeiende randen en behoud transparantie."""
    from PIL import Image, ImageTk

    with Image.open(path) as source:
        scaled = source.convert("RGBA")
        scaled.thumbnail((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(scaled, master=master)


def add_help(parent: ttk.Frame, *, summary: str, url: str) -> None:
    """Toon aanklikbare uitleg bij de infoknop."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    hint: tk.Toplevel | None = None
    hide_after: str | None = None

    def keep_hint(event: tk.Event | None = None) -> None:
        nonlocal hide_after
        if hide_after is not None:
            parent.after_cancel(hide_after)
            hide_after = None

    def hide_hint(event: tk.Event | None = None) -> None:
        nonlocal hint
        keep_hint()
        if hint is not None:
            hint.destroy()
            hint = None

    def leave_hint(event: tk.Event | None = None) -> None:
        nonlocal hide_after
        keep_hint()
        # Geef de muis tijd om van het icoon naar de uitleg te gaan.
        hide_after = parent.after(300, hide_hint)

    def open_manual(event: tk.Event | None = None) -> None:
        hide_hint()
        try:
            opened = webbrowser.open_new_tab(url)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            messagebox.showerror(
                "Handleiding openen lukt niet",
                f"Open deze link in je browser:\n{url}",
                parent=parent.winfo_toplevel(),
            )

    def show_hint(event: tk.Event | None = None) -> None:
        nonlocal hint
        keep_hint()
        if hint is not None:
            return
        hint = tk.Toplevel(parent)
        hint.withdraw()
        hint.overrideredirect(True)
        link = tk.Button(
            hint,
            text=f"{summary} ↗",
            command=open_manual,
            wraplength=320,
            justify="left",
            font=("Segoe UI", 10, "underline"),
            foreground="#116b65",
            background="#ffffff",
            activeforeground="#0d554f",
            activebackground="#edf5f4",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=10,
        )
        link.pack()
        for widget in (hint, link):
            for name in ("<Enter>", "<FocusIn>"):
                widget.bind(name, keep_hint)
            for name in ("<Leave>", "<FocusOut>"):
                widget.bind(name, leave_hint)
            widget.bind("<Escape>", hide_hint)
        link.bind("<Return>", open_manual)
        hint.update_idletasks()
        x = min(info.winfo_rootx(), hint.winfo_screenwidth() - hint.winfo_reqwidth())
        y = info.winfo_rooty() + info.winfo_height() + 4
        if y + hint.winfo_reqheight() > hint.winfo_screenheight():
            y = info.winfo_rooty() - hint.winfo_reqheight() - 4
        hint.geometry(f"+{max(0, x)}+{max(0, y)}")
        hint.deiconify()

    style = ttk.Style(parent)
    # Alleen het kleine infosymbool; de focusrand blijft voor toetsenbordgebruik.
    style.layout(
        "Help.TButton",
        [("Button.focus", {"children": [("Button.label", {"sticky": "nswe"})]})],
    )
    style.configure(
        "Help.TButton",
        padding=(2, 0),
        font=("Segoe UI Symbol", 11),
        foreground="#64748b",
        background="#ffffff",
        anchor="center",
    )
    style.map(
        "Help.TButton",
        foreground=[("active", "#116b65"), ("focus", "#116b65")],
        background=[("active", "#eaf5f3"), ("focus", "#eaf5f3")],
    )
    info = ttk.Button(
        parent,
        text="ⓘ",
        width=2,
        style="Help.TButton",
        command=open_manual,
        cursor="hand2",
    )
    info.pack(side="left", padx=(5, 0))
    for event in ("<Enter>", "<FocusIn>"):
        info.bind(event, show_hint)
    for event in ("<Leave>", "<FocusOut>"):
        info.bind(event, leave_hint)
    for event in ("<Escape>", "<Destroy>"):
        info.bind(event, hide_hint)
    info.bind("<Return>", open_manual)


def open_window(
    project: Path,
    build_form: Callable[[ttk.Frame], Callable[[], ScriptPlan]],
    *,
    title: str = "Runscript maken",
    description: str = "Kies je opties. Sla het script op of start meteen.",
    logo: Path | None = None,
    icon: Path | None = None,
    application_name: str = "",
) -> None:
    """Toon de keuzes van een toepassing en bewaar of start de gekozen opdrachten.

    ``build_form`` vult het formulier en geeft een functie terug die de huidige
    keuzes leest. Die functie levert een ``ScriptPlan`` of meldt een ValueError.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(title)
    if icon is not None:
        window_icon = _scaled_image(icon, 32, root)
        root.iconphoto(True, window_icon)
    width = min(760, root.winfo_screenwidth() - 80)
    height = min(900, root.winfo_screenheight() - 100)
    root.geometry(f"{width}x{height}")
    root.minsize(640, 520)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".", font=("Segoe UI", 10), background="#ffffff", foreground="#203644"
    )
    style.configure(
        "TButton", padding=(12, 8), background="#f4f7f8", bordercolor="#d9e2e7"
    )
    style.map("TButton", background=[("active", "#e8eff1")])
    style.configure("Compact.TButton", padding=(12, 5))
    style.configure("TSeparator", background="#e4ebef")
    # Gebruik de vertrouwde Windows-vinkjes binnen de rustige vensterstijl.
    if "vista" in style.theme_names():
        for control in ("Checkbutton", "Radiobutton"):
            indicator = f"Native.{control}.indicator"
            style.element_create(indicator, "from", "vista", f"{control}.indicator")
            style.layout(
                f"T{control}",
                [
                    (
                        f"{control}.padding",
                        {
                            "sticky": "nswe",
                            "children": [
                                (indicator, {"side": "left"}),
                                (
                                    f"{control}.focus",
                                    {
                                        "side": "left",
                                        "sticky": "w",
                                        "children": [
                                            (f"{control}.label", {"sticky": "nswe"})
                                        ],
                                    },
                                ),
                            ],
                        },
                    )
                ],
            )
    style.configure("TCheckbutton", padding=(0, 5))
    style.configure("TRadiobutton", padding=(0, 4))
    style.configure(
        "TEntry", padding=(8, 6), fieldbackground="#ffffff", bordercolor="#cbd5dc"
    )
    style.configure("TCombobox", padding=(8, 6), bordercolor="#cbd5dc")
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "#ffffff")],
        foreground=[("readonly", "#203644")],
    )
    style.configure(
        "TSpinbox", padding=(8, 6), fieldbackground="#ffffff", bordercolor="#cbd5dc"
    )
    style.configure(
        "Heading.TLabel", font=("Segoe UI", 12, "bold"), foreground="#123f4b"
    )
    style.configure("Hint.TLabel", foreground="#647482", font=("Segoe UI", 9))
    style.configure("Header.TFrame", background="#007db8")
    style.configure("Header.TLabel", background="#007db8", foreground="#ffffff")
    style.configure("Title.Header.TLabel", font=("Segoe UI", 22, "bold"))
    style.configure(
        "Brand.Header.TLabel", font=("Segoe UI", 10, "bold"), foreground="#ffffff"
    )
    style.configure("Footer.TFrame", background="#f4f7f8")
    style.configure(
        "Footer.TLabel",
        background="#f4f7f8",
        foreground="#647482",
        font=("Segoe UI", 9),
    )
    style.configure(
        "Save.TButton",
        background="#007db8",
        foreground="#ffffff",
        bordercolor="#007db8",
    )
    style.map(
        "Save.TButton", background=[("active", "#00689a"), ("disabled", "#cbd5dc")]
    )
    root.configure(background="#ffffff")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    header = ttk.Frame(root, padding=(28, 16), style="Header.TFrame")
    header.grid(row=0, column=0, sticky="ew")
    if logo is not None:
        header_logo = _scaled_image(logo, 28, root)
        ttk.Label(header, image=header_logo, style="Header.TLabel").pack(
            side="left", padx=(0, 14)
        )
    headings = ttk.Frame(header, style="Header.TFrame")
    headings.pack(side="left", fill="x", expand=True)
    if application_name:
        ttk.Label(headings, text=application_name, style="Brand.Header.TLabel").pack(
            anchor="w"
        )
    ttk.Label(headings, text="Runscript maken", style="Title.Header.TLabel").pack(
        anchor="w"
    )
    ttk.Label(
        headings,
        text=description,
        style="Header.TLabel",
        wraplength=460,
    ).pack(anchor="w", pady=(4, 0))

    body = ttk.Frame(root)
    body.grid(row=1, column=0, sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)
    canvas = tk.Canvas(body, background="#ffffff", highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)
    frame = ttk.Frame(canvas, padding=(28, 18))
    form_window = canvas.create_window((0, 0), window=frame, anchor="nw")

    def resize_form(event: tk.Event | None = None) -> None:
        canvas.itemconfigure(form_window, width=canvas.winfo_width())
        canvas.configure(scrollregion=canvas.bbox("all"))
        if frame.winfo_reqheight() > canvas.winfo_height():
            scrollbar.grid()
        else:
            scrollbar.grid_remove()
            canvas.yview_moveto(0)

    frame.bind("<Configure>", resize_form)
    canvas.bind("<Configure>", resize_form)

    def scroll_form(event: tk.Event) -> None:
        if isinstance(event.widget, (ttk.Combobox, ttk.Spinbox)):
            return
        if (
            canvas.winfo_rooty()
            <= event.y_root
            < canvas.winfo_rooty() + canvas.winfo_height()
        ):
            canvas.yview_scroll(-int(event.delta / 120), "units")

    root.bind("<MouseWheel>", scroll_form)

    read_plan = build_form(frame)

    def preview() -> None:
        try:
            plan = read_plan()
            script = (
                build_batch_script(plan.commands, project)
                if sys.platform == "win32"
                else build_script(plan.commands)
            )
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

    def save(*, start: bool = False) -> None:
        try:
            plan = read_plan()
            script = (
                build_batch_script(plan.commands, project)
                if sys.platform == "win32"
                else build_script(plan.commands)
            )
            filename = filedialog.asksaveasfilename(
                parent=root,
                title="Runscript opslaan",
                initialdir=project,
                initialfile=f"{plan.name}.bat"
                if sys.platform == "win32"
                else f"{plan.name}.ps1",
                defaultextension=".bat" if sys.platform == "win32" else ".ps1",
                filetypes=[("Windows-runfile", "*.bat")]
                if sys.platform == "win32"
                else [("PowerShell-script", "*.ps1")],
            )
            if not filename:
                return
            if Path(filename).suffix.lower() == ".bat":
                script = build_batch_script(plan.commands, project, Path(filename))
            else:
                script = build_script(plan.commands)
            save_script(script, Path(filename), project, start=start)
            if start:
                status.set(
                    "Runfile opgeslagen. Volg de uitvoering in het geopende venster."
                )
            else:
                if sys.platform == "win32":
                    explanation = (
                        f"Dubbelklik om te starten:\n{filename}"
                        "\n\nJe kunt de pixi-commando's in dit bestand aanpassen."
                    )
                else:
                    explanation = f"Opgeslagen: {filename}\n\nVoer de commando's uit in PowerShell vanuit:\n{project}"
                messagebox.showinfo("Runscript opgeslagen", explanation, parent=root)
        except (ValueError, OSError) as error:
            messagebox.showerror(
                "Opslaan of starten niet gelukt", str(error), parent=root
            )

    footer = ttk.Frame(root, padding=(28, 16), style="Footer.TFrame")
    footer.grid(row=2, column=0, sticky="ew")
    buttons = ttk.Frame(footer, style="Footer.TFrame")
    buttons.pack(fill="x")
    buttons.columnconfigure((0, 1, 2), weight=1, uniform="action")
    ttk.Button(buttons, text="Script bekijken", command=preview).grid(
        row=0, column=0, sticky="ew"
    )
    ttk.Button(buttons, text="Alleen opslaan", command=save).grid(
        row=0, column=1, sticky="ew", padx=10
    )
    start_button = ttk.Button(
        buttons,
        text="Opslaan en starten",
        command=lambda: save(start=True),
        style="Save.TButton",
    )
    start_button.grid(row=0, column=2, sticky="ew")
    status = tk.StringVar(value="Bij starten wordt het script eerst opgeslagen.")
    ttk.Label(footer, textvariable=status, style="Footer.TLabel", wraplength=590).pack(
        anchor="w", pady=(10, 0)
    )
    root.mainloop()
