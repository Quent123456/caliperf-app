"""
ui/header.py - Barre supérieure de télémétrie et indicateur visuel de navigation swipe.
"""

import html
import streamlit as st

from core.auth import get_default_admin, get_role_badge_info, render_avatar_html
from ui.theme import render_html


def render_app_header() -> None:
    """Affiche le bandeau supérieur compact (Marque, Profil connecté, Actions rapides)."""
    curr_u = st.session_state.current_user or get_default_admin()
    u_name = html.escape(str(curr_u.get("full_name") or curr_u.get("username", "Utilisateur")))
    u_role = curr_u.get("role", "admin")
    u_avatar = curr_u.get("avatar", "")
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role)

    col_brand, col_u_info, col_nav_actions = st.columns([2.3, 2.3, 1.3])

    with col_brand:
        render_html("""
            <div style="display:flex;align-items:center;gap:10px;padding:2px 0;">
                <div style="background:linear-gradient(135deg,#00E5FF,#0EA5E9);width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,229,255,0.3);flex-shrink:0;">
                    <span style="font-size:16px;">⚡</span>
                </div>
                <div style="line-height:1.15;">
                    <div style="display:flex;align-items:center;gap:5px;">
                        <span style="font-size:1.12rem;font-weight:800;letter-spacing:-0.025em;color:#F8FAFC;">CALIPERF</span>
                        <span style="color:#00E5FF;font-weight:800;font-size:1.12rem;">PRO</span>
                    </div>
                    <div style="font-size:0.65rem;color:#64748B;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;">
                        3D Telemetry Studio
                    </div>
                </div>
            </div>
        """)

    with col_u_info:
        avatar_html = render_avatar_html(u_avatar, u_name, size=34)
        u_card_html = (
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 10px;'
            f'background:rgba(13,18,30,0.85);border-radius:12px;border:1px solid rgba(255,255,255,0.09);">'
            f'{avatar_html}'
            f'<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
            f'<b style="font-size:0.83rem;color:#F8FAFC;display:block;line-height:1.2;">{u_name}</b>'
            f'<span class="{role_badge_cls}" style="font-size:0.64rem;padding:1px 7px;">{role_icon} {role_label}</span>'
            f'</div></div>'
        )
        st.markdown(u_card_html, unsafe_allow_html=True)

    with col_nav_actions:
        col_na1, col_na2 = st.columns(2)
        with col_na1:
            if st.button("🏠", key="btn_return_home", help="Page d'accueil", use_container_width=True):
                st.session_state.app_entered = False
                st.rerun()
        with col_na2:
            if st.button("🚪", key="btn_logout", help="Se déconnecter", use_container_width=True):
                st.session_state.current_user = None
                st.session_state.is_authenticated = False
                st.session_state.app_entered = False
                st.rerun()


def render_swipe_hud_and_anchor(num_tabs: int = 5) -> None:
    """
    Affiche l'indicateur de pagination dynamique (pastilles synchronisées au swipe)
    suivi immédiatement de l'ancre DOM pour la barre d'onglets principale.
    """
    dots_html = "".join('<span class="cali-swipe-dot"></span>' for _ in range(num_tabs))
    render_html(f"""
        <div class="cali-swipe-hud">
            <span class="cali-swipe-label">◀</span>
            <div id="caliperf-swipe-dots" class="cali-swipe-dots">{dots_html}</div>
            <span class="cali-swipe-label">▶ Glisser pour naviguer</span>
        </div>
        <div id="caliperf-main-tabs-anchor" style="display:none;"></div>
    """)
