"""
ui/header.py - Barre supérieure épurée (Sortie haut-gauche, Marque, Profil cliquable sans chevauchement mobile)
et indicateur visuel de navigation tactile.
"""

import html
import streamlit as st

from core.auth import get_role_badge_info, render_avatar_html
from ui.profile_dialog import open_profile_modal
from ui.theme import render_html


def render_app_header() -> None:
    """Affiche le bandeau supérieur compact sur 4 colonnes plates sans chevauchement mobile."""
    curr_u = st.session_state.get("current_user") or {
        "username": "coach",
        "full_name": "Coach",
        "role": "coach",
        "avatar": "",
    }
    u_name = html.escape(str(curr_u.get("full_name") or curr_u.get("username", "Utilisateur")))
    u_role = curr_u.get("role", "athlete")
    u_avatar = curr_u.get("avatar_b64") or curr_u.get("avatar", "")
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role, str(curr_u.get("username", "")))

    col_exit, col_brand, col_avatar, col_prof_btn = st.columns([0.55, 2.1, 1.35, 0.52])

    with col_exit:
        render_html('<span id="caliperf-header-exit-marker" style="display:none;"></span>')
        if st.button("🚪", key="btn_exit_to_home", help="Revenir à l'écran d'accueil", use_container_width=True):
            st.session_state.app_entered = False
            st.rerun()

    with col_brand:
        brand_html = (
            '<div style="display:flex;align-items:center;gap:7px;padding:2px 0;min-width:0;overflow:hidden;">'
            '<div style="background:linear-gradient(135deg,#00E5FF,#0EA5E9);width:28px;height:28px;border-radius:8px;'
            'display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,229,255,0.28);flex-shrink:0;">'
            '<span style="font-size:13px;">⚡</span>'
            '</div>'
            '<div style="line-height:1.1;min-width:0;overflow:hidden;">'
            '<div style="display:flex;align-items:center;gap:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            '<span style="font-size:0.95rem;font-weight:800;letter-spacing:-0.025em;color:#F8FAFC;">CALIPERF</span>'
            '<span style="color:#00E5FF;font-weight:800;font-size:0.95rem;">PRO</span>'
            '</div>'
            '<div style="font-size:0.56rem;color:#64748B;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;">3D Telemetry</div>'
            '</div></div>'
        )
        st.markdown(brand_html, unsafe_allow_html=True)

    with col_avatar:
        avatar_html = render_avatar_html(u_avatar, u_name, size=30)
        u_card_html = (
            '<div style="display:flex;align-items:center;gap:6px;padding:3px 7px;'
            'background:rgba(13,18,30,0.88);border-radius:10px;border:1px solid rgba(255,255,255,0.09);'
            'justify-content:flex-start;min-width:0;overflow:hidden;">'
            f'{avatar_html}'
            '<div class="cali-hdr-name" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">'
            f'<b style="font-size:0.74rem;color:#F8FAFC;display:block;line-height:1.15;overflow:hidden;text-overflow:ellipsis;">{u_name}</b>'
            f'<span class="{role_badge_cls}" style="font-size:0.56rem;padding:1px 5px;">{role_icon} {role_label}</span>'
            '</div></div>'
        )
        st.markdown(u_card_html, unsafe_allow_html=True)

    with col_prof_btn:
        if st.button("👤", key="btn_open_profile_header", help="Mon profil, statut & photo", use_container_width=True):
            open_profile_modal()


def render_swipe_hud_and_anchor(num_tabs: int = 5) -> None:
    """Affiche les pastilles de pagination dynamique et l'ancre DOM des onglets principaux."""
    dots_html = "".join('<span class="cali-swipe-dot"></span>' for _ in range(num_tabs))
    render_html(f"""
        <div class="cali-swipe-hud">
            <span class="cali-swipe-label">◀</span>
            <div id="caliperf-swipe-dots" class="cali-swipe-dots">{dots_html}</div>
            <span class="cali-swipe-label">▶ Glisser pour naviguer</span>
        </div>
        <div id="caliperf-main-tabs-anchor" style="display:none;"></div>
    """)
