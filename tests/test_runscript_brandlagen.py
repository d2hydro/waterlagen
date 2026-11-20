"""Een bruikbare TOML maken en uitsluitend aan afwateringseenheden doorgeven."""

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from test_runscript_maken import generator
from waterlagen.afwateringseenheden.config import read_brandlagen_config
from waterlagen.afwateringseenheden.config import Brandlaag
from waterlagen.datastore import DataStore

editor = importlib.import_module("runscript_tool_tests.brandlagen")


def test_own_geopackage_layers_can_be_saved_alone_or_with_public_sources(
    tmp_path, store
):
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    path = tmp_path / "eigen correcties.gpkg"
    gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs=28992).to_file(
        path, layer="correcties"
    )
    gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=28992).to_file(path, layer="punten")
    assert editor.custom_layer_names(path) == ["correcties"]
    own = Brandlaag(path, "correcties", brandwaarde=1.5, prioriteit=7)
    target = tmp_path / "eigen.toml"
    editor.save_config(target, [], store, custom_layers=[own])
    config = read_brandlagen_config(target)
    assert config.lagen == (own,)
    assert "openbare_bron" not in target.read_text(encoding="utf-8")
    editor.save_config(
        target,
        editor.template_choices()[:1],
        store,
        custom_layers=[own],
        overwrite=True,
    )
    config = read_brandlagen_config(target)
    assert len(config.lagen) == 2
    assert config.lagen[-1] == own
    original = target.read_bytes()
    with pytest.raises(ValueError, match="lijn- of vlaklaag"):
        editor.save_config(
            target,
            [],
            store,
            custom_layers=[Brandlaag(path, "punten", 1, 2)],
            overwrite=True,
        )
    assert target.read_bytes() == original


@pytest.fixture
def store(tmp_path):
    return DataStore(
        data_dir=tmp_path / "data",
        source_data_dir=tmp_path / "data/source_data",
        processed_data_dir=tmp_path / "data/processed_data",
    )


def test_saved_toml_works_with_production_reader_and_separate_data_location(
    tmp_path, store
):
    before = set(store.source_data_dir.rglob("*"))
    choices = editor.template_choices()
    assert len(choices) == 9
    choices = [
        replace(choice, value=-3.5, priority=4)
        for choice in choices
        if choice.layer in {"bgt_waterdelen", "osm_duikers"}
    ]
    path = tmp_path / "brandlagen.toml"
    editor.save_config(path, choices, store)
    config = read_brandlagen_config(path)
    assert len(config.lagen) == 2
    assert config.geisoleerde_branddiepte_m == 10
    text = path.read_text(encoding="utf-8")
    assert "geisoleerde_branddiepte_m" not in text
    assert "[defaults]" not in text
    assert "\nbron = " in text
    assert "\npath = " not in text
    assert "\nlayer = " not in text
    assert "\nrol = " not in text
    for layer in config.lagen:
        assert layer.brandwaarde == -3.5
        assert layer.prioriteit == 4
        assert layer.path is None
    assert config.lagen[1].bron == "osm_duikers"
    assert config.lagen[1].openbare_bron == "osm"
    assert set(store.source_data_dir.rglob("*")) == before


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_invalid_values_preserve_existing_file(tmp_path, store, value):
    path = tmp_path / "brandlagen.toml"
    path.write_text("bestaande inhoud", encoding="utf-8")
    choice = replace(editor.template_choices()[0], value=value)
    with pytest.raises(ValueError):
        editor.save_config(path, [choice], store, overwrite=True)
    assert path.read_text(encoding="utf-8") == "bestaande inhoud"


def test_save_requires_a_choice_and_explicit_overwrite(tmp_path, store):
    path = tmp_path / "brandlagen.toml"
    with pytest.raises(ValueError, match="minstens"):
        editor.save_config(path, [], store)
    editor.save_config(path, editor.template_choices()[:1], store)
    with pytest.raises(FileExistsError):
        editor.save_config(path, editor.template_choices(), store)


def test_only_afwateringseenheden_gets_the_selected_toml(tmp_path, store):
    path = tmp_path / "Aa's brandlagen.toml"
    editor.save_config(path, editor.template_choices()[:1], store)
    options = generator.RunSettings(
        tuple(generator.LAYERS),
        ("--waterbeheercode", "12"),
        "proef",
        brandlagen_config=path,
    )
    commands = generator._commands(options)
    assert all("--brandlagen-config" not in command for command in commands[:-1])
    assert "--brandlagen-config" in commands[-1]
    assert "Aa''s brandlagen.toml" in commands[-1]
    assert "--workers 8" in commands[-1]


@pytest.fixture(scope="module")
def tk_root():
    tk = pytest.importorskip("tkinter")
    try:
        window = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Geen grafische omgeving beschikbaar: {error}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def root(tk_root):
    yield tk_root
    for child in tk_root.winfo_children():
        child.destroy()


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def buttons(parent):
    from tkinter import ttk

    return {
        widget.cget("text"): widget
        for widget in widgets(parent)
        if isinstance(widget, ttk.Button)
    }


