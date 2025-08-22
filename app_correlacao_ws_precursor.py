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

TRIPLE_SHEET = "Triple_map"

try:
    # Lê somente a aba Triple_map
    df = pd.read_excel(uploaded, sheet_name=TRIPLE_SHEET)
except ValueError as e:
    st.error(f"Não encontrei a aba '{TRIPLE_SHEET}' no arquivo enviado. "
             f"Abra seu Excel e confirme que existe exatamente uma aba com este nome.")
    st.stop()
except Exception as e:
    st.error(f"Erro ao ler a planilha: {e}")
    st.stop()

# Validação mínima das colunas necessárias
required_cols = {"Report", "Text", "Top_WS", "Top_Precursores"}
missing = required_cols - set(df.columns)
if missing:
    st.error(f"A aba '{TRIPLE_SHEET}' não contém as colunas mínimas {missing}. "
             f"Verifique a geração do arquivo.")
    st.stop()

# Garante colunas opcionais para não quebrar o resto do app
for c in ["Unit", "Page", "Evidencia"]:
    if c not in df.columns:
        df[c] = np.nan

st.success(f"Aba '{TRIPLE_SHEET}' carregada com {len(df):,} linhas.")

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

# 🔽 NOVO: Filtro por frequência mínima do trio (HTO, Precursor, WeakSignal)
min_freq = st.sidebar.number_input(
    "Frequência mínima (nº de textos/relatórios)",
    min_value=1, max_value=100, value=1, step=1,
    help="Só mantém pares (HTO, Precursor, WeakSignal) com pelo menos esse nº de ocorrências."
)

st.sidebar.header("🧮 Rótulos de aresta")
show_edge_labels = st.sidebar.checkbox("Mostrar rótulo de força na aresta", value=False)
edge_label_metric = st.sidebar.selectbox(
    "Métrica do rótulo",
    ["Frequencia", "WS_Sim_med", "WS_Sim_max", "Prec_Sim_med", "Prec_Sim_max"],
    index=0,
    help="Qual valor imprimir na aresta Precursor ↔ WeakSignal"
)

df_filt = pairs.copy()
if only_evidence:
    df_filt = df_filt[df_filt["Evidencia"].astype(str).str.len() > 0]
df_filt = df_filt[df_filt["WS_Similarity"].fillna(0) >= float(min_ws)]
df_filt = df_filt[df_filt["Precursor_Similarity"].fillna(0) >= float(min_prec)]

# Depois de aplicar filtros globais em df_filt, monte um preview com frequência
preview = (df_filt
    .groupby(["HTO","Precursor","WeakSignal"], as_index=False)
    .agg(Frequencia=("Text","nunique"))
)
preview = preview[preview["Frequencia"] >= int(min_freq)]

opts = (preview[["HTO","Precursor"]]
        .drop_duplicates()
        .sort_values(["HTO","Precursor"]))
opts["label"] = opts["HTO"] + " — " + opts["Precursor"]


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

# 🔽 NOVO: mantém apenas sinais com Frequencia >= min_freq
df_prec = df_prec[df_prec["Frequencia"] >= int(min_freq)]

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

st.sidebar.header("⚙️ Física do grafo")
gravity = st.sidebar.slider("Gravidade (negativo = repulsa)", -20000, -500, -8000, 500)
spring_length = st.sidebar.slider("Comprimento da mola", 60, 300, 140, 10)
spring_const = st.sidebar.slider("Constante da mola", 0.01, 0.20, 0.03, 0.01)
damping = st.sidebar.slider("Damping", 0.60, 0.95, 0.85, 0.01)


st.divider()
st.subheader("Tabela detalhada (pares)")

# -----------------------------------------------------------
# ABA "Grafo" — Rede Precursor (HTO) ↔ WeakSignal (com filtros)
# -----------------------------------------------------------
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

st.subheader("🕸️ Grafo: Precursores (HTO) ↔ Weak Signals")

# 1) Agregar pares com os filtros globais aplicados
edges_df = (df_filt
    .groupby(["HTO","Precursor","WeakSignal"], as_index=False)
    .agg(Frequencia=("Text","nunique"),
         WS_Sim_med=("WS_Similarity","mean"),
         WS_Sim_max=("WS_Similarity","max"),
         Prec_Sim_med=("Precursor_Similarity","mean"),
         Prec_Sim_max=("Precursor_Similarity","max"),
         Reports=("Report", lambda s: ", ".join(sorted(set(map(str,s)))[:8])))
)

