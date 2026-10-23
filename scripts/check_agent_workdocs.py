"""Controleer tijdelijke agent-werkdocumenten in de volledige Git-index.

Centrale bron: d2hydro/devtools, scripts/check_agent_workdocs.py.
Zelfstandig te kopieren; vereist Python 3.11+ en Git, geen extra pakketten.
Exitcodes: 0 = schoon, 1 = tijdelijke bestanden, 2 = controle niet voltooid.
"""

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path

BLOCKED_DIRECTORIES = {
    "docs/bijdragen/implementatieplannen": "tijdelijke implementatieplannen",
    "reviewcases": "tijdelijke reviewrapporten, reproducties en resultaten",
}


def tracked_workdocs(repository: Path) -> list[str]:
    """Return blocked index entries from the entire repository, including staged files."""
    root_result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
    )
    root = os.fsdecode(root_result.stdout).rstrip("\r\n")
    index_result = subprocess.run(
        ["git", "-C", root, "ls-files", "--cached", "--full-name", "-z"],
        check=True,
        capture_output=True,
    )
    paths = {os.fsdecode(path) for path in index_result.stdout.split(b"\0") if path}
    return sorted(
        path
        for path in paths
        if any(
            path == directory or path.startswith(directory + "/")
            for directory in BLOCKED_DIRECTORIES
        )
    )


def _report(message: str, summary: Path | None, exit_code: int) -> int:
    """Print the result and optionally append a safely escaped Actions summary."""
    print(message, file=sys.stderr if exit_code == 2 else sys.stdout)
    if summary is not None:
        status = {0: "Geslaagd", 1: "Merge geblokkeerd", 2: "Controle niet voltooid"}
        markdown = (
            "## Tijdelijke agent-werkdocumenten\n\n"
            f"**{status[exit_code]}**\n\n"
            f"<pre>{html.escape(message)}</pre>\n\n"
        )
        try:
            with summary.open("a", encoding="utf-8") as destination:
                destination.write(markdown)
        except OSError as error:
            print(f"Samenvatting kon niet worden opgeslagen: {error}", file=sys.stderr)
            return 2
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository of een submap ervan (standaard: huidige werkmap).",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Voeg een Markdown-samenvatting toe aan dit bestand (optioneel).",
    )
    args = parser.parse_args(argv)
    try:
        blocked = tracked_workdocs(args.repo)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        if isinstance(detail, bytes):
            detail = os.fsdecode(detail).strip()
        return _report(
            f"Controle niet uitgevoerd: Git kon de repository niet uitlezen.\n{detail}",
            args.summary,
            2,
        )

    if not blocked:
        return _report(
            "Geslaagd: geen tijdelijke agent-werkdocumenten in de Git-index.",
            args.summary,
            0,
        )

    lines = [
        f"Merge geblokkeerd: {len(blocked)} tijdelijke agent-werkdocument(en) in Git."
    ]
    for path in blocked:
        reason = next(
            reason
            for directory, reason in BLOCKED_DIRECTORIES.items()
            if path == directory or path.startswith(directory + "/")
        )
        lines.append(f"  - {json.dumps(path, ensure_ascii=False)}: {reason}")
    lines.append(
        "Bewaar relevante kennis in reguliere documentatie en tests. "
        "Verwijder afgerond tijdelijk werk uit Git en stage die verwijdering. "
        "Alleen lokaal verwijderen of toevoegen aan .gitignore is niet voldoende. "
        "Niet-getrackte lokale bestanden worden niet gecontroleerd."
    )
    return _report("\n".join(lines), args.summary, 1)


if __name__ == "__main__":
    raise SystemExit(main())
