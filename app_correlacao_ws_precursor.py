import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

st.set_page_config(page_title="Mapa Precursores ↔ Weak Signals", layout="wide")

st.title("🔎 Mapeamento Tríplice: Precursores (HTO) ↔ Weak Signals")
st.caption("Carrega a planilha consolidada `mapeamento_triplice_WS_PREC.xlsx` e permite explorar relações por precursor.")

# ======= Sidebar / Entrada de dados =======
st.sidebar.header("📄 Dados")
#uploaded = st.sidebar.file_uploader("Selecione o arquivo `mapeamento_triplice_WS_PREC.xlsx`", type=["xlsx"])

# URLs dos arquivos no GitHub
uploaded = "https://raw.githubusercontent.com/titetodesco/CorrelacaoWS-PREC/main/mapeamento_triplce_WS_PREC.xlsx"
if uploaded is None:
    st.info("Faça upload da planilha consolidada para iniciar.")
    st.stop()

# Tente detectar a aba automaticamente
try:
    xls = pd.ExcelFile(uploaded)
    sheet_options = xls.sheet_names
    sheet = st.sidebar.selectbox("Aba", options=sheet_options, index=0)
    df = pd.read_excel(xls, sheet_name=sheet)
except Exception as e:
    st.error(f"Erro ao ler planilha: {e}")
    st.stop()

# Esperado: colunas criadas no bloco 'Triple_map' (ou equivalente)
# ["Report","Unit","Page","Text","Top_WS","Top_Precursores","Evidencia"]
expected = {"Report","Text","Top_WS","Top_Precursores"}
if not expected.issubset(set(df.columns)):
    st.error(f"A planilha não contém as colunas mínimas {expected}. Verifique o arquivo gerado.")
    st.stop()

# ======= Helpers p/ parsing =======
import re

def parse_ws_list(s: str):
    if not isinstance(s, str) or not s.strip():
        return []
    out = []
    for part in s.split(";"):
        t = part.strip()
        if not t:
            continue
        m = re.match(r"(.+?)\s*\(([-+]?\d*\.?\d+)\)\s*$", t)
        if m:
            name = m.group(1).strip()
            try:
                score = float(m.group(2))
            except:
                score = np.nan
            out.append((name, score))
        else:
            out.append((t, np.nan))
    return out

def parse_prec_list(s: str):
    if not isinstance(s, str) or not s.strip():
        return []
    out = []
    for part in s.split(";"):
        t = part.strip()
        if not t:
            continue
        m = re.match(r"(.+?)\s*\[([^\]]+)\]\s*\(([-+]?\d*\.?\d+)\)\s*$", t)
        if m:
            name = m.group(1).strip()
            hto  = m.group(2).strip()
            try:
                score = float(m.group(3))
            except:
                score = np.nan
            out.append((name, hto, score))
        else:
            m2 = re.match(r"(.+?)\s*\[([^\]]+)\]\s*(?:\(([-+]?\d*\.?\d+)\))?\s*$", t)
            if m2:
                name = m2.group(1).strip()
                hto  = m2.group(2).strip()
                score = float(m2.group(3)) if m2.group(3) else np.nan
                out.append((name, hto, score))
            else:
                out.append((t, "", np.nan))
    return out

# Explodir pares (cartesiano) por linha do texto
def explode_pairs(df_in: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df_in.iterrows():
        ws_list = parse_ws_list(r.get("Top_WS",""))
        prec_list = parse_prec_list(r.get("Top_Precursores",""))
        if not ws_list or not prec_list:
            continue
        for ws_name, ws_sim in ws_list:
            for prec_name, hto, prec_sim in prec_list:
                rows.append({
                    "Report": r.get("Report"),
                    "Unit": r.get("Unit"),
                    "Page": r.get("Page"),
                    "Text": r.get("Text"),
                    "WeakSignal": ws_name,
                    "WS_Similarity": ws_sim,
                    "Precursor": prec_name,
                    "HTO": hto,
                    "Precursor_Similarity": prec_sim,
                    "Evidencia": r.get("Evidencia","")
                })
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=False)
def build_pairs(df_in):
    return explode_pairs(df_in)

pairs = build_pairs(df)

if pairs.empty:
    st.warning("Não foram encontrados pares (Top_WS x Top_Precursores). Verifique a planilha.")
    st.stop()

