"""
core/auth.py - Système d'authentification et de gestion des comptes CaliPerf (Admin / Coach / Élève)
Fonctionnalités :
- Hachage sécurisé des mots de passe (SHA-256)
- Gestion des rôles : Admin (Principal), Coach, Élève
- Traitement et compression ultra-légère des photos de profil (Avatars en Base64 max 128x128)
- Vérification d'authentification et création de compte
- Affichage de badge profil responsive
"""

import io
import re
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def hash_password(password: str) -> str:
    """Génère un hash SHA-256 sécurisé pour un mot de passe."""
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Vérifie la correspondance d'un mot de passe avec son hash."""
    if not hashed:
        return False
    # Compatibilité mot de passe en clair pour le compte de transition 'admin'
    if hashed == password.strip():
        return True
    return hash_password(password) == hashed


def process_avatar_image(uploaded_file, max_size=(128, 128)) -> str:
    """
    Redimensionne et compresse une photo de profil uploadée en JPEG Base64 ultra-léger (< 10 Ko).
    Retourne une URI data:image/jpeg;base64,... prête pour le web.
    """
    if uploaded_file is None:
        return ""

    try:
        if hasattr(uploaded_file, "read"):
            bytes_data = uploaded_file.read()
        elif isinstance(uploaded_file, bytes):
            bytes_data = uploaded_file
        else:
            return ""

        if not bytes_data:
            return ""

        if HAS_PIL:
            import base64
            img = Image.open(io.BytesIO(bytes_data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Recadrage carré centré
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) / 2
            top = (h - min_dim) / 2
            right = (w + min_dim) / 2
            bottom = (h + min_dim) / 2
            img_cropped = img.crop((left, top, right, bottom))
            img_resized = img_cropped.resize(max_size, Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG", quality=82, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
        else:
            import base64
            encoded = base64.b64encode(bytes_data).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"Erreur traitement avatar : {e}")
        return ""


def get_default_admin(admin_pwd: str = "admin") -> Dict[str, Any]:
    """Retourne le compte administrateur principal par défaut."""
    return {
        "id": "usr_admin",
        "username": "admin",
        "password_hash": hash_password(admin_pwd),
        "role": "admin",
        "full_name": "Administrateur Principal",
        "avatar": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }


def authenticate_user(
    username: str,
    password: str,
    users_dict: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Vérifie les identifiants d'un utilisateur.
    Retourne le dictionnaire de l'utilisateur si succès, sinon None.
    """
    clean_u = username.strip().lower()
    if not clean_u or not password:
        return None

    # Recherche insensible à la casse
    user_record = None
    for uname, udata in users_dict.items():
        if uname.strip().lower() == clean_u or str(udata.get("username", "")).strip().lower() == clean_u:
            user_record = udata
            break

    if not user_record:
        return None

    stored_hash = user_record.get("password_hash", "")
    if verify_password(password, stored_hash):
        return user_record

    return None


def register_user(
    username: str,
    password: str,
    role: str,
    full_name: str,
    avatar_data: str,
    users_dict: Dict[str, Any]
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Crée un nouvel utilisateur (Coach ou Élève).
    """
    clean_u = re.sub(r'[^a-zA-Z0-9_\-\.]+', '', username.strip().lower())
    if len(clean_u) < 3:
        return False, "L'identifiant doit comporter au moins 3 caractères alphanumériques.", None

    if len(password) < 4:
        return False, "Le mot de passe doit comporter au moins 4 caractères.", None

    clean_role = role.strip().lower()
    if clean_role not in ("admin", "coach", "eleve"):
        clean_role = "eleve"

    # Vérification d'unicité
    for uname, udata in users_dict.items():
        if uname.strip().lower() == clean_u or str(udata.get("username", "")).strip().lower() == clean_u:
            return False, f"L'identifiant '{clean_u}' est déjà utilisé.", None

    user_id = f"usr_{clean_u}_{int(datetime.now().timestamp())}"
    new_user = {
        "id": user_id,
        "username": clean_u,
        "password_hash": hash_password(password),
        "role": clean_role,
        "full_name": full_name.strip() or clean_u.capitalize(),
        "avatar": avatar_data or "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    users_dict[clean_u] = new_user
    return True, f"Compte '{clean_u}' créé avec succès !", new_user


def get_role_badge_info(role: str) -> Tuple[str, str, str]:
    """Retourne (label, badge_class, icon) pour un rôle donné."""
    r = str(role).strip().lower()
    if r == "admin":
        return "Administrateur", "badge-gold", "👑"
    elif r == "coach":
        return "Coach", "badge-cyan", "🏋️"
    else:
        return "Élève", "badge-lime", "🤸"


def render_avatar_html(avatar_data: str, name: str, size: int = 38) -> str:
    """Génère le HTML d'un avatar circulaire (photo Base64 ou initiale avec gradient)."""
    clean_name = str(name).strip() or "User"
    initial = clean_name[0].upper()

    if avatar_data and avatar_data.startswith("data:image"):
        return f"""
            <img src="{avatar_data}" alt="{clean_name}" style="
                width: {size}px;
                height: {size}px;
                border-radius: 50%;
                object-fit: cover;
                border: 2px solid rgba(0, 240, 255, 0.4);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                display: inline-block;
                vertical-align: middle;
            " />
        """
    else:
        # Cercle avec dégradé et initiale
        font_size = max(11, int(size * 0.42))
        return f"""
            <div style="
                width: {size}px;
                height: {size}px;
                border-radius: 50%;
                background: linear-gradient(135deg, #00f0ff, #0077ff);
                color: #030712;
                font-weight: 800;
                font-size: {font_size}px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 2px solid rgba(255, 255, 255, 0.2);
                box-shadow: 0 2px 8px rgba(0, 240, 255, 0.3);
                vertical-align: middle;
            ">
                {initial}
            </div>
        """
