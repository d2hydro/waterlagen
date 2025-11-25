# %%
from waterrasters.ahn import create_download_dir, get_ahn_rasters


def test_download_raster(ahn_dir):
    """test if downloader works"""
    model_type = "dtm"
    cell_size = "05"
    ahn_version = 4

    # make download_dir and assert existing
    download_dir = create_download_dir(
        root_dir=ahn_dir,
        model_type=model_type,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )
    assert download_dir.exists()

    # download rasters and assert existing
    get_ahn_rasters(
        download_dir=download_dir,
        service="ahn_pdok",
        select_indices=["M_19BZ1"],
        model_type=model_type,
        cell_size=cell_size,
        ahn_version=4,
    )

    assert download_dir.joinpath("M_19BZ1.tif").exists()
    vrt_file = f"{download_dir.name}.vrt"
    assert download_dir.joinpath(vrt_file).exists()
