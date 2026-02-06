import streamlit as st
import pandas as pd
import time
import requests  # La "brique" qui permet de parler à Google
from datetime import datetime

# --- CONFIGURATION AUTOMATIQUE (C'est rempli !) ---
# J'ai remplacé 'viewform' par 'formResponse' pour que l'envoi fonctionne
URL_GOOGLE_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSfVrYwDZOWr1G800WwguVdiMMYokE1ryHL_yx_5wClsWmSuyg/formResponse"

# Tes codes d'identification extraits de ton lien :
ENTRY_NOM = "entry.1696045241"
ENTRY_EXO = "entry.957125700"
ENTRY_TST = "entry.2108294063"
ENTRY_RPE = "entry.1582638667"
# --------------------------------------------------

st.set_page_config(page_title="Caliperf - Cloud", layout="wide")
st.title("🏋️ Caliperf : Analyse & Performance")

# Création des onglets
tab1, tab2 = st.tabs(["📝 Séance & Volume", "🎥 Zone Vidéo & Analyse"])

# --- ONGLET 1 : SÉANCE ---
with tab1:
    st.header("Calcul Rapide")
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, step=1)
    with col2: reps = st.number_input("Répétitions", 0, step=1)
    with col3: poids = st.number_input("Poids (kg)", 0.0, step=0.5)
    
    if series*reps*poids > 0:
        st.info(f"Volume : {series*reps*poids} kg")

# --- ONGLET 2 : VIDÉO & ANALYSE ---
with tab2:
    st.header("1️⃣ Espace Athlète")

    # ZONE ÉLÈVE
    video_file = st.file_uploader("Déposer la vidéo ici", type=['mp4', 'mov', 'avi'])
    
    st.subheader("Ressenti (RPE)")
    rpe_value = st.slider("Niveau d'effort (1-10) :", 1, 10, 5)
    
    if rpe_value <= 3: st.success(f"RPE {rpe_value} : Facile 🟢")
    elif rpe_value <= 7: st.warning(f"RPE {rpe_value} : Moyen 🟠")
    else: st.error(f"RPE {rpe_value} : Maximal 🔴")

    if video_file:
        st.caption("✅ Vidéo chargée.")

    st.write("---")
    
    # ZONE ADMIN
    password = st.text_input("🔒 Mot de passe Coach :", type="password")

    if password == "admin":
        st.divider()
        st.header("2️⃣ Espace Coach (Analyse)")

        if video_file:
            st.video(video_file)
            st.write("") 

            # --- CHRONO ---
            if 'running' not in st.session_state: st.session_state.running = False
            if 'start_time' not in st.session_state: st.session_state.start_time = None
            if 'accumulated_time' not in st.session_state: st.session_state.accumulated_time = 0.0

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                label = "⏸️ PAUSE" if st.session_state.running else "▶️ START"
                if st.button(label, use_container_width=True):
                    if st.session_state.running:
                        st.session_state.accumulated_time += time.time() - st.session_state.start_time
                        st.session_state.running = False
                    else:
                        st.session_state.start_time = time.time()
                        st.session_state.running = True
            
            with col_btn2:
                if st.button("🗑️ RESET", use_container_width=True):
                    st.session_state.running = False
                    st.session_state.accumulated_time = 0.0

            if st.session_state.running:
                t = st.session_state.accumulated_time + (time.time() - st.session_state.start_time)
                st.warning(f"⏱️ CHRONO : {t:.2f} s")
            else:
                t = st.session_state.accumulated_time
                st.info(f"⏸️ TEMPS RETENU : {t:.2f} s")

            st.write("---")

            # --- ENVOI GOOGLE SHEETS ---
            st.subheader("3️⃣ Validation Cloud")
            with st.form("google_form"):
                nom = st.text_input("Nom de l'athlète")
                exo = st.text_input("Exercice")
                # Récupère automatiquement le temps du chrono
                final_tst = st.number_input("Temps Final (s)", value=float(t), step=0.1)
                
                submitted = st.form_submit_button("☁️ ENVOYER SUR GOOGLE SHEETS", type="primary", use_container_width=True)
                
                if submitted and nom and final_tst > 0:
                    # Préparation des données pour Google Form
                    form_data = {
                        ENTRY_NOM: nom,
                        ENTRY_EXO: exo,
                        ENTRY_TST: str(final_tst).replace('.', ','),
                        ENTRY_RPE: str(rpe_value)
                    }
                    
                    try:
                        # Envoi silencieux à Google
                        response = requests.post(URL_GOOGLE_FORM, data=form_data)
                        if response.status_code == 200:
                            st.success(f"✅ Performance envoyée ! ({nom} - {final_tst}s)")
                            st.balloons()
                            # Reset automatique du chrono après envoi
                            st.session_state.accumulated_time = 0.0
                            st.session_state.running = False
                        else:
                            st.error("⚠️ Erreur technique lors de l'envoi.")
                    except:
                        st.error("❌ Problème de connexion internet.")

        else:
            st.warning("⚠️ En attente de vidéo...")
            
    elif password:
        st.error("Mot de passe incorrect")
