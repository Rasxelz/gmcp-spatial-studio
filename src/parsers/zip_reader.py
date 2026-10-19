"""
Smart ZIP Reader untuk pipeline spasial GMCP.
Mengekstrak dan memindai arsip .zip secara otomatis untuk mendeteksi:
    - Shapefile (.shp)
    - Kumpulan GeoJSON (.geojson / .json)
    - Kumpulan CSV (.csv)
    - GeoPackage (.gpkg), KML (.kml), atau DXF (.dxf)
dan mengembalikannya sebagai kamus 4 layer kanonik GMCP (EPSG:4326).
"""

import os
import io
import zipfile
import tempfile
import geopandas as gpd

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _match_target_layer(name: str) -> str:
    """Mencocokkan nama berkas ke salah satu dari 4 layer kanonik GMCP."""
    nl = os.path.splitext(os.path.basename(name))[0].lower()
    if "address" in nl or "point" in nl:
        return "AddressPoints"
    elif "parcel" in nl or "kavling" in nl or "lot" in nl:
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


def parse_zip_package(file_source, filename: str = "archive.zip") -> dict:
    """
    Mengekstrak arsip .zip dan memetakan kontennya ke 4 layer GMCP.
    Mendukung path str maupun buffer stream BytesIO dari Streamlit.
    """
    layers = _empty_layers()

    # Siapkan byte arsip ZIP
    if hasattr(file_source, "read"):
        content = file_source.read()
        if hasattr(file_source, "seek"):
            file_source.seek(0)
        zip_bytes = io.BytesIO(content)
    elif isinstance(file_source, (str, os.PathLike)) and os.path.exists(file_source):
        with open(file_source, "rb") as f:
            zip_bytes = io.BytesIO(f.read())
    else:
        return layers

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            with zipfile.ZipFile(zip_bytes, "r") as zf:
                zf.extractall(tmp_dir)
        except Exception:
            return layers

        # Kumpulkan semua berkas yang ada di dalam ZIP
        extracted_files = []
        for root, _, files in os.walk(tmp_dir):
            for f in files:
                extracted_files.append(os.path.join(root, f))

        # 1. PRIORITAS 1: Periksa berkas Shapefile (.shp)
        shp_files = [f for f in extracted_files if f.lower().endswith(".shp")]
        if shp_files:
            for shp_path in shp_files:
                target = _match_target_layer(shp_path)
                if target:
                    try:
                        gdf = gpd.read_file(shp_path, engine="pyogrio")
                    except Exception:
                        gdf = gpd.read_file(shp_path)
                    layers[target] = _normalize_crs(gdf)
            return layers

        # 2. PRIORITAS 2: Periksa berkas GeoJSON (.geojson / .json)
        geojson_files = [
            f for f in extracted_files 
            if f.lower().endswith((".geojson", ".json")) and not f.lower().endswith("manifest.json")
        ]
        if geojson_files:
            for gj_path in geojson_files:
                target = _match_target_layer(gj_path)
                if target:
                    try:
                        gdf = gpd.read_file(gj_path, engine="pyogrio")
                    except Exception:
                        gdf = gpd.read_file(gj_path)
                    layers[target] = _normalize_crs(gdf)
            return layers

        # 3. PRIORITAS 3: Periksa berkas GeoPackage (.gpkg)
        gpkg_files = [f for f in extracted_files if f.lower().endswith(".gpkg")]
        if gpkg_files:
            from src.parsers.gpkg_reader import parse_gpkg_gmcp
            return parse_gpkg_gmcp(gpkg_files[0], os.path.basename(gpkg_files[0]))

        # 4. PRIORITAS 4: Periksa berkas CSV (.csv)
        csv_files = [
            f for f in extracted_files 
            if f.lower().endswith(".csv") and "audit" not in f.lower()
        ]
        if csv_files:
            from src.parsers.csv_reader import parse_csv_gmcp
            for cf in csv_files:
                target = _match_target_layer(cf)
                if target:
                    c_gdf = parse_csv_gmcp(cf, target)
                    layers[target] = _normalize_crs(c_gdf)
            return layers

        # 5. PRIORITAS 5: Periksa berkas DXF (.dxf)
        dxf_files = [f for f in extracted_files if f.lower().endswith(".dxf")]
        if dxf_files:
            from src.parsers.dxf_reader import parse_dxf_gmcp
            return parse_dxf_gmcp(dxf_files[0], os.path.basename(dxf_files[0]))

        # 6. PRIORITAS 6: Periksa berkas KML (.kml)
        kml_files = [f for f in extracted_files if f.lower().endswith(".kml")]
        if kml_files:
            from src.parsers.kml_reader import parse_kml_gmcp
            return parse_kml_gmcp(kml_files[0], os.path.basename(kml_files[0]))

    return layers