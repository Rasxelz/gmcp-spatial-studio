"""
Modul pengemasan (packaging) submission GMCP.

Menyediakan :func:`create_shapefile_submission_zip` yang menyusun berkas
``housing_development.zip`` berisi suite ESRI Shapefile lengkap
(.shp/.shx/.dbf/.prj/.cpg) untuk setiap lapisan GMCP yang tidak kosong, plus
lampiran ``GMCP_AUDIT_REPORT.csv`` bila terdapat flag audit.

Logika mencerminkan helper inline ``build_shapefile_zip`` di app.py: menulis
setiap GeoDataFrame via ``to_file(driver='ESRI Shapefile')`` (pyogrio sebagai
mesin IO sehingga suite lengkap tetap dihasilkan meski fiona tidak terpasang),
lalu mengemas seluruh berkas dengan nama datar (basename) ke dalam satu arsip
ZIP. Direktori sementara dibersihkan otomatis sehingga tidak meninggalkan
berkas residu.
"""

import os
import io
import zipfile
import tempfile

import pandas as pd

# Empat lapisan kanonik GMCP (urutan tetap).
GMCP_LAYERS = ["AddressPoints", "Parcels", "RoadCenterlines", "CommunityBoundary"]


def create_shapefile_submission_zip(layers_dict, flags_df) -> bytes:
    """
    Menyusun arsip ZIP submission GMCP sebagai bytes.

    Parameters
    ----------
    layers_dict : dict
        Kamus lapisan GMCP (kunci kanonik -> GeoDataFrame EPSG:4326). Boleh
        kosong atau parsial; hanya lapisan yang ada dan tidak kosong yang
        ditulis sebagai Shapefile.
    flags_df : pandas.DataFrame or None
        DataFrame flag audit QA/QC. Bila ``None`` atau kosong, lampiran
        ``GMCP_AUDIT_REPORT.csv`` tidak disertakan.

    Returns
    -------
    bytes
        Isi arsip ZIP. Berisi suite Shapefile lengkap per lapisan tidak kosong
        dengan nama berkas datar (tanpa prefix direktori sementara), plus
        ``GMCP_AUDIT_REPORT.csv`` bila ada flag.
    """
    buf = io.BytesIO()
    layers_dict = layers_dict or {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for layer in GMCP_LAYERS:
            gdf = layers_dict.get(layer)
            if gdf is None or len(gdf) == 0:
                continue
            out_shp = os.path.join(tmp_dir, f"{layer}.shp")
            gdf.to_file(out_shp, driver="ESRI Shapefile", encoding="utf-8")

        if flags_df is not None and not flags_df.empty:
            flags_df.to_csv(os.path.join(tmp_dir, "GMCP_AUDIT_REPORT.csv"), index=False)

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root_dir, _, files in os.walk(tmp_dir):
                for file in files:
                    zf.write(os.path.join(root_dir, file), arcname=file)

    return buf.getvalue()
