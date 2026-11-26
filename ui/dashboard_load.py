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

    render_html(f"""
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:8px;margin-bottom:0.85rem;">
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Aiguë EWMA (7j)</div>
                <div class="cali-kpi-val" style="color:#00E5FF;">{metrics['acute_ewma']:.1f}<span style="font-size:0.75rem;color:#94A3B8;margin-left:3px;">UA</span></div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Chronique (28j)</div>
                <div class="cali-kpi-val" style="color:#38BDF8;">{metrics['chronic_ewma']:.1f}<span style="font-size:0.75rem;color:#94A3B8;margin-left:3px;">UA</span></div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Ratio ACWR</div>
                <div class="cali-kpi-val" style="color:{metrics['acwr_color']};">{metrics['acwr']:.2f}</div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">Foster (Mono / Contr.)</div>
                <div class="cali-kpi-val" style="font-size:1.1rem;color:#FBBF24;">{metrics['foster_monotony']:.2f} <span style="font-size:0.78rem;color:#94A3B8;">| {metrics['foster_strain']:.0f}</span></div>
            </div>
        </div>
    """)

    df_d = metrics["daily_df"].copy()
    zones = metrics["zones_cfg"]
    t_cfg = metrics["tendon_cfg"]

    try:
        import altair as alt
        has_altair = True
    except ImportError:
        has_altair = False

    if has_altair and not df_d.empty:
        df_d["DateObj"] = pd.to_datetime(df_d["Date"])

        # Graphique 1 : Charge quotidienne + Courbes EWMA (propre et lisible sur mobile)
        st.markdown("##### 📊 Charge d'entraînement (EWMA 7j vs 28j)")
        bars = (
            alt.Chart(df_d)
            .mark_bar(color="#38BDF8", opacity=0.28, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("DateObj:T", title=None, axis=alt.Axis(format="%d/%m", labelColor="#94A3B8", tickCount=6)),
                y=alt.Y("Charge Externe (UA):Q", title="Charge (UA)", axis=alt.Axis(labelColor="#94A3B8", titleColor="#94A3B8")),
                tooltip=[
                    alt.Tooltip("Date:N", title="Date"),
                    alt.Tooltip("Charge Externe (UA):Q", title="Charge du jour (UA)", format=".1f"),
                    alt.Tooltip("EWMA Aiguë (7j):Q", title="Aiguë 7j (UA)", format=".1f"),
                    alt.Tooltip("EWMA Chronique (28j):Q", title="Chronique 28j (UA)", format=".1f"),
                ],
            )
        )
        ewma_melt = df_d.melt(
            id_vars=["DateObj", "Date"],
            value_vars=["EWMA Aiguë (7j)", "EWMA Chronique (28j)"],
            var_name="Courbe",
            value_name="UA",
        )
        lines = (
            alt.Chart(ewma_melt)
            .mark_line(strokeWidth=2.5)
            .encode(
                x=alt.X("DateObj:T", title=None),
                y=alt.Y("UA:Q"),
                color=alt.Color(
                    "Courbe:N",
                    scale=alt.Scale(
                        domain=["EWMA Aiguë (7j)", "EWMA Chronique (28j)"],
                        range=["#00E5FF", "#818CF8"],
                    ),
                    legend=alt.Legend(orient="bottom", title=None, labelColor="#E2E8F0"),
                ),
                strokeDash=alt.StrokeDash(
                    "Courbe:N",
                    scale=alt.Scale(
                        domain=["EWMA Aiguë (7j)", "EWMA Chronique (28j)"],
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

        # Graphique 2 : Ratio ACWR séparé avec bande verte optimale (0.8 - 1.3)
        st.markdown("##### ⚖️ Ratio de fatigue ACWR (Aiguë / Chronique)")
        sweet_min = float(zones.get("sweet_spot_min", 0.80))
        sweet_max = float(zones.get("sweet_spot_max", 1.30))
        caut_max = float(zones.get("caution_max", 1.50))
        max_acwr_val = max(1.8, float(df_d["ACWR"].max() or 0.0) * 1.15)

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
            .mark_line(color="#FBBF24", strokeWidth=2.5, point=alt.OverlayMarkDef(color="#FBBF24", size=36))
            .encode(
                x=alt.X("DateObj:T", title=None, axis=alt.Axis(format="%d/%m", labelColor="#94A3B8", tickCount=6)),
                y=alt.Y("ACWR:Q", title="Ratio ACWR", scale=alt.Scale(domain=[0, max_acwr_val]), axis=alt.Axis(labelColor="#94A3B8", titleColor="#94A3B8")),
                tooltip=[
                    alt.Tooltip("Date:N", title="Date"),
                    alt.Tooltip("ACWR:Q", title="Ratio ACWR", format=".2f"),
                ],
            )
        )
        chart_acwr = (
            alt.layer(opt_band, danger_rule, acwr_line)
            .properties(height=190, background="transparent")
            .configure_view(strokeWidth=0, fill="#0D121E")
            .configure_axis(gridColor="rgba(255,255,255,0.06)", domainColor="rgba(255,255,255,0.1)")
        )
        st.altair_chart(chart_acwr, use_container_width=True)
        st.caption("🟩 Zone optimale : **0.80 – 1.30** • 🟥 Ligne pointillée : seuil de surcharge (**1.50**)")
    else:
        st.line_chart(df_d.set_index("Date")[["EWMA Aiguë (7j)", "EWMA Chronique (28j)"]])

    # Jauge horizontale HTML/CSS claire et responsive (zéro coupure sur mobile 390px)
    mod_th = float(t_cfg.get("weekly_moderate_threshold", 600.0))
    high_th = float(t_cfg.get("weekly_high_threshold", 1200.0))
    max_g = max(float(t_cfg.get("weekly_max_gauge", 2000.0)), metrics["weekly_tendon_au"] * 1.15)
    val_tend = float(metrics["weekly_tendon_au"])
    pct_val = min(100.0, max(0.0, (val_tend / max_g) * 100.0))
    pct_mod = min(100.0, (mod_th / max_g) * 100.0)
    pct_high = min(100.0, (high_th / max_g) * 100.0)

    if val_tend >= high_th:
        tend_badge = '<span class="badge-rose">🔴 Élevé (Décharger)</span>'
        tend_col = "#FB7185"
    elif val_tend >= mod_th:
        tend_badge = '<span class="badge-amber">🟡 Modéré (Vigilance)</span>'
        tend_col = "#FBBF24"
    else:
        tend_badge = '<span class="badge-lime">🟢 Maîtrisé</span>'
        tend_col = "#34D399"

    render_html(f"""
        <div class="cali-card" style="padding:12px 14px;margin-top:0.4rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:8px;">
                <span style="font-size:0.86rem;font-weight:800;color:#F8FAFC;">🦴 Stress Tendineux Haute Intensité (7j)</span>
                {tend_badge}
            </div>
            <div style="font-size:1.35rem;font-weight:800;color:{tend_col};margin-bottom:8px;">
                {val_tend:.0f} <span style="font-size:0.82rem;color:#94A3B8;font-weight:600;">UA / {max_g:.0f} max</span>
            </div>
            <div style="position:relative;height:14px;border-radius:999px;background:linear-gradient(90deg, rgba(16,185,129,0.45) 0%, rgba(16,185,129,0.45) {pct_mod:.1f}%, rgba(245,158,11,0.48) {pct_mod:.1f}%, rgba(245,158,11,0.48) {pct_high:.1f}%, rgba(244,63,94,0.55) {pct_high:.1f}%, rgba(244,63,94,0.55) 100%);border:1px solid rgba(255,255,255,0.12);overflow:visible;">
                <div style="position:absolute;left:calc({pct_val:.1f}% - 7px);top:-3px;width:14px;height:20px;border-radius:4px;background:#F8FAFC;border:2px solid {tend_col};box-shadow:0 0 10px {tend_col};"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#94A3B8;margin-top:6px;">
                <span>0 UA</span>
                <span>{mod_th:.0f} UA</span>
                <span>{high_th:.0f} UA (Seuil)</span>
                <span>{max_g:.0f} UA</span>
            </div>
        </div>
    """)

    return metrics
