"""
ui/tab_studio.py - Compartiment 1 : Parcours unifié en 3 étapes (Import & Analyse 3D unique,
Résultats & Diagnostic biomécanique, Formulaire unique d'enregistrement SQL).
"""

import time
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.auth import normalize_role
from core.calibration import (
    VALID_CAMERA_VIEWS,
    compute_active_feature_vectors,
    load_baselines_table,
    save_calibrated_slot,
)
from core.database import (
    create_training_log,
    detect_student_and_exercise,
    get_coach_athletes,
    get_gemini_api_key,
    set_active_athlete_in_session,
)
from core.load_quantification import compute_set_load_bundle
from core.quality_control import evaluate_calibration_quality
from core.video_io import temporary_video_file
from ui.calibration_qc import render_qc_save_gate, render_quality_diagnostic_card
from ui.theme import render_html


def _ensure_stopwatch_entry(filename: str) -> dict:
    """Initialise ou retourne l'état du pré-remplissage / chronomètre pour une vidéo."""
    if filename not in st.session_state.stopwatches:
        st.session_state.stopwatches[filename] = {
            "tst_val": 0.0,
            "in_marker": 0.0,
            "out_marker": 0.0,
            "running": False,
            "start_time": 0.0,
            "rpe": 7.5,
            "reps": 0,
            "added_load_kg": 0.0,
            "exo_type": "isometric",
        }
    return st.session_state.stopwatches[filename]


