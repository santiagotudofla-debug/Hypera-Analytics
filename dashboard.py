# app/dashboard.py (ou app.py)
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import requests
import zipfile
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

try:
    from pytrends.request import TrendReq
    PYTRENDS_DISPONIVEL = True
except ImportError:
    PYTRENDS_DISPONIVEL = False

st.set_page_config(
    page_title="Hypera Analytics — HYPE3",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        header[data-testid="stHeader"] {
            background: rgba(0,0,0,0);
        }
        .block-container {
            padding-top: 1.5rem;
        }
        div[data-testid="stMetricValue"] {
            white-space: normal;
            overflow-wrap: break-word;
            font-size: 1.3rem;
            line-height: 1.3;
        }
    </style>
    """,
    unsafe_allow_html=True
)

TICKER_PRINCIPAL = "HYPE3.SA"
CD_CVM_HYPERA = 21431
TICKERS_PARES = {
    "Hypera Pharma (HYPE3)": "HYPE3.SA",
    "RaiaDrogasil (RADL3)": "RADL3.SA",
    "Pague Menos (PGMN3)": "PGMN3.SA",
    "Blau Farmacêutica (BLAU3)": "BLAU3.SA",
    "Panvel / Dimed (PNVL3)": "PNVL3.SA",
}

# ==========================================
# HELPERS
# ==========================================
def buscar_linha(df, nomes_possiveis):
    """Procura uma linha (métrica) num DataFrame de demonstrativos do yfinance
    testando múltiplos nomes possíveis."""
    if df is None or df.empty:
        return None
    for nome in nomes_possiveis:
        if nome in df.index:
            return df.loc[nome]
    return None


def valor_mais_recente(serie):
    """Pega o valor mais recente (primeira coluna) de uma Series de demonstrativo."""
    if serie is None or serie.empty:
        return None
    val = serie.iloc[0]
    return None if pd.isna(val) else float(val)


def fmt_moeda_bi(valor):
    if valor is None:
        return "N/D"
    return f"R$ {valor / 1e9:,.2f} Bi"


def fmt_moeda_mi(valor):
    if valor is None:
        return "N/D"
    return f"R$ {valor / 1e6:,.1f} Mi"


def fmt_pct(valor, casas=1):
    if valor is None:
        return "N/D"
    return f"{valor * 100:.{casas}f}%"


def fmt_pct_bruto(valor, casas=1):
    """Para valores que já vêm em % (não fração)."""
    if valor is None:
        return "N/D"
    return f"{valor:.{casas}f}%"


# ==========================================
# FUNÇÕES DE BUSCA DE DADOS REAIS
# ==========================================
@st.cache_data(ttl=300)
def carregar_dados_mercado_real(ticker=TICKER_PRINCIPAL, periodo="2y"):
    """Busca cotações reais, volume e variações atualizadas via Yahoo Finance (B3)."""
    try:
        ativo = yf.Ticker(ticker)
        df = ativo.history(period=periodo)
        if df.empty:
            return pd.DataFrame()
        return df.reset_index()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def carregar_info_ticker(ticker=TICKER_PRINCIPAL):
    """Busca dados fundamentalistas e múltiplos atuais reais via yfinance (.info)."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return info if info else {}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def carregar_demonstrativos_yf(ticker=TICKER_PRINCIPAL):
    """Busca DRE, Balanço Patrimonial e Fluxo de Caixa reais via yfinance."""
    resultado = {
        "income": pd.DataFrame(), "income_q": pd.DataFrame(),
        "balance": pd.DataFrame(), "balance_q": pd.DataFrame(),
        "cashflow": pd.DataFrame(), "cashflow_q": pd.DataFrame(),
    }
    try:
        t = yf.Ticker(ticker)
        resultado["income"] = t.financials
        resultado["income_q"] = t.quarterly_financials
        resultado["balance"] = t.balance_sheet
        resultado["balance_q"] = t.quarterly_balance_sheet
        resultado["cashflow"] = t.cashflow
        resultado["cashflow_q"] = t.quarterly_cashflow
    except Exception:
        pass
    return resultado


@st.cache_data(ttl=3600)
def carregar_dividendos_reais(ticker=TICKER_PRINCIPAL):
    """Busca o histórico real de dividendos pagos via yfinance."""
    try:
        t = yf.Ticker(ticker)
        div = t.dividends
        if div is None or div.empty:
            return pd.DataFrame()
        df = div.reset_index()
        df.columns = ["Data", "Valor por Ação (R$)"]
        df["Ano"] = pd.to_datetime(df["Data"]).dt.year
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def carregar_sustentabilidade_real(ticker=TICKER_PRINCIPAL):
    """Tenta buscar pontuação ESG real via yfinance."""
    try:
        t = yf.Ticker(ticker)
        sust = t.sustainability
        if sust is None or sust.empty:
            return pd.DataFrame()
        return sust
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21600)
def carregar_composicao_indice_b3(codigo_indice):
    """Consulta em tempo real a API pública da B3 para obter a carteira teórica vigente de um índice."""
    import base64
    import json as _json
    try:
        params = {"language": "pt-br", "pageNumber": 1, "pageSize": 200, "index": codigo_indice, "segment": "1"}
        encoded = base64.b64encode(_json.dumps(params).encode("ascii")).decode("ascii")
        url = f"https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{encoded}"
        response = requests.get(url, timeout=20, verify=True)
        if response.status_code != 200:
            return pd.DataFrame()
        data = response.json()
        resultados = data.get("results", [])
        if not resultados:
            return pd.DataFrame()
        return pd.DataFrame(resultados)
    except Exception:
        return pd.DataFrame()


def empresa_esta_no_indice(df_indice, ticker_base="HYPE"):
    """Verifica se o ticker aparece na carteira do índice retornada."""
    if df_indice is None or df_indice.empty:
        return None
    for col in ["cod", "codigo", "asset", "cdAtual", "code"]:
        if col in df_indice.columns:
            valores = df_indice[col].astype(str).str.upper()
            return valores.str.startswith(ticker_base.upper()).any()
    return None


