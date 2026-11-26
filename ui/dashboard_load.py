"""
ui/dashboard_load.py - Tableau de bord longitudinal (Chantier 4).
Calcule et visualise :
- Charge aiguë (EWMA 7j), Charge chronique (EWMA 28j) et Ratio ACWR
- Monotonie et Contrainte de Foster
- Jauge de Stress Mécanique / Tendineux Haute Intensité (Maltese, Planches, Front Lever, Hefesto...)
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import streamlit as st

from core.load_quantification import (
    is_high_tendon_stress_exercise,
    load_quantification_config,
)
from ui.theme import render_html


def _parse_log_date(log: Dict[str, Any]) -> date:
    dt_obj = log.get("date_dt")
    if isinstance(dt_obj, datetime):
        return dt_obj.date()
    raw = str(log.get("date", "")).strip()
    if raw:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw[:19], fmt).date()
            except Exception:
                continue
    return datetime.utcnow().date()


def compute_longitudinal_metrics(
    logs: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calcule les séries quotidiennes EWMA (7j/28j), ACWR, Monotonie/Contrainte de Foster
    et le Stress Tendineux Haute Intensité sans aucun seuil codé en dur.
    """
    cfg = config or load_quantification_config()
    ewma_cfg = cfg.get("ewma", {})
    zones_cfg = cfg.get("acwr_zones", {})
    tendon_cfg = cfg.get("tendon_stress", {})

    n_acute = max(1, int(ewma_cfg.get("acute_days", 7)))
    n_chronic = max(n_acute + 1, int(ewma_cfg.get("chronic_days", 28)))
    chronic_floor = float(ewma_cfg.get("min_chronic_floor", 1.0))

    lambda_a = 2.0 / float(n_acute + 1)
    lambda_c = 2.0 / float(n_chronic + 1)

    today = datetime.utcnow().date()
    parsed_dates = [_parse_log_date(l) for l in logs] if logs else []
    min_date = min(parsed_dates) if parsed_dates else (today - timedelta(days=n_chronic - 1))
    start_date = min(min_date, today - timedelta(days=n_chronic - 1))
    end_date = max([today] + parsed_dates) if parsed_dates else today

    n_days = (end_date - start_date).days + 1
    date_grid = [start_date + timedelta(days=i) for i in range(n_days)]
    ext_by_day: Dict[date, float] = {d: 0.0 for d in date_grid}
    srpe_by_day: Dict[date, float] = {d: 0.0 for d in date_grid}
    tendon_by_day: Dict[date, float] = {d: 0.0 for d in date_grid}

    for log, d in zip(logs, parsed_dates):
        ext_val = float(log.get("external_load_au", 0.0) or 0.0)
        srpe_val = float(log.get("srpe_load", 0.0) or 0.0)
        ext_by_day[d] = ext_by_day.get(d, 0.0) + ext_val
        srpe_by_day[d] = srpe_by_day.get(d, 0.0) + srpe_val
        if is_high_tendon_stress_exercise(str(log.get("exercise", "")), config=cfg):
            tendon_by_day[d] = tendon_by_day.get(d, 0.0) + ext_val

    ewma_acute: List[float] = []
    ewma_chronic: List[float] = []
    acwr_series: List[float] = []

    prev_a = ext_by_day[date_grid[0]]
    prev_c = ext_by_day[date_grid[0]]

    for i, d in enumerate(date_grid):
        load_d = ext_by_day[d]
        if i == 0:
            cur_a = load_d
            cur_c = load_d
        else:
            cur_a = lambda_a * load_d + (1.0 - lambda_a) * prev_a
            cur_c = lambda_c * load_d + (1.0 - lambda_c) * prev_c
        prev_a, prev_c = cur_a, cur_c
        ewma_acute.append(round(cur_a, 2))
        ewma_chronic.append(round(cur_c, 2))
        ratio = cur_a / max(cur_c, chronic_floor) if cur_a > 0 else 0.0
        acwr_series.append(round(ratio, 2))

    # Fenêtre glissante des 7 derniers jours jusqu'à end_date : Foster Monotony & Contrainte
    last_7_days = [end_date - timedelta(days=k) for k in range(6, -1, -1)]
    week_loads = np.array([ext_by_day.get(d, 0.0) for d in last_7_days], dtype=np.float64)
    week_sum = float(np.sum(week_loads))
    week_mean = float(np.mean(week_loads))
    week_std = float(np.std(week_loads, ddof=0))

    if week_sum <= 0.0:
        foster_monotony = 0.0
        foster_strain = 0.0
    else:
        foster_monotony = round(min(10.0, week_mean / max(week_std, 1.0)), 2)
        foster_strain = round(week_sum * foster_monotony, 1)

    weekly_tendon_au = round(sum(tendon_by_day.get(d, 0.0) for d in last_7_days), 1)

    cur_acute = ewma_acute[-1] if ewma_acute else 0.0
    cur_chronic = ewma_chronic[-1] if ewma_chronic else 0.0
    cur_acwr = acwr_series[-1] if acwr_series else 0.0

    sweet_min = float(zones_cfg.get("sweet_spot_min", 0.80))
    sweet_max = float(zones_cfg.get("sweet_spot_max", 1.30))
    caut_max = float(zones_cfg.get("caution_max", 1.50))

    if cur_acwr == 0.0:
        acwr_zone_lbl = "Aucune charge active"
        acwr_color = "#94A3B8"
    elif cur_acwr < sweet_min:
        acwr_zone_lbl = "Sous-charge (< 0.8)"
        acwr_color = "#38BDF8"
    elif cur_acwr <= sweet_max:
        acwr_zone_lbl = "Zone optimale (0.8 – 1.3)"
        acwr_color = "#34D399"
    elif cur_acwr <= caut_max:
        acwr_zone_lbl = "Vigilance (1.3 – 1.5)"
        acwr_color = "#FBBF24"
    else:
        acwr_zone_lbl = "Pic de surcharge (> 1.5)"
        acwr_color = "#FB7185"

    daily_df = pd.DataFrame({
        "Date": [d.strftime("%Y-%m-%d") for d in date_grid],
        "Charge Externe (UA)": [round(ext_by_day[d], 2) for d in date_grid],
        "sRPE": [round(srpe_by_day[d], 2) for d in date_grid],
        "EWMA Aiguë (7j)": ewma_acute,
        "EWMA Chronique (28j)": ewma_chronic,
        "ACWR": acwr_series,
        "Charge Tendineuse (UA)": [round(tendon_by_day[d], 2) for d in date_grid],
    })

    return {
        "acute_ewma": cur_acute,
        "chronic_ewma": cur_chronic,
        "acwr": cur_acwr,
        "acwr_label": acwr_zone_lbl,
        "acwr_color": acwr_color,
        "weekly_load_au": round(week_sum, 1),
        "foster_monotony": foster_monotony,
        "foster_strain": foster_strain,
        "weekly_tendon_au": weekly_tendon_au,
        "tendon_cfg": tendon_cfg,
        "zones_cfg": zones_cfg,
        "daily_df": daily_df,
    }


