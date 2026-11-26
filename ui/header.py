"""
ui/header.py - Barre supérieure épurée (Sortie haut-gauche, Marque, Profil utilisateur)
et indicateur visuel de navigation tactile.
"""

import html
import streamlit as st

from core.auth import get_default_admin, get_role_badge_info, render_avatar_html
from ui.theme import render_html


def render_app_header() -> None:
    """Affiche le bandeau supérieur compact : bouton de sortie à gauche, marque au centre, profil à droite."""
    curr_u = st.session_state.current_user or get_default_admin()
    u_name = html.escape(str(curr_u.get("full_name") or curr_u.get("username", "Utilisateur")))
    u_role = curr_u.get("role", "admin")
    u_avatar = curr_u.get("avatar", "")
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role)

    col_exit, col_brand, col_u_info = st.columns([0.55, 2.3, 2.15])

    with col_exit:
        render_html('<span id="caliperf-header-exit-marker" style="display:none;"></span>')
        if st.button("🚪", key="btn_exit_to_home", help="Revenir à l'écran d'accueil", use_container_width=True):
            st.session_state.app_entered = False
            st.rerun()

    with col_brand:
        render_html("""
            <div style="display:flex;align-items:center;gap:9px;padding:2px 0;">
                <div style="background:linear-gradient(135deg,#00E5FF,#0EA5E9);width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,229,255,0.28);flex-shrink:0;">
                    <span style="font-size:15px;">⚡</span>
                </div>
                <div style="line-height:1.15;min-width:0;">
                    <div style="display:flex;align-items:center;gap:4px;white-space:nowrap;">
                        <span style="font-size:1.05rem;font-weight:800;letter-spacing:-0.025em;color:#F8FAFC;">CALIPERF</span>
                        <span style="color:#00E5FF;font-weight:800;font-size:1.05rem;">PRO</span>
                    </div>
                    <div style="font-size:0.62rem;color:#64748B;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">
                        3D Telemetry
                    </div>
                </div>
            </div>
        """)

    with col_u_info:
        avatar_html = render_avatar_html(u_avatar, u_name, size=32)
        u_card_html = (
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 9px;'
            f'background:rgba(13,18,30,0.85);border-radius:12px;border:1px solid rgba(255,255,255,0.09);'
            f'justify-content:flex-start;min-width:0;">'
            f'{avatar_html}'
            f'<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">'
            f'<b style="font-size:0.8rem;color:#F8FAFC;display:block;line-height:1.2;overflow:hidden;text-overflow:ellipsis;">{u_name}</b>'
            f'<span class="{role_badge_cls}" style="font-size:0.62rem;padding:1px 6px;">{role_icon} {role_label}</span>'
            f'</div></div>'
        )
        st.markdown(u_card_html, unsafe_allow_html=True)


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
