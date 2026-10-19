"""
Universal Geo Reader untuk pipeline spasial GMCP.
Berperan sebagai router tunggal yang mendeteksi format berkas mentah
(berdasarkan ekstensi atau struktur data) dan mendelegasikannya
ke parser modular yang sesuai:
    - .xlsx / .xls -> excel_parser
    - .csv         -> csv_reader
    - .geojson / .json -> geojson_reader
    - .zip         -> zip_reader (deteksi otomatis .shp, .geojson, .csv)
    - .kml / .kmz  -> kml_reader
    - .dxf         -> dxf_reader
    - .gpkg        -> gpkg_reader

Semua delegasi menghasilkan kamus standar 4 layer GMCP ber-CRS EPSG:4326.
"""

import os
import geopandas as gpd

# Impor modular dengan fallback penanganan relatif / absolut
try:
    from src.parsers.excel_parser import parse_excel_gmcp
    from src.parsers.csv_reader import parse_csv_gmcp
    from src.parsers.geojson_reader import parse_geojson_gmcp
    from src.parsers.zip_reader import parse_zip_package
    from src.parsers.kml_reader import parse_kml_gmcp
    from src.parsers.dxf_reader import parse_dxf_gmcp
    from src.parsers.gpkg_reader import parse_gpkg_gmcp
except ImportError:
    from excel_parser import parse_excel_gmcp
    from csv_reader import parse_csv_gmcp
    from geojson_reader import parse_geojson_gmcp
    from zip_reader import parse_zip_package
    from kml_reader import parse_kml_gmcp
    from dxf_reader import parse_dxf_gmcp
    from gpkg_reader import parse_gpkg_gmcp

GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]
TARGET_CRS = "EPSG:4326"


class UniversalGeoReader:
    """Router pembaca geodata universal GMCP."""

    @classmethod
    def empty_layers(cls) -> dict:
        return {
            name: gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS) for name in GMCP_LAYERS
        }

    @classmethod
    def read_any(cls, file_source, filename: str = None) -> dict:
        """
        Mendeteksi ekstensi berkas secara otomatis dan memanggil parser yang tepat.
        Mendukung path berkas lokal (str/Path) maupun file buffer Streamlit (UploadedFile).
        """
        # Deteksi nama berkas
        if filename is None:
            if hasattr(file_source, "name"):
                filename = file_source.name
            elif isinstance(file_source, (str, os.PathLike)):
                filename = os.path.basename(file_source)
            else:
                filename = "dataset.bin"

        ext = os.path.splitext(filename)[1].lower()

        # 1. Excel (.xlsx, .xls)
        if ext in [".xlsx", ".xls"]:
            return parse_excel_gmcp(file_source)

        # 2. GeoJSON (.geojson, .json)
        elif ext in [".geojson", ".json"]:
            return parse_geojson_gmcp(file_source, filename=filename)

        # 3. Smart ZIP Package (.zip)
        elif ext == ".zip":
            return parse_zip_package(file_source, filename=filename)

        # 4. CSV (.csv)
        elif ext == ".csv":
            return parse_csv_gmcp(file_source)

        # 5. KML / KMZ (.kml, .kmz)
        elif ext in [".kml", ".kmz"]:
            return parse_kml_gmcp(file_source, filename=filename)

        # 6. CAD DXF (.dxf)
        elif ext == ".dxf":
            return parse_dxf_gmcp(file_source, filename=filename)

        # 7. OGC GeoPackage (.gpkg)
        elif ext == ".gpkg":
            return parse_gpkg_gmcp(file_source, filename=filename)

        else:
            raise ValueError(f"Ekstensi format geodata belum didukung: {ext}")

    # Aliases helper untuk backward compatibility jika dipanggil langsung
    @classmethod
    def read_excel(cls, file_source):
        return parse_excel_gmcp(file_source)

    @classmethod
    def read_geojson(cls, file_source, filename="data.geojson"):
        return parse_geojson_gmcp(file_source, filename=filename)

    @classmethod
    def read_zip_package(cls, file_source, filename="archive.zip"):
        return parse_zip_package(file_source, filename=filename)

    @classmethod
    def read_csv(cls, file_source):
        return parse_csv_gmcp(file_source)

    @classmethod
    def read_kml(cls, file_source, filename="survey.kml"):
        return parse_kml_gmcp(file_source, filename=filename)

    @classmethod
    def read_dxf(cls, file_source, filename="siteplan.dxf"):
        return parse_dxf_gmcp(file_source, filename=filename)

    @classmethod
    def read_gpkg(cls, file_source, filename="cases.gpkg"):
        return parse_gpkg_gmcp(file_source, filename=filename)