# 2) Aplicar corte pela frequência mínima
edges_df = edges_df[edges_df["Frequencia"] >= int(min_freq)].copy()

if edges_df.empty:
    st.info("Nenhuma aresta atende aos filtros atuais (verifique frequência mínima e limiares de similaridade).")
else:
    # 3) Construir grafo bipartido
    G = nx.Graph()

    # paleta por HTO (ajuste se desejar)
    HTO_COLORS = {
        "Humano": "#1f78b4",
        "Técnico": "#33a02c",
        "Tecnico": "#33a02c",     # caso venha sem acento
        "Organizacional": "#e31a1c",
        "Organizacinal": "#e31a1c"  # tolerância a typo comum
    }
    WS_COLOR = "#ff7f00"

    # graus acumulados para dimensionar nós
    freq_by_prec = edges_df.groupby(["HTO","Precursor"])["Frequencia"].sum().to_dict()
    freq_by_ws   = edges_df.groupby("WeakSignal")["Frequencia"].sum().to_dict()

    # 3a) Nós de Precursor (com HTO)
    for (hto, prec), freq_sum in freq_by_prec.items():
        color = HTO_COLORS.get(str(hto), "#6a3d9a")
        size = 10 + 3 * np.log1p(freq_sum)   # escala suave pelo log da frequência somada
        G.add_node(
            f"P::{hto}::{prec}",
            label=f"{prec} [{hto}]",
            title=f"<b>Precursor</b>: {prec}<br><b>HTO</b>: {hto}<br><b>Freq total</b>: {freq_sum}",
            color=color, shape="dot", size=float(size), group=str(hto), node_type="precursor"
        )

    # 3b) Nós de WeakSignal
    for ws, freq_sum in freq_by_ws.items():
        size = 8 + 3 * np.log1p(freq_sum)
        G.add_node(
            f"WS::{ws}",
            label=ws,
            title=f"<b>Weak Signal</b>: {ws}<br><b>Freq total</b>: {freq_sum}",
            color=WS_COLOR, shape="dot", size=float(size), group="WS", node_type="ws"
        )

    # 3c) Arestas (peso = frequência; tooltip com stats)
    for _, r in edges_df.iterrows():
        hto, prec, ws = r["HTO"], r["Precursor"], r["WeakSignal"]
        freq = int(r["Frequencia"])
        ws_med, ws_max = float(r["WS_Sim_med"]), float(r["WS_Sim_max"])
        pr_med, pr_max = float(r["Prec_Sim_med"]), float(r["Prec_Sim_max"])
    
        # defina SEMPRE o título antes de usar
        title = (
            f"{prec} [{hto}] ↔ {ws}\n"
            f"Frequência: {freq}\n"
            f"WS sim (média/máx): {ws_med:.2f} / {ws_max:.2f}\n"
            f"Prec sim (média/máx): {pr_med:.2f} / {pr_max:.2f}\n"
            f"Relatórios: {r.get('Reports', '')}"
        )
    
        # rótulo opcional na aresta
        edge_kwargs = {
            "value": freq,
            "title": title,
            "width": float(1 + np.log1p(freq)),
        }
        if show_edge_labels:
            val = r[edge_label_metric]
            edge_kwargs["label"] = (
                f"{val:.2f}" if isinstance(val, (float, np.floating)) else str(int(val))
                if isinstance(val, (int, np.integer)) else str(val)
            )
    
        G.add_edge(f"P::{hto}::{prec}", f"WS::{ws}", **edge_kwargs)

    # 4) Renderizar com PyVis e embutir no Streamlit
    net = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=False, notebook=False)
    net.barnes_hut(gravity=-2000, central_gravity=0.2, spring_length=120, spring_strength=0.045, damping=0.9)
    net.from_nx(G)

    # habilita physics e interação
    import json

    options = {
        "nodes": {
            "borderWidth": 1,
            "shadow": False
        },
        "edges": {
            "smooth": {"type": "dynamic", "roundness": 0.5},
            "color": {"opacity": 0.7}
        },
        "physics": {
            "enabled": True,
            "stabilization": {"iterations": 150},
            "barnesHut": {
                # use os sliders da sidebar aqui:
                "gravitationalConstant": int(gravity),
                "springLength": int(spring_length),
                "springConstant": float(spring_const),
                "damping": float(damping)
            }
        },
        "interaction": {
            "hover": True,
            "navigationButtons": True,
            "keyboard": True,
            "selectable": True,
            "multiselect": True,
            "zoomView": True
        }
    }
    
    net.set_options(json.dumps(options))


    
    # Renderizar
    #net.save_graph("graph.html")
    #st.components.v1.html(open("graph.html").read(), height=800, scrolling=True)

    # Renderizar apenas uma vez
    html_path = "graph_prec_ws.html"
    net.save_graph(html_path)
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    components.html(html, height=720, scrolling=True)


    # 5) Download das tabelas (arestas e nós)
    st.markdown("**Downloads (dados do grafo filtrado):**")
    colA, colB = st.columns(2)
    with colA:
        st.download_button(
            "📥 Arestas (CSV)",
            data=edges_df.to_csv(index=False).encode("utf-8"),
            file_name="edges_precursor_ws.csv",
            mime="text/csv"
        )
    # construir tabela de nós para download
    nodes_rows = []
    for nid, attrs in G.nodes(data=True):
        nodes_rows.append({
            "node_id": nid,
            "label": attrs.get("label",""),
            "group": attrs.get("group",""),
            "node_type": attrs.get("node_type",""),
            "size": attrs.get("size",""),
            "color": attrs.get("color","")
        })
    nodes_df = pd.DataFrame(nodes_rows)
    with colB:
        st.download_button(
            "📥 Nós (CSV)",
            data=nodes_df.to_csv(index=False).encode("utf-8"),
            file_name="nodes_precursor_ws.csv",
            mime="text/csv"
        )

    st.caption("Dica: ajuste os filtros (similaridade e frequência) na barra lateral para controlar a densidade do grafo.")

