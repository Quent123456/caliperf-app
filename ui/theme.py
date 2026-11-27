"""
ui/theme.py - Design System 'Kinetic Obsidian & Electric Telemetry' & Moteur de Swipe Fluide V4.
Fournit :
- L'injection du thème CSS complet (typography, glassmorphism carbone, badges, responsive mobile-first).
- La fonction render_html() immunisée contre le bug CommonMark (<pre><code> sur indentations >= 4).
- Le moteur de geste tactile V4 avec prévisualisation progressive en direct (Live Peek Side-by-Side) :
  la page suivante glisse et apparaît progressivement sous le doigt à 60/120fps sans flash ni saccade.
"""

import inspect
import streamlit as st
import streamlit.components.v1 as components


def render_html(html_str: str) -> None:
    """
    Rend du HTML brut dans Streamlit en supprimant toute indentation en début de ligne
    et les lignes vides, garantissant que Markdown (CommonMark) n'interprète jamais
    les balises comme un bloc de code préformaté.
    """
    cleaned = "\n".join(line.lstrip() for line in html_str.strip().splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700;800&display=swap');

:root {
    --cali-bg: #05070C;
    --cali-surface: rgba(13, 18, 30, 0.86);
    --cali-surface-solid: #0D121E;
    --cali-surface-elevated: rgba(19, 27, 45, 0.92);
    --cali-border: rgba(255, 255, 255, 0.08);
    --cali-border-strong: rgba(255, 255, 255, 0.14);
    --cali-cyan: #00E5FF;
    --cali-sky: #0EA5E9;
    --cali-emerald: #10B981;
    --cali-amber: #F59E0B;
    --cali-crimson: #F43F5E;
    --cali-gold: #FBBF24;
    --cali-text: #F8FAFC;
    --cali-muted: #94A3B8;
    --cali-dim: #64748B;
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-tap-highlight-color: transparent;
    color: var(--cali-text);
    touch-action: pan-y pinch-zoom;
    overscroll-behavior-x: none;
}

html, body,
[data-testid="stAppViewContainer"],
.main,
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
[data-testid="stVerticalBlock"]:has(#caliperf-active-view) {
    overflow-x: clip !important;
    max-width: 100vw !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stTabs"],
[data-baseweb="tab-panel"],
.cali-card,
.cali-card-accent,
[data-testid="stExpander"] {
    touch-action: pan-y pinch-zoom;
    overscroll-behavior-x: none;
}

[data-testid="stAppViewContainer"] {
    background-color: var(--cali-bg);
    background-image:
        radial-gradient(ellipse 80% 50% at 15% -5%, rgba(0, 229, 255, 0.085) 0%, transparent 60%),
        radial-gradient(ellipse 65% 45% at 88% 8%, rgba(14, 165, 233, 0.06) 0%, transparent 55%),
        linear-gradient(rgba(255, 255, 255, 0.014) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.014) 1px, transparent 1px);
    background-size: 100% 100%, 100% 100%, 36px 36px, 36px 36px;
    color: var(--cali-text);
}

/* Masquer proprement la hauteur des scripts invisibles (sans display:none qui suspend les iframes) */
[data-testid="stElementContainer"]:has(iframe[height="0"]),
[data-testid="stElementContainer"]:has(iframe[srcdoc*="cali-"]),
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) [data-testid="stElementContainer"]:has(iframe),
.element-container:has(iframe[height="0"]),
[data-testid="stElementContainer"]:has([data-cali-js]),
.element-container:has([data-cali-js]) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
    pointer-events: none !important;
}

/* Header responsive sur une seule ligne sans troncature */
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) {
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 5px !important;
    margin-bottom: 0.25rem !important;
    width: 100% !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"] {
    min-width: 0 !important;
    width: auto !important;
    padding: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) {
    flex: 0 0 38px !important;
    width: 38px !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(2) {
    flex: 0 0 auto !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(3) {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    display: flex !important;
    justify-content: flex-end !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(4) {
    flex: 0 0 36px !important;
    width: 36px !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) [data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(4) [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) [data-testid="stElementContainer"]:has(#caliperf-header-exit-marker) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) button,
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(4) button {
    min-height: 36px !important;
    height: 36px !important;
    padding: 0 !important;
    border-radius: 10px !important;
    background: rgba(13, 18, 30, 0.88) !important;
}

/* Padding haut adapté notch smartphone & marge basse pour Manage app (75px) */
.block-container {
    padding-top: calc(3.85rem + env(safe-area-inset-top, 0px)) !important;
    padding-bottom: calc(75px + env(safe-area-inset-bottom, 0px)) !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
    max-width: 1240px !important;
}

[data-testid="stHeader"] {
    background: rgba(5, 7, 12, 0.78) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    height: 3.3rem !important;
}

@media (min-width: 769px) {
    .block-container {
        padding-top: 2.2rem !important;
        padding-bottom: 75px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
}

/* Dock de navigation 5 pilules fixes (100% visible sur 390px, zéro scroll horizontal) */
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) {
    position: relative !important;
    flex-wrap: nowrap !important;
    gap: 4px !important;
    background: rgba(11, 16, 28, 0.92) !important;
    padding: 5px !important;
    border-radius: 15px !important;
    border: 1px solid rgba(255, 255, 255, 0.09) !important;
    margin-bottom: 0.55rem !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 8px 24px rgba(0, 0, 0, 0.35) !important;
    width: 100% !important;
    overflow: hidden !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) > [data-testid="stColumn"] {
    position: relative !important;
    z-index: 2 !important;
    flex: 1 1 0 !important;
    min-width: 0 !important;
    width: auto !important;
    padding: 0 !important;
}
#caliperf-dock-glider {
    position: absolute !important;
    top: 5px !important;
    left: 0 !important;
    height: 44px !important;
    border-radius: 10px !important;
    background: linear-gradient(135deg, #00E5FF 0%, #0EA5E9 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 3px 12px rgba(0, 229, 255, 0.34) !important;
    z-index: 1 !important;
    pointer-events: none !important;
    will-change: transform, width;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker)[data-cali-glider="1"] button[kind="primary"],
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker)[data-cali-glider="1"] button[kind="secondary"],
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker)[data-cali-glider="1"] button.cali-dock-optimistic-on,
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker)[data-cali-glider="1"] button.cali-dock-optimistic-off {
    background: transparent !important;
    border-color: transparent !important;
    box-shadow: none !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) > [data-testid="stColumn"]:nth-child(1) [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) [data-testid="stElementContainer"]:has(#caliperf-nav-marker) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) button {
    min-height: 44px !important;
    height: 44px !important;
    padding: 2px 2px !important;
    border-radius: 10px !important;
    border: 1px solid transparent !important;
    line-height: 1.15 !important;
    transition: background 0.18s ease, transform 0.15s ease !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) button p {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    white-space: pre-line !important;
    text-align: center !important;
    margin: 0 !important;
    line-height: 1.15 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) button[kind="secondary"] {
    background: transparent !important;
    color: var(--cali-muted) !important;
    box-shadow: none !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) button[kind="primary"] {
    background: linear-gradient(135deg, #00E5FF 0%, #0EA5E9 100%) !important;
    color: #020617 !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 3px 12px rgba(0, 229, 255, 0.3) !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-nav-marker) button[kind="primary"] p {
    color: #020617 !important;
    font-weight: 800 !important;
}
[data-testid="stElementContainer"]:has(#caliperf-active-view) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
/* Scène Pager Swipe Instagram-like (position fixed hors flux = zéro scrollWidth/décalage) */
#caliperf-swipe-stage {
    position: fixed !important;
    left: 0 !important;
    width: 100vw !important;
    max-width: 100vw !important;
    overflow: hidden !important;
    pointer-events: none !important;
    z-index: 45 !important;
    box-sizing: border-box !important;
}
#caliperf-swipe-incoming {
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    background: #05070C !important;
    background-image:
        radial-gradient(ellipse 80% 50% at 15% -5%, rgba(0, 229, 255, 0.085) 0%, transparent 60%),
        linear-gradient(rgba(255, 255, 255, 0.014) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.014) 1px, transparent 1px) !important;
    background-size: 100% 100%, 36px 36px, 36px 36px !important;
    padding: 0.45rem 0.85rem 80px 0.85rem !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
    border-left: 1px solid rgba(255, 255, 255, 0.10) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.10) !important;
    box-shadow: -14px 0 36px rgba(0, 0, 0, 0.72), 14px 0 36px rgba(0, 0, 0, 0.72) !important;
    will-change: transform, opacity;
}
.cali-ghost-card {
    background: rgba(13, 18, 30, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 16px;
    padding: 1rem 1.05rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
}
.cali-ghost-badge {
    display: inline-block;
    font-size: 0.66rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #00E5FF;
    background: rgba(0, 229, 255, 0.10);
    border: 1px solid rgba(0, 229, 255, 0.28);
    border-radius: 999px;
    padding: 2px 9px;
    margin-bottom: 0.45rem;
}
.cali-ghost-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #F8FAFC;
    margin-bottom: 0.25rem;
}
.cali-ghost-sub {
    font-size: 0.82rem;
    color: #94A3B8;
    line-height: 1.35;
}
.cali-ghost-bar {
    height: 10px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.07);
    margin-top: 0.65rem;
}
.cali-dock-optimistic-on {
    background: linear-gradient(135deg, #00E5FF 0%, #0EA5E9 100%) !important;
    color: #020617 !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 3px 12px rgba(0, 229, 255, 0.3) !important;
}
.cali-dock-optimistic-on p {
    color: #020617 !important;
    font-weight: 800 !important;
}
.cali-dock-optimistic-off {
    background: transparent !important;
    color: var(--cali-muted) !important;
    box-shadow: none !important;
}
.cali-dock-optimistic-off p {
    color: var(--cali-muted) !important;
    font-weight: 700 !important;
}

/* Vidéo responsive (ergonomie mobile : voir vidéo + chrono ensemble) */
video {
    max-height: 40vh !important;
    width: 100% !important;
    object-fit: contain !important;
    background: #020306 !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55) !important;
}

@media (min-width: 769px) {
    video {
        max-height: 54vh !important;
    }
}

/* ==========================================================================
   DOCK DE NAVIGATION SEGMENTÉ & ANIMATION SWIPE FLUIDE
   ========================================================================== */
.stTabs > div,
[data-testid="stTabs"] > div {
    position: relative !important;
    overflow-x: clip !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 6px !important;
    background: rgba(11, 16, 28, 0.9) !important;
    padding: 5px !important;
    border-radius: 16px !important;
    border: 1px solid rgba(255, 255, 255, 0.09) !important;
    display: flex !important;
    margin-bottom: 0.55rem !important;
    overflow-x: auto !important;
    scrollbar-width: none !important;
    -ms-overflow-style: none !important;
    -webkit-overflow-scrolling: touch !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 8px 24px rgba(0, 0, 0, 0.35) !important;
}

.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none !important;
}

