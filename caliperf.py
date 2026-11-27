"""
CaliPerf Pro - Cockpit Biomécanique 3D, Contrôle Qualité & Suivi Longitudinal SQL.
Point d'entrée haute performance :
- Connexion hybride SQLAlchemy cachée (@st.cache_resource) PostgreSQL / SQLite
- Rendu exclusif de l'onglet actif (Lazy Tab Rendering)
- Moteur de swipe mobile V6 & redirection directe Athlètes -> Stats & ACWR
"""

import importlib
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

import core.database as _core_db
if not hasattr(_core_db, "set_active_athlete_in_session") or not hasattr(_core_db, "purge_demo_athletes_for_coach"):
    importlib.reload(_core_db)

from core.auth import normalize_role
from core.database import (
    get_coach_athletes,
    get_user_by_id,
    init_session_state,
    set_active_athlete_in_session,
)
from ui.theme import inject_swipe_engine, inject_theme, render_html
from ui.landing import render_auth_portal, render_landing_page

MAIN_TABS = [
    "🎥 Studio",
    "📐 Calibrage 3D",
    "📊 Stats & ACWR",
    "👥 Athlètes",
    "⚙️ Réglages",
]

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

# 3. Sélecteur d'athlète latéral & synchronisation AVANT instanciation des widgets
curr_user = st.session_state.current_user
curr_role = normalize_role(curr_user.get("role", "athlete"))

if curr_role == "coach":
    coach_athletes = get_coach_athletes(int(curr_user["id"]))
    selectable_profiles = [curr_user] + coach_athletes
    profile_by_id = {int(p["id"]): p for p in selectable_profiles}
    cur_active_id = int(
        st.session_state.get("selected_athlete_id")
        or st.session_state.get("active_athlete_id")
        or curr_user["id"]
    )
    if cur_active_id not in profile_by_id:
        cur_active_id = int(curr_user["id"])

    st.session_state["active_athlete_id"] = cur_active_id
    st.session_state["selected_athlete_id"] = cur_active_id
    st.session_state.pop("_sync_athlete_widgets", None)
    st.session_state["sidebar_active_athlete_select"] = cur_active_id
    st.session_state["stats_athlete_select"] = cur_active_id
    st.session_state["studio_athlete_select"] = cur_active_id

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
    st.session_state.selected_athlete_id = int(curr_user["id"])
    fresh_u = get_user_by_id(int(curr_user["id"])) or curr_user
    st.session_state["active_athlete_profile"] = fresh_u

# 4. Navigation segmentée + Rendu Exclusif de l'Onglet Actif (Lazy Tab Rendering)
from ui.header import render_app_header, render_swipe_hud_and_anchor

render_app_header()
render_swipe_hud_and_anchor(num_tabs=len(MAIN_TABS))

cur_tab = st.session_state.get("active_tab") or MAIN_TABS[0]
if cur_tab not in MAIN_TABS:
    cur_tab = MAIN_TABS[0]
st.session_state["active_tab"] = cur_tab
st.session_state["nav_active_tab"] = cur_tab


def _on_nav_tab_change() -> None:
    chosen_t = st.session_state.get("nav_active_tab")
    if chosen_t in MAIN_TABS:
        st.session_state["active_tab"] = chosen_t


render_html('<div id="caliperf-nav-marker" class="cali-nav-anchor" style="display:none;"></div>')
selected_tab = st.radio(
    "Navigation principale",
    options=MAIN_TABS,
    horizontal=True,
    label_visibility="collapsed",
    key="nav_active_tab",
    on_change=_on_nav_tab_change,
)
st.session_state["active_tab"] = selected_tab
active_tab_idx = MAIN_TABS.index(selected_tab)

render_html(f'<div id="caliperf-active-view" class="cali-active-view" data-tab-idx="{active_tab_idx}" style="height:0;overflow:hidden;"></div>')

if selected_tab == "🎥 Studio":
    from ui.tab_studio import render_tab_studio
    render_tab_studio()
elif selected_tab == "📐 Calibrage 3D":
    from ui.tab_calibration import render_tab_calibration
    render_tab_calibration()
elif selected_tab == "📊 Stats & ACWR":
    from ui.tab_stats import render_tab_stats
    render_tab_stats()
elif selected_tab == "👥 Athlètes":
    from ui.tab_athletes import render_tab_athletes
    render_tab_athletes()
elif selected_tab == "⚙️ Réglages":
    from ui.tab_settings import render_tab_settings
    render_tab_settings()

# 5. Moteur de swipe V6 synchronisé sur l'onglet actif
inject_swipe_engine(stage="main")
