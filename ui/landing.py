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


def render_landing_page() -> None:
    """Affiche l'écran d'accueil épuré avec aperçu des capacités et accès rapide."""
    curr_u = st.session_state.get("current_user")
    counts = get_scoped_athlete_counts(curr_u) if curr_u else {"figures": 9, "sessions": 0, "athletes": 0}
    badge_stat = (
        f"Moteur 3D SQL • {counts['figures']} Figures • {counts['sessions']} Séances"
        if curr_u else
        "Moteur 3D SQL Autonome • Coach & Athlètes"
    )

    render_html(f"""
        <div style="text-align: center; margin-top: 1rem; margin-bottom: 1.5rem;">
            <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.28); border-radius: 9999px; padding: 5px 14px; margin-bottom: 0.9rem;">
                <span style="width: 7px; height: 7px; border-radius: 50%; background: #10B981; box-shadow: 0 0 8px #10B981; display: inline-block;"></span>
                <span style="color: #00E5FF; font-weight: 700; font-size: 0.74rem; letter-spacing: 0.06em; text-transform: uppercase;">
                    {badge_stat}
                </span>
            </div>
            <h1 style="font-size: clamp(2rem, 6vw, 2.8rem); font-weight: 800; letter-spacing: -0.03em; margin: 0 0 0.5rem 0; line-height: 1.1; color: #F8FAFC;">
                CALIPERF <span style="background: linear-gradient(135deg, #00E5FF, #0EA5E9); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRO</span>
            </h1>
            <p style="color: #94A3B8; font-size: 0.95rem; max-width: 520px; margin: 0 auto; line-height: 1.55;">
                Analyse cinématique 3D, contrôle qualité vidéo, charge pondérée ACWR EWMA et suivi multi-athlètes persistant en base SQL.
            </p>
        </div>
    """)

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">📐</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">Cinématique 3D & QC</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    Repères métriques MediaPipe 3D et contrôle qualité automatique avant sauvegarde
                </p>
            </div>
        """)
    with col_p2:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">⏱️</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">Charge & Fatigue</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    Charge externe UA, sRPE, dérive angulaire intra-série et perte de vélocité
                </p>
            </div>
        """)
    with col_p3:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">📊</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">ACWR & Stress Tendon</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    EWMA 7j/28j, Monotonie de Foster, jauge tendineuse et exports CSV / XLSX
                </p>
            </div>
        """)

    render_html("""
        <div class="cali-card-accent" style="text-align: center; padding: 1.55rem 1.2rem; margin-top: 0.45rem;">
            <div style="display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; background: rgba(0, 229, 255, 0.14); border: 1px solid rgba(0, 229, 255, 0.38); border-radius: 14px; margin-bottom: 0.75rem; font-size: 1.45rem;">
                🤸‍♂️
            </div>
            <h3 style="margin: 0 0 0.35rem 0; font-size: 1.25rem; font-weight: 800; color: #F8FAFC;">
                Prêt pour la séance ?
            </h3>
            <p style="margin: 0 0 0.2rem 0; font-size: 0.88rem; color: #94A3B8; line-height: 1.45;">
                Analysez vos vidéos, pilotez vos élèves en isolation stricte et suivez l'ACWR en temps réel.
            </p>
        </div>
    """)

    if curr_u:
        c_label = f"🚀 Reprendre la session ({curr_u.get('full_name') or curr_u.get('username')})"
        if st.button(c_label, type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()
        if st.button("🔄 Changer de compte / Se déconnecter", use_container_width=True, key="btn_switch_account_landing"):
            logout_user_from_session(stay_on_auth_portal=True)
            st.rerun()
    else:
        if st.button("🚀 C'est parti !", type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()

    render_html("""
        <div style="text-align: center; color: #64748B; font-size: 0.74rem; margin-top: 1.8rem; letter-spacing: 0.03em;">
            CaliPerf Pro • Base SQL Persistante & Navigation Tactile Fluide
        </div>
    """)


def render_auth_portal() -> None:
    """Affiche le portail de connexion et d'inscription sécurisé PBKDF2-HMAC + session F5."""
    render_html("""
        <div style="text-align: center; margin-top: 0.8rem; margin-bottom: 1.3rem;">
            <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 9999px; padding: 4px 14px; margin-bottom: 0.6rem;">
                <span style="font-size: 13px;">🔐</span>
                <span style="color: #00E5FF; font-weight: 700; font-size: 0.74rem; letter-spacing: 0.05em; text-transform: uppercase;">Authentification SQL</span>
            </div>
            <h2 style="font-size: 1.85rem; font-weight: 800; letter-spacing: -0.025em; margin: 0 0 0.3rem 0; color: #F8FAFC;">
                Espace Membres CaliPerf
            </h2>
            <p style="color: #94A3B8; font-size: 0.88rem; max-width: 460px; margin: 0 auto;">
                Accédez à votre cockpit Coach ou Athlète avec isolation stricte des données.
            </p>
        </div>
    """)

    tab_login, tab_register = st.tabs(["🔑 Se connecter", "📝 Créer un compte"])

    with tab_login:
        with st.form("form_login_user"):
            l_user = st.text_input("Identifiant :", placeholder="ex: admin, coach_alex, thomas...").strip()
            l_pass = st.text_input("Mot de passe :", type="password")

            c_btn1, c_btn2 = st.columns([1.4, 1.4])
            with c_btn1:
                btn_login = st.form_submit_button("🚀 Se connecter", type="primary", use_container_width=True)
            with c_btn2:
                btn_quick_admin = st.form_submit_button(
                    "⚡ Connexion Admin Rapide",
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
                        st.toast(f"✅ Bienvenue, {auth_u['full_name']} !")
                        time.sleep(0.25)
                        st.rerun()
                    else:
                        st.error("Identifiant ou mot de passe incorrect.")

            if btn_quick_admin:
                admin_u = get_user_by_username("admin")
                if admin_u:
                    login_user_in_session(admin_u)
                    st.toast("✅ Connecté en tant que Coach Principal")
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error("Compte principal introuvable en base SQL.")

    with tab_register:
        render_html("<small style='color:#94A3B8;'>Créez votre compte Coach ou Élève. Un élève peut saisir le code d'invitation de son coach.</small>")
        with st.form("form_register_user", clear_on_submit=False):
            reg_role = st.radio("Je suis :", ["🏋️ Coach", "🤸 Élève"], horizontal=True)
            col_rn1, col_rn2 = st.columns([1.6, 1.0])
            with col_rn1:
                reg_full_name = st.text_input("Nom complet / Prénom :", placeholder="ex: Alexandre Coach")
            with col_rn2:
                reg_bw = st.number_input("Poids de corps (kg) :", min_value=30.0, max_value=200.0, value=70.0, step=0.5)

            col_ru1, col_ru2 = st.columns([1.4, 1.2])
            with col_ru1:
                reg_username = st.text_input("Identifiant unique (login) :", placeholder="ex: coach_alex")
            with col_ru2:
                reg_invite = st.text_input("Code invitation coach (si Élève) :", placeholder="ex: CALI-A1B2C3")

            col_rp1, col_rp2 = st.columns(2)
            with col_rp1:
                reg_pass1 = st.text_input("Mot de passe :", type="password")
            with col_rp2:
                reg_pass2 = st.text_input("Confirmer le mot de passe :", type="password")

            reg_avatar_upload = st.file_uploader(
                "Photo de profil (smartphone ou PC) :",
                type=["jpg", "jpeg", "png", "webp"]
            )

            btn_create = st.form_submit_button("➕ Créer mon compte", type="primary", use_container_width=True)
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
                        st.success(f"✅ {msg_r} Bienvenue, {new_usr['full_name']} !")
                        time.sleep(0.35)
                        st.rerun()
                    else:
                        st.error(msg_r)

    render_html("<div style='height: 10px;'></div>")
    if st.button("👈 Revenir à la page d'accueil", use_container_width=True):
        st.session_state.app_entered = False
        st.rerun()
