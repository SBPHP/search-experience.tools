# -*- coding: utf-8 -*-
from typing import Dict
import os, json, time, pathlib, hashlib, hmac
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------
# User-Loading: secrets.toml / FILE / ENV / Dev
# ---------------------------------------

SECRET_PATHS = [
    "/var/www/.streamlit/secrets.toml",
    "/opt/tools/hub/.streamlit/secrets.toml",
    str(pathlib.Path.cwd() / ".streamlit" / "secrets.toml"),
]

FILE_USER_PATHS = [
    "/etc/se-hub/users.json",
    "/opt/tools/hub/config/users.json",
    "/var/www/se-hub/users.json",
]

def _secrets_available() -> bool:
    for p in SECRET_PATHS:
        try:
            if os.path.exists(p):
                return True
        except Exception:
            pass
    return False

def _read_users_file() -> Dict[str, str]:
    for p in FILE_USER_PATHS:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except Exception:
            continue
    return {}

def _load_users() -> Dict[str, str]:
    if _secrets_available():
        try:
            sec = st.secrets.get("users")  # type: ignore[attr-defined]
            if sec:
                return {str(k): str(v) for k, v in dict(sec).items()}
        except Exception:
            pass
    file_users = _read_users_file()
    if file_users:
        return file_users
    env_json = os.environ.get("SE_USERS_JSON")
    if env_json:
        try:
            data = json.loads(env_json)
            return {str(k): str(v) for k, v in dict(data).items()}
        except Exception:
            pass
    u = os.environ.get("SE_DEFAULT_USER")
    h = os.environ.get("SE_DEFAULT_PASS_SHA256")
    if u and h:
        return {u: f"sha256:{h}"}
    if os.environ.get("SE_DEV_FALLBACK") == "1":
        return {"admin": "sha256:" + hashlib.sha256(b"admin").hexdigest()}
    return {}

# === AUTH GUARD ===
def _se_auth_obj():
    return (
        st.session_state.get("authenticator")
        or st.session_state.get("auth")
        or st.session_state.get("AUTHENTICATOR")
    )

def _se_is_logged_in() -> bool:
    if st.session_state.get("authentication_status") is True:
        return True
    if st.session_state.get("authed") is True:
        return True
    for k in ("username","user","email","name","display_name","user_name"):
        v = st.session_state.get(k)
        if isinstance(v, str) and v.strip() and v.strip() != "-":
            return True
    return False

def _se_verify_pw(user: str, pw: str) -> bool:
    users = _load_users()
    if not users or not user or user not in users:
        return False
    try:
        algo, hexhash = str(users[user]).split(":", 1)
    except ValueError:
        return False
    if algo.lower() != "sha256":
        return False
    calc = hashlib.sha256(pw.encode()).hexdigest()
    return hmac.compare_digest(calc, hexhash)

def render_login():
    auth = _se_auth_obj()
    if auth and hasattr(auth, "login"):
        auth.login("🔐 Anmeldung", "sidebar", key="se_login_form_v2")
        return
    st.sidebar.markdown("### 🔐 Anmeldung")
    with st.sidebar.form("se_login_fallback", clear_on_submit=False):
        u = st.text_input("Benutzername")
        p = st.text_input("Passwort", type="password")
        ok = st.form_submit_button("Einloggen")
    if ok:
        if _se_verify_pw(u.strip(), p):
            st.session_state["authed"] = True
            st.session_state["username"] = u.strip()
            st.session_state["auth_time"] = int(time.time())
            st.rerun()
        else:
            st.error("Benutzername oder Passwort falsch")

def require_login():
    if _se_is_logged_in():
        return
    render_login()
    st.stop()

st.set_page_config(page_title="Tools Hub", page_icon="🧰", layout="wide", initial_sidebar_state="expanded")

# === CSS & JS: nur den FALschen Logout (Fallback) entsorgen ===
st.markdown("""
<style>
.st-key-sidebar_logout_btn_v2_fallback { display:none !important; }
</style>
""", unsafe_allow_html=True)

components.html("""
<script>
(function(){
  const kill = () => {
    document.querySelectorAll('.st-key-sidebar_logout_btn_v2_fallback').forEach(n => n.remove());
  };
  kill();
  const mo = new MutationObserver(kill);
  mo.observe(document.documentElement,{subtree:true,childList:true});
})();
</script>
""", height=0)

require_login()

def _extract_name(v):
    if not v: return ""
    if isinstance(v, str): return v.strip()
    if isinstance(v, dict):
        for k in ("display_name","name","username","user","email"):
            x = v.get(k)
            if isinstance(x, str) and x.strip(): return x.strip()
    return ""

def _current_user_name():
    for k in ("display_name","name","user_name","username","user","email"):
        n = _extract_name(st.session_state.get(k))
        if n: return n
    for k in ("profile","account","user_info"):
        n = _extract_name(st.session_state.get(k))
        if n: return n
    _auth = _se_auth_obj()
    if _auth:
        for attr in ("display_name","user_name","name","username","user","email"):
            if hasattr(_auth, attr):
                n = _extract_name(getattr(_auth, attr))
                if n: return n
    return ""