# =====================================
# 2) Grafo por Relatório (usando df_filt)
# =====================================
import json
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

st.divider()
st.subheader("🗂️ Grafo por Relatório")

# Relatórios disponíveis APÓS filtros globais (df_filt já filtrado por evidência, sim e etc.)
reports_available = sorted(df_filt["Report"].dropna().unique().tolist())
if not reports_available:
    st.info("Nenhum relatório disponível com os filtros atuais. Ajuste os filtros na barra lateral.")
else:
    sel_report = st.selectbox("Escolha o relatório", options=reports_available, index=0)
    df_rep = df_filt[df_filt["Report"] == sel_report].copy()

    if df_rep.empty:
        st.info("Este relatório não possui pares depois dos filtros aplicados. Tente reduzir os limiares ou a frequência mínima.")
    else:
        # -------- Agregações para dimensionar nós e arestas --------
        # Report -> Precursor
        r2p = (df_rep.groupby(["Report","HTO","Precursor"], as_index=False)
                      .agg(Freq=("Text","nunique"),
                           Prec_Sim_med=("Precursor_Similarity","mean"),
                           Prec_Sim_max=("Precursor_Similarity","max")))

        # Report -> WeakSignal
        r2ws = (df_rep.groupby(["Report","WeakSignal"], as_index=False)
                       .agg(Freq=("Text","nunique"),
                            WS_Sim_med=("WS_Similarity","mean"),
                            WS_Sim_max=("WS_Similarity","max")))

        # Precursor <-> WeakSignal dentro do relatório
        p2ws = (df_rep.groupby(["HTO","Precursor","WeakSignal"], as_index=False)
                       .agg(Freq=("Text","nunique"),
                            Prec_Sim_med=("Precursor_Similarity","mean"),
                            WS_Sim_med=("WS_Similarity","mean")))

        # Aplicar corte por frequência mínima (usa o mesmo min_freq da sidebar)
        r2p = r2p[r2p["Freq"] >= int(min_freq)]
        r2ws = r2ws[r2ws["Freq"] >= int(min_freq)]
        p2ws = p2ws[p2ws["Freq"] >= int(min_freq)]

        if r2p.empty and r2ws.empty:
            st.info("Sem nós/arestas para este relatório com a frequência mínima atual. Diminua o filtro de frequência.")
        else:
            # -------- Construir grafo --------
            G2 = nx.Graph()

            # Nó central do relatório
            rep_id = f"R::{sel_report}"
            G2.add_node(
                rep_id,
                label=sel_report,
                title=f"<b>Relatório</b>: {sel_report}",
                color="#2b7ce9",
                shape="star",
                size=25,
                node_type="report",
            )

            # Paleta HTO
            HTO_COLORS = {
                "Humano": "#1f78b4",
                "Técnico": "#33a02c", "Tecnico": "#33a02c",
                "Organizacional": "#e31a1c",
            }

            # Nós de Precursor + arestas Relatório→Precursor
            for _, r in r2p.iterrows():
                hto, prec, freq = r["HTO"], r["Precursor"], int(r["Freq"])
                p_id = f"P::{hto}::{prec}"
                size = 10 + 3 * np.log1p(freq)
                color = HTO_COLORS.get(str(hto), "#6a3d9a")

                G2.add_node(
                    p_id,
                    label=f"{prec} [{hto}]",
                    =(f"<b>Precursor</b>: {prec} [{hto}]<br>"
                           f"Frequência: {freq}<br>"
                           f"sim med/máx: {r['Prec_Sim_med']:.2f}/{r['Prec_Sim_max']:.2f}"),
                    color=color,
                    shape="dot",
                    size=float(size),
                    node_type="precursor",
                )

                edge_title = f"{sel_report} → {prec} [{hto}] (freq {freq})"
                G2.add_edge(rep_id, p_id, value=freq, width=float(1 + np.log1p(freq)), title=edge_title)

            # Nós de WeakSignal + arestas Relatório→WS
            for _, r in r2ws.iterrows():
                ws, freq = r["WeakSignal"], int(r["Freq"])
                ws_id = f"WS::{ws}"
                size = 8 + 3 * np.log1p(freq)

                G2.add_node(
                    ws_id,
                    label=ws,
                    title=(f"<b>Weak Signal</b>: {ws}<br>"
                           f"Frequência: {freq}<br>"
                           f"sim med/máx: {r['WS_Sim_med']:.2f}/{r['WS_Sim_max']:.2f}"),
                    color="#ff7f00",
                    shape="dot",
                    size=float(size),
                    node_type="ws",
                )

                edge_title = f"{sel_report} → {ws} (freq {freq})"
                G2.add_edge(rep_id, ws_id, value=freq, width=float(1 + np.log1p(freq)), title=edge_title)

            # (Opcional) Arestas Precursor ↔ WeakSignal dentro do relatório
            add_internal_links = st.checkbox(
                "Mostrar ligações Precursor ↔ Weak Signal dentro do relatório", value=True
            )
            if add_internal_links and not p2ws.empty:
                for _, r in p2ws.iterrows():
                    hto, prec, ws, freq = r["HTO"], r["Precursor"], r["WeakSignal"], int(r["Freq"])
                    p_id = f"P::{hto}::{prec}"
                    ws_id = f"WS::{ws}"
                    edge_title = (f"{prec} [{hto}] ↔ {ws}<br>"
                                  f"freq: {freq}<br>"
                                  f"WS_sim_med: {r['WS_Sim_med']:.2f} | "
                                  f"Prec_sim_med: {r['Prec_Sim_med']:.2f}")
                    G2.add_edge(p_id, ws_id, value=freq, width=float(1 + np.log1p(freq)), title=edge_title)

            # -------- Renderizar com PyVis --------
            net2 = Network(height="700px", width="100%", bgcolor="#ffffff", font_color="#222")
            net2.from_nx(G2)

            options2 = {
                "nodes": {"borderWidth": 1},
                "edges": {"smooth": {"type": "dynamic", "roundness": 0.5}, "color": {"opacity": 0.75}},
                "physics": {
                    "enabled": True,
                    "stabilization": {"iterations": 120},
                    "barnesHut": {
                        "gravitationalConstant": int(gravity),
                        "springLength": int(spring_length),
                        "springConstant": float(spring_const),
                        "damping": float(damping),
                    },
                },
                "interaction": {
                    "hover": True,
                    "navigationButtons": True,
                    "keyboard": True,
                    "selectable": True,
                    "multiselect": True,
                    "zoomView": True,
                },
            }
            net2.set_options(json.dumps(options2))

            html_path2 = "graph_report_view.html"
            net2.save_graph(html_path2)
            with open(html_path2, "r", encoding="utf-8") as f:
                html2 = f.read()
            components.html(html2, height=720, scrolling=True)


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
