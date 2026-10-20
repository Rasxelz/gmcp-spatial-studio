"""
GeoJSON / JSON reader untuk pipeline spasial GMCP.
"""

import os
import json
import geopandas as gpd

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _normalize_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf is None:
        return gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)
    if len(gdf) == 0:
        return gdf
    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS, allow_override=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


def _detect_layer_name(source, data: dict, explicit_filename: str = None, gdf: gpd.GeoDataFrame = None) -> str:
    # 1. Properti name di FeatureCollection
    fc_name = (data or {}).get("name")
    if isinstance(fc_name, str):
        for layer in GMCP_LAYERS:
            if layer.lower() == fc_name.lower():
                return layer

    # 2. Cek nama berkas
    candidate_name = explicit_filename
    if not candidate_name and isinstance(source, (str, os.PathLike)):
        candidate_name = os.path.basename(str(source))
    elif not candidate_name and hasattr(source, "name"):
        candidate_name = source.name

    if candidate_name:
        stem = os.path.splitext(os.path.basename(str(candidate_name)))[0].lower()
        if "address" in stem or "addr" in stem:
            return "AddressPoints"
        if "road" in stem or "street" in stem or "centerline" in stem:
            return "RoadCenterlines"
        if "parcel" in stem or "lot" in stem or "kavling" in stem:
            return "Parcels"
        if "bound" in stem or "community" in stem:
            return "CommunityBoundary"

    # 3. Fallback: tipe geometri
    if gdf is not None and not gdf.empty and 'geometry' in gdf:
        geom_types = gdf.geometry.geom_type.dropna().unique()
        if any("Point" in gt for gt in geom_types):
            return "AddressPoints"
        if any("Line" in gt for gt in geom_types):
            return "RoadCenterlines"
        if any("Polygon" in gt for gt in geom_types):
            return "Parcels"

    return "Parcels"


def parse_geojson_gmcp(file_source, filename: str = None, **kwargs) -> dict:
    result = _empty_layers()
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
    except Exception:
        raw_json = None

    if hasattr(file_source, "seek"):
        file_source.seek(0)

    gdf = gpd.read_file(file_source)
    gdf = _normalize_crs(gdf)

    target_layer = _detect_layer_name(file_source, raw_json, explicit_filename=filename, gdf=gdf)
    result[target_layer] = gdf

    return result