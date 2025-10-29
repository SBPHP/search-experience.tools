#!/usr/bin/env python3
# /opt/tools/hub/app.py

import time
import requests
import streamlit as st

# ---------- Seiteneinstellungen ----------
st.set_page_config(
    page_title="Tools Hub",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- KONFIG: Eure Tools ----------
# base = euer Base-Path, wie in Nginx + streamlit --server.baseUrlPath
TOOLS = [
    {
        "name": "RedirectMapper",
        "desc": "301/302-Redirects planen & prüfen",
        "emoji": "🔗",
        "port": 8501,
        "base": "/tools/redirectmapper/",
        "link": "/tools/redirectmapper/",
    },
    {
        "name": "LinkChecker",
        "desc": "Interne/Externe Links checken",
        "emoji": "🔍",
        "port": 8504,
        "base": "/tools/linkchecker/",
        "link": "/tools/linkchecker/",
    },
    {
        "name": "MetadataCreator",
        "desc": "Title, Meta-Description & H1 generieren",
        "emoji": "🧠",
        "port": 8505,
        "base": "/tools/metadatacreator/",
        "link": "/tools/metadatacreator/",
    },
    {
        "name": "ContentGapper",
        "desc": "Content-Gaps datengetrieben finden",
        "emoji": "📊",
        "port": 8506,
        "base": "/tools/contentgapper/",
        "link": "/tools/contentgapper/",
    },
]

# ---------- Styles ----------
st.markdown(
    """
    <style>
      .tool-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 16px;
        background: rgba(255,255,255,0.02);
        transition: border-color .15s ease, transform .1s ease, box-shadow .15s ease;
      }
      .tool-card:hover {
        border-color: rgba(255,255,255,0.22);
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(0,0,0,0.15);
      }
      .badge {
        display: inline-flex;
        align-items: center;
        gap: .45rem;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
      }
      .badge-up   { background: #0e4429; color: #2ee58c; border: 1px solid #1a7f4b; }
      .badge-warn { background: #3a2d09; color: #ffcc66; border: 1px solid #8f6b13; }
      .badge-down { background: #4d0f13; color: #ff7a7a; border: 1px solid #a81822; }

      .topbar {
        display: flex; justify-content: space-between; align-items: center;
        gap: 12px; margin-top: -14px; margin-bottom: 6px;
      }
      .topbar-right {
        display: flex; gap: 8px; align-items: center;
      }
      .tiny {
        font-size: 12px; opacity: .7;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill,minmax(280px,1fr));
        gap: 14px;
      }
      .muted {
        opacity:.8;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Healthcheck ----------
@st.cache_data(ttl=10)
def check_health(port: int, base_path: str) -> dict:
    """
    Prüft die Streamlit Health-Route der App intern.
    Erwartet base_path z.B. '/tools/linkchecker/'
    Health-URL wird dann: http://127.0.0.1:{port}/tools/linkchecker/_stcore/health
    """
    base = base_path if base_path.endswith("/") else base_path + "/"
    url = f"http://127.0.0.1:{port}{base}_stcore/health"
    t0 = time.time()
    try:
        r = requests.get(url, timeout=1.2)
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            if ms > 900:
                return {"status": "warn", "ms": ms, "detail": f"langsam ({ms} ms)"}
            return {"status": "up", "ms": ms, "detail": f"ok ({ms} ms)"}
        return {"status": "down", "ms": None, "detail": f"http {r.status_code}"}
    except requests.exceptions.Timeout:
        return {"status": "down", "ms": None, "detail": "timeout"}
    except Exception as e:
        return {"status": "down", "ms": None, "detail": str(e)}

STATUS_STYLE = {
    "up":   ("badge badge-up",   "● UP"),
    "warn": ("badge badge-warn", "● SLOW"),
    "down": ("badge badge-down", "● DOWN"),
}

# ---------- Kopfzeile ----------
colL, colR = st.columns([0.8, 0.2])
with colL:
    st.title("🧭 Tools Hub")
    st.caption("Zentrale Übersicht deiner Streamlit-Apps")

with colR:
    # Auto-Refresh (Meta Tag)
    with st.container():
        st.markdown("<div class='topbar-right'>", unsafe_allow_html=True)
        auto = st.toggle("Auto refresh", value=True)
        interval = st.selectbox("Intervall", [10, 20, 30, 60], index=0, key="refresh_iv", label_visibility="collapsed")
        if auto:
            st.markdown(f"<meta http-equiv='refresh' content='{interval}'>", unsafe_allow_html=True)
            st.markdown(f"<div class='tiny muted'>↻ alle {interval}s</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='tiny muted'>↻ aus</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# Manuelles Refresh der Health-Cachewerte
if st.button("Status aktualisieren"):
    check_health.clear()

# ---------- Globale Health-Zusammenfassung ----------
statuses = [check_health(t["port"], t["base"]) for t in TOOLS]
up_count = sum(1 for s in statuses if s["status"] == "up")
warn_count = sum(1 for s in statuses if s["status"] == "warn")
down_count = sum(1 for s in statuses if s["status"] == "down")

st.markdown(
    f"""
    <div class="topbar">
      <div></div>
      <div class="topbar-right">
        <span class="badge badge-up">✅ {up_count} up</span>
        <span class="badge badge-warn">⚠️ {warn_count} slow</span>
        <span class="badge badge-down">⛔ {down_count} down</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")

# ---------- Karten-Grid ----------
st.markdown("<div class='grid'>", unsafe_allow_html=True)

for tool, stat in zip(TOOLS, statuses):
    cls, label = STATUS_STYLE.get(stat["status"], STATUS_STYLE["down"])
    ms_text = f"{stat['ms']} ms" if stat["ms"] is not None else stat["detail"]

    st.markdown(
        f"""
        <div class="tool-card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <div style="font-size:22px; font-weight:700;">{tool['emoji']} {tool['name']}</div>
            <span class="{cls}">{label}</span>
          </div>
          <div class="muted" style="margin:.25rem 0 .75rem 0;">{tool['desc']}</div>
          <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
            <a href="{tool['link']}" target="_self">
              <button class="css-1x8cf1d edgvbvh3">Öffnen</button>
            </a>
            <span class="tiny muted">↔ Port {tool['port']} · {ms_text}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)
