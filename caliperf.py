import streamlit as st
import time
import requests
from datetime import datetime

# --- CONFIGURATION (Tes clés Google Form) ---
URL_GOOGLE_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"

ENTRY_NOM = "entry.1847695661"
ENTRY_EXO = "entry.1595307876"
ENTRY_TST = "entry.549289703"
ENTRY_RPE = "entry.46344190"

st.set_page_config(page_title="Caliperf - Multi", layout="wide", page_icon="🏋️")

# --- INITIALISATION DE L'ÉTAT (SESSION STATE) ---
# On stocke les temps et les statuts "traité" pour chaque fichier
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = set()
if 'timers' not in st.session_state:
    st.session_state.timers = {} # Format: {'nom_video': {'start': t, 'accumulated': 0, 'running': False}}

st.title("🏋️ Caliperf : Analyse Multi-Vidéos")

# --- ZONE 1 : UPLOAD (ATHLÈTE) ---
st.header("1️⃣ Espace Athlète : Dépôt de Séance")
uploaded_files = st.file_uploader(
    "Charge toutes tes vidéos ici (Tu peux en sélectionner plusieurs)", 
    type=['mp4', 'mov', 'avi'], 
    accept_multiple_files=True # <--- C'est ici que la magie opère
)

if uploaded_files:
    count = len(uploaded_files)
    st.success(f"📂 {count} fichiers reçus. En attente d'analyse coach.")
    st.divider()

    # --- ZONE 2 : ANALYSE (COACH) ---
    st.header("2️⃣ Espace Coach : Analyse")
    password = st.text_input("🔒 Mot de passe Coach :", type="password")

    if password == "admin":
        
        # Création des onglets ou d'un sélecteur pour naviguer entre les vidéos
        # On crée une liste de noms avec un indicateur visuel si c'est déjà traité
        video_options = {f.name: f for f in uploaded_files}
        option_labels = [f"✅ {name}" if name in st.session_state.processed_files else f"⏳ {name}" for name in video_options.keys()]
        
        # Sélecteur pour choisir quelle vidéo travailler
        selected_label = st.selectbox("Choisir la vidéo à analyser :", option_labels)
        
        # On retrouve le vrai nom du fichier à partir du label
        selected_filename = selected_label.replace("✅ ", "").replace("⏳ ", "")
        current_file = video_options[selected_filename]

        # --- INTERFACE D'ANALYSE POUR LA VIDÉO SÉLECTIONNÉE ---
        st.subheader(f"Analyse de : {selected_filename}")
        
        col_video, col_controls = st.columns([1.5, 1])

        with col_video:
            st.video(current_file)

        with col_controls:
            # --- LOGIQUE DU CHRONO PAR VIDÉO ---
            # Initialiser le chrono pour CE fichier spécifique s'il n'existe pas
            if selected_filename not in st.session_state.timers:
                st.session_state.timers[selected_filename] = {'start': 0, 'accumulated': 0.0, 'running': False}
            
            timer_data = st.session_state.timers[selected_filename]

            # Boutons Chrono
            c1, c2 = st.columns(2)
            with c1:
                btn_label = "⏸️ PAUSE" if timer_data['running'] else "▶️ START"
                if st.button(btn_label, key=f"btn_start_{selected_filename}", use_container_width=True):
                    if timer_data['running']:
                        # On arrête : on ajoute le temps écoulé au total
                        elapsed = time.time() - timer_data['start']
                        timer_data['accumulated'] += elapsed
                        timer_data['running'] = False
                    else:
                        # On démarre
                        timer_data['start'] = time.time()
                        timer_data['running'] = True
            
            with c2:
                if st.button("🗑️ RESET", key=f"btn_reset_{selected_filename}", use_container_width=True):
                    timer_data['accumulated'] = 0.0
                    timer_data['running'] = False
            
            # Calcul Affichage
            current_time = timer_data['accumulated']
            if timer_data['running']:
                current_time += time.time() - timer_data['start']
            
            st.metric("Temps sous tension (TST)", f"{current_time:.2f} s")

            st.write("---")

            # --- FORMULAIRE D'ENVOI ---
            with st.form(key=f"form_{selected_filename}"):
                st.caption("Validation des données")
                # Pré-remplissage intelligent
                nom_input = st.text_input("Athlète", placeholder="Nom de l'élève")
                # On essaie de deviner l'exo via le nom du fichier (ex: "Traction.mp4")
                exo_input = st.text_input("Exercice", value=selected_filename.split('.')[0])
                rpe_input = st.slider("RPE (Difficulté)", 1, 10, 7)
                
                submit_btn = st.form_submit_button("☁️ ENVOYER DONNÉES", type="primary", use_container_width=True)

                if submit_btn:
                    if nom_input and current_time > 0:
                        # Préparation Données
                        form_data = {
                            ENTRY_NOM: nom_input,
                            ENTRY_EXO: exo_input,
                            ENTRY_TST: str(round(current_time, 2)).replace('.', ','),
                            ENTRY_RPE: str(rpe_input)
                        }

                        try:
                            # Envoi Google Form
                            response = requests.post(URL_GOOGLE_FORM, data=form_data)
                            if response.status_code == 200:
                                st.success(f"✅ Données pour {selected_filename} envoyées !")
                                st.session_state.processed_files.add(selected_filename)
                                st.balloons()
                                time.sleep(1)
                                st.rerun() # Rafraichir pour mettre à jour le ✅ dans la liste
                            else:
                                st.error("Erreur Google.")
                        except Exception as e:
                            st.error(f"Erreur technique : {e}")
                    else:
                        st.warning("⚠️ Remplis le nom et chronomètre l'exercice.")

    elif password:
        st.error("Mot de passe incorrect.")

else:
    # Message d'accueil quand rien n'est chargé
    st.info("👋 Bienvenue sur Caliperf. Déposez vos vidéos ci-dessus pour commencer.")
