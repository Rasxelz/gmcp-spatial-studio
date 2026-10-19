import os
import sys
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium

# Pastikan root direktori dikenali Python
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.parsers.universal_reader import UniversalGeoReader
from src.qaqc.validator import audit_gmcp_layers
from src.exporter.packager import create_shapefile_submission_zip

st.set_page_config(
    layout="wide",
    page_title="GMCP Spatial Studio | Ingestion & QA/QC Engine",
    page_icon="🗺️"
)

# ---------------------------------------------------------
# Custom Styling: Modern & Clean Dashboard
# ---------------------------------------------------------
st.markdown("""
<style>
    .main {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Branding Header */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 2px;
    }
    .brand-title {
        font-size: 1.62rem;
        font-weight: 700;
        margin: 0;
        line-height: 1.2;
    }

    /* Scorecard KPI Containers */
    .stat-card {
        background-color: var(--background-color, #ffffff);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .stat-card:hover {
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
    }
    
    .card-total { border-left: 5px solid #2563eb; }
    .card-critical { border-left: 5px solid #dc2626; }
    .card-high { border-left: 5px solid #ea580c; }
    .card-warning { border-left: 5px solid #d97706; }

    .card-title {
        color: #64748b;
        font-size: 0.80rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 4px;
    }
    .card-value {
        font-size: 1.85rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .card-subtext {
        font-size: 0.78rem;
        color: #94a3b8;
        margin-top: 6px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Manajemen State Sesi & Reset Bersih
# ---------------------------------------------------------
if "uploader_key_id" not in st.session_state:
    st.session_state.uploader_key_id = 0
if "loaded_file_name" not in st.session_state:
    st.session_state.loaded_file_name = None
if "layers" not in st.session_state:
    st.session_state.layers = None
if "flags_df" not in st.session_state:
    st.session_state.flags_df = pd.DataFrame()
if "download_finished" not in st.session_state:
    st.session_state.download_finished = False

def reset_workspace():
    """Membersihkan seluruh memori sesi & mereset fisik widget uploader."""
    st.session_state.loaded_file_name = None
    st.session_state.layers = None
    st.session_state.flags_df = pd.DataFrame()
    st.session_state.download_finished = False
    st.session_state.uploader_key_id += 1
    st.rerun()

# ---------------------------------------------------------
# Header Aplikasi
# ---------------------------------------------------------
st.markdown("""
<div class="brand-container">
    <span style="font-size: 2.2rem;">🗺️</span>
    <span class="brand-title">GMCP Spatial Ingestion & QA/QC Studio</span>
</div>
""", unsafe_allow_html=True)
st.caption("Engine Audit Kepatuhan Topologi & Standardisasi Paket Geodata Google Maps Content Partners (GMCP)")
st.divider()

# ---------------------------------------------------------
# Uploader Geodata Mandiri (Multi-Format)
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "Unggah Berkas Geodata Mentah (Multi-Format):",
    type=["xlsx", "xls", "geojson", "json", "zip", "gpkg", "kml", "kmz", "dxf", "csv"],
    key=f"spatial_file_uploader_{st.session_state.uploader_key_id}",
    help="Mendukung Tier 1 (Excel, CSV, GeoJSON, Shapefile ZIP), Tier 2 (KML/KMZ, CAD DXF), dan Tier 3 (OGC GeoPackage)."
)

if uploaded_file is None and st.session_state.loaded_file_name is not None:
    reset_workspace()

if uploaded_file and st.session_state.loaded_file_name != uploaded_file.name:
    with st.spinner(f"Memproses & memetakan struktur spasial {uploaded_file.name}..."):
        try:
            parsed_layers = UniversalGeoReader.read_any(uploaded_file, uploaded_file.name)
            flags = audit_gmcp_layers(parsed_layers)
            
            st.session_state.layers = parsed_layers
            st.session_state.flags_df = flags
            st.session_state.loaded_file_name = uploaded_file.name
            st.session_state.download_finished = False
            st.rerun()
        except Exception as e:
            st.error(f"Gagal memproses berkas: {e}")

# Notifikasi Berhasil Memuat Dataset
if st.session_state.loaded_file_name and st.session_state.layers is not None:
    ext_detected = os.path.splitext(st.session_state.loaded_file_name)[1].upper().replace(".", "")
    total_fitur = sum(len(gdf) for gdf in st.session_state.layers.values())
    
    st.success(
        f"✅ **Dataset Siap:** `{st.session_state.loaded_file_name}` | "
        f"**Format:** `.{ext_detected}` | "
        f"**Objek Terpetakan:** `{total_fitur:,} fitur terurai ke 4 layer kanonik`"
    )

# Render Dasbor Utama
if st.session_state.layers is not None:
    layers = st.session_state.layers
    flags_df = st.session_state.flags_df
    file_key = str(st.session_state.loaded_file_name)

    gdf_addr = layers.get("AddressPoints", gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))
    gdf_parcels = layers.get("Parcels", gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))
    gdf_roads = layers.get("RoadCenterlines", gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))
    gdf_bound = layers.get("CommunityBoundary", gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))

    # Hitung titik tengah peta
    center_y, center_x = -6.0825, 106.7340
    if len(gdf_addr) > 0 and 'geometry' in gdf_addr and not gdf_addr.geometry.is_empty.all():
        center_y = float(gdf_addr.geometry.y.mean())
        center_x = float(gdf_addr.geometry.x.mean())
    elif len(gdf_parcels) > 0 and 'geometry' in gdf_parcels and not gdf_parcels.geometry.is_empty.all():
        center_y = float(gdf_parcels.geometry.centroid.y.mean())
        center_x = float(gdf_parcels.geometry.centroid.x.mean())

    # -----------------------------------------------------
    # Dual-Map View (Bebas Lag & Ringan)
    # -----------------------------------------------------
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown("##### 🗺️ Map 1: Geodata Asli")
        m1 = folium.Map(location=[center_y, center_x], zoom_start=15, tiles="OpenStreetMap")
        if len(gdf_bound) > 0:
            folium.GeoJson(gdf_bound, style_function=lambda x: {'color': '#2563eb', 'fillOpacity': 0.05, 'weight': 2}).add_to(m1)
        if len(gdf_parcels) > 0:
            folium.GeoJson(gdf_parcels, style_function=lambda x: {'color': '#f97316', 'fillOpacity': 0.35, 'weight': 1.5}).add_to(m1)
        if len(gdf_roads) > 0:
            folium.GeoJson(gdf_roads, style_function=lambda x: {'color': '#0f172a', 'weight': 3}).add_to(m1)
        if len(gdf_addr) > 0:
            folium.GeoJson(gdf_addr, marker=folium.CircleMarker(radius=4, color='#1d4ed8', fill=True, fill_color='#2563eb')).add_to(m1)
        
        st_folium(m1, width="100%", height=380, returned_objects=[], key=f"raw_map_{file_key}")

    with m_col2:
        st.markdown("##### ⚠️ Map 2: QA/QC Flag Map")
        m2 = folium.Map(location=[center_y, center_x], zoom_start=15, tiles="OpenStreetMap")
        
        if len(gdf_parcels) > 0:
            folium.GeoJson(gdf_parcels, style_function=lambda x: {'color': '#94a3b8', 'fillOpacity': 0.15, 'weight': 1}).add_to(m2)
        if len(gdf_roads) > 0:
            folium.GeoJson(gdf_roads, style_function=lambda x: {'color': '#64748b', 'weight': 1.5}).add_to(m2)
        
        if not flags_df.empty:
            for _, flg in flags_df.iterrows():
                lat_val, lon_val = flg.get('Lat'), flg.get('Lon')
                if pd.notna(lat_val) and pd.notna(lon_val):
                    marker_color = "red" if flg['Severity'] == "CRITICAL" else ("orange" if flg['Severity'] == "HIGH" else "blue")
                    folium.Marker(
                        location=[float(lat_val), float(lon_val)],
                        popup=folium.Popup(f"<b>[{flg['Severity']}] {flg['Type']}</b><br>{flg['Deskripsi']}<br><i>Solusi: {flg.get('Solusi', '-')}</i>", max_width=250),
                        tooltip=f"{flg['Type']} ({flg['Severity']})",
                        icon=folium.Icon(color=marker_color, icon="exclamation-sign")
                    ).add_to(m2)

        st_folium(m2, width="100%", height=380, returned_objects=[], key=f"flag_map_{file_key}")

    # -----------------------------------------------------
    # Scorecard Dashboard
    # -----------------------------------------------------
    st.write("")
    st.markdown("##### 📊 Ringkasan Temuan Audit GMCP")

    crit_count = int((flags_df["Severity"] == "CRITICAL").sum()) if not flags_df.empty else 0
    high_count = int((flags_df["Severity"] == "HIGH").sum()) if not flags_df.empty else 0
    warn_count = int((flags_df["Severity"] == "WARNING").sum()) if not flags_df.empty else 0
    total_count = len(flags_df)

    sc1, sc2, sc3, sc4 = st.columns(4)
    
    with sc1:
        st.markdown(f"""
        <div class="stat-card card-total">
            <div class="card-title">Total Catatan</div>
            <div class="card-value" style="color: #2563eb;">{total_count}</div>
            <div class="card-subtext">Seluruh anomali terdeteksi</div>
        </div>
        """, unsafe_allow_html=True)

    with sc2:
        val_col = "#dc2626" if crit_count > 0 else "#16a34a"
        sub_txt = "Blokir ekspor Google Maps" if crit_count > 0 else "Nol isu kritis (Lolos)"
        st.markdown(f"""
        <div class="stat-card card-critical">
            <div class="card-title">Critical Issue</div>
            <div class="card-value" style="color: {val_col};">{crit_count}</div>
            <div class="card-subtext">{sub_txt}</div>
        </div>
        """, unsafe_allow_html=True)

    with sc3:
        val_col = "#ea580c" if high_count > 0 else "#64748b"
        sub_txt = "Potensi konflik topologi" if high_count > 0 else "Struktur topologi valid"
        st.markdown(f"""
        <div class="stat-card card-high">
            <div class="card-title">High Severity</div>
            <div class="card-value" style="color: {val_col};">{high_count}</div>
            <div class="card-subtext">{sub_txt}</div>
        </div>
        """, unsafe_allow_html=True)

    with sc4:
        st.markdown(f"""
        <div class="stat-card card-warning">
            <div class="card-title">Warning / Info</div>
            <div class="card-value" style="color: #d97706;">{warn_count}</div>
            <div class="card-subtext">Rekomendasi atribut navigasi</div>
        </div>
        """, unsafe_allow_html=True)

    # -----------------------------------------------------
    # Panel Perbaikan Data In-Place & Tabel Flag
    # -----------------------------------------------------
    st.write("")
    st.divider()
    st.subheader("🛠️ Panel Perbaikan Data In-Place")
    
    tab_ap, tab_rd, tab_fl = st.tabs(["📝 AddressPoints", "🛣️ RoadCenterlines", "📋 Daftar Detail Flag QA/QC"])
    
    with tab_ap:
        df_addr_raw = pd.DataFrame(gdf_addr.drop(columns=['geometry'], errors='ignore'))
        edited_ap = st.data_editor(df_addr_raw, use_container_width=True, num_rows="dynamic", key=f"ed_ap_{file_key}")

    with tab_rd:
        df_roads_raw = pd.DataFrame(gdf_roads.drop(columns=['geometry'], errors='ignore'))
        edited_rd = st.data_editor(df_roads_raw, use_container_width=True, num_rows="dynamic", key=f"ed_rd_{file_key}")

    with tab_fl:
        if not flags_df.empty:
            st.dataframe(flags_df, use_container_width=True, height=280)
        else:
            st.success("🎉 Tidak ditemukan anomali atau kesalahan spasial pada dataset.")

    # -----------------------------------------------------
    # Modal Dialog Konfirmasi Ekspor
    # -----------------------------------------------------
    @st.dialog("⚠️ Konfirmasi Ekspor GMCP Package")
    def confirm_export_dialog():
        if not st.session_state.download_finished:
            st.write(f"Sistem mendeteksi **{total_count} catatan anomali** (termasuk **{crit_count} Critical Issue**).")
            st.info("Format Shapefile suite tetap dapat diunduh lengkap beserta lampiran audit resmi `GMCP_AUDIT_REPORT.csv`.")
            zip_bytes = create_shapefile_submission_zip(layers, flags_df)
            
            def mark_download_complete():
                st.session_state.download_finished = True

            st.download_button(
                label="✅ Lanjutkan & Unduh housing_development.zip",
                data=zip_bytes,
                file_name="housing_development.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
                on_click=mark_download_complete
            )
        else:
            st.success("🎉 **Konversi Selesai!** Berkas `housing_development.zip` siap digunakan.")
            st.caption("Klik tombol di bawah untuk membersihkan ruang kerja dan menyiapkan pengunggahan dataset baru.")
            if st.button("🔄 Selesai & Reset ke Tampilan Awal", type="primary", use_container_width=True):
                reset_workspace()

    # Tombol Aksi Bawah
    col_act1, col_act2 = st.columns([1, 2])
    with col_act1:
        if st.button("🔄 Terapkan Perbaikan & Re-run Audit", type="primary", use_container_width=True):
            for col in edited_ap.columns:
                gdf_addr[col] = edited_ap[col]
            for col in edited_rd.columns:
                gdf_roads[col] = edited_rd[col]
            
            layers["AddressPoints"] = gdf_addr
            layers["RoadCenterlines"] = gdf_roads
            st.session_state.layers = layers
            st.session_state.flags_df = audit_gmcp_layers(layers)
            st.rerun()

    with col_act2:
        if st.button("📦 Convert & Download GMCP Package (.zip)", use_container_width=True):
            confirm_export_dialog()