"""
OGC GeoPackage (.gpkg) Reader untuk pipeline spasial GMCP.
Membaca basis data spasial multi-layer .gpkg menggunakan pyogrio / geopandas
dan memetakannya ke kamus 4 layer kanonik GMCP:
    - AddressPoints
    - Parcels
    - RoadCenterlines
    - CommunityBoundary

Seluruh GeoDataFrame menggunakan CRS EPSG:4326.
"""

import os
import io
import tempfile
import geopandas as gpd

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _match_target_layer(name: str) -> str:
    """Mencocokkan nama layer di dalam GPKG ke standar GMCP."""
    nl = name.lower()
    if "address" in nl or "point" in nl:
        return "AddressPoints"
    elif "parcel" in nl or "kavling" in nl:
        return "Parcels"
    elif "road" in nl or "jalan" in nl or "centerline" in nl:
        return "RoadCenterlines"
    elif "bound" in nl or "community" in nl or "perimeter" in nl:
        return "CommunityBoundary"
    return None


def _normalize_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalisasi CRS ke EPSG:4326."""
    if gdf is None or len(gdf) == 0:
        return gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)
    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS, allow_override=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    return gdf


def parse_gpkg_gmcp(file_source, filename: str = "data.gpkg") -> dict:
    """
    Membaca berkas .gpkg (path str atau buffer BytesIO) dan mengembalikan
    kamus GeoDataFrame standar GMCP WGS84.
    """
    layers = _empty_layers()

    # Siapkan path berkas
    clean_up = False
    if isinstance(file_source, (str, os.PathLike)) and os.path.exists(file_source):
        target_path = file_source
    else:
        clean_up = True
        safe_name = os.path.basename(filename)
        tmp_file = tempfile.NamedTemporaryFile(suffix=f"_{safe_name}", delete=False)
        target_path = tmp_file.name
        if hasattr(file_source, "read"):
            content = file_source.read()
            if hasattr(file_source, "seek"):
                file_source.seek(0)
            tmp_file.write(content)
        else:
            with open(file_source, "rb") as f_in:
                tmp_file.write(f_in.read())
        tmp_file.close()

    try:
        # Deteksi daftar layer yang ada di dalam GPKG
        available_layers = []
        try:
            import pyogrio
            layers_info = pyogrio.list_layers(target_path)
            # pyogrio list_layers mengembalikan array Nx2 [layer_name, geom_type]
            available_layers = [row[0] for row in layers_info]
        except Exception:
            # Fallback jika list_layers gagal
            available_layers = GMCP_LAYERS

        for l_name in available_layers:
            target_key = _match_target_layer(l_name)
            if not target_key:
                continue

            try:
                gdf = gpd.read_file(target_path, layer=l_name, engine="pyogrio")
            except Exception:
                try:
                    gdf = gpd.read_file(target_path, layer=l_name)
                except Exception:
                    continue

            if len(gdf) > 0:
                layers[target_key] = _normalize_crs(gdf)

    finally:
        if clean_up and os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass

    return layers