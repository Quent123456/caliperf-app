"""
CaliPerf Pro - Cockpit Biomécanique 3D & Chronométrage TST.
Point d'entrée modulaire : orchestre la configuration, le thème Obsidian,
le moteur de swipe fluide à prévisualisation progressive et les 5 compartiments métier.
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

from core.database import init_session_state
from ui.theme import inject_theme, inject_swipe_engine
from ui.landing import render_landing_page, render_auth_portal

# 1. Initialisation de la session, du Design System et du moteur de navigation tactile
init_session_state()
inject_theme()
inject_swipe_engine()

# 2. Accueil & Portail d'authentification (démarrage instantané sans charger les modules lourds)
if not st.session_state.app_entered:
    render_landing_page()
    st.stop()

if st.session_state.current_user is None:
    render_auth_portal()
    st.stop()

# 3. Chargement à la demande des compartiments métier après connexion
from ui.header import render_app_header, render_swipe_hud_and_anchor
from ui.tab_studio import render_tab_studio
from ui.tab_calibration import render_tab_calibration
from ui.tab_stats import render_tab_stats
from ui.tab_athletes import render_tab_athletes
from ui.tab_settings import render_tab_settings

# 4. En-tête & Barre d'onglets principale avec indicateur de swipe synchronisé
render_app_header()
render_swipe_hud_and_anchor(num_tabs=5)

tab_studio, tab_calib, tab_stats, tab_athletes, tab_settings = st.tabs([
    "🎥 Studio",
    "📐 Calibrage 3D",
    "📊 Stats",
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
