from typing import Tuple, Optional
import streamlit as st

# 1) Konfiguration laden: bevorzugt hub_config.CONFIG, sonst Fallback
try:
    from hub_config import CONFIG as HUB_CONFIG
except Exception:
    HUB_CONFIG = None

_CFG = HUB_CONFIG or {
    "credentials": {
        "usernames": {
            "admin": {
                "name": "Admin",
                # Dieser Platzhalter wird nie genutzt, wenn hub_config vorhanden ist.
                # Falls doch: unbedingt durch echten bcrypt-Hash ersetzen.
                "password": "$2b$12$Jrfi8V7zG4JrJ7QyBz7lUeMZp5XhQm3W0hQxgI9m5bVnJ4m5W8f8y",
                "roles": ["admin"],
                "allowed_tools": ["*"],
            }
        }
    },
    "cookie": { "name": "se_hub_auth", "key": "SE_KEY_FALLBACK", "expiry_days": 7 },
    "preauthorized": { "emails": [] },
}

def get_config() -> dict:
    return _CFG

def _make_auth():
    """Erzeugt ein Authenticate-Objekt mit _CFG; robust gegen Paket-/Config-Fehler."""
    try:
        import streamlit_authenticator as stauth
    except Exception as e:
        st.error(f"Auth-Paket fehlt oder inkompatibel: {e}")
        st.stop()

    creds = _CFG.get("credentials", {})
    cookie = _CFG.get("cookie", {}) or {}
    cookie_name = cookie.get("name", "se_hub_auth")
    cookie_key  = cookie.get("key",  "SE_KEY")
    cookie_days = int(cookie.get("expiry_days", 7))

    try:
        auth = stauth.Authenticate(
            credentials=creds,
            cookie_name=cookie_name,
            key=cookie_key,
            cookie_expiry_days=cookie_days,
        )
    except Exception as e:
        st.error(f"Authenticate-Init fehlgeschlagen: {e}")
        st.stop()
    return auth

def do_auth() -> Tuple[Optional[str], Optional[str], str, object]:
    """
    Rendert die Login-Maske in der Sidebar (streamlit_authenticator >=0.3.x: login() gibt nichts zurück).
    Liest name/username/authentication_status aus st.session_state.
    Rückgabe: (name, username, status, auth)
      - status: 'authenticated' | 'failed' | 'pending'
    """
    auth = _make_auth()
    # Login UI (keine Unpack-Variante!)
    try:
        with st.sidebar:
            st.caption(" ")
            st.markdown("### 🔐 Login")
            auth.login("sidebar")
    except Exception as e:
        st.error(f"Login-Fehler: {e}")

    name = st.session_state.get("name")
    username = st.session_state.get("username")
    auth_status = st.session_state.get("authentication_status")

    if auth_status is True:
        status = "authenticated"
    elif auth_status is False:
        status = "failed"
    else:
        status = "pending"

    return name, username, status, auth

def sidebar_header(auth, name: Optional[str], username: Optional[str]) -> None:
    """Zeigt oben in der Sidebar Logout + 'Eingeloggt als' an."""
    with st.sidebar:
        st.divider()
        try:
            auth.logout("Logout", "sidebar", key="logout_btn_fixed")
        except Exception:
            pass
        st.caption(f"**Eingeloggt als:** {name or '-'} ({username or '-'})")
        st.divider()