# ======= Filtros globais =======
st.sidebar.header("🎚️ Filtros")
only_evidence = st.sidebar.checkbox("Somente evidência dupla (texto com WS e Precursor)", value=False)
min_ws = st.sidebar.slider("Similaridade mínima (Weak Signal)", 0.0, 0.9, 0.50, 0.05)
min_prec = st.sidebar.slider("Similaridade mínima (Precursor)", 0.0, 0.9, 0.50, 0.05)

df_filt = pairs.copy()
if only_evidence:
    df_filt = df_filt[df_filt["Evidencia"].astype(str).str.len() > 0]
df_filt = df_filt[df_filt["WS_Similarity"].fillna(0) >= float(min_ws)]
df_filt = df_filt[df_filt["Precursor_Similarity"].fillna(0) >= float(min_prec)]

# ======= Seletor de precursor =======
opts = (df_filt[["HTO","Precursor"]]
        .drop_duplicates()
        .sort_values(["HTO","Precursor"]))
opts["label"] = opts["HTO"] + " — " + opts["Precursor"]

if opts.empty:
    st.warning("Nenhum (HTO, Precursor) disponível com os filtros atuais.")
    st.stop()

choice = st.selectbox("Escolha o Precursor (HTO — Precursor)", options=opts["label"].tolist(), index=0)
sel_ht, sel_prec = choice.split(" — ", 1)

# ======= Agregação (para o precursor escolhido) =======
df_prec = (df_filt[(df_filt["HTO"]==sel_ht) & (df_filt["Precursor"]==sel_prec)]
           .groupby(["HTO","Precursor","WeakSignal"], as_index=False)
           .agg(Frequencia=("Text","nunique"),
                WS_Sim_med=("WS_Similarity","mean"),
                WS_Sim_max=("WS_Similarity","max"),
                Prec_Sim_med=("Precursor_Similarity","mean"),
                Prec_Sim_max=("Precursor_Similarity","max"),
                Reports=("Report", lambda s: ", ".join(sorted(set(map(str,s)))[:10])))
           .sort_values(["Frequencia","WS_Sim_max","Prec_Sim_max"], ascending=[False,False,False])
)

col1, col2 = st.columns([2,1], vertical_alignment="top")
with col1:
    st.subheader(f"Sinais fracos associados a: {sel_ht} — {sel_prec}")
    if df_prec.empty:
        st.info("Sem sinais para este precursor com os filtros atuais.")
    else:
        # Gráfico de barras (frequência)
        fig = px.bar(
            df_prec.sort_values("Frequencia", ascending=True),
            x="Frequencia", y="WeakSignal", orientation="h",
            title="Frequência por Weak Signal",
            hover_data=["WS_Sim_med","WS_Sim_max","Prec_Sim_med","Prec_Sim_max"]
        )
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")

with col2:
    # Pequeno heatmap opcional (similaridade média WS x frequência)
    if not df_prec.empty:
        top_n = st.number_input("Top-N para Heatmap", 5, 50, 15, 1)
        df_hm = df_prec.head(int(top_n)).copy()
        if not df_hm.empty:
            st.caption("Heatmap (freq x sim. média WS)")
            # normalizar para visual
            df_hm["WS_Sim_med_norm"] = (df_hm["WS_Sim_med"] - df_hm["WS_Sim_med"].min()) / max(1e-9, (df_hm["WS_Sim_med"].max() - df_hm["WS_Sim_med"].min()))
            fig2 = px.imshow(
                np.array([df_hm["Frequencia"].tolist(), (100*df_hm["WS_Sim_med"]).tolist()]),
                labels=dict(x="WeakSignal (Top-N)", y="Métrica", color="Valor"),
                x=df_hm["WeakSignal"].tolist(),
                y=["Frequência", "WS_sim (%)"]
            )
            st.plotly_chart(fig2, use_container_width=True, theme="streamlit")

st.divider()
st.subheader("Tabela detalhada (pares)")

st.dataframe(df_prec, use_container_width=True)

# Download do recorte atual (precursor)
def to_excel_bytes(df_in: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df_in.to_excel(writer, sheet_name="dados", index=False)
    bio.seek(0)
    return bio.read()

st.download_button(
    "📥 Baixar Excel (precursor filtrado)",
    data=to_excel_bytes(df_prec),
    file_name=f"{sel_ht}_{sel_prec}_weak_signals.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption("Dica: ajuste os sliders de similaridade para reduzir ruído ou focar em correlações mais fortes.")
