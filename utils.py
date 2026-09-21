import pandas as pd
import streamlit as st
import yfinance as yf
import requests
import zipfile
import io
from datetime import datetime

@st.cache_data(ttl=300) 
def carregar_dados_mercado_real(ticker="HYPE3.SA", periodo="1y"):
    """Busca cotações reais, volume e variações atualizadas via Yahoo Finance (B3)."""
    try:
        ativo = yf.Ticker(ticker)
        df = ativo.history(period=periodo)
        if df.empty:
            return pd.DataFrame()
        return df.reset_index()
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=86400) 
def carregar_demonstrativos_cvm_real(ano):
    """Baixa e processa dados reais de ITR/DFP (Demonstrações Financeiras) do portal da CVM em tempo real."""
    url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                nome_arquivo = f"itr_cia_aberta_DRE_con_{ano}.csv"
                if nome_arquivo in z.namelist():
                    with z.open(nome_arquivo) as f:
                        df = pd.read_csv(f, sep=';', encoding='ISO-8859-1')
                        df_hypera = df[df['CD_CVM'] == 21431].copy()
                        return df_hypera
    except Exception as e:
        pass
    return pd.DataFrame()

def injetar_css():
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');

            html, body, [class*="css"]  {
                font-family: 'Outfit', sans-serif;
            }

            header[data-testid="stHeader"] {
                background: rgba(0,0,0,0);
            }
            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
            }

            /* Sidebar Gradient */
            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0e1117 0%, #171b26 100%);
                border-right: 1px solid rgba(255,255,255,0.05);
            }

            /* Glassmorphism Metrics */
            div[data-testid="stMetric"] {
                background-color: rgba(26, 31, 43, 0.65);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                padding: 15px 20px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.3);
                backdrop-filter: blur(10px);
                transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
            }

            div[data-testid="stMetric"]:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.5);
                border-color: rgba(0, 210, 255, 0.5);
            }

            div[data-testid="stMetricValue"] {
                white-space: normal !important;
                word-break: break-word !important;
                overflow-wrap: break-word !important;
            }
            
            div[data-testid="stMetricValue"] > div {
                white-space: normal !important;
                word-wrap: break-word !important;
                text-overflow: clip !important;
                overflow: visible !important;
                font-size: clamp(1.2rem, 3vw, 1.8rem) !important;
                font-weight: 600;
                line-height: 1.3;
                color: #e2e8f0;
            }

            div[data-testid="stMetricLabel"] {
                font-size: clamp(0.85rem, 1.5vw, 0.95rem) !important;
                color: #a0aec0;
                font-weight: 400;
                white-space: normal !important;
            }
            
            div[data-testid="stMetricDelta"] > div {
                white-space: normal !important;
                font-size: clamp(0.8rem, 1.2vw, 1rem) !important;
            }

            /* Botões Modernos e Suaves */
            div.stButton > button {
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.1);
                background: linear-gradient(90deg, #1e2530 0%, #293240 100%);
                transition: all 0.3s ease;
                font-weight: 600;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }

            div.stButton > button:hover {
                border-color: #00d2ff;
                box-shadow: 0 0 10px rgba(0, 210, 255, 0.4);
                transform: translateY(-2px);
                color: #ffffff;
            }
            
            /* Tabs Style */
            button[data-baseweb="tab"] {
                font-size: 1.1rem;
                font-family: 'Outfit', sans-serif;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