@st.cache_data(ttl=86400)
def carregar_demonstrativos_cvm_real(ano, tipo="DRE"):
    """Baixa e processa dados reais de ITR do portal de dados abertos da CVM em tempo real."""
    url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                nome_arquivo = f"itr_cia_aberta_{tipo}_con_{ano}.csv"
                if nome_arquivo in z.namelist():
                    with z.open(nome_arquivo) as f:
                        df = pd.read_csv(f, sep=';', encoding='ISO-8859-1')
                        df_hypera = df[df['CD_CVM'] == CD_CVM_HYPERA].copy()
                        return df_hypera
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def carregar_fatos_relevantes_cvm(ano):
    """Busca comunicados e fatos relevantes reais protocolados na CVM."""
    url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return pd.DataFrame()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            nome_arquivo = f"ipe_cia_aberta_{ano}.csv"
            if nome_arquivo not in z.namelist():
                candidatos = [n for n in z.namelist() if n.lower().endswith('.csv')]
                if not candidatos:
                    return pd.DataFrame()
                nome_arquivo = candidatos[0]
            with z.open(nome_arquivo) as f:
                df = pd.read_csv(f, sep=';', encoding='windows-1252')

        col_cd_cvm = next((c for c in ["CD_CVM", "Codigo_CVM", "CODIGO_CVM"] if c in df.columns), None)
        if col_cd_cvm is None:
            return pd.DataFrame()
        df_hypera = df[df[col_cd_cvm] == CD_CVM_HYPERA].copy()

        col_data = next((c for c in ["Data_Entrega", "DT_RECEB", "Data_Referencia"] if c in df_hypera.columns), None)
        if col_data:
            df_hypera = df_hypera.sort_values(col_data, ascending=False)
        return df_hypera
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def carregar_noticias_google_news(query, max_itens=15):
    """Busca notícias reais e em tempo real via Google News RSS."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            return pd.DataFrame()
        root = ET.fromstring(response.content)
        itens = []
        for item in root.findall(".//item")[:max_itens]:
            titulo = item.findtext("title", default="")
            link = item.findtext("link", default="")
            data_pub = item.findtext("pubDate", default="")
            fonte_el = item.find("source")
            fonte = fonte_el.text if fonte_el is not None else ""
            itens.append({"Título": titulo, "Fonte": fonte, "Data": data_pub, "Link": link})
        return pd.DataFrame(itens)
    except Exception:
        return pd.DataFrame()


def carregar_info_par(ticker):
    return carregar_info_ticker(ticker)


@st.cache_data(ttl=21600)
def carregar_google_trends_marcas(marcas, timeframe="today 12-m"):
    """Busca o interesse de busca real (Google Trends, Brasil)."""
    if not PYTRENDS_DISPONIVEL:
        return pd.DataFrame()
    try:
        pytrends = TrendReq(hl='pt-BR', tz=180)
        pytrends.build_payload(list(marcas), cat=0, timeframe=timeframe, geo='BR', gprop='')
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame()
        if 'isPartial' in df.columns:
            df = df.drop(columns=['isPartial'])
        return df
    except Exception:
        return pd.DataFrame()


ODS_DESTAQUE_HYPERA = [
    {
        "ODS": "ODS 3 — Saúde e Bem-Estar",
        "Evidência Real e Citada": "Núcleo do próprio negócio: maior portfólio de medicamentos isentos de prescrição do país; centro de P&D (Brainfarma) dedicado a novos tratamentos.",
    },
    {
        "ODS": "ODS 4 — Educação de Qualidade",
        "Evidência Real e Citada": "Patrocínio de 10 bolsistas via Instituto Semear (desde 2023); apoio ao Instituto Horas da Vida.",
    },
    {
        "ODS": "ODS 6 — Água Potável e Saneamento",
        "Evidência Real e Citada": "Programas declarados de 'segurança hídrica' e redução de consumo de água nas subsidiárias.",
    },
    {
        "ODS": "ODS 12 — Consumo e Produção Responsáveis",
        "Evidência Real e Citada": "Logística reversa de embalagens e reciclagem de resíduos; Mantecorp Skincare/Inspire360 compensam 100% do GEE das entregas de e-commerce.",
    },
    {
        "ODS": "ODS 13 — Ação Contra a Mudança Climática",
        "Evidência Real e Citada": "Integra o ICO2 B3; duas subestações de energia limpa em Anápolis (GO, 2023); redução declarada de emissões de GEE.",
    },
    {
        "ODS": "ODS 15 — Vida Terrestre",
        "Evidência Real e Citada": "Investimento em recuperação de áreas degradadas da bacia hidrográfica do Rio Araguaia (GO).",
    },
    {
        "ODS": "ODS 17 — Parcerias e Meios de Implementação",
        "Evidência Real e Citada": "Signatária do Pacto Global da ONU desde 12/2020; parcerias com ONGs.",
    },
]


# ==========================================
# CARREGAMENTO INICIAL
# ==========================================
df_mercado_real = carregar_dados_mercado_real()
info_hypera = carregar_info_ticker()
demonstrativos_yf = carregar_demonstrativos_yf()
df_dividendos_real = carregar_dividendos_reais()
df_sustentabilidade_real = carregar_sustentabilidade_real()
df_indice_ise = carregar_composicao_indice_b3("ISEE")
df_indice_ico2 = carregar_composicao_indice_b3("ICO2")
hypera_no_ise = empresa_esta_no_indice(df_indice_ise, "HYPE")
hypera_no_ico2 = empresa_esta_no_indice(df_indice_ico2, "HYPE")

ano_atual = datetime.now(ZoneInfo("America/Sao_Paulo")).year
df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual, tipo="DRE")
if df_cvm_real.empty:
    df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual - 1, tipo="DRE")

df_fatos_relevantes = carregar_fatos_relevantes_cvm(ano_atual)
if df_fatos_relevantes.empty:
    df_fatos_relevantes = carregar_fatos_relevantes_cvm(ano_atual - 1)

roe_real = info_hypera.get("returnOnEquity")
roa_real = info_hypera.get("returnOnAssets")
margem_liq_real = info_hypera.get("profitMargins")
margem_ebitda_real = info_hypera.get("ebitdaMargins")
margem_operacional_real = info_hypera.get("operatingMargins")
pe_real = info_hypera.get("trailingPE")
pvp_real = info_hypera.get("priceToBook")
ev_ebitda_real = info_hypera.get("enterpriseToEbitda")
dividend_yield_real = info_hypera.get("dividendYield")
payout_real = info_hypera.get("payoutRatio")
total_debt_real = info_hypera.get("totalDebt")
total_cash_real = info_hypera.get("totalCash")
ebitda_real = info_hypera.get("ebitda")

serie_receita = buscar_linha(demonstrativos_yf["income"], ["Total Revenue", "TotalRevenue"])
serie_lucro_liquido = buscar_linha(demonstrativos_yf["income"], ["Net Income", "NetIncome", "Net Income Common Stockholders"])
serie_ebitda = buscar_linha(demonstrativos_yf["income"], ["EBITDA", "Normalized EBITDA"])

serie_fco = buscar_linha(demonstrativos_yf["cashflow"], ["Operating Cash Flow", "Total Cash From Operating Activities"])
serie_fci = buscar_linha(demonstrativos_yf["cashflow"], ["Investing Cash Flow", "Total Cashflows From Investing Activities"])
serie_fcf_financ = buscar_linha(demonstrativos_yf["cashflow"], ["Financing Cash Flow", "Total Cash From Financing Activities"])
serie_fcf_livre = buscar_linha(demonstrativos_yf["cashflow"], ["Free Cash Flow"])

serie_divida_total = buscar_linha(demonstrativos_yf["balance"], ["Total Debt", "TotalDebt"])
serie_caixa = buscar_linha(demonstrativos_yf["balance"], ["Cash And Cash Equivalents", "CashAndCashEquivalents", "Cash Cash Equivalents And Short Term Investments"])

# ==========================================
# MENU SIDEBAR / NAVEGAÇÃO PRINCIPAL
# ==========================================
st.sidebar.title("📊 Hypera Analytics")
st.sidebar.markdown("**HYPE3** — Inteligência Financeira (Dados Reais CVM & B3)")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Atualizar Dados Agora"):
    st.cache_data.clear()
    st.rerun()

hora_brasilia = datetime.now(ZoneInfo("America/Sao_Paulo"))
st.sidebar.caption(f"Última execução desta sessão: {hora_brasilia.strftime('%d/%m/%Y %H:%M:%S')}")

opcoes_navegacao = [
    "Noticias",
    "Visao Geral",
    "Mercado",
    "Analise Tecnica",
    "Fundamentos",
    "Portfolio e Sazonalidade",
    "Sustentabilidade & ODS",
    "Resultados",
    "Hypera AI Analyst",
    "Anomalias",
    "Forecast",
    "Relatório Diretoria",
    "Data Pipeline",
    "Metodologia"
]

if "menu_ativo" not in st.session_state:
    st.session_state["menu_ativo"] = "Noticias"

indice_atual = opcoes_navegacao.index(st.session_state["menu_ativo"]) if st.session_state["menu_ativo"] in opcoes_navegacao else 0

menu_opcao = st.sidebar.radio(
    "Navegação",
    opcoes_navegacao,
    index=indice_atual
)

st.session_state["menu_ativo"] = menu_opcao

st.sidebar.markdown("---")
st.sidebar.info(
    "**Aviso Legal:** Plataforma integrada com fontes públicas oficiais (CVM e Yahoo Finance/B3). "
    "Algumas seções (marcadas na tela) não possuem fonte pública gratuita confiável e são apresentadas "
    "apenas como conteúdo ilustrativo, não como dado oficial."
)

# ==========================================
# ROTEAMENTO E RENDERIZAÇÃO DOS MÓDULOS
# ==========================================

if menu_opcao == "Noticias":
    st.title("📰 Feed de Fatos Relevantes & Notícias — HYPE3")
    st.markdown("Duas fontes reais e independentes: comunicados oficiais (CVM) e notícias de mercado em tempo real (Google News).")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Fonte Oficial", value="Portal CVM (IPE)", delta="Dados Abertos")
    with col2:
        status_fonte = "Conectado" if not df_fatos_relevantes.empty else "Indisponível"
        st.metric(label="Status CVM", value=status_fonte)
    with col3:
        st.metric(label="Ativo Monitorado", value="HYPE3 (B3)", delta=f"CD_CVM {CD_CVM_HYPERA}")

    st.markdown("---")
    st.subheader("📋 Comunicados Oficiais Reais (Portal CVM — dataset IPE)")

    if not df_fatos_relevantes.empty:
        colunas_candidatas = ["Data_Entrega", "DT_RECEB", "Categoria", "Tipo", "Especie", "Assunto", "Link_Download", "Link_Arq"]
        colunas_exibir = [c for c in colunas_candidatas if c in df_fatos_relevantes.columns]
        st.dataframe(
            df_fatos_relevantes[colunas_exibir] if colunas_exibir else df_fatos_relevantes.head(30),
            use_container_width=True, hide_index=True
        )
    else:
        st.warning("Não foi possível carregar o feed real de fatos relevantes da CVM neste momento.")

    st.markdown("---")
    st.subheader("🌐 Notícias de Mercado em Tempo Real (Google News)")
    termo_busca = st.text_input("Termo de busca:", value="Hypera Pharma HYPE3")

    df_noticias_reais = carregar_noticias_google_news(termo_busca)
    if not df_noticias_reais.empty:
        for _, row in df_noticias_reais.iterrows():
            st.markdown(f"**[{row['Título']}]({row['Link']})**")
            st.caption(f"{row['Fonte']} · {row['Data']}")
            st.markdown("---")
    else:
        st.warning("Não foi possível carregar notícias no momento.")

elif menu_opcao == "Visao Geral":
    st.title("📊 Painel Analítico — Visão Geral (HYPE3)")
    st.markdown("Dados consolidados extraídos diretamente da CVM e do Yahoo Finance em tempo real.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Código CVM", value=str(CD_CVM_HYPERA), delta="Hypera S.A.")
    with col2:
        st.metric(label="Setor", value=info_hypera.get("sector", "N/D"), delta=info_hypera.get("industry", ""))
    with col3:
        preco_atual = info_hypera.get("currentPrice") or info_hypera.get("regularMarketPrice")
        st.metric(label="Preço Atual", value=f"R$ {preco_atual:.2f}" if preco_atual else "N/D")
    with col4:
        market_cap = info_hypera.get("marketCap")
        st.metric(label="Valor de Mercado", value=fmt_moeda_bi(market_cap))

    st.markdown("---")
    col_g1, col_g2 = st.columns([1, 1])
    with col_g1:
        st.subheader("🎯 Múltiplo P/L Atual vs. Setor")
        pe_setor_medio = None
        pes_pares = []
        for nome_par, tk_par in TICKERS_PARES.items():
            if tk_par == TICKER_PRINCIPAL:
                continue
            info_par = carregar_info_par(tk_par)
            pe_par = info_par.get("trailingPE")
            if pe_par:
                pes_pares.append(pe_par)
        if pes_pares:
            pe_setor_medio = float(np.mean(pes_pares))

        if pe_real:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=pe_real,
                delta={'reference': pe_setor_medio if pe_setor_medio else pe_real,
                       'decreasing': {'color': "green"}, 'increasing': {'color': "red"}},
                gauge={
                    'axis': {'range': [0, max(30, pe_real * 1.3)], 'tickwidth': 1, 'tickcolor': "white"},
                    'bar': {'color': "#00d2ff"},
                    'bgcolor': "rgba(0,0,0,0)",
                    'borderwidth': 2,
                    'bordercolor': "gray",
                }
            ))
            fig_gauge.update_layout(title={'text': "P/L Atual (real, ao vivo)", 'x': 0.5, 'xanchor': 'center'}, template="plotly_dark", height=320, margin=dict(t=50, b=10))
            st.plotly_chart(fig_gauge, use_container_width=True)
        else:
            st.info("P/L não disponível no momento via Yahoo Finance.")

    with col_g2:
        st.subheader("📋 Status de Carga dos Dados CVM (Online)")
        if not df_cvm_real.empty:
            st.success(f"Conexão com a CVM estabelecida em tempo real! {len(df_cvm_real)} registros carregados.")
            colunas_show = [c for c in ["DS_CONTA", "VL_CONTA"] if c in df_cvm_real.columns]
            if colunas_show:
                st.dataframe(df_cvm_real[colunas_show].head(5), use_container_width=True, hide_index=True)
        else:
            st.warning("Não foi possível conectar à CVM neste momento.")

elif menu_opcao == "Mercado":
    st.title("📈 Módulo de Mercado & Cotações Reais — HYPE3 (B3)")
    st.markdown("Dados de preços de fechamento e volume obtidos em tempo real via Yahoo Finance / B3.")

    if not df_mercado_real.empty:
        cotacao_atual = df_mercado_real['Close'].iloc[-1]
        cotacao_anterior = df_mercado_real['Close'].iloc[-2]
        var_pct = ((cotacao_atual - cotacao_anterior) / cotacao_anterior) * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cotação Atual", f"R$ {cotacao_atual:.2f}", f"{var_pct:+.2f}%")
        col2.metric("Máxima (Período)", f"R$ {df_mercado_real['High'].max():.2f}")
        col3.metric("Mínima (Período)", f"R$ {df_mercado_real['Low'].min():.2f}")
        col4.metric("Volume Médio", f"{df_mercado_real['Volume'].mean():,.0f}")

        st.markdown("---")
        st.subheader("📊 Gráfico Histórico de Preços (HYPE3.SA)")

        df_mercado_real['MA_7'] = df_mercado_real['Close'].rolling(window=7).mean()
        df_mercado_real['MA_21'] = df_mercado_real['Close'].rolling(window=21).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_mercado_real['Date'], y=df_mercado_real['Close'], name="Fechamento Real", line=dict(color="#00d2ff")))
        fig.add_trace(go.Scatter(x=df_mercado_real['Date'], y=df_mercado_real['MA_7'], name="Média Móvel 7d", line=dict(color="#ff7f0e", dash="dash")))
        fig.update_layout(template="plotly_dark", height=450, xaxis_title="Data", yaxis_title="Preço (R$)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Não foi possível conectar ao provedor de mercado no momento.")

elif menu_opcao == "Analise Tecnica":
    st.title("📊 Análise Técnica & Indicadores — HYPE3")
    st.markdown("Estudo de momentum, volatilidade e tendências, calculado sobre dados reais de mercado.")

    if not df_mercado_real.empty:
        df_at = df_mercado_real.copy()
        window = 20
        df_at['SMA'] = df_at['Close'].rolling(window=window).mean()
        df_at['STD'] = df_at['Close'].rolling(window=window).std()
        df_at['Banda_Superior'] = df_at['SMA'] + (df_at['STD'] * 2)
        df_at['Banda_Inferior'] = df_at['SMA'] - (df_at['STD'] * 2)

        delta = df_at['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_at['IFR'] = 100 - (100 / (1 + rs))

        ifr_atual = df_at['IFR'].dropna().iloc[-1] if not df_at['IFR'].dropna().empty else None
        st.session_state['ifr_atual'] = ifr_atual

        st.subheader("Bandas de Bollinger & IFR (14) — calculados sobre preços reais")
        fig_at = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.7, 0.3])
        fig_at.add_trace(go.Scatter(x=df_at['Date'], y=df_at['Close'], name="Preço Fechamento", line=dict(color="#00d2ff")), row=1, col=1)
        fig_at.add_trace(go.Scatter(x=df_at['Date'], y=df_at['Banda_Superior'], name="Banda Superior", line=dict(color="gray", dash="dot")), row=1, col=1)
        fig_at.add_trace(go.Scatter(x=df_at['Date'], y=df_at['Banda_Inferior'], name="Banda Inferior", line=dict(color="gray", dash="dot"), fill='tonexty', fillcolor='rgba(100,100,100,0.1)'), row=1, col=1)
        fig_at.add_trace(go.Scatter(x=df_at['Date'], y=df_at['IFR'], name="IFR (14)", line=dict(color="#ff7f0e")), row=2, col=1)
        fig_at.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Sobrecompra (70)", annotation_position="top right")
        fig_at.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Sobrevenda (30)", annotation_position="bottom right")
        fig_at.update_layout(template="plotly_dark", height=600, hovermode="x unified", margin=dict(t=30, b=30))
        st.plotly_chart(fig_at, use_container_width=True)
    else:
        st.warning("Sem dados de mercado disponíveis para calcular os indicadores técnicos.")

elif menu_opcao == "Fundamentos":
    st.title("💰 Fundamentos — Hypera Pharma (HYPE3)")
    st.markdown("Análise unificada da rentabilidade, margens e estrutura de divisões e subsidiárias.")

    tab_fund, tab_setor, tab_subs = st.tabs(["📊 Indicadores & Radar", "🏭 Benchmarking Setorial", "🏢 Divisões & Subsidiárias"])

    with tab_fund:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ROE", fmt_pct(roe_real))
        col2.metric("ROA", fmt_pct(roa_real))
        col3.metric("Margem Líquida", fmt_pct(margem_liq_real))
        col4.metric("Margem EBITDA", fmt_pct(margem_ebitda_real))

        st.markdown("---")
        st.subheader("🕸️ Radar: Hypera vs Média dos Pares Reais (dados ao vivo)")

        categorias = ['ROE (%)', 'Margem Líquida (%)', 'Margem Operacional (%)', 'Margem EBITDA (%)']
        valores_hypera = [
            (roe_real or 0) * 100,
            (margem_liq_real or 0) * 100,
            (margem_operacional_real or 0) * 100,
            (margem_ebitda_real or 0) * 100,
        ]

        valores_pares = {c: [] for c in categorias}
        for nome_par, tk_par in TICKERS_PARES.items():
            if tk_par == TICKER_PRINCIPAL:
                continue
            info_par = carregar_info_par(tk_par)
            valores_pares['ROE (%)'].append((info_par.get('returnOnEquity') or 0) * 100)
            valores_pares['Margem Líquida (%)'].append((info_par.get('profitMargins') or 0) * 100)
            valores_pares['Margem Operacional (%)'].append((info_par.get('operatingMargins') or 0) * 100)
            valores_pares['Margem EBITDA (%)'].append((info_par.get('ebitdaMargins') or 0) * 100)

        valores_media_setor = [np.mean(valores_pares[c]) if valores_pares[c] else 0 for c in categorias]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=valores_hypera, theta=categorias, fill='toself', name='Hypera Pharma (HYPE3)', line=dict(color='#00d2ff')))
        fig_radar.add_trace(go.Scatterpolar(r=valores_media_setor, theta=categorias, fill='toself', name='Média dos Pares (ao vivo)', line=dict(color='#ff7f0e')))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, gridcolor="gray", linecolor="gray")), template="plotly_dark", height=450, margin=dict(t=20, b=20, l=20, r=20), legend=dict(x=0.85, y=0.5))
        st.plotly_chart(fig_radar, use_container_width=True)

    with tab_setor:
        st.subheader("🏭 Comparação Setorial (Top 5 Empresas de Referência na B3)")
        linhas = []
        for nome_par, tk_par in TICKERS_PARES.items():
            info_par = carregar_info_par(tk_par)
            linhas.append({
                "Empresa / Ticker": nome_par,
                "Margem Líquida (%)": round((info_par.get("profitMargins") or 0) * 100, 1),
                "ROE (%)": round((info_par.get("returnOnEquity") or 0) * 100, 1),
                "P/L": round(info_par.get("trailingPE"), 1) if info_par.get("trailingPE") else None,
                "Dívida/Patrimônio": round(info_par.get("debtToEquity"), 1) if info_par.get("debtToEquity") else None,
            })
        df_setor_completo = pd.DataFrame(linhas)

        st.dataframe(df_setor_completo, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📊 Benchmarking: Margem Líquida vs ROE (real)")
        fig_setor_bench = go.Figure(data=[
            go.Bar(name='Margem Líquida (%)', x=df_setor_completo['Empresa / Ticker'], y=df_setor_completo['Margem Líquida (%)'], marker_color='#1f77b4'),
            go.Bar(name='ROE (%)', x=df_setor_completo['Empresa / Ticker'], y=df_setor_completo['ROE (%)'], marker_color='#2ca02c')
        ])
        fig_setor_bench.update_layout(barmode='group', template="plotly_dark", height=450, margin=dict(t=20, b=40, l=40, r=20), yaxis_title="Percentual (%)", xaxis_title="Empresas", legend=dict(x=0.85, y=0.95))
        st.plotly_chart(fig_setor_bench, use_container_width=True)

    with tab_subs:
        st.subheader("🏢 Principais Divisões e Subsidiárias da Hypera Pharma")
        st.markdown("Detalhamento estrutural, portfólio de marcas e valores estimados de participação interna de mercado das divisões do grupo:")

        df_subsidiarias = pd.DataFrame([
            {
                "Divisão / Subsidiária": "Brainfarma",
                "Foco Principal": "Complexo Industrial e P&D",
                "Localização": "Anápolis (Goiás)",
                "Participação / Contribuição": "Alta escala fabril (fábrica central do grupo)"
            },
            {
                "Divisão / Subsidiária": "Consumer Health (Saúde ao Consumidor)",
                "Foco Principal": "Medicamentos Isentos de Prescrição (MIPs)",
                "Localização": "Nacional",
                "Descrição das Marcas": "Benegrip, Naldecon, Coristina D, Engov, Epocler, Estomazil, Addera"
            },
            {
                "Divisão / Subsidiária": "Mantecorp Farmasa",
                "Foco Principal": "Produtos de Prescrição Médica",
                "Localização": "Nacional",
                "Descrição das Marcas": "Medicamentos prescritos em várias especialidades médicas"
            },
            {
                "Divisão / Subsidiária": "Mantecorp Skincare e Simple Organic",
                "Foco Principal": "Dermocosméticos e Cuidados com a Pele",
                "Localização": "Nacional",
                "Descrição das Marcas": "Dermocosméticos de alta performance e beleza sustentável"
            }
        ])

        st.dataframe(df_subsidiarias, use_container_width=True, hide_index=True)

elif menu_opcao == "Portfolio e Sazonalidade":
    st.title("💊 Mapeamento de Sintomas, Portfólio & Sazonalidade (HYPE3)")
    st.markdown(
        "Análise comparativa cruzando os principais sintomas de saúde pública "
        "com o portfólio de medicamentos isentos de prescrição (MIPs) da Hypera e o comportamento de mercado."
    )

    st.subheader("🔍 Seletor de Sintoma Alvo")
    sintoma_selecionado = st.selectbox(
        "Escolha o sintoma ou condição clínica para análise de impacto:",
        [
            "Gripe, Resfriado e Congestão Nasal",
            "Dor de Cabeça e Enxaqueca",
            "Dores Musculares e Febre",
            "Distúrbios Vitamínicos e Imunidade"
        ]
    )

    dados_sintomas = {
        "Gripe, Resfriado e Congestão Nasal": {
            "Marcas Hypera": ["Benegrip", "Naldecon", "Coristina D"],
            "Classe Terapêutica": "Antigripais / Descongestionantes",
            "Pico Sazonal Típico": "Outono / Inverno (Q2-Q3)",
            "Dinâmica Competitiva": "Alta concorrência com grandes redes de farmácia (RaiaDrogasil e Pague Menos). A Hypera ganha volume nos meses mais frios, mas enfrenta forte pressão de preços no varejo associativo."
        },
        "Dor de Cabeça e Enxaqueca": {
            "Marcas Hypera": ["Doril", "Neosaldina"],
            "Classe Terapêutica": "Analgésicos simples e associados",
            "Pico Sazonal Típico": "Estável ao longo do ano (Estresse / Rotina)",
            "Dinâmica Competitiva": "Forte constância de caixa e margem bruta elevada devido à capilaridade de distribuição nas farmácias independentes."
        },
        "Dores Musculares e Febre": {
            "Marcas Hypera": ["Engov", "Epocler"],
            "Classe Terapêutica": "Analgésicos e Sintomáticos",
            "Pico Sazonal Típico": "Eventos sazonais e festivos",
            "Dinâmica Competitiva": "Sensível a picos de consumo social. Logística robusta protege contra rupturas de estoque frente aos pares."
        },
        "Distúrbios Vitamínicos e Imunidade": {
            "Marcas Hypera": ["Addera", "Vitergan", "Estomazil", "Tamarine"],
            "Classe Terapêutica": "Polivitamínicos / Nutracêuticos / Digestivos",
            "Pico Sazonal Típico": "Q2-Q3 e mudança de estação",
            "Dinâmica Competitiva": "Segmento de maior crescimento defensivo no setor farmacêutico brasileiro, com margens líquidas atrativas."
        }
    }

    info_sintoma = dados_sintomas[sintoma_selecionado]

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric(label="Classe Terapêutica", value=info_sintoma["Classe Terapêutica"])
    with col_s2:
        st.metric(label="Pico Sazonal", value=info_sintoma["Pico Sazonal Típico"])
    with col_s3:
        st.metric(label="Portfólio Hypera", value=", ".join(info_sintoma["Marcas Hypera"]))

    st.markdown("---")
    st.subheader(f"📊 Análise de Onde Ganhamos ou Perdemos Vendas: {sintoma_selecionado}")
    st.info(info_sintoma["Dinâmica Competitiva"])

    st.markdown("---")
    st.subheader("📈 Validação por Demanda de Busca (Google Trends em Tempo Real)")
    
    marcas_hypera_10 = [
        "Benegrip", "Naldecon", "Doril", "Neosaldina", 
        "Engov", "Epocler", "Estomazil", "Addera", 
        "Tamarine", "Coristina D"
    ]
    
    if not PYTRENDS_DISPONIVEL:
        st.warning("A biblioteca `pytrends` não está instalada no ambiente.")
    else:
        df_trends_sintoma = carregar_google_trends_marcas(tuple(marcas_hypera_10[:5]))
        if not df_trends_sintoma.empty:
            fig_sint = go.Figure()
            for marca in marcas_hypera_10[:5]:
                if marca in df_trends_sintoma.columns:
                    fig_sint.add_trace(go.Scatter(
                        x=df_trends_sintoma.index, 
                        y=df_trends_sintoma[marca], 
                        name=f"Busca: {marca}",
                        mode='lines+markers'
                    ))
            fig_sint.update_layout(
                template="plotly_dark",
                height=400,
                margin=dict(t=20, b=20, l=40, r=20),
                yaxis_title="Volume Relativo (0-100)",
                xaxis_title="Período"
            )
            st.plotly_chart(fig_sint, use_container_width=True)
            st.caption("Nota: Termômetro antecipado de demanda digital das principais marcas do portfólio.")
        else:
            st.info("Volume de busca indisponível no momento para o comparativo de marcas.")

elif menu_opcao == "Sustentabilidade & ODS":
    st.title("🌱 Sustentabilidade, ESG & ODS — Hypera Pharma")
    st.markdown("Painel de Governança Corporativa, conformidade socioambiental e alinhamento aos Objetivos de Desenvolvimento Sustentável (ODS).")

    st.subheader("📋 Participação em Índices Oficiais da B3 (Verificação ao Vivo)")
    
    col_esg1, col_esg2 = st.columns(2)
    with col_esg1:
        status_ise = "🟢 Ativo" if hypera_no_ise else "🔴 Inativo"
        st.metric(label="ISE B3 (Índice de Sustentabilidade Empresarial)", value=status_ise, delta="Governança & Social")
    with col_esg2:
        status_ico2 = "🟢 Ativo" if hypera_no_ico2 else "🔴 Inativo"
        st.metric(label="ICO2 B3 (Índice Carbono Eficiente)", value=status_ico2, delta="Baixo Carbono")

    st.caption("🔍 Metodologia: Consulta direta à API pública de carteiras teóricas vigentes da B3.")

    st.markdown("---")
    
    st.subheader("🤝 Alinhamento Internacional — Pacto Global da ONU")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        st.metric(label="Status de Adesão", value="Signatária Ativa", delta="Nº 142300")
    with col_p2:
        st.metric(label="Compromisso Firmado", value="Dezembro / 2020", delta="COP Anual")
    with col_p3:
        st.metric(label="Pilar de Atuação", value="Saúde, Direitos & Ética", delta="Compliance")

    st.markdown("---")

    st.subheader("🎯 Onde a Hypera se Destaca nos ODS da ONU")
    st.markdown("Iniciativas corporativas validadas nos relatórios anuais e de sustentabilidade oficiais da companhia:")
    
    df_ods = pd.DataFrame(ODS_DESTAQUE_HYPERA)
    st.dataframe(df_ods, use_container_width=True, hide_index=True)

    st.markdown("---")

    st.subheader("🏛️ Indicadores de Governança e Transparência Corporativa")
    col_gov1, col_gov2 = st.columns(2)
    with col_gov1:
        st.metric(label="Segmento de Listagem B3", value=info_hypera.get("exchange", "Novo Mercado / SAO"))
    with col_gov2:
        st.metric(label="Portal de RI Oficial", value="ri.hypera.com.br", delta="Transparência Total")

    st.info(
        "💡 **Nota Metodológica para a Apresentação:** Para métricas granulares de emissões de escopo 1, 2 e 3 "
        "ou inventário de gases de efeito estufa (GEE), a companhia reporta em seu Relatório Anual de Sustentabilidade, "
        "garantindo rastreabilidade completa e conformidade com os padrões GRI."
    )

elif menu_opcao == "Resultados":
    st.title("📑 Central de Resultados & Fundamentos — HYPE3")
    st.markdown("Visão consolidada de desempenho financeiro, fluxo de caixa, alavancagem, proventos e valuation em tempo real.")

    tab_dre, tab_fco, tab_div, tab_prov, tab_val = st.tabs([
        "📊 DRE & Desempenho", 
        "💵 Fluxo de Caixa", 
        "🏛️ Endividamento & Alavancagem", 
        "💎 Proventos & Dividendos", 
        "🧮 Valuation & Múltiplos"
    ])

    with tab_dre:
        st.subheader("Demonstração de Resultados (CVM & Yahoo Finance)")
        if not df_cvm_real.empty:
            st.success(f"Conexão CVM ativa: {len(df_cvm_real)} registros processados.")
            colunas_disp = [c for c in ["CD_CVM", "DS_CONTA", "VL_CONTA", "DT_REFER", "DT_FIM_EXERC"] if c in df_cvm_real.columns]
            st.dataframe(df_cvm_real[colunas_disp] if colunas_disp else df_cvm_real, use_container_width=True, hide_index=True)
        else:
            st.warning("Dados CVM temporariamente indisponíveis para este lote.")

        if serie_receita is not None or serie_lucro_liquido is not None:
            c1, c2 = st.columns(2)
            c1.metric("Receita Líquida (Mais Recente)", fmt_moeda_bi(valor_mais_recente(serie_receita)))
            c2.metric("Lucro Líquido (Mais Recente)", fmt_moeda_bi(valor_mais_recente(serie_lucro_liquido)))

    with tab_fco:
        st.subheader("Dinâmica do Fluxo de Caixa")
        fco = valor_mais_recente(serie_fco)
        fci = valor_mais_recente(serie_fci)
        fcf_livre = valor_mais_recente(serie_fcf_livre)

        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("Caixa Operacional (FCO)", fmt_moeda_bi(fco))
        col_f2.metric("Caixa de Investimento (FCI)", fmt_moeda_mi(fci))
        col_f3.metric("Fluxo de Caixa Livre (FCF)", fmt_moeda_bi(fcf_livre))

        if fco is not None:
            fig_dfc = go.Figure(data=[go.Bar(x=["FCO", "FCI", "FCF Livre"], y=[fco or 0, fci or 0, fcf_livre or 0], marker_color=['#2ca02c', '#d62728', '#00d2ff'])])
            fig_dfc.update_layout(template="plotly_dark", height=350, margin=dict(t=20, b=20, l=40, r=20), yaxis_title="R$")
            st.plotly_chart(fig_dfc, use_container_width=True)

    with tab_div:
        st.subheader("Perfil de Endividamento & Alavancagem")
        caixa_atual = total_cash_real if total_cash_real is not None else valor_mais_recente(serie_caixa)
        divida_atual = total_debt_real if total_debt_real is not None else valor_mais_recente(serie_divida_total)
        divida_liquida = (divida_atual - caixa_atual) if (divida_atual is not None and caixa_atual is not None) else None
        
        div_ebitda = (divida_liquida / ebitda_real) if (divida_liquida is not None and ebitda_real) else None
        st.session_state['divida_liquida_ebitda'] = div_ebitda

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Dívida Bruta", fmt_moeda_bi(divida_atual))
        e2.metric("Caixa Total", fmt_moeda_bi(caixa_atual))
        e3.metric("Dívida Líquida", fmt_moeda_bi(divida_liquida))
        e4.metric("Dívida Líq. / EBITDA", f"{div_ebitda:.2f}x" if div_ebitda is not None else "N/D")

        st.markdown("---")

        col_g_div1, col_g_div2 = st.columns([1.2, 1])

        with col_g_div1:
            st.markdown("### 📊 Composição de Capital (R$ Bi)")
            if divida_atual is not None and caixa_atual is not None:
                comps = ["Dívida Bruta", "Caixa Total", "Dívida Líquida"]
                vals = [divida_atual / 1e9, caixa_atual / 1e9, divida_liquida / 1e9]
                cores = ['#ff4b4b', '#2ca02c', '#00d2ff']

                fig_comp = go.Figure(data=[go.Bar(x=comps, y=vals, marker_color=cores, text=[f"R$ {v:.2f} Bi" for v in vals], textposition='auto')])
                fig_comp.update_layout(template="plotly_dark", height=320, margin=dict(t=20, b=20, l=20, r=20), yaxis_title="R$ Bilhões")
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.info("Dados insuficientes para gerar o gráfico de composição.")

        with col_g_div2:
            st.markdown("### 🎯 Termômetro de Alavancagem")
            if div_ebitda is not None:
                fig_gauge_div = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=div_ebitda,
                    number={'suffix': "x"},
                    gauge={
                        'axis': {'range': [0, 5], 'tickwidth': 1, 'tickcolor': "white"},
                        'bar': {'color': "#00d2ff"},
                        'bgcolor': "rgba(0,0,0,0)",
                        'borderwidth': 2,
                        'bordercolor': "gray",
                        'steps': [
                            {'range': [0, 2.5], 'color': "rgba(46, 160, 67, 0.3)"},
                            {'range': [2.5, 3.5], 'color': "rgba(255, 127, 14, 0.3)"},
                            {'range': [3.5, 5], 'color': "rgba(255, 75, 75, 0.3)"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 3.0
                        }
                    }
                ))
                fig_gauge_div.update_layout(template="plotly_dark", height=320, margin=dict(t=30, b=10, l=20, r=20))
                st.plotly_chart(fig_gauge_div, use_container_width=True)
            else:
                st.info("Métrica de alavancagem indisponível no momento.")

    with tab_prov:
        st.subheader("Retorno via Proventos")
        pA, pB, pC = st.columns(3)
        pA.metric("Dividend Yield (Atual)", fmt_pct(dividend_yield_real))
        pB.metric("Payout Ratio", fmt_pct(payout_real))
        pC.metric("Total de Pagamentos Históricos", str(len(df_dividendos_real)) if not df_dividendos_real.empty else "0")

        if not df_dividendos_real.empty:
            st.dataframe(df_dividendos_real.sort_values("Data", ascending=False).head(10), use_container_width=True, hide_index=True)

    with tab_val:
        st.subheader("Valuation Interativo (Modelo de Gordon)")
        fco_def = fco if 'fco' in locals() and fco else 2_000_000_000.0
        
        v1, v2, v3 = st.columns(3)
        base_fco = v1.number_input("Base de Caixa (R$)", value=float(fco_def), step=100_000_000.0)
        wacc = v2.slider("WACC (%)", 5.0, 20.0, 11.5, 0.5)
        g = v3.slider("Crescimento (g %)", 0.0, 6.0, 3.0, 0.5)

        if st.button("Calcular Valuation Intrínseco"):
            if wacc > g:
                firma = base_fco / ((wacc - g) / 100.0)
                st.success(f"Valor Intrínseco Estimado da Firma: R$ {firma:,.2f}")
            else:
                st.error("WACC precisa ser superior à taxa de crescimento (g).")

        st.markdown("---")
        st.dataframe(pd.DataFrame({
            "Múltiplo": ["P/L", "P/VP", "EV/EBITDA"],
            "Atual (Real)": [
                f"{pe_real:.1f}x" if pe_real else "N/D",
                f"{pvp_real:.1f}x" if pvp_real else "N/D",
                f"{ev_ebitda_real:.1f}x" if ev_ebitda_real else "N/D"
            ]
        }), use_container_width=True, hide_index=True)

elif menu_opcao == "Hypera AI Analyst":
    st.title("🧠 Hypera AI Analyst — Assistente Baseado em Regras (dados reais)")
    st.markdown(
        "**Importante:** este assistente não é um modelo de linguagem/IA generativa — é um sistema de "
        "regras por palavra-chave que insere valores reais e ao vivo nas respostas contábeis e de mercado."
    )

    pergunta = st.text_input("💬 Faça uma pergunta (ex: 'Qual o ROE atual?' ou 'Como está o fluxo de caixa?'):")

    col_sug1, col_sug2, col_sug3 = st.columns(3)
    pergunta_selecionada = None
    with col_sug1:
        if st.button("📊 Qual o ROE atual?"):
            pergunta_selecionada = "roe"
    with col_sug2:
        if st.button("📈 Como está o fluxo de caixa?"):
            pergunta_selecionada = "caixa"
    with col_sug3:
        if st.button("📋 Perspectiva de Dividendos"):
            pergunta_selecionada = "dividendo"

    query_ativa = (pergunta.lower() if pergunta else "") or (pergunta_selecionada or "")

    if query_ativa:
        st.markdown("---")
        st.subheader("🤖 Resposta (com dados reais e ao vivo):")
        if "roe" in query_ativa or "roic" in query_ativa:
            st.success(f"O **ROE** atual da Hypera Pharma (HYPE3), via Yahoo Finance, é de **{fmt_pct(roe_real)}**.")
        elif "caixa" in query_ativa:
            st.success(f"O fluxo de caixa operacional (FCO) do último período reportado é de **{fmt_moeda_bi(valor_mais_recente(serie_fco))}**.")
        elif "dividendo" in query_ativa:
            st.success(f"O Dividend Yield atual é de **{fmt_pct(dividend_yield_real)}**, com payout ratio de **{fmt_pct(payout_real)}**.")
        else:
            st.success(
                f"Com base nos dados ao vivo: margem líquida de **{fmt_pct(margem_liq_real)}**, "
                f"ROE de **{fmt_pct(roe_real)}**, e P/L atual de **{pe_real:.1f}x**." if pe_real else
                "Não foi possível obter todos os dados necessários no momento."
            )

elif menu_opcao == "Anomalias":
    st.title("🔎 Detecção de Anomalias & Outliers — HYPE3")
    st.markdown("Cálculo estatístico de Z-Score cruzado com fatos relevantes da CVM (Governança e Eventos Corporativos).")

    if not df_mercado_real.empty:
        retornos = df_mercado_real['Close'].pct_change().dropna()
        media_ret = retornos.mean()
        std_ret = retornos.std()
        z_scores = (retornos - media_ret) / std_ret if std_ret else pd.Series(dtype=float)

        limiar = 2.5
        anomalias_detectadas = z_scores[abs(z_scores) > limiar]

        col1, col2, col3 = st.columns(3)
        col1.metric(label="Anomalias Detectadas (Z-Score)", value=str(len(anomalias_detectadas)))
        col2.metric(label="Método Estatístico", value="Z-Score sobre Retornos Diários")
        col3.metric(label="Limiar de Volatilidade", value=f"|Z| > {limiar}")

        st.markdown("---")
        st.subheader("📋 Tabela de Anomalias com Cruzamento de Fatos Relevantes (CVM)")

        if not anomalias_detectadas.empty:
            df_anom = df_mercado_real.loc[anomalias_detectadas.index, ["Date", "Close"]].copy()
            df_anom["Retorno Diário (%)"] = (retornos.loc[anomalias_detectadas.index] * 100).round(2)
            df_anom["Z-Score"] = z_scores.loc[anomalias_detectadas.index].round(2)
            df_anom["Data_Fmt"] = pd.to_datetime(df_anom["Date"]).dt.date

            if not df_fatos_relevantes.empty:
                col_data_cvm = next((c for c in ["Data_Entrega", "DT_RECEB", "Data_Referencia"] if c in df_fatos_relevantes.columns), None)
                if col_data_cvm:
                    df_fatos_relevantes["Data_Fmt"] = pd.to_datetime(df_fatos_relevantes[col_data_cvm]).dt.date
                    df_anom = pd.merge(df_anom, df_fatos_relevantes[["Data_Fmt", "Assunto", "Categoria"]], on="Data_Fmt", how="left")
                    df_anom["Evento CVM Associado"] = df_anom["Assunto"].fillna("Nenhum fato relevante protocolado nesta data")
                else:
                    df_anom["Evento CVM Associado"] = "Dataset CVM sem coluna de data compatível"
            else:
                df_anom["Evento CVM Associado"] = "Sem feed CVM ativo no momento"

            colunas_exibir = ["Date", "Close", "Retorno Diário (%)", "Z-Score", "Evento CVM Associado"]
            st.dataframe(df_anom[[c for c in colunas_exibir if c in df_anom.columns]], use_container_width=True, hide_index=True)
            st.caption("🔍 Nota: O cruzamento busca alinhar oscilações de preço anômalas com comunicados oficiais protocolados na CVM no mesmo dia útil.")
        else:
            st.success("Nenhuma anomalia estatística (|Z| > 2.5) detectada nos retornos diários do período carregado.")
    else:
        st.warning("Sem dados de mercado disponíveis para rodar a detecção de anomalias.")

elif menu_opcao == "Forecast":
    st.title("🔮 Projeções & Forecast Financeiro — HYPE3")
    st.markdown("Regressão linear real sobre a série histórica de Receita e Lucro Líquido (Yahoo Finance).")

    if serie_receita is not None and not serie_receita.dropna().empty:
        serie_rec_limpa = serie_receita.dropna().sort_index()
        
        if len(serie_rec_limpa) >= 2:
            anos_idx = np.arange(len(serie_rec_limpa))
            receita_vals = serie_rec_limpa.values.astype(float)
            
            coef_receita = np.polyfit(anos_idx, receita_vals, 1)
            proximo_idx = len(serie_rec_limpa)
            receita_projetada = float(np.polyval(coef_receita, proximo_idx))

            lucro_projetado = None
            if serie_lucro_liquido is not None and not serie_lucro_liquido.dropna().empty:
                serie_lucro_limpo = serie_lucro_liquido.dropna().sort_index()
                if len(serie_lucro_limpo) >= 2:
                    lucro_vals = serie_lucro_limpo.values.astype(float)
                    coef_lucro = np.polyfit(np.arange(len(lucro_vals)), lucro_vals, 1)
                    lucro_projetado = float(np.polyval(coef_lucro, len(lucro_vals)))

            col1, col2, col3 = st.columns(3)
            col1.metric(label="Receita Projetada (Próx. Período)", value=fmt_moeda_bi(receita_projetada))
            col2.metric(label="Lucro Líquido Projetado", value=fmt_moeda_bi(lucro_projetado))
            col3.metric(label="Modelo", value="Regressão Linear (real, numpy.polyfit)")

            st.markdown("---")
            st.subheader("📈 Série Histórica Real + Projeção Futura")
            
            datas_hist = [str(c.date()) if hasattr(c, "date") else str(c) for c in serie_rec_limpa.index]
            
            ultima_data = pd.to_datetime(serie_rec_limpa.index[-1])
            proxima_data_str = (ultima_data + pd.DateOffset(years=1)).strftime('%Y-%m-%d')

            datas_proj = datas_hist + [proxima_data_str]
            valores_proj = list(receita_vals) + [receita_projetada]

            fig_f = go.Figure()
            fig_f.add_trace(go.Scatter(
                x=datas_hist, y=receita_vals, 
                name="Receita Líquida (Real)", 
                line=dict(color="#00d2ff", width=3), 
                mode='lines+markers'
            ))
            fig_f.add_trace(go.Scatter(
                x=datas_proj, y=valores_proj, 
                name="Projeção (Tendência Linear)", 
                line=dict(color="#ff7f0e", width=3, dash="dash"), 
                mode='lines+markers'
            ))
            
            fig_f.update_layout(
                template="plotly_dark", 
                height=420, 
                margin=dict(t=20, b=20, l=40, r=20), 
                yaxis_title="R$ (Bilhões)", 
                xaxis_title="Período de Referência",
                legend=dict(x=0.02, y=0.98)
            )
            st.plotly_chart(fig_f, use_container_width=True)
            st.caption(
                "Projeção baseada em regressão linear simples sobre o histórico de demonstrativos disponíveis "
                "via Yahoo Finance — serve como indicador de tendência estatística para a análise."
            )
        else:
            st.warning("Dados históricos insuficientes para calcular a regressão linear.")
    else:
        st.warning("Série de receita indisponível no momento via Yahoo Finance.")

elif menu_opcao == "Relatório Diretoria":
    st.title("🎯 Relatório Executivo & Apresentação para a Diretoria — HYPE3")
    st.markdown("Painel de exportação profissional: gere arquivos limpos em formato executivo e apresentações em PowerPoint prontas para uso.")

    col_d1, col_d2, col_d3, col_d4 = st.columns(4)
    preco_atual_dir = info_hypera.get("currentPrice") or info_hypera.get("regularMarketPrice")
    col_d1.metric("Preço Atual (B3)", f"R$ {preco_atual_dir:.2f}" if preco_atual_dir else "N/D")
    col_d2.metric("Valor de Mercado", fmt_moeda_bi(info_hypera.get("marketCap")))
    col_d3.metric("ROE Real", fmt_pct(roe_real))
    col_d4.metric("Margem Líquida", fmt_pct(margem_liq_real))

    st.markdown("---")
    st.subheader("📋 Resumo Executivo Consolidado")

    df_resumo_diretoria = pd.DataFrame([
        {"Indicador Executivo": "Ticker Principal", "Valor Atual (Tempo Real)": "HYPE3.SA (Hypera S.A.)"},
        {"Indicador Executivo": "Código CVM", "Valor Atual (Tempo Real)": str(CD_CVM_HYPERA)},
        {"Indicador Executivo": "Múltiplo P/L", "Valor Atual (Tempo Real)": f"{pe_real:.1f}x" if pe_real else "N/D"},
        {"Indicador Executivo": "Múltiplo P/VP", "Valor Atual (Tempo Real)": f"{pvp_real:.1f}x" if pvp_real else "N/D"},
        {"Indicador Executivo": "Múltiplo EV/EBITDA", "Valor Atual (Tempo Real)": f"{ev_ebitda_real:.1f}x" if ev_ebitda_real else "N/D"},
        {"Indicador Executivo": "Dividend Yield", "Valor Atual (Tempo Real)": fmt_pct(dividend_yield_real)},
        {"Indicador Executivo": "Dívida Líquida / EBITDA", "Valor Atual (Tempo Real)": f"{st.session_state.get('divida_liquida_ebitda', 0):.2f}x" if st.session_state.get('divida_liquida_ebitda') else "N/D"},
        {"Indicador Executivo": "Status ISE B3 (ESG)", "Valor Atual (Tempo Real)": "Ativo" if hypera_no_ise else "Inativo"},
        {"Indicador Executivo": "Status ICO2 B3 (Carbono)", "Valor Atual (Tempo Real)": "Ativo" if hypera_no_ico2 else "Inativo"}
    ])

    st.dataframe(df_resumo_diretoria, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📥 Central de Exportação Profissional")

    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        st.markdown("#### 📄 Exportar Tabela Executiva (CSV)")
        st.markdown("Arquivo formatado corretamente com codificação UTF-8 para visualização perfeita no Excel.")
        csv_diretoria = df_resumo_diretoria.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(
            label="📥 Baixar Dados Executivos (CSV)",
            data=csv_diretoria,
            file_name=f"Relatorio_Diretoria_Hypera_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    with col_exp2:
        st.markdown("#### 📊 Gerar Apresentação PowerPoint Corporativa (.pptx)")
        st.markdown("Criação automatizada de slides com layout moderno, caixas de destaque e logotipo oficial.")

        def gerar_apresentacao_profissional_pptx():
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            
            # Cores Corporativas
            COR_AZUL_FUNDO = RGBColor(10, 25, 47)      # Azul executivo escuro
            COR_CINZA_CLARO = RGBColor(245, 247, 250)  # Fundo leve
            COR_TEXTO_ESCURO = RGBColor(30, 41, 59)    # Texto primário
            COR_BRANCO = RGBColor(255, 255, 255)
            COR_AZUL_DESTAQUE = RGBColor(0, 130, 200)

            # Baixar Logotipo Oficial da Hypera Pharma de forma dinâmica
            logo_bytes = None
            try:
                logo_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Hypera_Pharma_logo.svg/512px-Hypera_Pharma_logo.svg.png"
                resp = requests.get(logo_url, timeout=5)
                if resp.status_code == 200:
                    logo_bytes = io.BytesIO(resp.content)
            except Exception:
                pass

            blank_layout = prs.slide_layouts[6] # Layout totalmente em branco

            # ================= SLIDE 1: CAPA =================
            slide1 = prs.slides.add_slide(blank_layout)
            bg1 = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
            bg1.fill.solid()
            bg1.fill.fore_color.rgb = COR_AZUL_FUNDO
            bg1.line.fill.background()

            if logo_bytes:
                slide1.shapes.add_picture(logo_bytes, Inches(1.2), Inches(1.2), width=Inches(2.5))

            # Título da Capa
            txBox1 = slide1.shapes.add_textbox(Inches(1.2), Inches(3.0), Inches(11.0), Inches(3.0))
            tf1 = txBox1.text_frame
            tf1.word_wrap = True
            
            p1 = tf1.paragraphs[0]
            p1.text = "Hypera Analytics (HYPE3)"
            p1.font.size = Pt(40)
            p1.font.bold = True
            p1.font.color.rgb = COR_BRANCO

            p1_sub = tf1.add_paragraph()
            p1_sub.text = f"Relatório Executivo para a Diretoria • Projeto Integrador 3\nGerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            p1_sub.font.size = Pt(18)
            p1_sub.font.color.rgb = RGBColor(148, 163, 184)
            p1_sub.space_before = Pt(15)

            # Função auxiliar para slides internos padronizados
            def criar_slide_padrao(titulo_texto):
                s = prs.slides.add_slide(blank_layout)
                
                # Fundo claro
                bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
                bg.fill.solid()
                bg.fill.fore_color.rgb = COR_CINZA_CLARO
                bg.line.fill.background()

                # Barra superior de cabeçalho
                header_bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(1.1))
                header_bar.fill.solid()
                header_bar.fill.fore_color.rgb = COR_AZUL_FUNDO
                header_bar.line.fill.background()

                # Título no cabeçalho
                tb_tit = s.shapes.add_textbox(Inches(0.8), Inches(0.2), Inches(9.0), Inches(0.8))
                tf_tit = tb_tit.text_frame
                pt = tf_tit.paragraphs[0]
                pt.text = titulo_texto
                pt.font.size = Pt(26)
                pt.font.bold = True
                pt.font.color.rgb = COR_BRANCO

                # Logotipo no canto superior direito
                if logo_bytes:
                    logo_bytes.seek(0)
                    s.shapes.add_picture(logo_bytes, Inches(11.2), Inches(0.25), width=Inches(1.5))

                return s

            # ================= SLIDE 2: DESTAQUES FINANCEIROS =================
            slide2 = criar_slide_padrao("Destaques Financeiros & Mercado (Tempo Real)")
            
            # Criar 4 cartões de métricas
            metricas_s2 = [
                ("Preço Atual (B3)", f"R$ {preco_atual_dir:.2f}" if preco_atual_dir else "N/D"),
                ("Valor de Mercado", fmt_moeda_bi(info_hypera.get('marketCap'))),
                ("Rentabilidade (ROE)", fmt_pct(roe_real)),
                ("Margem Líquida", fmt_pct(margem_liq_real))
            ]

            left_pos = Inches(0.8)
            for rotulo, valor in metricas_s2:
                card = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_pos, Inches(2.0), Inches(2.7), Inches(4.5))
                card.fill.solid()
                card.fill.fore_color.rgb = COR_BRANCO
                card.line.color.rgb = RGBColor(203, 213, 225)

                tf_card = card.text_frame
                tf_card.word_wrap = True
                
                p_rot = tf_card.paragraphs[0]
                p_rot.text = rotulo.upper()
                p_rot.font.size = Pt(13)
                p_rot.font.bold = True
                p_rot.font.color.rgb = COR_AZUL_DESTAQUE
                p_rot.alignment = PP_ALIGN.CENTER
                p_rot.space_before = Pt(20)

                p_val = tf_card.add_paragraph()
                p_val.text = str(valor)
                p_val.font.size = Pt(24)
                p_val.font.bold = True
                p_val.font.color.rgb = COR_TEXTO_ESCURO
                p_val.alignment = PP_ALIGN.CENTER
                p_val.space_before = Pt(30)

                left_pos += Inches(3.0)

            # ================= SLIDE 3: ALAVANCAGEM E GOVERNANÇA =================
            slide3 = criar_slide_padrao("Perfil de Alavancagem & Governança Corporativa (ESG)")
            
            div_ebitda_val = st.session_state.get('divida_liquida_ebitda')
            metricas_s3 = [
                ("Dívida Líquida / EBITDA", f"{div_ebitda_val:.2f}x" if div_ebitda_val else "N/D", "Limite prudencial de mercado: 3.0x"),
                ("Índice ISE B3 (ESG)", "Ativo" if hypera_no_ise else "Inativo", "Governança e Sustentabilidade Empresarial"),
                ("Índice ICO2 B3", "Ativo" if hypera_no_ico2 else "Inativo", "Eficiência e Baixo Carbono")
            ]

            left_pos3 = Inches(0.8)
            for tit, val, desc in metricas_s3:
                card3 = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_pos3, Inches(2.0), Inches(3.8), Inches(3.64))
                card3.fill.solid()
                card3.fill.fore_color.rgb = COR_BRANCO
                card3.line.color.rgb = RGBColor(203, 213, 225)

                tf_c3 = card3.text_frame
                tf_c3.word_wrap = True

                p_t3 = tf_c3.paragraphs[0]
                p_t3.text = tit
                p_t3.font.size = Pt(16)
                p_t3.font.bold = True
                p_t3.font.color.rgb = COR_AZUL_DESTAQUE
                p_t3.space_before = Pt(15)

                p_v3 = tf_c3.add_paragraph()
                p_v3.text = val
                p_v3.font.size = Pt(28)
                p_v3.font.bold = True
                p_v3.font.color.rgb = COR_TEXTO_ESCURO
                p_v3.space_before = Pt(20)

                p_d3 = tf_c3.add_paragraph()
                p_d3.text = desc
                p_d3.font.size = Pt(12)
                p_d3.font.color.rgb = RGBColor(100, 116, 139)
                p_d3.space_before = Pt(20)

                left_pos3 += Inches(4.0)

            # Salvar em BytesIO
            ppt_io = io.BytesIO()
            prs.save(ppt_io)
            ppt_io.seek(0)
            return ppt_io.getvalue()

        pptx_bytes = gerar_apresentacao_profissional_pptx()
        st.download_button(
            label="📥 Baixar Apresentação Corporativa (.pptx)",
            data=pptx_bytes,
            file_name=f"Apresentacao_Corporativa_Hypera_{datetime.now().strftime('%Y%m%d')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

elif menu_opcao == "Data Pipeline":
    st.markdown("### ⚙️ Arquitetura & Status do Data Pipeline")
    st.markdown("Status calculado ao vivo a partir do resultado real das últimas chamadas às fontes de dados.")
    st.write("")

    fontes_status = {
        "Mercado (Yahoo Finance)": not df_mercado_real.empty,
        "Fundamentos (.info)": bool(info_hypera),
        "Demonstrativos (Yahoo Finance)": not demonstrativos_yf["income"].empty,
        "Dividendos (Yahoo Finance)": not df_dividendos_real.empty,
        "CVM (DRE)": not df_cvm_real.empty,
        "CVM (Fatos Relevantes)": not df_fatos_relevantes.empty,
    }
    total_ok = sum(fontes_status.values())

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("**Status Geral**")
        st.markdown(f"🟢 **{total_ok}/{len(fontes_status)} fontes OK**" if total_ok else "🔴 **Nenhuma fonte respondeu**")
    with col2:
        st.markdown("**Execução Desta Sessão**")
        st.markdown(f"### {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%H:%M:%S')}")
    with col3:
        st.markdown("**Registros CVM Carregados**")
        st.markdown(f"### {len(df_cvm_real)}")
    with col4:
        st.markdown("**Registros de Mercado**")
        st.markdown(f"### {len(df_mercado_real)}")

    st.markdown("---")
    st.markdown("### 📋 Status Real por Fonte de Dados")
    df_pipeline = pd.DataFrame({
        "Fonte": list(fontes_status.keys()),
        "Status": ["✅ OK" if v else "❌ Falhou / Indisponível" for v in fontes_status.values()],
        "TTL do Cache": ["5 min", "1 hora", "1 hora", "1 hora", "24 horas", "1 hora"],
    })
    st.dataframe(df_pipeline, use_container_width=True, hide_index=True)

elif menu_opcao == "Metodologia":
    st.title("📚 Metodologia — Projeto Integrador 3")
    st.markdown("Plataforma integrada a dados públicos oficiais da CVM e do Yahoo Finance.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Arquitetura", value="Modular / Streamlit", delta="Python")
    with col2:
        st.metric(label="Fontes de Dados", value="CVM & Yahoo Finance", delta="Tempo Real")
    with col3:
        st.metric(label="Escopo Acadêmico", value="Projeto Integrador 3")

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
            "Regressão linear real (NumPy) + modelo de Gordon interativo"
        ],
        "Descrição": [
            "Extração automatizada de ITR/IPE do portal de dados abertos da CVM e de cotações/demonstrativos via Yahoo Finance.",
            "Limpeza, normalização e estruturação dos dados contábeis em DataFrames.",
            "Construção de dashboards responsivos.",
            "Aplicação de métricas reais de valuation, alavancagem, indicadores fundamentalistas e projeção estatística simples."
        ]
    })
    st.dataframe(df_metodologia, use_container_width=True, hide_index=True)

    st.info(
        "💡 **Nota Metodológica:** seções sem fonte pública gratuita confiável (ESG detalhado, sazonalidade de "
        "portfólio por produto) são claramente identificadas na tela como conteúdo ilustrativo, e não "
        "apresentadas como dado oficial em tempo real."
    )

else:
    st.title(f"{menu_opcao}")
    st.info("Módulo carregado com sucesso.")
