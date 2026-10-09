"""Zoekindex voor stap 1: vind verblijfsobjecten snel op pand-ID.

- Eén rij per koppeling tussen pand en verblijfsobject.
- Gedeelde verblijfsobjecten krijgen een rij voor ieder pand.
- Bewaar de index naast de BAG; wijzig de bron niet.
"""

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from waterlagen.logger import get_logger

logger = get_logger(__name__)


def _read_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _fingerprint(path: Path, layer: str) -> str:
    # Versie, bronpad, bestandsgrootte, wijzigingsdatum en laagnaam.
    # Hiermee controleren we of de opgeslagen koppelingen nog bij de bron horen.
    stat = path.stat()
    return json.dumps([1, str(path.resolve()), stat.st_size, stat.st_mtime_ns, layer])


def _is_current(path: Path, fingerprint: str) -> bool:
    if not path.is_file():
        return False
    try:
        with closing(_read_connection(path)) as connection:
            row = connection.execute("SELECT fingerprint FROM metadata").fetchone()
        return row == (fingerprint,)
    except sqlite3.DatabaseError:
        return False


def _write_pand_vbo_links(
    source: sqlite3.Connection, output: sqlite3.Connection, layer: str
) -> int:
    """Lees de bron eenmaal; schrijf een rij per pand-VBO-koppeling plus zoekindex."""
    quoted_layer = '"' + layer.replace('"', '""') + '"'
    columns = source.execute(f"PRAGMA table_info({quoted_layer})").fetchall()
    primary = [row for row in columns if row[5]]
    if len(primary) != 1 or primary[0][2].upper() != "INTEGER":
        raise ValueError("BAG VBO-laag vereist één INTEGER primary key (FID).")
    fid_column = '"' + primary[0][1].replace('"', '""') + '"'
    output.execute(
        "CREATE TABLE links (pand_id TEXT NOT NULL, vbo_fid INTEGER NOT NULL)"
    )
    cursor = source.execute(
        f"SELECT {fid_column}, pand_identificatie FROM {quoted_layer}"
    )
    count = 0
    while True:
        rows = cursor.fetchmany(50_000)
        if not rows:
            break
        # Spaties verwijderen en volledige IDs splitsen; 12 mag niet 112 vinden.
        links = []
        for fid, value in rows:
            if value is None:
                continue
            for pand_id in set(str(value).replace(" ", "").split(",")):
                if pand_id:
                    links.append((pand_id, fid))
        output.executemany("INSERT INTO links VALUES (?, ?)", links)
        count += len(rows)
        if count % 1_000_000 == 0:
            logger.info("BAG pand-VBO-index: %s verblijfsobjecten verwerkt", count)
    output.execute("CREATE UNIQUE INDEX links_by_pand ON links (pand_id, vbo_fid)")
    return count


def ensure_bag_link_index(path: Path, *, layer: str = "verblijfsobject") -> Path:
    """Maak of hergebruik de zoekindex voor pand-ID's.

    Parameters
    ----------
    path : pathlib.Path
        BAG-GeoPackage; de map moet schrijfbaar zijn voor de aparte index.
    layer : str, optional
        Verblijfsobjectenlaag met ``pand_identificatie`` als kommagescheiden lijst.

    Returns
    -------
    pathlib.Path
        - SQLite-index naast het bronbestand.
        - Opnieuw opgebouwd bij gewijzigd bronpad, bestandsgrootte, datum of laag.
        - Pas vervangen na validatie; gedeeld door alle workers.
    """
    path = Path(path)
    # Een andere verblijfsobjectenlaag krijgt een eigen indexnaam.
    layer_suffix = "" if layer == "verblijfsobject" else f".{layer.encode().hex()}"
    target = path.with_name(f"{path.stem}{layer_suffix}.pand_vbo.sqlite")
    fingerprint = _fingerprint(path, layer)
    # 1. Een actuele index kan direct worden hergebruikt door alle workers.
    if _is_current(target, fingerprint):
        return target
    logger.info("BAG pand-VBO-index opbouwen: %s", target)
    # 2. Bouw eerst een compleet nieuw zoekbestand naast het bestaande.
    with tempfile.TemporaryDirectory(prefix=".bag_index_", dir=target.parent) as work:
        temporary = Path(work) / "index.sqlite"
        with (
            closing(_read_connection(path)) as source,
            closing(sqlite3.connect(temporary)) as output,
        ):
            count = _write_pand_vbo_links(source, output, layer)
            output.execute("CREATE TABLE metadata (fingerprint TEXT NOT NULL)")
            output.execute("INSERT INTO metadata VALUES (?)", (fingerprint,))
            output.commit()
            if output.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Validatie BAG pand-VBO-index mislukt.")
        if _fingerprint(path, layer) != fingerprint:
            raise RuntimeError("BAG-bron gewijzigd tijdens het opbouwen van de index.")
        # 3. Alleen een complete index van een ongewijzigde bron overnemen.
        temporary.replace(target)
    logger.info("BAG pand-VBO-index gereed: %s verblijfsobjecten", count)
    return target


def find_vbo_fids(index_path: Path, pand_ids: list[str]) -> list[int]:
    """Zoek unieke FID's van verblijfsobjecten op volledige pand-ID's.

    Parameters
    ----------
    index_path : pathlib.Path
        Index gemaakt met ``ensure_bag_link_index``.
    pand_ids : list[str]
        Pand-ID's, inclusief voorloopnullen.

    Returns
    -------
    list[int]
        Unieke FID's in bronvolgorde, ook van gedeelde verblijfsobjecten.
    """
    fids = set()
    with closing(_read_connection(index_path)) as connection:
        for start in range(0, len(pand_ids), 500):
            batch = pand_ids[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT vbo_fid FROM links WHERE pand_id IN ({placeholders})", batch
            )
            fids.update(row[0] for row in rows)
    return sorted(fids)