def public_inputs(parent, label):
    from tkinter import ttk

    checkbox = next(
        widget
        for widget in widgets(parent)
        if isinstance(widget, ttk.Checkbutton) and widget.cget("text") == label
    )
    row = checkbox.grid_info()["row"]
    entries = sorted(
        (
            child
            for child in checkbox.master.winfo_children()
            if isinstance(child, ttk.Entry) and child.grid_info().get("row") == row
        ),
        key=lambda child: child.grid_info()["column"],
    )
    return checkbox, *entries


@pytest.mark.parametrize("loaded", [False, True])
def test_editor_requires_a_layer_before_saving(
    root, tmp_path, store, monkeypatch, loaded
):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    original = tmp_path / "origineel.toml"
    editor.save_config(original, editor.template_choices()[:1], store)
    original_bytes = original.read_bytes()
    target = tmp_path / "bestaande-uitvoer.toml"
    target.write_bytes(original_bytes)
    selected = tk.StringVar(root, value=str(original) if loaded else "")
    previous_selection = selected.get()
    errors = []
    save_dialogs = []

    def choose_target(**kwargs):
        save_dialogs.append(kwargs)
        return str(target)

    monkeypatch.setattr(editor, "DataStore", lambda: store)
    monkeypatch.setattr(filedialog, "asksaveasfilename", choose_target)
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    editor.open_options(root, selected)
    if loaded:
        public_inputs(root, "BGT – water")[0].invoke()
    buttons(root)["Opslaan als…"].invoke()
    assert errors and "brandlaag" in errors[0][1]
    assert not save_dialogs
    assert selected.get() == previous_selection
    assert target.read_bytes() == original_bytes
    assert original.read_bytes() == original_bytes

    errors.clear()
    public_inputs(root, "BGT – duikers")[0].invoke()
    buttons(root)["Opslaan als…"].invoke()
    assert not errors
    assert len(save_dialogs) == 1
    assert selected.get() == str(target)
    config = read_brandlagen_config(target)
    assert len(config.lagen) == 1
    assert config.lagen[0].layer == "bgt_duiker"
    assert config.lagen[0].openbare_bron == "bgt"
    assert config.lagen[0].bron == "bgt_duikers"
    assert config.lagen[0].brandwaarde == -10
    assert config.lagen[0].prioriteit == 2
    assert "bgt_duikers" in target.read_text(encoding="utf-8")
    assert original.read_bytes() == original_bytes


def test_open_edit_save_copy_and_reopen_preserve_settings(root, tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    original = tmp_path / "origineel.toml"
    original.write_text(
        """geisoleerde_branddiepte_m = 6.5
[defaults]
brandwaarde = -4.0
prioriteit = 8
[[lagen]]
bron = "osm_duikers"
[[lagen]]
path = "lokale-bgt.gpkg"
layer = "bgt_waterdeel"
brandwaarde = 1.5
[[lagen]]
bron = "bgt_waterdelen"
brandwaarde = -2.5
prioriteit = 3
[[lagen]]
bron = "bgt_wegdelen"
brandwaarde = 2.0
""",
        encoding="utf-8",
    )
    before = original.read_bytes()
    config = read_brandlagen_config(original)
    target = tmp_path / "andere map" / "kopie.toml"
    target.parent.mkdir()
    selected = tk.StringVar(root)
    errors = []
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kwargs: str(original))
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    editor.open_options(root, selected)
    buttons(root)["Bestand openen"].invoke()
    assert Path(selected.get()) == original
    check, value, priority = public_inputs(root, "BGT – water")
    assert check.instate(["selected"])
    assert value.get() == "-2.5"
    assert priority.get() == "3"
    value.delete(0, "end")
    value.insert(0, "-3.5")
    buttons(root)["Opslaan als…"].invoke()
    assert errors == []
    assert Path(selected.get()) == target
    assert original.read_bytes() == before
    expected = replace(
        config,
        brandwaarde=None,
        prioriteit=None,
        lagen=(
            replace(config.lagen[0], brandwaarde=-4.0, prioriteit=8),
            replace(config.lagen[1], prioriteit=8),
            replace(config.lagen[2], brandwaarde=-3.5),
            replace(config.lagen[3], prioriteit=8),
        ),
    )
    assert read_brandlagen_config(target) == expected
    editor.open_options(root, selected)
    assert public_inputs(root, "BGT – water")[1].get() == "-3.5"
    table = next(widget for widget in widgets(root) if isinstance(widget, ttk.Treeview))
    assert len(table.get_children()) == 2
    # Annuleren verandert de gekozen run-invoer niet.
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **kwargs: "")
    buttons(root)["Opslaan als…"].invoke()
    assert Path(selected.get()) == target
    assert original.read_bytes() == before
    assert read_brandlagen_config(target) == expected


