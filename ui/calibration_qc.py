"""
ui/calibration_qc.py - Composants d'interface pour le Quality Control Gate (Diagnostic Qualité).
Affiche la carte de score sur 100, les 5 critères détaillés (✅ / ⚠️ / ❌),
les recommandations correctives et applique les règles de blocage/confirmation avant sauvegarde.
"""

from html import escape
from typing import Tuple
import streamlit as st

from core.quality_control import QualityReport
from ui.theme import render_html


_STATUS_META = {
    "PASS": {
        "icon": "",
        "badge_cls": "badge-lime",
        "label": "Vidéo valide",
        "accent": "#34D399",
        "rec_bg": "rgba(16, 185, 129, 0.08)",
    },
    "WARNING": {
        "icon": "",
        "badge_cls": "badge-amber",
        "label": "À vérifier",
        "accent": "#FBBF24",
        "rec_bg": "rgba(245, 158, 11, 0.10)",
    },
    "REJECT": {
        "icon": "",
        "badge_cls": "badge-crimson",
        "label": "Vidéo non exploitable",
        "accent": "#FB7185",
        "rec_bg": "rgba(244, 63, 94, 0.12)",
    },
}


def render_quality_diagnostic_card(report: QualityReport, compact: bool = False) -> None:
    """
    Rend la carte de vérification vidéo (score /100 + 5 contrôles + conseils correctifs).
    """
    meta = _STATUS_META.get(report.status, _STATUS_META["WARNING"])
    score = max(0, min(100, int(report.global_score)))
    safe_summary = escape(report.summary)

    with st.container(border=True):
        header_html = (
            '<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">'
            '<div>'
            f'<span class="{meta["badge_cls"]}">Vérification de la vidéo • {meta["label"]}</span>'
            f'<div style="font-size:0.82rem; color:#CBD5E1; margin-top:4px; line-height:1.35;">{safe_summary}</div>'
            '</div>'
            '<div style="text-align:right; min-width:86px;">'
            f'<div class="cali-tabular" style="font-family:\'JetBrains Mono\',monospace; font-variant-numeric:tabular-nums; font-size:1.35rem; font-weight:800; color:{meta["accent"]}; line-height:1;">{score}<span style="font-size:0.8rem; color:#94A3B8;">/100</span></div>'
            '<div style="font-size:0.68rem; color:#94A3B8; text-transform:uppercase; letter-spacing:0.05em;">Score qualité</div>'
            '</div>'
            '</div>'
        )
        render_html(header_html)
        st.progress(score / 100.0)

        rows_html = []
        row_pad = "4px 0" if compact else "6px 0"
        for chk in report.checks:
            cm = _STATUS_META.get(chk.status, _STATUS_META["WARNING"])
            rec_block = ""
            if chk.recommendation:
                rec_block = (
                    f'<div style="margin-top:3px; padding:4px 8px; border-radius:6px; '
                    f'background:{cm["rec_bg"]}; color:#F8FAFC; font-size:0.76rem; line-height:1.35;">'
                    f'<b>Conseil :</b> {escape(chk.recommendation)}'
                    '</div>'
                )
            msg_block = (
                ""
                if (compact and chk.status == "PASS") else
                f'<div style="font-size:0.78rem; color:#CBD5E1; line-height:1.35;">{escape(chk.message)}</div>'
            )
            rows_html.append(
                f'<div style="padding:{row_pad}; border-bottom:1px solid rgba(148,163,184,0.12);">'
                '<div style="display:flex; align-items:flex-start; gap:8px;">'
                f'<span style="width:8px; height:8px; margin-top:5px; border-radius:999px; background:{cm["accent"]}; flex-shrink:0;"></span>'
                '<div style="flex:1; min-width:0;">'
                f'<div style="font-size:0.82rem; font-weight:700; color:#F8FAFC;">{escape(chk.title)} '
                f'<span class="cali-tabular" style="font-family:\'JetBrains Mono\',monospace; font-variant-numeric:tabular-nums; font-size:0.72rem; color:{cm["accent"]}; font-weight:700;">({chk.score}/100)</span></div>'
                f'{msg_block}'
                f'{rec_block}'
                '</div>'
                '</div>'
                '</div>'
            )

        render_html('<div style="margin-top:4px;">' + "".join(rows_html) + '</div>')


def render_qc_save_gate(
    report: QualityReport,
    save_button_key: str,
    confirm_checkbox_key: str,
    button_label: str = "Enregistrer cette figure"
) -> Tuple[bool, bool]:
    """
    Applique la règle de validation après vérification vidéo :
    - PASS (Vidéo valide) : bouton actif directement.
    - WARNING (À vérifier) : confirmation demandée avant enregistrement.
    - REJECT (Vidéo non exploitable) : enregistrement bloqué.
    """
    if report.status == "REJECT":
        st.error(
            "**Vidéo non exploitable :** corrigez les points signalés ci-dessus et filmez à nouveau en suivant le guide."
        )
        st.button(
            button_label,
            key=save_button_key,
            type="primary",
            use_container_width=True,
            disabled=True,
        )
        return False, False

    if report.status == "WARNING":
        st.warning(
            "**À vérifier :** contrôlez les remarques ci-dessus avant d'enregistrer cette figure de référence."
        )
        confirmed = st.checkbox(
            "Confirmer l'enregistrement malgré l'avertissement",
            key=confirm_checkbox_key,
        )
        clicked = st.button(
            button_label,
            key=save_button_key,
            type="primary",
            use_container_width=True,
            disabled=(not confirmed),
        )
        return bool(clicked and confirmed), bool(confirmed)

    clicked = st.button(
        button_label,
        key=save_button_key,
        type="primary",
        use_container_width=True,
        disabled=False,
    )
    return bool(clicked), False
