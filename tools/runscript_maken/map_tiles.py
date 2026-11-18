"""Haal uitsluitend zichtbare kaarttegels op en hergebruik ze lokaal."""

import threading
import time
from pathlib import Path

import requests

SOURCES = {
    "streets": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "aerial": "https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/Actueel_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg",
}
LIMIT = threading.Semaphore(4)


def tile(cache: Path, provider: str, level: int, x: int, y: int) -> tuple[bytes, str]:
    """Lees een OSM- of PDOK-tegel; download geen tegels buiten de kaartvraag."""
    maximum = 21 if provider == "aerial" else 19
    if provider not in SOURCES or not (
        0 <= level <= maximum and 0 <= x < 2**level and 0 <= y < 2**level
    ):
        raise ValueError("Ongeldige kaarttegel.")
    target = cache / provider / str(level) / str(x) / f"{y}.tile"
    lifetime = 86400 if provider == "aerial" else 7 * 86400
    with LIMIT:
        if not target.exists() or time.time() - target.stat().st_mtime > lifetime:
            response = requests.get(
                SOURCES[provider].format(z=level, x=x, y=y),
                timeout=20,
                headers={
                    "User-Agent": "Waterlagen-RunMaken/1.0 (+https://d2hydro.github.io/waterlagen/)",
                    "Referer": "https://d2hydro.github.io/waterlagen/",
                },
            )
            response.raise_for_status()
            content = response.content
            if not response.headers.get("Content-Type", "").startswith(
                "image/"
            ) or not content.startswith((b"\x89PNG", b"\xff\xd8")):
                raise ValueError("Kaartbron gaf geen afbeelding.")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(f".{threading.get_ident()}.tmp")
            try:
                temporary.write_bytes(content)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        content = target.read_bytes()
    return content, "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
