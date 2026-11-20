"""Maak en bewaar zelfstandige PowerShell-scripts voor gekozen opdrachten."""

import os
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


def build_script(commands: Sequence[str], project: Path | None = None) -> str:
    """Schrijf de gekozen commando's, één per regel."""
    if not commands:
        raise ValueError("Kies minstens één opdracht.")
    return "\n".join(commands) + "\n"


def _powershell_command(script: str) -> str:
    """Start de commando's direct; stop bij een fout en houd het venster open."""
    lines = [
        "& {",
        "$ErrorActionPreference = 'Stop'",
        "$global:LASTEXITCODE = 0",
    ]
    for command in script.splitlines():
        lines.extend(
            [
                command,
                "if ($LASTEXITCODE -ne 0) {",
                "    Write-Host 'Opdracht gestopt. Bekijk de melding hierboven.' -ForegroundColor Red",
                "    return",
                "}",
            ]
        )
    lines.append("}")
    return "\n".join(lines)


def _batch_argument(value: str) -> str:
    """Zet bijzondere tekens letterlijk in een Windows-batchcommando."""
    if re.fullmatch(r"[-A-Za-z0-9_./:\\]+", value):
        return value
    # Verdubbel backslashes voor aanhalingstekens en aan het einde.
    value = re.sub(r'(\\*)"', r'\1\1""', value)
    value = re.sub(r"(\\+)$", r"\1\1", value)
    return '"' + value.replace("%", "%%") + '"'


def build_batch_script(
    commands: Sequence[str], project: Path, path: Path | None = None
) -> str:
    """Maak een zelfstandig BAT-bestand met de gekozen commando's."""
    if not commands:
        raise ValueError("Kies minstens één opdracht.")
    folder = str(project.resolve()).replace("%", "%%")
    if path is None or path.parent.resolve() == project.resolve():
        folder = "%~dp0"
    lines = [
        "@echo off",
        "setlocal DisableDelayedExpansion",
        "chcp 65001 >nul",
        f'cd /d "{folder}"',
        "if errorlevel 1 goto einde",
        "",
    ]
    for command in commands:
        words = read_commands(command.removeprefix("& "))[0]
        lines.append(" ".join(_batch_argument(word) for word in words))
        lines.append("if errorlevel 1 goto einde")
    lines.extend(
        [
            "",
            ":einde",
            'set "run_exit_code=%errorlevel%"',
            "pause",
            "exit /b %run_exit_code%",
        ]
    )
    return "\n".join(lines) + "\n"


def save_script(
    script: str, path: Path, project: Path, *, start: bool = False
) -> subprocess.Popen | None:
    """Bewaar een zelfstandige runfile en start die desgewenst."""
    suffix = path.suffix.lower()
    if suffix not in {".bat", ".ps1"}:
        raise ValueError("Sla het runscript op met de extensie .bat of .ps1.")
    # PowerShell gebruikt een BOM; BAT schakelt zelf naar UTF-8.
    encoding = "utf-8" if suffix == ".bat" else "utf-8-sig"
    path.write_text(script, encoding=encoding)
    if not start:
        return None
    try:
        if suffix == ".bat":
            return start_batch(path, project)
        return start_commands(script, project)
    except OSError as error:
        raise OSError(f"Script opgeslagen in {path}. {error}") from error


def start_batch(path: Path, project: Path) -> subprocess.Popen:
    """Start het BAT-bestand vanuit de projectmap in een eigen venster."""
    if sys.platform != "win32":
        raise OSError("Start een BAT-bestand op Windows.")
    environment = os.environ.copy()
    environment["RUNSCRIPT_FILE"] = str(path.resolve())
    return subprocess.Popen(
        'cmd.exe /d /s /c ""%RUNSCRIPT_FILE%""',
        cwd=project,
        env=environment,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def start_commands(
    script: str, project: Path, *, env: dict[str, str] | None = None
) -> subprocess.Popen:
    """Start opdrachten in een apart venster dat de uitvoer leesbaar houdt."""
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        raise OSError("PowerShell is niet gevonden.")
    return subprocess.Popen(
        [powershell, "-NoProfile", "-NoExit", "-Command", _powershell_command(script)],
        cwd=project,
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def read_commands(text: str) -> list[list[str]]:
    """Lees letterlijke commando's; voer geen PowerShell-code uit."""
    pattern = re.compile(
        r"\s*(?P<word>'(?:[^']|'')*'|\"[^\"$`]*\"|[^\s'\";|&<>$`(){}#]+)(?=\s|$)"
    )
    commands = []
    for line in re.sub(r"`\r?\n", " ", text).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words = []
        position = 0
        while position < len(line):
            if line[position:].lstrip().startswith("#"):
                break
            match = pattern.match(line, position)
            if match is None:
                raise ValueError(
                    "Laad een runfile met alleen pixi-commando's, één per regel. "
                    "PowerShell-variabelen en andere opdrachten worden niet ingelezen."
                )
            word = match.group("word")
            if word.startswith("'"):
                word = word[1:-1].replace("''", "'")
            elif word.startswith('"'):
                word = word[1:-1]
            words.append(word)
            position = match.end()
        commands.append(words)
    if not commands:
        raise ValueError("Dit bestand bevat geen pixi-commando's.")
    return commands


def _read_batch_word(word: str) -> str:
    """Lees de letterlijke aanhalingstekens en procenttekens uit één argument."""
    if "%" in word.replace("%%", ""):
        raise ValueError("Gebruik letterlijke waarden in de pixi-commando's.")
    if word.startswith('"'):
        value = word[1:-1]

        def unquote(match: re.Match[str]) -> str:
            backslashes = match.group(1)
            if len(backslashes) % 2:
                raise ValueError("Controleer de aanhalingstekens in de runfile.")
            return "\\" * (len(backslashes) // 2) + '"'

        value = re.sub(r'(\\*)""', unquote, value)
        trailing = len(value) - len(value.rstrip("\\"))
        if trailing % 2:
            raise ValueError("Controleer de afsluitende backslash in de runfile.")
        if trailing:
            value = value[:-trailing] + "\\" * (trailing // 2)
    else:
        value = word
    return value.replace("%%", "%")


def read_batch_commands(text: str) -> list[list[str]]:
    """Lees de commando's uit een BAT-runfile zonder het bestand uit te voeren."""
    wrappers = {
        "@echo off",
        "setlocal disabledelayedexpansion",
        "chcp 65001 >nul",
        "if errorlevel 1 goto einde",
        ":einde",
        'set "run_exit_code=%errorlevel%"',
        "pause",
        "exit /b %run_exit_code%",
    }
    pattern = re.compile(r'\s*(?P<word>"(?:[^"]|"")*"|[^\s"^&|<>()%]+)(?=\s|$)')
    commands = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("rem ") or line.lower() in wrappers:
            continue
        if re.fullmatch(r'cd /d "[^"]+"', line, flags=re.IGNORECASE):
            continue
        words = []
        position = 0
        while position < len(line):
            match = pattern.match(line, position)
            if match is None:
                raise ValueError(
                    "Gebruik losse pixi-commando's zonder extra batchcode."
                )
            words.append(_read_batch_word(match.group("word")))
            position = match.end()
        commands.append(words)
    if not commands:
        raise ValueError("Dit bestand bevat geen pixi-commando's.")
    return commands
