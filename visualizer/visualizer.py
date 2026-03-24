import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

# Configuracion inicial

CSV_PATH        = Path(os.getenv("INPUT_CSV", "./data/words.csv"))
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "5"))
TOP_N           = int(os.getenv("TOP_N", "10"))


st.set_page_config(
    page_title="Word Miner — Ranking",
    page_icon="📊",
    layout="wide",
)

st.title("Ranking de palabras en nombres de funciones")
st.caption(f"Fuente: `{CSV_PATH}` — actualizando cada {REFRESH_SECONDS}s")


# Lectura y procesamiento del CSV

def load_rankings(path: Path, top_n: int) -> dict[str, pd.DataFrame]:

    if not path.exists():
        return {}

    try:
        df = pd.read_csv(path)
    except Exception:
        return {}

    if df.empty or "word" not in df.columns or "language" not in df.columns:
        return {}

    rankings = {}
    for lang in df["language"].unique():
        subset = df[df["language"] == lang]
        counts = (
            subset["word"]
            .value_counts()
            .head(top_n)
            .reset_index()
        )
        counts.columns = ["word", "count"]
        counts.insert(0, "rank", range(1, len(counts) + 1))
        rankings[lang] = counts

    return rankings


def load_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}

    return {
        "total_words":  len(df),
        "unique_words": df["word"].nunique() if "word" in df.columns else 0,
        "total_repos":  df["repo"].nunique() if "repo" in df.columns else 0,
        "languages":    df["language"].value_counts().to_dict() if "language" in df.columns else {},
    }


# Interfaz
summary = load_summary(CSV_PATH)

if not summary:
    st.warning(f"No se encontró el archivo `{CSV_PATH}`. Inicia el miner primero.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total palabras",   f"{summary['total_words']:,}")
    col2.metric("Palabras únicas",  f"{summary['unique_words']:,}")
    col3.metric("Repositorios",     f"{summary['total_repos']:,}")

    st.divider()

    # Tablas por lenguaje
    rankings = load_rankings(CSV_PATH, TOP_N)

    if not rankings:
        st.info("El CSV existe pero aún no tiene datos suficientes.")
    else:
        cols = st.columns(len(rankings))
        for col, (lang, df) in zip(cols, rankings.items()):
            with col:
                total_lang = summary["languages"].get(lang, 0)
                st.subheader(f"{lang.capitalize()}")
                st.caption(f"{total_lang:,} palabras registradas")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "rank":  st.column_config.NumberColumn("#",     width="small"),
                        "word":  st.column_config.TextColumn("Palabra", width="medium"),
                        "count": st.column_config.NumberColumn("Conteo",width="small"),
                    },
                )

# Pie de pagina con timestamp y refresco
st.divider()
st.caption(f"Última actualización: {time.strftime('%H:%M:%S')}")

time.sleep(REFRESH_SECONDS)
st.rerun()
