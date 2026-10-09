import os
import sqlite3
from contextlib import closing

import pytest

from waterlagen.functioneel_landgebruik.bag_zoekindex import (
    ensure_bag_link_index,
    find_vbo_fids,
)


def make_source(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE verblijfsobject (fid INTEGER PRIMARY KEY, pand_identificatie TEXT)"
        )
        connection.executemany(
            "INSERT INTO verblijfsobject VALUES (?, ?)",
            [
                (1, "0012, 0013,0012"),
                (2, "00112"),
                (3, None),
                (4, "0012"),
                (5, "quote'id"),
                (6, ""),
            ],
        )
        connection.commit()


def test_exact_shared_ids_index_lookup_and_reuse(tmp_path):
    source = tmp_path / "bag.gpkg"
    make_source(source)
    original = source.read_bytes()
    index = ensure_bag_link_index(source)
    assert find_vbo_fids(index, ["0012", "0013"]) == [1, 4]
    assert find_vbo_fids(index, ["0013"]) == [1]
    assert find_vbo_fids(index, ["quote'id"]) == [5]
    assert find_vbo_fids(index, ["unknown"]) == []
    assert find_vbo_fids(index, []) == []
    assert find_vbo_fids(index, ["0012"] * 1001) == [1, 4]
    timestamp = index.stat().st_mtime_ns
    assert ensure_bag_link_index(source) == index
    assert index.stat().st_mtime_ns == timestamp
    assert source.read_bytes() == original
    with closing(sqlite3.connect(index)) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT vbo_fid FROM links WHERE pand_id IN (?)",
            ("0012",),
        ).fetchall()
    assert any("SEARCH" in row[3] and "links_by_pand" in row[3] for row in plan)


def test_source_change_and_invalid_cache_are_rebuilt(tmp_path):
    source = tmp_path / "bag.gpkg"
    make_source(source)
    index = ensure_bag_link_index(source)
    before = source.stat()
    with closing(sqlite3.connect(source)) as connection:
        connection.execute(
            "UPDATE verblijfsobject SET pand_identificatie='new' WHERE fid=4"
        )
        connection.commit()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    ensure_bag_link_index(source)
    assert find_vbo_fids(index, ["0012"]) == [1]
    assert find_vbo_fids(index, ["new"]) == [4]
    index.write_bytes(b"broken cache")
    ensure_bag_link_index(source)
    assert find_vbo_fids(index, ["new"]) == [4]


def test_failed_rebuild_keeps_previous_index(tmp_path):
    source = tmp_path / "bag.gpkg"
    make_source(source)
    index = ensure_bag_link_index(source)
    previous = index.read_bytes()
    with closing(sqlite3.connect(source)) as connection:
        connection.execute(
            "ALTER TABLE verblijfsobject RENAME COLUMN pand_identificatie TO missing"
        )
        connection.commit()
    with pytest.raises(sqlite3.OperationalError):
        ensure_bag_link_index(source)
    assert index.read_bytes() == previous
