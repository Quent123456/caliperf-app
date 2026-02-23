import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px
import plotly.graph_objects as go
import time
import requests
import json
import os
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CHARGEMENT SÉCURISÉ DES CONFIGURATIONS ---
try:
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    LINK_UNIQUE = st.secrets["general"]["google_form_url"]
    DELETE_SCRIPT_URL = st.secrets["general"]["delete_script_url"]
    ENTRIES = st.secrets["google_entries"]
    CSV_URL_SECRET = st.secrets["general"].get("csv_url", "")
    UPLOAD_LINK = st.secrets["general"].get("upload_link", "https://drive.google.com/") 
except Exception as e:
    st.error(f"⚠️ Erreur critique de configuration : {e}")
    st.stop()

DB_FILE = "caliperf_db.json"

# --- 2. FONCTIONS DE GESTION DES DONNÉES (VERSION CLOUD) ---
# Connexion au Sheet grâce à tes secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def get_users_data():
    """Récupère les données de l'onglet 'Users'"""
    try:
        # ttl=0 pour toujours avoir les données fraîches
        return conn.read(worksheet="Users", ttl=0)
    except Exception:
        return pd.DataFrame()

def add_new_user(user_dict):
    """Ajoute un nouvel utilisateur dans le Cloud"""
    try:
        df_actuel = get_users_data()
        new_row = pd.DataFrame([user_dict])
        
        if not df_actuel.empty:
            df_updated = pd.concat([df_actuel, new_row], ignore_index=True)
        else:
            df_updated = new_row
            
        conn.update(worksheet="Users", data=df_updated)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

@st.cache_data(ttl=60)
def fetch_training_data(csv_url):
    try:
        if not csv_url: return pd.DataFrame()
        df = pd.read_csv(csv_url)
        # On s'assure d'avoir les bonnes colonnes pour éviter les bugs
        # Si tes colonnes dans le CSV sont différentes, adapte cette liste !
        if len(df.columns) >= 6:
            df.columns = ["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge"]
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 3. GESTION DU CHRONO ---
def toggle_timer(video_key):
    timer = st.session_state.timers[video_key]
    if timer['run']:
        timer['acc'] += time.time() - timer['start']
        timer['run'] = False
    else:
        timer['start'] = time.time()
        timer['run'] = True

def reset_timer(video_key):
    st.session_state.timers[video_key] = {'start': 0, 'acc': 0.0, 'run': False}

