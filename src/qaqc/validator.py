"""
Modul audit QA/QC spasial GMCP.

Menyediakan :func:`audit_gmcp_layers` yang menerima kamus GeoDataFrame standar
GMCP (AddressPoints, Parcels, RoadCenterlines, CommunityBoundary ber-CRS
EPSG:4326) dan mengembalikan satu pandas.DataFrame berisi seluruh flag anomali
sesuai 12 skenario audit (TC-01..TC-12) di Bab 3 SPEC_FINAL.md.

Setiap baris flag memiliki kolom persis:

    ['Layer', 'ID', 'Type', 'Severity', 'Lat', 'Lon', 'Deskripsi', 'Solusi']

Interpretasi TC-11 & TC-12
--------------------------
Skema GMCP hanya memiliki empat lapisan kanonik dan TIDAK memiliki lapisan
khusus transit maupun fasilitas jalur sepeda. Karena itu:

- **TC-11 (MISSING_TRANSIT_AGENCY)** diterapkan pada baris AddressPoints yang
  kolom ``TYPE``-nya (huruf kecil) mengandung 'transit'/'station'/'stasiun'
  namun tidak memiliki nilai pada atribut ``AGENCY``. Bila kolom ``TYPE`` atau
  ``AGENCY`` tidak ada, aturan ini tidak menghasilkan flag apa pun.
- **TC-12 (MISSING_BIKE_CATEGORY)** diterapkan pada fitur fasilitas jalur
  sepeda (baris Parcels/AddressPoints yang kolom ``TYPE``-nya mengandung
  'bike'/'bicycle'/'sepeda') yang tidak memiliki kategori utama pada field
  ``CATEG``/``category``. Bila kolom/jenis fitur terkait tidak ada, aturan ini
  tidak menghasilkan flag apa pun.

Pada data sintetis (synthetic_test_cases.xlsx) kedua aturan ini menghasilkan
NOL flag karena sheet Transit & BicycleFacilities bukan bagian dari 4 lapisan
GMCP yang dibaca parser.
"""

import math

import pandas as pd
import geopandas as gpd

# Kolom keluaran DataFrame flag (urutan tetap).
FLAG_COLUMNS = ["Layer", "ID", "Type", "Severity", "Lat", "Lon", "Deskripsi", "Solusi"]

# Ambang batas longitude daratan (dari app.py / SPEC Bab 3 TC-01).
OFFSHORE_LON_THRESHOLD = 106.732

# Toleransi pembulatan koordinat ujung jalan (TC-07).
_ENDPOINT_ROUND = 7


