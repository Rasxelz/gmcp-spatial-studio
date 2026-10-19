"""
CSV reader untuk pipeline spasial GMCP.

Membaca berkas ``.csv`` tabular menjadi kamus (dictionary) berisi GeoDataFrame
standar GMCP dengan empat lapisan kanonik:

    - AddressPoints
    - Parcels
    - RoadCenterlines
    - CommunityBoundary

Geometri dibangun dari kolom tabular sesuai lapisan yang terdeteksi dari nama
berkas (LAT/LONG, corner{i}_lat/lon, point{i}_lat/lon). Seluruh GeoDataFrame
dinormalisasi ke CRS WGS84 (EPSG:4326).
"""

import os

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Polygon

# Empat lapisan kanonik GMCP (urutan tetap).
GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]

TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    """Membuat kerangka kamus GMCP dengan GeoDataFrame kosong ber-CRS 4326."""
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _csv_layer_name(source) -> str:
    """Menebak lapisan GMCP dari nama berkas CSV."""
    stem = os.path.splitext(os.path.basename(str(source)))[0]
    for layer in GMCP_LAYERS:
        if layer.lower() == stem.lower() or layer.lower() in stem.lower():
            return layer
    return None


def _build_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    valid = df.dropna(subset=["LAT", "LONG"])
    if len(valid) == 0:
        return gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)
    return gpd.GeoDataFrame(
        valid,
        geometry=gpd.points_from_xy(valid["LONG"], valid["LAT"]),
        crs=TARGET_CRS,
    )


def _build_polygons(df: pd.DataFrame, n_corners: int = 8) -> gpd.GeoDataFrame:
    geoms = []
    for _, row in df.iterrows():
        corners = []
        for i in range(1, n_corners + 1):
            lat = row.get(f"corner{i}_lat")
            lon = row.get(f"corner{i}_lon")
            if pd.notna(lat) and pd.notna(lon):
                corners.append((float(lon), float(lat)))
        if len(corners) >= 3:
            if corners[0] != corners[-1]:
                corners.append(corners[0])
            geoms.append(Polygon(corners))
        else:
            geoms.append(None)
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs=TARGET_CRS)
    return gdf.dropna(subset=["geometry"])


def _build_lines(df: pd.DataFrame, n_points: int = 10) -> gpd.GeoDataFrame:
    geoms = []
    for _, row in df.iterrows():
        pts = []
        for i in range(1, n_points + 1):
            lat = row.get(f"point{i}_lat")
            lon = row.get(f"point{i}_lon")
            if pd.notna(lat) and pd.notna(lon):
                pts.append((float(lon), float(lat)))
        geoms.append(LineString(pts) if len(pts) >= 2 else None)
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs=TARGET_CRS)
    return gdf.dropna(subset=["geometry"])


def parse_csv_gmcp(file_source) -> dict:
    """
    Membaca satu CSV tabular GMCP menjadi kamus GeoDataFrame.

    Geometri dibangun dari kolom tabular sesuai lapisan yang terdeteksi dari
    nama berkas (LAT/LONG, corner{i}_lat/lon, point{i}_lat/lon).

    Parameters
    ----------
    file_source : str | os.PathLike | file-like
        Path berkas ``.csv`` atau buffer (mis. upload Streamlit).

    Returns
    -------
    dict
        Kamus dengan kunci kanonik GMCP -> GeoDataFrame (EPSG:4326).
    """
    result = _empty_layers()
    df = pd.read_csv(file_source)
    layer = _csv_layer_name(file_source)

    if layer == "AddressPoints":
        result[layer] = _build_points(df)
    elif layer in ("Parcels", "CommunityBoundary"):
        result[layer] = _build_polygons(df)
    elif layer == "RoadCenterlines":
        result[layer] = _build_lines(df)
    else:
        # Fallback: deteksi dari kolom yang tersedia.
        if {"LAT", "LONG"}.issubset(df.columns):
            result["AddressPoints"] = _build_points(df)
        elif "point1_lat" in df.columns:
            result["RoadCenterlines"] = _build_lines(df)
        elif "corner1_lat" in df.columns:
            result["Parcels"] = _build_polygons(df)
        else:
            result["_unmatched"] = gpd.GeoDataFrame(df)

    return result


def parse_csv_directory(dir_or_list) -> dict:
    """
    Membaca banyak CSV GMCP dan menggabungkannya menjadi satu kamus standar.

    Parameters
    ----------
    dir_or_list : str | os.PathLike | iterable
        Path direktori berisi berkas ``*.csv`` ATAU daftar/iterable path CSV.

    Returns
    -------
    dict
        Kamus empat lapisan kanonik GMCP -> GeoDataFrame (EPSG:4326). Lapisan
        yang terdeteksi dari berkas belakangan menimpa lapisan sejenis dari
        berkas sebelumnya.
    """
    if isinstance(dir_or_list, (str, os.PathLike)):
        base = str(dir_or_list)
        paths = sorted(
            os.path.join(base, name)
            for name in os.listdir(base)
            if name.lower().endswith(".csv")
        )
    else:
        paths = list(dir_or_list)

    result = _empty_layers()
    for path in paths:
        parsed = parse_csv_gmcp(path)
        for layer in GMCP_LAYERS:
            gdf = parsed.get(layer)
            if gdf is not None and len(gdf) > 0:
                result[layer] = gdf

    return result
