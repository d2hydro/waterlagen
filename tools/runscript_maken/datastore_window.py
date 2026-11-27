"""Kies en bewerk een Waterlagen-datastore."""

import os
import tempfile
import threading
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from waterlagen_paths import ahn_tile_directory

from dotenv import dotenv_values, set_key, unset_key

from .native_dialogs import create_run_window


SOURCES = {
    "BAG": "bag",
    "BGT": "bgt",
    "BRP": "brp",
    "CBS": "cbs",
    "HyDAMO": "hydamo",
    "Bestuurlijke gebieden": "administratieve_gebieden",
    "Dijkringen": "dijkringen",
    "Waterketen DAMO": "waterketen_damo",
    "TOP10NL": "top10nl",
    "OSM": "osm",
    "LIWO": "liwo",
    "Brandlagen": "brandlagen",
}
LABELS = {
    "DATA_DIR": "Basismap",
    "SOURCE_DATA_DIR": "Brongegevens",
    "PROCESSED_DATA_DIR": "Resultaten",
    "AHN_DATA_DIR": "AHN-hoofdmap",
    **{f"AHN{v}_DATA_DIR": f"    AHN{v} · tegels" for v in (6, 5, 4)},
    **{name.upper() + "_DATA_DIR": label for label, name in SOURCES.items()},
    "BAG_FILE": "    BAG · bestand",
    "BGT_FILE": "    BGT · bestand",
    "BRP_FILE": "    BRP · bestand",
    "TOP10NL_FILE": "    TOP10NL · bestand",
}


def profile_paths(path: Path, values: dict) -> dict[str, Path]:
    """Toon de effectieve paden ten opzichte van het datastorebestand."""

    def get(key: str, default: Path) -> Path:
        return (
            Path(os.path.abspath(path.parent / values[key]))
            if values.get(key)
            else default
        )

    base = get("DATA_DIR", path.parent / "data")
    sources = get("SOURCE_DATA_DIR", base / "source_data")
    ahn = get("AHN_DATA_DIR", sources / "ahn")
    result = {
        "DATA_DIR": base,
        "SOURCE_DATA_DIR": sources,
        "PROCESSED_DATA_DIR": get("PROCESSED_DATA_DIR", base / "processed_data"),
        "AHN_DATA_DIR": ahn,
    }
    for version in (6, 5, 4):
        key = f"AHN{version}_DATA_DIR"
        folder = ahn_tile_directory(sources, version, ahn if values.get("AHN_DATA_DIR") else None)
        result[key] = get(key, folder)
    for name in SOURCES.values():
        key = name.upper() + "_DATA_DIR"
        result[key] = get(key, sources / name)
    for name, filename in (
        ("BAG", "bag-light.gpkg"),
        ("BGT", "bgt.gpkg"),
        ("BRP", "brpgewaspercelen_definitief_2025.gpkg"),
    ):
        key = name + "_FILE"
        result[key] = get(key, result[name + "_DATA_DIR"] / filename)
    result["TOP10NL_FILE"] = get(
        "TOP10NL_FILE", result["TOP10NL_DATA_DIR"] / "top10nl_Compleet.gpkg"
    )
    return result