def _render_live_stopwatch_display(sw: dict) -> None:
    """Affiche le chronomètre digital 60fps compact dans le panneau de saisie manuelle."""
    if sw["running"]:
        elapsed_now = max(0.0, float(sw["tst_val"]) + (time.time() - float(sw["start_time"])))
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700&family=JetBrains+Mono:wght@800&display=swap" rel="stylesheet">
        <style>
            html, body {{ margin: 0; padding: 0; background: transparent; font-family: 'Plus Jakarta Sans', sans-serif; overflow: hidden; }}
            .wrap {{ text-align: center; padding: 2px 0; }}
            .sub {{ font-size: 11px; color: #34D399; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }}
            .timer {{ font-family: 'JetBrains Mono', monospace; font-size: 36px; font-weight: 800; color: #10B981; line-height: 1.1; }}
            .unit {{ font-size: 16px; color: #94A3B8; margin-left: 2px; }}
        </style>
        </head>
        <body>
            <div class="wrap">
                <div class="sub">● CHRONO EN COURS</div>
                <div class="timer"><span id="val">{elapsed_now:.2f}</span><span class="unit">s</span></div>
            </div>
            <script>
                var baseVal = {elapsed_now:.4f};
                var t0 = performance.now();
                var el = document.getElementById('val');
                function tick() {{
                    el.textContent = (baseVal + (performance.now() - t0) / 1000.0).toFixed(2);
                    requestAnimationFrame(tick);
                }}
                requestAnimationFrame(tick);
            </script>
        </body>
        </html>
        """, height=64)
    else:
        disp_tst = float(sw["tst_val"])
        render_html(f"""
            <div style="text-align: center; padding: 0.1rem 0 0.25rem 0;">
                <span class="digital-sub">TEMPS SOUS TENSION (TST)</span>
                <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.15rem; color:#94A3B8; margin-left:3px;">s</span></div>
            </div>
        """)


def _get_dynamic_exercise_choices(user) -> list:
    """Construit la liste des exercices forçables depuis baselines_3d SQL scopée."""
    choices = [("auto", "Auto (1-NN 3D)")]
    seen = set()
    try:
        df_b = load_baselines_table(user=user)
        if not df_b.empty and "exercise" in df_b.columns:
            calib_df = df_b[df_b["status"] == "calibrated"] if "status" in df_b.columns else df_b
            target_df = calib_df if not calib_df.empty else df_b
            for ex in target_df["exercise"].unique():
                clean_ex = str(ex).strip()
                if clean_ex and clean_ex.lower() not in seen:
                    seen.add(clean_ex.lower())
                    choices.append((clean_ex, clean_ex))
    except Exception:
        pass

    fallbacks = [
        "Full Planche", "Straddle Planche", "Maltese",
        "Front Lever", "Back Lever", "Tractions", "Dips", "Pompes", "Hefesto"
    ]
    for fb in fallbacks:
        if fb.lower() not in seen:
            seen.add(fb.lower())
            choices.append((fb, fb))

    return choices


def _render_intra_set_fatigue_panel(bio_r: dict, current_fname: str) -> None:
    """Affiche l'analyse de dérive technique intra-série (Δθ ou perte de vélocité %)."""
    fatigue = bio_r.get("fatigue") or {}
    if not fatigue.get("available"):
        return

    with st.expander("🔋 Dérive Technique Intra-Série & Fatigue", expanded=True):
        if fatigue.get("type") == "isometric":
            sh_d = fatigue.get("shoulder_drift_deg", 0.0)
            hip_d = fatigue.get("hip_drift_deg", 0.0)
            trunk_d = fatigue.get("trunk_drift_deg", 0.0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Δθ Épaule", f"{sh_d:+.1f}°")
            c2.metric("Δθ Hanche", f"{hip_d:+.1f}°")
            c3.metric("Δθ Tronc", f"{trunk_d:+.1f}°")
        else:
            loss_pct = float(fatigue.get("velocity_loss_pct", 0.0) or 0.0)
            st.metric("Perte de vélocité", f"{loss_pct:.1f}%", fatigue.get("failure_proximity_label", ""))


def render_tab_studio() -> None:
    """Rend le Studio Vidéo unifié en 3 étapes claires."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    u_id = int(curr_u["id"])
    u_role = normalize_role(curr_u.get("role", "athlete"))
    active_profile = st.session_state.get("active_athlete_profile") or curr_u

    # ==========================================================================
    # ÉTAPE 1 : ATHLÈTE, IMPORT VIDÉO & BOUTON UNIQUE D'ANALYSE 3D
    # ==========================================================================
    if u_role == "coach":
        profile_map = st.session_state.get("selectable_profiles_map")
        opt_ids_top = st.session_state.get("selectable_profile_ids")
        if not profile_map or not opt_ids_top:
            coach_athletes = get_coach_athletes(u_id)
            selectable = [curr_u] + coach_athletes
            profile_map = {int(p["id"]): p for p in selectable}
            opt_ids_top = [int(p["id"]) for p in selectable]
        else:
            selectable = [profile_map[pid] for pid in opt_ids_top]

        def _on_studio_ath_change() -> None:
            chosen = st.session_state.get("studio_athlete_select")
            if chosen is not None:
                set_active_athlete_in_session(int(chosen), sync_widgets=True)

        sel_top_id = st.selectbox(
            "🎯 Athlète suivi (enregistrement SQL) :",
            options=opt_ids_top,
            format_func=lambda pid: (
                f"🏋️ Moi-même ({profile_map[pid]['full_name']})"
                if pid == u_id else
                f"🤸 {profile_map[pid]['full_name']} ({profile_map[pid]['bodyweight_kg']:.0f} kg)"
            ),
            key="studio_athlete_select",
            on_change=_on_studio_ath_change,
        )
        active_profile = profile_map[int(sel_top_id)]
        st.session_state["active_athlete_profile"] = active_profile
    else:
        selectable = [curr_u]
        profile_map = {u_id: curr_u}

    with st.expander("1️⃣ Importer des vidéos (jusqu'à 10 fichiers)", expanded=not bool(st.session_state.get("active_uploaded_files"))):
        uploaded_files = st.file_uploader(
            "Importer les vidéos (.mp4, .mov, .avi)",
            type=["mp4", "mov", "avi"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if st.session_state.get("active_uploaded_files"):
            if st.button("🧹 Vider la file de vidéos", key="btn_clear_studio_queue", use_container_width=True):
                st.session_state.active_uploaded_files = []
                st.session_state.batch_results = []
                st.session_state.active_video_idx = 0
                st.rerun()

    if uploaded_files:
        if len(uploaded_files) > 10:
            st.warning("⚠️ Lot limité à 10 vidéos simultanées : les 10 premières ont été retenues.")
            uploaded_files = uploaded_files[:10]
        st.session_state.active_uploaded_files = uploaded_files
    else:
        uploaded_files = st.session_state.get("active_uploaded_files", [])

    # Option repliable de saisie manuelle sans vidéo (fermée par défaut)
    if not uploaded_files:
        render_html("""
            <div class="cali-card-accent" style="text-align:center; padding: 1.8rem 1rem; margin-top: 0.3rem;">
                <div style="font-size: 2rem; margin-bottom: 0.35rem;">🎬</div>
                <h3 style="margin: 0 0 0.3rem 0; font-size: 1.12rem; color:#F8FAFC;">Studio Vidéo Prêt</h3>
                <p style="color:#94A3B8; font-size: 0.85rem; max-width: 440px; margin: 0 auto; line-height:1.45;">
                    Importez une vidéo pour lancer l'Analyse 3D, ou utilisez la saisie manuelle ci-dessous sans vidéo.
                </p>
            </div>
        """)
        with st.expander("⏱️ Saisie manuelle sans vidéo", expanded=False):
            manual_sw = _ensure_stopwatch_entry("__manual__")
            _render_live_stopwatch_display(manual_sw)
            cm1, cm2 = st.columns(2)
            with cm1:
                if st.button("⏸️ PAUSE" if manual_sw["running"] else "▶️ DÉMARRER", key="btn_man_run", use_container_width=True):
                    if manual_sw["running"]:
                        manual_sw["tst_val"] += time.time() - manual_sw["start_time"]
                        manual_sw["running"] = False
                    else:
                        manual_sw["start_time"] = time.time()
                        manual_sw["running"] = True
                    st.rerun()
            with cm2:
                if st.button("🔄 RAZ", key="btn_man_raz", use_container_width=True):
                    manual_sw["tst_val"] = 0.0
                    manual_sw["running"] = False
                    st.rerun()

            with st.form("form_manual_no_video_log"):
                m_exo = st.text_input("🏋️ Exercice :", value="Full Planche")
                mt1, mt2 = st.columns(2)
                with mt1:
                    m_type = st.selectbox("Type :", ["isometric", "dynamic"], format_func=lambda x: "Isométrique" if x == "isometric" else "Dynamique")
                with mt2:
                    m_tut = st.number_input("TUT effectif (s) :", min_value=0.0, max_value=3600.0, value=round(float(manual_sw["tst_val"]), 2), step=0.5)
                mn1, mn2 = st.columns(2)
                with mn1:
                    m_reps = st.number_input("Répétitions :", min_value=0, max_value=200, value=0, step=1)
                with mn2:
                    m_lest = st.number_input("Lest additionnel (kg) :", min_value=0.0, max_value=200.0, value=0.0, step=1.25)
                m_rpe = st.slider("🔥 RPE (1–10) :", min_value=1.0, max_value=10.0, value=7.5, step=0.5)
                if st.form_submit_button("💾 Enregistrer dans le journal SQL", type="primary", use_container_width=True):
                    if m_tut <= 0 and m_reps <= 0:
                        st.warning("⚠️ Indiquez un TUT > 0 s ou au moins 1 répétition.")
                    else:
                        bw_m = float(active_profile.get("bodyweight_kg", 70.0) or 70.0)
                        b_m = compute_set_load_bundle(m_exo, m_type, m_tut, m_reps, m_lest, bw_m, m_rpe)
                        create_training_log(
                            athlete_id=int(active_profile["id"]),
                            coach_id=u_id if u_role == "coach" else active_profile.get("coach_id"),
                            exercise=m_exo,
                            exercise_type=m_type,
                            reps=int(m_reps),
                            tut_effective_sec=float(m_tut),
                            added_load_kg=float(m_lest),
                            bodyweight_kg=bw_m,
                            difficulty_coef=1.0,
                            external_load_au=b_m["external_load_au"],
                            rpe=float(m_rpe),
                            srpe_load=b_m["srpe_load"],
                            notes="Saisie manuelle",
                        )
                        st.success(f"✅ Séance enregistrée pour {active_profile['full_name']} !")
                        st.rerun()
        return

    files_dict = {f.name: f for f in uploaded_files}
    file_names = list(files_dict.keys())
    total_files = len(file_names)
    athlete_names = [str(p["full_name"]) for p in selectable]

    cur_idx = min(st.session_state.active_video_idx, total_files - 1)
    st.session_state.active_video_idx = cur_idx
    current_fname = file_names[cur_idx]
    current_file = files_dict[current_fname]

    if total_files > 1:
        col_prev, col_status, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀️ Préc.", key="btn_prev_vid", use_container_width=True, disabled=(cur_idx == 0)):
                st.session_state.active_video_idx = max(0, cur_idx - 1)
                st.rerun()
        with col_status:
            is_analyzed = current_fname in st.session_state.processed_videos
            badge_type = "badge-lime" if is_analyzed else "badge-amber"
            status_text = "✅ Analysée" if is_analyzed else "⏳ En attente"
            render_html(f"""
                <div style="text-align:center; padding-top: 2px;">
                    <span style="font-size: 0.84rem; font-weight:700; color:#F8FAFC;">Vidéo {cur_idx + 1} / {total_files}</span>
                    <div style="margin-top:3px;"><span class="{badge_type}">{status_text}</span></div>
                </div>
            """)
        with col_next:
            if st.button("Suiv. ▶️", key="btn_next_vid", use_container_width=True, disabled=(cur_idx >= total_files - 1)):
                st.session_state.active_video_idx = min(total_files - 1, cur_idx + 1)
                st.rerun()

    auto_student_name, auto_exo = detect_student_and_exercise(current_fname, athlete_names)
    sw = _ensure_stopwatch_entry(current_fname)

    # Réglages optionnels d'analyse + BOUTON UNIQUE D'ANALYSE 3D
    exo_choices = _get_dynamic_exercise_choices(curr_u)
    c_opt1, c_opt2 = st.columns([1.2, 1.2])
    with c_opt1:
        forced_opt = st.selectbox(
            "Exercice (Auto ou forcé) :",
            exo_choices,
            format_func=lambda x: x[1],
            key=f"forced_exo_{current_fname}",
        )
    with c_opt2:
        custom_tol = st.slider(
            "Tolérance angulaire (±°) :",
            min_value=8.0,
            max_value=25.0,
            value=15.0,
            step=1.0,
            key=f"tol_slider_{current_fname}",
        )

    if st.button("🚀 Lancer l'Analyse 3D", key=f"btn_unified_run_3d_{current_fname}", type="primary", use_container_width=True):
        with st.spinner("Extraction cinématique MediaPipe 3D CPU en cours..."):
            try:
                from core.rep_counter import analyze_single_video_pipeline
                forced_key = None if forced_opt[0] == "auto" else forced_opt[0]
                with temporary_video_file(current_file) as cur_temp:
                    res = analyze_single_video_pipeline(
                        cur_temp,
                        forced_exercise=forced_key,
                        custom_tolerance=custom_tol,
                        user=curr_u,
                    )
                res["filename"] = current_fname
                sw["tst_val"] = float(res["tut"])
                sw["reps"] = int(res["reps"])
                sw["detected_exo"] = res["exercise_display"]
                sw["exo_type"] = res.get("type", "isometric")
                st.session_state.biomech_results[current_fname] = res
                st.session_state.processed_videos.add(current_fname)
                st.toast(f"✅ {res['exercise_display']} : TUT = {sw['tst_val']} s | {sw['reps']} reps")
                time.sleep(0.15)
                st.rerun()
            except Exception as err_track:
                st.error(f"Erreur d'analyse MediaPipe 3D : {err_track}")

    gem_key = get_gemini_api_key()
    if gem_key:
        if st.button("🧠 Analyse IA Gemini Vision (Secours)", key=f"gemini_fb_{current_fname}", use_container_width=True):
            with st.spinner("Analyse Gemini Flash Vision..."):
                from services.gemini_vision import analyze_motion_gemini
                with temporary_video_file(current_file) as cur_temp:
                    g_data, _, g_msg = analyze_motion_gemini(cur_temp, gem_key)
                if g_data:
                    sw["tst_val"] = float(g_data.get("tut", 0.0))
                    sw["reps"] = int(g_data.get("reps", 0))
                    sw["detected_exo"] = g_data.get("exercise_display", auto_exo)
                    sw["exo_type"] = g_data.get("type", "isometric")
                    st.toast(f"🧠 Gemini : {sw['detected_exo']} | TUT={sw['tst_val']}s | {sw['reps']} reps")
                    st.rerun()
                else:
                    st.warning(g_msg)

    # ==========================================================================
    # ÉTAPE 2 : RÉSULTATS & DIAGNOSTIC BIOMÉCANIQUE
    # ==========================================================================
    st.video(current_file)

    bio_cur = st.session_state.biomech_results.get(current_fname, {})
    if bio_cur:
        det_exo = bio_cur.get("exercise_display", auto_exo)
        det_type_lbl = "Isométrique" if bio_cur.get("type") == "isometric" else "Dynamique"
        det_tut = float(bio_cur.get("tut", 0.0) or 0.0)
        det_reps = int(bio_cur.get("reps", 0) or 0)
        det_drift = str(bio_cur.get("drift", "Stable"))

        render_html(f"""
            <div class="cali-card" style="padding: 12px 14px; margin-bottom: 0.65rem; border-color: rgba(0,229,255,0.28);">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
                    <span style="font-size:0.95rem; font-weight:800; color:#F8FAFC;">2️⃣ {det_exo}</span>
                    <span class="badge-cyan">{det_type_lbl}</span>
                </div>
                <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; text-align:center;">
                    <div style="background:rgba(255,255,255,0.03); border-radius:9px; padding:7px 4px;">
                        <div style="font-size:0.64rem; color:#94A3B8; font-weight:700; text-transform:uppercase;">TUT Effectif</div>
                        <div style="font-size:1.12rem; font-weight:800; color:#00E5FF; font-family:'JetBrains Mono',monospace;">{det_tut:.2f} s</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.03); border-radius:9px; padding:7px 4px;">
                        <div style="font-size:0.64rem; color:#94A3B8; font-weight:700; text-transform:uppercase;">Répétitions</div>
                        <div style="font-size:1.12rem; font-weight:800; color:#34D399; font-family:'JetBrains Mono',monospace;">{det_reps}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.03); border-radius:9px; padding:7px 4px;">
                        <div style="font-size:0.64rem; color:#94A3B8; font-weight:700; text-transform:uppercase;">Diagnostic</div>
                        <div style="font-size:0.74rem; font-weight:700; color:#E2E8F0; line-height:1.25;">{det_drift}</div>
                    </div>
                </div>
            </div>
        """)

        _render_intra_set_fatigue_panel(bio_cur, current_fname)

        kin = bio_cur.get("kinematics")
        ev = bio_cur.get("evaluation") or {}
        seg = bio_cur.get("segmentation") or {}
        effort_w = seg.get("effort_window") or {}

        with st.expander("📈 Courbes Articulaires 3D (Plotly) & Calibration", expanded=False):
            try:
                import plotly.graph_objects as go
                has_plotly = True
            except ImportError:
                has_plotly = False
            if kin and has_plotly:
                t_ser = kin["timestamps"]
                filt_features = kin.get("features_filtered") or {}
                is_iso = bio_cur.get("type") == "isometric"

                fig_3d = go.Figure()
                if "elbow_angle" in filt_features:
                    fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["elbow_angle"], mode="lines", name="Coude 3D (°)", line=dict(color="#00E5FF", width=2.5)))
                if "shoulder_flexion" in filt_features:
                    fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["shoulder_flexion"], mode="lines", name="Épaule 3D (°)", line=dict(color="#F59E0B", width=2.0)))
                if "trunk_inclination" in filt_features:
                    fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["trunk_inclination"], mode="lines", name="Tronc (°)", line=dict(color="#10B981", width=1.8, dash="dot")))

                if is_iso:
                    for hb in ev.get("hold_blocks", []):
                        fig_3d.add_vrect(x0=hb["start_time"], x1=hb["end_time"], fillcolor="rgba(16,185,129,0.2)", layer="below", line_width=0)
                else:
                    for rep in ev.get("reps_details", []):
                        fig_3d.add_vrect(x0=rep["start_time"], x1=rep["end_time"], fillcolor="rgba(0,229,255,0.15)", layer="below", line_width=0)

                fig_3d.update_layout(
                    title="Cinématique Articulaire 3D (°)",
                    xaxis_title="Temps (s)",
                    yaxis_title="Degrés (°)",
                    paper_bgcolor="rgba(13,18,30,0.6)",
                    plot_bgcolor="rgba(13,18,30,0.6)",
                    font=dict(color="#F8FAFC"),
                    margin=dict(l=20, r=14, t=35, b=28),
                    height=240,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig_3d, use_container_width=True)

            if u_role == "coach" and kin and seg and "effort_window" in seg:
                render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin:8px 0;'>")
                user_cam_view = st.selectbox("Angle de vue :", VALID_CAMERA_VIEWS, key=f"sel_cam_add_{current_fname}")
                qc_studio = evaluate_calibration_quality(
                    kinematics=kin,
                    segmentation=seg,
                    camera_view=user_cam_view,
                    exo_type=bio_cur.get("type", "isometric"),
                    exercise_name=det_exo,
                )
                render_quality_diagnostic_card(qc_studio, compact=True)
                clicked_b, qc_ack_b = render_qc_save_gate(
                    report=qc_studio,
                    save_button_key=f"btn_add_to_base_{current_fname}",
                    confirm_checkbox_key=f"chk_studio_qc_{current_fname}_{user_cam_view}",
                    button_label="💾 Enregistrer comme référence 3D",
                )
                if clicked_b:
                    means_v, stds_v = compute_active_feature_vectors(kin, effort_w)
                    ok_b, msg_b = save_calibrated_slot(
                        exercise_name=det_exo,
                        camera_view=user_cam_view,
                        exo_type=bio_cur.get("type", "isometric"),
                        mean_features=means_v.tolist(),
                        std_features=stds_v.tolist(),
                        user=curr_u,
                        is_shared=False,
                        quality_report=qc_studio,
                        qc_confirmed_warning=qc_ack_b,
                    )
                    if ok_b:
                        st.success(f"✅ {det_exo} ({user_cam_view}) calibré !")
                        st.rerun()
                    else:
                        st.error(msg_b)

    # ==========================================================================
    # ÉTAPE 3 : FORMULAIRE UNIQUE D'ENREGISTREMENT SQL
    # ==========================================================================
    fat_cur = bio_cur.get("fatigue") or {}
    default_aid = int(active_profile["id"])
    if auto_student_name:
        for p in selectable:
            if p["full_name"] == auto_student_name:
                default_aid = int(p["id"])
                break
    opt_ids = [int(p["id"]) for p in selectable]

    st.markdown("##### 3️⃣ Validation & Enregistrement SQL")
    with st.form(key=f"eval_form_{current_fname}"):
        sel_aid = st.selectbox(
            "👤 Athlète :",
            options=opt_ids,
            index=opt_ids.index(default_aid) if default_aid in opt_ids else 0,
            format_func=lambda pid: profile_map[pid]["full_name"],
        )
        target_ath_obj = profile_map[int(sel_aid)]

        c_ex1, c_ex2 = st.columns([1.4, 1.0])
        with c_ex1:
            val_exo = st.text_input("🏋️ Exercice :", value=str(sw.get("detected_exo", auto_exo)))
        with c_ex2:
            cur_tp = str(bio_cur.get("type", sw.get("exo_type", "isometric")))
            val_type = st.selectbox(
                "Type :",
                ["isometric", "dynamic"],
                index=1 if cur_tp == "dynamic" else 0,
                format_func=lambda x: "Isométrique" if x == "isometric" else "Dynamique",
            )

        c_num1, c_num2, c_num3 = st.columns(3)
        with c_num1:
            val_tut = st.number_input("TUT effectif (s) :", min_value=0.0, max_value=3600.0, value=round(float(sw.get("tst_val", 0.0)), 2), step=0.5)
        with c_num2:
            val_reps = st.number_input("Répétitions :", min_value=0, max_value=200, value=int(sw.get("reps", 0)), step=1)
        with c_num3:
            val_lest = st.number_input("Lest (kg) :", min_value=0.0, max_value=200.0, value=float(sw.get("added_load_kg", 0.0)), step=1.25)

        bw_ref = float(target_ath_obj.get("bodyweight_kg", 70.0) or 70.0)
        rpe_score = st.slider(f"🔥 RPE (1–10) • PDC {bw_ref:.0f} kg :", min_value=1.0, max_value=10.0, value=float(sw.get("rpe", 7.5)), step=0.5)

        preview_bundle = compute_set_load_bundle(
            exercise=val_exo,
            exo_type=val_type,
            tut_effective_sec=val_tut,
            reps=val_reps,
            added_load_kg=val_lest,
            bodyweight_kg=bw_ref,
            rpe=rpe_score,
        )

        pondered_badge = (
            f'<span>🏋️ Volume pondéré : <b style="color:#34D399;font-family:\'JetBrains Mono\',monospace;">{preview_bundle["external_load_au"]:.1f}</b></span>'
            if float(val_lest or 0.0) > 0.0 else ""
        )
        render_html(f"""
            <div style="background:rgba(0,229,255,0.08);border:1px solid rgba(0,229,255,0.25);border-radius:10px;padding:8px 10px;margin:4px 0 8px 0;font-size:0.78rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;">
                <span>⏱️ TUT effectif : <b style="color:#00E5FF;font-family:'JetBrains Mono',monospace;">{val_tut:.1f} s</b></span>
                {pondered_badge}
                <span>🔥 Charge interne sRPE : <b style="color:#FBBF24;font-family:'JetBrains Mono',monospace;">{preview_bundle['srpe_load']:.1f}</b></span>
            </div>
        """)

        coach_notes = st.text_input("💬 Notes / Consignes :", placeholder="Ex: Verrouillage strict, bon tempo")
        if st.form_submit_button("💾 Enregistrer dans le journal SQL", type="primary", use_container_width=True):
            if val_tut <= 0 and val_reps <= 0:
                st.warning("⚠️ Indiquez un TUT > 0 s ou au moins 1 répétition.")
            else:
                sw["tst_val"] = float(val_tut)
                sw["reps"] = int(val_reps)
                sw["added_load_kg"] = float(val_lest)
                sw["rpe"] = float(rpe_score)

                final_bundle = compute_set_load_bundle(
                    exercise=val_exo,
                    exo_type=val_type,
                    tut_effective_sec=val_tut,
                    reps=val_reps,
                    added_load_kg=val_lest,
                    bodyweight_kg=bw_ref,
                    rpe=rpe_score,
                )
                coach_ref = u_id if u_role == "coach" else target_ath_obj.get("coach_id")

                create_training_log(
                    athlete_id=int(sel_aid),
                    coach_id=coach_ref,
                    exercise=val_exo,
                    exercise_type=val_type,
                    reps=int(val_reps),
                    tut_effective_sec=float(val_tut),
                    added_load_kg=float(val_lest),
                    bodyweight_kg=bw_ref,
                    difficulty_coef=1.0,
                    external_load_au=final_bundle["external_load_au"],
                    rpe=float(rpe_score),
                    srpe_load=final_bundle["srpe_load"],
                    fatigue_drift_deg=fat_cur.get("fatigue_drift_deg"),
                    velocity_loss_pct=fat_cur.get("velocity_loss_pct"),
                    notes=coach_notes or f"Vidéo: {current_fname}",
                )
                st.session_state.processed_videos.add(current_fname)
                st.toast(f"✅ Séance enregistrée : {target_ath_obj['full_name']} • sRPE {final_bundle['srpe_load']}")

                if st.session_state.get("session_settings", {}).get("auto_advance", True) and cur_idx < total_files - 1:
                    st.session_state.active_video_idx += 1

                time.sleep(0.25)
                st.rerun()

    # Saisie manuelle repliable en bas de page même quand une vidéo est chargée
    with st.expander("⏱️ Saisie manuelle sans vidéo", expanded=False):
        _render_live_stopwatch_display(sw)
        cm1, cm2 = st.columns(2)
        with cm1:
            if st.button("⏸️ PAUSE" if sw["running"] else "▶️ DÉMARRER", key=f"btn_man_v_{current_fname}", use_container_width=True):
                if sw["running"]:
                    sw["tst_val"] += time.time() - sw["start_time"]
                    sw["running"] = False
                else:
                    sw["start_time"] = time.time()
                    sw["running"] = True
                st.rerun()
        with cm2:
            if st.button("🔄 RAZ", key=f"btn_raz_v_{current_fname}", use_container_width=True):
                sw["tst_val"] = 0.0
                sw["running"] = False
                st.rerun()
