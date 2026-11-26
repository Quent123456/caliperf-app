"""
ui/profile_dialog.py - Gestion du profil utilisateur SQL, photo Base64, PDC et code d'invitation coach.
"""

import html
import time
import streamlit as st

from core.auth import (
    get_role_badge_info,
    normalize_role,
    process_avatar_image,
    render_avatar_html,
)
from core.database import (
    get_scoped_athlete_counts,
    get_user_by_id,
    link_athlete_to_coach_by_code,
    login_user_in_session,
    logout_user_from_session,
    update_user_profile_sql,
)
from ui.theme import render_html


def _get_role_description(role: str) -> str:
    if normalize_role(role) == "coach":
        return "Coach CaliPerf : création et calibrage de vos figures 3D, gestion isolée de vos athlètes et suivi ACWR."
    return "Élève CaliPerf : suivi de vos séances, analyse 3D sur les baselines partagées de votre coach et exports."


def _rerun_app() -> None:
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()


def _build_profile_content() -> None:
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        st.warning("Aucun utilisateur connecté.")
        return

    user_rec = get_user_by_id(int(curr_u["id"])) or curr_u
    uid = int(user_rec["id"])
    u_full = str(user_rec.get("full_name") or user_rec.get("username", "Utilisateur"))
    u_username = str(user_rec.get("username", "user"))
    u_role = normalize_role(user_rec.get("role", "athlete"))
    u_avatar = str(user_rec.get("avatar_b64") or user_rec.get("avatar", ""))
    u_created = str(user_rec.get("created_at", "—"))
    u_bw = float(user_rec.get("bodyweight_kg", 70.0) or 70.0)
    u_invite = user_rec.get("invite_code") or ""
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role, u_username)

    counts = get_scoped_athlete_counts(user_rec)
    avatar_big = render_avatar_html(u_avatar, u_full, size=76)
    safe_full = html.escape(u_full)
    safe_user = html.escape(u_username)
    role_desc = html.escape(_get_role_description(u_role))

    invite_line = (
        f'<br>🔑 <b>Code d\'invitation Coach :</b> <span style="font-family:\'JetBrains Mono\',monospace;color:#00E5FF;font-weight:800;">{html.escape(u_invite)}</span>'
        if u_role == "coach" and u_invite else ""
    )

    render_html(f"""
        <div class="cali-card-accent" style="display:flex;align-items:center;gap:14px;padding:1rem;margin-bottom:0.9rem;">
            <div style="flex-shrink:0;">{avatar_big}</div>
            <div style="min-width:0;flex:1;">
                <h3 style="margin:0;font-size:1.15rem;font-weight:800;color:#F8FAFC;line-height:1.2;">{safe_full}</h3>
                <div style="font-size:0.78rem;color:#94A3B8;margin:2px 0 6px 0;">@{safe_user} • PDC {u_bw:.1f} kg • Membre depuis {html.escape(u_created)}</div>
                <span class="{role_badge_cls}">{role_icon} {role_label}</span>
            </div>
        </div>
    """)

    render_html(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 12px;margin-bottom:0.9rem;font-size:0.82rem;color:#CBD5E1;line-height:1.45;">
            <b>Statut du compte :</b> {role_desc}<br>
            <span style="color:#00E5FF;font-weight:700;">📐 {counts['figures']} figure(s)</span> •
            <span style="color:#34D399;font-weight:700;">📊 {counts['sessions']} séance(s)</span>
            {invite_line}
        </div>
    """)

    if u_role == "athlete":
        coach_obj = get_user_by_id(int(user_rec["coach_id"])) if user_rec.get("coach_id") else None
        if coach_obj:
            st.info(f"🏋️ Rattaché au coach : **{coach_obj['full_name']}** (@{coach_obj['username']})")
        else:
            with st.form("form_bind_coach_invite"):
                code_inp = st.text_input("Rejoindre un coach (Code invitation) :", placeholder="ex: CALI-1A2B3C")
                if st.form_submit_button("🔗 Associer à ce coach", use_container_width=True):
                    ok_l, msg_l, upd_u = link_athlete_to_coach_by_code(uid, code_inp)
                    if ok_l and upd_u:
                        login_user_in_session(upd_u)
                        st.success(msg_l)
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error(msg_l)

    st.markdown("##### 📸 Photo de profil")
    new_photo = st.file_uploader(
        "Importer ou remplacer votre photo (JPG, PNG, WEBP) :",
        type=["jpg", "jpeg", "png", "webp"],
        key="modal_profile_avatar_upload"
    )

    if new_photo is not None:
        preview_b64 = process_avatar_image(new_photo)
        if preview_b64:
            render_html(
                '<div style="display:flex;align-items:center;gap:12px;margin:8px 0;padding:8px 10px;'
                'background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.22);border-radius:10px;">'
                f'{render_avatar_html(preview_b64, u_full, size=64)}'
                '<div style="font-size:0.82rem;color:#E2E8F0;"><b>Aperçu prêt</b><br>'
                '<span style="color:#94A3B8;">Cliquez ci-dessous pour enregistrer sur votre profil.</span></div></div>'
            )
            if st.button("💾 Enregistrer cette photo", type="primary", use_container_width=True, key="btn_save_new_avatar"):
                ok_u, _, upd_u = update_user_profile_sql(uid, avatar_b64=preview_b64)
                if ok_u and upd_u:
                    login_user_in_session(upd_u)
                    st.toast("✅ Photo de profil enregistrée !")
                    _rerun_app()
        else:
            st.error("Impossible de décoder cette image. Essayez un fichier JPG ou PNG.")

    if u_avatar:
        if st.button("🗑️ Retirer la photo actuelle (revenir à l'initiale)", use_container_width=True, key="btn_remove_avatar"):
            ok_r, _, upd_u = update_user_profile_sql(uid, avatar_b64="")
            if ok_r and upd_u:
                login_user_in_session(upd_u)
                st.toast("✅ Photo retirée")
                _rerun_app()

    with st.expander("✏️ Modifier mes informations (Nom / PDC / Mot de passe)", expanded=False):
        with st.form("form_edit_profile_info"):
            c_ed1, c_ed2 = st.columns([1.6, 1.0])
            with c_ed1:
                upd_name = st.text_input("Nom d'affichage :", value=u_full)
            with c_ed2:
                upd_bw = st.number_input("Poids de corps (kg) :", min_value=25.0, max_value=250.0, value=u_bw, step=0.5)

            c_pw1, c_pw2 = st.columns(2)
            with c_pw1:
                upd_p1 = st.text_input("Nouveau mot de passe (optionnel) :", type="password")
            with c_pw2:
                upd_p2 = st.text_input("Confirmer le mot de passe :", type="password")

            if st.form_submit_button("💾 Mettre à jour mon profil", type="primary", use_container_width=True):
                if upd_p1 or upd_p2:
                    if upd_p1 != upd_p2 or len(upd_p1) < 4:
                        st.error("Les mots de passe doivent correspondre (min. 4 caractères).")
                        st.stop()
                ok_p, msg_p, upd_u = update_user_profile_sql(
                    uid,
                    full_name=upd_name,
                    password=upd_p1 if upd_p1 else None,
                    bodyweight_kg=upd_bw,
                )
                if ok_p and upd_u:
                    login_user_in_session(upd_u)
                    st.toast("✅ Profil mis à jour !")
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error(msg_p)

    render_html("<div style='height:6px;'></div>")
    c_act1, c_act2 = st.columns(2)
    with c_act1:
        if st.button("🔄 Changer de compte", use_container_width=True, key="btn_profile_switch_acct"):
            logout_user_from_session(stay_on_auth_portal=True)
            st.rerun()
    with c_act2:
        if st.button("✅ Fermer", type="primary", use_container_width=True, key="btn_profile_close"):
            st.rerun()


if hasattr(st, "dialog"):
    @st.dialog("👤 Mon Profil CaliPerf", width="large")
    def open_profile_modal():
        """Ouvre la modale de profil (statut, photo, PDC, code invitation)."""
        _build_profile_content()
else:
    def open_profile_modal():
        with st.container(border=True):
            st.subheader("👤 Mon Profil CaliPerf")
            _build_profile_content()
