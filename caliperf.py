import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime

# --- CONFIGURATION ---
URL_GOOGLE_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"

ENTRY_NOM = "entry.1847695661"
ENTRY_EXO = "entry.1595307876"
ENTRY_TST = "entry.549289703"
ENTRY_RPE = "entry.46344190"

st.set_page_config(page_title="Caliperf - App", layout="wide", page_icon="💪")

# --- CSS / STYLE ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #1f2937; border-radius: 5px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION DE L'ÉTAT (SESSION STATE) ---
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = set()
if 'timers' not in st.session_state:
    st.session_state.timers = {} 

st.title("🏋️ Caliperf : Street Workout Cloud")

# === CRÉATION DES ONGLETS DE NAVIGATION ===
tab_accueil, tab_analyse = st.tabs(["🏠 Calcul & Accueil", "🎥 Analyse Coach"])

# =========================================================
# ONGLET 1 : ACCUEIL & CALCULATEUR RAPIDE (Ton ancien code)
# =========================================================
with tab_accueil:
    st.header("🧮 Calculateur de Charge")
    st.write("Calcule rapidement le tonnage de ta séance.")
    
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, 20, 4)
    with col2: reps = st.number_input("Répétitions", 0, 100, 10)
    with col3: poids = st.number_input("Poids (kg)", 0.0, 200.0, 0.0, step=1.0)
    
    total = series * reps * (poids if poids > 0 else 1) # Simplifié
    
    if total > 0:
        st.info(f"📊 Volume Total : **{total}** kg (théorique)")
    else:
        st.caption("Rentre tes données pour voir le résultat.")

# =========================================================
# ONGLET 2 : ANALYSE MULTI-VIDÉOS (Le nouveau code)
# =========================================================
with tab_analyse:
    st.header("1️⃣ Espace Athlète : Dépôt")
    uploaded_files = st.file_uploader(
        "Déposer les vidéos ici", 
        type=['mp4', 'mov', 'avi'], 
        accept_multiple_files=True
    )

    st.divider()

    st.header("2️⃣ Espace Coach : Analyse")
    password = st.text_input("🔒 Mot de passe Coach :", type="password")

    if password == "admin":
        if not uploaded_files:
            st.info("⚠️ Aucune vidéo chargée par l'athlète.")
        else:
            # --- SÉLECTEUR DE VIDÉO ---
            # On crée une liste propre pour le menu déroulant
            video_map = {f.name: f for f in uploaded_files}
            
            # On ajoute un emoji ✅ si la vidéo a déjà été envoyée
            options_display = []
            for name in video_map.keys():
                prefix = "✅ " if name in st.session_state.processed_files else "⏳ "
                options_display.append(prefix + name)

            selected_option = st.selectbox("Choisir la vidéo à corriger :", options_display)
            
            # On récupère le vrai nom du fichier
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            current_file = video_map[real_name]

            # --- AFFICHAGE VIDÉO + OUTILS ---
            c_vid, c_tools = st.columns([1.5, 1])
            
            with c_vid:
                st.video(current_file)
            
            with c_tools:
                st.subheader("⏱️ Chrono & Données")
                
                # Gestion du chrono spécifique à CE fichier
                if real_name not in st.session_state.timers:
                    st.session_state.timers[real_name] = {'start': 0, 'accumulated': 0.0, 'running': False}
                
                timer = st.session_state.timers[real_name]

                # Boutons Chrono
                b1, b2 = st.columns(2)
                with b1:
                    lbl = "⏸️ PAUSE" if timer['running'] else "▶️ START"
                    if st.button(lbl, key=f"btn_s_{real_name}", use_container_width=True):
                        if timer['running']:
                            timer['accumulated'] += time.time() - timer['start']
                            timer['running'] = False
                        else:
                            timer['start'] = time.time()
                            timer['running'] = True
                with b2:
                    if st.button("🗑️ RAZ", key=f"btn_r_{real_name}", use_container_width=True):
                        timer['accumulated'] = 0.0
                        timer['running'] = False
                
                # Calcul temps réel
                disp_time = timer['accumulated']
                if timer['running']:
                    disp_time += time.time() - timer['start']
                
                st.metric("Temps (TST)", f"{disp_time:.2f} s")

                # Formulaire d'envoi
                with st.form(key=f"frm_{real_name}"):
                    nom = st.text_input("Athlète")
                    exo = st.text_input("Exercice", value=real_name.split('.')[0])
                    rpe = st.slider("RPE", 1, 10, 7)
                    
                    if st.form_submit_button("☁️ ENVOYER"):
                        if nom:
                            data = {
                                ENTRY_NOM: nom,
                                ENTRY_EXO: exo,
                                ENTRY_TST: str(round(disp_time, 2)).replace('.', ','),
                                ENTRY_RPE: str(rpe)
                            }
                            try:
                                r = requests.post(URL_GOOGLE_FORM, data=data)
                                if r.status_code == 200:
                                    st.success("Envoyé !")
                                    st.session_state.processed_files.add(real_name)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Erreur Google")
                            except:
                                st.error("Erreur connexion")
                        else:
                            st.warning("Nom requis")

    elif password:
        st.error("Mot de passe incorrect")