with st.sidebar:
    _auth = _se_auth_obj()
    if _auth and hasattr(_auth, "logout"):
        _auth.logout("🚪 Logout", "sidebar", key="sidebar_logout_btn_v2_native")
    elif os.environ.get("SE_ENABLE_FALLBACK_LOGOUT") == "1":
        if st.button("🚪 Logout (Fallback)", key="manual_logout_btn", use_container_width=True):
            for k in ("authentication_status","authed","username","user","email","name",
                      "display_name","user_name","roles"):
                st.session_state.pop(k, None)
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()

    st.caption(f"👤 Eingeloggt als: {_current_user_name() or '–'}")

def check_health(port: int, slug: str, timeout: float = 2.0):
    import time as _t, subprocess, shutil
    start = _t.perf_counter()
    ok_sys = False
    try:
        unit = {
            "metadatacreator": "se-metadatacreator.service",
            "redirectmapper":  "se-redirectmapper.service",
            "linkchecker":     "se-linkchecker.service",
            "contentgapper":   "se-contentgapper.service",
        }.get(slug)
        if unit and shutil.which("systemctl"):
            out = subprocess.check_output(["systemctl","is-active",unit], text=True, timeout=1.5).strip()
            ok_sys = (out == "active")
    except Exception:
        ok_sys = False

    ok_http = False
    try:
        try:
            import requests
        except ImportError:
            # Streamlit-Fehler vermeiden, wenn requests nicht installiert ist
            if not st.session_state.get("_warn_requests_missing"):
                st.session_state["_warn_requests_missing"] = True
                st.warning("Das Paket 'requests' fehlt – Health-Checks nur teilweise verfügbar.")
            raise

        urls = [
            f"http://127.0.0.1:{port}/_stcore/health",
            f"http://127.0.0.1:{port}/healthz",
            f"http://127.0.0.1:{port}/",
        ]

        def _probe(url: str) -> int:
            try:
                r = requests.head(url, timeout=timeout, allow_redirects=False)
                if 200 <= r.status_code < 400:
                    return r.status_code
            except Exception:
                pass
            try:
                r = requests.get(url, timeout=timeout, allow_redirects=True)
                return r.status_code
            except Exception:
                return 0

        for url in urls:
            code = _probe(url)
            if 200 <= code < 400:
                ok_http = True
                break
    except Exception:
        ok_http = False
    ok = ok_sys or ok_http
    latency_ms = (_t.perf_counter() - start) * 1000.0
    return ok, latency_ms

def status_badge(is_up: bool, latency_ms: float) -> str:
    if is_up:
        color, label = "#22c55e", "UP"
    else:
        color, label = "#ef4444", "DOWN"
    latency = f"{latency_ms:.0f}ms" if latency_ms > 0 else "—"
    return f"""
    <span style="display:inline-flex;align-items:center;gap:.35rem;
        padding:.15rem .5rem;border-radius:999px;background:{color}1A;color:{color};
        font-weight:600;font-size:.85rem;">● {label} · {latency}</span>
    """

def tool_card(tool: Dict, base_href: str):
    slug = tool["slug"]; name = tool["name"]; desc = tool.get("desc","")
    emoji = tool.get("emoji","🧩"); port = tool["port"]; href = f"/{slug}/"
    up, lat = check_health(port, slug)
    with st.container(border=True):
        c1, c2 = st.columns([0.75, 0.25], vertical_alignment="center")
        with c1:
            st.markdown(f"### {emoji} [{name}]({href})", unsafe_allow_html=True)
            st.caption(desc)
        with c2:
            st.markdown(status_badge(up, lat), unsafe_allow_html=True)

st.title("🧰 Search Experience – Tools Hub")

with st.sidebar:
    st.header("🧰 Tools")
    TOOLS = [
        {"slug": "redirectmapper", "name": "RedirectMapper", "port": 8502, "emoji": "🗺️"},
        {"slug": "linkchecker", "name": "LinkChecker", "port": 8504, "emoji": "🔗"},
        {"slug": "metadatacreator", "name": "MetadataCreator", "port": 8505, "emoji": "✍️"},
        {"slug": "contentgapper", "name": "ContentGapper", "port": 8506, "emoji": "🎯"},
    ]
    for t in TOOLS:
        slug, name, emoji, port = t["slug"], t["name"], t["emoji"], t["port"]
        ok, lat = check_health(port, slug)
        color = "#22c55e" if ok else "#ef4444"
        label = "UP" if ok else "DOWN"
        href = f"/{slug}/"
        st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
padding:.35rem .5rem;border-radius:.5rem;">
  <div style="display:flex;align-items:center;gap:.35rem;">
    <span style="font-size:1rem;">{emoji}</span>
    <a href="{href}" style="text-decoration:none;font-weight:600;">{name}</a>
  </div>
  <span style="display:inline-flex;align-items:center;gap:.35rem;
  padding:.1rem .45rem;border-radius:999px;background:{color}1A;
  color:{color};font-weight:700;font-size:.78rem;">● {label}</span>
</div>
""", unsafe_allow_html=True)

BASE_HREF = ""
flt_tools = TOOLS
for i in range(0, len(flt_tools), 2):
    cols = st.columns(2)
    for j, tool in enumerate(flt_tools[i:i+2]):
        with cols[j]:
            tool_card(tool, base_href=BASE_HREF)
