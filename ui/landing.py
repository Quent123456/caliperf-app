"""
ui/landing.py - Page d'accueil et portail d'authentification SQL CaliPerf Pro.
Prend en charge les comptes Coach / Élève, les codes d'invitation coach et la session F5.
"""

import time
import streamlit as st

from core.auth import process_avatar_image
from core.database import (
    authenticate_user_sql,
    get_scoped_athlete_counts,
    get_user_by_username,
    login_user_in_session,
    logout_user_from_session,
    register_user_sql,
)
from ui.theme import render_html


def _get_invite_code_from_query() -> str:
    """Lit le paramètre URL ?invite=CODE s'il est présent."""
    try:
        raw = st.query_params.get("invite", "")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        return str(raw or "").strip()
    except Exception:
        return ""


def render_landing_page() -> None:
    """Affiche l'écran d'accueil épuré avec bénéfices concrets pour le coach et l'athlète."""
    curr_u = st.session_state.get("current_user")
    counts = get_scoped_athlete_counts(curr_u) if curr_u else {"figures": 9, "sessions": 0, "athletes": 0}
    badge_stat = (
        f"Espace actif • {counts['figures']} figures • {counts['sessions']} séances"
        if curr_u else
        "Suivi sportif • Coachs & Athlètes"
    )

    render_html(f"""
        <div style="text-align: center; margin-top: 1.1rem; margin-bottom: 1.65rem;">
            <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.24); border-radius: 9999px; padding: 5px 14px; margin-bottom: 0.9rem;">
                <span style="width: 7px; height: 7px; border-radius: 50%; background: #10B981; box-shadow: 0 0 8px #10B981; display: inline-block;"></span>
                <span style="color: #00E5FF; font-weight: 700; font-size: 0.74rem; letter-spacing: 0.06em; text-transform: uppercase;">
                    {badge_stat}
                </span>
            </div>
            <h1 style="font-size: clamp(2rem, 6vw, 2.8rem); font-weight: 800; letter-spacing: -0.03em; margin: 0 0 0.55rem 0; line-height: 1.1; color: #F8FAFC;">
                CALIPERF
            </h1>
            <p style="color: #94A3B8; font-size: 0.96rem; max-width: 520px; margin: 0 auto; line-height: 1.55;">
                Suivez les séries de vos athlètes, chronométrez vos vidéos automatiquement et adaptez l'entraînement à la fatigue du moment.
            </p>
        </div>
    """)

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.15rem 0.95rem; margin-bottom: 0.8rem;">
                <div style="font-size: 0.94rem; font-weight: 800; color: #F8FAFC;">Chronométrage vidéo</div>
                <p style="font-size: 0.8rem; color: #94A3B8; margin: 6px 0 0 0; line-height: 1.45;">
                    Mesurez automatiquement le temps sous tension et comptez les répétitions depuis chaque vidéo.
                </p>
            </div>
        """)
    with col_p2:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.15rem 0.95rem; margin-bottom: 0.8rem;">
                <div style="font-size: 0.94rem; font-weight: 800; color: #F8FAFC;">Suivi des séries & lest</div>
                <p style="font-size: 0.8rem; color: #94A3B8; margin: 6px 0 0 0; line-height: 1.45;">
                    Enregistrez vos séries, conservez le dernier lest utilisé et comparez chaque passage au précédent.
                </p>
            </div>
        """)
    with col_p3:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.15rem 0.95rem; margin-bottom: 0.8rem;">
                <div style="font-size: 0.94rem; font-weight: 800; color: #F8FAFC;">Gestion de la fatigue</div>
                <p style="font-size: 0.8rem; color: #94A3B8; margin: 6px 0 0 0; line-height: 1.45;">
                    Comparez la charge des 7 derniers jours à l'habitude du mois et exportez vos bilans PDF.
                </p>
            </div>
        """)

    render_html("""
        <div class="cali-card-accent" style="text-align: center; padding: 1.45rem 1.2rem; margin-top: 0.45rem;">
            <h3 style="margin: 0 0 0.35rem 0; font-size: 1.2rem; font-weight: 800; color: #F8FAFC;">
                Prêt pour la séance ?
            </h3>
            <p style="margin: 0 0 0.15rem 0; font-size: 0.88rem; color: #94A3B8; line-height: 1.45;">
                Analysez vos vidéos d'entraînement, suivez chaque élève individuellement et ajustez le volume en un coup d'œil.
            </p>
        </div>
    """)

    if curr_u:
        c_label = f"Reprendre la session ({curr_u.get('full_name') or curr_u.get('username')})"
        if st.button(c_label, type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()
        if st.button("Changer de compte / Se déconnecter", use_container_width=True, key="btn_switch_account_landing"):
            logout_user_from_session(stay_on_auth_portal=True)
            st.rerun()
    else:
        if st.button("C'est parti !", type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()

    render_html("""
        <div style="text-align: center; color: #64748B; font-size: 0.74rem; margin-top: 1.8rem; letter-spacing: 0.03em;">
            CaliPerf • Suivi d'entraînement & Analyse vidéo
        </div>
    """)


def render_auth_portal() -> None:
    """Affiche le portail de connexion et d'inscription."""
    render_html("""
        <div style="text-align: center; margin-top: 0.8rem; margin-bottom: 1.3rem;">
            <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.025em; margin: 0 0 0.35rem 0; color: #F8FAFC;">
                Espace Membres CaliPerf
            </h2>
            <p style="color: #94A3B8; font-size: 0.88rem; max-width: 460px; margin: 0 auto;">
                Connectez-vous à votre espace Coach ou Athlète pour retrouver vos séances et vos élèves.
            </p>
        </div>
    """)

    tab_login, tab_register = st.tabs(["Se connecter", "Créer un compte"])

    with tab_login:
        with st.form("form_login_user"):
            l_user = st.text_input("Identifiant :", placeholder="ex: admin, coach_alex, thomas...").strip()
            l_pass = st.text_input("Mot de passe :", type="password")

            c_btn1, c_btn2 = st.columns([1.4, 1.4])
            with c_btn1:
                btn_login = st.form_submit_button("Se connecter", type="primary", use_container_width=True)
            with c_btn2:
                btn_quick_admin = st.form_submit_button(
                    "Connexion Admin Rapide",
                    help="Connexion directe au compte Coach Principal",
                    use_container_width=True
                )

            if btn_login:
                if not l_user or not l_pass:
                    st.warning("Veuillez renseigner votre identifiant et votre mot de passe.")
                else:
                    auth_u = authenticate_user_sql(l_user, l_pass)
                    if auth_u:
                        login_user_in_session(auth_u)
                        st.toast(f"Bienvenue, {auth_u['full_name']} !")
                        time.sleep(0.25)
                        st.rerun()
                    else:
                        st.error("Identifiant ou mot de passe incorrect.")

            if btn_quick_admin:
                admin_u = get_user_by_username("admin")
                if admin_u:
                    login_user_in_session(admin_u)
                    st.toast("Connecté en tant que Coach Principal")
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error("Compte principal introuvable.")

    with tab_register:
        invite_qp = _get_invite_code_from_query()
        if invite_qp:
            st.info(f"Invitation coach détectée : **{invite_qp}** — pré-remplie ci-dessous pour votre compte Élève.")
        render_html("<small style='color:#94A3B8;'>Créez votre compte Coach ou Élève. Un élève peut saisir le code d'invitation de son coach.</small>")
        with st.form("form_register_user", clear_on_submit=False):
            reg_role = st.radio(
                "Je suis :",
                ["Coach", "Élève"],
                index=1 if invite_qp else 0,
                horizontal=True,
            )
            col_rn1, col_rn2 = st.columns([1.6, 1.0])
            with col_rn1:
                reg_full_name = st.text_input("Nom complet / Prénom :", placeholder="ex: Alexandre Coach")
            with col_rn2:
                reg_bw = st.number_input("Poids de corps (kg) :", min_value=30.0, max_value=200.0, value=70.0, step=0.5)

            col_ru1, col_ru2 = st.columns([1.4, 1.2])
            with col_ru1:
                reg_username = st.text_input("Identifiant unique :", placeholder="ex: coach_alex")
            with col_ru2:
                reg_invite = st.text_input(
                    "Code invitation coach (si Élève) :",
                    value=invite_qp,
                    placeholder="ex: CALI-A1B2C3",
                )

            col_rp1, col_rp2 = st.columns(2)
            with col_rp1:
                reg_pass1 = st.text_input("Mot de passe :", type="password")
            with col_rp2:
                reg_pass2 = st.text_input("Confirmer le mot de passe :", type="password")

            reg_avatar_upload = st.file_uploader(
                "Photo de profil (smartphone ou PC) :",
                type=["jpg", "jpeg", "png", "webp"]
            )

            btn_create = st.form_submit_button("Créer mon compte", type="primary", use_container_width=True)
            if btn_create:
                if not reg_username.strip():
                    st.warning("Veuillez choisir un identifiant.")
                elif not reg_pass1 or reg_pass1 != reg_pass2:
                    st.warning("Les mots de passe ne correspondent pas ou sont vides.")
                else:
                    avatar_b64 = process_avatar_image(reg_avatar_upload) if reg_avatar_upload else ""
                    role_str = "coach" if "coach" in reg_role.lower() else "athlete"
                    ok_r, msg_r, new_usr = register_user_sql(
                        username=reg_username,
                        password=reg_pass1,
                        role=role_str,
                        full_name=reg_full_name,
                        avatar_b64=avatar_b64,
                        invite_code_input=reg_invite,
                        bodyweight_kg=reg_bw,
                    )
                    if ok_r and new_usr:
                        login_user_in_session(new_usr)
                        st.success(f"{msg_r} Bienvenue, {new_usr['full_name']} !")
                        time.sleep(0.35)
                        st.rerun()
                    else:
                        st.error(msg_r)

    render_html("<div style='height: 10px;'></div>")
    if st.button("Revenir à la page d'accueil", use_container_width=True):
        st.session_state.app_entered = False
        st.rerun()
