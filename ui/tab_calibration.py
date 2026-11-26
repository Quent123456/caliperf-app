"""
ui/tab_calibration.py - Compartiment 2 : Bibliothèque & Calibrage 3D en 2 étapes.
"""

import re
import time
from datetime import datetime
import numpy as np
import streamlit as st

from core.auth import get_default_admin
from core.database import get_persisted_temp_video_path
from core.calibration import (
    load_baselines_table,
    create_figure_slots,
    save_calibrated_slot,
    reset_slot,
    delete_figure,
    promote_to_master,
    export_baselines_json,
    compute_active_feature_vectors,
    VALID_CAMERA_VIEWS
)
from ui.calibration_tutorial import render_tutorial_button
from ui.theme import render_html


def _render_last_calibration_preview() -> None:
    """Affiche de manière persistante les 6 angles 3D du dernier calibrage effectué."""
    preview = st.session_state.get("last_calib_preview")
    if not preview:
        return

    means = preview.get("means", [])
    stds = preview.get("stds", [])
    rom = preview.get("rom")
    if len(means) < 6 or len(stds) < 6:
        return

    vd_label = "Ventrale (+1, Face au sol)" if means[5] >= 0 else "Dorsale (-1, Dos au sol)"

    with st.container(border=True):
        c_head, c_cls = st.columns([3, 1])
        with c_head:
            render_html(f"""
                <div>
                    <span class="badge-lime">✅ Dernier calibrage validé</span>
                    <h4 style="margin:6px 0 2px 0; font-size:1.02rem; color:#F8FAFC;">
                        📐 {preview.get('exercise')} — Angle {preview.get('camera_view')}
                    </h4>
                </div>
            """)
        with c_cls:
            if st.button("✖ Masquer", key="btn_dismiss_calib_preview", use_container_width=True):
                st.session_state.last_calib_preview = None
                st.rerun()

        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Coude 3D", f"{means[2]:.1f}°", f"± {stds[2]:.1f}°")
        c_m1.metric("Épaule (Flexion)", f"{means[0]:.1f}°", f"± {stds[0]:.1f}°")
        c_m2.metric("Écartement Bras", f"{means[1]:.1f}°", f"± {stds[1]:.1f}°")
        c_m2.metric("Hanche (Align.)", f"{means[3]:.1f}°", f"± {stds[3]:.1f}°")
        c_m3.metric("Inclinaison Tronc", f"{means[4]:.1f}°", f"± {stds[4]:.1f}°")
        c_m3.metric("Orientation", vd_label)

        if rom:
            st.info(
                f"📊 Amplitude dynamique mesurée : Lockout = **{rom['lockout_angle']}°** • "
                f"Inflexion = **{rom['inflection_angle']}°**"
            )


