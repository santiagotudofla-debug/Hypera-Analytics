import streamlit as st
from utils import injetar_css

st.set_page_config(
    page_title="Hypera Analytics — HYPE3",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

injetar_css()

st.sidebar.title("📊 Hypera Analytics")
st.sidebar.markdown("**HYPE3** — Inteligência Financeira (Dados Reais CVM & B3)")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Atualizar Dados Agora"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info(
    "**Aviso Legal:** Plataforma integrada com fontes públicas oficiais (CVM, B3 e Relatórios de Sustentabilidade) em tempo real."
)

p1 = st.Page("pages/1_Visao_Corporativa.py", title="Visão Corporativa", icon="🌍")
p2 = st.Page("pages/2_Desempenho_Financeiro.py", title="Desempenho Financeiro", icon="💰")
p3 = st.Page("pages/3_Inteligencia_e_Risco.py", title="Inteligência & Risco", icon="🔎")
p4 = st.Page("pages/4_Hypera_AI_Analyst.py", title="Hypera AI Analyst", icon="🧠")
p5 = st.Page("pages/5_Metodologia.py", title="Metodologia", icon="📚")

pg = st.navigation([p1, p2, p3, p4, p5])
pg.run()
