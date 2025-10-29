import streamlit as st
import pandas as pd
from anthropic import Anthropic
from openai import OpenAI
from groq import Groq
import google.generativeai as genai
import re
import time
import advertools as adv

# -------------------------------
# Constants (Updated 2025-10-18)
# -------------------------------
ANTHROPIC_MODELS = [
    "claude-sonnet-4.5",   # balanced, top quality
    "claude-haiku-4.5",    # fast & cheap
    "claude-opus-4.1",     # deep reasoning
]

OPENAI_MODELS = [
    "gpt-4.1",             # top-tier
    "gpt-4.1-mini",        # cost-effective & fast
]

GOOGLE_MODELS = [
    "gemini-2.5-flash",    # strong general model
    "gemini-2.0-flash-lite",
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

MODELS = GOOGLE_MODELS + ANTHROPIC_MODELS + OPENAI_MODELS + GROQ_MODELS

LANGUAGES = [
    'German', 'English', 'Spanish', 'French', 'Italian', 'Dutch', 'Polish', 'Russian', 'Turkish',
    'Arabic', 'Chinese', 'Japanese', 'Korean', 'Vietnamese', 'Indonesian', 'Hindi', 'Bengali',
    'Urdu', 'Malay', 'Thai', 'Burmese', 'Cambodian', 'Amharic', 'Swahili', 'Hausa', 'Yoruba',
    'Igbo', 'Oromo', 'Tigrinya', 'Afar', 'Somali', 'Ethiopian', 'Tajik', 'Pashto', 'Persian',
    'Uzbek', 'Kazakh', 'Kyrgyz', 'Turkmen', 'Azerbaijani', 'Armenian', 'Georgian', 'Moldovan'
]

MAX_TOKENS_TITLE = 16
MAX_TOKENS_META_DESCRIPTION = 44
MAX_TOKENS_H1 = 17
TEMPERATURE = 0.7

# -------------------------------
# Session State
# -------------------------------
def init_session_state():
    if 'confirmed_preview' not in st.session_state:
        st.session_state.confirmed_preview = False

# -------------------------------
# Streamlit App Configuration
# -------------------------------
def setup_streamlit():
    st.set_page_config(
        page_title="AI Meta Data Optimizer & Creator",
        page_icon="🤖",
        layout="wide"
    )
    st.title("🤖 Optimize & create your SEO Meta Data with LLMs")
    st.write("This tool creates a new Title Tag, Meta Description and H1 based on your existing ones. "
             "If you don't have any yet, the tool will create its own.")
    st.write("You only have to enter URLs and the matching keywords.")
    st.divider()

# -------------------------------
# Helper Functions
# -------------------------------
def text_to_df(text, column_name):
    items = [item.strip() for item in re.split(r',|\n', text) if item.strip()]
    df = pd.DataFrame(items, columns=[column_name])
    return df

def show_dataframe(df):
    with st.expander("Preview the First 100 Rows"):
        st.dataframe(df.head(100))

def handle_api_keys():
    model = st.selectbox("Choose a model:", MODELS, help=(
        "Pick a provider/model. Groq ist schnell & günstig; OpenAI/Anthropic top Qualität; "
        "Gemini 2.5 ist stark und kosteneffizient."
    ))
    client = None

    if model in GROQ_MODELS:
        api_key = st.text_input('Enter your Groq API Key:', type="password",
                                value=st.secrets.get("groq", {}).get("api_key", ""))
        if api_key:
            client = Groq(api_key=api_key)

    elif model in ANTHROPIC_MODELS:
        api_key = st.text_input('Enter your Anthropic API Key:', type="password")
        if api_key:
            client = Anthropic(api_key=api_key)

    elif model in OPENAI_MODELS:
        api_key = st.text_input('Enter your OpenAI API Key:', type="password")
        if api_key:
            client = OpenAI(api_key=api_key)

    elif model in GOOGLE_MODELS:
        api_key = st.text_input('Enter your Google AI Studio API Key:', type="password")
        if api_key:
            genai.configure(api_key=api_key)
            client = genai

    return client, model

def download_dataframe(df):
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download Your new Meta-Data as CSV",
        data=csv,
        file_name='meta-data.csv',
        mime='text/csv',
    )

def generate_content(client, model, text, language, meta_type):
    # Token-Limits nach Meta-Typ
    meta_type_norm = meta_type.lower()
    if meta_type_norm == 'title tag':
        max_tokens = MAX_TOKENS_TITLE
    elif meta_type_norm == 'meta description':
        max_tokens = MAX_TOKENS_META_DESCRIPTION
    else:
        max_tokens = MAX_TOKENS_H1

    prompt = f"""
You are a specialized assistant trained to craft the optimal {meta_type} for SEO in {language}. Produce content that is:
- Human-like, unique, concise, keyword-optimized
- Engaging with varied CTAs; avoid boilerplate
- Front-load the most important words

Input may contain Title, Meta Description, H1 and a target keyword. If any are None/missing, create new copy based on what's available.

Respond only with the new {meta_type} (no quotes, no brackets, no '{meta_type}:'). Output must be in {language}.
Limit strictly to {max_tokens} tokens. For product pages include salient product details to improve relevance.
""".strip()

    # Anthropic
    if model in ANTHROPIC_MODELS:
        while True:
            try:
                resp = client.messages.create(
                    model=model,
                    system=prompt,
                    max_tokens=max_tokens,
                    temperature=TEMPERATURE,
                    messages=[{"role": "user", "content": text}]
                )
                return resp.content[0].text.strip()
            except Exception as e:
                print(f"Anthropic error: {e}. Retrying in 7 seconds...")
                time.sleep(7)

    # Google Gemini
    if model in GOOGLE_MODELS:
        while True:
            try:
                gmodel = client.GenerativeModel(model_name=model, system_instruction=prompt)
                resp = gmodel.generate_content(text)
                return (getattr(resp, "text", "") or "").strip()
            except Exception as e:
                print(f"Gemini error: {e}. Retrying in 7 seconds...")
                time.sleep(7)

    # OpenAI / Groq (OpenAI-kompatibles chat.completions)
    while True:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI/Groq error: {e}. Retrying in 7 seconds...")
            time.sleep(7)

