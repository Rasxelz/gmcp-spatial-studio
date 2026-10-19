"""
Shapefile (ESRI) reader untuk pipeline spasial GMCP.

Mengekstrak arsip ``.zip`` yang berisi satu atau lebih suite Shapefile
(``.shp`` + ``.dbf`` + ``.prj`` + ``.shx`` + ``.cpg``) dan membacanya menjadi
kamus GeoDataFrame standar GMCP:

    - AddressPoints
    - Parcels
    - RoadCenterlines
    - CommunityBoundary

Seluruh GeoDataFrame dinormalisasi ke CRS WGS84 (EPSG:4326).
"""

import os
import tempfile
import zipfile

import geopandas as gpd

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _normalize_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf is None or len(gdf) == 0:
        return gdf
    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS, allow_override=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


def _match_layer(stem: str) -> str:
    """Mencocokkan nama berkas (.shp) dengan lapisan kanonik GMCP."""
    for layer in GMCP_LAYERS:
        if layer.lower() == stem.lower():
            return layer
    for layer in GMCP_LAYERS:
        if layer.lower() in stem.lower():
            return layer
    return None


def parse_shapefile_zip(zip_source) -> dict:
    """
    Mengekstrak arsip ZIP berisi Shapefile dan membaca tiap ``.shp`` menjadi
    kamus GeoDataFrame standar GMCP (EPSG:4326).

    Parameters
    ----------
    zip_source : str | os.PathLike | file-like
        Path berkas ``.zip`` atau buffer (mis. upload Streamlit).

    Returns
    -------
    dict
        Kamus dengan kunci kanonik GMCP -> GeoDataFrame (EPSG:4326).
        Shapefile yang tidak cocok dengan lapisan kanonik disimpan di bawah
        kunci bernama stem berkasnya.

    Raises
    ------
    ValueError
        Bila arsip tidak memuat satu pun berkas ``.shp``.
    """
    result = _empty_layers()

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_source, "r") as zf:
            zf.extractall(tmpdir)

        # Temukan seluruh .shp secara rekursif (arsip mungkin punya subfolder).
        shp_files = []
        for root, _dirs, files in os.walk(tmpdir):
            for fname in files:
                if fname.lower().endswith(".shp"):
                    shp_files.append(os.path.join(root, fname))

        if not shp_files:
            raise ValueError(
                "Arsip ZIP tidak mengandung berkas Shapefile (.shp) apa pun."
            )

        for shp_path in sorted(shp_files):
            stem = os.path.splitext(os.path.basename(shp_path))[0]
            gdf = _normalize_crs(gpd.read_file(shp_path))

            layer_name = _match_layer(stem)
            if layer_name is not None:
                result[layer_name] = gdf
            else:
                result[stem] = gdf

    return result
