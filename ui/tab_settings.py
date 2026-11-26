"""
ui/tab_settings.py - Compartiment 5 : Paramètres Système SQL, Exports & Session.
Zéro dépendance à Google Sheets / Google Forms.
"""

from datetime import datetime
import time
import streamlit as st

from core.calibration import export_baselines_json, load_baselines_table
from core.database import (
    get_gemini_api_key,
    get_training_logs_for_athlete,
    logout_user_from_session,
    resolve_database_url,
)
from services.export_service import (
    build_logs_export_dataframe,
    export_dataframe_to_csv_bytes,
    export_workbook_xlsx_bytes,
)
from ui.dashboard_load import compute_longitudinal_metrics
from ui.profile_dialog import open_profile_modal
from ui.theme import render_html


def render_tab_settings() -> None:
    """Rend les réglages système, statut SQL, exports et gestion de session."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    render_html("""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                ⚙️ Paramètres & Sauvegardes SQL
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Stockage autonome SQL (PostgreSQL / SQLite), profil, clé Vision et exports multi-formats.
            </p>
        </div>
    """)

    if st.button("👤 Mon Profil, Statut, PDC & Photo", key="btn_open_profile_settings", type="secondary", use_container_width=True):
        open_profile_modal()

    db_uri = resolve_database_url()
    is_pg = db_uri.startswith("postgresql")
    backend_lbl = "PostgreSQL Cloud (Persistance absolue)" if is_pg else "SQLite Local (data/caliperf.db)"
    backend_badge = "badge-lime" if is_pg else "badge-cyan"

    render_html(f"""
        <div class="cali-card" style="padding: 12px 14px; margin: 0.7rem 0;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <span style="font-size:0.82rem; font-weight:700; color:#F8FAFC;">🗄️ Moteur de Base de Données</span>
                <span class="{backend_badge}">{backend_lbl}</span>
            </div>
        </div>
    """)

    sess_cfg = st.session_state.get("session_settings", {"auto_advance": True})

    with st.form("settings_full_form"):
        st.markdown("##### 🤖 Intelligence Artificielle Vision (Secours optionnel)")
        gem_key_input = st.text_input(
            "Clé API Gemini (Optionnel) :",
            value=get_gemini_api_key(),
            type="password",
            help="Active le bouton de secours Gemini Vision dans le Studio."
        )

        render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.8rem 0;'>")
        st.markdown("##### ⚡ Ergonomie du Studio")
        auto_adv = st.checkbox(
            "Passer automatiquement à la vidéo suivante après validation",
            value=bool(sess_cfg.get("auto_advance", True))
        )

        if st.form_submit_button("💾 Enregistrer la configuration", type="primary", use_container_width=True):
            st.session_state.active_gemini_key = gem_key_input.strip()
            st.session_state.session_settings = {"auto_advance": auto_adv}
            st.toast("✅ Configuration enregistrée !")
            time.sleep(0.25)
            st.rerun()

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 1rem 0;'>")
    st.markdown("##### 📤 Sauvegardes & Exports (CSV / Excel / JSON)")

    active_profile = st.session_state.get("active_athlete_profile") or curr_u
    logs = get_training_logs_for_athlete(curr_u, target_athlete_id=int(active_profile["id"]))
    df_base = load_baselines_table(user=curr_u)
    acwr_metrics = compute_longitudinal_metrics(logs)

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        st.download_button(
            "📄 CSV Séances",
            data=export_dataframe_to_csv_bytes(build_logs_export_dataframe(logs)),
            file_name=f"caliperf_seances_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="settings_dl_csv",
        )
    with col_e2:
        st.download_button(
            "📊 Excel Complet (.xlsx)",
            data=export_workbook_xlsx_bytes(logs, acwr_metrics["daily_df"], df_base),
            file_name=f"caliperf_complet_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="settings_dl_xlsx",
        )
    with col_e3:
        st.download_button(
            "📦 JSON Calibrations",
            data=export_baselines_json(user=curr_u).encode("utf-8"),
            file_name=f"baselines_3d_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
            key="settings_dl_json",
        )

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 1rem 0;'>")
    st.markdown("##### 🔐 Session & Compte")
    if st.button("🔄 Se déconnecter / Changer de compte", key="btn_logout_settings", use_container_width=True):
        logout_user_from_session(stay_on_auth_portal=True)
        st.rerun()
