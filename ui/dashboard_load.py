"""
ui/dashboard_load.py - Tableau de bord longitudinal (Chantier 4).
Calcule et visualise :
- Charge aiguë (EWMA 7j), Charge chronique (EWMA 28j) et Ratio ACWR
- Monotonie et Contrainte de Foster
- Volume Hebdomadaire (7 derniers jours) : TUT effectif, Répétitions, sRPE
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import streamlit as st

from core.load_quantification import load_quantification_config
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
    et le Volume Hebdomadaire (7 derniers jours).
    """
    cfg = config or load_quantification_config()
    ewma_cfg = cfg.get("ewma", {})
    zones_cfg = cfg.get("acwr_zones", {})

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
    tut_by_day: Dict[date, float] = {d: 0.0 for d in date_grid}
    reps_by_day: Dict[date, int] = {d: 0 for d in date_grid}

    for log, d in zip(logs, parsed_dates):
        ext_val = float(log.get("external_load_au", 0.0) or 0.0)
        srpe_val = float(log.get("srpe_load", 0.0) or 0.0)
        tut_val = float(log.get("tut_effective_sec", 0.0) or 0.0)
        reps_val = int(log.get("reps", 0) or 0)
        ext_by_day[d] = ext_by_day.get(d, 0.0) + ext_val
        srpe_by_day[d] = srpe_by_day.get(d, 0.0) + srpe_val
        tut_by_day[d] = tut_by_day.get(d, 0.0) + tut_val
        reps_by_day[d] = reps_by_day.get(d, 0) + reps_val

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

    weekly_tut_sec = round(sum(tut_by_day.get(d, 0.0) for d in last_7_days), 1)
    weekly_reps = int(sum(reps_by_day.get(d, 0) for d in last_7_days))
    weekly_srpe = round(sum(srpe_by_day.get(d, 0.0) for d in last_7_days), 1)

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
        acwr_zone_lbl = "Sous-charge (< 0,8)"
        acwr_color = "#38BDF8"
    elif cur_acwr <= sweet_max:
        acwr_zone_lbl = "Zone optimale (0,8 – 1,3)"
        acwr_color = "#34D399"
    elif cur_acwr <= caut_max:
        acwr_zone_lbl = "Vigilance (1,3 – 1,5)"
        acwr_color = "#FBBF24"
    else:
        acwr_zone_lbl = "Pic de surcharge (> 1,5)"
        acwr_color = "#FB7185"

    daily_df = pd.DataFrame({
        "Date": [d.strftime("%Y-%m-%d") for d in date_grid],
        "Charge du jour": [round(ext_by_day[d], 2) for d in date_grid],
        "Charge ressentie": [round(srpe_by_day[d], 2) for d in date_grid],
        "Charge récente (7 jours)": ewma_acute,
        "Charge habituelle (28 jours)": ewma_chronic,
        "Équilibre charge / récupération": acwr_series,
    })

    return {
        "acute_ewma": cur_acute,
        "chronic_ewma": cur_chronic,
        "acwr": cur_acwr,
        "acwr_label": acwr_zone_lbl,
        "acwr_color": acwr_color,
        "weekly_load_au": round(week_sum, 1),
        "weekly_tut_sec": weekly_tut_sec,
        "weekly_reps": weekly_reps,
        "weekly_srpe": weekly_srpe,
        "foster_monotony": foster_monotony,
        "foster_strain": foster_strain,
        "zones_cfg": zones_cfg,
        "daily_df": daily_df,
    }


