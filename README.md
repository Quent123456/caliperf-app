# ⚡ Caliperf V2 - Studio de Vidéo-Coaching & Analyse TST

Caliperf V2 est une application dédiée aux coachs sportifs (Calisthenics, Street Lifting, Force Athlétique, Musculation) pour accélérer et fiabiliser l'analyse vidéo des entraînements de leurs élèves.

---

## 🚀 Nouveautés de la Version 2 (Ergonomie & Vitesse)

### 1. 🎬 Studio Vidéo Haute Vélocité
- **Détection Automatique (Zero Clic)** : Analyse automatique du nom de fichier vidéo (ex: `Lucas_Dips_20kg.mp4`) pour pré-sélectionner instantanément l'athlète et l'exercice.
- **Triple Méthode de Mesure du TST (Temps Sous Tension)** :
  1. **Repères In/Out précis** : Pointez le début du set (ex: 3.5s) et la fin du set (ex: 28.0s) ➔ calcul automatique instantané ($24.5s$).
  2. **Chronomètre dynamique** : Démarrage / pause avec ajustements fins (`+0.5s`, `-1.0s`, `+5s`, `RAZ`).
  3. **Saisie directe** : Tapez directement la valeur si vous avez chronométré manuellement.
- **Réglette RPE Interactive** : Échelle 1-10 avec zones d'effort codées par couleur (vert pour technique/récupération, bleu pour hypertrophie, orange pour intensité haute, rouge pour échec musculaire/PR).
- **Enchaînement automatique** : Dès la validation, la séance est enregistrée et l'application passe automatiquement à la vidéo suivante de la file.

### 2. 📊 Suivi & Progression Locale Intégrée
- **Ne perdez plus aucune donnée** : Toutes les séances sont historisées localement dans `caliperf_db.json`.
- **Graphiques de progression** : Visualisez l'évolution du TST au fil des semaines par exercice et par athlète (générés avec Plotly).
- **Export en 1 clic** : Exportation de tout l'historique en fichier CSV / Excel.

### 3. 🔗 Synchronisation Google Forms / Google Sheets Robuste
- Synchronisation automatique avec votre formulaire Google (configurable dans l'onglet Paramètres).
- **Mode résilient** : Si la connexion Internet échoue, les données restent enregistrées localement sans bloquer votre travail de coaching.

### 4. 👥 Dossiers Athlètes
- Fiches de suivi avec objectifs, fréquence hebdomadaire et compteur de séances validées.
- Inscription rapide d'un nouvel athlète en 1 formulaire.

---

## 🛠️ Démarrage Rapide

### Prérequis
- Python 3.10+
- Dépendances : `streamlit`, `pandas`, `requests`, `plotly`

### Lancement
```bash
streamlit run caliperf.py
```

L'application s'ouvrira automatiquement dans votre navigateur par défaut à l'adresse `http://localhost:8501`.

---

## 🎨 Direction Artistique
- Thème sombre athlétique à haut contraste (*Dark Athletic Kinetic*)
- Accents Cyan Électrique (`#00f0ff`) et Vert Lime (`#10b981`)
- Cartes en verre dépoli (*glassmorphism*) et affichage numérique d'inspiration chrono pro.
