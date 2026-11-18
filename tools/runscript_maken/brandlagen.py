"""Kies een brandlagenbestand of maak er een vanuit het bestaande voorbeeld."""

from __future__ import annotations

import json
import tempfile
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from collections.abc import Callable, Sequence

from waterlagen._crs import read_layer_crs_info
from waterlagen.afwateringseenheden.config import (
    Brandlaag,
    BrandlagenConfig,
    read_brandlagen_config,
)
from waterlagen.datastore import DataStore

from .window import add_help

if TYPE_CHECKING:
    import tkinter as tk


TEMPLATE = (
    Path(__file__).resolve().parents[2] / "docs/reference/voorbeelden/brandlagen.toml"
)
HELP_URL = "https://d2hydro.github.io/waterlagen/produceren/afwateringseenheden/#test-met-eigen-gebied-en-brandlagen"
LABELS = {
    "bgt_waterdelen": "BGT – water",
    "bgt_duikers": "BGT – duikers",
    "top10nl_waterdeel_vlak": "TOP10NL – watervlakken",
    "top10nl_waterdeel_lijn": "TOP10NL – waterlijnen",
    "osm_duikers": "OSM – duikers",
    "osm_canals": "OSM – kanalen",
    "osm_ditches": "OSM – sloten en greppels",
    "osm_drains": "OSM – afvoerwatergangen",
    "osm_streams": "OSM – beken",
}


@dataclass(frozen=True)
class BrandChoice:
    """Een gekozen laag met hoogteverandering en voorrang."""

    layer: str
    value: float
    priority: int


@dataclass
class _BrandInputs:
    choice: BrandChoice
    enabled: tk.BooleanVar
    value: tk.StringVar
    priority: tk.StringVar
    index: int | None = None


def template_choices() -> list[BrandChoice]:
    """Lees de standaardwaarden uit de voorbeeld-TOML in de handleiding."""
    values = tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))
    defaults = values.get("defaults", {})
    return [
        BrandChoice(
            entry["bron"],
            entry.get("brandwaarde", defaults.get("brandwaarde")),
            entry.get("prioriteit", defaults.get("prioriteit", 0)),
        )
        for entry in values["lagen"]
    ]


def save_config(
    path: Path,
    choices: list[BrandChoice],
    store: DataStore,
    *,
    overwrite: bool = False,
    custom_layers: Sequence[Brandlaag] = (),
) -> None:
    """Bewaar geldige keuzes zonder bronnen op te halen of productie te starten."""
    if not choices and not custom_layers:
        raise ValueError("Kies minstens één brandlaag.")
    if path.exists() and not overwrite:
        raise FileExistsError(f"Het bestand bestaat al: {path}")
    layers = _public_layers(choices, store)
    for layer in custom_layers:
        if layer.openbare_bron is not None:
            raise ValueError("Een eigen brandlaag moet een lokaal bestand blijven.")
        if layer.layer not in custom_layer_names(layer.path):
            raise ValueError(f"Geen bruikbare lijn- of vlaklaag: {layer.layer}")
        layers.append(layer)
    _write_config(path, BrandlagenConfig(tuple(layers)), overwrite=overwrite)


def _public_layers(choices: list[BrandChoice], store: DataStore) -> list[Brandlaag]:
    template = tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))
    entries = {entry["bron"]: entry for entry in template["lagen"]}
    layers = []
    for choice in choices:
        if choice.layer not in entries:
            raise ValueError(f"Onbekende brandlaag: {choice.layer}")
        layers.append(
            Brandlaag(
                bron=choice.layer, brandwaarde=choice.value, prioriteit=choice.priority
            )
        )
    return layers


