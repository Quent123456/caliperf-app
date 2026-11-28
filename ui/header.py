"""
ui/header.py - Barre supérieure responsive sur une seule ligne :
- Gauche : bouton compact 🚪 + titre CALIPERF sans retour à la ligne
- Droite : pilule profil (avatar 28px + nom tronqué max 130px + rôle) + bouton 👤 compact
"""

import html
import streamlit as st

from core.auth import get_role_badge_info, normalize_role, render_avatar_html
from core.database import get_coach_athletes, set_active_athlete_in_session
from ui.profile_dialog import open_profile_modal
from ui.theme import render_empty_state, render_html


def render_app_header() -> None:
    """Affiche le bandeau supérieur compact sur une seule ligne sans troncature mobile."""
    curr_u = st.session_state.get("current_user") or {
        "username": "coach",
        "full_name": "Coach",
        "role": "coach",
        "avatar": "",
    }
    raw_full = str(curr_u.get("full_name") or curr_u.get("username", "Coach")).strip()
    short_label = raw_full if len(raw_full) <= 14 else str(curr_u.get("username") or raw_full.split()[0])
    u_name = html.escape(short_label)
    u_role = curr_u.get("role", "athlete")
    u_avatar = curr_u.get("avatar_b64") or curr_u.get("avatar", "")
    role_label, role_badge_cls, role_icon = get_role_badge_info(u_role, str(curr_u.get("username", "")))

    col_exit, col_brand, col_avatar, col_prof_btn = st.columns([0.46, 1.45, 1.9, 0.46])

    with col_exit:
        render_html('<span id="caliperf-header-exit-marker" style="display:none;"></span>')
        if st.button("🚪", key="btn_exit_to_home", help="Revenir à l'écran d'accueil", use_container_width=True):
            st.session_state.app_entered = False
            st.rerun()

    with col_brand:
        brand_html = (
            '<div style="display:flex;align-items:center;gap:6px;padding:2px 0;min-width:0;">'
            '<div style="background:linear-gradient(135deg,#00E5FF,#0EA5E9);width:26px;height:26px;border-radius:7px;'
            'display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,229,255,0.28);flex-shrink:0;">'
            '<span style="font-size:12px;">⚡</span>'
            '</div>'
            '<span style="font-size:0.95rem;font-weight:800;letter-spacing:-0.02em;color:#F8FAFC;white-space:nowrap;">CALIPERF</span>'
            '</div>'
        )
        st.markdown(brand_html, unsafe_allow_html=True)

    with col_avatar:
        avatar_html = render_avatar_html(u_avatar, u_name, size=28)
        u_card_html = (
            '<div style="display:flex;align-items:center;gap:6px;padding:3px 8px;'
            'background:rgba(13,18,30,0.88);border-radius:999px;border:1px solid rgba(255,255,255,0.09);'
            'justify-content:flex-start;min-width:0;max-width:100%;margin-left:auto;">'
            f'{avatar_html}'
            '<div class="cali-hdr-name" style="min-width:0;max-width:130px;overflow:hidden;">'
            f'<b style="font-size:0.74rem;color:#F8FAFC;display:block;line-height:1.12;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{u_name}</b>'
            f'<span class="{role_badge_cls}" style="font-size:0.54rem;padding:0px 5px;line-height:1.25;">{role_icon} {role_label}</span>'
            '</div></div>'
        )
        st.markdown(u_card_html, unsafe_allow_html=True)

    with col_prof_btn:
        if st.button("👤", key="btn_open_profile_header", help="Mon profil, statut & photo", use_container_width=True):
            open_profile_modal()


def render_active_athlete_pill() -> None:
    """Affiche pour le coach une pilule compacte avec sélecteur rapide en 1 tap sous le header."""
    curr_u = st.session_state.get("current_user")
    if not curr_u or normalize_role(curr_u.get("role", "athlete")) != "coach":
        return

    u_id = int(curr_u["id"])
    profile_by_id = st.session_state.get("selectable_profiles_map")
    option_ids = st.session_state.get("selectable_profile_ids")
    if not profile_by_id or not option_ids:
        coach_athletes = get_coach_athletes(u_id)
        profiles = [curr_u] + coach_athletes
        profile_by_id = {int(p["id"]): p for p in profiles}
        option_ids = [int(p["id"]) for p in profiles]

    cur_aid = int(
        st.session_state.get("selected_athlete_id")
        or st.session_state.get("active_athlete_id")
        or u_id
    )
    if cur_aid not in profile_by_id:
        cur_aid = u_id
    st.session_state["header_active_athlete_select"] = cur_aid
    active_p = profile_by_id[cur_aid]
    st.session_state["active_athlete_profile"] = active_p

    is_self = (cur_aid == u_id)
    pill_badge_cls = "badge-cyan" if is_self else "badge-lime"
    pill_role_txt = "Moi-même" if is_self else f"Élève • {float(active_p.get('bodyweight_kg', 70.0) or 70.0):.0f} kg"

    def _on_header_athlete_change() -> None:
        chosen = st.session_state.get("header_active_athlete_select")
        if chosen is not None:
            cid = int(chosen)
            set_active_athlete_in_session(cid, sync_widgets=True)
            if cid in profile_by_id:
                st.session_state["active_athlete_profile"] = profile_by_id[cid]

    c_pill, c_sel = st.columns([0.95, 1.55])
    with c_pill:
        render_html(
            f'<span id="caliperf-athlete-pill-marker" style="display:none;"></span>'
            f'<div style="display:flex;align-items:center;gap:6px;white-space:nowrap;">'
            f'<span style="font-size:0.74rem;font-weight:700;color:#94A3B8;">🎯 Suivi</span>'
            f'<span class="{pill_badge_cls} cali-tabular" style="font-size:0.65rem;padding:2px 7px;">{html.escape(pill_role_txt)}</span>'
            f'</div>'
        )
    with c_sel:
        st.selectbox(
            "Athlète actif :",
            options=option_ids,
            format_func=lambda pid: (
                f"🏋️ Moi-même ({profile_by_id[pid]['full_name']})"
                if pid == u_id else
                f"🤸 {profile_by_id[pid]['full_name']} ({float(profile_by_id[pid].get('bodyweight_kg', 70.0) or 70.0):.0f} kg)"
            ),
            key="header_active_athlete_select",
            label_visibility="collapsed",
            on_change=_on_header_athlete_change,
        )


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
