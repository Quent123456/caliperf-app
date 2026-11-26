"""
ui/landing.py - Page d'accueil et portail d'authentification CaliPerf Pro.
Design System : Kinetic Obsidian & Electric Telemetry.
"""

import time
import streamlit as st

from core.auth import (
    get_default_admin,
    authenticate_user,
    register_user,
    process_avatar_image
)
from core.database import save_db
from ui.theme import render_html


def render_landing_page() -> None:
    """Affiche l'écran d'accueil épuré avec aperçu des capacités et accès rapide."""
    db = st.session_state.get("db", {})
    nb_evals = len(db.get("evaluations", []))
    nb_figs = len(set(
        str(x.get("exercise", "")).strip()
        for x in db.get("baselines_3d", [])
        if str(x.get("exercise", "")).strip()
    ))

    render_html(f"""
        <div style="text-align: center; margin-top: 1rem; margin-bottom: 1.5rem;">
            <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.28); border-radius: 9999px; padding: 5px 14px; margin-bottom: 0.9rem;">
                <span style="width: 7px; height: 7px; border-radius: 50%; background: #10B981; box-shadow: 0 0 8px #10B981; display: inline-block;"></span>
                <span style="color: #00E5FF; font-weight: 700; font-size: 0.74rem; letter-spacing: 0.06em; text-transform: uppercase;">
                    Moteur 3D Local • {nb_figs} Figures • {nb_evals} Séances
                </span>
            </div>
            <h1 style="font-size: clamp(2rem, 6vw, 2.8rem); font-weight: 800; letter-spacing: -0.03em; margin: 0 0 0.5rem 0; line-height: 1.1; color: #F8FAFC;">
                CALIPERF <span style="background: linear-gradient(135deg, #00E5FF, #0EA5E9); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRO</span>
            </h1>
            <p style="color: #94A3B8; font-size: 0.95rem; max-width: 520px; margin: 0 auto; line-height: 1.55;">
                Analyse cinématique 3D haute précision, comptage automatique & chronométrage TST sans latence pour la Callisthénie et le Street Workout.
            </p>
        </div>
    """)

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">📐</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">Cinématique 3D</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    Repères métriques MediaPipe 3D invariants à l'angle de caméra
                </p>
            </div>
        """)
    with col_p2:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">⏱️</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">Chrono Pur TST</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    Temps sous tension temps réel & comptage automatique des reps
                </p>
            </div>
        """)
    with col_p3:
        render_html("""
            <div class="cali-card" style="text-align: center; padding: 1.1rem 0.9rem; margin-bottom: 0.65rem;">
                <div style="font-size: 1.55rem; margin-bottom: 6px;">📊</div>
                <div style="font-size: 0.92rem; font-weight: 800; color: #F8FAFC;">Suivi & RPE</div>
                <p style="font-size: 0.76rem; color: #94A3B8; margin: 4px 0 0 0; line-height: 1.4;">
                    Courbes d'évolution athlète, RPE et synchronisation cloud
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
                Analysez vos vidéos par lot, calibrez votre répertoire 3D et pilotez vos athlètes.
            </p>
        </div>
    """)

    curr_u = st.session_state.get("current_user")
    if curr_u:
        c_label = f"🚀 Reprendre la session ({curr_u.get('full_name') or curr_u.get('username')})"
        if st.button(c_label, type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()
        if st.button("🔄 Changer de compte / Se déconnecter", use_container_width=True, key="btn_switch_account_landing"):
            st.session_state.current_user = None
            st.session_state.is_authenticated = False
            st.session_state.app_entered = True
            st.rerun()
    else:
        if st.button("🚀 C'est parti !", type="primary", use_container_width=True, key="btn_start_app"):
            st.session_state.app_entered = True
            st.rerun()

    render_html("""
        <div style="text-align: center; color: #64748B; font-size: 0.74rem; margin-top: 1.8rem; letter-spacing: 0.03em;">
            CaliPerf Pro v2.1 • Architecture Modulaire & Navigation Tactile Fluide
        </div>
    """)


def render_auth_portal() -> None:
    """Affiche le portail de connexion et d'inscription."""
    render_html("""
        <div style="text-align: center; margin-top: 0.8rem; margin-bottom: 1.3rem;">
            <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 9999px; padding: 4px 14px; margin-bottom: 0.6rem;">
                <span style="font-size: 13px;">🔐</span>
                <span style="color: #00E5FF; font-weight: 700; font-size: 0.74rem; letter-spacing: 0.05em; text-transform: uppercase;">Authentification</span>
            </div>
            <h2 style="font-size: 1.85rem; font-weight: 800; letter-spacing: -0.025em; margin: 0 0 0.3rem 0; color: #F8FAFC;">
                Espace Membres CaliPerf
            </h2>
            <p style="color: #94A3B8; font-size: 0.88rem; max-width: 460px; margin: 0 auto;">
                Accédez à votre cockpit Coach / Administrateur ou consultez vos repères 3D.
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
                    help="Connexion directe en Administrateur Principal",
                    use_container_width=True
                )

            if btn_login:
                if not l_user or not l_pass:
                    st.warning("Veuillez renseigner votre identifiant et votre mot de passe.")
                else:
                    auth_u = authenticate_user(l_user, l_pass, st.session_state.db.get("users", {}))
                    if auth_u:
                        st.session_state.current_user = auth_u
                        st.session_state.is_authenticated = True
                        st.toast(f"✅ Bienvenue, {auth_u['full_name']} !")
                        time.sleep(0.25)
                        st.rerun()
                    else:
                        st.error("Identifiant ou mot de passe incorrect.")

            if btn_quick_admin:
                admin_u = st.session_state.db.get("users", {}).get("admin", get_default_admin())
                st.session_state.current_user = admin_u
                st.session_state.is_authenticated = True
                st.toast("✅ Connecté en tant qu'Administrateur Principal")
                time.sleep(0.25)
                st.rerun()

    with tab_register:
        render_html("<small style='color:#94A3B8;'>Créez votre compte pour sauvegarder vos analyses et enrichir votre répertoire de figures.</small>")
        with st.form("form_register_user", clear_on_submit=False):
            reg_role = st.radio("Je suis :", ["🏋️ Coach", "🤸 Élève"], horizontal=True)
            reg_full_name = st.text_input("Nom complet / Prénom :", placeholder="ex: Alexandre Coach")
            reg_username = st.text_input("Identifiant unique (login) :", placeholder="ex: coach_alex")

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
                    role_str = "coach" if "coach" in reg_role.lower() else "eleve"
                    if "users" not in st.session_state.db:
                        st.session_state.db["users"] = {}
                    ok_r, msg_r, new_usr = register_user(
                        reg_username,
                        reg_pass1,
                        role_str,
                        reg_full_name,
                        avatar_b64,
                        st.session_state.db["users"]
                    )
                    if ok_r and new_usr:
                        save_db(st.session_state.db)
                        st.session_state.current_user = new_usr
                        st.session_state.is_authenticated = True
                        st.success(f"✅ {msg_r} Bienvenue, {new_usr['full_name']} !")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error(msg_r)

    render_html("<div style='height: 10px;'></div>")
    if st.button("👈 Revenir à la page d'accueil", use_container_width=True):
        st.session_state.app_entered = False
        st.rerun()
