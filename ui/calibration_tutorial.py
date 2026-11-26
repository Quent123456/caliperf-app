"""
ui/calibration_tutorial.py
Fiche tutorielle standardisée pour la calibration 3D dans CaliPerf.
Affiche une boîte de dialogue modale native (@st.dialog) guidant l'enregistrement
des figures de référence (Face, 3/4, Profil) et les 5 règles optiques fondamentales.
"""

import streamlit as st
from ui.theme import render_html


def _build_tutorial_content():
    """Génère le contenu pédagogique et scientifique du protocole de standardisation."""
    render_html("""
        <div style="background: rgba(0, 229, 255, 0.06); border-left: 3px solid #00E5FF; padding: 10px 14px; border-radius: 10px; margin-bottom: 1rem;">
            <p style="margin: 0; font-size: 0.9rem; color: #F8FAFC; line-height: 1.45;">
                🎯 <b>Objectif :</b> Standardiser la prise de vue afin que l'extraction biomécanique 3D
                (<code>pose_world_landmarks</code>) produise des angles articulaires reproductibles et rigoureusement identiques,
                quel que soit le smartphone ou le coach qui filme.
            </p>
        </div>
    """)

    st.markdown("#### 📐 Les 3 angles obligatoires par figure")
    c1, c2, c3 = st.columns(3)

    with c1:
        with st.container(border=True):
            render_html("""
                <div style="text-align:center;">
                    <span style="font-size:1.4rem;">👤</span>
                    <h4 style="margin:4px 0; font-size:1rem; color:#00E5FF;">Face (0°)</h4>
                    <p style="font-size:0.78rem; color:#94A3B8; margin:0;">
                        Symétrie stricte des épaules, abduction des bras et rotation du buste.
                    </p>
                </div>
            """)

    with c2:
        with st.container(border=True):
            render_html("""
                <div style="text-align:center;">
                    <span style="font-size:1.4rem;">👥</span>
                    <h4 style="margin:4px 0; font-size:1rem; color:#38BDF8;">Trois-quarts (45°)</h4>
                    <p style="font-size:0.78rem; color:#94A3B8; margin:0;">
                        Vision volumétrique complète : profondeur coudes, hanches et tronc.
                    </p>
                </div>
            """)

    with c3:
        with st.container(border=True):
            render_html("""
                <div style="text-align:center;">
                    <span style="font-size:1.4rem;">🧍</span>
                    <h4 style="margin:4px 0; font-size:1rem; color:#818CF8;">Profil strict (90°)</h4>
                    <p style="font-size:0.78rem; color:#94A3B8; margin:0;">
                        Inclinaison du tronc, extension hanches et alignement longitudinal.
                    </p>
                </div>
            """)

    render_html("""
        <div style="padding: 8px 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; margin: 8px 0 16px 0; font-size:0.82rem; color:#CBD5E1;">
            ⏱️ <b>Protocole d'enregistrement :</b>
            <b>3 à 5 secondes</b> de tenue stricte pour les figures isométriques •
            <b>2 à 3 répétitions propres</b> pour les mouvements dynamiques.
            <i>Réduisez les temps morts avant et après l'exercice.</i>
        </div>
    """)

    st.markdown("#### 🔬 Les 5 règles optiques & géométriques indispensables")
    r1, r2 = st.columns(2)

    with r1:
        with st.container(border=True):
            st.markdown("##### 1. Zoom / Focale")
            st.markdown(
                "- ✅ **Zoom 1.0x strict** (capteur photo principal standard).\n"
                "- ❌ **Jamais de mode ultra-grand angle (0.5x)** : les déformations optiques déforment les membres et faussent les calculs d'angles 3D."
            )

        with st.container(border=True):
            st.markdown("##### 2. Distance & Cadrage")
            st.markdown(
                "- ✅ **Distance : 2.5 à 4 mètres** (soit environ **3 à 4 grands pas** par rapport au smartphone).\n"
                "- ✅ L'athlète doit occuper **60 % à 80 % du cadre** (orientation paysage recommandée, ou portrait si le corps entier reste visible de la tête aux pieds)."
            )

        with st.container(border=True):
            st.markdown("##### 3. Fréquence d'images (FPS)")
            st.markdown(
                "- ✅ **30 FPS ou 60 FPS constants**.\n"
                "- ❌ **Désactivez les modes \"Auto FPS nuit\"** ou les ralentis extrêmes (120/240 FPS) qui alourdissent le fichier sans gain de précision."
            )

    with r2:
        with st.container(border=True):
            st.markdown("##### 4. Hauteur & Prise de vue (Pratique)")
            st.markdown(
                "- ✅ **Au sol ou sur parallettes basses :** Téléphone posé au sol (calé simplement contre une gourde ou bouteille d'eau).\n"
                "- ✅ **Sur parallettes hautes ou barre :** Surélever le téléphone si possible (sur une chaise ou un banc à ~1 m).\n"
                "- ✅ **Contre-plongée tolérée :** Pas besoin d'un trépied ni d'être à 90° droit comme un piquet ! Une **légère contre-plongée naturelle** (smartphone incliné vers le haut au sol) est **parfaitement acceptée** par l'extraction 3D tant que le corps entier est cadré."
            )

        with st.container(border=True):
            st.markdown("##### 5. Tenue & Éclairage")
            st.markdown(
                "- ✅ **Vêtements ajustés** et contrastant clairement avec le sol ou le mur d'arrière-plan.\n"
                "- ✅ **Éclairage frontal ou latéral uniforme**.\n"
                "- ❌ **Éviter les contre-jours intenses** (fenêtres lumineuses ou spots directs derrière l'athlète)."
            )

    st.info(
        "💡 **Rappel Coach :** La précision du classifieur 1-NN (reconnaissance automatique et calcul de conformité) "
        "dépend directement de la qualité de vos vidéos étalons. Une calibration rigoureuse garantit des analyses fiables "
        "pour vous et vos athlètes."
    )

    if st.button("✅ J'ai compris", type="primary", use_container_width=True, key="btn_close_tuto_modal"):
        st.rerun()


if hasattr(st, "dialog"):
    @st.dialog("Protocole de standardisation — Calibration 3D", width="large")
    def open_calibration_tutorial():
        """Ouvre la fenêtre modale native du protocole de standardisation 3D."""
        _build_tutorial_content()
else:
    def open_calibration_tutorial():
        """Fallback si st.dialog n'est pas présent."""
        with st.container(border=True):
            st.subheader("Protocole de standardisation — Calibration 3D")
            _build_tutorial_content()


def render_tutorial_button(key: str = "btn_tuto_calibration_3d"):
    """Rend un bouton compact discret permettant d'ouvrir la modale du tutoriel."""
    if st.button("📖 Tuto calibration 3D", key=key, use_container_width=True, type="secondary"):
        open_calibration_tutorial()
