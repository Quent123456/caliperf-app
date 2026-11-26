"""
ui/tab_settings.py - Compartiment 5 : Paramètres, Connecteurs Cloud & Sauvegardes JSON.
"""

import json
import time
from datetime import datetime
import streamlit as st

from core.database import (
    save_db,
    get_gemini_api_key,
    DEFAULT_FORM_URL,
    DEFAULT_ENTRY_NOM,
    DEFAULT_ENTRY_EXO,
    DEFAULT_ENTRY_TST,
    DEFAULT_ENTRY_RPE
)
from ui.theme import render_html


def render_tab_settings() -> None:
    """Rend les réglages système, connecteurs externes et sauvegarde/restauration."""
    render_html("""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                ⚙️ Paramètres & Connecteurs
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Configurez la synchronisation de vos séances, l'IA de secours et les sauvegardes complètes.
            </p>
        </div>
    """)

    settings = st.session_state.db.get("settings", {})

    with st.form("settings_full_form"):
        st.markdown("##### 🌐 Mode d'Enregistrement")
        cur_mode = settings.get("sync_mode", "google_forms")
        mode_idx = 0 if cur_mode == "google_forms" else (1 if cur_mode == "gsheet_webhook" else 2)

        sync_mode = st.radio(
            "Où stocker vos analyses ?",
            [
                ("google_forms", "📝 Google Forms (Méthode actuelle)"),
                ("gsheet_webhook", "🚀 Google Sheets Direct (Sans formulaire)"),
                ("local_only", "💾 Caliperf Local uniquement (100% hors-ligne)")
            ],
            format_func=lambda x: x[1],
            index=mode_idx
        )[0]

        if sync_mode == "gsheet_webhook":
            wh_url_input = st.text_input("URL Webhook Google Apps Script :", value=settings.get("webhook_url", ""))
        else:
            wh_url_input = settings.get("webhook_url", "")

        if sync_mode == "google_forms":
            form_url = st.text_input("URL Google Form :", value=settings.get("form_url", DEFAULT_FORM_URL))
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_nom = st.text_input("Entry Nom :", value=settings.get("entry_nom", DEFAULT_ENTRY_NOM))
                e_tst = st.text_input("Entry TST :", value=settings.get("entry_tst", DEFAULT_ENTRY_TST))
            with col_e2:
                e_exo = st.text_input("Entry Exo :", value=settings.get("entry_exo", DEFAULT_ENTRY_EXO))
                e_rpe = st.text_input("Entry RPE :", value=settings.get("entry_rpe", DEFAULT_ENTRY_RPE))
        else:
            form_url = settings.get("form_url", DEFAULT_FORM_URL)
            e_nom = settings.get("entry_nom", DEFAULT_ENTRY_NOM)
            e_tst = settings.get("entry_tst", DEFAULT_ENTRY_TST)
            e_exo = settings.get("entry_exo", DEFAULT_ENTRY_EXO)
            e_rpe = settings.get("entry_rpe", DEFAULT_ENTRY_RPE)

        render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.8rem 0;'>")
        st.markdown("##### 🤖 Intelligence Artificielle & Vision (Secours)")
        gem_key_input = st.text_input(
            "Clé API Gemini (Optionnel) :",
            value=get_gemini_api_key(),
            type="password",
            help="Active un bouton de secours IA Gemini Flash Vision dans le Studio si besoin."
        )

        render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.8rem 0;'>")
        st.markdown("##### ⚡ Ergonomie du Studio")
        auto_adv = st.checkbox(
            "Passer automatiquement à la vidéo suivante après validation",
            value=bool(settings.get("auto_advance", True))
        )

        if st.form_submit_button("💾 Enregistrer la configuration", type="primary", use_container_width=True):
            st.session_state.db["settings"] = {
                "sync_mode": sync_mode,
                "webhook_url": wh_url_input.strip(),
                "form_url": form_url.strip(),
                "entry_nom": e_nom.strip(),
                "entry_exo": e_exo.strip(),
                "entry_tst": e_tst.strip(),
                "entry_rpe": e_rpe.strip(),
                "gemini_api_key": gem_key_input.strip(),
                "admin_pwd": settings.get("admin_pwd", "admin"),
                "auto_advance": auto_adv
            }
            save_db(st.session_state.db)
            st.toast("✅ Configuration sauvegardée !")
            time.sleep(0.4)
            st.rerun()

    with st.expander("📄 Script Google Apps Script pour Google Sheets direct", expanded=False):
        st.code(
            """function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = JSON.parse(e.postData.contents);
  sheet.appendRow([data.date, data.student, data.exercise, data.tst, data.rpe, data.reps, data.notes]);
  return ContentService.createTextOutput("OK");
}""",
            language="javascript"
        )

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 1rem 0;'>")
    st.markdown("##### 💾 Sauvegarde & Restauration complète (JSON)")
    json_bytes = json.dumps(st.session_state.db, indent=2, ensure_ascii=False).encode("utf-8")

    col_dl, col_ul = st.columns(2)
    with col_dl:
        st.download_button(
            "📥 Télécharger la base complète",
            data=json_bytes,
            file_name=f"caliperf_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
    with col_ul:
        uploaded_backup = st.file_uploader(
            "Restaurer sauvegarde JSON",
            type=["json"],
            label_visibility="collapsed",
            key="restore_json_uploader"
        )
        if uploaded_backup is not None:
            try:
                loaded_data = json.load(uploaded_backup)
                if isinstance(loaded_data, dict):
                    st.session_state.db = loaded_data
                    save_db(st.session_state.db)
                    st.success("✅ Base restaurée avec succès !")
                    time.sleep(0.4)
                    st.rerun()
            except Exception as e_res:
                st.error(f"Erreur lors de la restauration : {e_res}")

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 1rem 0;'>")
    st.markdown("##### 🔐 Session & Compte")
    if st.button("🔄 Se déconnecter / Changer de compte", key="btn_logout_settings", use_container_width=True):
        st.session_state.current_user = None
        st.session_state.is_authenticated = False
        st.session_state.app_entered = True
        st.rerun()
