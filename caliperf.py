"""
CaliPerf Pro - Cockpit Biomécanique 3D, Contrôle Qualité & Suivi Longitudinal SQL.
Point d'entrée haute performance :
- Connexion hybride SQLAlchemy cachée (@st.cache_resource) PostgreSQL / SQLite
- Rendu exclusif de l'onglet actif (Lazy Tab Rendering) sur dock 5 pilules 100% synchronisé
- Moteur de swipe mobile stabilisé (overflow-x: clip, zéro décalage d'écran)
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

# Libellés compacts pour tenir tous les 5 onglets sur un écran smartphone 390px sans scroll horizontal
NAV_DOCK_LABELS = [
    "🎥\nStudio",
    "📐\nCalib",
    "📊\nStats",
    "👥\nÉlèves",
    "⚙️\nRégl.",
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

# 4. Dock de navigation 5 pilules (zéro scroll horizontal, synchronisation Python exacte)
from ui.header import render_app_header, render_swipe_hud_and_anchor

render_app_header()
render_swipe_hud_and_anchor(num_tabs=len(MAIN_TABS))

cur_tab = st.session_state.get("active_tab") or MAIN_TABS[0]
if cur_tab not in MAIN_TABS:
    cur_tab = MAIN_TABS[0]
st.session_state["active_tab"] = cur_tab

nav_cols = st.columns(len(MAIN_TABS))
for idx, (tab_key, dock_lbl) in enumerate(zip(MAIN_TABS, NAV_DOCK_LABELS)):
    with nav_cols[idx]:
        if idx == 0:
            render_html('<span id="caliperf-nav-marker" style="display:none;"></span>')
        is_act = (cur_tab == tab_key)
        if st.button(
            dock_lbl,
            key=f"nav_dock_btn_{idx}",
            type="primary" if is_act else "secondary",
            use_container_width=True,
        ):
            if not is_act:
                st.session_state["active_tab"] = tab_key
                st.rerun()

active_tab_idx = MAIN_TABS.index(cur_tab)
prev_tab_idx = st.session_state.get("_prev_tab_idx", active_tab_idx)
if active_tab_idx > prev_tab_idx:
    anim_dir = "right"
elif active_tab_idx < prev_tab_idx:
    anim_dir = "left"
else:
    anim_dir = "none"
st.session_state["_prev_tab_idx"] = active_tab_idx

render_html(
    f'<div id="caliperf-active-view" class="cali-active-view" '
    f'data-tab-idx="{active_tab_idx}" data-anim-dir="{anim_dir}" '
    f'style="height:0;overflow:hidden;"></div>'
)

# Rendu exclusif de l'onglet actif (Lazy Tab Rendering)
if cur_tab == "🎥 Studio":
    from ui.tab_studio import render_tab_studio
    render_tab_studio()
elif cur_tab == "📐 Calibrage 3D":
    from ui.tab_calibration import render_tab_calibration
    render_tab_calibration()
elif cur_tab == "📊 Stats & ACWR":
    from ui.tab_stats import render_tab_stats
    render_tab_stats()
elif cur_tab == "👥 Athlètes":
    from ui.tab_athletes import render_tab_athletes
    render_tab_athletes()
elif cur_tab == "⚙️ Réglages":
    from ui.tab_settings import render_tab_settings
    render_tab_settings()

# 5. Moteur de swipe V7 stabilisé (aucun décalage horizontal, anti double-swipe)
inject_swipe_engine(stage="main")
