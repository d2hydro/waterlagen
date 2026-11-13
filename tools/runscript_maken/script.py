"""Maak en bewaar zelfstandige PowerShell-scripts voor gekozen opdrachten."""

import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScriptPlan:
    """Een bestandsnaam en de opdrachten die de gebruiker heeft gekozen."""

    name: str
    commands: tuple[str, ...]


def quote(value: str) -> str:
    """Zet een waarde letterlijk tussen PowerShell-aanhalingstekens."""
    return "'" + value.replace("'", "''") + "'"


def format_command(arguments: Sequence[str | Path]) -> str:
    """Maak een leesbaar commando; paden en speciale tekens blijven letterlijk."""
    if not arguments:
        raise ValueError("Een commando moet minstens een programmanaam hebben.")
    words = []
    for argument in arguments:
        value = str(argument)
        if isinstance(argument, Path) or not re.fullmatch(r"[-A-Za-z0-9_./:]+", value):
            words.append(quote(value))
        else:
            words.append(value)
    command = " ".join(words)
    if words[0].startswith("'"):
        command = "& " + command
    return command


def build_script(commands: Sequence[str], project: Path) -> str:
    """Voer opdrachten na elkaar uit vanuit de projectmap; stop bij een fout."""
    if not commands:
        raise ValueError("Kies minstens één opdracht.")
    lines = [
        "# Pas de opties in de commando's hieronder aan voor een volgende run.",
        "$ErrorActionPreference = 'Stop'",
        f"Set-Location -LiteralPath {quote(str(project.resolve()))}",
        "",
        "# De opdrachten draaien na elkaar. Bij een fout stopt het script.",
    ]
    for command in commands:
        lines.extend(
            [
                command,
                "if ($LASTEXITCODE -ne 0) {",
                "    throw 'Opdracht is gestopt. Bekijk de melding hierboven.'",
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def save_script(
    script: str, path: Path, project: Path, *, start: bool = False
) -> subprocess.Popen | None:
    """Bewaar eerst het script; start alleen na succesvol opslaan."""
    if path.suffix.lower() != ".ps1":
        raise ValueError("Sla het runscript op met de extensie .ps1.")
    # De BOM laat Windows PowerShell ook accenten goed lezen.
    path.write_text(script, encoding="utf-8-sig")
    if not start:
        return None
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        raise OSError(f"Script opgeslagen in {path}. PowerShell is niet gevonden.")
    # Het venster blijft open, zodat ook een foutmelding leesbaar blijft.
    return subprocess.Popen(
        [powershell, "-NoProfile", "-NoExit", "-File", str(path.resolve())],
        cwd=project,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )
