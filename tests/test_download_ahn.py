# %%
from waterlagen.ahn import create_download_dir, get_ahn_rasters


def test_download_ahn4_pdok(ahn_dir):
    """test if PDOK AHN4 downloader works"""
    model = "dtm"
    cell_size = "05"
    ahn_version = 4
    select_indices = ["M_19BZ1"]
    service = "ahn_pdok"

    # make download_dir and assert existing
    download_dir = create_download_dir(
        root_dir=ahn_dir,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )
    assert download_dir.exists()

    # download rasters and assert existing
    vrt_file = get_ahn_rasters(
        ahn_dir=download_dir,
        service=service,
        select_indices=select_indices,
        model=model,
        cell_size=cell_size,
        ahn_version=4,
        save_tiles_index=True,
        missing_only=False,
    )

    assert vrt_file.exists()
    assert vrt_file.with_name("M_19BZ1.tif").exists()
    assert vrt_file.with_suffix(".gpkg").exists()


def test_download_ahn5_datastroom(ahn_dir):
    """test if DataStromen AHN5 downloader works"""
    model = "dtm"
    cell_size = "05"
    ahn_version = 5
    select_indices = ["M_19BZ1"]
    service = "ahn_datastroom"

    # make download_dir and assert existing
    download_dir = create_download_dir(
        root_dir=ahn_dir,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )

    # download rasters and assert existing
    vrt_file = get_ahn_rasters(
        ahn_dir=download_dir,
        service=service,
        select_indices=select_indices,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
        save_tiles_index=True,
        missing_only=False,
    )
    assert vrt_file.exists()
    assert vrt_file.with_name("M_19BZ1.tif").exists()
    assert vrt_file.with_suffix(".gpkg").exists()


def test_download_ahn6_datastroom(ahn_dir):
    """test if DataStromen AHN6 downloader works"""
    model = "dtm"
    cell_size = "05"
    ahn_version = 6
    select_indices = ["249000_466000"]
    service = "ahn_datastroom"

    # make download_dir and assert existing
    download_dir = create_download_dir(
        root_dir=ahn_dir,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )

    # download rasters and assert existing
    vrt_file = get_ahn_rasters(
        ahn_dir=download_dir,
        service=service,
        select_indices=select_indices,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
        save_tiles_index=True,
    )
    assert vrt_file.exists()
    assert vrt_file.with_name("249000_466000.tif").exists()
    assert vrt_file.with_suffix(".gpkg").exists()
