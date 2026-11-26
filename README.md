# ⚡ CaliPerf Pro — Plateforme Biomécanique 3D, Charge & Suivi Longitudinal SQL

CaliPerf Pro est une application autonome dédiée au coaching de Callisthénie, Street Workout et Street Lifting : analyse cinématique 3D (`pose_world_landmarks`), contrôle qualité vidéo avant calibration, quantification de charge pondérée, dérive technique intra-série, suivi longitudinal ACWR (EWMA 7j/28j), jauge de stress tendineux et persistance relationnelle SQL.

## Fonctionnalités Clés
- **Persistance SQL autonome (`SQLAlchemy`) :** PostgreSQL cloud via `st.secrets["DATABASE_URL"]` avec bascule automatique sur SQLite local (`data/caliperf.db`). Zéro dépendance à Google Sheets / Google Forms.
- **Multi-utilisateurs isolés & persistance `F5` :** Comptes `Coach` et `Élève` protégés par `hashlib.pbkdf2_hmac`, codes d'invitation coach, sélecteur d'athlète latéral et jeton signé HMAC dans `?session=` conservant la session au rafraîchissement.
- **Quality Control Gate 3D (`core/quality_control.py`) :** Évalue en passe unique cadrage (`0.03–0.97`), occupation (`45–85 %`), visibilité (`>= 0.80`), cadence (`FPS >= 24`), stabilité angulaire 3D et cohérence de l'angle déclaré avant sauvegarde dans `baselines_3d`.
- **Pont Vidéo → Charge & Dérive Intra-Série :** Calcul automatique de la charge externe pondérée (UA), du `sRPE`, de la dérive $\Delta\theta$ seconde par seconde (isométrique) et de la perte de vélocité `%` (dynamique).
- **Dashboard Longitudinal & Exports :** Ratio ACWR EWMA, Monotonie/Contrainte de Foster, Stress Tendineux Haute Intensité, exports CSV (`utf-8-sig`) et Excel multi-onglets (`.xlsx` via `openpyxl`).
- **RAM maîtrisée (< 1 Go) :** Écriture/lecture vidéo en flux via `tempfile.NamedTemporaryFile` + suppression explicite et `gc.collect()` après chaque vidéo.

## Démarrage rapide
```powershell
pip install -r requirements.txt
streamlit run caliperf.py
```
