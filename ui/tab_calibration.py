"""
ui/tab_calibration.py - Compartiment 2 : Bibliothèque & Calibrage 3D SQL avec Quality Control Gate.
"""

from datetime import datetime
import re
import time
import numpy as np
import streamlit as st

from core.auth import is_master_coach, normalize_role
from core.calibration import (
    VALID_CAMERA_VIEWS,
    compute_active_feature_vectors,
    create_figure_slots,
    delete_figure,
    export_baselines_json,
    load_baselines_table,
    reset_slot,
    save_calibrated_slot,
    toggle_figure_sharing,
)
from core.video_io import temporary_video_file
from services.export_service import (
    build_baselines_export_dataframe,
    export_dataframe_to_csv_bytes,
)
from ui.calibration_qc import render_qc_save_gate, render_quality_diagnostic_card
from ui.calibration_tutorial import render_tutorial_button
from ui.theme import render_empty_state, render_html


def _render_last_calibration_preview() -> None:
    """Affiche les 6 angles 3D + quality_score du dernier calibrage validé."""
    preview = st.session_state.get("last_calib_preview")
    if not preview:
        return

    means = preview.get("means", [])
    stds = preview.get("stds", [])
    rom = preview.get("rom")
    q_score = preview.get("quality_score")
    if len(means) < 6 or len(stds) < 6:
        return

    vd_label = "Face au sol" if means[5] >= 0 else "Dos au sol"
    score_badge = f" • Score {q_score}/100" if q_score is not None else ""

    with st.container(border=True):
        c_head, c_cls = st.columns([3, 1])
        with c_head:
            render_html(f"""
                <div>
                    <span class="badge-lime cali-tabular">Figure enregistrée{score_badge}</span>
                    <h4 style="margin:6px 0 2px 0; font-size:1.02rem; color:#F8FAFC;">
                        {preview.get('exercise')} — Angle {preview.get('camera_view')}
                    </h4>
                </div>
            """)
        with c_cls:
            if st.button("Masquer", key="btn_dismiss_calib_preview", use_container_width=True):
                st.session_state.last_calib_preview = None
                st.rerun()

        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Coude", f"{means[2]:.1f}°", f"± {stds[2]:.1f}°")
        c_m1.metric("Épaule", f"{means[0]:.1f}°", f"± {stds[0]:.1f}°")
        c_m2.metric("Écartement bras", f"{means[1]:.1f}°", f"± {stds[1]:.1f}°")
        c_m2.metric("Hanche", f"{means[3]:.1f}°", f"± {stds[3]:.1f}°")
        c_m3.metric("Inclinaison buste", f"{means[4]:.1f}°", f"± {stds[4]:.1f}°")
        c_m3.metric("Orientation", vd_label)

        if rom:
            st.info(
                f"Amplitude mesurée : Extension = **{rom['lockout_angle']}°** • "
                f"Flexion = **{rom['inflection_angle']}°**"
            )


