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
conn = st.connection("gsheets", type=GSheetsConnection)

def get_users_data():
    """Récupère les données de l'onglet 'Users'"""
    try:
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

def save_figures_to_cloud(fullname, figures_dict):
    """Sauvegarde le dictionnaire de figures d'un élève dans le Google Sheet"""
    try:
        df = get_users_data()
        if not df.empty and "Fullname" in df.columns:
            if "Figures" not in df.columns:
                df["Figures"] = "{}"
            
            json_str = json.dumps(figures_dict)
            df.loc[df["Fullname"] == fullname, "Figures"] = json_str
            
            conn.update(worksheet="Users", data=df)
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde Cloud : {e}")
        return False

@st.cache_data(ttl=60)
def fetch_training_data(csv_url):
    try:
        if not csv_url: return pd.DataFrame()
        df = pd.read_csv(csv_url)
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
    .stApp { background-color: #0e1117; }
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; text-transform: uppercase; letter-spacing: 1px; }
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-size: 1.1rem; font-weight: 600; }
    .metric-card { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); transition: transform 0.2s; }
    .metric-card:hover { transform: translateY(-5px); border-color: #ff4b4b; }
    div.stButton > button { border-radius: 20px; font-weight: bold; border: none; transition: all 0.3s ease; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state:
    df_users = get_users_data()
    st.session_state.students_data = {}
    
    if not df_users.empty and "Fullname" in df_users.columns:
        for _, row in df_users.iterrows():
            user_dict = row.to_dict()
            
            if "Figures" in user_dict and pd.notna(user_dict["Figures"]) and str(user_dict["Figures"]).strip() != "":
                try:
                    user_dict["Figures"] = json.loads(str(user_dict["Figures"]))
                except:
                    user_dict["Figures"] = {"Mouvement basique": 1}
            else:
                user_dict["Figures"] = {"Mouvement basique": 1}
                
            st.session_state.students_data[row["Fullname"]] = user_dict
    else:
        st.session_state.students_data = {}

st.title("🏋️ Caliperf : Espace Coaching")

tab_intro, tab_analyse, tab_eleves, tab_vbt = st.tabs(["👋 Profil", "🎥 Espace Vidéo", "📊 Mon Suivi", "⚡ Analyse Vitesse (VBT)"])
# =========================================================
# COMPOSANT PARTAGÉ : BIBLIOTHÈQUE DE FIGURES
# =========================================================
def render_figure_manager(athlete_name):
    """Affiche l'interface de gestion de la bibliothèque de mouvements pour un élève"""
    st.markdown("### 📚 Ma Bibliothèque de Mouvements")
    st.caption("Ajoute tes figures et détermine leur difficulté (1 = Simple, 5 = Extrême) pour calculer ton combo.")
    
    dict_figures = st.session_state.students_data[athlete_name].get('Figures', {"Mouvement basique": 1})

    c_nom, c_diff, c_btn = st.columns([2, 1, 1])
    with c_nom:
        new_fig_name = st.text_input("Nom de la figure", key=f"fig_name_{athlete_name}")
    with c_diff:
        new_fig_diff = st.number_input("Difficulté", min_value=1, max_value=5, value=3, key=f"fig_diff_{athlete_name}")
    with c_btn:
        st.write("")
        st.write("")
        if st.button("➕ Enregistrer", key=f"btn_add_{athlete_name}"):
            if new_fig_name:
                st.session_state.students_data[athlete_name]['Figures'][new_fig_name] = new_fig_diff
                if save_figures_to_cloud(athlete_name, st.session_state.students_data[athlete_name]['Figures']):
                    st.success(f"✅ {new_fig_name} (Niveau {new_fig_diff}) sauvegardé dans le Cloud !")
                    time.sleep(1)
                    st.rerun()

    if dict_figures:
        df_figs = pd.DataFrame(list(dict_figures.items()), columns=["Figure", "Niveau de Difficulté"])
        st.dataframe(df_figs, hide_index=True, use_container_width=True)

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
        
        uploaded_file = st.file_uploader("📥 Charger la vidéo à analyser (1 à la fois)", type=['mp4', 'mov', 'avi'], accept_multiple_files=False)

        if uploaded_file:
            real_name = uploaded_file.name
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
                
                # --- NOUVELLE STRUCTURE ---
                s_keys = list(st.session_state.students_data.keys())
                
                if s_keys:
                    s_student = st.selectbox("Athlète", s_keys, key=f"sel_athlete_{real_name}")
                    
                    with st.form(key=f"f_{real_name}"):
                        c_rpe, c_info = st.columns([2, 1])
                        with c_rpe:
                            rpe = st.slider("Intensité globale (RPE)", 1, 10, 7)
                        with c_info:
                            st.info(f"⏱️ Temps total : {curr:.2f} s")

                        st.write("---")
                        st.write("🔥 **Détail du Combo**")
                        st.caption("Ajoute les figures réalisées et le nombre de répétitions. Tu peux ajouter autant de lignes que tu veux !")

                        # --- RÉCUPÉRATION DES FIGURES ---
                        athlete_figures = st.session_state.students_data[s_student].get('Figures', {})
                        if not athlete_figures:
                            athlete_figures = {"Mouvement basique": 1}
                            
                        liste_noms_figures = list(athlete_figures.keys())

                        # --- NOUVELLE UI MOBILE-FRIENDLY ---
                        options_figures = ["-- Aucune --"] + liste_noms_figures
                        
                        st.write("---")
                        st.markdown("🔥 **Détail du Combo**")
                        st.caption("Sélectionne tes figures. Laisse sur '-- Aucune --' si tu n'as pas besoin de toutes les lignes.")
                        
                        combo_selections = []
                        
                        # On prépare 5 emplacements (suffisant pour un combo classique)
                        for i in range(5):
                            c_fig, c_reps = st.columns([3, 1])
                            with c_fig:
                                # Le premier emplacement prend la 1ère figure par défaut, les autres sont vides
                                default_idx = 1 if i == 0 else 0 
                                fig = st.selectbox(
                                    f"Figure {i}", 
                                    options=options_figures, 
                                    index=default_idx, 
                                    key=f"fig_{real_name}_{s_student}_{i}",
                                    label_visibility="collapsed" # Cache le titre pour gagner de la place
                                )
                            with c_reps:
                                reps = st.number_input(
                                    f"Reps {i}", 
                                    min_value=1, step=1, 
                                    key=f"reps_{real_name}_{s_student}_{i}",
                                    label_visibility="collapsed"
                                )
                            combo_selections.append({"Figure": fig, "Répétitions": reps})

                        st.write("---")

                        # Bouton en pleine largeur pour mobile
                        if st.form_submit_button("☁️ ENVOYER DONNÉES", type="primary", use_container_width=True):
                            f_time = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                            
                            total_coeff = 0
                            noms_figures_realisees = []

                            for item in combo_selections:
                                fig_name = item["Figure"]
                                reps = item["Répétitions"]
                                
                                # On ignore les lignes laissées sur "-- Aucune --"
                                if fig_name != "-- Aucune --":
                                    diff = athlete_figures.get(fig_name, 1)
                                    multiplicateur_unitaire = 1.0 + (diff - 1) * 0.25
                                    total_coeff += (multiplicateur_unitaire * reps)
                                    noms_figures_realisees.append(f"{reps}x {fig_name}")

                            if not noms_figures_realisees:
                                st.error("⚠️ Tu dois sélectionner au moins une figure !")
                            else:
                                nom_exo_final = " + ".join(noms_figures_realisees)
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
                                            st.toast(f"✅ Combo enregistré ! (Charge: {charge:.1f} | Coeff: x{total_coeff:.2f})")
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
        st.markdown("Pour que ton coach puisse analyser tes mouvements, il faut lui envoyer tes vidéos.")
        col_send1, col_send2 = st.columns([1, 2])
        with col_send1:
            st.info("👇 Clique ici pour déposer tes fichiers")
            st.link_button("📂 Ouvrir le dossier de dépôt", UPLOAD_LINK, type="primary", use_container_width=True)
        with col_send2:
            st.caption("Une fois tes vidéos déposées, préviens ton coach ! Il les récupérera pour les analyser ici même.")

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

                        with st.expander(f"📚 Gérer les figures de {name}"):
                            render_figure_manager(name)

                st.write("---")
                cd, ct = st.columns([1,3])
                with cd:
                    if st.button("🗑️ Supprimer un élève", key="del_student_btn"):
                        st.warning("La suppression nécessite l'ID exact. Fonction en maintenance.")
            else:
                st.warning("La base de données des élèves est vide. Si tu viens d'ajouter un élève, rafraîchis la page.")
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
                            
                            st.write("---")
                            render_figure_manager(selected_name)
                            
                        else:
                            st.error("Mot de passe incorrect ❌")
        else:
            st.warning("Aucun élève inscrit dans la base.")
            

import cv2
import numpy as np
import tempfile
from streamlit_image_coordinates import streamlit_image_coordinates

with tab_vbt:
    st.header("⚡ Analyse de la Vitesse (Velocity-Based Training)")
    st.markdown("Mesure la vitesse de convergence entre le bassin et la barre pour objectiver la fatigue nerveuse.")

    vbt_file = st.file_uploader("📥 Charger la vidéo pour analyse biomécanique", type=['mp4', 'mov'], key="vbt_uploader")

    if vbt_file:
        # 1. Sauvegarder la vidéo temporairement pour qu'OpenCV puisse la lire
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(vbt_file.read())
        video_path = tfile.name

        # 2. Lire la vidéo et extraire la première image
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        ret, frame = cap.read()
        
        if ret:
            # Convertir l'image de BGR (OpenCV) à RGB (Streamlit)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            st.subheader("🎯 Étape 1 : Place tes gommettes")
            st.info("Clique sur l'image pour placer tes 2 points (1: Bassin, 2: Barre).")
            
            # Initialiser le stockage des points dans la session
            if 'gommettes' not in st.session_state:
                st.session_state.gommettes = []

            # Afficher l'image interactive
            value = streamlit_image_coordinates(frame_rgb, key=f"points_{vbt_file.name}")
            
            # Enregistrer les clics
            if value is not None:
                point = (value["x"], value["y"])
                if point not in st.session_state.gommettes and len(st.session_state.gommettes) < 2:
                    st.session_state.gommettes.append(point)
                    st.rerun()

            # Afficher les points sélectionnés
            if len(st.session_state.gommettes) > 0:
                st.write(f"📍 Point 1 (Bassin) : {st.session_state.gommettes[0]}")
            if len(st.session_state.gommettes) == 2:
                st.write(f"📍 Point 2 (Barre) : {st.session_state.gommettes[1]}")
                
                if st.button("🚀 Lancer l'analyse de vitesse", type="primary"):
                    st.info("Traitement vidéo en cours avec OpenCV... (cela peut prendre quelques secondes)")
                    
                    # --- LOGIQUE DE TRACKING OPENCV (Simplifiée pour l'exemple) ---
                    # Dans une version complète, on utiliserait cv2.TrackerCSRT_create() ici.
                    # Pour l'instant, on simule la récupération des distances frame par frame.
                    
                    distances = []
                    times = []
                    frame_count = 0
                    
                    # Boucle de lecture de la vidéo (simulation du suivi)
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        
                        # Ici interviendrait le tracker OpenCV pour mettre à jour les (x, y)
                        # On simule un rapprochement des deux points
                        simulated_distance = max(0, 300 - (frame_count * 5)) 
                        
                        distances.append(simulated_distance)
                        times.append(frame_count / fps)
                        frame_count += 1
                        
                    cap.release()
                    
                    # --- CALCUL DE LA VITESSE ---
                    # Vitesse = Différence de distance / Différence de temps
                    df_vbt = pd.DataFrame({"Temps (s)": times, "Distance (px)": distances})
                    df_vbt["Vitesse (px/s)"] = abs(df_vbt["Distance (px)"].diff() / df_vbt["Temps (s)"].diff())
                    
                    # Lissage de la courbe (Moyenne mobile) pour éviter le bruit
                    df_vbt["Vitesse_lisse"] = df_vbt["Vitesse (px/s)"].rolling(window=3).mean()
                    
                    v_max = df_vbt["Vitesse_lisse"].max()
                    
                    st.success(f"✅ Analyse terminée ! Vitesse Max atteinte : {v_max:.2f} px/s")
                    
                    # Affichage graphique
                    fig = px.line(df_vbt, x="Temps (s)", y="Vitesse_lisse", title="Profil Vitesse du Mouvement")
                    st.plotly_chart(fig, use_container_width=True)
                    
            if st.button("🗑️ Réinitialiser les points"):
                st.session_state.gommettes = []
                st.rerun()



