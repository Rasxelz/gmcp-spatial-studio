"""
KML / KMZ Reader untuk pipeline spasial GMCP.
Menggunakan modul bawaan Python (xml.etree.ElementTree) & Shapely murni,
sehingga tidak memerlukan pustaka eksternal seperti fiona.
"""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def _parse_kml_text(xml_string: str) -> list:
    """Mengurai string XML KML menjadi daftar rekaman dictionary."""
    records = []
    try:
        root = ET.fromstring(xml_string)
    except Exception:
        return records

    # Deteksi XML namespace bila ada
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    for pm in root.findall(f".//{ns}Placemark"):
        name_el = pm.find(f"{ns}name")
        desc_el = pm.find(f"{ns}description")
        name = name_el.text.strip() if (name_el is not None and name_el.text) else ""
        desc = desc_el.text.strip() if (desc_el is not None and desc_el.text) else ""

        # 1. Parsing Titik (Point)
        pt_el = pm.find(f".//{ns}Point/{ns}coordinates")
        if pt_el is not None and pt_el.text:
            coords = pt_el.text.strip().split(",")
            if len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])
                records.append({
                    "Name": name,
                    "Description": desc,
                    "geometry": Point(lon, lat),
                    "geom_type": "Point"
                })
                continue

        # 2. Parsing Garis (LineString)
        ls_el = pm.find(f".//{ns}LineString/{ns}coordinates")
        if ls_el is not None and ls_el.text:
            pts = []
            for token in ls_el.text.strip().split():
                c = token.split(",")
                if len(c) >= 2:
                    pts.append((float(c[0]), float(c[1])))
            if len(pts) >= 2:
                records.append({
                    "Name": name,
                    "Description": desc,
                    "geometry": LineString(pts),
                    "geom_type": "LineString"
                })
                continue

        # 3. Parsing Poligon (Polygon)
        poly_el = pm.find(f".//{ns}Polygon//{ns}coordinates")
        if poly_el is not None and poly_el.text:
            pts = []
            for token in poly_el.text.strip().split():
                c = token.split(",")
                if len(c) >= 2:
                    pts.append((float(c[0]), float(c[1])))
            if len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                records.append({
                    "Name": name,
                    "Description": desc,
                    "geometry": Polygon(pts),
                    "geom_type": "Polygon"
                })
                continue

    return records


def parse_kml_gmcp(file_source, filename: str = "data.kml") -> dict:
    """
    Membaca berkas KML atau KMZ dan memetakannya ke kamus 4 layer GMCP.
    """
    layers = _empty_layers()
    ext = os.path.splitext(filename)[1].lower()
    raw_xml = ""

    # Ekstraksi byte data
    if hasattr(file_source, "read"):
        content = file_source.read()
        if hasattr(file_source, "seek"):
            file_source.seek(0)
    else:
        with open(file_source, "rb") as f:
            content = f.read()

    # Ekstraksi KMZ (ZIP) atau KML
    if ext == ".kmz":
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                for f in zf.namelist():
                    if f.lower().endswith(".kml"):
                        raw_xml = zf.read(f).decode("utf-8", errors="replace")
                        break
        except Exception:
            return layers
    else:
        raw_xml = content.decode("utf-8", errors="replace")

    if not raw_xml:
        return layers

    records = _parse_kml_text(raw_xml)
    if not records:
        return layers

    addr_recs, parcels_recs, roads_recs, bound_recs = [], [], [], []

    for r in records:
        gt = r.get("geom_type")
        name_val = r.get("Name", "").lower()
        desc_val = r.get("Description", "").lower()

        if gt == "Point":
            addr_recs.append(r)
        elif gt == "LineString":
            roads_recs.append(r)
        elif gt == "Polygon":
            if any(k in name_val or k in desc_val for k in ["boundary", "batas", "kawasan", "perimeter"]):
                bound_recs.append(r)
            else:
                parcels_recs.append(r)

    if addr_recs:
        layers["AddressPoints"] = gpd.GeoDataFrame(addr_recs, crs=TARGET_CRS).drop(columns=["geom_type"])
    if parcels_recs:
        layers["Parcels"] = gpd.GeoDataFrame(parcels_recs, crs=TARGET_CRS).drop(columns=["geom_type"])
    if roads_recs:
        layers["RoadCenterlines"] = gpd.GeoDataFrame(roads_recs, crs=TARGET_CRS).drop(columns=["geom_type"])
    if bound_recs:
        layers["CommunityBoundary"] = gpd.GeoDataFrame(bound_recs, crs=TARGET_CRS).drop(columns=["geom_type"])

    return layers