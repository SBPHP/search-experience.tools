# -*- coding: utf-8 -*-
# Topical Authority Checker (Service-Account Variante, kein OAuth-Login nötig)

import datetime
import base64
import json
import re
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_tags import st_tags
import nltk
from nltk.corpus import stopwords

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# -----------------------------
# Grund-Setup
# -----------------------------
st.set_page_config(
    page_title="Topical Authority (Service Account)",
    page_icon=":weight_lifter:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("Topical Authority of a GSC Property (Service Account)")
st.caption("Runs headless via Google Service Account – no user login required.")
st.divider()

# NLTK Stopwords (wird nur einmal geladen)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

STOP_WORDS = set(stopwords.words('english')) | set(stopwords.words('german'))
RE_ALLOWED = re.compile(r"[^A-Za-z0-9 '’äöüßÄÖÜ]+")

SEARCH_TYPES = ["web", "image", "video", "news", "discover", "googleNews"]
DATE_RANGE_OPTIONS = [
    "Last 7 Days", "Last 30 Days", "Last 3 Months",
    "Last 6 Months", "Last 12 Months", "Last 16 Months"
]
BASE_DIMENSIONS = ["page", "query", "country", "date"]
MAX_ROWS = 250_000
DF_PREVIEW_ROWS = 100

# -----------------------------
# Service Account Auth
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def get_sc_service_from_sa():
    """
    """
    sa = st.secrets.get("service_account", {})
    if not sa:
        raise RuntimeError("Missing [service_account] in secrets.toml (json oder path).")
    if "json" in sa:
        info = json.loads(sa["json"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif "path" in sa:
        creds = Credentials.from_service_account_file(sa["path"], scopes=SCOPES)
    else:
        raise RuntimeError("service_account must provide 'json' or 'path'.")
    # cache_discovery=False verhindert alte Discovery-Caches
    return build("webmasters", "v3", credentials=creds, cache_discovery=False)

def list_gsc_properties_via_sa(service):
    site_list = service.sites().list().execute() or {}
    return [s["siteUrl"] for s in site_list.get("siteEntry", [])]

def gsc_query_df(service, site_url: str,
                 start_date: str, end_date: str,
                 dimensions: list[str], row_limit: int = 25000) -> pd.DataFrame:
    """
    Ruft GSC Search Analytics via Service-Account ab und gibt ein DataFrame zurück.
    """
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit
    }
    resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute() or {}
    rows = resp.get("rows", [])
    data = []
    for r in rows:
        entry = {dim: r.get("keys", [None]*len(dimensions))[i] for i, dim in enumerate(dimensions)}
        entry.update({
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0.0),
            "position": r.get("position", 0.0),
        })
        data.append(entry)
    return pd.DataFrame(data)

# -----------------------------
# UI / Helpers
# -----------------------------
def calc_date_range(selection: str):
    range_map = {
        'Last 7 Days': 7, 'Last 30 Days': 30, 'Last 3 Months': 90,
        'Last 6 Months': 180, 'Last 12 Months': 365, 'Last 16 Months': 480
    }
    today = datetime.date.today()
    return today - datetime.timedelta(days=range_map.get(selection, 7)), today

def update_dimensions() -> list[str]:
    # Für Topical-Checks sind i.d.R. query/page/date relevant
    return BASE_DIMENSIONS

def show_dataframe(df: pd.DataFrame, title: str = "Preview the First 100 Rows"):
    with st.expander(title):
        st.dataframe(df.head(DF_PREVIEW_ROWS), use_container_width=True)

def download_csv_link(df: pd.DataFrame, filename: str):
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    b64 = base64.b64encode(csv.encode()).decode()
    st.markdown(
        f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download {filename}</a>',
        unsafe_allow_html=True
    )

# -----------------------------
# N-gram Verarbeitung
# -----------------------------
def process_ngrams(df: pd.DataFrame, n: int, min_occurrences: int = 1) -> pd.DataFrame:
    if df.empty or "query" not in df.columns:
        return pd.DataFrame(columns=["Ngram", "Occurrences", "Total Clicks", "Unique Pages"])
    # Klicks robust in int wandeln
    df = df.copy()
    df["clicks"] = pd.to_numeric(df.get("clicks", 0), errors="coerce").fillna(0).astype(int)

    def clean_and_tokenize(q: str):
        q = RE_ALLOWED.sub("", str(q).lower())
        words = [w for w in q.split() if w and w not in STOP_WORDS]
        return [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]

    df["ngrams"] = df["query"].apply(clean_and_tokenize)
    ngrams_flat = [ng for sub in df["ngrams"] for ng in sub]
    counts = Counter(ngrams_flat)

    ngram_clicks: dict[tuple, int] = {}
    ngram_pages: dict[tuple, set] = {}
    has_page = "page" in df.columns

    for _, row in df.iterrows():
        for ng in row["ngrams"]:
            if counts[ng] >= min_occurrences:
                ngram_clicks[ng] = ngram_clicks.get(ng, 0) + int(row["clicks"])
                if has_page:
                    s = ngram_pages.get(ng, set())
                    s.add(row.get("page"))
                    ngram_pages[ng] = s

    out = []
    for ng, cnt in counts.items():
        if cnt >= min_occurrences:
            clicks = ngram_clicks.get(ng, 0)
            label = " ".join(ng)
            if has_page:
                out.append([label, cnt, clicks, len(ngram_pages.get(ng, set()))])
            else:
                out.append([label, cnt, clicks, None])

    cols = ["Ngram", "Occurrences", "Total Clicks", "Unique Pages"]
    res = pd.DataFrame(out, columns=cols)
    return res.sort_values(by="Total Clicks", ascending=False)

def process_and_plot_ngrams(df: pd.DataFrame, n: int, min_occ: int = 1):
    ndf = process_ngrams(df, n, min_occ)
    fig = px.bar(ndf.head(10), x="Total Clicks", y="Ngram", title=f"Top 10 {n}-grams by Total Clicks")
    return ndf, fig

# -----------------------------
# MAIN
# -----------------------------
def main():
    # Sidebar: Property & Zeitraum
    svc = get_sc_service_from_sa()
    properties = list_gsc_properties_via_sa(svc)
    if not properties:
        st.error("No GSC properties found for this Service Account. "
                 "Bitte Service-Account als User in GSC hinzufügen (Settings → Users & permissions).")
        st.stop()

    with st.sidebar:
        site = st.selectbox("GSC Property", properties, index=0)
        date_range = st.selectbox("Date Range", DATE_RANGE_OPTIONS, index=1)  # Last 30 Days
        start_date, end_date = calc_date_range(date_range)
        st.write(f"**From:** {start_date}  **To:** {end_date}")

        dims = update_dimensions()
        st.caption("Dimensions (fest): " + ", ".join(dims))

        max_position = st.slider("Max Position (filter)", 1, 100, 100)
        min_clicks = st.number_input("Min Clicks (filter)", min_value=0, value=1)
        brand_keywords = st_tags(
            value=[], suggestions=[],
            label="Brand Keywords (exclude)",
            text="Enter keywords to exclude", maxtags=-1, key="brand_keywords"
        )

        fetch_btn = st.button("Fetch Data")

    if not fetch_btn:
        st.info("Set your parameters in the sidebar and click **Fetch Data**.")
        st.stop()

    with st.spinner("Fetching data from GSC..."):
        df = gsc_query_df(
            service=svc,
            site_url=site,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            dimensions=dims,
            row_limit=MAX_ROWS,
        )

    if df.empty:
        st.warning("No data returned for the selected period/dimensions.")
        st.stop()

    # Filter
    if "clicks" in df.columns:
        df = df[df["clicks"] >= min_clicks]
    if "position" in df.columns:
        df = df[df["position"] <= max_position]
    for kw in brand_keywords:
        if "query" in df.columns:
            df = df[~df["query"].str.contains(kw, case=False, na=False)]

    st.success(f"Fetched {len(df):,} rows.")
    show_dataframe(df, "Raw GSC Rows (preview)")
    download_csv_link(df, "gsc_rows.csv")

    # N-grams 1..4
    st.subheader("Topical N-grams")
    for n in range(1, 4 + 1):
        ndf, fig = process_and_plot_ngrams(df, n)
        st.plotly_chart(fig, use_container_width=True)
        with st.expander(f"{n}-grams (full table)"):
            st.dataframe(ndf, use_container_width=True)
        download_csv_link(ndf, f"ngrams_{n}.csv")

if __name__ == "__main__":
    main()