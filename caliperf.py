"""
CaliPerf Pro - Cockpit Biomécanique 3D, Contrôle Qualité & Suivi Longitudinal SQL.
Point d'entrée modulaire : persistance SQLAlchemy (PostgreSQL / SQLite), session signée F5,
sélecteur d'athlète latéral, moteur de swipe fluide V6 et 5 compartiments métier.
"""

import os
import sys
import streamlit as st

_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

st.set_page_config(
    page_title="CaliPerf Pro | Studio Biomécanique 3D",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import importlib
import core.database as _core_db
if not hasattr(_core_db, "set_active_athlete_in_session"):
    importlib.reload(_core_db)

from core.auth import normalize_role
from core.database import (
    get_coach_athletes,
    get_user_by_id,
    init_session_state,
    set_active_athlete_in_session,
)
from ui.theme import inject_swipe_engine, inject_theme
from ui.landing import render_auth_portal, render_landing_page

# 1. Initialisation SQL, restauration de session (?session= sur F5) et Design System
init_session_state()
inject_theme()

# 2. Accueil & Portail d'authentification
if not st.session_state.app_entered:
    render_landing_page()
    st.stop()

if st.session_state.current_user is None:
    render_auth_portal()
    inject_swipe_engine(stage="auth")
    st.stop()

# 3. Sélecteur d'athlète latéral pour le Coach (isolation stricte sur son coach_id)
curr_user = st.session_state.current_user
curr_role = normalize_role(curr_user.get("role", "athlete"))

if curr_role == "coach":
    coach_athletes = get_coach_athletes(int(curr_user["id"]))
    selectable_profiles = [curr_user] + coach_athletes
    profile_by_id = {int(p["id"]): p for p in selectable_profiles}
    cur_active_id = int(st.session_state.get("active_athlete_id") or curr_user["id"])
    if cur_active_id not in profile_by_id:
        cur_active_id = int(curr_user["id"])
    st.session_state["active_athlete_id"] = cur_active_id
    st.session_state.pop("_sync_athlete_widgets", None)
    # Synchroniser les deux clés de selectbox AVANT leur instanciation
    st.session_state["sidebar_active_athlete_select"] = cur_active_id
    st.session_state["stats_athlete_select"] = cur_active_id

    option_ids = [int(p["id"]) for p in selectable_profiles]
    st.session_state["selectable_profiles_map"] = profile_by_id
    st.session_state["selectable_profile_ids"] = option_ids

    def _on_sidebar_athlete_change() -> None:
        chosen = st.session_state.get("sidebar_active_athlete_select")
        if chosen is not None:
            set_active_athlete_in_session(int(chosen), sync_widgets=True)

    with st.sidebar:
        st.markdown("### 🎯 Athlète actif")
        selected_id = st.selectbox(
            "Basculer sur un suivi :",
            options=option_ids,
            format_func=lambda pid: (
                f"🏋️ Moi-même ({profile_by_id[pid]['full_name']})"
                if pid == int(curr_user["id"]) else
                f"🤸 {profile_by_id[pid]['full_name']} ({profile_by_id[pid]['bodyweight_kg']:.0f} kg)"
            ),
            key="sidebar_active_athlete_select",
            on_change=_on_sidebar_athlete_change,
        )
        active_profile = profile_by_id[int(selected_id)]
        st.session_state["active_athlete_profile"] = active_profile
        st.caption(
            f"Code invitation coach : **{curr_user.get('invite_code') or '—'}**\n\n"
            f"PDC actif : **{active_profile.get('bodyweight_kg', 70.0):.1f} kg**"
        )
else:
    st.session_state.active_athlete_id = int(curr_user["id"])
    fresh_u = get_user_by_id(int(curr_user["id"])) or curr_user
    st.session_state["active_athlete_profile"] = fresh_u

# 4. Chargement des 5 compartiments après connexion
from ui.header import render_app_header, render_swipe_hud_and_anchor
from ui.tab_studio import render_tab_studio
from ui.tab_calibration import render_tab_calibration
from ui.tab_stats import render_tab_stats
from ui.tab_athletes import render_tab_athletes
from ui.tab_settings import render_tab_settings

render_app_header()
render_swipe_hud_and_anchor(num_tabs=5)

tab_studio, tab_calib, tab_stats, tab_athletes, tab_settings = st.tabs([
    "🎥 Studio",
    "📐 Calibrage 3D",
    "📊 Stats & ACWR",
    "👥 Athlètes",
    "⚙️ Réglages"
])

with tab_studio:
    render_tab_studio()

with tab_calib:
    render_tab_calibration()

with tab_stats:
    render_tab_stats()

with tab_athletes:
    render_tab_athletes()

with tab_settings:
    render_tab_settings()

# 5. Injection du moteur de swipe V6 après montage complet des 5 onglets
redirect_idx = st.session_state.pop("_redirect_tab_idx", None)
inject_swipe_engine(stage="main", redirect_tab_idx=redirect_idx)