def _write_config(
    path: Path, config: BrandlagenConfig, *, overwrite: bool = False
) -> None:
    """Bewaar ook geërfde waarden en bronpaden bij opslaan in een andere map."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"Het bestand bestaat al: {path}")
    lines = [
        "# Aanvullende lagen die de berekende afstroming sturen.",
        "# Openbare bronnen: alleen bron, brandwaarde en prioriteit.",
        "# Alleen voor een eigen GeoPackage: path en layer.",
        "# Relatieve paden zijn relatief aan dit TOML-bestand.",
        "# Negatief verlaagt en positief verhoogt.",
        "# HyDAMO/Rijkswateren gaan voor. Daarna geldt de hoogste prioriteit.",
    ]
    if config.geisoleerde_branddiepte_m != BrandlagenConfig().geisoleerde_branddiepte_m:
        lines.append(f"geisoleerde_branddiepte_m = {config.geisoleerde_branddiepte_m}")
    for layer in config.lagen:
        lines.append("")
        lines.append("[[lagen]]")
        if layer.bron is not None:
            entry = {"bron": layer.bron}
        else:
            entry = {"path": layer.path.as_posix(), "layer": layer.layer}
        for name in ("brandwaarde", "prioriteit"):
            value = getattr(layer, name)
            if value is None:
                value = getattr(config, name)
            if value is not None:
                entry[name] = value
        for key, value in entry.items():
            lines.append(
                f"{key} = {json.dumps(value, ensure_ascii=False, allow_nan=False)}"
            )
    text = "\n".join(lines) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".toml", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        read_brandlagen_config(temporary)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def custom_layer_names(path: Path) -> list[str]:
    """Lees alleen de metadata van lokale lijn- en vlaklagen met een CRS."""
    if not path.is_file():
        raise ValueError(f"GeoPackage niet gevonden: {path}")
    try:
        infos = read_layer_crs_info(path)
    except (ValueError, OSError, RuntimeError) as error:
        raise ValueError(f"Kan dit GeoPackage niet lezen: {path}") from error
    names = [
        info.layer
        for info in infos
        if info.crs
        and any(
            kind in (info.geometry_type or "") for kind in ("LineString", "Polygon")
        )
    ]
    if not names:
        raise ValueError(
            "Kies een GeoPackage met lijnen of vlakken en een bekend coördinatenstelsel."
        )
    return names


def open_custom_layer(
    parent: tk.Misc, save: Callable[[Brandlaag], None], layer: Brandlaag | None = None
) -> None:
    """Kies een eigen laag en de waarden die bij ontbrekende objectwaarden gelden."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Toplevel(parent)
    window.title("Brandlaag aanpassen" if layer else "Eigen brandlaag")
    window.transient(parent.winfo_toplevel())
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure((0, 1), weight=1)
    url = "https://d2hydro.github.io/waterlagen/bewerkte-lagen/afwateringseenheden/#optionele-brandlagen"

    def label(text: str, summary: str, row: int, column: int = 0) -> None:
        heading = ttk.Frame(frame)
        heading.grid(row=row, column=column, sticky="w", pady=(10, 5))
        ttk.Label(heading, text=text).pack(side="left")
        add_help(heading, summary=summary, url=url)

    path = tk.StringVar(value=str(layer.path) if layer else "")
    name = tk.StringVar(value=layer.layer if layer else "")
    value = tk.StringVar(
        value=str(layer.brandwaarde) if layer and layer.brandwaarde is not None else ""
    )
    priority = tk.StringVar(
        value=(str(layer.prioriteit) if layer.prioriteit is not None else "")
        if layer
        else "0"
    )
    public_source = layer is not None and layer.bron is not None

    if public_source:
        ttk.Label(frame, text=LABELS.get(layer.bron, layer.bron)).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
    else:
        label(
            "GeoPackage",
            "Dit lokale bestand wordt rechtstreeks gebruikt en niet gedownload.",
            0,
        )
        file_row = ttk.Frame(frame)
        file_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Entry(file_row, textvariable=path, width=58, state="readonly").pack(
            side="left", fill="x", expand=True
        )
        label(
            "Laag", "Kies een lijn- of vlaklaag met een bekend coördinatenstelsel.", 2
        )
        layer_input = ttk.Combobox(frame, textvariable=name, state="readonly")
        layer_input.grid(row=3, column=0, columnspan=2, sticky="ew")

        def choose_file() -> None:
            filename = filedialog.askopenfilename(
                parent=window,
                title="Eigen brandlaag kiezen",
                filetypes=[("GeoPackage", "*.gpkg")],
            )
            if not filename:
                return
            try:
                names = custom_layer_names(Path(filename))
            except ValueError as error:
                messagebox.showerror("Laag niet bruikbaar", str(error), parent=window)
                return
            path.set(str(Path(filename).resolve()))
            layer_input.configure(values=names)
            name.set(names[0] if len(names) == 1 else "")

        file_button = ttk.Button(file_row, text="Bestand kiezen", command=choose_file)
        file_button.pack(side="left", padx=(8, 0))
        if layer:
            layer_input.configure(values=[layer.layer])

    label(
        "Brandwaarde (m)",
        "Negatief verlaagt, positief verhoogt. Waarden bij objecten in de laag gaan voor.",
        4,
    )
    label(
        "Prioriteit",
        "HyDAMO/Rijkswateren gaan voor. Bij aanvullende lagen wint de hoogste prioriteit. Objectwaarden gaan voor deze standaard.",
        4,
        1,
    )
    ttk.Entry(frame, textvariable=value).grid(
        row=5, column=0, sticky="ew", padx=(0, 16)
    )
    ttk.Entry(frame, textvariable=priority).grid(row=5, column=1, sticky="ew")

    def confirm() -> None:
        try:
            # Bestaande bronverwijzingen blijven bruikbaar voordat de bron is opgehaald.
            same_source = (
                layer is not None
                and path.get() == str(layer.path)
                and name.get() == layer.layer
            )
            if (
                not public_source
                and not same_source
                and name.get() not in custom_layer_names(Path(path.get()))
            ):
                raise ValueError("Kies een laag uit het GeoPackage.")
            if not layer and not value.get().strip():
                raise ValueError(
                    "Vul een brandwaarde in; gebruik 0 voor geen hoogteverandering."
                )
            chosen = Brandlaag(
                path=None if public_source else Path(path.get()),
                layer=None if public_source else name.get(),
                brandwaarde=float(value.get()) if value.get().strip() else None,
                prioriteit=int(priority.get()) if priority.get().strip() else None,
                bron=layer.bron if public_source else None,
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Controleer de brandlaag", str(error), parent=window)
            return
        save(chosen)
        window.destroy()

    ttk.Button(
        frame, text="Laag gebruiken", command=confirm, style="Save.TButton"
    ).grid(row=6, column=0, columnspan=2, sticky="e", pady=(20, 0))


def open_options(
    parent: tk.Misc, selected: tk.StringVar, *, create_new: bool = False
) -> None:
    """Open de gekozen brandlagen en bewaar aanpassingen in een TOML."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Toplevel(parent)
    window.title("Brandlagen instellen")
    window.transient(parent.winfo_toplevel())
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill="both", expand=True)
    heading = ttk.Frame(frame)
    heading.pack(fill="x")
    ttk.Label(heading, text="Brandlagen instellen", style="Heading.TLabel").pack(
        side="left"
    )
    add_help(
        heading,
        summary="Kies brandlagen of open een bestand. Bewaar je keuzes met Opslaan als.",
        url=HELP_URL,
    )
    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=(12, 8))
    filename_text = tk.StringVar(window, value="Nog niet opgeslagen")
    ttk.Label(frame, textvariable=filename_text, wraplength=600).pack(anchor="w")
    loaded_path: Path | None = None
    config = BrandlagenConfig()
    layers: list[Brandlaag | None] = []
    extra_indices: list[int] = []
    builder = ttk.Frame(frame)
    builder.pack(fill="x", pady=12)
    builder.columnconfigure(0, weight=1)
    fields: list[_BrandInputs] = []
    titles = (
        ("Brandlaag", "De productie haalt ontbrekende openbare bronnen zelf op."),
        (
            "Brandwaarde (m)",
            "Negatief verlaagt; positief verhoogt. Leeg gebruikt de waarde uit de TOML of de bronlaag.",
        ),
        (
            "Prioriteit",
            "HyDAMO/Rijkswateren gaan voor. Bij aanvullende lagen wint het hoogste getal. Leeg gebruikt de waarde uit de TOML of de bronlaag.",
        ),
    )
    for column, (label, summary) in enumerate(titles):
        title = ttk.Frame(builder)
        title.grid(row=0, column=column, sticky="w", pady=8)
        ttk.Label(title, text=label).pack(side="left")
        add_help(
            title,
            summary=summary,
            url="https://d2hydro.github.io/waterlagen/bewerkte-lagen/afwateringseenheden/#optionele-brandlagen",
        )
    for row, choice in enumerate(template_choices(), start=1):
        enabled = tk.BooleanVar(window, value=False)
        value = tk.StringVar(window, value=str(choice.value))
        priority = tk.StringVar(window, value=str(choice.priority))
        ttk.Checkbutton(builder, text=LABELS[choice.layer], variable=enabled).grid(
            row=row, column=0, sticky="w"
        )
        ttk.Entry(builder, textvariable=value, width=12).grid(
            row=row, column=1, sticky="ew", padx=(0, 16), pady=3
        )
        ttk.Entry(builder, textvariable=priority, width=8).grid(
            row=row, column=2, sticky="ew", pady=3
        )
        fields.append(_BrandInputs(choice, enabled, value, priority))

    def read_config() -> BrandlagenConfig:
        chosen = list(layers)
        for field in fields:
            if not field.enabled.get():
                if field.index is not None:
                    chosen[field.index] = None
                continue
            value = float(field.value.get()) if field.value.get().strip() else None
            priority = (
                int(field.priority.get()) if field.priority.get().strip() else None
            )
            if field.index is None:
                source = _public_layers([field.choice], DataStore())[0]
                chosen.append(replace(source, brandwaarde=value, prioriteit=priority))
            else:
                source = layers[field.index]
                chosen[field.index] = replace(
                    source, brandwaarde=value, prioriteit=priority
                )
        return replace(
            config, lagen=tuple(layer for layer in chosen if layer is not None)
        )

    def discard_changes() -> bool:
        try:
            changed = read_config() != config
        except (ValueError, TypeError):
            changed = True
        return not changed or messagebox.askyesno(
            "Niet-opgeslagen wijzigingen",
            "Doorgaan zonder je wijzigingen op te slaan?",
            parent=window,
        )

    def show_custom_layers() -> None:
        children = table.get_children()
        if children:
            table.delete(*children)
        for index in extra_indices:
            layer = layers[index]
            table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    LABELS.get(layer.bron, layer.bron)
                    if layer.bron
                    else layer.path.name,
                    layer.layer,
                    layer.brandwaarde if layer.brandwaarde is not None else "standaard",
                    layer.prioriteit if layer.prioriteit is not None else "standaard",
                ),
            )

    def fill_form(loaded: BrandlagenConfig, path: Path | None) -> None:
        nonlocal config, loaded_path
        config = loaded
        loaded_path = path
        layers[:] = loaded.lagen
        extra_indices.clear()
        fields_by_name = {field.choice.layer: field for field in fields}
        for field in fields:
            field.index = None
            field.enabled.set(False)
            field.value.set(str(field.choice.value))
            field.priority.set(str(field.choice.priority))
        for index, layer in enumerate(layers):
            field = fields_by_name.get(layer.bron)
            # Een lokale laag met dezelfde naam blijft lokale invoer.
            if layer.openbare_bron and field is not None and field.index is None:
                field.index = index
                field.enabled.set(True)
                field.value.set(
                    str(layer.brandwaarde) if layer.brandwaarde is not None else ""
                )
                field.priority.set(
                    str(layer.prioriteit) if layer.prioriteit is not None else ""
                )
            else:
                extra_indices.append(index)
        filename_text.set(str(path) if path else "Nog niet opgeslagen")
        defaults_text.set(
            "Lege velden gebruiken de waarden uit de TOML of de bronlaag."
            if path
            else "Vink de gewenste brandlagen aan of voeg een eigen laag toe."
        )
        show_custom_layers()

    def load_file(path: Path) -> bool:
        try:
            loaded = read_brandlagen_config(path)
        except (ValueError, TypeError, OSError) as error:
            messagebox.showerror("Bestand niet bruikbaar", str(error), parent=window)
            return False
        if not discard_changes():
            return False
        fill_form(loaded, path.resolve())
        selected.set(str(path.resolve()))
        return True

    def choose_existing() -> None:
        filename = filedialog.askopenfilename(
            parent=window, title="Brandlagen openen", filetypes=[("TOML", "*.toml")]
        )
        if filename:
            load_file(Path(filename))

    def save_as() -> None:
        try:
            chosen = read_config()
            if not chosen.lagen:
                raise ValueError(
                    "Vink minstens één brandlaag aan of voeg een eigen laag toe."
                )
            filename = filedialog.asksaveasfilename(
                parent=window,
                title="Brandlagen opslaan als",
                initialdir=str(loaded_path.parent) if loaded_path else None,
                initialfile=f"{loaded_path.stem}-aangepast.toml"
                if loaded_path
                else "brandlagen.toml",
                defaultextension=".toml",
                filetypes=[("TOML", "*.toml")],
            )
            if not filename:
                return
            _write_config(Path(filename), chosen, overwrite=True)
        except (ValueError, TypeError, OSError) as error:
            messagebox.showerror("Opslaan niet gelukt", str(error), parent=window)
            return
        selected.set(str(Path(filename).resolve()))
        window.destroy()

    ttk.Button(actions, text="Bestand openen", command=choose_existing).pack(
        side="left"
    )
    custom_frame = ttk.Frame(builder)
    custom_frame.grid(
        row=len(fields) + 1, column=0, columnspan=3, sticky="ew", pady=(14, 0)
    )
    ttk.Label(
        custom_frame, text="Eigen en overige brandlagen", style="Heading.TLabel"
    ).pack(anchor="w", pady=(0, 6))
    table = ttk.Treeview(
        custom_frame,
        columns=("bestand", "laag", "waarde", "prioriteit"),
        show="headings",
        height=3,
    )
    for column, title, width in (
        ("bestand", "Bestand", 170),
        ("laag", "Laag", 160),
        ("waarde", "Brandwaarde", 100),
        ("prioriteit", "Prioriteit", 85),
    ):
        table.heading(column, text=title)
        table.column(column, width=width, minwidth=50)
    table.pack(fill="x")
    custom_actions = ttk.Frame(custom_frame)
    custom_actions.pack(fill="x", pady=(8, 0))

    def add_custom(layer: Brandlaag) -> None:
        extra_indices.append(len(layers))
        layers.append(layer)
        show_custom_layers()

    def edit_custom() -> None:
        selection = table.selection()
        if not selection:
            return
        index = int(selection[0])

        def replace_layer(layer: Brandlaag) -> None:
            layers[index] = layer
            show_custom_layers()

        open_custom_layer(window, replace_layer, layers[index])

    def remove_custom() -> None:
        selection = table.selection()
        if selection:
            index = int(selection[0])
            layers[index] = None
            extra_indices.remove(index)
            show_custom_layers()

    ttk.Button(
        custom_actions,
        text="Eigen laag toevoegen",
        command=lambda: open_custom_layer(window, add_custom),
    ).pack(side="left")
    ttk.Button(custom_actions, text="Bewerken", command=edit_custom).pack(
        side="left", padx=8
    )
    ttk.Button(custom_actions, text="Verwijderen", command=remove_custom).pack(
        side="left"
    )
    defaults_text = tk.StringVar(
        window, value="Vink de gewenste brandlagen aan of voeg een eigen laag toe."
    )
    ttk.Label(builder, textvariable=defaults_text, wraplength=600).grid(
        row=len(fields) + 2, column=0, columnspan=3, sticky="w", pady=10
    )
    ttk.Button(
        builder, text="Opslaan als…", command=save_as, style="Save.TButton"
    ).grid(row=len(fields) + 3, column=0, columnspan=3, sticky="e")

    def close() -> None:
        if discard_changes():
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    if selected.get() and not create_new:
        load_file(Path(selected.get()))
