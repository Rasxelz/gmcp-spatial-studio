# SPESIFIKASI TEKNIS: UNIVERSAL SPATIAL INGESTION & GMCP QA/QC ENGINE

## 1. TUJUAN SISTEM
Membangun web-engine produksi berbasis Streamlit yang mampu:
1. Menerima ragam format geodata mentah (.xlsx, .csv, .geojson, .zip Shapefile, .kml, .dxf).
2. Memetakan data ke 4 layer standar Google Maps Content Partners (GMCP) WGS84 (EPSG:4326): AddressPoints, Parcels, RoadCenterlines, CommunityBoundary.
3. Melakukan audit topologi & atribut otomatis terhadap 12 skenario edge cases.
4. Menyediakan antarmuka Dual-Map (Peta Mentah vs Peta Flag Anomali) dengan fitur perbaikan langsung di tempat (In-Place Fixer).
5. Mengekspor bundel resmi ESRI Shapefile suite (.shp, .shx, .dbf, .prj, .cpg) bernama `housing_development.zip` beserta lampiran audit justification.
6. Menyediakan formulir pengajuan mandiri ke tim data (simulasi antrean BigQuery & Cloud Storage).

## 2. STANDAR SKEMA GMCP (EPSG:4326)
- **AddressPoints (Point)**: id, NAME, TYPE, LotNum, ST_NUM, ST_NAME, FULL_AD, CITY, STATE, ZIP, LAT, LONG.
- **Parcels (Polygon)**: id, APN (unik), NAME, LotNum, ST_NUM, ST_NAME, FULL_AD, CITY, STATE, ZIP, TYPE, CATEG.
- **RoadCenterlines (LineString)**: id, ST_NAME, RT_NAME, CITY, ADMIN, POSTAL, SURFACE, SPEED_LM, BIKE, CAR_RESTR, PED_RESTR, DIR, SEPARATE, ELEV.
- **CommunityBoundary (Polygon)**: id, Community, City, State, Country, ZipCode.

## 3. MATRIKS QA/QC FLAG & LOGIKA AUDIT (12 SKENARIO)
- **TC-01 (CRITICAL)**: `OFFSHORE_WATERBODY` -> AddressPoint dengan Longitude < 106.732 (terindikasi di badan air/laut tanpa reklamasi).
- **TC-02 (CRITICAL)**: `MISSING_ST_NUM` / `MISSING_ST_NAME` -> Field wajib nomor atau nama jalan kosong.
- **TC-03 (WARNING)**: `ORPHAN_ADDRESS` -> Titik alamat berada di luar poligon seluruh kavling (Parcels).
- **TC-04 (CRITICAL)**: `DUPLICATE_APN` -> Nomor APN kavling terduplikasi.
- **TC-05 (HIGH)**: `PARCEL_OVERLAP` -> Poligon kavling saling tumpang tindih (`geom.overlaps(other)`).
- **TC-06 (CRITICAL)**: `DEGENERATE_POLYGON` -> Poligon kavling tidak tertutup atau sudut < 3 titik.
- **TC-07 (WARNING)**: `DANGLING_ROAD` -> Ujung jalan menggantung / buntu tanpa terhubung simpul jalan lain.
- **TC-08 (HIGH)**: `ROAD_PARCEL_CONFLICT` -> Garis jalan memotong/menabrak poligon kavling privat (`crosses`).
- **TC-09 (WARNING)**: `MISSING_BIKE_ATTR` -> Atribut navigasi `BIKE` pada jalan kosong.
- **TC-10 (WARNING)**: `OUT_OF_BOUNDS` -> Objek berada di luar perimeter CommunityBoundary.
- **TC-11 (CRITICAL)**: `MISSING_TRANSIT_AGENCY` -> Stasiun transit tanpa atribut AGENCY.
- **TC-12 (CRITICAL)**: `MISSING_BIKE_CATEGORY` -> Fasilitas jalur sepeda tanpa kategori utama.

## 4. ARSITEKTUR KODE MODULAR (SRC/)
1. **`src/parsers/excel_parser.py`**: Parser template Excel GMCP -> Dict[str, GeoDataFrame].
2. **`src/parsers/geojson_reader.py`**: Parser berkas GeoJSON -> Dict[str, GeoDataFrame].
3. **`src/parsers/shapefile_reader.py`**: Ekstraktor & pembaca file .zip Shapefile -> Dict[str, GeoDataFrame].
4. **`src/parsers/csv_reader.py`**: Pembaca multi-CSV GMCP -> Dict[str, GeoDataFrame].
5. **`src/parsers/universal_reader.py`**: Router deteksi format otomatis berdasarkan ekstensi file mentah.
6. **`src/qaqc/validator.py`**: Fungsi `audit_gmcp_layers(layers_dict)` -> Mengembalikan DataFrame berisi seluruh flag anomali.
7. **`src/exporter/packager.py`**: Fungsi `create_shapefile_submission_zip(layers_dict, flags_df)` -> Mengembalikan byte stream `housing_development.zip` (ESRI Shapefile suite lengkap + report CSV).
8. **`app.py`**: UI Streamlit (Dual-Map Folium, Data Editor Interaktif, Dialog Konfirmasi Peringatan, Form Direct Submission).