def render_longitudinal_dashboard(athlete_user: Dict[str, Any], logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Affiche le tableau de bord EWMA ACWR, Monotonie/Contrainte de Foster
    et la Jauge Stress Mécanique / Tendineux Haute Intensité.
    Retourne le dict metrics (contenant daily_df pour l'export Excel Synthese_ACWR).
    """
    cfg = load_quantification_config()
    metrics = compute_longitudinal_metrics(logs, config=cfg)

    ath_name = str(athlete_user.get("full_name") or athlete_user.get("username", "Athlète"))
    render_html(f"""
        <div class="cali-card" style="padding:10px 14px;margin-bottom:0.7rem;border-color:rgba(0,229,255,0.24);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
                <span style="font-size:0.86rem;font-weight:800;color:#F8FAFC;">📈 Pilotage Longitudinal EWMA & Stress Tendineux — {ath_name}</span>
                <span style="font-size:0.74rem;font-weight:700;color:{metrics['acwr_color']};">{metrics['acwr_label']}</span>
            </div>
        </div>
    """)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_html(f"""
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Aiguë EWMA (7j)</div>
                <div class="cali-kpi-val" style="color:#00E5FF;">{metrics['acute_ewma']:.1f}<span style="font-size:0.75rem;color:#94A3B8;margin-left:3px;">UA</span></div>
            </div>
        """)
    with k2:
        render_html(f"""
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Chronique (28j)</div>
                <div class="cali-kpi-val" style="color:#38BDF8;">{metrics['chronic_ewma']:.1f}<span style="font-size:0.75rem;color:#94A3B8;margin-left:3px;">UA</span></div>
            </div>
        """)
    with k3:
        render_html(f"""
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Ratio ACWR</div>
                <div class="cali-kpi-val" style="color:{metrics['acwr_color']};">{metrics['acwr']:.2f}</div>
            </div>
        """)
    with k4:
        render_html(f"""
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Foster (Mono / Contr.)</div>
                <div class="cali-kpi-val" style="font-size:1.15rem;color:#FBBF24;">{metrics['foster_monotony']:.2f} <span style="font-size:0.78rem;color:#94A3B8;">| {metrics['foster_strain']:.0f}</span></div>
            </div>
        """)

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        has_plotly = True
    except ImportError:
        has_plotly = False

    if has_plotly:
        df_d = metrics["daily_df"]
        zones = metrics["zones_cfg"]
        t_cfg = metrics["tendon_cfg"]

        c_chart, c_gauge = st.columns([1.45, 1.0])
        with c_chart:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(x=df_d["Date"], y=df_d["Charge Externe (UA)"], name="Charge / jour (UA)", marker_color="rgba(56,189,248,0.28)"),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=df_d["Date"], y=df_d["EWMA Aiguë (7j)"], name="EWMA Aiguë (7j)", line=dict(color="#00E5FF", width=2.3)),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=df_d["Date"], y=df_d["EWMA Chronique (28j)"], name="EWMA Chronique (28j)", line=dict(color="#818CF8", width=2.1, dash="dot")),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=df_d["Date"], y=df_d["ACWR"], name="ACWR", line=dict(color="#FBBF24", width=2.2)),
                secondary_y=True,
            )
            fig.add_hrect(
                y0=float(zones.get("sweet_spot_min", 0.80)),
                y1=float(zones.get("sweet_spot_max", 1.30)),
                fillcolor="rgba(16, 185, 129, 0.10)",
                line_width=0,
                secondary_y=True,
            )
            fig.update_layout(
                title="EWMA Charge (7j/28j) & Ratio ACWR",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(13,18,30,0.65)",
                font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
                height=310,
                margin=dict(l=12, r=12, t=36, b=24),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig.update_yaxes(title_text="Charge (UA)", secondary_y=False)
            fig.update_yaxes(title_text="Ratio ACWR", secondary_y=True, rangemode="tozero")
            st.plotly_chart(fig, use_container_width=True)

        with c_gauge:
            mod_th = float(t_cfg.get("weekly_moderate_threshold", 600.0))
            high_th = float(t_cfg.get("weekly_high_threshold", 1200.0))
            max_g = max(float(t_cfg.get("weekly_max_gauge", 2000.0)), metrics["weekly_tendon_au"] * 1.15)
            val_tend = metrics["weekly_tendon_au"]

            fig_g = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=val_tend,
                    title={"text": "Stress Tendineux Haute Intensité (7j)", "font": {"size": 14, "color": "#F8FAFC"}},
                    number={"suffix": " UA", "font": {"color": "#F8FAFC", "size": 24}},
                    gauge={
                        "axis": {"range": [0, max_g], "tickcolor": "#94A3B8"},
                        "bar": {"color": "#00E5FF"},
                        "bgcolor": "rgba(13,18,30,0.8)",
                        "steps": [
                            {"range": [0, mod_th], "color": "rgba(16, 185, 129, 0.32)"},
                            {"range": [mod_th, high_th], "color": "rgba(245, 158, 11, 0.35)"},
                            {"range": [high_th, max_g], "color": "rgba(244, 63, 94, 0.40)"},
                        ],
                        "threshold": {
                            "line": {"color": "#FB7185", "width": 3},
                            "thickness": 0.78,
                            "value": high_th,
                        },
                    },
                )
            )
            fig_g.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
                height=265,
                margin=dict(l=18, r=18, t=42, b=10),
            )
            st.plotly_chart(fig_g, use_container_width=True)
            if val_tend >= high_th:
                st.error(f"🔴 Stress tendineux élevé ({val_tend:.0f} UA ≥ {high_th:.0f}) : prévoyez du déchargement sur les leviers.")
            elif val_tend >= mod_th:
                st.warning(f"🟡 Stress tendineux soutenu ({val_tend:.0f} UA) : surveillez coudes & épaules.")
            else:
                st.caption(f"🟢 Volume tendineux maîtrisé sur 7 jours ({val_tend:.0f} UA sur figures à fort levier).")

    return metrics
