import streamlit as st
import pandas as pd
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

# --- 2. FONCTIONS DE GESTION DES DONNÉES ---
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

@st.cache_data(ttl=60)
def fetch_training_data(csv_url):
    try:
        if not csv_url: return pd.DataFrame()
        df = pd.read_csv(csv_url)
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
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1f2937; border-radius: 5px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    .metric-card { background-color: #262730; padding: 15px; border-radius: 10px; border: 1px solid #4b4b4b; margin-bottom: 10px; }
    .big-time { font-size: 2.5em; font-weight: bold; color: #00FF00; text-align: center; }
    div.stButton > button:first-child { border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state: st.session_state.students_data = load_data()

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
                full_name = f"{prenom} {nom}"
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, "freq": freq, "goal": objectif, "exp": experience,
                    "weight": poids, "height": taille, "sex": sexe,
                    "password": pwd_eleve
                }
                save_data(st.session_state.students_data)
                st.success(f"Compte configuré pour {prenom} ! Tu peux maintenant aller dans l'onglet 'Mon Suivi'.")
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

        uploaded_files = st.file_uploader("📥 Charger les vidéos reçues", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)

        if uploaded_files:
            files_map = {f.name: f for f in uploaded_files}
            opts = [("✅ " if n in st.session_state.processed_files else "⏳ ") + n for n in files_map.keys()]
            sel_opt = st.selectbox("Vidéo en cours :", opts)
            real_name = sel_opt.replace("✅ ", "").replace("⏳ ", "")
            
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            with c_vid: st.video(files_map[real_name])
            with c_tools:
                st.subheader("⏱️ Chrono")
                curr = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                st.markdown(f'<div class="big-time">{curr:.2f} s</div>', unsafe_allow_html=True)
                
                b1, b2 = st.columns(2)
                with b1: st.button("⏸️ PAUSE" if timer['run'] else "▶️ START", key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2: st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")
                
                with st.form(key=f"f_{real_name}"):
                    s_keys = list(st.session_state.students_data.keys())
                    if s_keys:
                        ca, cb = st.columns(2)
                        with ca: s_student = st.selectbox("Athlète", s_keys)
                        with cb: t_effort = st.radio("Type", ["Statique ⏱️", "Dynamique 🔁"], horizontal=True)
                        
                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        cc1, cc2 = st.columns(2)
                        with cc1: rpe = st.slider("RPE", 1, 10, 7)
                        with cc2:
                            reps = st.number_input("Reps", 1, 100, 10) if t_effort == "Dynamique 🔁" else 0
                            if t_effort == "Statique ⏱️": st.info(f"Temps : {curr:.2f} s")

                        if st.form_submit_button("☁️ ENVOYER"):
                            f_time = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                            if t_effort == "Statique ⏱️":
                                charge = f_time * rpe
                                val_princ = f"{round(f_time, 2)} s"
                            else:
                                charge = reps * rpe
                                val_princ = f"{reps} reps"

                            if charge > 0:
                                d_send = {
                                    ENTRIES['nom']: s_student, ENTRIES['exo']: exo,
                                    ENTRIES['tst']: str(val_princ).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe), ENTRIES['charge']: str(round(charge, 2)).replace('.', ',')
                                }
                                try:
                                    if requests.post(LINK_UNIQUE, data=d_send).status_code == 200:
                                        st.success("✅ Données envoyées !")
                                        st.session_state.processed_files.add(real_name)
                                        time.sleep(1)
                                        st.rerun()
                                    else: st.error("Erreur Forms")
                                except Exception as e: st.error(f"Erreur: {e}")
                    else: st.warning("Aucun élève.")
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
    st.divider()

    # ----------------------------------------------------------------
    # MODE 1 : LE COACH (Accès Total)
    # ----------------------------------------------------------------
    if mode_connexion == "🧢 Je suis le Coach":
        pwd_input = st.text_input("Mot de passe Coach", type="password", key="pwd_coach_suivi")
        
        if pwd_input == ADMIN_PWD:
            st.success("Accès Administrateur ✅")
            
            if st.session_state.students_data:
                cols = st.columns(2)
                
                # --- CORRECTION ICI : On utilise list() pour éviter l'erreur de modification pendant la boucle ---
                for index, (name, info) in enumerate(list(st.session_state.students_data.items())):
                    with cols[index % 2]:
                        emoji_sexe = "♂️" if info.get('sex') == "Homme" else "♀️"
                        pwd_user = info.get('password', '⚠️ Non défini')
                        
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name} {emoji_sexe}</h3>
                            <p><b>🔑 Pwd:</b> {pwd_user}</p>
                            <p><b>📏 Physio:</b> {info.get('height','?')}cm | {info.get('weight','?')}kg</p>
                        </div>""", unsafe_allow_html=True)

                        with st.expander(f"📈 Stats de {name}"):
                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = s_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'}).reset_index().sort_values('Date')
                                    daily['MA_Ch'] = daily['Charge'].rolling(3).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(3).mean()

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['Charge'], mode='lines+markers', line=dict(color='#00CC96'), marker=dict(color=daily['RPE'], colorscale='RdYlGn_r'), name='Charge'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange'), name='Tend.'))
                                    fig_c.update_layout(title="Charge", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False, clickmode='event+select')
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily['Date'], y=daily['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Volume", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False, clickmode='event+select')

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

                        # --- LOGIQUE DE SUPPRESSION CORRIGÉE ---
                        st.write("---")
                        cd, ct = st.columns([1,3])
                        with cd:
                            # Bouton de suppression
                            if st.button("🗑️", key=f"del_{name}"):
                                try:
                                    # 1. Envoi requête au script (optionnel, ne bloque pas si échec)
                                    try:
                                        requests.get(DELETE_SCRIPT_URL, params={"name": name}, timeout=3)
                                    except:
                                        pass # On continue même si le script répond pas
                                    
                                    # 2. Suppression locale et sauvegarde
                                    if name in st.session_state.students_data:
                                        del st.session_state.students_data[name]
                                        save_data(st.session_state.students_data)
                                        st.success(f"Supprimé !")
                                        time.sleep(1)
                                        st.rerun() # On recharge proprement
                                except Exception as e:
                                    st.error(f"Erreur : {e}")
        else:
            if pwd_input: st.error("Mot de passe incorrect.")

    # ----------------------------------------------------------------
    # MODE 2 : L'ÉLÈVE (Accès Sécurisé)
    # ----------------------------------------------------------------
    else:
        st.info("Connecte-toi pour voir tes progrès.")
        
        all_students = list(st.session_state.students_data.keys())
        if all_students:
            selected_name = st.selectbox("Je m'appelle :", ["-- Choisir --"] + all_students)
            
            if selected_name != "-- Choisir --":
                info = st.session_state.students_data[selected_name]
                stored_password = info.get('password')

                if not stored_password:
                    st.warning("⚠️ Tu n'as pas encore défini de mot de passe.")
                    st.markdown("Va dans l'onglet **'👋 Création Compte / Profil'**, remets ton nom/prénom et crée un mot de passe.")
                else:
                    input_pwd = st.text_input("Mon mot de passe :", type="password", key=f"pwd_{selected_name}")
                    
                    if st.button("Se connecter 🔓", key=f"btn_log_{selected_name}") or input_pwd == stored_password:
                        if input_pwd == stored_password:
                            st.success(f"Bon retour, {selected_name} !")
                            
                            emoji_sexe = "♂️" if info.get('sex') == "Homme" else "♀️"
                            st.markdown(f"""
                            <div class="metric-card">
                                <h3 style='margin-top:0; color:#ff4b4b;'>Bonjour {selected_name} ! {emoji_sexe}</h3>
                                <p><b>📏 Tes mensurations:</b> {info.get('height','?')}cm | {info.get('weight','?')}kg</p>
                                <p><b>🎯 Ton Objectif:</b> {info.get('goal', 'N/A')}</p>
                            </div>""", unsafe_allow_html=True)
                            
                            st.subheader("📈 Tes Graphiques")

                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == selected_name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = s_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'}).reset_index().sort_values('Date')
                                    daily['MA_Ch'] = daily['Charge'].rolling(3).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(3).mean()

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['Charge'], mode='lines+markers', line=dict(color='#00CC96'), marker=dict(color=daily['RPE'], colorscale='RdYlGn_r'), name='Charge'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange'), name='Tend.'))
                                    fig_c.update_layout(title="Ta Charge d'entraînement", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False, clickmode='event+select')
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily['Date'], y=daily['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Ton Volume (Temps / Reps)", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False, clickmode='event+select')

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