def clean_up_string(s):
    if not isinstance(s, str):
        return s  # leave non-strings as-is
    cleaned = s.replace('@@', '\n')
    elements = [elem.strip() for elem in cleaned.split('\n') if elem.strip()]
    return ' '.join(elements)

def analyze_urls(dataframe, client, model, language, meta_data_to_change):
    # Progress UI
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Crawl URLs
    open('crawl_file.jl', 'w').close()
    adv.crawl(dataframe['url'], 'crawl_file.jl', follow_links=False)
    crawl_df = pd.read_json('crawl_file.jl', lines=True)

    # Clean/ensure columns
    columns_to_clean = ['title', 'meta_desc', 'h1', 'h2']
    for col in columns_to_clean:
        if col not in crawl_df.columns:
            crawl_df[col] = None
    crawl_df[columns_to_clean] = crawl_df[columns_to_clean].applymap(clean_up_string)

    # Merge input with crawl (left join to keep all input URLs)
    df = pd.merge(
        dataframe,
        crawl_df[["url", "title", "meta_desc", "h1", "status"]],
        on=["url"],
        how="left"
    )

    results = []
    total_rows = len(df)

    for index, row in df.iterrows():
        url = row['url']
        keyword = row['keyword']
        status = row.get('status', None)

        if status != 200:
            title = meta_description = h1 = None
        else:
            title = row.get('title')
            meta_description = row.get('meta_desc')
            h1 = row.get('h1')

        combined_text = f"Title: {title}\nMeta Description: {meta_description}\nH1: {h1}\nKeyword: {keyword}"

        new_title = new_meta_description = new_h1 = None
        if 'Title Tag' in meta_data_to_change:
            new_title = generate_content(client, model, combined_text, language, 'title tag')
        if 'Meta Description' in meta_data_to_change:
            new_meta_description = generate_content(client, model, combined_text, language, 'meta description')
        if 'H1' in meta_data_to_change:
            new_h1 = generate_content(client, model, combined_text, language, 'h1')

        results.append({
            "url": url,
            "new title": new_title,
            "new meta_desc": new_meta_description,
            "new h1": new_h1
        })

        progress = (index + 1) / total_rows
        progress_bar.progress(progress)
        status_text.text(f"Processing row {index + 1} of {total_rows}")

    return pd.DataFrame(results)

# -------------------------------
# Main
# -------------------------------
def main():
    setup_streamlit()
    init_session_state()  # Initialize session state

    # Inputs
    urls_text = st.text_area("Enter URLs 🔗 (separated by commas or line breaks):")
    keywords_text = st.text_area("Enter Keywords 🔑 (separated by commas or line breaks):")

    # Convert to DataFrames
    urls_df = text_to_df(urls_text, 'url')
    keywords_df = text_to_df(keywords_text, 'keyword')

    # Validate counts
    if len(urls_df) != len(keywords_df):
        st.error("The number of URLs does not match the number of keywords. "
                 "Please ensure that each URL has a corresponding keyword.")
        return

    # Merge
    df = pd.merge(urls_df, keywords_df, left_index=True, right_index=True)

    if not df.empty:
        st.write('Preview of the first 100 rows of your data, please make sure that it matches as intended.')
        st.dataframe(df.head(100))

        if st.button("Confirm Preview"):
            st.session_state.confirmed_preview = True

        if st.session_state.confirmed_preview:
            # Model + API Key
            client, model = handle_api_keys()
            st.write('If you are unsure which model you should choose, hover over the ❔ on the right to get some help.')

            # Language selection
            language = st.selectbox("Choose a language 🌐 for the Meta Data:", LANGUAGES)

            # What to change
            meta_data_to_change = st.multiselect(
                "Select which meta data you want to change:",
                options=['Title Tag', 'Meta Description', 'H1'],
                default=['Title Tag', 'Meta Description', 'H1']
            )

            # Generate
            if st.button("Generate Meta Data"):
                if client is None:
                    st.error("Please enter a valid API key for the selected model.")
                    return

                new_df = analyze_urls(df, client, model, language, meta_data_to_change)
                show_dataframe(new_df)
                download_dataframe(new_df)
    else:
        st.error("It looks like your text input is empty, please fill in both text fields")

if __name__ == "__main__":
    main()