def test_invalid_open_and_discard_cancel_keep_the_current_list(
    root, tmp_path, store, monkeypatch
):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    source = tmp_path / "geldig.toml"
    editor.save_config(source, editor.template_choices()[:1], store)
    invalid = tmp_path / "ongeldig.toml"
    invalid.write_text("dit is geen toml", encoding="utf-8")
    selected = tk.StringVar(root, value=str(source))
    errors = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kwargs: str(invalid))
    editor.open_options(root, selected)
    buttons(root)["Bestand openen"].invoke()
    assert len(errors) == 1
    assert selected.get() == str(source)
    check, value, _ = public_inputs(root, "BGT – water")
    assert check.instate(["selected"])
    value.delete(0, "end")
    value.insert(0, "-8")
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kwargs: str(source))
    buttons(root)["Bestand openen"].invoke()
    assert value.get() == "-8"
    assert selected.get() == str(source)


def test_imported_public_layer_can_be_edited_before_download(
    root, tmp_path, monkeypatch
):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    original = tmp_path / "wegdelen.toml"
    original.write_text(
        """[defaults]
brandwaarde = 2.0
[[lagen]]
bron = "bgt_wegdelen"
""",
        encoding="utf-8",
    )
    config = read_brandlagen_config(original)
    target = tmp_path / "kopie.toml"
    selected = tk.StringVar(root, value=str(original))
    errors = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    editor.open_options(root, selected)
    table = next(widget for widget in widgets(root) if isinstance(widget, ttk.Treeview))
    table.selection_set(table.get_children()[0])
    buttons(root)["Bewerken"].invoke()
    dialog = next(
        widget
        for widget in widgets(root)
        if isinstance(widget, tk.Toplevel) and widget.title() == "Brandlaag aanpassen"
    )
    entries = [
        widget
        for widget in widgets(dialog)
        if isinstance(widget, ttk.Entry)
        and not isinstance(widget, ttk.Combobox)
        and not widget.instate(["readonly"])
    ]
    assert "Bestand kiezen" not in buttons(dialog)
    assert not any(isinstance(w, ttk.Combobox) for w in widgets(dialog))
    assert entries[0].get() == ""
    assert entries[1].get() == ""
    entries[0].insert(0, "3.0")
    buttons(dialog)["Laag gebruiken"].invoke()
    buttons(root)["Opslaan als…"].invoke()
    assert errors == []
    assert read_brandlagen_config(target) == replace(
        config, brandwaarde=None, lagen=(replace(config.lagen[0], brandwaarde=3.0),)
    )
    assert config.lagen[0].path is None


def test_dialog_adds_an_own_layer_and_saves_its_toml(
    root, tmp_path, store, monkeypatch
):
    import geopandas as gpd
    from shapely.geometry import LineString

    tk = pytest.importorskip("tkinter")
    from tkinter import filedialog, messagebox, ttk

    source = tmp_path / "eigen.gpkg"
    gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs=28992).to_file(
        source, layer="correctie"
    )
    target = tmp_path / "brandlagen.toml"
    monkeypatch.setattr(editor, "DataStore", lambda: store)
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kwargs: str(source))
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    errors = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    selected = tk.StringVar(root)

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def buttons(parent):
        return {
            widget.cget("text"): widget
            for widget in widgets(parent)
            if isinstance(widget, ttk.Button)
        }

    try:
        editor.open_options(root, selected, create_new=True)
        buttons(root)["Eigen laag toevoegen"].invoke()
        custom = next(
            widget
            for widget in widgets(root)
            if isinstance(widget, tk.Toplevel) and widget.title() == "Eigen brandlaag"
        )
        buttons(custom)["Bestand kiezen"].invoke()
        numeric_entries = [
            widget
            for widget in widgets(custom)
            if isinstance(widget, ttk.Entry)
            and not isinstance(widget, ttk.Combobox)
            and not widget.instate(["readonly"])
        ]
        assert len(numeric_entries) == 2
        numeric_entries[0].insert(0, "-2.5")
        numeric_entries[1].delete(0, "end")
        numeric_entries[1].insert(0, "3")
        assert not any(
            isinstance(widget, ttk.Label) and widget.cget("text") == "Bron duikers"
            for widget in widgets(custom)
        )
        assert not any(
            isinstance(widget, ttk.Label) and widget.cget("text") == "Rol"
            for widget in widgets(custom)
        )
        assert (
            len(
                [
                    widget
                    for widget in widgets(custom)
                    if isinstance(widget, ttk.Combobox)
                ]
            )
            == 1
        )
        buttons(custom)["Laag gebruiken"].invoke()
        buttons(root)["Opslaan als…"].invoke()
        assert not errors
        assert Path(selected.get()) == target
        config = read_brandlagen_config(target)
        assert config.lagen == (Brandlaag(source, "correctie", -2.5, 3),)
        # Bestaande TOML-bestanden bewaren hun herkomst bij bewerken.
        legacy = config.lagen[0]
        saved = []
        editor.open_custom_layer(root, saved.append, legacy)
        buttons(root)["Laag gebruiken"].invoke()
        assert saved == [legacy]
    finally:
        for child in root.winfo_children():
            child.destroy()
