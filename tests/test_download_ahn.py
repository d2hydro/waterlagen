from waterrasters.ahn import get_ahn_rasters, get_tiles_gdf

SELECT_INDICES = ["M_19BZ1", "M_25BN2", "M_14EN1", "M_14EZ1"]


def test_get_index():
    """test if ahn index hasn't changed"""

    gdf = get_tiles_gdf()
    assert len(gdf) == 1373
    assert "kaartbladNr" in gdf.columns
    assert [int(i) for i in gdf.total_bounds] == [10000, 306250, 280000, 618750]
    assert len(gdf[gdf["kaartbladNr"].isin(SELECT_INDICES)]) == 4


def test_download_raster(ahn_dir):
    """test if downloader works"""

    get_ahn_rasters(
        download_dir=ahn_dir,
        select_indices=["M_19BZ1"],
        ahn_type="dtm_05m",
    )

    dtm_dir = ahn_dir / "dtm_05m"
    assert dtm_dir.joinpath("M_19BZ1.tif").exists()
    assert dtm_dir.joinpath("dtm_05m.vrt").exists()