.stTabs [data-baseweb="tab-border"],
.stTabs [data-baseweb="tab-highlight"] {
    display: none !important;
}

.stTabs [data-baseweb="tab"] {
    flex: 1 0 auto !important;
    min-height: 44px !important;
    padding: 0 14px !important;
    border-radius: 11px !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
    color: var(--cali-muted) !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    text-align: center !important;
    white-space: nowrap !important;
    transition: color 0.22s ease, background 0.22s ease, transform 0.2s cubic-bezier(0.22, 1, 0.36, 1) !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--cali-text) !important;
    background: rgba(255, 255, 255, 0.04) !important;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #00E5FF 0%, #0EA5E9 100%) !important;
    color: #020617 !important;
    font-weight: 800 !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 4px 16px rgba(0, 229, 255, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.35) !important;
}

/* Panneaux : Live Peek pendant swipe + transitions directionnelles nettes */
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 0.5rem !important;
    transform-origin: center top;
    backface-visibility: hidden;
    -webkit-backface-visibility: hidden;
}

[data-testid="stTabs"] [data-baseweb="tab-panel"].cali-swipe-peek,
[data-baseweb="tab-panel"].cali-swipe-peek[hidden] {
    display: block !important;
    visibility: visible !important;
}

[data-baseweb="tab-panel"].cali-enter-right {
    animation: caliPanelEnterRight 0.28s cubic-bezier(0.22, 1, 0.36, 1) both;
    will-change: transform, opacity;
}

[data-baseweb="tab-panel"].cali-enter-left {
    animation: caliPanelEnterLeft 0.28s cubic-bezier(0.22, 1, 0.36, 1) both;
    will-change: transform, opacity;
}

[data-cali-silent="1"] [data-baseweb="tab-panel"] {
    animation: none !important;
}

@keyframes caliPanelEnterRight {
    0% {
        opacity: 0.25;
        transform: translate3d(44px, 0, 0) scale(0.985);
    }
    100% {
        opacity: 1;
        transform: translate3d(0, 0, 0) scale(1);
    }
}

@keyframes caliPanelEnterLeft {
    0% {
        opacity: 0.25;
        transform: translate3d(-44px, 0, 0) scale(0.985);
    }
    100% {
        opacity: 1;
        transform: translate3d(0, 0, 0) scale(1);
    }
}

@media (prefers-reduced-motion: reduce) {
    [data-baseweb="tab-panel"].cali-enter-right,
    [data-baseweb="tab-panel"].cali-enter-left {
        animation: caliFadeSimple 0.14s ease both;
    }
    @keyframes caliFadeSimple {
        from { opacity: 0.4; }
        to { opacity: 1; }
    }
}

/* Indicateur de progression & lueur latérale de swipe */
.cali-swipe-hud {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin: -0.1rem 0 0.45rem 0;
    user-select: none;
}

.cali-swipe-dots {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 9999px;
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.06);
}

.cali-swipe-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.35);
    transition: width 0.25s cubic-bezier(0.22, 1, 0.36, 1), background 0.25s ease, opacity 0.2s ease;
}