# ---------------------------------------------------------------------------
# Helper internal
# ---------------------------------------------------------------------------
def _is_blank(value) -> bool:
    """True bila nilai atribut dianggap kosong (NaN/''/'nan'/'none')."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    return text in ("", "nan", "none")


def _rep_point(geom):
    """
    Titik representatif (Lat, Lon) untuk sebuah geometri.

    Point -> (y, x); Line/Polygon -> centroid.y/x. Mengembalikan (None, None)
    bila geometri kosong/tidak valid.
    """
    if geom is None:
        return None, None
    try:
        if geom.is_empty:
            return None, None
    except Exception:
        return None, None
    try:
        if geom.geom_type == "Point":
            return geom.y, geom.x
        c = geom.centroid
        return c.y, c.x
    except Exception:
        return None, None


def _get_layer(layers_dict, name):
    """Ambil lapisan bernama ``name`` bila ada isinya, selain itu None."""
    if not layers_dict:
        return None
    gdf = layers_dict.get(name)
    if gdf is None or len(gdf) == 0:
        return None
    return gdf


def _row_id(row, idx, prefix):
    """ID baris: pakai kolom 'id' bila ada, selain itu '<prefix>_<idx>'."""
    val = row.get("id") if hasattr(row, "get") else None
    if _is_blank(val):
        return f"{prefix}_{idx}"
    return str(val)


def _union(gdf):
    """Union geometri dengan union_all() (fallback unary_union)."""
    if gdf is None or len(gdf) == 0:
        return None
    try:
        return gdf.geometry.union_all()
    except AttributeError:
        return gdf.geometry.unary_union


class _Flags:
    """Akumulator flag anomali."""

    def __init__(self):
        self._rows = []

    def add(self, layer, _id, _type, severity, geom, deskripsi, solusi, lat=None, lon=None):
        if lat is None or lon is None:
            lat, lon = _rep_point(geom)
        self._rows.append(
            {
                "Layer": layer,
                "ID": _id,
                "Type": _type,
                "Severity": severity,
                "Lat": lat,
                "Lon": lon,
                "Deskripsi": deskripsi,
                "Solusi": solusi,
            }
        )

    def to_frame(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame(columns=FLAG_COLUMNS)
        return pd.DataFrame(self._rows, columns=FLAG_COLUMNS)


# ---------------------------------------------------------------------------
# Aturan audit TC-01 .. TC-12
# ---------------------------------------------------------------------------
def _tc01_offshore(flags, addr, offshore_ids):
    """TC-01 OFFSHORE_WATERBODY (CRITICAL) pada AddressPoints."""
    if addr is None:
        return
    for idx, row in addr.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt_id = _row_id(row, idx, "AP")
        if geom.x < OFFSHORE_LON_THRESHOLD:
            offshore_ids.add(idx)
            flags.add(
                "AddressPoints", pt_id, "OFFSHORE_WATERBODY", "CRITICAL", geom,
                "Posisi titik di atas air/laut tanpa verifikasi daratan.",
                "Perbarui koordinat atau sertakan justifikasi reklamasi.",
            )


def _tc02_missing_street(flags, addr):
    """TC-02 MISSING_ST_NUM / MISSING_ST_NAME (CRITICAL) pada AddressPoints."""
    if addr is None:
        return
    has_num = "ST_NUM" in addr.columns
    has_name = "ST_NAME" in addr.columns
    for idx, row in addr.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt_id = _row_id(row, idx, "AP")
        if has_num and _is_blank(row.get("ST_NUM")):
            flags.add(
                "AddressPoints", pt_id, "MISSING_ST_NUM", "CRITICAL", geom,
                "Atribut wajib ST_NUM tidak terisi.",
                "Lengkapi nomor jalan di tabel Data AddressPoints.",
            )
        if has_name and _is_blank(row.get("ST_NAME")):
            flags.add(
                "AddressPoints", pt_id, "MISSING_ST_NAME", "CRITICAL", geom,
                "Atribut wajib ST_NAME tidak terisi.",
                "Lengkapi nama jalan di tabel Data AddressPoints.",
            )


def _tc03_orphan(flags, addr, parcels, offshore_ids):
    """TC-03 ORPHAN_ADDRESS (WARNING) pada AddressPoints vs union Parcels."""
    if addr is None:
        return
    union = _union(parcels)
    if union is None:
        return
    for idx, row in addr.iterrows():
        # Mirror app.py: hanya dievaluasi bila titik belum tertandai offshore.
        if idx in offshore_ids:
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt_id = _row_id(row, idx, "AP")
        if not union.contains(geom):
            flags.add(
                "AddressPoints", pt_id, "ORPHAN_ADDRESS", "WARNING", geom,
                "Titik alamat di luar poligon kavling.",
                "Pindahkan ke kavling atau biarkan jika fasilitas umum.",
            )


def _tc04_duplicate_apn(flags, parcels):
    """TC-04 DUPLICATE_APN (CRITICAL) pada Parcels."""
    if parcels is None or "APN" not in parcels.columns:
        return
    apn = parcels["APN"]
    dup_mask = apn.duplicated(keep=False) & apn.notna()
    for idx, row in parcels.iterrows():
        if not dup_mask.get(idx, False):
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        p_id = _row_id(row, idx, "P")
        flags.add(
            "Parcels", p_id, "DUPLICATE_APN", "CRITICAL", geom,
            f"Nomor APN '{row.get('APN')}' terduplikasi antar kavling.",
            "Pastikan setiap kavling memiliki APN yang unik.",
        )


def _tc05_overlap(flags, parcels):
    """TC-05 PARCEL_OVERLAP (HIGH) pada pasangan Parcels yang tumpang tindih."""
    if parcels is None:
        return
    rows = list(parcels.iterrows())
    flagged_ids = set()
    for a in range(len(rows)):
        idx_a, row_a = rows[a]
        geom_a = row_a.geometry
        if geom_a is None or geom_a.is_empty:
            continue
        for b in range(a + 1, len(rows)):
            idx_b, row_b = rows[b]
            geom_b = row_b.geometry
            if geom_b is None or geom_b.is_empty:
                continue
            try:
                if geom_a.overlaps(geom_b):
                    for idx, row, geom in ((idx_a, row_a, geom_a), (idx_b, row_b, geom_b)):
                        if idx in flagged_ids:
                            continue
                        flagged_ids.add(idx)
                        flags.add(
                            "Parcels", _row_id(row, idx, "P"), "PARCEL_OVERLAP", "HIGH", geom,
                            "Poligon kavling saling tumpang tindih dengan kavling lain.",
                            "Perbaiki batas kavling agar tidak beririsan.",
                        )
            except Exception:
                continue


def _is_degenerate(geom) -> bool:
    """True bila poligon None/kosong/tak valid/tak tertutup/<3 titik unik."""
    if geom is None:
        return True
    try:
        if geom.is_empty or not geom.is_valid:
            return True
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            return True
        if geom.geom_type == "MultiPolygon":
            return any(_is_degenerate(g) for g in geom.geoms)
        coords = list(geom.exterior.coords)
        if len(coords) < 4:  # minimal 3 titik + penutup
            return True
        if coords[0] != coords[-1]:
            return True
        distinct = set(coords[:-1])
        return len(distinct) < 3
    except Exception:
        return True


def _tc06_degenerate(flags, parcels):
    """
    TC-06 DEGENERATE_POLYGON (CRITICAL) pada Parcels.

    Catatan: parser hulu memanggil ``dropna(subset=['geometry'])`` sehingga
    kavling degenerate (mis. < 3 sudut) umumnya sudah dibuang sebelum tiba di
    sini. Aturan ini tetap menandai poligon tak valid/tak tertutup yang lolos,
    dan mengandalkan penyaringan hulu untuk kasus geometri None.
    """
    if parcels is None:
        return
    for idx, row in parcels.iterrows():
        geom = row.geometry
        if not _is_degenerate(geom):
            continue
        # Lewati geometri None/kosong (tidak ada titik representatif).
        if geom is None or getattr(geom, "is_empty", True):
            continue
        p_id = _row_id(row, idx, "P")
        flags.add(
            "Parcels", p_id, "DEGENERATE_POLYGON", "CRITICAL", geom,
            "Poligon kavling tidak tertutup atau memiliki sudut < 3 titik.",
            "Perbaiki rangkaian sudut kavling agar membentuk poligon tertutup yang sah.",
        )


def _endpoints(geom):
    """Koordinat ujung awal & akhir (dibulatkan) dari sebuah LineString."""
    try:
        coords = list(geom.coords)
    except Exception:
        return None
    if len(coords) < 2:
        return None
    start = (round(coords[0][0], _ENDPOINT_ROUND), round(coords[0][1], _ENDPOINT_ROUND))
    end = (round(coords[-1][0], _ENDPOINT_ROUND), round(coords[-1][1], _ENDPOINT_ROUND))
    return start, end


def _tc07_dangling(flags, roads):
    """TC-07 DANGLING_ROAD (WARNING) pada RoadCenterlines."""
    if roads is None:
        return
    # Hitung frekuensi setiap koordinat ujung di seluruh jaringan jalan.
    counts = {}
    cache = {}
    for idx, row in roads.iterrows():
        ep = _endpoints(row.geometry)
        if ep is None:
            continue
        cache[idx] = ep
        for coord in ep:
            counts[coord] = counts.get(coord, 0) + 1
    for idx, row in roads.iterrows():
        ep = cache.get(idx)
        if ep is None:
            continue
        start, end = ep
        # Ujung menggantung bila tidak dibagi dengan ujung jalan lain.
        if counts.get(start, 0) <= 1 or counts.get(end, 0) <= 1:
            geom = row.geometry
            r_id = _row_id(row, idx, "Road")
            flags.add(
                "RoadCenterlines", r_id, "DANGLING_ROAD", "WARNING", geom,
                "Ujung jalan menggantung/buntu tanpa terhubung ke simpul jalan lain.",
                "Sambungkan ujung jalan ke jaringan atau tandai sebagai jalan buntu yang sah.",
            )


def _tc08_road_parcel_conflict(flags, roads, parcels):
    """TC-08 ROAD_PARCEL_CONFLICT (HIGH): road.crosses(parcel)."""
    if roads is None or parcels is None:
        return
    for r_idx, r_row in roads.iterrows():
        r_geom = r_row.geometry
        if r_geom is None or r_geom.is_empty:
            continue
        r_id = _row_id(r_row, r_idx, "Road")
        for p_idx, p_row in parcels.iterrows():
            p_geom = p_row.geometry
            if p_geom is None or p_geom.is_empty:
                continue
            try:
                if r_geom.crosses(p_geom):
                    p_id = p_row.get("id") if not _is_blank(p_row.get("id")) else p_idx
                    flags.add(
                        "RoadCenterlines", f"{r_id} vs {p_id}",
                        "ROAD_PARCEL_CONFLICT", "HIGH", r_geom,
                        "Garis jalan menembus kavling privat.",
                        "Periksa batas ROW jalan atau tandai sebagai kavling bersama.",
                    )
            except Exception:
                continue


def _tc09_missing_bike(flags, roads):
    """TC-09 MISSING_BIKE_ATTR (WARNING) pada RoadCenterlines."""
    if roads is None or "BIKE" not in roads.columns:
        return
    for idx, row in roads.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if _is_blank(row.get("BIKE")):
            r_id = _row_id(row, idx, "Road")
            flags.add(
                "RoadCenterlines", r_id, "MISSING_BIKE_ATTR", "WARNING", geom,
                "Field wajib BIKE kosong.",
                "Isi dengan 'Non-applicable' atau kategori jalur sepeda.",
            )


def _tc10_out_of_bounds(flags, addr, boundary):
    """TC-10 OUT_OF_BOUNDS (WARNING): AddressPoints di luar CommunityBoundary."""
    if addr is None:
        return
    union = _union(boundary)
    if union is None:
        return
    for idx, row in addr.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt_id = _row_id(row, idx, "AP")
        try:
            inside = union.contains(geom) or union.intersects(geom)
        except Exception:
            continue
        if not inside:
            flags.add(
                "AddressPoints", pt_id, "OUT_OF_BOUNDS", "WARNING", geom,
                "Objek berada di luar perimeter CommunityBoundary.",
                "Periksa posisi objek atau perluas batas komunitas bila perlu.",
            )


def _tc11_missing_transit_agency(flags, addr):
    """TC-11 MISSING_TRANSIT_AGENCY (CRITICAL) pada AddressPoints transit."""
    if addr is None or "TYPE" not in addr.columns or "AGENCY" not in addr.columns:
        return
    for idx, row in addr.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        type_val = str(row.get("TYPE") or "").lower()
        if not any(k in type_val for k in ("transit", "station", "stasiun")):
            continue
        if _is_blank(row.get("AGENCY")):
            pt_id = _row_id(row, idx, "AP")
            flags.add(
                "AddressPoints", pt_id, "MISSING_TRANSIT_AGENCY", "CRITICAL", geom,
                "Stasiun transit tanpa atribut AGENCY.",
                "Lengkapi nama operator/agensi transit pada atribut AGENCY.",
            )


def _tc12_missing_bike_category(flags, layers_dict):
    """TC-12 MISSING_BIKE_CATEGORY (CRITICAL) pada fitur fasilitas sepeda."""
    for layer_name in ("AddressPoints", "Parcels"):
        gdf = _get_layer(layers_dict, layer_name)
        if gdf is None or "TYPE" not in gdf.columns:
            continue
        categ_col = None
        for cand in ("CATEG", "category", "CATEGORY"):
            if cand in gdf.columns:
                categ_col = cand
                break
        if categ_col is None:
            continue
        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            type_val = str(row.get("TYPE") or "").lower()
            if not any(k in type_val for k in ("bike", "bicycle", "sepeda")):
                continue
            if _is_blank(row.get(categ_col)):
                f_id = _row_id(row, idx, layer_name[:2].upper())
                flags.add(
                    layer_name, f_id, "MISSING_BIKE_CATEGORY", "CRITICAL", geom,
                    "Fasilitas jalur sepeda tanpa kategori utama.",
                    f"Lengkapi kategori utama fasilitas pada field {categ_col}.",
                )


# ---------------------------------------------------------------------------
# API utama
# ---------------------------------------------------------------------------
def audit_gmcp_layers(layers_dict) -> pd.DataFrame:
    """
    Menjalankan seluruh 12 aturan audit QA/QC GMCP atas ``layers_dict``.

    Parameters
    ----------
    layers_dict : dict
        Kamus lapisan GMCP (kunci kanonik -> GeoDataFrame EPSG:4326). Boleh
        kosong atau parsial; aturan menjadi no-op untuk lapisan yang hilang/
        kosong atau kolom yang tidak tersedia.

    Returns
    -------
    pandas.DataFrame
        Satu baris per flag anomali dengan kolom persis:
        ['Layer', 'ID', 'Type', 'Severity', 'Lat', 'Lon', 'Deskripsi', 'Solusi'].
        DataFrame kosong (dengan kolom yang sama) bila tidak ada flag.
    """
    flags = _Flags()
    if not layers_dict:
        return flags.to_frame()

    addr = _get_layer(layers_dict, "AddressPoints")
    parcels = _get_layer(layers_dict, "Parcels")
    roads = _get_layer(layers_dict, "RoadCenterlines")
    boundary = _get_layer(layers_dict, "CommunityBoundary")

    offshore_ids = set()

    # AddressPoints
    _tc01_offshore(flags, addr, offshore_ids)
    _tc02_missing_street(flags, addr)
    _tc03_orphan(flags, addr, parcels, offshore_ids)

    # Parcels
    _tc04_duplicate_apn(flags, parcels)
    _tc05_overlap(flags, parcels)
    _tc06_degenerate(flags, parcels)

    # RoadCenterlines
    _tc07_dangling(flags, roads)
    _tc08_road_parcel_conflict(flags, roads, parcels)
    _tc09_missing_bike(flags, roads)

    # Boundary & fitur khusus
    _tc10_out_of_bounds(flags, addr, boundary)
    _tc11_missing_transit_agency(flags, addr)
    _tc12_missing_bike_category(flags, layers_dict)

    return flags.to_frame()