def write_profile(target: Path, template: str, values: dict, old: dict) -> None:
    """Bewaar gewijzigde paden en behoud bestaande opmerkingen."""
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        temporary.write_text(template, encoding="utf-8")
        for key in LABELS:
            if old.get(key) == values.get(key):
                continue
            if values.get(key):
                set_key(temporary, key, values[key], quote_mode="auto")
            elif key in old:
                unset_key(temporary, key)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def choose_profile(project: Path) -> Path | None:
    """Toon bronlocaties en open de Runmaker met de gekozen datastore."""
    import hashlib

    root = create_run_window()
    root.title("Waterlagen · Datastore kiezen")
    root.geometry(f"{min(960, root.winfo_screenwidth()-50)}x{min(740, root.winfo_screenheight()-90)}")
    root.minsize(620, 450)
    identity = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:12]
    prefs = (
        Path(os.getenv("LOCALAPPDATA") or Path.home())
        / "Waterlagen"
        / ("datastore-" + identity + ".txt")
    )
    current = project / ".datastore"
    if prefs.is_file():
        try:
            current = Path(prefs.read_text("utf-8").strip())
        except OSError:
            pass
    state = {}
    result = None
    path_text = tk.StringVar()
    info = tk.StringVar()
    expanded_sources: set[str] = set()
    messages = Queue()
    revision = 0
    timer = None

    style = ttk.Style(root)
    style.theme_use("clam")
    ink, heading, action = "#3a4f66", "#192a3d", "#26668b"
    paper, soft, line = "#ffffff", "#f4f7f9", "#dbe4ea"
    style.configure(".", font=("Segoe UI", 10), background=paper, foreground=ink)
    style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"), foreground=heading)
    style.configure("Group.TLabel", font=("Segoe UI", 11, "bold"), foreground=heading)
    style.configure("TButton", padding=(10, 4), borderwidth=1, bordercolor=line)
    style.map("TButton", background=[("active", soft)])
    style.configure("Folder.TButton", padding=(6, 3), background=soft)
    style.configure("Primary.TButton", background=action, foreground=paper, padding=(15, 7))
    style.map("Primary.TButton", background=[("active", "#1b5374")], foreground=[("active", paper)])
    style.configure("Path.TEntry", bordercolor=line, padding=(5, 3))
    style.map("Path.TEntry", fieldbackground=[("readonly", soft)])
    style.configure("Disclosure.TButton", anchor="w", borderwidth=0, foreground=action)
    style.configure("TSeparator", background=line)
    from PIL import Image, ImageDraw, ImageTk

    icon = Image.new("RGBA", (80, 80))
    draw = ImageDraw.Draw(icon)
    draw.line([(7,62),(7,20),(31,20),(38,28),(67,28),(67,36)], fill=action, width=6)
    draw.line([(7,62),(18,36),(73,36),(62,62),(7,62)], fill=action, width=6)
    size = round(18 * root.winfo_fpixels("1i") / 96)
    folder = ImageTk.PhotoImage(icon.resize((size, size), Image.Resampling.LANCZOS), master=root)
    card = ttk.Frame(root, padding=(18, 13))
    card.pack(expand=True, fill="both")
    card.columnconfigure(0, weight=1)
    card.rowconfigure(3, weight=1)
    ttk.Label(card, text="Datastore kiezen", style="Title.TLabel").grid(row=0, sticky="w")
    profile = ttk.Frame(card)
    profile.grid(row=1, sticky="ew", pady=(8, 12))
    profile.columnconfigure(0, weight=1)

    def path_field(parent, variable):
        return ttk.Entry(parent, textvariable=variable, state="readonly", style="Path.TEntry")

    path_field(profile, path_text).grid(row=0, column=0, sticky="ew")
    ttk.Separator(card).grid(row=2, sticky="ew")
    viewport = ttk.Frame(card)
    viewport.grid(row=3, sticky="nsew")
    viewport.columnconfigure(0, weight=1)
    viewport.rowconfigure(0, weight=1)
    canvas = tk.Canvas(viewport, bg=paper, highlightthickness=0, yscrollincrement=18)
    canvas.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(viewport, command=canvas.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scroll.set)
    rows = ttk.Frame(canvas, padding=(0, 0, 8, 4))
    inner = canvas.create_window((0, 0), anchor="nw", window=rows)
    rows.columnconfigure(1, weight=1)
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner, width=e.width))
    rows.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    def wheel(event):
        if rows.winfo_height() > canvas.winfo_height():
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    root.bind("<MouseWheel>", wheel)
    ttk.Separator(card).grid(row=4, sticky="ew", pady=(4, 9))
    buttons = ttk.Frame(card)
    buttons.grid(row=5, sticky="ew")
    buttons.columnconfigure(0, weight=1)
    ttk.Label(buttons, textvariable=info, wraplength=360).grid(row=0, column=0, sticky="w")
    status_widgets = {}

    def inspect_files(paths, number):
        for key, path in paths.items():
            try:
                status = "" if path.is_file() else "Kies een bestaand bestand"
            except OSError:
                status = "Controleer de bestandstoegang"
            messages.put((number, key, status))

    def update_status():
        nonlocal timer
        try:
            while True:
                number, key, status = messages.get_nowait()
                if revision == number and key in status_widgets:
                    status_widgets[key].configure(text=status)
        except Empty:
            pass
        timer = root.after(150, update_status)

    def render():
        nonlocal revision
        revision += 1
        for child in rows.winfo_children():
            child.destroy()
        status_widgets.clear()
        paths = profile_paths(state["path"], state["values"])
        values = state["values"]
        own_files = {}
        row = 0

        def section(title):
            nonlocal row
            ttk.Label(rows, text=title, style="Group.TLabel").grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(9, 3)
            )
            row += 1

        def add(key, label=None, *, details=(), indent=0):
            nonlocal row
            label = label or LABELS[key].strip()
            if details:
                arrow = "▾" if key in expanded_sources else "▸"
                name = ttk.Button(
                    rows, text=f"{arrow}  {label}", style="Disclosure.TButton",
                    command=lambda: toggle_source(key),
                )
            else:
                name = ttk.Label(rows, text=label)
            name.grid(row=row, column=0, sticky="w", padx=(indent, 12))
            value = tk.StringVar(root, str(paths[key]))
            field = path_field(rows, value)
            field.path_value = value
            field.grid(row=row, column=1, sticky="ew", pady=2)
            choose = ttk.Button(rows, image=folder, text=f"{label} kiezen",
                                style="Folder.TButton", command=lambda: change(key))
            choose.grid(row=row, column=2, padx=(4, 0))
            checks = (key,) if key in expanded_sources else (key, *details)
            for file_key in checks:
                if not file_key.endswith("_FILE") or not values.get(file_key):
                    continue
                own_files[file_key] = paths[file_key]
                warning = ttk.Label(rows, foreground="#914800")
                warning.grid(row=row, column=3, sticky="w", padx=(5, 0))
                status_widgets[file_key] = warning
            if values.get(key) and (key != "DATA_DIR" or values[key] != "./data"):
                ttk.Button(rows, text="Volg standaardpad", command=lambda: reset(key)).grid(
                    row=row, column=4, sticky="w"
                )
            row += 1

        section("Opslag")
        for key in ("DATA_DIR", "SOURCE_DATA_DIR", "PROCESSED_DATA_DIR"):
            add(key)
        section("Basisbronnen")
        for label, name in sorted({"AHN": "ahn", **SOURCES}.items()):
            directory = name.upper() + "_DATA_DIR"
            file_key = name.upper() + "_FILE"
            if name == "ahn":
                details = ("AHN6_DATA_DIR", "AHN5_DATA_DIR", "AHN4_DATA_DIR")
            elif file_key in paths:
                details = (file_key,)
            else:
                details = ()
            add(directory, label, details=details)
            if directory in expanded_sources:
                for detail in details:
                    add(detail, indent=25)
        path_text.set(str(state["path"]))
        dirty = values != state["original"]
        info.set("Gewijzigde paden" if dirty else "Deze mappen mogen leeg zijn. Ontbrekende openbare brongegevens worden zo nodig gedownload.")
        primary.configure(text="Opslaan en openen" if dirty else "Runmaker openen")
        if own_files:
            threading.Thread(target=inspect_files, args=(own_files, revision), daemon=True).start()

    def toggle_source(key):
        if key in expanded_sources:
            expanded_sources.remove(key)
        else:
            expanded_sources.add(key)
        render()

    def reset(key):
        state["values"].pop(key, None)
        render()

    def load(path):
        try:
            text = path.read_text("utf-8-sig") if path.is_file() else ""
            if not text and not path.is_file() and path != project / ".datastore":
                raise FileNotFoundError(f"Datastorebestand ontbreekt: {path}")
            values = (
                dict(dotenv_values(path, encoding="utf-8-sig", interpolate=False))
                if text
                else {"DATA_DIR": "./data"}
            )
            if path != state.get("path"):
                expanded_sources.clear()
            state.update(
                path=path,
                text=text,
                original=values.copy() if text else {},
                values=values,
            )
            render()
            return True
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Datastore openen", str(error), parent=root)
            return False

    def browse():
        if state["values"] != state["original"] and not messagebox.askyesno(
            "Andere datastore openen", "Wijzigingen verwerpen?", parent=root
        ):
            return
        path = filedialog.askopenfilename(
            parent=root,
            title="Datastore openen",
            filetypes=[
                ("Waterlagen-datastore", "*.datastore"),
                ("Alle bestanden", "*"),
            ],
        )
        if path:
            load(Path(path))

    def change(key):
        effective = profile_paths(state["path"], state["values"])[key]
        file = key.endswith("_FILE")
        options = dict(parent=root, title=LABELS[key].strip(),
                       initialdir=str(effective.parent if file else effective))
        if file:
            selected = filedialog.askopenfilename(**options, filetypes=[("GeoPackage", "*.gpkg")])
        else:
            selected = filedialog.askdirectory(**options)
        if selected:
            state["values"][key] = Path(selected).as_posix()
            render()

    def save(copy=False):
        target = state["path"]
        if copy:
            selected = filedialog.asksaveasfilename(
                parent=root,
                title="Eigen datastore opslaan",
                initialdir=target.parent,
                initialfile="Waterlagen.datastore",
                defaultextension=".datastore",
            )
            if not selected:
                return False
            target = Path(selected)
        try:
            values = state["values"].copy()
            if target.parent != state["path"].parent:
                for key in LABELS.keys() & values.keys():
                    if values[key] and not Path(values[key]).is_absolute():
                        values[key] = str(
                            (state["path"].parent / values[key]).resolve()
                        )
                values.setdefault(
                    "DATA_DIR", str(profile_paths(state["path"], values)["DATA_DIR"])
                )
            if (
                target == state["path"]
                and target.is_file()
                and target.read_text("utf-8-sig") != state["text"]
            ):
                raise OSError(
                    "De datastore is intussen gewijzigd. Open hem opnieuw of kies Opslaan als…"
                )
            write_profile(target, state["text"], values, state["original"])
            return load(target)
        except OSError as error:
            messagebox.showerror("Opslaan mislukt", str(error), parent=root)
            return False

    def accept():
        nonlocal result
        if state["values"] != state["original"] or not state["path"].is_file():
            if state["path"].is_file() and not messagebox.askokcancel(
                "Datastore opslaan", f"Gewijzigde paden opslaan in {state['path']}?", parent=root
            ):
                return
            if not save():
                return
        result = state["path"]
        try:
            prefs.parent.mkdir(parents=True, exist_ok=True)
            prefs.write_text(str(result), encoding="utf-8")
        except OSError:
            pass
        close()

    ttk.Button(profile, text="Datastore openen…", image=folder, compound="left",
               command=browse).grid(row=0, column=1, padx=(8, 0))
    ttk.Button(buttons, text="Opslaan als…", command=lambda: save(True)).grid(row=0, column=1, padx=8)
    primary = ttk.Button(buttons, text="Runmaker openen", style="Primary.TButton", command=accept)
    primary.grid(row=0, column=2)

    def close():
        if timer is not None:
            root.after_cancel(timer)
        root.update_idletasks()
        root.destroy()

    def activate_on_open(event):
        if event.widget is not root:
            return
        root.unbind("<Map>", binding)
        root.lift()
        root.focus_force()
        root.attributes("-topmost", False)

    if os.name == "nt":
        root.attributes("-topmost", True)
        binding = root.bind("<Map>", activate_on_open, add="+")

    root.protocol("WM_DELETE_WINDOW", close)
    if not load(current):
        load(project / ".datastore")
    timer = root.after(150, update_status)
    root.mainloop()
    return result
