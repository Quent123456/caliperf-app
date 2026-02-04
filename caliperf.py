import streamlit as st
import pandas as pd
import time
from datetime import datetime

# Configuration de la page
st.set_page_config(page_title="Caliperf - Mobile", layout="wide")
st.title("🏋️ Caliperf : Analyse & Performance")

# Création des onglets
tab1, tab2 = st.tabs(["📝 Séance & Volume", "🎥 Zone Vidéo & Analyse"])

# --- ONGLET 1 : SÉANCE (Inchangé) ---
with tab1:
    st.header("Calcul Rapide")
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, step=1)
    with col2: reps = st.number_input("Répétitions", 0, step=1)
    with col3: poids = st.number_input("Poids (kg)", 0.0, step=0.5)
    
    if series*reps*poids > 0:
        st.info(f"Volume : {series*reps*poids} kg")

# --- ONGLET 2 : VIDÉO (Mixte Élève / Coach) ---
with tab2:
    st.header("Espace Athlète")

    # 1. ZONE ÉLÈVE : Vidéo + RPE
    video_file = st.file_uploader("1️⃣ Déposer la vidéo ici", type=['mp4', 'mov', 'avi'])
    
    # Jauge RPE (Visible tout le temps)
    st.write("---")
    st.subheader("2️⃣ Ressenti de l'effort (RPE)")
    st.caption("Échelle de 1 (Très facile) à 10 (Effort Maximal)")
    
    # Slider RPE (1 à 10)
    rpe_value = st.slider(
        "Sélectionne ton niveau d'effort :", 
        min_value=1, 
        max_value=10, 
        value=5,  # Valeur par défaut
        step=1
    )
    
    # Feedback visuel du RPE
    if rpe_value <= 3:
        st.success(f"RPE {rpe_value} : Effort Faible 🟢")
    elif rpe_value <= 7:
        st.warning(f"RPE {rpe_value} : Effort Modéré/Difficile 🟠")
    else:
        st.error(f"RPE {rpe_value} : Effort Intense/Maximal 🔴")

    if video_file:
        st.video(video_file)

    st.write("---")
    st.header("🔒 Espace Coach (Admin)")

    # 2. ZONE ADMIN : Mot de passe
    password = st.text_input("Entrer le mot de passe pour analyser :", type="password")

    # Si le mot de passe est bon (ici "admin")
    if password == "admin":
        st.success("Accès autorisé ✅")
        
        st.divider()
        st.subheader("3️⃣ Chronomètre TST")
        
        # --- LOGIQUE DU CHRONO (Inchangée) ---
        if 'running' not in st.session_state: st.session_state.running = False
        if 'start_time' not in st.session_state: st.session_state.start_time = None
        if 'accumulated_time' not in st.session_state: st.session_state.accumulated_time = 0.0

        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            label = "⏸️ PAUSE" if st.session_state.running else "▶️ START / REPRENDRE"
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

        # Affichage temps
        if st.session_state.running:
            t = st.session_state.accumulated_time + (time.time() - st.session_state.start_time)
            st.warning(f"⏱️ EN COURS : {t:.2f} s")
        else:
            t = st.session_state.accumulated_time
            st.info(f"⏸️ ARRÊTÉ : {t:.2f} s")

        st.divider()

        # 3. SAUVEGARDE (Avec RPE inclus)
        st.subheader("4️⃣ Valider la performance")
        nom = st.text_input("Nom de l'athlète")
        exo = st.text_input("Exercice")
        
        final_tst = st.number_input("Temps Final (s)", value=float(t), step=0.1)

        if nom and final_tst > 0:
            now = datetime.now()
            # Ajout du RPE dans les données
            data = {
                "Date": [now.strftime("%d/%m/%Y")],
                "Athlète": [nom],
                "Exercice": [exo],
                "TST (s)": [str(final_tst).replace('.', ',')],
                "RPE": [rpe_value]  # Nouvelle colonne
            }
            df = pd.DataFrame(data)
            
            # Format Excel (Point-virgule + UTF-8)
            csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            
            nom_fichier = f"Perf_{nom}_{now.strftime('%Hh%M')}.csv"

            st.download_button(
                label="📥 TÉLÉCHARGER LE FICHIER EXCEL",
                data=csv,
                file_name=nom_fichier,
                mime='text/csv',
                type="primary"
            )
            
    elif password:
        st.error("Mot de passe incorrect ❌")
