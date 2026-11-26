"""
ui/theme.py - Design System 'Kinetic Obsidian & Electric Telemetry' & Moteur de Swipe Fluide V4.
Fournit :
- L'injection du thème CSS complet (typography, glassmorphism carbone, badges, responsive mobile-first).
- La fonction render_html() immunisée contre le bug CommonMark (<pre><code> sur indentations >= 4).
- Le moteur de geste tactile V4 avec prévisualisation progressive en direct (Live Peek Side-by-Side) :
  la page suivante glisse et apparaît progressivement sous le doigt à 60/120fps sans flash ni saccade.
"""

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
    overflow-x: hidden !important;
}

[data-testid="stMain"] {
    touch-action: pan-y pinch-zoom;
    overflow-x: hidden !important;
}

/* Masquer proprement la hauteur des scripts invisibles (sans display:none qui suspend les iframes) */
[data-testid="stElementContainer"]:has(iframe[height="0"]),
.element-container:has(iframe[height="0"]) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
    pointer-events: none !important;
}

/* Maintien horizontal strict de la barre d'en-tête sur smartphone et desktop */
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) {
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 8px !important;
    margin-bottom: 0.25rem !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"] {
    min-width: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) {
    flex: 0 0 46px !important;
    width: 46px !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 auto !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(3) {
    flex: 0 1 auto !important;
    max-width: 46% !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) [data-testid="stElementContainer"]:has(#caliperf-header-exit-marker) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
[data-testid="stHorizontalBlock"]:has(#caliperf-header-exit-marker) > [data-testid="stColumn"]:nth-child(1) button {
    min-height: 38px !important;
    height: 38px !important;
    padding: 0 !important;
    border-radius: 11px !important;
    background: rgba(13, 18, 30, 0.85) !important;
}

/* Padding haut adapté notch smartphone & barre Streamlit */
.block-container {
    padding-top: calc(3.85rem + env(safe-area-inset-top, 0px)) !important;
    padding-bottom: calc(2.5rem + env(safe-area-inset-bottom, 0px)) !important;
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
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
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
</style>
"""


# ATTENTION : N'utilisez aucun commentaire // sur une seule ligne dans ce script.
# Tous les commentaires doivent utiliser /* ... */ pour rester valides en toute circonstance.
SWIPE_ENGINE_JS = r"""
(function() {
    var targetWin = window;
    var targetDoc = document;
    try {
        if (window.parent && window.parent.document) {
            targetWin = window.parent;
            targetDoc = window.parent.document;
        }
    } catch (e) {}

    /* Nettoyage propre si une version précédente du gestionnaire était attachée */
    if (targetWin._caliperfSwipeCleanup) {
        try { targetWin._caliperfSwipeCleanup(); } catch (errClean) {}
    }

    var state = {
        tabsRoot: null,
        tabs: [],
        panels: [],
        lastActiveIdx: 0,
        startX: 0,
        startY: 0,
        currentX: 0,
        dx: 0,
        startTime: 0,
        isTracking: false,
        isHorizontal: false,
        isAnimating: false,
        activePanel: null,
        neighborPanel: null,
        targetIdx: null,
        dir: 0,
        containerW: 360,
        peekTopPx: 0,
        needScrollResetOnCommit: false,
        resetScrollTop: 0,
        rafId: null,
        resizeDispatchedOnDrag: false
    };

    var noSwipeSelector = [
        'input', 'textarea', 'select', 'button', 'a', 'label',
        'video', 'audio', '.stVideo', '.stAudio',
        '[role="slider"]', '.stSlider', '[data-baseweb="slider"]', '.stNumberInput',
        'pre', 'code',
        '[data-testid="stDataFrame"]', '.stDataFrame',
        '[data-testid="stTable"]', '.stTable',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        '[role="grid"]', '[role="treegrid"]', '[role="row"]', '[role="gridcell"]',
        '.glideDataEditor', 'canvas',
        '[data-testid="stPlotlyChart"]', '.js-plotly-plot', '.plotly', 'svg.main-svg', '.draglayer',
        '[data-baseweb="tab-list"]', '[data-baseweb="tab"]', '[role="tab"]',
        '.stSelectbox', '[role="combobox"]', '[role="listbox"]',
        '[data-no-swipe]', '.no-swipe'
    ].join(', ');

    function getTabsRootFromContainer(stEl) {
        if (!stEl) return null;
        var firstPanel = stEl.querySelector('[data-baseweb="tab-panel"]');
        return firstPanel ? firstPanel.parentElement : null;
    }

    function resolveMainTabsRoot(touchTarget) {
        /* 1. Priorité au marqueur principal s'il existe dans la page */
        var anchor = targetDoc.getElementById('caliperf-main-tabs-anchor');
        if (anchor) {
            var block = anchor.closest('[data-testid="stElementContainer"], .element-container') || anchor.parentElement;
            var cursor = block ? block.nextElementSibling : null;
            var steps = 0;
            while (cursor && steps < 10) {
                if (cursor.matches && cursor.matches('[data-testid="stTabs"], .stTabs')) {
                    var r1 = getTabsRootFromContainer(cursor);
                    if (r1) return r1;
                } else if (cursor.querySelector) {
                    var nestedSt = cursor.querySelector('[data-testid="stTabs"], .stTabs');
                    var r2 = getTabsRootFromContainer(nestedSt);
                    if (r2) return r2;
                }
                cursor = cursor.nextElementSibling;
                steps++;
            }
        }
        /* 2. Sinon (ex: écran de connexion), utiliser l'éventuel onglet racine */
        if (touchTarget && touchTarget.closest) {
            var localSt = touchTarget.closest('[data-testid="stTabs"], .stTabs');
            var rLocal = getTabsRootFromContainer(localSt);
            if (rLocal) return rLocal;
        }
        var firstSt = targetDoc.querySelector('[data-testid="stTabs"], .stTabs');
        return getTabsRootFromContainer(firstSt);
    }

    function getDirectTabs(tabsRoot) {
        if (!tabsRoot) return [];
        var list = tabsRoot.querySelector('[data-baseweb="tab-list"]');
        if (!list) return [];
        return Array.from(list.querySelectorAll(':scope > button[data-baseweb="tab"], :scope > [role="tab"]'));
    }

    function getDirectPanels(tabsRoot) {
        if (!tabsRoot) return [];
        return Array.from(tabsRoot.querySelectorAll(':scope > [data-baseweb="tab-panel"]'));
    }

    function getActiveIndex(tabs) {
        for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].getAttribute('aria-selected') === 'true') return i;
        }
        return 0;
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

    function isInsideScrollableOrBlocked(el) {
        if (!el) return false;
        if (el.closest && el.closest(noSwipeSelector)) return true;
        var curr = el;
        while (curr && curr !== targetDoc.body && curr !== targetDoc.documentElement) {
            if (curr.getAttribute && curr.getAttribute('data-baseweb') === 'tab-panel') {
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

    function clearInlinePanelStyles(panel) {
        if (!panel) return;
        panel.classList.remove('cali-swipe-peek');
        panel.style.position = '';
        panel.style.top = '';
        panel.style.left = '';
        panel.style.width = '';
        panel.style.zIndex = '';
        panel.style.pointerEvents = '';
        panel.style.willChange = '';
        panel.style.transition = '';
        panel.style.transform = '';
        panel.style.opacity = '';
    }

    function prepareNeighborPanel(targetIdx, activePanel, tabsRoot) {
        var neighbor = state.panels[targetIdx];
        if (!neighbor) return null;

        var topPx = activePanel.offsetTop;
        var needReset = false;
        var resetTop = 0;
        var mainScroller = targetDoc.querySelector('[data-testid="stMain"]');

        if (mainScroller && tabsRoot) {
            var tabsRect = tabsRoot.getBoundingClientRect();
            var mainRect = mainScroller.getBoundingClientRect();
            var headerAllowance = 56;
            var visibleTopInTabs = (mainRect.top + headerAllowance) - tabsRect.top;
            if (visibleTopInTabs > topPx + 24) {
                topPx = Math.min(
                    visibleTopInTabs,
                    Math.max(topPx, activePanel.offsetTop + activePanel.offsetHeight - 240)
                );
                needReset = true;
                var panelTopInScroll = mainScroller.scrollTop + (activePanel.getBoundingClientRect().top - mainRect.top);
                resetTop = Math.max(0, panelTopInScroll - headerAllowance);
            }
        }

        state.needScrollResetOnCommit = needReset;
        state.resetScrollTop = resetTop;
        state.peekTopPx = topPx;

        neighbor.classList.add('cali-swipe-peek');
        neighbor.style.position = 'absolute';
        neighbor.style.top = topPx + 'px';
        neighbor.style.left = '0';
        neighbor.style.width = '100%';
        neighbor.style.zIndex = '4';
        neighbor.style.pointerEvents = 'none';
        neighbor.style.willChange = 'transform, opacity';
        neighbor.style.transition = 'none';

        return neighbor;
    }

    function renderDragFrame() {
        state.rafId = null;
        if (!state.isTracking || !state.isHorizontal || !state.activePanel) return;

        var dx = state.dx;
        var w = state.containerW || 360;
        var desiredDir = dx < 0 ? 1 : -1;
        var desiredTarget = state.lastActiveIdx + desiredDir;
        if (desiredTarget < 0 || desiredTarget >= state.panels.length) {
            desiredTarget = null;
        }

        /* Si l'utilisateur inverse son geste en cours de glissement, basculer proprement le panneau voisin */
        if (desiredTarget !== state.targetIdx) {
            if (state.neighborPanel) {
                clearInlinePanelStyles(state.neighborPanel);
                state.neighborPanel = null;
            }
            state.targetIdx = desiredTarget;
            state.dir = desiredDir;
            state.resizeDispatchedOnDrag = false;
            if (state.targetIdx !== null) {
                state.neighborPanel = prepareNeighborPanel(state.targetIdx, state.activePanel, state.tabsRoot);
                if (!state.resizeDispatchedOnDrag) {
                    state.resizeDispatchedOnDrag = true;
                    triggerResizePulse();
                }
            }
        }

        if (state.targetIdx === null || !state.neighborPanel) {
            /* Effet élastique naturel aux extrémités */
            var elasticDx = dx * 0.22;
            state.activePanel.style.transition = 'none';
            state.activePanel.style.willChange = 'transform';
            state.activePanel.style.transform = 'translate3d(' + elasticDx.toFixed(1) + 'px, 0, 0)';
            state.activePanel.style.opacity = '1';
            syncProgressDots(state.lastActiveIdx, null, 0);
            return;
        }

        var clampedDx = Math.max(-w, Math.min(w, dx));
        var progress = Math.min(1, Math.abs(clampedDx) / w);
        var scaleOut = 1 - progress * 0.03;
        var opacityOut = 1 - progress * 0.45;
        var scaleIn = 0.965 + progress * 0.035;
        var opacityIn = 0.35 + progress * 0.65;
        var incomingX = (state.dir * w) + clampedDx;

        state.activePanel.style.transition = 'none';
        state.activePanel.style.willChange = 'transform, opacity';
        state.activePanel.style.transform = 'translate3d(' + clampedDx.toFixed(1) + 'px, 0, 0) scale(' + scaleOut.toFixed(4) + ')';
        state.activePanel.style.opacity = opacityOut.toFixed(3);

        state.neighborPanel.style.transition = 'none';
        state.neighborPanel.style.transform = 'translate3d(' + incomingX.toFixed(1) + 'px, 0, 0) scale(' + scaleIn.toFixed(4) + ')';
        state.neighborPanel.style.opacity = opacityIn.toFixed(3);

        syncProgressDots(state.lastActiveIdx, state.targetIdx, progress);
    }

    function onTouchStart(e) {
        if (state.isAnimating || !e.touches || e.touches.length !== 1) return;
        if (isInsideScrollableOrBlocked(e.target)) return;

        var root = resolveMainTabsRoot(e.target);
        if (!root) return;

        var tabs = getDirectTabs(root);
        var panels = getDirectPanels(root);
        if (!tabs.length || !panels.length) return;

        var activeIdx = getActiveIndex(tabs);
        var activeP = panels[activeIdx];
        if (!activeP) return;

        state.tabsRoot = root;
        state.tabs = tabs;
        state.panels = panels;
        state.lastActiveIdx = activeIdx;
        state.activePanel = activeP;
        state.neighborPanel = null;
        state.targetIdx = null;
        state.dir = 0;
        state.containerW = root.clientWidth || targetWin.innerWidth || 360;
        state.startX = e.touches[0].clientX;
        state.startY = e.touches[0].clientY;
        state.currentX = state.startX;
        state.dx = 0;
        state.startTime = Date.now();
        state.isTracking = true;
        state.isHorizontal = false;
        state.needScrollResetOnCommit = false;
    }

    function onTouchMove(e) {
        if (!state.isTracking || !e.touches || e.touches.length !== 1) return;
        if (isInsideScrollableOrBlocked(e.target)) {
            onTouchCancel();
            return;
        }

        state.currentX = e.touches[0].clientX;
        var currentY = e.touches[0].clientY;
        state.dx = state.currentX - state.startX;
        var dy = currentY - state.startY;

        if (!state.isHorizontal) {
            if (Math.abs(state.dx) > 10 && Math.abs(state.dx) > Math.abs(dy) * 1.15) {
                state.isHorizontal = true;
            } else if (Math.abs(dy) > 12) {
                state.isTracking = false;
                return;
            }
        }

        if (state.isHorizontal && !state.rafId) {
            state.rafId = targetWin.requestAnimationFrame(renderDragFrame);
        }
    }

    function finishTransition(committed, targetIdx, dir) {
        var root = state.tabsRoot;
        var activeP = state.activePanel;
        var neighborP = state.neighborPanel;
        var w = state.containerW || 360;

        if (state.rafId) {
            targetWin.cancelAnimationFrame(state.rafId);
            state.rafId = null;
        }

        if (!activeP) {
            state.isAnimating = false;
            return;
        }

        state.isAnimating = true;

        var easeCurve = 'transform 260ms cubic-bezier(0.22, 1, 0.36, 1), opacity 220ms ease';

        if (committed && neighborP && targetIdx !== null) {
            if (targetWin.navigator && targetWin.navigator.vibrate) {
                try { targetWin.navigator.vibrate(12); } catch (vErr) {}
            }

            activeP.style.transition = easeCurve;
            activeP.style.transform = 'translate3d(' + (-dir * w * 0.42).toFixed(1) + 'px, 0, 0) scale(0.96)';
            activeP.style.opacity = '0';

            neighborP.style.transition = easeCurve;
            neighborP.style.transform = 'translate3d(0, 0, 0) scale(1)';
            neighborP.style.opacity = '1';

            syncProgressDots(targetIdx, null, 0);

            targetWin.setTimeout(function() {
                if (root) root.setAttribute('data-cali-silent', '1');
                clearInlinePanelStyles(activeP);
                clearInlinePanelStyles(neighborP);

                if (state.needScrollResetOnCommit) {
                    var scroller = targetDoc.querySelector('[data-testid="stMain"]');
                    if (scroller) scroller.scrollTop = state.resetScrollTop;
                }

                var targetBtn = state.tabs[targetIdx];
                if (targetBtn) {
                    targetBtn.click();
                    try {
                        targetBtn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
                    } catch (sErr) {}
                }

                targetWin.requestAnimationFrame(function() {
                    if (root) root.removeAttribute('data-cali-silent');
                    triggerResizePulse();
                    state.isAnimating = false;
                });
            }, 265);
        } else {
            activeP.style.transition = easeCurve;
            activeP.style.transform = 'translate3d(0, 0, 0) scale(1)';
            activeP.style.opacity = '1';

            if (neighborP) {
                neighborP.style.transition = easeCurve;
                neighborP.style.transform = 'translate3d(' + (dir * w).toFixed(1) + 'px, 0, 0) scale(0.965)';
                neighborP.style.opacity = '0.3';
            }
            syncProgressDots(state.lastActiveIdx, null, 0);

            targetWin.setTimeout(function() {
                clearInlinePanelStyles(activeP);
                clearInlinePanelStyles(neighborP);
                state.isAnimating = false;
            }, 250);
        }
    }

    function onTouchEnd() {
        if (!state.isTracking) return;
        state.isTracking = false;

        if (!state.isHorizontal) {
            return;
        }
        state.isHorizontal = false;

        var w = state.containerW || 360;
        var diffX = state.dx;
        var elapsed = Math.max(1, Date.now() - state.startTime);
        var velocity = Math.abs(diffX) / elapsed;
        var threshold = Math.min(w * 0.20, 88);

        var shouldSwitch = (
            state.targetIdx !== null &&
            (Math.abs(diffX) > threshold || (velocity > 0.28 && Math.abs(diffX) > 24))
        );

        finishTransition(shouldSwitch, state.targetIdx, state.dir);
    }

    function onTouchCancel() {
        if (!state.isTracking) return;
        state.isTracking = false;
        if (state.isHorizontal) {
            state.isHorizontal = false;
            finishTransition(false, null, state.dir);
        }
    }

    /* Animation directionnelle lors d'un clic direct sur les boutons d'onglets */
    function onTabClickCapture(e) {
        var tabBtn = e.target && e.target.closest ? e.target.closest('button[data-baseweb="tab"], [role="tab"]') : null;
        if (!tabBtn) return;

        var stEl = tabBtn.closest('[data-testid="stTabs"], .stTabs');
        var root = getTabsRootFromContainer(stEl);
        if (!root || root.getAttribute('data-cali-silent') === '1') return;

        var tabs = getDirectTabs(root);
        var prevIdx = getActiveIndex(tabs);
        var nextIdx = tabs.indexOf(tabBtn);
        if (nextIdx === -1 || nextIdx === prevIdx) return;

        var panels = getDirectPanels(root);
        var targetPanel = panels[nextIdx];
        var animClass = nextIdx > prevIdx ? 'cali-enter-right' : 'cali-enter-left';

        targetWin.requestAnimationFrame(function() {
            if (targetPanel) {
                targetPanel.classList.remove('cali-enter-right', 'cali-enter-left');
                void targetPanel.offsetWidth;
                targetPanel.classList.add(animClass);
            }
            if (root === resolveMainTabsRoot(null)) {
                syncProgressDots(nextIdx, null, 0);
            }
            targetWin.setTimeout(triggerResizePulse, 50);
        });
    }

    /* Synchronisation initiale des pastilles de progression avec l'onglet actif */
    function syncInitialDots() {
        var root = resolveMainTabsRoot(null);
        if (!root) return;
        var tabs = getDirectTabs(root);
        var activeIdx = getActiveIndex(tabs);
        syncProgressDots(activeIdx, null, 0);
    }

    targetDoc.addEventListener('touchstart', onTouchStart, { passive: true });
    targetDoc.addEventListener('touchmove', onTouchMove, { passive: true });
    targetDoc.addEventListener('touchend', onTouchEnd, { passive: true });
    targetDoc.addEventListener('touchcancel', onTouchCancel, { passive: true });
    targetDoc.addEventListener('click', onTabClickCapture, true);

    var observer = null;
    if (typeof targetWin.MutationObserver !== 'undefined') {
        observer = new targetWin.MutationObserver(function() {
            if (!state.isTracking && !state.isAnimating) {
                syncInitialDots();
            }
        });
        if (targetDoc.body) {
            observer.observe(targetDoc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-selected'] });
        }
    }

    targetWin._caliperfSwipeHandlers = true;
    targetWin._caliperfSwipeCleanup = function() {
        targetDoc.removeEventListener('touchstart', onTouchStart, { passive: true });
        targetDoc.removeEventListener('touchmove', onTouchMove, { passive: true });
        targetDoc.removeEventListener('touchend', onTouchEnd, { passive: true });
        targetDoc.removeEventListener('touchcancel', onTouchCancel, { passive: true });
        targetDoc.removeEventListener('click', onTabClickCapture, true);
        if (observer) observer.disconnect();
    };

    syncInitialDots();
})();
"""


def inject_theme() -> None:
    """Injecte le Design System CSS complet dans la page Streamlit."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def inject_swipe_engine() -> None:
    """Injecte le moteur de geste tactile fluide V4 (Live Peek) via iframe same-origin sans flash."""
    components.html(f"<script>{SWIPE_ENGINE_JS}</script>", height=0)
