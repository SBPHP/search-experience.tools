# -*- coding: utf-8 -*-
# AI Redirect Mapper – Streamlit App
# Per-side column selection (no more "common columns"), batch encoding, robust matching.

import base64
import numpy as np
import pandas as pd
import streamlit as st
from typing import Optional, List, Dict

import faiss
from sentence_transformers import SentenceTransformer
from huggingface_hub import HfFolder

st.set_page_config(
    page_title="AI Redirect Mapper",
    page_icon=":arrow_right_hook:",
    layout="wide",
)

# -------------------------------
# Settings
# -------------------------------
BATCH_SIZE = 64  # Batch size for fast & memory-efficient encodes

# -------------------------------
# Model (load once)
# -------------------------------
@st.cache_resource(show_spinner=True)
def load_model():
    # all-MiniLM-L6-v2 is small & cloud-friendly
    return SentenceTransformer("all-MiniLM-L6-v2")

model = load_model()

# -------------------------------
# Helpers
# -------------------------------
def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names: remove BOM, trim, convert multiple spaces to one."""
    df = df.copy()
    cleaned = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)  # remove BOM
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )
    df.columns = cleaned
    return df

def _guess_url_column(df: pd.DataFrame) -> Optional[str]:
    """Guess likely URL column (Address, URL, Url, url, address) or first column that looks like a URL."""
    candidates = ["Address", "URL", "Url", "url", "address", "Origin", "origin", "Destination", "destination"]
    for c in candidates:
        if c in df.columns:
            return c
    if len(df.columns) > 0:
        first = df.columns[0]
        try:
            is_urlish = df[first].astype(str).str.startswith(("http://", "https://", "/")).mean() > 0.5
        except Exception:
            is_urlish = False
        if is_urlish:
            return first
    return None

def _suggest_text_columns(df: pd.DataFrame) -> List[str]:
    """Suggest likely text columns (Title, Meta Description, H1, …) or fallback to the first non-URL column."""
    prefer = ["Title", "title", "Meta Description", "meta description", "H1", "h1", "Description", "description"]
    suggestions = [c for c in df.columns if c in prefer]
    if suggestions:
        return suggestions[:2]  # not too many defaults
    url_col = _guess_url_column(df)
    candidates = [c for c in df.columns if c != url_col]
    return candidates[:1] if candidates else list(df.columns[:1])

# -------------------------------
# Embedding / Encoding (Batch)
# -------------------------------
def encode_texts(
    df: pd.DataFrame,
    selected_columns: List[str],
    progress_bar: "st.runtime.scriptrunner.progress.ProgressBar",
    status_placeholder: "st.delta_generator.DeltaGenerator",
) -> np.ndarray:
    """Encodes texts using SentenceTransformer in batches. Updates Streamlit progress bar and status text."""
    df = df.copy()

    missing = [c for c in selected_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in DataFrame: {missing}")

    df["combined_text"] = df[selected_columns].apply(lambda row: " ".join(row.values.astype(str)), axis=1)
    texts: List[str] = df["combined_text"].astype(str).tolist()

    total = len(texts)
    if total == 0:
        return np.zeros((0, model.get_sentence_embedding_dimension()), dtype="float32")


    all_embeddings: List[np.ndarray] = []
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for bidx in range(0, total, BATCH_SIZE):
        batch_texts = texts[bidx : bidx + BATCH_SIZE]
        emb_batch = model.encode(
            batch_texts,
            batch_size=min(BATCH_SIZE, len(batch_texts)),
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=False,
        )
        all_embeddings.append(emb_batch.astype("float32"))

        done = min(bidx + len(batch_texts), total)
        progress_bar.progress(done / float(total))
        status_placeholder.write(f"Encoding batch {bidx // BATCH_SIZE + 1} / {total_batches} ({done}/{total})")


    status_placeholder.write("Encoding complete ✅")
    embeddings = np.vstack(all_embeddings).astype("float32")
    return embeddings

# -------------------------------
# UI Helpers
# -------------------------------
def show_dataframe(report: pd.DataFrame) -> None:
    """Shows a preview of the first 100 rows."""
    with st.expander("Preview the First 100 Rows"):
        st.dataframe(report.head(100), use_container_width=True)

def download_csv_link(report: pd.DataFrame) -> None:
    """Displays a download link for the report as CSV."""
    csv = report.to_csv(index=False, encoding="utf-8-sig")
    b64_csv = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64_csv}" download="redirect_mapping_results.csv">Download Results</a>'
    st.markdown(href, unsafe_allow_html=True)

# -------------------------------
# Main
# -------------------------------
def main():
    st.title("Use FAISS to find matching redirect URLs (semantic similarity)")

    with st.expander("Before using this tool 🚨", expanded=False):
        st.markdown(
            """
