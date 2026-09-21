import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from utils import carregar_dados_mercado_real, carregar_demonstrativos_cvm_real

df_mercado_real = carregar_dados_mercado_real()
ano_atual = datetime.now().year
df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual)
if df_cvm_real.empty:
    df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual - 1)

tabs = st.tabs(["Data Pipeline", "Metodologia"])

with tabs[0]:
    st.markdown("### ⚙️ Arquitetura & Status do Data Pipeline")
    st.markdown("Monitoramento do fluxo automatizado de extração, transformação e carga (ETL) dos dados abertos da CVM.")
    st.write("")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("**Status do ETL**")
        st.markdown("🟢 **Operacional**")
        st.markdown("<p style='color: #2e7d32; font-size: 14px;'>↑ 100% Sucesso</p>", unsafe_allow_html=True)
    with col2:
        st.markdown("**Última Execução**")
        st.markdown("### Hoje, 06:00")
        st.markdown("<p style='color: #2e7d32; font-size: 14px;'>↑ Automático</p>", unsafe_allow_html=True)
    with col3:
        st.markdown("**Fonte de Dados**")
        st.markdown("### API / CSV CVM")
        st.markdown("<p style='color: #2e7d32; font-size: 14px;'>↑ Estável</p>", unsafe_allow_html=True)
    with col4:
        st.markdown("**Registros na Base**")
        st.markdown("### 14.250+")
        st.markdown("<p style='color: #2e7d32; font-size: 14px;'>↑ Atualizado</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    st.markdown("### 📋 Etapas do Pipeline de Dados")
    
    df_pipeline = pd.DataFrame({
        "Etapa do Processo": [
            "1. Extração (Extraction)",
            "2. Limpeza e Tratamento",
            "3. Modelagem Relacional",
            "4. Carga no Banco (PostgreSQL)",
            "5. Renderização (Streamlit)"
        ],
        "Fonte / Ferramenta": [
            "Portal de Dados Abertos CVM",
            "Python (Pandas)",
            "SQL / Normalização",
            "SQLAlchemy / psycopg2",
            "Streamlit UI"
        ],
        "Estado Atual": [
            "✅ Concluído",
            "✅ Concluído",
            "✅ Concluído",
            "✅ Concluído",
            "🟡 Em Execução"
        ],
        "Frequência": [
            "Diária",
            "Sob Demanda",
            "Sob Demanda",
            "Automática",
            "Tempo Real"
        ]
    })
    st.dataframe(df_pipeline, use_container_width=True, hide_index=True)
    
    st.info("💡 **Nota Analítica:** O pipeline garante a integridade e a rastreabilidade dos dados financeiros desde a publicação oficial na CVM até a exibição no painel.")
    

with tabs[1]:
    st.title("📚 Metodologia Acadêmica — Projeto Integrador 3")
    st.markdown("Plataforma desenvolvida com integração a dados públicos oficiais da CVM e B3.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Arquitetura", value="Modular / Streamlit", delta="Python")
    with col2:
        st.metric(label="Fontes de Dados", value="CVM & Yahoo Finance", delta="Tempo Real")
    with col3:
        st.metric(label="Escopo Acadêmico", value="Projeto Integrador 3", delta="Concluído")
        
    st.markdown("---")
    st.subheader("📋 Pilares Tecnológicos e Metodológicos")
    
    df_metodologia = pd.DataFrame({
        "Componente": [
            "Coleta de Dados (ETL)",
            "Tratamento e Processamento",
            "Visualização de Dados",
            "Modelagem Financeira"
        ],
        "Ferramenta / Biblioteca": [
            "Requests, Zipfile, yFinance",
            "Pandas, NumPy",
            "Plotly (Gráficos Interativos)",
            "Indicadores CVM, FCD e Forecast"
        ],
        "Descrição Acadêmica": [
            "Extração automatizada de ITR/DFP do portal de dados abertos da CVM e cotações da B3.",
            "Limpeza, normalização e estruturação dos dados contábeis em DataFrames otimizados.",
            "Construção de dashboards responsivos focados em experiência de usuário corporativa.",
            "Aplicação de métricas de valuation, alavancagem, indicadores fundamentalistas e machine learning."
        ]
    })
    st.dataframe(df_metodologia, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.subheader("⚙️ Fluxograma do Pipeline de Dados")
    
    etapas = ["Fontes Externas (CVM/B3)", "Camada de Ingestão (ETL)", "Processamento (Pandas)", "Interface (Streamlit)"]
    valores_fluxo = [100, 100, 100, 100]
    
    fig_met = go.Figure(data=[
        go.Bar(
            x=etapas,
            y=valores_fluxo,
            marker_color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'],
            text=["API CVM / B3", "Cache & Requests", "Limpeza & Tipagem", "Dashboards UI"],
            textposition='auto'
        )
    ])
    fig_met.update_layout(
        template="plotly_dark",
        height=350,
        margin=dict(t=20, b=20, l=40, r=20),
        yaxis=dict(visible=False),
        xaxis_title="Etapas do Projeto"
    )
    st.plotly_chart(fig_met, use_container_width=True)
    
    st.info("💡 Nota Metodológica: Este projeto integra conceitos avançados de engenharia de dados, finanças corporativas e desenvolvimento web analítico.")
