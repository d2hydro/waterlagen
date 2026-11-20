"""Uitleg en handleiding openen zonder de productie-instellingen te veranderen."""

import importlib
import re

import pytest
from test_runscript_maken import REPOSITORY, generator, generic_window


HELP = dict(generator.LAYER_HELP)
extra_options = importlib.import_module("runscript_tool_tests.waterlagen_options")
HELP.update(
    {
        f"{layer}-{option.flag}": option.help
        for layer, entries in extra_options.EXTRA_OPTIONS.items()
        for option in entries
    }
)


@pytest.mark.parametrize("key", HELP)
def test_manual_page_and_section_still_exist(key):
    help_text = HELP[key]
    path = REPOSITORY / "docs" / help_text.category / f"{help_text.page}.md"
    assert path.is_file(), (
        f"Werk de handleidinglink voor {key} bij en behoud het oude adres."
    )
    if help_text.section:
        markdown = path.read_text(encoding="utf-8")
        headings = re.findall(r"^#+ (.+)$", markdown, re.MULTILINE)
        anchors = {
            re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
            for heading in headings
        }
        anchors.update(re.findall(r'<span id="([^"]+)"></span>', markdown))
        assert help_text.section in anchors, (
            f"Het anker voor {key} ontbreekt: {help_text.url}"
        )


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("Geen grafische omgeving beschikbaar")
    window.withdraw()
    yield window
    window.destroy()


def test_explanation_stays_clickable_and_keyboard_can_open_manual(root, monkeypatch):
    import tkinter as tk
    from tkinter import ttk

    opened = []

    def open_page(url):
        opened.append(url)
        return True

    monkeypatch.setattr(generic_window.webbrowser, "open_new_tab", open_page)
    frame = ttk.Frame(root)
    frame.pack()
    generic_window.add_help(frame, summary="Korte uitleg.", url="https://example.org/")
    info = frame.winfo_children()[0]
    assert len(frame.winfo_children()) == 1
    root.attributes("-alpha", 0)
    root.deiconify()
    root.update()

    def hints():
        return [
            child for child in frame.winfo_children() if isinstance(child, tk.Toplevel)
        ]

    def finish_hover_delay():
        root.after(350, root.quit)
        root.mainloop()

    info.event_generate("<Enter>")
    root.update()
    assert len(hints()) == 1
    link = hints()[0].winfo_children()[0]
    assert link.cget("text") == "Korte uitleg. ↗"
    info.event_generate("<Leave>")
    link.event_generate("<Enter>")
    finish_hover_delay()
    assert len(hints()) == 1
    assert opened == []
    link.event_generate("<Leave>")
    finish_hover_delay()
    assert hints() == []
    info.focus_force()
    root.update()
    assert len(hints()) == 1
    info.event_generate("<Escape>")
    root.update()
    assert hints() == []
    info.event_generate("<Return>")
    root.update()
    assert hints() == []
    assert opened == ["https://example.org/"]


@pytest.mark.parametrize("raise_error", [False, True])
def test_browser_failure_shows_a_copyable_link(root, monkeypatch, raise_error):
    from tkinter import messagebox, ttk

    def unavailable(url):
        if raise_error:
            raise OSError("Geen browser")
        return False

    errors = []
    monkeypatch.setattr(generic_window.webbrowser, "open_new_tab", unavailable)
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    frame = ttk.Frame(root)
    generic_window.add_help(frame, summary="Uitleg.", url="https://example.org/uitleg/")
    frame.winfo_children()[0].invoke()
    assert errors == [
        (
            "Handleiding openen lukt niet",
            "Open deze link in je browser:\nhttps://example.org/uitleg/",
        )
    ]


def test_extra_options_link_to_production_instructions():
    for options in extra_options.EXTRA_OPTIONS.values():
        for option in options:
            assert option.help.category == "produceren", option.flag
