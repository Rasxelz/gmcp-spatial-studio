"""
DXF Reader untuk pipeline spasial GMCP.
Membaca berkas CAD .dxf (AutoCAD siteplan) menggunakan ezdxf murni
dan mengekstrak entitas spasial ke 4 layer kanonik GMCP:
    - AddressPoints (dari entitas POINT / TEXT)
    - Parcels (dari entitas LWPOLYLINE/POLYLINE tertutup pada layer kavling)
    - RoadCenterlines (dari entitas LINE / LWPOLYLINE terbuka pada layer jalan)
    - CommunityBoundary (dari poligon batas kawasan)

Seluruh GeoDataFrame menggunakan CRS EPSG:4326.
"""

import os
import io
import tempfile
import ezdxf
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


def _empty_layers() -> dict:
    return {
        name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
    }


def parse_dxf_gmcp(file_source, filename: str = "drawing.dxf") -> dict:
    """
    Membaca berkas .dxf (str path atau buffer BytesIO) dan mengembalikan
    kamus GeoDataFrame standar GMCP WGS84.
    """
    layers = _empty_layers()

    # 1. Buka dokumen DXF (langsung jika path, atau via tempfile jika buffer Streamlit)
    doc = None
    if isinstance(file_source, (str, os.PathLike)) and os.path.exists(file_source):
        try:
            doc = ezdxf.readfile(file_source)
        except Exception:
            return layers
    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_name = os.path.basename(filename)
            tmp_dxf = os.path.join(tmp_dir, f"temp_{safe_name}")
            if hasattr(file_source, "read"):
                content = file_source.read()
                if hasattr(file_source, "seek"):
                    file_source.seek(0)
                with open(tmp_dxf, "wb") as f:
                    f.write(content)
            try:
                doc = ezdxf.readfile(tmp_dxf)
            except Exception:
                return layers

    if doc is None:
        return layers

    msp = doc.modelspace()

    addr_recs = []
    parcels_recs = []
    roads_recs = []
    bound_recs = []

    for entity in msp:
        layer_name = str(entity.dxf.layer).lower()
        dxftype = entity.dxftype()

        # 1. ENTITAS TITIK (POINT / TEXT)
        if dxftype == "POINT":
            loc = entity.dxf.location
            addr_recs.append({
                "CAD_Layer": entity.dxf.layer,
                "geometry": Point(loc.x, loc.y)
            })
        elif dxftype == "TEXT":
            loc = entity.dxf.insert
            addr_recs.append({
                "CAD_Layer": entity.dxf.layer,
                "Text": entity.dxf.text,
                "geometry": Point(loc.x, loc.y)
            })

        # 2. ENTITAS GARIS (LINE) -> Jalan
        elif dxftype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            geom = LineString([(start.x, start.y), (end.x, end.y)])
            roads_recs.append({
                "CAD_Layer": entity.dxf.layer,
                "geometry": geom
            })

        # 3. ENTITAS POLILIN (LWPOLYLINE / POLYLINE)
        elif dxftype in ["LWPOLYLINE", "POLYLINE"]:
            if dxftype == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in entity.get_points(format="xy")]
            else:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]

            if len(pts) < 2:
                continue

            is_closed = entity.is_closed

            # Jika tertutup -> Poligon (Kavling atau Batas)
            if is_closed and len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                poly_geom = Polygon(pts)
                
                if any(k in layer_name for k in ["bound", "batas", "perimeter"]):
                    bound_recs.append({"CAD_Layer": entity.dxf.layer, "geometry": poly_geom})
                else:
                    parcels_recs.append({"CAD_Layer": entity.dxf.layer, "geometry": poly_geom})

            # Jika terbuka -> Garis Jalan
            else:
                roads_recs.append({
                    "CAD_Layer": entity.dxf.layer,
                    "geometry": LineString(pts)
                })

    if addr_recs:
        layers["AddressPoints"] = gpd.GeoDataFrame(addr_recs, crs=TARGET_CRS)
    if parcels_recs:
        layers["Parcels"] = gpd.GeoDataFrame(parcels_recs, crs=TARGET_CRS)
    if roads_recs:
        layers["RoadCenterlines"] = gpd.GeoDataFrame(roads_recs, crs=TARGET_CRS)
    if bound_recs:
        layers["CommunityBoundary"] = gpd.GeoDataFrame(bound_recs, crs=TARGET_CRS)

    return layers