**Please Note:** Streamlit Cloud does not support long runtimes. For large mappings (+20k URLs), run locally.

#### 🐸 Data Preparation with Screaming Frog
1. Crawl both sites (origin & destination), filter to HTML 200.
2. Export CSVs with **Address/URL**, **Title**, **Meta Description**, etc.

### ⚠️ Instructions
1. Upload `origin.csv` & `destination.csv`.
2. Select **origin text columns** and **destination text columns** (they may have different names!).
3. Click **Match URLs**.
4. Download results.
            """
        )

    try:
        hf_token = str(st.secrets.get("installed", {}).get("hf_token", "")) or None
    except Exception:
        hf_token = None
    if hf_token:
        HfFolder.save_token(hf_token)

    origin_file = st.file_uploader("Upload the origin.csv file:", type="csv")
    destination_file = st.file_uploader("Upload the destination.csv file:", type="csv")


    if origin_file and destination_file:
        origin_df = pd.read_csv(origin_file)
        destination_df = pd.read_csv(destination_file)

        origin_df = _normalize_columns(origin_df)
        destination_df = _normalize_columns(destination_df)

        st.subheader("Select text columns for similarity")
        with st.columns(2)[0]:
            st.markdown("")
        with st.columns(2)[1]:
            st.markdown("")

        col1, col2 = st.columns(2, gap="large")
        with col1:
            origin_text_cols = st.multiselect(
                "Origin text columns:",
                options=list(origin_df.columns),
                default=_suggest_text_columns(origin_df),
                key="origin_text_cols",
            )
        with col2:
            destination_text_cols = st.multiselect(
                "Destination text columns:",
                options=list(destination_df.columns),
                default=_suggest_text_columns(destination_df),
                key="destination_text_cols",
            )

        st.subheader("Select URL columns for output")
        col3, col4 = st.columns(2, gap="large")
        with col3:
            origin_url_col = _guess_url_column(origin_df) or st.selectbox(
                "Origin URL column:", options=list(origin_df.columns), key="origin_url_col"
            )
        with col4:
            dest_url_col = _guess_url_column(destination_df) or st.selectbox(
                "Destination URL column:", options=list(destination_df.columns), key="dest_url_col"
            )

        if st.button("Match URLs"):
            if not origin_text_cols:
                st.error("Please select at least one origin text column.")
                return
            if not destination_text_cols:
                st.error("Please select at least one destination text column.")
                return
            if origin_url_col not in origin_df.columns:
                st.error("Selected origin URL column not found.")
                return
            if dest_url_col not in destination_df.columns:
                st.error("Selected destination URL column not found.")
                return

            progress_bar_origin = st.progress(0.0)
            status_origin = st.empty()

            progress_bar_destination = st.progress(0.0)
            status_destination = st.empty()

            try:
                origin_embeddings = encode_texts(origin_df, origin_text_cols, progress_bar_origin, status_origin)
                st.write("Encoding of origin texts is complete.")
            except Exception as e:
                st.error(f"Failed to encode origin: {e}")
                return

            progress_bar_destination.progress(0.0)
            try:
                destination_embeddings = encode_texts(destination_df, destination_text_cols, progress_bar_destination, status_destination)
                st.write("Encoding of destination texts is complete.")
            except Exception as e:
                st.error(f"Failed to encode destination: {e}")
                return

            if destination_embeddings.size == 0 or origin_embeddings.size == 0:
                st.error("Embeddings are empty. Please check your input data and selected columns.")
                return

            dimension = destination_embeddings.shape[1]
            faiss_index = faiss.IndexFlatL2(dimension)
            faiss_index.add(destination_embeddings.astype("float32"))

            distances, indices = faiss_index.search(origin_embeddings.astype("float32"), k=1)
            flattened_indices = indices.flatten()

            d_max = float(np.max(distances)) if distances.size else 0.0
            if d_max == 0.0:
                similarity_scores = np.ones_like(distances, dtype="float32")
            else:
                similarity_scores = 1.0 - (distances / d_max)

            matched_urls = destination_df[dest_url_col].iloc[flattened_indices].values

            report = pd.DataFrame({
                "origin_url": origin_df[origin_url_col],
                "matched_url": matched_urls,
                "similarity_score": similarity_scores.flatten(),
            })

            show_dataframe(report)
            download_csv_link(report)

    else:
        st.info("Please upload your origin.csv and destination.csv file to start the redirect mapping.")


if __name__ == "__main__":
    main()

