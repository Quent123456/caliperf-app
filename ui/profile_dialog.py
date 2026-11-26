"""
ui/profile_dialog.py - Consultation du statut utilisateur et gestion de la photo de profil.
Permet à l'Administrateur, au Coach ou à l'Élève de voir son statut, modifier sa photo
de profil (compressée Base64) et mettre à jour son nom / mot de passe.
"""

import html
import time
import streamlit as st

from core.auth import (
    get_default_admin,
    get_role_badge_info,
    render_avatar_html,
    process_avatar_image,
    hash_password
)
from core.database import save_db
from ui.theme import render_html


def _get_role_description(role: str) -> str:
    r = str(role).strip().lower()
    if r == "admin":
        return "Administrateur Principal : accès complet, bibliothèque officielle permanente, validation des figures coachs."
    if r == "coach":
        return "Coach CaliPerf : création et calibrage de vos figures personnalisées, analyse 3D et suivi de vos athlètes."
    return "Élève CaliPerf : consultation de la bibliothèque 3D et visualisation de vos repères biomécaniques."


def _ensure_user_in_db(curr_u: dict) -> str:
    """Garantit la présence de l'utilisateur courant dans db['users'] et retourne sa clé."""
    if "users" not in st.session_state.db or not isinstance(st.session_state.db["users"], dict):
        st.session_state.db["users"] = {"admin": get_default_admin()}

    uname = str(curr_u.get("username", "admin")).strip().lower()
    users = st.session_state.db["users"]
    for k in users.keys():
        if k.strip().lower() == uname:
            return k

    users[uname] = dict(curr_u)
    return uname


def _build_profile_content() -> None:
    curr_u = st.session_state.current_user or get_default_admin()
    db_key = _ensure_user_in_db(curr_u)
    user_rec = st.session_state.db["users"][db_key]

    u_full = str(user_rec.get("full_name") or user_rec.get("username", "Utilisateur"))
    u_username = str(user_rec.get("username", db_key))
    u_role = str(user_rec.get("role", "eleve"))
    u_avatar = str(user_rec.get("avatar", ""))
    u_created = str(user_rec.get("created_at", "—"))
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role)

    # Compteurs personnels
    baselines = st.session_state.db.get("baselines_3d", [])
    my_figs = len(set(
        str(b.get("exercise", "")).strip()
        for b in baselines
        if str(b.get("owner", "")).strip().lower() == u_username.lower()
    ))
    evals_count = len(st.session_state.db.get("evaluations", []))

    avatar_big = render_avatar_html(u_avatar, u_full, size=76)
    safe_full = html.escape(u_full)
    safe_user = html.escape(u_username)
    role_desc = html.escape(_get_role_description(u_role))

    render_html(f"""
        <div class="cali-card-accent" style="display:flex;align-items:center;gap:14px;padding:1rem;margin-bottom:0.9rem;">
            <div style="flex-shrink:0;">{avatar_big}</div>
            <div style="min-width:0;flex:1;">
                <h3 style="margin:0;font-size:1.15rem;font-weight:800;color:#F8FAFC;line-height:1.2;">{safe_full}</h3>
                <div style="font-size:0.78rem;color:#94A3B8;margin:2px 0 6px 0;">@{safe_user} • Membre depuis {html.escape(u_created)}</div>
                <span class="{role_badge_cls}">{role_icon} {role_label}</span>
            </div>
        </div>
    """)

    render_html(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 12px;margin-bottom:0.9rem;font-size:0.82rem;color:#CBD5E1;line-height:1.45;">
            <b>Statut du compte :</b> {role_desc}<br>
            <span style="color:#00E5FF;font-weight:700;">📐 {my_figs} figure(s) associée(s)</span> •
            <span style="color:#34D399;font-weight:700;">📊 {evals_count} séance(s) dans la base</span>
        </div>
    """)

    # Section Photo de profil
    st.markdown("##### 📸 Photo de profil")
    new_photo = st.file_uploader(
        "Importer ou remplacer votre photo (JPG, PNG, WEBP) :",
        type=["jpg", "jpeg", "png", "webp"],
        key="modal_profile_avatar_upload"
    )

    if new_photo is not None:
        st.image(new_photo, width=84, caption="Aperçu de la nouvelle photo")
        if st.button("💾 Enregistrer cette photo", type="primary", use_container_width=True, key="btn_save_new_avatar"):
            b64 = process_avatar_image(new_photo)
            if b64:
                st.session_state.db["users"][db_key]["avatar"] = b64
                st.session_state.current_user = dict(st.session_state.db["users"][db_key])
                save_db(st.session_state.db)
                st.toast("✅ Photo de profil enregistrée !")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Impossible de traiter cette image.")

    if u_avatar:
        if st.button("🗑️ Retirer la photo actuelle (revenir à l'initiale)", use_container_width=True, key="btn_remove_avatar"):
            st.session_state.db["users"][db_key]["avatar"] = ""
            st.session_state.current_user = dict(st.session_state.db["users"][db_key])
            save_db(st.session_state.db)
            st.toast("✅ Photo retirée")
            time.sleep(0.25)
            st.rerun()

    # Modification Nom / Mot de passe
    with st.expander("✏️ Modifier mes informations (Nom / Mot de passe)", expanded=False):
        with st.form("form_edit_profile_info"):
            upd_name = st.text_input("Nom d'affichage :", value=u_full)
            c_pw1, c_pw2 = st.columns(2)
            with c_pw1:
                upd_p1 = st.text_input("Nouveau mot de passe (optionnel) :", type="password")
            with c_pw2:
                upd_p2 = st.text_input("Confirmer le mot de passe :", type="password")

            if st.form_submit_button("💾 Mettre à jour mon profil", type="primary", use_container_width=True):
                if upd_name.strip():
                    st.session_state.db["users"][db_key]["full_name"] = upd_name.strip()
                if upd_p1 or upd_p2:
                    if upd_p1 != upd_p2 or len(upd_p1) < 4:
                        st.error("Les mots de passe doivent correspondre (min. 4 caractères).")
                        st.stop()
                    st.session_state.db["users"][db_key]["password_hash"] = hash_password(upd_p1)
                st.session_state.current_user = dict(st.session_state.db["users"][db_key])
                save_db(st.session_state.db)
                st.toast("✅ Profil mis à jour !")
                time.sleep(0.3)
                st.rerun()

    render_html("<div style='height:6px;'></div>")
    c_act1, c_act2 = st.columns(2)
    with c_act1:
        if st.button("🔄 Changer de compte", use_container_width=True, key="btn_profile_switch_acct"):
            st.session_state.current_user = None
            st.session_state.is_authenticated = False
            st.session_state.app_entered = True
            st.rerun()
    with c_act2:
        if st.button("✅ Fermer", type="primary", use_container_width=True, key="btn_profile_close"):
            st.rerun()


if hasattr(st, "dialog"):
    @st.dialog("👤 Mon Profil CaliPerf", width="large")
    def open_profile_modal():
        """Ouvre la modale de profil (statut, photo de profil, modification)."""
        _build_profile_content()
else:
    def open_profile_modal():
        with st.container(border=True):
            st.subheader("👤 Mon Profil CaliPerf")
            _build_profile_content()
