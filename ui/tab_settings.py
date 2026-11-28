"""
ui/tab_settings.py - Compartiment 5 : Paramètres Système SQL, Exports & Session.
Zéro dépendance à Google Sheets / Google Forms.
"""

from datetime import datetime
import time
import streamlit as st

from core.auth import normalize_role
from core.calibration import export_baselines_json, load_baselines_table
from core.database import (
    get_gemini_api_key,
    get_training_logs_for_athlete,
    logout_user_from_session,
    purge_demo_athletes_for_coach,
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
        <div style="margin-bottom: 0.75rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                Paramètres & Sauvegardes
            </h3>
            <p style="margin:3px 0 0 0; font-size:0.82rem; color:#94A3B8;">
                Profil, réglages du Studio, exports et gestion de votre compte.
            </p>
        </div>
    """)

    if st.button("Mon profil, poids et photo", key="btn_open_profile_settings", type="secondary", use_container_width=True):
        open_profile_modal()

    if normalize_role(curr_u.get("role", "")) == "coach":
        render_html("<div style='height:8px;'></div>")
        with st.expander("Maintenance : Élèves de démonstration", expanded=False):
            st.caption("Supprime uniquement les profils de démonstration et leurs séances, sans toucher à vos vrais élèves ni à vos figures de référence.")
            confirm_purge = st.checkbox("Confirmer la suppression des élèves de démo", key="chk_confirm_purge_demo")
            if st.button(
                "Supprimer les élèves de démo",
                key="btn_purge_demo_athletes",
                type="secondary",
                use_container_width=True,
                disabled=not confirm_purge,
            ):
                ok_p, msg_p, _ = purge_demo_athletes_for_coach(int(curr_u["id"]))
                if ok_p:
                    st.session_state["active_athlete_id"] = int(curr_u["id"])
                    st.session_state["selected_athlete_id"] = int(curr_u["id"])
                    st.toast(msg_p)
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error(msg_p)

    db_uri = resolve_database_url()
    is_pg = db_uri.startswith("postgresql")
    backend_lbl = "Sauvegarde cloud active" if is_pg else "Stockage local"
    backend_badge = "badge-lime" if is_pg else "badge-cyan"

    render_html(f"""
        <div class="cali-card" style="padding: 12px 14px; margin: 0.85rem 0;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <span style="font-size:0.84rem; font-weight:700; color:#F8FAFC;">Synchronisation des données</span>
                <span class="{backend_badge}">{backend_lbl}</span>
            </div>
        </div>
    """)

    sess_cfg = st.session_state.get("session_settings", {"auto_advance": True})

    with st.form("settings_full_form"):
        st.markdown("##### Option d'analyse vidéo complémentaire")
        gem_key_input = st.text_input(
            "Clé API Gemini (optionnel) :",
            value=get_gemini_api_key(),
            type="password",
            help="Active l'option d'estimation complémentaire dans le Studio."
        )

        render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin: 0.9rem 0;'>")
        st.markdown("##### Confort d'utilisation du Studio")
        auto_adv = st.checkbox(
            "Passer automatiquement à la vidéo suivante après enregistrement",
            value=bool(sess_cfg.get("auto_advance", True))
        )

        if st.form_submit_button("Enregistrer les réglages", type="primary", use_container_width=True):
            st.session_state.active_gemini_key = gem_key_input.strip()
            st.session_state.session_settings = {"auto_advance": auto_adv}
            st.toast("Réglages enregistrés.")
            time.sleep(0.25)
            st.rerun()

    render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin: 1.05rem 0;'>")
    st.markdown("##### Exports & sauvegardes")

    active_profile = st.session_state.get("active_athlete_profile") or curr_u
    logs = get_training_logs_for_athlete(curr_u, target_athlete_id=int(active_profile["id"]))
    df_base = load_baselines_table(user=curr_u)
    acwr_metrics = compute_longitudinal_metrics(logs)

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        st.download_button(
            "Exporter en CSV",
            data=export_dataframe_to_csv_bytes(build_logs_export_dataframe(logs)),
            file_name=f"caliperf_seances_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="settings_dl_csv",
        )
    with col_e2:
        st.download_button(
            "Exporter en Excel",
            data=export_workbook_xlsx_bytes(logs, acwr_metrics["daily_df"], df_base),
            file_name=f"caliperf_complet_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="settings_dl_xlsx",
        )
    with col_e3:
        st.download_button(
            "Exporter les figures",
            data=export_baselines_json(user=curr_u).encode("utf-8"),
            file_name=f"figures_reference_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
            key="settings_dl_json",
        )

    render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin: 1.05rem 0;'>")
    st.markdown("##### Session & Compte")
    if st.button("Se déconnecter / Changer de compte", key="btn_logout_settings", use_container_width=True):
        logout_user_from_session(stay_on_auth_portal=True)
        st.rerun()
