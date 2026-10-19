"""
GeoJSON / JSON reader untuk pipeline spasial GMCP.

Membaca berkas ``.geojson`` atau ``.json`` menjadi kamus (dictionary) berisi
GeoDataFrame standar GMCP dengan empat lapisan kanonik:

    - AddressPoints
    - Parcels
    - RoadCenterlines
    - CommunityBoundary

Seluruh GeoDataFrame dinormalisasi ke CRS WGS84 (EPSG:4326).
"""

import os
import json

import geopandas as gpd

# Empat lapisan kanonik GMCP (urutan tetap).
GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]

TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    """Membuat kerangka kamus GMCP dengan GeoDataFrame kosong ber-CRS 4326."""
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _normalize_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Memastikan GeoDataFrame memiliki/diproyeksikan ke EPSG:4326."""
    if gdf is None:
        return gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)
    if len(gdf) == 0:
        return gdf
    if gdf.crs is None:
        # GeoJSON secara spesifikasi selalu WGS84; asumsikan 4326 bila kosong.
        gdf = gdf.set_crs(TARGET_CRS, allow_override=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


def _detect_layer_name(source, data: dict) -> str:
    """
    Menentukan nama lapisan GMCP dari properti ``name`` FeatureCollection
    atau dari nama berkas.
    """
    # 1. Properti "name" pada FeatureCollection.
    fc_name = (data or {}).get("name")
    if isinstance(fc_name, str):
        for layer in GMCP_LAYERS:
            if layer.lower() == fc_name.lower():
                return layer

    # 2. Dari nama berkas (jika source berupa path string).
    if isinstance(source, (str, os.PathLike)):
        stem = os.path.splitext(os.path.basename(str(source)))[0]
        for layer in GMCP_LAYERS:
            if layer.lower() == stem.lower():
                return layer
        for layer in GMCP_LAYERS:
            if layer.lower() in stem.lower():
                return layer

    return None


def parse_geojson_gmcp(file_source) -> dict:
    """
    Membaca satu berkas GeoJSON/JSON menjadi kamus GeoDataFrame standar GMCP.

    Hanya lapisan yang terdeteksi pada berkas ini yang akan terisi; lapisan
    lain tetap sebagai GeoDataFrame kosong ber-CRS EPSG:4326.

    Parameters
    ----------
    file_source : str | os.PathLike | file-like
        Path berkas ``.geojson``/``.json`` atau buffer (mis. upload Streamlit).

    Returns
    -------
    dict
        Kamus dengan kunci kanonik GMCP -> GeoDataFrame (EPSG:4326).
    """
    result = _empty_layers()

    # Baca metadata JSON untuk mendeteksi nama lapisan.
    raw_json = None
    try:
        if isinstance(file_source, (str, os.PathLike)):
            with open(file_source, "r", encoding="utf-8") as fh:
                raw_json = json.load(fh)
        elif hasattr(file_source, "read"):
            pos = file_source.tell() if hasattr(file_source, "tell") else None
            raw_json = json.load(file_source)
            if pos is not None and hasattr(file_source, "seek"):
                file_source.seek(pos)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        raw_json = None

    gdf = gpd.read_file(file_source)
    gdf = _normalize_crs(gdf)

    layer_name = _detect_layer_name(file_source, raw_json)
    if layer_name is None:
        # Tidak terdeteksi: kembalikan di bawah kunci khusus agar tidak hilang.
        result["_unmatched"] = gdf
    else:
        result[layer_name] = gdf

    return result
