import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

def parse_excel_gmcp(file_source) -> dict:
    """
    Membaca template Excel GMCP dan mengubah seluruh sheet menjadi GeoDataFrame WGS84 (EPSG:4326).
    Mendukung input berupa file path (str) atau buffer upload Streamlit (BytesIO).
    """
    xl = pd.ExcelFile(file_source)
    sheets = xl.sheet_names

    result = {
        "AddressPoints": gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        "Parcels": gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        "RoadCenterlines": gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        "CommunityBoundary": gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    }

    # 1. AddressPoints (Geometri: Point dari LAT & LONG)
    if "AddressPoints" in sheets:
        df_addr = pd.read_excel(xl, "AddressPoints")
        df_valid = df_addr.dropna(subset=['LAT', 'LONG'])
        if len(df_valid) > 0:
            result["AddressPoints"] = gpd.GeoDataFrame(
                df_valid,
                geometry=gpd.points_from_xy(df_valid['LONG'], df_valid['LAT']),
                crs="EPSG:4326"
            )

    # 2. Parcels (Geometri: Polygon dari corner1 s/d corner8)
    if "Parcels" in sheets:
        df_parcels = pd.read_excel(xl, "Parcels")
        parcels_geoms = []
        for _, row in df_parcels.iterrows():
            corners = []
            for i in range(1, 9):
                lat = row.get(f'corner{i}_lat')
                lon = row.get(f'corner{i}_lon')
                if pd.notna(lat) and pd.notna(lon):
                    corners.append((float(lon), float(lat)))
            if len(corners) >= 3:
                if corners[0] != corners[-1]:
                    corners.append(corners[0])
                parcels_geoms.append(Polygon(corners))
            else:
                parcels_geoms.append(None)
        
        gdf_p = gpd.GeoDataFrame(df_parcels, geometry=parcels_geoms, crs="EPSG:4326")
        result["Parcels"] = gdf_p.dropna(subset=['geometry'])

    # 3. RoadCenterlines (Geometri: LineString dari point1 s/d point10)
    if "RoadCenterlines" in sheets:
        df_roads = pd.read_excel(xl, "RoadCenterlines")
        road_geoms = []
        for _, row in df_roads.iterrows():
            pts = []
            for i in range(1, 11):
                lat = row.get(f'point{i}_lat')
                lon = row.get(f'point{i}_lon')
                if pd.notna(lat) and pd.notna(lon):
                    pts.append((float(lon), float(lat)))
            road_geoms.append(LineString(pts) if len(pts) >= 2 else None)
        
        gdf_r = gpd.GeoDataFrame(df_roads, geometry=road_geoms, crs="EPSG:4326")
        result["RoadCenterlines"] = gdf_r.dropna(subset=['geometry'])

    # 4. CommunityBoundary (Geometri: Polygon perimeter kawasan)
    if "CommunityBoundary" in sheets:
        df_bound = pd.read_excel(xl, "CommunityBoundary")
        bound_geoms = []
        for _, row in df_bound.iterrows():
            corners = []
            for i in range(1, 9):
                lat = row.get(f'corner{i}_lat')
                lon = row.get(f'corner{i}_lon')
                if pd.notna(lat) and pd.notna(lon):
                    corners.append((float(lon), float(lat)))
            if len(corners) >= 3:
                if corners[0] != corners[-1]:
                    corners.append(corners[0])
                bound_geoms.append(Polygon(corners))
            else:
                bound_geoms.append(None)
        
        gdf_b = gpd.GeoDataFrame(df_bound, geometry=bound_geoms, crs="EPSG:4326")
        result["CommunityBoundary"] = gdf_b.dropna(subset=['geometry'])

    return result