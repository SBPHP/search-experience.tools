# -*- coding: utf-8 -*-
from typing import List, Tuple, Dict, Optional
import os, json, time, subprocess
import streamlit as st

# === AUTH_GUARD_FALLBACK_V1 ===
try:
    if not _se_is_logged_in():
        try:
            render_login
        except Exception:
            pass
        try:
            render_login()
        except Exception:
            st.markdown("### 🔐 Bitte einloggen")
            st.stop()
        st.stop()
except Exception:
    pass

try:
    import requests
except Exception:
    requests = None


# === SIDEBAR_LOGOUT_WIRE_V2 ===
try:
    if _se_is_logged_in():
        if st.sidebar.button("Logout", key="logout_btn"):
            _se_perform_logout()
    else:
        st.sidebar.caption("🚪 nicht eingeloggt")
except Exception:
    pass


# --- HIDE_MAIN_LOGOUT ---
try:
    _st_hide = st
    _st_hide.markdown("""
<style>
div.st-key-logout_btn_sidebar { display: none !important; }
</style>
""", unsafe_allow_html=True)
except Exception:
    pass


# === SIDEBAR_LOGOUT_V2 ===
import os as _os

def _extract_name(v):
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("display_name","name","username","user","email"):
            x = v.get(k)
            if isinstance(x, str) and x.strip():
                return x.strip()
    return ""

def _current_user_name():
    for k in ("display_name","name","user_name","username","user","email"):
        n = _extract_name(st.session_state.get(k))
        if n: return n
    for k in ("profile","account","user_info"):
        n = _extract_name(st.session_state.get(k))
        if n: return n
    _auth = (st.session_state.get("authenticator")
             or st.session_state.get("auth")
             or st.session_state.get("AUTHENTICATOR"))
    try:
        if _auth:
            for attr in ("display_name","user_name","name","username","user","email"):
                if hasattr(_auth, attr):
                    n = _extract_name(getattr(_auth, attr))
                    if n: return n
    except Exception:
        pass
    return ""

with st.sidebar:
    if _os.environ.get("SE_DEBUG_AUTH") == "1":
        st.caption("🔧 Auth-Debug aktiv")
        try:
            st.write({k: st.session_state.get(k) for k in sorted(st.session_state.keys())})
        except Exception:
            st.write(list(st.session_state.keys()))

    _auth = (st.session_state.get("authenticator")
             or st.session_state.get("auth")
             or st.session_state.get("AUTHENTICATOR"))

    used_native = False
    try:
        if _auth and hasattr(_auth, "logout"):
            _auth.logout("🚪 Logout", "sidebar", key="sidebar_logout_btn_v2_native")
            used_native = True
    except Exception:
        used_native = False

    if not used_native:
        if st.button("🚪 Logout", key="sidebar_logout_btn_v2_fallback", use_container_width=True):
            try:
                if _auth and getattr(_auth, "cookie_manager", None):
                    cname = getattr(_auth, "cookie_name", None) or getattr(_auth, "_cookie_name", None)
                    if cname:
                        _auth.cookie_manager.delete(cname)
            except Exception:
                pass
            for k in ("authentication_status","authed","username","user","email","name",
                      "display_name","user_name","roles"):
                st.session_state.pop(k, None)
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()

    _nm = _current_user_name()
    st.caption(f"👤 Eingeloggt als: {_nm or '–'}")

# === /SIDEBAR_LOGOUT_V2 ===


if "live_status_on" not in st.session_state: st.session_state["live_status_on"] = False
live = st.session_state["live_status_on"]

def filter_tools(tools_list):
    roles = st.session_state.get("user_roles") or set()
    allowed = st.session_state.get("allowed_tools")
    if isinstance(roles, (set, list)) and "admin" in roles:
        return tools_list
    if allowed == "*" or (isinstance(allowed, list) and "*" in allowed):
        return tools_list
    if not allowed:
        return tools_list
    keep = set(allowed if isinstance(allowed, list) else [allowed])
    return [t for t in tools_list if t.get("slug") in keep]


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
        import requests
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


# -----------------------------
# Streamlit Page Setup
# -----------------------------
st.set_page_config(page_title="Tools Hub", page_icon="🧰", layout="wide", initial_sidebar_state="expanded")
st.title("🧰 Search Experience – Tools Hub")

# --- Sidebar: Tools Übersicht ---
with st.sidebar:
    st.header("🧰 Tools")
    TOOLS = [
        {"slug": "redirectmapper", "name": "RedirectMapper", "port": 8502, "emoji": "🗺️"},
        {"slug": "linkchecker", "name": "LinkChecker", "port": 8504, "emoji": "🔗"},
        {"slug": "metadatacreator", "name": "MetadataCreator", "port": 8505, "emoji": "✍️"},
        {"slug": "contentgapper", "name": "ContentGapper", "port": 8506, "emoji": "🎯"},
    ]

    for t in TOOLS:
        slug = t["slug"]; name = t["name"]; emoji = t["emoji"]
        port = t["port"]
        ok, lat = check_health(port, slug)
        color = "#22c55e" if ok else "#ef4444"
        label = "UP" if ok else "DOWN"
        href = f"/{slug}/"

        st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;padding:.35rem .5rem;border-radius:.5rem;">
  <div style="display:flex;align-items:center;gap:.35rem;">
    <span style="font-size:1rem;">{emoji}</span>
    <a href="{href}" style="text-decoration:none;font-weight:600;">{name}</a>
  </div>
  <span style="display:inline-flex;align-items:center;gap:.35rem;padding:.1rem .45rem;border-radius:999px;background:{color}1A;color:{color};font-weight:700;font-size:.78rem;">● {label}</span>
</div>
""", unsafe_allow_html=True)

# --- Main Grid ---
BASE_HREF = ""

flt_tools = TOOLS
for i in range(0, len(flt_tools), 2):
    cols = st.columns(2)
    for j, tool in enumerate(flt_tools[i:i+2]):
        with cols[j]:
            tool_card(tool, base_href=BASE_HREF)

st.markdown("---")
st.markdown("### ℹ️ Hinweise")
st.markdown(
    "- Root der Domain zeigt auf den Hub.\n"
    "- Die Tools liegen jetzt direkt unter `/<slug>/` statt `/tools/<slug>/`.\n"
)