def render_tab_calibration() -> None:
    """Rend l'interface complète des figures de référence et de vérification vidéo."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        st.warning("Connectez-vous pour accéder aux figures de référence.")
        return

    u_id = int(curr_u["id"])
    u_role = normalize_role(curr_u.get("role", "athlete"))
    is_coach = (u_role == "coach")
    is_adm = is_master_coach(curr_u)

    col_calib_title, col_calib_tuto = st.columns([2.4, 1.6])
    with col_calib_title:
        render_html("""
            <div style="margin-bottom: 0.45rem;">
                <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                    Figures de référence
                </h3>
                <p style="margin:3px 0 0 0; font-size:0.82rem; color:#94A3B8; line-height:1.4;">
                    Créez vos exercices (Face, 3/4, Profil), vérifiez la qualité de prise de vue et enregistrez vos vidéos modèles.
                </p>
            </div>
        """)
    with col_calib_tuto:
        render_tutorial_button(key="btn_tuto_calib_header")

    df_base = load_baselines_table(user=curr_u)
    distinct_figures = (
        [str(x).strip() for x in df_base["exercise"].unique() if str(x).strip()]
        if not df_base.empty and "exercise" in df_base.columns else []
    )

    calib_count = len(df_base[df_base["status"] == "calibrated"]) if not df_base.empty and "status" in df_base.columns else 0
    distinct_count = len(distinct_figures)
    total_slots = len(df_base)
    ratio = (calib_count / float(total_slots)) if total_slots > 0 else 0.0

    render_html(f"""
        <div class="cali-card" style="padding: 10px 14px; margin-bottom: 0.8rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <span style="font-size:0.84rem; font-weight:700; color:#F8FAFC;">
                    {distinct_count} figure(s) disponible(s)
                </span>
                <span class="cali-tabular" style="font-family:'JetBrains Mono',monospace; font-size:0.78rem; color:#00E5FF; font-weight:700;">
                    {calib_count} / {total_slots} angles enregistrés ({int(ratio * 100)}%)
                </span>
            </div>
        </div>
    """)
    if total_slots > 0:
        st.progress(min(1.0, max(0.0, ratio)))

    _render_last_calibration_preview()

    if not is_coach:
        st.info("Mode Élève : vous consultez uniquement les figures de référence de votre coach.")
    else:
        step_title = "Étape 1 : Ajouter une figure (3 angles de vue)"
        with st.expander(step_title, expanded=(distinct_count == 0)):
            with st.form("form_create_exo_slots", clear_on_submit=True):
                col_new_name, col_new_type = st.columns([1.5, 1])
                with col_new_name:
                    new_exo_input = st.text_input(
                        "Nom de la figure :",
                        placeholder="ex: Full Planche, Maltese, Front Lever, Tractions..."
                    )
                with col_new_type:
                    new_exo_type = st.radio("Type de mouvement :", ["Isométrique", "Dynamique"], horizontal=True)

                if st.form_submit_button("Ajouter une figure", type="primary", use_container_width=True):
                    if not new_exo_input.strip():
                        st.warning("Veuillez saisir un nom pour la figure.")
                    else:
                        c_type = "isometric" if new_exo_type == "Isométrique" else "dynamic"
                        ok_c, msg_c = create_figure_slots(
                            new_exo_input,
                            exo_type=c_type,
                            user=curr_u,
                            is_shared=False,
                        )
                        if ok_c:
                            st.success(msg_c)
                            time.sleep(0.25)
                            st.rerun()
                        else:
                            st.error(msg_c)

    render_html("<h4 style='margin: 1rem 0 0.5rem 0; font-size:1rem; font-weight:800; color:#F8FAFC;'>Répertoire des figures</h4>")

    if not distinct_figures:
        render_empty_state(
            title="Aucune figure pour le moment",
            description="Aucune figure pour le moment. Ajoute ta première figure de référence ci-dessus ou associe ton compte à un coach.",
            icon="",
        )
    else:
        col_f1, col_f2 = st.columns([1.4, 1.4])
        with col_f1:
            search_q = st.text_input("Rechercher une figure :", placeholder="ex: Planche, Lever, Dips...", key="calib_search_fig").strip().lower()
        with col_f2:
            filter_mode = st.selectbox(
                "Filtrer :",
                ["Toutes", "En attente", "Calibrées"],
                key="calib_filter_mode"
            )

        filtered_figs = []
        for fig_name in distinct_figures:
            if search_q and search_q not in fig_name.lower():
                continue
            sub_df = df_base[df_base["exercise"] == fig_name]
            nb_calib = len(sub_df[sub_df["status"] == "calibrated"])

            if filter_mode == "En attente" and nb_calib == 3:
                continue
            if filter_mode == "Calibrées" and nb_calib == 0:
                continue

            filtered_figs.append(fig_name)

        if not filtered_figs:
            st.caption("Aucune figure ne correspond à ce filtre.")
        else:
            for fig_name in filtered_figs:
                sub_df = df_base[df_base["exercise"] == fig_name]
                fig_type = sub_df["type"].iloc[0] if not sub_df.empty else "isometric"
                type_label = "Isométrique" if fig_type == "isometric" else "Dynamique"
                owner_id = int(sub_df["owner_id"].iloc[0])
                is_owner = (owner_id == u_id)

                nb_calib = len(sub_df[sub_df["status"] == "calibrated"])
                calib_icon = "🟢" if nb_calib == 3 else "🟡"
                calib_ratio = f"{nb_calib}/3 validé{'s' if nb_calib > 1 else ''}"
                clean_key = re.sub(r"[^a-zA-Z0-9]+", "_", f"{owner_id}_{fig_name.lower()}").strip("_")
                exp_header = f"{calib_icon} {fig_name} • {type_label} ({calib_ratio})"

                with st.expander(exp_header, expanded=False):
                    pills_parts = []
                    for v_name in VALID_CAMERA_VIEWS:
                        v_row = sub_df[sub_df["camera_view"] == v_name]
                        is_cal = not v_row.empty and v_row.iloc[0]["status"] == "calibrated"
                        q_val = v_row.iloc[0]["quality_score"] if not v_row.empty else None
                        q_txt = f" ({int(q_val)}/100)" if (is_cal and q_val is not None and not np.isnan(q_val)) else ""
                        dot_cls = "badge-lime cali-tabular" if is_cal else "badge-amber"
                        dot_state = "Prêt" if is_cal else "À faire"
                        pills_parts.append(f'<span class="{dot_cls}">{v_name} • {dot_state}{q_txt}</span>')
                    render_html(f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;'>{''.join(pills_parts)}</div>")

                    for v_name in VALID_CAMERA_VIEWS:
                        v_row = sub_df[sub_df["camera_view"] == v_name]
                        is_cal = not v_row.empty and v_row.iloc[0]["status"] == "calibrated"

                        c_v1, c_v2, c_v3 = st.columns([1.2, 2, 1.2])
                        with c_v1:
                            render_html(f"<b>Angle {v_name}</b>")
                        with c_v2:
                            if is_cal:
                                render_html("<span style='color:#34D399; font-weight:700;'>Vidéo enregistrée</span>")
                            else:
                                render_html("<span style='color:#94A3B8;'>En attente de vidéo</span>")
                        with c_v3:
                            if is_cal and is_owner and is_coach:
                                slot_id = int(v_row.iloc[0]["id"])
                                if st.button("Réinitialiser", key=f"reset_{slot_id}", use_container_width=True):
                                    ok_r, msg_r = reset_slot(slot_id, user=curr_u)
                                    if ok_r:
                                        st.toast(msg_r)
                                        time.sleep(0.2)
                                        st.rerun()
                                    else:
                                        st.error(msg_r)
                            elif is_cal:
                                st.caption("Coach")
                            else:
                                st.caption("—")

                    if is_owner and is_coach:
                        render_html("<div style='height:6px;'></div>")
                        if st.button("Supprimer la figure", key=f"del_fig_{clean_key}", use_container_width=True):
                            ok_d, msg_d = delete_figure(fig_name, user=curr_u)
                            if ok_d:
                                st.toast(msg_d)
                                time.sleep(0.2)
                                st.rerun()
                            else:
                                st.error(msg_d)

    # ------------------------------------------------------------------
    # ÉTAPE 2 : VÉRIFICATION DE LA VIDÉO ET ENREGISTREMENT (COACH)
    # ------------------------------------------------------------------
    if is_coach:
        render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin:18px 0 14px 0;'>")
        with st.expander("Étape 2 : Enregistrer une vidéo de référence (Vérification de la vidéo)", expanded=(distinct_count > 0)):
            if not distinct_figures:
                st.warning("Ajoutez d'abord au moins une figure à l'Étape 1 ci-dessus.")
            else:
                col_sel_exo, col_sel_ang = st.columns([1.5, 1])
                with col_sel_exo:
                    chosen_exo = st.selectbox("Figure à calibrer :", distinct_figures, key="select_calib_exo_step_b")
                with col_sel_ang:
                    sub_chosen = df_base[df_base["exercise"] == chosen_exo]

                    def _fmt_angle_status(ang):
                        match_ang = sub_chosen[sub_chosen["camera_view"] == ang]
                        if not match_ang.empty and match_ang.iloc[0]["status"] == "calibrated":
                            return f"{ang} (Enregistré)"
                        return f"{ang} (En attente)"

                    chosen_angle = st.selectbox(
                        "Angle de vue :",
                        VALID_CAMERA_VIEWS,
                        format_func=_fmt_angle_status,
                        key="select_calib_angle_step_b"
                    )

                calib_video_upload = st.file_uploader(
                    f"Vidéo de référence pour {chosen_exo} ({chosen_angle}) — 3 à 5 s recommandées :",
                    type=["mp4", "mov", "avi"],
                    key="uploader_calib_video_step_b"
                )

                if calib_video_upload is not None:
                    upload_sig = f"{getattr(calib_video_upload, 'name', '')}_{getattr(calib_video_upload, 'size', 0)}"
                    pending_qc = st.session_state.get("pending_calib_analysis")
                    has_pending = bool(pending_qc and pending_qc.get("upload_sig") == upload_sig)

                    btn_analyze_lbl = (
                        f"Réanalyser la vidéo ({chosen_angle})"
                        if has_pending else
                        f"Analyser et vérifier la vidéo ({chosen_angle})"
                    )
                    btn_analyze_type = "secondary" if has_pending else "primary"

                    if st.button(btn_analyze_lbl, type=btn_analyze_type, use_container_width=True, key="btn_run_calib_step_b"):
                        with st.spinner("Vérification de la vidéo en cours..."):
                            try:
                                from core.biomechanics_3d import extract_3d_kinematics_from_video
                                from core.segmentation import segment_and_classify_video

                                with temporary_video_file(calib_video_upload) as temp_cal_path:
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
                                        "max_rep_duration_sec": 9.0,
                                    }

                                st.session_state.pending_calib_analysis = {
                                    "upload_sig": upload_sig,
                                    "kinematics": kin_cal,
                                    "segmentation": seg_cal,
                                    "means": [round(float(x), 1) for x in means_cal],
                                    "stds": [round(float(x), 1) for x in stds_cal],
                                    "rom": rom_data,
                                }
                                pending_qc = st.session_state.pending_calib_analysis
                                has_pending = True
                            except Exception as err_c:
                                st.session_state.pending_calib_analysis = None
                                has_pending = False
                                st.error(f"Erreur d'analyse de calibrage : {err_c}")

                    if has_pending and pending_qc:
                        from core.quality_control import evaluate_calibration_quality

                        fig_type_current = sub_chosen["type"].iloc[0] if not sub_chosen.empty else pending_qc["segmentation"].get("type", "isometric")
                        qc_report = evaluate_calibration_quality(
                            kinematics=pending_qc["kinematics"],
                            segmentation=pending_qc["segmentation"],
                            camera_view=chosen_angle,
                            exo_type=fig_type_current,
                            exercise_name=chosen_exo,
                        )

                        render_quality_diagnostic_card(qc_report)

                        means_preview = pending_qc.get("means", [])
                        if len(means_preview) >= 6:
                            st.caption(
                                f"Angles mesurés ({chosen_exo} • {chosen_angle}) : "
                                f"Coude {means_preview[2]:.1f}° • Épaule {means_preview[0]:.1f}° • "
                                f"Hanche {means_preview[3]:.1f}° • Buste {means_preview[4]:.1f}°"
                            )

                        clean_confirm_key = re.sub(r"[^a-zA-Z0-9_]+", "_", f"chk_qc_warn_{upload_sig}_{chosen_exo}_{chosen_angle}")
                        clicked_save, qc_confirmed = render_qc_save_gate(
                            report=qc_report,
                            save_button_key="btn_save_calib_after_qc",
                            confirm_checkbox_key=clean_confirm_key,
                            button_label="Enregistrer cette figure",
                        )

                        if clicked_save:
                            fig_shared_cur = bool(sub_chosen["is_shared"].iloc[0]) if not sub_chosen.empty else False
                            ok_save, msg_save = save_calibrated_slot(
                                exercise_name=chosen_exo,
                                camera_view=chosen_angle,
                                exo_type=fig_type_current,
                                mean_features=pending_qc["means"],
                                std_features=pending_qc["stds"],
                                rom_bounds=pending_qc.get("rom"),
                                user=curr_u,
                                is_shared=fig_shared_cur,
                                quality_report=qc_report,
                                qc_confirmed_warning=qc_confirmed,
                            )
                            if ok_save:
                                st.session_state.last_calib_preview = {
                                    "exercise": chosen_exo,
                                    "camera_view": chosen_angle,
                                    "means": pending_qc["means"],
                                    "stds": pending_qc["stds"],
                                    "rom": pending_qc.get("rom"),
                                    "quality_score": qc_report.global_score,
                                }
                                st.session_state.pending_calib_analysis = None
                                st.toast(msg_save)
                                time.sleep(0.25)
                                st.rerun()
                            else:
                                st.error(msg_save)
                else:
                    if st.session_state.get("pending_calib_analysis") is not None:
                        st.session_state.pending_calib_analysis = None

    render_html("<div style='height:8px;'></div>")
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        csv_base = export_dataframe_to_csv_bytes(build_baselines_export_dataframe(df_base))
        st.download_button(
            "Exporter en CSV",
            data=csv_base,
            file_name=f"figures_reference_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_export_baselines_csv"
        )
    with col_u2:
        json_backup = export_baselines_json(user=curr_u).encode("utf-8")
        st.download_button(
            "Exporter en JSON",
            data=json_backup,
            file_name=f"figures_reference_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
            key="btn_export_baselines_json"
        )
