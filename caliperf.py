import streamlit as st
import pandas as pd
import time
from datetime import datetime

# Configuration de la page
st.set_page_config(page_title="Caliperf - Mobile", layout="wide")
st.title("🏋️ Caliperf : Analyse & Performance")

# Création des onglets
tab1, tab2 = st.tabs(["📝 Séance & Volume", "⏱️ Config TST (Vidéo)"])

# --- ONGLET 1 : SÉANCE ---
with tab1:
    st.header("Calcul Rapide")
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, step=1)
    with col2: reps = st.number_input("Répétitions", 0, step=1)
    with col3: poids = st.number_input("Poids (kg)", 0.0, step=0.5)
    
    if series*reps*poids > 0:
        st.info(f"Volume : {series*reps*poids} kg")

# --- ONGLET 2 : CONFIG TST ---
with tab2:
    st.header("Analyse Vidéo & Export Excel")

    # 1. LA VIDÉO
    video_file = st.file_uploader("Importer une vidéo", type=['mp4', 'mov', 'avi'])
    
    if video_file:
        st.video(video_file)
        st.divider()

        # 2. LE CHRONO (AVEC PAUSE)
        st.subheader("Chronomètre de précision")
        
        if 'running' not in st.session_state: st.session_state.running = False
        if 'start_time' not in st.session_state: st.session_state.start_time = None
        if 'accumulated_time' not in st.session_state: st.session_state.accumulated_time = 0.0

        col_btn1, col_btn2 = st.columns(2)
        
        # Bouton START / PAUSE
        with col_btn1:
            label = "⏸️ PAUSE" if st.session_state.running else "▶️ START / REPRENDRE"
            if st.button(label, use_container_width=True):
                if st.session_state.running:
                    # On met en pause : on sauvegarde le temps écoulé
                    st.session_state.accumulated_time += time.time() - st.session_state.start_time
                    st.session_state.running = False
                else:
                    # On lance ou relance
                    st.session_state.start_time = time.time()
                    st.session_state.running = True
        
        # Bouton RESET
        with col_btn2:
            if st.button("🗑️ RESET", use_container_width=True):
                st.session_state.running = False
                st.session_state.accumulated_time = 0.0

        # Affichage du temps en gros
        if st.session_state.running:
            t = st.session_state.accumulated_time + (time.time() - st.session_state.start_time)
            st.warning(f"⏱️ EN COURS : {t:.2f} s")
        else:
            t = st.session_state.accumulated_time
            st.info(f"⏸️ TEMPS ARRÊTÉ : {t:.2f} s")

        st.divider()

        # 3. L'ENVOI VERS EXCEL (Via Téléchargement)
        st.subheader("Valider la performance")
        nom = st.text_input("Nom de l'athlète")
        exo = st.text_input("Exercice")
        
        # On récupère le temps du chrono automatiquement
        final_tst = st.number_input("Temps Final (s)", value=float(t), step=0.1)

        if nom and final_tst > 0:
            # Création de la ligne de données (Format Validé)
            now = datetime.now()
            data = {
                "Date": [now.strftime("%d/%m/%Y")],
                "Athlète": [nom],
                "Exercice": [exo],
                # Remplacement du point par la virgule pour ton Excel
                "TST (s)": [str(final_tst).replace('.', ',')]
            }
            df = pd.DataFrame(data)
            
            # Conversion technique pour Excel (encodage et point-virgule)
            csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            
            # Nom du fichier personnalisé
            nom_fichier = f"Perf_{nom}_{now.strftime('%Hh%M')}.csv"

            # LE BOUTON POUR RÉCUPÉRER LE FICHIER SUR TON TÉLÉPHONE
            st.download_button(
                label="📥 TÉLÉCHARGER LE FICHIER EXCEL (CSV)",
                data=csv,
                file_name=nom_fichier,
                mime='text/csv',
                type="primary"
            )