# --- CSS / STYLE ---
st.markdown("""
    <style>
    /* Fond global plus sombre */
    .stApp {
        background-color: #0e1117;
    }
    
    /* Titres en majuscules et police plus impactante */
    h1, h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Style des onglets plus moderne */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
    
    /* Cards métriques avec effet de verre (Glassmorphism) */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: #ff4b4b;
    }
    
    /* Boutons plus ronds */
    div.stButton > button {
        border-radius: 20px;
        font-weight: bold;
        border: none;
        transition: all 0.3s ease;
    }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state:
    # 1. On récupère les données du Cloud
    df_users = get_users_data()
    
    # 2. Si on a des données, on les convertit au format que ton application connaît déjà (Dictionnaire)
    if not df_users.empty:
        # On vérifie si la colonne 'Fullname' existe (créée à l'inscription)
        if "Fullname" in df_users.columns:
            st.session_state.students_data = df_users.set_index("Fullname").to_dict(orient="index")
        else:
            # Si c'est vide ou pas encore formaté
            st.session_state.students_data = {}
    else:
        st.session_state.students_data = {}

st.title("🏋️ Caliperf : Espace Coaching")

tab_intro, tab_analyse, tab_eleves = st.tabs(["👋 Création Compte / Profil", "🎥 Espace Vidéo", "📊 Mon Suivi (Connexion)"])

# =========================================================
# ONGLET 1 : INSCRIPTION / PROFIL
# =========================================================
with tab_intro:
    st.header("Création ou Mise à jour du Profil 🚀")
    st.caption("Remplis ce formulaire pour créer ton compte ou mettre à jour tes informations.")
    
    with st.form("form_intro"):
        col1, col2 = st.columns(2)
        with col1: nom = st.text_input("Nom")
        with col2: prenom = st.text_input("Prénom")
        
        st.write("---")
        pwd_eleve = st.text_input("🔒 Crée ton mot de passe personnel (pour accéder à tes stats)", type="password")
        st.write("---")

        col3, col4 = st.columns(2)
        with col3: freq = st.selectbox("Fréquence", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "Tous les jours"])
        with col4: experience = st.text_input("Temps de pratique", placeholder="Ex: 2 ans, Débutant...")
        
        c_poids, c_taille, c_sexe = st.columns(3)
        with c_poids: poids = st.number_input("Poids (kg)", 30.0, 150.0, step=0.5, value=70.0)
        with c_taille: taille = st.number_input("Taille (cm)", 100, 230, step=1, value=175)
        with c_sexe: sexe = st.radio("Sexe", ["Homme", "Femme"], horizontal=True)
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Créer / Mettre à jour mon compte", type="primary", use_container_width=True):
            if nom and prenom and pwd_eleve:
                # Préparation des données
                new_user_data = {
                    "Fullname": f"{prenom} {nom}",
                    "Nom": nom,
                    "Prenom": prenom,
                    "Password": pwd_eleve,
                    "Frequence": freq,
                    "Experience": experience,
                    "Poids": poids,
                    "Taille": taille,
                    "Sexe": sexe,
                    "Objectif": objectif,
                    "Date": datetime.now().strftime("%Y-%m-%d")
                }
                
                # Envoi vers Google Sheets
                if add_new_user(new_user_data):
                    st.success(f"Compte créé pour {prenom} ! 🎉")
                    st.balloons()
            else:
                st.warning("Nom, Prénom et Mot de passe sont obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE VIDÉO
# =========================================================
with tab_analyse:
    col_titre, col_login = st.columns([3, 1])
    with col_titre:
        st.caption("Espace d'échange et d'analyse technique.")
    with col_login:
        password = st.text_input("🔒 Accès Coach (Analyse)", type="password", key="pwd_analyse")

    st.divider()

    # --- MODE COACH ---
    if password == ADMIN_PWD:
        st.success("🔓 Mode Coach activé")
        
        with st.expander("🛌 Enregistrement Rapide : REPOS / ABSENCE", expanded=True):
            c_rep1, c_rep2 = st.columns([2, 1])
            with c_rep1:
                keys = list(st.session_state.students_data.keys())
                eleve_repos = st.selectbox("Sélectionner l'élève :", keys, key="sel_repos") if keys else None
            with c_rep2:
                st.write("")
                st.write("")
                if eleve_repos and st.button("💤 VALIDER REPOS", type="primary", use_container_width=True):
                    data_repos = {
                        ENTRIES['nom']: eleve_repos, ENTRIES['exo']: "Repos",
                        ENTRIES['tst']: "0", ENTRIES['rpe']: "0", ENTRIES['charge']: "0"
                    }
                    try:
                        requests.post(LINK_UNIQUE, data=data_repos)
                        st.success(f"Repos noté pour {eleve_repos}")
                        time.sleep(1)
                        st.rerun()
                    except: st.error("Erreur envoi")

        st.divider()
        
# --- 📚 DICTIONNAIRE DE FIGURES DE L'ATHLÈTE ---
        with st.expander("📚 Gérer le dictionnaire de figures (Création de mouvements)", expanded=False):
            s_keys_dict = list(st.session_state.students_data.keys())
            if s_keys_dict:
                selected_athlete = st.selectbox("Modifier le dico de :", s_keys_dict, key="dict_athlete")
                
                # Initialiser le dico si l'élève n'en a pas encore
                if 'Figures' not in st.session_state.students_data[selected_athlete]:
                    st.session_state.students_data[selected_athlete]['Figures'] = {"Mouvement basique": 1}
                
                dict_figures = st.session_state.students_data[selected_athlete]['Figures']

                # Formulaire pour ajouter une nouvelle figure
                c_nom, c_diff, c_btn = st.columns([2, 1, 1])
                with c_nom:
                    new_fig_name = st.text_input("Nom de la figure (ex: Planche Push Up)")
                with c_diff:
                    new_fig_diff = st.number_input("Difficulté (1 à 5)", min_value=1, max_value=5, value=3)
                with c_btn:
                    st.write("")
                    st.write("")
                    if st.button("➕ Ajouter"):
                        if new_fig_name:
                            st.session_state.students_data[selected_athlete]['Figures'][new_fig_name] = new_fig_diff
                            st.success(f"Ajouté : {new_fig_name} (Niv. {new_fig_diff})")
                            time.sleep(1)
                            st.rerun()

                # Afficher le dictionnaire existant
                if dict_figures:
                    st.write("**Figures actuellement enregistrées :**")
                    df_figs = pd.DataFrame(list(dict_figures.items()), columns=["Figure", "Niveau de Difficulté"])
                    st.dataframe(df_figs, hide_index=True, use_container_width=True)
            else:
                st.warning("Aucun élève enregistré.")
                
        st.divider()
        
        # accept_multiple_files=False empêche la surcharge de la RAM
        uploaded_file = st.file_uploader("📥 Charger la vidéo à analyser (1 à la fois)", type=['mp4', 'mov', 'avi'], accept_multiple_files=False)

        if uploaded_file:
            real_name = uploaded_file.name
            
            # Affichage du statut
            if real_name in st.session_state.processed_files:
                st.success(f"✅ {real_name} déjà traitée !")
            else:
                st.info(f"⏳ Analyse en cours : {real_name}")
            
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            with c_vid: st.video(uploaded_file)
            with c_tools:
                st.subheader("⏱️ Chrono")
                curr = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                st.markdown(f'<div class="big-time">{curr:.2f} s</div>', unsafe_allow_html=True)
                
                b1, b2 = st.columns(2)
                with b1: st.button("⏸️ PAUSE" if timer['run'] else "▶️ START", key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2: st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")
                
                # --- FORMULAIRE AVANCÉ : CONSTRUCTEUR DE COMBO ---
                with st.form(key=f"f_{real_name}"):
                    s_keys = list(st.session_state.students_data.keys())
                    if s_keys:
                        s_student = st.selectbox("Athlète", s_keys)
                        
                        c_rpe, c_info = st.columns([2, 1])
                        with c_rpe:
                            rpe = st.slider("Intensité globale (RPE)", 1, 10, 7)
                        with c_info:
                            st.info(f"⏱️ Temps total : {curr:.2f} s")

                        st.write("---")
                        st.write("🔥 **Détail du Combo**")
                        st.caption("Ajoute les figures réalisées et le nombre de répétitions. Tu peux ajouter autant de lignes que tu veux !")

                        # Récupérer les figures enregistrées par l'athlète
                        athlete_figures = st.session_state.students_data[s_student].get('Figures', {"Mouvement basique": 1})
                        liste_noms_figures = list(athlete_figures.keys())

                        # Tableau dynamique (Le Combo Builder)
                        df_combo_init = pd.DataFrame([{"Figure": liste_noms_figures[0], "Répétitions": 1}])
                        
                        edited_combo = st.data_editor(
                            df_combo_init,
                            column_config={
                                "Figure": st.column_config.SelectboxColumn(
                                    "Figure réalisée",
                                    help="Sélectionne la figure dans ton dictionnaire",
                                    width="large",
                                    options=liste_noms_figures,
                                    required=True,
                                ),
                                "Répétitions": st.column_config.NumberColumn(
                                    "Répétitions",
                                    min_value=1,
                                    step=1,
                                    required=True,
                                )
                            },
                            num_rows="dynamic", # C'est CA qui permet d'ajouter plusieurs figures !
                            use_container_width=True,
                            key=f"editor_{real_name}"
                        )

                        if st.form_submit_button("☁️ ENVOYER DONNÉES"):
                            f_time = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                            
                            # --- CALCUL AUTOMATIQUE DU COEFFICIENT DU COMBO ---
                            total_coeff = 0
                            noms_figures_realisees = []

                            for index, row in edited_combo.iterrows():
                                fig_name = row["Figure"]
                                reps = row["Répétitions"]
                                
                                # On récupère la difficulté de 1 à 5, on la traduit en multiplicateur
                                diff = athlete_figures.get(fig_name, 1)
                                multiplicateur_unitaire = 1.0 + (diff - 1) * 0.25
                                
                                # On multiplie par le nombre de répétitions réalisées
                                total_coeff += (multiplicateur_unitaire * reps)
                                
                                # On construit le nom de l'exercice pour le suivi graphique
                                noms_figures_realisees.append(f"{reps}x {fig_name}")

                            nom_exo_final = " + ".join(noms_figures_realisees) # Ex: "5x Planche Push Up + 1x Front Lever"

                            # Nouvelle formule de charge finale !
                            charge = f_time * rpe * total_coeff
                            val_princ = f"{round(f_time, 2)} s"

                            if charge > 0:
                                d_send = {
                                    ENTRIES['nom']: s_student, 
                                    ENTRIES['exo']: nom_exo_final,
                                    ENTRIES['tst']: str(val_princ).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe), 
                                    ENTRIES['charge']: str(round(charge, 2)).replace('.', ',')
                                }
                                try:
                                    if requests.post(LINK_UNIQUE, data=d_send).status_code == 200:
                                        st.toast(f"✅ Combo enregistré ! (Charge: {charge:.1f} | Coeff Total: x{total_coeff:.2f})")
                                        st.session_state.processed_files.add(real_name)
                                        time.sleep(1)
                                        st.rerun()
                                    else: 
                                        st.error("Erreur d'envoi vers Google Forms")
                                except Exception as e: 
                                    st.error(f"Erreur: {e}")
                            else:
                                st.warning("Le chrono est à 0 !")
                    else:
                        st.warning("Aucun élève enregistré.")
        else:
            st.info("📂 En attente de vidéos à analyser...")
    # --- MODE ÉLÈVE ---
    else:
        st.subheader("📤 Envoyer mes vidéos au Coach")
        st.markdown("""
        Pour que ton coach puisse analyser tes mouvements, il faut lui envoyer tes vidéos.
        """)
        col_send1, col_send2 = st.columns([1, 2])
        with col_send1:
            st.info("👇 Clique ici pour déposer tes fichiers")
            st.link_button("📂 Ouvrir le dossier de dépôt", UPLOAD_LINK, type="primary", use_container_width=True)
        with col_send2:
            st.caption("Une fois tes vidéos déposées, préviens ton coach ! Il les récupérera pour les analyser ici même.")
            st.image("https://cdn-icons-png.flaticon.com/512/2983/2983067.png", width=100)

# =========================================================
# ONGLET 3 : MON SUIVI (SÉCURISÉ)
# =========================================================
with tab_eleves:
    st.header("📊 Suivi des Performances")
    
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    if SHEET_CSV_URL:
        df_history = fetch_training_data(SHEET_CSV_URL)
        if not df_history.empty and 'Charge' in df_history.columns:
            df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
            df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
            df_history['Date'] = df_history['Timestamp'].dt.date
    else:
        df_history = pd.DataFrame()

    mode_connexion = st.radio("Qui êtes-vous ?", ["👤 Je suis Élève", "🧢 Je suis le Coach"], horizontal=True)
    st.write("---")

    # ----------------------------------------------------------------
    # MODE 1 : LE COACH (Accès Total)
    # ----------------------------------------------------------------
    if "Coach" in mode_connexion:
        pwd_input = st.text_input("Mot de passe Coach", type="password", key="pwd_coach_suivi")
        
        if pwd_input == ADMIN_PWD:
            st.success("Accès Administrateur ✅")
            
            if st.session_state.students_data:
                cols = st.columns(2)
                
                # --- LIST() POUR ÉVITER L'ERREUR DE SUPPRESSION ---
                for index, (name, info) in enumerate(list(st.session_state.students_data.items())):
                    with cols[index % 2]:
                        emoji_sexe = "♂️" if info.get('Sexe') == "Homme" else "♀️"
                        pwd_user = info.get('Password', '⚠️ Non défini')
                        
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name} {emoji_sexe}</h3>
                            <p><b>🔑 Mot de passe:</b> {pwd_user}</p>
                            <p><b>📏 Morpho:</b> {info.get('Taille','?')}cm | {info.get('Poids','?')}kg</p>
                        </div>""", unsafe_allow_html=True)

                        with st.expander(f"📈 Stats de {name}"):
                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = s_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                    s_df['Date'] = pd.to_datetime(s_df['Date'])
                                    
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                                    daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                                    daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                                    
                                    daily = daily.reset_index()
                                    daily_train = daily[daily['Charge'] > 0]

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily_train['Date'], y=daily_train['Charge'], mode='markers', marker=dict(color=daily_train['RPE'], colorscale='RdYlGn_r', size=10), name='Séance'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
                                    fig_c.update_layout(title="Charge", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily_train['Date'], y=daily_train['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Volume", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

                                    c1, c2 = st.columns(2)
                                    with c1: sc = st.plotly_chart(fig_c, use_container_width=True, on_select="rerun", key=f"c_{name}")
                                    with c2: sv = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key=f"v_{name}")

                                    sel = sc if sc and sc["selection"]["points"] else sv if sv and sv["selection"]["points"] else None
                                    if sel:
                                        dt = sel["selection"]["points"][0]["x"]
                                        st.markdown(f"**🔎 Détail du {dt}**")
                                        det = s_df[s_df['Date'].astype(str)==dt].copy()
                                        st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)
                                else: st.info("Pas de données.")
                            else: st.error("Erreur données.")

                        # --- LOGIQUE DE SUPPRESSION SÉCURISÉE ---
                        st.write("---")
                        cd, ct = st.columns([1,3])
                        with cd:
                            if st.button("🗑️", key=f"del_{name}"):
                                try:
                                    try:
                                        requests.get(DELETE_SCRIPT_URL, params={"name": name}, timeout=3)
                                    except: pass
                                    
                                    if name in st.session_state.students_data:
                                        del st.session_state.students_data[name]
                                        st.success(f"Supprimé de la vue actuelle.")
                                        time.sleep(1)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur : {e}")
        else:
            if pwd_input: st.error("Mot de passe incorrect.")

    # ----------------------------------------------------------------
    # MODE 2 : L'ÉLÈVE (Accès Sécurisé)
    # ----------------------------------------------------------------
    elif "Élève" in mode_connexion:
        st.info("Connecte-toi pour voir tes progrès.")
        
        all_students = list(st.session_state.students_data.keys())
        if all_students:
            selected_name = st.selectbox("Je m'appelle :", ["-- Choisir --"] + all_students)
            
            if selected_name != "-- Choisir --":
                info = st.session_state.students_data[selected_name]
                stored_password = info.get('Password')

                if not stored_password:
                    st.warning("⚠️ Tu n'as pas encore défini de mot de passe.")
                    st.markdown("Va dans l'onglet **'👋 Création Compte / Profil'**, remets ton nom/prénom et crée un mot de passe.")
                else:
                    input_pwd = st.text_input("Mon mot de passe :", type="password", key=f"pwd_{selected_name}")
                    
                    if st.button("Se connecter 🔓", key=f"btn_log_{selected_name}") or input_pwd == stored_password:
                        if input_pwd == stored_password:
                            st.success(f"Bon retour, {selected_name} !")
                            
                            emoji_sexe = "♂️" if info.get('Sexe') == "Homme" else "♀️"
                            st.markdown(f"""
                            <div class="metric-card">
                                <h3 style='margin-top:0; color:#ff4b4b;'>Bonjour {selected_name} ! {emoji_sexe}</h3>
                                <p><b>📏 Tes mensurations:</b> {info.get('Taille','?')}cm | {info.get('Poids','?')}kg</p>
                                <p><b>🎯 Ton Objectif:</b> {info.get('Objectif', 'N/A')}</p>
                            </div>""", unsafe_allow_html=True)
                            
                            st.subheader("📈 Tes Graphiques")

                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == selected_name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = s_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                    s_df['Date'] = pd.to_datetime(s_df['Date'])
                                    
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                                    daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                                    daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                                    
                                    daily = daily.reset_index()
                                    daily_train = daily[daily['Charge'] > 0]

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily_train['Date'], y=daily_train['Charge'], mode='markers', marker=dict(color=daily_train['RPE'], colorscale='RdYlGn_r', size=10), name='Séance'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
                                    fig_c.update_layout(title="Ta Charge d'entraînement", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily_train['Date'], y=daily_train['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Ton Volume (TST / Reps)", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

                                    c1, c2 = st.columns(2)
                                    with c1: sc = st.plotly_chart(fig_c, use_container_width=True, on_select="rerun", key=f"c_student_{selected_name}")
                                    with c2: sv = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key=f"v_student_{selected_name}")

                                    sel = sc if sc and sc["selection"]["points"] else sv if sv and sv["selection"]["points"] else None
                                    if sel:
                                        dt = sel["selection"]["points"][0]["x"]
                                        st.markdown(f"**🔎 Détail de ta séance du {dt}**")
                                        det = s_df[s_df['Date'].astype(str)==dt].copy()
                                        st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)
                                else: st.info("Pas encore de données d'entraînement. Envoie tes vidéos !")
                            else: st.error("Impossible de récupérer l'historique.")
                        else:
                            st.error("Mot de passe incorrect ❌")
        else:
            st.warning("Aucun élève inscrit dans la base.")