def render_tab_calibration() -> None:
    """Rend l'interface complète de la bibliothèque et du calibrage 3D en 2 étapes."""
    col_calib_title, col_calib_tuto = st.columns([2.6, 1.4])
    with col_calib_title:
        render_html("""
            <div style="margin-bottom: 0.35rem;">
                <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                    📐 Bibliothèque & Calibrage 3D
                </h3>
                <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8; line-height:1.4;">
                    Créez vos mouvements avec 3 emplacements (Face, 3/4, Profil), puis associez une vidéo de référence à chaque angle.
                </p>
            </div>
        """)
    with col_calib_tuto:
        render_tutorial_button(key="btn_tuto_calib_header")

    df_base = load_baselines_table()
    distinct_figures = (
        [str(x).strip() for x in df_base["exercise"].unique() if str(x).strip()]
        if not df_base.empty and "exercise" in df_base.columns else []
    )

    curr_u = st.session_state.current_user or get_default_admin()
    u_role = curr_u.get("role", "admin")
    u_name = curr_u.get("username", "admin")
    is_adm = (u_role == "admin")

    calib_count = len(df_base[df_base["status"] == "calibrated"]) if not df_base.empty and "status" in df_base.columns else 0
    distinct_count = len(distinct_figures)
    total_slots = len(df_base)
    ratio = (calib_count / float(total_slots)) if total_slots > 0 else 0.0

    render_html(f"""
        <div class="cali-card" style="padding: 10px 14px; margin-bottom: 0.7rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <span style="font-size:0.82rem; font-weight:700; color:#F8FAFC;">
                    📚 {distinct_count} figure(s) enregistrée(s)
                </span>
                <span style="font-family:'JetBrains Mono',monospace; font-size:0.78rem; color:#00E5FF; font-weight:700;">
                    {calib_count} / {total_slots} angles calibrés ({int(ratio*100)}%)
                </span>
            </div>
        </div>
    """)
    if total_slots > 0:
        st.progress(min(1.0, max(0.0, ratio)))

    _render_last_calibration_preview()

    # ------------------------------------------------------------------
    # ÉTAPE A : CRÉER UNE FIGURE DANS LA BIBLIOTHÈQUE (3 ANGLES)
    # ------------------------------------------------------------------
    if u_role == "eleve":
        st.info("ℹ️ Mode consultation : En tant qu'élève, vous pouvez consulter les repères 3D des mouvements ci-dessous.")
    else:
        step_title = (
            "1️⃣ Étape A : Créer un mouvement officiel permanent (3 angles)"
            if is_adm else
            "1️⃣ Étape A : Ajouter une figure personnalisée (3 angles)"
        )
        step_desc = (
            "Administrateur principal : vous enrichissez la bibliothèque officielle permanente (non modifiable par les autres coachs)."
            if is_adm else
            "Ajoutez vos propres mouvements à votre répertoire de coach pour les calibrer et les analyser."
        )
        with st.expander(step_title, expanded=(distinct_count == 0)):
            render_html(f"<small style='color:#94A3B8;'>{step_desc}</small>")
            with st.form("form_create_exo_slots", clear_on_submit=True):
                col_new_name, col_new_type = st.columns([1.5, 1])
                with col_new_name:
                    new_exo_input = st.text_input(
                        "Nom de la figure :",
                        placeholder="ex: Full Planche, Maltese, Front Lever, Tractions, Pompes, Hefesto..."
                    )
                with col_new_type:
                    new_exo_type = st.radio("Type de mouvement :", ["Isométrique", "Dynamique"], horizontal=True)

                btn_label = "➕ Créer la figure officielle (3 angles)" if is_adm else "➕ Ajouter ma figure de coach (3 angles)"
                if st.form_submit_button(btn_label, type="primary", use_container_width=True):
                    if not new_exo_input.strip():
                        st.warning("Veuillez saisir un nom pour la figure.")
                    else:
                        c_type = "isometric" if new_exo_type == "Isométrique" else "dynamic"
                        ok_c, msg_c = create_figure_slots(
                            new_exo_input,
                            c_type,
                            owner="admin" if is_adm else u_name,
                            is_master=is_adm
                        )
                        if ok_c:
                            st.success(f"✅ {msg_c}")
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.error(msg_c)

    # ------------------------------------------------------------------
    # RÉPERTOIRE DES MOUVEMENTS CRÉÉS (AVEC RECHERCHE & FILTRES)
    # ------------------------------------------------------------------
    render_html("<h4 style='margin: 0.85rem 0 0.45rem 0; font-size:1rem; font-weight:800; color:#F8FAFC;'>📚 Répertoire des mouvements</h4>")

    if not distinct_figures:
        st.info("ℹ️ Votre bibliothèque est vide pour l'instant. Utilisez l'Étape A ci-dessus pour ajouter vos premières figures !")
    else:
        col_f1, col_f2 = st.columns([1.4, 1.4])
        with col_f1:
            search_q = st.text_input("🔍 Rechercher une figure :", placeholder="ex: Planche, Lever, Dips...", key="calib_search_fig").strip().lower()
        with col_f2:
            filter_mode = st.selectbox(
                "Filtrer :",
                ["Toutes", "En attente ⏳", "Calibrées ✅", "Officielles 👑", "Mes figures 🏋️"],
                key="calib_filter_mode"
            )

        filtered_figs = []
        for fig_name in distinct_figures:
            if search_q and search_q not in fig_name.lower():
                continue
            sub_df = df_base[df_base["exercise"] == fig_name]
            nb_calib = len(sub_df[sub_df["status"] == "calibrated"])
            is_official = bool(sub_df["is_master"].iloc[0]) if "is_master" in sub_df.columns else True
            fig_owner = str(sub_df["owner"].iloc[0]) if "owner" in sub_df.columns else "admin"

            if filter_mode == "En attente ⏳" and nb_calib == 3:
                continue
            if filter_mode == "Calibrées ✅" and nb_calib == 0:
                continue
            if filter_mode == "Officielles 👑" and not is_official:
                continue
            if filter_mode == "Mes figures 🏋️" and (is_official or fig_owner.lower() != u_name.lower()):
                continue

            filtered_figs.append(fig_name)

        if not filtered_figs:
            st.caption("Aucune figure ne correspond à ce filtre.")
        else:
            for fig_name in filtered_figs:
                sub_df = df_base[df_base["exercise"] == fig_name]
                fig_type = sub_df["type"].iloc[0] if not sub_df.empty else "isometric"
                type_label = "Isométrique" if fig_type == "isometric" else "Dynamique"

                is_official = bool(sub_df["is_master"].iloc[0]) if "is_master" in sub_df.columns else True
                fig_owner = str(sub_df["owner"].iloc[0]) if "owner" in sub_df.columns else "admin"

                calib_rows = sub_df[sub_df["status"] == "calibrated"]
                nb_calib = len(calib_rows)
                calib_icon = "🟢" if nb_calib == 3 else ("🟡" if nb_calib > 0 else "⚪")
                calib_ratio = f"{nb_calib}/3 validé{'s' if nb_calib > 1 else ''}"
                clean_key = re.sub(r"[^a-zA-Z0-9]+", "_", fig_name.lower()).strip("_")

                owner_badge = "👑 Officiel" if is_official else f"🏋️ @{fig_owner}"
                exp_header = f"{calib_icon} {fig_name}  •  {type_label}  [{owner_badge}]  ({calib_ratio})"

                with st.expander(exp_header, expanded=False):
                    # Pastilles visuelles rapides des 3 angles
                    pills_parts = []
                    for v_name in VALID_CAMERA_VIEWS:
                        v_row = sub_df[sub_df["camera_view"] == v_name]
                        is_cal = not v_row.empty and v_row.iloc[0]["status"] == "calibrated"
                        dot_cls = "badge-lime" if is_cal else "badge-amber"
                        dot_ico = "✅" if is_cal else "⏳"
                        pills_parts.append(f'<span class="{dot_cls}">{dot_ico} {v_name}</span>')
                    render_html(f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;'>{''.join(pills_parts)}</div>")

                    for v_name in VALID_CAMERA_VIEWS:
                        v_row = sub_df[sub_df["camera_view"] == v_name]
                        is_cal = not v_row.empty and v_row.iloc[0]["status"] == "calibrated"

                        c_v1, c_v2, c_v3 = st.columns([1.2, 2, 1.2])
                        with c_v1:
                            render_html(f"<b>Angle {v_name}</b>")
                        with c_v2:
                            if is_cal:
                                render_html("<span style='color:#34D399; font-weight:700;'>✅ Calibré</span>")
                            else:
                                render_html("<span style='color:#94A3B8;'>⏳ En attente de vidéo</span>")
                        with c_v3:
                            if is_cal:
                                slot_id = v_row.iloc[0]["id"]
                                can_reset = (is_adm) or (not is_official and fig_owner.lower() == u_name.lower())
                                if can_reset:
                                    if st.button("🔄 Réinit.", key=f"reset_{slot_id}", help=f"Réinitialiser l'angle {v_name}", use_container_width=True):
                                        ok_r, msg_r = reset_slot(slot_id, user_role=u_role, username=u_name)
                                        if ok_r:
                                            st.toast(f"✅ {msg_r}")
                                            time.sleep(0.25)
                                            st.rerun()
                                        else:
                                            st.error(msg_r)
                                else:
                                    st.caption("🔒 Verrouillé")
                            else:
                                st.caption("—")

                    render_html("<div style='height:8px;'></div>")

                    if is_official:
                        if is_adm:
                            _, col_d_btn = st.columns([2.5, 1.5])
                            with col_d_btn:
                                if st.button("🗑️ Supprimer la figure", key=f"del_fig_{clean_key}", help=f"Supprimer définitivement {fig_name}", use_container_width=True):
                                    _, msg_d = delete_figure(fig_name, user_role=u_role, username=u_name)
                                    st.toast(f"✅ {msg_d}")
                                    time.sleep(0.25)
                                    st.rerun()
                        else:
                            render_html("<small style='color:#00E5FF;'>🔒 Figure officielle permanente (Lecture seule)</small>")
                    else:
                        if is_adm:
                            col_prom, col_del_c = st.columns([2.2, 1.3])
                            with col_prom:
                                if st.button("🌟 Intégrer à la base officielle", key=f"prom_{clean_key}", help="Rendre cette figure permanente et officielle", use_container_width=True):
                                    _, msg_p = promote_to_master(fig_name)
                                    st.toast(f"✅ {msg_p}")
                                    time.sleep(0.25)
                                    st.rerun()
                            with col_del_c:
                                if st.button("🗑️ Supprimer", key=f"del_fig_{clean_key}", use_container_width=True):
                                    _, msg_d = delete_figure(fig_name, user_role=u_role, username=u_name)
                                    st.toast(f"✅ {msg_d}")
                                    time.sleep(0.25)
                                    st.rerun()
                        elif u_role == "coach" and fig_owner.lower() == u_name.lower():
                            _, col_d_btn = st.columns([2.5, 1.5])
                            with col_d_btn:
                                if st.button("🗑️ Supprimer ma figure", key=f"del_fig_{clean_key}", use_container_width=True):
                                    _, msg_d = delete_figure(fig_name, user_role=u_role, username=u_name)
                                    st.toast(f"✅ {msg_d}")
                                    time.sleep(0.25)
                                    st.rerun()
                        else:
                            render_html(f"<small style='color:#94A3B8;'>Figure créée par @{fig_owner} (Lecture seule)</small>")

    # ------------------------------------------------------------------
    # ÉTAPE B : ASSOCIER UNE VIDÉO DE CALIBRAGE À UN EMPLACEMENT
    # ------------------------------------------------------------------
    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin:16px 0 12px 0;'>")
    with st.expander("2️⃣ Étape B : Associer une vidéo de calibrage à un emplacement", expanded=(distinct_count > 0)):
        if not distinct_figures:
            st.warning("⚠️ Veuillez d'abord créer au moins une figure dans l'Étape A ci-dessus.")
        else:
            col_sel_exo, col_sel_ang = st.columns([1.5, 1])
            with col_sel_exo:
                chosen_exo = st.selectbox("Figure à calibrer :", distinct_figures, key="select_calib_exo_step_b")
            with col_sel_ang:
                sub_chosen = df_base[df_base["exercise"] == chosen_exo]

                def _fmt_angle_status(ang):
                    match_ang = sub_chosen[sub_chosen["camera_view"] == ang]
                    if not match_ang.empty and match_ang.iloc[0]["status"] == "calibrated":
                        return f"{ang} (✅ Calibré)"
                    return f"{ang} (⏳ En attente)"

                chosen_angle = st.selectbox(
                    "Angle de vue :",
                    VALID_CAMERA_VIEWS,
                    format_func=_fmt_angle_status,
                    key="select_calib_angle_step_b"
                )

            calib_video_upload = st.file_uploader(
                f"Vidéo de calibrage pour {chosen_exo} ({chosen_angle}) — 3 à 5 s recommandées :",
                type=["mp4", "mov", "avi"],
                key="uploader_calib_video_step_b"
            )

            if calib_video_upload is not None:
                if st.button(f"🚀 Analyser et enregistrer ce calibrage ({chosen_angle})", type="primary", use_container_width=True, key="btn_run_calib_step_b"):
                    with st.spinner("Extraction cinématique MediaPipe 3D, auto-trimming et calcul biomécanique..."):
                        try:
                            from core.biomechanics_3d import extract_3d_kinematics_from_video
                            from core.segmentation import segment_and_classify_video
                            temp_cal_path = get_persisted_temp_video_path(calib_video_upload)
                            kin_cal = extract_3d_kinematics_from_video(temp_cal_path)
                            seg_cal = segment_and_classify_video(kin_cal)

                            fig_type_current = sub_chosen["type"].iloc[0] if not sub_chosen.empty else seg_cal["type"]
                            means_cal, stds_cal = compute_active_feature_vectors(kin_cal, seg_cal["effort_window"])

                            rom_data = None
                            if fig_type_current == "dynamic":
                                filt_c = kin_cal["features_filtered"]
                                s_i = seg_cal["effort_window"]["start_idx"]
                                e_i = seg_cal["effort_window"]["end_idx"]
                                el_act = filt_c["elbow_angle"][s_i:e_i + 1]
                                rom_data = {
                                    "primary_joint": "elbow_angle",
                                    "min_amplitude_deg": 20.0,
                                    "lockout_angle": round(float(np.max(el_act)), 1) if len(el_act) > 0 else 165.0,
                                    "inflection_angle": round(float(np.min(el_act)), 1) if len(el_act) > 0 else 90.0,
                                    "min_rep_duration_sec": 0.4,
                                    "max_rep_duration_sec": 9.0
                                }

                            ok_save, msg_save = save_calibrated_slot(
                                exercise_name=chosen_exo,
                                camera_view=chosen_angle,
                                exo_type=fig_type_current,
                                mean_features=means_cal.tolist(),
                                std_features=stds_cal.tolist(),
                                rom_bounds=rom_data,
                                owner="admin" if is_adm else u_name
                            )

                            if ok_save:
                                st.session_state.last_calib_preview = {
                                    "exercise": chosen_exo,
                                    "camera_view": chosen_angle,
                                    "means": [round(float(x), 1) for x in means_cal],
                                    "stds": [round(float(x), 1) for x in stds_cal],
                                    "rom": rom_data
                                }
                                st.toast(f"✅ {msg_save}")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(msg_save)
                        except Exception as err_c:
                            st.error(f"Erreur d'analyse de calibrage : {err_c}")

    # Barre utilitaire discrète en bas de page
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        if st.button("🔄 Synchroniser depuis Google Sheets", key="btn_refresh_calib_sheets", use_container_width=True):
            load_baselines_table(force_refresh=True)
            st.toast("✅ Bibliothèque actualisée")
            st.rerun()
    with col_u2:
        json_backup = export_baselines_json().encode("utf-8")
        st.download_button(
            "💾 Exporter sauvegarde JSON (Baselines)",
            data=json_backup,
            file_name=f"baselines_3d_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
            key="btn_export_baselines_json"
        )