def render_longitudinal_dashboard(athlete_user: Dict[str, Any], logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Affiche les indicateurs de charge (7j / 28j, équilibre charge / récupération,
    régularité & fatigue accumulée) ainsi que les graphiques et le volume hebdomadaire.
    """
    cfg = load_quantification_config()
    metrics = compute_longitudinal_metrics(logs, config=cfg)

    ath_name = str(athlete_user.get("full_name") or athlete_user.get("username", "Athlète"))
    render_html(f"""
        <div class="cali-card" style="padding:10px 14px;margin-bottom:0.75rem;border-color:rgba(148,163,184,0.14);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
                <span style="font-size:0.86rem;font-weight:700;color:#F8FAFC;">{ath_name}</span>
                <span style="font-size:0.75rem;font-weight:700;color:{metrics['acwr_color']};">{metrics['acwr_label']}</span>
            </div>
        </div>
    """)

    render_html(f"""
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:1rem;">
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Charge récente (7 jours)</div>
                <div class="cali-kpi-val" style="color:#00E5FF;">{metrics['acute_ewma']:.1f}</div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Charge habituelle (28 jours)</div>
                <div class="cali-kpi-val" style="color:#38BDF8;">{metrics['chronic_ewma']:.1f}</div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Équilibre charge / récupération</div>
                <div class="cali-kpi-val" style="color:{metrics['acwr_color']};">{metrics['acwr']:.2f}</div>
                <div style="font-size:0.68rem;color:#94A3B8;margin-top:3px;">Zone optimale : 0,8 – 1,3</div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Régularité & Fatigue accumulée</div>
                <div class="cali-kpi-val" style="font-size:1.15rem;color:#FBBF24;">{metrics['foster_monotony']:.2f} <span style="font-size:0.78rem;color:#94A3B8;">| {metrics['foster_strain']:.0f}</span></div>
            </div>
        </div>
    """)

    df_d = metrics["daily_df"].copy()
    zones = metrics["zones_cfg"]

    try:
        import altair as alt
        has_altair = True
    except ImportError:
        has_altair = False

    if has_altair and not df_d.empty:
        df_d["DateObj"] = pd.to_datetime(df_d["Date"])

        # Graphique 1 : Charge récente (7 jours) vs Charge habituelle (28 jours)
        st.markdown("##### Évolution de la charge (7 jours vs 28 jours)")
        bars = (
            alt.Chart(df_d)
            .mark_bar(color="#38BDF8", opacity=0.28, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("DateObj:T", title=None, axis=alt.Axis(format="%d/%m", labelColor="#94A3B8", tickCount=5)),
                y=alt.Y(
                    "Charge du jour:Q",
                    title="Charge",
                    scale=alt.Scale(domainMin=0),
                    axis=alt.Axis(labelColor="#94A3B8", titleColor="#94A3B8"),
                ),
                tooltip=[
                    alt.Tooltip("Date:N", title="Date"),
                    alt.Tooltip("Charge du jour:Q", title="Charge du jour", format=".1f"),
                    alt.Tooltip("Charge récente (7 jours):Q", title="Charge récente (7j)", format=".1f"),
                    alt.Tooltip("Charge habituelle (28 jours):Q", title="Charge habituelle (28j)", format=".1f"),
                ],
            )
        )
        load_melt = df_d.melt(
            id_vars=["DateObj", "Date"],
            value_vars=["Charge récente (7 jours)", "Charge habituelle (28 jours)"],
            var_name="Courbe",
            value_name="Valeur",
        )
        lines = (
            alt.Chart(load_melt)
            .mark_line(strokeWidth=2.5)
            .encode(
                x=alt.X("DateObj:T", title=None),
                y=alt.Y("Valeur:Q", scale=alt.Scale(domainMin=0)),
                color=alt.Color(
                    "Courbe:N",
                    scale=alt.Scale(
                        domain=["Charge récente (7 jours)", "Charge habituelle (28 jours)"],
                        range=["#00E5FF", "#818CF8"],
                    ),
                    legend=alt.Legend(orient="top", title=None, labelColor="#E2E8F0", columns=2),
                ),
                strokeDash=alt.StrokeDash(
                    "Courbe:N",
                    scale=alt.Scale(
                        domain=["Charge récente (7 jours)", "Charge habituelle (28 jours)"],
                        range=[[1, 0], [5, 4]],
                    ),
                    legend=None,
                ),
            )
        )
        chart_load = (
            alt.layer(bars, lines)
            .properties(height=230, background="transparent")
            .configure_view(strokeWidth=0, fill="#0D121E")
            .configure_axis(gridColor="rgba(255,255,255,0.06)", domainColor="rgba(255,255,255,0.1)")
        )
        st.altair_chart(chart_load, use_container_width=True)

        # Graphique 2 : Équilibre charge / récupération
        st.markdown("##### Équilibre charge / récupération")
        st.caption("Zone optimale : 0,8 – 1,3 • Seuil de vigilance haute : 1,5")
        sweet_min = float(zones.get("sweet_spot_min", 0.80))
        sweet_max = float(zones.get("sweet_spot_max", 1.30))
        caut_max = float(zones.get("caution_max", 1.50))
        max_acwr_val = max(1.8, float(df_d["Équilibre charge / récupération"].max() or 0.0) * 1.15)

        band_df = pd.DataFrame({
            "DateStart": [df_d["DateObj"].min()],
            "DateEnd": [df_d["DateObj"].max()],
            "yMin": [sweet_min],
            "yMax": [sweet_max],
        })
        opt_band = (
            alt.Chart(band_df)
            .mark_rect(color="#10B981", opacity=0.14)
            .encode(x="DateStart:T", x2="DateEnd:T", y="yMin:Q", y2="yMax:Q")
        )
        danger_rule = (
            alt.Chart(pd.DataFrame({"y": [caut_max]}))
            .mark_rule(color="#FB7185", strokeDash=[5, 4], strokeWidth=1.5)
            .encode(y="y:Q")
        )
        acwr_line = (
            alt.Chart(df_d)
            .mark_line(color="#FBBF24", strokeWidth=2.5, point=alt.OverlayMarkDef(color="#FBBF24", size=34))
            .encode(
                x=alt.X("DateObj:T", title=None, axis=alt.Axis(format="%d/%m", labelColor="#94A3B8", tickCount=5)),
                y=alt.Y(
                    "Équilibre charge / récupération:Q",
                    title="Indice",
                    scale=alt.Scale(domainMin=0, domain=[0, max_acwr_val]),
                    axis=alt.Axis(labelColor="#94A3B8", titleColor="#94A3B8"),
                ),
                tooltip=[
                    alt.Tooltip("Date:N", title="Date"),
                    alt.Tooltip("Équilibre charge / récupération:Q", title="Équilibre charge / récup.", format=".2f"),
                ],
            )
        )
        chart_acwr = (
            alt.layer(opt_band, danger_rule, acwr_line)
            .properties(height=185, background="transparent")
            .configure_view(strokeWidth=0, fill="#0D121E")
            .configure_axis(gridColor="rgba(255,255,255,0.06)", domainColor="rgba(255,255,255,0.1)")
        )
        st.altair_chart(chart_acwr, use_container_width=True)
    else:
        st.line_chart(df_d.set_index("Date")[["Charge récente (7 jours)", "Charge habituelle (28 jours)"]])

    # Encart synthétique Volume Hebdomadaire (7 derniers jours)
    render_html(f"""
        <div class="cali-card" style="padding:12px 14px;margin-top:0.5rem;border-color:rgba(148,163,184,0.14);">
            <div style="font-size:0.86rem;font-weight:700;color:#F8FAFC;margin-bottom:8px;">
                Volume Hebdomadaire (7 derniers jours)
            </div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;">
                <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(148,163,184,0.12);border-radius:10px;padding:8px 4px;">
                    <div style="font-size:0.65rem;color:#94A3B8;font-weight:700;text-transform:uppercase;">Temps sous tension</div>
                    <div class="cali-tabular" style="font-size:1.15rem;font-weight:800;color:#00E5FF;font-family:'JetBrains Mono',monospace;">{metrics['weekly_tut_sec']:.1f}s</div>
                </div>
                <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(148,163,184,0.12);border-radius:10px;padding:8px 4px;">
                    <div style="font-size:0.65rem;color:#94A3B8;font-weight:700;text-transform:uppercase;">Répétitions</div>
                    <div class="cali-tabular" style="font-size:1.15rem;font-weight:800;color:#34D399;font-family:'JetBrains Mono',monospace;">{metrics['weekly_reps']}</div>
                </div>
                <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(148,163,184,0.12);border-radius:10px;padding:8px 4px;">
                    <div style="font-size:0.65rem;color:#94A3B8;font-weight:700;text-transform:uppercase;">Charge ressentie</div>
                    <div class="cali-tabular" style="font-size:1.15rem;font-weight:800;color:#FBBF24;font-family:'JetBrains Mono',monospace;">{metrics['weekly_srpe']:.0f}</div>
                </div>
            </div>
        </div>
    """)

    return metrics
