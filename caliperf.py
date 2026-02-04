import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime

# Configuration de la page
st.set_page_config(page_title="Caliperf - Mobile", layout="wide")
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

# --- ONGLET 2 : VIDÉO ---
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

            # --- LE CHRONO ---
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

            # --- VALIDATION ---
            st.subheader("3️⃣ Sauvegarde")
            nom = st.text_input("Nom de l'athlète")
            exo = st.text_input("Exercice")
            final_tst = st.number_input("Temps Final (s)", value=float(t), step=0.1)

            if nom and final_tst > 0:
                now = datetime.now()
                # Création de la donnée
                data = {
                    "Date": [now.strftime("%d/%m/%Y")],
                    "Athlète": [nom],
                    "Exercice": [exo],
                    "TST (s)": [str(final_tst).replace('.', ',')],
                    "RPE": [rpe_value]
                }
                df = pd.DataFrame(data)

                # --- OPTION A : TÉLÉCHARGEMENT (MOBILE / CLOUD) ---
                st.markdown("#### 📱 Option Mobile (Cloud)")
                csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                nom_fichier_mobile = f"Perf_{nom}_{now.strftime('%Hh%M')}.csv"
                
                st.download_button(
                    label="📥 TÉLÉCHARGER LE FICHIER",
                    data=csv,
                    file_name=nom_fichier_mobile,
                    mime='text/csv',
                    type="primary",
                    use_container_width=True
                )

                # --- OPTION B : SAUVEGARDE LOCALE (PC SEULEMENT) ---
                st.write("")
                st.markdown("#### 💻 Option PC (Bureau)")
                
                if st.button("💾 AJOUTER AU FICHIER PRINCIPAL (PC)", use_container_width=True):
                    try:
                        file_name_pc = "suivi_tst.csv"
                        if not os.path.isfile(file_name_pc):
                            df.to_csv(file_name_pc, index=False, sep=';', encoding='utf-8-sig')
                        else:
                            df.to_csv(file_name_pc, mode='a', header=False, index=False, sep=';', encoding='utf-8-sig')
                        st.success(f"✅ Ajouté à {file_name_pc} sur ton Bureau !")
                    except:
                        st.error("❌ Impossible d'écrire sur le disque. (C'est normal si tu es sur la version Mobile/Web). Utilise le bouton Télécharger ci-dessus.")

        else:
            st.warning("⚠️ En attente de vidéo...")
            
    elif password:
        st.error("Mot de passe incorrect")