.cali-swipe-dot.active {
    width: 20px;
    background: linear-gradient(90deg, #00E5FF, #0EA5E9);
    box-shadow: 0 0 8px rgba(0, 229, 255, 0.55);
}

.cali-swipe-label {
    font-size: 0.68rem;
    color: var(--cali-dim);
    font-weight: 600;
    letter-spacing: 0.03em;
}

/* ==========================================================================
   SURFACES GLASSMORPHISM CARBONE & CARTES
   ========================================================================== */
.cali-card {
    background: var(--cali-surface);
    border: 1px solid var(--cali-border);
    border-radius: 16px;
    padding: 1rem 1.15rem;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 10px 30px rgba(0, 0, 0, 0.4);
    margin-bottom: 0.85rem;
    transition: border-color 0.2s ease;
}

.cali-card-accent {
    background: linear-gradient(160deg, rgba(0, 229, 255, 0.07) 0%, rgba(13, 18, 30, 0.92) 60%);
    border: 1px solid rgba(0, 229, 255, 0.26);
    border-radius: 16px;
    padding: 1rem 1.15rem;
    box-shadow: inset 0 1px 0 rgba(0, 229, 255, 0.12), 0 12px 32px rgba(0, 0, 0, 0.45);
    margin-bottom: 0.85rem;
}

.cali-kpi-tile {
    background: rgba(13, 18, 30, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 14px;
    padding: 0.8rem 0.9rem;
    text-align: left;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.cali-kpi-val {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 1.5rem;
    font-weight: 800;
    color: var(--cali-text);
    line-height: 1.15;
    margin-top: 2px;
}

.cali-kpi-lbl {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--cali-muted);
}

/* Badges sémantiques */
.badge-cyan, .badge-lime, .badge-amber, .badge-gold, .badge-crimson {
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
}
.badge-cyan { background: rgba(0, 229, 255, 0.12); color: #22D3EE; border: 1px solid rgba(0, 229, 255, 0.35); }
.badge-lime { background: rgba(16, 185, 129, 0.14); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.35); }
.badge-amber { background: rgba(245, 158, 11, 0.14); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.35); }
.badge-gold { background: rgba(251, 191, 36, 0.16); color: #FDE047; border: 1px solid rgba(251, 191, 36, 0.42); }
.badge-crimson { background: rgba(244, 63, 94, 0.15); color: #FB7185; border: 1px solid rgba(244, 63, 94, 0.38); }

/* Chronomètre digital télémétrique (Chiffres tabulaires) */
.digital-timer {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 2.75rem;
    font-weight: 800;
    color: var(--cali-cyan);
    text-shadow: 0 0 22px rgba(0, 229, 255, 0.42);
    letter-spacing: -0.025em;
    line-height: 1.05;
    margin: 0.15rem 0 0.35rem 0;
}

.digital-sub {
    font-size: 0.72rem;
    color: var(--cali-muted);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* Indicateur RPE */
.rpe-indicator {
    padding: 8px 12px;
    border-radius: 10px;
    margin-top: 6px;
    font-size: 0.82rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
}
.rpe-low { background: rgba(16, 185, 129, 0.14); border-left: 3px solid #10B981; color: #6EE7B7; }
.rpe-mod { background: rgba(14, 165, 233, 0.14); border-left: 3px solid #0EA5E9; color: #7DD3FC; }
.rpe-opt { background: rgba(245, 158, 11, 0.14); border-left: 3px solid #F59E0B; color: #FDE68A; }
.rpe-max { background: rgba(244, 63, 94, 0.18); border-left: 3px solid #F43F5E; color: #FDA4AF; }

/* Boutons ergonomiques tactiles >= 44px */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    border-radius: 11px !important;
    font-weight: 700 !important;
    min-height: 44px !important;
    font-size: 0.9rem !important;
    transition: transform 0.14s ease, box-shadow 0.18s ease, border-color 0.18s ease !important;
    border: 1px solid rgba(255, 255, 255, 0.11) !important;
}

.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00E5FF 0%, #0EA5E9 100%) !important;
    color: #020617 !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 4px 16px rgba(0, 229, 255, 0.25) !important;
}

.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 22px rgba(0, 229, 255, 0.42) !important;
}

.stButton > button:active,
.stFormSubmitButton > button:active {
    transform: scale(0.97) !important;
}

/* Expanders épurés */
[data-testid="stExpander"] {
    background: rgba(11, 16, 28, 0.72) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 14px !important;
    overflow: hidden;
}

/* Protection tactile des éléments horizontaux (Dataframes, Graphiques, Vidéo) */
[data-testid="stDataFrame"], .stDataFrame, [data-testid="stTable"], .stTable,
table, .js-plotly-plot, .no-swipe {
    touch-action: pan-x pan-y !important;
    -webkit-overflow-scrolling: touch !important;
}

/* Zone d'import vidéo : autorise le défilement vertical et libère le swipe horizontal JS */
[data-testid="stFileUploader"], [data-testid="stFileUploaderDropzone"] {
    touch-action: pan-y pinch-zoom !important;
}
</style>
"""


# ATTENTION : N'utilisez aucun commentaire // sur une seule ligne dans ce script.
# Tous les commentaires doivent utiliser /* ... */ pour rester valides en toute circonstance.
SWIPE_ENGINE_JS = r"""
(function() {
    var targetWin = window;
    var targetDoc = document;
    /* Monter vers window.parent uniquement si exécuté dans un iframe component isolé */
    try {
        if (!document.querySelector('[data-testid="stAppViewContainer"]') && window.parent && window.parent.document) {
            targetWin = window.parent;
            targetDoc = window.parent.document;
        }
    } catch (e) {}

    /* Nettoyage propre si une version précédente du gestionnaire était attachée */
    if (targetWin._caliperfSwipeCleanup) {
        try { targetWin._caliperfSwipeCleanup(); } catch (errClean) {}
    }

    targetWin._caliperfTabSnaps = targetWin._caliperfTabSnaps || {};

    var TAB_META = [
        { icon: '🎥', name: 'Studio Vidéo', sub: 'Auto-Track 3D, Répétitions & Fatigue Intra-Série', badge: 'BIOMÉCANIQUE 3D' },
        { icon: '📐', name: 'Calibrage 3D', sub: 'Bibliothèque de Figures & Contrôle Qualité', badge: 'RÉFÉRENTIELS' },
        { icon: '📊', name: 'Stats & ACWR', sub: 'Charge Hebdomadaire, EWMA & Stress Tendineux', badge: 'SUIVI LONGITUDINAL' },
        { icon: '👥', name: 'Athlètes', sub: 'Effectif, Profils & Suivi Personnalisé', badge: 'ESPACE COACH' },
        { icon: '⚙️', name: 'Réglages', sub: 'Profil, Apparence & Export CSV', badge: 'CONFIGURATION' }
    ];

    var state = {
        mode: 'dock',
        stContainer: null,
        tabsRoot: null,
        tabs: [],
        panels: [],
        blocks: [],
        lastActiveIdx: 0,
        startX: 0,
        startY: 0,
        currentX: 0,
        currentY: 0,
        dx: 0,
        samples: [],
        isTracking: false,
        isHorizontal: false,
        isVerticalScroll: false,
        navLockUntil: 0,
        targetIdx: null,
        dir: 0,
        vw: 390,
        rafId: null,
        stageTimer: null,
        snapTimer: null,
        snapScheduledTab: null,
        dragRendered: false
    };

    var noSwipeSelector = [
        'input[type="range"]', 'select',
        'video', 'audio', '.stVideo', '.stAudio',
        '[role="slider"]', '.stSlider', '[data-baseweb="slider"]',
        'pre', 'code',
        '[data-testid="stDataFrame"]', '.stDataFrame',
        '[data-testid="stTable"]', '.stTable',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        '[role="grid"]', '[role="treegrid"]', '[role="row"]', '[role="gridcell"]',
        '.glideDataEditor', 'canvas',
        '[data-testid="stPlotlyChart"]', '.js-plotly-plot', '.plotly', 'svg.main-svg', '.draglayer',
        '[data-testid="stVegaLiteChart"]', '.vega-embed',
        '[data-baseweb="tab-list"]', '[data-baseweb="tab"]', '[role="tab"]',
        '.stSelectbox', '[role="combobox"]', '[role="listbox"]',
        '[role="dialog"]', '[data-testid="stDialog"]', '[data-baseweb="modal"]', '[data-baseweb="popover"]',
        '[data-no-swipe]', '.no-swipe'
    ].join(', ');

    function getNavRow() {
        var navMark = targetDoc.getElementById('caliperf-nav-marker');
        if (!navMark) return null;
        return navMark.closest('[data-testid="stHorizontalBlock"]');
    }

    function getDockButtons() {
        var navRow = getNavRow();
        if (!navRow) return [];
        return Array.from(navRow.querySelectorAll('button'));
    }

    function getActiveViewMarker() {
        return targetDoc.getElementById('caliperf-active-view');
    }

    function getDockContentBlocks() {
        var viewMarker = getActiveViewMarker();
        if (!viewMarker) return [];
        var markerContainer = viewMarker.closest('[data-testid="stElementContainer"], .element-container');
        if (!markerContainer || !markerContainer.parentElement) return [];
        var out = [];
        var cur = markerContainer.nextElementSibling;
        while (cur) {
            if (cur.getAttribute && cur.getAttribute('data-stale') === 'true') {
                cur = cur.nextElementSibling;
                continue;
            }
            if (cur.querySelector && (cur.querySelector('[data-cali-js]') || cur.querySelector('iframe[height="0"]'))) {
                cur = cur.nextElementSibling;
                continue;
            }
            out.push(cur);
            cur = cur.nextElementSibling;
        }
        return out;
    }

    function getDirectTabs(stEl) {
        if (!stEl) return [];
        return Array.from(stEl.querySelectorAll('button[data-baseweb="tab"], [role="tab"]')).filter(function(btn) {
            return btn.closest('[data-testid="stTabs"], .stTabs') === stEl;
        });
    }

    function getActiveIndex(tabs) {
        for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].getAttribute('aria-selected') === 'true') return i;
        }
        return 0;
    }

    function resolveNavMode(touchTarget) {
        var navRow = getNavRow();
        if (navRow) {
            var navBtns = Array.from(navRow.querySelectorAll('button'));
            if (navBtns.length > 0) {
                var viewMarker = getActiveViewMarker();
                var activeIdx = viewMarker ? parseInt(viewMarker.getAttribute('data-tab-idx') || '0', 10) : -1;
                if (isNaN(activeIdx) || activeIdx < 0 || activeIdx >= navBtns.length) {
                    activeIdx = 0;
                    for (var i = 0; i < navBtns.length; i++) {
                        if (navBtns[i].getAttribute('kind') === 'primary') { activeIdx = i; break; }
                    }
                }
                return { mode: 'dock', stEl: navRow, tabs: navBtns, activeIdx: activeIdx };
            }
        }
        var stEl = null;
        if (touchTarget && touchTarget.closest) {
            stEl = touchTarget.closest('[data-testid="stTabs"], .stTabs');
        }
        if (!stEl) stEl = targetDoc.querySelector('[data-testid="stTabs"], .stTabs');
        if (!stEl) return null;
        var tabs = getDirectTabs(stEl);
        return { mode: 'tabs', stEl: stEl, tabs: tabs, activeIdx: getActiveIndex(tabs) };
    }

    function syncProgressDots(activeIdx, previewIdx, progress) {
        var dotsWrap = targetDoc.getElementById('caliperf-swipe-dots');
        if (!dotsWrap) return;
        var dots = dotsWrap.querySelectorAll('.cali-swipe-dot');
        for (var i = 0; i < dots.length; i++) {
            if (i === activeIdx) {
                dots[i].classList.add('active');
                if (previewIdx !== null && progress > 0) {
                    var w = Math.max(6, 20 - progress * 14);
                    dots[i].style.width = w.toFixed(1) + 'px';
                    dots[i].style.opacity = (1 - progress * 0.45).toFixed(2);
                } else {
                    dots[i].style.width = '';
                    dots[i].style.opacity = '';
                }
            } else if (previewIdx !== null && i === previewIdx && progress > 0) {
                dots[i].classList.remove('active');
                var pw = 6 + progress * 14;
                dots[i].style.width = pw.toFixed(1) + 'px';
                dots[i].style.background = 'linear-gradient(90deg, rgba(0,229,255,' + (0.4 + progress * 0.6).toFixed(2) + '), #0EA5E9)';
            } else {
                dots[i].classList.remove('active');
                dots[i].style.width = '';
                dots[i].style.background = '';
                dots[i].style.opacity = '';
            }
        }
    }

    function ensureDockGlider(navRow) {
        if (!navRow) return null;
        navRow.setAttribute('data-cali-glider', '1');
        var glider = navRow.querySelector('#caliperf-dock-glider');
        if (!glider) {
            glider = targetDoc.createElement('div');
            glider.id = 'caliperf-dock-glider';
            glider.setAttribute('aria-hidden', 'true');
            var prev = targetWin._caliperfGliderState;
            if (prev && typeof prev.x === 'number' && typeof prev.w === 'number') {
                glider.style.transition = 'none';
                glider.style.transform = 'translate3d(' + prev.x.toFixed(1) + 'px, 0, 0)';
                glider.style.width = prev.w.toFixed(1) + 'px';
            }
            navRow.insertBefore(glider, navRow.firstChild);
            if (prev) {
                void glider.offsetWidth;
            }
        }
        return glider;
    }

    function lerpRgb(c1, c2, t) {
        var r = Math.round(c1[0] + (c2[0] - c1[0]) * t);
        var g = Math.round(c1[1] + (c2[1] - c1[1]) * t);
        var b = Math.round(c1[2] + (c2[2] - c1[2]) * t);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }

    function syncDockGlider(activeIdx, previewIdx, progress, animate) {
        var navRow = getNavRow();
        if (!navRow) return;
        var btns = getDockButtons();
        if (!btns.length || !btns[activeIdx]) return;
        var glider = ensureDockGlider(navRow);
        if (!glider) return;

        var navRect = navRow.getBoundingClientRect();
        var rA = btns[activeIdx].getBoundingClientRect();
        if (rA.width <= 0) return;

        var x = rA.left - navRect.left;
        var w = rA.width;
        var topPx = Math.round(rA.top - navRect.top);
        var hPx = Math.round(rA.height);

        var hasPreview = (previewIdx !== null && typeof previewIdx === 'number' && progress > 0 && btns[previewIdx]);
        if (hasPreview) {
            var rB = btns[previewIdx].getBoundingClientRect();
            if (rB.width > 0) {
                x = (rA.left - navRect.left) + (rB.left - rA.left) * progress;
                w = rA.width + (rB.width - rA.width) * progress;
            }
        }

        glider.style.top = topPx + 'px';
        glider.style.height = hPx + 'px';
        glider.style.transition = animate
            ? 'transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), width 0.28s cubic-bezier(0.22, 1, 0.36, 1)'
            : 'none';
        glider.style.transform = 'translate3d(' + x.toFixed(1) + 'px, 0, 0)';
        glider.style.width = w.toFixed(1) + 'px';
        targetWin._caliperfGliderState = { idx: activeIdx, x: x, w: w };

        var dark = [2, 6, 23];
        var muted = [148, 163, 184];
        for (var i = 0; i < btns.length; i++) {
            var pEl = btns[i].querySelector('p') || btns[i];
            if (hasPreview) {
                if (i === activeIdx) {
                    pEl.style.setProperty('color', lerpRgb(dark, muted, progress), 'important');
                } else if (i === previewIdx) {
                    pEl.style.setProperty('color', lerpRgb(muted, dark, progress), 'important');
                } else {
                    pEl.style.setProperty('color', 'rgb(148,163,184)', 'important');
                }
            } else {
                pEl.style.removeProperty('color');
            }
        }
    }

    function setOptimisticDock(targetIdx) {
        var btns = getDockButtons();
        for (var i = 0; i < btns.length; i++) {
            btns[i].classList.remove('cali-dock-optimistic-on', 'cali-dock-optimistic-off');
            if (i === targetIdx) {
                btns[i].classList.add('cali-dock-optimistic-on');
            } else {
                btns[i].classList.add('cali-dock-optimistic-off');
            }
        }
    }

    function clearOptimisticDock() {
        var btns = getDockButtons();
        for (var i = 0; i < btns.length; i++) {
            btns[i].classList.remove('cali-dock-optimistic-on', 'cali-dock-optimistic-off');
        }
    }

    function isInsideScrollableOrBlocked(el) {
        if (!el) return false;
        var navRow = getNavRow();
        if (navRow && navRow.contains(el)) return true;
        var editableEl = el.closest ? el.closest('input:not([type="file"]):not([type="range"]), textarea') : null;
        if (editableEl && editableEl === targetDoc.activeElement) return true;
        if (el.closest && el.closest(noSwipeSelector)) return true;
        var curr = el;
        while (curr && curr !== targetDoc.body && curr !== targetDoc.documentElement) {
            var tid = curr.getAttribute ? curr.getAttribute('data-testid') : '';
            if (
                (curr.getAttribute && curr.getAttribute('data-baseweb') === 'tab-panel') ||
                tid === 'stMainBlockContainer' ||
                tid === 'stMain' ||
                tid === 'stAppViewContainer'
            ) {
                break;
            }
            if (curr.nodeType === 1) {
                try {
                    var style = targetWin.getComputedStyle(curr);
                    var ox = style.overflowX;
                    if ((ox === 'auto' || ox === 'scroll') && curr.scrollWidth > curr.clientWidth + 6) {
                        return true;
                    }
                } catch (errStyle) {}
            }
            curr = curr.parentElement;
        }
        return false;
    }

    function triggerResizePulse() {
        try {
            targetWin.dispatchEvent(new Event('resize'));
        } catch (errR) {}
    }

    function clearBlockStyles(blocks) {
        if (!blocks) return;
        for (var i = 0; i < blocks.length; i++) {
            var b = blocks[i];
            if (!b) continue;
            if (b.getAnimations) {
                try {
                    var anims = b.getAnimations();
                    for (var j = 0; j < anims.length; j++) anims[j].cancel();
                } catch (ea) {}
            }
            b.style.transition = '';
            b.style.transform = '';
            b.style.opacity = '';
            b.style.willChange = '';
        }
    }

    function clearAllSiblingsStyles() {
        var viewMarker = getActiveViewMarker();
        if (!viewMarker) return;
        var mc = viewMarker.closest('[data-testid="stElementContainer"], .element-container');
        if (!mc) return;
        var all = [];
        var cur = mc.nextElementSibling;
        while (cur) {
            all.push(cur);
            cur = cur.nextElementSibling;
        }
        clearBlockStyles(all);
    }

    function buildGhostCardHtml(idx) {
        var m = TAB_META[idx] || { icon: '⚡', name: 'CaliPerf', sub: 'Chargement de la vue...', badge: 'CALIPERF PRO' };
        return (
            '<div class="cali-ghost-card">' +
                '<div class="cali-ghost-badge">' + m.badge + '</div>' +
                '<div class="cali-ghost-title">' + m.icon + ' ' + m.name + '</div>' +
                '<div class="cali-ghost-sub">' + m.sub + '</div>' +
                '<div class="cali-ghost-bar" style="width:72%;"></div>' +
            '</div>' +
            '<div class="cali-ghost-card" style="opacity:0.78;">' +
                '<div class="cali-ghost-bar" style="width:44%;margin-top:0;"></div>' +
                '<div class="cali-ghost-bar" style="width:92%;height:42px;border-radius:12px;"></div>' +
                '<div class="cali-ghost-bar" style="width:65%;"></div>' +
            '</div>'
        );
    }

    function captureTabSnapshot(tabIdx) {
        if (typeof tabIdx !== 'number' || tabIdx < 0 || tabIdx > 4) return;
        var blocks = getDockContentBlocks();
        if (!blocks.length) return;
        try {
            var parts = [];
            for (var i = 0; i < blocks.length && parts.length < 6; i++) {
                if ((blocks[i].offsetHeight || 0) < 6) continue;
                var clone = blocks[i].cloneNode(true);
                var bad = clone.querySelectorAll('script, style, iframe, video, audio, input, select, textarea, form');
                for (var j = 0; j < bad.length; j++) {
                    var ph = targetDoc.createElement('div');
                    var tag = bad[j].tagName;
                    if (tag === 'VIDEO' || tag === 'IFRAME' || tag === 'AUDIO') {
                        ph.style.cssText = 'height:110px;border-radius:12px;background:rgba(13,18,30,0.85);border:1px solid rgba(255,255,255,0.06);margin:6px 0;';
                    } else {
                        ph.style.cssText = 'display:none;';
                    }
                    if (bad[j].parentNode) bad[j].parentNode.replaceChild(ph, bad[j]);
                }
                var allAttrs = clone.querySelectorAll('[id], [name], [for]');
                for (var k = 0; k < allAttrs.length; k++) {
                    allAttrs[k].removeAttribute('id');
                    allAttrs[k].removeAttribute('name');
                    allAttrs[k].removeAttribute('for');
                }
                if (clone.removeAttribute) clone.removeAttribute('id');
                parts.push(clone.outerHTML);
            }
            var htmlStr = parts.join('');
            if (htmlStr && htmlStr.length > 400 && htmlStr.length < 180000) {
                targetWin._caliperfTabSnaps[tabIdx] = htmlStr;
            }
        } catch (errSnap) {}
    }

    function removeSwipeStage() {
        if (state.stageTimer) {
            targetWin.clearTimeout(state.stageTimer);
            state.stageTimer = null;
        }
        var oldStage = targetDoc.getElementById('caliperf-swipe-stage');
        if (oldStage && oldStage.parentNode) {
            oldStage.parentNode.removeChild(oldStage);
        }
    }

    function dissolveSwipeStage() {
        var stage = targetDoc.getElementById('caliperf-swipe-stage');
        if (!stage) return;
        if (state.stageTimer) {
            targetWin.clearTimeout(state.stageTimer);
            state.stageTimer = null;
        }
        stage.style.transition = 'opacity 140ms ease-out';
        stage.style.opacity = '0';
        state.stageTimer = targetWin.setTimeout(function() {
            removeSwipeStage();
        }, 150);
    }

    function ensureSwipeStage(targetIdx) {
        var stage = targetDoc.getElementById('caliperf-swipe-stage');
        var navRow = getNavRow();
        var topPx = 118;
        if (navRow) {
            var r = navRow.getBoundingClientRect();
            topPx = Math.max(48, Math.round(r.bottom + 6));
        } else {
            var vm = getActiveViewMarker();
            if (vm) {
                var vr = vm.getBoundingClientRect();
                if (vr.top > 40) topPx = Math.round(vr.top);
            }
        }
        if (!stage) {
            stage = targetDoc.createElement('div');
            stage.id = 'caliperf-swipe-stage';
            stage.setAttribute('aria-hidden', 'true');
            stage.setAttribute('inert', '');
            var incoming = targetDoc.createElement('div');
            incoming.id = 'caliperf-swipe-incoming';
            stage.appendChild(incoming);
            targetDoc.body.appendChild(stage);
        }
        stage.style.top = topPx + 'px';
        stage.style.bottom = '0px';
        stage.style.opacity = '1';
        stage.style.transition = 'none';

        var inc = targetDoc.getElementById('caliperf-swipe-incoming');
        if (inc && inc.getAttribute('data-target-idx') !== String(targetIdx)) {
            inc.setAttribute('data-target-idx', String(targetIdx));
            var snapHtml = targetWin._caliperfTabSnaps && targetWin._caliperfTabSnaps[targetIdx];
            inc.innerHTML = snapHtml ? snapHtml : buildGhostCardHtml(targetIdx);
        }
        return inc;
    }

    function renderDragFrame() {
        state.rafId = null;
        if (!state.isTracking || !state.isHorizontal) return;

        var dx = state.dx;
        var vw = state.vw || 390;
        var dir = dx < 0 ? 1 : -1;
        var targetIdx = state.lastActiveIdx + dir;
        if (targetIdx < 0 || targetIdx >= state.tabs.length) {
            targetIdx = null;
        }
        state.dir = dir;
        state.targetIdx = targetIdx;

        var blocks = state.blocks;
        if (!blocks || !blocks.length) return;

        if (targetIdx === null) {
            removeSwipeStage();
            var elasticDx = dx * 0.22;
            for (var i = 0; i < blocks.length; i++) {
                blocks[i].style.transition = 'none';
                blocks[i].style.willChange = 'transform';
                blocks[i].style.transform = 'translate3d(' + elasticDx.toFixed(1) + 'px, 0, 0)';
                blocks[i].style.opacity = '1';
            }
            syncProgressDots(state.lastActiveIdx, null, 0);
            return;
        }

        var clampedDx = Math.max(-vw, Math.min(vw, dx));
        var progress = Math.min(1, Math.abs(clampedDx) / vw);
        var uiProgress = Math.min(1, Math.abs(clampedDx) / Math.min(220, vw * 0.56));
        var outOpacity = (1 - progress * 0.14).toFixed(3);

        for (var j = 0; j < blocks.length; j++) {
            blocks[j].style.transition = 'none';
            blocks[j].style.willChange = 'transform, opacity';
            blocks[j].style.transform = 'translate3d(' + clampedDx.toFixed(1) + 'px, 0, 0)';
            blocks[j].style.opacity = outOpacity;
        }

        var inc = ensureSwipeStage(targetIdx);
        if (inc) {
            var incomingX = (dir * vw) + clampedDx;
            inc.style.transition = 'none';
            inc.style.transform = 'translate3d(' + incomingX.toFixed(1) + 'px, 0, 0)';
            inc.style.opacity = (0.76 + progress * 0.24).toFixed(3);
        }

        syncProgressDots(state.lastActiveIdx, targetIdx, uiProgress);
        syncDockGlider(state.lastActiveIdx, targetIdx, uiProgress, false);
        state.dragRendered = true;
    }

    function playWaapiEnter(blocks, dirPx, durMs) {
        if (!blocks || !blocks.length) return;
        for (var i = 0; i < blocks.length; i++) {
            var el = blocks[i];
            if (!el || !el.animate) continue;
            try {
                el.animate([
                    { opacity: 0.12, transform: 'translate3d(' + dirPx + 'px, 0, 0)' },
                    { opacity: 1, transform: 'translate3d(0, 0, 0)' }
                ], {
                    duration: durMs || 280,
                    easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
                    fill: 'none'
                });
            } catch (errAnim) {}
        }
    }

    function handleActiveTabSeqChange() {
        var vm = getActiveViewMarker();
        if (!vm) return;
        var tabIdx = parseInt(vm.getAttribute('data-tab-idx') || '0', 10);
        var animDir = vm.getAttribute('data-anim-dir') || 'none';
        var tabSeq = vm.getAttribute('data-tab-seq') || '0';

        if (targetWin._caliperfLastTabSeq === tabSeq) {
            if (!state.isTracking && !targetWin._caliperfPendingEnter) {
                syncDockGlider(tabIdx, null, 0, false);
            }
            if (!targetWin._caliperfTabSnaps[tabIdx] && state.snapScheduledTab !== tabIdx) {
                state.snapScheduledTab = tabIdx;
                if (state.snapTimer) targetWin.clearTimeout(state.snapTimer);
                state.snapTimer = targetWin.setTimeout(function() {
                    state.snapScheduledTab = null;
                    captureTabSnapshot(tabIdx);
                }, 250);
            }
            return;
        }
        var isFirstBoot = (typeof targetWin._caliperfLastTabSeq === 'undefined');
        targetWin._caliperfLastTabSeq = tabSeq;

        if (isFirstBoot) {
            syncProgressDots(tabIdx, null, 0);
            syncDockGlider(tabIdx, null, 0, false);
            state.snapScheduledTab = tabIdx;
            if (state.snapTimer) targetWin.clearTimeout(state.snapTimer);
            state.snapTimer = targetWin.setTimeout(function() {
                state.snapScheduledTab = null;
                captureTabSnapshot(tabIdx);
            }, 250);
            return;
        }

        clearOptimisticDock();
        syncProgressDots(tabIdx, null, 0);
        syncDockGlider(tabIdx, null, 0, true);

        var blocks = getDockContentBlocks();
        clearBlockStyles(blocks);

        var pending = targetWin._caliperfPendingEnter;
        targetWin._caliperfPendingEnter = null;

        var vw = targetWin.innerWidth || 390;
        if (pending && pending.source === 'swipe' && pending.targetIdx === tabIdx && targetDoc.getElementById('caliperf-swipe-stage')) {
            /* Attendre la fin du glissement vers x=0 avant nettoyage complet et fondu invisible sur le vrai onglet */
            var remMs = Math.max(0, (pending.animDoneAt || 0) - Date.now());
            var finishHandoff = function() {
                clearAllSiblingsStyles();
                dissolveSwipeStage();
            };
            if (remMs > 15) {
                targetWin.setTimeout(finishHandoff, remMs);
            } else {
                finishHandoff();
            }
        } else if (animDir === 'right' || animDir === 'left') {
            clearAllSiblingsStyles();
            removeSwipeStage();
            var dirSign = animDir === 'left' ? -1 : 1;
            var slideDist = dirSign * Math.round(vw * 0.85);
            playWaapiEnter(blocks, slideDist, 300);
        } else {
            clearAllSiblingsStyles();
            removeSwipeStage();
        }

        targetWin.setTimeout(triggerResizePulse, 70);
        if (state.snapTimer) targetWin.clearTimeout(state.snapTimer);
        state.snapTimer = targetWin.setTimeout(function() { captureTabSnapshot(tabIdx); }, 500);
    }

    function onTouchStart(e) {
        if (Date.now() < (state.navLockUntil || 0)) {
            state.isTracking = false;
            return;
        }
        if (!e.touches || e.touches.length !== 1) return;
        if (isInsideScrollableOrBlocked(e.target)) {
            state.isTracking = false;
            return;
        }
        var ctx = resolveNavMode(e.target);
        if (!ctx || !ctx.tabs.length) {
            state.isTracking = false;
            return;
        }
        state.mode = ctx.mode;
        state.tabs = ctx.tabs;
        state.lastActiveIdx = ctx.activeIdx;
        state.startX = e.touches[0].clientX;
        state.startY = e.touches[0].clientY;
        state.currentX = state.startX;
        state.currentY = state.startY;
        state.dx = 0;
        state.vw = targetWin.innerWidth || 390;
        state.samples = [{ x: state.startX, t: Date.now() }];
        state.isTracking = true;
        state.isHorizontal = false;
        state.isVerticalScroll = false;
        state.targetIdx = null;
        state.dir = 0;
        state.dragRendered = false;
        state.blocks = (ctx.mode === 'dock') ? getDockContentBlocks() : [];
        if (ctx.mode === 'dock' && !targetWin._caliperfTabSnaps[ctx.activeIdx]) {
            captureTabSnapshot(ctx.activeIdx);
        }
    }

    function onTouchMove(e) {
        if (!state.isTracking || state.isVerticalScroll || !e.touches || e.touches.length !== 1) return;
        state.currentX = e.touches[0].clientX;
        state.currentY = e.touches[0].clientY;
        state.dx = state.currentX - state.startX;
        var dy = state.currentY - state.startY;

        if (!state.isHorizontal) {
            if (Math.abs(state.dx) < 10 && Math.abs(dy) < 10) return;
            if (Math.abs(dy) > Math.abs(state.dx) * 1.1) {
                state.isVerticalScroll = true;
                state.isTracking = false;
                return;
            }
            if (Math.abs(state.dx) >= 10 && Math.abs(state.dx) > Math.abs(dy) * 1.25) {
                state.isHorizontal = true;
                if (state.mode === 'dock') {
                    clearBlockStyles(state.blocks);
                }
            } else {
                return;
            }
        }

        var now = Date.now();
        state.samples.push({ x: state.currentX, t: now });
        while (state.samples.length > 5 && now - state.samples[0].t > 110) {
            state.samples.shift();
        }

        if (state.mode === 'dock') {
            if (!state.rafId) {
                state.rafId = targetWin.requestAnimationFrame(renderDragFrame);
            }
        } else {
            var dir = state.dx < 0 ? 1 : -1;
            var previewIdx = state.lastActiveIdx + dir;
            if (previewIdx >= 0 && previewIdx < state.tabs.length) {
                syncProgressDots(state.lastActiveIdx, previewIdx, Math.min(1, Math.abs(state.dx) / 140));
            }
        }
    }

    function onTouchEnd(e) {
        if (!state.isTracking) return;
        state.isTracking = false;
        if (state.rafId) {
            targetWin.cancelAnimationFrame(state.rafId);
            state.rafId = null;
        }

        var touch = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0] : null;
        var endX = touch ? touch.clientX : state.currentX;
        var endY = touch ? touch.clientY : state.currentY;
        var dx = endX - state.startX;
        var dy = endY - state.startY;
        var vw = state.vw || 390;

        var vx = 0;
        if (state.samples.length >= 2) {
            var first = state.samples[0];
            var last = state.samples[state.samples.length - 1];
            var dt = Math.max(12, last.t - first.t);
            vx = (last.x - first.x) / dt;
        }

        var dir = dx < 0 ? 1 : -1;
        var targetIdx = state.lastActiveIdx + dir;
        var validTarget = (targetIdx >= 0 && targetIdx < state.tabs.length);
        var threshold = Math.min(88, vw * 0.22);
        var shouldCommit = validTarget && (
            Math.abs(dx) >= threshold ||
            (Math.abs(dx) >= 48 && Math.abs(vx) > 0.45 && ((dx < 0 && vx < 0) || (dx > 0 && vx > 0)))
        ) && Math.abs(dx) > Math.abs(dy) * 1.25;

        if (shouldCommit) {
            var targetBtn = state.tabs[targetIdx];
            if (targetBtn) {
                state.navLockUntil = Date.now() + 450;
                if (targetWin.navigator && targetWin.navigator.vibrate) {
                    try { targetWin.navigator.vibrate(10); } catch (vErr) {}
                }
                syncProgressDots(targetIdx, null, 0);

                if (state.mode === 'dock') {
                    setOptimisticDock(targetIdx);
                    syncDockGlider(targetIdx, null, 0, true);
                    var blocks = state.blocks;
                    var inc = ensureSwipeStage(targetIdx);
                    var startOutX = state.dragRendered ? dx : 0;
                    var startIncX = (dir * vw) + startOutX;
                    var startOutOp = state.dragRendered ? Math.max(0.84, 1 - Math.min(1, Math.abs(startOutX) / vw) * 0.14) : 1;
                    var startIncOp = state.dragRendered ? Math.min(1, 0.76 + Math.min(1, Math.abs(startOutX) / vw) * 0.24) : 0.76;
                    var dur = Math.max(220, Math.min(310, Math.round(300 * (1 - Math.min(0.45, Math.abs(startOutX) / vw)))));
                    targetWin._caliperfPendingEnter = { targetIdx: targetIdx, dir: dir, source: 'swipe', startedAt: Date.now(), animDoneAt: Date.now() + dur };
                    var easing = 'cubic-bezier(0.22, 1, 0.36, 1)';
                    clearBlockStyles(blocks);
                    for (var i = 0; i < blocks.length; i++) {
                        if (blocks[i].animate) {
                            try {
                                blocks[i].animate([
                                    { transform: 'translate3d(' + startOutX.toFixed(1) + 'px, 0, 0)', opacity: startOutOp },
                                    { transform: 'translate3d(' + (-dir * vw) + 'px, 0, 0)', opacity: 0.72 }
                                ], { duration: dur, easing: easing, fill: 'forwards' });
                            } catch (eOutAnim) {}
                        }
                    }
                    if (inc) {
                        clearBlockStyles([inc]);
                        if (inc.animate) {
                            try {
                                inc.animate([
                                    { transform: 'translate3d(' + startIncX.toFixed(1) + 'px, 0, 0)', opacity: startIncOp },
                                    { transform: 'translate3d(0px, 0, 0)', opacity: 1 }
                                ], { duration: dur, easing: easing, fill: 'forwards' });
                            } catch (eIncAnim) {
                                inc.style.transform = 'translate3d(0px, 0, 0)';
                                inc.style.opacity = '1';
                            }
                        } else {
                            inc.style.transform = 'translate3d(0px, 0, 0)';
                            inc.style.opacity = '1';
                        }
                    }
                    state.stageTimer = targetWin.setTimeout(function() {
                        var curVm = getActiveViewMarker();
                        var curRenderedIdx = curVm ? parseInt(curVm.getAttribute('data-tab-idx') || '-1', 10) : -1;
                        if (curRenderedIdx === targetIdx) {
                            clearAllSiblingsStyles();
                            dissolveSwipeStage();
                        }
                    }, dur + 30);
                    /* Sécurité absolue : ne jamais laisser la scène figée si Streamlit ignore un clic */
                    targetWin.setTimeout(function() {
                        if (targetWin._caliperfPendingEnter && Date.now() - targetWin._caliperfPendingEnter.startedAt > 3000) {
                            targetWin._caliperfPendingEnter = null;
                            clearOptimisticDock();
                            clearAllSiblingsStyles();
                            removeSwipeStage();
                        }
                    }, 3200);
                }

                var clickIdx = targetIdx;
                var fallbackBtn = targetBtn;
                var clickMode = state.mode;
                var fireDockClick = function() {
                    var btnToClick = fallbackBtn;
                    if (clickMode === 'dock') {
                        var fresh = getDockButtons();
                        if (fresh[clickIdx]) btnToClick = fresh[clickIdx];
                    }
                    if (btnToClick && btnToClick.click) {
                        btnToClick.click();
                    }
                };
                fireDockClick();
                if (clickMode === 'dock') {
                    targetWin.setTimeout(function() {
                        var p = targetWin._caliperfPendingEnter;
                        var curVm = getActiveViewMarker();
                        var curIdx = curVm ? parseInt(curVm.getAttribute('data-tab-idx') || '-1', 10) : -1;
                        var appEl = targetDoc.querySelector('[data-testid="stApp"]');
                        var scriptState = appEl ? appEl.getAttribute('data-test-script-state') : '';
                        if (p && p.source === 'swipe' && p.targetIdx === clickIdx && curIdx !== clickIdx && scriptState !== 'running') {
                            fireDockClick();
                        }
                    }, 650);
                }
                state.isHorizontal = false;
                return;
            }
        }

        /* Geste annulé ou en bout de course : ressort doux vers 0px puis nettoyage complet */
        if (state.mode === 'dock' && state.isHorizontal) {
            var cancelBlocks = state.blocks;
            var cancelInc = targetDoc.getElementById('caliperf-swipe-incoming');
            var snapDur = 230;
            var snapEase = 'cubic-bezier(0.22, 1, 0.36, 1)';
            for (var k = 0; k < cancelBlocks.length; k++) {
                cancelBlocks[k].style.transition = 'transform ' + snapDur + 'ms ' + snapEase + ', opacity ' + snapDur + 'ms ease';
                cancelBlocks[k].style.transform = 'translate3d(0px, 0, 0)';
                cancelBlocks[k].style.opacity = '1';
            }
            if (cancelInc) {
                cancelInc.style.transition = 'transform ' + snapDur + 'ms ' + snapEase + ', opacity ' + snapDur + 'ms ease';
                cancelInc.style.transform = 'translate3d(' + (dir * vw) + 'px, 0, 0)';
                cancelInc.style.opacity = '0.5';
            }
            state.stageTimer = targetWin.setTimeout(function() {
                clearBlockStyles(cancelBlocks);
                removeSwipeStage();
            }, snapDur + 20);
        } else {
            removeSwipeStage();
        }
        state.isHorizontal = false;
        syncProgressDots(state.lastActiveIdx, null, 0);
        if (state.mode === 'dock') {
            syncDockGlider(state.lastActiveIdx, null, 0, true);
        }
    }

    function onTouchCancel() {
        state.isTracking = false;
        state.isHorizontal = false;
        if (state.rafId) {
            targetWin.cancelAnimationFrame(state.rafId);
            state.rafId = null;
        }
        clearBlockStyles(state.blocks);
        removeSwipeStage();
        syncProgressDots(state.lastActiveIdx, null, 0);
        if (state.mode === 'dock') {
            syncDockGlider(state.lastActiveIdx, null, 0, true);
        }
    }

    function onGlobalClickCapture(e) {
        var navRow = getNavRow();
        if (navRow && e.target && e.target.closest) {
            var dockBtn = e.target.closest('button');
            if (dockBtn && navRow.contains(dockBtn) && e.isTrusted) {
                var btns = getDockButtons();
                var nextIdx = btns.indexOf(dockBtn);
                var vm = getActiveViewMarker();
                var curIdx = vm ? parseInt(vm.getAttribute('data-tab-idx') || '0', 10) : 0;
                if (nextIdx !== -1 && nextIdx !== curIdx) {
                    var dir = nextIdx > curIdx ? 1 : -1;
                    setOptimisticDock(nextIdx);
                    syncProgressDots(nextIdx, null, 0);
                    syncDockGlider(nextIdx, null, 0, true);
                    targetWin._caliperfPendingEnter = { targetIdx: nextIdx, dir: dir, source: 'click', startedAt: Date.now() };
                    var blocks = getDockContentBlocks();
                    for (var i = 0; i < blocks.length; i++) {
                        if (blocks[i].animate) {
                            try {
                                blocks[i].animate([
                                    { opacity: 1, transform: 'translate3d(0, 0, 0)' },
                                    { opacity: 0.25, transform: 'translate3d(' + (-dir * 54) + 'px, 0, 0)' }
                                ], { duration: 155, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'forwards' });
                            } catch (eOut) {}
                        }
                    }
                }
                return;
            }
        }
        onTabClickCapture(e);
    }

    function onTabClickCapture(e) {
        var tabBtn = e.target && e.target.closest ? e.target.closest('button[data-baseweb="tab"], [role="tab"]') : null;
        if (!tabBtn) return;
        var stEl = tabBtn.closest('[data-testid="stTabs"], .stTabs');
        if (!stEl) return;
        var tabs = getDirectTabs(stEl);
        var nextIdx = tabs.indexOf(tabBtn);
        if (nextIdx === -1) return;
        targetWin.requestAnimationFrame(function() {
            syncProgressDots(nextIdx, null, 0);
            targetWin.setTimeout(triggerResizePulse, 50);
        });
    }

    function syncInitialDots() {
        var ctx = resolveNavMode(null);
        if (!ctx) return;
        syncProgressDots(ctx.activeIdx, null, 0);
        if (ctx.mode === 'dock') {
            syncDockGlider(ctx.activeIdx, null, 0, false);
        }
    }

    function onResizeSync() {
        if (state.isTracking) return;
        var ctx = resolveNavMode(null);
        if (ctx && ctx.mode === 'dock') {
            syncDockGlider(ctx.activeIdx, null, 0, false);
        }
    }

    targetWin.addEventListener('touchstart', onTouchStart, { capture: true, passive: true });
    targetWin.addEventListener('touchmove', onTouchMove, { capture: true, passive: true });
    targetWin.addEventListener('touchend', onTouchEnd, { capture: true, passive: true });
    targetWin.addEventListener('touchcancel', onTouchCancel, { capture: true, passive: true });
    targetWin.addEventListener('click', onGlobalClickCapture, true);
    targetWin.addEventListener('resize', onResizeSync);

    var observer = null;
    if (typeof targetWin.MutationObserver !== 'undefined') {
        observer = new targetWin.MutationObserver(function() {
            handleActiveTabSeqChange();
            if (!state.isTracking && !targetWin._caliperfPendingEnter) {
                syncInitialDots();
            }
        });
        if (targetDoc.body) {
            observer.observe(targetDoc.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['aria-selected', 'data-tab-idx', 'data-tab-seq']
            });
        }
    }

    targetWin._caliperfSwipeHandlers = true;
    targetWin._caliperfSwipeCleanup = function() {
        targetWin.removeEventListener('touchstart', onTouchStart, { capture: true, passive: true });
        targetWin.removeEventListener('touchmove', onTouchMove, { capture: true, passive: true });
        targetWin.removeEventListener('touchend', onTouchEnd, { capture: true, passive: true });
        targetWin.removeEventListener('touchcancel', onTouchCancel, { capture: true, passive: true });
        targetWin.removeEventListener('click', onGlobalClickCapture, true);
        targetWin.removeEventListener('resize', onResizeSync);
        if (observer) observer.disconnect();
    };

    handleActiveTabSeqChange();
    syncInitialDots();
})();
"""


def inject_theme() -> None:
    """Injecte le Design System CSS complet dans la page Streamlit."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def inject_swipe_engine(stage: str = "app", redirect_tab_idx: int = None) -> None:
    """
    Injecte le moteur de geste tactile fluide V8 (Pager Instagram 1:1) + redirection optionnelle d'onglet.
    Utilise components.html(height=0) car Streamlit >=1.53 n'exécute pas de manière fiable <script> dans st.html.
    """
    import time as _time
    safe_stage = "".join(c for c in (stage or "app") if c.isalnum() or c in "_-") or "app"
    script_payload = f"/* cali-stage:{safe_stage} */\n{SWIPE_ENGINE_JS}"
    html_payload = f'<span data-cali-js="{safe_stage}" style="display:none;"></span><script>{script_payload}</script>'
    components.html(html_payload, height=0)

    if redirect_tab_idx is not None:
        idx_int = max(0, int(redirect_tab_idx))
        nonce = int(_time.time() * 1000)
        redir_html = (
            f'<script>/* cali-redir:{idx_int}:{nonce} */'
            f'(function(){{'
            f'var w=(window.parent&&window.parent!==window)?window.parent:window;'
            f'var d=w.document;'
            f'var go=function(attempt){{'
            f'var anchor=d.getElementById("caliperf-main-tabs-anchor");'
            f'var stEl=null;'
            f'if(anchor){{var b=anchor.closest("[data-testid=\\"stElementContainer\\"],.element-container")||anchor.parentElement;'
            f'var cur=b?b.nextElementSibling:null;while(cur){{if(cur.matches&&cur.matches("[data-testid=\\"stTabs\\"],.stTabs")){{stEl=cur;break;}}'
            f'var q=cur.querySelector?cur.querySelector("[data-testid=\\"stTabs\\"],.stTabs"):null;if(q){{stEl=q;break;}}cur=cur.nextElementSibling;}}}}'
            f'if(!stEl)stEl=d.querySelector("[data-testid=\\"stTabs\\"],.stTabs");'
            f'if(!stEl){{if(attempt<15)w.setTimeout(function(){{go(attempt+1);}},40);return;}}'
            f'var tabs=Array.from(stEl.querySelectorAll("button[data-baseweb=\\"tab\\"],[role=\\"tab\\"]")).filter(function(t){{return t.closest("[data-testid=\\"stTabs\\"],.stTabs")===stEl;}});'
            f'var btn=tabs[{idx_int}];'
            f'if(btn){{if(btn.getAttribute("aria-selected")!=="true"){{btn.click();}}'
            f'try{{btn.scrollIntoView({{behavior:"smooth",inline:"center",block:"nearest"}});}}catch(e){{}}'
            f'w.setTimeout(function(){{try{{w.dispatchEvent(new Event("resize"));}}catch(e){{}}}},100);}}'
            f'}};'
            f'w.setTimeout(function(){{go(0);}},50);'
            f'}})();</script>'
        )
        components.html(redir_html, height=0)
